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
        is_indonesian = run.event.language == "id"
        source_text = (
            f"Stok cukup untuk {coverage_days:g} hari"
            if is_indonesian
            else f"Stock for {coverage_days:g} days"
        )
        if event_kind == "draft_ready":
            subject = (
                f"Persetujuan diminta: {run.event.component_name}"
                if is_indonesian
                else f"Approval requested: {run.event.component_name}"
            )
            decision_summary = (
                f"{run.draft_po.vendor_name} direkomendasikan; biaya tanpa tindakan "
                f"${run.cost_of_inaction:,.0f}. Draf PO menunggu persetujuan manusia."
                if is_indonesian
                else (
                    f"{run.draft_po.vendor_name} is recommended; cost of inaction is "
                    f"${run.cost_of_inaction:,.0f}. The draft PO awaits human approval."
                )
            )
            if is_indonesian:
                recommendation = (
                    f"Rekomendasi: beli dari {run.draft_po.vendor_name} seharga "
                    f"${run.draft_po.total_price:,.0f} (sumber: SAP Ariba)."
                )
                body = (
                    f"Bahan baku {run.event.component_name} terlambat "
                    f"{run.event.delay_days:g} hari. {source_text} "
                    f"(sumber: SAP S/4HANA). {recommendation}\n"
                    f"Ringkasan keputusan: {decision_summary}"
                )
            else:
                recommendation = (
                    f"Recommendation: buy from {run.draft_po.vendor_name} at "
                    f"${run.draft_po.total_price:,.0f} (source: SAP Ariba)."
                )
                body = (
                    f"Raw material {run.event.component_name} delayed "
                    f"{run.event.delay_days:g} days. {source_text} "
                    f"(source: SAP S/4HANA). {recommendation}\n"
                    f"Decision summary: {decision_summary}"
                )
        elif event_kind == "approval_overdue":
            subject = (
                f"Persetujuan terlambat: {run.event.component_name}"
                if is_indonesian
                else f"Approval overdue: {run.event.component_name}"
            )
            body = (
                f"Persetujuan manusia untuk draf purchase order {run.draft_po.vendor_name} "
                f"senilai ${run.draft_po.total_price:,.0f} telah melewati batas waktu."
                if is_indonesian
                else (
                    f"Human approval is overdue for {run.draft_po.vendor_name}'s "
                    f"${run.draft_po.total_price:,.0f} draft purchase order."
                )
            )
        elif event_kind == "tracking_deviation":
            subject = (
                f"Penyimpangan ETA pengiriman: {run.event.component_name}"
                if is_indonesian
                else f"Shipment ETA deviation: {run.event.component_name}"
            )
            body = (
                run.execution_tracking.alert
                if run.execution_tracking and run.execution_tracking.alert
                else (
                    "ETA pemasok berbeda dari waktu pengiriman yang ditawarkan."
                    if is_indonesian
                    else "The supplier ETA differs from the quoted lead time."
                )
            )
        else:
            raise ValueError(f"Unsupported notification event: {event_kind}")

        approve_token = self._signer.create(
            run.run_id,
            "approve",
            tenant_id=run.tenant_id,
        )
        view_token = self._signer.create(
            run.run_id,
            "view",
            tenant_id=run.tenant_id,
        )
        approve_url = f"{self._dashboard_url}/?approve={approve_token}"
        view_url = f"{self._api_base_url}/notifications/links/{view_token}"
        approval_action = (
            "Setujui (membuka tinjauan eksplisit; tidak langsung mengeksekusi)"
            if is_indonesian
            else "Approve (opens an explicit review; never executes directly)"
        )
        view_action = "Lihat detail" if is_indonesian else "View details"
        message = NotificationMessage(
            run_id=run.run_id,
            event_kind=event_kind,
            subject=subject,
            text=(f"{body}\n{approval_action}: {approve_url}\n{view_action}: {view_url}"),
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

    def create_link(
        self,
        run_id: UUID,
        action: Literal["approve", "view"],
        *,
        tenant_id: str = "demo",
    ) -> str:
        """Create a scoped signed link for an existing run."""

        return self._signer.create(run_id, action, tenant_id=tenant_id)

    @staticmethod
    def audit_summary(message: NotificationMessage) -> str:
        """Return message content without retaining reusable signed URL tokens."""

        return message.text.replace(message.approve_url, "[signed approval link]").replace(
            message.view_url, "[signed view link]"
        )
