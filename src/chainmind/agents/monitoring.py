"""Monitoring agent for disruption severity and significance."""

from chainmind.core.models import (
    AffectedSupplyChainRecords,
    DisruptionEvent,
    DisruptionType,
    MonitoringResult,
    Severity,
)


class MonitoringAgent:
    """Classify a disruption against the component's available stock coverage."""

    def analyze(
        self,
        event: DisruptionEvent,
        coverage_days: float,
        affected_records: AffectedSupplyChainRecords | None = None,
    ) -> MonitoringResult:
        """Classify the event and return severity plus matched SAP records."""

        disruption_type = event.event_type or self.classify(event)
        records = affected_records or AffectedSupplyChainRecords(component_id=event.component_id)
        if event.delay_days >= coverage_days * 2:
            severity = Severity.CRITICAL
        elif event.delay_days > coverage_days:
            severity = Severity.HIGH
        elif event.delay_days >= coverage_days * 0.75:
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW
        significant = severity != Severity.LOW
        action = (
            "significant and requires mitigation"
            if significant
            else "below the intervention threshold"
        )
        summary = (
            f"{severity.value} severity; {event.delay_days:g}-day delay versus "
            f"{coverage_days:g} days of stock coverage."
        )
        reasoning = (
            f"Classified as {disruption_type.value}. The disruption delay is "
            f"{event.delay_days:g} days and available stock covers {coverage_days:g} days. "
            f"The resulting {severity.value.lower()} classification is {action}. "
            f"Matched {len(records.shipment_ids)} shipments and "
            f"{len(records.open_purchase_order_ids)} open purchase orders in SAP."
        )
        return MonitoringResult(
            agent="monitoring",
            summary=summary,
            reasoning=reasoning,
            severity=severity,
            significant=significant,
            coverage_days=coverage_days,
            disruption_type=disruption_type,
            affected_records=records,
        )

    @staticmethod
    def classify(event: DisruptionEvent) -> DisruptionType:
        """Classify an event using explicit type first, then deterministic keywords."""

        if event.event_type is not None:
            return event.event_type
        text = f"{event.title} {event.description} {event.source}".lower()
        if any(term in text for term in ("weather", "storm", "flood", "typhoon", "extreme")):
            return DisruptionType.WEATHER
        if any(term in text for term in ("geopolitical", "border closure", "sanction", "conflict")):
            return DisruptionType.GEOPOLITICAL
        if any(term in text for term in ("vendor", "supplier", "factory", "supplier failure")):
            return DisruptionType.VENDOR_FAILURE
        return DisruptionType.LOGISTICS_DELAY
