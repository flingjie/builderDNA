"""Tests for the radar-cycle engine (``radar_cycles/engine.py``).

Covers the Task 10 requirements:

- ``phase_sequence`` returns the deterministic, de-duplicated order per mode;
- ``next_action`` returns ``validate`` first on a fresh run and advances past
  ``completed``/``partial`` phases to the next incomplete one;
- the engine never offers ``experiment`` before ``decide`` is completed *and*
  a Build decision is recorded (skips to the following phase otherwise);
- ``is_finalizable`` is false while any required phase is
  ``pending``/``running``/``blocked``/``failed`` and true when all are
  ``completed``/``partial`` (with ``experiment`` skipped when no Build passed);
- ``decision_eligibility`` is a structural, phase-state-only prerequisite check
  for the ``decide`` phase.
"""
from __future__ import annotations

import pytest

from radar_cycles.config import RadarConfig
from radar_cycles.engine import (
    PHASE_SPECS,
    NextAction,
    build_decision_count,
    decision_eligibility,
    has_build_decision,
    is_finalizable,
    next_action,
    phase_sequence,
)
from radar_cycles.models import (
    Mode,
    PhaseCheckpoint,
    PhaseName,
    PhaseStatus,
    RadarCycleRun,
)

FINGERPRINT = "sha256:" + "ab" * 32


# ── helpers ──

def make_run(
    mode: Mode = Mode.WEEKLY,
    completed: list[PhaseName] | None = None,
    counts: dict[PhaseName, int] | None = None,
) -> RadarCycleRun:
    """Build an in-memory run with the given phases marked completed."""
    checkpoint = PhaseCheckpoint(config_fingerprint=FINGERPRINT, mode=mode)
    for phase in completed or []:
        checkpoint.phases[phase] = PhaseStatus.COMPLETED
    if counts:
        checkpoint.counts.update(counts)
    return RadarCycleRun(
        id="run-1",
        radar="agent-reliability",
        mode=mode,
        checkpoint=checkpoint,
    )


def make_config(**overrides) -> RadarConfig:
    """Build a minimal valid radar config (3 neighborhoods), optionally overridden."""
    data: dict = {
        "version": 1,
        "name": "agent-reliability",
        "description": "test radar",
        "neighborhoods": [
            {"id": "n1", "label": "One", "focus": "first"},
            {"id": "n2", "label": "Two", "focus": "second"},
            {"id": "n3", "label": "Three", "focus": "third"},
        ],
    }
    data.update(overrides)
    return RadarConfig.model_validate(data)


# ── phase_sequence ──

class TestPhaseSequence:
    def test_daily(self):
        assert phase_sequence(Mode.DAILY) == [
            PhaseName.VALIDATE,
            PhaseName.X_DISCOVERY,
            PhaseName.REDDIT_SCAN,
            PhaseName.REDUCE,
            PhaseName.REPORT,
        ]

    def test_weekly(self):
        assert phase_sequence(Mode.WEEKLY) == [
            PhaseName.VALIDATE,
            PhaseName.X_DISCOVERY,
            PhaseName.REDDIT_SCAN,
            PhaseName.REDUCE,
            PhaseName.VERIFY,
            PhaseName.DECIDE,
            PhaseName.EXPERIMENT,
            PhaseName.CALIBRATION,
            PhaseName.REPORT,
        ]

    def test_monthly(self):
        assert phase_sequence(Mode.MONTHLY) == [
            PhaseName.VALIDATE,
            PhaseName.SOURCE_AUDIT,
            PhaseName.CALIBRATION,
            PhaseName.REPORT,
        ]

    def test_full_is_union_of_daily_and_weekly_plus_calibration(self):
        seq = phase_sequence(Mode.FULL)
        daily = set(phase_sequence(Mode.DAILY))
        weekly = set(phase_sequence(Mode.WEEKLY))
        assert set(seq) == daily | weekly | {PhaseName.CALIBRATION}
        # de-duplicated and deterministic (weekly already contains daily + calibration)
        assert len(seq) == len(set(seq))
        assert seq == phase_sequence(Mode.WEEKLY)

    def test_resume_is_derived_not_a_fixed_sequence(self):
        # A resumed run keeps its concrete start mode; Mode.RESUME has no fixed
        # sequence and must fail closed rather than invent one.
        with pytest.raises(ValueError):
            phase_sequence(Mode.RESUME)


# ── next_action ──

