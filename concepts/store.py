"""Atomic JSONL persistence for concept cards, evidence, and reviews.

Three runtime files, all under ``state/`` by default and created lazily on first
use:

- ``state/concepts.jsonl``       — one current snapshot per concept ID (rewritten
  atomically on every upsert).
- ``state/concept_evidence.jsonl`` — append-only ``ConceptEvidence`` records.
- ``state/radar_reviews.jsonl``    — append-only ``RadarReview`` records.

Design rules enforced here:

- **Atomic writes.** Every write goes through a same-directory temporary file
  followed by ``os.replace``, so an interrupted write never truncates or
  partially overwrites prior state.
- **Robust reads.** Every non-empty line is parsed independently. A line that is
  unparsable JSON, not a JSON object, or fails model validation is collected as a
  ``CorruptLine`` (reported, never raised) and skipped.
- **Deterministic ID de-duplication on read.** If a file contains the same ID
  more than once (manual edits, partial recovery), the *last* occurrence wins
  (later lines override earlier ones). The returned ordering is the order of
  first appearance of each ID in the file. This is the documented policy.
- **Corruption guard on write.** If more than half of an existing file's
  non-empty lines are corrupt, the store refuses to write and raises
  ``CorruptionError`` instead of silently rewriting away history.
- **Idempotent replay vs conflict.** Appending evidence or a review whose ID
  already exists compares the existing record to the incoming one by their
  serialized fields (``model_dump(mode="json")``). An identical ID plus an
  identical payload is an idempotent success — it returns the existing record
  and writes nothing. An identical ID plus a different payload raises
  ``ConflictError``. The comparison ignores the write-only timestamps
  ``captured_at`` (evidence) and ``recorded_at`` (reviews) so a replayed record
  that only differs by when it was captured/recorded is treated as the same
  logical record. Every other field — including the semantic ``review_date`` —
  participates in the comparison.
- **Process-local lock.** Reads and read-modify-rewrite cycles are guarded by a
  ``threading.RLock`` so concurrent calls within one process cannot interleave
  and lose an append. Multi-host / multi-process writers are **unsupported**:
  the lock only serializes threads inside a single process, and there is no
  file-level (``flock``) coordination. Run one writer process per store
  directory.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Generic, TypeVar

from models.concept import ConceptCard, ConceptEvidence, RadarReview

T = TypeVar("T")


# ── Errors ──

class ConceptStoreError(Exception):
    """Base error for concept store operations."""


class CorruptionError(ConceptStoreError):
    """Refusing to write: more than half of the existing file is corrupt."""


class DuplicateRecordError(ConceptStoreError):
    """Refusing to append a record whose ID already exists."""


class ConflictError(DuplicateRecordError):
    """Refusing to append: same ID as an existing record but a different payload.

    Distinct from an idempotent replay (same ID *and* same payload, which is a
    no-op) and from the generic ``DuplicateRecordError`` it subclasses, so callers
    can catch the specific conflict case while existing handlers for the broader
    duplicate/``ConceptStoreError`` families keep working.
    """


@dataclass(frozen=True)
class CorruptLine:
    """One line that could not be read as a valid record."""

    path: Path
    line_no: int
    raw: str
    error: str


@dataclass
class ReadResult(Generic[T]):
    """Outcome of a robust read: valid records plus collected corrupt lines."""

    records: list[T] = field(default_factory=list)
    corrupt: list[CorruptLine] = field(default_factory=list)
    total_lines: int = 0


# ── Low-level read / write helpers ──

def _read_jsonl(path: Path, model_cls: type[T]) -> ReadResult[T]:
    """Read every non-empty line as ``model_cls``, skipping and collecting corrupt lines.

    Blank lines are ignored entirely (not counted, not corrupt). Valid records are
    de-duplicated by ``id`` with *last wins*; ordering is by first appearance.
    """
    if not path.exists():
        return ReadResult()
    by_id: dict[str, T] = {}
    corrupt: list[CorruptLine] = []
    total = 0
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            total += 1
            try:
                data = json.loads(stripped)
                if not isinstance(data, dict):
                    raise ValueError("record is not a JSON object")
                record = model_cls.model_validate(data)
            except Exception as exc:  # JSON decode or model validation failure
                corrupt.append(
                    CorruptLine(
                        path=path,
                        line_no=line_no,
                        raw=stripped,
                        error=str(exc),
                    )
                )
                continue
            by_id[record.id] = record  # last wins
    return ReadResult(records=list(by_id.values()), corrupt=corrupt, total_lines=total)


def _check_corruption(path: Path, result: ReadResult) -> None:
    """Refuse to write when more than half of the existing lines are corrupt."""
    if result.total_lines > 0 and len(result.corrupt) * 2 > result.total_lines:
        raise CorruptionError(
            f"refusing to write {path}: {len(result.corrupt)} of "
            f"{result.total_lines} non-empty lines are corrupt (more than half); "
            f"fix or restore the file before writing again"
        )


def _atomic_write(path: Path, records: list) -> None:
    """Write ``records`` as JSONL via a same-directory temp file + atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for record in records:
                fh.write(record.model_dump_json() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _append_line(path: Path, record: T) -> None:
    """Append one JSONL line without rewriting the file (O(1) per append).

    Evidence/review files are append-only, so a full-file rewrite is unnecessary
    work (O(n^2) across a batch). The caller holds the store lock and verifies the
    tail afterward; a crash mid-line is handled by the corruption guard on read.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(record.model_dump_json() + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# Write-only timestamp fields that do not change a record's logical identity.
# A replayed record whose only difference is *when* it was captured/recorded is
# the same logical record, so these are dropped before idempotency comparison.
_WRITE_TIMESTAMP_FIELDS = frozenset({"captured_at", "recorded_at"})


def _record_view(record: T) -> dict:
    """Deterministic comparison view of a record for idempotency checks.

    Serializes via ``model_dump(mode="json")`` (enums and datetimes become their
    JSON string forms) and removes the write-only timestamp fields so two
    logically identical records compare equal even when ``captured_at`` /
    ``recorded_at`` differ.
    """
    data = record.model_dump(mode="json")
    for field in _WRITE_TIMESTAMP_FIELDS:
        data.pop(field, None)
    return data


def _verify_tail_parses(path: Path, model_cls: type[T]) -> None:
    """Confirm the last non-empty line of ``path`` parses as ``model_cls``.

    Runs after an append to guarantee the write did not leave a malformed tail.
    A failure here raises ``CorruptionError`` rather than being silently ignored.
    """
    last: str | None = None
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                last = stripped
    if last is None:
        return
    try:
        data = json.loads(last)
        if not isinstance(data, dict):
            raise ValueError("record is not a JSON object")
        model_cls.model_validate(data)
    except Exception as exc:
        raise CorruptionError(
            f"append verification failed for {path}: last line does not parse "
            f"as {model_cls.__name__}: {exc}"
        )


# ── Store ──

class ConceptStore:
    """JSONL-backed persistence for concept snapshots, evidence, and reviews."""

    def __init__(self, state_dir: str | Path = "state"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.concepts_path = self.state_dir / "concepts.jsonl"
        self.evidence_path = self.state_dir / "concept_evidence.jsonl"
        self.reviews_path = self.state_dir / "radar_reviews.jsonl"
        self._last_read: dict[Path, ReadResult] = {}
        # Reentrant so a locked method may safely call another locked method.
        # Serializes only this process; multi-process writers are unsupported.
        self._lock = threading.RLock()

    # ── read plumbing ──

    def _read(self, path: Path, model_cls: type[T]) -> ReadResult[T]:
        result = _read_jsonl(path, model_cls)
        self._last_read[path] = result
        return result

    def corrupt_lines(self) -> list[CorruptLine]:
        """Collect every corrupt line seen by the most recent read of each file."""
        with self._lock:
            out: list[CorruptLine] = []
            for result in self._last_read.values():
                out.extend(result.corrupt)
            return out

    # ── concepts (one current snapshot per ID) ──

    def list_concepts(self) -> list[ConceptCard]:
        with self._lock:
            result = self._read(self.concepts_path, ConceptCard)
            return result.records

    def get_concept(self, concept_id: str) -> ConceptCard | None:
        for card in self.list_concepts():
            if card.id == concept_id:
                return card
        return None

    def upsert_concept(self, card: ConceptCard) -> ConceptCard:
        """Atomically set the current snapshot for ``card.id`` and return it.

        ``created_at`` is preserved from the existing snapshot when one exists;
        ``updated_at`` is bumped to the current UTC time on every write.
        """
        with self._lock:
            result = self._read(self.concepts_path, ConceptCard)
            _check_corruption(self.concepts_path, result)
            by_id = {c.id: c for c in result.records}
            existing = by_id.get(card.id)
            created_at = existing.created_at if existing is not None else card.created_at
            updated = card.model_copy(
                update={
                    "created_at": created_at,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            by_id[card.id] = updated
            _atomic_write(self.concepts_path, list(by_id.values()))
            return updated

    # ── evidence (append-only) ──

    def _append_record(
        self,
        path: Path,
        model_cls: type[T],
        record: T,
        kind: str,
    ) -> T:
        """Shared append path: idempotent replay, conflict detection, atomic write.

        Reads the deduped view, runs the corruption guard, then either returns the
        existing identical record (idempotent no-op), raises ``ConflictError`` for a
        same-ID/different-payload record, or appends. The tail is verified after
        the write so a malformed last line can never silently land.
        """
        result = self._read(path, model_cls)
        _check_corruption(path, result)
        by_id = {r.id: r for r in result.records}
        existing = by_id.get(record.id)
        if existing is not None:
            if _record_view(existing) == _record_view(record):
                return existing  # idempotent replay — no-op
            if kind == "evidence":
                hint = (
                    "corrections append a new record with a new ID and "
                    f"supersedes={record.id!r}"
                )
            else:
                hint = "reviews are append-only; append a correction with a new ID"
            raise ConflictError(
                f"{kind} ID {record.id!r} already exists with a different payload; "
                f"{hint}"
            )
        _append_line(path, record)
        _verify_tail_parses(path, model_cls)
        return record

    def add_evidence(self, evidence: ConceptEvidence) -> ConceptEvidence:
        """Append an evidence record.

        Replaying an identical record (same ID, same payload — ``captured_at``
        ignored) is an idempotent no-op that returns the existing record. A same
        ID with a different payload raises ``ConflictError``. Evidence is
        otherwise immutable: a correction appends a new record with a fresh ID
        and ``supersedes=<old_id>`` rather than editing history.
        """
        with self._lock:
            return self._append_record(
                self.evidence_path, ConceptEvidence, evidence, "evidence"
            )

    def list_evidence(self, concept_id: str | None = None) -> list[ConceptEvidence]:
        with self._lock:
            result = self._read(self.evidence_path, ConceptEvidence)
            if concept_id is None:
                return result.records
            return [e for e in result.records if e.concept_id == concept_id]

    def get_evidence(self, evidence_id: str) -> ConceptEvidence | None:
        for evidence in self.list_evidence():
            if evidence.id == evidence_id:
                return evidence
        return None

    def evidence_conflicts(self, records: list[ConceptEvidence]) -> list[str]:
        """Pre-check ``records`` for same-ID/different-payload conflicts (no writes).

        Returns one message per record whose ID already exists with a different
        payload. The handoff importer uses this to reject a whole handoff atomically
        before writing any record.
        """
        existing = {e.id: e for e in self.list_evidence()}
        conflicts = []
        for record in records:
            prev = existing.get(record.id)
            if prev is not None and _record_view(prev) != _record_view(record):
                conflicts.append(
                    f"evidence ID {record.id!r} already exists with a different payload"
                )
        return conflicts

    # ── reviews (append-only) ──

    def add_review(self, review: RadarReview) -> RadarReview:
        """Append a review record.

        Replaying an identical record (same ID, same payload — ``recorded_at``
        ignored) is an idempotent no-op that returns the existing record. A same
        ID with a different payload raises ``ConflictError``.
        """
        with self._lock:
            return self._append_record(
                self.reviews_path, RadarReview, review, "review"
            )

    def list_reviews(self, concept_id: str | None = None) -> list[RadarReview]:
        with self._lock:
            result = self._read(self.reviews_path, RadarReview)
            if concept_id is None:
                return result.records
            return [r for r in result.records if r.concept_id == concept_id]

    def get_review(self, review_id: str) -> RadarReview | None:
        for review in self.list_reviews():
            if review.id == review_id:
                return review
        return None
