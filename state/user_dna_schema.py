"""User DNA schema — the contract for Value Discovery Skill output.

This model captures a user's cognitive decision model:
  Values → Beliefs → Criteria → Preferences

Used by:
  - value-discovery Skill (output)
  - collect command (mapping rules)
  - opportunity command (personalized scoring)
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


# ── Value dimensions (4 dimensions × 4 candidate values each) ──

ENVIRONMENT_VALUES = ["autonomy", "collaboration", "stability", "competition"]
ACTIVITY_VALUES = ["creation", "exploration", "optimization", "execution"]
OUTPUT_VALUES = ["devtools", "end_user", "infrastructure", "knowledge"]
REWARD_VALUES = ["growth", "mastery", "recognition", "wealth"]


class ValueDimension(BaseModel):
    """One dimension of values with ranking + 1-10 scores."""
    ranking: list[str] = Field(
        default_factory=list,
        description="Ordered list of value keys, most important first",
    )
    scores: dict[str, float] = Field(
        default_factory=dict,
        description="1-10 importance score per value key",
    )


class Values(BaseModel):
    """Four value dimensions, each independently ranked."""
    environment: ValueDimension = Field(default_factory=ValueDimension)
    activity: ValueDimension = Field(default_factory=ValueDimension)
    output: ValueDimension = Field(default_factory=ValueDimension)
    reward: ValueDimension = Field(default_factory=ValueDimension)


# ── Beliefs ──

class Belief(BaseModel):
    """An extracted belief — all inferred from language patterns."""
    statement: str = Field(description="The belief statement in natural language")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="How confident the model is in this extraction")
    source: Literal["inferred"] = "inferred"


# ── Criteria ──

class Criterion(BaseModel):
    """A decision rule extracted from user language."""
    decision_context: str = Field(description="When this rule applies, e.g. '技术选型', '工作机会'")
    rule: str = Field(description="The rule, e.g. '长期可维护性 > 短期开发速度'")


# ── Preferences ──

class Preferences(BaseModel):
    """Free-tag preferences derived from values. No fixed enum — user's own language."""
    work_style: list[str] = Field(default_factory=list, description="e.g. async_communication, deep_work_blocks")
    complexity: str = Field(default="", description="Preferred complexity level: low, medium, high")
    team_size: str = Field(default="", description="Preferred team: solo, small, medium, large")
    stage_preference: str = Field(default="", description="Project stage: early_stage, growth, mature")
    custom: dict[str, list[str]] = Field(default_factory=dict, description="Any additional preference categories")


# ── Evidence Log ──

class EvidenceEntry(BaseModel):
    """One piece of evidence linking user language to an extraction."""
    signal: str = Field(description="The user's original statement or observed pattern")
    extraction: str = Field(description="What was extracted from this signal, e.g. 'belief: depth_over_speed'")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


# ── Top-level User DNA ──

class UserDNA(BaseModel):
    """Complete cognitive model extracted from a user via Meta Model interview."""
    version: int = Field(default=1)
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    values: Values = Field(default_factory=Values)
    beliefs: list[Belief] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    evidence_log: list[EvidenceEntry] = Field(default_factory=list)


# ── Mapping Helpers ──

def load_user_dna(path: str = "state/user_dna.json") -> UserDNA | None:
    """Load User DNA from state file. Returns None if not found or empty."""
    import json
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        if not data.get("values") or not data["values"].get("environment", {}).get("ranking"):
            return None  # Empty template — no real extraction yet
        return UserDNA(**data)
    except Exception:
        return None


# Domain mapping from output value → topics
OUTPUT_DOMAIN_MAP: dict[str, dict] = {
    "devtools": {
        "domain": "devtools",
        "topics": ["sdk", "cli", "framework", "library", "api", "open-source-tools"],
    },
    "infrastructure": {
        "domain": "agent",
        "topics_filter": ["mcp", "tool-calling", "runtime", "networking", "infrastructure"],
    },
    "end_user": {
        "domain": "consumer",
        "topics": ["productivity", "creator-tool", "app", "ui", "consumer"],
    },
    "knowledge": {
        "domain": None,  # Keep current domain, append topics
        "topics_append": ["tutorial", "best-practices", "documentation", "awesome-list"],
    },
}

# Activity → window + filter mapping
ACTIVITY_CONFIG: dict[str, dict] = {
    "creation":    {"window": 90,  "min_stars": 0,   "boost": "recency"},
    "exploration": {"window": 365, "min_stars": 0,   "boost": "velocity"},
    "optimization": {"window": 180, "min_stars": 100, "boost": "recently_updated"},
    "execution":   {"window": 90,  "min_stars": 500, "boost": "maturity"},
}

# Reward → repo sort weight distribution
REWARD_WEIGHTS: dict[str, dict[str, float]] = {
    "growth":      {"velocity": 0.5, "stars_log": 0.2, "commercial": 0.1, "contributors": 0.2},
    "recognition": {"velocity": 0.15, "stars_log": 0.5, "commercial": 0.2, "contributors": 0.15},
    "wealth":      {"velocity": 0.15, "stars_log": 0.2, "commercial": 0.5, "contributors": 0.15},
    "mastery":     {"velocity": 0.15, "stars_log": 0.15, "commercial": 0.1, "contributors": 0.6},
}

# Environment → data source mix (accounts / vendors / topics)
ENVIRONMENT_SOURCE_MIX: dict[str, dict[str, float]] = {
    "autonomy":      {"accounts": 0.7, "vendors": 0.2, "topics": 0.1},
    "stability":     {"accounts": 0.1, "vendors": 0.3, "topics": 0.6},
    "collaboration": {"accounts": 0.2, "vendors": 0.5, "topics": 0.3},
    "competition":   {"accounts": 0.2, "vendors": 0.2, "topics": 0.6},
}
