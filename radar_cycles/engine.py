"""Radar-cycle engine — mode-to-phase selection and next-action steering.

The engine is the deterministic state machine that decides *what the agent should
do next* during a radar cycle. It performs **no web retrieval and no
persistence**: it reads a :class:`~radar_cycles.models.RadarCycleRun` (carrying
its current :class:`~radar_cycles.models.PhaseCheckpoint`) and a resolved
:class:`~radar_cycles.config.RadarConfig`, and returns typed instructions.

Responsibilities (plan Task 10):

- **Mode → phase selection** (:func:`phase_sequence`): the ordered, de-duplicated
  phase list for each concrete mode.
- **Budgets**: each phase surfaces the configured cap that applies to it, or
  ``None`` when the phase has no configured budget.
- **Required handoff**: source-producing phases declare the ``source_phase`` they
  must import (the handoff contract in ``concepts/handoffs.py``).
- **Next-action instructions** (:func:`next_action`): the first incomplete phase
  as a :class:`NextAction`, or ``None`` when the run is finalizable.
- **Decision eligibility** (:func:`decision_eligibility`): the structural,
  phase-state-only prerequisite for running the ``decide`` phase. The CLI layers
  the actual Build gate on top of this — this check never scores concepts.
- **Finalization readiness** (:func:`is_finalizable`).

Design rules:

- **Experiment gate (hard invariant).** The engine never offers ``experiment`` as
  the next action unless ``decide`` is ``completed`` *and* the run recorded at
  least one Build decision (``checkpoint.counts[decide] > 0``). When no Build
  passed, ``experiment`` is skipped and the next action is the following phase
  (``calibration`` / ``report``).
- **``resume`` is not a stored mode.** A resumed run keeps its concrete start
  mode (``run.mode``); ``Mode.RESUME`` therefore has no fixed sequence and
  :func:`phase_sequence` rejects it. Resume is derived at the run level: the
  stored mode's sequence minus already-completed phases (see :func:`required_phases`).
- **Blocked/failed phases are surfaced, never skipped.** :func:`next_action`
  returns the first phase that is not ``completed``/``partial``. A ``blocked`` or
  ``failed`` phase is returned so the caller can retry/unblock it rather than
  silently bypassing it.
- **``partial`` counts as done.** A phase that completed with gaps still lets the
  run proceed (gaps are recorded separately as source coverage).
"""
from __future__ import annotations

from dataclasses import dataclass

from radar_cycles.config import RadarConfig
from radar_cycles.models import (
    Mode,
    PhaseName,
    PhaseStatus,
    RadarCycleRun,
)

__all__ = [
    "NextAction",
    "PHASE_SPECS",
    "phase_sequence",
    "required_phases",
    "build_decision_count",
    "has_build_decision",
    "next_action",
    "decision_eligibility",
    "is_finalizable",
]


# ── NextAction ──

@dataclass(frozen=True)
class NextAction:
    """The engine's instruction for the agent: what to run next.

    Fields
    ------
    phase:
        The phase to execute next.
    specialist_skill:
        The specialist skill to load for this phase (``"twitter-learning"``,
        ``"reddit-opportunity"``, ``"repo-trend"``), or ``""`` for a local phase
        the orchestrating skill performs itself.
    required_handoff:
        The ``source_phase`` value this phase must import (e.g. ``"x-discovery"``),
        or ``None`` for local phases (``reduce`` / ``decide`` / ``report`` / …)
        that produce no source handoff.
    budget:
        The configured per-phase cap, or ``None`` when the phase has no budget.
    completion_command:
        The CLI command to run next to record this phase's completion and receive
        the following action (e.g. ``radar-cycle import …`` / ``radar-cycle decide
        …`` / ``radar-cycle complete …`` for local phases).
    """

    phase: PhaseName
    specialist_skill: str
    required_handoff: str | None
    budget: int | None
    completion_command: str


# ── Phase → specialist skill / required handoff table ──
#
# This is the explicit, documented contract the Skill (and later CLI waves)
# consume. ``required_handoff`` mirrors the ``source_phase`` values of the handoff
# envelope (``concepts/handoffs.SourcePhase``); ``specialist_skill`` is the skill
# to load to produce that handoff.
#
#   phase          specialist_skill     required_handoff
#   ─────────────  ───────────────────  ────────────────
#   validate       ""                   None             (local: config review)
#   x-discovery    twitter-learning     x-discovery
#   reddit-scan    reddit-opportunity   reddit-scan
#   reduce         ""                   None             (local: concept capture)
#   verify         repo-trend           verify
#   decide         ""                   None             (local: decision gate)
#   experiment     ""                   None             (local: one experiment)
#   calibration    ""                   None             (local: reconcile)
#   source-audit   repo-trend           source-audit
#   report         ""                   None             (local: render report)

