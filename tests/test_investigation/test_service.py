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


def test_run_action_raises_on_paused_investigation(service):
    """Fix 1: PAUSED investigations cannot execute data actions."""
    service.init("agent reliability", subreddit="AI_Agents")
    service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                     action="ask_user", reason="escalate to user"))
    # investigation is now PAUSED; run_action should reject
    req = ActionRequest(investigation_id="inv_1", expected_revision=1,
                        action="search_discussions", params={"subreddit": "AI_Agents"})
    with pytest.raises(InvestigationValidationError):
        service.run_action(req)


def test_propose_raises_on_paused_investigation(service):
    """Fix 1: PAUSED investigations cannot propose candidates."""
    service.init("agent reliability", subreddit="AI_Agents")
    service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                     action="ask_user", reason="escalate to user"))
    # investigation is now PAUSED; propose should reject
    candidate = PainClusterCandidate(
        id="pc_1", investigation_id="inv_1", problem_statement="test",
        minimal_validation_action="test",
        evidence_ids=[],
    )
    with pytest.raises(InvestigationValidationError):
        service.propose("inv_1", candidate)


def test_finish_allows_paused_investigation(service):
    """Fix 1: PAUSED investigations can still be finished."""
    service.init("agent reliability", subreddit="AI_Agents")
    service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                     action="ask_user", reason="escalate to user"))
    # investigation is PAUSED; finish should work
    out = service.finish("inv_1", "user escalation completed")
    assert out["investigation"]["status"] == "completed"
    assert out["investigation"]["end_reason"] == "user escalation completed"


def test_finish_rejects_completed_investigation(service):
    """Fix 1: COMPLETED investigations cannot be finished again."""
    service.init("agent reliability", subreddit="AI_Agents")
    service.finish("inv_1", "already complete")
    with pytest.raises(InvestigationValidationError):
        service.finish("inv_1", "second finish attempt")


def test_finish_rejects_failed_investigation(service):
    """Fix 1: FAILED investigations cannot be finished."""
    service.init("agent reliability", subreddit="AI_Agents")
    inv = service.store.get_investigation("inv_1")
    inv.status = "failed"
    service.store.upsert_investigation(inv)
    with pytest.raises(InvestigationValidationError):
        service.finish("inv_1", "attempt to finish failed inv")


def test_evidence_round_budget_exhaustion(service):
    """Fix 2: Fourth evidence round exceeds budget -> budget_exhausted status."""
    service.init("agent reliability", subreddit="AI_Agents")
    # Max evidence rounds is 3; three searches with fresh posts should succeed
    # Track the next post id so each search gets new posts (avoiding dedup)
    next_id = [1]

    def fresh_fetcher(subreddit, sort, limit):
        result = [
            {
                "id": f"round_{next_id[0]}_post_{i}",
                "title": f"issue round {next_id[0]}, post {i}",
                "author": "user1",
                "permalink": f"https://www.reddit.com/r/SaaS/comments/round_{next_id[0]}_post_{i}",
                "published": f"2026-09-0{next_id[0]}T10:00:00Z",
                "selftext": f"Problem in round {next_id[0]}.",
                "category": "",
            }
            for i in range(2)
        ]
        next_id[0] += 1
        return result

    service.fetcher = fresh_fetcher

    # Three searches with fresh posts should each consume 1 evidence_round
    for i in range(3):
        req = ActionRequest(investigation_id="inv_1", expected_revision=i,
                            action="search_discussions", params={"subreddit": "AI_Agents"},
                            reason=f"round {i+1}")
        resp = service.run_action(req)
        assert resp["status"] == "completed", f"round {i+1} status was {resp['status']}"
        assert resp["remaining_budget"]["evidence_rounds"] == 2 - i

    # Fourth search should return budget_exhausted (evidence round budget is exhausted)
    req = ActionRequest(investigation_id="inv_1", expected_revision=3,
                        action="search_discussions", params={"subreddit": "AI_Agents"},
                        reason="fourth round - exceeds budget")
    resp = service.run_action(req)
    assert resp["status"] == "budget_exhausted"
    assert resp["observation"]["summary"] == "evidence round budget exhausted: at most 3 round(s) per investigation"
    assert resp["allowed_next_actions"] == ["finish"]
