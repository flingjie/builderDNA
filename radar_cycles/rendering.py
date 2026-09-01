"""JSON-first report contract and rendering for radar cycles.

This module defines the canonical *report* payload for one completed (or
partial) radar cycle, then renders it to Markdown. The Markdown is presentation
only and is derived exclusively from the validated JSON model: ``render_run_markdown``
serializes the report with ``model_dump(mode="json")`` and renders that dict,
never the original live objects. Anything that survives a JSON round-trip is
visible in the report; anything that does not, is not.

The report leads with *decisions* and *coverage gaps*, not collected-item
counts (the plan's acceptance criterion): the two most decision-relevant
sections are rendered before any evidence/concept count section.

Render failure is non-fatal to the data: ``write_report`` writes the JSON first,
and if Markdown rendering raises it marks the ``report`` phase ``partial``,
keeps the JSON on disk, and raises :class:`ReportRenderError` — a caller can
then resume render-only by reloading the JSON and calling ``render_run_markdown``
again.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from concepts.rendering import (
    render_concept_card_summary,
    render_decision_line,
    render_evidence_summary,
)
from experiments.fde_gym import FdeGymScenarioProposal
from models.concept import (
    ConceptCard,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    OutcomeState,
    PortfolioStage,
    SourceType,
)
from models.radar_payload import SourceCoverage
from radar_cycles.models import (
    Mode,
    PhaseName,
    PhaseStatus,
    RadarCycleRun,
)

__all__ = [
    "ReportRenderError",
    "Decision",
    "EvidenceSummary",
    "ConceptFlows",
    "EvidenceCounts",
    "CalibrationRecord",
    "CalibrationResult",
    "NextCycle",
    "RadarCycleReport",
    "render_run_json",
    "render_run_markdown",
    "write_report",
]


# ── Report-only sub-models ──

class Decision(BaseModel):
    """One portfolio decision: a concept moved to ``stage`` for ``reason``."""

    concept_id: str = Field(min_length=1, description="Concept the decision applies to")
    stage: PortfolioStage = Field(description="Stage the concept moved to")
    reason: str = Field(min_length=1, description="Why the concept moved")


class EvidenceSummary(BaseModel):
    """A compact evidence summary used for top support / top counterevidence."""

    evidence_id: str = Field(min_length=1, description="Evidence record ID")
    concept_id: str = Field(min_length=1, description="Concept this evidence backs")
    source_type: SourceType = Field(description="Where the evidence came from")
    role: EvidenceRole = Field(description="Problem / implementation / adoption / counterevidence")
    strength: EvidenceStrength = Field(description="How strong the source is as evidence")
    directness: Directness = Field(description="How directly the source speaks to the claim")
    independence_key: str = Field(
        default="",
        description="Groups reposts/citations of one upstream claim",
    )
    note: str = Field(default="", description="Human-curated note or quoted excerpt")


class ConceptFlows(BaseModel):
    """Concepts created, merged, advanced, or dropped during the cycle."""

    created: list[ConceptCard] = Field(
        default_factory=list, description="Concepts created this cycle"
    )
    merged: list[ConceptCard] = Field(
        default_factory=list, description="Concepts merged into another card this cycle"
    )
    advanced: list[ConceptCard] = Field(
        default_factory=list, description="Concepts that advanced stage this cycle"
    )
    dropped: list[ConceptCard] = Field(
        default_factory=list, description="Concepts dropped this cycle"
    )


class EvidenceCounts(BaseModel):
    """Collected-item counts across the cycle."""

    total: int = Field(default=0, ge=0, description="Total evidence records")
    support: int = Field(default=0, ge=0, description="Supporting evidence records")
    counterevidence: int = Field(default=0, ge=0, description="Counterevidence records")
    independence_keys: int = Field(default=0, ge=0, description="Distinct independence keys")


class CalibrationRecord(BaseModel):
    """One prediction reviewed during calibration, with its recorded outcome."""

    concept_id: str = Field(min_length=1, description="Concept the prediction was made on")
    prediction: str = Field(default="", description="The original prediction")
    outcome: OutcomeState | None = Field(default=None, description="Recorded outcome")
    lesson: str = Field(default="", description="Lesson learned from the outcome")


class CalibrationResult(BaseModel):
    """Calibration results for the cycle (monthly prediction review)."""

    due: bool = Field(default=False, description="Whether calibration was due this cycle")
    records: list[CalibrationRecord] = Field(
        default_factory=list, description="Predictions reviewed against outcomes"
    )
    notes: list[str] = Field(
        default_factory=list, description="Calibration notes"
    )


class NextCycle(BaseModel):
    """The next recommended cycle for the radar."""

    mode: Mode = Field(description="Recommended mode for the next cycle")
    reason: str = Field(default="", description="Why this mode is recommended")


# ── The report contract ──

class RadarCycleReport(BaseModel):
    """The canonical, JSON-first report payload for one radar cycle.

    Carries run metadata, a full phase-status snapshot, source coverage and its
    explicit gaps, concept flows, evidence counts, decisions, top
    support/counterevidence, an optional experiment proposal, calibration
    results, errors, and the next recommended cycle.
    """

    run: RadarCycleRun = Field(description="Run metadata (id, radar, mode, checkpoint)")
    phases: dict[PhaseName, PhaseStatus] = Field(
        default_factory=dict,
        description="Phase-status snapshot; filled from the run checkpoint when omitted",
    )
    source_coverage: list[SourceCoverage] = Field(
        default_factory=list, description="Per-source coverage status"
    )
    coverage_gaps: list[str] = Field(
        default_factory=list, description="Explicit coverage gaps discovered"
    )
    concepts: ConceptFlows = Field(
        default_factory=ConceptFlows, description="Concepts created/merged/advanced/dropped"
    )
    evidence_counts: EvidenceCounts = Field(
        default_factory=EvidenceCounts, description="Collected-item counts"
    )
    decisions: list[Decision] = Field(
        default_factory=list, description="Portfolio decisions made this cycle"
    )
    top_support: list[EvidenceSummary] = Field(
        default_factory=list, description="Strongest supporting evidence"
    )
    top_counterevidence: list[EvidenceSummary] = Field(
        default_factory=list, description="Strongest counterevidence"
    )
    experiment: FdeGymScenarioProposal | None = Field(
        default=None, description="The (at most one) falsifiable experiment proposal"
    )
    calibration: CalibrationResult = Field(
        default_factory=CalibrationResult, description="Calibration results"
    )
    errors: list[str] = Field(
        default_factory=list, description="Errors surfaced in the report"
    )
    next_recommended_cycle: NextCycle | None = Field(
        default=None, description="Next recommended cycle"
    )

    @model_validator(mode="after")
    def _fill_phases_from_run(self) -> "RadarCycleReport":
        if not self.phases:
            self.phases = {
                phase: self.run.checkpoint.status_of(phase) for phase in PhaseName
            }
        return self


# ── Rendering ──

class ReportRenderError(Exception):
    """Raised when Markdown rendering fails after the JSON report was written."""


def render_run_json(report: RadarCycleReport) -> str:
    """Serialize the report to its canonical JSON form."""
    return report.model_dump_json(indent=2)


def render_run_markdown(report: RadarCycleReport) -> str:
    """Render the report to Markdown, derived exclusively from its JSON form."""
    data = report.model_dump(mode="json")
    return _render_markdown(data)


def _render_markdown(data: dict) -> str:
    lines: list[str] = []

    run = data["run"]
    lines.append(f"# Radar Cycle Report: {run['id']}")
    lines.append("")
    lines.append(f"> radar: {run['radar']} · mode: {run['mode']} · created: {run['created_at']}")
    lines.append("")

    # Decisions lead, before any collected-item count.
    lines.append("## Decisions")
    lines.append("")
    decisions = data.get("decisions") or []
    if decisions:
        for decision in decisions:
            lines.append(f"- {render_decision_line(decision)}")
    else:
        lines.append("- _None recorded_")
    lines.append("")

    # Coverage gaps come second — a partial source run is visible immediately.
    lines.append("## Coverage gaps")
    lines.append("")
    gaps = data.get("coverage_gaps") or []
    if gaps:
        for gap in gaps:
            lines.append(f"- {gap}")
    else:
        lines.append("- _None recorded_")
    lines.append("")

    # Concept flows.
    lines.append("## Concepts")
    lines.append("")
    concepts = data.get("concepts") or {}
    for key, label in (
        ("created", "Created"),
        ("merged", "Merged"),
        ("advanced", "Advanced"),
        ("dropped", "Dropped"),
    ):
        cards = concepts.get(key) or []
        lines.append(f"### {label}")
        lines.append("")
        if cards:
            for card in cards:
                lines.append(f"- {render_concept_card_summary(card)}")
        else:
            lines.append("- _None_")
        lines.append("")

    # Collected-item counts.
    lines.append("## Evidence counts")
    lines.append("")
    counts = data.get("evidence_counts") or {}
    lines.append(f"- total: {counts.get('total', 0)}")
    lines.append(f"- support: {counts.get('support', 0)}")
    lines.append(f"- counterevidence: {counts.get('counterevidence', 0)}")
    lines.append(f"- independence keys: {counts.get('independence_keys', 0)}")
    lines.append("")

    # Source coverage.
    lines.append("## Source coverage")
    lines.append("")
    sources = data.get("source_coverage") or []
    if sources:
        for source in sources:
            note = source.get("note") or ""
            suffix = f" — {note}" if note else ""
            lines.append(f"- {source.get('source_type')}: {source.get('status')}{suffix}")
    else:
        lines.append("- _None recorded_")
    lines.append("")

    # Top support.
    lines.append("## Top support")
    lines.append("")
    top_support = data.get("top_support") or []
    if top_support:
        for item in top_support:
            lines.append(f"- {render_evidence_summary(item)}")
    else:
        lines.append("- _None_")
    lines.append("")

    # Top counterevidence.
    lines.append("## Top counterevidence")
    lines.append("")
    top_counterevidence = data.get("top_counterevidence") or []
    if top_counterevidence:
        for item in top_counterevidence:
            lines.append(f"- {render_evidence_summary(item)}")
    else:
        lines.append("- _None_")
    lines.append("")

    # Experiment.
    lines.append("## Experiment")
    lines.append("")
    experiment = data.get("experiment")
    if experiment:
        lines.append(f"- concept: {experiment.get('concept_id')}")
        lines.append(f"- scenario: {experiment.get('scenario_name')}")
        lines.append(f"- failure mode: {experiment.get('failure_mode')}")
        criteria = experiment.get("success_criteria") or []
        lines.append(f"- success criteria: {', '.join(criteria)}")
    else:
        lines.append("- _None_")
    lines.append("")

    # Calibration.
    lines.append("## Calibration")
    lines.append("")
    calibration = data.get("calibration") or {}
    lines.append(f"- due: {calibration.get('due', False)}")
    records = calibration.get("records") or []
    if records:
        for record in records:
            outcome = record.get("outcome")
            outcome_str = outcome if outcome is not None else "-"
            prediction = record.get("prediction") or "(no prediction)"
            lines.append(f"- {record.get('concept_id')}: {prediction} → {outcome_str}")
    else:
        lines.append("- _no records_")
    for note in calibration.get("notes") or []:
        lines.append(f"- note: {note}")
    lines.append("")

    # Errors.
    lines.append("## Errors")
    lines.append("")
    errors = data.get("errors") or []
    if errors:
        for error in errors:
            lines.append(f"- {error}")
    else:
        lines.append("- _None_")
    lines.append("")

    # Next recommended cycle.
    lines.append("## Next recommended cycle")
    lines.append("")
    next_cycle = data.get("next_recommended_cycle")
    if next_cycle:
        lines.append(f"- mode: {next_cycle.get('mode')}")
        reason = next_cycle.get("reason") or ""
        if reason:
            lines.append(f"- reason: {reason}")
    else:
        lines.append("- _None_")
    lines.append("")

    # Phase status.
    lines.append("## Phase status")
    lines.append("")
    phases = data.get("phases") or {}
    if phases:
        for phase, status in phases.items():
            lines.append(f"- {phase}: {status}")
    else:
        lines.append("- _None recorded_")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ── Writing ──

def write_report(
    report: RadarCycleReport,
    out_dir: str | Path = "output/radar_cycles",
) -> tuple[str, str]:
    """Write ``{run_id}.json`` and ``{run_id}.md`` under ``out_dir``.

    The JSON is the canonical, resumable artifact. Markdown is presentation
    only: if ``render_run_markdown`` raises, the JSON is still written (with the
    ``report`` phase marked ``partial``) and :class:`ReportRenderError` is
    raised so the caller can resume render-only by reloading the JSON and
    calling ``render_run_markdown`` again.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    run_id = report.run.id
    json_path = out / f"{run_id}.json"
    md_path = out / f"{run_id}.md"

    try:
        markdown = render_run_markdown(report)
    except Exception as exc:  # noqa: BLE001 - any render error must not lose the JSON
        report.phases[PhaseName.REPORT] = PhaseStatus.PARTIAL
        json_path.write_text(render_run_json(report), encoding="utf-8")
        raise ReportRenderError(
            f"markdown rendering failed for run {run_id!r}; JSON kept at "
            f"{json_path}, report phase marked partial: {exc}"
        ) from exc

    json_path.write_text(render_run_json(report), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return str(json_path), str(md_path)
