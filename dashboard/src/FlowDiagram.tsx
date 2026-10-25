import type { DisruptionRun, Stage } from "./types";
import { translate, type Language } from "./i18n";

type FlowStage = {
  index: number;
  label: string;
  match: string[];
  box: { x: number; y: number; width: number; height: number };
  color: string;
};

const stages: FlowStage[] = [
  { index: 0, label: "flowExternal", match: ["ingestion", "event"], box: { x: 25, y: 25, width: 290, height: 155 }, color: "#64748b" },
  { index: 1, label: "stageDetection", match: ["monitoring"], box: { x: 350, y: 25, width: 300, height: 155 }, color: "#0f766e" },
  { index: 2, label: "stageImpact", match: ["logistics"], box: { x: 895, y: 25, width: 280, height: 155 }, color: "#0284c7" },
  { index: 3, label: "stageSolutions", match: ["procurement"], box: { x: 895, y: 275, width: 280, height: 235 }, color: "#7c3aed" },
  { index: 4, label: "stageDecision", match: ["orchestrator"], box: { x: 555, y: 275, width: 285, height: 190 }, color: "#d97706" },
  { index: 5, label: "stageHuman", match: ["human approval"], box: { x: 25, y: 275, width: 290, height: 170 }, color: "#db2777" },
  { index: 6, label: "stageExecution", match: ["po execution", "execution & tracking"], box: { x: 25, y: 590, width: 390, height: 205 }, color: "#15803d" },
];

function stageFor(run: DisruptionRun, flowStage: FlowStage): Stage | undefined {
  return run.stages.find((stage) =>
    flowStage.match.some((name) => stage.name.toLowerCase().includes(name)),
  );
}

function statusTone(status: string | undefined): string {
  if (status === "COMPLETED") return "complete";
  if (status === "IN_PROGRESS" || status === "PENDING") return "active";
  if (status === "REJECTED" || status === "FAILED") return "failed";
  return "waiting";
}

function detailLines(run: DisruptionRun, flowStage: FlowStage, language: Language): string[] {
  if (flowStage.index === 0) {
    return [
      run.event.title,
      `${run.event.delay_days} ${language === "id" ? "hari keterlambatan" : "days delay"}`,
      "Amazon EventBridge · SAP Event Mesh",
    ];
  }
  if (flowStage.index === 1) {
    return [
      `${translate(language, "severity")}: ${run.severity ?? "—"}`,
      `${language === "id" ? "Cakupan stok" : "Stock coverage"}: ${coverage(run)} ${language === "id" ? "hari" : "days"}`,
      "Monitoring Agent · DynamoDB",
    ];
  }
  if (flowStage.index === 2) {
    return [
      `${language === "id" ? "Material" : "Material"}: ${run.inventory_snapshot?.component_name ?? run.event.component_name}`,
      `${language === "id" ? "Risiko stockout" : "Stockout risk"}: ${Math.max(0, run.event.delay_days - coverage(run))} ${language === "id" ? "hari" : "days"}`,
      "Logistics Agent · SAP S/4HANA",
    ];
  }
  if (flowStage.index === 3) {
    const vendors = run.vendor_comparison.slice(0, 4).map((evaluation) =>
      `${evaluation.vendor.vendor_name}: ${evaluation.vendor.lead_time_days}d · $${evaluation.action_cost.toLocaleString("en-US")} · risk ${evaluation.vendor.risk_score}`,
    );
    return [...vendors, "Procurement Agent · SAP Ariba"];
  }
  if (flowStage.index === 4) {
    const chosen = run.vendor_comparison.find((item) => item.vendor.vendor_id === run.selected_vendor_id);
    return [
      `${language === "id" ? "Vendor terpilih" : "Selected vendor"}: ${chosen?.vendor.vendor_name ?? "—"}`,
      `${language === "id" ? "Biaya inaction" : "Cost of inaction"}: $${run.cost_of_inaction.toLocaleString("en-US")}`,
      `Orchestrator Agent · Amazon Bedrock`,
    ];
  }
  if (flowStage.index === 5) {
    return [
      run.draft_po ? `${language === "id" ? "Draf" : "Draft"} ${shortPo(run)}` : (language === "id" ? "Belum ada PO" : "No PO yet"),
      run.draft_po ? `${run.draft_po.quantity.toLocaleString("en-US")} pcs · $${run.draft_po.unit_price}/unit` : "",
      run.draft_po ? `$${run.draft_po.total_price.toLocaleString("en-US")} · ${run.draft_po.terms}` : "",
      run.draft_po?.expected_date ? `${translate(language, "expectedDate")}: ${run.draft_po.expected_date}` : "",
      run.status === "PENDING_APPROVAL" ? "PENDING_APPROVAL" : run.status,
      "Human approval · SAP S/4HANA",
    ].filter(Boolean);
  }
  return [
    run.execution_tracking
      ? `${run.execution_tracking.shipment.tracking_id} · ETA ${run.execution_tracking.shipment.estimated_arrival}`
      : (language === "id" ? "Menunggu persetujuan manusia" : "Waiting for human approval"),
    run.execution_tracking
      ? `${language === "id" ? "Stok proyeksi" : "Projected stock"}: ${run.execution_tracking.inventory_projection.projected_stock_at_arrival.toLocaleString()} pcs`
      : "",
    run.execution_tracking?.alert ?? (language === "id" ? "Pantau pengiriman · update ETA · alert deviasi" : "Monitor shipment · update ETA · deviation alerts"),
    "SAP S/4HANA · SAP Ariba · CloudWatch",
  ].filter(Boolean);
}

