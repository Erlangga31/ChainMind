"""Framework-independent four-agent disruption resolution pipeline."""

from datetime import UTC, datetime
from uuid import UUID

from chainmind.agents.logistics import LogisticsAgent
from chainmind.agents.monitoring import MonitoringAgent
from chainmind.agents.orchestrator import OrchestratorAgent
from chainmind.agents.procurement import ProcurementAgent
from chainmind.core.audit import audit_for
from chainmind.core.config import Settings
from chainmind.core.errors import ChainMindError
from chainmind.core.events import EventStore, RunStore
from chainmind.core.models import (
    AuditEntry,
    DecisionRequest,
    DecisionResult,
    DecisionType,
    DisruptionEvent,
    DisruptionRun,
    InventorySnapshot,
    LogisticsResult,
    ProcurementResult,
    RunStatus,
    StageResult,
)
from chainmind.core.retry import retry_integration_call
from chainmind.integrations.llm.base import LLMClient
from chainmind.integrations.sap.base import ApprovalWorkflowClient, AribaClient, SAPClient
from chainmind.integrations.sap.real_clients import InMemoryApprovalWorkflowClient


class DisruptionPipeline:
    """Run monitoring, logistics, procurement, and economic orchestration in order."""

    def __init__(
        self,
        *,
        sap: SAPClient,
        ariba: AribaClient,
        llm: LLMClient,
        settings: Settings,
        store: RunStore | None = None,
        workflow_client: ApprovalWorkflowClient | None = None,
    ) -> None:
        self._sap = sap
        self._ariba = ariba
        self._llm = llm
        self._settings = settings
        self._store = store or EventStore()
        self._workflow = workflow_client or InMemoryApprovalWorkflowClient()
        self._monitoring = MonitoringAgent()
        self._logistics = LogisticsAgent()
        self._procurement = ProcurementAgent(ariba, settings)
        self._orchestrator = OrchestratorAgent(llm)
        self._run_context: dict[
            UUID, tuple[InventorySnapshot, LogisticsResult, ProcurementResult]
        ] = {}

    @property
    def store(self) -> RunStore:
        """Expose the event store to API routes."""

        return self._store

    def run(self, event: DisruptionEvent) -> DisruptionRun:
        """Execute the four agent stages and persist a draft awaiting approval."""

        existing = self._store.get_by_idempotency_key(event.dedupe_key)
        if existing is not None:
            return existing
        run = DisruptionRun(event=event)
        self._store.save(run)
        try:
            inventory = retry_integration_call(
                lambda: self._sap.get_inventory(event.component_id),
                attempts=self._settings.retry_attempts,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
            coverage = inventory.current_stock / inventory.daily_consumption
            affected_records = retry_integration_call(
                lambda: self._sap.find_affected_records(event),
                attempts=self._settings.retry_attempts,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
            run.audit_log.append(
                AuditEntry(
                    agent="sap_s4hana",
                    input_summary=f"Inventory requested for {event.component_id}.",
                    output_summary=(
                        f"{inventory.current_stock:,} units; "
                        f"{inventory.daily_consumption:,} units consumed per day."
                    ),
                    reasoning="Retrieved the stock-of-record snapshot used for this analysis.",
                )
            )

            monitoring = self._monitoring.analyze(event, coverage, affected_records)
            run.severity = monitoring.severity
            run.significant = monitoring.significant
            run.affected_records = monitoring.affected_records
            run.chain_of_thought.append(monitoring.reasoning)
            run.audit_log.append(audit_for(monitoring, event.model_dump_json()))
            run.stages.append(
                StageResult(name="Monitoring", status="COMPLETED", summary=monitoring.summary)
            )
            self._store.save(run)

            if not monitoring.significant:
                run.status = RunStatus.NOT_SIGNIFICANT
                self._skip_remaining_stages(run)
                run.updated_at = datetime.now(UTC)
                self._store.save(run)
                return run

            logistics = self._logistics.analyze(event, inventory)
            run.chain_of_thought.append(logistics.reasoning)
            run.audit_log.append(
                audit_for(
                    logistics,
                    f"delay={event.delay_days:g}; inventory={inventory.model_dump_json()}",
                )
            )
            run.stages.append(
                StageResult(name="Logistics", status="COMPLETED", summary=logistics.summary)
            )
            self._store.save(run)

            procurement = retry_integration_call(
                lambda: self._procurement.compare(event, inventory, logistics),
                attempts=self._settings.retry_attempts,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
            run.vendor_comparison = procurement.evaluations
            run.chain_of_thought.append(procurement.reasoning)
            run.audit_log.append(
                audit_for(
                    procurement,
                    f"component={event.component_id}; quantity={inventory.purchase_quantity}",
                )
            )
            run.stages.append(
                StageResult(name="Procurement", status="COMPLETED", summary=procurement.summary)
            )
            self._store.save(run)

            orchestration = retry_integration_call(
                lambda: self._orchestrator.choose(
                    procurement,
                    logistics,
                    run_id=str(run.run_id),
                ),
                attempts=self._settings.retry_attempts,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
            draft = self._orchestrator.draft_purchase_order(
                orchestration.selected_vendor, inventory
            )
            draft = retry_integration_call(
                lambda: self._sap.create_draft_purchase_order(draft),
                attempts=self._settings.retry_attempts,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
            workflow_task_id = self._workflow.create_task(str(run.run_id), str(draft.po_id))
            run.selected_vendor_id = orchestration.selected_vendor.vendor.vendor_id
            run.draft_po = draft
            run.workflow_task_id = workflow_task_id
            run.trace_steps.extend(orchestration.trace)
            run.chain_of_thought.extend(
                f"[{step.source}] {step.text}" for step in orchestration.trace
            )
            run.chain_of_thought.append(orchestration.reasoning)
            run.audit_log.append(
                audit_for(
                    orchestration,
                    f"inaction_cost={logistics.cost_of_inaction:.2f}; "
                    f"vendors={len(procurement.evaluations)}",
                )
            )
            if orchestration.fallback_used:
                run.audit_log.append(
                    AuditEntry(
                        agent="orchestrator",
                        input_summary=f"run_id={run.run_id}",
                        output_summary="A deterministic explanation fallback was used.",
                        reasoning=orchestration.fallback_reason
                        or "The model output did not pass validation.",
                    )
                )
            run.audit_log.append(
                AuditEntry(
                    agent="sap_s4hana",
                    input_summary=orchestration.summary,
                    output_summary=f"Draft PO {draft.po_id} created; not executed.",
                    reasoning=(
                        "A draft is stored for human review; no financial transaction was executed."
                    ),
                )
            )
            run.audit_log.append(
                AuditEntry(
                    agent="sap_business_workflow",
                    input_summary=f"run_id={run.run_id}; po_id={draft.po_id}",
                    output_summary=f"Approval task {workflow_task_id} created.",
                    reasoning=(
                        "The draft is linked to a human approval task; it remains unexecuted."
                    ),
                )
            )
            run.stages.append(
                StageResult(
                    name="Orchestrator",
                    status="COMPLETED",
                    summary=orchestration.summary,
                )
            )
            run.stages.append(
                StageResult(
                    name="Human approval",
                    status="PENDING",
                    summary="A human decision is required before purchase-order execution.",
                )
            )
            run.stages.append(
                StageResult(
                    name="PO execution",
                    status="WAITING_FOR_APPROVAL",
                    summary="No PO has been executed.",
                )
            )
            run.status = RunStatus.PENDING_APPROVAL
            self._run_context[run.run_id] = (inventory, logistics, procurement)
            run.updated_at = datetime.now(UTC)
            self._store.save(run)
            return run
        except ChainMindError as exc:
            run.status = RunStatus.FAILED
            run.error = exc.message
            run.audit_log.append(
                AuditEntry(
                    agent="workflow",
                    input_summary=f"event_id={event.event_id}",
                    output_summary=f"Run failed: {exc.code}.",
                    reasoning=exc.message,
                )
            )
            run.updated_at = datetime.now(UTC)
            self._store.save(run)
            raise

    def get_run(self, run_id: UUID) -> DisruptionRun:
        """Return a persisted run or a structured not-found error."""

        run = self._store.get(run_id)
        if run is None:
            raise ChainMindError(
                "run_not_found",
                "No disruption run exists with that ID.",
                status_code=404,
                details={"run_id": str(run_id)},
            )
        return run

    def decide(self, run_id: UUID, decision: DecisionRequest) -> DecisionResult:
        """Record approval, rejection, or a human-selected vendor revision."""

        run = self.get_run(run_id)
        if run.last_decision == decision and run.status != RunStatus.PENDING_APPROVAL:
            return DecisionResult(
                run_id=run.run_id,
                status=run.status,
                message="This decision was already recorded.",
                draft_po=run.draft_po,
            )
        if run.last_decision == decision and run.status == RunStatus.PENDING_APPROVAL:
            return DecisionResult(
                run_id=run.run_id,
                status=run.status,
                message="This revision was already recorded; the draft remains pending approval.",
                draft_po=run.draft_po,
            )
        if run.status != RunStatus.PENDING_APPROVAL or run.draft_po is None:
            raise ChainMindError(
                "decision_not_allowed",
                "A decision can only be recorded for a draft pending approval.",
                status_code=409,
                details={"status": run.status.value},
            )
        if decision.decision == DecisionType.REVISE:
            return self._revise(run, decision)
        if decision.decision == DecisionType.REJECT:
            if run.workflow_task_id is not None:
                self._workflow.record_decision(
                    run.workflow_task_id,
                    decision.decision.value,
                    decision.note,
                )
            run.status = RunStatus.REJECTED
            run.draft_po.status = "REJECTED"
            run.last_decision = decision.model_copy(deep=True)
            run.audit_log.append(
                AuditEntry(
                    agent="human",
                    input_summary=f"run_id={run.run_id}",
                    output_summary="Draft purchase order rejected.",
                    reasoning=decision.note or "Rejected by human reviewer.",
                )
            )
            self._complete_decision(
                run, "Human approval", "REJECTED", "PO execution", "NOT_EXECUTED"
            )
            self._store.save(run)
            return DecisionResult(
                run_id=run.run_id,
                status=run.status,
                message="Draft rejected; no SAP purchase order was executed.",
                draft_po=run.draft_po,
            )

        if run.workflow_task_id is not None:
            self._workflow.record_decision(
                run.workflow_task_id,
                decision.decision.value,
                decision.note,
            )
        sap_reference = retry_integration_call(
            lambda: self._sap.execute_purchase_order(run.draft_po),
            attempts=self._settings.retry_attempts,
            base_delay_seconds=self._settings.retry_base_delay_seconds,
        )
        run.status = RunStatus.EXECUTED
        run.draft_po.status = "EXECUTED"
        run.draft_po.sap_reference = sap_reference
        run.last_decision = decision.model_copy(deep=True)
        run.audit_log.append(
            AuditEntry(
                agent="human",
                input_summary=f"run_id={run.run_id}; po_id={run.draft_po.po_id}",
                output_summary=f"Approved and executed as {sap_reference}.",
                reasoning=decision.note or "Explicit human approval recorded.",
            )
        )
        self._complete_decision(run, "Human approval", "APPROVED", "PO execution", "EXECUTED")
        run.updated_at = datetime.now(UTC)
        self._store.save(run)
        return DecisionResult(
            run_id=run.run_id,
            status=run.status,
            message=f"Purchase order approved and executed as {sap_reference}.",
            draft_po=run.draft_po,
        )

    def _revise(self, run: DisruptionRun, decision: DecisionRequest) -> DecisionResult:
        if not decision.vendor_id:
            raise ChainMindError(
                "vendor_required",
                "A vendor_id is required when requesting a vendor revision.",
                status_code=422,
            )
        context = self._run_context.get(run.run_id)
        if context is None:
            raise ChainMindError(
                "revision_context_unavailable",
                "The economics context for this run is no longer available.",
                status_code=409,
            )
        inventory, logistics, _ = context
        procurement = self._procurement.compare(run.event, inventory, logistics)
        run.vendor_comparison = procurement.evaluations
        revised = retry_integration_call(
            lambda: self._orchestrator.choose(
                procurement,
                logistics,
                vendor_id=decision.vendor_id,
                run_id=str(run.run_id),
            ),
            attempts=self._settings.retry_attempts,
            base_delay_seconds=self._settings.retry_base_delay_seconds,
        )
        new_order = self._orchestrator.draft_purchase_order(revised.selected_vendor, inventory)
        run.draft_po = retry_integration_call(
            lambda: self._sap.create_draft_purchase_order(new_order),
            attempts=self._settings.retry_attempts,
            base_delay_seconds=self._settings.retry_base_delay_seconds,
        )
        if run.workflow_task_id is not None:
            self._workflow.update_draft(run.workflow_task_id, str(run.draft_po.po_id))
        run.selected_vendor_id = revised.selected_vendor.vendor.vendor_id
        run.revision_note = decision.note
        run.last_decision = decision.model_copy(deep=True)
        run.trace_steps.extend(revised.trace)
        run.chain_of_thought.extend(f"[{step.source}] {step.text}" for step in revised.trace)
        run.chain_of_thought.append(f"Human-requested revision: {revised.reasoning}")
        run.audit_log.append(
            audit_for(
                revised,
                f"requested_vendor={decision.vendor_id}; note={decision.note}",
            )
        )
        if revised.fallback_used:
            run.audit_log.append(
                AuditEntry(
                    agent="orchestrator",
                    input_summary=f"run_id={run.run_id}",
                    output_summary="A deterministic explanation fallback was used.",
                    reasoning=revised.fallback_reason
                    or "The model output did not pass validation.",
                )
            )
        run.audit_log.append(
            AuditEntry(
                agent="sap_s4hana",
                input_summary=f"Revised PO for {decision.vendor_id}.",
                output_summary=f"New draft PO {run.draft_po.po_id} remains pending approval.",
                reasoning="Revision creates a replacement draft and does not execute it.",
            )
        )
        run.stages = [
            stage for stage in run.stages if stage.name not in {"Human approval", "PO execution"}
        ]
        run.stages.extend(
            [
                StageResult(
                    name="Human approval",
                    status="PENDING",
                    summary="Revised draft is awaiting a new human decision.",
                ),
                StageResult(
                    name="PO execution",
                    status="WAITING_FOR_APPROVAL",
                    summary="Revised PO has not been executed.",
                ),
            ]
        )
        run.updated_at = datetime.now(UTC)
        self._store.save(run)
        return DecisionResult(
            run_id=run.run_id,
            status=run.status,
            message=(
                f"Draft revised to {revised.selected_vendor.vendor.vendor_name}; "
                "approval is still required."
            ),
            draft_po=run.draft_po,
        )

    @staticmethod
    def _complete_decision(
        run: DisruptionRun,
        approval_name: str,
        approval_status: str,
        execution_name: str,
        execution_status: str,
    ) -> None:
        for stage in run.stages:
            if stage.name == approval_name:
                stage.status = approval_status
                stage.summary = (
                    "A human approved the purchase order."
                    if approval_status == "APPROVED"
                    else "A human rejected the purchase order."
                )
            elif stage.name == execution_name:
                stage.status = execution_status
                stage.summary = (
                    f"Purchase order executed as {run.draft_po.sap_reference}."
                    if execution_status == "EXECUTED" and run.draft_po
                    else "Purchase order was not executed."
                )
        run.updated_at = datetime.now(UTC)

    @staticmethod
    def _skip_remaining_stages(run: DisruptionRun) -> None:
        for name in ("Logistics", "Procurement", "Orchestrator", "Human approval", "PO execution"):
            run.stages.append(
                StageResult(name=name, status="SKIPPED", summary="Disruption was not significant.")
            )
