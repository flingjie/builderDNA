"""L2 Insight Classifier — LLM-powered semantic understanding."""

from datetime import datetime, timezone
from typing import Any

from models.insight import Insight
from models.signal import SignalCluster
from llm.client import LLMClient


def build_classification_prompt(
    clusters: list[SignalCluster], actor: str,
    previous_insights: list[dict[str, Any]] | None = None,
) -> str:
    """Build the prompt for L2 classification."""
    cluster_lines = []
    for i, c in enumerate(clusters):
        cluster_lines.append(
            f"Cluster {i+1}:\n  Topics: {', '.join(c.topics)}\n"
            f"  Languages: {', '.join(c.languages)}\n  Total Weight: {c.total_weight}\n"
            f"  Time Span: {c.time_span_days} days\n  Growth Rate: {c.growth_rate}\n"
            f"  Signals: {len(c.signals)}"
        )

    previous_text = ""
    if previous_insights:
        previous_text = "\nPrevious analysis insights:\n"
        for pi in previous_insights:
            previous_text += (
                f"- Tags: {pi['tags']}, Summary: {pi['summary']}, "
                f"Trend: {pi['trend']}, Strength: {pi['strength']}\n"
            )
        previous_text += (
            "\nCompare current clusters with previous insights. "
            "Update trend to 'rising', 'stable', or 'fading' based on changes.\n"
        )

    return f"""Analyze the following technical activity data for builder '{actor}'.

{previous_text}
Quantitative signal clusters:
{''.join(cluster_lines)}

Return a JSON object with an 'insights' array. For each cluster, generate one insight:
- id: "in_NNN" (sequential)
- tags: array of technology labels (lowercase, e.g. "llm", "agent", "python")
- summary: one sentence describing the builder's focus in this area
- strength: the cluster's total_weight
- trend: "rising" if growth_rate > 0.5, "stable" if 0.2-0.5, "fading" if < 0.2
- signal_count: number of signals
- evidence: array of key references (repo names, etc.)

Respond with ONLY valid JSON, no markdown fences."""


def build_fallback_insights(clusters: list[SignalCluster], actor: str) -> list[Insight]:
    """Generate rule-based insights when LLM is unavailable."""
    insights: list[Insight] = []
    for i, c in enumerate(clusters):
        topic_str = ", ".join(c.topics[:5]) if c.topics else "general development"
        lang_str = f" (using {', '.join(c.languages)})" if c.languages else ""
        summary = f"{actor} focuses on {topic_str}{lang_str}"
        trend = "stable"
        if c.growth_rate > 0.5:
            trend = "rising"
        elif c.growth_rate < 0.2:
            trend = "fading"
        insights.append(Insight(
            id=f"in_fallback_{i+1}", tags=c.topics[:5], summary=summary,
            strength=c.total_weight, trend=trend,
            signal_count=len(c.signals), evidence=[],
        ))
    return insights


def classify(
    clusters: list[SignalCluster], llm: LLMClient, actor: str,
    previous_insights: list[dict[str, Any]] | None = None,
) -> list[Insight]:
    """Classify signal clusters into semantic insights using LLM."""
    if not clusters:
        return []
    try:
        prompt = build_classification_prompt(clusters, actor, previous_insights)
        response = llm.complete(prompt, response_format=dict)
        raw_insights = response.get("insights", [])
    except Exception:
        return build_fallback_insights(clusters, actor)

    insights: list[Insight] = []
    for raw in raw_insights:
        insights.append(Insight(
            id=raw.get("id", f"in_{len(insights)+1}"),
            tags=raw.get("tags", []), summary=raw.get("summary", ""),
            strength=raw.get("strength", 0.0), trend=raw.get("trend", "stable"),
            signal_count=raw.get("signal_count", 0),
            evidence=raw.get("evidence", []),
            created_at=datetime.now(timezone.utc),
        ))
    return insights