function coverage(run: DisruptionRun): number {
  const inventory = run.inventory_snapshot;
  return inventory ? inventory.current_stock / inventory.daily_consumption : 0;
}

function shortPo(run: DisruptionRun): string {
  const identifier = run.draft_po?.po_id.replace(/[^a-z0-9]/gi, "").slice(0, 4).toUpperCase();
  return identifier ? `DRAFT-${identifier}` : "DRAFT";
}

function isCompleted(stage: Stage | undefined): boolean {
  return stage?.status === "COMPLETED";
}

export function FlowDiagram({ run, language = "id" }: { run: DisruptionRun; language?: Language }) {
  const stageStates = stages.map((stage) => stageFor(run, stage));
  const approved = run.status === "EXECUTED" || run.status === "APPROVED";
  const rejected = run.status === "REJECTED";
  const revised = (run.revision_count ?? 0) > 0;
  const significant = run.significant;
  const arrows = [
    { id: "ingestion-monitoring", d: "M315 102 H350", active: true },
    { id: "monitoring-significant", d: "M650 102 H695", active: isCompleted(stageStates[1]) },
    { id: "significant-impact", d: "M845 102 H895", active: significant },
    { id: "insignificant-end", d: "M770 152 V215", active: !significant },
    { id: "impact-procurement", d: "M1035 180 V275", active: isCompleted(stageStates[2]) },
    { id: "procurement-decision", d: "M895 390 H840", active: isCompleted(stageStates[3]) },
    { id: "decision-approval", d: "M555 370 H520", active: isCompleted(stageStates[4]) },
    { id: "approval-human", d: "M370 370 H315", active: run.status === "PENDING_APPROVAL" || approved || rejected || revised },
    { id: "human-execution", d: "M170 445 V590", active: approved },
    { id: "revision-loop", d: "M445 410 V545 H1035 V510", active: revised },
    { id: "rejection-end", d: "M370 385 V500 H250", active: rejected },
  ];

  return (
    <section aria-label={translate(language, "flowTitle")} className="space-y-4">
      <h2 className="text-xl font-bold text-ink">{translate(language, "flowTitle")}</h2>
      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white p-3">
        <svg
          aria-label={translate(language, "flowDiagram")}
          className="h-auto min-w-[900px] w-full"
          role="img"
          viewBox="0 0 1200 830"
        >
          <defs>
            <marker id="flow-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
              <path d="M0,0 L8,4 L0,8 z" fill="#64748b" />
            </marker>
            <marker id="flow-arrow-active" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
              <path d="M0,0 L8,4 L0,8 z" fill="#0f766e" />
            </marker>
          </defs>
          {arrows.map((arrow) => (
            <path
              key={arrow.id}
              className={arrow.active ? "flow-arrow-active" : "flow-arrow"}
              d={arrow.d}
              fill="none"
              markerEnd={`url(#${arrow.active ? "flow-arrow-active" : "flow-arrow"})`}
              stroke={arrow.active ? "#0f766e" : "#94a3b8"}
              strokeDasharray={arrow.active ? undefined : "6 5"}
              strokeWidth={arrow.active ? 4 : 2}
              data-testid={`flow-branch-${arrow.id}`}
              data-active={arrow.active}
            />
          ))}
          <g role="group" aria-label={translate(language, "significanceDecision")} data-testid="flow-decision-significant">
            <polygon points="770,45 845,102 770,159 695,102" fill={significant ? "#ccfbf1" : "#fef3c7"} stroke={significant ? "#0f766e" : "#d97706"} strokeWidth="3" />
            <text x="770" y="96" textAnchor="middle" className="flow-decision">{language === "id" ? "Gangguan" : "Significant"}</text>
            <text x="770" y="116" textAnchor="middle" className="flow-decision">{language === "id" ? "Signifikan?" : "disruption?"}</text>
          </g>
          <g role="group" aria-label={translate(language, "approvalDecision")} data-testid="flow-decision-approval">
            <polygon points="445,315 520,372 445,429 370,372" fill={approved ? "#dcfce7" : rejected ? "#ffe4e6" : "#fef3c7"} stroke={approved ? "#15803d" : rejected ? "#be123c" : "#d97706"} strokeWidth="3" />
            <text x="445" y="366" textAnchor="middle" className="flow-decision">{language === "id" ? "Setujui" : "Approve"}</text>
            <text x="445" y="386" textAnchor="middle" className="flow-decision">{language === "id" ? "Rekomendasi?" : "recommendation?"}</text>
          </g>
          <text x="855" y="88" className="flow-branch-label">{language === "id" ? "YA" : "YES"}</text>
          <text x="780" y="195" className="flow-branch-label">{language === "id" ? "TIDAK → Selesai" : "NO → Done"}</text>
          <text x="340" y="356" className="flow-branch-label">{language === "id" ? "YA" : "YES"}</text>
          <text x="447" y="530" className="flow-branch-label">{language === "id" ? "REVISI → ulangi" : "REVISE → retry"}</text>
          <text x="305" y="490" className="flow-branch-label">{language === "id" ? "TOLAK → Selesai" : "REJECT → Done"}</text>
          <g data-testid="flow-insignificant-end">
            <rect x="690" y="210" width="160" height="48" rx="16" fill={!significant ? "#ccfbf1" : "#f1f5f9"} stroke={!significant ? "#0f766e" : "#cbd5e1"} strokeWidth="2" />
            <text x="770" y="240" textAnchor="middle" className="flow-branch-label">{language === "id" ? "Selesai" : "Done"}</text>
          </g>
          <text x="26" y="837" className="flow-footer">
            AWS: EventBridge · Step Functions · Lambda · DynamoDB · S3 · Bedrock  |  SAP: S/4HANA · Ariba · Integration Suite · Event Mesh
          </text>
          {stages.map((flowStage) => {
            const stage = stageStates[flowStage.index];
            const status = flowStage.index === 0 ? (stageStates[1]?.status ?? "WAITING") : stage?.status;
            const lines = detailLines(run, flowStage, language);
            return (
              <foreignObject
                key={flowStage.index}
                x={flowStage.box.x}
                y={flowStage.box.y}
                width={flowStage.box.width}
                height={flowStage.box.height}
                data-testid={`flow-stage-${flowStage.index}`}
                data-status={statusTone(status)}
              >
                <div
                  className={`flow-node flow-node-${statusTone(status)}`}
                  style={{ borderTopColor: flowStage.color }}
                  aria-label={`${translate(language, flowStage.label)}: ${status ?? "WAITING"}`}
                >
                  <div className="flow-node-heading">
                    <span className="flow-node-index">0{flowStage.index}</span>
                    <strong>{translate(language, flowStage.label)}</strong>
                    <span className="flow-node-status">{status?.replaceAll("_", " ") ?? "WAITING"}</span>
                  </div>
                  <ul>
                    {lines.map((line) => <li key={line}>{line}</li>)}
                  </ul>
                </div>
              </foreignObject>
            );
          })}
        </svg>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-slate-600" aria-label={translate(language, "flowLegend")}>
        <span><i className="flow-legend flow-legend-data" /> {translate(language, "legendData")}</span>
        <span><i className="flow-legend flow-legend-ai" /> {translate(language, "legendAi")}</span>
        <span><i className="flow-legend flow-legend-solution" /> {translate(language, "legendSolution")}</span>
        <span><i className="flow-legend flow-legend-decision" /> {translate(language, "legendDecision")}</span>
        <span><i className="flow-legend flow-legend-approval" /> {translate(language, "legendApproval")}</span>
        <span><i className="flow-legend flow-legend-execution" /> {translate(language, "legendExecution")}</span>
        <span><i className="flow-legend flow-legend-arrow" /> {translate(language, "legendActivePath")}</span>
      </div>
    </section>
  );
}
