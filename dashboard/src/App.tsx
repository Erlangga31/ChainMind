import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AgentReasoning,
  AuditViewer,
  ImpactPanel,
  KpiCards,
  VendorCharts,
  WorkflowTimeline,
} from "./components";
import type { ApiError, DisruptionRun, KPIReport } from "./types";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const SCENARIOS = [
  {
    id: "weather",
    label: "Extreme weather",
    title: "Extreme weather delays cargo ship",
    description: "Severe weather delayed the vessel carrying Microchip X by five days.",
    event_type: "weather",
    delay_days: 5,
  },
  {
    id: "geopolitical",
    label: "Geopolitical disruption",
    title: "Geopolitical disruption delays component supply",
    description: "Regional restrictions delayed the shipment of Microchip X.",
    event_type: "geopolitical",
    delay_days: 5,
  },
  {
    id: "vendor_failure",
    label: "Vendor failure",
    title: "Primary vendor reports a supply failure",
    description: "The contracted supplier cannot fulfill the Microchip X shipment.",
    event_type: "vendor_failure",
    delay_days: 4,
  },
  {
    id: "port_congestion",
    label: "Port congestion",
    title: "Port congestion delays inbound shipment",
    description: "Port congestion delayed the Microchip X shipment by five days.",
    event_type: "logistics_delay",
    delay_days: 5,
  },
] as const;

async function responseError(response: Response): Promise<Error> {
  let message = `Request failed with HTTP ${response.status}.`;
  try {
    const body = (await response.json()) as ApiError;
    message = body.message ?? body.detail ?? message;
  } catch {
    message = `Request failed with HTTP ${response.status}.`;
  }
  return new Error(message);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(path.endsWith("/decision")
        || path.includes("/notifications/links/")
        ? { "X-ChainMind-Role": sessionStorage.getItem("chainmind.role") ?? "viewer" }
        : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) throw await responseError(response);
  return (await response.json()) as T;
}

function money(value: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "PENDING_APPROVAL" || status === "PENDING"
      ? "bg-amber-100 text-amber-800"
      : status === "EXECUTED" || status === "COMPLETED" || status === "APPROVED"
        ? "bg-emerald-100 text-emerald-800"
        : status === "REJECTED" || status === "FAILED"
          ? "bg-rose-100 text-rose-800"
          : "bg-slate-100 text-slate-700";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}>{status.replaceAll("_", " ")}</span>;
}

