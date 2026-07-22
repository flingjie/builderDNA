"""Demand Validation engine — cross-validates opportunities with 3 signal sources."""
from backend.models.opportunity import ValidationResult
from backend.models.opportunity import OpportunityCard
from backend.models.trend import TrendSnapshot
from backend.models.pain import PainSnapshot


def validate_opportunity(
    card: OpportunityCard,
    trend_snapshot: TrendSnapshot | None = None,
    pain_snapshot: PainSnapshot | None = None,
) -> ValidationResult:
    """Cross-validate a single OpportunityCard against demand, supply, and adoption signals.

    Demand: pain cluster relevance + issue severity
    Supply: topic trend velocity (are repos growing in this area?)
    Adoption: downstream dependent activity (simplified heuristic — count of evidence repos)

    Returns:
        ValidationResult with scores and confidence level.
    """
    demand_score = 0.0
    supply_score = 0.0
    adoption_score = 0.0

    # Demand signal: pain clusters mentioned in evidence
    pain_clusters_mentioned = card.evidence.pain_clusters if card.evidence else []
    if pain_snapshot and pain_clusters_mentioned:
        matching_clusters = [
            c for c in pain_snapshot.clusters
            if c.title in pain_clusters_mentioned
        ]
        if matching_clusters:
            # Average severity normalized to 0-1 (severity is 0-5 scale in pain mining)
            avg_severity = sum(c.severity for c in matching_clusters) / len(matching_clusters)
            demand_score = min(1.0, avg_severity / 5.0)

    # Supply signal: related topic trend velocity
    topics_mentioned = card.evidence.trends if card.evidence else []
    if trend_snapshot and topics_mentioned:
        matching_topics = [
            t for t in trend_snapshot.topics
            if t.topic in topics_mentioned
        ]
        if matching_topics:
            avg_velocity = sum(t.growth_velocity for t in matching_topics) / len(matching_topics)
            supply_score = min(1.0, avg_velocity / 15.0)  # normalize: 15 velocity → 1.0

    # Adoption signal: number of key repos mentioned as evidence
    key_repos = card.evidence.key_repos if card.evidence else []
    adoption_score = min(1.0, len(key_repos) / 10.0)  # 10+ repos → 1.0

    # Confidence: all three strong → high, 2 strong → medium, else low
    strong_count = sum(1 for s in [demand_score, supply_score, adoption_score] if s >= 0.6)
    if strong_count >= 3:
        confidence = "high"
    elif strong_count >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    # Generate summary
    parts = []
    if demand_score >= 0.6:
        parts.append("需求信号强")
    elif demand_score > 0:
        parts.append("需求信号中等")

    if supply_score >= 0.6:
        parts.append("厂商积极投入")
    elif supply_score > 0:
        parts.append("厂商投入中等")

    if adoption_score >= 0.6:
        parts.append("生态采纳活跃")
    elif adoption_score > 0:
        parts.append("生态采纳待观察")

    summary = "，".join(parts) if parts else "信号不足"

    return ValidationResult(
        demand_score=round(demand_score, 2),
        supply_score=round(supply_score, 2),
        adoption_score=round(adoption_score, 2),
        confidence=confidence,
        summary=summary,
    )
