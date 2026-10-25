"""Notification channel, signed-link, and workflow-trigger behavior."""

import json
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import UUID, uuid4

import boto3
import pytest
from botocore.stub import Stubber
from fastapi.testclient import TestClient

from chainmind.core.config import Settings
from chainmind.core.errors import ChainMindError, IntegrationError
from chainmind.core.events import EventStore
from chainmind.core.models import (
    DecisionRequest,
    DecisionType,
    DisruptionEvent,
    DisruptionRun,
    PurchaseOrder,
    RunStatus,
    ShipmentTracking,
)
from chainmind.factory import create_pipeline
from chainmind.integrations.sap.mock_ariba import MockAribaClient
from chainmind.notifications.channels import EmailNotifier, SlackNotifier, TeamsNotifier
from chainmind.notifications.links import NotificationLinkSigner
from chainmind.notifications.service import NotificationService


class CaptureNotifier:
    def __init__(self) -> None:
        self.messages = []

    def send(self, message) -> None:
        self.messages.append(message)


@pytest.fixture
def fake_webhook():
    captured: list[dict[str, object]] = []
    statuses: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            captured.append(
                {
                    "path": self.path,
                    "content_type": self.headers["Content-Type"],
                    "payload": json.loads(self.rfile.read(length)),
                }
            )
            status = statuses.pop(0) if statuses else 200
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/webhook", captured, statuses
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def make_service(notifier: CaptureNotifier | None = None) -> NotificationService:
    return NotificationService(
        [notifier or CaptureNotifier()],
        NotificationLinkSigner("test-signing-secret-with-at-least-32-chars", 60),
        api_base_url="http://localhost:8000",
        dashboard_url="http://localhost:5173",
    )


def test_signed_links_validate_expiration_and_tampering() -> None:
    signer = NotificationLinkSigner("test-signing-secret-with-at-least-32-chars", 1)
    run_id = uuid4()
    token = signer.create(run_id, "approve", now=100)

    claims = signer.validate(token, now=159)
    assert claims.run_id == run_id
    assert claims.action == "approve"
    with pytest.raises(ChainMindError) as expired:
        signer.validate(token, now=160)
    assert expired.value.code == "expired_notification_link"

    encoded, signature = token.split(".")
    tampered = f"{encoded[:-1]}{'A' if encoded[-1] != 'A' else 'B'}.{signature}"
    with pytest.raises(ChainMindError) as invalid:
        signer.validate(tampered, now=120)
    assert invalid.value.code == "invalid_notification_link"


@pytest.mark.parametrize(
    ("notifier_type", "expected_key"),
    [(TeamsNotifier, "attachments"), (SlackNotifier, "blocks")],
)
def test_webhook_notifiers_send_channel_payloads(
    notifier_type,
    expected_key: str,
    fake_webhook,
) -> None:
    url, captured, _ = fake_webhook
    notifier = notifier_type(url)
    message = make_service().notify(
        create_pipeline(Settings(mode="mock", notification_backends=[]), EventStore()).run(
            DisruptionEvent(
                title="Port weather delay",
                description="Extreme weather delayed the ship.",
                delay_days=5,
                language="en",
            )
        ),
        "draft_ready",
    )

    notifier.send(message)

    assert captured[0]["path"] == "/webhook"
    assert captured[0]["content_type"].startswith("application/json")
    payload = captured[0]["payload"]
    assert isinstance(payload, dict)
    assert expected_key in payload
    if notifier_type is TeamsNotifier:
        card = payload["attachments"][0]["content"]
        assert card["type"] == "AdaptiveCard"
        assert card["actions"][0]["url"] == message.approve_url
        assert card["actions"][1]["url"] == message.view_url
    else:
        assert payload["blocks"][0]["type"] == "section"
        assert payload["blocks"][1]["type"] == "actions"
        assert payload["blocks"][1]["elements"][0]["url"] == message.approve_url
    assert "Raw material Microchip X delayed 5 days." in message.text
    assert "Stock for 3 days (source: SAP S/4HANA)." in message.text
    assert "Vendor B at $135,000 (source: SAP Ariba)." in message.text
    assert "[signed" not in message.text


def test_notification_body_uses_event_language() -> None:
    pipeline = create_pipeline(
        Settings(mode="mock", notification_backends=[]),
        EventStore(),
    )
    run = pipeline.run(
        DisruptionEvent(
            title="Port weather delay",
            description="Extreme weather delayed the ship.",
            delay_days=5,
            language="id",
        )
    )

    message = make_service().notify(run, "draft_ready")

    assert "Bahan baku Microchip X terlambat 5 hari." in message.text
    assert "Setujui (membuka tinjauan eksplisit" in message.text


