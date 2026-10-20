// Shapes of the JSON files that `fdeops demo --export` writes. Only the fields the UI reads.

export type Provenance = "pipeline-test" | "measured-in-simulation" | "estimated";

export interface TenantEntry {
  id: string;
  display_name: string;
  pack: string;
}

export interface DemoStep {
  key: string;
  title: string;
  text: string;
  refs: Record<string, string>;
}

export interface RunIndexEntry {
  label: string;
  run_id: string;
  config: string;
  split: string;
  provenance: Provenance;
  incident: string | null;
  success: number;
  ci: [number, number];
  critical_trials: number;
  n: number;
}

export interface DemoIndex {
  generated_at: string;
  fdeops_version: string;
  provenance: Provenance[];
  tenant: {
    id: string;
    display_name: string;
    pack: string;
    notes: string;
    scenarios: string[];
    kb_sections: number;
    pii_redaction: boolean;
    data_quality: { loaded: number; isolated: number; issues: number };
  };
  steps: DemoStep[];
  runs: RunIndexEntry[];
  detail_runs: string[];
  comparisons: string[];
}

export interface SliceStat {
  slice: string;
  n: number;
  cases: number;
  successes: number;
  rate: number;
  ci_lo: number;
  ci_hi: number;
}

export interface RunSummary {
  run_id: string;
  provenance: Provenance;
  agent_config_id: string;
  dataset_ref: string;
  incident: string | null;
  trials: number;
  overall: SliceStat;
  pass_hat_k: Record<string, number>;
  by_scenario: SliceStat[];
  by_tag: SliceStat[];
  evaluator_pass_rates: Record<string, number>;
  critical_trials: number;
  critical_violations: number;
  critical_rate_upper: number;
  metrics: Record<string, number | null>;
}

export interface TrialRow {
  case_id: string;
  trial: number;
  scenario: string;
  tags: string[];
  difficulty: string;
  success: boolean;
  primary_failure: string | null;
  resolution: string | null;
  steps: number;
  latency_ms: number;
  violations: string[];
}

export interface RunFile {
  label: string;
  summary: RunSummary;
  report_md: string;
  trials: TrialRow[];
}

export interface DiffEstimate {
  mean: number;
  lo: number;
  hi: number;
  n: number;
}

export interface Comparison {
  a_run_id: string;
  b_run_id: string;
  a_config: string;
  b_config: string;
  n_pairs: number;
  trials: number;
  a_rate: number;
  b_rate: number;
  diff: DiffEstimate;
  a_only: number;
  b_only: number;
  mcnemar_p: number;
  by_scenario: Record<string, DiffEstimate>;
  scenario_p: Record<string, number>;
  holm_p: Record<string, number>;
  by_tag: Record<string, DiffEstimate>;
  tag_holm_p: Record<string, number>;
}

export interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_calls: { id: string; name: string; arguments: Record<string, unknown> | null }[];
  name: string | null;
}

export interface Span {
  span_id: string;
  parent_id: string | null;
  kind: string;
  name: string;
  status: "ok" | "error";
  error: string | null;
  attributes: Record<string, unknown>;
}

export interface Score {
  evaluator: string;
  name: string;
  value: number | null;
  passed: boolean | null;
  critical: boolean;
  details: Record<string, unknown>;
}

export interface TrialDetail {
  case_id: string;
  scenario: string;
  tags: string[];
  trial: number;
  success: boolean;
  scores: Score[];
  episode: {
    outcome: string;
    turns: number;
    steps: number;
    transcript: Message[];
    tool_calls: {
      op: string;
      args: Record<string, unknown> | null;
      ok: boolean;
      error_code: string | null;
      latency_ms: number;
      attempts: number;
      mutating: boolean;
    }[];
    retrieved: { uid: string; title: string; rank: number; stale: boolean }[];
    violations: { rule: string; severity: string; message: string }[];
    final_message: string;
    trace: { spans: Span[] };
    faults_injected: [string, string][];
  };
}

export interface Evidence {
  kind: string;
  ref: string;
  detail: string;
}

export interface InterventionResult {
  intervention_id: string;
  description: string;
  deployable: boolean;
  n_cases: number;
  fixed: number;
  fix_rate: number;
  fix_ci: [number, number];
  n_control: number;
  regressions: number;
  regression_ci: [number, number];
}

