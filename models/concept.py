"""Concept radar domain models — the canonical contracts for the concept lifecycle.

These Pydantic models are the authoritative machine contract for the
Inbox -> Watch -> Verify -> Build/Drop lifecycle. They mirror the English
description in ``.claude/skills/concept-radar/references/schema.md``.

Design rules enforced structurally here:

- Evidence and review records are immutable (``frozen=True``) — corrections
  append a superseding record rather than editing history.
- Component scores are validated to [0, 3].
- The experiment-priority total is always recomputed from components and is
  never trusted from caller input.
- All timestamps must be timezone-aware UTC.
- A Build-stage card must carry a bounded, falsifiable smallest experiment.
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


# ── Timestamps ──

def _ensure_utc(value: datetime) -> datetime:
    """Reject naive or non-UTC datetimes; return the value unchanged."""
    if value.tzinfo is None:
        raise ValueError(
            "timestamp must be timezone-aware (use datetime.now(timezone.utc))"
        )
    if value.utcoffset() != timedelta(0):
        raise ValueError(
            "timestamp must be UTC (got offset %s)" % value.utcoffset()
        )
    return value


UtcDatetime = Annotated[datetime, AfterValidator(_ensure_utc)]


# ── Enums ──

class SourceType(str, Enum):
    """Where a piece of evidence came from."""
    X = "x"
    REDDIT = "reddit"
    GITHUB = "github"
    PAPER = "paper"
    OFFICIAL_DOC = "official_doc"
    MANUAL = "manual"


class EvidenceRole(str, Enum):
    """The role a piece of evidence plays for a concept."""
    PROBLEM = "problem"               # the failure/job is real
    IMPLEMENTATION = "implementation"  # it can be built / is technically feasible
    ADOPTION = "adoption"             # people actually use it
    COUNTER = "counterevidence"       # evidence against the hypothesis


class Directness(str, Enum):
    """How directly the source speaks to the claim."""
    DIRECT = "direct"      # primary source, first-hand observation
    INDIRECT = "indirect"  # second-hand report, repost, or summary
    INFERRED = "inferred"  # note-taker inference without a primary link


class EvidenceStrength(str, Enum):
    """How strong the source is as evidence."""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class MaturityStage(str, Enum):
    """Evidence status — how well-supported a concept is (NOT a portfolio decision)."""
    SIGNAL = "signal"        # one or a few weak signals
    EMERGING = "emerging"    # growing evidence, not yet independent
    VERIFIED = "verified"    # multiple independent chains / source types
    CONTESTED = "contested"  # counterevidence present and unresolved


class PortfolioStage(str, Enum):
    """The lifecycle portfolio decision for a card."""
    INBOX = "inbox"
    WATCH = "watch"
    VERIFY = "verify"
    BUILD = "build"
    DROP = "drop"


class OutcomeState(str, Enum):
    """Recorded outcome of a Build experiment."""
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


# ── Score components ──

class ComponentScores(BaseModel):
    """The individual score components that make up experiment priority.

    Every component is scored 0-3. The ``total`` is always recomputed from the
    components (``2P + 2E + R + A - 2H - C``) and is never trusted from caller
    input: high hype can only lower priority, and high user alignment can never
    raise evidence strength or maturity.
    """
    problem: int = Field(
        default=0, ge=0, le=3,
        description="P — problem severity: how painful and frequent the failure is (0-3)",
    )
    evidence: int = Field(
        default=0, ge=0, le=3,
        description="E — independent evidence strength supporting the concept (0-3)",
    )
    reach: int = Field(
        default=0, ge=0, le=3,
        description="R — reach: how many people or systems are affected (0-3)",
    )
    user_alignment: int = Field(
        default=0, ge=0, le=3,
        description="A — personal adjacency. Changes priority only, never evidence strength or maturity (0-3)",
    )
    hype: int = Field(
        default=0, ge=0, le=3,
        description="H — hype: how inflated the surrounding discourse is. Penalty term (0-3)",
    )
    competition: int = Field(
        default=0, ge=0, le=3,
        description="C — competition: how crowded the space already is. Penalty term (0-3)",
    )
    total: int = Field(
        default=0,
        description="Experiment priority = 2P + 2E + R + A - 2H - C. Always recomputed from the component scores; any caller-supplied value is overwritten.",
    )

    @model_validator(mode="after")
    def _recompute_total(self) -> "ComponentScores":
        self.total = (
            2 * self.problem
            + 2 * self.evidence
            + self.reach
            + self.user_alignment
            - 2 * self.hype
            - self.competition
        )
        return self


# ── Smallest experiment ──

class SmallestExperiment(BaseModel):
    """A bounded, falsifiable experiment proposal (required before Build)."""
    hypothesis: str = Field(
        min_length=1,
        description="The falsifiable hypothesis being tested",
    )
    target: str = Field(
        min_length=1,
        description="Target user or system the experiment runs against",
    )
    artifact: str = Field(
        default="",
        description="Minimal artifact to build or expose",
    )
    success_threshold: str = Field(
        min_length=1,
        description="What observable result counts as success",
    )
    failure_threshold: str = Field(
        min_length=1,
        description="What observable result counts as failure",
    )
    stop_condition: str = Field(
        min_length=1,
        description="Bounded stop condition (time or cost budget) that ends the experiment",
    )


# ── Concept card ──

class ConceptCard(BaseModel):
    """The current snapshot of one concept.

    One current snapshot per concept ID; updates are atomic at the store level.
    ``maturity`` describes evidence status; ``stage`` describes a portfolio
    decision — the two are independent axes.
    """
    id: str = Field(min_length=1, description="Stable concept ID (slug)")
    title: str = Field(min_length=1, description="Display name")
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names this concept has been captured under",
    )
    problem: str = Field(
        default="",
        description="The job or failure the concept addresses",
    )
    why_now: str = Field(
        default="",
        description="What changed that makes this worth acting on now",
    )
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="IDs of ConceptEvidence records backing this card",
    )
    maturity: MaturityStage = Field(
        default=MaturityStage.SIGNAL,
        description="Evidence status: how well-supported the concept is",
    )
    stage: PortfolioStage = Field(
        default=PortfolioStage.INBOX,
        description="Portfolio decision: Inbox / Watch / Verify / Build / Drop",
    )
    component_scores: ComponentScores = Field(
        default_factory=ComponentScores,
        description="Individual score components that make up experiment priority",
    )
    smallest_experiment: SmallestExperiment | None = Field(
        default=None,
        description="Bounded, falsifiable experiment proposal. Required when stage='build'.",
    )
    prediction: str = Field(
        default="",
        description="Prediction recorded on entry to Build",
    )
    outcome: OutcomeState | None = Field(
        default=None,
        description="Recorded outcome of the Build experiment",
    )
    lesson: str = Field(
        default="",
        description="Lesson learned from the outcome",
    )
    created_at: UtcDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this card was first captured (UTC)",
    )
    updated_at: UtcDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this snapshot was last updated (UTC)",
    )

    @model_validator(mode="after")
    def _require_smallest_experiment_for_build(self) -> "ConceptCard":
        if self.stage == PortfolioStage.BUILD and self.smallest_experiment is None:
            raise ValueError(
                "A Build-stage concept requires a bounded, falsifiable smallest "
                "experiment; provide `smallest_experiment` before setting "
                "stage='build'."
            )
        return self


# ── Evidence ──

class ConceptEvidence(BaseModel):
    """An immutable source record backing a concept.

    Evidence is immutable: corrections append a superseding record (``supersedes``)
    rather than editing history. Reposts or citations of one upstream claim share
    an ``independence_key`` so they do not inflate recurrence.
    """
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, description="Stable evidence record ID")
    concept_id: str = Field(
        min_length=1,
        description="ID of the concept card this evidence supports",
    )
    source_type: SourceType = Field(description="Where this evidence came from")
    source_url: str = Field(
        default="",
        description="URL of the original source, when available",
    )
    role: EvidenceRole = Field(
        description="Role this evidence plays: problem, implementation, adoption, or counterevidence",
    )
    directness: Directness = Field(
        description="How directly the source speaks to the claim",
    )
    strength: EvidenceStrength = Field(
        description="How strong the source is as evidence",
    )
    independence_key: str = Field(
        min_length=1,
        description="Groups reposts or citations of one upstream claim so they do not inflate recurrence",
    )
    note: str = Field(
        default="",
        description="Human-curated note or quoted excerpt",
    )
    captured_at: UtcDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this evidence was captured (UTC)",
    )
    supersedes: str | None = Field(
        default=None,
        description="ID of an earlier evidence record this one supersedes (append-only correction)",
    )


# ── Radar review ──

class RadarReview(BaseModel):
    """An immutable transition record for one concept.

    Records why a card moved between portfolio stages, what evidence is expected
    next, and when the next review is due. Immutable: reviews append, never edit.
    """
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, description="Stable review record ID")
    concept_id: str = Field(
        min_length=1,
        description="ID of the concept card that transitioned",
    )
    from_stage: PortfolioStage | None = Field(
        default=None,
        description="Stage before the transition (None on initial capture)",
    )
    to_stage: PortfolioStage = Field(description="Stage after the transition")
    reason: str = Field(min_length=1, description="Why the card transitioned")
    expected_evidence: str = Field(
        default="",
        description="What evidence is expected next",
    )
    review_date: UtcDatetime = Field(
        description="When the transition happened or the next review is due (UTC)",
    )
    recorded_at: UtcDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this record was written (UTC)",
    )
