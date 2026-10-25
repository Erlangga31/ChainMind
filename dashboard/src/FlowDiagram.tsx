import type { CSSProperties } from "react";
import type { DisruptionRun, Stage } from "./types";
import { translate, type Language } from "./i18n";

type FlowStage = {
  index: number;
  label: string;
  match: string[];
  color: string;
};

type FlowCardProps = {
  x: number;
  y: number;
  width: number;
  height: number;
  title: string;
  lines: string[];
  color: string;
  status?: string;
  testId?: string;
};

const stages: FlowStage[] = [
  { index: 0, label: "flowExternal", match: ["ingestion", "event"], color: "#64748b" },
  { index: 1, label: "stageDetection", match: ["monitoring"], color: "#2563eb" },
  { index: 2, label: "stageImpact", match: ["logistics"], color: "#16a34a" },
  { index: 3, label: "stageSolutions", match: ["procurement"], color: "#ea580c" },
  { index: 4, label: "stageDecision", match: ["orchestrator"], color: "#7c3aed" },
  { index: 5, label: "stageHuman", match: ["human approval"], color: "#e11d48" },
  { index: 6, label: "stageExecution", match: ["po execution", "execution & tracking"], color: "#0891b2" },
];

const lanes = [
  { index: 1, y: 205, height: 155, color: "#2563eb", fill: "#eff6ff" },
  { index: 2, y: 375, height: 170, color: "#16a34a", fill: "#f0fdf4" },
  { index: 3, y: 560, height: 170, color: "#ea580c", fill: "#fff7ed" },
  { index: 4, y: 745, height: 170, color: "#7c3aed", fill: "#faf5ff" },
  { index: 5, y: 930, height: 190, color: "#e11d48", fill: "#fff1f2" },
  { index: 6, y: 1135, height: 185, color: "#0891b2", fill: "#ecfeff" },
];

function stageFor(run: DisruptionRun, flowStage: FlowStage): Stage | undefined {
  return run.stages.find((stage) =>
    flowStage.match.some((name) => stage.name.toLowerCase().includes(name)),
  );
}

function statusTone(status: string | undefined): string {
  if (status === "COMPLETED") return "complete";
  if (status === "IN_PROGRESS" || status === "PENDING" || status === "PENDING_APPROVAL") return "active";
  if (status === "REJECTED" || status === "FAILED") return "failed";
  return "waiting";
}

function money(amount: number): string {
  return `$${amount.toLocaleString("en-US")}`;
}

function coverage(run: DisruptionRun): number {
  const inventory = run.inventory_snapshot;
  return inventory ? inventory.current_stock / inventory.daily_consumption : 0;
}

function selectedVendorName(run: DisruptionRun): string {
  return run.vendor_comparison.find((item) => item.vendor.vendor_id === run.selected_vendor_id)?.vendor.vendor_name ?? "—";
}

function shortPo(run: DisruptionRun): string {
  const identifier = run.draft_po?.po_id.replace(/[^a-z0-9]/gi, "").slice(0, 4).toUpperCase();
  return identifier ? `DRAFT-${identifier}` : "DRAFT";
}