class TestNextAction:
    def test_fresh_run_returns_validate(self):
        run = make_run(Mode.WEEKLY)
        action = next_action(run, make_config())
        assert isinstance(action, NextAction)
        assert action.phase == PhaseName.VALIDATE

    def test_advances_after_marking_completed(self):
        run = make_run(Mode.WEEKLY)
        assert next_action(run, make_config()).phase == PhaseName.VALIDATE
        run.checkpoint.phases[PhaseName.VALIDATE] = PhaseStatus.COMPLETED
        assert next_action(run, make_config()).phase == PhaseName.X_DISCOVERY

    def test_partial_counts_as_done(self):
        run = make_run(Mode.DAILY, completed=[PhaseName.VALIDATE])
        run.checkpoint.phases[PhaseName.X_DISCOVERY] = PhaseStatus.PARTIAL
        assert next_action(run, make_config()).phase == PhaseName.REDDIT_SCAN

    def test_x_discovery_maps_to_twitter_learning(self):
        run = make_run(Mode.WEEKLY, completed=[PhaseName.VALIDATE])
        action = next_action(run, make_config())
        assert action.phase == PhaseName.X_DISCOVERY
        assert action.specialist_skill == "twitter-learning"
        assert action.required_handoff == "x-discovery"
        assert action.completion_command.startswith("radar-cycle import")

    def test_reddit_scan_maps_to_reddit_opportunity(self):
        run = make_run(Mode.WEEKLY, completed=[PhaseName.VALIDATE, PhaseName.X_DISCOVERY])
        action = next_action(run, make_config())
        assert action.phase == PhaseName.REDDIT_SCAN
        assert action.specialist_skill == "reddit-opportunity"
        assert action.required_handoff == "reddit-scan"

    def test_verify_maps_to_repo_trend(self):
        run = make_run(
            Mode.WEEKLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
            ],
        )
        action = next_action(run, make_config())
        assert action.phase == PhaseName.VERIFY
        assert action.specialist_skill == "repo-trend"
        assert action.required_handoff == "verify"

    def test_source_audit_maps_to_repo_trend(self):
        run = make_run(Mode.MONTHLY, completed=[PhaseName.VALIDATE])
        action = next_action(run, make_config())
        assert action.phase == PhaseName.SOURCE_AUDIT
        assert action.specialist_skill == "repo-trend"
        assert action.required_handoff == "source-audit"

    def test_local_phases_have_no_handoff(self):
        run = make_run(Mode.DAILY)
        action = next_action(run, make_config())
        assert action.phase == PhaseName.VALIDATE
        assert action.specialist_skill == ""
        assert action.required_handoff is None

    def test_returns_none_when_all_required_done(self):
        run = make_run(
            Mode.DAILY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
                PhaseName.REPORT,
            ],
        )
        assert next_action(run, make_config()) is None

    def test_surfaces_failed_phase_instead_of_skipping(self):
        run = make_run(
            Mode.WEEKLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
            ],
        )
        run.checkpoint.phases[PhaseName.VERIFY] = PhaseStatus.FAILED
        action = next_action(run, make_config())
        assert action is not None
        assert action.phase == PhaseName.VERIFY


# ── budgets ──

class TestBudgets:
    def test_reddit_budget_from_preset_scan_limit(self):
        config = make_config(reddit={"name": "p", "scan": {"limit": 10}, "feeds": []})
        run = make_run(Mode.DAILY, completed=[PhaseName.VALIDATE, PhaseName.X_DISCOVERY])
        action = next_action(run, config)
        assert action.phase == PhaseName.REDDIT_SCAN
        assert action.budget == 10

    def test_reddit_budget_none_without_preset(self):
        run = make_run(Mode.DAILY, completed=[PhaseName.VALIDATE, PhaseName.X_DISCOVERY])
        action = next_action(run, make_config())
        assert action.phase == PhaseName.REDDIT_SCAN
        assert action.budget is None

    def test_reduce_budget_is_daily_card_cap(self):
        config = make_config(daily_card_cap=7)
        run = make_run(
            Mode.DAILY,
            completed=[PhaseName.VALIDATE, PhaseName.X_DISCOVERY, PhaseName.REDDIT_SCAN],
        )
        action = next_action(run, config)
        assert action.phase == PhaseName.REDUCE
        assert action.budget == 7

    def test_decide_budget_is_weekly_build_cap(self):
        config = make_config(weekly_build_cap=2)
        run = make_run(
            Mode.WEEKLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
                PhaseName.VERIFY,
            ],
        )
        action = next_action(run, config)
        assert action.phase == PhaseName.DECIDE
        assert action.budget == 2

    def test_validate_has_no_budget(self):
        action = next_action(make_run(Mode.WEEKLY), make_config())
        assert action.phase == PhaseName.VALIDATE
        assert action.budget is None


# ── experiment invariant ──

class TestExperimentInvariant:
    def _run_reaching_decide(self) -> RadarCycleRun:
        return make_run(
            Mode.WEEKLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
                PhaseName.VERIFY,
            ],
        )

    def test_never_experiment_before_decide_completed(self):
        run = self._run_reaching_decide()
        # decide is still pending; the next action must be decide, not experiment.
        assert next_action(run, make_config()).phase == PhaseName.DECIDE

    def test_experiment_skipped_when_decide_completed_without_build(self):
        run = self._run_reaching_decide()
        run.checkpoint.phases[PhaseName.DECIDE] = PhaseStatus.COMPLETED
        assert has_build_decision(run) is False
        action = next_action(run, make_config())
        assert action is not None
        assert action.phase != PhaseName.EXPERIMENT
        assert action.phase == PhaseName.CALIBRATION

    def test_experiment_returned_when_build_decision_recorded(self):
        run = self._run_reaching_decide()
        run.checkpoint.phases[PhaseName.DECIDE] = PhaseStatus.COMPLETED
        run.checkpoint.counts[PhaseName.DECIDE] = 1
        action = next_action(run, make_config())
        assert action.phase == PhaseName.EXPERIMENT

    def test_build_decision_count_zero_means_no_build(self):
        run = self._run_reaching_decide()
        run.checkpoint.phases[PhaseName.DECIDE] = PhaseStatus.COMPLETED
        assert build_decision_count(run) == 0
        assert has_build_decision(run) is False


