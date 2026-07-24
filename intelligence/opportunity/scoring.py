"""Rule-engine scoring for opportunity detection.

Deterministic formulas — no LLM calls:
  demand = f(trend_velocity, pain_severity, pain_frequency)
  competition = f(evidence_count, repo_maturity)
  gap_score = demand / competition
"""
import math


def compute_demand(trends: list[dict], pain_clusters: list[dict]) -> float:
    """Demand score from trend velocity + pain intensity."""
    avg_velocity = sum(t.get("growth_velocity", 0) for t in trends) / max(1, len(trends))
    avg_severity = sum(p.get("severity", 0) for p in pain_clusters) / max(1, len(pain_clusters))
    total_frequency = sum(p.get("frequency", 0) for p in pain_clusters)

    vel_score = min(10, avg_velocity / 10)
    pain_score = min(10, avg_severity * 2)
    freq_score = min(10, math.log(total_frequency + 1) * 3)

    return round((vel_score * 0.4 + pain_score * 0.4 + freq_score * 0.2), 1)


def compute_competition(trends: list[dict]) -> float:
    """Competition score: more evidence → more crowded."""
    total_evidence = sum(t.get("evidence_count", 0) for t in trends)
    total_repos = sum(len(t.get("top_repos", [])) for t in trends)

    raw = math.log(total_evidence + 1) * 1.5 + math.log(total_repos + 1)
    return round(min(10, max(1, raw)), 1)


def compute_gap(demand: float, competition: float) -> float:
    """Gap = demand / competition. Higher gap = better opportunity."""
    return round(demand / max(0.1, competition), 1)


def recommend_action(topic: str, gap: float) -> str:
    """Generate an action recommendation from gap score."""
    if gap > 2.0:
        return f"强烈推荐在 {topic} 方向创业或立项，缺口显著"
    elif gap > 1.5:
        return f"密切关注 {topic}，需求强但已有竞争，需差异化切入"
    elif gap > 1.0:
        return f"跟踪 {topic} 发展，等待更明确的市场信号"
    else:
        return f"暂不建议进入 {topic}，竞争饱和或需求不足"
