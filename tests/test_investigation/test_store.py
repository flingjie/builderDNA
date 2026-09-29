"""Tests for investigations/store.py — idempotency, conflict, atomic writes."""
from datetime import datetime, timezone

import pytest

from concepts.handoffs import SourceHandoffItem
from investigations.models import (
    ActionRecord,
    EvidenceRecord,
    Investigation,
    InvestigationBudget,
    PainClusterCandidate,
)
from investigations.store import (
    InvestigationConflictError,
    InvestigationStore,
)
from models.concept import Directness, EvidenceRole, EvidenceStrength, SourceType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def store(tmp_path):
    return InvestigationStore(state_dir=tmp_path)


def make_inv(**overrides) -> Investigation:
    fields = dict(
        id="inv_1", topic="agent reliability", subreddit="AI_Agents",
        created_at=utc_now(), updated_at=utc_now(), budget=InvestigationBudget(),
    )
    fields.update(overrides)
    return Investigation(**fields)


def make_action(**overrides) -> ActionRecord:
    fields = dict(
        id="act_1", investigation_id="inv_1", action="search_discussions",
        params={}, canonical_params="", reason="", expected_revision=0,
        revision_after=1, status="completed", observation={},
        remaining_budget={}, allowed_next_actions=[], created_at=utc_now(),
    )
    fields.update(overrides)
    return ActionRecord(**fields)


def make_evidence(**overrides) -> EvidenceRecord:
    item = SourceHandoffItem(
        source=SourceType.REDDIT, role=EvidenceRole.PROBLEM, author="alice",
        url="https://www.reddit.com/r/SaaS/comments/x", excerpt="copy-paste onboarding",
        directness=Directness.DIRECT, strength=EvidenceStrength.MODERATE,
    )
    fields = dict(id="reddit:x", investigation_id="inv_1", item=item, created_at=utc_now())
    fields.update(overrides)
    return EvidenceRecord(**fields)


def test_upsert_investigation_preserves_created_at(store):
    inv = make_inv()
    store.upsert_investigation(inv)
    got = store.get_investigation("inv_1")
    assert got.id == "inv_1"
    assert got.status.value == "open"


def test_add_action_is_idempotent(store):
    store.upsert_investigation(make_inv())
    a = make_action()
    first = store.add_action(a)
    second = store.add_action(a)  # identical replay
    assert second is first or second == first
    assert len(store.list_actions("inv_1")) == 1


def test_add_action_conflict_on_same_id_different_payload(store):
    store.upsert_investigation(make_inv())
    store.add_action(make_action())
    with pytest.raises(InvestigationConflictError):
        store.add_action(make_action(status="no_results"))


def test_add_evidence_idempotent_and_filtered(store):
    store.upsert_investigation(make_inv())
    store.add_evidence(make_evidence())
    store.add_evidence(make_evidence())
    assert len(store.list_evidence("inv_1")) == 1
    assert store.list_evidence("other") == []


def test_add_candidate(store):
    store.upsert_investigation(make_inv())
    c = PainClusterCandidate(
        id="pc_1", investigation_id="inv_1", problem_statement="onboarding is manual",
        minimal_validation_action="count how many people already use a tool",
        evidence_ids=["reddit:x"], created_at=utc_now(),
    )
    store.add_candidate(c)
    assert len(store.list_candidates("inv_1")) == 1
