"""Schema-enforced output models for all sandbox commands.

Every command outputs a SandboxResult wrapper containing typed payload data.
Claude Code reads these JSON outputs — the schemas here are the contract.
"""
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class SandboxResult(BaseModel):
    """Every sandbox command wraps its output in this."""
    command: str
    domain: str
    computed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: dict[str, Any]
    stats: dict[str, Any] = Field(default_factory=dict)


# ── collect command output ──

class RepoSignal(BaseModel):
    """A single repo signal from the collect command."""
    full_name: str
    owner: str
    stars: int = 0
    forks: int = 0
    contributors: int = 0
    velocity: float = 0.0
    topics: list[str] = Field(default_factory=list)
    description: str = ""
    language: str = ""
    created_at: str = ""


class IssueSignal(BaseModel):
    """A single issue signal from the collect command."""
    repo: str
    issue_number: int
    title: str
    body: str = ""
    comments: int = 0
    participants: int = 0
    reactions: int = 0
    labels: list[str] = Field(default_factory=list)
    url: str = ""


class CollectPayload(BaseModel):
    """Payload for collect command output.

    repos and issues are flat, human-readable output contracts.
    signals is the normalized form (Signal JSON dicts) for direct
    consumption by downstream commands — no re-normalization needed.
    """
    repos: list[RepoSignal] = Field(default_factory=list)
    issues: list[IssueSignal] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list, description="Normalized Signal objects serialized as JSON dicts")


# ── trend command output ──

class RepoSummary(BaseModel):
    """Trend command's repo summary."""
    full_name: str
    stars: int
    stars_delta: int = 0
    forks: int
    contributors: int = 0
    velocity: float
    description: str = ""


class TopicTrend(BaseModel):
    """A single topic trend from the trend command."""
    topic: str
    stage: Literal["accelerating", "emerging", "mainstream", "declining"]
    confidence: float
    growth_velocity: float
    acceleration: float = 0.0
    evidence_count: int
    top_repos: list[RepoSummary] = Field(default_factory=list)


class TrendPayload(BaseModel):
    """Payload for trend command output."""
    trends: list[TopicTrend] = Field(default_factory=list)
    domain: str
    window_days: int


# ── pain command output ──

class IssueSummary(BaseModel):
    """Pain command's issue summary."""
    repo: str
    issue_number: int
    title: str
    pain_score: float


class PainCluster(BaseModel):
    """A single pain cluster from the pain command."""
    cluster_id: int
    title: str
    severity: float
    frequency: int
    affected_repos: list[str] = Field(default_factory=list)
    top_issues: list[IssueSummary] = Field(default_factory=list)


class PainPayload(BaseModel):
    """Payload for pain command output."""
    clusters: list[PainCluster] = Field(default_factory=list)
    issue_count: int = 0
    repos_analyzed: list[str] = Field(default_factory=list)


# ── opportunity command output ──

class OpportunityCard(BaseModel):
    """A single opportunity from the rule-engine scorer."""
    title: str
    demand_score: float
    competition_score: float
    gap_score: float
    signals: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    # Personalized fields added by alignment engine (User DNA integration)
    personalized_score: float | None = Field(default=None, description="gap_score × alignment_multiplier")
    alignment_reason: str = Field(default="", description="Why this opportunity matches user values")
    alignment_multiplier: float = Field(default=1.0, description="Raw multiplier from User DNA alignment")


class OpportunityPayload(BaseModel):
    """Payload for opportunity command output."""
    opportunities: list[OpportunityCard] = Field(default_factory=list)
