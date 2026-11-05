export type Nullable<T> = T | null;

export interface Envelope<T> {
  api_version: number;
  state: string;
  snapshot: SnapshotMeta | null;
  data: T | null;
  error: ApiErrorBody | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
}

export interface SnapshotGap {
  day?: string;
  reason?: string;
  [key: string]: unknown;
}

export interface SnapshotMeta {
  as_of: string | null;
  first_day: string | null;
  last_day: string | null;
  last_valid_valuation_at: string | null;
  mode: string;
  source: string;
  source_version: string;
  evidence_class: string;
  publication: string;
  refresh_policy: string;
  forward_account: string;
  market_freshness: string;
  gaps: Array<string | SnapshotGap>;
  snapshot_id: string;
  report_sha256: string;
  input_sha256: string;
  ledger_head: string;
  validation: string;
  execution_model?: unknown;
  historical_assumptions?: unknown;
  missing_opening_evidence_sessions?: string;
  unverified_status_sessions?: string;
  unobserved_calendar_days_including_weekends?: string;
  timezone?: string;
}

export interface Deployment {
  deployment_id: string;
  frozen_version: string;
  group_id: string;
  strategy_id: string;
}

export interface PaperPortfolioBatch {
  decision_day: string; target_day: string | null; frozen_at: string; finalized_at: string | null;
  label: string; reason: string; source_sha256: string; calendar_sha256: string; policy_sha256: string;
  candidate: {task_id:string; candidate_sha256:string; registration_sha256:string; model_version:string} | null;
  order_ids: string[]; rejections: Array<[Instrument,string]>; confirmation_source_sha256: string | null;
}
export interface PaperPortfolio {
  capacity_scope?: string | null; capacity_shares?: string;
  unverified_eod_assumption?: {version:string;max_exposure:string} | null;
  recoveries?: Array<{label:string;previous_day:string;valuation:{day:string};equity:string}>;
  automatic: boolean; policy_version: string; policy_sha256:string; target_value_fen:string;
  max_positions: string; max_daily_orders: string; pending: string | null; batches: PaperPortfolioBatch[];
}
export interface AccountData {
  portfolio?: PaperPortfolio | null;
  account_id: string;
  day: string | null;
  nav_fen: string | null;
  cash_fen: string | null;
  available_cash_fen: string | null;
  reserved_cash_fen: string | null;
  session_pnl_fen: string | null;
  cumulative_pnl_fen: string | null;
  total_return_bps: string | null;
  max_daily_observation_drawdown_bps: string | null;
  total_fee_fen: string | null;
  initial_nav_fen: string | null;
  external_flow_total_fen: string | null;
  valuation_error: string | null;
  risk: RiskState | null;
  deployment: Deployment;
}

export interface RiskState {
  account_id: string;
  cash_flow_adjusted_peak: string | null;
  account_freezes: unknown[] | null;
  strategy_freezes: unknown[] | null;
  deployment: Deployment;
}

export interface EquityRow {
  day: string;
  nav_fen: string | null;
  cash_fen: string | null;
  cumulative_pnl_fen: string | null;
  return_bps: string | null;
  valuation_error: string | null;
}

export interface Instrument {
  code: string;
  market: string;
}

export interface Lot {
  acquired_on?: string | null;
  quantity?: string | null;
  cost_basis_fen?: string | null;
}

export interface Position {
  instrument: Instrument;
  quantity: string;
  sellable_shares: string;
  unsettled_shares: string;
  reserved_sell_shares: string;
  market_value_fen: string | null;
  cost_basis_fen: string | null;
  unrealized_pnl_fen: string | null;
  lots: Lot[] | null;
  deployment: Deployment;
  price_series?: unknown;
  price_series_reason?: string | null;
}

export interface StrategyRecord {
  deployment: Deployment;
  status: string;
  pnl_fen: string | null;
  drawdown_bps: string | null;
  unavailable_reason: string | null;
}

export interface FeeBreakdown {
  commission: string;
  tax: string;
  transfer: string;
}

export interface Fill {
  fill_id: string;
  order_id: string;
  day: string;
  instrument: Instrument;
  side: 'Buy' | 'Sell' | string;
  quantity: string;
  price_fen: string;
  fee_fen: string;
  fees: FeeBreakdown | null;
  simulated_at: string | null;
  risk_checked_at: string | null;
  deployment: Deployment;
  execution_assumption: string | null;
  source_version: string | null;
}

export interface Order {
  order_id: string;
  day: string;
  instrument: Instrument;
  side: 'Buy' | 'Sell' | string;
  quantity: string;
  confirmed_filled_shares: string;
  remaining: string;
  limit_fen: string;
  status: string;
  reason: string | null;
  deployment: Deployment;
}

