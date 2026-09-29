"""Tests for investigations/models.py."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from investigations.models import (
    ActionRecord,
    EvidenceRecord,
    Investigation,
    InvestigationBudget,
    InvestigationStatus,
    PainClusterCandidate,
)
from concepts.handoffs import SourceHandoffItem
from models.concept import Directness, EvidenceRole, EvidenceStrength, SourceType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_investigation_defaults():
    inv = Investigation(
        id="inv_1",
        topic="agent reliability",
        subreddit="AI_Agents",
        created_at=utc_now(),
        updated_at=utc_now(),
        budget=InvestigationBudget(),
    )
    assert inv.status == InvestigationStatus.OPEN
    assert inv.revision == 0
    assert inv.budget.max_actions == 8
    assert inv.budget.max_evidence_rounds == 3
    assert inv.budget.max_candidates == 1


def test_investigation_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        Investigation(
            id="inv_1",
            topic="x",
            created_at=datetime(2026, 9, 29),  # naive
            updated_at=datetime(2026, 9, 29),
            budget=InvestigationBudget(),
        )


def test_candidate_requires_problem_and_action():
    with pytest.raises(ValidationError):
        PainClusterCandidate(id="pc_1", investigation_id="inv_1", problem_statement="")
    with pytest.raises(ValidationError):
        PainClusterCandidate(
            id="pc_1", investigation_id="inv_1", problem_statement="p", minimal_validation_action=""
        )


def test_evidence_record_wraps_handoff_item():
    item = SourceHandoffItem(
        source=SourceType.REDDIT,
        role=EvidenceRole.PROBLEM,
        author="alice",
        url="https://www.reddit.com/r/SaaS/comments/x",
        excerpt="we keep copy-pasting onboarding",
        directness=Directness.DIRECT,
        strength=EvidenceStrength.MODERATE,
    )
    rec = EvidenceRecord(id="reddit:x", investigation_id="inv_1", item=item, created_at=utc_now())
    assert rec.item.role == EvidenceRole.PROBLEM


def test_action_record_round_trips():
    rec = ActionRecord(
        id="act_1",
        investigation_id="inv_1",
        action="search_discussions",
        params={"query": "onboarding"},
        canonical_params="search_discussions:onboarding",
        reason="gap: no independent cases",
        expected_revision=0,
        revision_after=1,
        status="completed",
        observation={"evidence_ids": ["reddit:a"], "summary": "2 posts"},
        remaining_budget={"actions": 7},
        allowed_next_actions=["inspect_thread"],
        created_at=utc_now(),
    )
    assert rec.status == "completed"
    assert rec.revision_after == 1
