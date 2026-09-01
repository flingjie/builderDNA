"""Atomic JSON checkpoint persistence for radar-cycle runs.

One checkpoint file per run, under ``state/radar_cycles/{run-id}.json`` by
default. The file is a single JSON object: the serialized
:class:`~radar_cycles.models.RadarCycleRun` plus three checkpoint-only keys that
the run model does not carry (``RadarCycleRun`` ignores unknown keys on
validation, so the run round-trips cleanly):

- ``outputs``     — ``{phase_name: [output_path, ...]}``: completed output paths
  per phase, preserved across resume so a resumed run can reference (rather than
  re-produce) prior work.
- ``coverage``    — a list of ``SourceCoverage`` records (source type, status,
  note).
- ``run_status``  — ``"running"`` or ``"completed"`` (set by :func:`finish`).

Design rules:

- **Atomic writes.** Every write goes through a same-directory temporary file
  (``tempfile.mkstemp``), flushed with ``fsync``, then ``os.replace`` into place.
  An interrupted write therefore never truncates or partially overwrites a prior
  valid checkpoint — the old file stays intact until the new one is durable and
  renamed over it.
- **Retry counts.** ``partial``/``failed`` may return to ``running`` exactly once
  and ``blocked`` may return to ``running`` only after changed input or user
  direction (``allow_unblock=True``). These rules live in
  :meth:`radar_cycles.models.PhaseCheckpoint.transition`, which
  :func:`transition` delegates to rather than reimplementing; the retry counts
  are stored on the checkpoint and survive a load.
- **Output-path preservation.** :func:`save` re-reads the current file and
  carries forward the recorded ``outputs``/``coverage``/``run_status``, so a
  plain save never silently drops work recorded by :func:`record_output`.
- **Process-local lock.** Read-modify-write cycles are serialized by a
  ``threading.RLock``. Multi-host / multi-process writers are **unsupported**:
  the lock only serializes threads inside one process and there is no file-level
  (``flock``) coordination. Run one writer process per store directory.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from models.concept import SourceType
from models.radar_payload import SourceCoverage, SourceStatus
from radar_cycles.models import (
    Limits,
    Mode,
    PhaseCheckpoint,
    PhaseName,
    RadarCycleRun,
)

__all__ = [
    "DEFAULT_STORE_DIR",
    "RUNNING",
    "COMPLETED",
    "CheckpointDocument",
    "create",
    "load",
    "load_document",
    "save",
    "transition",
    "record_output",
    "record_coverage",
    "record_error",
    "finish",
    "outputs_of",
    "coverage_of",
    "run_status_of",
    "exists",
]

#: Default directory holding one ``{run-id}.json`` file per radar-cycle run.
DEFAULT_STORE_DIR = Path("state") / "radar_cycles"

#: ``run_status`` values recorded alongside the run.
RUNNING = "running"
COMPLETED = "completed"

# Checkpoint-only top-level keys in the persisted JSON document.
_OUTPUTS_KEY = "outputs"
_COVERAGE_KEY = "coverage"
_STATUS_KEY = "run_status"

# Serializes read-modify-write cycles within this process. Multi-process /
# multi-host writers are unsupported (no flock).
_lock = threading.RLock()


@dataclass
class CheckpointDocument:
    """Everything persisted for one run: the run plus checkpoint-only state."""

    run: RadarCycleRun
    outputs: dict[str, list[str]] = field(default_factory=dict)
    coverage: list[SourceCoverage] = field(default_factory=list)
    run_status: str = RUNNING


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_dir(store_dir: str | Path | None) -> Path:
    return Path(store_dir) if store_dir is not None else DEFAULT_STORE_DIR


def _validate_run_id(run_id: str) -> str:
    """Reject run IDs that could escape the store directory or name a bad file."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    if run_id in (".", "..") or "/" in run_id or "\\" in run_id:
        raise ValueError(f"unsafe run_id {run_id!r}: must not contain path separators")
    return run_id


