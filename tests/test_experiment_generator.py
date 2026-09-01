"""Tests for experiments/models.py and experiments/generator.py.

Encodes the Task 5.1 acceptance criteria:

- Generation fails closed when a threshold, budget, or stop condition is absent.
- Output is falsifiable: testable hypothesis, observable and distinct
  success/failure thresholds, and a bounded stop condition.
- ``Experiment`` composes (does not duplicate) ``SmallestExperiment``.
"""
import pytest
from pydantic import ValidationError

from experiments.generator import ExperimentGenerationError, generate_experiment
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


def make_core(**overrides) -> SmallestExperiment:
    fields = dict(CORE_FIELDS)
    fields.update(overrides)
    return SmallestExperiment(**fields)


def make_card(core: SmallestExperiment | None = None) -> ConceptCard:
    return ConceptCard(
        id="agent-reliability",
        title="Agent Reliability",
        smallest_experiment=core,
    )


def make_card_with_blank(field: str) -> ConceptCard:
    """A card whose smallest-experiment core has one blank field.

    Bypasses model validation (``model_construct``) to simulate a malformed or
    leniently-loaded core, so the generator — not the model — is what fails closed.
    """
    core = make_core()
    setattr(core, field, "")
    return ConceptCard.model_construct(
        id="agent-reliability",
        title="Agent Reliability",
        smallest_experiment=core,
    )


def make_evidence(**overrides) -> ConceptEvidence:
    fields = dict(
        id="ev1",
        concept_id="agent-reliability",
        source_type=SourceType.REDDIT,
        source_url="https://reddit.com/r/agentops",
        role=EvidenceRole.PROBLEM,
        directness=Directness.DIRECT,
        strength=EvidenceStrength.MODERATE,
        independence_key="reddit.com/r/agentops",
    )
    fields.update(overrides)
    return ConceptEvidence(**fields)


# ── Fail closed ──

class TestGenerateExperimentFailsClosed:
    def test_no_smallest_experiment_raises(self):
        # Thresholds and stop condition are absent together (no core at all).
        card = make_card(core=None)
        with pytest.raises(ExperimentGenerationError) as exc:
            generate_experiment(card, [], budget="4 hours")
        message = str(exc.value).lower()
        assert "threshold" in message
        assert "stop condition" in message

    def test_missing_budget_raises(self):
        card = make_card(make_core())
        with pytest.raises(ExperimentGenerationError, match="budget"):
            generate_experiment(card, [])

    def test_blank_budget_raises(self):
        card = make_card(make_core())
        with pytest.raises(ExperimentGenerationError, match="budget"):
            generate_experiment(card, [], budget="   ")

    def test_missing_stop_condition_raises(self):
        card = make_card_with_blank("stop_condition")
        with pytest.raises(ExperimentGenerationError, match="stop_condition"):
            generate_experiment(card, [], budget="4 hours")

    def test_missing_success_threshold_raises(self):
        card = make_card_with_blank("success_threshold")
        with pytest.raises(ExperimentGenerationError, match="success_threshold"):
            generate_experiment(card, [], budget="4 hours")

    def test_missing_failure_threshold_raises(self):
        card = make_card_with_blank("failure_threshold")
        with pytest.raises(ExperimentGenerationError, match="failure_threshold"):
            generate_experiment(card, [], budget="4 hours")

    def test_missing_artifact_raises(self):
        card = make_card_with_blank("artifact")
        with pytest.raises(ExperimentGenerationError, match="artifact"):
            generate_experiment(card, [], budget="4 hours")

    def test_identical_thresholds_raise(self):
        card = make_card(
            make_core(success_threshold="any reduction", failure_threshold="any reduction")
        )
        with pytest.raises(ExperimentGenerationError, match="distinct"):
            generate_experiment(card, [], budget="4 hours")


# ── Falsifiable output ──

