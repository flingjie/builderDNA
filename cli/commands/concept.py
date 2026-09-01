"""concept — capture, move, merge, score, and record outcomes for concept cards.

Thin Typer layer over :mod:`concepts.service`. All business logic lives in the
service; this module only parses Typer options, delegates to the service, and
renders a JSON-first result (with optional Markdown).

Exit codes:

- ``0`` — success.
- ``1`` — unexpected failure (``ConceptServiceError`` base, a store error like
  ``CorruptionError``, or an unhandled ``ValueError``).
- ``2`` — validation error (``ConceptValidationError``): bad input, unknown
  concept, disallowed transition, ambiguous capture, invalid handoff.
- ``3`` — conflict (``ConceptConflictError`` or ``concepts.store.ConflictError``).
- ``4`` — blocked gate (``ConceptGateBlockedError``).

Design rules honoured here:

- **JSON first.** Every command prints one versioned JSON payload to stdout;
  ``--format md`` is the only escape hatch that renders Markdown instead.
- **Never silently advance a stage.** A failed gate aborts with exit 4 and a
  message listing every missing requirement.
- **Never silently mutate state.** Every payload carries a ``changed`` list.
- **Capture is idempotent** by normalized URL/content fingerprint, and matches
  via ``classify_match`` (``suggested`` never auto-merges).
- **Build predictions cannot be rewritten.** ``move ... build`` records the
  prediction; ``outcome`` records the result and lesson without touching it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer

from concepts.service import (
    ConceptConflictError,
    ConceptGateBlockedError,
    ConceptServiceError,
    ConceptValidationError,
    capture,
    capture_handoff,
    derive_title,
    list_cards,
    merge,
    move,
    parse_experiment,
    parse_review_date,
    record_outcome,
    score,
    show,
    slugify,
)
from concepts.store import ConceptStore, ConceptStoreError
from concepts.store import ConflictError as StoreConflictError
from observability import RunTelemetry

SCHEMA_VERSION = "builderdna.concept.v1"

concept = typer.Typer(
    name="concept",
    help="Capture, move, merge, score, and record outcomes for concept cards (Inbox -> Watch -> Verify -> Build/Drop).",
    no_args_is_help=True,
)

# Backward-compatible alias: the old generic command error now maps to validation (exit 2).
ConceptCommandError = ConceptValidationError

__all__ = [
    "concept",
    "ConceptCommandError",
    "capture",
    "record_outcome",
    "derive_title",
    "slugify",
]


# ── Small utilities ──


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _emit_payload(payload: dict, output_format: str) -> None:
    if output_format == "md":
        print(_render_markdown(payload))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


def _emit_error(
    command: str, message: str, details: dict | None = None, exit_code: int = 1
) -> None:
    print(
        json.dumps(
            _error(command, message, details, exit_code),
            indent=2,
            ensure_ascii=False,
        )
    )


def _finalize(command: str, output_format: str, func) -> None:
    """Run ``func`` and emit its JSON/Markdown result; translate known errors."""
    if output_format not in ("json", "md"):
        _emit_error(
            command,
            f"invalid --format {output_format!r}; expected 'json' or 'md'",
            exit_code=2,
        )
        raise typer.Exit(2)
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
        _emit_payload(payload, output_format)
    except ConceptGateBlockedError as exc:
        _emit_error(command, exc.message, exc.details, exit_code=exc.exit_code)
        raise typer.Exit(exc.exit_code)
    except ConceptConflictError as exc:
        _emit_error(command, exc.message, exc.details, exit_code=exc.exit_code)
        raise typer.Exit(exc.exit_code)
    except ConceptValidationError as exc:
        _emit_error(command, exc.message, exc.details, exit_code=exc.exit_code)
        raise typer.Exit(exc.exit_code)
    except StoreConflictError as exc:
        _emit_error(command, str(exc), exit_code=3)
        raise typer.Exit(3)
    except ConceptServiceError as exc:
        _emit_error(command, exc.message, exc.details, exit_code=exc.exit_code)
        raise typer.Exit(exc.exit_code)
    except ConceptStoreError as exc:
        _emit_error(command, str(exc), exit_code=1)
        raise typer.Exit(1)
    except ValueError as exc:
        _emit_error(command, str(exc), exit_code=1)
        raise typer.Exit(1)


def _read_handoff_raw(handoff: str, stdin: bool) -> dict:
    """Read a handoff JSON object from ``--stdin`` or a ``--handoff`` file."""
    if stdin:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ConceptValidationError("--stdin provided but stdin is empty")
    else:
        path = Path(handoff)
        if not path.exists():
            raise ConceptValidationError(f"handoff file not found: {handoff}")
        raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConceptValidationError(f"invalid handoff JSON: {exc}")
    if not isinstance(data, dict):
        raise ConceptValidationError("handoff must be a JSON object")
    return data


# ── CLI subcommands ──


@concept.command("capture")
def capture_cmd(
    source: str = typer.Option("x", "--source", help="Source type: x, reddit, github, paper, official_doc, manual"),
    url: str = typer.Option("", "--url", help="Source URL"),
    note: str = typer.Option("", "--note", help="Human-curated note or quoted excerpt"),
    title: str | None = typer.Option(None, "--title", help="Display title (defaults to first line of note)"),
    problem: str | None = typer.Option(None, "--problem", help="Problem/job this concept addresses (defaults to note)"),
    concept_id: str | None = typer.Option(None, "--id", help="Stable concept ID slug (defaults to a slug of the title)"),
    aliases: list[str] | None = typer.Option(None, "--alias", help="Alternative name (repeatable)"),
    author: str = typer.Option("", "--author", help="Author / curator login"),
    quoted_source_url: str | None = typer.Option(None, "--quoted-source-url", help="Primary source URL this note quotes"),
    upstream_origin: str | None = typer.Option(None, "--upstream-origin", help="Upstream origin for repost chains"),
    role: str | None = typer.Option(None, "--role", help="Evidence role: problem, implementation, adoption, counterevidence"),
    directness: str | None = typer.Option(None, "--directness", help="Directness: direct, indirect, inferred"),
    strength: str | None = typer.Option(None, "--strength", help="Strength: weak, moderate, strong"),
    merge_into: str | None = typer.Option(None, "--into", help="Explicit concept ID to merge into (disambiguates)"),
    handoff: str | None = typer.Option(None, "--handoff", help="Path to a source handoff JSON file (combine with --stdin to read it from stdin)"),
    stdin: bool = typer.Option(False, "--stdin", help="Read a JSON capture object (or, with --handoff, a handoff envelope) from stdin"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Capture a weak signal or a source handoff, creating/merging concept cards."""
    store = ConceptStore(state_dir=state_dir)

    def run() -> dict:
        if handoff is not None:
            raw = _read_handoff_raw(handoff, stdin)
            return capture_handoff(store, raw, merge_into=merge_into)

        kwargs: dict[str, Any] = {
            "source": source,
            "url": url,
            "note": note,
            "title": title,
            "problem": problem,
            "concept_id": concept_id,
            "aliases": list(aliases or []),
            "author": author,
            "quoted_source_url": quoted_source_url,
            "upstream_origin": upstream_origin,
            "role": role,
            "directness": directness,
            "strength": strength,
            "merge_into": merge_into,
        }
        if stdin:
            raw = sys.stdin.read()
            if not raw.strip():
                raise ConceptValidationError("--stdin provided but stdin is empty")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ConceptValidationError(f"invalid stdin JSON: {exc}")
            if not isinstance(data, dict):
                raise ConceptValidationError("stdin JSON must be an object")
            for key in (
                "source", "url", "note", "title", "problem", "author",
                "quoted_source_url", "upstream_origin", "role", "directness",
                "strength", "into",
            ):
                if key in data and data[key] is not None:
                    kwargs["merge_into" if key == "into" else key] = data[key]
            if "id" in data and data["id"] is not None:
                kwargs["concept_id"] = data["id"]
            if "aliases" in data and data["aliases"] is not None:
                kwargs["aliases"] = list(data["aliases"])
        return capture(store, **kwargs)

    _finalize("concept.capture", output_format, run)


