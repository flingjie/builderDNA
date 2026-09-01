"""radar-cycle — resumable concept-radar loop orchestration.

A thin Typer layer over the deterministic radar-cycle engine and checkpoint
store (``radar_cycles/``) plus the concept store and handoff import contracts
(``concepts/``). It does no web retrieval and no LLM: it only drives the
persisted state machine and imports already-collected source handoffs.

Subcommands
-----------
``start --radar NAME --mode MODE`` — create a checkpoint, return the first action.
``status RUN_ID``                    — phase snapshot + coverage + errors + next action.
``import RUN_ID PHASE --file PATH``  — import a source handoff, complete the phase.
``decide RUN_ID``                    — score reviewed concepts, record Build decisions.
``resume RUN_ID``                    — fail closed on config change, return next action.
``finalize RUN_ID``                  — render the report, complete report, finish the run.

Design rules honoured here:

- **JSON first.** Every command prints one versioned JSON envelope to stdout;
  human notices go to stderr so stdout stays machine-readable.
- **Never silently advance state.** A mismatched import phase, a changed config
  fingerprint, a non-eligible ``decide``, and a non-finalizable run all fail with
  a clean JSON error and a non-zero exit.
- **Idempotent replay.** A duplicate import (phase already completed, or the same
  handoff replayed against the store) imports no new records and returns the same
  next action rather than double-advancing.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import typer

from concepts.handoffs import SourceHandoffEnvelope, import_handoff
from concepts.scoring import EXPERIMENT_GATES, score as score_concept
from concepts.store import ConceptStore, ConceptStoreError, ConflictError
from models.concept import (
    ConceptCard,
    ConceptEvidence,
    EvidenceRole,
    EvidenceStrength,
    PortfolioStage,
    SmallestExperiment,
)
from models.radar_payload import SourceStatus
from observability import RunTelemetry
from radar_cycles import checkpoint
from radar_cycles.config import RadarConfig, RadarConfigError, load_radar_config
from radar_cycles.engine import (
    PHASE_SPECS,
    NextAction,
    decision_eligibility,
    is_finalizable,
    next_action,
)
from radar_cycles.models import Mode, PhaseName, PhaseStatus, RadarCycleRun
from radar_cycles.rendering import (
    CalibrationResult,
    ConceptFlows,
    Decision,
    EvidenceCounts,
    EvidenceSummary,
    RadarCycleReport,
    ReportRenderError,
    write_report,
)

SCHEMA_VERSION = "builderdna.radar-cycle.v1"

radar_cycle = typer.Typer(
    name="radar-cycle",
    help="Resumable concept-radar loop: start, import source handoffs, decide, resume, finalize.",
    no_args_is_help=True,
)

# ── Errors ──


class RadarCycleCommandError(Exception):
    """Base error surfaced as a clean JSON failure."""

    exit_code = 1

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class RadarCycleValidationError(RadarCycleCommandError):
    """Bad input / mismatched phase / changed fingerprint / unknown run."""

    exit_code = 2


class RadarCycleGateError(RadarCycleCommandError):
    """A structural gate refused the operation (e.g. not finalizable)."""

    exit_code = 4


# ── Small utilities ──


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _notice(message: str) -> None:
    """Human-facing notice on stderr, keeping stdout a pure JSON stream."""
    print(message, file=sys.stderr)


def _generate_run_id(radar: str) -> str:
    """A unique, filesystem-safe run id derived from the radar name."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    safe = re.sub(r"[^a-z0-9]+", "-", (radar or "").lower()).strip("-") or "radar"
    return f"{safe}-{stamp}-{uuid4().hex[:6]}"


def _run_store_dir(state_dir: str | Path) -> str:
    """Checkpoint store directory (holds one ``{run-id}.json`` per run)."""
    return str(Path(state_dir) / "radar_cycles")


def _load_config(
    name: str, config_dir: str, reddit_dir: str
) -> RadarConfig:
    try:
        return load_radar_config(name, config_dir, reddit_dir)
    except RadarConfigError as exc:
        raise RadarCycleValidationError(str(exc))


