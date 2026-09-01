"""radar — cross-source concept lifecycle orchestration commands.

Deterministic-sandbox commands that orchestrate already-collected state (the
concept store plus a versioned radar config). No network, no LLM.

Subcommands
-----------
``radar scan <name>``          — scan a radar across its sources; record per-source
                                 coverage and surface affected concept cards.
``radar verify <concept_id>``  — run the hard build gate on one concept card.
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

from collections import defaultdict
from pathlib import Path
from typing import Callable

import typer
import yaml
from pydantic import BaseModel, ValidationError

from concepts.scoring import evaluate_build_gate
from concepts.store import ConceptStore
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
    """One of the four hard build-gate requirements and whether it is met."""

    name: str
    met: bool
    detail: str


class VerifyEvidence(BaseModel):
    """Evidence summary backing a build-gate verification."""

    source_types: list[str]
    source_type_count: int
    supporting_chains: int
    counterevidence_count: int


class VerifyPayload(BaseModel):
    """Structured build-gate report for ``radar verify``."""

    concept_id: str
    title: str
    passed: bool
    requirements: list[GateRequirement]
    missing: list[str]
    evidence: VerifyEvidence


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

# The four hard build-gate requirements, in a stable display order. Each name
# must be a prefix of the corresponding "missing" string emitted by
# ``concepts.scoring.evaluate_build_gate`` so we can map met/unmet.
GATE_REQUIREMENT_SPECS: tuple[tuple[str, str], ...] = (
    ("two source types", "at least two distinct evidence source types"),
    (
        "two independent supporting chains",
        "at least two independent supporting evidence chains (counterevidence excluded)",
    ),
    (
        "reviewed counterevidence",
        "counterevidence is absent or resolved (maturity is not 'contested')",
    ),
    (
        "a bounded smallest experiment",
        "a bounded, falsifiable smallest experiment is defined",
    ),
)


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
    help="Cross-source concept radar: scan, verify, review, and source-audit.",
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


@radar_app.command("verify")
def verify(
    concept_id: str = typer.Argument(..., help="Concept card ID to verify"),
    state_dir: str = typer.Option("state", "--state-dir", help="Concept store directory"),
    output: str = typer.Option(
        "output/radar/verify.json", "--output", "-o", help="Output JSON path"
    ),
) -> None:
    """Run the hard build gate on one concept card and report what is missing."""
    store = ConceptStore(state_dir=state_dir)
    card = store.get_concept(concept_id)
    if card is None:
        vprint(
            f"[red]concept {concept_id!r} not found in store[/red]",
            level=OutputLevel.QUIET,
        )
        raise typer.Exit(1)

    evidence = store.list_evidence(concept_id)
    gate = evaluate_build_gate(card, evidence)

    requirements = []
    for name, description in GATE_REQUIREMENT_SPECS:
        miss = next((m for m in gate.missing if m.startswith(name)), None)
        requirements.append(
            GateRequirement(name=name, met=miss is None, detail=miss or description)
        )

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
        passed=gate.passed,
        requirements=requirements,
        missing=list(gate.missing),
        evidence=evidence_summary,
    )
    out = _emit(payload, Path(output), VerifyPayload, _render_verify_md)
    vprint(
        f"[green]build gate {'passed' if gate.passed else 'not passed'} → {out}[/green]",
        level=OutputLevel.NORMAL,
    )


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
