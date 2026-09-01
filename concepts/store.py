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
- **Append-only IDs.** Adding evidence or a review whose ID already exists raises
  ``DuplicateRecordError`` — history is never silently clobbered. Corrections
  append a new record with a fresh ID and ``supersedes=old_id``.
"""

from __future__ import annotations

import json
import os
import tempfile
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

    # ── read plumbing ──

    def _read(self, path: Path, model_cls: type[T]) -> ReadResult[T]:
        result = _read_jsonl(path, model_cls)
        self._last_read[path] = result
        return result

    def corrupt_lines(self) -> list[CorruptLine]:
        """Collect every corrupt line seen by the most recent read of each file."""
        out: list[CorruptLine] = []
        for result in self._last_read.values():
            out.extend(result.corrupt)
        return out

    # ── concepts (one current snapshot per ID) ──

    def list_concepts(self) -> list[ConceptCard]:
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

    def add_evidence(self, evidence: ConceptEvidence) -> ConceptEvidence:
        """Append an evidence record; raise if its ID already exists.

        Evidence is immutable. A correction appends a new record with a fresh ID
        and ``supersedes=<old_id>`` rather than editing history.
        """
        result = self._read(self.evidence_path, ConceptEvidence)
        _check_corruption(self.evidence_path, result)
        existing_ids = {e.id for e in result.records}
        if evidence.id in existing_ids:
            raise DuplicateRecordError(
                f"evidence ID {evidence.id!r} already exists; corrections append "
                f"a new record with a new ID and supersedes={evidence.id!r}"
            )
        _atomic_write(self.evidence_path, result.records + [evidence])
        return evidence

    def list_evidence(self, concept_id: str | None = None) -> list[ConceptEvidence]:
        result = self._read(self.evidence_path, ConceptEvidence)
        if concept_id is None:
            return result.records
        return [e for e in result.records if e.concept_id == concept_id]

    def get_evidence(self, evidence_id: str) -> ConceptEvidence | None:
        for evidence in self.list_evidence():
            if evidence.id == evidence_id:
                return evidence
        return None

    # ── reviews (append-only) ──

    def add_review(self, review: RadarReview) -> RadarReview:
        """Append a review record; raise if its ID already exists."""
        result = self._read(self.reviews_path, RadarReview)
        _check_corruption(self.reviews_path, result)
        existing_ids = {r.id for r in result.records}
        if review.id in existing_ids:
            raise DuplicateRecordError(
                f"review ID {review.id!r} already exists; reviews are append-only"
            )
        _atomic_write(self.reviews_path, result.records + [review])
        return review

    def list_reviews(self, concept_id: str | None = None) -> list[RadarReview]:
        result = self._read(self.reviews_path, RadarReview)
        if concept_id is None:
            return result.records
        return [r for r in result.records if r.concept_id == concept_id]

    def get_review(self, review_id: str) -> RadarReview | None:
        for review in self.list_reviews():
            if review.id == review_id:
                return review
        return None
