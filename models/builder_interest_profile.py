"""BuilderInterestProfile — the converged user-interest model.

Replaces the generalized User DNA (4 value dimensions) as the *public* user
contract. The profile expresses only what shapes learning / validation / build
prioritization:

    domains                 — technical domains the user wants to learn or build in
    technical_adjacencies   — adjacent technologies worth watching
    problem_preferences     — the kinds of problems the user wants to solve
    build_constraints       — team size, complexity, stage, and other build limits
    learning_goals          — build / explore / deepen / ship
    risk_tolerance          — low / medium / high

Every list item carries provenance (``source``, ``confirmed``, ``updated_at``) so
an unconfirmed inference is never persisted as fact. The profile only reorders
and reweights recommendations — it never changes evidence strength, trend stage,
pain severity, hypothesis maturity, or Build gates.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InterestItem(BaseModel):
    """One interest entry with provenance so inferences are never silent facts."""

    value: str = Field(description="The interest keyword, domain, goal, or constraint")
    source: Literal["user_confirmed", "inferred"] = Field(
        default="inferred",
        description="Where this item came from: an explicit user confirmation, or a model inference",
    )
    confirmed: bool = Field(
        default=False,
        description="Whether the user has confirmed this item. Unconfirmed items are provisional.",
    )
    updated_at: str = Field(
        default_factory=_now_iso,
        description="ISO 8601 timestamp of the last update to this item",
    )


class BuilderInterestProfile(BaseModel):
    """The converged interest profile. Only affects ranking, never facts or gates."""

    version: int = Field(default=1)
    extracted_at: str = Field(default_factory=_now_iso)

    domains: list[InterestItem] = Field(default_factory=list)
    technical_adjacencies: list[InterestItem] = Field(default_factory=list)
    problem_preferences: list[InterestItem] = Field(default_factory=list)
    build_constraints: list[InterestItem] = Field(default_factory=list)
    learning_goals: list[InterestItem] = Field(default_factory=list)
    risk_tolerance: Literal["low", "medium", "high"] = Field(default="medium")

    migrated_from: str = Field(
        default="",
        description="Path of the legacy user_dna.json this profile was migrated from (empty if authored directly)",
    )


# ── Loading ───────────────────────────────────────────────────────────────

def load_profile(path: str = "state/builder_interest_profile.json") -> BuilderInterestProfile | None:
    """Load the profile from state. Returns None when missing, empty, or corrupt."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # An empty template (no domains and no other fields) is "no profile yet".
        if not any(data.get(k) for k in (
            "domains", "technical_adjacencies", "problem_preferences",
            "build_constraints", "learning_goals",
        )):
            return None
        return BuilderInterestProfile(**data)
    except Exception:
        return None


