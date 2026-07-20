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
        previous_text = "\n前次分析洞察:\n"
        for pi in previous_insights:
            previous_text += (
                f"- 标签: {pi['tags']}, 摘要: {pi['summary']}, "
                f"趋势: {pi['trend']}, 强度: {pi['strength']}\n"
            )
        previous_text += (
            "\n请对比当前聚类与历史洞察，"
            "根据变化将趋势更新为 'rising'（上升）、'stable'（稳定）或 'fading'（衰退）。\n"
        )

    return f"""Analyze the following technical activity data for builder '{actor}'.

{previous_text}
Quantitative signal clusters:
{''.join(cluster_lines)}

Return a JSON object with an 'insights' array. For each cluster, generate one insight:
- id: "in_NNN" (sequential)
- tags: array of technology labels (use lowercase English keywords, e.g. "llm", "agent", "python", "kubernetes")
- summary: one sentence in CHINESE describing the builder's focus and expertise in this area (use Chinese, be specific and vivid)
- strength: the cluster's total_weight
- trend: "rising" if growth_rate > 0.5, "stable" if 0.2-0.5, "fading" if < 0.2
- signal_count: number of signals
- evidence: array of key references in CHINESE context (repo names can stay English)

IMPORTANT: summary and evidence MUST be written in Chinese.
Respond with ONLY valid JSON, no markdown fences."""


def build_fallback_insights(clusters: list[SignalCluster], actor: str) -> list[Insight]:
    """Generate rule-based insights when LLM is unavailable."""
    insights: list[Insight] = []
    for i, c in enumerate(clusters):
        topic_str = ", ".join(c.topics[:5]) if c.topics else "通用开发"
        lang_str = f"（使用 {', '.join(c.languages)}）" if c.languages else ""
        summary = f"{actor} 重点关注 {topic_str} 领域{lang_str}"
        trend = "stable"
        if c.growth_rate > 0.5:
            trend = "rising"
        elif c.growth_rate < 0.2:
            trend = "fading"
        insights.append(Insight(
            id=f"in_fallback_{i+1}", tags=c.topics[:5], summary=summary,
            strength=c.total_weight, trend=trend,
            signal_count=len(c.signals), evidence=[],
            source_cluster_id=c.id,
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
    for i, raw in enumerate(raw_insights):
        cluster_id = clusters[i].id if i < len(clusters) else ""
        insights.append(Insight(
            id=raw.get("id", f"in_{len(insights)+1}"),
            tags=raw.get("tags", []), summary=raw.get("summary", ""),
            strength=raw.get("strength", 0.0), trend=raw.get("trend", "stable"),
            signal_count=raw.get("signal_count", 0),
            evidence=raw.get("evidence", []),
            source_cluster_id=cluster_id,
            created_at=datetime.now(timezone.utc),
        ))
    return insights
