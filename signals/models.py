"""Unified Signal model — normalization target for all upstream data sources.

All upstream data normalizes into Signal. GitHub API responses remain the
primary producer (via collector/normalizer.py), but the shared model is now
cross-source (Task 3.1): x, reddit, paper, official_doc, and manual evidence
normalize into the same immutable event.

Aggregate views are defined in models/payload.py as the canonical output
contract.
"""
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

# Cross-source signal origins (Task 3.1). `github` remains the default and the
# only source emitted by the existing collector pipeline. Adapters for the new
# sources live elsewhere (concepts/adapters) and import SignalSource here.
SignalSource = Literal["x", "reddit", "github", "paper", "official_doc", "manual"]

# GitHub-specific event types — unchanged so existing GitHub records and
# consumers (cli/commands/collect.py, intelligence/trend/velocity.py) keep
# working verbatim.
GITHUB_EVENT_TYPES: tuple[str, ...] = (
    "repo_created",       # active: new repository
    "star_growth",        # active: star increase event
    "issue_opened",       # active: issue created (contains body text)
    "issue_commented",    # reserved: issue discussion activity
    "release",            # reserved: version release
    "fork",               # reserved: fork event
    "discussion",         # reserved: discussion created
)

# Generic event types for the non-GitHub sources. `type` is deliberately a free
# string (not a Literal) so new adapters can introduce their own labels without
# a schema change; these are sensible defaults.
GENERIC_EVENT_TYPES: tuple[str, ...] = (
    "signal",           # catch-all observation / finding
    "evidence",         # verifiable artifact: quote, citation, primary link
    "note",             # manual human-curated capture
    "counterexample",   # evidence against a hypothesis
)


class Signal(BaseModel):
    """Unified immutable event. All data sources normalize to this.

    Source-specific detail lives in `payload` — it is the extensibility point
    and must not be flattened into normalized fields. Normalized evidence
    metadata (role, directness, strength, independence) is nullable so
    pre-existing GitHub records do not require it.
    """

    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    source: SignalSource = "github"
    # Free string rather than a rigid Literal: GitHub sources keep the
    # GITHUB_EVENT_TYPES vocabulary, non-GitHub sources use GENERIC_EVENT_TYPES
    # or their own labels. Defaults to the generic "signal" fallback so new
    # source adapters are not forced to invent a type.
    type: str = "signal"
    actor: str                                # developer, org, author, or curator login
    target_repo: str                          # canonical target: "org/repo", subreddit, paper id, URL, etc.
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    velocity: float = 0.0                     # instantaneous growth rate (stars/day)
    impact: float = 0.0                       # influence weight (0-1)

    # ── Evidence metadata (Task 3.1, nullable) ──────────────────────────────
    # These enrich a Signal into evidence for concept validation. Existing
    # GitHub records predate them, so all four are optional and default to None.
    evidence_role: str | None = None
    """Role the signal plays for a concept: problem, attempted_solution,
    adoption, implementation, validation, counterexample, or context."""
    directness: str | None = None
    """How directly the signal addresses the claim: L1 (primary source),
    L2 (secondary/derived), L3 (tertiary/linked artifact)."""
    strength: float | None = None
    """Evidence strength weight (nullable; scale interpretation is left to the
    scoring layer, which may use 0-1 or 0-3)."""
    independence_key: str | None = None
    """Shared by reposts/citations of one upstream claim so duplicate
    propagation does not inflate recurrence counts."""

    payload: dict[str, Any] = Field(default_factory=dict)  # raw source-specific snapshot
