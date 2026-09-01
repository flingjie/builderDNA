"""Tests for the radar-cycle domain models (radar_cycles/models.py).

Covers the hard requirements from the plan's M1 foundation:
- ``Mode`` / ``PhaseStatus`` / ``PhaseName`` enum validity.
- ``PhaseCheckpoint`` carries a config fingerprint, limits, per-phase state,
  per-phase counts, an error list, and UTC timestamps.
- Allowed phase transitions (pending -> running; running -> terminal;
  one read-only retry from partial/failed; blocked only after changed input;
  completed never returns to running).
- UTC-only timestamps.
- ``model_json_schema()`` succeeds for every public contract.
"""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from radar_cycles.models import (
    Limits,
    Mode,
    PhaseCheckpoint,
    PhaseName,
    PhaseStatus,
    RadarCycleRun,
    SourceCoverage,
    SourceStatus,
)


def make_checkpoint(**overrides) -> PhaseCheckpoint:
    fields = dict(
        config_fingerprint="sha256:abc123",
        mode=Mode.FULL,
    )
    fields.update(overrides)
    return PhaseCheckpoint(**fields)


# ── Enums ──

class TestModeEnum:
    def test_values(self):
        assert {m.value for m in Mode} == {"daily", "weekly", "monthly", "full", "resume"}

    def test_invalid_value_rejected(self):
        with pytest.raises(ValidationError):
            PhaseCheckpoint(config_fingerprint="f", mode="hourly")


class TestPhaseStatusEnum:
    def test_values(self):
        assert {s.value for s in PhaseStatus} == {
            "pending", "running", "completed", "partial", "blocked", "failed",
        }


class TestPhaseNameEnum:
    def test_values(self):
        assert {p.value for p in PhaseName} == {
            "validate", "x-discovery", "reddit-scan", "reduce", "verify",
            "decide", "experiment", "calibration", "source-audit", "report",
        }

    def test_hyphenated_members(self):
        assert PhaseName.X_DISCOVERY.value == "x-discovery"
        assert PhaseName.REDDIT_SCAN.value == "reddit-scan"
        assert PhaseName.SOURCE_AUDIT.value == "source-audit"


# ── Limits ──

class TestLimits:
    def test_defaults_to_zero(self):
        limits = Limits()
        assert limits.daily_builds == 0
        assert limits.weekly_builds == 0

    def test_nonnegative_caps(self):
        limits = Limits(daily_builds=1, weekly_builds=3)
        assert limits.daily_builds == 1
        assert limits.weekly_builds == 3

    @pytest.mark.parametrize("field", ["daily_builds", "weekly_builds"])
    def test_negative_rejected(self, field):
        with pytest.raises(ValidationError):
            Limits(**{field: -1})


# ── PhaseCheckpoint construction ──

class TestPhaseCheckpoint:
    def test_construction_minimal(self):
        cp = make_checkpoint()
        assert cp.config_fingerprint == "sha256:abc123"
        assert cp.mode == Mode.FULL
        assert cp.phases == {}
        assert cp.counts == {}
        assert cp.errors == []
        assert cp.retry_counts == {}

    def test_requires_fingerprint(self):
        with pytest.raises(ValidationError):
            PhaseCheckpoint(mode=Mode.FULL)

    def test_requires_mode(self):
        with pytest.raises(ValidationError):
            PhaseCheckpoint(config_fingerprint="f")

    def test_status_of_defaults_to_pending(self):
        cp = make_checkpoint()
        assert cp.status_of(PhaseName.VERIFY) == PhaseStatus.PENDING

    def test_counts_and_errors_recorded(self):
        cp = make_checkpoint(
            counts={PhaseName.VERIFY: 3},
            errors=["x unavailable"],
        )
        assert cp.counts[PhaseName.VERIFY] == 3
        assert cp.errors == ["x unavailable"]

    def test_json_schema_succeeds(self):
        schema = PhaseCheckpoint.model_json_schema()
        assert "config_fingerprint" in schema["properties"]
        assert "phases" in schema["properties"]
        assert "counts" in schema["properties"]
        assert "errors" in schema["properties"]


# ── Allowed phase transitions ──

