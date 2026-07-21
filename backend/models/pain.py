"""Pain data models for BuilderDNA 2.0 Phase 2."""
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class PainIssue(BaseModel):
    repo: str
    issue_number: int
    title: str
    body: str = ""                    # truncated to 500 chars
    comments: int = 0
    participants: int = 0
    pain_score: float = 0.0           # LLM rated 1-5 x log(comments+1) x log(participants+1)
    labels: list[str] = Field(default_factory=list)
    url: str = ""


class PainCluster(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    title: str                        # "Agent State Debugging"
    severity: float                   # aggregated pain score
    frequency: int                    # issue count in cluster
    description: str = ""             # LLM root cause summary
    evidence: list[PainIssue] = Field(default_factory=list)
    affected_repos: list[str] = Field(default_factory=list)


class PainSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    domain: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    clusters: list[PainCluster] = Field(default_factory=list)
    issue_count: int = 0
    repos_analyzed: list[str] = Field(default_factory=list)
