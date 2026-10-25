import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AgentReasoning,
  AuditViewer,
  ImpactPanel,
  KpiCards,
  UsageCard,
  VendorCharts,
  WorkflowTimeline,
} from "./components";
import { FlowDiagram } from "./FlowDiagram";
import type { ApiError, DisruptionRun, KPIReport, UsageReport } from "./types";
import { formatNotification, translate, type Language } from "./i18n";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const OIDC_ISSUER = import.meta.env.VITE_OIDC_ISSUER ?? "http://127.0.0.1:8100";
const OIDC_CLIENT_ID = import.meta.env.VITE_OIDC_CLIENT_ID ?? "chainmind-dashboard";
const OIDC_REDIRECT_URI = import.meta.env.VITE_OIDC_REDIRECT_URI ?? "http://localhost:5173/";
const SCENARIOS = [
  {
    id: "weather",
    label: "weather",
    title: "Extreme weather delays cargo ship",
    description: "Severe weather delayed the vessel carrying Microchip X by five days.",
    event_type: "weather",
    delay_days: 5,
  },
  {
    id: "geopolitical",
    label: "geopolitical",
    title: "Geopolitical disruption delays component supply",
    description: "Regional restrictions delayed the shipment of Microchip X.",
    event_type: "geopolitical",
    delay_days: 5,
  },
  {
    id: "vendor_failure",
    label: "vendorFailure",
    title: "Primary vendor reports a supply failure",
    description: "The contracted supplier cannot fulfill the Microchip X shipment.",
    event_type: "vendor_failure",
    delay_days: 4,
  },
  {
    id: "port_congestion",
    label: "portCongestion",
    title: "Port congestion delays inbound shipment",
    description: "Port congestion delayed the Microchip X shipment by five days.",
    event_type: "logistics_delay",
    delay_days: 5,
  },
] as const;

type TokenClaims = {
  sub: string;
  roles?: string[];
  "cognito:groups"?: string[];
  tenant_id: string;
  exp: number;
  nonce?: string;
};

type AuthSession = {
  token: string;
  subject: string;
  role: "viewer" | "approver" | "admin";
  expiresAt: number;
};

function LanguageControls({
  language,
  onChange,
}: {
  language: Language;
  onChange: (language: Language) => void;
}) {
  return (
    <div role="group" aria-label={translate(language, "language")} className="flex gap-1">
      <button
        type="button"
        aria-pressed={language === "id"}
        className="rounded-md border border-slate-400 px-2 py-1 text-xs font-semibold"
        onClick={() => onChange("id")}
      >
        ID
      </button>
      <button
        type="button"
        aria-pressed={language === "en"}
        className="rounded-md border border-slate-400 px-2 py-1 text-xs font-semibold"
        onClick={() => onChange("en")}
      >
        EN
      </button>
    </div>
  );
}

function AccessibilityControls({
  largeText,
  highContrast,
  onLargeTextChange,
  onHighContrastChange,
  language,
}: {
  largeText: boolean;
  highContrast: boolean;
  onLargeTextChange: (enabled: boolean) => void;
  onHighContrastChange: (enabled: boolean) => void;
  language: Language;
}) {
  return (
    <div className="flex gap-2">
      <button
        type="button"
        aria-pressed={largeText}
        onClick={() => onLargeTextChange(!largeText)}
        className="rounded-md border border-slate-400 px-2 py-1 text-xs font-semibold"
      >
        {translate(language, "largeText")}
      </button>
      <button
        type="button"
        aria-pressed={highContrast}
        onClick={() => onHighContrastChange(!highContrast)}
        className="rounded-md border border-slate-400 px-2 py-1 text-xs font-semibold"
      >
        {translate(language, "highContrast")}
      </button>
    </div>
  );
}

let accessToken: string | null = null;
let onSessionExpired: (() => void) | null = null;

function decodeClaims(token: string): TokenClaims {
  const encoded = token.split(".")[1];
  if (!encoded) throw new Error("Identity provider returned a malformed token.");
  const base64 = encoded.replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="))) as TokenClaims;
}

function randomBase64Url(size: number): string {
  const bytes = window.crypto.getRandomValues(new Uint8Array(size));
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

async function beginLogin(): Promise<void> {
  if (new URLSearchParams(window.location.search).get("presenter") === "1") {
    sessionStorage.setItem("chainmind.presenter", "true");
  } else {
    sessionStorage.removeItem("chainmind.presenter");
  }
  const state = randomBase64Url(32);
  const nonce = randomBase64Url(32);
  const verifier = randomBase64Url(48);
  const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  const challenge = btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  sessionStorage.setItem("chainmind.oidc.state", state);
  sessionStorage.setItem("chainmind.oidc.nonce", nonce);
  sessionStorage.setItem("chainmind.oidc.verifier", verifier);
  const authorizeUrl = new URL(`${OIDC_ISSUER}/oidc/authorize`);
  authorizeUrl.search = new URLSearchParams({
    response_type: "code",
    client_id: OIDC_CLIENT_ID,
    redirect_uri: OIDC_REDIRECT_URI,
    scope: "openid profile",
    state,
    nonce,
    code_challenge: challenge,
    code_challenge_method: "S256",
  }).toString();
  window.location.assign(authorizeUrl.toString());
}

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
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...init?.headers,
    },
  });
  if (response.status === 401 && accessToken) onSessionExpired?.();
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