# ── is_finalizable ──

class TestIsFinalizable:
    def test_false_with_pending_phase(self):
        assert is_finalizable(make_run(Mode.DAILY)) is False

    def test_true_when_all_completed(self):
        run = make_run(
            Mode.DAILY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
                PhaseName.REPORT,
            ],
        )
        assert is_finalizable(run) is True

    def test_partial_counts_as_done(self):
        run = make_run(
            Mode.DAILY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
            ],
        )
        run.checkpoint.phases[PhaseName.REPORT] = PhaseStatus.PARTIAL
        assert is_finalizable(run) is True

    def test_false_when_failed(self):
        run = make_run(
            Mode.DAILY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
                PhaseName.REPORT,
            ],
        )
        run.checkpoint.phases[PhaseName.REDUCE] = PhaseStatus.FAILED
        assert is_finalizable(run) is False

    def test_false_when_blocked(self):
        run = make_run(
            Mode.DAILY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
                PhaseName.REPORT,
            ],
        )
        run.checkpoint.phases[PhaseName.X_DISCOVERY] = PhaseStatus.BLOCKED
        assert is_finalizable(run) is False

    def test_weekly_without_build_skips_experiment(self):
        run = make_run(
            Mode.WEEKLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
                PhaseName.VERIFY,
                PhaseName.DECIDE,
                PhaseName.CALIBRATION,
                PhaseName.REPORT,
            ],
        )
        # experiment skipped (no Build recorded) -> the run is finalizable.
        assert is_finalizable(run) is True

    def test_weekly_with_build_requires_experiment(self):
        run = make_run(
            Mode.WEEKLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
                PhaseName.VERIFY,
                PhaseName.DECIDE,
                PhaseName.CALIBRATION,
                PhaseName.REPORT,
            ],
        )
        run.checkpoint.counts[PhaseName.DECIDE] = 1
        # experiment is now required but still pending -> not finalizable.
        assert is_finalizable(run) is False


# ── decision_eligibility ──

class TestDecisionEligibility:
    def test_daily_has_no_decide(self):
        run = make_run(
            Mode.DAILY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
            ],
        )
        assert decision_eligibility(run, make_config()) is False

    def test_monthly_has_no_decide(self):
        run = make_run(
            Mode.MONTHLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.SOURCE_AUDIT,
                PhaseName.CALIBRATION,
            ],
        )
        assert decision_eligibility(run, make_config()) is False

    def test_false_when_reduce_pending(self):
        run = make_run(
            Mode.WEEKLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.VERIFY,
            ],
        )
        assert decision_eligibility(run, make_config()) is False

    def test_true_when_prerequisites_complete(self):
        run = make_run(
            Mode.WEEKLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
                PhaseName.VERIFY,
            ],
        )
        assert decision_eligibility(run, make_config()) is True

    def test_partial_prerequisite_counts(self):
        run = make_run(
            Mode.WEEKLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
            ],
        )
        run.checkpoint.phases[PhaseName.VERIFY] = PhaseStatus.PARTIAL
        assert decision_eligibility(run, make_config()) is True

    def test_false_when_prerequisite_failed(self):
        run = make_run(
            Mode.WEEKLY,
            completed=[
                PhaseName.VALIDATE,
                PhaseName.X_DISCOVERY,
                PhaseName.REDDIT_SCAN,
                PhaseName.REDUCE,
            ],
        )
        run.checkpoint.phases[PhaseName.VERIFY] = PhaseStatus.FAILED
        assert decision_eligibility(run, make_config()) is False


# ── phase → skill / handoff table ──

class TestPhaseSpecs:
    def test_every_phase_has_a_spec(self):
        assert set(PHASE_SPECS) == set(PhaseName)

    def test_source_phases_require_a_handoff(self):
        for phase in (
            PhaseName.X_DISCOVERY,
            PhaseName.REDDIT_SCAN,
            PhaseName.VERIFY,
            PhaseName.SOURCE_AUDIT,
        ):
            skill, handoff = PHASE_SPECS[phase]
            assert skill, f"{phase.value!r} must map to a specialist skill"
            assert handoff == phase.value

    def test_local_phases_have_no_handoff(self):
        for phase in (
            PhaseName.VALIDATE,
            PhaseName.REDUCE,
            PhaseName.DECIDE,
            PhaseName.EXPERIMENT,
            PhaseName.CALIBRATION,
            PhaseName.REPORT,
        ):
            _, handoff = PHASE_SPECS[phase]
            assert handoff is None
