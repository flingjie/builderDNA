"""Unified Signal model and aggregate views for BuilderDNA 2.0.

All upstream data (GitHub API responses) normalizes into Signal.
Aggregate views (TopicTrend, RepoTrend, VendorProfile) are computed
from Signal collections, not stored as independent models.
"""
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Signal(BaseModel):
    """Unified immutable event. All data sources normalize to this."""

    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    source: Literal["github"] = "github"
    type: Literal[
        "repo_created",      # new repository
        "star_growth",       # star increase event
        "issue_opened",      # issue created (contains body text)
        "issue_commented",   # issue discussion activity
        "release",           # version release
        "fork",              # fork event
        "discussion",        # discussion created
    ]
    actor: str                                # developer or org login
    target_repo: str                          # full_name e.g. "org/repo"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    velocity: float = 0.0                     # instantaneous growth rate
    impact: float = 0.0                       # influence weight (0-1)
    payload: dict[str, Any] = Field(default_factory=dict)  # raw snapshot


class AggregateRepoTrend(BaseModel):
    """Computed view: velocity and trend for a single repo."""
    full_name: str
    stars: int = 0
    stars_delta: int = 0
    forks: int = 0
    contributors: int = 0
    contributor_growth: float = 0.0
    velocity: float = 0.0
    trend_score: float = 0.0
    days_since_first_release: int = 0
    topics: list[str] = Field(default_factory=list)


class AggregateTopicTrend(BaseModel):
    """Computed view: aggregated trend for a topic."""
    topic: str
    stage: Literal["emerging", "accelerating", "mainstream", "declining"] = "emerging"
    confidence: float = 0.0
    growth_velocity: float = 0.0
    evidence_count: int = 0
    top_repos: list[AggregateRepoTrend] = Field(default_factory=list)

    @classmethod
    def from_signals(cls, signals: list[Signal]) -> list["AggregateTopicTrend"]:
        """Build topic trends from a flat list of signals."""
        topic_signals: dict[str, list[Signal]] = {}
        for s in signals:
            for topic in s.payload.get("topics", []):
                topic_signals.setdefault(topic, []).append(s)

        results = []
        for topic, sigs in topic_signals.items():
            velocities = [s.velocity for s in sigs if s.velocity > 0]
            avg_vel = sum(velocities) / len(velocities) if velocities else 0.0
            confidence = min(1.0, len(sigs) / 10.0)
            results.append(cls(
                topic=topic,
                confidence=round(confidence, 2),
                growth_velocity=round(avg_vel, 2),
                evidence_count=len(sigs),
            ))
        results.sort(key=lambda t: t.growth_velocity, reverse=True)
        return results


class AggregateVendorProfile(BaseModel):
    """Computed view: vendor activity abstracted from signals."""
    name: str
    display_name: str = ""
    tags: list[str] = Field(default_factory=list)
    comparison_group: str = ""
    active_topics: list[str] = Field(default_factory=list)
    total_repos: int = 0
    total_stars: int = 0
    recent_signal_count: int = 0
