"""Tests for the builder problem/trajectory store, service, and CLI."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from cli.commands.builders import builders
from intelligence.builder_problems.service import (
    BuilderProblemValidationError,
    build_opportunity_cards,
    capture_problem,
    compare_problems,
    record_event,
    show_problem,
)
from intelligence.builder_problems.store import (
    BuilderProblemConflictError,
    BuilderProblemStore,
)
from models.builder_problem import (
    BuilderProblem,
    ProblemEvent,
    ProblemEventType,
    ProblemStatus,
)


runner = CliRunner()


def _capture(store, person, statement, **overrides):
    fields = dict(
        person_ref=person,
        statement=statement,
        user_segment="独立 Agent 开发者",
        trigger_context="修改 prompt 或工具实现后",
        job_to_be_done="确认历史失败案例是否修复",
        current_workaround="手工重跑历史失败输入",
        primary_cost="准备输入、恢复环境、判断结果",
        source_refs=[f"x/{person}/1"],
    )
    fields.update(overrides)
    return capture_problem(store, **fields)


class TestModels:
    def test_problem_id_is_store_key(self):
        problem = BuilderProblem(problem_id="p1", person_ref="alice", statement="x")
        assert problem.id == "p1"
        assert problem.status == ProblemStatus.OBSERVED

    def test_event_id_is_store_key(self):
        event = ProblemEvent(event_id="e1", problem_id="p1", summary="tried script")
        assert event.id == "e1"
        assert event.event_type == ProblemEventType.NOTE


class TestCapture:
    def test_create_appends_initial_event(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        result = _capture(store, "alice", "修改 prompt 后难以确认旧问题是否修复")

        assert result["action"] == "created"
        problem = result["data"]["problem"]
        event = result["data"]["event"]
        assert problem["person_ref"] == "alice"
        assert problem["status"] == "observed"
        assert event["event_type"] == "problem_observed"
        assert store.get_problem(problem["problem_id"]) is not None
        assert len(store.list_events(problem["problem_id"])) == 1

    def test_update_appends_event_and_preserves_first_seen(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        first = _capture(store, "alice", "old statement", problem_id="p1")
        first_seen = first["data"]["problem"]["first_seen_at"]

        second = _capture(
            store,
            "alice",
            "new statement",
            problem_id="p1",
            current_workaround="now use a script",
        )

        assert second["action"] == "updated"
        assert second["data"]["problem"]["statement"] == "new statement"
        assert second["data"]["problem"]["first_seen_at"] == first_seen
        assert second["data"]["event"]["event_type"] == "note"
        assert len(store.list_events("p1")) == 2

    def test_identical_capture_is_idempotent(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        _capture(store, "alice", "same", problem_id="p1")
        result = _capture(store, "alice", "same", problem_id="p1")

        assert result["action"] == "already_captured"
        assert result["data"]["event"] is None
        assert len(store.list_events("p1")) == 1

    def test_missing_person_or_statement(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        with pytest.raises(BuilderProblemValidationError):
            capture_problem(store, person_ref="", statement="x")
        with pytest.raises(BuilderProblemValidationError):
            capture_problem(store, person_ref="alice", statement="")


class TestRecordEvent:
    def test_record_updates_snapshot_and_trajectory(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        _capture(store, "alice", "a problem", problem_id="p1")

        result = record_event(
            store,
            problem_id="p1",
            event_type="attempt",
            summary="尝试脚本",
            detail="维护一个重跑脚本",
            to_status="confirmed",
            current_workaround="脚本重跑",
            source_refs=["x/alice/2"],
        )

        assert result["action"] == "recorded"
        problem = result["data"]["problem"]
        assert problem["status"] == "confirmed"
        assert problem["current_workaround"] == "脚本重跑"
        assert problem["source_refs"] == ["x/alice/1", "x/alice/2"]
        assert len(store.list_events("p1")) == 2
        assert store.list_events("p1")[-1].summary == "尝试脚本"

    def test_unknown_problem_raises(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        with pytest.raises(BuilderProblemValidationError):
            record_event(store, problem_id="missing", summary="x")


class TestComparison:
    def test_groups_by_task_and_obstacle_not_keyword(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        _capture(store, "alice", "alice eval regression", source_refs=["x/alice/1"])
        _capture(
            store,
            "bob",
            "bob regression after prompt change",
            current_workaround="维护脚本",
            primary_cost="手工判断",
            source_refs=["x/bob/1"],
        )
        _capture(
            store,
            "carol",
            "carol needs long-horizon eval",
            trigger_context="上线长程 agent 前",
            job_to_be_done="评估 agent 是否达到发布标准",
            user_segment="团队负责人",
            source_refs=["x/carol/1"],
        )

        result = compare_problems(store)
        comparisons = result["data"]["comparisons"]

        assert len(comparisons) == 1
        comparison = comparisons[0]
        assert comparison["person_refs"] == ["alice", "bob"]
        assert comparison["job_to_be_done"] == "确认历史失败案例是否修复"
        assert "carol" not in comparison["person_refs"]
        assert any(problem_id.startswith("carol-") for problem_id in result["data"]["ungrouped"])

    def test_comparison_captures_differences_and_unknowns(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        _capture(
            store,
            "alice",
            "a",
            current_workaround="手工",
            primary_cost="准备输入",
            source_refs=["x/alice/1"],
        )
        _capture(
            store,
            "bob",
            "b",
            current_workaround="脚本",
            primary_cost="判断结果",
            source_refs=[],
        )

        comparison = compare_problems(store)["data"]["comparisons"][0]
        assert "current_workaround" in comparison["differences"]
        assert "primary_cost" in comparison["differences"]
        assert any("缺少可核验来源" in q for q in comparison["open_questions"])
        assert comparison["minimal_deliverable"]
        assert {t["person_ref"] for t in comparison["validation_targets"]} == {"alice", "bob"}

    def test_single_problem_is_ungrouped(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        _capture(store, "alice", "only one", source_refs=["x/alice/1"])
        result = compare_problems(store)
        assert result["data"]["comparisons"] == []
        assert result["data"]["ungrouped"]

    def test_missing_field_is_not_treated_as_common(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        _capture(store, "alice", "a", current_workaround="手工")
        _capture(store, "bob", "b", current_workaround="")

        comparison = compare_problems(store)["data"]["comparisons"][0]
        assert comparison["current_workaround"] == ""
        assert "current_workaround" in comparison["differences"]


class TestOpportunityCards:
    def test_opportunity_card_is_verifiable(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        _capture(
            store,
            "alice",
            "a",
            current_workaround="手工",
            primary_cost="准备输入",
            source_refs=["x/alice/1"],
        )
        _capture(
            store,
            "bob",
            "b",
            current_workaround="脚本",
            primary_cost="判断结果",
            source_refs=["x/bob/1"],
        )

        result = build_opportunity_cards(store)
        cards = result["data"]["opportunities"]

        assert len(cards) == 1
        card = cards[0]
        assert card["title"]
        assert card["confidence"] >= 0.0
        assert {w["person_ref"] for w in card["who"]} == {"alice", "bob"}
        assert card["same_parts"]
        assert card["different_parts"]
        assert card["key_unknowns"]
        assert card["validation_targets"]
        assert card["minimal_deliverable"]
        assert card["source_refs"] == ["x/alice/1", "x/bob/1"]


class TestStore:
    def test_event_conflict(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        event = ProblemEvent(event_id="e1", problem_id="p1", summary="a")
        store.add_event(event)
        conflict = ProblemEvent(event_id="e1", problem_id="p1", summary="different")
        with pytest.raises(BuilderProblemConflictError):
            store.add_event(conflict)

    def test_show_orders_events(self, tmp_path):
        store = BuilderProblemStore(tmp_path)
        _capture(store, "alice", "a", problem_id="p1")
        record_event(store, problem_id="p1", event_type="attempt", summary="attempt")
        shown = show_problem(store, "p1")["data"]
        assert [e["event_type"] for e in shown["events"]] == ["problem_observed", "attempt"]


class TestCLI:
    def _run(self, *args):
        return runner.invoke(builders, list(args))

    def test_capture_list_show_record_compare_opportunity(self, tmp_path):
        state_dir = str(tmp_path / "state")
        base = ["--state-dir", state_dir]

        r1 = self._run(
            "capture", "alice",
            "--statement", "a problem",
            "--user-segment", "独立 Agent 开发者",
            "--trigger-context", "修改 prompt 后",
            "--job-to-be-done", "确认历史失败案例是否修复",
            "--workaround", "手工重跑",
            "--source-ref", "x/alice/1",
            *base,
        )
        assert r1.exit_code == 0, r1.output
        payload = json.loads(r1.output)
        assert payload["ok"] is True
        problem_id = payload["data"]["problem"]["problem_id"]

        r2 = self._run(
            "record", problem_id,
            "--event-type", "attempt",
            "--summary", "尝试脚本",
            "--to-status", "confirmed",
            *base,
        )
        assert r2.exit_code == 0, r2.output
        assert json.loads(r2.output)["data"]["problem"]["status"] == "confirmed"

        r3 = self._run("list", *base)
        assert json.loads(r3.output)["data"]["count"] == 1

        r4 = self._run("show", problem_id, *base)
        assert json.loads(r4.output)["data"]["event_count"] == 2

        r5 = self._run("compare", *base)
        assert json.loads(r5.output)["data"]["comparison_count"] == 0

        r6 = self._run("opportunity", *base)
        assert json.loads(r6.output)["data"]["count"] == 0

    def test_capture_markdown(self, tmp_path):
        result = self._run(
            "capture", "alice",
            "--statement", "a problem",
            "--format", "md",
            "--state-dir", str(tmp_path),
        )
        assert result.exit_code == 0
        assert "# builders.capture" in result.output
        assert "a problem" in result.output

    def test_missing_person_is_error(self, tmp_path):
        result = self._run(
            "capture", "",
            "--statement", "x",
            "--state-dir", str(tmp_path),
        )
        assert result.exit_code != 0
        assert "requires --person-ref" in result.output
