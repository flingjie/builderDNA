"""Tests for atomic radar-cycle checkpoints (``radar_cycles/checkpoint.py``).

Covers the Task 9 requirements:

- create -> load round-trips (every phase starts ``pending``);
- ``pending -> running -> completed`` transitions;
- ``completed -> running`` is rejected;
- ``partial -> running`` succeeds exactly once, then a second retry is rejected;
- ``blocked -> running`` requires ``allow_unblock=True``;
- an interrupted rewrite never corrupts the prior checkpoint (atomic rename);
- completed output paths and per-phase counts survive a load;
- ``record_output`` / ``record_coverage`` / ``record_error`` append and persist;
- ``finish`` marks the run complete.
"""
from __future__ import annotations

import json
import os

import pytest

from models.concept import SourceType
from models.radar_payload import SourceStatus
from radar_cycles import checkpoint
from radar_cycles.models import (
    Limits,
    Mode,
    PhaseName,
    PhaseStatus,
    RadarCycleRun,
)


FINGERPRINT = "sha256:deadbeefdeadbeefdeadbeefdeadbeef"


def make_limits() -> Limits:
    return Limits(daily_builds=1, weekly_builds=3)


def create_run(tmp_path, run_id: str = "run-1") -> RadarCycleRun:
    return checkpoint.create(
        run_id,
        "agent-reliability",
        Mode.FULL,
        make_limits(),
        FINGERPRINT,
        store_dir=tmp_path,
    )


def raw_checkpoint(tmp_path, run_id: str = "run-1") -> dict:
    return json.loads((tmp_path / f"{run_id}.json").read_text(encoding="utf-8"))


def assert_valid_run_file(tmp_path, run_id: str = "run-1") -> None:
    """The checkpoint file is always valid JSON that parses as a RadarCycleRun."""
    raw = raw_checkpoint(tmp_path, run_id)
    RadarCycleRun.model_validate(raw)


# ── create / load ──

class TestCreateAndLoad:
    def test_create_all_phases_pending(self, tmp_path):
        run = create_run(tmp_path)
        for phase in PhaseName:
            assert run.checkpoint.status_of(phase) == PhaseStatus.PENDING

    def test_create_returns_run_metadata(self, tmp_path):
        run = create_run(tmp_path)
        assert run.id == "run-1"
        assert run.radar == "agent-reliability"
        assert run.mode == Mode.FULL
        assert run.checkpoint.config_fingerprint == FINGERPRINT
        assert run.checkpoint.limits == make_limits()

    def test_create_load_roundtrip(self, tmp_path):
        run = create_run(tmp_path)
        loaded = checkpoint.load("run-1", store_dir=tmp_path)
        assert loaded == run
        assert loaded.checkpoint.config_fingerprint == FINGERPRINT
        assert loaded.checkpoint.limits == make_limits()

    def test_load_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            checkpoint.load("nope", store_dir=tmp_path)

    def test_file_written_at_expected_path(self, tmp_path):
        create_run(tmp_path)
        assert (tmp_path / "run-1.json").exists()
        assert (tmp_path / "nope.json").exists() is False


# ── transitions ──

