"""Notification rendering and multi-channel dispatch for workflow events."""

from typing import Literal
from uuid import UUID

from chainmind.core.models import (
    DisruptionRun,
    NotificationLinkPayload,
    NotificationMessage,
)
from chainmind.notifications.base import Notifier
from chainmind.notifications.links import NotificationLinkSigner


class NotificationService:
    """Render actionable supply-chain alerts and deliver them to configured channels."""

    def __init__(
        self,
        notifiers: list[Notifier],
        signer: NotificationLinkSigner,
        *,
        api_base_url: str,
        dashboard_url: str,
    ) -> None:
        self._notifiers = notifiers
        self._signer = signer
        self._api_base_url = api_base_url.rstrip("/")
        self._dashboard_url = dashboard_url.rstrip("/")

    def notify(self, run: DisruptionRun, event_kind: str) -> NotificationMessage:
        """Send a draft, overdue-approval, or ETA-deviation alert."""

        if run.draft_po is None:
            raise ValueError("Workflow notifications require a purchase-order draft.")
        inventory = run.inventory_snapshot
        coverage_days = inventory.current_stock / inventory.daily_consumption if inventory else 0
        source_text = f"Stock for {coverage_days:g} days"
        if event_kind == "draft_ready":
            subject = f"Approval requested: {run.event.component_name}"
            decision_summary = run.chain_of_thought[-1] if run.chain_of_thought else run.event.title
            recommendation = (
                f"Recommendation: buy from {run.draft_po.vendor_name} at "
                f"${run.draft_po.total_price:,.0f} (source: SAP Ariba)."
            )
            body = (
                f"Raw material {run.event.component_name} delayed {run.event.delay_days:g} days. "
                f"{source_text} (source: SAP S/4HANA). {recommendation}\n"
                f"Decision summary: {decision_summary}"
            )
        elif event_kind == "approval_overdue":
            subject = f"Approval overdue: {run.event.component_name}"
            body = (
                f"Human approval is overdue for {run.draft_po.vendor_name}'s "
                f"${run.draft_po.total_price:,.0f} draft purchase order."
            )
        elif event_kind == "tracking_deviation":
            subject = f"Shipment ETA deviation: {run.event.component_name}"
            body = (
                run.execution_tracking.alert
                if run.execution_tracking and run.execution_tracking.alert
                else "The supplier ETA differs from the quoted lead time."
            )
        else:
            raise ValueError(f"Unsupported notification event: {event_kind}")

        approve_token = self._signer.create(run.run_id, "approve")
        view_token = self._signer.create(run.run_id, "view")
        approve_url = f"{self._dashboard_url}/?approve={approve_token}"
        view_url = f"{self._api_base_url}/notifications/links/{view_token}"
        message = NotificationMessage(
            run_id=run.run_id,
            event_kind=event_kind,
            subject=subject,
            text=(
                f"{body}\nApprove (opens an explicit review; never executes directly): "
                f"{approve_url}\nView details: {view_url}"
            ),
            approve_url=approve_url,
            view_url=view_url,
        )
        for notifier in self._notifiers:
            notifier.send(message)
        return message

    @property
    def channel_count(self) -> int:
        """Return the number of active delivery channels."""

        return len(self._notifiers)

    def validate_link(self, token: str) -> NotificationLinkPayload:
        """Validate a signed action URL token."""

        return self._signer.validate(token)

    def create_link(self, run_id: UUID, action: Literal["approve", "view"]) -> str:
        """Create a scoped signed link for an existing run."""

        return self._signer.create(run_id, action)

    @staticmethod
    def audit_summary(message: NotificationMessage) -> str:
        """Return message content without retaining reusable signed URL tokens."""

        return message.text.replace(message.approve_url, "[signed approval link]").replace(
            message.view_url, "[signed view link]"
        )