def _load_run(run_id: str, state_dir: str) -> RadarCycleRun:
    try:
        return checkpoint.load(run_id, store_dir=_run_store_dir(state_dir))
    except FileNotFoundError:
        raise RadarCycleValidationError(f"no checkpoint for run {run_id!r}")


def _check_fingerprint(run_obj: RadarCycleRun, config: RadarConfig) -> None:
    """Fail closed if the config fingerprint drifted from the one at ``start``.

    Every state-advancing command checks this (not just ``resume``) so an edited
    config can never silently alter an in-progress run.
    """
    if config.fingerprint != run_obj.checkpoint.config_fingerprint:
        raise RadarCycleValidationError(
            "config fingerprint changed since start; refusing to advance state "
            f"(stored {run_obj.checkpoint.config_fingerprint[:12]}..., "
            f"current {config.fingerprint[:12]}...) to avoid silently continuing "
            "under different configuration"
        )


def _draft_experiment(card: ConceptCard) -> SmallestExperiment:
    """Derive a minimal DRAFT smallest experiment for a build-worthy card.

    A genuinely falsifiable threshold is a semantic judgment the orchestrating
    skill must supply; these placeholders are marked ``[draft]`` so the fde-gym
    export (which fails closed on non-falsifiable fields) surfaces the need to
    refine them before running.
    """
    problem = (card.problem or card.title or "the problem").strip()
    return SmallestExperiment(
        hypothesis=f"{card.title}: {problem}",
        target="[draft] the target user/system (refine)",
        artifact=f"[draft] a minimal prototype for {card.title}",
        success_threshold="[draft] observable success metric (refine)",
        failure_threshold="[draft] observable failure metric, distinct from success (refine)",
        stop_condition="[draft] bounded time/cost budget (refine)",
    )


def _status_snapshot(run: RadarCycleRun) -> dict:
    return {
        phase.value: run.checkpoint.status_of(phase).value for phase in PhaseName
    }


def _action_payload(action: NextAction | None) -> dict | None:
    if action is None:
        return None
    return {
        "phase": action.phase.value,
        "specialist_skill": action.specialist_skill,
        "required_handoff": action.required_handoff,
        "budget": action.budget,
        "completion_command": action.completion_command,
    }


def _complete_phase(run_id: str, phase: PhaseName, state_dir: str) -> None:
    """Drive ``phase`` to ``completed`` through the allowed transition table."""
    store_dir = _run_store_dir(state_dir)
    status = checkpoint.load(run_id, store_dir=store_dir).checkpoint.status_of(phase)

    if status == PhaseStatus.PENDING:
        checkpoint.transition(run_id, phase, "running", store_dir=store_dir)
        checkpoint.transition(run_id, phase, "completed", store_dir=store_dir)
    elif status == PhaseStatus.RUNNING:
        checkpoint.transition(run_id, phase, "completed", store_dir=store_dir)
    elif status in (PhaseStatus.PARTIAL, PhaseStatus.FAILED):
        # one read-only retry, then complete
        checkpoint.transition(run_id, phase, "running", store_dir=store_dir)
        checkpoint.transition(run_id, phase, "completed", store_dir=store_dir)
    elif status == PhaseStatus.BLOCKED:
        # a fresh handoff is changed input, so unblocking is allowed here
        checkpoint.transition(
            run_id, phase, "running", allow_unblock=True, store_dir=store_dir
        )
        checkpoint.transition(run_id, phase, "completed", store_dir=store_dir)
    else:  # completed / partial — already terminal
        raise RadarCycleValidationError(
            f"phase {phase.value!r} is already {status.value}"
        )


def _record_handoff_coverage(
    run_id: str, envelope: SourceHandoffEnvelope, state_dir: str
) -> None:
    """Record per-source coverage from a handoff envelope onto the checkpoint."""
    status_map = {
        "complete": SourceStatus.COMPLETE,
        "partial": SourceStatus.PARTIAL,
        "unavailable": SourceStatus.UNAVAILABLE,
    }
    status = status_map[envelope.coverage.value]
    note = "; ".join(envelope.coverage_notes) or (
        f"{envelope.source_phase.value} coverage {envelope.coverage.value}"
    )
    store_dir = _run_store_dir(state_dir)
    seen: set[str] = set()
    for item in envelope.items:
        source_value = item.source.value
        if source_value in seen:
            continue
        seen.add(source_value)
        checkpoint.record_coverage(
            run_id, source_value, status.value, note, store_dir=store_dir
        )