export interface HealthData {
  service: string;
  paper_only: boolean;
  market_data: string;
  forward_account: string;
  agent: string;
  notifications: string;
  refresh_policy: string;
}

export interface ResearchWindow {
  name?: string;
  first_day?: string;
  last_day?: string;
  days?: string;
  net_pnl_fen?: string | null;
  fills?: string;
  missing_nav_days?: string;
  [key: string]: unknown;
}

export interface ResearchResult {
  strategy_version?: string;
  research_evidence?: string;
  engineering?: string;
  independent_acceptance?: string | boolean;
  data_coverage?: {
    target?: string;
    target_blockers?: unknown[];
    [key: string]: unknown;
  };
  windows?: ResearchWindow[];
  [key: string]: unknown;
}

export interface ResearchData {
  results: ResearchResult[];
  status: string;
}

export interface PaperBundle {
  account: AccountData;
  equity: EquityRow[];
  positions: Position[];
  strategies: StrategyRecord[];
  fills: Fill[];
  orders: Order[];
}

// ---------- Agent V1 ----------

export interface AgentBudget {
  state: 'configured' | 'unconfigured' | string;
  currency: string;
  timezone: string;
  day: string;
  month: string;
  unit: string;
  daily_limit_micro: string | null;
  monthly_limit_micro: string | null;
  daily_settled_micro: string | null;
  monthly_settled_micro: string | null;
  daily_remaining_micro: string | null;
  monthly_remaining_micro: string | null;
  reserved_micro: string | null;
  call_count: string | null;
  input_tokens: string | null;
  output_tokens: string | null;
  usage_estimate_micro: string | null;
  billing: string;
}

export interface AgentModel {
  id: string;
  label: string;
  kind: string;
  model: string;
  endpoint: string | null;
  authorization: string;
  availability: string;
  last_reason?: string | null;
  price_version: string;
  verification: string;
}

export interface AgentUsageByModel {
  provider_id: string;
  calls: string;
  input_tokens: string;
  output_tokens: string;
  usage_micro: string;
}

export interface AgentEodLatest {
  source_day?: string | null;
  disposition?: string | null;
  reason?: string | null;
  task_id?: string | null;
  [key: string]: unknown;
}

export interface AgentEod {
  enabled: boolean;
  latest: AgentEodLatest | null;
  reason: string | null;
  skipped: string;
}

export interface AgentInput {
  version: string;
  source_day: string;
  mode: string;
  scopes: string[];
  summary: Record<string, unknown>;
  eod_eligible: boolean;
}

export interface AgentStatus {
  dashboard_mode?: 'attached_explicit_operations' | 'worker';
  service: string;
  paused: boolean;
  worker_concurrency: string;
  worker_error: string | null;
  default_model: string | null;
  backup_model: string | null;
  models: AgentModel[];
  budget: AgentBudget;
  usage_by_model: AgentUsageByModel[];
  eod: AgentEod;
  input: AgentInput;
  qualification: string;
  automatic_fallback: string;
  budget_settings: string;
}

export interface AgentCall {
  id: string;
  state: string;
  day: string;
  month: string;
  maximum_micro: string;
  settled_micro: string;
  usage_micro: string;
  price_version: string;
  reason: string | null;
  input_tokens: string;
  output_tokens: string;
}

export interface AgentTask {
  id: string;
  name: string;
  status: string;
  reason: string | null;
  provider_id: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  conclusion: string | null;
  calls: AgentCall[];
  retryable: boolean;
}

export interface AgentTaskRequest {
  name: string;
  goal: string;
  scope: string;
  start_day: string;
  end_day: string;
  task_budget_micro: string | null;
}

export interface AgentResearchOutput {
  hypothesis: string;
  evidence: string[];
  risks: string[];
  next_steps: string[];
}

export interface AgentResult {
  research: AgentResearchOutput;
  provider_id: string;
  provider_kind: string;
  model: string;
  input_summary_version: string;
  source_day: string;
  input_mode: string;
  generated_at: string;
  synthetic_provider: boolean;
  qualification: string;
  limitations: string;
  billing: string;
}

export interface AgentTaskDetail {
  artifact?: unknown;
  id: string;
  status: string;
  reason: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested_at: string | null;
  retryable: boolean;
  provider_id: string;
  provider_hash: string;
  request: AgentTaskRequest;
  input: AgentInput;
  result: AgentResult | null;
  calls: AgentCall[];
}

export interface AgentTaskList {
  tasks: AgentTask[];
  next_before: string | null;
}

export interface AgentCreateResult {
  id: string;
  status: string;
}
