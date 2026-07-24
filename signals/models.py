"""Unified Signal model — normalization target for all upstream data sources.

All upstream data (GitHub API responses) normalizes into Signal.
Aggregate views are defined in models/payload.py as the canonical output contract.
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
        "repo_created",       # new repository
        "star_growth",        # star increase event
        "issue_opened",       # issue created (contains body text)
        "issue_commented",    # issue discussion activity
        "release",            # version release
        "fork",               # fork event
        "discussion",         # discussion created
    ]
    actor: str                                # developer or org login
    target_repo: str                          # full_name e.g. "org/repo"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    velocity: float = 0.0                     # instantaneous growth rate (stars/day)
    impact: float = 0.0                       # influence weight (0-1)
    payload: dict[str, Any] = Field(default_factory=dict)  # raw snapshot
