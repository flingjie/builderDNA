"""Generic append-only / snapshot JSONL persistence.

Extracted from ``concepts/store.py`` so the concept store and the investigation
store share one tested implementation of atomic writes, robust reads, idempotent
comparison, and corruption guards.

Design rules (unchanged from the concept store):

- **Atomic writes** via a same-directory temp file + ``os.replace``.
- **Robust reads**: each non-empty line is parsed independently; a corrupt line is
  collected (reported, never raised) and skipped; duplicate IDs de-duplicate with
  *last wins*.
- **Corruption guard on write**: >50% corrupt lines refuses the write.
- **Write-only timestamp fields** (``captured_at`` / ``recorded_at``) are dropped
  from the idempotency comparison view.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

T = TypeVar("T")


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


# Write-only timestamp fields that do not change a record's logical identity.
_WRITE_TIMESTAMP_FIELDS = frozenset({"captured_at", "recorded_at"})


def read_jsonl(path: Path, model_cls: type[T]) -> ReadResult[T]:
    """Read every non-empty line as ``model_cls``, skipping and collecting corrupt lines."""
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
                    CorruptLine(path=path, line_no=line_no, raw=stripped, error=str(exc))
                )
                continue
            by_id[record.id] = record  # last wins
    return ReadResult(records=list(by_id.values()), corrupt=corrupt, total_lines=total)


def corruption_detected(result: ReadResult) -> bool:
    """True when more than half of the existing lines are corrupt."""
    return result.total_lines > 0 and len(result.corrupt) * 2 > result.total_lines


def atomic_write(path: Path, records: list) -> None:
    """Write ``records`` as JSONL via a same-directory temp file + atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
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


def append_line(path: Path, record: T) -> None:
    """Append one JSONL line without rewriting the file (O(1) per append)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(record.model_dump_json() + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def tail_parses(path: Path, model_cls: type[T]) -> bool:
    """True when the last non-empty line parses as ``model_cls`` (or the file is empty)."""
    last: str | None = None
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                last = stripped
    if last is None:
        return True
    try:
        data = json.loads(last)
        if not isinstance(data, dict):
            return False
        model_cls.model_validate(data)
        return True
    except Exception:
        return False


def record_view(record: T) -> dict:
    """Deterministic comparison view: JSON dump minus write-only timestamp fields."""
    data = record.model_dump(mode="json")
    for field in _WRITE_TIMESTAMP_FIELDS:
        data.pop(field, None)
    return data
