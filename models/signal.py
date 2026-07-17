"""Signal domain model — the unified input model for BuilderDNA."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Signal(BaseModel):
    """A unified signal representing one unit of builder activity.

    All data sources (GitHub, future Twitter/ArXiv/etc.) normalize to this model.
    """

    id: str = Field(description="Unique identifier, e.g. 'gh_repo_user_toolkit'")
    source: str = Field(description="Signal source, e.g. 'github'")
    type: str = Field(description="Signal type: 'repo', 'star', 'commit'")
    timestamp: datetime = Field(description="When the signal occurred")
    weight: float = Field(description="Preset weight from config, e.g. 5.0 for repo")
    actor: str = Field(description="The builder account being analyzed")
    target: str = Field(description="Entity identifier, e.g. repo full_name")
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured summary: language, topics, description, etc.",
    )
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Complete raw API response, never discard information",
    )


class SignalCluster(BaseModel):
    """L1 product: a quantitative cluster of related Signals.

    Internal-only — not exposed to output. Feeds into L2 Insight generation.
    """

    signals: list[str] = Field(description="Signal IDs participating in this cluster")
    topics: list[str] = Field(description="Union of all topics across signals")
    languages: list[str] = Field(description="Union of all languages across signals")
    total_weight: float = Field(description="Sum of signal weights")
    time_span_days: int = Field(description="Days between earliest and latest signal")
    growth_rate: float = Field(
        description="Recent 30-day weight / total weight. 0.0 to 1.0"
    )
