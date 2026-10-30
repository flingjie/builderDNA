"""Rule-engine scoring for opportunity detection.

Deterministic formulas — no LLM calls.

Two-axis scoring (gap × market_size → 4 quadrants):
  - demand = f(trend_velocity, pain_severity, pain_frequency) with configurable weights
  - competition = f(evidence_count) — simplified, single log term (no collinear terms)
  - gap = demand / competition — relative underservice
  - market_size = f(total_stars) — absolute scale of activity
  - quadrant = classify(gap, market_size) → Build / Niche / Monitor / Avoid

Weights are passed as parameters (defaults match legacy 0.4/0.4/0.2) so they
can be driven by config.yaml or future bootstrap optimization.
"""
import math
from typing import Literal


# ── Demand ────────────────────────────────────────────────────────────

def compute_demand(
    trends: list[dict],
    pain_clusters: list[dict],
    weights: dict | None = None,
) -> float:
    """Demand score from trend velocity + pain intensity.

    Args:
        trends: List of trend dicts with growth_velocity.
        pain_clusters: List of pain cluster dicts with severity + frequency.
        weights: Optional dict with keys "velocity", "severity", "frequency".
                 Defaults to {"velocity": 0.4, "severity": 0.4, "frequency": 0.2}.

    Returns:
        Demand score (0-10), weighted sum of three signal channels.
    """
    if weights is None:
        weights = {"velocity": 0.4, "severity": 0.4, "frequency": 0.2}

    avg_velocity = sum(t.get("growth_velocity", 0) for t in trends) / max(1, len(trends))
    avg_severity = sum(p.get("severity", 0) for p in pain_clusters) / max(1, len(pain_clusters))
    total_frequency = sum(p.get("frequency", 0) for p in pain_clusters)

    vel_score = min(10, avg_velocity / 10)
    pain_score = min(10, avg_severity * 2)
    freq_score = min(10, math.log(total_frequency + 1) * 3)

    return round(
        vel_score * weights.get("velocity", 0.4)
        + pain_score * weights.get("severity", 0.4)
        + freq_score * weights.get("frequency", 0.2),
        1,
    )


# ── Competition ───────────────────────────────────────────────────────

def compute_competition(trends: list[dict]) -> float:
    """Competition score from evidence volume.

    Uses a single log(evidence+1) term — the old formula had a second
    log(repos+1) term that was collinear with evidence_count (more repos
    → more signals), so it was double-counting the same dimension.

    No floor — low competition is NOT masked. The gap formula and
    confidence scoring handle low-competition uncertainty explicitly.

    Returns:
        Competition score (0-10). Returns 0.0 when there are zero trends
        (the gap formula's max(0.1, competition) handles the division).
    """
    total_evidence = sum(t.get("evidence_count", 0) for t in trends)
    return round(min(10, math.log(total_evidence + 1) * 2.0), 1)


# ── Gap ───────────────────────────────────────────────────────────────

def compute_gap(demand: float, competition: float) -> float:
    """Gap = demand / competition. Higher gap = more underserved demand.

    The max(0.1, competition) floor prevents division by zero but a
    competition of 0.1 produces a suspiciously high gap — this is flagged
    by compute_confidence() as low-confidence.
    """
    return round(demand / max(0.1, competition), 1)


# ── Market Size ───────────────────────────────────────────────────────

def compute_market_size(trends: list[dict]) -> float:
    """Activity-strength hint from total star activity across all trends.

    Star count is an *activity* signal, NOT a measured market size. It is a
    coarse ordering hint only — it does not establish that a real, addressable
    market exists.

    Log-scaled to prevent a few mega-repos from dominating. Capped at 10.

    Returns:
        Activity-strength score (0-10). 0 when there are no trends.
    """
    total_stars = 0
    for t in trends:
        for r in t.get("top_repos", []):
            total_stars += r.get("stars", 0)

    if total_stars == 0:
        return 0.0
    return round(min(10, math.log(total_stars + 1) * 1.5), 1)


# ── Confidence ────────────────────────────────────────────────────────

