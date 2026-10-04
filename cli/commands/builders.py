"""builders — record and compare builder problems and practice trajectories.

JSON-first command group. Human-facing notices stay on stdout only when
``--format md`` is requested; otherwise stdout is one JSON object.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import typer

from intelligence.builder_problems.service import (
    BuilderProblemError,
    build_opportunity_cards,
    capture_problem,
    compare_problems,
    list_problems,
    record_event,
    show_problem,
)
from intelligence.builder_problems.store import BuilderProblemStore


SCHEMA_VERSION = "builderdna.builders.v1"

builders = typer.Typer(
    name="builders",
    help="Record builder problems/trajectories, compare scenarios, and produce verifiable opportunity cards.",
    no_args_is_help=True,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(command: str, result: dict) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "command": command,
        "ok": True,
        "action": result.get("action", ""),
        "changed": result.get("changed", []),
        "data": result.get("data", {}),
        "computed_at": _now_iso(),
    }


def _error(command: str, message: str) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "error": message,
        "data": {},
        "computed_at": _now_iso(),
    }


def _emit(payload: dict, output_format: str) -> None:
    if output_format == "md":
        print(_render_markdown(payload))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _finalize(command: str, output_format: str, func) -> None:
    if output_format not in ("json", "md"):
        _emit(_error(command, f"invalid --format {output_format!r}; expected 'json' or 'md'"), "json")
        raise typer.Exit(2)
    try:
        _emit(_envelope(command, func()), output_format)
    except BuilderProblemError as exc:
        _emit(_error(command, str(exc)), "json")
        raise typer.Exit(1)


def _render_markdown(payload: dict) -> str:
    if not payload.get("ok"):
        return f"# Error\n\n{payload.get('error', 'unknown error')}"
    data = payload.get("data", {})
    command = payload.get("command", "")
    lines = [f"# {command}", ""]

    if command == "builders.capture" or command == "builders.record":
        problem = data.get("problem") or {}
        lines.append(f"- ID: `{problem.get('problem_id', '')}`")
        lines.append(f"- Person: `{problem.get('person_ref', '')}`")
        lines.append(f"- Status: `{problem.get('status', '')}`")
        lines.append(f"- Statement: {problem.get('statement', '')}")
        if problem.get("current_workaround"):
            lines.append(f"- Workaround: {problem.get('current_workaround')}")
        lines.append(f"- Changed: {', '.join(payload.get('changed', [])) or 'none'}")
        return "\n".join(lines)

    if command == "builders.list":
        problems = data.get("problems", [])
        lines.append(f"Count: {data.get('count', len(problems))}")
        lines.append("")
        lines.append("| ID | Person | Status | Statement |")
        lines.append("| --- | --- | --- | --- |")
        for p in problems:
            statement = str(p.get("statement", "")).replace("|", "\\|")
            lines.append(
                f"| `{p.get('problem_id', '')}` | `{p.get('person_ref', '')}` "
                f"| `{p.get('status', '')}` | {statement} |"
            )
        return "\n".join(lines)

    if command == "builders.show":
        problem = data.get("problem") or {}
        lines.append(f"- ID: `{problem.get('problem_id', '')}`")
        lines.append(f"- Person: `{problem.get('person_ref', '')}`")
        lines.append(f"- Status: `{problem.get('status', '')}`")
        lines.append(f"- Statement: {problem.get('statement', '')}")
        lines.append("")
        lines.append("## Trajectory")
        for event in data.get("events", []):
            lines.append(
                f"- `{event.get('recorded_at', '')}` [{event.get('event_type', '')}] "
                f"{event.get('summary', '')}"
            )
        return "\n".join(lines)

    if command == "builders.compare":
        comparisons = data.get("comparisons", [])
        lines.append(f"Comparisons: {data.get('comparison_count', len(comparisons))}")
        lines.append("")
        for c in comparisons:
            lines.append(f"## {c.get('title', '')}")
            lines.append(f"- People: {', '.join(c.get('person_refs', []))}")
            lines.append(f"- Minimal deliverable: {c.get('minimal_deliverable', '')}")
            for question in c.get("open_questions", []):
                lines.append(f"- Unknown: {question}")
            lines.append("")
        return "\n".join(lines)

    if command == "builders.opportunity":
        cards = data.get("opportunities", [])
        lines.append(f"Opportunities: {data.get('count', len(cards))}")
        lines.append("")
        for card in cards:
            lines.append(f"## {card.get('title', '')}")
            lines.append(f"- Confidence: {card.get('confidence', 0):.2f}")
            lines.append(f"- Who: {', '.join(w.get('person_ref', '') for w in card.get('who', []))}")
            lines.append(f"- Minimal deliverable: {card.get('minimal_deliverable', '')}")
            for unknown in card.get("key_unknowns", []):
                lines.append(f"- Unknown: {unknown}")
            lines.append("")
        return "\n".join(lines)

    return json.dumps(payload, ensure_ascii=False, indent=2)


@builders.command("capture")
def capture_cmd(
    person_ref: str = typer.Argument(..., help="Stable builder/person reference"),
    statement: str = typer.Option(..., "--statement", "-s", help="Concrete problem statement"),
    problem_id: str | None = typer.Option(None, "--id", help="Stable problem ID (defaults to person + statement slug)"),
    project_ref: str = typer.Option("", "--project-ref", help="Stable project reference"),
    context: str = typer.Option("", "--context", help="When/where the problem appears"),
    workaround: str = typer.Option("", "--workaround", help="Current workaround"),
    user_segment: str = typer.Option("", "--user-segment", help="Who the person is"),
    trigger_context: str = typer.Option("", "--trigger-context", help="What action/change triggers the problem"),
    job_to_be_done: str = typer.Option("", "--job-to-be-done", help="Task the person is trying to complete"),
    primary_cost: str = typer.Option("", "--primary-cost", help="Main cost the problem imposes"),
    source_ref: list[str] | None = typer.Option(None, "--source-ref", help="Evidence reference (repeatable)"),
    status: str = typer.Option("observed", "--status", help="observed, confirmed, resolved"),
    state_dir: str = typer.Option("state", "--state-dir", help="Builder problem store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Create or update one problem record."""
    store = BuilderProblemStore(state_dir=state_dir)

    def run() -> dict:
        return capture_problem(
            store,
            person_ref=person_ref,
            statement=statement,
            project_ref=project_ref,
            context=context,
            current_workaround=workaround,
            user_segment=user_segment,
            trigger_context=trigger_context,
            job_to_be_done=job_to_be_done,
            primary_cost=primary_cost,
            source_refs=list(source_ref or []),
            problem_id=problem_id,
            status=status,
        )

    _finalize("builders.capture", output_format, run)


