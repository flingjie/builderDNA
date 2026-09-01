"""Tests for prediction/outcome recording (Task 6.1).

Covers the judgment-calibration loop:

- ``move ... build`` requires a prediction, expected evidence, and review date.
- ``review`` records one of the four ``OutcomeState`` values plus a lesson.
- The original prediction can never be rewritten by ``review``.
- Outcome history stays traceable (an immutable review is appended on every
  review, even though the card keeps the latest outcome).

These run through a locally-constructed Typer app and a ``tmp_path`` store, plus
direct unit tests of ``record_outcome``.
"""

import json

import pytest
import typer
from typer.testing import CliRunner

from cli.commands.concept import concept as concept_group, record_outcome
from concepts.store import ConceptStore
from models.concept import (
    ConceptCard,
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    OutcomeState,
    PortfolioStage,
    SmallestExperiment,
    SourceType,
)


def make_app() -> typer.Typer:
    app = typer.Typer()
    app.add_typer(concept_group, name="concept")
    return app


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def store(tmp_path):
    return ConceptStore(state_dir=tmp_path)


def invoke(app, runner, tmp_path, subcommand, *args, input=None):
    full = ["concept", subcommand, "--state-dir", str(tmp_path), *args]
    return runner.invoke(app, full, input=input)


def load(result):
    return json.loads(result.stdout)


EXPERIMENT = {
    "hypothesis": "agents will fail less",
    "target": "first-time agent CLI users",
    "artifact": "a 20-line prototype",
    "success_threshold": ">= 5 of 10 users succeed",
    "failure_threshold": "< 3 of 10 users succeed",
    "stop_condition": "stop after 10 users or 2 hours",
}


def seed_build_card(store: ConceptStore, prediction: str = "agents will fail 30% less") -> None:
    """Seed a card that has entered Build with a prediction."""
    store.upsert_concept(
        ConceptCard(
            id="agent-reliability",
            title="Agent Reliability",
            stage=PortfolioStage.BUILD,
            prediction=prediction,
            smallest_experiment=SmallestExperiment(**EXPERIMENT),
        )
    )


def build_ready_card(store: ConceptStore) -> None:
    """A card that satisfies the structural build gate."""
    store.upsert_concept(ConceptCard(id="agent-reliability", title="Agent Reliability", stage=PortfolioStage.VERIFY))
    store.add_evidence(ConceptEvidence(
        id="e1", concept_id="agent-reliability", source_type=SourceType.GITHUB,
        source_url="https://github.com/x/y", role=EvidenceRole.IMPLEMENTATION,
        directness=Directness.DIRECT, strength=EvidenceStrength.STRONG,
        independence_key="gh-a",
    ))
    store.add_evidence(ConceptEvidence(
        id="e2", concept_id="agent-reliability", source_type=SourceType.REDDIT,
        source_url="https://reddit.com/r/x", role=EvidenceRole.PROBLEM,
        directness=Directness.DIRECT, strength=EvidenceStrength.MODERATE,
        independence_key="reddit-b",
    ))


# ── move -> build requires the prediction fields ──


class TestBuildRequiresPrediction:
    def test_build_requires_all_three_prediction_fields(self, app, runner, tmp_path):
        build_ready_card(ConceptStore(state_dir=tmp_path))
        result = invoke(
            app, runner, tmp_path, "move", "agent-reliability", "build",
            "--reason", "r",
        )
        assert result.exit_code == 1
        error = load(result)["error"]
        assert "--prediction" in error
        assert "--expected-evidence" in error
        assert "--review-date" in error

    def test_build_records_prediction(self, app, runner, tmp_path):
        build_ready_card(ConceptStore(state_dir=tmp_path))
        result = invoke(
            app, runner, tmp_path, "move", "agent-reliability", "build",
            "--reason", "r",
            "--prediction", "agents will fail 30% less",
            "--expected-evidence", "10-user pilot",
            "--review-date", "2026-09-08T00:00:00Z",
            "--experiment", json.dumps(EXPERIMENT),
        )
        assert result.exit_code == 0, result.stdout
        payload = load(result)
        assert payload["data"]["concept"]["stage"] == "build"
        assert payload["data"]["concept"]["prediction"] == "agents will fail 30% less"


# ── review records outcome and preserves the prediction ──


