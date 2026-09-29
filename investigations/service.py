"""InvestigationService — deterministic orchestration of the action loop.

Thin business logic over ``InvestigationStore`` + ``actions`` + ``contract``. No
stdout, no Typer. Validates every action, executes it, persists the result, bumps
the revision, and returns the response envelope the Agent reads.
"""
from __future__ import annotations

from datetime import datetime, timezone

from investigations.actions import Fetcher, default_fetcher, execute
from investigations.contract import (
    ActionRequest,
    ActionStatus,
    DATA_ACTIONS,
    allowed_next_actions,
    canonicalize_params,
)
from investigations.models import (
    ActionRecord,
    Investigation,
    InvestigationBudget,
    InvestigationStatus,
    PainClusterCandidate,
)
from investigations.store import InvestigationStore


class InvestigationServiceError(Exception):
    exit_code = 1


class InvestigationValidationError(InvestigationServiceError):
    exit_code = 2


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _action_id(investigation_id: str, revision: int, action: str, canonical_params: str) -> str:
    return f"{investigation_id}:{revision}:{action}:{canonical_params}"


class InvestigationService:
    def __init__(self, store: InvestigationStore, fetcher: Fetcher | None = None):
        self.store = store
        self.fetcher = fetcher or default_fetcher

    # ── init ──

    def init(self, topic: str, subreddit: str = "", budget: InvestigationBudget | None = None) -> dict:
        if not topic.strip():
            raise InvestigationValidationError("init requires a non-empty --topic")
        inv = Investigation(
            id="inv_1",
            topic=topic.strip(),
            subreddit=subreddit.strip(),
            budget=budget or InvestigationBudget(),
        )
        # stable id: first investigation is inv_1; reuse existing if present (idempotent init)
        if self.store.get_investigation(inv.id) is None:
            self.store.upsert_investigation(inv)
        else:
            inv = self.store.get_investigation(inv.id)
        return {
            "investigation": inv.model_dump(mode="json"),
            "allowed_actions": self._next_actions(inv),
        }

    # ── helpers ──

    def _require_open(self, investigation_id: str) -> Investigation:
        inv = self.store.get_investigation(investigation_id)
        if inv is None:
            raise InvestigationValidationError(f"investigation {investigation_id!r} not found")
        if inv.status in (InvestigationStatus.COMPLETED, InvestigationStatus.FAILED):
            raise InvestigationValidationError(
                f"investigation {investigation_id!r} is {inv.status.value}; no further actions"
            )
        return inv

    def _next_actions(self, inv: Investigation) -> list[str]:
        candidates = self.store.list_candidates(inv.id)
        return allowed_next_actions(
            "completed",
            actions_used=inv.budget.actions_used,
            max_actions=inv.budget.max_actions,
            has_candidate=bool(candidates),
            candidates_used=len(candidates),
            max_candidates=inv.budget.max_candidates,
        )

    def _budget_dict(self, inv: Investigation) -> dict:
        return {
            "actions": max(0, inv.budget.max_actions - inv.budget.actions_used),
            "actions_used": inv.budget.actions_used,
            "max_actions": inv.budget.max_actions,
        }

    # ── run_action ──

    def run_action(self, request: ActionRequest) -> dict:
        inv = self._require_open(request.investigation_id)
        canonical = canonicalize_params(request.params)

        # Idempotent retry: the same submission (same expected_revision, action, and
        # canonical params) already executed -> return the saved result, no new source call.
        existing = self._find_action(request.investigation_id, request.expected_revision, request.action, canonical)
        if existing is not None:
            return self._response_from(existing)

        # A submission against an older revision with no matching saved action is stale.
        if request.expected_revision != inv.revision:
            return self._stale(inv)

        if request.action == "finish":
            return self._invalid(inv, "use `investigate finish --reason ...` to end the investigation")
        if request.action == "propose_pain_cluster":
            return self._invalid(inv, "use `investigate propose --candidate <file>` to submit a candidate")
        if request.action == "ask_user":
            return self._pause(inv)
        if request.action not in DATA_ACTIONS:
            return self._invalid(inv, f"unknown action {request.action!r}")

        if inv.budget.actions_used >= inv.budget.max_actions:
            return {
                "status": ActionStatus.BUDGET_EXHAUSTED.value,
                "revision": inv.revision,
                "observation": {"summary": "action budget exhausted"},
                "remaining_budget": self._budget_dict(inv),
                "allowed_next_actions": ["finish"],
            }

        evidence = self.store.list_evidence(request.investigation_id)
        result = execute(
            request.action,
            request.params,
            fetcher=self.fetcher,
            evidence=evidence,
            investigation_id=request.investigation_id,
        )
        new_evidence = result.pop("new_evidence", [])
        budget_delta = result.pop("budget_delta", {})

        # Persist newly collected evidence (idempotent; conflict only on ID reuse).
        for rec in new_evidence:
            self.store.add_evidence(rec)

        return self._record_and_return(inv, request, canonical, result["status"], result["observation"], budget_delta)

    def _record_and_return(self, inv, request, canonical, status, observation, budget_delta=None):
        budget_delta = budget_delta or {}
        actions_used = inv.budget.actions_used + 1
        evidence_rounds = inv.budget.evidence_rounds_used + int(budget_delta.get("evidence_rounds", 0))
        new_budget = inv.budget.model_copy(update={"actions_used": actions_used, "evidence_rounds_used": evidence_rounds})
        record = ActionRecord(
            id=_action_id(inv.id, inv.revision, request.action, canonical),
            investigation_id=inv.id,
            action=request.action,
            params=request.params,
            canonical_params=canonical,
            reason=request.reason,
            uncertainty_to_reduce=request.uncertainty_to_reduce,
            expected_revision=request.expected_revision,
            revision_after=inv.revision + 1,
            status=status,
            observation=observation,
            remaining_budget=self._budget_dict(inv.model_copy(update={"budget": new_budget})),
            allowed_next_actions=self._next_actions(inv.model_copy(update={"budget": new_budget})),
        )
        self.store.add_action(record)
        updated = inv.model_copy(
            update={
                "revision": inv.revision + 1,
                "budget": new_budget,
                "checkpoint": record.id,
            }
        )
        self.store.upsert_investigation(updated)
        return self._response_from(record)

    def _response_from(self, record: ActionRecord) -> dict:
        return {
            "status": record.status,
            "revision": record.revision_after,
            "observation": record.observation,
            "remaining_budget": record.remaining_budget,
            "allowed_next_actions": record.allowed_next_actions,
        }

    def _find_action(self, investigation_id, expected_revision, action, canonical) -> ActionRecord | None:
        for rec in self.store.list_actions(investigation_id):
            if rec.action == action and rec.canonical_params == canonical and rec.expected_revision == expected_revision:
                return rec
        return None

    def _stale(self, inv) -> dict:
        return {
            "status": ActionStatus.STALE_REVISION.value,
            "revision": inv.revision,
            "observation": {"summary": f"expected_revision {inv.revision} but you sent an older one"},
            "remaining_budget": self._budget_dict(inv),
            "allowed_next_actions": ["finish"],
        }

    def _invalid(self, inv, summary) -> dict:
        return {
            "status": ActionStatus.INVALID_ACTION.value,
            "revision": inv.revision,
            "observation": {"summary": summary},
            "remaining_budget": self._budget_dict(inv),
            "allowed_next_actions": self._next_actions(inv),
        }

    def _pause(self, inv):
        updated = inv.model_copy(update={"status": InvestigationStatus.PAUSED})
        self.store.upsert_investigation(updated)
        return {
            "status": "completed",
            "revision": inv.revision,
            "observation": {"summary": "escalated to user; investigation paused"},
            "remaining_budget": self._budget_dict(inv),
            "allowed_next_actions": ["finish"],
        }

    # ── propose ──

    def propose(self, investigation_id: str, candidate: PainClusterCandidate) -> dict:
        inv = self._require_open(investigation_id)
        existing = self.store.list_candidates(investigation_id)
        if len(existing) >= inv.budget.max_candidates:
            raise InvestigationValidationError(
                f"candidate budget exhausted: at most {inv.budget.max_candidates} candidate(s) per topic"
            )
        evidence_ids = {e.id for e in self.store.list_evidence(investigation_id)}
        missing = [eid for eid in candidate.evidence_ids if eid not in evidence_ids]
        if missing:
            raise InvestigationValidationError(
                f"candidate references unknown evidence: {missing}; every fact must trace to a collected source"
            )
        self.store.add_candidate(candidate)
        return {"action": "candidate_saved", "changed": ["candidate appended"], "data": {"candidate": candidate.model_dump(mode="json")}}

    # ── finish / resume / status ──

    def finish(self, investigation_id: str, reason: str) -> dict:
        inv = self._require_open(investigation_id)
        updated = inv.model_copy(update={"status": InvestigationStatus.COMPLETED, "end_reason": reason})
        self.store.upsert_investigation(updated)
        return {"investigation": updated.model_dump(mode="json")}

    def resume(self, investigation_id: str) -> dict:
        inv = self.store.get_investigation(investigation_id)
        if inv is None:
            raise InvestigationValidationError(f"investigation {investigation_id!r} not found")
        if inv.status != InvestigationStatus.PAUSED:
            raise InvestigationValidationError(f"investigation {investigation_id!r} is {inv.status.value}, not paused")
        updated = inv.model_copy(update={"status": InvestigationStatus.OPEN})
        self.store.upsert_investigation(updated)
        return {"investigation": updated.model_dump(mode="json"), "allowed_actions": self._next_actions(updated)}

    def status(self, investigation_id: str) -> dict:
        inv = self.store.get_investigation(investigation_id)
        if inv is None:
            raise InvestigationValidationError(f"investigation {investigation_id!r} not found")
        actions = self.store.list_actions(investigation_id)
        candidates = self.store.list_candidates(investigation_id)
        return {
            "investigation": inv.model_dump(mode="json"),
            "actions": [a.model_dump(mode="json") for a in actions],
            "candidates": [c.model_dump(mode="json") for c in candidates],
            "allowed_actions": self._next_actions(inv),
        }
