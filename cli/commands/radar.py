"""radar — cross-source concept lifecycle orchestration commands.

Deterministic-sandbox commands that orchestrate already-collected state (the
concept store plus a versioned radar config). No network, no LLM.

Subcommands
-----------
``radar scan <name>``          — scan a radar across its sources; record per-source
                                 coverage and surface affected concept cards.
``radar verify <concept_id>``  — run the six-gate build check on one concept card;
                                 ``--handoff`` imports a verification handoff first.
``radar experiment <id>``      — export a reviewable FDE-Gym scenario proposal from a
                                 Build-gated card (rejects unfalsifiable experiments).
``radar review <name>``        — weekly summary; surface build-eligible cards,
                                 respecting ``weekly_build_cap``.
``radar source-audit <name>``  — list per-source coverage status for a radar.

Every run loads a versioned YAML config from ``config/radars/<name>.yaml``,
writes the JSON payload first, re-validates the written JSON against the schema,
then renders Markdown (JSON-first, like the rest of the toolkit).

Source coverage
---------------
Each source type is recorded as one of:

- ``complete``      — evidence present, no known gaps,
- ``partial``       — evidence present but with an explicit gap (e.g. Reddit
                      RSS evidence whose comments were not read),
- ``unavailable``   — no evidence of that type in the store; recorded with a gap
                      note and the run continues with the other sources, and
- ``not_requested`` — the source was not requested for this run.

A partial source failure therefore yields a *usable* partial run with explicit
gaps: an unavailable source is never silently substituted by another source.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Callable

import typer
import yaml
from pydantic import BaseModel, ValidationError

from concepts.handoffs import (
    SourceHandoffEnvelope,
    import_handoff,
    normalize_handoff,
)
from concepts.scoring import (
    GATE_COUNTEREVIDENCE_REVIEWED,
    GATE_DESCRIPTIONS,
    GATE_EXPERIMENT_THRESHOLDS_AND_BUDGET,
    GATE_ORDER,
    GATE_SMALLEST_EXPERIMENT_PRESENT,
    GATE_TWO_INDEPENDENT_CHAINS,
    GATE_TWO_SOURCE_TYPES,
    GATE_WEEKLY_BUILDS_AVAILABLE,
    evaluate_build_gate,
    score,
)
from concepts.store import ConceptStore
from experiments.fde_gym import (
    FdeGymScenarioProposal,
    ScenarioExportError,
    export_fde_gym_scenario,
)
from experiments.generator import ExperimentGenerationError, generate_experiment
from models.concept import (
    ConceptEvidence,
    EvidenceRole,
    PortfolioStage,
    SourceType,
)
from models.radar_payload import (
    RadarRunPayload,
    SourceCoverage,
    SourceStatus,
)
from observability import OutputLevel, vprint


# ── Radar config models (inline; the radar config lives in config/radars/) ──

class Neighborhood(BaseModel):
    """One exploration neighborhood / lens over the radar's sources."""

    id: str
    label: str
    focus: str = ""


class RedditCommunity(BaseModel):
    """A Reddit community watched by the radar (problem or solution side)."""

    subreddit: str
    role: str = "problem"  # "problem" | "solution"
    segment: str = ""


class RadarConfig(BaseModel):
    """Versioned radar configuration loaded from config/radars/<name>.yaml."""

    version: int
    name: str
    description: str = ""
    neighborhoods: list[Neighborhood] = []
    exclusions: list[str] = []
    daily_card_cap: int = 3
    weekly_build_cap: int = 1
    reddit_communities: list[RedditCommunity] = []


# ── Verify payload (no canonical model exists for the build-gate report) ──

class GateRequirement(BaseModel):
    """One of the six hard build-gate requirements and whether it is met."""

    name: str
    met: bool
    detail: str


class VerifyEvidence(BaseModel):
    """Evidence summary backing a build-gate verification."""

    source_types: list[str]
    source_type_count: int
    supporting_chains: int
    counterevidence_count: int


class HandoffImportSummary(BaseModel):
    """Summary of one atomic verification-handoff import."""

    imported: int
    skipped_idempotent: int
    conflicts: list[str] = []
    attached_evidence_ids: list[str] = []


class VerifyPayload(BaseModel):
    """Structured six-gate build-gate report for ``radar verify``."""

    concept_id: str
    title: str
    passed: bool
    total: int = 0
    requirements: list[GateRequirement]
    missing: list[str]
    evidence: VerifyEvidence
    handoff: HandoffImportSummary | None = None


