export type Row = Record<string, string>;
export type Table = {
  table_id: string;
  page: number;
  kind: string;
  headers: string[];
  rows: string[][];
  requires_review: boolean;
};
export type Extraction = {
  document_id: string;
  source_file: string;
  records: Row[];
  tables: Table[];
  issues: Record<string, unknown>[];
  pages: Record<string, unknown>[];
};
export type Session = {
  id: string;
  filename: string;
  project: string;
  contractor: string;
  status: string;
  use_ocr: boolean;
  page: number;
  total_pages: number;
  revision: number;
  created_at: string;
  error?: string;
  extraction?: Extraction;
  review_tokens?: Record<string, string>;
  reviewed?: Record<string, string>;
  review_summary?: ReviewSummary;
  saved_ids?: string[];
};
export type ReferenceRow = Record<
  | "source_csv_row_number"
  | "subcontractor"
  | "position"
  | "effective_time_period_start"
  | "effective_time_period_finish"
  | "reg_rate"
  | "ot_rate"
  | "dt_rate"
  | "status"
  | "bu_approval_received",
  string
> & { issues: string[] };
export type Reference = {
  id: string;
  name: string;
  created_at: string;
  rows: ReferenceRow[];
  issues: { reference_row: string; messages: string[] }[];
};
export type Finding = Record<
  | "finding_id"
  | "run_id"
  | "record_id"
  | "document_id"
  | "project"
  | "contractor"
  | "classification"
  | "work_start"
  | "work_end"
  | "source_file"
  | "source_page"
  | "table_id"
  | "document_reference"
  | "ticket_id"
  | "rate_type"
  | "submitted_rate"
  | "approved_rate"
  | "difference_per_hour"
  | "reference_version"
  | "reference_row"
  | "reference_rate_field"
  | "effective_start"
  | "effective_finish"
  | "approval_status"
  | "bu_approval_received",
  string
> & {
  outcome: "match" | "difference" | "needs_review";
  reason: string;
  finding_kind?: string;
  match_method?: string;
  match_explanation?: string;
  trade_family?: string;
  approved_rates?: string[];
  matched_classifications?: string[];
  reference_rows?: string[];
  candidates: ReferenceRow[];
  review_details: Row;
};
export type Run = {
  id: string;
  created_at: string;
  reference_version: string;
  reference_name: string;
  stale: boolean;
  rules_changed?: boolean;
  record_ids: string[];
  results: Finding[];
  counts: Record<string, number>;
};

export type ReviewItem = {
  table_id: string;
  page: number;
  label: string;
  status: "mapping" | "needs_review" | "reviewed" | "ready" | "saved";
  row_count: number;
  unsaved_rows: number;
  reason: string;
};
export type ReviewSummary = {
  status: string;
  pending_tables: number;
  reviewed_tables: number;
  unsaved_rows: number;
  items: ReviewItem[];
  problem_pages: number[];
};
