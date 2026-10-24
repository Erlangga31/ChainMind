import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DisruptionRun, KPIReport, VendorEvaluation } from "./types";

const timeline = [
  { label: "Deteksi Gangguan", match: ["monitoring"] },
  { label: "Analisis Dampak", match: ["logistics"] },
  { label: "Pencarian Solusi", match: ["procurement"] },
  { label: "Analisis & Keputusan", match: ["orchestrator"] },
  { label: "Human-in-the-Loop", match: ["human approval"] },
  { label: "Eksekusi Purchase Order", match: ["po execution", "execution & tracking"] },
];

export function WorkflowTimeline({ run }: { run: DisruptionRun }) {
  return (
    <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {timeline.map((item, index) => {
        const stages = run.stages.filter((stage) =>
          item.match.some((name) => stage.name.toLowerCase().includes(name)),
        );
        const status =
          stages.find((stage) => stage.status === "COMPLETED")?.status ??
          stages[0]?.status ??
          "WAITING";
        const isActive = status === "PENDING" || status === "IN_PROGRESS";
        return (
          <li key={item.label} className="rounded-xl border border-slate-200 p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                0{index + 1}
              </span>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${isActive ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-700"}`}>
                {status.replaceAll("_", " ")}
              </span>
            </div>
            <h3 className="mt-2 font-semibold text-ink">{item.label}</h3>
            <p className="mt-1 text-sm leading-5 text-slate-600">
              {stages.map((stage) => stage.summary).join(" ") ||
                (index === 5 && run.execution_tracking
                  ? `Tracking ${run.execution_tracking.shipment.tracking_id}: ${run.execution_tracking.shipment.status}.`
                  : "Menunggu penyelesaian tahap sebelumnya.")}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

export function ImpactPanel({ run }: { run: DisruptionRun }) {
  const inventory = run.inventory_snapshot;
  const coverage = inventory ? inventory.current_stock / inventory.daily_consumption : 0;
  const stockoutDays = Math.max(0, run.event.delay_days - coverage);
  return (
    <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
      <p className="text-sm text-slate-500">Dampak operasional · source: SAP S/4HANA</p>
      <h2 className="mt-1 text-lg font-bold text-ink">Material risk snapshot</h2>
      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Metric label="Current stock" value={inventory?.current_stock.toLocaleString() ?? "—"} />
        <Metric label="Daily consumption" value={inventory?.daily_consumption.toLocaleString() ?? "—"} />
        <Metric label="Coverage" value={`${coverage.toFixed(1)} days`} />
        <Metric label="Delay duration" value={`${run.event.delay_days} days`} />
        <Metric label="Stockout risk" value={`${stockoutDays.toFixed(1)} days`} />
        <Metric label="Estimated line loss" value={money(run.cost_of_inaction)} />
      </div>
    </section>
  );
}

export function VendorCharts({
  evaluations,
  selectedVendorId,
  costOfInaction,
}: {
  evaluations: VendorEvaluation[];
  selectedVendorId: string | null;
  costOfInaction: number;
}) {
  const chartData = evaluations.map((evaluation) => ({
    name: evaluation.vendor.vendor_name,
    lead: evaluation.vendor.lead_time_days,
    quote: evaluation.action_cost,
    risk: evaluation.vendor.risk_score,
    action: evaluation.risk_adjusted_total,
    inaction: costOfInaction,
    recommended: evaluation.vendor.vendor_id === selectedVendorId,
  }));
  return (
    <section className="grid gap-5 xl:grid-cols-2">
      <div className="rounded-2xl bg-white p-5 shadow-card md:p-6">
        <p className="text-sm text-slate-500">Source: SAP Ariba</p>
        <h2 className="mb-3 text-lg font-bold text-ink">Cost vs lead time</h2>
        <div className="h-64" role="img" aria-label="Vendor cost versus lead time chart">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 12, right: 18, bottom: 12, left: 12 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="lead" name="Lead time (days)" unit="d" type="number" />
              <YAxis dataKey="quote" name="Quote" tickFormatter={(value: number) => `$${Math.round(value / 1000)}k`} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} />
              <Scatter data={chartData.filter((item) => !item.recommended)} fill="#94a3b8" />
              <Scatter data={chartData.filter((item) => item.recommended)} fill="#0f766e" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="rounded-2xl bg-white p-5 shadow-card md:p-6">
        <p className="text-sm text-slate-500">Illustrative economics · not a forecast</p>
        <h2 className="mb-3 text-lg font-bold text-ink">Cost of inaction vs action</h2>
        <div className="h-64" role="img" aria-label="Vendor action cost compared with cost of inaction">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 12, right: 12, bottom: 12, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis tickFormatter={(value: number) => `$${Math.round(value / 1000)}k`} />
              <Tooltip formatter={(value) => money(Number(value))} />
              <Legend />
              <Bar dataKey="inaction" name="Cost of inaction" fill="#f59e0b" />
              <Bar dataKey="action" name="Risk-adjusted action cost" fill="#0f766e" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="text-xs text-slate-500">Vendor risk scores are shown in the comparison table.</p>
      </div>
      <div className="rounded-2xl bg-white p-5 shadow-card md:p-6">
        <p className="text-sm text-slate-500">Supplier risk indicator · 0–100</p>
        <h2 className="mb-3 text-lg font-bold text-ink">Vendor risk score</h2>
        <div className="h-56" role="img" aria-label="Vendor risk score chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 12, right: 12, bottom: 12, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Bar dataKey="risk" name="Risk score" fill="#e11d48" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}

export function AgentReasoning({ run }: { run: DisruptionRun }) {
  const entries = run.chain_of_thought.length > 0
    ? run.chain_of_thought.map((text, index) => {
        const tracedSource = text.match(/^\[([^\]]+)\]/)?.[1];
        const agentSource =
          index === 0
            ? "Monitoring Agent · SAP S/4HANA"
            : index === 1
              ? "Logistics Agent · SAP S/4HANA"
              : index === 2
                ? "Procurement Agent · SAP Ariba"
                : "Orchestrator Agent · Decision summary";
        return {
          source: tracedSource ? `Orchestrator Agent · ${tracedSource}` : agentSource,
          text: text.replace(/^\[[^\]]+\]\s*/, ""),
        };
      })
    : run.trace_steps.map((step) => ({
        source: `Orchestrator Agent · ${step.source}`,
        text: step.text,
      }));
  const groups = entries.reduce<Record<string, string[]>>((result, entry) => {
    (result[entry.source] ??= []).push(entry.text);
    return result;
  }, {});
  return (
    <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
      <p className="text-sm text-slate-500">Trace transparan</p>
      <h2 className="text-lg font-bold text-ink">Chain of Thought summary</h2>
      <div className="mt-3 space-y-2">
        {Object.entries(groups).map(([source, texts]) => (
          <details key={source} className="rounded-xl border border-slate-200 p-3" open>
            <summary className="cursor-pointer font-semibold text-ink">{source}</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-700">
              {texts.map((text, index) => <li key={`${source}-${index}`}>{text}</li>)}
            </ul>
          </details>
        ))}
      </div>
    </section>
  );
}

export function AuditViewer({ run }: { run: DisruptionRun }) {
  return (
    <details className="rounded-2xl bg-white p-5 shadow-card md:p-6">
      <summary className="cursor-pointer text-lg font-bold text-ink">Audit log · {run.audit_log.length} entries</summary>
      <ol className="mt-4 space-y-3">
        {run.audit_log.map((entry, index) => (
          <li key={`${entry.timestamp}-${index}`} className="border-l-2 border-teal-500 pl-4">
            <p className="text-xs text-slate-500">{new Date(entry.timestamp).toLocaleString()} · {entry.agent}</p>
            <p className="mt-1 text-sm font-semibold text-ink">{entry.output_summary}</p>
            <p className="mt-1 text-sm text-slate-600">{entry.reasoning}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}

export function KpiCards({ report }: { report: KPIReport }) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-card md:p-7">
      <p className="text-sm font-semibold uppercase tracking-wide text-accent">Illustrative · simulated</p>
      <h1 className="mt-1 text-2xl font-bold text-ink">Response KPIs</h1>
      <p className="mt-2 text-sm text-slate-600">{report.label}</p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Metric label="Tracked runs" value={report.tracked_runs.toString()} />
        <Metric label="Executed runs" value={report.executed_runs.toString()} />
        <Metric label="Line stoppages avoided" value={report.line_stoppages_avoided.toString()} />
        <Metric label="Cost of inaction" value={money(report.illustrative_cost_of_inaction)} />
        <Metric label="Action cost" value={money(report.illustrative_action_cost)} />
        <Metric label="Illustrative savings" value={money(report.illustrative_savings)} />
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">
      {label}
      <strong className="mt-1 block text-lg text-ink">{value}</strong>
    </p>
  );
}

function money(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}