function presenterNarrations(language: Language): string[] {
  return language === "id"
    ? [
        "Kapal pembawa Microchip X tertunda lima hari karena cuaca ekstrem; stok SAP hanya mencakup tiga hari.",
        "Monitoring mengklasifikasikan gangguan dan Logistics menghitung risiko stockout dua hari.",
        "Procurement membandingkan empat vendor berdasarkan lead time, biaya, kapasitas, dan risiko.",
        "Orchestrator memilih Vendor B: tiba dua hari, total $135.000, dengan Air Freight.",
        "Draf PO 5.000 pcs tetap PENDING_APPROVAL; tidak ada pembelian sebelum persetujuan manusia.",
        "Setelah persetujuan, pantau konfirmasi, pengiriman, ETA, proyeksi stok, dan KPI ilustratif.",
      ]
    : [
        "The Microchip X cargo ship is delayed five days by extreme weather; SAP stock covers three days.",
        "Monitoring classifies the disruption and Logistics calculates two days of stockout risk.",
        "Procurement compares four vendors by lead time, cost, capacity, and risk.",
        "The Orchestrator selects Vendor B: two-day arrival, $135,000 total, by Air Freight.",
        "The 5,000-piece draft PO remains PENDING_APPROVAL; no purchase occurs before human approval.",
        "After approval, track confirmation, shipment, ETA, projected stock, and illustrative KPIs.",
      ];
}

