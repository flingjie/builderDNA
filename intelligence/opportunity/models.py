"""Opportunity data models — merged from backend/models with CriticReview addition."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from backend.models.opportunity import (
    OpportunityCard as _OpportunityCard,
    OpportunityEvidence as _OpportunityEvidence,
    OpportunitySnapshot as _OpportunitySnapshot,
)
from backend.models.opportunity import ValidationResult
from pydantic import BaseModel, Field


# Re-export existing models for convenience
OpportunityEvidence = _OpportunityEvidence
OpportunitySnapshot = _OpportunitySnapshot


class CriticReview(BaseModel):
    """Skeptical LLM review of an opportunity's risks and blind spots."""

    feasibility: int = 0
    market_size: int = 0
    timing: int = 0
    blind_spots: list[str] = Field(default_factory=list)
    counter_view: str = ""


class OpportunityCard(_OpportunityCard):
    """Extended OpportunityCard with validation and critic review fields."""

    validation: ValidationResult | None = Field(
        default=None, description="Cross-signal demand validation"
    )
    critic_review: CriticReview | None = Field(
        default=None, description="Independent skeptical LLM review"
    )
