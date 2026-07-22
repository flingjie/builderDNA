"""Opportunity Generator — generates opportunity cards from trend + pain signals.

Phase 3: Takes TrendSnapshot + PainSnapshot, uses LLM CoT to identify
3-5 concrete product/business opportunities, outputs OpportunityCard list.
"""
import asyncio
import json
from typing import cast
from uuid import uuid4

from intelligence.trend.models import TrendSnapshot, TopicTrend, RepoTrend
from intelligence.pain.models import PainSnapshot, PainCluster, PainIssue
from intelligence.opportunity.models import OpportunityCard, OpportunityEvidence, OpportunitySnapshot


def format_trends_for_llm(snapshot: TrendSnapshot) -> str:
    """Format trend snapshot for LLM consumption.

    Format: "Topic: {name}, Stage: {stage}, Velocity: {velocity}, Top Repos: {top 3 repos}"
    Max 5 topics.

    Args:
        snapshot: TrendSnapshot with topics and repo trends.

    Returns:
        Formatted string for LLM prompt.
    """
    lines = []
    topics = snapshot.topics[:5]

    for topic in topics:
        topic_name = topic.topic
        stage = topic.stage
        velocity = topic.growth_velocity
        top_repos = topic.top_repos[:3]

        repo_names = ", ".join(r.full_name for r in top_repos) if top_repos else "none"

        lines.append(
            f"Topic: {topic_name}, Stage: {stage}, Velocity: {velocity:.2f}, Top Repos: {repo_names}"
        )

    return "\n".join(lines)


def format_pains_for_llm(snapshot: PainSnapshot) -> str:
    """Format pain snapshot for LLM consumption.

    Format: "Pain: {title}, Severity: {severity}, Root Cause: {description}, Affected: {top 3 repos}"
    Max 5 pain clusters.

    Args:
        snapshot: PainSnapshot with clusters.

    Returns:
        Formatted string for LLM prompt.
    """
    lines = []
    clusters = snapshot.clusters[:5]

    for cluster in clusters:
        title = cluster.title
        severity = cluster.severity
        description = cluster.description or ""
        affected_repos = cluster.affected_repos[:3]

        repo_names = ", ".join(affected_repos) if affected_repos else "none"

        lines.append(
            f"Pain: {title}, Severity: {severity:.2f}, Root Cause: {description}, Affected: {repo_names}"
        )

    return "\n".join(lines)


async def generate_opportunities(
    trend_snapshot: TrendSnapshot, pain_snapshot: PainSnapshot, llm
) -> list[OpportunityCard]:
    """Generate opportunity cards using LLM chain-of-thought reasoning.

    Args:
        trend_snapshot: TrendSnapshot from Phase 1 radar.
        pain_snapshot: PainSnapshot from Phase 2 pain mining.
        llm: LLM client with complete() method.

    Returns:
        List of OpportunityCard objects, or empty list on LLM error.
    """
    formatted_trends = format_trends_for_llm(trend_snapshot)
    formatted_pains = format_pains_for_llm(pain_snapshot)

    prompt = f"""You are a top-tier AI venture strategist. Identify 3-5 concrete product/business opportunities from these technology signals.

TREND SIGNALS (what's accelerating on GitHub):
{formatted_trends}

PAIN SIGNALS (what developers are struggling with):
{formatted_pains}

For each opportunity, reason step by step:
1. WHY NOW: Why has this problem become urgent now?
2. WHY NOT EXISTING: Why can't current tools/solutions address this?
3. MVP: What's the minimum viable product (2-3 bullet points)?
4. SCORE (1-10, be strict) and RISK (low/medium/high)

Return ONLY valid JSON:
{{"opportunities": [{{"title": "...", "why_now": "...", "problem": "...", "evidence": {{"trends": ["..."], "pain_clusters": ["..."]}}, "existing_solutions": ["..."], "gap": "...", "mvp": "...", "score": 8.0, "risk": "medium"}}, ...]}}
"""

    try:
        response = llm.complete(prompt, response_format=dict)
    except Exception:
        return []

    opportunities_data = response.get("opportunities", [])
    if not isinstance(opportunities_data, list):
        return []

    result = []
    for opp_data in opportunities_data:
        if not isinstance(opp_data, dict):
            continue

        evidence_data = opp_data.get("evidence", {})
        if isinstance(evidence_data, dict):
            trends = evidence_data.get("trends", [])
            pain_clusters = evidence_data.get("pain_clusters", [])
            key_issues = evidence_data.get("key_issues", [])
            key_repos = evidence_data.get("key_repos", [])
        else:
            trends = []
            pain_clusters = []
            key_issues = []
            key_repos = []

        card = OpportunityCard(
            id=opp_data.get("id") or uuid4().hex[:8],
            title=opp_data.get("title", "")[:100],
            why_now=opp_data.get("why_now", "")[:500],
            problem=opp_data.get("problem", "")[:500],
            evidence=OpportunityEvidence(
                trends=[str(t) for t in trends],
                pain_clusters=[str(p) for p in pain_clusters],
                key_issues=[str(k) for k in key_issues[:10]],
                key_repos=[str(k) for k in key_repos[:10]],
            ),
            existing_solutions=[str(s) for s in opp_data.get("existing_solutions", [])[:10]],
            gap=opp_data.get("gap", "")[:500],
            mvp=opp_data.get("mvp", "")[:500],
            score=float(opp_data.get("score", 0.0)),
            risk=cast(str, opp_data.get("risk", "medium")),
        )
        result.append(card)

    return result


async def run_opportunity_engine(
    trend_snapshot: TrendSnapshot,
    pain_snapshot: PainSnapshot,
    llm,
    store,
) -> OpportunitySnapshot:
    """Run the full opportunity engine pipeline.

    Generate cards from trend + pain signals, build snapshot, save to store.

    Args:
        trend_snapshot: TrendSnapshot from Phase 1 radar.
        pain_snapshot: PainSnapshot from Phase 2 pain mining.
        llm: LLM client with complete() method.
        store: OpportunityStore for persistence.

    Returns:
        OpportunitySnapshot with generated cards.
    """
    cards = await generate_opportunities(trend_snapshot, pain_snapshot, llm)

    from intelligence.opportunity.validator import validate_opportunity
    for card in cards:
        try:
            card.validation = validate_opportunity(card, trend_snapshot, pain_snapshot)
        except Exception:
            card.validation = None

    snapshot = OpportunitySnapshot(
        domain=trend_snapshot.domain,
        cards=cards,
    )

    store.save(snapshot)

    return snapshot