# ── Result envelope ──


def _ok(command: str, action: str, data: dict, changed: list[str], stats: dict) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "command": command,
        "ok": True,
        "action": action,
        "changed": changed,
        "data": data,
        "stats": stats,
        "computed_at": _now_iso(),
    }


def _error(
    command: str, message: str, details: dict | None = None, exit_code: int = 1
) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "error": message,
        "exit_code": exit_code,
        "details": details or {},
        "computed_at": _now_iso(),
    }


def _emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _finalize(command: str, func) -> None:
    """Run ``func`` and emit its JSON result; translate known errors to exit codes."""
    tel = RunTelemetry()
    try:
        result = func()
        payload = _ok(
            command,
            result["action"],
            result["data"],
            result.get("changed", []),
            stats={"elapsed_seconds": tel.elapsed_seconds},
        )
        _emit(payload)
    except RadarCycleCommandError as exc:
        _emit(_error(command, exc.message, exc.details, exc.exit_code))
        raise typer.Exit(exc.exit_code)
    except ReportRenderError as exc:
        _emit(_error(command, str(exc), exit_code=1))
        raise typer.Exit(1)
    except ConflictError as exc:
        _emit(_error(command, str(exc), exit_code=3))
        raise typer.Exit(3)
    except ConceptStoreError as exc:
        _emit(_error(command, str(exc), exit_code=1))
        raise typer.Exit(1)
    except ValueError as exc:
        _emit(_error(command, str(exc), exit_code=1))
        raise typer.Exit(1)


# ── start ──


@radar_cycle.command("start")
def start_cmd(
    radar: str = typer.Option(..., "--radar", help="Radar name (config/radars/<name>.yaml)"),
    mode: str = typer.Option(..., "--mode", help="Mode: daily | weekly | monthly | full"),
    state_dir: str = typer.Option("state", "--state-dir", help="State directory"),
    config_dir: str = typer.Option("config/radars", "--config-dir", help="Radar config directory"),
    reddit_dir: str = typer.Option("config/reddit_feeds", "--reddit-dir", help="Reddit preset directory"),
    json_flag: bool = typer.Option(False, "--json", help="Emit a JSON envelope (JSON-first)"),
) -> None:
    """Create a radar-cycle checkpoint and return the first NextAction."""

    def run() -> dict:
        config = _load_config(radar, config_dir, reddit_dir)
        try:
            mode_enum = Mode(mode)
        except ValueError:
            raise RadarCycleValidationError(
                f"invalid mode {mode!r}; expected one of "
                f"{[m.value for m in Mode if m != Mode.RESUME]}"
            )
        if mode_enum == Mode.RESUME:
            raise RadarCycleValidationError(
                "start requires a concrete mode (daily|weekly|monthly|full); "
                "'resume' is derived from the stored run, not a start mode"
            )

        run_id = _generate_run_id(radar)
        checkpoint.create(
            run_id,
            radar,
            mode_enum,
            config.limits,
            config.fingerprint,
            store_dir=_run_store_dir(state_dir),
        )
        run_obj = checkpoint.load(run_id, store_dir=_run_store_dir(state_dir))
        action = next_action(run_obj, config)
        _notice(f"radar-cycle start: run {run_id} ({mode_enum.value})")

        return {
            "action": "started",
            "changed": ["checkpoint created"],
            "data": {
                "run_id": run_id,
                "radar": radar,
                "mode": mode_enum.value,
                "config_fingerprint": config.fingerprint,
                "next_action": _action_payload(action),
                "phase_status": _status_snapshot(run_obj),
            },
        }

    _finalize("radar-cycle.start", run)


# ── complete ──


