"""Monitoring agent for disruption severity and significance."""

from chainmind.core.models import DisruptionEvent, MonitoringResult, Severity


class MonitoringAgent:
    """Classify a disruption against the component's available stock coverage."""

    def analyze(self, event: DisruptionEvent, coverage_days: float) -> MonitoringResult:
        """Return a typed severity decision and auditable explanation."""

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
            f"The disruption delay is {event.delay_days:g} days and available stock covers "
            f"{coverage_days:g} days. The resulting {severity.value.lower()} classification "
            f"is {action}."
        )
        return MonitoringResult(
            agent="monitoring",
            summary=summary,
            reasoning=reasoning,
            severity=severity,
            significant=significant,
            coverage_days=coverage_days,
        )
