"""Run workspace layout and persistence for repo-evolution-learning.

A run lives in ``<out_dir>/repo-learning/<run_id>/`` and holds:

- ``request.yaml``    — the resolved :class:`RequestSpec`
- ``sources.jsonl``   — :class:`SourceRecord` lines (GitHub + web content)
- ``search-log.jsonl``— :class:`SearchRecord` lines
- ``analysis.json``   — the skill-written :class:`Analysis`
- ``manifest.json``   — the :class:`RunManifest` checkpoint
- ``report.html``     — the rendered report

JSONL records delegate to ``state/jsonl.py`` (atomic append, idempotent dedup).
Single JSON files use a same-directory atomic write (mkstemp + fsync + os.replace).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from repo_learning.models import (
    Analysis,
    RunManifest,
    SearchRecord,
    SourceRecord,
)
from state.jsonl import ReadResult, append_line, read_jsonl

__all__ = [
    "REQUEST_FILE",
    "SOURCES_FILE",
    "SEARCH_LOG_FILE",
    "ANALYSIS_FILE",
    "MANIFEST_FILE",
    "REPORT_FILE",
    "atomic_write_json",
    "init_workspace",
    "append_source",
    "append_search",
    "read_sources",
    "read_search",
    "load_manifest",
    "save_manifest",
    "load_analysis",
]

REQUEST_FILE = "request.yaml"
SOURCES_FILE = "sources.jsonl"
SEARCH_LOG_FILE = "search-log.jsonl"
ANALYSIS_FILE = "analysis.json"
MANIFEST_FILE = "manifest.json"
REPORT_FILE = "report.html"


def atomic_write_json(path: Path, data: dict) -> None:
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


def init_workspace(run_dir: Path, request, manifest: RunManifest) -> Path:
    """Create the run workspace: write ``request.yaml`` and ``manifest.json``."""
    run_dir.mkdir(parents=True, exist_ok=True)
    from repo_learning.request import save_request

    save_request(run_dir, request)
    save_manifest(run_dir, manifest)
    return run_dir


# ── JSONL append / read ──


def append_source(run_dir: Path, record: SourceRecord) -> None:
    """Append one :class:`SourceRecord` line (atomic, O(1) per append)."""
    append_line(run_dir / SOURCES_FILE, record)


def append_search(run_dir: Path, record: SearchRecord) -> None:
    """Append one :class:`SearchRecord` line (atomic, O(1) per append)."""
    append_line(run_dir / SEARCH_LOG_FILE, record)


def read_sources(run_dir: Path) -> ReadResult[SourceRecord]:
    """Read ``sources.jsonl`` (dedup by id, collect corrupt lines)."""
    return read_jsonl(run_dir / SOURCES_FILE, SourceRecord)


def read_search(run_dir: Path) -> ReadResult[SearchRecord]:
    """Read ``search-log.jsonl`` (dedup by id, collect corrupt lines)."""
    return read_jsonl(run_dir / SEARCH_LOG_FILE, SearchRecord)


# ── Manifest / analysis ──


def load_manifest(run_dir: Path) -> RunManifest:
    path = run_dir / MANIFEST_FILE
    if not path.exists():
        raise FileNotFoundError(f"manifest.json not found in {run_dir}")
    return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))


def save_manifest(run_dir: Path, manifest: RunManifest) -> Path:
    path = run_dir / MANIFEST_FILE
    atomic_write_json(path, manifest.model_dump(mode="json"))
    return path


def load_analysis(run_dir: Path) -> Analysis:
    path = run_dir / ANALYSIS_FILE
    if not path.exists():
        raise FileNotFoundError(f"analysis.json not found in {run_dir}")
    return Analysis.model_validate_json(path.read_text(encoding="utf-8"))
