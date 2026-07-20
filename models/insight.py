"""Insight domain model — semantic understanding derived from Signal clusters."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Insight(BaseModel):
    """A semantic insight distilled from one or more SignalClusters.

    L2 (LLM) is responsible for generating the summary and tags.
    If LLM is unavailable, a rule-based fallback produces a minimal Insight.
    """

    id: str = Field(description="Unique insight ID, e.g. 'insight_001'")
    tags: list[str] = Field(description="Technology tags, e.g. ['MCP', 'Agent']")
    summary: str = Field(description="One-sentence description of the insight")
    strength: float = Field(description="Weighted sum of supporting signals")
    trend: str = Field(description="'rising' | 'stable' | 'fading'")
    signal_count: int = Field(description="Number of signals supporting this insight")
    evidence: list[str] = Field(
        default_factory=list,
        description="Key evidence: repo names, commit message excerpts",
    )
    source_cluster_id: str = Field(
        default="",
        description="ID of the SignalCluster that generated this insight",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this insight was generated",
    )
