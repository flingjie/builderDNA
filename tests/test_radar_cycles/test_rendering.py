"""Tests for JSON-first report rendering (``radar_cycles/rendering.py``).

Covers the Task 13 requirements:

- a ``RadarCycleReport`` round-trips through its JSON form;
- Markdown is derived exclusively from the validated JSON model (changing a
  field changes the Markdown, and the renderer reads ``model_dump`` output);
- the Markdown leads with decisions and coverage gaps before any collected-item
  count section;
- a Markdown render failure keeps the JSON on disk and marks the ``report``
  phase ``partial`` so a caller can resume render-only.
"""
from __future__ import annotations

import json

import pytest

import radar_cycles.rendering as rendering
from experiments.fde_gym import FdeGymScenarioProposal
from models.concept import (
    ConceptCard,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    OutcomeState,
    PortfolioStage,
    SmallestExperiment,
    SourceType,
)
from models.radar_payload import SourceCoverage, SourceStatus
from radar_cycles.models import (
    Mode,
    PhaseCheckpoint,
    PhaseName,
    PhaseStatus,
    RadarCycleRun,
)
from radar_cycles.rendering import (
    CalibrationRecord,
    CalibrationResult,
    ConceptFlows,
    Decision,
    EvidenceCounts,
    EvidenceSummary,
    NextCycle,
    RadarCycleReport,
    ReportRenderError,
    render_run_json,
    render_run_markdown,
    write_report,
)


# ── Fixtures ──

def make_run(run_id: str = "run-1") -> RadarCycleRun:
    return RadarCycleRun(
        id=run_id,
        radar="agent-reliability",
        mode=Mode.FULL,
        checkpoint=PhaseCheckpoint(
            config_fingerprint="sha256:abc123",
            mode=Mode.FULL,
            phases={PhaseName.DECIDE: PhaseStatus.COMPLETED},
        ),
    )


def make_card(concept_id: str, stage: PortfolioStage) -> ConceptCard:
    smallest = None
    if stage == PortfolioStage.BUILD:
        smallest = SmallestExperiment(
            hypothesis="agents fail silently under load",
            target="agent operator",
            artifact="minimal harness",
            success_threshold="failure is observable",
            failure_threshold="failure is silent",
            stop_condition="10 runs or 1 hour",
        )
    return ConceptCard(
        id=concept_id,
        title=concept_id.replace("-", " ").title(),
        problem="a real, recurring problem",
        stage=stage,
        smallest_experiment=smallest,
    )


def make_experiment() -> FdeGymScenarioProposal:
    return FdeGymScenarioProposal(
        concept_id="concept-b",
        scenario_name="reliability-gym",
        observed_pain="a real, recurring problem",
        evidence_ids=["ev-1"],
        failure_mode="agent fails silently",
        environment="simulated tool loop",
        agent_goal="complete the task",
        hidden_constraints=["must not retry silently"],
        success_criteria=["failure is observable"],
        counterexample="naive agent retries forever",
        replay_reset_requirements="deterministic reset",
        smallest_prototype="minimal harness",
    )


@pytest.fixture
def report() -> RadarCycleReport:
    return RadarCycleReport(
        run=make_run(),
        source_coverage=[
            SourceCoverage(
                source_type=SourceType.X,
                status=SourceStatus.PARTIAL,
                note="thread replies unavailable",
            ),
            SourceCoverage(
                source_type=SourceType.GITHUB,
                status=SourceStatus.COMPLETE,
                note="repos and issues scanned",
            ),
        ],
        coverage_gaps=["X thread replies unavailable"],
        concepts=ConceptFlows(
            created=[make_card("concept-a", PortfolioStage.INBOX)],
            merged=[make_card("concept-d", PortfolioStage.WATCH)],
            advanced=[make_card("concept-b", PortfolioStage.BUILD)],
            dropped=[make_card("concept-c", PortfolioStage.DROP)],
        ),
        evidence_counts=EvidenceCounts(
            total=5,
            support=4,
            counterevidence=1,
            independence_keys=3,
        ),
        decisions=[
            Decision(
                concept_id="concept-b",
                stage=PortfolioStage.BUILD,
                reason="two independent evidence chains",
            ),
        ],
        top_support=[
            EvidenceSummary(
                evidence_id="ev-1",
                concept_id="concept-b",
                source_type=SourceType.GITHUB,
                role=EvidenceRole.IMPLEMENTATION,
                strength=EvidenceStrength.STRONG,
                directness=Directness.DIRECT,
                note="repo used in production",
            ),
        ],
        top_counterevidence=[
            EvidenceSummary(
                evidence_id="ev-2",
                concept_id="concept-b",
                source_type=SourceType.REDDIT,
                role=EvidenceRole.COUNTER,
                strength=EvidenceStrength.MODERATE,
                directness=Directness.INDIRECT,
                note="users report a workaround",
            ),
        ],
        experiment=make_experiment(),
        calibration=CalibrationResult(
            due=True,
            records=[
                CalibrationRecord(
                    concept_id="concept-x",
                    prediction="silent failures dominate",
                    outcome=OutcomeState.PARTIALLY_CONFIRMED,
                    lesson="domain narrower than predicted",
                ),
            ],
            notes=["quarterly calibration"],
        ),
        errors=["x discovery unavailable"],
        next_recommended_cycle=NextCycle(
            mode=Mode.WEEKLY,
            reason="one Build pending verification",
        ),
    )