export interface ClusterDiagnosis {
  cluster: {
    id: string;
    failure_class: string;
    scenario: string;
    n_trials: number;
    n_cases: number;
    share_of_failures: number;
    tags: Record<string, number>;
    examples: Evidence[];
  };
  hypotheses: string[];
  results: InterventionResult[];
  verdict: string;
  confirmed_by: string | null;
  recommended_fix: string | null;
  rationale: string;
}

export interface Diagnosis {
  run_id: string;
  n_trials: number;
  n_failures: number;
  clusters: ClusterDiagnosis[];
  warnings: string[];
}

export interface GateResult {
  gate: string;
  status: "pass" | "fail" | "not_measured" | "not_applicable";
  passed: boolean;
  observed: string;
  threshold: string;
  why: string;
}

export interface Decision {
  decision_id: string;
  release: { release_id: string; version: string; agent_config_id: string; bundle_hash: string };
  candidate_run_id: string;
  baseline_run_id: string | null;
  gates: GateResult[];
  gates_passed: boolean;
  status: "pending_approval" | "approved" | "rejected" | "rejected_by_gates";
  approval: { approver: string; role: string; decision: string; comment: string; at: string } | null;
  created_at: string;
  notes: string;
  regression_cases: string[];
  memo_md: string;
}

export interface Releases {
  production: { version: string; release_id: string } | null;
  decisions: Decision[];
  history: { action: string; version: string; actor: string; role: string; at: string; detail: string }[];
  regression_cases: string[];
}

export interface Distribution {
  p5: number;
  p50: number;
  p95: number;
  mean: number;
  prob_positive: number;
}

export interface Assumption {
  low: number;
  likely: number;
  high: number;
  source: string;
}

export interface Impact {
  draws: number;
  measured: {
    run_id: string;
    provenance: Provenance;
    automation_rate: number;
    escalation_rate: number;
    critical_error_rate: number;
    model_cost_per_ticket: number;
    categories: { category: string; n_trials: number; resolved: number; escalated: number; failed: number; failed_critical: number }[];
  };
  baseline: { automation_rate: number; run_id: string } | null;
  assumptions: Record<string, Assumption | Record<string, Assumption> | string>;
  human_cost_per_ticket: Distribution;
  agent_cost_per_ticket: Distribution;
  baseline_cost_per_ticket: Distribution | null;
  monthly_savings_vs_human: Distribution;
  monthly_savings_vs_baseline: Distribution | null;
  payback_months: Distribution;
  cost_per_automated_resolution: Distribution;
  report_md: string;
}

export interface Opportunity {
  id: string;
  title: string;
  problem: string;
  cluster_id: string;
  failure_class: string;
  scenario: string;
  verdict: string;
  evidence: string[];
  affected_share: number;
  affected_tickets_per_month: number;
  severity: "critical" | "major";
  cost_per_month: number;
  fix: string | null;
  fix_rate_lower: number;
  effort_weeks: number;
  effort_basis: string;
  confidence: number;
  expected_benefit_per_month: number;
  score: number;
  formula: string;
  validation_plan: string;
  decision: "build" | "not build";
  reason: string;
}

export interface MonitorResult {
  signal: string;
  description: string;
  statistic: "rate" | "p95" | "mean";
  direction: "up" | "down";
  severity: "page" | "ticket";
  why: string;
  status: "alert" | "ok" | "too few samples" | "not measured";
  reference: number;
  current: number;
  change: number;
  lo: number;
  hi: number;
  tolerance: number;
  n_reference: number;
  n_current: number;
  detected_after: number | null;
}

export interface SignalQuality {
  signal: string;
  flagged: number;
  true_positive: number;
  precision: number;
  recall: number;
}

export interface MonitorReport {
  tenant_id: string;
  reference_run: string;
  current_run: string;
  provenance: string;
  results: MonitorResult[];
  quality: {
    failures: number;
    trials: number;
    seen: number;
    silent: number;
    silent_rate: number;
    silent_rate_hi: number;
    review_sample: number | null;
    signals: SignalQuality[];
  };
  streams: Record<string, boolean[]>;
  report_md: string;
}

export type MonitorExport = Partial<Record<"during_incident" | "after_fix", MonitorReport>>;
