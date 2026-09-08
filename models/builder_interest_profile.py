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

The legacy :class:`models.user_dna_schema.UserDNA` (values/beliefs/criteria) is
retained as the *internal* scoring representation consumed by the alignment
engine. :meth:`BuilderInterestProfile.to_values` provides the lossy bridge from
this public contract to that internal representation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from models.user_dna_schema import Values, ValueDimension


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

    # ── Lossy bridge to the internal scoring representation ──────────────────

    @staticmethod
    def _items(values: list[InterestItem]) -> list[str]:
        return [i.value for i in values]

    def to_values(self) -> Values:
        """Map this profile to the internal 4-dimension ``Values`` the alignment
        engine scores. Keyword-based and lossy — the profile is the source of
        truth; ``Values`` is only the scoring signal derived from it.
        """
        domain_out = {
            "agent": "infrastructure", "infrastructure": "infrastructure",
            "devtools": "devtools", "developer": "devtools", "tooling": "devtools",
            "consumer": "end_user", "b2c": "end_user", "end-user": "end_user",
            "knowledge": "knowledge", "education": "knowledge", "tutorial": "knowledge",
        }
        goal_act = {
            "build": "creation", "create": "creation", "prototype": "creation",
            "explore": "exploration", "learn": "exploration", "research": "exploration",
            "deepen": "optimization", "optimize": "optimization", "improve": "optimization",
            "ship": "execution", "launch": "execution", "productionize": "execution",
        }
        constraint_env = {
            "solo": "autonomy", "independent": "autonomy", "autonomy": "autonomy",
            "collaborative": "collaboration", "team": "collaboration", "oss": "collaboration",
            "stable": "stability", "mature": "stability",
            "competitive": "competition", "fast-moving": "competition",
        }
        pref_reward = {
            "growth": "growth", "learning": "growth",
            "mastery": "mastery", "depth": "mastery", "craft": "mastery",
            "recognition": "recognition", "visibility": "recognition",
            "revenue": "wealth", "commercial": "wealth", "wealth": "wealth",
        }

        def _dedup(seq: list[str], fallback: list[str]) -> list[str]:
            out: list[str] = []
            for x in seq:
                if x not in out:
                    out.append(x)
            return out or fallback

        output_ranking = _dedup(
            [domain_out.get(d.lower(), "devtools") for d in self._items(self.domains)],
            ["devtools", "infrastructure", "end_user", "knowledge"],
        )
        activity_ranking = _dedup(
            [goal_act.get(g.lower(), "exploration") for g in self._items(self.learning_goals)],
            ["exploration", "creation", "optimization", "execution"],
        )
        env_ranking = _dedup(
            [constraint_env.get(c.lower(), "autonomy") for c in self._items(self.build_constraints)],
            ["autonomy", "collaboration", "stability", "competition"],
        )
        reward_ranking = _dedup(
            [pref_reward.get(p.lower(), "growth") for p in self._items(self.problem_preferences)],
            ["growth", "mastery", "recognition", "wealth"],
        )

        def _scores(ranking: list[str]) -> dict[str, float]:
            # Rank 0 gets the highest weight, decaying down the list.
            n = len(ranking)
            return {v: max(1.0, 10.0 - (i * 9.0 / max(1, n - 1))) for i, v in enumerate(ranking)}

        return Values(
            environment=ValueDimension(ranking=env_ranking, scores=_scores(env_ranking)),
            activity=ValueDimension(ranking=activity_ranking, scores=_scores(activity_ranking)),
            output=ValueDimension(ranking=output_ranking, scores=_scores(output_ranking)),
            reward=ValueDimension(ranking=reward_ranking, scores=_scores(reward_ranking)),
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


# ── One-time migration from the legacy user_dna.json ──────────────────────

_OUTPUT_TO_DOMAIN = {
    "devtools": "devtools", "infrastructure": "agent", "end_user": "consumer", "knowledge": "knowledge",
}
_ACTIVITY_TO_GOAL = {
    "creation": "build", "exploration": "explore", "optimization": "deepen", "execution": "ship",
}
_ENV_TO_CONSTRAINT = {
    "autonomy": "solo", "collaboration": "collaborative", "stability": "stable", "competition": "competitive",
}
_REWARD_TO_PREF = {
    "growth": "growth", "mastery": "mastery", "recognition": "recognition", "wealth": "revenue",
}


def _migrate_items(ranking: list[str], mapping: dict[str, str], *, confirmed: bool) -> list[InterestItem]:
    source: Literal["user_confirmed", "inferred"] = "user_confirmed" if confirmed else "inferred"
    return [
        InterestItem(value=mapping.get(k, k), source=source, confirmed=confirmed)
        for k in ranking
        if k
    ]


def migrate_user_dna(
    old_path: str = "state/user_dna.json",
    new_path: str = "state/builder_interest_profile.json",
    *,
    backup: bool = True,
) -> BuilderInterestProfile:
    """One-time migration from the legacy ``user_dna.json`` to the new profile.

    Maps the legacy 4-dimension value model to the 6-field interest profile,
    backs up the old file (``.bak``) before writing, and writes the new file.
    Idempotent: if the new file already exists it is returned unchanged and the
    old file is left untouched.
    """
    new = Path(new_path)
    if new.exists():
        existing = load_profile(new_path)
        if existing is not None:
            return existing

    old = Path(old_path)
    if not old.exists():
        # Nothing to migrate — write an empty profile so the file exists.
        profile = BuilderInterestProfile()
        new.parent.mkdir(parents=True, exist_ok=True)
        new.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        return profile

    # Read the legacy values directly from the raw dict rather than
    # constructing a full UserDNA — legacy files may carry fields (beliefs,
    # preferences) that predate or drift from the current strict schema, and
    # the migration only needs the four value rankings.
    raw = json.loads(old.read_text(encoding="utf-8"))
    values = raw.get("values", {}) or {}
    output_ranking = (values.get("output") or {}).get("ranking", []) or []
    activity_ranking = (values.get("activity") or {}).get("ranking", []) or []
    env_ranking = (values.get("environment") or {}).get("ranking", []) or []
    reward_ranking = (values.get("reward") or {}).get("ranking", []) or []

    profile = BuilderInterestProfile(
        domains=_migrate_items(output_ranking, _OUTPUT_TO_DOMAIN, confirmed=True),
        technical_adjacencies=[],
        problem_preferences=_migrate_items(reward_ranking, _REWARD_TO_PREF, confirmed=True),
        build_constraints=_migrate_items(env_ranking, _ENV_TO_CONSTRAINT, confirmed=True),
        learning_goals=_migrate_items(activity_ranking, _ACTIVITY_TO_GOAL, confirmed=True),
        risk_tolerance="medium",
        migrated_from=str(old),
    )

    if backup:
        backup_path = Path(str(old) + ".bak")
        backup_path.write_text(old.read_text(encoding="utf-8"), encoding="utf-8")

    new.parent.mkdir(parents=True, exist_ok=True)
    new.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return profile