class TestGenerateExperimentFalsifiable:
    def _generate(self, **kwargs) -> Experiment:
        return generate_experiment(
            make_card(make_core()), [make_evidence()], budget="4 hours", **kwargs
        )

    def test_produces_complete_experiment(self):
        exp = self._generate()
        assert exp.concept_id == "agent-reliability"
        assert exp.core.hypothesis == CORE_FIELDS["hypothesis"]
        assert exp.core.target == CORE_FIELDS["target"]
        assert exp.core.artifact == CORE_FIELDS["artifact"]
        assert exp.core.success_threshold == CORE_FIELDS["success_threshold"]
        assert exp.core.failure_threshold == CORE_FIELDS["failure_threshold"]
        assert exp.core.stop_condition == CORE_FIELDS["stop_condition"]
        assert exp.budget == "4 hours"
        assert exp.evidence_to_collect
        assert exp.confirmed_followup

    def test_hypothesis_is_testable(self):
        exp = self._generate()
        assert exp.core.hypothesis
        assert exp.core.hypothesis.strip().lower() not in {"tbd", "todo", "placeholder"}
        # A testable hypothesis names the target it tests.
        assert exp.core.target.lower() in exp.core.hypothesis.lower()

    def test_thresholds_are_observable_and_distinct(self):
        exp = self._generate()
        assert exp.core.success_threshold
        assert exp.core.failure_threshold
        assert exp.core.success_threshold != exp.core.failure_threshold

    def test_stop_condition_is_bounded(self):
        exp = self._generate()
        sc = exp.core.stop_condition.lower()
        assert sc
        assert any(token in sc for token in ("stop", "until", "whichever", "or"))

    def test_artifact_is_a_minimal_increment(self):
        exp = self._generate()
        assert isinstance(exp.core.artifact, str)
        assert exp.core.artifact.strip()

    def test_derived_evidence_is_grounded_in_thresholds(self):
        exp = generate_experiment(make_card(make_core()), [], budget="4 hours")
        joined = " ".join(exp.evidence_to_collect).lower()
        assert exp.core.target.lower() in joined
        assert exp.core.success_threshold.lower() in joined

    def test_explicit_overrides_are_respected(self):
        exp = generate_experiment(
            make_card(make_core()),
            [make_evidence()],
            budget="4 hours",
            evidence_to_collect=["per-operator failure log"],
            confirmed_followup="ship the wrapper behind a feature flag",
        )
        assert exp.evidence_to_collect == ["per-operator failure log"]
        assert exp.confirmed_followup == "ship the wrapper behind a feature flag"


# ── Experiment model: composition + invariants ──

class TestExperimentModel:
    def _experiment(self, **overrides) -> Experiment:
        fields = dict(
            concept_id="agent-reliability",
            core=make_core(),
            evidence_to_collect=["per-operator uncaught-failure counts"],
            budget="4 hours",
            confirmed_followup="advance to a larger sample",
        )
        fields.update(overrides)
        return Experiment(**fields)

    def test_composes_smallest_experiment_without_duplication(self):
        # Composition: the core fields live on SmallestExperiment, not Experiment.
        assert "core" in Experiment.model_fields
        for field in (
            "hypothesis",
            "target",
            "artifact",
            "success_threshold",
            "failure_threshold",
            "stop_condition",
        ):
            assert field not in Experiment.model_fields

    def test_round_trips(self):
        core = make_core()
        exp = self._experiment(core=core)
        assert exp.core is core
        assert exp.concept_id == "agent-reliability"
        assert exp.budget == "4 hours"

    def test_blank_budget_rejected(self):
        with pytest.raises(ValidationError):
            self._experiment(budget="   ")

    def test_blank_confirmed_followup_rejected(self):
        with pytest.raises(ValidationError):
            self._experiment(confirmed_followup="")

    def test_empty_evidence_list_rejected(self):
        with pytest.raises(ValidationError):
            self._experiment(evidence_to_collect=[])

    def test_blank_evidence_item_rejected(self):
        with pytest.raises(ValidationError):
            self._experiment(evidence_to_collect=["   "])

    def test_blank_artifact_rejected(self):
        with pytest.raises(ValidationError, match="artifact"):
            self._experiment(core=make_core(artifact=""))

    def test_identical_thresholds_rejected(self):
        with pytest.raises(ValidationError, match="distinct"):
            self._experiment(
                core=make_core(success_threshold="same", failure_threshold="same")
            )

    def test_schema_nests_smallest_experiment(self):
        schema = Experiment.model_json_schema()
        assert schema["properties"]["core"]["$ref"] == "#/$defs/SmallestExperiment"
        assert "SmallestExperiment" in schema["$defs"]