export default function App() {
  const [runs, setRuns] = useState<DisruptionRun[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [run, setRun] = useState<DisruptionRun | null>(null);
  const [decisionNote, setDecisionNote] = useState("");
  const [revisionVendorId, setRevisionVendorId] = useState("");
  const [scenarioId, setScenarioId] = useState<(typeof SCENARIOS)[number]["id"]>("weather");
  const [role, setRole] = useState<"viewer" | "approver">(
    sessionStorage.getItem("chainmind.role") === "approver" ? "approver" : "viewer",
  );
  const [page, setPage] = useState<"runs" | "kpis">("runs");
  const [apiMode, setApiMode] = useState("mock");
  const [kpis, setKpis] = useState<KPIReport | null>(null);
  const [pendingDecision, setPendingDecision] = useState<"approve" | "reject" | "revise" | null>(null);
  const [decisionConfirmed, setDecisionConfirmed] = useState(false);
  const [notificationToken, setNotificationToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refreshRuns = useCallback(async (preferredId?: string) => {
    const items = await request<DisruptionRun[]>("/runs");
    setRuns(items);
    const nextId = preferredId || selectedId || items[0]?.run_id || "";
    setSelectedId(nextId);
    if (nextId) {
      const detail = await request<DisruptionRun>(`/runs/${nextId}`);
      setRun(detail);
    } else {
      setRun(null);
    }
  }, [selectedId]);

  useEffect(() => {
    void refreshRuns().catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "Could not load runs.");
    });
  }, [refreshRuns]);

  useEffect(() => {
    void request<{ mode: string }>("/health")
      .then((health) => setApiMode(health.mode))
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Could not read API mode.");
      });
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshRuns().catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Could not refresh live run status.");
      });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refreshRuns]);

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("approve");
    if (!token) return;
    window.history.replaceState({}, "", window.location.pathname);
    setNotificationToken(token);
    void request<{ run_id: string; confirmation_required: boolean }>(
      `/notifications/links/${encodeURIComponent(token)}`,
    )
      .then((result) => refreshRuns(result.run_id))
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "The approval link could not be opened.");
      });
  }, [refreshRuns]);

  useEffect(() => {
    if (page !== "kpis") return;
    void request<KPIReport>("/kpis")
      .then(setKpis)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Could not load KPI data.");
      });
  }, [page]);

  const feasibleVendors = useMemo(
    () => run?.vendor_comparison.filter((evaluation) => evaluation.feasible) ?? [],
    [run],
  );
  const pending = run?.status === "PENDING_APPROVAL";

  async function triggerDemo() {
    setBusy(true);
    setError("");
    try {
      const scenario = SCENARIOS.find((item) => item.id === scenarioId) ?? SCENARIOS[0];
      const created = await request<{ run_id: string }>("/disruptions", {
        method: "POST",
        body: JSON.stringify({
          title: scenario.title,
          description: scenario.description,
          event_type: scenario.event_type,
          delay_days: scenario.delay_days,
          component_id: "microchip-x",
          component_name: "Microchip X",
          source: "dashboard-demo",
        }),
      });
      await refreshRuns(created.run_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not trigger the demo disruption.");
    } finally {
      setBusy(false);
    }
  }

  async function selectRun(runId: string) {
    setSelectedId(runId);
    setError("");
    try {
      setRun(await request<DisruptionRun>(`/runs/${runId}`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load this run.");
    }
  }

  async function decide(decision: "approve" | "reject" | "revise") {
    setPendingDecision(decision);
    setDecisionConfirmed(false);
  }

  async function confirmDecision() {
    if (!run || !pendingDecision || !decisionConfirmed || role !== "approver") return;
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      const fromNotification = pendingDecision === "approve" && notificationToken;
      await request(
        fromNotification
          ? `/notifications/links/${encodeURIComponent(notificationToken)}/approve`
          : `/runs/${run.run_id}/decision`,
        {
        method: "POST",
          body: JSON.stringify(
            fromNotification
              ? { confirmed: true, note: decisionNote }
              : {
                  decision: pendingDecision,
                  note: decisionNote,
                  ...(pendingDecision === "revise" ? { vendor_id: revisionVendorId } : {}),
                },
          ),
        },
      );
      setPendingDecision(null);
      setNotificationToken("");
      window.history.replaceState({}, "", window.location.pathname);
      await refreshRuns(run.run_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save the decision.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-canvas">
      <header className="bg-ink text-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 lg:px-8">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-teal-400 text-lg font-black text-ink">C</span>
            <div>
              <p className="font-bold tracking-wide">CHAINMIND</p>
              <p className="text-xs text-slate-300">Autonomous Disruption Resolver</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-300">
              Mock SSO role
              <select
                aria-label="Mock SSO role"
                className="ml-2 rounded-lg border border-slate-600 bg-slate-800 px-2 py-1 text-white"
                value={role}
                onChange={(event) => {
                  const nextRole = event.target.value as "viewer" | "approver";
                  setRole(nextRole);
                  sessionStorage.setItem("chainmind.role", nextRole);
                }}
              >
                <option value="viewer">Viewer</option>
                <option value="approver">Approver</option>
              </select>
            </label>
            <span className="rounded-full border border-teal-300/40 px-3 py-1 text-xs font-semibold text-teal-200">
              {apiMode === "mock" ? "MOCK MODE" : `${apiMode.toUpperCase()} MODE`}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-5 py-8 lg:px-8">
        <section className="flex flex-col justify-between gap-5 rounded-3xl bg-white p-6 shadow-card md:flex-row md:items-center md:p-8">
          <div>
            <p className="text-sm font-semibold uppercase tracking-widest text-accent">Manufacturing control tower</p>
            <h1 className="mt-2 text-3xl font-bold text-ink">Disruption response</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              Monitor stock risk, compare alternative suppliers, and prepare a purchase order.
              Financial action remains blocked until a human approves.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm font-medium text-slate-700">
              Scenario
              <select
                aria-label="Disruption scenario"
                className="ml-2 rounded-lg border border-slate-300 px-3 py-2"
                value={scenarioId}
                onChange={(event) => setScenarioId(event.target.value as typeof scenarioId)}
              >
                {SCENARIOS.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.label}</option>)}
              </select>
            </label>
            <button
              className="rounded-xl bg-accent px-5 py-3 font-semibold text-white shadow-sm transition hover:bg-teal-800 disabled:cursor-wait disabled:opacity-60"
              disabled={busy}
              onClick={() => void triggerDemo()}
            >
              {busy ? "Working…" : "Trigger demo disruption"}
            </button>
          </div>
        </section>

        {error && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div>}

        <nav className="flex gap-2" aria-label="Dashboard sections">
          <button className={`rounded-lg px-4 py-2 text-sm font-semibold ${page === "runs" ? "bg-ink text-white" : "bg-white text-ink"}`} onClick={() => setPage("runs")}>Disruptions</button>
          <button className={`rounded-lg px-4 py-2 text-sm font-semibold ${page === "kpis" ? "bg-ink text-white" : "bg-white text-ink"}`} onClick={() => setPage("kpis")}>KPIs</button>
        </nav>

        {page === "kpis" ? (
          kpis ? <KpiCards report={kpis} /> : <div className="rounded-xl bg-white p-6 text-slate-500">Loading KPI data…</div>
        ) : (
        <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
          <aside className="h-fit rounded-2xl bg-white p-4 shadow-card">
            <div className="mb-3 flex items-center justify-between px-2">
              <h2 className="font-bold text-ink">Disruption runs</h2>
              <button className="text-xs font-semibold text-accent hover:underline" onClick={() => void refreshRuns()}>Refresh</button>
            </div>
            {runs.length === 0 ? (
              <p className="px-2 py-6 text-sm text-slate-500">No runs yet. Trigger the demo to begin.</p>
            ) : (
              <ul className="space-y-2">
                {runs.map((item) => (
                  <li key={item.run_id}>
                    <button
                      className={`w-full rounded-xl p-3 text-left transition ${item.run_id === selectedId ? "bg-teal-50 ring-1 ring-teal-200" : "hover:bg-slate-50"}`}
                      onClick={() => void selectRun(item.run_id)}
                    >
                      <span className="block truncate text-sm font-semibold text-ink">{item.event.component_name}</span>
                      <span className="mt-1 block text-xs text-slate-500">{item.event.delay_days} day delay · {item.severity ?? "Unclassified"}</span>
                      <span className="mt-2 block"><StatusPill status={item.status} /></span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </aside>

          {run ? (
            <div className="space-y-6">
              <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm text-slate-500">Active event · {run.event.component_name}</p>
                    <h2 className="mt-1 text-xl font-bold text-ink">{run.event.title}</h2>
                    <p className="mt-1 text-sm text-slate-600">{run.event.delay_days}-day delay · Severity {run.severity ?? "—"}</p>
                  </div>
                  <StatusPill status={run.status} />
                </div>
                <div className="mt-6"><WorkflowTimeline run={run} /></div>
              </section>

              <ImpactPanel run={run} />
              <VendorCharts
                evaluations={run.vendor_comparison}
                selectedVendorId={run.selected_vendor_id}
                costOfInaction={run.cost_of_inaction}
              />

              {run.execution_tracking && (
                <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-sm text-slate-500">Post-approval operations</p>
                      <h2 className="text-lg font-bold text-ink">Execution & tracking</h2>
                    </div>
                    <StatusPill status={run.execution_tracking.shipment.status} />
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">Supplier confirmation<strong className="mt-1 block text-ink">{run.execution_tracking.confirmation.confirmation_status} · {run.execution_tracking.confirmation.confirmed_quantity.toLocaleString()} pcs</strong></p>
                    <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">ASN / ETA<strong className="mt-1 block text-ink">{run.execution_tracking.shipment.tracking_id} · {run.execution_tracking.shipment.estimated_arrival}</strong></p>
                    <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">Projected stock<strong className="mt-1 block text-ink">{run.execution_tracking.inventory_projection.projected_stock_at_arrival.toLocaleString()} pcs · {run.execution_tracking.inventory_projection.projected_coverage_days} days</strong></p>
                    <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">Line stoppage<strong className="mt-1 block text-ink">{run.execution_tracking.line_stoppage_avoided ? "Avoided (simulated)" : "Not avoided"}</strong></p>
                  </div>
                  {run.execution_tracking.alert && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{run.execution_tracking.alert}</p>}
                  {run.kpis && (
                    <div className="mt-4 border-t border-slate-100 pt-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Illustrative per-run KPI · not a forecast</p>
                      <div className="mt-2 grid gap-3 sm:grid-cols-3">
                        <p className="text-sm text-slate-500">Cost of inaction<strong className="block text-ink">{money(run.kpis.cost_of_inaction)}</strong></p>
                        <p className="text-sm text-slate-500">Action cost<strong className="block text-ink">{money(run.kpis.action_cost)}</strong></p>
                        <p className="text-sm text-slate-500">Illustrative savings<strong className="block text-ink">{money(run.kpis.illustrative_savings)}</strong></p>
                      </div>
                    </div>
                  )}
                </section>
              )}

              <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
                <div className="mb-4 flex items-end justify-between gap-3">
                  <div><p className="text-sm text-slate-500">SAP Ariba Network</p><h2 className="text-lg font-bold text-ink">Vendor comparison</h2></div>
                  <span className="text-xs text-slate-500">{feasibleVendors.length} feasible</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[700px] text-left text-sm">
                    <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                      <tr><th className="px-3 py-3">Vendor</th><th className="px-3 py-3">Lead</th><th className="px-3 py-3">Capacity</th><th className="px-3 py-3">Quote</th><th className="px-3 py-3">Risk score</th><th className="px-3 py-3">Residual loss</th><th className="px-3 py-3">Economic total</th><th className="px-3 py-3">Status</th></tr>
                    </thead>
                    <tbody>
                      {run.vendor_comparison.map((evaluation) => (
                        <tr className={`border-b border-slate-100 ${evaluation.vendor.vendor_id === run.selected_vendor_id ? "bg-teal-50/70" : ""}`} key={evaluation.vendor.vendor_id}>
                          <td className="px-3 py-3 font-semibold">{evaluation.vendor.vendor_name}{evaluation.vendor.vendor_id === run.selected_vendor_id && <span className="ml-2 text-xs text-accent">Recommended</span>}</td>
                          <td className="px-3 py-3">{evaluation.vendor.lead_time_days} days</td>
                          <td className="px-3 py-3">{evaluation.vendor.capacity.toLocaleString()} pcs</td>
                          <td className="px-3 py-3">{money(evaluation.action_cost)}</td>
                          <td className="px-3 py-3">{evaluation.vendor.risk_score}/100</td>
                          <td className="px-3 py-3">{money(evaluation.residual_stockout_loss)}</td>
                          <td className="px-3 py-3 font-semibold">{money(evaluation.risk_adjusted_total)}</td>
                          <td className="px-3 py-3"><StatusPill status={evaluation.feasible ? "FEASIBLE" : "NOT FEASIBLE"} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <div className="grid gap-6 xl:grid-cols-2">
                <AgentReasoning run={run} />

                <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
                  <p className="text-sm text-slate-500">
                    SAP S/4HANA · {run.draft_po?.status === "PENDING_APPROVAL" ? "draft for approval" : "purchase order"}
                  </p>
                  <h2 className="text-lg font-bold text-ink">Purchase order</h2>
                  {run.draft_po ? (
                    <>
                      <div className="mt-4 rounded-xl bg-slate-50 p-4">
                        <div className="flex items-start justify-between gap-3"><div><p className="font-semibold text-ink">{run.draft_po.component_name}</p><p className="text-sm text-slate-500">{run.draft_po.vendor_name}</p></div><StatusPill status={run.draft_po.status} /></div>
                        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                          <p className="text-slate-500">Quantity <strong className="block text-ink">{run.draft_po.quantity.toLocaleString()} pcs</strong></p>
                          <p className="text-slate-500">Unit price <strong className="block text-ink">{money(run.draft_po.unit_price)}</strong></p>
                          <p className="text-slate-500">Total <strong className="block text-ink">{money(run.draft_po.total_price)}</strong></p>
                          <p className="text-slate-500">Terms <strong className="block text-ink">{run.draft_po.terms}</strong></p>
                          {run.draft_po.sap_reference && <p className="col-span-2 text-slate-500">SAP reference <strong className="block text-ink">{run.draft_po.sap_reference}</strong></p>}
                        </div>
                      </div>
                      {pending && role === "approver" && (
                        <div className="mt-4 space-y-3">
                          <label className="block text-sm font-medium text-slate-700">Decision note
                            <input className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} placeholder="Optional note for the audit record" />
                          </label>
                          <label className="block text-sm font-medium text-slate-700">Vendor for revision
                            <select className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" value={revisionVendorId} onChange={(event) => setRevisionVendorId(event.target.value)}>
                              <option value="">Select a feasible vendor</option>
                              {feasibleVendors.map((evaluation) => <option key={evaluation.vendor.vendor_id} value={evaluation.vendor.vendor_id}>{evaluation.vendor.vendor_name} · {money(evaluation.risk_adjusted_total)}</option>)}
                            </select>
                          </label>
                          <div className="flex flex-wrap gap-2 pt-1">
                            <button className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={busy} onClick={() => void decide("approve")}>Review approval</button>
                            <button className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50" disabled={busy || !revisionVendorId} onClick={() => void decide("revise")}>Revise vendor</button>
                            <button className="rounded-lg border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-700 disabled:opacity-50" disabled={busy} onClick={() => void decide("reject")}>Reject</button>
                          </div>
                          <p className="text-xs leading-5 text-slate-500">Approve executes the PO in the configured SAP adapter. Reject and revise do not execute a purchase.</p>
                        </div>
                      )}
                      {pending && role === "viewer" && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Viewer access is read-only. Switch to Approver in Mock SSO to submit a decision.</p>}
                    </>
                  ) : <p className="mt-4 text-sm text-slate-500">No purchase order was created for this run.</p>}
                </section>
              </div>
              <AuditViewer run={run} />
            </div>
          ) : (
            <section className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
              <div><p className="text-lg font-semibold text-ink">No disruption selected</p><p className="mt-2 text-sm text-slate-500">Trigger the demo disruption to run the six-stage analysis.</p></div>
            </section>
          )}
        </div>
        )}
      </main>
      {pendingDecision && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-ink/60 p-4" role="presentation">
          <section role="dialog" aria-modal="true" aria-labelledby="decision-title" className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
            <h2 id="decision-title" className="text-xl font-bold text-ink">Confirm {pendingDecision}</h2>
            <p className="mt-2 text-sm text-slate-600">
              {pendingDecision === "approve"
                ? "This authorizes the pending purchase order to be executed by the configured SAP adapter."
                : "This decision will be recorded in the run audit log."}
            </p>
            <label className="mt-4 flex items-start gap-3 text-sm text-slate-700">
              <input type="checkbox" checked={decisionConfirmed} onChange={(event) => setDecisionConfirmed(event.target.checked)} />
              I explicitly confirm this human decision.
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button className="rounded-lg border border-slate-300 px-4 py-2" onClick={() => setPendingDecision(null)}>Cancel</button>
              <button className="rounded-lg bg-accent px-4 py-2 font-semibold text-white disabled:opacity-50" disabled={!decisionConfirmed || busy} onClick={() => void confirmDecision()}>
                {busy ? "Submitting…" : "Confirm decision"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
