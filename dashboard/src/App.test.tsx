import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { pendingRun } from "./test-fixtures";

describe("approval dashboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it("keeps viewers read-only and requires explicit confirmation from approvers", async () => {
    sessionStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const value = url.endsWith("/health")
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

    render(<App />);
    expect(await screen.findByText(/Viewer access is read-only/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review approval" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox", { name: "Mock SSO role" }), {
      target: { value: "approver" },
    });
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
    expect((decisionCall?.[1]?.headers as Record<string, string>)["X-ChainMind-Role"]).toBe(
      "approver",
    );
    expect(JSON.parse(String(decisionCall?.[1]?.body))).toEqual({
      decision: "approve",
      note: "",
    });
  });
});