@concept.command("list")
def list_cmd(
    stage: str | None = typer.Option(None, "--stage", help="Filter by portfolio stage"),
    radar: str | None = typer.Option(None, "--radar", help="Filter by radar name (no-op until cards carry a radar field)"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """List concept cards, optionally filtered by stage and/or radar name."""
    store = ConceptStore(state_dir=state_dir)

    def run() -> dict:
        return list_cards(store, stage=stage, radar=radar)

    _finalize("concept.list", output_format, run)


@concept.command("show")
def show_cmd(
    concept_id: str = typer.Argument(..., help="Concept ID"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Show one card with its evidence and review history."""
    store = ConceptStore(state_dir=state_dir)

    def run() -> dict:
        return show(store, concept_id)

    _finalize("concept.show", output_format, run)


@concept.command("move")
def move_cmd(
    concept_id: str = typer.Argument(..., help="Concept ID"),
    stage: str = typer.Argument(..., help="Target stage: inbox, watch, verify, build, drop"),
    reason: str = typer.Option(..., "--reason", "-r", help="Why the card is moving"),
    prediction: str = typer.Option("", "--prediction", help="Prediction recorded on entry to Build (required for build)"),
    expected_evidence: str = typer.Option("", "--expected-evidence", help="Evidence expected next (required for build)"),
    review_date: str | None = typer.Option(None, "--review-date", help="ISO 8601 UTC review date (required for build)"),
    experiment: str | None = typer.Option(None, "--experiment", help="Inline JSON smallest experiment"),
    experiment_file: str | None = typer.Option(None, "--experiment-file", help="Path to a JSON smallest experiment"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Move a card to another stage, enforcing the hard build gate."""
    store = ConceptStore(state_dir=state_dir)

    def run() -> dict:
        review_dt = parse_review_date(review_date) if review_date else None
        smallest = parse_experiment(experiment, experiment_file)
        return move(
            store,
            concept_id,
            stage,
            reason=reason,
            prediction=prediction,
            expected_evidence=expected_evidence,
            review_date=review_dt,
            experiment=smallest,
        )

    _finalize("concept.move", output_format, run)


@concept.command("merge")
def merge_cmd(
    survivor_id: str = typer.Argument(..., help="Surviving concept ID"),
    merged_id: str = typer.Argument(..., help="Concept ID to merge into the survivor"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Merge one card into another, preserving aliases and evidence lineage."""
    store = ConceptStore(state_dir=state_dir)

    def run() -> dict:
        return merge(store, survivor_id, merged_id)

    _finalize("concept.merge", output_format, run)


@concept.command("score")
def score_cmd(
    concept_id: str = typer.Argument(..., help="Concept ID"),
    user_alignment: int = typer.Option(0, "--user-alignment", "-a", help="Caller-supplied alignment 0-3"),
    hype: int | None = typer.Option(None, "--hype", help="Caller-supplied hype penalty 0-3"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Compute component scores, per-component reasons, and the build gate."""
    store = ConceptStore(state_dir=state_dir)

    def run() -> dict:
        return score(store, concept_id, user_alignment=user_alignment, hype=hype)

    _finalize("concept.score", output_format, run)


def _outcome_run(store, concept_id, outcome, lesson) -> dict:
    return record_outcome(store, concept_id, outcome, lesson)


def outcome_cmd(
    concept_id: str = typer.Argument(..., help="Concept ID"),
    outcome: str = typer.Option(..., "--outcome", "-o", help="Outcome: confirmed, partially_confirmed, rejected, inconclusive"),
    lesson: str = typer.Option(..., "--lesson", "-l", help="Lesson learned from the outcome"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Record a Build outcome + lesson without rewriting the original prediction."""
    store = ConceptStore(state_dir=state_dir)
    _finalize(
        "concept.outcome", output_format,
        lambda: _outcome_run(store, concept_id, outcome, lesson),
    )


def review_cmd(
    concept_id: str = typer.Argument(..., help="Concept ID"),
    outcome: str = typer.Option(..., "--outcome", "-o", help="Outcome: confirmed, partially_confirmed, rejected, inconclusive"),
    lesson: str = typer.Option(..., "--lesson", "-l", help="Lesson learned from the outcome"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Deprecated alias for ``outcome``; reports the ``concept.review`` command name."""
    store = ConceptStore(state_dir=state_dir)
    _finalize(
        "concept.review", output_format,
        lambda: _outcome_run(store, concept_id, outcome, lesson),
    )


concept.command("outcome")(outcome_cmd)
concept.command("review", deprecated=True)(review_cmd)


# ── Markdown rendering ──


def _render_markdown(payload: dict) -> str:
    command = payload["command"]
    lines = [f"## {command}", ""]

    if not payload["ok"]:
        lines.append(f"**Error:** {payload.get('error', '')}")
        details = payload.get("details") or {}
        if details.get("candidates"):
            lines.append("")
            lines.append("### Candidate matches (disambiguate with --into)")
            for c in details["candidates"]:
                lines.append(
                    f"- `{c['concept_id']}` — {c['title']} (score={c['score']:.2f})"
                )
        if details.get("missing"):
            lines.append("")
            lines.append("**Missing requirements:**")
            for m in details["missing"]:
                lines.append(f"- {m}")
        if details.get("conflicts"):
            lines.append("")
            lines.append("**Conflicts:**")
            for c in details["conflicts"]:
                lines.append(f"- {c}")
        return "\n".join(lines)

    lines.append(f"**Action:** `{payload.get('action', '')}`")
    if payload.get("changed"):
        lines.append("")
        lines.append("**Changed:**")
        for change in payload["changed"]:
            lines.append(f"- {change}")

    data = payload.get("data", {})
    lines.append("")

    if command == "concept.capture":
        if payload.get("action") == "handoff_captured":
            imp = data.get("import") or {}
            lines.append(f"- imported: {imp.get('imported', 0)} evidence record(s)")
            lines.append(f"- skipped (idempotent): {imp.get('skipped_idempotent', 0)}")
            lines.append(
                f"- created: {', '.join(data.get('created_ids') or []) or '(none)'}"
            )
            lines.append(
                f"- merged: {', '.join(data.get('merged_ids') or []) or '(none)'}"
            )
            for c in data.get("created") or []:
                lines.append(f"  - created `{c.get('id')}` — {c.get('title')}")
            for c in data.get("merged") or []:
                lines.append(f"  - merged `{c.get('id')}` — {c.get('title')}")
        else:
            card = data.get("concept") or {}
            lines.append(f"- concept: `{card.get('id', '?')}` ({card.get('title', '?')})")
            lines.append(
                f"- stage: {card.get('stage', '?')} / maturity: {card.get('maturity', '?')}"
            )
            if data.get("merged_into"):
                lines.append(f"- merged into: `{data['merged_into']}`")
            evidence = data.get("evidence") or {}
            lines.append(
                f"- evidence: `{evidence.get('id', '?')}` [{evidence.get('source_type', '?')}]"
            )
            for c in data.get("candidates") or []:
                lines.append(
                    f"  - candidate `{c['concept_id']}` — {c['title']} (score={c['score']:.2f})"
                )
    elif command == "concept.list":
        for c in data.get("cards") or []:
            lines.append(f"- `{c.get('id')}` [{c.get('stage')}] {c.get('title')}")
    elif command == "concept.show":
        card = data.get("concept") or {}
        lines.append(f"- concept: `{card.get('id')}` ({card.get('title')})")
        lines.append(f"- stage: {card.get('stage')} / maturity: {card.get('maturity')}")
        lines.append(f"- prediction: {card.get('prediction') or '(none)'}")
        lines.append(f"- outcome: {card.get('outcome') or '(none)'}")
        lines.append(f"- evidence records: {len(data.get('evidence') or [])}")
        lines.append(f"- reviews: {len(data.get('reviews') or [])}")
    elif command == "concept.move":
        card = data.get("concept") or {}
        lines.append(f"- concept: `{card.get('id')}` now `{card.get('stage')}`")
        review = data.get("review") or {}
        lines.append(f"- reason: {review.get('reason', '')}")
    elif command == "concept.merge":
        survivor = data.get("survivor") or {}
        lines.append(f"- survivor: `{survivor.get('id')}` ({survivor.get('title')})")
        lines.append(f"- aliases: {survivor.get('aliases')}")
        lines.append(
            f"- evidence re-pointed: {len(data.get('repointed_evidence_ids') or [])}"
        )
    elif command == "concept.score":
        scores = data.get("scores") or {}
        reasons = data.get("reasons") or {}
        lines.append(f"- total (2P+2E+R+A-2H-C): {scores.get('total')}")
        for comp in ("problem", "evidence", "reach", "user_alignment", "hype", "competition"):
            lines.append(f"- {comp}: {scores.get(comp)} — {reasons.get(comp, '')}")
        gate = data.get("gate") or {}
        if gate.get("passed"):
            lines.append("- build gate: passed")
        else:
            lines.append(
                "- build gate: missing " + ", ".join(gate.get("missing", []))
            )
    elif command in ("concept.review", "concept.outcome"):
        card = data.get("concept") or {}
        lines.append(f"- outcome: {card.get('outcome')}")
        lines.append(f"- lesson: {card.get('lesson')}")
        lines.append(f"- prediction preserved: {data.get('prediction_preserved')}")

    return "\n".join(lines)
