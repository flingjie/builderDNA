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

    def run() -> dict:
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
        return service.run_action(request)

    _finalize("investigate.run", run)


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

    def propose() -> dict:
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
        return service.propose(investigation_id, model)

    _finalize("investigate.propose", propose)


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