# ── JSON contract ──

class TestJsonContract:
    def test_report_roundtrips_through_json(self, report):
        json_str = render_run_json(report)
        data = json.loads(json_str)
        assert data["run"]["id"] == "run-1"
        assert data["run"]["radar"] == "agent-reliability"
        assert data["phases"]["decide"] == "completed"
        assert data["coverage_gaps"] == ["X thread replies unavailable"]
        assert data["decisions"][0]["concept_id"] == "concept-b"

        reconstructed = RadarCycleReport.model_validate_json(json_str)
        assert reconstructed == report

    def test_empty_report_defaults(self):
        run = make_run()
        report = RadarCycleReport(run=run)
        assert report.phases["decide"] == "completed"
        assert report.concepts.created == []
        assert report.decisions == []
        assert report.experiment is None
        assert report.next_recommended_cycle is None


# ── Markdown derivation ──

class TestMarkdownDerivation:
    def test_markdown_changes_when_field_changes(self, report):
        before = render_run_markdown(report)
        report.decisions[0].reason = "entirely new reasoning"
        after = render_run_markdown(report)
        assert before != after
        assert "entirely new reasoning" in after

    def test_markdown_reads_model_dump_not_raw_input(self, report, monkeypatch):
        original = RadarCycleReport.model_dump

        def fake_dump(self, **kwargs):
            data = original(self, **kwargs)
            data["decisions"][0]["reason"] = "OVERRIDDEN VIA DUMP"
            return data

        monkeypatch.setattr(RadarCycleReport, "model_dump", fake_dump)
        md = render_run_markdown(report)
        # The renderer read the *dumped* value, not the live field value.
        assert "OVERRIDDEN VIA DUMP" in md
        assert "two independent evidence chains" not in md

    def test_markdown_stable_after_json_reconstruction(self, report):
        md = render_run_markdown(report)
        reconstructed = RadarCycleReport.model_validate_json(report.model_dump_json())
        assert render_run_markdown(reconstructed) == md


# ── Decisions-first ordering ──

class TestDecisionsFirst:
    def test_decisions_and_gaps_precede_counts(self, report):
        md = render_run_markdown(report)
        assert "## Decisions" in md
        assert "## Coverage gaps" in md
        assert "## Evidence counts" in md
        assert md.index("## Decisions") < md.index("## Evidence counts")
        assert md.index("## Coverage gaps") < md.index("## Evidence counts")
        assert md.index("## Decisions") < md.index("## Concepts")
        assert md.index("## Coverage gaps") < md.index("## Concepts")

    def test_decisions_and_gaps_still_first_when_empty(self):
        report = RadarCycleReport(run=make_run())
        md = render_run_markdown(report)
        assert md.index("## Decisions") < md.index("## Evidence counts")
        assert md.index("## Coverage gaps") < md.index("## Evidence counts")


# ── Render-failure fallback ──

class TestRenderFailureFallback:
    def test_render_failure_keeps_json_and_marks_partial(self, report, tmp_path, monkeypatch):
        def boom(report_):
            raise RuntimeError("markdown exploded")

        monkeypatch.setattr(rendering, "render_run_markdown", boom)

        with pytest.raises(ReportRenderError):
            write_report(report, out_dir=str(tmp_path))

        json_path = tmp_path / "run-1.json"
        md_path = tmp_path / "run-1.md"
        assert json_path.exists()
        assert not md_path.exists()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["phases"]["report"] == "partial"
        # the report object in memory also reflects the partial phase
        assert report.phases[PhaseName.REPORT] == PhaseStatus.PARTIAL

    def test_success_writes_both_files(self, report, tmp_path):
        json_path, md_path = write_report(report, out_dir=str(tmp_path))
        assert json_path.endswith("run-1.json")
        assert md_path.endswith("run-1.md")
        assert (tmp_path / "run-1.json").exists()
        assert (tmp_path / "run-1.md").exists()
        # the markdown is the same as a direct render
        assert (tmp_path / "run-1.md").read_text(encoding="utf-8") == render_run_markdown(
            report
        )