class TestReviewPreservesPrediction:
    def test_review_records_outcome_and_lesson(self, app, runner, tmp_path):
        seed_build_card(ConceptStore(state_dir=tmp_path))
        result = invoke(
            app, runner, tmp_path, "review", "agent-reliability",
            "--outcome", "confirmed", "--lesson", "the failure was real and fixable",
        )
        assert result.exit_code == 0, result.stdout
        payload = load(result)
        assert payload["action"] == "reviewed"
        assert payload["data"]["concept"]["outcome"] == "confirmed"
        assert payload["data"]["concept"]["lesson"] == "the failure was real and fixable"
        assert payload["data"]["prediction_preserved"] is True
        assert payload["data"]["original_prediction"] == "agents will fail 30% less"

    def test_review_cannot_rewrite_prediction(self, app, runner, tmp_path):
        seed_build_card(ConceptStore(state_dir=tmp_path), prediction="ORIGINAL PREDICTION")
        invoke(
            app, runner, tmp_path, "review", "agent-reliability",
            "--outcome", "rejected", "--lesson", "did not hold",
        )
        card = ConceptStore(state_dir=tmp_path).get_concept("agent-reliability")
        assert card.prediction == "ORIGINAL PREDICTION"
        assert card.outcome == OutcomeState.REJECTED

    def test_review_requires_prior_prediction(self, app, runner, tmp_path):
        # A card that never entered Build has no prediction -> review is refused.
        ConceptStore(state_dir=tmp_path).upsert_concept(
            ConceptCard(id="c1", title="C1", stage=PortfolioStage.WATCH)
        )
        result = invoke(app, runner, tmp_path, "review", "c1", "--outcome", "confirmed", "--lesson", "l")
        assert result.exit_code == 1
        assert "no recorded prediction" in load(result)["error"]

    def test_review_invalid_outcome_rejected(self, app, runner, tmp_path):
        seed_build_card(ConceptStore(state_dir=tmp_path))
        result = invoke(app, runner, tmp_path, "review", "agent-reliability", "--outcome", "maybe", "--lesson", "l")
        assert result.exit_code == 1
        assert "invalid outcome" in load(result)["error"]

    def test_review_requires_lesson(self, app, runner, tmp_path):
        seed_build_card(ConceptStore(state_dir=tmp_path))
        result = invoke(app, runner, tmp_path, "review", "agent-reliability", "--outcome", "confirmed", "--lesson", "")
        assert result.exit_code == 1
        assert "requires --lesson" in load(result)["error"]

    def test_outcome_history_stays_traceable(self, app, runner, tmp_path):
        seed_build_card(ConceptStore(state_dir=tmp_path))
        first = invoke(app, runner, tmp_path, "review", "agent-reliability", "--outcome", "partially_confirmed", "--lesson", "first lesson")
        second = invoke(app, runner, tmp_path, "review", "agent-reliability", "--outcome", "confirmed", "--lesson", "second lesson")
        assert first.exit_code == 0
        assert second.exit_code == 0

        s = ConceptStore(state_dir=tmp_path)
        reviews = s.list_reviews("agent-reliability")
        # two immutable review records capture the full history
        reasons = " ".join(r.reason for r in reviews)
        assert "first lesson" in reasons
        assert "second lesson" in reasons
        # the card reflects the latest outcome, and the prediction is untouched
        card = s.get_concept("agent-reliability")
        assert card.outcome == OutcomeState.CONFIRMED
        assert card.prediction == "agents will fail 30% less"


# ── direct unit tests of record_outcome ──


class TestRecordOutcomeDirect:
    def test_preserves_prediction_across_multiple_reviews(self, store):
        seed_build_card(store, prediction="PRED-A")
        record_outcome(store, "agent-reliability", "rejected", "did not hold")
        record_outcome(store, "agent-reliability", "confirmed", "re-tested and held")
        card = store.get_concept("agent-reliability")
        assert card.prediction == "PRED-A"
        assert card.outcome == OutcomeState.CONFIRMED
        assert card.lesson == "re-tested and held"

    def test_outcome_is_one_of_four_states(self):
        assert [o.value for o in OutcomeState] == [
            "confirmed", "partially_confirmed", "rejected", "inconclusive",
        ]