def _path_for(store_dir: Path, run_id: str) -> Path:
    return store_dir / f"{_validate_run_id(run_id)}.json"


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write ``data`` as JSON via a same-directory temp file + atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _serialize(doc: CheckpointDocument) -> dict:
    data = doc.run.model_dump(mode="json")
    data[_OUTPUTS_KEY] = doc.outputs
    data[_COVERAGE_KEY] = [c.model_dump(mode="json") for c in doc.coverage]
    data[_STATUS_KEY] = doc.run_status
    return data


def _deserialize(data: dict) -> CheckpointDocument:
    run = RadarCycleRun.model_validate(data)  # ignores the checkpoint-only keys
    outputs = data.get(_OUTPUTS_KEY) or {}
    coverage_raw = data.get(_COVERAGE_KEY) or []
    coverage = [SourceCoverage.model_validate(c) for c in coverage_raw]
    run_status = data.get(_STATUS_KEY) or RUNNING
    return CheckpointDocument(
        run=run,
        outputs=outputs,
        coverage=coverage,
        run_status=run_status,
    )


def _read_document(store_dir: Path, run_id: str) -> CheckpointDocument:
    path = _path_for(store_dir, run_id)
    if not path.exists():
        raise FileNotFoundError(f"no checkpoint for run {run_id!r} at {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"checkpoint {path} is not a JSON object")
    return _deserialize(data)


def _write_document(store_dir: Path, run_id: str, doc: CheckpointDocument) -> None:
    _atomic_write_json(_path_for(store_dir, run_id), _serialize(doc))


# ── public API ──

def create(
    run_id: str,
    radar: str,
    mode: Mode | str,
    limits: Limits | dict,
    config_fingerprint: str,
    *,
    store_dir: str | Path | None = None,
) -> RadarCycleRun:
    """Create a new run with every phase ``pending`` and persist it atomically.

    ``limits`` may be a :class:`~radar_cycles.models.Limits` instance or a dict.
    """
    store_dir = _resolve_dir(store_dir)
    _validate_run_id(run_id)
    mode = Mode(mode)
    if not isinstance(limits, Limits):
        limits = Limits.model_validate(limits)
    checkpoint = PhaseCheckpoint(
        config_fingerprint=config_fingerprint,
        mode=mode,
        limits=limits,
    )
    run = RadarCycleRun(id=run_id, radar=radar, mode=mode, checkpoint=checkpoint)
    with _lock:
        _write_document(store_dir, run_id, CheckpointDocument(run=run))
    return run


def load_document(
    run_id: str,
    *,
    store_dir: str | Path | None = None,
) -> CheckpointDocument:
    """Return the full persisted document (run + outputs + coverage + status)."""
    store_dir = _resolve_dir(store_dir)
    with _lock:
        return _read_document(store_dir, run_id)


def load(run_id: str, *, store_dir: str | Path | None = None) -> RadarCycleRun:
    """Load a saved run. Raises ``FileNotFoundError`` when the run is unknown."""
    return load_document(run_id, store_dir=store_dir).run


def save(run: RadarCycleRun, *, store_dir: str | Path | None = None) -> RadarCycleRun:
    """Atomically persist ``run``, preserving any recorded outputs/coverage/status.

    Re-serializes the whole run (never a diff). The checkpoint-only keys already
    on disk (``outputs``, ``coverage``, ``run_status``) are carried forward so a
    plain save does not drop work recorded by :func:`record_output` et al.
    """
    store_dir = _resolve_dir(store_dir)
    with _lock:
        path = _path_for(store_dir, run.id)
        if path.exists():
            existing = _read_document(store_dir, run.id)
            doc = CheckpointDocument(
                run=run,
                outputs=existing.outputs,
                coverage=existing.coverage,
                run_status=existing.run_status,
            )
        else:
            doc = CheckpointDocument(run=run)
        _write_document(store_dir, run.id, doc)
    return run


def transition(
    run_id: str,
    phase: PhaseName | str,
    new_status: PhaseStatus | str,
    *,
    allow_unblock: bool = False,
    store_dir: str | Path | None = None,
) -> RadarCycleRun:
    """Apply an allowed phase transition and atomically persist it.

    Delegates to :meth:`radar_cycles.models.PhaseCheckpoint.transition`, so an
    illegal transition (``completed -> running``, a second read-only retry, or
    ``blocked -> running`` without ``allow_unblock=True``) raises ``ValueError``
    and leaves the persisted checkpoint unchanged.
    """
    store_dir = _resolve_dir(store_dir)
    with _lock:
        doc = _read_document(store_dir, run_id)
        doc.run.checkpoint.transition(phase, new_status, allow_unblock=allow_unblock)
        doc.run.updated_at = _now()
        _write_document(store_dir, run_id, doc)
    return doc.run


def record_output(
    run_id: str,
    phase: PhaseName | str,
    path: str,
    *,
    store_dir: str | Path | None = None,
) -> RadarCycleRun:
    """Record that ``phase`` produced ``path`` and atomically persist it.

    Identical paths are not duplicated; order is preserved.
    """
    store_dir = _resolve_dir(store_dir)
    phase_key = PhaseName(phase).value
    with _lock:
        doc = _read_document(store_dir, run_id)
        paths = doc.outputs.setdefault(phase_key, [])
        if path not in paths:
            paths.append(path)
        doc.run.updated_at = _now()
        _write_document(store_dir, run_id, doc)
    return doc.run


def record_coverage(
    run_id: str,
    source_type: SourceType | str,
    status: SourceStatus | str,
    note: str = "",
    *,
    store_dir: str | Path | None = None,
) -> RadarCycleRun:
    """Append a ``SourceCoverage`` record for one source type and persist it."""
    store_dir = _resolve_dir(store_dir)
    coverage = SourceCoverage(
        source_type=SourceType(source_type),
        status=SourceStatus(status),
        note=note,
    )
    with _lock:
        doc = _read_document(store_dir, run_id)
        doc.coverage.append(coverage)
        doc.run.updated_at = _now()
        _write_document(store_dir, run_id, doc)
    return doc.run


def record_error(
    run_id: str,
    message: str,
    *,
    store_dir: str | Path | None = None,
) -> RadarCycleRun:
    """Append an error message to the checkpoint's error list and persist it."""
    store_dir = _resolve_dir(store_dir)
    with _lock:
        doc = _read_document(store_dir, run_id)
        doc.run.checkpoint.errors.append(message)
        doc.run.checkpoint.updated_at = _now()
        doc.run.updated_at = _now()
        _write_document(store_dir, run_id, doc)
    return doc.run


def finish(run_id: str, *, store_dir: str | Path | None = None) -> RadarCycleRun:
    """Mark the run complete (``run_status = "completed"``) and persist it."""
    store_dir = _resolve_dir(store_dir)
    with _lock:
        doc = _read_document(store_dir, run_id)
        doc.run_status = COMPLETED
        doc.run.updated_at = _now()
        _write_document(store_dir, run_id, doc)
    return doc.run


# ── read accessors ──

def outputs_of(
    run_id: str,
    *,
    store_dir: str | Path | None = None,
) -> dict[str, list[str]]:
    """Recorded output paths keyed by phase name (string)."""
    return load_document(run_id, store_dir=store_dir).outputs


def coverage_of(
    run_id: str,
    *,
    store_dir: str | Path | None = None,
) -> list[SourceCoverage]:
    """Recorded source coverage, in insertion order."""
    return load_document(run_id, store_dir=store_dir).coverage


def run_status_of(run_id: str, *, store_dir: str | Path | None = None) -> str:
    """``"running"`` or ``"completed"`` for the run."""
    return load_document(run_id, store_dir=store_dir).run_status


def exists(run_id: str, *, store_dir: str | Path | None = None) -> bool:
    """Whether a checkpoint file exists for ``run_id``."""
    return _path_for(_resolve_dir(store_dir), run_id).exists()
