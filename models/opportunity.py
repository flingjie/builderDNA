"""Opportunity domain model — the SSOT output of BuilderDNA."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Opportunity(BaseModel):
    """A product/tool opportunity derived from builder insights.

    Opportunity is the single source of truth. CLI, Markdown, JSON, and
    future dashboards are all just different Views of this model.
    """

    id: str = Field(description="Unique opportunity ID, e.g. 'opp_001'")
    title: str = Field(description="Opportunity direction, e.g. 'Agent Replay Visualizer'")
    pain_point: str = Field(description="Core pain point this opportunity addresses")
    demand_score: float = Field(description="Demand heat 1-5", ge=1.0, le=5.0)
    competition_score: float = Field(
        description="Competition intensity 1-5 (lower = less competition)", ge=1.0, le=5.0
    )
    gap_score: float = Field(
        description="demand / competition — higher means more worth pursuing"
    )
    recommended_action: str = Field(description="Suggested next step")
    source_insights: list[str] = Field(
        description="Insight IDs that support this opportunity"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this opportunity was generated",
    )