@radar_cycle.command("complete")
def complete_cmd(
    run_id: str = typer.Argument(..., help="Run ID"),
    phase: str = typer.Argument(..., help="Local phase to complete"),
    state_dir: str = typer.Option("state", "--state-dir", help="State directory"),
    config_dir: str = typer.Option("config/radars", "--config-dir", help="Radar config directory"),
    reddit_dir: str = typer.Option("config/reddit_feeds", "--reddit-dir", help="Reddit preset directory"),
    json_flag: bool = typer.Option(False, "--json", help="Emit a JSON envelope (JSON-first)"),
) -> None:
    """Complete a local phase (validate/reduce/experiment/calibration)."""

    def run() -> dict:
        run_obj = _load_run(run_id, state_dir)
        config = _load_config(run_obj.radar, config_dir, reddit_dir)
        _check_fingerprint(run_obj, config)

        try:
            phase_enum = PhaseName(phase)
        except ValueError:
            raise RadarCycleValidationError(
                f"invalid phase {phase!r}; expected one of {[p.value for p in PhaseName]}"
            )

        _, required_handoff = PHASE_SPECS[phase_enum]
        if required_handoff is not None:
            raise RadarCycleValidationError(
                f"phase {phase!r} requires a source handoff — use "
                "`radar-cycle import`, not `complete`"
            )
        if phase_enum == PhaseName.DECIDE:
            raise RadarCycleValidationError(
                "use `radar-cycle decide` to complete the decide phase"
            )
        if phase_enum == PhaseName.REPORT:
            raise RadarCycleValidationError(
                "use `radar-cycle finalize` to complete the report phase"
            )

        _complete_phase(run_id, phase_enum, state_dir)
        run2 = checkpoint.load(run_id, store_dir=_run_store_dir(state_dir))
        next_act = next_action(run2, config)
        _notice(f"radar-cycle complete: {phase_enum.value} completed")

        return {
            "action": "completed",
            "changed": [f"phase {phase_enum.value} completed"],
            "data": {
                "run_id": run_id,
                "phase": phase_enum.value,
                "next_action": _action_payload(next_act),
                "phase_status": _status_snapshot(run2),
            },
        }

    _finalize("radar-cycle.complete", run)


# ── status ──


@radar_cycle.command("status")
def status_cmd(
    run_id: str = typer.Argument(..., help="Run ID"),
    state_dir: str = typer.Option("state", "--state-dir", help="State directory"),
    config_dir: str = typer.Option("config/radars", "--config-dir", help="Radar config directory"),
    reddit_dir: str = typer.Option("config/reddit_feeds", "--reddit-dir", help="Reddit preset directory"),
    json_flag: bool = typer.Option(False, "--json", help="Emit a JSON envelope (JSON-first)"),
) -> None:
    """Return the run's phase snapshot, coverage, errors, and next action."""

    def run() -> dict:
        run_obj = _load_run(run_id, state_dir)
        config = _load_config(run_obj.radar, config_dir, reddit_dir)
        action = next_action(run_obj, config)
        doc = checkpoint.load_document(run_id, store_dir=_run_store_dir(state_dir))

        return {
            "action": "status",
            "changed": [],
            "data": {
                "run_id": run_id,
                "radar": run_obj.radar,
                "mode": run_obj.mode.value,
                "run_status": doc.run_status,
                "config_fingerprint": run_obj.checkpoint.config_fingerprint,
                "phase_status": _status_snapshot(run_obj),
                "counts": {
                    phase.value: count for phase, count in run_obj.checkpoint.counts.items()
                },
                "errors": list(run_obj.checkpoint.errors),
                "coverage": [c.model_dump(mode="json") for c in doc.coverage],
                "outputs": doc.outputs,
                "next_action": _action_payload(action),
            },
        }

    _finalize("radar-cycle.status", run)


# ── import ──


