"""Tests for investigations/contract.py."""
from investigations.contract import (
    ActionRequest,
    ActionStatus,
    DATA_ACTIONS,
    KNOWN_ACTIONS,
    allowed_next_actions,
    canonicalize_params,
)


def test_known_actions():
    assert {"search_discussions", "inspect_thread", "propose_pain_cluster", "finish"} <= KNOWN_ACTIONS
    assert DATA_ACTIONS == {
        "search_discussions", "inspect_thread", "find_similar_cases",
        "seek_workaround", "seek_counterevidence",
    }


def test_canonicalize_params_is_order_independent():
    assert canonicalize_params({"a": 1, "b": 2}) == canonicalize_params({"b": 2, "a": 1})
    assert canonicalize_params({"query": "onboarding"}) == '{"query":"onboarding"}'


def test_action_request_validates_action():
    req = ActionRequest(
        investigation_id="inv_1", expected_revision=0, action="seek_counterevidence",
        params={"claim_id": "claim_1"}, reason="single community",
        uncertainty_to_reduce="other contexts have solutions",
    )
    assert req.action == "seek_counterevidence"


def test_allowed_next_actions_budget_exhausted():
    # budget exhausted -> only finish
    got = allowed_next_actions("completed", actions_used=8, max_actions=8, has_candidate=True,
                               candidates_used=1, max_candidates=1)
    assert got == ["finish"]


def test_allowed_next_actions_can_propose_when_no_candidate():
    got = allowed_next_actions("completed", actions_used=3, max_actions=8, has_candidate=False,
                               candidates_used=0, max_candidates=1)
    assert "propose_pain_cluster" in got
    assert "finish" in got


def test_allowed_next_actions_omits_propose_when_candidate_exists():
    got = allowed_next_actions("completed", actions_used=3, max_actions=8, has_candidate=True,
                               candidates_used=1, max_candidates=1)
    assert "propose_pain_cluster" not in got
