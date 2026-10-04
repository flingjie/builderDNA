"""JSONL persistence for builder problems and trajectory events.

Files:

- ``<state_dir>/builders/problems.jsonl`` — one current snapshot per problem ID.
- ``<state_dir>/builders/events.jsonl``  — append-only ``ProblemEvent`` records.

Uses the shared mechanics in ``state/jsonl.py`` so snapshots are written
atomically and events are immutable after append.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from models.builder_problem import BuilderProblem, ProblemEvent
from state.jsonl import (
    CorruptLine,
    append_line,
    atomic_write,
    corruption_detected,
    read_jsonl,
    record_view,
    tail_parses,
)

T = TypeVar("T")


class BuilderProblemStoreError(Exception):
    """Base error for builder problem store operations."""


class BuilderProblemConflictError(BuilderProblemStoreError):
    """Same event ID with a different payload."""


def _check_corruption(path: Path, result) -> None:
    if corruption_detected(result):
        raise BuilderProblemStoreError(
            f"refusing to write {path}: {len(result.corrupt)} of "
            f"{result.total_lines} non-empty lines are corrupt (more than half)"
        )


def _verify_tail(path: Path, model_cls) -> None:
    if not tail_parses(path, model_cls):
        raise BuilderProblemStoreError(
            f"append verification failed for {path}: last line does not parse as {model_cls.__name__}"
        )


class BuilderProblemStore:
    """JSONL-backed persistence for problem snapshots and events."""

    def __init__(self, state_dir: str | Path = "state"):
        self.root = Path(state_dir) / "builders"
        self.root.mkdir(parents=True, exist_ok=True)
        self.problems_path = self.root / "problems.jsonl"
        self.events_path = self.root / "events.jsonl"
        self._last_read: dict[Path, object] = {}
        self._lock = threading.RLock()

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

    # ── problems (one current snapshot per ID) ──

    def list_problems(self) -> list[BuilderProblem]:
        with self._lock:
            return self._read(self.problems_path, BuilderProblem).records

    def get_problem(self, problem_id: str) -> BuilderProblem | None:
        for problem in self.list_problems():
            if problem.problem_id == problem_id:
                return problem
        return None

    def upsert_problem(self, problem: BuilderProblem) -> BuilderProblem:
        with self._lock:
            result = self._read(self.problems_path, BuilderProblem)
            _check_corruption(self.problems_path, result)
            by_id = {p.problem_id: p for p in result.records}
            existing = by_id.get(problem.problem_id)
            first_seen_at = existing.first_seen_at if existing is not None else problem.first_seen_at
            updated = problem.model_copy(
                update={
                    "first_seen_at": first_seen_at,
                    "last_seen_at": problem.last_seen_at,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            by_id[problem.problem_id] = updated
            atomic_write(self.problems_path, list(by_id.values()))
            return updated

    # ── events (append-only) ──

    @staticmethod
    def _event_view(event: ProblemEvent) -> dict:
        data = record_view(event)
        data.pop("recorded_at", None)
        return data

    def add_event(self, event: ProblemEvent) -> ProblemEvent:
        with self._lock:
            result = self._read(self.events_path, ProblemEvent)
            _check_corruption(self.events_path, result)
            by_id = {e.event_id: e for e in result.records}
            existing = by_id.get(event.event_id)
            if existing is not None:
                if self._event_view(existing) == self._event_view(event):
                    return existing
                raise BuilderProblemConflictError(
                    f"event ID {event.event_id!r} already exists with a different payload"
                )
            append_line(self.events_path, event)
            _verify_tail(self.events_path, ProblemEvent)
            return event

    def list_events(self, problem_id: str | None = None) -> list[ProblemEvent]:
        with self._lock:
            result = self._read(self.events_path, ProblemEvent)
            if problem_id is None:
                return result.records
            return [e for e in result.records if e.problem_id == problem_id]
