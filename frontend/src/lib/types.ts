export interface OpportunityEvidence {
  trends: string[];
  pain_clusters: string[];
  key_issues: string[];
  key_repos: string[];
}

export interface ValidationResult {
  demand_score: number;
  supply_score: number;
  adoption_score: number;
  confidence: "high" | "medium" | "low";
  summary: string;
}

export interface OpportunityCard {
  id: string;
  title: string;
  why_now: string;
  problem: string;
  evidence: OpportunityEvidence;
  existing_solutions: string[];
  gap: string;
  mvp: string;
  score: number;
  risk: "low" | "medium" | "high";
  validation?: ValidationResult | null;
}

export interface PainIssue {
  repo: string;
  issue_number: number;
  title: string;
  body: string;
  comments: number;
  participants: number;
  pain_score: number;
  labels: string[];
  url: string;
}

export interface PainCluster {
  id: string;
  title: string;
  severity: number;
  frequency: number;
  description: string;
  evidence: PainIssue[];
  affected_repos: string[];
}

export interface PainResponse {
  id: string;
  domain: string;
  clusters: PainCluster[];
  issue_count: number;
  repos_analyzed: string[];
}

export interface RepoTrend {
  full_name: string;
  stars: number;
  stars_delta: number;
  forks: number;
  contributors: number;
  contributor_growth: number;
  velocity: number;
  trend_score: number;
  days_since_first_release: number;
}

export type TrendStage = "emerging" | "accelerating" | "mainstream" | "declining";

export interface TopicTrend {
  topic: string;
  stage: TrendStage;
  confidence: number;
  growth_velocity: number;
  evidence_count: number;
  top_repos: RepoTrend[];
}

export interface RadarResponse {
  domain: string;
  snapshot_id: string;
  generated_at: string;
  window_days: number;
  rate_limit: { calls: number };
  topics: TopicTrend[];
}

export interface DiscoveredTheme {
  topic: string;
  description: string;
  repo_count: number;
  avg_stars: number;
  velocity: number;
  stage: "emerging" | "accelerating" | "stable" | "cooling";
  sample_repos: string[];
  is_new: boolean;
  suggested_as_topic: boolean;
}

export interface ExplorerResponse {
  domain: string;
  snapshot_id: string;
  generated_at: string;
  window_days: number;
  themes: DiscoveredTheme[];
}

export interface VendorDirection {
  topic: string;
  intensity: number;
  trend: "↑" | "→" | "↓";
}

export interface VendorSignal {
  type: string;
  repo: string;
  timestamp: string;
}

export interface VendorProfile {
  name: string;
  display_name: string;
  accounts: string[];
  tags: string[];
  comparison_group: string;
  active_directions: VendorDirection[];
  recent_signals: VendorSignal[];
  total_public_repos: number;
  total_stars: number;
}

export interface VendorDiff {
  dimension: string;
  domestic_summary: string;
  overseas_summary: string;
  common_patterns: string;
  domestic_vendors: string[];
  overseas_vendors: string[];
}