# ── Errors ──

class RadarConfigError(Exception):
    """Raised when a radar config cannot be found, parsed, or validated."""


# ── Constants ──

# All six evidence source types, in canonical enum order.
DEFAULT_SOURCE_TYPES: tuple[SourceType, ...] = tuple(SourceType)

# Adapters append "[coverage gap: ...]" into evidence notes for known gaps.
GAP_MARKER = "[coverage gap"

# Reddit RSS import carries no comments; the radar treats reddit evidence as
# PARTIAL (comments not read) unless a record is explicitly annotated otherwise.
COMMENTS_READ_MARKER = "[comments read]"

# Specific "missing" detail per failed six-gate name, rendered only for gates the
# scorer reports failed. Pass/fail itself comes from ``concepts.scoring.score``;
# these strings just make each failure actionable without re-deriving the check.
def _gate_missing_details(card, evidence) -> dict[str, str]:
    source_types = {e.source_type for e in evidence}
    supporting = [e for e in evidence if e.role != EvidenceRole.COUNTER]
    chains = {e.independence_key for e in supporting}
    return {
        GATE_TWO_SOURCE_TYPES: f"at least two source types (have {len(source_types)})",
        GATE_TWO_INDEPENDENT_CHAINS: (
            f"at least two independent supporting chains (have {len(chains)})"
        ),
        GATE_COUNTEREVIDENCE_REVIEWED: (
            "counterevidence present but unresolved (maturity is 'contested')"
        ),
        GATE_SMALLEST_EXPERIMENT_PRESENT: "a bounded smallest experiment is defined",
        GATE_EXPERIMENT_THRESHOLDS_AND_BUDGET: (
            "experiment must include success threshold, failure threshold, and a "
            "stop condition"
        ),
        GATE_WEEKLY_BUILDS_AVAILABLE: "weekly build budget exhausted for this run",
    }


def _verify_requirements(
    card,
    evidence,
    passed_gates: set[str],
) -> list[GateRequirement]:
    """Render the six build gates, with a specific detail for each failed gate."""
    missing_details = _gate_missing_details(card, evidence)
    requirements = []
    for gate_name in GATE_ORDER:
        met = gate_name in passed_gates
        detail = GATE_DESCRIPTIONS[gate_name] if met else missing_details[gate_name]
        requirements.append(GateRequirement(name=gate_name, met=met, detail=detail))
    return requirements


# ── Config loading ──