@builders.command("record")
def record_cmd(
    problem_id: str = typer.Argument(..., help="Problem ID"),
    event_type: str = typer.Option("note", "--event-type", "-t", help="problem_observed, attempt, tool_switch, status_change, note"),
    summary: str = typer.Option("", "--summary", "-s", help="Short event summary"),
    detail: str = typer.Option("", "--detail", help="Optional detail"),
    to_status: str | None = typer.Option(None, "--to-status", help="New status after this event"),
    from_status: str | None = typer.Option(None, "--from-status", help="Status before this event"),
    workaround: str | None = typer.Option(None, "--workaround", help="Current workaround captured by this event"),
    source_ref: list[str] | None = typer.Option(None, "--source-ref", help="Evidence reference (repeatable)"),
    state_dir: str = typer.Option("state", "--state-dir", help="Builder problem store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Append one trajectory event to an existing problem."""
    store = BuilderProblemStore(state_dir=state_dir)

    def run() -> dict:
        return record_event(
            store,
            problem_id=problem_id,
            event_type=event_type,
            summary=summary,
            detail=detail,
            source_refs=list(source_ref or []),
            to_status=to_status,
            from_status=from_status,
            current_workaround=workaround,
        )

    _finalize("builders.record", output_format, run)


@builders.command("list")
def list_cmd(
    person_ref: str | None = typer.Option(None, "--person-ref", help="Filter by person reference"),
    status: str | None = typer.Option(None, "--status", help="Filter by observed, confirmed, resolved"),
    state_dir: str = typer.Option("state", "--state-dir", help="Builder problem store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """List current problem snapshots."""
    store = BuilderProblemStore(state_dir=state_dir)

    def run() -> dict:
        return list_problems(store, person_ref=person_ref, status=status)

    _finalize("builders.list", output_format, run)


@builders.command("show")
def show_cmd(
    problem_id: str = typer.Argument(..., help="Problem ID"),
    state_dir: str = typer.Option("state", "--state-dir", help="Builder problem store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Show one problem and its full trajectory."""
    store = BuilderProblemStore(state_dir=state_dir)

    def run() -> dict:
        return show_problem(store, problem_id)

    _finalize("builders.show", output_format, run)


@builders.command("compare")
def compare_cmd(
    state_dir: str = typer.Option("state", "--state-dir", help="Builder problem store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Compare problems across people by task + obstacle."""
    store = BuilderProblemStore(state_dir=state_dir)

    def run() -> dict:
        return compare_problems(store)

    _finalize("builders.compare", output_format, run)


@builders.command("opportunity")
def opportunity_cmd(
    state_dir: str = typer.Option("state", "--state-dir", help="Builder problem store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Generate verifiable opportunity cards from cross-person comparisons."""
    store = BuilderProblemStore(state_dir=state_dir)

    def run() -> dict:
        return build_opportunity_cards(store)

    _finalize("builders.opportunity", output_format, run)


__all__ = ["builders"]
