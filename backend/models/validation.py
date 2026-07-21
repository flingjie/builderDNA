"""Validation data models — cross-signal demand validation."""
from typing import Literal

from pydantic import BaseModel, Field


class ValidationSignal(BaseModel):
    """A single validation signal source with score and evidence."""
    source: str = ""                               # "demand" | "supply" | "adoption"
    score: float = 0.0                             # 0.0-1.0
    evidence: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Three-way cross-validation result attached to an OpportunityCard."""
    demand_score: float = 0.0                      # from Pain Mining issues
    supply_score: float = 0.0                      # from Vendor Tracking (are vendors investing?)
    adoption_score: float = 0.0                    # from dependency network (are others using it?)
    confidence: Literal["high", "medium", "low"] = "low"
    summary: str = ""                              # one-line interpretation in Chinese
