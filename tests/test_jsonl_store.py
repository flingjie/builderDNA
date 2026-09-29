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
