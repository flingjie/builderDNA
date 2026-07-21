/* Types matching backend models from backend/models/trend.py */

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
