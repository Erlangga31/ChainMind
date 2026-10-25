import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  AgentReasoning,
  AuditViewer,
  ImpactPanel,
  KpiCards,
  UsageCard,
  VendorCharts,
  WorkflowTimeline,
} from "./components";
import { pendingRun } from "./test-fixtures";
import type { KPIReport, UsageReport, VendorEvaluation } from "./types";

const vendorEvaluations: VendorEvaluation[] = [
  {
    vendor: {
      vendor_id: "vendor-a",
      vendor_name: "Vendor A",
      lead_time_days: 3,
      total_cost: 120000,
      currency: "USD",
      risk_score: 78,
      capacity: 6000,
      region: "East Java",
      distance_km: 650,
    },
    feasible: true,
    action_cost: 120000,
    residual_stockout_days: 0,
    residual_stockout_loss: 0,
    risk_adjusted_total: 120000,
    rationale: "Lower price, later arrival.",
  },
  {
    vendor: {
      vendor_id: "vendor-b",
      vendor_name: "Vendor B",
      lead_time_days: 2,
      total_cost: 135000,
      currency: "USD",
      risk_score: 88,
      capacity: 6000,
      region: "West Java",
      distance_km: 125,
    },
    feasible: true,
    action_cost: 135000,
    residual_stockout_days: 0,
    residual_stockout_loss: 0,
    risk_adjusted_total: 135000,
    rationale: "Fastest feasible delivery.",
  },
];

const report: KPIReport = {
  simulated: true,
  label: "Illustrative sandbox results",
  tracked_runs: 3,
  executed_runs: 2,
  line_stoppages_avoided: 2,
  illustrative_cost_of_inaction: 250000,
  illustrative_action_cost: 135000,
  illustrative_savings: 115000,
  comparison: [
    {
      metric: "Response time",
      unit: "minutes",
      manual_baseline: 240,
      chainmind_value: 1.5,
      manual_is_illustrative: true,
      chainmind_is_illustrative: false,
    },
  ],
};

const usage: UsageReport = {
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
};

describe("dashboard visual components", () => {
  it("renders all six workflow stages and current status", () => {
    render(<WorkflowTimeline run={pendingRun} />);

    expect(screen.getByText("Deteksi Gangguan")).toBeInTheDocument();
    expect(screen.getByText("Analisis Dampak")).toBeInTheDocument();
    expect(screen.getByText("Pencarian Solusi")).toBeInTheDocument();
    expect(screen.getByText("Analisis & Keputusan")).toBeInTheDocument();
    expect(screen.getByText("Human-in-the-Loop")).toBeInTheDocument();
    expect(screen.getByText("Eksekusi Purchase Order")).toBeInTheDocument();
    expect(screen.getAllByText("COMPLETED").length).toBeGreaterThan(0);
  });

  it("shows SAP inventory impact and derives coverage and stockout risk", () => {
    render(
      <ImpactPanel
        language="en"
        run={{
          ...pendingRun,
          inventory_snapshot: {
            component_name: "Microchip X",
            current_stock: 3000,
            daily_consumption: 1000,
            line_stoppage_cost_per_day: 5000,
            purchase_quantity: 5000,
          },
          cost_of_inaction: 10000,
        }}
      />,
    );

    expect(screen.getByText("3.0 days")).toBeInTheDocument();
    expect(screen.getByText("2.0 days")).toBeInTheDocument();
    expect(screen.getByText("$10,000")).toBeInTheDocument();
    expect(screen.getByText(/source: SAP S\/4HANA/)).toBeInTheDocument();
  });

  it("lists each affected BOM component and marks the critical material", () => {
    render(
      <ImpactPanel
        language="en"
        run={{
          ...pendingRun,
          material_impacts: [
            {
              component_id: "microchip-x",
              component_name: "Microchip X",
              coverage_days: 3,
              stockout_days: 2,
              cost_of_inaction: 200_000,
              critical: false,
            },
            {
              component_id: "sensor-y",
              component_name: "Sensor Y",
              coverage_days: 1,
              stockout_days: 4,
              cost_of_inaction: 1_000_000,
              critical: true,
            },
          ],
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "BOM component impact" })).toBeInTheDocument();
    expect(screen.getByText("Sensor Y")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("$1,000,000")).toBeInTheDocument();
  });

  it("renders supplier source and comparison charts", () => {
    render(
      <VendorCharts
        language="en"
        evaluations={vendorEvaluations}
        selectedVendorId="vendor-b"
        costOfInaction={200000}
      />,
    );

    expect(screen.getByText("Source: SAP Ariba")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Vendor cost versus lead time chart" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Vendor action cost compared with cost of inaction" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Vendor risk score chart" })).toBeInTheDocument();
  });

  it("groups chain-of-thought entries under source badges", () => {
    render(
      <AgentReasoning
        run={{
          ...pendingRun,
          chain_of_thought: [
            "[SAP S/4HANA] Current inventory covers three production days.",
            "[SAP Ariba] Vendor B can deliver in two days.",
          ],
        }}
      />,
    );

    expect(screen.getByText("Orchestrator Agent · SAP S/4HANA")).toBeInTheDocument();
    expect(screen.getByText("Orchestrator Agent · SAP Ariba")).toBeInTheDocument();
    expect(screen.getByText("Vendor B can deliver in two days.")).toBeInTheDocument();
  });

  it("renders audit entries and the KPI summary", () => {
    render(
      <AuditViewer
        language="en"
        run={{
          ...pendingRun,
          audit_log: [
            {
              timestamp: "2026-01-01T00:00:00Z",
              agent: "orchestrator",
              input_summary: "Vendor comparison",
              output_summary: "Selected Vendor B.",
              reasoning: "Lowest total economic cost.",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("Audit log · 1 entries")).toBeInTheDocument();
    expect(screen.getByText("Selected Vendor B.")).toBeInTheDocument();
    expect(screen.getByText("Lowest total economic cost.")).toBeInTheDocument();

    render(<KpiCards language="en" report={report} />);
    expect(screen.getByText("Response KPIs")).toBeInTheDocument();
    expect(screen.getByText("Illustrative savings")).toBeInTheDocument();
    expect(screen.getByText("$115,000")).toBeInTheDocument();
    expect(screen.getByText("Manual baseline vs ChainMind")).toBeInTheDocument();
    expect(screen.getByText("240 minutes · illustrative")).toBeInTheDocument();
  });

  it("renders tenant usage and explicitly separates onboarding from monthly charges", () => {
    render(<UsageCard language="en" report={usage} />);

    expect(screen.getByText("Usage & Plan")).toBeInTheDocument();
    expect(screen.getByText("Usage month")).toBeInTheDocument();
    expect(screen.getByText("2026-10")).toBeInTheDocument();
    expect(screen.getByText("Resolved disruptions")).toBeInTheDocument();
    expect(screen.getByText("One-time onboarding")).toBeInTheDocument();
    expect(screen.getByText("$1,700")).toBeInTheDocument();
    expect(screen.getAllByText(/not a quote or invoice/)).toHaveLength(2);
  });
});
