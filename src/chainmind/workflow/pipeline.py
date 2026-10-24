"""Framework-independent four-agent disruption resolution pipeline."""

from datetime import UTC, datetime
from uuid import UUID

from chainmind.agents.logistics import LogisticsAgent
from chainmind.agents.monitoring import MonitoringAgent
from chainmind.agents.orchestrator import OrchestratorAgent
from chainmind.agents.procurement import ProcurementAgent
from chainmind.agents.tracking import TrackingAgent
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
    NotificationLinkPayload,
    ProcurementResult,
    RunStatus,
    StageResult,
)
from chainmind.core.retry import retry_integration_call
from chainmind.integrations.llm.base import LLMClient
from chainmind.integrations.sap.base import ApprovalWorkflowClient, AribaClient, SAPClient
from chainmind.integrations.sap.real_clients import InMemoryApprovalWorkflowClient
from chainmind.notifications.service import NotificationService
from chainmind.workflow.definition import WorkflowState, validate_transition


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
        notification_service: NotificationService | None = None,
    ) -> None:
        self._sap = sap
        self._ariba = ariba
        self._llm = llm
        self._settings = settings
        self._store = store or EventStore()
        self._workflow = workflow_client or InMemoryApprovalWorkflowClient()
        self._notifications = notification_service
        self._monitoring = MonitoringAgent()
        self._logistics = LogisticsAgent()
        self._procurement = ProcurementAgent(ariba, settings)
        self._orchestrator = OrchestratorAgent(llm)
        self._tracking = TrackingAgent()
        self._run_context: dict[
            UUID, tuple[InventorySnapshot, LogisticsResult, ProcurementResult]
        ] = {}

    @property
    def store(self) -> RunStore:
        """Expose the event store to API routes."""

        return self._store

    def run(self, event: DisruptionEvent) -> DisruptionRun:
        """Execute the four agent stages and persist a draft awaiting approval."""

        existing = self._store.get_by_idempotency_key(event.dedupe_key, event.tenant_id)
        if existing is not None:
            return existing
        run = DisruptionRun(event=event, tenant_id=event.tenant_id)
        self._store.save(run)
        try:
            self._transition(run, WorkflowState.MONITORING)
            inventory = retry_integration_call(
                lambda: self._sap.get_inventory(event.component_id),
                attempts=self._settings.retry_attempts,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
            run.inventory_snapshot = inventory.model_copy(deep=True)
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
                self._transition(run, WorkflowState.NOT_SIGNIFICANT)
                run.status = RunStatus.NOT_SIGNIFICANT
                self._skip_remaining_stages(run)
                run.updated_at = datetime.now(UTC)
                self._store.save(run)
                return run

            self._transition(run, WorkflowState.LOGISTICS)
            logistics = self._logistics.analyze(event, inventory)
            run.cost_of_inaction = logistics.cost_of_inaction
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

            self._transition(run, WorkflowState.PROCUREMENT)
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

            self._transition(run, WorkflowState.ORCHESTRATOR)
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
            run.stages.append(
                StageResult(
                    name="Execution & tracking",
                    status="WAITING_FOR_APPROVAL",
                    summary="Supplier confirmation and shipment tracking start after approval.",
                )
            )
            run.status = RunStatus.PENDING_APPROVAL
            self._transition(run, WorkflowState.HUMAN_APPROVAL)
            self._run_context[run.run_id] = (inventory, logistics, procurement)
            run.updated_at = datetime.now(UTC)
            self._store.save(run)
            self._notify(run, "draft_ready")
            return run
        except ChainMindError as exc:
            self._transition(run, WorkflowState.FAILED)
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

    def check_approval_overdue(self, *, now: datetime | None = None) -> int:
        """Notify once for pending approvals older than the configured threshold."""

        current_time = now or datetime.now(UTC)
        overdue_before = current_time.timestamp() - (
            self._settings.notification_approval_overdue_minutes * 60
        )
        notified = 0
        for run in self._store.list():
            if (
                run.status != RunStatus.PENDING_APPROVAL
                or run.approval_overdue_notified
                or run.created_at.timestamp() > overdue_before
            ):
                continue
            if self._notify(run, "approval_overdue"):
                run.approval_overdue_notified = True
                run.audit_log.append(
                    AuditEntry(
                        agent="notifications",
                        input_summary=f"run_id={run.run_id}",
                        output_summary="Approval overdue escalation delivered.",
                        reasoning=(
                            "The approval exceeded the configured "
                            f"{self._settings.notification_approval_overdue_minutes}-minute limit."
                        ),
                    )
                )
                self._store.save(run)
                notified += 1
        return notified

    def decide(self, run_id: UUID, decision: DecisionRequest) -> DecisionResult:
        """Record approval, rejection, or a human-selected vendor revision."""

        run = self.get_run(run_id)
        if run.last_decision == decision and run.status != RunStatus.PENDING_APPROVAL:
            if (
                run.status == RunStatus.APPROVED
                and decision.decision == DecisionType.APPROVE
                and run.execution_tracking is None
            ):
                return self._finish_tracking(run)
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
            self._transition(run, WorkflowState.REJECTED)
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
        self._transition(run, WorkflowState.EXECUTION)
        sap_reference = retry_integration_call(
            lambda: self._sap.execute_purchase_order(run.draft_po),
            attempts=self._settings.retry_attempts,
            base_delay_seconds=self._settings.retry_base_delay_seconds,
        )
        run.status = RunStatus.APPROVED
        run.draft_po.status = "APPROVED"
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
        for stage in run.stages:
            if stage.name == "Execution & tracking":
                stage.status = "IN_PROGRESS"
                stage.summary = (
                    "SAP execution completed; waiting for supplier confirmation and ASN."
                )
        run.updated_at = datetime.now(UTC)
        self._store.save(run)
        return self._finish_tracking(run)

    def _finish_tracking(self, run: DisruptionRun) -> DecisionResult:
        """Submit the approved PO to Ariba and persist its tracking outcome."""

        if run.draft_po is None or run.draft_po.sap_reference is None:
            raise ChainMindError(
                "executed_order_unavailable",
                "Tracking requires a purchase order already executed in SAP.",
                status_code=409,
            )
        try:
            context = self._run_context.get(run.run_id)
            inventory = (
                context[0]
                if context is not None
                else retry_integration_call(
                    lambda: self._sap.get_inventory(run.event.component_id),
                    attempts=self._settings.retry_attempts,
                    base_delay_seconds=self._settings.retry_base_delay_seconds,
                )
            )
            vendor = next(
                (
                    item.vendor
                    for item in run.vendor_comparison
                    if item.vendor.vendor_id == run.draft_po.vendor_id
                ),
                None,
            )
            if vendor is None:
                raise ChainMindError(
                    "tracking_vendor_unavailable",
                    "The selected vendor quote is not available for tracking.",
                    status_code=409,
                    details={"vendor_id": run.draft_po.vendor_id},
                )
            ariba_reference = retry_integration_call(
                lambda: self._ariba.submit_purchase_order(run.draft_po),
                attempts=self._settings.retry_attempts,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
            confirmation = retry_integration_call(
                lambda: self._ariba.get_vendor_confirmation(run.draft_po),
                attempts=self._settings.retry_attempts,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
            shipment = retry_integration_call(
                lambda: self._ariba.get_shipment_tracking(run.draft_po),
                attempts=self._settings.retry_attempts,
                base_delay_seconds=self._settings.retry_base_delay_seconds,
            )
            monitoring_stage = next(
                (stage for stage in run.stages if stage.name == "Monitoring"),
                None,
            )
            draft_stage = next(
                (stage for stage in run.stages if stage.name == "Orchestrator"),
                None,
            )
            response_time_seconds = (
                max((draft_stage.completed_at - monitoring_stage.completed_at).total_seconds(), 0)
                if monitoring_stage is not None and draft_stage is not None
                else None
            )
            tracking, kpis = self._tracking.analyze(
                sap_reference=run.draft_po.sap_reference,
                ariba_reference=ariba_reference,
                order=run.draft_po,
                vendor=vendor,
                inventory=inventory,
                confirmation=confirmation,
                shipment=shipment,
                cost_of_inaction=run.cost_of_inaction,
                estimated_stockout_days=max(
                    run.event.delay_days - inventory.current_stock / inventory.daily_consumption,
                    0,
                ),
                simulated=not (
                    self._settings.mode == "aws" and self._settings.resolved_sap_backend == "real"
                ),
                response_time_seconds=response_time_seconds,
            )
            self._sap.record_inventory_projection(tracking.inventory_projection)
        except ChainMindError as exc:
            run.audit_log.append(
                AuditEntry(
                    agent="execution_tracking",
                    input_summary=f"run_id={run.run_id}; po_id={run.draft_po.po_id}",
                    output_summary=f"Supplier tracking did not complete: {exc.code}.",
                    reasoning=exc.message,
                )
            )
            run.updated_at = datetime.now(UTC)
            self._store.save(run)
            raise

        run.execution_tracking = tracking
        run.kpis = kpis
        run.draft_po.status = "EXECUTED"
        run.status = RunStatus.EXECUTED
        self._transition(run, WorkflowState.COMPLETED)
        tracking_summary = (
            f"Ariba confirmed {confirmation.confirmed_quantity:,} units; "
            f"ETA {shipment.estimated_arrival.isoformat()}; projected stock "
            f"{tracking.inventory_projection.projected_stock_at_arrival:,} units."
        )
        for stage in run.stages:
            if stage.name == "Execution & tracking":
                stage.status = "COMPLETED"
                stage.summary = tracking_summary
        run.audit_log.append(
            AuditEntry(
                agent="execution_tracking",
                input_summary=(
                    f"SAP PO={tracking.sap_reference}; Ariba PO={tracking.ariba_reference}"
                ),
                output_summary=tracking_summary,
                reasoning=(
                    "Supplier confirmation, advance shipment notice, and future stock "
                    "projection were reconciled after explicit approval."
                ),
            )
        )
        if tracking.alert:
            run.audit_log.append(
                AuditEntry(
                    agent="execution_tracking",
                    input_summary=f"tracking_id={shipment.tracking_id}",
                    output_summary=tracking.alert,
                    reasoning="The reported ETA exceeds the selected vendor's quoted lead time.",
                )
            )
            if (
                tracking.eta_deviation_days
                > self._settings.notification_eta_deviation_threshold_days
            ):
                self._notify(run, "tracking_deviation")
        run.chain_of_thought.append(
            f"[SAP Ariba] Supplier confirmed the PO; ASN {shipment.tracking_id} "
            f"estimates arrival {shipment.estimated_arrival.isoformat()}."
        )
        run.chain_of_thought.append(
            f"[SAP S/4HANA] Projected {tracking.inventory_projection.projected_coverage_days:g} "
            "coverage days after receipt; values are illustrative."
        )
        run.updated_at = datetime.now(UTC)
        self._store.save(run)
        return DecisionResult(
            run_id=run.run_id,
            status=run.status,
            message=(
                f"Purchase order executed as {tracking.sap_reference}; "
                "supplier tracking is complete."
            ),
            draft_po=run.draft_po,
        )

    def _notify(self, run: DisruptionRun, event_kind: str) -> bool:
        """Send a channel notification and retain an explicit audit on delivery failure."""

        if self._notifications is None:
            return False
        try:
            message = self._notifications.notify(run, event_kind)
        except ChainMindError as exc:
            run.audit_log.append(
                AuditEntry(
                    agent="notifications",
                    input_summary=f"run_id={run.run_id}; event={event_kind}",
                    output_summary=f"Notification delivery failed: {exc.code}.",
                    reasoning=exc.message,
                )
            )
            self._store.save(run)
            return False
        run.audit_log.append(
            AuditEntry(
                agent="notifications",
                input_summary=f"run_id={run.run_id}; event={event_kind}",
                output_summary=(
                    f"Notification delivered to {self._notifications.channel_count} channel(s)."
                ),
                reasoning=self._notifications.audit_summary(message),
            )
        )
        self._store.save(run)
        return True

    def validate_notification_link(self, token: str) -> NotificationLinkPayload:
        """Validate a signed notification link, if notifications are configured."""

        if self._notifications is None:
            raise ChainMindError(
                "notifications_disabled",
                "Notification links are not enabled.",
                status_code=404,
            )
        return self._notifications.validate_link(token)

    def create_notification_link(
        self,
        run_id: UUID,
        action: str,
    ) -> str:
        """Create a signed action link scoped to a stored run."""

        if action not in {"approve", "view"}:
            raise ChainMindError(
                "invalid_notification_action",
                "Notification link action must be approve or view.",
                status_code=422,
            )
        run = self.get_run(run_id)
        if self._notifications is None:
            raise ChainMindError(
                "notifications_disabled",
                "Notification links are not enabled.",
                status_code=404,
            )
        return self._notifications.create_link(
            run_id,
            action,
            tenant_id=run.tenant_id,
        )

    def _revise(self, run: DisruptionRun, decision: DecisionRequest) -> DecisionResult:
        if not decision.vendor_id:
            raise ChainMindError(
                "vendor_required",
                "A vendor_id is required when requesting a vendor revision.",
                status_code=422,
            )
        if run.revision_count >= self._settings.max_revisions:
            raise ChainMindError(
                "revision_limit_reached",
                "The maximum number of vendor revisions has been reached.",
                status_code=409,
                details={"max_revisions": self._settings.max_revisions},
            )
        self._transition(run, WorkflowState.PROCUREMENT)
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
        self._transition(run, WorkflowState.ORCHESTRATOR)
        new_order = self._orchestrator.draft_purchase_order(revised.selected_vendor, inventory)
        run.draft_po = retry_integration_call(
            lambda: self._sap.create_draft_purchase_order(new_order),
            attempts=self._settings.retry_attempts,
            base_delay_seconds=self._settings.retry_base_delay_seconds,
        )
        if run.workflow_task_id is not None:
            self._workflow.update_draft(run.workflow_task_id, str(run.draft_po.po_id))
        run.selected_vendor_id = revised.selected_vendor.vendor.vendor_id
        run.revision_count += 1
        self._transition(run, WorkflowState.HUMAN_APPROVAL)
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
            stage
            for stage in run.stages
            if stage.name not in {"Human approval", "PO execution", "Execution & tracking"}
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
                StageResult(
                    name="Execution & tracking",
                    status="WAITING_FOR_APPROVAL",
                    summary="Supplier confirmation and shipment tracking start after approval.",
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
    def _transition(run: DisruptionRun, following: WorkflowState) -> None:
        validate_transition(run.workflow_state, following)
        run.workflow_state = following

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
            elif stage.name == "Execution & tracking" and execution_status == "NOT_EXECUTED":
                stage.status = "NOT_EXECUTED"
                stage.summary = "Supplier execution and shipment tracking were not started."
        run.updated_at = datetime.now(UTC)

    @staticmethod
    def _skip_remaining_stages(run: DisruptionRun) -> None:
        for name in (
            "Logistics",
            "Procurement",
            "Orchestrator",
            "Human approval",
            "PO execution",
            "Execution & tracking",
        ):
            run.stages.append(
                StageResult(name=name, status="SKIPPED", summary="Disruption was not significant.")
            )
