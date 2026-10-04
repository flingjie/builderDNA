"""Builder problem and practice-trajectory contracts.

These models capture the shift from a static developer profile to an
evidence-backed, evolving problem record:

- ``BuilderProblem`` is the current snapshot of one problem.
- ``ProblemEvent`` is an append-only trajectory event. Corrections and updates
  add events instead of rewriting history.
- ``ProblemComparison`` groups problems by task + obstacle, not by keyword.
- ``ProblemOpportunityCard`` turns a sufficiently similar problem cluster into
  a verifiable opportunity with explicit unknowns and validation targets.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from models.concept import UtcDatetime


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ProblemStatus(str, Enum):
    OBSERVED = "observed"
    CONFIRMED = "confirmed"
    RESOLVED = "resolved"


class ProblemEventType(str, Enum):
    PROBLEM_OBSERVED = "problem_observed"
    ATTEMPT = "attempt"
    TOOL_SWITCH = "tool_switch"
    STATUS_CHANGE = "status_change"
    NOTE = "note"


class BuilderProblem(BaseModel):
    """Current snapshot for one person's problem.

    ``problem_id`` is the store key. ``person_ref`` and ``project_ref`` are
    stable references into the person/project records owned by the orchestrating
    skill. The structured scenario fields make cross-person comparison possible
    without keyword clustering.
    """

    problem_id: str = Field(min_length=1, description="Stable problem ID")
    person_ref: str = Field(min_length=1, description="Stable reference to the builder/person")
    project_ref: str = Field(default="", description="Stable reference to the project, when relevant")
    statement: str = Field(min_length=1, description="The concrete problem statement")
    context: str = Field(default="", description="When and where the problem appears")
    current_workaround: str = Field(default="", description="What the person currently does to work around the problem")

    user_segment: str = Field(default="", description="Who the person is, e.g. independent Agent developer")
    trigger_context: str = Field(default="", description="What action/change triggers the problem")
    job_to_be_done: str = Field(default="", description="The task the person is trying to complete")
    primary_cost: str = Field(default="", description="The main cost the problem imposes")

    source_refs: list[str] = Field(default_factory=list, description="Evidence references backing this record")
    first_seen_at: UtcDatetime = Field(default_factory=_now_utc, description="When this problem was first observed")
    last_seen_at: UtcDatetime = Field(default_factory=_now_utc, description="When this problem was last seen/updated")
    status: ProblemStatus = Field(default=ProblemStatus.OBSERVED, description="observed / confirmed / resolved")
    updated_at: UtcDatetime = Field(default_factory=_now_utc, description="When this snapshot was last written")

    @property
    def id(self) -> str:
        """JSONL store key alias for the generic read/write helpers."""
        return self.problem_id


class ProblemEvent(BaseModel):
    """One immutable trajectory event for a problem."""

    event_id: str = Field(min_length=1, description="Stable event ID")
    problem_id: str = Field(min_length=1, description="Problem this event belongs to")
    event_type: ProblemEventType = Field(default=ProblemEventType.NOTE, description="Trajectory event type")
    summary: str = Field(min_length=1, description="Short description, e.g. '尝试脚本'")
    detail: str = Field(default="", description="Optional detail about the attempt or change")
    source_refs: list[str] = Field(default_factory=list, description="Evidence references for this event")
    from_status: ProblemStatus | None = Field(default=None, description="Status before this event, if relevant")
    to_status: ProblemStatus | None = Field(default=None, description="Status after this event, if relevant")
    current_workaround: str = Field(default="", description="Workaround captured by this event, if any")
    recorded_at: UtcDatetime = Field(default_factory=_now_utc, description="When this event happened")

    @property
    def id(self) -> str:
        """JSONL store key alias for the generic read/write helpers."""
        return self.event_id


class ProblemEvidenceRef(BaseModel):
    """Who encountered a problem and the evidence for that claim."""

    problem_id: str = Field(min_length=1)
    person_ref: str = Field(min_length=1)
    project_ref: str = Field(default="")
    statement: str = Field(default="")
    status: ProblemStatus = ProblemStatus.OBSERVED
    source_refs: list[str] = Field(default_factory=list)


class ValidationTarget(BaseModel):
    """A person/problem that should be contacted to validate the shared need."""

    problem_id: str = Field(min_length=1)
    person_ref: str = Field(min_length=1)
    project_ref: str = Field(default="")
    status: ProblemStatus = ProblemStatus.OBSERVED
    reason: str = Field(default="", description="Why this target is the right validation contact")
    source_refs: list[str] = Field(default_factory=list)


class ProblemComparison(BaseModel):
    """A task-and-obstacle based comparison across multiple people.

    Only problems whose normalized ``job_to_be_done`` and ``trigger_context``
    match are grouped. Mentioning the same keyword such as 'eval' is not enough.
    """

    scenario_key: str = Field(description="Deterministic task+obstacle fingerprint")
    title: str = Field(description="Human-readable scenario title")
    user_segment: str = Field(default="", description="User segment when all problems agree; otherwise empty")
    trigger_context: str = Field(description="Shared trigger context")
    job_to_be_done: str = Field(description="Shared job to be done")
    current_workaround: str = Field(default="", description="Shared workaround when all problems agree; otherwise empty")
    primary_cost: str = Field(default="", description="Shared primary cost when all problems agree; otherwise empty")

    problem_ids: list[str] = Field(default_factory=list)
    person_refs: list[str] = Field(default_factory=list)
    project_refs: list[str] = Field(default_factory=list)
    similarities: dict[str, str] = Field(default_factory=dict)
    differences: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    evidence: list[ProblemEvidenceRef] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    validation_targets: list[ValidationTarget] = Field(default_factory=list)
    minimal_deliverable: str = Field(default="", description="Smallest verifiable next result")


class ProblemOpportunityCard(BaseModel):
    """A verifiable opportunity derived from a cross-person problem comparison."""

    scenario_key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    who: list[ProblemEvidenceRef] = Field(default_factory=list, description="Who encountered the problem and the evidence")
    same_parts: list[str] = Field(default_factory=list, description="What is the same across people")
    different_parts: list[str] = Field(default_factory=list, description="What differs across people")
    key_unknowns: list[str] = Field(default_factory=list, description="Critical unknowns that still need validation")
    validation_targets: list[ValidationTarget] = Field(default_factory=list, description="Who to validate with first")
    minimal_deliverable: str = Field(default="", description="Smallest verifiable next result")
    source_refs: list[str] = Field(default_factory=list, description="Evidence references")