export default function App() {
  const presenter =
    new URLSearchParams(window.location.search).get("presenter") === "1" ||
    sessionStorage.getItem("chainmind.presenter") === "true";
  const [language, setLanguage] = useState<Language>(
    () => (localStorage.getItem("chainmind.language") === "en" ? "en" : "id"),
  );
  const [largeText, setLargeText] = useState(
    () => localStorage.getItem("chainmind.largeText") === "true",
  );
  const [highContrast, setHighContrast] = useState(
    () => localStorage.getItem("chainmind.highContrast") === "true",
  );
  const [session, setSession] = useState<AuthSession | null>(null);
  const [runs, setRuns] = useState<DisruptionRun[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [run, setRun] = useState<DisruptionRun | null>(null);
  const [decisionNote, setDecisionNote] = useState("");
  const [revisionVendorId, setRevisionVendorId] = useState("");
  const [scenarioId, setScenarioId] = useState<(typeof SCENARIOS)[number]["id"]>("weather");
  const role = session?.role;
  const canApprove = role === "approver" || role === "admin";
  const [page, setPage] = useState<"runs" | "flow" | "kpis" | "usage">("runs");
  const [apiMode, setApiMode] = useState("mock");
  const [kpis, setKpis] = useState<KPIReport | null>(null);
  const [usage, setUsage] = useState<UsageReport | null>(null);
  const [pendingDecision, setPendingDecision] = useState<"approve" | "reject" | "revise" | null>(null);
  const [decisionConfirmed, setDecisionConfirmed] = useState(false);
  const [notificationToken, setNotificationToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [apiUnavailable, setApiUnavailable] = useState(false);
  const [replayMode, setReplayMode] = useState(false);
  const [replayProgress, setReplayProgress] = useState(0);
  const [presenterStep, setPresenterStep] = useState(0);
  const presenterStarted = useRef(false);
  const t = (key: string) => translate(language, key);

  useEffect(() => {
    localStorage.setItem("chainmind.language", language);
    document.documentElement.lang = language;
  }, [language]);
  useEffect(() => {
    localStorage.setItem("chainmind.largeText", String(largeText));
    document.documentElement.dataset.fontScale = largeText ? "large" : "normal";
  }, [largeText]);
  useEffect(() => {
    localStorage.setItem("chainmind.highContrast", String(highContrast));
    document.documentElement.dataset.contrast = highContrast ? "high" : "standard";
  }, [highContrast]);

  onSessionExpired = () => {
    accessToken = null;
    setSession(null);
    setPage("runs");
    setUsage(null);
    setKpis(null);
    setError("Your session expired. Sign in again to continue.");
  };

  useEffect(() => {
    const callback = new URLSearchParams(window.location.search);
    const code = callback.get("code");
    if (!code) return;
    const state = callback.get("state");
    const expectedState = sessionStorage.getItem("chainmind.oidc.state");
    const nonce = sessionStorage.getItem("chainmind.oidc.nonce");
    const verifier = sessionStorage.getItem("chainmind.oidc.verifier");
    window.history.replaceState({}, "", window.location.pathname);
    sessionStorage.removeItem("chainmind.oidc.state");
    sessionStorage.removeItem("chainmind.oidc.nonce");
    sessionStorage.removeItem("chainmind.oidc.verifier");
    if (!state || state !== expectedState || !nonce || !verifier) {
      setError("The sign-in response could not be verified. Please sign in again.");
      return;
    }
    void fetch(`${OIDC_ISSUER}/oidc/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: OIDC_CLIENT_ID,
        redirect_uri: OIDC_REDIRECT_URI,
        code,
        code_verifier: verifier,
      }),
    })
      .then(async (response) => {
        if (!response.ok) throw await responseError(response);
        return response.json() as Promise<{ access_token: string; id_token: string }>;
      })
      .then(({ id_token: identityToken }) => {
        const claims = decodeClaims(identityToken);
        const roles = claims.roles ?? claims["cognito:groups"] ?? [];
        if (claims.nonce !== nonce || claims.exp <= Date.now() / 1000) {
          throw new Error("The identity token expired or failed nonce validation.");
        }
        if (!claims.tenant_id) {
          throw new Error("The identity token does not contain a tenant claim.");
        }
        if (!roles.includes("viewer") && !roles.includes("approver") && !roles.includes("admin")) {
          throw new Error("The identity token does not contain a supported role.");
        }
        const nextSession = {
          token: identityToken,
          subject: claims.sub,
          role: roles.includes("admin")
            ? "admin" as const
            : roles.includes("approver")
              ? "approver" as const
              : "viewer" as const,
          expiresAt: claims.exp * 1000,
        } satisfies AuthSession;
        accessToken = nextSession.token;
        setSession(nextSession);
        setError("");
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Sign-in failed.");
      });
  }, []);

  useEffect(() => {
    if (!session) return;
    const remaining = session.expiresAt - Date.now();
    if (remaining <= 0) {
      onSessionExpired?.();
      return;
    }
    const timer = window.setTimeout(() => onSessionExpired?.(), remaining);
    return () => window.clearTimeout(timer);
  }, [session]);

  const refreshRuns = useCallback(async (preferredId?: string) => {
    const items = await request<DisruptionRun[]>("/runs");
    setRuns((current) => JSON.stringify(current) === JSON.stringify(items) ? current : items);
    const nextId = preferredId || selectedId || items[0]?.run_id || "";
    setSelectedId(nextId);
    if (nextId) {
      const detail = await request<DisruptionRun>(`/runs/${nextId}`);
      setRun((current) => JSON.stringify(current) === JSON.stringify(detail) ? current : detail);
    } else {
      setRun((current) => current === null ? current : null);
    }
  }, [selectedId]);

  useEffect(() => {
    if (!session || replayMode) return;
    void refreshRuns().catch((caught: unknown) => {
      setApiUnavailable(true);
      setError(caught instanceof Error ? caught.message : "Could not load runs.");
    });
  }, [refreshRuns, replayMode, session]);

  useEffect(() => {
    if (!session || replayMode) return;
    void request<{ mode: string }>("/health")
      .then((health) => {
        setApiMode(health.mode);
        setApiUnavailable(false);
      })
      .catch((caught: unknown) => {
        setApiUnavailable(true);
        setError(caught instanceof Error ? caught.message : "Could not read API mode.");
      });
  }, [replayMode, session]);

  useEffect(() => {
    if (!session || busy || replayMode) return;
    const timer = window.setInterval(() => {
      void refreshRuns().catch((caught: unknown) => {
        setApiUnavailable(true);
        setError(caught instanceof Error ? caught.message : "Could not refresh live run status.");
      });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [busy, refreshRuns, replayMode, session]);

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
    if (!session || replayMode || page !== "kpis") return;
    void request<KPIReport>("/kpis")
      .then(setKpis)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Could not load KPI data.");
      });
  }, [page, replayMode, session]);

  useEffect(() => {
    if (!session || replayMode || page !== "usage" || !canApprove) return;
    void request<UsageReport>("/usage")
      .then(setUsage)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Could not load usage data.");
      });
  }, [canApprove, page, replayMode, session]);

  const feasibleVendors = useMemo(
    () => run?.vendor_comparison.filter((evaluation) => evaluation.feasible) ?? [],
    [run],
  );
  const pendingNotifications = useMemo(
    () => runs.filter((item) => item.status === "PENDING_APPROVAL" && item.draft_po),
    [runs],
  );
  const pending = run?.status === "PENDING_APPROVAL";
  const replayRun = useMemo(() => {
    if (!run || !replayMode) return run;
    return {
      ...run,
      stages: run.stages.map((stage, index) => ({
        ...stage,
        status: index < replayProgress
          ? "COMPLETED"
          : index === replayProgress
            ? "IN_PROGRESS"
            : "WAITING_FOR_APPROVAL",
      })),
    };
  }, [replayMode, replayProgress, run]);

  async function triggerDemo(scenarioOverride?: string) {
    setBusy(true);
    setError("");
    try {
      const scenario = SCENARIOS.find((item) => item.id === (scenarioOverride ?? scenarioId)) ?? SCENARIOS[0];
      const created = await request<{ run_id: string }>("/disruptions", {
        method: "POST",
        body: JSON.stringify({
          title: scenario.title,
          description: scenario.description,
          event_type: scenario.event_type,
          delay_days: scenario.delay_days,
          language,
          component_id: "microchip-x",
          component_name: "Microchip X",
          source: "dashboard-demo",
        }),
      });
      setApiUnavailable(false);
      await refreshRuns(created.run_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not trigger the demo disruption.");
    } finally {
      setBusy(false);
    }
  }

  async function loadReplay() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/replay-run.json");
      if (!response.ok) throw await responseError(response);
      const fixture = await response.json() as DisruptionRun;
      if (!fixture.run_id || !fixture.draft_po || fixture.vendor_comparison.length < 2) {
        throw new Error("The replay fixture is incomplete and cannot be displayed.");
      }
      setRuns([fixture]);
      setRun(fixture);
      setSelectedId(fixture.run_id);
      setReplayMode(true);
      setReplayProgress(0);
      setApiMode("replay");
      setPage("flow");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the recorded demo.");
    } finally {
      setBusy(false);
    }
  }

  async function reconnectLive() {
    setReplayMode(false);
    setApiUnavailable(false);
    setError("");
    try {
      const health = await request<{ mode: string }>("/health");
      setApiMode(health.mode);
      const items = await request<DisruptionRun[]>("/runs");
      setRuns(items);
      const nextRun = items[0] ?? null;
      setSelectedId(nextRun?.run_id ?? "");
      setRun(nextRun);
      if (nextRun) setRun(await request<DisruptionRun>(`/runs/${nextRun.run_id}`));
    } catch (caught) {
      setApiUnavailable(true);
      setError(caught instanceof Error ? caught.message : "Could not reconnect to the live API.");
    }
  }

  useEffect(() => {
    if (!presenter || !session || presenterStarted.current || replayMode) return;
    presenterStarted.current = true;
    setPage("flow");
    void triggerDemo("weather");
  }, [presenter, replayMode, session]);

  useEffect(() => {
    if (!replayMode || replayProgress >= 4) return;
    const timer = window.setTimeout(
      () => setReplayProgress((progress) => Math.min(progress + 1, 4)),
      900,
    );
    return () => window.clearTimeout(timer);
  }, [replayMode, replayProgress]);

  async function selectRun(runId: string) {
    setSelectedId(runId);
    setError("");
    if (replayMode) {
      const replay = runs.find((item) => item.run_id === runId);
      setRun(replay ?? null);
      return;
    }
    try {
      setRun(await request<DisruptionRun>(`/runs/${runId}`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load this run.");
    }
  }

  async function openNotificationApproval(runId: string) {
    setBusy(true);
    setError("");
    try {
      const detail = await request<DisruptionRun>(`/runs/${runId}`);
      setSelectedId(runId);
      setRun(detail);
      setNotificationToken("");
      setPendingDecision("approve");
      setDecisionConfirmed(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not open this approval.");
    } finally {
      setBusy(false);
    }
  }

  async function decide(decision: "approve" | "reject" | "revise") {
    setPendingDecision(decision);
    setDecisionConfirmed(false);
  }

  async function confirmDecision() {
    if (!run || !pendingDecision || !decisionConfirmed || !canApprove || replayMode) return;
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

  function logout() {
    accessToken = null;
    setSession(null);
    setRuns([]);
    setRun(null);
    setSelectedId("");
    setPage("runs");
    setReplayMode(false);
    setReplayProgress(0);
    setApiUnavailable(false);
    sessionStorage.removeItem("chainmind.presenter");
    setUsage(null);
    setKpis(null);
    setError("");
  }

  if (!session) {
    return (
      <main className="grid min-h-screen place-items-center bg-canvas p-6">
        <section className="w-full max-w-md rounded-3xl bg-white p-8 shadow-card">
          <p className="text-sm font-semibold uppercase tracking-widest text-accent">ChainMind SSO</p>
          <div className="flex items-center justify-between gap-3">
            <h1 className="mt-2 text-2xl font-bold text-ink">{t("signInTitle")}</h1>
            <div className="flex flex-wrap justify-end gap-2">
              <LanguageControls language={language} onChange={setLanguage} />
              <AccessibilityControls
                largeText={largeText}
                highContrast={highContrast}
                onLargeTextChange={setLargeText}
                onHighContrastChange={setHighContrast}
                language={language}
              />
            </div>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            {t("signInDescription")}
          </p>
          {error && <p role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
          {apiUnavailable && <p className="mt-3 text-xs text-slate-500">{t("replayRequiresSignIn")}</p>}
          <button
            className="mt-6 w-full rounded-xl bg-accent px-5 py-3 font-semibold text-white"
            onClick={() => void beginLogin().catch((caught: unknown) => {
              setError(caught instanceof Error ? caught.message : "Could not start sign-in.");
            })}
          >
            {t("signIn")}
          </button>
        </section>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
      <header className="bg-ink text-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-teal-400 text-lg font-black text-ink">C</span>
            <div>
              <p className="font-bold tracking-wide">CHAINMIND</p>
              <p className="text-xs text-slate-300">{t("brandSubtitle")}</p>
            </div>
          </div>
          <div className="flex min-w-0 flex-wrap items-center justify-center gap-2 sm:justify-end">
            <span className="text-xs text-slate-300">{session.subject} · {role}</span>
            <LanguageControls language={language} onChange={setLanguage} />
            <AccessibilityControls
              largeText={largeText}
              highContrast={highContrast}
              onLargeTextChange={setLargeText}
              onHighContrastChange={setHighContrast}
              language={language}
            />
            <button className="rounded-lg border border-slate-500 px-3 py-1 text-xs text-white" onClick={logout}>{t("logout")}</button>
            <span className="rounded-full border border-teal-300/40 px-3 py-1 text-xs font-semibold text-teal-200">
              {replayMode ? "REPLAY" : apiMode === "mock" ? "MOCK MODE" : `${apiMode.toUpperCase()} MODE`}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-5 py-8 lg:px-8">
        <section className="flex flex-col justify-between gap-5 rounded-3xl bg-white p-6 shadow-card md:flex-row md:items-center md:p-8">
          <div>
            <p className="text-sm font-semibold uppercase tracking-widest text-accent">{t("controlTower")}</p>
            <h1 className="mt-2 text-3xl font-bold text-ink">{t("responseTitle")}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              {t("responseDescription")}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm font-medium text-slate-700">
              {t("scenario")}
              <select
                aria-label="Disruption scenario"
                className="ml-2 rounded-lg border border-slate-300 px-3 py-2"
                value={scenarioId}
                onChange={(event) => setScenarioId(event.target.value as typeof scenarioId)}
              >
                {SCENARIOS.map((scenario) => <option key={scenario.id} value={scenario.id}>{t(scenario.label)}</option>)}
              </select>
            </label>
            {!replayMode && <button
              className="rounded-xl bg-accent px-5 py-3 font-semibold text-white shadow-sm transition-colors hover:bg-teal-800 disabled:cursor-wait disabled:opacity-60"
              disabled={busy || replayMode}
              onClick={() => void triggerDemo()}
            >
              {busy ? t("working") : t("trigger")}
            </button>}
          </div>
        </section>

        {error && (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
            <span>{error}</span>
            {apiUnavailable && !replayMode && (
              <button className="rounded-lg border border-rose-300 bg-white px-3 py-2 font-semibold" disabled={busy} onClick={() => void loadReplay()}>
                {busy ? t("working") : t("loadReplay")}
              </button>
            )}
          </div>
        )}

        {replayMode && (
          <div role="status" aria-label="Replay mode" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm font-semibold text-amber-950">
            <span>REPLAY · {t("replayReadOnly")}</span>
            <button className="rounded-lg border border-amber-500 bg-white px-3 py-2" onClick={() => void reconnectLive()}>{t("reconnectLive")}</button>
          </div>
        )}

        {presenter && (
          <section aria-label={t("presenterMode")} className="rounded-2xl bg-ink p-5 text-white shadow-card">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-teal-200">{t("presenterMode")} · {presenterStep + 1}/{presenterNarrations(language).length}</p>
                <p aria-live="polite" className="mt-2 max-w-4xl text-lg font-semibold leading-7">{presenterNarrations(language)[presenterStep]}</p>
              </div>
              <button
                className="rounded-lg bg-teal-300 px-4 py-2 font-bold text-ink disabled:opacity-50"
                disabled={presenterStep >= presenterNarrations(language).length - 1}
                onClick={() => setPresenterStep((step) => Math.min(step + 1, presenterNarrations(language).length - 1))}
              >
                {t("next")}
              </button>
            </div>
          </section>
        )}

        <section aria-label={t("notificationFeed")} className="rounded-2xl bg-white p-5 shadow-card">
          <h2 className="text-lg font-bold text-ink">{t("notificationFeed")}</h2>
          {pendingNotifications.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">{t("noNotifications")}</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {pendingNotifications.map((item) => {
                const inventory = item.inventory_snapshot;
                const coverageDays = inventory
                  ? inventory.current_stock / inventory.daily_consumption
                  : 0;
                return (
                  <li key={item.run_id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-slate-200 p-4">
                    <p className="min-w-60 flex-1 text-sm leading-6 text-slate-700">
                      {formatNotification(
                        language,
                        item.inventory_snapshot?.component_name ?? item.event.component_name,
                        item.event.delay_days,
                        coverageDays,
                        item.draft_po?.vendor_name ?? "—",
                        money(item.draft_po?.total_price ?? 0),
                      )}
                    </p>
                    <div className="flex gap-2">
                      <button
                        className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={busy || !canApprove || replayMode}
                        onClick={() => void openNotificationApproval(item.run_id)}
                      >
                        {t("approve")}
                      </button>
                      <button
                        className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700"
                        onClick={() => void selectRun(item.run_id)}
                      >
                        {t("viewDetails")}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <nav className="flex flex-wrap gap-2" aria-label={t("dashboardSections")}>
          <button className={`rounded-lg px-4 py-2 text-sm font-semibold ${page === "runs" ? "bg-ink text-white" : "bg-white text-ink"}`} onClick={() => setPage("runs")}>{t("disruptions")}</button>
          <button className={`rounded-lg px-4 py-2 text-sm font-semibold ${page === "flow" ? "bg-ink text-white" : "bg-white text-ink"}`} onClick={() => setPage("flow")}>{t("flowTitle")}</button>
          {!replayMode && <button className={`rounded-lg px-4 py-2 text-sm font-semibold ${page === "kpis" ? "bg-ink text-white" : "bg-white text-ink"}`} onClick={() => setPage("kpis")}>{t("kpis")}</button>}
          {canApprove && !presenter && !replayMode && (
            <button className={`rounded-lg px-4 py-2 text-sm font-semibold ${page === "usage" ? "bg-ink text-white" : "bg-white text-ink"}`} onClick={() => setPage("usage")}>{t("usagePlan")}</button>
          )}
        </nav>

        {page === "flow" ? (
          replayRun ? <FlowDiagram run={replayRun} language={language} /> : <div className="rounded-xl bg-white p-6 text-slate-500">{t("selectRunForFlow")}</div>
        ) : page === "kpis" ? (
          kpis ? <KpiCards report={kpis} language={language} /> : <div className="rounded-xl bg-white p-6 text-slate-500">{language === "id" ? "Memuat data KPI…" : "Loading KPI data…"}</div>
        ) : page === "usage" ? (
          usage ? <UsageCard report={usage} language={language} /> : <div className="rounded-xl bg-white p-6 text-slate-500">{language === "id" ? "Memuat data penggunaan…" : "Loading usage data…"}</div>
        ) : (
        <div className="grid min-w-0 gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
          <aside className="h-fit rounded-2xl bg-white p-4 shadow-card">
            <div className="mb-3 flex items-center justify-between px-2">
              <h2 className="font-bold text-ink">{t("disruptionRuns")}</h2>
              <button className="text-xs font-semibold text-accent hover:underline disabled:opacity-50" disabled={replayMode} onClick={() => void refreshRuns()}>{t("refresh")}</button>
            </div>
            {runs.length === 0 ? (
              <p className="px-2 py-6 text-sm text-slate-500">{t("noRuns")}</p>
            ) : (
              <ul className="space-y-2">
                {runs.map((item) => (
                  <li key={item.run_id}>
                    <button
                      className={`w-full rounded-xl p-3 text-left transition ${item.run_id === selectedId ? "bg-teal-50 ring-1 ring-teal-200" : "hover:bg-slate-50"}`}
                      onClick={() => void selectRun(item.run_id)}
                    >
                      <span className="block truncate text-sm font-semibold text-ink">{item.event.component_name}</span>
                      <span className="mt-1 block text-xs text-slate-500">{item.event.delay_days} {language === "id" ? "hari keterlambatan" : "day delay"} · {item.severity ?? t("unclassified")}</span>
                      <span className="mt-2 block"><StatusPill status={item.status} /></span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </aside>

          {run ? (
            <div className="min-w-0 space-y-6">
              <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm text-slate-500">{t("activeEvent")} · {run.inventory_snapshot?.component_name ?? run.event.component_name}</p>
                    <h2 className="mt-1 text-xl font-bold text-ink">{run.event.title}</h2>
                    <p className="mt-1 text-sm text-slate-600">{run.event.delay_days} {t("delay")} · {t("severity")} {run.severity ?? "—"}</p>
                  </div>
                  <StatusPill status={run.status} />
                </div>
                <div className="mt-6"><WorkflowTimeline run={run} language={language} /></div>
              </section>

              <ImpactPanel run={run} language={language} />
              <VendorCharts
                evaluations={run.vendor_comparison}
                selectedVendorId={run.selected_vendor_id}
                costOfInaction={run.cost_of_inaction}
                language={language}
              />

              {run.execution_tracking && (
                <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-sm text-slate-500">{t("postApproval")}</p>
                      <h2 className="text-lg font-bold text-ink">{t("executionTracking")}</h2>
                    </div>
                    <StatusPill status={run.execution_tracking.shipment.status} />
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">{t("supplierConfirmation")}<strong className="mt-1 block text-ink">{run.execution_tracking.confirmation.confirmation_status} · {run.execution_tracking.confirmation.confirmed_quantity.toLocaleString()} pcs</strong></p>
                    <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">{t("asnEta")}<strong className="mt-1 block text-ink">{run.execution_tracking.shipment.tracking_id} · {run.execution_tracking.shipment.estimated_arrival}</strong></p>
                    <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">{t("projectedStock")}<strong className="mt-1 block text-ink">{run.execution_tracking.inventory_projection.projected_stock_at_arrival.toLocaleString()} pcs · {run.execution_tracking.inventory_projection.projected_coverage_days} {language === "id" ? "hari" : "days"}</strong></p>
                    <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">{t("lineStoppage")}<strong className="mt-1 block text-ink">{run.execution_tracking.line_stoppage_avoided ? t("avoidedSimulated") : t("notAvoided")}</strong></p>
                  </div>
                  {run.execution_tracking.alert && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{run.execution_tracking.alert}</p>}
                  <ul aria-label={t("monitoringTrackingOutputs")} className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    {run.execution_tracking.monitoring_outputs.map((output) => (
                      <li key={output.kind} className="rounded-xl border border-slate-200 p-3 text-sm">
                        <strong className="block text-ink">{t(`tracking.${output.kind}`)} · {output.status}</strong>
                        <span className="mt-1 block text-slate-600">{output.summary}</span>
                      </li>
                    ))}
                  </ul>
                  {run.kpis && (
                    <div className="mt-4 border-t border-slate-100 pt-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("illustrativePerRun")}</p>
                      <div className="mt-2 grid gap-3 sm:grid-cols-3">
                        <p className="text-sm text-slate-500">{t("costOfInaction")}<strong className="block text-ink">{money(run.kpis.cost_of_inaction)}</strong></p>
                        <p className="text-sm text-slate-500">{t("actionCost")}<strong className="block text-ink">{money(run.kpis.action_cost)}</strong></p>
                        <p className="text-sm text-slate-500">{t("illustrativeSavings")}<strong className="block text-ink">{money(run.kpis.illustrative_savings)}</strong></p>
                      </div>
                    </div>
                  )}
                </section>
              )}

              <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
                <div className="mb-4 flex items-end justify-between gap-3">
                <div><p className="text-sm text-slate-500">{t("aribaNetwork")}</p><h2 className="text-lg font-bold text-ink">{t("vendorComparison")}</h2></div>
                <span className="text-xs text-slate-500">{feasibleVendors.length} {t("feasible")}</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[700px] text-left text-sm">
                    <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                      <tr><th className="px-3 py-3">{t("vendor")}</th><th className="px-3 py-3">{t("regionDistance")}</th><th className="px-3 py-3">{t("lead")}</th><th className="px-3 py-3">{t("capacity")}</th><th className="px-3 py-3">{t("quote")}</th><th className="px-3 py-3">{t("riskScore")}</th><th className="px-3 py-3">{t("residualLoss")}</th><th className="px-3 py-3">{t("economicTotal")}</th><th className="px-3 py-3">{t("status")}</th></tr>
                    </thead>
                    <tbody>
                      {run.vendor_comparison.map((evaluation) => (
                        <tr className={`border-b border-slate-100 ${evaluation.vendor.vendor_id === run.selected_vendor_id ? "bg-teal-50/70" : ""}`} key={evaluation.vendor.vendor_id}>
                          <td className="px-3 py-3 font-semibold">{evaluation.vendor.vendor_name}{evaluation.vendor.vendor_id === run.selected_vendor_id && <span className="ml-2 text-xs text-accent">{t("recommended")}</span>}</td>
                          <td className="px-3 py-3">{evaluation.vendor.region} · {evaluation.vendor.distance_km.toLocaleString()} km</td>
                          <td className="px-3 py-3">{evaluation.vendor.lead_time_days} {language === "id" ? "hari" : "days"}</td>
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
                <AgentReasoning run={run} language={language} />

                <section className="rounded-2xl bg-white p-5 shadow-card md:p-6">
                  <p className="text-sm text-slate-500">
                    SAP S/4HANA · {run.draft_po?.status === "PENDING_APPROVAL" ? t("draftForApproval") : t("purchaseOrder")}
                  </p>
                  <h2 className="text-lg font-bold text-ink">{t("purchaseOrder")}</h2>
                  {run.draft_po ? (
                    <>
                      <div className="mt-4 rounded-xl bg-slate-50 p-4">
                        <div className="flex items-start justify-between gap-3"><div><p className="font-semibold text-ink">{run.draft_po.component_name}</p><p className="text-sm text-slate-500">{run.draft_po.vendor_name}</p></div><StatusPill status={run.draft_po.status} /></div>
                        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                          <p className="text-slate-500">{t("quantity")} <strong className="block text-ink">{run.draft_po.quantity.toLocaleString()} pcs</strong></p>
                          <p className="text-slate-500">{t("unitPrice")} <strong className="block text-ink">{money(run.draft_po.unit_price)}</strong></p>
                          <p className="text-slate-500">{t("total")} <strong className="block text-ink">{money(run.draft_po.total_price)}</strong></p>
                          <p className="text-slate-500">{t("terms")} <strong className="block text-ink">{run.draft_po.terms}</strong></p>
                          <p className="text-slate-500">{t("expectedDate")} <strong className="block text-ink">{run.draft_po.expected_date ?? "—"}</strong></p>
                          <p className="col-span-2 text-slate-500">{t("poNumber")} <strong className="block text-ink">DRAFT-{run.draft_po.po_id.replace(/[^a-z0-9]/gi, "").slice(0, 4).toUpperCase()}</strong></p>
                          {run.draft_po.sap_reference && <p className="col-span-2 text-slate-500">{t("sapReference")} <strong className="block text-ink">{run.draft_po.sap_reference}</strong></p>}
                        </div>
                      </div>
                      {pending && canApprove && !replayMode && (
                        <div className="mt-4 space-y-3">
                          <label className="block text-sm font-medium text-slate-700">{t("decisionNote")}
                            <input className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} placeholder={t("optionalAuditNote")} />
                          </label>
                          <label className="block text-sm font-medium text-slate-700">Vendor for revision
                            <select className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" value={revisionVendorId} onChange={(event) => setRevisionVendorId(event.target.value)}>
                              <option value="">{t("selectFeasibleVendor")}</option>
                              {feasibleVendors.map((evaluation) => <option key={evaluation.vendor.vendor_id} value={evaluation.vendor.vendor_id}>{evaluation.vendor.vendor_name} · {money(evaluation.risk_adjusted_total)}</option>)}
                            </select>
                          </label>
                          <div className="flex flex-wrap gap-2 pt-1">
                            <button className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={busy} onClick={() => void decide("approve")}>{t("reviewApproval")}</button>
                            <button className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50" disabled={busy || !revisionVendorId} onClick={() => void decide("revise")}>{t("reviseVendor")}</button>
                            <button className="rounded-lg border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-700 disabled:opacity-50" disabled={busy} onClick={() => void decide("reject")}>{t("reject")}</button>
                          </div>
                          <p className="text-xs leading-5 text-slate-500">{t("approvalInstructions")}</p>
                        </div>
                      )}
                      {pending && !canApprove && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{t("viewerDecisionHelp")}</p>}
                    </>
                  ) : <p className="mt-4 text-sm text-slate-500">{t("noPurchaseOrder")}</p>}
                </section>
              </div>
              <AuditViewer run={run} language={language} />
            </div>
          ) : (
            <section className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
              <div><p className="text-lg font-semibold text-ink">{t("noDisruptionSelected")}</p><p className="mt-2 text-sm text-slate-500">{t("triggerToAnalyze")}</p></div>
            </section>
          )}
        </div>
        )}
      </main>
      {pendingDecision && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-ink/60 p-4" role="presentation">
          <section role="dialog" aria-modal="true" aria-labelledby="decision-title" className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
            <h2 id="decision-title" className="text-xl font-bold text-ink">{t("decisionConfirmation")}: {t(pendingDecision)}</h2>
            <p className="mt-2 text-sm text-slate-600">
              {pendingDecision === "approve"
                ? t("approveConfirmation")
                : t("decisionRecorded")}
            </p>
            <label className="mt-4 flex items-start gap-3 text-sm text-slate-700">
              <input type="checkbox" checked={decisionConfirmed} onChange={(event) => setDecisionConfirmed(event.target.checked)} />
              {t("confirmCheckbox")}
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button className="rounded-lg border border-slate-300 px-4 py-2" onClick={() => setPendingDecision(null)}>{t("cancel")}</button>
              <button className="rounded-lg bg-accent px-4 py-2 font-semibold text-white disabled:opacity-50" disabled={!decisionConfirmed || busy} onClick={() => void confirmDecision()}>
                {busy ? (language === "id" ? "Mengirim…" : "Submitting…") : t("confirmDecision")}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
