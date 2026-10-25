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
import type { DisruptionRun, KPIReport, UsageReport, VendorEvaluation } from "./types";
import { translate, type Language } from "./i18n";

const timeline = [
  { label: "stageDetection", match: ["monitoring"] },
  { label: "stageImpact", match: ["logistics"] },
  { label: "stageSolutions", match: ["procurement"] },
  { label: "stageDecision", match: ["orchestrator"] },
  { label: "stageHuman", match: ["human approval"] },
  { label: "stageExecution", match: ["po execution", "execution & tracking"] },
];

export function WorkflowTimeline({
  run,
  language = "id",
}: {
  run: DisruptionRun;
  language?: Language;
}) {
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
            <h3 className="mt-2 font-semibold text-ink">{translate(language, item.label)}</h3>
            <p className="mt-1 text-sm leading-5 text-slate-600">
              {stages.map((stage) => stage.summary).join(" ") ||
                (index === 5 && run.execution_tracking
                  ? `Tracking ${run.execution_tracking.shipment.tracking_id}: ${run.execution_tracking.shipment.status}.`
                  : translate(language, "waiting"))}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

export function ImpactPanel({
  run,
  language = "id",
}: {
  run: DisruptionRun;
  language?: Language;
}) {
  const inventory = run.inventory_snapshot;
  const coverage = inventory ? inventory.current_stock / inventory.daily_consumption : 0;
  const stockoutDays = Math.max(0, run.event.delay_days - coverage);
  return (
    <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
      <p className="text-sm text-slate-500">{translate(language, "operationalImpact")}</p>
      <h2 className="mt-1 text-lg font-bold text-ink">{translate(language, "materialRisk")}</h2>
      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Metric label={translate(language, "currentStock")} value={inventory?.current_stock.toLocaleString() ?? "—"} />
        <Metric label={translate(language, "dailyConsumption")} value={inventory?.daily_consumption.toLocaleString() ?? "—"} />
        <Metric label={translate(language, "coverage")} value={`${coverage.toFixed(1)} ${language === "id" ? "hari" : "days"}`} />
        <Metric label={translate(language, "delayDuration")} value={`${run.event.delay_days} ${language === "id" ? "hari" : "days"}`} />
        <Metric label={translate(language, "stockoutRisk")} value={`${stockoutDays.toFixed(1)} ${language === "id" ? "hari" : "days"}`} />
        <Metric label={translate(language, "estimatedLineLoss")} value={money(run.cost_of_inaction)} />
      </div>
      {run.material_impacts.length > 1 && (
        <div className="mt-5 overflow-x-auto">
          <h3 className="mb-2 font-semibold text-ink">{translate(language, "bomImpact")}</h3>
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="border-b text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-3">{translate(language, "component")}</th>
                <th className="py-2 pr-3">{translate(language, "coverage")}</th>
                <th className="py-2 pr-3">{translate(language, "stockout")}</th>
                <th className="py-2 pr-3">{translate(language, "costOfInaction")}</th>
                <th className="py-2">{translate(language, "impact")}</th>
              </tr>
            </thead>
            <tbody>
              {run.material_impacts.map((impact) => (
                <tr key={impact.component_id} className="border-b last:border-0">
                  <th className="py-2 pr-3 font-medium">{impact.component_name}</th>
                  <td className="py-2 pr-3">{impact.coverage_days.toFixed(1)} days</td>
                  <td className="py-2 pr-3">{impact.stockout_days.toFixed(1)} days</td>
                  <td className="py-2 pr-3">{money(impact.cost_of_inaction)}</td>
                  <td className="py-2">{translate(language, impact.critical ? "critical" : "affected")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function VendorCharts({
  evaluations,
  selectedVendorId,
  costOfInaction,
  language = "id",
}: {
  evaluations: VendorEvaluation[];
  selectedVendorId: string | null;
  costOfInaction: number;
  language?: Language;
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
        <p className="text-sm text-slate-500">{translate(language, "aribaSource")}</p>
        <h2 className="mb-3 text-lg font-bold text-ink">{translate(language, "costLeadTime")}</h2>
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
        <p className="text-sm text-slate-500">{translate(language, "illustrativeEconomics")}</p>
        <h2 className="mb-3 text-lg font-bold text-ink">{translate(language, "inactionVsAction")}</h2>
        <div className="h-64" role="img" aria-label="Vendor action cost compared with cost of inaction">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 12, right: 12, bottom: 12, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis tickFormatter={(value: number) => `$${Math.round(value / 1000)}k`} />
              <Tooltip formatter={(value) => money(Number(value))} />
              <Legend />
              <Bar dataKey="inaction" name={translate(language, "costOfInaction")} fill="#f59e0b" />
              <Bar dataKey="action" name={translate(language, "riskAdjustedActionCost")} fill="#0f766e" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="text-xs text-slate-500">{translate(language, "vendorRiskScoresTable")}</p>
      </div>
      <div className="rounded-2xl bg-white p-5 shadow-card md:p-6">
        <p className="text-sm text-slate-500">{translate(language, "riskIndicator")}</p>
        <h2 className="mb-3 text-lg font-bold text-ink">{translate(language, "supplierRisk")}</h2>
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

export function AgentReasoning({
  run,
  language = "id",
}: {
  run: DisruptionRun;
  language?: Language;
}) {
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
      <p className="text-sm text-slate-500">{translate(language, "traceTransparent")}</p>
      <h2 className="text-lg font-bold text-ink">{translate(language, "chainOfThought")}</h2>
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

export function AuditViewer({
  run,
  language = "id",
}: {
  run: DisruptionRun;
  language?: Language;
}) {
  return (
    <details className="rounded-2xl bg-white p-5 shadow-card md:p-6">
      <summary className="cursor-pointer text-lg font-bold text-ink">{translate(language, "auditLog")} · {run.audit_log.length} {language === "id" ? "entri" : "entries"}</summary>
      <ol className="mt-4 space-y-3">
        {run.audit_log.map((entry, index) => (
          <li key={`${entry.timestamp}-${index}`} className="border-l-2 border-teal-500 pl-4">
            <p className="text-xs text-slate-500">{entry.proposal_step ? `Step ${entry.proposal_step} · ` : ""}{new Date(entry.timestamp).toLocaleString()} · {entry.agent}</p>
            <p className="mt-1 text-sm font-semibold text-ink">{entry.output_summary}</p>
            <p className="mt-1 text-sm text-slate-600">{entry.reasoning}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}

export function KpiCards({
  report,
  language = "id",
}: {
  report: KPIReport;
  language?: Language;
}) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-card md:p-7">
      <p className="text-sm font-semibold uppercase tracking-wide text-accent">{translate(language, "simulatedIllustrative")}</p>
      <h1 className="mt-1 text-2xl font-bold text-ink">{translate(language, "responseKpis")}</h1>
      <p className="mt-2 text-sm text-slate-600">{report.label}</p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Metric label={translate(language, "trackedRuns")} value={report.tracked_runs.toString()} />
        <Metric label={translate(language, "executedRuns")} value={report.executed_runs.toString()} />
        <Metric label={translate(language, "lineStoppagesAvoided")} value={report.line_stoppages_avoided.toString()} />
        <Metric label={translate(language, "costOfInaction")} value={money(report.illustrative_cost_of_inaction)} />
        <Metric label={translate(language, "actionCost")} value={money(report.illustrative_action_cost)} />
        <Metric label={translate(language, "illustrativeSavings")} value={money(report.illustrative_savings)} />
      </div>
      <h2 className="mt-8 text-lg font-bold text-ink">{translate(language, "manualBaseline")}</h2>
      <p className="mt-1 text-sm text-slate-600">
        {translate(language, "proposalBaselines")}
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="border-b text-xs uppercase text-slate-500">
            <tr>
              <th className="py-2 pr-3">{translate(language, "metric")}</th>
              <th className="py-2 pr-3">{translate(language, "manualBaselineColumn")}</th>
              <th className="py-2">ChainMind</th>
            </tr>
          </thead>
          <tbody>
            {report.comparison.map((item) => (
              <tr key={item.metric} className="border-b last:border-0">
                <th className="py-3 pr-3 font-semibold text-ink">{translate(language, item.metric)}</th>
                <td className="py-3 pr-3 text-slate-600">
                  {formatComparison(item.manual_baseline, item.unit, language)}
                  {item.manual_is_illustrative && ` · ${translate(language, "illustrativeSuffix")}`}
                </td>
                <td className="py-3 text-slate-600">
                  {formatComparison(item.chainmind_value, item.unit, language)}
                  {item.chainmind_is_illustrative && ` · ${translate(language, "illustrativeTarget")}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function UsageCard({
  report,
  language = "id",
}: {
  report: UsageReport;
  language?: Language;
}) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-card md:p-7">
      <p className="text-sm font-semibold uppercase tracking-wide text-accent">
      {language === "id"
        ? "Ilustratif · bukan penawaran atau tagihan"
        : "Illustrative · not a quote or invoice"}
      </p>
      <h1 className="mt-1 text-2xl font-bold text-ink">{translate(language, "usagePlan")}</h1>
      <p className="mt-2 text-sm text-slate-600">
        {language === "id" ? translate(language, "usageEstimateLabel") : report.label}
      </p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Metric label={translate(language, "usageMonth")} value={report.period_start.slice(0, 7)} />
        <Metric label={translate(language, "planTier")} value={report.plan_tier} />
        <Metric
          label={translate(language, "resolvedDisruptions")}
          value={`${report.resolved_disruptions} / ${report.included_disruptions} ${translate(language, "included")}`}
        />
        <Metric
          label={translate(language, "activeAgents")}
          value={`${report.active_agents} / ${report.included_agents} ${translate(language, "included")}`}
        />
        <Metric label={translate(language, "monthlySubscription")} value={money(report.monthly_subscription_fee)} />
        <Metric label={translate(language, "disruptionOverage")} value={money(report.disruption_overage_fee)} />
        <Metric label={translate(language, "additionalAgents")} value={money(report.additional_agent_fee)} />
        <Metric label={translate(language, "oneTimeOnboarding")} value={money(report.one_time_onboarding_fee)} />
        <Metric
          label={translate(language, "monthlyEstimate")}
          value={money(report.illustrative_monthly_estimate)}
        />
        <Metric
          label={translate(language, "firstInvoice")}
          value={money(report.illustrative_first_invoice_estimate)}
        />
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

function formatComparison(value: number | null, unit: string, language: Language): string {
  if (value === null) return translate(language, "noRunData");
  const formatted = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value);
  if (unit === "percent") return `${formatted}%`;
  const localizedUnit =
    language === "id"
      ? unit === "minutes"
        ? "menit"
        : unit === "hours per disruption"
          ? "jam per gangguan"
          : unit
      : unit;
  return `${formatted} ${localizedUnit}`;
}

function money(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}
