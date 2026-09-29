"""Tests for investigations/service.py — the deterministic loop orchestrator."""
from datetime import datetime, timezone

import pytest

from investigations.contract import ActionRequest
from investigations.models import (
    InvestigationBudget,
    PainClusterCandidate,
)
from investigations.service import (
    InvestigationService,
    InvestigationValidationError,
)
from investigations.store import InvestigationStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


SAMPLE_POSTS = [
    {
        "id": "p1", "title": "I keep copy-pasting onboarding", "author": "alice",
        "permalink": "https://www.reddit.com/r/SaaS/comments/p1", "published": "2026-09-01T10:00:00Z",
        "selftext": "Every customer we copy-paste the same steps.", "category": "",
    },
    {
        "id": "p2", "title": "same onboarding pain", "author": "bob",
        "permalink": "https://www.reddit.com/r/startups/comments/p2", "published": "2026-09-02T10:00:00Z",
        "selftext": "we copy-paste onboarding too.", "category": "",
    },
]


@pytest.fixture
def service(tmp_path):
    store = InvestigationStore(state_dir=tmp_path)

    def fetcher(subreddit, sort, limit):
        return list(SAMPLE_POSTS)

    return InvestigationService(store, fetcher=fetcher)


def test_init_creates_investigation(service):
    out = service.init("agent reliability", subreddit="AI_Agents")
    inv = out["investigation"]
    assert inv["status"] == "open"
    assert "search_discussions" in out["allowed_actions"]


def test_run_action_advances_revision_and_budget(service):
    service.init("agent reliability", subreddit="AI_Agents")
    req = ActionRequest(investigation_id="inv_1", expected_revision=0,
                        action="search_discussions", params={"subreddit": "AI_Agents"},
                        reason="gap: no independent cases")
    resp = service.run_action(req)
    assert resp["status"] == "completed"
    assert resp["revision"] == 1
    assert resp["remaining_budget"]["actions"] == 7


def test_run_action_stale_revision_is_rejected(service):
    service.init("agent reliability", subreddit="AI_Agents")
    service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                     action="search_discussions", params={"subreddit": "AI_Agents"}))
    # stale: a NEW action submitted against the now-outdated revision 0
    resp = service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                            action="seek_counterevidence", params={}))
    assert resp["status"] == "stale_revision"


def test_run_action_idempotent_retry(service):
    service.init("agent reliability", subreddit="AI_Agents")
    req = ActionRequest(investigation_id="inv_1", expected_revision=0,
                        action="search_discussions", params={"subreddit": "AI_Agents"})
    first = service.run_action(req)
    # retry same request (same revision+action+canonical params) -> same result, no new source call
    second = service.run_action(req)
    assert first["revision"] == second["revision"]
    assert first["observation"] == second["observation"]


def test_run_action_unknown_action_rejected(service):
    service.init("agent reliability", subreddit="AI_Agents")
    req = ActionRequest(investigation_id="inv_1", expected_revision=0, action="rm_rf")
    resp = service.run_action(req)
    assert resp["status"] == "invalid_action"


def test_propose_validates_evidence_traceability(service):
    service.init("agent reliability", subreddit="AI_Agents")
    service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                     action="search_discussions", params={"subreddit": "AI_Agents"}))
    good = PainClusterCandidate(
        id="pc_1", investigation_id="inv_1", problem_statement="onboarding is manual",
        minimal_validation_action="ask 5 founders if they'd pay",
        evidence_ids=["reddit:p1", "reddit:p2"],
    )
    out = service.propose("inv_1", good)
    assert out["action"] == "candidate_saved"


def test_propose_rejects_fabricated_evidence(service):
    service.init("agent reliability", subreddit="AI_Agents")
    bad = PainClusterCandidate(
        id="pc_1", investigation_id="inv_1", problem_statement="onboarding is manual",
        minimal_validation_action="x", evidence_ids=["reddit:not_real"],
    )
    with pytest.raises(InvestigationValidationError):
        service.propose("inv_1", bad)


def test_finish_sets_completed_and_checkpoint(service):
    service.init("agent reliability", subreddit="AI_Agents")
    service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                     action="search_discussions", params={"subreddit": "AI_Agents"}))
    out = service.finish("inv_1", "low information gain")
    assert out["investigation"]["status"] == "completed"
    assert out["investigation"]["end_reason"] == "low information gain"
    assert out["investigation"]["checkpoint"]  # last action id
