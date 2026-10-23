import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { WorkflowTimeline } from "./components";
import { pendingRun } from "./test-fixtures";

describe("WorkflowTimeline", () => {
  it("renders the six named proposal stages", () => {
    render(<WorkflowTimeline run={pendingRun} />);
    expect(screen.getByText("Deteksi Gangguan")).toBeInTheDocument();
    expect(screen.getByText("Analisis Dampak")).toBeInTheDocument();
    expect(screen.getByText("Pencarian Solusi")).toBeInTheDocument();
    expect(screen.getByText("Analisis & Keputusan")).toBeInTheDocument();
    expect(screen.getByText("Human-in-the-Loop")).toBeInTheDocument();
    expect(screen.getByText("Eksekusi Purchase Order")).toBeInTheDocument();
  });
});
