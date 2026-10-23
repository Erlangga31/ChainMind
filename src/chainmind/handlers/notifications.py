"""Scheduled Lambda wrapper for pending-approval escalation notifications."""

from datetime import UTC, datetime, timedelta
from typing import Any

from chainmind.core.config import Settings
from chainmind.core.models import AuditEntry, RunStatus
from chainmind.factory import create_notification_service
from chainmind.integrations.aws.event_store import DynamoDBEventStore


def approval_overdue(event: dict[str, Any], context: object) -> dict[str, int]:
    """Escalate pending approvals after the configured age, once per run."""

    del event, context
    settings = Settings()
    notifications = create_notification_service(settings)
    if notifications is None:
        return {"notified": 0}
    store = DynamoDBEventStore(settings.event_table_name, settings.aws_region)
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.notification_approval_overdue_minutes)
    count = 0
    for run in store.list():
        if (
            run.status != RunStatus.PENDING_APPROVAL
            or run.approval_overdue_notified
            or run.created_at > cutoff
        ):
            continue
        message = notifications.notify(run, "approval_overdue")
        run.approval_overdue_notified = True
        run.audit_log.append(
            AuditEntry(
                agent="notifications",
                input_summary=f"run_id={run.run_id}; event=approval_overdue",
                output_summary=(
                    f"Approval overdue escalation delivered to "
                    f"{notifications.channel_count} channel(s)."
                ),
                reasoning=notifications.audit_summary(message),
            )
        )
        store.save(run)
        count += 1
    return {"notified": count}
