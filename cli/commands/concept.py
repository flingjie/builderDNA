"""concept — capture, move, merge, score, and review concept cards.

Thin orchestrator over the deterministic concept layer (``concepts/``): the
store persists state, ``matching`` decides created-vs-merged, and ``scoring``
enforces the hard build gates. This module only wires those together and
renders a JSON-first result (with optional Markdown).

Design rules honoured here:

- **JSON first.** Every command prints one versioned JSON payload to stdout;
  ``--format md`` is the only escape hatch that renders Markdown instead.
  Human notices go to stderr so stdout stays machine-readable.
- **Never silently advance a stage.** A failed gate aborts with a non-zero
  exit and a message listing every missing requirement.
- **Never silently mutate state.** Every payload carries a ``changed`` list
  describing exactly what was written.
- **Capture is idempotent** by normalized URL/content fingerprint (the same
  fingerprint the manual-X adapter derives for evidence IDs).
- **Build predictions cannot be rewritten.** ``move ... build`` records the
  prediction; ``review`` records the outcome and lesson without touching it.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import typer

from concepts.adapters.manual_x import to_evidence
from concepts.matching import find_candidates, is_ambiguous, normalize_name
from concepts.scoring import evaluate_build_gate, score_components
from concepts.store import ConceptStore, ConceptStoreError
from models.concept import (
    ConceptCard,
    ConceptEvidence,
    OutcomeState,
    PortfolioStage,
    RadarReview,
    SmallestExperiment,
    SourceType,
)
from observability import RunTelemetry

SCHEMA_VERSION = "builderdna.concept.v1"

concept = typer.Typer(
    name="concept",
    help="Capture, move, merge, score, and review concept cards (Inbox -> Watch -> Verify -> Build/Drop).",
    no_args_is_help=True,
)

# ── Errors ──


class ConceptCommandError(Exception):
    """A domain error surfaced as a clean JSON failure (exit code 1)."""

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ── Small utilities ──


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _notice(message: str) -> None:
    """Human-facing notice on stderr, keeping stdout a pure JSON stream."""
    print(message, file=sys.stderr)


def slugify(title: str) -> str:
    """Derive a stable concept-ID slug from a display title."""
    norm = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return norm or "concept"


def derive_title(note: str) -> str:
    """Derive a display title from the first line of a note (or "")."""
    text = (note or "").strip()
    if not text:
        return ""
    return text.splitlines()[0].strip()[:80]


def _parse_source(value: str) -> SourceType:
    try:
        return SourceType(value.strip().lower())
    except ValueError:
        raise ConceptCommandError(
            f"invalid source {value!r}; expected one of {[s.value for s in SourceType]}"
        )


def _parse_review_date(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConceptCommandError(f"invalid --review-date {value!r}: {exc}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.utcoffset() != timedelta(0):
        raise ConceptCommandError(
            "--review-date must be UTC (e.g. 2026-09-08T00:00:00Z)"
        )
    return dt


def _load_experiment(
    experiment_json: str | None, experiment_file: str | None
) -> SmallestExperiment | None:
    if experiment_json and experiment_file:
        raise ConceptCommandError(
            "provide only one of --experiment or --experiment-file"
        )
    raw: str | None = None
    if experiment_file:
        path = Path(experiment_file)
        if not path.exists():
            raise ConceptCommandError(f"experiment file not found: {experiment_file}")
        raw = path.read_text(encoding="utf-8")
    elif experiment_json:
        raw = experiment_json
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConceptCommandError(f"invalid experiment JSON: {exc}")
    if not isinstance(data, dict):
        raise ConceptCommandError("experiment must be a JSON object")
    try:
        return SmallestExperiment(**data)
    except Exception as exc:  # pydantic validation -> clean CLI error
        raise ConceptCommandError(f"invalid smallest experiment: {exc}")


def _review_id(concept_id: str) -> str:
    """A unique, append-only review record ID."""
    return f"rev-{concept_id}-{int(_now_utc().timestamp() * 1000)}-{uuid4().hex[:8]}"


def _unique_id(store: ConceptStore, base: str) -> str:
    """Return ``base`` unless it collides with an existing concept ID."""
    existing = {c.id for c in store.list_concepts()}
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


def _existing_urls(store: ConceptStore) -> dict[str, list[str]]:
    """Map concept_id -> source URLs, for deterministic URL matching."""
    out: dict[str, list[str]] = {}
    for evidence in store.list_evidence():
        if evidence.source_url:
            out.setdefault(evidence.concept_id, []).append(evidence.source_url)
    return out


def _candidates_payload(matches: list) -> list[dict]:
    return [
        {
            "concept_id": m.concept_id,
            "title": m.title,
            "score": m.score,
            "name_score": m.name_score,
            "url_score": m.url_score,
            "problem_score": m.problem_score,
            "reasons": [
                {"signal": r.signal, "detail": r.detail, "score": r.score}
                for r in m.reasons
            ],
        }
        for m in matches
    ]


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


def _error(command: str, message: str, details: dict | None = None) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "error": message,
        "details": details or {},
        "computed_at": _now_iso(),
    }


def _emit_payload(payload: dict, output_format: str) -> None:
    if output_format == "md":
        print(_render_markdown(payload))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


def _emit_error(command: str, message: str, details: dict | None = None) -> None:
    print(json.dumps(_error(command, message, details), indent=2, ensure_ascii=False))


def _finalize(command: str, output_format: str, func) -> None:
    """Run ``func`` and emit its JSON/Markdown result; translate known errors."""
    if output_format not in ("json", "md"):
        _emit_error(command, f"invalid --format {output_format!r}; expected 'json' or 'md'")
        raise typer.Exit(1)
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
    except ConceptCommandError as exc:
        _emit_error(command, exc.message, exc.details)
        raise typer.Exit(1)
    except ConceptStoreError as exc:
        _emit_error(command, str(exc))
        raise typer.Exit(1)
    except ValueError as exc:
        _emit_error(command, str(exc))
        raise typer.Exit(1)


# ── Core helpers (unit-testable, no stdout side effects) ──


def capture(
    store: ConceptStore,
    *,
    source: str = "x",
    url: str = "",
    note: str = "",
    title: str | None = None,
    problem: str | None = None,
    concept_id: str | None = None,
    aliases: list[str] | None = None,
    author: str = "",
    quoted_source_url: str | None = None,
    upstream_origin: str | None = None,
    role: str | None = None,
    directness: str | None = None,
    strength: str | None = None,
    merge_into: str | None = None,
) -> dict:
    """Capture one weak signal, creating or merging a concept card.

    Returns ``action`` in {"created", "merged", "already_captured"}. Raises
    ``ConceptCommandError`` on ambiguity (never auto-merges an ambiguous match).
    """
    aliases = list(aliases or [])
    source_type = _parse_source(source)

    if not title:
        title = derive_title(note)
    if not title or not title.strip():
        raise ConceptCommandError(
            "capture requires a --title or a non-empty --note to derive one"
        )
    title = title.strip()
    if problem is None:
        problem = (note or "").strip()
    problem = problem or ""

    # A provisional card drives matching; its ID is not used by the matcher.
    provisional_id = concept_id or slugify(title)
    candidate = ConceptCard(
        id=provisional_id, title=title, aliases=aliases, problem=problem
    )

    # Idempotency fingerprint: the adapter derives a deterministic evidence ID
    # from the normalized URL (or an author|note content hash when URL-less).
    probe = to_evidence(
        concept_id="__probe__",
        url=url,
        author=author,
        note=note,
        quoted_source_url=quoted_source_url,
        upstream_origin=upstream_origin,
        role=role,
        strength=strength,
        directness=directness,
        source_type=source_type,
    )
    existing_evidence = store.get_evidence(probe.id)
    if existing_evidence is not None:
        card = store.get_concept(existing_evidence.concept_id)
        return {
            "action": "already_captured",
            "changed": [],
            "data": {
                "concept": card.model_dump(mode="json") if card else None,
                "evidence": existing_evidence.model_dump(mode="json"),
                "candidates": [],
            },
        }

    matches = find_candidates(
        candidate,
        store.list_concepts(),
        candidate_urls=[url],
        existing_urls=_existing_urls(store),
    )
    candidates_payload = _candidates_payload(matches)

    target_id: str | None = None
    action = "created"
    if matches:
        if merge_into:
            if store.get_concept(merge_into) is None:
                raise ConceptCommandError(f"merge target {merge_into!r} not found")
            target_id = merge_into
            action = "merged"
        elif is_ambiguous(matches):
            raise ConceptCommandError(
                "capture is ambiguous — multiple or conflicting matches; "
                "re-run with --into <ID> to disambiguate (never auto-merged)",
                details={
                    "candidates": candidates_payload,
                    "hint": "pass --into with one of the candidate concept IDs",
                },
            )
        else:
            target_id = matches[0].concept_id
            action = "merged"

    if target_id is None:
        final_id = _unique_id(store, provisional_id)
        card = ConceptCard(
            id=final_id,
            title=title,
            aliases=aliases,
            problem=problem,
            stage=PortfolioStage.INBOX,
        )
        evidence = to_evidence(
            concept_id=final_id,
            url=url,
            author=author,
            note=note,
            quoted_source_url=quoted_source_url,
            upstream_origin=upstream_origin,
            role=role,
            strength=strength,
            directness=directness,
            source_type=source_type,
        )
        card = card.model_copy(update={"evidence_ids": [evidence.id]})
        store.add_evidence(evidence)
        store.upsert_concept(card)
        changed = ["concept created", "evidence appended"]
    else:
        surviving = store.get_concept(target_id)
        evidence = to_evidence(
            concept_id=target_id,
            url=url,
            author=author,
            note=note,
            quoted_source_url=quoted_source_url,
            upstream_origin=upstream_origin,
            role=role,
            strength=strength,
            directness=directness,
            source_type=source_type,
        )
        new_aliases = list(surviving.aliases)
        existing_norms = {normalize_name(a) for a in surviving.aliases}
        if normalize_name(title) != normalize_name(surviving.title) and normalize_name(
            title
        ) not in existing_norms:
            new_aliases.append(title)
        evidence_ids = list(surviving.evidence_ids)
        if evidence.id not in evidence_ids:
            evidence_ids.append(evidence.id)
        card = surviving.model_copy(
            update={"aliases": new_aliases, "evidence_ids": evidence_ids}
        )
        store.add_evidence(evidence)
        store.upsert_concept(card)
        changed = ["evidence appended", "concept merged (alias/evidence updated)"]

    return {
        "action": action,
        "changed": changed,
        "data": {
            "concept": card.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
            "candidates": candidates_payload,
            "merged_into": target_id,
        },
    }


def apply_move(
    store: ConceptStore,
    concept_id: str,
    target_stage: str,
    *,
    reason: str,
    prediction: str = "",
    expected_evidence: str = "",
    review_date: datetime | None = None,
    experiment: SmallestExperiment | None = None,
) -> dict:
    """Move a card to ``target_stage``, enforcing the hard build gate.

    Moving to ``build`` requires ``prediction``, ``expected_evidence``, a
    ``review_date`` (Task 6.1), and a passing ``evaluate_build_gate``. Every
    successful move appends a ``RadarReview``.
    """
    card = store.get_concept(concept_id)
    if card is None:
        raise ConceptCommandError(f"concept {concept_id!r} not found")
    try:
        target = PortfolioStage(target_stage)
    except ValueError:
        raise ConceptCommandError(
            f"invalid stage {target_stage!r}; expected one of {[s.value for s in PortfolioStage]}"
        )
    if card.stage == target:
        raise ConceptCommandError(
            f"concept {concept_id!r} is already in stage '{target.value}'"
        )
    if not reason or not reason.strip():
        raise ConceptCommandError("move requires --reason")

    evidence = store.list_evidence(concept_id)
    review_dt = review_date if review_date is not None else _now_utc()
    from_stage = card.stage

    if target == PortfolioStage.BUILD:
        missing = []
        if not prediction.strip():
            missing.append("--prediction")
        if not expected_evidence.strip():
            missing.append("--expected-evidence")
        if review_date is None:
            missing.append("--review-date")
        if missing:
            raise ConceptCommandError(
                "move to 'build' requires " + ", ".join(missing)
            )
        if experiment is not None:
            card = card.model_copy(update={"smallest_experiment": experiment})
        gate = evaluate_build_gate(card, evidence)
        if not gate.passed:
            raise ConceptCommandError(
                "build gate failed — missing: " + "; ".join(gate.missing),
                details={"missing": list(gate.missing)},
            )
        # A prediction recorded on an earlier Build entry is never rewritten.
        final_prediction = card.prediction.strip() or prediction.strip()
        card = card.model_copy(
            update={"stage": target, "prediction": final_prediction}
        )
    else:
        card = card.model_copy(update={"stage": target})

    card = store.upsert_concept(card)
    review = RadarReview(
        id=_review_id(concept_id),
        concept_id=concept_id,
        from_stage=from_stage,
        to_stage=target,
        reason=reason.strip(),
        expected_evidence=expected_evidence.strip(),
        review_date=review_dt,
    )
    store.add_review(review)

    return {
        "action": "moved",
        "changed": [
            f"stage {from_stage.value} -> {target.value}",
            "review recorded",
        ],
        "data": {
            "concept": card.model_dump(mode="json"),
            "review": review.model_dump(mode="json"),
            "gate": {"passed": True, "missing": []},
        },
    }


def apply_merge(store: ConceptStore, survivor_id: str, merged_id: str) -> dict:
    """Merge ``merged_id`` into ``survivor_id``.

    Unions aliases, re-points the merged-away card's evidence to the survivor
    via append-only superseding records, and marks the merged-away card dropped.
    """
    if survivor_id == merged_id:
        raise ConceptCommandError("cannot merge a concept into itself")
    survivor = store.get_concept(survivor_id)
    merged = store.get_concept(merged_id)
    if survivor is None:
        raise ConceptCommandError(f"concept {survivor_id!r} not found")
    if merged is None:
        raise ConceptCommandError(f"concept {merged_id!r} not found")

    survivor_norm = normalize_name(survivor.title)
    alias_set = set(survivor.aliases) | set(merged.aliases) | {merged.title}
    new_aliases = sorted(a for a in alias_set if normalize_name(a) != survivor_norm)

    repointed: list[str] = []
    for evidence in store.list_evidence(merged_id):
        new_id = f"{evidence.id}->{survivor_id}"
        if store.get_evidence(new_id) is None:
            store.add_evidence(
                ConceptEvidence(
                    id=new_id,
                    concept_id=survivor_id,
                    source_type=evidence.source_type,
                    source_url=evidence.source_url,
                    role=evidence.role,
                    directness=evidence.directness,
                    strength=evidence.strength,
                    independence_key=evidence.independence_key,
                    note=evidence.note,
                    supersedes=evidence.id,
                )
            )
        repointed.append(new_id)

    evidence_ids = sorted(set(survivor.evidence_ids) | set(repointed))
    survivor = survivor.model_copy(
        update={"aliases": new_aliases, "evidence_ids": evidence_ids}
    )
    survivor = store.upsert_concept(survivor)

    from_stage = merged.stage
    merged = merged.model_copy(update={"stage": PortfolioStage.DROP})
    merged = store.upsert_concept(merged)
    review = RadarReview(
        id=_review_id(merged_id),
        concept_id=merged_id,
        from_stage=from_stage,
        to_stage=PortfolioStage.DROP,
        reason=f"merged into {survivor_id}",
        expected_evidence="",
        review_date=_now_utc(),
    )
    store.add_review(review)

    return {
        "action": "merged",
        "changed": [
            f"evidence re-pointed {merged_id} -> {survivor_id}",
            f"{merged_id} marked dropped",
            "review recorded",
        ],
        "data": {
            "survivor": survivor.model_dump(mode="json"),
            "merged_away": merged.model_dump(mode="json"),
            "repointed_evidence_ids": repointed,
            "review": review.model_dump(mode="json"),
        },
    }


def score_card(
    store: ConceptStore,
    concept_id: str,
    *,
    user_alignment: int = 0,
    hype: int | None = None,
) -> dict:
    """Return derived component scores, per-component reasons, and the gate."""
    card = store.get_concept(concept_id)
    if card is None:
        raise ConceptCommandError(f"concept {concept_id!r} not found")
    evidence = store.list_evidence(concept_id)
    scored = score_components(card, evidence, user_alignment=user_alignment, hype=hype)
    gate = evaluate_build_gate(card, evidence)
    return {
        "action": "scored",
        "changed": [],
        "data": {
            "concept_id": concept_id,
            "scores": scored.scores.model_dump(mode="json"),
            "reasons": scored.reasons,
            "gate": {"passed": gate.passed, "missing": list(gate.missing)},
        },
    }


def record_outcome(
    store: ConceptStore, concept_id: str, outcome: str, lesson: str
) -> dict:
    """Record a Build outcome + lesson without rewriting the prediction (Task 6.1).

    Requires a prior prediction (proof the card entered Build). The original
    prediction is left untouched, and every review appends an immutable
    ``RadarReview`` so the outcome history stays traceable.
    """
    card = store.get_concept(concept_id)
    if card is None:
        raise ConceptCommandError(f"concept {concept_id!r} not found")
    if not card.prediction.strip():
        raise ConceptCommandError(
            f"concept {concept_id!r} has no recorded prediction — enter Build first "
            "('concept move <id> build --prediction ...') before recording an outcome"
        )
    try:
        outcome_state = OutcomeState(outcome)
    except ValueError:
        raise ConceptCommandError(
            f"invalid outcome {outcome!r}; expected one of {[o.value for o in OutcomeState]}"
        )
    if not lesson or not lesson.strip():
        raise ConceptCommandError("review requires --lesson")

    original_prediction = card.prediction
    card = card.model_copy(
        update={"outcome": outcome_state, "lesson": lesson.strip()}
    )
    card = store.upsert_concept(card)
    review = RadarReview(
        id=_review_id(concept_id),
        concept_id=concept_id,
        from_stage=card.stage,
        to_stage=card.stage,
        reason=f"Build outcome recorded: {outcome_state.value}. Lesson: {lesson.strip()}",
        expected_evidence="",
        review_date=_now_utc(),
    )
    store.add_review(review)

    return {
        "action": "reviewed",
        "changed": ["outcome recorded", "review appended for traceability"],
        "data": {
            "concept": card.model_dump(mode="json"),
            "review": review.model_dump(mode="json"),
            "prediction_preserved": True,
            "original_prediction": original_prediction,
        },
    }


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
    stdin: bool = typer.Option(False, "--stdin", help="Read a JSON capture object from stdin"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Capture a weak signal, creating a new card or merging into an existing one."""
    store = ConceptStore(state_dir=state_dir)

    def run() -> dict:
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
                raise ConceptCommandError("--stdin provided but stdin is empty")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ConceptCommandError(f"invalid stdin JSON: {exc}")
            if not isinstance(data, dict):
                raise ConceptCommandError("stdin JSON must be an object")
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
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """List concept cards, optionally filtered by stage."""
    store = ConceptStore(state_dir=state_dir)

    def run() -> dict:
        cards = store.list_concepts()
        if stage:
            try:
                st = PortfolioStage(stage)
            except ValueError:
                raise ConceptCommandError(
                    f"invalid stage {stage!r}; expected one of {[s.value for s in PortfolioStage]}"
                )
            cards = [c for c in cards if c.stage == st]
        return {
            "action": "listed",
            "changed": [],
            "data": {
                "cards": [c.model_dump(mode="json") for c in cards],
                "count": len(cards),
            },
        }

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
        card = store.get_concept(concept_id)
        if card is None:
            raise ConceptCommandError(f"concept {concept_id!r} not found")
        return {
            "action": "shown",
            "changed": [],
            "data": {
                "concept": card.model_dump(mode="json"),
                "evidence": [
                    e.model_dump(mode="json") for e in store.list_evidence(concept_id)
                ],
                "reviews": [
                    r.model_dump(mode="json") for r in store.list_reviews(concept_id)
                ],
            },
        }

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
        review_dt = _parse_review_date(review_date) if review_date else None
        smallest = _load_experiment(experiment, experiment_file)
        return apply_move(
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
        return apply_merge(store, survivor_id, merged_id)

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
        if not (0 <= user_alignment <= 3):
            raise ConceptCommandError("--user-alignment must be 0-3")
        if hype is not None and not (0 <= hype <= 3):
            raise ConceptCommandError("--hype must be 0-3")
        return score_card(store, concept_id, user_alignment=user_alignment, hype=hype)

    _finalize("concept.score", output_format, run)


@concept.command("review")
def review_cmd(
    concept_id: str = typer.Argument(..., help="Concept ID"),
    outcome: str = typer.Option(..., "--outcome", "-o", help="Outcome: confirmed, partially_confirmed, rejected, inconclusive"),
    lesson: str = typer.Option(..., "--lesson", "-l", help="Lesson learned from the outcome"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format: json or md"),
) -> None:
    """Record a Build outcome + lesson without rewriting the original prediction."""
    store = ConceptStore(state_dir=state_dir)

    def run() -> dict:
        return record_outcome(store, concept_id, outcome, lesson)

    _finalize("concept.review", output_format, run)


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
    elif command == "concept.review":
        card = data.get("concept") or {}
        lines.append(f"- outcome: {card.get('outcome')}")
        lines.append(f"- lesson: {card.get('lesson')}")
        lines.append(f"- prediction preserved: {data.get('prediction_preserved')}")

    return "\n".join(lines)
