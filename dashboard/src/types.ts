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
  };
  stages: Stage[];
  vendor_comparison: VendorEvaluation[];
  selected_vendor_id: string | null;
  chain_of_thought: string[];
  draft_po: PurchaseOrder | null;
  error: string | null;
}

export interface ApiError {
  code?: string;
  message?: string;
  detail?: string;
}
