"""Tests for experiments/fde_gym.py — the FDE-Gym scenario proposal export.

Encodes the Task 5.2 acceptance criteria:

- The export links evidence IDs rather than copying unverifiable prose.
- All required fields are present and non-empty in the output.
- The output can be serialized to JSON and reconstructed.
- The export composes (does not duplicate) the ``Experiment`` from Task 5.1 and
  fails closed when a required semantic field cannot be resolved.
"""
import pytest

from experiments.fde_gym import (
    FdeGymScenarioProposal,
    ScenarioExportError,
    export_fde_gym_scenario,
)
from experiments.generator import generate_experiment
from experiments.models import Experiment
from models.concept import (
    ConceptCard,
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    SmallestExperiment,
    SourceType,
)


CORE_FIELDS = dict(
    hypothesis=(
        "operators of a production agent pipeline see fewer uncaught failures "
        "with a one-line watchdog wrapper"
    ),
    target="operators of a production agent pipeline",
    artifact="a 20-line watchdog wrapper script",
    success_threshold=">= 5 of 10 operators report fewer uncaught failures over 2 days",
    failure_threshold="< 3 of 10 operators report any reduction in failures",
    stop_condition="stop after 10 operators or 2 days, whichever comes first",
)

# Prose that lives only on evidence records; it must never leak into the export.
UNVERIFIABLE_SENTINEL = "TRANSCRIPT: the agent silently skipped the cleanup step at 03:12 UTC"

REQUIRED_FIELDS = [
    "scenario_name",
    "observed_pain",
    "evidence_ids",
    "failure_mode",
    "environment",
    "agent_goal",
    "hidden_constraints",
    "success_criteria",
    "counterexample",
    "replay_reset_requirements",
    "smallest_prototype",
]

SCENARIO_KWARGS = dict(
    failure_mode="the agent silently skips a post-run cleanup step and loses state",
    environment=(
        "a sandboxed shell with a persistent working directory, an agent process, "
        "and a trailing cleanup step the harness can observe"
    ),
    agent_goal="complete the assigned task and exit cleanly",
    hidden_constraints=[
        "the working directory must be empty of intermediate files on exit",
        "the agent must not leak credentials into the transcript",
    ],
    counterexample=(
        "a naive agent that reports success while intermediate files remain, "
        "reproducing the skipped-cleanup failure"
    ),
    replay_reset_requirements=(
        "reset the working directory and transcript to a fixed seed state before "
        "each run; the environment is deterministic given the seed"
    ),
)


def make_core(**overrides) -> SmallestExperiment:
    fields = dict(CORE_FIELDS)
    fields.update(overrides)
    return SmallestExperiment(**fields)


def make_evidence(id: str = "ev1", **overrides) -> ConceptEvidence:
    fields = dict(
        id=id,
        concept_id="agent-reliability",
        source_type=SourceType.REDDIT,
        source_url=f"https://reddit.com/r/agentops/{id}",
        role=EvidenceRole.PROBLEM,
        directness=Directness.DIRECT,
        strength=EvidenceStrength.MODERATE,
        independence_key=f"reddit.com/r/agentops/{id}",
        note=UNVERIFIABLE_SENTINEL,
    )
    fields.update(overrides)
    return ConceptEvidence(**fields)


def make_card(**overrides) -> ConceptCard:
    fields = dict(
        id="agent-reliability",
        title="Agent Reliability",
        problem="operators of production agent pipelines lose time to uncaught failures",
        evidence_ids=["ev1", "ev2"],
        smallest_experiment=make_core(),
    )
    fields.update(overrides)
    return ConceptCard(**fields)


def make_experiment() -> Experiment:
    card = make_card()
    return generate_experiment(
        card,
        [make_evidence("ev1"), make_evidence("ev2")],
        budget="4 hours",
    )


def export(**overrides):
    card = make_card()
    evidence = [make_evidence("ev1"), make_evidence("ev2")]
    kwargs = dict(SCENARIO_KWARGS)
    kwargs.update(overrides)
    return export_fde_gym_scenario(card, evidence, make_experiment(), **kwargs)


# ── Links evidence rather than copying prose ──

class TestLinksEvidenceNotProse:
    def test_exports_evidence_ids_from_card(self):
        proposal = export()
        assert proposal.evidence_ids == ["ev1", "ev2"]

    def test_concept_id_is_linked(self):
        proposal = export()
        assert proposal.concept_id == "agent-reliability"

    def test_evidence_prose_never_leaks_into_export(self):
        proposal = export()
        serialized = proposal.model_dump_json()
        assert UNVERIFIABLE_SENTINEL not in serialized
        # The observed pain is the card's own problem statement, not evidence text.
        assert proposal.observed_pain == (
            "operators of production agent pipelines lose time to uncaught failures"
        )

    def test_blank_evidence_items_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FdeGymScenarioProposal(
                **{
                    "concept_id": "c",
                    "scenario_name": "s",
                    "observed_pain": "p",
                    "evidence_ids": ["   "],
                    "failure_mode": "f",
                    "environment": "e",
                    "agent_goal": "g",
                    "hidden_constraints": ["h"],
                    "success_criteria": ["s"],
                    "counterexample": "x",
                    "replay_reset_requirements": "r",
                    "smallest_prototype": "p",
                }
            )


# ── All required fields present and non-empty ──

