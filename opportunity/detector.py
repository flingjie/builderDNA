"""Opportunity Detector — LLM-powered opportunity discovery."""

from datetime import datetime, timezone
from typing import Any

from models.insight import Insight
from models.opportunity import Opportunity
from llm.client import LLMClient


def build_detection_prompt(insights: list[Insight]) -> str:
    """Build the prompt for opportunity detection."""
    insight_lines = []
    for i, ins in enumerate(insights):
        insight_lines.append(
            f"Insight ID: {ins.id}\n  Tags: {ins.tags}\n  Summary: {ins.summary}\n"
            f"  Strength: {ins.strength}\n  Trend: {ins.trend}\n"
            f"  Signal Count: {ins.signal_count}\n  Evidence: {ins.evidence}"
        )
    return f"""Based on the following builder insights, identify product/tool opportunities.

Insights:
{''.join(insight_lines)}

Return a JSON object with an 'opportunities' array. For each:
- id: "op_NNN" (sequential)
- title: concise opportunity name
- pain_point: the core problem being solved
- demand_score: 1-5 (how much demand exists)
- competition_score: 1-5 (how much existing competition; lower = less competition)
- recommended_action: concrete next step suggestion
- source_insights: array of the EXACT Insight IDs (copy from "Insight ID:" above) that support this

Respond with ONLY valid JSON, no markdown fences."""


def build_fallback_opportunities(insights: list[Insight]) -> list[Opportunity]:
    """Build basic opportunities when LLM is unavailable."""
    opportunities: list[Opportunity] = []
    for i, ins in enumerate(insights):
        opportunities.append(Opportunity(
            id=f"op_fallback_{i+1}",
            title=f"Tooling for {', '.join(ins.tags[:3])}",
            pain_point=f"Builders investing in {', '.join(ins.tags[:3])} may need better tooling",
            demand_score=3.0, competition_score=3.0, gap_score=1.0,
            recommended_action="Explore further", source_insights=[ins.id],
        ))
    return opportunities


def detect(insights: list[Insight], llm: LLMClient) -> list[Opportunity]:
    """Detect opportunities from insights using LLM reasoning."""
    if not insights:
        return []
    try:
        prompt = build_detection_prompt(insights)
        response = llm.complete(prompt, response_format=dict)
        raw_ops = response.get("opportunities", [])
    except Exception:
        return build_fallback_opportunities(insights)

    opportunities: list[Opportunity] = []
    for raw in raw_ops:
        demand = max(1.0, min(5.0, raw.get("demand_score", 3.0)))
        competition = max(1.0, min(5.0, raw.get("competition_score", 3.0)))
        opportunities.append(Opportunity(
            id=raw.get("id", f"op_{len(opportunities)+1}"),
            title=raw.get("title", ""), pain_point=raw.get("pain_point", ""),
            demand_score=demand, competition_score=competition,
            gap_score=demand / competition if competition > 0 else demand,
            recommended_action=raw.get("recommended_action", ""),
            source_insights=raw.get("source_insights", []),
            created_at=datetime.now(timezone.utc),
        ))
    return opportunities
