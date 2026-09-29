# Thin Agent Loop, Thick Control Plane — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic "investigation control plane" (`investigations/` module + `builderdna investigate` CLI) that lets the Agent dynamically decide its next Reddit pain-discovery action while the Python control plane owns source calls, budget, state, evidence thresholds, persistence, and recovery. Pilot on `reddit-opportunity`.

**Architecture:** Reuse the existing evidence contract (`SourceHandoffItem`), RSS normalization (`concepts/adapters/reddit.py`), and handoff (`concepts/handoffs.py`); extract the generic JSONL store mechanics into `state/jsonl.py` shared by `ConceptStore` and the new `InvestigationStore`. Build only the new pieces: investigation lifecycle, action contract, action executor, and `PainClusterCandidate`.

**Tech Stack:** Python 3.12, pydantic v2, Typer, pytest, stdlib-only RSS fetcher (`scripts/reddit_rss.py`). No new dependencies.

## Global Constraints

- Run all commands from the repo root with `PYTHONPATH=.` (per `CLAUDE.md`). Tests via `uv run pytest ...`.
- Timestamps must be timezone-aware UTC — use `UtcDatetime` from `models.concept` (it rejects naive/non-UTC datetimes).
- Evidence records are immutable; corrections append (`supersedes`), never edit history.
- Idempotency rule (from `concepts/store.py`): same ID + same payload = no-op; same ID + different payload = conflict. Write-only timestamp fields (`captured_at`/`recorded_at`) are ignored in the comparison.
- Acquisition is RSS-only for this plan. No comments, scores, votes, or removal data. No Reddit auth/credentials. No posting/replies.
- Budget defaults are **max 8 actions, max 3 evidence rounds, max 1 candidate per topic**, as configurable parameters — never hard-coded domain truths.
- CLI output is JSON-first; `--format md` is the only escape hatch (mirror `cli/commands/concept.py`).
- Exit codes mirror `concepts/service.py`: `0` success, `1` unexpected failure, `2` validation error, `3` conflict. Exit `4` is reserved/unused.
- P4 (`repo-trend`) and P5 (`builderdna` router) are **out of scope** for this plan — they are gated behind P3 results and get their own plans.

---

## File Structure

| File | Responsibility |
|---|---|
| `state/jsonl.py` | Generic append-only/snapshot JSONL mechanics (extracted from `concepts/store.py`) |
| `concepts/store.py` | `ConceptStore` refactored onto `state/jsonl.py` (behavior unchanged) |
| `investigations/__init__.py` | Package marker + re-exports |
| `investigations/models.py` | `Investigation`, `InvestigationBudget`, `ActionRecord`, `EvidenceRecord`, `PainClusterCandidate`, `InvestigationStatus` |
| `investigations/store.py` | `InvestigationStore` — JSONL persistence for the four record kinds |
| `investigations/contract.py` | Action request/response envelope, `canonicalize_params`, `allowed_next_actions`, status enum |
| `investigations/actions.py` | Action registry + executor: the 5 data actions (RSS-backed, injectable fetcher) |
| `investigations/service.py` | `InvestigationService`: `init` / `run_action` / `propose` / `finish` / `resume` / `status` |
| `cli/commands/investigate.py` | `investigate` Typer command group |
| `cli/main.py` | Register the `investigate` group |
| `.claude/skills/reddit-opportunity/SKILL.md` | Rewritten as the four-part thin loop (P2) |
| `state/replay/topics.json` | Frozen replay topic manifest (P0) |
| `scripts/replay_report.py` | P3 comparison reporter (deterministic metrics + human-annotation slots) |
| `tests/test_jsonl_store.py` | Tests for the shared `state/jsonl.py` |
| `tests/test_investigation/*.py` | Tests for models/store/contract/actions/service/CLI |

---

## Task 1: Extract `state/jsonl.py` (shared JSONL mechanics)

Move the generic JSONL helpers out of `concepts/store.py` into `state/jsonl.py`, and refactor `ConceptStore` to delegate to them. `ConceptStore` behavior must be identical — the existing `tests/test_concept_store.py` is the safety net.

**Files:**
- Create: `state/__init__.py` (empty package marker)
- Create: `state/jsonl.py`
- Modify: `concepts/store.py`
- Test: `tests/test_jsonl_store.py`

