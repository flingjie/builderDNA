"""Deterministic concept lifecycle service (no Typer, no stdout).

The pure business logic behind the ``concept`` CLI: capture, move, merge, score,
record outcomes, and import source handoffs. Every method takes a
:class:`~concepts.store.ConceptStore` and returns a ``{"action", "changed",
"data"}`` dictionary — never prints, never exits. The CLI layer
(``cli/commands/concept.py``) parses Typer options, calls these methods, and
renders the JSON-first envelope.

Exit-code contract (surfaced by the CLI, documented here as the source of truth):

- ``0`` — success.
- ``1`` — unexpected failure (:class:`ConceptServiceError` base, a store error
  like ``CorruptionError``, or an unhandled ``ValueError``).
- ``2`` — validation error (:class:`ConceptValidationError`): bad input, an
  unknown concept, a disallowed stage transition, an ambiguous capture, or a
  structurally invalid handoff envelope.
- ``3`` — conflict (:class:`ConceptConflictError`, or a
  :class:`concepts.store.ConflictError` bubbling up from the store): the same
  record ID already exists with a different payload.
- ``4`` — blocked gate (:class:`ConceptGateBlockedError`): a hard build gate did
  not pass.

Capture matching uses :func:`concepts.matching.classify_match`:

- ``"none"``     -> create a new card;
- ``"exact"``    -> auto-merge into the top candidate;
- ``"suggested"`` -> raise the ambiguity error (never auto-merge).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError

from concepts.adapters.manual_x import to_evidence
from concepts.handoffs import (
    UNASSIGNED_CONCEPT_ID,
    SourceHandoffEnvelope,
    import_handoff,
    normalize_handoff,
)
from concepts.matching import classify_match, normalize_name
from concepts.scoring import evaluate_build_gate, score_components
from concepts.store import ConceptStore
from models.concept import (
    ConceptCard,
    ConceptEvidence,
    OutcomeState,
    PortfolioStage,
    RadarReview,
    SmallestExperiment,
    SourceType,
)

# ── Errors (each carries its documented exit code) ──


class ConceptServiceError(Exception):
    """Base domain error — maps to exit code 1 (unexpected failure)."""

    exit_code = 1

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConceptValidationError(ConceptServiceError):
    """Invalid input or disallowed state — maps to exit code 2."""

    exit_code = 2


class ConceptConflictError(ConceptServiceError):
    """Same record ID with a different payload — maps to exit code 3."""

    exit_code = 3


class ConceptGateBlockedError(ConceptServiceError):
    """A hard build gate did not pass — maps to exit code 4."""

    exit_code = 4


# ── Small utilities ──


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


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
        raise ConceptValidationError(
            f"invalid source {value!r}; expected one of {[s.value for s in SourceType]}"
        )


def parse_review_date(value: str) -> datetime:
    """Parse a ``--review-date`` value, requiring an explicit UTC timestamp."""
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConceptValidationError(f"invalid --review-date {value!r}: {exc}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.utcoffset() != timedelta(0):
        raise ConceptValidationError(
            "--review-date must be UTC (e.g. 2026-09-08T00:00:00Z)"
        )
    return dt


def parse_experiment(
    experiment_json: str | None, experiment_file: str | None
) -> SmallestExperiment | None:
    """Parse an inline JSON experiment or a JSON experiment file."""
    if experiment_json and experiment_file:
        raise ConceptValidationError(
            "provide only one of --experiment or --experiment-file"
        )
    raw: str | None = None
    if experiment_file:
        path = Path(experiment_file)
        if not path.exists():
            raise ConceptValidationError(f"experiment file not found: {experiment_file}")
        raw = path.read_text(encoding="utf-8")
    elif experiment_json:
        raw = experiment_json
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConceptValidationError(f"invalid experiment JSON: {exc}")
    if not isinstance(data, dict):
        raise ConceptValidationError("experiment must be a JSON object")
    try:
        return SmallestExperiment(**data)
    except Exception as exc:  # pydantic validation -> clean service error
        raise ConceptValidationError(f"invalid smallest experiment: {exc}")


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


def _repoint_evidence(
    store: ConceptStore, evidence: ConceptEvidence, new_concept_id: str
) -> str:
    """Append a superseding evidence record pointing at ``new_concept_id``.

    Evidence is immutable, so re-pointing appends ``<old_id>-><new_id>`` rather
    than editing the original record (mirrors ``merge``'s lineage behaviour).
    Returns the new record's ID.
    """
    new_id = f"{evidence.id}->{new_concept_id}"
    if store.get_evidence(new_id) is None:
        store.add_evidence(
            ConceptEvidence(
                id=new_id,
                concept_id=new_concept_id,
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
    return new_id


# ── Capture ──


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

    Matching uses ``classify_match``: ``none`` creates, ``exact`` auto-merges,
    ``suggested`` raises the ambiguity error (never auto-merged). Returns
    ``action`` in {"created", "merged", "already_captured"}.
    """
    aliases = list(aliases or [])
    source_type = _parse_source(source)

    if not title:
        title = derive_title(note)
    if not title or not title.strip():
        raise ConceptValidationError(
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

    classification = classify_match(
        candidate,
        store.list_concepts(),
        candidate_urls=[url],
        existing_urls=_existing_urls(store),
    )
    candidates_payload = _candidates_payload(list(classification.candidates))

    target_id: str | None = None
    action = "created"
    if merge_into:
        if store.get_concept(merge_into) is None:
            raise ConceptValidationError(f"merge target {merge_into!r} not found")
        target_id = merge_into
        action = "merged"
    elif classification.kind == "exact":
        target_id = classification.top.concept_id
        action = "merged"
    elif classification.kind == "suggested":
        raise ConceptValidationError(
            "capture is ambiguous — multiple or conflicting matches; "
            "re-run with --into <ID> to disambiguate (never auto-merged)",
            details={
                "candidates": candidates_payload,
                "hint": "pass --into with one of the candidate concept IDs",
            },
        )

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


# ── Move ──


def move(
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
    ``review_date``, and a passing ``evaluate_build_gate`` (a failed gate raises
    :class:`ConceptGateBlockedError` -> exit 4). Every successful move appends a
    ``RadarReview``.
    """
    card = store.get_concept(concept_id)
    if card is None:
        raise ConceptValidationError(f"concept {concept_id!r} not found")
    try:
        target = PortfolioStage(target_stage)
    except ValueError:
        raise ConceptValidationError(
            f"invalid stage {target_stage!r}; expected one of {[s.value for s in PortfolioStage]}"
        )
    if card.stage == target:
        raise ConceptValidationError(
            f"concept {concept_id!r} is already in stage '{target.value}'"
        )
    if not reason or not reason.strip():
        raise ConceptValidationError("move requires --reason")

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
            raise ConceptValidationError(
                "move to 'build' requires " + ", ".join(missing)
            )
        if experiment is not None:
            card = card.model_copy(update={"smallest_experiment": experiment})
        gate = evaluate_build_gate(card, evidence)
        if not gate.passed:
            raise ConceptGateBlockedError(
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


# ── Merge ──


def merge(store: ConceptStore, survivor_id: str, merged_id: str) -> dict:
    """Merge ``merged_id`` into ``survivor_id``.

    Unions aliases, re-points the merged-away card's evidence to the survivor
    via append-only superseding records, and marks the merged-away card dropped.
    """
    if survivor_id == merged_id:
        raise ConceptValidationError("cannot merge a concept into itself")
    survivor = store.get_concept(survivor_id)
    merged = store.get_concept(merged_id)
    if survivor is None:
        raise ConceptValidationError(f"concept {survivor_id!r} not found")
    if merged is None:
        raise ConceptValidationError(f"concept {merged_id!r} not found")

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


# ── Score ──


def score(
    store: ConceptStore,
    concept_id: str,
    *,
    user_alignment: int = 0,
    hype: int | None = None,
) -> dict:
    """Return derived component scores, per-component reasons, and the gate."""
    if not (0 <= user_alignment <= 3):
        raise ConceptValidationError("--user-alignment must be 0-3")
    if hype is not None and not (0 <= hype <= 3):
        raise ConceptValidationError("--hype must be 0-3")
    card = store.get_concept(concept_id)
    if card is None:
        raise ConceptValidationError(f"concept {concept_id!r} not found")
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


# ── Outcome ──


def record_outcome(
    store: ConceptStore, concept_id: str, outcome: str, lesson: str
) -> dict:
    """Record a Build outcome + lesson without rewriting the prediction.

    Requires a prior prediction (proof the card entered Build). The original
    prediction is left untouched, and every review appends an immutable
    ``RadarReview`` so the outcome history stays traceable.
    """
    card = store.get_concept(concept_id)
    if card is None:
        raise ConceptValidationError(f"concept {concept_id!r} not found")
    if not card.prediction.strip():
        raise ConceptValidationError(
            f"concept {concept_id!r} has no recorded prediction — enter Build first "
            "('concept move <id> build --prediction ...') before recording an outcome"
        )
    try:
        outcome_state = OutcomeState(outcome)
    except ValueError:
        raise ConceptValidationError(
            f"invalid outcome {outcome!r}; expected one of {[o.value for o in OutcomeState]}"
        )
    if not lesson or not lesson.strip():
        raise ConceptValidationError("outcome requires --lesson")

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


# ── Handoff capture ──


def capture_handoff(
    store: ConceptStore,
    handoff_data: SourceHandoffEnvelope | dict,
    *,
    merge_into: str | None = None,
) -> dict:
    """Validate/import a source handoff and attach created/merged cards.

    Flow: validate the envelope, import evidence atomically via
    :func:`concepts.handoffs.import_handoff` (a conflict raises
    :class:`ConceptConflictError` -> exit 3; an invalid envelope raises
    :class:`ConceptValidationError` -> exit 2), then for every item carrying a
    ``proposed_concept`` classify against existing cards:

    - ``none``      -> create a card and attach the imported evidence;
    - ``exact``     -> merge into the matched card and attach the evidence;
    - ``suggested`` -> raise the ambiguity error (never auto-merge).

    Items without a proposed concept stay attached to ``"unassigned"`` and are
    reported in ``unattached_evidence_ids`` for a later phase to attach.
    """
    try:
        envelope = (
            handoff_data
            if isinstance(handoff_data, SourceHandoffEnvelope)
            else SourceHandoffEnvelope.model_validate(handoff_data)
        )
    except PydanticValidationError as exc:
        raise ConceptValidationError(f"invalid handoff envelope: {exc}")

    import_result = import_handoff(store, envelope)
    if import_result.conflicts:
        raise ConceptConflictError(
            "handoff import conflict — evidence IDs collide with existing records",
            details={"conflicts": import_result.conflicts},
        )

    # Normalization is deterministic, so these records mirror what import_handoff
    # just wrote (same IDs, same concept_ids, same order as envelope.items).
    records = normalize_handoff(envelope)

    created_ids: list[str] = []
    merged_ids: list[str] = []
    created_cards: list[ConceptCard] = []
    merged_cards: list[ConceptCard] = []
    unattached: list[str] = []
    changed: list[str] = []

    for item, record in zip(envelope.items, records):
        proposed = item.proposed_concept
        if proposed is None or not proposed.title.strip():
            if record.concept_id == UNASSIGNED_CONCEPT_ID:
                unattached.append(record.id)
            continue

        provisional_id = slugify(proposed.title)
        candidate = ConceptCard(
            id=provisional_id,
            title=proposed.title,
            aliases=list(proposed.aliases),
            problem=proposed.problem,
            why_now=proposed.why_now,
        )
        classification = classify_match(
            candidate,
            store.list_concepts(),
            candidate_urls=[item.url] if item.url else [],
            existing_urls=_existing_urls(store),
        )

        target_id: str | None = None
        if merge_into:
            if store.get_concept(merge_into) is None:
                raise ConceptValidationError(f"merge target {merge_into!r} not found")
            target_id = merge_into
        elif classification.kind == "exact":
            target_id = classification.top.concept_id
        elif classification.kind == "suggested":
            raise ConceptValidationError(
                "handoff capture is ambiguous — multiple or conflicting matches; "
                "re-run with --into <ID> to disambiguate (never auto-merged)",
                details={
                    "candidates": _candidates_payload(list(classification.candidates)),
                    "hint": "pass --into with one of the candidate concept IDs",
                },
            )

        if target_id is None:
            final_id = _unique_id(store, provisional_id)
            card = ConceptCard(
                id=final_id,
                title=proposed.title,
                aliases=list(proposed.aliases),
                problem=proposed.problem,
                why_now=proposed.why_now,
                stage=PortfolioStage.INBOX,
            )
            attached_id = record.id
            if record.concept_id != final_id:
                attached_id = _repoint_evidence(store, record, final_id)
            card = card.model_copy(update={"evidence_ids": [attached_id]})
            card = store.upsert_concept(card)
            created_ids.append(final_id)
            created_cards.append(card)
            changed.append(f"concept created: {final_id}")
        else:
            surviving = store.get_concept(target_id)
            new_aliases = list(surviving.aliases)
            existing_norms = {normalize_name(a) for a in surviving.aliases}
            title_norm = normalize_name(proposed.title)
            if (
                title_norm != normalize_name(surviving.title)
                and title_norm not in existing_norms
            ):
                new_aliases.append(proposed.title)
            attached_id = record.id
            if record.concept_id != target_id:
                attached_id = _repoint_evidence(store, record, target_id)
            evidence_ids = list(surviving.evidence_ids)
            if attached_id not in evidence_ids:
                evidence_ids.append(attached_id)
            card = surviving.model_copy(
                update={"aliases": new_aliases, "evidence_ids": evidence_ids}
            )
            card = store.upsert_concept(card)
            merged_ids.append(target_id)
            merged_cards.append(card)
            changed.append(f"concept merged: {target_id}")

    return {
        "action": "handoff_captured",
        "changed": changed,
        "data": {
            "import": {
                "imported": import_result.imported,
                "skipped_idempotent": import_result.skipped_idempotent,
                "conflicts": import_result.conflicts,
                "concept_ids_affected": import_result.concept_ids_affected,
            },
            "created": [c.model_dump(mode="json") for c in created_cards],
            "merged": [c.model_dump(mode="json") for c in merged_cards],
            "created_ids": created_ids,
            "merged_ids": merged_ids,
            "unattached_evidence_ids": unattached,
        },
    }


# ── Read-only helpers for the list / show commands ──


def list_cards(
    store: ConceptStore,
    *,
    stage: str | None = None,
    radar: str | None = None,
) -> dict:
    """List concept cards, optionally filtered by stage and/or radar name.

    ``radar`` filters on an optional ``radar`` attribute when cards carry one;
    cards without a radar field (the current ``ConceptCard`` model) are left
    unfiltered — a graceful no-op until the model grows the field.
    """
    cards = store.list_concepts()
    if stage:
        try:
            st = PortfolioStage(stage)
        except ValueError:
            raise ConceptValidationError(
                f"invalid stage {stage!r}; expected one of {[s.value for s in PortfolioStage]}"
            )
        cards = [c for c in cards if c.stage == st]
    if radar:
        cards = [
            c
            for c in cards
            if not hasattr(c, "radar") or getattr(c, "radar", None) == radar
        ]
    return {
        "action": "listed",
        "changed": [],
        "data": {
            "cards": [c.model_dump(mode="json") for c in cards],
            "count": len(cards),
        },
    }


def show(store: ConceptStore, concept_id: str) -> dict:
    """Show one card with its evidence and review history."""
    card = store.get_concept(concept_id)
    if card is None:
        raise ConceptValidationError(f"concept {concept_id!r} not found")
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
