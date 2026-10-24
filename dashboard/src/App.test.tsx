import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { pendingRun } from "./test-fixtures";

function makeJwt(role: "viewer" | "approver"): string {
  const claims = {
    sub: `demo-${role}`,
    roles: [role],
    exp: Math.floor(Date.now() / 1000) + 300,
    nonce: "expected-nonce",
  };
  return `header.${btoa(JSON.stringify(claims))}.signature`;
}

function installAuthenticatedFetch(role: "viewer" | "approver") {
  const idToken = makeJwt(role);
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
    window.history.replaceState({}, "", "/");
  });

  it("keeps authenticated viewers read-only", async () => {
    installAuthenticatedFetch("viewer");

    render(<App />);

    expect(await screen.findByText(/Viewer access is read-only/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review approval" })).not.toBeInTheDocument();
    expect(screen.getByText("demo-viewer · viewer")).toBeInTheDocument();
    expect(sessionStorage.getItem("chainmind.access_token")).toBeNull();
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
});