class TestTransitions:
    def test_pending_to_running_to_completed(self, tmp_path):
        create_run(tmp_path)
        checkpoint.transition("run-1", "x-discovery", "running", store_dir=tmp_path)
        assert (
            checkpoint.load("run-1", store_dir=tmp_path).checkpoint.status_of(
                PhaseName.X_DISCOVERY
            )
            == PhaseStatus.RUNNING
        )
        checkpoint.transition("run-1", "x-discovery", "completed", store_dir=tmp_path)
        assert (
            checkpoint.load("run-1", store_dir=tmp_path).checkpoint.status_of(
                PhaseName.X_DISCOVERY
            )
            == PhaseStatus.COMPLETED
        )

    def test_completed_cannot_return_to_running(self, tmp_path):
        create_run(tmp_path)
        checkpoint.transition("run-1", "x-discovery", "running", store_dir=tmp_path)
        checkpoint.transition("run-1", "x-discovery", "completed", store_dir=tmp_path)
        with pytest.raises(ValueError):
            checkpoint.transition("run-1", "x-discovery", "running", store_dir=tmp_path)
        # the failed transition must not corrupt persisted state
        assert (
            checkpoint.load("run-1", store_dir=tmp_path).checkpoint.status_of(
                PhaseName.X_DISCOVERY
            )
            == PhaseStatus.COMPLETED
        )

    def test_partial_retry_succeeds_once_then_rejected(self, tmp_path):
        create_run(tmp_path)
        checkpoint.transition("run-1", "reddit-scan", "running", store_dir=tmp_path)
        checkpoint.transition("run-1", "reddit-scan", "partial", store_dir=tmp_path)
        # first read-only retry succeeds
        checkpoint.transition("run-1", "reddit-scan", "running", store_dir=tmp_path)
        assert (
            checkpoint.load("run-1", store_dir=tmp_path).checkpoint.retry_counts[
                PhaseName.REDDIT_SCAN
            ]
            == 1
        )
        # go partial again, then the second retry is rejected
        checkpoint.transition("run-1", "reddit-scan", "partial", store_dir=tmp_path)
        with pytest.raises(ValueError):
            checkpoint.transition("run-1", "reddit-scan", "running", store_dir=tmp_path)

    def test_blocked_requires_allow_unblock(self, tmp_path):
        create_run(tmp_path)
        checkpoint.transition("run-1", "x-discovery", "running", store_dir=tmp_path)
        checkpoint.transition("run-1", "x-discovery", "blocked", store_dir=tmp_path)
        with pytest.raises(ValueError):
            checkpoint.transition("run-1", "x-discovery", "running", store_dir=tmp_path)
        checkpoint.transition(
            "run-1", "x-discovery", "running", allow_unblock=True, store_dir=tmp_path
        )
        assert (
            checkpoint.load("run-1", store_dir=tmp_path).checkpoint.status_of(
                PhaseName.X_DISCOVERY
            )
            == PhaseStatus.RUNNING
        )

    def test_transition_missing_run_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            checkpoint.transition("nope", "verify", "running", store_dir=tmp_path)


# ── atomic writes ──

class TestAtomicWrites:
    def test_file_is_always_valid_json_across_rewrites(self, tmp_path):
        create_run(tmp_path)
        assert_valid_run_file(tmp_path)
        run = checkpoint.load("run-1", store_dir=tmp_path)
        run.checkpoint.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)
        checkpoint.save(run, store_dir=tmp_path)
        assert_valid_run_file(tmp_path)
        run = checkpoint.load("run-1", store_dir=tmp_path)
        run.checkpoint.transition(PhaseName.VERIFY, PhaseStatus.COMPLETED)
        checkpoint.save(run, store_dir=tmp_path)
        assert_valid_run_file(tmp_path)

    def test_interrupted_write_preserves_prior_checkpoint(self, tmp_path, monkeypatch):
        create_run(tmp_path)
        prior = (tmp_path / "run-1.json").read_text(encoding="utf-8")

        def boom(src, dst):
            raise OSError("simulated crash during replace")

        monkeypatch.setattr(os, "replace", boom)
        run = checkpoint.load("run-1", store_dir=tmp_path)
        run.checkpoint.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)
        with pytest.raises(OSError):
            checkpoint.save(run, store_dir=tmp_path)

        monkeypatch.undo()  # restore os.replace before reading again

        # the prior checkpoint is untouched and still loadable
        assert (tmp_path / "run-1.json").read_text(encoding="utf-8") == prior
        loaded = checkpoint.load("run-1", store_dir=tmp_path)
        assert loaded.checkpoint.status_of(PhaseName.VERIFY) == PhaseStatus.PENDING
        assert_valid_run_file(tmp_path)

    def test_no_leftover_temp_files(self, tmp_path):
        create_run(tmp_path)
        run = checkpoint.load("run-1", store_dir=tmp_path)
        run.checkpoint.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)
        checkpoint.save(run, store_dir=tmp_path)
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []


# ── outputs / coverage / errors / finish ──

class TestRecordings:
    def test_record_output_persists_paths_across_load(self, tmp_path):
        create_run(tmp_path)
        checkpoint.record_output(
            "run-1", "x-discovery", "output/handoffs/x-learning.json", store_dir=tmp_path
        )
        checkpoint.record_output(
            "run-1", "x-discovery", "output/handoffs/x-more.json", store_dir=tmp_path
        )
        assert checkpoint.outputs_of("run-1", store_dir=tmp_path) == {
            "x-discovery": [
                "output/handoffs/x-learning.json",
                "output/handoffs/x-more.json",
            ]
        }
        # loading the run does not drop recorded outputs, and the run itself
        # still round-trips as a plain RadarCycleRun.
        run = checkpoint.load("run-1", store_dir=tmp_path)
        assert run.id == "run-1"
        assert "outputs" not in run.model_dump(mode="json")

    def test_record_output_deduplicates_identical_path(self, tmp_path):
        create_run(tmp_path)
        checkpoint.record_output("run-1", "verify", "a.json", store_dir=tmp_path)
        checkpoint.record_output("run-1", "verify", "a.json", store_dir=tmp_path)
        assert checkpoint.outputs_of("run-1", store_dir=tmp_path)["verify"] == ["a.json"]

    def test_record_coverage_appends(self, tmp_path):
        create_run(tmp_path)
        checkpoint.record_coverage(
            "run-1", SourceType.REDDIT, SourceStatus.PARTIAL, "no comments", store_dir=tmp_path
        )
        coverage = checkpoint.coverage_of("run-1", store_dir=tmp_path)
        assert len(coverage) == 1
        assert coverage[0].source_type == SourceType.REDDIT
        assert coverage[0].status == SourceStatus.PARTIAL
        assert coverage[0].note == "no comments"

    def test_record_error_appends(self, tmp_path):
        create_run(tmp_path)
        checkpoint.record_error("run-1", "x unavailable", store_dir=tmp_path)
        assert checkpoint.load("run-1", store_dir=tmp_path).checkpoint.errors == [
            "x unavailable"
        ]

    def test_counts_and_errors_survive_load(self, tmp_path):
        run = create_run(tmp_path)
        run.checkpoint.counts[PhaseName.VERIFY] = 7
        run.checkpoint.errors.append("github rate limited")
        checkpoint.save(run, store_dir=tmp_path)
        loaded = checkpoint.load("run-1", store_dir=tmp_path)
        assert loaded.checkpoint.counts[PhaseName.VERIFY] == 7
        assert loaded.checkpoint.errors == ["github rate limited"]

    def test_save_preserves_recorded_outputs(self, tmp_path):
        create_run(tmp_path)
        checkpoint.record_output("run-1", "x-discovery", "a.json", store_dir=tmp_path)
        run = checkpoint.load("run-1", store_dir=tmp_path)
        checkpoint.save(run, store_dir=tmp_path)
        assert checkpoint.outputs_of("run-1", store_dir=tmp_path)["x-discovery"] == [
            "a.json"
        ]

    def test_finish_marks_run_complete(self, tmp_path):
        create_run(tmp_path)
        assert checkpoint.run_status_of("run-1", store_dir=tmp_path) == "running"
        checkpoint.finish("run-1", store_dir=tmp_path)
        assert checkpoint.run_status_of("run-1", store_dir=tmp_path) == "completed"
        # finish is persisted, not just in-memory
        assert checkpoint.load_document("run-1", store_dir=tmp_path).run_status == "completed"