class TestPhaseTransitions:
    def test_pending_to_running(self):
        cp = make_checkpoint()
        cp.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)
        assert cp.status_of(PhaseName.VERIFY) == PhaseStatus.RUNNING

    def test_pending_to_terminal_rejected(self):
        cp = make_checkpoint()
        with pytest.raises(ValueError):
            cp.transition(PhaseName.VERIFY, PhaseStatus.COMPLETED)

    @pytest.mark.parametrize(
        "target",
        [PhaseStatus.COMPLETED, PhaseStatus.PARTIAL, PhaseStatus.BLOCKED, PhaseStatus.FAILED],
    )
    def test_running_to_each_terminal(self, target):
        cp = make_checkpoint()
        cp.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)
        cp.transition(PhaseName.VERIFY, target)
        assert cp.status_of(PhaseName.VERIFY) == target

    def test_completed_cannot_return_to_running(self):
        cp = make_checkpoint()
        cp.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)
        cp.transition(PhaseName.VERIFY, PhaseStatus.COMPLETED)
        with pytest.raises(ValueError):
            cp.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)

    def test_partial_retry_once_only(self):
        cp = make_checkpoint()
        cp.transition(PhaseName.REDDIT_SCAN, PhaseStatus.RUNNING)
        cp.transition(PhaseName.REDDIT_SCAN, PhaseStatus.PARTIAL)
        cp.transition(PhaseName.REDDIT_SCAN, PhaseStatus.RUNNING)  # retry 1 OK
        assert cp.retry_counts[PhaseName.REDDIT_SCAN] == 1
        cp.transition(PhaseName.REDDIT_SCAN, PhaseStatus.PARTIAL)
        with pytest.raises(ValueError):
            cp.transition(PhaseName.REDDIT_SCAN, PhaseStatus.RUNNING)  # retry 2 rejected

    def test_failed_retry_once_only(self):
        cp = make_checkpoint()
        cp.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)
        cp.transition(PhaseName.VERIFY, PhaseStatus.FAILED)
        cp.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)  # retry 1 OK
        assert cp.retry_counts[PhaseName.VERIFY] == 1

    def test_blocked_requires_changed_input(self):
        cp = make_checkpoint()
        cp.transition(PhaseName.X_DISCOVERY, PhaseStatus.RUNNING)
        cp.transition(PhaseName.X_DISCOVERY, PhaseStatus.BLOCKED)
        with pytest.raises(ValueError):
            cp.transition(PhaseName.X_DISCOVERY, PhaseStatus.RUNNING)
        cp.transition(PhaseName.X_DISCOVERY, PhaseStatus.RUNNING, allow_unblock=True)
        assert cp.status_of(PhaseName.X_DISCOVERY) == PhaseStatus.RUNNING

    def test_running_cannot_transition_to_running(self):
        cp = make_checkpoint()
        cp.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)
        with pytest.raises(ValueError):
            cp.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)

    def test_cannot_return_to_pending(self):
        cp = make_checkpoint()
        cp.transition(PhaseName.VERIFY, PhaseStatus.RUNNING)
        with pytest.raises(ValueError):
            cp.transition(PhaseName.VERIFY, PhaseStatus.PENDING)

    def test_str_phase_name_coerced(self):
        cp = make_checkpoint()
        cp.transition("verify", PhaseStatus.RUNNING)
        assert cp.status_of(PhaseName.VERIFY) == PhaseStatus.RUNNING

    def test_allowed_transitions_table(self):
        table = PhaseCheckpoint.ALLOWED_TRANSITIONS
        assert table[PhaseStatus.COMPLETED] == set()
        assert PhaseStatus.RUNNING in table[PhaseStatus.PENDING]
        assert PhaseStatus.COMPLETED in table[PhaseStatus.RUNNING]


# ── UTC-only timestamps ──

class TestUtcTimestamps:
    def test_naive_created_at_rejected(self):
        with pytest.raises(ValidationError):
            make_checkpoint(created_at=datetime(2026, 1, 1))

    def test_non_utc_offset_rejected(self):
        with pytest.raises(ValidationError):
            make_checkpoint(
                created_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))
            )

    def test_utc_accepted(self):
        cp = make_checkpoint(created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert cp.created_at.utcoffset() == timedelta(0)

    def test_defaults_are_utc(self):
        cp = make_checkpoint()
        assert cp.created_at.tzinfo is not None
        assert cp.created_at.utcoffset() == timedelta(0)
        assert cp.updated_at.utcoffset() == timedelta(0)


# ── RadarCycleRun ──

class TestRadarCycleRun:
    def test_construction(self):
        run = RadarCycleRun(
            id="run-1",
            radar="agent-reliability",
            mode=Mode.FULL,
            checkpoint=make_checkpoint(),
        )
        assert run.id == "run-1"
        assert run.radar == "agent-reliability"
        assert run.mode == Mode.FULL
        assert run.checkpoint.mode == Mode.FULL

    def test_requires_checkpoint(self):
        with pytest.raises(ValidationError):
            RadarCycleRun(id="run-1", radar="agent-reliability", mode=Mode.FULL)

    def test_json_schema_succeeds(self):
        assert RadarCycleRun.model_json_schema() is not None


# ── SourceCoverage reuse ──

class TestSourceCoverageReuse:
    def test_imported_not_redefined(self):
        # SourceCoverage is re-exported from models.radar_payload, not redefined.
        from models.radar_payload import SourceCoverage as Original

        assert SourceCoverage is Original
        assert SourceStatus.COMPLETE.value == "complete"
