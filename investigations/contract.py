"""Action contract request/response envelope, canonical params, allowed actions.

Pure and side-effect free: the service validates the request and calls
``canonicalize_params`` to build the idempotency key; the Agent sees
``allowed_next_actions`` after every observation.
"""
from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel, Field

KNOWN_ACTIONS: frozenset[str] = frozenset(
    {
        "search_discussions",
        "inspect_thread",
        "find_similar_cases",
        "seek_workaround",
        "seek_counterevidence",
        "propose_pain_cluster",
        "ask_user",
        "finish",
    }
)

DATA_ACTIONS: frozenset[str] = frozenset(
    {
        "search_discussions",
        "inspect_thread",
        "find_similar_cases",
        "seek_workaround",
        "seek_counterevidence",
    }
)


class ActionStatus(str, Enum):
    COMPLETED = "completed"
    NO_RESULTS = "no_results"
    SOURCE_FAILURE = "source_failure"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INVALID_ACTION = "invalid_action"
    STALE_REVISION = "stale_revision"


class ActionRequest(BaseModel):
    schema_version: int = 1
    investigation_id: str = Field(min_length=1)
    expected_revision: int = 0
    action: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)
    reason: str = ""
    uncertainty_to_reduce: str = ""


def canonicalize_params(params: dict) -> str:
    """Deterministic key for ``params``, order-independent."""
    return json.dumps(params or {}, sort_keys=True, separators=(",", ":"))


def allowed_next_actions(
    status: str,
    actions_used: int,
    max_actions: int,
    has_candidate: bool,
    candidates_used: int,
    max_candidates: int,
) -> list[str]:
    """The set of actions the Agent may take next, given state and budget.

    Always allowed: ``finish``. Data actions are allowed while the action budget
    remains. ``propose_pain_cluster`` is allowed only while no candidate exists and
    the candidate budget remains. ``ask_user`` is allowed while the action budget
    remains (a fork escalates to the user without consuming a source call).
    """
    actions: list[str] = []
    if status == ActionStatus.STALE_REVISION.value:
        return ["finish"]
    budget_left = actions_used < max_actions
    if budget_left:
        actions += sorted(DATA_ACTIONS)
        actions.append("ask_user")
    if not has_candidate and candidates_used < max_candidates:
        actions.append("propose_pain_cluster")
    actions.append("finish")
    return actions
