"""Opportunity data models — merged from backend/models with CriticReview addition."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class ValidationSignal(BaseModel):
    """A single validation signal source with score and evidence."""
    source: str = ""
    score: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Three-way cross-validation result attached to an OpportunityCard."""
    demand_score: float = 0.0
    supply_score: float = 0.0
    adoption_score: float = 0.0
    confidence: Literal["high", "medium", "low"] = "low"
    summary: str = ""


class OpportunityEvidence(BaseModel):
    trends: list[str] = Field(default_factory=list)
    pain_clusters: list[str] = Field(default_factory=list)
    key_issues: list[str] = Field(default_factory=list)
    key_repos: list[str] = Field(default_factory=list)


class CriticReview(BaseModel):
    """Skeptical LLM review of an opportunity's risks and blind spots."""

    feasibility: int = 0
    market_size: int = 0
    timing: int = 0
    blind_spots: list[str] = Field(default_factory=list)
    counter_view: str = ""


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
    validation: ValidationResult | None = Field(default=None, description="Cross-signal demand validation")
    risk: Literal["low", "medium", "high"] = "medium"
    critic_review: CriticReview | None = Field(
        default=None, description="Independent skeptical LLM review"
    )
    related_repos: list[dict] = Field(
        default_factory=list,
        description="Related fast-growing GitHub repos for this opportunity",
    )


class OpportunitySnapshot(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    domain: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cards: list[OpportunityCard] = Field(default_factory=list)