PHASE_SPECS: dict[PhaseName, tuple[str, str | None]] = {
    PhaseName.VALIDATE: ("", None),
    PhaseName.X_DISCOVERY: ("twitter-learning", "x-discovery"),
    PhaseName.REDDIT_SCAN: ("reddit-opportunity", "reddit-scan"),
    PhaseName.REDUCE: ("", None),
    PhaseName.VERIFY: ("repo-trend", "verify"),
    PhaseName.DECIDE: ("", None),
    PhaseName.EXPERIMENT: ("", None),
    PhaseName.CALIBRATION: ("", None),
    PhaseName.SOURCE_AUDIT: ("repo-trend", "source-audit"),
    PhaseName.REPORT: ("", None),
}

# Completion instruction for local phases (no source handoff) is the
# ``radar-cycle complete`` command; the CLI marks the phase done and returns the
# next action. (``decide`` and ``report`` have their own commands, handled below.)


# ── Mode → phase sequences ──

_DAILY = [
    PhaseName.VALIDATE,
    PhaseName.X_DISCOVERY,
    PhaseName.REDDIT_SCAN,
    PhaseName.REDUCE,
    PhaseName.REPORT,
]

_WEEKLY = [
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

_MONTHLY = [
    PhaseName.VALIDATE,
    PhaseName.SOURCE_AUDIT,
    PhaseName.CALIBRATION,
    PhaseName.REPORT,
]


def _union(*sequences: list[PhaseName]) -> list[PhaseName]:
    """Deterministic set-union of ordered sequences, preserving first appearance."""
    seen: set[PhaseName] = set()
    out: list[PhaseName] = []
    for sequence in sequences:
        for phase in sequence:
            if phase not in seen:
                seen.add(phase)
                out.append(phase)
    return out


# ``full`` = daily ∪ weekly phases + calibration (dedupe, deterministic order).
# Weekly already contains every daily phase plus ``calibration``, so the union
# collapses to the weekly sequence.
_FULL = _union(_WEEKLY, _DAILY, [PhaseName.CALIBRATION])

_SEQUENCES: dict[Mode, list[PhaseName]] = {
    Mode.DAILY: _DAILY,
    Mode.WEEKLY: _WEEKLY,
    Mode.MONTHLY: _MONTHLY,
    Mode.FULL: _FULL,
}


def phase_sequence(mode: Mode) -> list[PhaseName]:
    """Return the ordered phase sequence for a concrete ``mode``.

    - ``daily``:   validate, x-discovery, reddit-scan, reduce, report
    - ``weekly``:  validate, x-discovery, reddit-scan, reduce, verify, decide,
      experiment, calibration, report
    - ``monthly``: validate, source-audit, calibration, report
    - ``full``:    daily ∪ weekly phases + calibration (== the weekly order)
    - ``resume``:  **rejected** — a resumed run keeps its concrete start mode, so
      the sequence is derived from the stored mode + checkpoint, not from the
      ``resume`` verb (see :func:`required_phases`).
    """
    if not isinstance(mode, Mode):
        mode = Mode(mode)
    if mode == Mode.RESUME:
        raise ValueError(
            "Mode.RESUME has no fixed phase sequence; derive it from the run's "
            "stored mode and checkpoint via required_phases()"
        )
    return list(_SEQUENCES[mode])


# ── Build-decision recording ──

def build_decision_count(run: RadarCycleRun) -> int:
    """How many Build decisions this run recorded.

    The radar-cycle CLI (later wave) records the number of concepts that passed
    the Build gate under ``run.checkpoint.counts[decide]``. Zero means no Build
    passed, which makes ``experiment`` skippable.
    """
    return int(run.checkpoint.counts.get(PhaseName.DECIDE, 0))


def has_build_decision(run: RadarCycleRun) -> bool:
    """Whether the run recorded at least one concept that passed the Build gate."""
    return build_decision_count(run) > 0


def _experiment_required(run: RadarCycleRun) -> bool:
    """``experiment`` is required only when ``decide`` completed with a Build."""
    return (
        run.checkpoint.status_of(PhaseName.DECIDE) == PhaseStatus.COMPLETED
        and has_build_decision(run)
    )


def required_phases(run: RadarCycleRun) -> list[PhaseName]:
    """The run's mode sequence minus phases that are skippable.

    ``experiment`` is the only optional phase: when ``decide`` did not record a
    Build, ``experiment`` is removed so the run advances straight to the next
    phase (``calibration`` / ``report``) and can finalize without it.
    """
    sequence = phase_sequence(run.mode)
    if PhaseName.EXPERIMENT in sequence and not _experiment_required(run):
        sequence = [p for p in sequence if p != PhaseName.EXPERIMENT]
    return sequence


# ── Budgets ──

def _budget_for(phase: PhaseName, config: RadarConfig) -> int | None:
    """The configured per-phase cap, or ``None`` when the phase has no budget."""
    if phase == PhaseName.REDDIT_SCAN:
        return config.reddit.scan.limit if config.reddit is not None else None
    if phase == PhaseName.REDUCE:
        return config.daily_card_cap
    if phase == PhaseName.DECIDE:
        return config.weekly_build_cap
    return None


# ── Completion command ──

def _completion_command(phase: PhaseName, run_id: str) -> str:
    """The CLI command (or local instruction) that records ``phase`` completion."""
    _, handoff = PHASE_SPECS[phase]
    if handoff is not None:
        return (
            f"radar-cycle import {run_id} {phase.value} "
            f"--file output/handoffs/{phase.value}.json"
        )
    if phase == PhaseName.DECIDE:
        return f"radar-cycle decide {run_id} --json"
    if phase == PhaseName.REPORT:
        return f"radar-cycle finalize {run_id} --json"
    return f"radar-cycle complete {run_id} {phase.value} --json"


def _make_action(phase: PhaseName, run: RadarCycleRun, config: RadarConfig) -> NextAction:
    skill, handoff = PHASE_SPECS[phase]
    return NextAction(
        phase=phase,
        specialist_skill=skill,
        required_handoff=handoff,
        budget=_budget_for(phase, config),
        completion_command=_completion_command(phase, run.id),
    )


# ── Next action ──

def next_action(run: RadarCycleRun, config: RadarConfig) -> NextAction | None:
    """Return the first incomplete phase as a :class:`NextAction`, else ``None``.

    Iterates :func:`required_phases` in order and returns the first phase whose
    status is not ``completed``/``partial``. This surfaces ``pending`` /
    ``running`` / ``blocked`` / ``failed`` alike — the earliest one — so the
    caller can start, continue, retry, or unblock it. ``None`` means every
    required phase is done and the run is finalizable.

    The experiment gate is enforced structurally by :func:`required_phases`:
    ``experiment`` is only ever part of the sequence when ``decide`` completed
    with a Build decision, so it can never be returned otherwise.
    """
    for phase in required_phases(run):
        if run.checkpoint.status_of(phase) in (
            PhaseStatus.COMPLETED,
            PhaseStatus.PARTIAL,
        ):
            continue
        return _make_action(phase, run, config)
    return None


# ── Decision eligibility ──

def decision_eligibility(run: RadarCycleRun, config: RadarConfig) -> bool:
    """Whether the ``decide`` phase may run, on structural phase state alone.

    ``decide`` requires every phase that precedes it in the mode's sequence
    (``validate`` … ``reduce`` … ``verify``) to have reached a terminal state —
    ``completed`` or ``partial``. This is deliberately *not* a scoring check: it
    never evaluates the Build gate, budgets, or concept scores. The CLI layers
    the actual Build gate on top.

    ``config`` is accepted for a uniform engine API and reserved for the CLI's
    Build-gate layering; this structural check does not depend on it.
    """
    sequence = phase_sequence(run.mode)
    if PhaseName.DECIDE not in sequence:
        return False
    prerequisites = sequence[: sequence.index(PhaseName.DECIDE)]
    return all(
        run.checkpoint.status_of(phase) in (PhaseStatus.COMPLETED, PhaseStatus.PARTIAL)
        for phase in prerequisites
    )


# ── Finalization readiness ──

def is_finalizable(run: RadarCycleRun) -> bool:
    """True when every required phase is ``completed``, ``partial``, or skipped.

    ``experiment`` counts as *skipped* when no Build decision was recorded (it is
    removed from the required sequence), so a weekly/full run without a Build is
    finalizable once ``report`` (and ``calibration``) are done. Any remaining
    ``pending`` / ``running`` / ``blocked`` / ``failed`` phase makes the run not
    finalizable.
    """
    return all(
        run.checkpoint.status_of(phase) in (PhaseStatus.COMPLETED, PhaseStatus.PARTIAL)
        for phase in required_phases(run)
    )
