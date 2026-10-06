"""repo-learning — resumable development-episode learning.

A thin Typer layer over the deterministic repo-evolution-learning collection,
validation, and rendering modules. It does no web search, no content fetching,
and no LLM — search and content are skill-owned (via opencli/gh); the skill writes
``analysis.json`` into the run workspace and this CLI validates and renders it.

Design rules honoured here:

- **JSON first.** Every command prints one versioned JSON envelope to stdout;
  human notices go to stderr.
- **Never silently advance state.** A changed request fingerprint fails ``resume``
  closed rather than silently continuing under different inputs.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer

from config import load_config
from repo_learning import collection, render as render_mod, validation, workspace
from repo_learning.models import RunManifest, StageStatus
from repo_learning.request import (
    RequestError,
    RequestOutput,
    RequestSpec,
    generate_run_id,
    load_request,
    parse_repo_ref,
    request_hash,
)

SCHEMA_VERSION = "builderdna.repo-learning.v1"

repo_learning = typer.Typer(
    name="repo-learning",
    help="Reconstruct a development episode and its promotion, then render an interactive HTML report.",
    no_args_is_help=True,
)

#: Run stages in order. ``search`` / ``content`` / ``analyze`` are skill-owned;
#: the CLI owns ``init``, ``collect``, ``validate``, ``render``.
STAGES = ["init", "collect", "search", "content", "analyze", "validate", "render"]


class RepoLearningCommandError(Exception):
    """Base error surfaced as a clean JSON failure."""

    exit_code = 1

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class RepoLearningValidationError(RepoLearningCommandError):
    """Bad input / changed fingerprint / missing workspace."""

    exit_code = 2


# ── Small utilities ──


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _notice(message: str) -> None:
    print(message, file=sys.stderr)


def _ok(command: str, action: str, data: dict, changed: list[str]) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "command": command,
        "ok": True,
        "action": action,
        "changed": changed,
        "data": data,
        "computed_at": _now_iso(),
    }


def _error(command: str, message: str, details: dict | None = None, exit_code: int = 1) -> dict:
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
    try:
        result = func()
        _emit(_ok(command, result["action"], result["data"], result.get("changed", [])))
    except RepoLearningCommandError as exc:
        _emit(_error(command, exc.message, exc.details, exc.exit_code))
        raise typer.Exit(exc.exit_code)
    except FileNotFoundError as exc:
        _emit(_error(command, str(exc), exit_code=2))
        raise typer.Exit(2)
    except ValueError as exc:
        _emit(_error(command, str(exc), exit_code=1))
        raise typer.Exit(1)


def _resolve_run_dir(run_dir: str) -> Path:
    path = Path(run_dir)
    if not (path / workspace.MANIFEST_FILE).exists():
        raise RepoLearningValidationError(f"no repo-learning run at {run_dir} (missing manifest.json)")
    return path


def _next_stage(manifest: RunManifest) -> str | None:
    for stage in STAGES:
        status = manifest.stage_status.get(stage, StageStatus.PENDING)
        if status in (StageStatus.PENDING, StageStatus.FAILED, StageStatus.PARTIAL):
            return stage
    return None


def _set_stage(run_dir: Path, stage: str, status: StageStatus) -> None:
    manifest = workspace.load_manifest(run_dir)
    manifest.stage_status[stage] = status
    workspace.save_manifest(run_dir, manifest)


# ── init ──


@repo_learning.command("init")
def init_cmd(
    repo: str = typer.Option(..., "--repo", help="GitHub repo URL or owner/repo"),
    entry_url: str | None = typer.Option(None, "--entry-url", help="Optional PR/Issue URL"),
    focus: str | None = typer.Option(None, "--focus", help="Optional feature/dir/design-question focus"),
    learning_goal: str | None = typer.Option(None, "--learning-goal", help="Learning goal"),
    mode: str = typer.Option("report", "--mode", help="report | guided"),
    out_dir: str = typer.Option("output", "--out-dir", help="Output root directory"),
    config_path: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
) -> None:
    """Create a run workspace (request.yaml + manifest.json) and return its id."""

    def run() -> dict:
        if mode not in ("report", "guided"):
            raise RepoLearningValidationError(f"invalid mode {mode!r}; expected report|guided")
        try:
            owner, name = parse_repo_ref(repo)
        except RequestError as exc:
            raise RepoLearningValidationError(str(exc))

        cfg = load_config(config_path)
        rl = cfg.repo_learning
        spec = RequestSpec(
            repo=f"https://github.com/{owner}/{name}",
            entry_url=entry_url,
            focus=focus,
            learning_goal=learning_goal or "学习开发取舍与传播方法",
            mode=mode,  # type: ignore[arg-type]
            promotion_research=rl.promotion_research,
            limits=rl.limits,
            output=RequestOutput(language=rl.output_language),
        )
        run_id = generate_run_id(repo)
        run_dir = Path(out_dir) / "repo-learning" / run_id
        manifest = RunManifest(
            run_id=run_id,
            request_hash=request_hash(spec),
            stage_status={stage: StageStatus.PENDING for stage in STAGES},
        )
        manifest.stage_status["init"] = StageStatus.COMPLETED
        workspace.init_workspace(run_dir, spec, manifest)
        _notice(f"repo-learning init: run {run_id} -> {run_dir}")

        return {
            "action": "started",
            "changed": ["workspace created"],
            "data": {
                "run_id": run_id,
                "run_dir": str(run_dir),
                "repo": f"{owner}/{name}",
                "request_hash": manifest.request_hash,
                "next_stage": _next_stage(manifest),
            },
        }

    _finalize("repo-learning.init", run)


# ── collect ──


@repo_learning.command("collect")
def collect_cmd(
    run_dir: str = typer.Option(..., "--run-dir", help="Run workspace directory"),
    entry_url: str | None = typer.Option(None, "--entry-url", help="Override the PR/Issue to fetch detail for"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass HTTP cache"),
    force: bool = typer.Option(False, "--force", help="Re-collect even if already completed"),
    config_path: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
) -> None:
    """Collect GitHub material (metadata, README, PR/review/commit/diff, follow-ups)."""

    def run() -> dict:
        rd = _resolve_run_dir(run_dir)
        request = load_request(rd)
        manifest = workspace.load_manifest(rd)
        if not force and manifest.stage_status.get("collect") == StageStatus.COMPLETED:
            return {"action": "duplicate", "changed": [], "data": {"run_id": manifest.run_id, "run_dir": str(rd)}}
        _set_stage(rd, "collect", StageStatus.RUNNING)
        cfg = load_config(config_path)
        summary = asyncio.run(
            collection.collect_github(request, cfg, rd, entry_url=entry_url, no_cache=no_cache)
        )
        _set_stage(rd, "collect", StageStatus.COMPLETED if not summary["warnings"] else StageStatus.PARTIAL)
        manifest = workspace.load_manifest(rd)
        manifest.budgets_used["collect"] = summary["records"]
        if summary["observation_cutoff"] is not None:
            manifest.observation_cutoff = summary["observation_cutoff"]
        workspace.save_manifest(rd, manifest)
        _notice(f"repo-learning collect: {summary['records']} source record(s)")

        return {
            "action": "collected",
            "changed": [f"{summary['records']} source records appended"],
            "data": {
                "run_id": manifest.run_id,
                "run_dir": str(rd),
                "records": summary["records"],
                "by_kind": summary["by_kind"],
                "warnings": summary["warnings"],
                "next_stage": _next_stage(manifest),
            },
        }

    _finalize("repo-learning.collect", run)


# ── validate ──


@repo_learning.command("validate")
def validate_cmd(
    run_dir: str = typer.Option(..., "--run-dir", help="Run workspace directory"),
) -> None:
    """Validate analysis.json against the collected material."""

    def run() -> dict:
        rd = _resolve_run_dir(run_dir)
        request = load_request(rd)
        result = validation.validate(request, rd)
        manifest = workspace.load_manifest(rd)
        manifest.stage_status["validate"] = StageStatus.COMPLETED if result["valid"] else StageStatus.FAILED
        workspace.save_manifest(rd, manifest)

        return {
            "action": "validated",
            "changed": ["validate stage recorded"],
            "data": {
                "run_id": manifest.run_id,
                "run_dir": str(rd),
                "valid": result["valid"],
                "errors": result["errors"],
                "warnings": result["warnings"],
                "counts": result["counts"],
                "next_stage": _next_stage(manifest),
            },
        }

    _finalize("repo-learning.validate", run)


# ── render ──


@repo_learning.command("render")
def render_cmd(
    run_dir: str = typer.Option(..., "--run-dir", help="Run workspace directory"),
    template: str | None = typer.Option(None, "--template", help="Override the HTML template path"),
) -> None:
    """Render the interactive HTML report into the run workspace."""

    def run() -> dict:
        rd = _resolve_run_dir(run_dir)
        report_path = render_mod.render(rd, template_path=template)
        manifest = workspace.load_manifest(rd)
        manifest.stage_status["render"] = StageStatus.COMPLETED
        manifest.report_path = str(report_path)
        manifest.generated_at = datetime.now(timezone.utc)
        workspace.save_manifest(rd, manifest)
        _notice(f"repo-learning render: {report_path}")

        return {
            "action": "rendered",
            "changed": ["report.html written"],
            "data": {
                "run_id": manifest.run_id,
                "run_dir": str(rd),
                "report_path": str(report_path),
                "next_stage": _next_stage(manifest),
            },
        }

    _finalize("repo-learning.render", run)


# ── status ──


@repo_learning.command("status")
def status_cmd(
    run_dir: str = typer.Option(..., "--run-dir", help="Run workspace directory"),
) -> None:
    """Return the run's stage status, budgets, errors, and report path."""

    def run() -> dict:
        rd = _resolve_run_dir(run_dir)
        manifest = workspace.load_manifest(rd)
        return {
            "action": "status",
            "changed": [],
            "data": {
                "run_id": manifest.run_id,
                "run_dir": str(rd),
                "stage_status": {k: v.value for k, v in manifest.stage_status.items()},
                "budgets_used": manifest.budgets_used,
                "errors": manifest.errors,
                "report_path": manifest.report_path,
                "next_stage": _next_stage(manifest),
            },
        }

    _finalize("repo-learning.status", run)


# ── resume ──


@repo_learning.command("resume")
def resume_cmd(
    run_dir: str = typer.Option(..., "--run-dir", help="Run workspace directory"),
) -> None:
    """Re-check the request fingerprint and return the first incomplete stage."""

    def run() -> dict:
        rd = _resolve_run_dir(run_dir)
        request = load_request(rd)
        manifest = workspace.load_manifest(rd)
        current = request_hash(request)
        if current != manifest.request_hash:
            raise RepoLearningValidationError(
                "request.yaml changed since init; refusing to resume under different inputs "
                f"(stored {manifest.request_hash[:12]}..., current {current[:12]}...)"
            )
        return {
            "action": "resumed",
            "changed": [],
            "data": {
                "run_id": manifest.run_id,
                "run_dir": str(rd),
                "request_hash": current,
                "stage_status": {k: v.value for k, v in manifest.stage_status.items()},
                "next_stage": _next_stage(manifest),
            },
        }

    _finalize("repo-learning.resume", run)
