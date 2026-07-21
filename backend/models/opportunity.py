"""Opportunity data models for BuilderDNA 2.0 Phase 3."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class OpportunityEvidence(BaseModel):
    trends: list[str] = Field(default_factory=list)
    pain_clusters: list[str] = Field(default_factory=list)
    key_issues: list[str] = Field(default_factory=list)
    key_repos: list[str] = Field(default_factory=list)


class OpportunityCard(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    title: str
    why_now: str = ""
    problem: str = ""
    evidence: OpportunityEvidence = Field(default_factory=OpportunityEvidence)
    existing_solutions: list[str] = Field(default_factory=list)
    gap: str = ""
    mvp: str = ""
    score: float = 0.0
    risk: Literal["low", "medium", "high"] = "medium"


class OpportunitySnapshot(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    domain: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cards: list[OpportunityCard] = Field(default_factory=list)