def compute_confidence(
    demand: float,
    competition: float,
    total_evidence: int,
    total_pain_issues: int = 0,
) -> float:
    """Confidence in the opportunity assessment (0-1).

    Penalizes:
      - Very low competition (< 0.5): might mean "no market" not "untapped gold"
      - Very low evidence (< 3 signals): insufficient data
      - No pain data: demand is trend-only, may underestimate real need

    Starts at 1.0 and applies multiplicative penalties.
    """
    confidence = 1.0

    # Low-competition penalty: competition < 1.0 → uncertainty whether
    # this means "no one is building" or "no market exists"
    if competition < 1.0:
        confidence *= max(0.3, competition)  # 0.1 comp → 0.3; 0.5 comp → 0.5
    elif competition < 2.0:
        confidence *= 0.7 + 0.3 * (competition - 1.0)  # linear ramp 1.0→2.0

    # Low-evidence penalty: < 3 evidence items is very thin
    if total_evidence < 3:
        confidence *= 0.5 + (1/6) * total_evidence  # 0 evid → 0.5; 3 evid → 1.0
    elif total_evidence < 10:
        confidence *= 0.8 + (1/35) * (total_evidence - 3)  # gentle ramp 3→10

    # No-pain-data penalty: demand may be underestimated
    if total_pain_issues == 0:
        confidence *= 0.85

    return round(min(1.0, confidence), 2)


# ── Quadrant ──────────────────────────────────────────────────────────

def classify_quadrant(
    gap: float,
    market_size: float,
    gap_threshold: float = 1.5,
    market_threshold: float = 5.0,
) -> Literal["Build", "Niche", "Monitor", "Avoid"]:
    """Classify opportunity into a 2×2 gap × market_size quadrant.

    ┌──────────┬────────────────┬──────────────┐
    │          │ Big Market     │ Small Market │
    ├──────────┼────────────────┼──────────────┤
    │ High Gap │ Build          │ Niche        │
    │ Low Gap  │ Monitor        │ Avoid        │
    └──────────┴────────────────┴──────────────┘

    Args:
        gap: demand/competition ratio
        market_size: absolute market activity (0-10)
        gap_threshold: gap above this → "high gap" (Build or Niche)
        market_threshold: market above this → "big market" (Build or Monitor)
    """
    high_gap = gap > gap_threshold
    big_market = market_size > market_threshold

    if high_gap and big_market:
        return "Build"
    elif high_gap and not big_market:
        return "Niche"
    elif not high_gap and big_market:
        return "Monitor"
    else:
        return "Avoid"


# ── Action Recommendation ─────────────────────────────────────────────

def recommend_action(
    topic: str,
    gap: float,
    quadrant: str,
    market_size: float,
    confidence: float,
) -> str:
    """Generate a signal-ordering hint from quadrant + activity context.

    These strings are *hints to investigate further*, not conclusions. Demand is
    not proven, market size is not measured, and a "Build" quadrant does not mean
    "go build" — it means the activity/gap signals are strong enough to justify
    bounded validation.
    """
    confidence_note = ""
    if confidence < 0.5:
        confidence_note = "，但信号较弱，建议先验证需求"

    if quadrant == "Build":
        return (
            f"{topic} 的活跃度与缺口信号较强（gap={gap:.1f}），值得**进一步验证**需求；"
            f"尚未证明需求成立，先做有界验证而非立项{confidence_note}"
        )
    elif quadrant == "Niche":
        return (
            f"{topic} 的缺口信号较强但活跃度有限（activity={market_size:.1f}/10），"
            f"可作为利基方向观察并验证{confidence_note}"
        )
    elif quadrant == "Monitor":
        return (
            f"关注 {topic} 的后续证据——活跃度较高（activity={market_size:.1f}/10）"
            f"但竞争较充分（gap={gap:.1f}），暂不进入{confidence_note}"
        )
    else:  # Avoid
        return (
            f"{topic} 当前活跃度低（activity={market_size:.1f}/10）且竞争充分"
            f"（gap={gap:.1f}），暂不建议投入{confidence_note}"
        )


# ── Pain-to-trend matching ─────────────────────────────────────────────

def match_pains_to_trend(trend: dict, pain_clusters: list[dict]) -> list[dict]:
    """Return pain clusters whose affected repos overlap the trend's repos.

    A pain cluster relates to a trend only when they share at least one repo
    ``full_name``. No fallback: a trend with no overlapping repos gets no pain,
    so demand stays trend-only rather than inheriting the top-N unrelated pain
    clusters (which previously saturated every trend's demand).
    """
    trend_repos = {r.get("full_name", "") for r in trend.get("top_repos", [])}
    if not trend_repos:
        return []
    return [
        p for p in pain_clusters
        if any(repo in trend_repos for repo in p.get("affected_repos", []))
    ]