**Interfaces:**
- Produces (imported by Task 3's `InvestigationStore` and by `concepts/store.py`):
  - `read_jsonl(path: Path, model_cls: type[T]) -> ReadResult[T]`
  - `corruption_detected(result: ReadResult) -> bool`
  - `atomic_write(path: Path, records: list) -> None`
  - `append_line(path: Path, record) -> None`
  - `tail_parses(path: Path, model_cls: type[T]) -> bool`
  - `record_view(record) -> dict` (returns `model_dump(mode="json")` minus `captured_at`/`recorded_at`)
  - Types: `ReadResult(Generic[T])`, `CorruptLine`

- [ ] **Step 1: Write the failing test**

Create `tests/test_jsonl_store.py`:

```python
"""Tests for the shared JSONL store mechanics (state/jsonl.py)."""
import json
from pathlib import Path

from pydantic import BaseModel

from state.jsonl import (
    atomic_write,
    corruption_detected,
    read_jsonl,
    record_view,
    tail_parses,
)


class Row(BaseModel):
    id: str
    value: str


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def test_read_jsonl_skips_corrupt_and_dedups(tmp_path):
    path = tmp_path / "rows.jsonl"
    write_lines(
        path,
        [
            json.dumps({"id": "a", "value": "1"}),
            "not-json",
            json.dumps({"id": "a", "value": "2"}),  # duplicate id: last wins
            "",
            json.dumps({"id": "b", "value": "3"}),
        ],
    )
    result = read_jsonl(path, Row)
    assert [r.id for r in result.records] == ["a", "b"]
    assert result.records[0].value == "2"
    assert len(result.corrupt) == 1
    assert result.corrupt[0].line_no == 2
    assert result.total_lines == 4


def test_read_jsonl_missing_file_returns_empty(tmp_path):
    result = read_jsonl(tmp_path / "nope.jsonl", Row)
    assert result.records == []
    assert result.corrupt == []
    assert result.total_lines == 0


def test_corruption_detected_majority_corrupt(tmp_path):
    path = tmp_path / "rows.jsonl"
    write_lines(path, ["garbage", "also-garbage", json.dumps({"id": "a", "value": "1"})])
    result = read_jsonl(path, Row)
    assert corruption_detected(result) is True


def test_corruption_detected_clean(tmp_path):
    path = tmp_path / "rows.jsonl"
    write_lines(path, [json.dumps({"id": "a", "value": "1"})])
    result = read_jsonl(path, Row)
    assert corruption_detected(result) is False


def test_tail_parses_detects_malformed_tail(tmp_path):
    path = tmp_path / "rows.jsonl"
    write_lines(path, [json.dumps({"id": "a", "value": "1"}), "not-json"])
    assert tail_parses(path, Row) is False


def test_tail_parses_empty_or_valid(tmp_path):
    path = tmp_path / "rows.jsonl"
    write_lines(path, [json.dumps({"id": "a", "value": "1"})])
    assert tail_parses(path, Row) is True
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert tail_parses(empty, Row) is True


def test_atomic_write_round_trips(tmp_path):
    path = tmp_path / "rows.jsonl"
    rows = [Row(id="a", value="1"), Row(id="b", value="2")]
    atomic_write(path, rows)
    result = read_jsonl(path, Row)
    assert [r.id for r in result.records] == ["a", "b"]


def test_record_view_drops_write_timestamps():
    from datetime import datetime, timezone
    from models.concept import ConceptEvidence, Directness, EvidenceRole, EvidenceStrength, SourceType

    now = datetime.now(timezone.utc)
    e = ConceptEvidence(
        id="ev1", concept_id="c1", source_type=SourceType.REDDIT, source_url="https://x",
        role=EvidenceRole.PROBLEM, directness=Directness.DIRECT,
        strength=EvidenceStrength.WEAK, independence_key="k", captured_at=now,
    )
    view = record_view(e)
    assert "captured_at" not in view
    assert "recorded_at" not in view
    assert view["id"] == "ev1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_jsonl_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'state.jsonl'`

- [ ] **Step 3: Create `state/jsonl.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run pytest tests/test_jsonl_store.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Refactor `concepts/store.py` to delegate to `state/jsonl.py`**

Keep the public `ConceptStore` class and its error hierarchy (`ConceptStoreError`, `CorruptionError`, `DuplicateRecordError`, `ConflictError`) **unchanged**. Delete the private module-level mechanics (`_read_jsonl`, `_atomic_write`, `_append_line`, `_verify_tail_parses`, `_record_view`, `_WRITE_TIMESTAMP_FIELDS`, `ReadResult`, `CorruptLine`) and replace `_check_corruption`/`_verify_tail_parses` with thin wrappers over the shared predicates, raising the concept `CorruptionError`.

In `concepts/store.py`:

```python
from state.jsonl import (
    CorruptLine,
    ReadResult,
    atomic_write,
    append_line,
    corruption_detected,
    read_jsonl,
    record_view as _record_view,
    tail_parses,
)


def _check_corruption(path: Path, result: ReadResult) -> None:
    """Refuse to write when more than half of the existing lines are corrupt."""
    if corruption_detected(result):
        raise CorruptionError(
            f"refusing to write {path}: {len(result.corrupt)} of "
            f"{result.total_lines} non-empty lines are corrupt (more than half); "
            f"fix or restore the file before writing again"
        )


def _verify_tail_parses(path: Path, model_cls) -> None:
    """Confirm the last non-empty line parses; raise ``CorruptionError`` otherwise."""
    if not tail_parses(path, model_cls):
        raise CorruptionError(
            f"append verification failed for {path}: last line does not parse as {model_cls.__name__}"
        )
```

Then update `ConceptStore`'s method bodies to call the shared functions. The body of `_append_record` stays (it encodes the concept-specific idempotency *policy* and `ConflictError` hints); only its mechanics calls change:

```python
def _read(self, path, model_cls):
    result = read_jsonl(path, model_cls)
    self._last_read[path] = result
    return result

# inside _append_record:
result = self._read(path, model_cls)
_check_corruption(path, result)
# ... existing idempotent/conflict logic using _record_view(existing) == _record_view(record) ...
append_line(path, record)
_verify_tail_parses(path, model_cls)
```

Note: `ConceptStore.upsert_concept` already uses `_atomic_write`; rename its call to `atomic_write`. The old `_append_line` call becomes `append_line`; `_record_view` stays via the alias.

- [ ] **Step 6: Run the existing concept store tests**

Run: `PYTHONPATH=. uv run pytest tests/test_concept_store.py -v`
Expected: PASS — the refactor must not change `ConceptStore` behavior.

- [ ] **Step 7: Commit**

```bash
git add state/ concepts/store.py tests/test_jsonl_store.py
git commit -m "refactor(store): extract shared JSONL mechanics into state/jsonl.py"
```

---

## Task 2: `investigations/models.py` — domain models

**Files:**
- Create: `investigations/__init__.py`
- Create: `investigations/models.py`
- Test: `tests/test_investigation/__init__.py` (empty), `tests/test_investigation/test_models.py`

**Interfaces:**
- Produces (imported by store, contract, actions, service, CLI):
  - `InvestigationStatus(str, Enum)`: `OPEN="open"`, `PAUSED="paused"`, `COMPLETED="completed"`, `FAILED="failed"`
  - `InvestigationBudget(BaseModel)`: `max_actions: int = 8`, `max_evidence_rounds: int = 3`, `max_candidates: int = 1`, `actions_used: int = 0`, `evidence_rounds_used: int = 0`
  - `Investigation(BaseModel)`: `id`, `topic`, `subreddit: str = ""`, `created_at: UtcDatetime`, `updated_at: UtcDatetime`, `revision: int = 0`, `schema_version: int = 1`, `config_fingerprint: str = ""`, `budget: InvestigationBudget`, `status: InvestigationStatus = OPEN`, `checkpoint: str = ""`, `end_reason: str = ""`
  - `ActionRecord(BaseModel)`: `id`, `investigation_id`, `action`, `params: dict`, `canonical_params: str`, `reason: str = ""`, `uncertainty_to_reduce: str = ""`, `expected_revision: int`, `revision_after: int`, `status: str`, `observation: dict`, `remaining_budget: dict`, `allowed_next_actions: list[str]`, `created_at: UtcDatetime`
  - `EvidenceRecord(BaseModel)`: `id`, `investigation_id`, `item: SourceHandoffItem`, `created_at: UtcDatetime`
  - `PainClusterCandidate(BaseModel)`: `id`, `investigation_id`, `problem_statement`, `affected_scenarios: list[str]`, `evidence_ids: list[str]`, `time_span_start: str = ""`, `time_span_end: str = ""`, `workarounds: list[str]`, `counterevidence: list[str]`, `coverage_limits: list[str]`, `open_questions: list[str]`, `minimal_validation_action: str = ""`, `created_at: UtcDatetime`
  - Validation: `PainClusterCandidate.problem_statement` and `minimal_validation_action` are required (`min_length=1`); `EvidenceRecord` reuses `SourceHandoffItem` from `concepts.handoffs`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_investigation/test_models.py`:

```python
"""Tests for investigations/models.py."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from investigations.models import (
    ActionRecord,
    EvidenceRecord,
    Investigation,
    InvestigationBudget,
    InvestigationStatus,
    PainClusterCandidate,
)
from concepts.handoffs import SourceHandoffItem
from models.concept import Directness, EvidenceRole, EvidenceStrength, SourceType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_investigation_defaults():
    inv = Investigation(
        id="inv_1",
        topic="agent reliability",
        subreddit="AI_Agents",
        created_at=utc_now(),
        updated_at=utc_now(),
        budget=InvestigationBudget(),
    )
    assert inv.status == InvestigationStatus.OPEN
    assert inv.revision == 0
    assert inv.budget.max_actions == 8
    assert inv.budget.max_evidence_rounds == 3
    assert inv.budget.max_candidates == 1


def test_investigation_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        Investigation(
            id="inv_1",
            topic="x",
            created_at=datetime(2026, 9, 29),  # naive
            updated_at=datetime(2026, 9, 29),
            budget=InvestigationBudget(),
        )


def test_candidate_requires_problem_and_action():
    with pytest.raises(ValidationError):
        PainClusterCandidate(id="pc_1", investigation_id="inv_1", problem_statement="")
    with pytest.raises(ValidationError):
        PainClusterCandidate(
            id="pc_1", investigation_id="inv_1", problem_statement="p", minimal_validation_action=""
        )


def test_evidence_record_wraps_handoff_item():
    item = SourceHandoffItem(
        source=SourceType.REDDIT,
        role=EvidenceRole.PROBLEM,
        author="alice",
        url="https://www.reddit.com/r/SaaS/comments/x",
        excerpt="we keep copy-pasting onboarding",
        directness=Directness.DIRECT,
        strength=EvidenceStrength.MODERATE,
    )
    rec = EvidenceRecord(id="reddit:x", investigation_id="inv_1", item=item, created_at=utc_now())
    assert rec.item.role == EvidenceRole.PROBLEM


def test_action_record_round_trips():
    rec = ActionRecord(
        id="act_1",
        investigation_id="inv_1",
        action="search_discussions",
        params={"query": "onboarding"},
        canonical_params="search_discussions:onboarding",
        reason="gap: no independent cases",
        expected_revision=0,
        revision_after=1,
        status="completed",
        observation={"evidence_ids": ["reddit:a"], "summary": "2 posts"},
        remaining_budget={"actions": 7},
        allowed_next_actions=["inspect_thread"],
        created_at=utc_now(),
    )
    assert rec.status == "completed"
    assert rec.revision_after == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'investigations'`

- [ ] **Step 3: Write `investigations/__init__.py` and `investigations/models.py`**

`investigations/__init__.py`:

```python
"""Investigation control plane — deterministic action loop over Reddit pain discovery."""

from investigations.models import (
    ActionRecord,
    EvidenceRecord,
    Investigation,
    InvestigationBudget,
    InvestigationStatus,
    PainClusterCandidate,
)

__all__ = [
    "ActionRecord",
    "EvidenceRecord",
    "Investigation",
    "InvestigationBudget",
    "InvestigationStatus",
    "PainClusterCandidate",
]
```

`investigations/models.py`:

```python
"""Investigation control-plane domain models.

Mirrors the design spec's §4 "数据与状态". Timestamps use ``UtcDatetime`` from
``models.concept`` (rejects naive/non-UTC), and ``EvidenceRecord`` reuses
``SourceHandoffItem`` as the evidence contract rather than defining a parallel
model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from concepts.handoffs import SourceHandoffItem
from models.concept import UtcDatetime


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class InvestigationStatus(str, Enum):
    OPEN = "open"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestigationBudget(BaseModel):
    """Bounded action/evidence/candidate budget (configurable, not domain truth)."""

    max_actions: int = 8
    max_evidence_rounds: int = 3
    max_candidates: int = 1
    actions_used: int = 0
    evidence_rounds_used: int = 0


class Investigation(BaseModel):
    """One investigation: target, revision, budget, status, checkpoint, end reason."""

    id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    subreddit: str = ""
    created_at: UtcDatetime = Field(default_factory=_now_utc)
    updated_at: UtcDatetime = Field(default_factory=_now_utc)
    revision: int = 0
    schema_version: int = 1
    config_fingerprint: str = ""
    budget: InvestigationBudget = Field(default_factory=InvestigationBudget)
    status: InvestigationStatus = InvestigationStatus.OPEN
    checkpoint: str = ""
    end_reason: str = ""


class ActionRecord(BaseModel):
    """An append-only record of one validated action and its observation."""

    id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)
    canonical_params: str = ""
    reason: str = ""
    uncertainty_to_reduce: str = ""
    expected_revision: int = 0
    revision_after: int = 0
    status: str = Field(min_length=1)
    observation: dict = Field(default_factory=dict)
    remaining_budget: dict = Field(default_factory=dict)
    allowed_next_actions: list[str] = Field(default_factory=list)
    created_at: UtcDatetime = Field(default_factory=_now_utc)


class EvidenceRecord(BaseModel):
    """A collected evidence item (a ``SourceHandoffItem``) plus a stable store ID."""

    id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    item: SourceHandoffItem
    created_at: UtcDatetime = Field(default_factory=_now_utc)


class PainClusterCandidate(BaseModel):
    """A single-source discovery artifact — NOT a ``ConceptCard``.

    ``evidence_ids`` must each reference a real stored evidence record (traceability).
    ``coverage_limits`` and ``open_questions`` carry explicit unknowns.
    """

    id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    problem_statement: str = Field(min_length=1)
    affected_scenarios: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    time_span_start: str = ""
    time_span_end: str = ""
    workarounds: list[str] = Field(default_factory=list)
    counterevidence: list[str] = Field(default_factory=list)
    coverage_limits: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    minimal_validation_action: str = Field(min_length=1)
    created_at: UtcDatetime = Field(default_factory=_now_utc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_models.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add investigations/ tests/test_investigation/
git commit -m "feat(investigations): add control-plane domain models"
```

---

## Task 3: `investigations/store.py` — `InvestigationStore`

**Files:**
- Create: `investigations/store.py`
- Test: `tests/test_investigation/test_store.py`

**Interfaces:**
- Consumes: `state.jsonl` (read_jsonl, corruption_detected, atomic_write, append_line, tail_parses, record_view); `investigations.models`.
- Produces (imported by service/CLI/actions):
  - `InvestigationStore(state_dir: str | Path = "state")` → files under `<state_dir>/investigations/`
  - `list_investigations() -> list[Investigation]`
  - `get_investigation(id) -> Investigation | None`
  - `upsert_investigation(inv: Investigation) -> Investigation`
  - `add_action(record: ActionRecord) -> ActionRecord` (idempotent/conflict)
  - `list_actions(investigation_id: str | None = None) -> list[ActionRecord]`
  - `add_evidence(record: EvidenceRecord) -> EvidenceRecord` (idempotent/conflict)
  - `list_evidence(investigation_id: str | None = None) -> list[EvidenceRecord]`
  - `add_candidate(c: PainClusterCandidate) -> PainClusterCandidate` (idempotent/conflict)
  - `list_candidates(investigation_id: str | None = None) -> list[PainClusterCandidate]`
  - `corrupt_lines() -> list[CorruptLine]`
  - Errors: `InvestigationStoreError(Exception)`, `InvestigationConflictError(InvestigationStoreError)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_investigation/test_store.py`:

```python
"""Tests for investigations/store.py — idempotency, conflict, atomic writes."""
from datetime import datetime, timezone

import pytest

from concepts.handoffs import SourceHandoffItem
from investigations.models import (
    ActionRecord,
    EvidenceRecord,
    Investigation,
    InvestigationBudget,
    PainClusterCandidate,
)
from investigations.store import (
    InvestigationConflictError,
    InvestigationStore,
)
from models.concept import Directness, EvidenceRole, EvidenceStrength, SourceType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def store(tmp_path):
    return InvestigationStore(state_dir=tmp_path)


def make_inv(**overrides) -> Investigation:
    fields = dict(
        id="inv_1", topic="agent reliability", subreddit="AI_Agents",
        created_at=utc_now(), updated_at=utc_now(), budget=InvestigationBudget(),
    )
    fields.update(overrides)
    return Investigation(**fields)


def make_action(**overrides) -> ActionRecord:
    fields = dict(
        id="act_1", investigation_id="inv_1", action="search_discussions",
        params={}, canonical_params="", reason="", expected_revision=0,
        revision_after=1, status="completed", observation={},
        remaining_budget={}, allowed_next_actions=[], created_at=utc_now(),
    )
    fields.update(overrides)
    return ActionRecord(**fields)


def make_evidence(**overrides) -> EvidenceRecord:
    item = SourceHandoffItem(
        source=SourceType.REDDIT, role=EvidenceRole.PROBLEM, author="alice",
        url="https://www.reddit.com/r/SaaS/comments/x", excerpt="copy-paste onboarding",
        directness=Directness.DIRECT, strength=EvidenceStrength.MODERATE,
    )
    fields = dict(id="reddit:x", investigation_id="inv_1", item=item, created_at=utc_now())
    fields.update(overrides)
    return EvidenceRecord(**fields)


def test_upsert_investigation_preserves_created_at(store):
    inv = make_inv()
    store.upsert_investigation(inv)
    got = store.get_investigation("inv_1")
    assert got.id == "inv_1"
    assert got.status.value == "open"


def test_add_action_is_idempotent(store):
    store.upsert_investigation(make_inv())
    a = make_action()
    first = store.add_action(a)
    second = store.add_action(a)  # identical replay
    assert second is first or second == first
    assert len(store.list_actions("inv_1")) == 1


def test_add_action_conflict_on_same_id_different_payload(store):
    store.upsert_investigation(make_inv())
    store.add_action(make_action())
    with pytest.raises(InvestigationConflictError):
        store.add_action(make_action(status="no_results"))


def test_add_evidence_idempotent_and_filtered(store):
    store.upsert_investigation(make_inv())
    store.add_evidence(make_evidence())
    store.add_evidence(make_evidence())
    assert len(store.list_evidence("inv_1")) == 1
    assert store.list_evidence("other") == []


def test_add_candidate(store):
    store.upsert_investigation(make_inv())
    c = PainClusterCandidate(
        id="pc_1", investigation_id="inv_1", problem_statement="onboarding is manual",
        minimal_validation_action="count how many people already use a tool",
        evidence_ids=["reddit:x"], created_at=utc_now(),
    )
    store.add_candidate(c)
    assert len(store.list_candidates("inv_1")) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'investigations.store'`

- [ ] **Step 3: Write `investigations/store.py`**

```python
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
            if record_view(existing) == record_view(record):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_store.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add investigations/store.py tests/test_investigation/test_store.py
git commit -m "feat(investigations): add InvestigationStore on shared JSONL mechanics"
```

---

## Task 4: `investigations/contract.py` — action contract + allowed actions

**Files:**
- Create: `investigations/contract.py`
- Test: `tests/test_investigation/test_contract.py`

**Interfaces:**
- Consumes: `investigations.models` (for status checks only; the contract is pure).
- Produces (imported by actions, service, CLI):
  - `KNOWN_ACTIONS: frozenset[str]` = `{"search_discussions", "inspect_thread", "find_similar_cases", "seek_workaround", "seek_counterevidence", "propose_pain_cluster", "ask_user", "finish"}`
  - `DATA_ACTIONS: frozenset[str]` = the first five (executed by `actions.py`)
  - `ActionStatus(str, Enum)`: `COMPLETED="completed"`, `NO_RESULTS="no_results"`, `SOURCE_FAILURE="source_failure"`, `BUDGET_EXHAUSTED="budget_exhausted"`, `INVALID_ACTION="invalid_action"`, `STALE_REVISION="stale_revision"`
  - `ActionRequest(BaseModel)`: `schema_version: int = 1`, `investigation_id: str`, `expected_revision: int`, `action: str`, `params: dict = {}`, `reason: str = ""`, `uncertainty_to_reduce: str = ""`
  - `canonicalize_params(params: dict) -> str` — `json.dumps(params, sort_keys=True, separators=(",", ":"))`
  - `allowed_next_actions(status: str, actions_used: int, max_actions: int, has_candidate: bool, candidates_used: int, max_candidates: int) -> list[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_investigation/test_contract.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_contract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'investigations.contract'`

- [ ] **Step 3: Write `investigations/contract.py`**

```python
"""Action contract — request/response envelope, canonical params, allowed actions.

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_contract.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add investigations/contract.py tests/test_investigation/test_contract.py
git commit -m "feat(investigations): add action contract and allowed-next-actions"
```

---

## Task 5: `investigations/actions.py` — action executor (RSS-backed)

**Files:**
- Create: `investigations/actions.py`
- Test: `tests/test_investigation/test_actions.py`

**Interfaces:**
- Consumes: `scripts.reddit_rss` (`build_url`, `fetch`, `parse_atom`); `concepts.adapters.reddit` (`infer_directness`, `independence_key_for_post`); `concepts.handoffs` (`SourceHandoffItem`); `models.concept` (`SourceType`, `EvidenceRole`, `EvidenceStrength`, `Directness`).
- Produces (imported by service):
  - `Fetcher = Callable[[str, str, int], list[dict]]` — `(subreddit, sort, limit) -> posts`
  - `default_fetcher(subreddit, sort="new", limit=25) -> list[dict]`
  - `normalize_post(post: dict, investigation_id: str) -> EvidenceRecord`
  - `execute(action: str, params: dict, *, fetcher: Fetcher, evidence: list[EvidenceRecord]) -> dict` returning `{"status", "observation", "new_evidence": list[EvidenceRecord], "budget_delta": {"evidence_rounds": int}}`
  - Each data action maps to a deterministic executor function.

- [ ] **Step 1: Write the failing test**

Create `tests/test_investigation/test_actions.py`:

```python
"""Tests for investigations/actions.py — deterministic action executors."""
from investigations.actions import (
    execute,
    normalize_post,
)
from investigations.models import EvidenceRecord


SAMPLE_POST = {
    "id": "abc123",
    "title": "We keep copy-pasting onboarding steps",
    "author": "alice",
    "permalink": "https://www.reddit.com/r/SaaS/comments/abc123/onboarding",
    "published": "2026-09-01T10:00:00Z",
    "selftext": "Every new customer we copy-paste the same steps. It's manual and error-prone.",
    "category": "",
}


def test_normalize_post_builds_evidence_record():
    rec = normalize_post(SAMPLE_POST, "inv_1")
    assert isinstance(rec, EvidenceRecord)
    assert rec.investigation_id == "inv_1"
    assert rec.item.source.value == "reddit"
    assert rec.item.url == SAMPLE_POST["permalink"]
    assert rec.item.author == "alice"
    # first-person body -> DIRECT
    assert rec.item.directness.value == "direct"


def test_search_discussions_no_results():
    def empty_fetcher(subreddit, sort, limit):
        return []

    out = execute("search_discussions", {"subreddit": "SaaS"}, fetcher=empty_fetcher, evidence=[])
    assert out["status"] == "no_results"
    assert out["new_evidence"] == []


def test_search_discussions_collects_posts():
    def two_fetcher(subreddit, sort, limit):
        return [SAMPLE_POST, {**SAMPLE_POST, "id": "def456"}]

    out = execute("search_discussions", {"subreddit": "SaaS"}, fetcher=two_fetcher, evidence=[])
    assert out["status"] == "completed"
    assert len(out["new_evidence"]) == 2
    ids = {e.id for e in out["new_evidence"]}
    assert ids == {"reddit:abc123", "reddit:def456"}


def test_search_discussions_dedupes_against_existing():
    existing = normalize_post(SAMPLE_POST, "inv_1")

    def one_fetcher(subreddit, sort, limit):
        return [SAMPLE_POST]

    out = execute("search_discussions", {"subreddit": "SaaS"}, fetcher=one_fetcher, evidence=[existing])
    assert out["status"] == "no_results"  # only post already known
    assert out["new_evidence"] == []


def test_search_discussions_source_failure():
    def failing_fetcher(subreddit, sort, limit):
        raise RuntimeError("network down")

    out = execute("search_discussions", {"subreddit": "SaaS"}, fetcher=failing_fetcher, evidence=[])
    assert out["status"] == "source_failure"


def test_find_similar_cases_groups_by_independence_key():
    a = normalize_post(SAMPLE_POST, "inv_1")
    # second post cites the same upstream URL -> shares independence key
    repost = {**SAMPLE_POST, "id": "xyz", "selftext": "repost of https://github.com/acme/tool"}
    b = normalize_post(repost, "inv_1")
    out = execute("find_similar_cases", {}, fetcher=None, evidence=[a, b])
    assert out["status"] == "completed"
    keys = {g["independence_key"] for g in out["observation"]["groups"]}
    assert keys == {a.item.independence_key}


def test_seek_counterevidence_records_coverage():
    out = execute("seek_counterevidence", {"query": "existing tool"}, fetcher=None, evidence=[])
    assert out["status"] == "completed"
    assert "coverage" in out["observation"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_actions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'investigations.actions'`

- [ ] **Step 3: Write `investigations/actions.py`**

```python
"""Action executor — maps domain actions to deterministic RSS-backed operations.

The control plane executes the *mechanism* (fetch, group, search, record); the
Agent supplies the *judgment* (which gap to pursue, what counts as a workaround).
Each action returns ``{"status", "observation", "new_evidence", "budget_delta"}``.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable

from concepts.adapters.reddit import independence_key_for_post, infer_directness
from concepts.handoffs import SourceHandoffItem
from investigations.models import EvidenceRecord
from models.concept import Directness, EvidenceRole, EvidenceStrength, SourceType

Fetcher = Callable[[str, str, int], list[dict]]

_WORKAROUND_MARKERS = re.compile(
    r"\b(?:workaround|worked around|we use|i use|we use|using|temporarily|"
    r"manual|spreadsheet|zapier|copy-paste|copy paste|hack)\b",
    re.IGNORECASE,
)
_COUNTER_MARKERS = re.compile(
    r"\b(?:already exists|solved|solution exists|there's a tool|there is a tool|"
    r"built-in|out of the box|paid for)\b",
    re.IGNORECASE,
)


def default_fetcher(subreddit: str, sort: str = "new", limit: int = 25) -> list[dict]:
    """Fetch and parse a subreddit's RSS feed via the stdlib helper."""
    from scripts.reddit_rss import build_url, fetch, parse_atom

    xml_text = fetch(build_url(subreddit, sort, limit))
    return parse_atom(xml_text)


def _post_text(post: dict) -> str:
    return " ".join(str(post.get(k) or "") for k in ("title", "selftext", "body"))


def normalize_post(post: dict, investigation_id: str) -> EvidenceRecord:
    """Normalize one RSS post into an ``EvidenceRecord`` (a ``SourceHandoffItem``)."""
    raw_id = str(post.get("id") or "").strip()
    directness = infer_directness(post)
    item = SourceHandoffItem(
        source=SourceType.REDDIT,
        role=EvidenceRole.PROBLEM,
        author=str(post.get("author") or ""),
        url=str(post.get("permalink") or ""),
        published_at=_parse_published(post.get("published")),
        excerpt=_post_text(post)[:500],
        directness=directness,
        strength=EvidenceStrength.MODERATE if directness == Directness.DIRECT else EvidenceStrength.WEAK,
        independence_key=independence_key_for_post(post),
    )
    return EvidenceRecord(
        id=f"reddit:{raw_id}", investigation_id=investigation_id, item=item,
    )


def _parse_published(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


# ── Action executors ──

def _search_discussions(params, fetcher, evidence, investigation_id):
    subreddit = str(params.get("subreddit") or "").strip()
    if not subreddit:
        return {"status": "invalid_action", "observation": {"summary": "missing subreddit"}, "new_evidence": [], "budget_delta": {}}
    sort = params.get("sort", "new")
    limit = int(params.get("limit", 25))
    try:
        posts = fetcher(subreddit, sort, limit)
    except Exception as exc:  # network / HTTP / parse
        return {"status": "source_failure", "observation": {"summary": str(exc)}, "new_evidence": [], "budget_delta": {"evidence_rounds": 1}}
    known_ids = {e.id for e in evidence}
    new_evidence: list[EvidenceRecord] = []
    for post in posts:
        rec = normalize_post(post, investigation_id)
        if rec.id not in known_ids:
            new_evidence.append(rec)
            known_ids.add(rec.id)
    if not new_evidence:
        return {"status": "no_results", "observation": {"summary": "no new posts"}, "new_evidence": [], "budget_delta": {"evidence_rounds": 1}}
    return {"status": "completed", "observation": {"evidence_ids": [e.id for e in new_evidence], "summary": f"{len(new_evidence)} new posts"}, "new_evidence": new_evidence, "budget_delta": {"evidence_rounds": 1}}


def _inspect_thread(params, fetcher, evidence):
    target = str(params.get("permalink") or params.get("id") or "").strip()
    if not target:
        return {"status": "invalid_action", "observation": {"summary": "missing permalink/id"}, "new_evidence": [], "budget_delta": {}}
    for rec in evidence:
        if rec.item.url == target or rec.id == target or rec.id == f"reddit:{target}":
            return {"status": "completed", "observation": {"post": rec.item.model_dump(mode="json")}, "new_evidence": [], "budget_delta": {}}
    return {"status": "no_results", "observation": {"summary": "thread not in collected evidence"}, "new_evidence": [], "budget_delta": {}}


def _find_similar_cases(params, fetcher, evidence):
    groups: dict[str, dict] = defaultdict(lambda: {"independence_key": "", "count": 0, "authors": set(), "ids": []})
    for rec in evidence:
        key = rec.item.independence_key
        g = groups[key]
        g["independence_key"] = key
        g["count"] += 1
        g["ids"].append(rec.id)
        if rec.item.author:
            g["authors"].add(rec.item.author)
    out = []
    for g in groups.values():
        out.append({
            "independence_key": g["independence_key"],
            "count": g["count"],
            "authors": sorted(g["authors"]),
            "evidence_ids": g["ids"],
        })
    return {"status": "completed", "observation": {"groups": out}, "new_evidence": [], "budget_delta": {}}


def _seek_workaround(params, fetcher, evidence):
    matches = []
    for rec in evidence:
        text = rec.item.excerpt
        if _WORKAROUND_MARKERS.search(text):
            matches.append({
                "evidence_id": rec.id,
                "excerpt": text,
                "directness": rec.item.directness.value,
            })
    return {"status": "completed", "observation": {"matches": matches}, "new_evidence": [], "budget_delta": {}}


def _seek_counterevidence(params, fetcher, evidence):
    matches = []
    for rec in evidence:
        if _COUNTER_MARKERS.search(rec.item.excerpt):
            matches.append({"evidence_id": rec.id, "excerpt": rec.item.excerpt})
    return {
        "status": "completed",
        "observation": {
            "found": bool(matches),
            "matches": matches,
            "coverage": f"searched {len(evidence)} collected posts for solution markers; comments not read",
        },
        "new_evidence": [],
        "budget_delta": {},
    }


_EXECUTORS = {
    "search_discussions": _search_discussions,
    "inspect_thread": _inspect_thread,
    "find_similar_cases": _find_similar_cases,
    "seek_workaround": _seek_workaround,
    "seek_counterevidence": _seek_counterevidence,
}


def execute(action: str, params: dict, *, fetcher: Fetcher, evidence: list[EvidenceRecord], investigation_id: str = "") -> dict:
    executor = _EXECUTORS.get(action)
    if executor is None:
        return {"status": "invalid_action", "observation": {"summary": f"unknown action {action!r}"}, "new_evidence": [], "budget_delta": {}}
    if action == "search_discussions":
        return executor(params, fetcher, evidence, investigation_id)
    return executor(params, fetcher, evidence)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_actions.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add investigations/actions.py tests/test_investigation/test_actions.py
git commit -m "feat(investigations): add RSS-backed action executor"
```

---

## Task 6: `investigations/service.py` — `InvestigationService`

The service is the thin deterministic orchestrator: validate → execute → persist → respond. It owns the revision counter, budget accounting, idempotent retry, `stale_revision` detection, candidate validation, and `ask_user`/`finish`.

**Files:**
- Create: `investigations/service.py`
- Test: `tests/test_investigation/test_service.py`

**Interfaces:**
- Consumes: `investigations.store`, `investigations.models`, `investigations.contract`, `investigations.actions`.
- Produces (imported by CLI):
  - `InvestigationServiceError(Exception)`; `InvestigationValidationError` (exit 2)
  - `InvestigationService(store: InvestigationStore, fetcher: Fetcher | None = None)`
  - `init(topic, subreddit="", budget: InvestigationBudget | None = None) -> dict` — returns `{"investigation": ..., "allowed_actions": [...]}`
  - `run_action(request: ActionRequest) -> dict` — returns the response envelope: `{"status", "revision", "observation", "remaining_budget", "allowed_next_actions"}`
  - `propose(investigation_id, candidate: PainClusterCandidate) -> dict`
  - `finish(investigation_id, reason) -> dict`
  - `resume(investigation_id) -> dict`
  - `status(investigation_id) -> dict`
  - Retry semantics: same `(investigation_id, revision, action, canonical_params)` returns the already-saved result (idempotent), without re-calling the source.

- [ ] **Step 1: Write the failing test**

Create `tests/test_investigation/test_service.py`:

```python
"""Tests for investigations/service.py — the deterministic loop orchestrator."""
from datetime import datetime, timezone

import pytest

from investigations.contract import ActionRequest
from investigations.models import (
    InvestigationBudget,
    PainClusterCandidate,
)
from investigations.service import (
    InvestigationService,
    InvestigationValidationError,
)
from investigations.store import InvestigationStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


SAMPLE_POSTS = [
    {
        "id": "p1", "title": "I keep copy-pasting onboarding", "author": "alice",
        "permalink": "https://www.reddit.com/r/SaaS/comments/p1", "published": "2026-09-01T10:00:00Z",
        "selftext": "Every customer we copy-paste the same steps.", "category": "",
    },
    {
        "id": "p2", "title": "same onboarding pain", "author": "bob",
        "permalink": "https://www.reddit.com/r/startups/comments/p2", "published": "2026-09-02T10:00:00Z",
        "selftext": "we copy-paste onboarding too.", "category": "",
    },
]


@pytest.fixture
def service(tmp_path):
    store = InvestigationStore(state_dir=tmp_path)

    def fetcher(subreddit, sort, limit):
        return list(SAMPLE_POSTS)

    return InvestigationService(store, fetcher=fetcher)


def test_init_creates_investigation(service):
    out = service.init("agent reliability", subreddit="AI_Agents")
    inv = out["investigation"]
    assert inv["status"] == "open"
    assert "search_discussions" in out["allowed_actions"]


def test_run_action_advances_revision_and_budget(service):
    service.init("agent reliability", subreddit="AI_Agents")
    req = ActionRequest(investigation_id="inv_1", expected_revision=0,
                        action="search_discussions", params={"subreddit": "AI_Agents"},
                        reason="gap: no independent cases")
    resp = service.run_action(req)
    assert resp["status"] == "completed"
    assert resp["revision"] == 1
    assert resp["remaining_budget"]["actions"] == 7


def test_run_action_stale_revision_is_rejected(service):
    service.init("agent reliability", subreddit="AI_Agents")
    service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                     action="search_discussions", params={"subreddit": "AI_Agents"}))
    # stale: a NEW action submitted against the now-outdated revision 0
    resp = service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                            action="seek_counterevidence", params={}))
    assert resp["status"] == "stale_revision"


def test_run_action_idempotent_retry(service):
    service.init("agent reliability", subreddit="AI_Agents")
    req = ActionRequest(investigation_id="inv_1", expected_revision=0,
                        action="search_discussions", params={"subreddit": "AI_Agents"})
    first = service.run_action(req)
    # retry same request (same revision+action+canonical params) -> same result, no new source call
    second = service.run_action(req)
    assert first["revision"] == second["revision"]
    assert first["observation"] == second["observation"]


def test_run_action_unknown_action_rejected(service):
    service.init("agent reliability", subreddit="AI_Agents")
    req = ActionRequest(investigation_id="inv_1", expected_revision=0, action="rm_rf")
    resp = service.run_action(req)
    assert resp["status"] == "invalid_action"


def test_propose_validates_evidence_traceability(service):
    service.init("agent reliability", subreddit="AI_Agents")
    service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                     action="search_discussions", params={"subreddit": "AI_Agents"}))
    good = PainClusterCandidate(
        id="pc_1", investigation_id="inv_1", problem_statement="onboarding is manual",
        minimal_validation_action="ask 5 founders if they'd pay",
        evidence_ids=["reddit:p1", "reddit:p2"],
    )
    out = service.propose("inv_1", good)
    assert out["action"] == "candidate_saved"


def test_propose_rejects_fabricated_evidence(service):
    service.init("agent reliability", subreddit="AI_Agents")
    bad = PainClusterCandidate(
        id="pc_1", investigation_id="inv_1", problem_statement="onboarding is manual",
        minimal_validation_action="x", evidence_ids=["reddit:not_real"],
    )
    with pytest.raises(InvestigationValidationError):
        service.propose("inv_1", bad)


def test_finish_sets_completed_and_checkpoint(service):
    service.init("agent reliability", subreddit="AI_Agents")
    service.run_action(ActionRequest(investigation_id="inv_1", expected_revision=0,
                                     action="search_discussions", params={"subreddit": "AI_Agents"}))
    out = service.finish("inv_1", "low information gain")
    assert out["investigation"]["status"] == "completed"
    assert out["investigation"]["end_reason"] == "low information gain"
    assert out["investigation"]["checkpoint"]  # last action id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'investigations.service'`

- [ ] **Step 3: Write `investigations/service.py`**

```python
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
```

Note on `init`: it hard-codes `id="inv_1"` in this first version. A later task (CLI or a follow-up) may add `--id`; the pilot is single-user and one topic at a time, so `inv_1` plus idempotent re-init is sufficient and keeps retry deterministic. (If a second investigation is needed, `init` can accept an explicit `investigation_id` — flag this as a known limitation, not a bug.)

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_service.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add investigations/service.py tests/test_investigation/test_service.py
git commit -m "feat(investigations): add InvestigationService orchestrator"
```

---

## Task 7: `cli/commands/investigate.py` — CLI command group

**Files:**
- Create: `cli/commands/investigate.py`
- Modify: `cli/main.py` (register the group)
- Test: `tests/test_investigation/test_cli_investigate.py`

**Interfaces:**
- Consumes: `investigations.service`, `investigations.store`, `investigations.models`.
- Produces: `investigate` Typer group with subcommands `init`, `run`, `status`, `propose`, `finish`, `resume`. Registered in `cli/main.py` via `app.add_typer(investigate, name="investigate")`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_investigation/test_cli_investigate.py`:

```python
"""Tests for the investigate CLI command group (via Typer CliRunner)."""
import json

import pytest
from typer.testing import CliRunner

from cli.commands.investigate import investigate

runner = CliRunner()


def test_init_prints_json(tmp_path):
    result = runner.invoke(investigate, ["init", "--topic", "agent reliability", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["investigation"]["id"] == "inv_1"


def test_init_requires_topic(tmp_path):
    result = runner.invoke(investigate, ["init", "--state-dir", str(tmp_path)])
    assert result.exit_code == 2  # validation error


def test_run_action_round_trip(tmp_path):
    runner.invoke(investigate, ["init", "--topic", "agent reliability", "--state-dir", str(tmp_path)])
    result = runner.invoke(
        investigate,
        ["run", "--id", "inv_1", "--action", "ask_user", "--reason", "fork to user", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["status"] == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_cli_investigate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.commands.investigate'`

- [ ] **Step 3: Write `cli/commands/investigate.py`**

```python
"""investigate — deterministic Reddit pain-discovery action loop.

Thin Typer layer over :class:`investigations.service.InvestigationService`. All
business logic lives in the service; this module parses options, delegates, and
renders a JSON-first envelope (mirroring ``cli/commands/concept.py``).

Exit codes: 0 success, 1 unexpected failure, 2 validation error, 3 conflict.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer

from investigations.models import InvestigationBudget, PainClusterCandidate
from investigations.service import (
    InvestigationService,
    InvestigationServiceError,
    InvestigationValidationError,
)
from investigations.store import (
    InvestigationConflictError,
    InvestigationStore,
    InvestigationStoreError,
)
from observability import RunTelemetry

SCHEMA_VERSION = "builderdna.investigate.v1"

investigate = typer.Typer(
    name="investigate",
    help="Run a bounded, deterministic Reddit pain-discovery investigation.",
    no_args_is_help=True,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(command: str, data: dict) -> dict:
    return {"schema": SCHEMA_VERSION, "command": command, "ok": True, "data": data, "computed_at": _now_iso()}


def _error(command: str, message: str, exit_code: int) -> dict:
    return {"schema": SCHEMA_VERSION, "command": command, "ok": False, "error": message, "exit_code": exit_code, "computed_at": _now_iso()}


def _finalize(command: str, func) -> None:
    tel = RunTelemetry()
    try:
        payload = _ok(command, func())
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    except InvestigationValidationError as exc:
        print(json.dumps(_error(command, exc.message, exc.exit_code), indent=2, ensure_ascii=False))
        raise typer.Exit(exc.exit_code)
    except InvestigationConflictError as exc:
        print(json.dumps(_error(command, str(exc), 3), indent=2, ensure_ascii=False))
        raise typer.Exit(3)
    except InvestigationServiceError as exc:
        print(json.dumps(_error(command, str(exc), exc.exit_code), indent=2, ensure_ascii=False))
        raise typer.Exit(exc.exit_code)
    except InvestigationStoreError as exc:
        print(json.dumps(_error(command, str(exc), 1), indent=2, ensure_ascii=False))
        raise typer.Exit(1)
    except ValueError as exc:
        print(json.dumps(_error(command, str(exc), 1), indent=2, ensure_ascii=False))
        raise typer.Exit(1)


def _make_service(state_dir: str, fetcher=None) -> InvestigationService:
    return InvestigationService(InvestigationStore(state_dir=state_dir), fetcher=fetcher)


@investigate.command("init")
def init_cmd(
    topic: str = typer.Option(..., "--topic", "-t", help="Investigation topic / target"),
    subreddit: str = typer.Option("", "--subreddit", "-s", help="Subreddit name without r/"),
    state_dir: str = typer.Option("state", "--state-dir", help="Investigation store directory"),
) -> None:
    """Create an investigation and print its state plus available actions."""
    service = _make_service(state_dir)
    _finalize("investigate.init", lambda: service.init(topic, subreddit=subreddit))


@investigate.command("run")
def run_cmd(
    action: str = typer.Option(..., "--action", "-a", help="Action to run"),
    investigation_id: str = typer.Option("inv_1", "--id", help="Investigation ID"),
    expected_revision: int = typer.Option(0, "--expected-revision", help="Revision the agent is responding to"),
    params: str = typer.Option("{}", "--params", help="JSON object of action params"),
    reason: str = typer.Option("", "--reason", help="Why this action (evidence gap)"),
    uncertainty_to_reduce: str = typer.Option("", "--uncertainty-to-reduce", help="What uncertainty this reduces"),
    state_dir: str = typer.Option("state", "--state-dir", help="Investigation store directory"),
) -> None:
    """Validate and run one action, returning the observation envelope."""
    from investigations.contract import ActionRequest

    try:
        params_dict = json.loads(params)
    except json.JSONDecodeError as exc:
        raise InvestigationValidationError(f"invalid --params JSON: {exc}")
    request = ActionRequest(
        investigation_id=investigation_id,
        expected_revision=expected_revision,
        action=action,
        params=params_dict,
        reason=reason,
        uncertainty_to_reduce=uncertainty_to_reduce,
    )
    service = _make_service(state_dir)
    _finalize("investigate.run", lambda: service.run_action(request))


@investigate.command("status")
def status_cmd(
    investigation_id: str = typer.Option("inv_1", "--id", help="Investigation ID"),
    state_dir: str = typer.Option("state", "--state-dir", help="Investigation store directory"),
) -> None:
    """Show investigation state, action log summary, and candidates."""
    service = _make_service(state_dir)
    _finalize("investigate.status", lambda: service.status(investigation_id))


@investigate.command("propose")
def propose_cmd(
    candidate: str = typer.Option(..., "--candidate", help="Path to a JSON PainClusterCandidate"),
    investigation_id: str = typer.Option("inv_1", "--id", help="Investigation ID"),
    state_dir: str = typer.Option("state", "--state-dir", help="Investigation store directory"),
) -> None:
    """Validate and persist a PainClusterCandidate (every fact must trace to evidence)."""
    path = Path(candidate)
    if not path.exists():
        raise InvestigationValidationError(f"candidate file not found: {candidate}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvestigationValidationError(f"invalid candidate JSON: {exc}")
    data["investigation_id"] = investigation_id
    try:
        model = PainClusterCandidate(**data)
    except Exception as exc:
        raise InvestigationValidationError(f"invalid candidate: {exc}")
    service = _make_service(state_dir)
    _finalize("investigate.propose", lambda: service.propose(investigation_id, model))


@investigate.command("finish")
def finish_cmd(
    reason: str = typer.Option(..., "--reason", "-r", help="Why the investigation ends"),
    investigation_id: str = typer.Option("inv_1", "--id", help="Investigation ID"),
    state_dir: str = typer.Option("state", "--state-dir", help="Investigation store directory"),
) -> None:
    """Complete the investigation with a recorded end reason."""
    service = _make_service(state_dir)
    _finalize("investigate.finish", lambda: service.finish(investigation_id, reason))


@investigate.command("resume")
def resume_cmd(
    investigation_id: str = typer.Option("inv_1", "--id", help="Investigation ID"),
    state_dir: str = typer.Option("state", "--state-dir", help="Investigation store directory"),
) -> None:
    """Resume a paused investigation."""
    service = _make_service(state_dir)
    _finalize("investigate.resume", lambda: service.resume(investigation_id))
```

- [ ] **Step 4: Register the group in `cli/main.py`**

Add `from cli.commands.investigate import investigate` near the other command imports, and register with `app.add_typer(investigate, name="investigate")` next to the other `add_typer` calls.

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_cli_investigate.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the full investigation test suite**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/ tests/test_jsonl_store.py tests/test_concept_store.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add cli/commands/investigate.py cli/main.py tests/test_investigation/test_cli_investigate.py
git commit -m "feat(cli): add builderdna investigate command group"
```

---

## Task 8: Rewrite `reddit-opportunity/SKILL.md` as the thin loop (P2)

This is a prompt rewrite, not code — the deliverable is a new `SKILL.md` whose fixed recipe is replaced by the four-part loop over `builderdna investigate`.

**Files:**
- Modify: `.claude/skills/reddit-opportunity/SKILL.md`

**Interfaces:**
- Consumes: `builderdna investigate init/run/status/propose/finish` (from Task 7).

- [ ] **Step 1: Replace the SKILL.md body**

Replace the file with this four-part structure (goal, available actions, stop condition, output requirements). Keep the frontmatter and the "does / does not" routing table; delete the long fixed steps (fetch → filter → profile → pain → rank → concept → write output) and replace them with the loop.

```markdown
---
name: reddit-opportunity
description: >
  ALWAYS use this skill when the user wants to discover product opportunities or pain points
  from a Reddit community and they do NOT yet have a product. Use when the user says
  "find problems people will pay to solve", "what should I build from r/...",
  "reddit opportunity", "discover product ideas from a subreddit", "需求发现",
  "从 Reddit 找商机", or asks to monitor/analyze a subreddit for recurring complaints.
  Runs a bounded, deterministic investigation loop over a subreddit's public RSS feed
  (no API key, no scraper): the control plane owns source calls, budget, state, and
  evidence thresholds; you decide the next action from evidence. RSS returns posts only —
  no comments, no scores. After every run, present the pain cluster and ask whether to
  deep-dive.
---

# reddit-opportunity Skill

You discover product opportunities from a Reddit community when the user has **no product yet**.
You run a **thin agent loop over a thick control plane**: `builderdna investigate` owns source
calls, budget, state, and persistence; you own the judgment — which evidence gap to close next.

## 这个 Skill 做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 从 Reddit 发现重复痛点与付费意愿，产出 PainCluster 候选 | 回复帖子、私信、获客（超出本项目范围）|
| 通过 `investigate` 控制面动态决定下一步动作 | 从 X 学习技术信号（那是 twitter-learning 的事）|
| 把被选中的候选交给 concept radar 做跨源验证 | 跨源验证概念（那是 concept-radar 的事）|

## 目标 (Goal)

用尽量少的动作，确定一个**可行动、可验证**的痛点候选：明确受影响场景 + 最小验证动作，
而不是一篇更长的报告。默认预算：最多 8 个动作、最多 3 轮补证、每个主题最多 1 个候选
（这些是可配置参数，不是领域真理）。

## 可用动作 (Available actions)

先 `init`，然后每轮从控制面返回的 `allowed_next_actions` 里选一个动作：

- `search_discussions` — 扩展相关讨论（`--params '{"subreddit":"X","sort":"new","limit":25}'`）
- `inspect_thread` — 深读一个已采集的讨论（完整 selftext + 链接的上游来源）
- `find_similar_cases` — 检查重复是否来自独立讨论（按共同上游去重）
- `seek_workaround` — 查用户当前如何解决（保留原文，区分真实实践 vs 建议）
- `seek_counterevidence` — 找"问题不成立/已经解决"的证据
- `propose_pain_cluster` — 提交结构化候选（每个事实必须可追溯到已采集证据）
- `ask_user` / `finish` — 关键分歧交给用户，或结束并记录原因

每条动作的理由必须指向**具体证据缺口**，禁止写"继续搜索"这类泛词。

命令映射：数据动作和 `ask_user` 走 `investigate run --action <action>`；`propose_pain_cluster`
走 `investigate propose --candidate <file>`；`finish` 走 `investigate finish --reason ...`。

## 停止条件 (Stop condition)

满足任一即结束：

1. 信息收益低——新一轮动作不再改变痛点判断；
2. 动作预算或补证轮数用尽；
3. 已找到明确反证或成熟解法，候选降级为"待验证/不成立"；
4. 候选的证据已可追溯、覆盖限制已写明。

诚实报告缺口：没有可靠证据就结束为"待验证"，不要强行生成机会。

## 输出要求 (Output requirements)

1. 用 `investigate propose` 提交 PainClusterCandidate，字段：问题陈述、受影响场景、
   独立案例（evidence_ids）、时间跨度、workaround、反证、样本/覆盖限制、未解决问题、
   最小验证动作。
2. 向用户呈现：扫描摘要 → 排序后的痛点 → "要深入哪个？报数字。"
3. 明确写出"评论未读"（RSS 只给帖子，不给评论/分数），不得把 RSS 结果说成社区共识或生产验证。
4. 单源强信号可以形成候选，但**不能**自行满足 concept-radar 的跨源 BUILD 门槛。

## 循环 (Loop)

```text
用户目标 → investigate init（拿到状态+可用动作）
→ 选一个动作并给理由 → investigate run（校验/执行/持久化，返回 observation + allowed_next_actions）
→ 决定继续 / ask_user / finish
→ investigate propose 提交候选（控制面校验可追溯性）
```

## Guardrails

- 只读公开帖子、只写本地状态，绝不发帖。
- 候选是给用户验证的；不部署、不收款。
- 被用户选中的候选，走 `concepts.adapters.reddit` / `concepts.handoffs` 交给 concept radar
  （`comments_read: false`，`independence_key` 按共同上游去重，绝不把转述算成多个案例）。
```

- [ ] **Step 2: Smoke-check the skill drives the CLI**

Run the loop once by hand to confirm the command names/flags match Task 7:

```bash
PYTHONPATH=. uv run builderdna investigate init --topic "agent reliability" --subreddit AI_Agents
PYTHONPATH=. uv run builderdna investigate run --id inv_1 --action finish --reason "smoke"
```

Expected: `init` prints `ok: true` with `allowed_actions`; `run ... finish` prints `status: completed`.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/reddit-opportunity/SKILL.md
git commit -m "docs(reddit-opportunity): rewrite SKILL.md as thin loop over investigate"
```

---

## Task 9: Replay manifest + comparison reporter (P0/P3 software)

The human-annotation parts of P0/P3 are process steps the user performs; this task builds the deterministic software that captures and compares the run metrics: a frozen topic manifest and a reporter that computes source calls, evidence-independence collisions, counterevidence coverage, and candidate count from a run's store.

**Files:**
- Create: `state/replay/topics.json`
- Create: `scripts/replay_report.py`
- Test: `tests/test_investigation/test_replay_report.py`

**Interfaces:**
- Produces: `scripts/replay_report.py --new <state_dir> --out <report.json>` computes, from an `InvestigationStore` under `<state_dir>`, the deterministic P3 metrics and writes a JSON report with human-annotation slots.

- [ ] **Step 1: Write the frozen topic manifest**

Create `state/replay/topics.json`:

```json
{
  "schema_version": 1,
  "topics": [
    {"topic": "onboarding automation", "subreddit": "SaaS", "category": "recurring_pain"},
    {"topic": "agent workflow reliability", "subreddit": "AI_Agents", "category": "recurring_pain"},
    {"topic": "self-hosted LLM inference cost", "subreddit": "LocalLLaMA", "category": "recurring_pain"},
    {"topic": "single noisy complaint", "subreddit": "microSaaS", "category": "single_post_noise"},
    {"topic": "cross-posted complaint", "subreddit": "SaaS", "category": "same_source_repost"},
    {"topic": "already-solved problem", "subreddit": "n8n", "category": "already_solved"},
    {"topic": "nonexistent niche", "subreddit": "startups", "category": "zero_results"},
    {"topic": "rate-limited feed", "subreddit": "SaaS", "category": "source_failure"}
  ]
}
```

(Add or trim topics to cover every P0 category: recurring pain, single-post noise, same-source repost, already-solved, source failure, zero results.)

- [ ] **Step 2: Write the failing test**

Create `tests/test_investigation/test_replay_report.py`:

```python
"""Tests for scripts/replay_report.py — deterministic P3 metrics."""
import json

from investigations.models import ActionRecord, EvidenceRecord
from investigations.store import InvestigationStore
from scripts.replay_report import compute_metrics


def test_compute_metrics_counts_source_calls_and_independence(tmp_path):
    store = InvestigationStore(state_dir=tmp_path)
    from investigations.service import InvestigationService

    svc = InvestigationService(store, fetcher=lambda s, sort, limit: [])
    svc.init("onboarding automation", subreddit="SaaS")

    metrics = compute_metrics(store, "inv_1")
    assert metrics["source_calls"] == 0
    assert "independent_evidence_chains" in metrics
    assert "candidate_count" in metrics
    assert "counterevidence_actions" in metrics


def test_compute_metrics_reports_human_slots(tmp_path):
    store = InvestigationStore(state_dir=tmp_path)
    from investigations.service import InvestigationService
    svc = InvestigationService(store, fetcher=lambda s, sort, limit: [])
    svc.init("onboarding automation", subreddit="SaaS")
    metrics = compute_metrics(store, "inv_1")
    # human-annotation slots are present and empty
    for key in ("actionability_score", "useful_annotation"):
        assert key in metrics
        assert metrics[key] in ("", None)
```

- [ ] **Step 3: Write `scripts/replay_report.py`**

```python
#!/usr/bin/env python3
"""P3 replay reporter — deterministic metrics + human-annotation slots.

Reads one investigation's store and computes the metrics the release gate needs:

- source_calls                — number of data actions that consumed a source call
- independent_evidence_chains — distinct independence keys among collected evidence
- counterevidence_actions     — number of ``seek_counterevidence`` actions
- unsupported_assertions      — candidate evidence_ids that reference unknown evidence
- candidate_count             — number of PainClusterCandidate records

Human-annotation slots (actionability_score, useful_annotation, blind_notes) are
left empty for the reviewer to fill; they are never computed here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigations.store import InvestigationStore


def compute_metrics(store: InvestigationStore, investigation_id: str) -> dict:
    actions = store.list_actions(investigation_id)
    evidence = store.list_evidence(investigation_id)
    candidates = store.list_candidates(investigation_id)

    source_calls = sum(1 for a in actions if a.action in ("search_discussions", "inspect_thread"))
    chains = len({e.item.independence_key for e in evidence})
    counter_actions = sum(1 for a in actions if a.action == "seek_counterevidence")

    known_ids = {e.id for e in evidence}
    unsupported = 0
    for c in candidates:
        unsupported += sum(1 for eid in c.evidence_ids if eid not in known_ids)

    return {
        "investigation_id": investigation_id,
        "source_calls": source_calls,
        "action_count": len(actions),
        "independent_evidence_chains": chains,
        "counterevidence_actions": counter_actions,
        "unsupported_assertions": unsupported,
        "candidate_count": len(candidates),
        # human-annotation slots — never computed
        "actionability_score": None,
        "useful_annotation": "",
        "blind_notes": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new", required=True, help="state dir for the new-flow run")
    parser.add_argument("--id", default="inv_1", help="investigation id")
    parser.add_argument("--out", required=True, help="output JSON report path")
    args = parser.parse_args()

    store = InvestigationStore(state_dir=args.new)
    metrics = compute_metrics(store, args.id)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. uv run pytest tests/test_investigation/test_replay_report.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add state/replay/topics.json scripts/replay_report.py tests/test_investigation/test_replay_report.py
git commit -m "feat(replay): add frozen topic manifest and P3 comparison reporter"
```

---

## Self-Review Notes (already applied)

- **Spec coverage:** P1 control plane → Tasks 1–7; P2 skill rewrite → Task 8; P0/P3 software → Task 9. P4/P5 are gated and explicitly out of scope (see Global Constraints). The 8 required test scenarios from the spec map to `test_service.py` (scenarios 2,4,5), `test_actions.py` (scenarios 1,3,7 partially), and `test_cli_investigate.py`/`test_replay_report.py` (scenarios 6,8); scenario 8's "cannot self-satisfy BUILD" is enforced structurally by `PainClusterCandidate` being a distinct type from `ConceptCard`, with handoff happening only via the existing `concepts.handoffs` path.
- **Type consistency:** `canonicalize_params`, `ActionRequest`, `allowed_next_actions`, `execute`, and the store/service method signatures are consistent across Tasks 4–7.
- **Known limitation (flagged, not a bug):** `init` hard-codes `id="inv_1"` for the single-user, one-topic-at-a-time pilot. A follow-up adds `--id` when multi-topic concurrency is needed.

## Execution Handoff

After each task, run its tests and commit. The full suite is:

```bash
PYTHONPATH=. uv run pytest tests/test_investigation/ tests/test_jsonl_store.py tests/test_concept_store.py -v
```
