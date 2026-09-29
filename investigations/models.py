"""Investigation control-plane domain models.

Mirrors the design spec's §4 "数据与状态". Timestamps use ``UtcDatetime`` from
``models.concept`` (rejects naive/non-UTC), and ``EvidenceRecord`` reuses
``SourceHandoffItem`` as the evidence contract rather than defining a parallel
model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from concepts.handoffs import SourceHandoffItem
from models.concept import UtcDatetime


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class InvestigationStatus(str, Enum):
    OPEN = "open"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestigationBudget(BaseModel):
    """Bounded action/evidence/candidate budget (configurable, not domain truth)."""

    max_actions: int = 8
    max_evidence_rounds: int = 3
    max_candidates: int = 1
    actions_used: int = 0
    evidence_rounds_used: int = 0


class Investigation(BaseModel):
    """One investigation: target, revision, budget, status, checkpoint, end reason."""

    id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    subreddit: str = ""
    created_at: UtcDatetime = Field(default_factory=_now_utc)
    updated_at: UtcDatetime = Field(default_factory=_now_utc)
    revision: int = 0
    schema_version: int = 1
    config_fingerprint: str = ""
    budget: InvestigationBudget = Field(default_factory=InvestigationBudget)
    status: InvestigationStatus = InvestigationStatus.OPEN
    checkpoint: str = ""
    end_reason: str = ""


class ActionRecord(BaseModel):
    """An append-only record of one validated action and its observation."""

    id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)
    canonical_params: str = ""
    reason: str = ""
    uncertainty_to_reduce: str = ""
    expected_revision: int = 0
    revision_after: int = 0
    status: str = Field(min_length=1)
    observation: dict = Field(default_factory=dict)
    remaining_budget: dict = Field(default_factory=dict)
    allowed_next_actions: list[str] = Field(default_factory=list)
    created_at: UtcDatetime = Field(default_factory=_now_utc)


class EvidenceRecord(BaseModel):
    """A collected evidence item (a ``SourceHandoffItem``) plus a stable store ID."""

    id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    item: SourceHandoffItem
    created_at: UtcDatetime = Field(default_factory=_now_utc)


class PainClusterCandidate(BaseModel):
    """A single-source discovery artifact — NOT a ``ConceptCard``.

    ``evidence_ids`` must each reference a real stored evidence record (traceability).
    ``coverage_limits`` and ``open_questions`` carry explicit unknowns.
    """

    id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    problem_statement: str = Field(min_length=1)
    affected_scenarios: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    time_span_start: str = ""
    time_span_end: str = ""
    workarounds: list[str] = Field(default_factory=list)
    counterevidence: list[str] = Field(default_factory=list)
    coverage_limits: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    minimal_validation_action: str = Field(min_length=1)
    created_at: UtcDatetime = Field(default_factory=_now_utc)
