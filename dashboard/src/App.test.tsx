import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { pendingRun } from "./test-fixtures";

function makeJwt(role: "viewer" | "approver"): string {
  const claims = {
    sub: `demo-${role}`,
    tenant_id: "demo",
    roles: [role],
    exp: Math.floor(Date.now() / 1000) + 300,
    nonce: "expected-nonce",
  };
  return `header.${btoa(JSON.stringify(claims))}.signature`;
}

function installAuthenticatedFetch(role: "viewer" | "approver", language: "id" | "en" = "en") {
  const idToken = makeJwt(role);
  localStorage.setItem("chainmind.language", language);
  sessionStorage.setItem("chainmind.oidc.state", "expected-state");
  sessionStorage.setItem("chainmind.oidc.nonce", "expected-nonce");
  sessionStorage.setItem("chainmind.oidc.verifier", "test-verifier");
  window.history.replaceState({}, "", "/?code=authorization-code&state=expected-state");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const value = url.endsWith("/oidc/token")
        ? { access_token: "api-token", id_token: idToken }
        : url.endsWith("/health")
          ? { mode: "mock" }
          : url.endsWith("/usage")
            ? {
                tenant_id: "demo",
                period_start: "2026-10-01",
                plan_tier: "Starter",
                resolved_disruptions: 12,
                included_disruptions: 10,
                active_agents: 5,
                included_agents: 4,
                monthly_subscription_fee: 500,
                disruption_overage_fee: 100,
                additional_agent_fee: 100,
                one_time_onboarding_fee: 1000,
                illustrative_monthly_estimate: 700,
                illustrative_first_invoice_estimate: 1700,
                illustrative: true,
                label: "Illustrative estimate only; not a quote or invoice.",
              }
          : url.endsWith("/runs")
            ? [pendingRun]
            : pendingRun;
      return new Response(JSON.stringify(value), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return idToken;
}

describe("OIDC-authenticated approval dashboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
    localStorage.clear();
    delete document.documentElement.dataset.fontScale;
    delete document.documentElement.dataset.highContrast;
    window.history.replaceState({}, "", "/");
  });

  it("keeps authenticated viewers read-only", async () => {
    installAuthenticatedFetch("viewer");

    render(<App />);

    expect(await screen.findByText(/Viewer access is read-only/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review approval" })).not.toBeInTheDocument();
    expect(screen.getByText("demo-viewer · viewer")).toBeInTheDocument();
    expect(sessionStorage.getItem("chainmind.access_token")).toBeNull();
    const feed = screen.getByRole("region", { name: "Notification feed" });
    expect(feed).toHaveTextContent(
      "Raw material Microchip X delayed 5 days. Stock for 3 days (source: SAP S/4HANA). Recommendation: buy from Vendor B at $135,000 (source: SAP Ariba).",
    );
    expect(within(feed).getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(within(feed).getByRole("button", { name: "View details" })).toBeEnabled();
  });

  it("allows authenticated approvers to confirm a decision with the bearer token", async () => {
    const idToken = installAuthenticatedFetch("approver");

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Review approval" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const confirmButton = screen.getByRole("button", { name: "Confirm decision" });
    expect(confirmButton).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    await waitFor(() => expect(confirmButton).toBeEnabled());
    fireEvent.click(confirmButton);
    await waitFor(() => expect(confirmButton).not.toBeInTheDocument());
    const decisionCall = vi.mocked(fetch).mock.calls.find(([input]) =>
      String(input).endsWith("/runs/demo-run/decision"),
    );
    expect(decisionCall).toBeDefined();
    const headers = decisionCall?.[1]?.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Bearer ${idToken}`);
    expect(headers["X-ChainMind-Role"]).toBeUndefined();
    expect(JSON.parse(String(decisionCall?.[1]?.body))).toEqual({
      decision: "approve",
      note: "",
    });
  });

  it("opens a confirmation dialog from the notification feed without approving directly", async () => {
    installAuthenticatedFetch("approver");

    render(<App />);
    const feed = await screen.findByRole("region", { name: "Notification feed" });
    fireEvent.click(within(feed).getByRole("button", { name: "Approve" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(
      vi.mocked(fetch).mock.calls.some(([input]) =>
        String(input).endsWith("/runs/demo-run/decision"),
      ),
    ).toBe(false);
    expect(screen.getByRole("button", { name: "Confirm decision" })).toBeDisabled();
  });

  it("shows usage and plan details only to approvers", async () => {
    installAuthenticatedFetch("viewer");
    const viewer = render(<App />);
    await screen.findByRole("button", { name: "Disruptions" });
    expect(screen.queryByRole("button", { name: "Usage & Plan" })).not.toBeInTheDocument();
    viewer.unmount();

    installAuthenticatedFetch("approver");
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Usage & Plan" }));

    expect(await screen.findByText("Usage & Plan")).toBeInTheDocument();
    expect(await screen.findByText("$1,700")).toBeInTheDocument();
  });

  it("defaults to Indonesian and exposes language and accessibility controls", async () => {
    installAuthenticatedFetch("approver", "id");
    render(<App />);

    expect(await screen.findByRole("button", { name: "Gangguan" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Feed notifikasi" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(await screen.findByRole("button", { name: "Disruptions" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Larger text" }));
    fireEvent.click(screen.getByRole("button", { name: "High contrast" }));
    expect(document.documentElement.dataset.fontScale).toBe("large");
    expect(document.documentElement.dataset.contrast).toBe("high");
  });
});
