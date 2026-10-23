export type RunStatus =
  | "ANALYZING"
  | "NOT_SIGNIFICANT"
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "EXECUTED"
  | "REJECTED"
  | "FAILED";

export interface Stage {
  name: string;
  status: string;
  summary: string;
  completed_at: string;
}

export interface VendorEvaluation {
  vendor: {
    vendor_id: string;
    vendor_name: string;
    lead_time_days: number;
    total_cost: number;
    currency: string;
    risk_score: number;
    capacity: number;
  };
  feasible: boolean;
  action_cost: number;
  residual_stockout_days: number;
  residual_stockout_loss: number;
  risk_adjusted_total: number;
  rationale: string;
}

export interface PurchaseOrder {
  po_id: string;
  sap_reference: string | null;
  vendor_id: string;
  vendor_name: string;
  component_id: string;
  component_name: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  currency: string;
  terms: string;
  status: string;
}

export interface DisruptionRun {
  run_id: string;
  status: RunStatus;
  severity: string | null;
  significant: boolean;
  event: {
    title: string;
    component_name: string;
    delay_days: number;
    event_type: string | null;
  };
  stages: Stage[];
  vendor_comparison: VendorEvaluation[];
  trace_steps: { source: string; text: string }[];
  selected_vendor_id: string | null;
  chain_of_thought: string[];
  inventory_snapshot: {
    current_stock: number;
    daily_consumption: number;
    line_stoppage_cost_per_day: number;
    purchase_quantity: number;
  } | null;
  cost_of_inaction: number;
  audit_log: {
    timestamp: string;
    agent: string;
    input_summary: string;
    output_summary: string;
    reasoning: string;
  }[];
  draft_po: PurchaseOrder | null;
  execution_tracking: {
    sap_reference: string;
    ariba_reference: string;
    confirmation: {
      confirmation_status: string;
      confirmed_quantity: number;
      note: string;
    };
    shipment: {
      tracking_id: string;
      status: string;
      estimated_arrival: string;
      note: string;
    };
    inventory_projection: {
      projected_stock_at_arrival: number;
      projected_coverage_days: number;
      source: string;
    };
    line_stoppage_avoided: boolean;
    eta_deviation_days: number;
    alert: string | null;
    simulated: boolean;
  } | null;
  kpis: {
    simulated: boolean;
    cost_of_inaction: number;
    action_cost: number;
    illustrative_savings: number;
    line_stoppage_avoided: boolean;
    estimated_stockout_days_avoided: number;
  } | null;
  error: string | null;
}

export interface KPIReport {
  simulated: boolean;
  label: string;
  tracked_runs: number;
  executed_runs: number;
  line_stoppages_avoided: number;
  illustrative_cost_of_inaction: number;
  illustrative_action_cost: number;
  illustrative_savings: number;
}

export interface ApiError {
  code?: string;
  message?: string;
  detail?: string;
}