class TestRequiredFieldsPresentAndNonEmpty:
    def test_all_required_fields_are_non_empty(self):
        proposal = export()
        for field in REQUIRED_FIELDS:
            value = getattr(proposal, field)
            if isinstance(value, list):
                assert value, f"{field} is an empty list"
                assert all(
                    item and item.strip() for item in value
                ), f"{field} contains a blank item"
            else:
                assert value and value.strip(), f"{field} is blank"

    def test_required_field_names_are_declared(self):
        assert set(REQUIRED_FIELDS) <= set(FdeGymScenarioProposal.model_fields)

    def test_schema_version_is_declared(self):
        assert FdeGymScenarioProposal.model_fields["schema_version"].default == "1.0"
        assert export().schema_version == "1.0"


# ── Serializes to JSON and reconstructs ──

class TestJsonRoundTrip:
    def test_serializes_and_reconstructs(self):
        proposal = export()
        reconstructed = FdeGymScenarioProposal.model_validate_json(
            proposal.model_dump_json()
        )
        assert reconstructed == proposal
        assert reconstructed.evidence_ids == proposal.evidence_ids

    def test_to_json_is_valid_json_equivalent(self):
        import json

        proposal = export()
        assert json.loads(proposal.to_json()) == json.loads(
            proposal.model_dump_json()
        )

    def test_json_contains_evidence_ids_not_prose(self):
        proposal = export()
        payload = proposal.model_dump()
        assert payload["evidence_ids"] == ["ev1", "ev2"]
        assert all(
            UNVERIFIABLE_SENTINEL not in str(value)
            for value in payload.values()
        )


# ── Composes the Experiment from Task 5.1 ──

class TestComposesExperiment:
    def test_smallest_prototype_comes_from_experiment_core(self):
        experiment = make_experiment()
        proposal = export()
        assert proposal.smallest_prototype == experiment.core.artifact

    def test_success_criteria_comes_from_experiment_core(self):
        experiment = make_experiment()
        proposal = export()
        assert proposal.success_criteria == [experiment.core.success_threshold]

    def test_falls_back_to_card_smallest_experiment_without_experiment(self):
        card = make_card()
        proposal = export_fde_gym_scenario(
            card,
            [make_evidence("ev1"), make_evidence("ev2")],
            None,
            **SCENARIO_KWARGS,
        )
        assert proposal.smallest_prototype == card.smallest_experiment.artifact
        assert proposal.success_criteria == [card.smallest_experiment.success_threshold]

    def test_explicit_overrides_win_over_experiment(self):
        proposal = export(
            smallest_prototype="a custom 5-line harness",
            success_criteria=["agent exits with no intermediate files"],
        )
        assert proposal.smallest_prototype == "a custom 5-line harness"
        assert proposal.success_criteria == ["agent exits with no intermediate files"]

    def test_does_not_duplicate_experiment_core_fields(self):
        # The proposal flattens the reusable values; it does not re-declare the
        # Experiment's core fields as its own.
        for field in ("core", "hypothesis", "target", "artifact", "budget"):
            assert field not in FdeGymScenarioProposal.model_fields


# ── Fails closed ──

class TestFailsClosed:
    def test_missing_evidence_ids_raises(self):
        card = make_card(evidence_ids=[])
        with pytest.raises(ScenarioExportError, match="evidence"):
            export_fde_gym_scenario(
                card,
                None,
                None,
                smallest_prototype="p",
                success_criteria=["s"],
                **SCENARIO_KWARGS,
            )

    def test_blank_problem_raises(self):
        card = make_card(problem="   ")
        with pytest.raises(ScenarioExportError, match="observed pain"):
            export_fde_gym_scenario(
                card,
                None,
                None,
                smallest_prototype="p",
                success_criteria=["s"],
                **SCENARIO_KWARGS,
            )

    def test_dangling_evidence_id_raises(self):
        card = make_card(evidence_ids=["ev1", "ev-missing"])
        with pytest.raises(ScenarioExportError, match="ev-missing"):
            export_fde_gym_scenario(
                card,
                [make_evidence("ev1")],
                None,
                smallest_prototype="p",
                success_criteria=["s"],
                **SCENARIO_KWARGS,
            )

    def test_missing_failure_mode_raises(self):
        kwargs = dict(SCENARIO_KWARGS)
        kwargs.pop("failure_mode")
        with pytest.raises(ScenarioExportError, match="failure_mode"):
            export_fde_gym_scenario(
                make_card(),
                None,
                None,
                smallest_prototype="p",
                success_criteria=["s"],
                **kwargs,
            )

    def test_missing_hidden_constraints_raises(self):
        kwargs = dict(SCENARIO_KWARGS)
        kwargs.pop("hidden_constraints")
        with pytest.raises(ScenarioExportError, match="hidden_constraints"):
            export_fde_gym_scenario(
                make_card(),
                None,
                None,
                smallest_prototype="p",
                success_criteria=["s"],
                **kwargs,
            )

    def test_no_experiment_and_no_prototype_raises(self):
        card = make_card(smallest_experiment=None)
        with pytest.raises(ScenarioExportError, match="smallest prototype"):
            export_fde_gym_scenario(
                card,
                [make_evidence("ev1"), make_evidence("ev2")],
                None,
                success_criteria=["s"],
                **SCENARIO_KWARGS,
            )

    def test_blank_proposal_fields_rejected_by_model(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FdeGymScenarioProposal(
                concept_id="c",
                scenario_name="   ",
                observed_pain="p",
                evidence_ids=["e"],
                failure_mode="f",
                environment="e",
                agent_goal="g",
                hidden_constraints=["h"],
                success_criteria=["s"],
                counterexample="x",
                replay_reset_requirements="r",
                smallest_prototype="p",
            )