function stageDetails(run: DisruptionRun, index: number, language: Language): string[] {
  const unit = language === "id" ? "hari" : "days";
  const selectedVendor = run.vendor_comparison.find((item) => item.vendor.vendor_id === run.selected_vendor_id);
  if (index === 0) {
    return [
      run.event.title,
      `${run.event.delay_days} ${language === "id" ? "hari keterlambatan" : "days delayed"} · ${run.event.component_name}`,
      language === "id" ? "Cuaca · logistik · geopolitik · vendor" : "Weather · logistics · geopolitical · vendor",
    ];
  }
  if (index === 1) {
    return [
      `${translate(language, "severity")}: ${run.severity ?? "—"}`,
      `${language === "id" ? "Klasifikasi" : "Classification"}: ${run.significant ? (language === "id" ? "signifikan" : "significant") : (language === "id" ? "tidak signifikan" : "not significant")}`,
      `${language === "id" ? "Cakupan stok" : "Stock coverage"}: ${coverage(run)} ${unit}`,
    ];
  }
  if (index === 2) {
    const inventory = run.inventory_snapshot;
    return [
      `${language === "id" ? "Stok saat ini" : "Current stock"}: ${inventory?.current_stock.toLocaleString("en-US") ?? "—"} pcs`,
      `${language === "id" ? "Konsumsi harian" : "Daily consumption"}: ${inventory?.daily_consumption.toLocaleString("en-US") ?? "—"} pcs`,
      `${language === "id" ? "Cakupan / keterlambatan" : "Coverage / delay"}: ${coverage(run)} / ${run.event.delay_days} ${unit}`,
      `${language === "id" ? "Risiko stockout" : "Stockout risk"}: ${Math.max(0, run.event.delay_days - coverage(run))} ${unit}`,
    ];
  }
  if (index === 3) {
    return [...run.vendor_comparison]
      .sort((left, right) => left.vendor.vendor_name.localeCompare(right.vendor.vendor_name))
      .slice(0, 4)
      .map((evaluation) =>
      `${evaluation.vendor.vendor_name}: ${evaluation.vendor.lead_time_days}d · ${money(evaluation.action_cost)} · risk ${evaluation.vendor.risk_score}`,
      );
  }
  if (index === 4) {
    return [
      `${language === "id" ? "Vendor terpilih" : "Selected vendor"}: ${selectedVendor?.vendor.vendor_name ?? "—"}`,
      `${language === "id" ? "Biaya tanpa tindakan" : "Cost of inaction"}: ${money(run.cost_of_inaction)}`,
      `${language === "id" ? "Biaya tindakan" : "Cost of action"}: ${money(selectedVendor?.action_cost ?? 0)}`,
      `${language === "id" ? "Rekomendasi" : "Recommendation"}: ${selectedVendor?.rationale ?? "—"}`,
    ];
  }
  if (index === 5) {
    const po = run.draft_po;
    return [
      po ? `${shortPo(run)} · ${po.status}` : (language === "id" ? "Draf PO belum dibuat" : "Draft PO not created"),
      po ? `${po.quantity.toLocaleString("en-US")} pcs ${po.component_name} · ${money(po.unit_price)}/unit` : "",
      po ? `${money(po.total_price)} · ${po.vendor_name} · ${po.terms}` : "",
      po?.expected_date ? `${translate(language, "expectedDate")}: ${po.expected_date}` : "",
    ].filter(Boolean);
  }
  const tracking = run.execution_tracking;
  return tracking?.monitoring_outputs.length
    ? tracking.monitoring_outputs.map((output) => output.summary)
    : [
        language === "id" ? "Menunggu persetujuan manusia" : "Waiting for human approval",
        language === "id" ? "Pantau pengiriman" : "Monitor shipment",
        language === "id" ? "Perbarui ETA · inventaris" : "Update ETA · inventory",
        language === "id" ? "Peringatan deviasi" : "Deviation alert",
        language === "id" ? "KPI tercapai" : "KPI achieved",
      ];
}

function FlowCard({
  x,
  y,
  width,
  height,
  title,
  lines,
  color,
  status,
  testId,
}: FlowCardProps) {
  const style = { borderTopColor: color } as CSSProperties;
  const tone = statusTone(status);
  return (
    <foreignObject
      x={x}
      y={y}
      width={width}
      height={height}
      data-testid={testId}
      data-status={status ? tone : undefined}
      aria-label={status ? `${title}: ${status}` : title}
    >
      <div className={`flow-node flow-card flow-node-${tone}`} style={style}>
        <div className="flow-node-heading">
          <strong>{title}</strong>
          {status && <span className="flow-node-status">{status.replaceAll("_", " ")}</span>}
        </div>
        <ul>{lines.filter(Boolean).map((line) => <li key={line}>{line}</li>)}</ul>
      </div>
    </foreignObject>
  );
}

function StaticCard({
  x,
  y,
  width,
  height,
  title,
  lines,
  color,
  testId,
}: Omit<FlowCardProps, "status">) {
  return <FlowCard x={x} y={y} width={width} height={height} title={title} lines={lines} color={color} testId={testId} />;
}