def load_radar_config(name: str, config_dir: str | Path = "config/radars") -> RadarConfig:
    """Load and validate a versioned radar config from ``<config_dir>/<name>.yaml``.

    Follows the ``config.load_config`` convention (YAML -> Pydantic validation).
    Raises :class:`RadarConfigError` for a missing file, unparsable YAML, or a
    ``name`` field that does not match the requested radar; raises Pydantic
    ``ValidationError`` for a structurally invalid config.
    """
    path = Path(config_dir) / f"{name}.yaml"
    if not path.exists():
        raise RadarConfigError(f"radar config not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RadarConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RadarConfigError(f"radar config {path} must be a YAML mapping")
    cfg = RadarConfig.model_validate(raw)
    if cfg.name != name:
        raise RadarConfigError(
            f"radar config name {cfg.name!r} does not match requested radar {name!r}"
        )
    return cfg


def _load_radar_or_exit(name: str, config_dir: str) -> RadarConfig:
    """Load the radar config, or print a friendly error and exit non-zero."""
    try:
        return load_radar_config(name, config_dir)
    except (RadarConfigError, ValidationError) as exc:
        vprint(f"[red]{exc}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)


# ── Source coverage ──

def _parse_sources(raw: str | None) -> set[SourceType]:
    """Parse a comma-separated ``--sources`` value into a set of source types.

    ``None`` (the default) means "all six source types are requested".
    """
    if raw is None or not raw.strip():
        return set(DEFAULT_SOURCE_TYPES)
    requested: set[SourceType] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            requested.add(SourceType(token))
        except ValueError:
            valid = ", ".join(st.value for st in SourceType)
            raise RadarConfigError(
                f"unknown source type {token!r}; valid: {valid}"
            )
    return requested


def _parse_sources_or_exit(raw: str | None) -> set[SourceType]:
    """Parse ``--sources``, or print a friendly error and exit non-zero."""
    try:
        return _parse_sources(raw)
    except RadarConfigError as exc:
        vprint(f"[red]{exc}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)


def _gap_text(note: str) -> str:
    """Return the coverage-gap portion of a note, or the note itself."""
    idx = note.find(GAP_MARKER)
    if idx == -1:
        return note
    return note[idx:].strip()


def _source_gaps(source_type: SourceType, records: list[ConceptEvidence]) -> list[str]:
    """Collect explicit coverage gaps for one source type's evidence records."""
    gaps: list[str] = []
    for record in records:
        if GAP_MARKER in record.note:
            gaps.append(f"{record.id}: {_gap_text(record.note)}")

    # Reddit RSS returns posts only (no comments). Unless a record is explicitly
    # annotated "[comments read]", the coverage is only partial — it cannot be
    # described as community consensus.
    if source_type is SourceType.REDDIT and not any(
        COMMENTS_READ_MARKER in r.note for r in records
    ):
        gaps.append(
            "Reddit RSS evidence — comments not read; not community consensus"
        )
    return gaps


def classify_source(
    source_type: SourceType,
    records: list[ConceptEvidence],
    requested: set[SourceType],
) -> SourceCoverage:
    """Classify one source as complete / partial / unavailable / not_requested.

    An unavailable source is recorded with a gap note and the caller continues
    with the other sources — never silently substituting another source.
    """
    if source_type not in requested:
        return SourceCoverage(
            source_type=source_type,
            status=SourceStatus.NOT_REQUESTED,
            note="not requested for this radar run",
        )
    if not records:
        return SourceCoverage(
            source_type=source_type,
            status=SourceStatus.UNAVAILABLE,
            note=(
                f"no {source_type.value} evidence in the store; "
                f"source unavailable for this run"
            ),
        )
    gaps = _source_gaps(source_type, records)
    if gaps:
        return SourceCoverage(
            source_type=source_type,
            status=SourceStatus.PARTIAL,
            note="; ".join(gaps),
        )
    return SourceCoverage(
        source_type=source_type,
        status=SourceStatus.COMPLETE,
        note=f"{len(records)} {source_type.value} evidence record(s) scanned, no known gaps",
    )


def build_coverage(
    evidence: list[ConceptEvidence],
    requested: set[SourceType],
) -> list[SourceCoverage]:
    """Build per-source coverage for all source types in canonical order."""
    by_source: dict[SourceType, list[ConceptEvidence]] = defaultdict(list)
    for record in evidence:
        by_source[record.source_type].append(record)
    return [
        classify_source(source_type, by_source[source_type], requested)
        for source_type in DEFAULT_SOURCE_TYPES
    ]


# ── JSON-first emit ──

def _emit(
    payload: BaseModel,
    output: Path,
    model_cls: type[BaseModel],
    renderer: Callable[[BaseModel], str],
) -> Path:
    """Write JSON first, re-validate it, then render Markdown.

    The JSON payload is the canonical artifact; the Markdown is rendered from
    the validated JSON so the two can never disagree.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    json_text = payload.model_dump_json(indent=2)
    output.write_text(json_text, encoding="utf-8")

    # Validate the written JSON round-trips through the schema before rendering.
    validated = model_cls.model_validate_json(json_text)

    md_path = output.with_suffix(".md")
    md_path.write_text(renderer(validated), encoding="utf-8")
    return output


# ── Markdown renderers ──

def _render_radar_md(payload: RadarRunPayload) -> str:
    lines = [f"# Radar: {payload.radar}"]
    if payload.period:
        lines.append(f"**Period:** {payload.period}")
    lines.append(f"**Run at:** {payload.run_at.isoformat()}")
    lines.append("")
    lines.append("## Source coverage")
    lines.append("| Source | Status | Note |")
    lines.append("|---|---|---|")
    for source in payload.sources:
        lines.append(
            f"| {source.source_type.value} | {source.status.value} | {source.note} |"
        )
    lines.append("")
    if payload.cards_affected:
        lines.append("## Cards affected")
        for concept_id in payload.cards_affected:
            lines.append(f"- {concept_id}")
        lines.append("")
    if payload.summary:
        lines.append(f"**Summary:** {payload.summary}")
        lines.append("")
    if payload.gaps:
        lines.append("## Gaps")
        for gap in payload.gaps:
            lines.append(f"- {gap}")
        lines.append("")
    return "\n".join(lines)


def _render_verify_md(payload: VerifyPayload) -> str:
    lines = [f"# Build-gate verification: {payload.concept_id}"]
    lines.append(f"**Title:** {payload.title}")
    lines.append(f"**Passed:** {'yes' if payload.passed else 'no'}")
    lines.append("")
    lines.append("## Requirements")
    for requirement in payload.requirements:
        mark = "x" if requirement.met else " "
        lines.append(f"- [{mark}] {requirement.name} — {requirement.detail}")
    if payload.missing:
        lines.append("")
        lines.append("## Missing")
        for missing in payload.missing:
            lines.append(f"- {missing}")
    lines.append("")
    lines.append("## Evidence")
    evidence = payload.evidence
    lines.append(
        f"- source types: {', '.join(evidence.source_types) or 'none'} "
        f"({evidence.source_type_count})"
    )
    lines.append(f"- supporting independent chains: {evidence.supporting_chains}")
    lines.append(f"- counterevidence records: {evidence.counterevidence_count}")
    return "\n".join(lines)


# ── Typer app ──

radar_app = typer.Typer(
    name="radar",
    help="Cross-source concept radar: scan, verify, experiment, review, and source-audit.",
    no_args_is_help=True,
)


@radar_app.command("scan")
def scan(
    radar: str = typer.Argument(..., help="Radar name (config/radars/<name>.yaml)"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output: str = typer.Option(
        "output/radar/scan.json", "--output", "-o", help="Output JSON path"
    ),
    config_dir: str = typer.Option(
        "config/radars", "--config-dir", help="Radar config directory"
    ),
    sources: str | None = typer.Option(
        None,
        "--sources",
        help="Comma-separated source types to request (default: all six)",
    ),
    override: bool = typer.Option(
        False, "--override", help="Bypass daily_card_cap"
    ),
) -> None:
    """Scan a radar across its sources and record per-source coverage.

    Loads the versioned radar config, inspects already-collected evidence in the
    store, and records each source as complete / partial / unavailable /
    not_requested. An unavailable source is recorded with a gap and the scan
    continues — it is never silently substituted. ``daily_card_cap`` limits the
    number of surfaced cards unless ``--override`` is given.
    """
    cfg = _load_radar_or_exit(radar, config_dir)
    store = ConceptStore(state_dir=state_dir)
    requested = _parse_sources_or_exit(sources)

    evidence = store.list_evidence()
    coverage = build_coverage(evidence, requested)

    # A card is "affected" when it has evidence of a requested source type.
    affected = sorted(
        {e.concept_id for e in evidence if e.source_type in requested}
    )

    gaps: list[str] = [s.note for s in coverage if s.status in (SourceStatus.PARTIAL, SourceStatus.UNAVAILABLE)]

    surfaced = affected
    if not override and len(affected) > cfg.daily_card_cap:
        surfaced = affected[: cfg.daily_card_cap]
        gaps.append(
            f"daily_card_cap={cfg.daily_card_cap} enforced: surfaced "
            f"{len(surfaced)} of {len(affected)} affected card(s); "
            f"use --override to bypass"
        )

    status_counts = {
        status: sum(1 for s in coverage if s.status is status)
        for status in SourceStatus
    }
    summary = (
        f"scanned {cfg.name}: {len(surfaced)} of {len(affected)} affected "
        f"card(s) surfaced; {status_counts[SourceStatus.COMPLETE]} complete, "
        f"{status_counts[SourceStatus.PARTIAL]} partial, "
        f"{status_counts[SourceStatus.UNAVAILABLE]} unavailable, "
        f"{status_counts[SourceStatus.NOT_REQUESTED]} not requested"
    )

    payload = RadarRunPayload(
        radar=cfg.name,
        period="",
        sources=coverage,
        cards_affected=surfaced,
        summary=summary,
        gaps=gaps,
    )
    out = _emit(payload, Path(output), RadarRunPayload, _render_radar_md)
    vprint(f"[green]radar scan → {out}[/green]", level=OutputLevel.NORMAL)


def _read_verification_handoff(path: str) -> SourceHandoffEnvelope:
    """Read and validate a verification handoff JSON file.

    Raises :class:`RadarConfigError` for a missing file, invalid JSON, or a
    handoff that fails envelope validation. Validation is atomic: one
    structurally invalid item rejects the whole handoff, matching
    ``concepts.handoffs.import_handoff``.
    """
    handoff_path = Path(path)
    if not handoff_path.exists():
        raise RadarConfigError(f"handoff file not found: {handoff_path}")
    try:
        raw = handoff_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RadarConfigError(f"cannot read handoff file {handoff_path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RadarConfigError(f"invalid JSON in handoff {handoff_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RadarConfigError(f"handoff {handoff_path} must be a JSON object")
    try:
        return SourceHandoffEnvelope.model_validate(data)
    except ValidationError as exc:
        raise RadarConfigError(f"invalid verification handoff {handoff_path}: {exc}") from exc


def _attach_handoff_evidence(
    store: ConceptStore,
    concept_id: str,
    envelope: SourceHandoffEnvelope,
) -> HandoffImportSummary:
    """Import a verification handoff and attach its evidence to ``concept_id``.

    Verification handoffs (GitHub / paper / official doc) attach to an existing
    concept the envelope does not name, so ``import_handoff`` lands them under a
    placeholder ``concept_id``. This re-points each imported record to
    ``concept_id`` with the same append-only ``supersedes`` pattern as a concept
    merge, then links the attached IDs onto the card's ``evidence_ids``. Replay
    is idempotent: a re-targeted record is only appended once and the card's
    ``evidence_ids`` stays de-duplicated.
    """
    result = import_handoff(store, envelope)

    attached: list[str] = []
    for record in normalize_handoff(envelope):
        if record.concept_id == concept_id:
            attached.append(record.id)
            continue
        re_targeted_id = f"{record.id}->{concept_id}"
        if store.get_evidence(re_targeted_id) is None:
            store.add_evidence(
                ConceptEvidence(
                    id=re_targeted_id,
                    concept_id=concept_id,
                    source_type=record.source_type,
                    source_url=record.source_url,
                    role=record.role,
                    directness=record.directness,
                    strength=record.strength,
                    independence_key=record.independence_key,
                    note=record.note,
                    supersedes=record.id,
                )
            )
        attached.append(re_targeted_id)

    card = store.get_concept(concept_id)
    evidence_ids = list(card.evidence_ids)
    for evidence_id in attached:
        if evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
    store.upsert_concept(card.model_copy(update={"evidence_ids": evidence_ids}))

    return HandoffImportSummary(
        imported=result.imported,
        skipped_idempotent=result.skipped_idempotent,
        conflicts=list(result.conflicts),
        attached_evidence_ids=attached,
    )


@radar_app.command("verify")
def verify(
    concept_id: str = typer.Argument(..., help="Concept card ID to verify"),
    handoff: str | None = typer.Option(
        None, "--handoff", help="Path to a verification handoff JSON file to import"
    ),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output: str = typer.Option(
        "output/radar/verify.json", "--output", "-o", help="Output JSON path"
    ),
) -> None:
    """Run the six-gate build check on one card and report what is missing.

    ``--handoff`` imports a verification handoff atomically (via
    ``concepts.handoffs.import_handoff``) and attaches its evidence to the card
    before scoring. Without it, the card and its already-stored evidence are
    scored as-is.
    """
    store = ConceptStore(state_dir=state_dir)
    card = store.get_concept(concept_id)
    if card is None:
        vprint(
            f"[red]concept {concept_id!r} not found in store[/red]",
            level=OutputLevel.QUIET,
        )
        raise typer.Exit(1)

    handoff_summary: HandoffImportSummary | None = None
    if handoff is not None:
        try:
            envelope = _read_verification_handoff(handoff)
        except (RadarConfigError, ValidationError) as exc:
            vprint(f"[red]{exc}[/red]", level=OutputLevel.QUIET)
            raise typer.Exit(1)
        handoff_summary = _attach_handoff_evidence(store, concept_id, envelope)
        card = store.get_concept(concept_id)

    evidence = store.list_evidence(concept_id)
    result = score(card, evidence)

    requirements = _verify_requirements(card, evidence, set(result.passed_gates))

    evidence_summary = VerifyEvidence(
        source_types=sorted({e.source_type.value for e in evidence}),
        source_type_count=len({e.source_type for e in evidence}),
        supporting_chains=len(
            {e.independence_key for e in evidence if e.role != EvidenceRole.COUNTER}
        ),
        counterevidence_count=sum(
            1 for e in evidence if e.role == EvidenceRole.COUNTER
        ),
    )

    payload = VerifyPayload(
        concept_id=concept_id,
        title=card.title,
        passed=not result.failed_gates,
        total=result.total,
        requirements=requirements,
        missing=list(result.failed_gates),
        evidence=evidence_summary,
        handoff=handoff_summary,
    )
    out = _emit(payload, Path(output), VerifyPayload, _render_verify_md)
    vprint(
        f"[green]build gate {'passed' if payload.passed else 'not passed'} → {out}[/green]",
        level=OutputLevel.NORMAL,
    )


@radar_app.command("experiment")
def experiment(
    concept_id: str = typer.Argument(..., help="Concept card ID"),
    output_format: str = typer.Option(
        "json", "--format", "-f", help="Output format: json or fde-gym"
    ),
    budget: str = typer.Option(
        None, "--budget", help="Time/cost budget committed to the experiment"
    ),
    scenario_name: str = typer.Option(
        None, "--scenario-name", help="Scenario name (default: card title)"
    ),
    failure_mode: str = typer.Option(
        None, "--failure-mode",
        help="The specific failure the simulated environment reproduces",
    ),
    environment: str = typer.Option(
        None, "--environment",
        help="The simulated environment (state, tools, feedback)",
    ),
    agent_goal: str = typer.Option(
        None, "--agent-goal", help="The visible goal given to the agent"
    ),
    hidden_constraints: list[str] | None = typer.Option(
        None, "--hidden-constraint", help="A hidden constraint (repeatable)"
    ),
    counterexample: str = typer.Option(
        None, "--counterexample", help="A concrete case where naive behaviour fails"
    ),
    replay_reset: str = typer.Option(
        None, "--replay-reset",
        help="How the scenario resets and replays deterministically",
    ),
    smallest_prototype: str = typer.Option(
        None, "--smallest-prototype",
        help="Minimal prototype (default: experiment core artifact)",
    ),
    success_criteria: list[str] | None = typer.Option(
        None, "--success-criteria", help="Observable success criterion (repeatable)"
    ),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output: str = typer.Option(
        "output/radar/experiment.json", "--output", "-o", help="Output JSON path"
    ),
) -> None:
    """Export a reviewable FDE-Gym scenario proposal from a Build-gated card.

    Loads the card and its evidence, requires a smallest experiment, generates a
    bounded, falsifiable ``Experiment`` (rejecting anything missing a
    success/failure threshold, budget, or stop condition), then exports an
    ``FdeGymScenarioProposal``. Unsupported or unfalsifiable experiments are
    rejected before export; this writes a proposal only and never mutates
    FDE-Gym or any external repo.
    """
    if output_format not in ("json", "fde-gym"):
        vprint(
            f"[red]invalid --format {output_format!r}; expected 'json' or 'fde-gym'[/red]",
            level=OutputLevel.QUIET,
        )
        raise typer.Exit(1)

    store = ConceptStore(state_dir=state_dir)
    card = store.get_concept(concept_id)
    if card is None:
        vprint(
            f"[red]concept {concept_id!r} not found in store[/red]",
            level=OutputLevel.QUIET,
        )
        raise typer.Exit(1)

    if card.smallest_experiment is None:
        vprint(
            f"[red]concept {concept_id!r} is not Build-gated: no smallest "
            "experiment is defined, so the success/failure thresholds and stop "
            "condition are absent[/red]",
            level=OutputLevel.QUIET,
        )
        raise typer.Exit(1)

    evidence = store.list_evidence(concept_id)

    try:
        generated = generate_experiment(card, evidence, budget=budget)
    except ExperimentGenerationError as exc:
        vprint(f"[red]{exc}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    try:
        proposal = export_fde_gym_scenario(
            card,
            evidence,
            generated,
            scenario_name=scenario_name,
            failure_mode=failure_mode,
            environment=environment,
            agent_goal=agent_goal,
            hidden_constraints=hidden_constraints,
            success_criteria=success_criteria,
            counterexample=counterexample,
            replay_reset_requirements=replay_reset,
            smallest_prototype=smallest_prototype,
        )
    except ScenarioExportError as exc:
        vprint(f"[red]{exc}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    # JSON-first: write the proposal, re-validate the written JSON, done. A
    # proposal only — no Markdown render, no external mutation.
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_json = proposal.to_json()
    out_path.write_text(proposal_json, encoding="utf-8")
    FdeGymScenarioProposal.model_validate_json(proposal_json)

    vprint(f"[green]radar experiment → {out_path}[/green]", level=OutputLevel.NORMAL)


@radar_app.command("review")
def review(
    radar: str = typer.Argument(..., help="Radar name (config/radars/<name>.yaml)"),
    period: str = typer.Option(..., "--period", help="Review period, e.g. 2026-W36"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output: str = typer.Option(
        "output/radar/review.json", "--output", "-o", help="Output JSON path"
    ),
    config_dir: str = typer.Option(
        "config/radars", "--config-dir", help="Radar config directory"
    ),
    override: bool = typer.Option(
        False, "--override", help="Bypass weekly_build_cap"
    ),
) -> None:
    """Produce a weekly review summary for a radar and its period.

    A card is eligible for promotion to Build when it is at the ``verify`` stage
    and passes the hard build gate. ``weekly_build_cap`` limits the number of
    promotions unless ``--override`` is given.
    """
    cfg = _load_radar_or_exit(radar, config_dir)
    store = ConceptStore(state_dir=state_dir)

    concepts = store.list_concepts()
    evidence = store.list_evidence()
    by_concept: dict[str, list[ConceptEvidence]] = defaultdict(list)
    for record in evidence:
        by_concept[record.concept_id].append(record)

    eligible = [
        card
        for card in concepts
        if card.stage == PortfolioStage.VERIFY
        and evaluate_build_gate(card, by_concept.get(card.id, [])).passed
    ]
    eligible.sort(key=lambda c: c.id)

    gaps: list[str] = []
    promoted = eligible
    if not override and len(eligible) > cfg.weekly_build_cap:
        promoted = eligible[: cfg.weekly_build_cap]
        gaps.append(
            f"weekly_build_cap={cfg.weekly_build_cap} enforced: promoted "
            f"{len(promoted)} of {len(eligible)} build-eligible card(s); "
            f"use --override to bypass"
        )

    coverage = build_coverage(evidence, set(DEFAULT_SOURCE_TYPES))
    gaps.extend(
        s.note for s in coverage if s.status in (SourceStatus.PARTIAL, SourceStatus.UNAVAILABLE)
    )

    summary = (
        f"weekly review {period} for {cfg.name}: {len(promoted)} of "
        f"{len(eligible)} build-eligible card(s) promoted to Build"
    )

    payload = RadarRunPayload(
        radar=cfg.name,
        period=period,
        sources=coverage,
        cards_affected=[c.id for c in promoted],
        summary=summary,
        gaps=gaps,
    )
    out = _emit(payload, Path(output), RadarRunPayload, _render_radar_md)
    vprint(f"[green]radar review → {out}[/green]", level=OutputLevel.NORMAL)


@radar_app.command("source-audit")
def source_audit(
    radar: str = typer.Argument(..., help="Radar name (config/radars/<name>.yaml)"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output: str = typer.Option(
        "output/radar/source-audit.json", "--output", "-o", help="Output JSON path"
    ),
    config_dir: str = typer.Option(
        "config/radars", "--config-dir", help="Radar config directory"
    ),
    sources: str | None = typer.Option(
        None,
        "--sources",
        help="Comma-separated source types to request (default: all six)",
    ),
) -> None:
    """List per-source coverage status for a radar (no card updates)."""
    cfg = _load_radar_or_exit(radar, config_dir)
    store = ConceptStore(state_dir=state_dir)
    requested = _parse_sources_or_exit(sources)

    coverage = build_coverage(store.list_evidence(), requested)
    gaps: list[str] = [
        s.note for s in coverage if s.status in (SourceStatus.PARTIAL, SourceStatus.UNAVAILABLE)
    ]

    status_counts = {
        status: sum(1 for s in coverage if s.status is status)
        for status in SourceStatus
    }
    summary = (
        f"source audit for {cfg.name}: "
        f"{status_counts[SourceStatus.COMPLETE]} complete, "
        f"{status_counts[SourceStatus.PARTIAL]} partial, "
        f"{status_counts[SourceStatus.UNAVAILABLE]} unavailable, "
        f"{status_counts[SourceStatus.NOT_REQUESTED]} not requested"
    )

    payload = RadarRunPayload(
        radar=cfg.name,
        period="",
        sources=coverage,
        cards_affected=[],
        summary=summary,
        gaps=gaps,
    )
    out = _emit(payload, Path(output), RadarRunPayload, _render_radar_md)
    vprint(f"[green]radar source-audit → {out}[/green]", level=OutputLevel.NORMAL)