@radar_cycle.command("import")
def import_cmd(
    run_id: str = typer.Argument(..., help="Run ID"),
    phase: str = typer.Argument(..., help="Phase whose handoff is being imported"),
    handoff_file: str = typer.Option(..., "--file", "-f", help="Handoff JSON file path"),
    state_dir: str = typer.Option("state", "--state-dir", help="State directory"),
    config_dir: str = typer.Option("config/radars", "--config-dir", help="Radar config directory"),
    reddit_dir: str = typer.Option("config/reddit_feeds", "--reddit-dir", help="Reddit preset directory"),
    json_flag: bool = typer.Option(False, "--json", help="Emit a JSON envelope (JSON-first)"),
) -> None:
    """Import a source handoff for ``PHASE``, complete the phase, return the next action."""

    def run() -> dict:
        run_obj = _load_run(run_id, state_dir)
        config = _load_config(run_obj.radar, config_dir, reddit_dir)
        _check_fingerprint(run_obj, config)

        try:
            phase_enum = PhaseName(phase)
        except ValueError:
            raise RadarCycleValidationError(
                f"invalid phase {phase!r}; expected one of {[p.value for p in PhaseName]}"
            )

        _, required_handoff = PHASE_SPECS[phase_enum]
        if required_handoff is None:
            raise RadarCycleValidationError(
                f"phase {phase!r} is a local phase with no handoff to import "
                f"(completion command: no import; use the phase's own command)"
            )

        action = next_action(run_obj, config)
        status = run_obj.checkpoint.status_of(phase_enum)

        # Duplicate import: the phase was already completed/partial. Replay the
        # same next action with no new records — never double-advance.
        if status in (PhaseStatus.COMPLETED, PhaseStatus.PARTIAL):
            return {
                "action": "duplicate",
                "changed": [],
                "data": {
                    "run_id": run_id,
                    "phase": phase_enum.value,
                    "import": {
                        "imported": 0,
                        "skipped_idempotent": 0,
                        "conflicts": [],
                        "concept_ids_affected": [],
                    },
                    "next_action": _action_payload(action),
                    "phase_status": _status_snapshot(run_obj),
                },
            }

        if action is None:
            raise RadarCycleValidationError(
                f"run {run_id!r} has no incomplete phase to import (already finalizable)"
            )
        if action.phase != phase_enum:
            raise RadarCycleValidationError(
                f"phase mismatch: current incomplete phase is "
                f"{action.phase.value!r}, not {phase_enum.value!r}"
            )

        path = Path(handoff_file)
        if not path.exists():
            raise RadarCycleValidationError(f"handoff file not found: {handoff_file}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RadarCycleValidationError(f"invalid handoff JSON: {exc}")
        if not isinstance(raw, dict):
            raise RadarCycleValidationError("handoff must be a JSON object")
        try:
            envelope = SourceHandoffEnvelope.model_validate(raw)
        except Exception as exc:
            raise RadarCycleValidationError(f"invalid handoff envelope: {exc}")

        if envelope.source_phase.value != phase_enum.value:
            raise RadarCycleValidationError(
                f"handoff source_phase {envelope.source_phase.value!r} does not "
                f"match phase {phase_enum.value!r}"
            )

        store = ConceptStore(state_dir=state_dir)
        result = import_handoff(store, envelope)

        if result.conflicts:
            raise ConflictError(
                f"handoff import had {len(result.conflicts)} conflict(s); refusing "
                f"to complete phase {phase_enum.value!r}: " + "; ".join(result.conflicts[:5])
            )

        # Complete the phase, then record counts + output + coverage.
        _complete_phase(run_id, phase_enum, state_dir)
        store_dir = _run_store_dir(state_dir)
        run2 = checkpoint.load(run_id, store_dir=store_dir)
        run2.checkpoint.counts[phase_enum] = result.imported
        checkpoint.save(run2, store_dir=store_dir)
        checkpoint.record_output(
            run_id, phase_enum, handoff_file, store_dir=store_dir
        )
        _record_handoff_coverage(run_id, envelope, state_dir)

        run3 = checkpoint.load(run_id, store_dir=store_dir)
        next_act = next_action(run3, config)
        _notice(
            f"radar-cycle import: {phase_enum.value} imported "
            f"{result.imported} record(s) (skipped {result.skipped_idempotent})"
        )

        return {
            "action": "imported",
            "changed": ["phase completed", "evidence imported", "output recorded"],
            "data": {
                "run_id": run_id,
                "phase": phase_enum.value,
                "import": {
                    "imported": result.imported,
                    "skipped_idempotent": result.skipped_idempotent,
                    "conflicts": result.conflicts,
                    "concept_ids_affected": result.concept_ids_affected,
                },
                "next_action": _action_payload(next_act),
                "phase_status": _status_snapshot(run3),
            },
        }

    _finalize("radar-cycle.import", run)


# ── decide ──


@radar_cycle.command("decide")
def decide_cmd(
    run_id: str = typer.Argument(..., help="Run ID"),
    state_dir: str = typer.Option("state", "--state-dir", help="State directory"),
    config_dir: str = typer.Option("config/radars", "--config-dir", help="Radar config directory"),
    reddit_dir: str = typer.Option("config/reddit_feeds", "--reddit-dir", help="Reddit preset directory"),
    json_flag: bool = typer.Option(False, "--json", help="Emit a JSON envelope (JSON-first)"),
) -> None:
    """Score reviewed concepts, enforce the one-Build cap, record the Build count."""

    def run() -> dict:
        run_obj = _load_run(run_id, state_dir)
        config = _load_config(run_obj.radar, config_dir, reddit_dir)
        _check_fingerprint(run_obj, config)
        store = ConceptStore(state_dir=state_dir)

        status = run_obj.checkpoint.status_of(PhaseName.DECIDE)
        if status in (PhaseStatus.COMPLETED, PhaseStatus.PARTIAL):
            existing = run_obj.checkpoint.counts.get(PhaseName.DECIDE, 0)
            return {
                "action": "duplicate",
                "changed": [],
                "data": {
                    "run_id": run_id,
                    "weekly_build_cap": config.weekly_build_cap,
                    "build_decisions": existing,
                    "decisions": [],
                    "next_action": _action_payload(next_action(run_obj, config)),
                    "phase_status": _status_snapshot(run_obj),
                },
            }

        if not decision_eligibility(run_obj, config):
            raise RadarCycleGateError(
                "decide is not eligible: its prerequisite phases are not all "
                "completed or partial"
            )

        reviewed = sorted(
            (c for c in store.list_concepts() if c.stage == PortfolioStage.VERIFY),
            key=lambda c: c.id,
        )
        cap = config.weekly_build_cap
        builds_used = 0
        decisions: list[dict] = []
        experiment_failed = set(EXPERIMENT_GATES)
        for card in reviewed:
            evidence = store.list_evidence(card.id)
            result = score_concept(
                card,
                evidence,
                weekly_builds_used=builds_used,
                weekly_builds_cap=cap,
            )
            # Decide on the evidence gates alone: a VERIFY card has no
            # smallest experiment yet, so the experiment gates are evaluated at
            # promotion time, not here.
            decision_failed = [g for g in result.failed_gates if g not in experiment_failed]
            passed = not decision_failed
            if passed and builds_used < cap:
                # Promote to BUILD, attaching a (possibly draft) experiment so the
                # decision is persisted on the card and the experiment phase can
                # export/refine it.
                experiment = card.smallest_experiment or _draft_experiment(card)
                store.upsert_concept(
                    card.model_copy(
                        update={
                            "stage": PortfolioStage.BUILD,
                            "smallest_experiment": experiment,
                        }
                    )
                )
                builds_used += 1
                decisions.append(
                    {
                        "concept_id": card.id,
                        "total": result.total,
                        "passed": True,
                        "promoted": True,
                        "deferred_experiment": True,
                    }
                )
            else:
                decisions.append(
                    {
                        "concept_id": card.id,
                        "total": result.total,
                        "passed": False,
                        "promoted": False,
                        "failed_gates": decision_failed,
                    }
                )

        store_dir = _run_store_dir(state_dir)
        run2 = checkpoint.load(run_id, store_dir=store_dir)
        # This count is the contract the engine reads to require ``experiment``.
        run2.checkpoint.counts[PhaseName.DECIDE] = builds_used
        checkpoint.save(run2, store_dir=store_dir)
        _complete_phase(run_id, PhaseName.DECIDE, state_dir)

        run3 = checkpoint.load(run_id, store_dir=store_dir)
        next_act = next_action(run3, config)
        _notice(f"radar-cycle decide: {builds_used} build decision(s) recorded")

        return {
            "action": "decided",
            "changed": [
                "decide completed",
                f"{builds_used} build decision(s) recorded",
            ],
            "data": {
                "run_id": run_id,
                "weekly_build_cap": cap,
                "build_decisions": builds_used,
                "decisions": decisions,
                "next_action": _action_payload(next_act),
                "phase_status": _status_snapshot(run3),
            },
        }

    _finalize("radar-cycle.decide", run)


# ── resume ──


@radar_cycle.command("resume")
def resume_cmd(
    run_id: str = typer.Argument(..., help="Run ID"),
    state_dir: str = typer.Option("state", "--state-dir", help="State directory"),
    config_dir: str = typer.Option("config/radars", "--config-dir", help="Radar config directory"),
    reddit_dir: str = typer.Option("config/reddit_feeds", "--reddit-dir", help="Reddit preset directory"),
    json_flag: bool = typer.Option(False, "--json", help="Emit a JSON envelope (JSON-first)"),
) -> None:
    """Re-check the config fingerprint and return the first incomplete phase."""

    def run() -> dict:
        run_obj = _load_run(run_id, state_dir)
        config = _load_config(run_obj.radar, config_dir, reddit_dir)

        _check_fingerprint(run_obj, config)

        action = next_action(run_obj, config)
        _notice(f"radar-cycle resume: run {run_id} ({run_obj.mode.value})")

        return {
            "action": "resumed",
            "changed": [],
            "data": {
                "run_id": run_id,
                "radar": run_obj.radar,
                "mode": run_obj.mode.value,
                "config_fingerprint": config.fingerprint,
                "phase_status": _status_snapshot(run_obj),
                "next_action": _action_payload(action),
            },
        }

    _finalize("radar-cycle.resume", run)


# ── finalize ──


def _finalize_gate(run_obj: RadarCycleRun, config) -> str | None:
    """Return a refusal message if finalize must not proceed, else ``None``.

    ``finalize`` is what completes the ``report`` phase, so a run whose only
    remaining phase is ``report`` may finalize. Any other non-terminal required
    phase (and a blocked/failed ``report``) blocks finalization.
    """
    if is_finalizable(run_obj):
        return None  # everything (including report) already done; idempotent
    action = next_action(run_obj, config)
    if action is not None and action.phase == PhaseName.REPORT:
        status = run_obj.checkpoint.status_of(PhaseName.REPORT)
        if status in (PhaseStatus.BLOCKED, PhaseStatus.FAILED):
            return f"cannot finalize: report phase is {status.value}"
        return None
    if action is None:
        return "cannot finalize: unknown phase state"
    status = run_obj.checkpoint.status_of(action.phase)
    return (
        f"cannot finalize: phase {action.phase.value!r} is {status.value}; "
        "all required phases must be completed or partial before finalizing"
    )


def _complete_report_phase(run_id: str, state_dir: str) -> None:
    store_dir = _run_store_dir(state_dir)
    status = checkpoint.load(run_id, store_dir=store_dir).checkpoint.status_of(
        PhaseName.REPORT
    )
    if status == PhaseStatus.PENDING:
        checkpoint.transition(run_id, PhaseName.REPORT, "running", store_dir=store_dir)
        checkpoint.transition(run_id, PhaseName.REPORT, "completed", store_dir=store_dir)
    elif status == PhaseStatus.RUNNING:
        checkpoint.transition(run_id, PhaseName.REPORT, "completed", store_dir=store_dir)
    # completed / partial are already terminal


def _build_report(run_obj, store, coverage) -> RadarCycleReport:
    cards = store.list_concepts()
    evidence = store.list_evidence()

    created = [c for c in cards if c.stage != PortfolioStage.DROP]
    dropped = [c for c in cards if c.stage == PortfolioStage.DROP]
    advanced = [
        c for c in cards if c.stage in (PortfolioStage.VERIFY, PortfolioStage.BUILD)
    ]

    supporting = [e for e in evidence if e.role != EvidenceRole.COUNTER]
    counter = [e for e in evidence if e.role == EvidenceRole.COUNTER]
    independence_keys = {e.independence_key for e in evidence}

    decisions = []
    for c in cards:
        if c.stage == PortfolioStage.BUILD:
            decisions.append(
                Decision(
                    concept_id=c.id,
                    stage=PortfolioStage.BUILD,
                    reason=c.prediction or "passed build gate",
                )
            )
        elif c.stage == PortfolioStage.DROP:
            decisions.append(
                Decision(
                    concept_id=c.id,
                    stage=PortfolioStage.DROP,
                    reason=c.lesson or "dropped",
                )
            )

    strength_order = {
        EvidenceStrength.STRONG: 3,
        EvidenceStrength.MODERATE: 2,
        EvidenceStrength.WEAK: 1,
    }

    def _summaries(records: list[ConceptEvidence]) -> list[EvidenceSummary]:
        ordered = sorted(
            records, key=lambda e: strength_order[e.strength], reverse=True
        )[:5]
        return [
            EvidenceSummary(
                evidence_id=e.id,
                concept_id=e.concept_id,
                source_type=e.source_type,
                role=e.role,
                strength=e.strength,
                directness=e.directness,
                independence_key=e.independence_key,
                note=e.note,
            )
            for e in ordered
        ]

    coverage_gaps = [
        c.note for c in coverage if c.status in (SourceStatus.PARTIAL, SourceStatus.UNAVAILABLE)
    ]

    return RadarCycleReport(
        run=run_obj,
        source_coverage=coverage,
        coverage_gaps=coverage_gaps,
        concepts=ConceptFlows(
            created=created, merged=[], advanced=advanced, dropped=dropped
        ),
        evidence_counts=EvidenceCounts(
            total=len(evidence),
            support=len(supporting),
            counterevidence=len(counter),
            independence_keys=len(independence_keys),
        ),
        decisions=decisions,
        top_support=_summaries(supporting),
        top_counterevidence=_summaries(counter),
        experiment=None,
        calibration=CalibrationResult(),
        errors=list(run_obj.checkpoint.errors),
        next_recommended_cycle=None,
    )


@radar_cycle.command("finalize")
def finalize_cmd(
    run_id: str = typer.Argument(..., help="Run ID"),
    state_dir: str = typer.Option("state", "--state-dir", help="State directory"),
    config_dir: str = typer.Option("config/radars", "--config-dir", help="Radar config directory"),
    reddit_dir: str = typer.Option("config/reddit_feeds", "--reddit-dir", help="Reddit preset directory"),
    out_dir: str = typer.Option("output/radar_cycles", "--out-dir", help="Report output directory"),
    json_flag: bool = typer.Option(False, "--json", help="Emit a JSON envelope (JSON-first)"),
) -> None:
    """Render the cycle report, complete the report phase, and finish the run."""

    def run() -> dict:
        run_obj = _load_run(run_id, state_dir)
        config = _load_config(run_obj.radar, config_dir, reddit_dir)
        _check_fingerprint(run_obj, config)

        refusal = _finalize_gate(run_obj, config)
        if refusal:
            raise RadarCycleGateError(refusal)

        store = ConceptStore(state_dir=state_dir)
        coverage = checkpoint.coverage_of(run_id, store_dir=_run_store_dir(state_dir))
        report = _build_report(run_obj, store, coverage)
        json_path, md_path = write_report(report, out_dir=out_dir)

        _complete_report_phase(run_id, state_dir)
        checkpoint.finish(run_id, store_dir=_run_store_dir(state_dir))

        final_run = checkpoint.load(run_id, store_dir=_run_store_dir(state_dir))
        _notice(f"radar-cycle finalize: run {run_id} complete -> {json_path}")

        return {
            "action": "finalized",
            "changed": ["report written", "report phase completed", "run finished"],
            "data": {
                "run_id": run_id,
                "json_path": json_path,
                "md_path": md_path,
                "run_status": "completed",
                "phase_status": _status_snapshot(final_run),
            },
        }

    _finalize("radar-cycle.finalize", run)