def test_webhook_retries_transient_failure(fake_webhook) -> None:
    url, captured, statuses = fake_webhook
    statuses.extend([503, 200])
    notifier = SlackNotifier(url)
    run = create_pipeline(Settings(mode="mock", notification_backends=[]), EventStore()).run(
        DisruptionEvent(
            title="Port weather delay",
            description="Extreme weather delayed the ship.",
            delay_days=5,
        )
    )

    notifier.send(make_service().notify(run, "draft_ready"))

    assert len(captured) == 2
    notifier.close()


def test_webhook_delivery_failure_is_reported(fake_webhook) -> None:
    url, captured, statuses = fake_webhook
    statuses.extend([503, 503, 503])
    notifier = SlackNotifier(url)
    run = create_pipeline(Settings(mode="mock", notification_backends=[]), EventStore()).run(
        DisruptionEvent(
            title="Port weather delay",
            description="Extreme weather delayed the ship.",
            delay_days=5,
        )
    )

    with pytest.raises(IntegrationError, match="Slack notification"):
        notifier.send(make_service().notify(run, "draft_ready"))
    assert len(captured) == 3
    notifier.close()


def test_mock_email_writes_notification_to_jsonl_outbox(tmp_path) -> None:
    outbox = tmp_path / "notifications.jsonl"
    notifier = EmailNotifier(
        mode="mock",
        sender="demo@example.invalid",
        recipient="judge@example.invalid",
        region_name="us-east-1",
        outbox_path=outbox,
    )
    run = create_pipeline(
        Settings(mode="mock", notification_backends=[]),
        EventStore(),
    ).run(
        DisruptionEvent(
            title="Weather delay",
            description="A storm delayed the component cargo.",
            delay_days=5,
        )
    )

    notifier.send(make_service().notify(run, "draft_ready"))

    assert len(outbox.read_text(encoding="utf-8").splitlines()) == 1
    assert "Vendor B" in outbox.read_text(encoding="utf-8")


