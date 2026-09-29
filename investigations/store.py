"""JSONL persistence for investigations, actions, evidence, and candidates.

Four files under ``<state_dir>/investigations/``:

- ``investigations.jsonl`` — one current snapshot per investigation (atomic rewrite).
- ``actions.jsonl``      — append-only ``ActionRecord``.
- ``evidence.jsonl``     — append-only ``EvidenceRecord``.
- ``candidates.jsonl``   — append-only ``PainClusterCandidate``.

Reuses the shared mechanics in ``state/jsonl.py`` (atomic write, idempotent
comparison, corruption guard) so the investigation store and the concept store
share one tested implementation. Investigation evidence lives here — separate from
``ConceptStore``'s concept-anchored evidence — so pre-candidate evidence never
pollutes the concept radar's evidence space with a synthetic ``concept_id``.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from state.jsonl import (
    CorruptLine,
    atomic_write,
    append_line,
    corruption_detected,
    read_jsonl,
    record_view,
    tail_parses,
)
from investigations.models import (
    ActionRecord,
    EvidenceRecord,
    Investigation,
    PainClusterCandidate,
)

T = TypeVar("T")


class InvestigationStoreError(Exception):
    """Base error for investigation store operations."""


class InvestigationConflictError(InvestigationStoreError):
    """Same record ID with a different payload."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _check_corruption(path: Path, result) -> None:
    """Refuse to write when more than half of the existing lines are corrupt."""
    if corruption_detected(result):
        raise InvestigationStoreError(
            f"refusing to write {path}: {len(result.corrupt)} of "
            f"{result.total_lines} non-empty lines are corrupt (more than half)"
        )


def _verify_tail(path: Path, model_cls) -> None:
    """Confirm the last non-empty line parses; raise otherwise."""
    if not tail_parses(path, model_cls):
        raise InvestigationStoreError(
            f"append verification failed for {path}: last line does not parse as {model_cls.__name__}"
        )


def _append_record_view(record) -> dict:
    """Comparison view for append-only records: exclude write-only timestamps.

    For append-only records (actions, evidence, candidates), written_at timestamps
    (created_at) are excluded from the idempotent comparison since replaying the
    same logical record should be idempotent even if timestamps differ slightly.
    """
    data = record_view(record)
    # Remove write-only timestamps from comparison for append-only records
    data.pop("created_at", None)
    return data


class InvestigationStore:
    def __init__(self, state_dir: str | Path = "state"):
        self.root = Path(state_dir) / "investigations"
        self.root.mkdir(parents=True, exist_ok=True)
        self.investigations_path = self.root / "investigations.jsonl"
        self.actions_path = self.root / "actions.jsonl"
        self.evidence_path = self.root / "evidence.jsonl"
        self.candidates_path = self.root / "candidates.jsonl"
        self._last_read: dict[Path, object] = {}
        self._lock = threading.RLock()

    # ── read plumbing ──

    def _read(self, path: Path, model_cls: type[T]):
        result = read_jsonl(path, model_cls)
        self._last_read[path] = result
        return result

    def corrupt_lines(self) -> list[CorruptLine]:
        with self._lock:
            out: list[CorruptLine] = []
            for result in self._last_read.values():
                out.extend(result.corrupt)
            return out

    # ── investigations (snapshot, atomic rewrite) ──

    def list_investigations(self) -> list[Investigation]:
        with self._lock:
            return self._read(self.investigations_path, Investigation).records

    def get_investigation(self, investigation_id: str) -> Investigation | None:
        for inv in self.list_investigations():
            if inv.id == investigation_id:
                return inv
        return None

    def upsert_investigation(self, inv: Investigation) -> Investigation:
        with self._lock:
            result = self._read(self.investigations_path, Investigation)
            _check_corruption(self.investigations_path, result)
            by_id = {i.id: i for i in result.records}
            existing = by_id.get(inv.id)
            created_at = existing.created_at if existing is not None else inv.created_at
            updated = inv.model_copy(
                update={"created_at": created_at, "updated_at": _now_utc()}
            )
            by_id[inv.id] = updated
            atomic_write(self.investigations_path, list(by_id.values()))
            return updated

    # ── append-only records (idempotent + conflict) ──

    def _append_record(self, path: Path, model_cls: type[T], record: T, kind: str) -> T:
        result = self._read(path, model_cls)
        _check_corruption(path, result)
        by_id = {r.id: r for r in result.records}
        existing = by_id.get(record.id)
        if existing is not None:
            if _append_record_view(existing) == _append_record_view(record):
                return existing  # idempotent replay — no-op
            raise InvestigationConflictError(
                f"{kind} ID {record.id!r} already exists with a different payload"
            )
        append_line(path, record)
        _verify_tail(path, model_cls)
        return record

    def add_action(self, record: ActionRecord) -> ActionRecord:
        with self._lock:
            return self._append_record(self.actions_path, ActionRecord, record, "action")

    def list_actions(self, investigation_id: str | None = None) -> list[ActionRecord]:
        with self._lock:
            result = self._read(self.actions_path, ActionRecord)
            if investigation_id is None:
                return result.records
            return [r for r in result.records if r.investigation_id == investigation_id]

    def add_evidence(self, record: EvidenceRecord) -> EvidenceRecord:
        with self._lock:
            return self._append_record(self.evidence_path, EvidenceRecord, record, "evidence")

    def list_evidence(self, investigation_id: str | None = None) -> list[EvidenceRecord]:
        with self._lock:
            result = self._read(self.evidence_path, EvidenceRecord)
            if investigation_id is None:
                return result.records
            return [r for r in result.records if r.investigation_id == investigation_id]

    def add_candidate(self, candidate: PainClusterCandidate) -> PainClusterCandidate:
        with self._lock:
            return self._append_record(self.candidates_path, PainClusterCandidate, candidate, "candidate")

    def list_candidates(self, investigation_id: str | None = None) -> list[PainClusterCandidate]:
        with self._lock:
            result = self._read(self.candidates_path, PainClusterCandidate)
            if investigation_id is None:
                return result.records
            return [r for r in result.records if r.investigation_id == investigation_id]
