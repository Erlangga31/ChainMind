import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FlowDiagram } from "./FlowDiagram";
import { pendingRun } from "./test-fixtures";

describe("live proposal flow diagram", () => {
  it("renders the seven live stages and decision branches with run values", () => {
    render(<FlowDiagram run={pendingRun} language="id" />);

    for (let stage = 0; stage <= 6; stage += 1) {
      expect(screen.getByTestId(`flow-stage-${stage}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("flow-decision-significant")).toBeInTheDocument();
    expect(screen.getByTestId("flow-decision-approval")).toBeInTheDocument();
    expect(screen.getByTestId("flow-branch-external-ingestion")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("flow-branch-ingestion-monitoring")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("flow-branch-significant-impact")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("flow-branch-insignificant-end")).toHaveAttribute("data-active", "false");
    expect(screen.getByText(/Vendor B: 2d · \$135,000 · risk 88/)).toBeInTheDocument();
    expect(screen.getByText(/PENDING_APPROVAL/)).toBeInTheDocument();
    expect(screen.getByText("Amazon DynamoDB")).toBeInTheDocument();
    expect(screen.getAllByText("SAP Ariba Network")).toHaveLength(2);
    expect(screen.getByTestId("flow-stage-4-po")).toHaveTextContent(/5,000 pcs Microchip X.*\$27\/unit/);
    expect(screen.getByText(/Monitoring & Tracking/)).toBeInTheDocument();
  });

  it("highlights the insignificant no-branch and terminates at Done", () => {
    const insignificantRun = {
      ...pendingRun,
      significant: false,
      status: "NOT_SIGNIFICANT" as const,
      stages: [
        { ...pendingRun.stages[0], status: "COMPLETED" },
        { ...pendingRun.stages[1], status: "SKIPPED" },
      ],
    };
    render(<FlowDiagram run={insignificantRun} language="en" />);

    expect(screen.getByTestId("flow-branch-insignificant-end")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("flow-insignificant-end")).toHaveTextContent("Done");
    expect(screen.getByTestId("flow-branch-significant-impact")).toHaveAttribute("data-active", "false");
  });

  it("shows the approval rejection and revision paths from run state", () => {
    const rejected = { ...pendingRun, status: "REJECTED" as const };
    const revised = { ...pendingRun, revision_count: 1 };
    const { rerender } = render(<FlowDiagram run={rejected} language="en" />);
    expect(screen.getByTestId("flow-branch-rejection-end")).toHaveAttribute("data-active", "true");

    rerender(<FlowDiagram run={revised} language="en" />);
    expect(screen.getByTestId("flow-branch-revision-loop")).toHaveAttribute("data-active", "true");
  });
});