def test_aws_email_uses_ses_send_email_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ses_client = boto3.client(
        "ses",
        region_name="us-east-1",
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
    )
    monkeypatch.setattr(
        "chainmind.notifications.channels.boto3.client",
        lambda service, region_name: ses_client,
    )
    run = create_pipeline(Settings(mode="mock", notification_backends=[]), EventStore()).run(
        DisruptionEvent(
            title="Weather delay",
            description="A storm delayed the component cargo.",
            delay_days=5,
        )
    )
    message = make_service().notify(run, "draft_ready")
    expected = {
        "Source": "demo@example.invalid",
        "Destination": {"ToAddresses": ["judge@example.invalid"]},
        "Message": {
            "Subject": {"Data": message.subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": message.text, "Charset": "UTF-8"}},
        },
    }
    notifier = EmailNotifier(
        mode="aws",
        sender="demo@example.invalid",
        recipient="judge@example.invalid",
        region_name="us-east-1",
        outbox_path="unused.jsonl",
    )

    with Stubber(ses_client) as stubber:
        stubber.add_response(
            "send_email",
            {"MessageId": "demo-message-id"},
            expected_params=expected,
        )
        notifier.send(message)
        stubber.assert_no_pending_responses()


def test_mock_pipeline_notifies_draft_and_escalates_overdue_once() -> None:
    notifier = CaptureNotifier()
    service = make_service(notifier)
    pipeline = create_pipeline(
        Settings(
            mode="mock",
            notification_backends=[],
            notification_approval_overdue_minutes=30,
        ),
        EventStore(),
        notification_service=service,
    )
    run = pipeline.run(
        DisruptionEvent(
            title="Weather delay",
            description="A storm delayed the component cargo.",
            delay_days=5,
        )
    )
    assert notifier.messages[0].event_kind == "draft_ready"

    now = datetime.now(UTC)
    run.created_at = now - timedelta(hours=1)
    pipeline.store.save(run)
    assert pipeline.check_approval_overdue(now=now) == 1
    assert pipeline.check_approval_overdue(now=now + timedelta(hours=1)) == 0
    assert [item.event_kind for item in notifier.messages] == [
        "draft_ready",
        "approval_overdue",
    ]
    stored = pipeline.store.get(run.run_id)
    assert stored is not None
    assert stored.status == RunStatus.PENDING_APPROVAL
    assert stored.approval_overdue_notified is True
    assert stored.last_decision is None
    assert stored.audit_log[-1].agent == "notifications"
    assert stored.audit_log[-1].output_summary == "Approval overdue escalation delivered."


def test_eta_deviation_triggers_tracking_alert() -> None:
    notifier = CaptureNotifier()
    service = make_service(notifier)

    class LateAribaClient(MockAribaClient):
        def get_shipment_tracking(self, order):
            super().get_vendor_confirmation(order)
            vendor = next(item for item in self._vendors if item.vendor_id == order.vendor_id)
            return ShipmentTracking(
                tracking_id="ASN-LATE",
                status="IN_TRANSIT",
                estimated_arrival=date.today() + timedelta(days=vendor.lead_time_days + 2),
            )

    pipeline = create_pipeline(
        Settings(
            mode="mock",
            notification_backends=[],
            notification_eta_deviation_threshold_days=1,
        ),
        EventStore(),
        ariba_client=LateAribaClient(),
        notification_service=service,
    )
    run = pipeline.run(
        DisruptionEvent(
            title="Weather delay",
            description="A storm delayed the component cargo.",
            delay_days=5,
        )
    )
    pipeline.decide(run.run_id, DecisionRequest(decision=DecisionType.APPROVE))

    assert [item.event_kind for item in notifier.messages] == [
        "draft_ready",
        "tracking_deviation",
    ]
    assert "2 days later" in notifier.messages[-1].text


def test_signed_approval_requires_role_and_explicit_confirmation() -> None:
    from fastapi import HTTPException, Request

    from chainmind.api.identity import AuthenticatedUser, authenticated_user
    from chainmind.api.main import app, pipeline

    def test_user(request: Request) -> AuthenticatedUser:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401)
        role = authorization.removeprefix("Bearer ")
        return AuthenticatedUser(
            subject=role,
            roles=frozenset({"approver"} if role == "test-approver" else {"viewer"}),
        )

    app.dependency_overrides[authenticated_user] = test_user
    client = TestClient(app)
    created = client.post(
        "/disruptions",
        json={
            "title": "Weather delay",
            "description": "A storm delayed the component cargo.",
            "delay_days": 5,
        },
    )
    run_id = created.json()["run_id"]
    token = pipeline.create_notification_link(UUID(run_id), "approve")
    link = f"/notifications/links/{token}"

    inspected = client.get(link)
    assert inspected.status_code == 200
    assert inspected.json()["confirmation_required"] is True
    assert client.get(f"/runs/{run_id}").json()["status"] == "PENDING_APPROVAL"
    unconfirmed = client.post(
        f"{link}/approve",
        json={"confirmed": False},
        headers={"Authorization": "Bearer test-approver"},
    )
    viewer = client.post(
        f"{link}/approve",
        json={"confirmed": True},
        headers={"Authorization": "Bearer test-viewer"},
    )
    assert unconfirmed.status_code == 422
    assert viewer.status_code == 403
    approved = client.post(
        f"{link}/approve",
        json={"confirmed": True, "note": "Approved after review."},
        headers={"Authorization": "Bearer test-approver"},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "EXECUTED"
    app.dependency_overrides.pop(authenticated_user, None)


def test_aws_overdue_handler_marks_pending_run_and_audits_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from chainmind.handlers import notifications as notification_handler

    class FakeStore:
        def __init__(self) -> None:
            self.runs = [
                DisruptionRun(
                    event=DisruptionEvent(
                        title="Late supplier",
                        description="An input shipment is late.",
                        delay_days=5,
                    ),
                    status=RunStatus.PENDING_APPROVAL,
                    draft_po=PurchaseOrder(
                        vendor_id="vendor-b",
                        vendor_name="Vendor B",
                        component_id="microchip-x",
                        component_name="Microchip X",
                        quantity=5000,
                        unit_price=27,
                        total_price=135000,
                    ),
                    created_at=datetime.now(UTC) - timedelta(hours=2),
                )
            ]

        def list(self):
            return self.runs

        def save(self, run) -> None:
            self.runs[0] = run

    store = FakeStore()
    notifications = make_service()
    monkeypatch.setattr(
        notification_handler,
        "Settings",
        lambda: Settings(mode="mock", notification_approval_overdue_minutes=30),
    )
    monkeypatch.setattr(
        notification_handler,
        "DynamoDBEventStore",
        lambda table, region: store,
    )
    monkeypatch.setattr(
        notification_handler,
        "create_notification_service",
        lambda settings: notifications,
    )

    result = notification_handler.approval_overdue({}, object())

    assert result == {"notified": 1}
    assert store.runs[0].approval_overdue_notified is True
    assert store.runs[0].audit_log[-1].agent == "notifications"