export function FlowDiagram({ run, language = "id" }: { run: DisruptionRun; language?: Language }) {
  const stageStates = stages.map((stage) => stageFor(run, stage));
  const completed = (index: number) => stageStates[index]?.status === "COMPLETED";
  const approved = run.status === "EXECUTED" || run.status === "APPROVED";
  const rejected = run.status === "REJECTED";
  const revised = (run.revision_count ?? 0) > 0;
  const significant = run.significant;
  const yes = language === "id" ? "YA" : "YES";
  const no = language === "id" ? "TIDAK" : "NO";
  const arrows = [
    { id: "external-ingestion", d: "M460 120 H560", active: true },
    { id: "ingestion-monitoring", d: "M860 178 V195 H550 V225", active: true },
    { id: "monitoring-significant", d: "M430 285 H455", active: completed(1) },
    { id: "significant-impact", d: "M760 325 V365 H285 V375", active: significant },
    { id: "insignificant-end", d: "M820 285 H920", active: !significant },
    { id: "impact-procurement", d: "M1095 475 V550 H285 V560", active: completed(2) },
    { id: "procurement-decision", d: "M1095 660 V735 H285 V745", active: completed(3) },
    { id: "decision-approval", d: "M1095 845 V920 H285 V930", active: completed(4) },
    { id: "approval-human", d: "M575 1025 H635", active: run.status === "PENDING_APPROVAL" || approved || rejected || revised },
    { id: "human-execution", d: "M910 1100 V1130 H285 V1135", active: approved },
    { id: "revision-loop", d: "M1035 1060 H1170 V735 H285 V775", active: revised },
    { id: "rejection-end", d: "M575 1050 H610 V1110 H1100 V1095", active: rejected },
  ];

  return (
    <section aria-label={translate(language, "flowTitle")} className="space-y-4">
      <h2 className="text-xl font-bold text-ink">{translate(language, "flowTitle")}</h2>
      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white p-3">
        <svg
          aria-label={translate(language, "flowDiagram")}
          className="h-auto min-w-[1000px] w-full"
          role="img"
          viewBox="0 0 1200 1445"
        >
          <defs>
            <marker id="flow-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
              <path d="M0,0 L8,4 L0,8 z" fill="#64748b" />
            </marker>
            <marker id="flow-arrow-active" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
              <path d="M0,0 L8,4 L0,8 z" fill="#0f766e" />
            </marker>
          </defs>

          <text x="30" y="30" className="flow-title">CHAINMIND — Autonomous Disruption Resolver</text>
          <text x="30" y="49" className="flow-subtitle">
            {language === "id" ? "Alur End-to-End (AWS & SAP Native)" : "End-to-End Flow (AWS & SAP Native)"}
          </text>

          <rect x="20" y="60" width="1160" height="130" rx="12" fill="#f8fafc" stroke="#94a3b8" />
          <text x="35" y="82" className="flow-lane-title">
            {language === "id" ? "0. GANGGUAN EKSTERNAL" : "0. EXTERNAL DISRUPTION"}
          </text>
          <FlowCard
            x={30}
            y={92}
            width={430}
            height={86}
            title={language === "id" ? "Sumber gangguan" : "Disruption sources"}
            lines={[
              run.event.title,
              `${run.event.component_name} · ${run.event.delay_days} ${language === "id" ? "hari" : "days"}`,
              language === "id" ? "Cuaca · logistik · geopolitik · vendor" : "Weather · logistics · geopolitical · vendor",
            ]}
            color={stages[0].color}
            status={stageStates[1]?.status ?? "WAITING"}
            testId="flow-stage-0"
          />
          <StaticCard
            x={560}
            y={92}
            width={600}
            height={86}
            title={language === "id" ? "AWS — Lapisan Ingestion Event" : "AWS — Event Ingestion Layer"}
            lines={[
              "AWS Lambda (Event Receiver) → Amazon EventBridge (Event Bus)",
              "AWS Step Functions · SAP Event Mesh (simulated)",
            ]}
            color="#7c3aed"
          />

          {lanes.map((lane) => (
            <g key={lane.index}>
              <rect
                x="20"
                y={lane.y}
                width="1160"
                height={lane.height}
                rx="12"
                fill={lane.fill}
                stroke={lane.color}
                strokeOpacity="0.55"
              />
              <rect x="30" y={lane.y + 10} width="135" height={lane.height - 20} rx="8" fill="#fff" stroke={lane.color} />
              <circle cx="49" cy={lane.y + 32} r="13" fill={lane.color} />
              <text x="49" y={lane.y + 36} textAnchor="middle" className="flow-lane-number">
                {lane.index}
              </text>
              <foreignObject x="43" y={lane.y + 52} width="112" height={lane.height - 65}>
                <div className="flow-lane-label" style={{ color: lane.color }}>
                  {translate(language, stages[lane.index].label)}
                </div>
              </foreignObject>
            </g>
          ))}

          {arrows.map((arrow) => (
            <path
              key={arrow.id}
              className={arrow.active ? "flow-arrow-active" : "flow-arrow"}
              d={arrow.d}
              fill="none"
              markerEnd={`url(#${arrow.active ? "flow-arrow-active" : "flow-arrow"})`}
              stroke={arrow.active ? "#0f766e" : "#94a3b8"}
              strokeDasharray={arrow.active ? undefined : "6 5"}
              strokeWidth={arrow.active ? 3 : 2}
              data-testid={`flow-branch-${arrow.id}`}
              data-active={arrow.active}
            />
          ))}

          <FlowCard
            x={190} y={225} width={240} height={105}
            title="Monitoring Agent"
            lines={stageDetails(run, 1, language)}
            color={lanes[0].color}
            status={stageStates[1]?.status}
            testId="flow-stage-1"
          />
          <StaticCard
            x={455} y={225} width={190} height={105}
            title="Amazon DynamoDB"
            lines={[language === "id" ? "Event Store" : "Event store", language === "id" ? "Simpan event · audit · monitoring" : "Persist event · audit · monitoring"]}
            color={lanes[0].color}
          />
          <g role="group" aria-label={translate(language, "significanceDecision")} data-testid="flow-decision-significant">
            <polygon points="760,245 820,285 760,325 700,285" fill={significant ? "#dbeafe" : "#fef3c7"} stroke={significant ? "#2563eb" : "#d97706"} strokeWidth="2" />
            <text x="760" y="281" textAnchor="middle" className="flow-decision">{language === "id" ? "Gangguan" : "Significant"}</text>
            <text x="760" y="297" textAnchor="middle" className="flow-decision">{language === "id" ? "Signifikan?" : "disruption?"}</text>
          </g>
          <text x="768" y="350" className="flow-branch-label">{yes}</text>
          <text x="855" y="277" className="flow-branch-label">{no}</text>
          <g data-testid="flow-insignificant-end">
            <rect x="920" y="255" width="180" height="60" rx="10" fill={!significant ? "#dbeafe" : "#fff"} stroke={!significant ? "#2563eb" : "#cbd5e1"} />
            <text x="1010" y="280" textAnchor="middle" className="flow-subnode-title">{language === "id" ? "Selesai" : "Done"}</text>
            <text x="1010" y="298" textAnchor="middle" className="flow-subnode-copy">{language === "id" ? "(Monitoring)" : "(Monitoring)"}</text>
          </g>

          <FlowCard
            x={190} y={405} width={190} height={115}
            title="Logistics Agent"
            lines={stageDetails(run, 2, language)}
            color={lanes[1].color}
            status={stageStates[2]?.status}
            testId="flow-stage-2"
          />
          <StaticCard
            x={390} y={405} width={170} height={115}
            title="SAP S/4HANA"
            lines={["Inventory · BOM", "Production schedule", "Scheduled receipts"]}
            color={lanes[1].color}
          />
          <StaticCard
            x={570} y={405} width={205} height={115}
            title={language === "id" ? "Analisis Dampak" : "Impact Analysis"}
            lines={[
              `${language === "id" ? "Stok saat ini" : "Current stock"}: ${run.inventory_snapshot?.current_stock.toLocaleString("en-US") ?? "—"} pcs`,
              `${language === "id" ? "Konsumsi harian" : "Daily consumption"}: ${run.inventory_snapshot?.daily_consumption.toLocaleString("en-US") ?? "—"} pcs`,
              `${language === "id" ? "Cakupan" : "Coverage"}: ${coverage(run)} ${language === "id" ? "hari" : "days"}`,
            ]}
            color={lanes[1].color}
          />
          <StaticCard
            x={785} y={405} width={330} height={115}
            title={language === "id" ? "Hasil Analisis" : "Analysis Results"}
            lines={[
              `${language === "id" ? "Risiko lini" : "Line risk"}: ${Math.max(0, run.event.delay_days - coverage(run))} ${language === "id" ? "hari stockout" : "stockout days"}`,
              `${language === "id" ? "Dampak finansial" : "Financial impact"}: ${money(run.cost_of_inaction)}`,
              `${language === "id" ? "Rekomendasi" : "Recommendation"}: ${selectedVendorName(run)}`,
            ]}
            color={lanes[1].color}
          />

          <FlowCard
            x={190} y={590} width={185} height={115}
            title="Procurement Agent"
            lines={[
              language === "id" ? "Cari vendor alternatif" : "Find alternate vendors",
              language === "id" ? "Evaluasi biaya · lead time · risiko" : "Compare cost · lead time · risk",
              `${run.vendor_comparison.length} ${language === "id" ? "vendor dibandingkan" : "vendors compared"}`,
            ]}
            color={lanes[2].color}
            status={stageStates[3]?.status}
            testId="flow-stage-3"
          />
          <StaticCard
            x={385} y={590} width={175} height={115}
            title="SAP Ariba Network"
            lines={["Vendor list · capacity", "Lead time · price", "Rating · risk score"]}
            color={lanes[2].color}
          />
          <StaticCard
            x={570} y={590} width={190} height={115}
            title={language === "id" ? "Evaluasi Vendor" : "Vendor Evaluation"}
            lines={[
              language === "id" ? "Ketersediaan stok" : "Stock availability",
              language === "id" ? "Kelayakan · kualitas" : "Feasibility · quality",
              language === "id" ? "Risiko & biaya total" : "Risk & total cost",
            ]}
            color={lanes[2].color}
          />
          <StaticCard
            x={770} y={580} width={345} height={140}
            title={language === "id" ? "Perbandingan Vendor" : "Vendor Comparison"}
            lines={stageDetails(run, 3, language)}
            color={lanes[2].color}
          />

          <FlowCard
            x={190} y={775} width={190} height={115}
            title="Orchestrator Agent"
            lines={[
              language === "id" ? "Bandingkan opsi & biaya" : "Compare options & costs",
              language === "id" ? "Pilih solusi optimal" : "Select best economic option",
            ]}
            color={lanes[3].color}
            status={stageStates[4]?.status}
            testId="flow-stage-4"
          />
          <StaticCard
            x={390} y={775} width={190} height={115}
            title={language === "id" ? "Analisis Ekonomi" : "Economic Analysis"}
            lines={[
              `${language === "id" ? "Biaya inaction" : "Cost of inaction"}: ${money(run.cost_of_inaction)}`,
              `${language === "id" ? "Biaya aksi" : "Action cost"}: ${money(run.vendor_comparison.find((item) => item.vendor.vendor_id === run.selected_vendor_id)?.action_cost ?? 0)}`,
              "ROI · benefit",
            ]}
            color={lanes[3].color}
          />
          <StaticCard
            x={590} y={775} width={210} height={115}
            title={language === "id" ? "Rekomendasi AI" : "AI Recommendation"}
            lines={[
              `${language === "id" ? "Vendor" : "Vendor"}: ${run.vendor_comparison.find((item) => item.vendor.vendor_id === run.selected_vendor_id)?.vendor.vendor_name ?? "—"}`,
              `${language === "id" ? "Lead time" : "Lead time"}: ${run.vendor_comparison.find((item) => item.vendor.vendor_id === run.selected_vendor_id)?.vendor.lead_time_days ?? "—"} ${language === "id" ? "hari" : "days"}`,
              "Amazon Bedrock · rule-based mock",
            ]}
            color={lanes[3].color}
          />
          <FlowCard
            x={810} y={765} width={305} height={135}
            title={language === "id" ? "Draf Purchase Order" : "Draft Purchase Order"}
            lines={stageDetails(run, 5, language)}
            color={lanes[3].color}
            status={run.draft_po?.status ?? "WAITING"}
            testId="flow-stage-4-po"
          />

          <FlowCard
            x={190} y={960} width={185} height={130}
            title={language === "id" ? "Human / Procurement" : "Human / Procurement"}
            lines={[
              language === "id" ? "Tinjau rekomendasi AI" : "Review AI recommendation",
              language === "id" ? "Cek vendor & dampak finansial" : "Check vendor & financial impact",
              language === "id" ? "Ambil keputusan" : "Record decision",
            ]}
            color={lanes[4].color}
            status={stageStates[5]?.status}
            testId="flow-stage-5"
          />
          <StaticCard
            x={385} y={960} width={190} height={130}
            title={language === "id" ? "Dashboard Review" : "Dashboard Review"}
            lines={[
              run.draft_po ? `${shortPo(run)} · ${run.draft_po.vendor_name}` : (language === "id" ? "Ringkasan run" : "Run summary"),
              language === "id" ? "Bandingkan rekomendasi" : "Review recommendation",
              "SAP Business Workflow (simulated)",
            ]}
            color={lanes[4].color}
          />
          <g role="group" aria-label={translate(language, "approvalDecision")} data-testid="flow-decision-approval">
            <polygon points="715,960 795,1000 715,1040 635,1000" fill={approved ? "#dcfce7" : rejected ? "#ffe4e6" : "#fff7ed"} stroke={approved ? "#16a34a" : rejected ? "#be123c" : "#e11d48"} strokeWidth="2" />
            <text x="715" y="996" textAnchor="middle" className="flow-decision">{language === "id" ? "Setujui" : "Approve"}</text>
            <text x="715" y="1012" textAnchor="middle" className="flow-decision">{language === "id" ? "Rekomendasi?" : "recommendation?"}</text>
          </g>
          <text x="805" y="987" className="flow-branch-label">{yes}</text>
          <text x="725" y="1060" className="flow-branch-label">{no}</text>
          <StaticCard
            x={830} y={945} width={185} height={72}
            title={language === "id" ? "Setujui" : "Approve"}
            lines={[language === "id" ? "Lanjutkan eksekusi PO" : "Proceed to PO execution"]}
            color="#16a34a"
          />
          <StaticCard
            x={830} y={1025} width={205} height={75}
            title={language === "id" ? "Revisi / pilih opsi lain" : "Revise / choose another option"}
            lines={[language === "id" ? "Pilih vendor · ulangi analisis" : "Select vendor · rerun analysis"]}
            color="#e11d48"
          />
          <g data-testid="flow-rejection-end">
            <rect x="1040" y="1030" width="120" height="64" rx="8" fill={rejected ? "#ffe4e6" : "#fff"} stroke={rejected ? "#be123c" : "#cbd5e1"} />
            <text x="1100" y="1057" textAnchor="middle" className="flow-subnode-title">{language === "id" ? "Ditolak" : "Rejected"}</text>
            <text x="1100" y="1076" textAnchor="middle" className="flow-subnode-copy">{language === "id" ? "Tanpa eksekusi" : "No execution"}</text>
          </g>

          <FlowCard
            x={180} y={1170} width={185} height={125}
            title={language === "id" ? "Kirim ke SAP" : "Send to SAP"}
            lines={["SAP Integration Suite", language === "id" ? "Validasi · mapping · data PO" : "Validate · map · PO data"]}
            color={lanes[5].color}
            status={stageStates[6]?.status}
            testId="flow-stage-6"
          />
          <StaticCard x={375} y={1170} width={175} height={125} title="SAP S/4HANA" lines={["Create Purchase Order", "PO number · final status", "Update PO status"]} color={lanes[5].color} />
          <StaticCard x={560} y={1170} width={180} height={125} title="SAP Ariba Network" lines={["PO sent to vendor", "Vendor confirmation", "ASN / delivery"]} color={lanes[5].color} />
          <StaticCard
            x={750} y={1170} width={255} height={125}
            title={language === "id" ? "Monitoring & Tracking" : "Monitoring & Tracking"}
            lines={stageDetails(run, 6, language)}
            color={lanes[5].color}
            testId="flow-stage-6-tracking"
          />
          <StaticCard
            x={1015} y={1170} width={145} height={125}
            title={language === "id" ? "Selesai" : "Done"}
            lines={[
              language === "id" ? "Gangguan ditangani" : "Disruption handled",
              language === "id" ? "Produksi aman" : "Production protected",
              language === "id" ? "KPI ilustratif" : "Illustrative KPI",
            ]}
            color="#16a34a"
          />

          <line x1="25" y1="1350" x2="1175" y2="1350" stroke="#cbd5e1" />
          <text x="30" y="1378" className="flow-footer">
            AWS: Lambda · EventBridge · Step Functions · DynamoDB · Bedrock · CloudWatch · S3
          </text>
          <text x="30" y="1399" className="flow-footer">
            SAP: S/4HANA · Ariba Network · BTP · Integration Suite · Event Mesh · Business Workflow · IAS
          </text>
          <text x="30" y="1420" className="flow-footer">
            {language === "id" ? "AGEN UTAMA" : "PRIMARY AGENTS"}: Monitoring · Logistics · Procurement · Orchestrator
          </text>
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
