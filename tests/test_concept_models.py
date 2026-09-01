"""Tests for the concept radar domain models (models/concept.py, models/radar_payload.py).

Covers the hard requirements:
- Score components are validated to [0, 3].
- The priority total is recomputed, never trusted from caller input.
- Timestamps must be timezone-aware UTC.
- A Build-stage card requires a bounded, falsifiable smallest experiment.
- Invalid enums fail with actionable validation errors.
- Evidence and review records are immutable (frozen).
- JSON schema generation succeeds for every model.
"""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError

from models.concept import (
    ComponentScores,
    ConceptCard,
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    MaturityStage,
    OutcomeState,
    PortfolioStage,
    RadarReview,
    SmallestExperiment,
    SourceType,
    UtcDatetime,
)
from models.radar_payload import (
    RadarRunPayload,
    SourceCoverage,
    SourceStatus,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_experiment(**overrides) -> SmallestExperiment:
    fields = dict(
        hypothesis="Users will complete the task unaided",
        target="first-time users of an agent CLI",
        artifact="a 20-line prototype script",
        success_threshold=">= 5 of 10 users complete the task in under 2 minutes",
        failure_threshold="< 3 of 10 users complete the task",
        stop_condition="stop after 10 users or 2 hours, whichever first",
    )
    fields.update(overrides)
    return SmallestExperiment(**fields)


# ── Component scores ──

class TestComponentScores:
    def test_defaults_to_zero(self):
        s = ComponentScores()
        assert s.problem == s.evidence == s.reach == 0
        assert s.user_alignment == s.hype == s.competition == 0
        assert s.total == 0

    def test_valid_range_accepted(self):
        s = ComponentScores(problem=3, evidence=0, reach=3, user_alignment=0, hype=3, competition=0)
        assert s.problem == 3
        assert s.hype == 3

    @pytest.mark.parametrize("field", ["problem", "evidence", "reach", "user_alignment", "hype", "competition"])
    def test_upper_bound_rejected(self, field):
        with pytest.raises(ValidationError) as exc:
            ComponentScores(**{field: 4})
        assert exc.value.errors()[0]["type"] == "less_than_equal"
        assert exc.value.errors()[0]["loc"] == (field,)

    @pytest.mark.parametrize("field", ["problem", "evidence", "reach", "user_alignment", "hype", "competition"])
    def test_lower_bound_rejected(self, field):
        with pytest.raises(ValidationError) as exc:
            ComponentScores(**{field: -1})
        assert exc.value.errors()[0]["type"] == "greater_than_equal"
        assert exc.value.errors()[0]["loc"] == (field,)

    def test_total_is_recomputed_from_components(self):
        s = ComponentScores(problem=3, evidence=2, reach=1, user_alignment=2, hype=1, competition=1)
        expected = 2 * 3 + 2 * 2 + 1 + 2 - 2 * 1 - 1
        assert s.total == expected == 10

    def test_total_ignores_caller_supplied_value(self):
        # Even when a caller passes total, it is overwritten by the recomputed value.
        s = ComponentScores(problem=3, evidence=3, reach=3, user_alignment=3, hype=0, competition=0, total=999)
        assert s.total == 2 * 3 + 2 * 3 + 3 + 3 - 2 * 0 - 0 == 18

    def test_total_in_schema_and_fields(self):
        assert "total" in ComponentScores.model_fields
        schema = ComponentScores.model_json_schema()
        assert "total" in schema["properties"]
        assert schema["properties"]["problem"]["maximum"] == 3
        assert schema["properties"]["problem"]["minimum"] == 0


# ── Smallest experiment ──

class TestSmallestExperiment:
    def test_valid(self):
        e = make_experiment()
        assert e.hypothesis
        assert e.stop_condition

    @pytest.mark.parametrize("field", ["hypothesis", "target", "success_threshold", "failure_threshold", "stop_condition"])
    def test_required_fields_reject_empty(self, field):
        with pytest.raises(ValidationError):
            make_experiment(**{field: ""})

    def test_artifact_optional(self):
        e = make_experiment(artifact="")
        assert e.artifact == ""


# ── Concept card ──

class TestConceptCard:
    def test_minimal_defaults(self):
        c = ConceptCard(id="agent-reliability", title="Agent Reliability")
        assert c.aliases == []
        assert c.evidence_ids == []
        assert c.maturity == MaturityStage.SIGNAL
        assert c.stage == PortfolioStage.INBOX
        assert c.component_scores.total == 0
        assert c.smallest_experiment is None
        assert c.outcome is None
        assert c.prediction == ""
        assert c.created_at.tzinfo is not None

    def test_full_creation_round_trips(self):
        c = ConceptCard(
            id="agent-reliability",
            title="Agent Reliability",
            aliases=["hallucination", "agent trust"],
            problem="Agents fail unpredictably in production",
            why_now="More teams ship agents to production",
            evidence_ids=["ev1", "ev2"],
            maturity=MaturityStage.VERIFIED,
            stage=PortfolioStage.BUILD,
            component_scores=ComponentScores(problem=3, evidence=3, reach=2),
            smallest_experiment=make_experiment(),
            prediction="A watchdog will cut uncaught failures by half",
            outcome=None,
            lesson="",
        )
        assert c.aliases == ["hallucination", "agent trust"]
        assert c.evidence_ids == ["ev1", "ev2"]
        assert c.stage == PortfolioStage.BUILD
        assert c.smallest_experiment.hypothesis

    def test_build_without_smallest_experiment_rejected(self):
        with pytest.raises(ValidationError, match="smallest experiment"):
            ConceptCard(id="x", title="X", stage=PortfolioStage.BUILD)

    def test_build_without_smallest_experiment_rejected_string_stage(self):
        with pytest.raises(ValidationError, match="smallest experiment"):
            ConceptCard(id="x", title="X", stage="build")

    def test_build_with_smallest_experiment_accepted(self):
        c = ConceptCard(id="x", title="X", stage=PortfolioStage.BUILD, smallest_experiment=make_experiment())
        assert c.stage == PortfolioStage.BUILD

    @pytest.mark.parametrize("stage", [PortfolioStage.INBOX, PortfolioStage.WATCH, PortfolioStage.VERIFY, PortfolioStage.DROP])
    def test_non_build_stages_do_not_require_experiment(self, stage):
        c = ConceptCard(id="x", title="X", stage=stage)
        assert c.smallest_experiment is None

    def test_invalid_stage_rejected(self):
        with pytest.raises(ValidationError):
            ConceptCard(id="x", title="X", stage="shipping")

    def test_invalid_maturity_rejected(self):
        with pytest.raises(ValidationError):
            ConceptCard(id="x", title="X", maturity="pretty-sure")

    def test_empty_id_rejected(self):
        with pytest.raises(ValidationError):
            ConceptCard(id="", title="X")

    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            ConceptCard(id="x", title="")

    def test_invalid_outcome_rejected(self):
        with pytest.raises(ValidationError):
            ConceptCard(id="x", title="X", outcome="maybe")

    def test_naive_created_at_rejected(self):
        with pytest.raises(ValidationError, match="timezone-aware"):
            ConceptCard(id="x", title="X", created_at=datetime(2026, 9, 1, 12, 0, 0))

    def test_non_utc_created_at_rejected(self):
        with pytest.raises(ValidationError, match="UTC"):
            ConceptCard(
                id="x",
                title="X",
                created_at=datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=8))),
            )

    def test_utc_created_at_accepted(self):
        c = ConceptCard(id="x", title="X", created_at=utc_now())
        assert c.created_at.utcoffset() == timedelta(0)

    def test_default_timestamps_are_utc(self):
        c = ConceptCard(id="x", title="X")
        assert c.created_at.tzinfo is timezone.utc or c.created_at.utcoffset() == timedelta(0)
        assert c.updated_at.utcoffset() == timedelta(0)


# ── Evidence ──

class TestConceptEvidence:
    def _valid(self, **overrides) -> ConceptEvidence:
        fields = dict(
            id="ev1",
            concept_id="agent-reliability",
            source_type=SourceType.GITHUB,
            source_url="https://github.com/example/repo",
            role=EvidenceRole.IMPLEMENTATION,
            directness=Directness.DIRECT,
            strength=EvidenceStrength.STRONG,
            independence_key="github.com/example/repo",
        )
        fields.update(overrides)
        return ConceptEvidence(**fields)

    def test_valid_creation(self):
        e = self._valid()
        assert e.role == EvidenceRole.IMPLEMENTATION
        assert e.captured_at.utcoffset() == timedelta(0)
        assert e.supersedes is None

    def test_supersedes_append_only(self):
        e = self._valid(supersedes="ev0")
        assert e.supersedes == "ev0"

    def test_is_immutable(self):
        e = self._valid()
        with pytest.raises(ValidationError, match="frozen"):
            e.strength = EvidenceStrength.WEAK

    def test_requires_independence_key(self):
        with pytest.raises(ValidationError):
            self._valid(independence_key="")

    def test_requires_non_empty_id_and_concept(self):
        with pytest.raises(ValidationError):
            self._valid(id="")
        with pytest.raises(ValidationError):
            self._valid(concept_id="")

    @pytest.mark.parametrize(
        "field,bad",
        [
            ("source_type", "newsletter"),
            ("role", "vibes"),
            ("directness", "sideways"),
            ("strength", "mega"),
        ],
    )
    def test_invalid_enum_rejected(self, field, bad):
        with pytest.raises(ValidationError) as exc:
            self._valid(**{field: bad})
        assert exc.value.errors()[0]["type"] == "enum"

    def test_naive_captured_at_rejected(self):
        with pytest.raises(ValidationError, match="timezone-aware"):
            self._valid(captured_at=datetime(2026, 9, 1, 12, 0, 0))

    def test_non_utc_captured_at_rejected(self):
        with pytest.raises(ValidationError, match="UTC"):
            self._valid(
                captured_at=datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
            )


# ── Radar review ──

class TestRadarReview:
    def _valid(self, **overrides) -> RadarReview:
        fields = dict(
            id="rev1",
            concept_id="agent-reliability",
            from_stage=PortfolioStage.VERIFY,
            to_stage=PortfolioStage.BUILD,
            reason="Two independent chains and reviewed counterevidence",
            expected_evidence="At least one production failure observed",
            review_date=utc_now(),
        )
        fields.update(overrides)
        return RadarReview(**fields)

    def test_valid_creation(self):
        r = self._valid()
        assert r.to_stage == PortfolioStage.BUILD
        assert r.recorded_at.utcoffset() == timedelta(0)

    def test_from_stage_optional(self):
        r = RadarReview(
            id="rev1",
            concept_id="c1",
            to_stage=PortfolioStage.INBOX,
            reason="Initial capture",
            review_date=utc_now(),
        )
        assert r.from_stage is None

    def test_is_immutable(self):
        r = self._valid()
        with pytest.raises(ValidationError, match="frozen"):
            r.reason = "edited"

    def test_reason_required(self):
        with pytest.raises(ValidationError):
            self._valid(reason="")

    def test_to_stage_required(self):
        with pytest.raises(ValidationError):
            RadarReview(id="rev1", concept_id="c1", reason="move", review_date=utc_now())

    def test_invalid_to_stage_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(to_stage="maybe-later")

    def test_naive_review_date_rejected(self):
        with pytest.raises(ValidationError, match="timezone-aware"):
            self._valid(review_date=datetime(2026, 9, 1, 12, 0, 0))

    def test_non_utc_review_date_rejected(self):
        with pytest.raises(ValidationError, match="UTC"):
            self._valid(
                review_date=datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=3)))
            )


# ── Radar run payload ──

class TestRadarRunPayload:
    def test_minimal_defaults(self):
        p = RadarRunPayload(radar="agent-reliability")
        assert p.sources == []
        assert p.cards_affected == []
        assert p.gaps == []
        assert p.period == ""
        assert p.run_at.utcoffset() == timedelta(0)

    def test_with_sources(self):
        p = RadarRunPayload(
            radar="agent-reliability",
            period="2026-W36",
            sources=[
                SourceCoverage(source_type=SourceType.GITHUB, status=SourceStatus.COMPLETE),
                SourceCoverage(source_type=SourceType.REDDIT, status=SourceStatus.PARTIAL, note="RSS only, no comments"),
                SourceCoverage(source_type=SourceType.X, status=SourceStatus.UNAVAILABLE),
                SourceCoverage(source_type=SourceType.PAPER, status=SourceStatus.NOT_REQUESTED),
            ],
            cards_affected=["agent-reliability"],
            summary="Scanned agent-reliability",
            gaps=["X unavailable", "Reddit comments not read"],
        )
        assert len(p.sources) == 4
        assert p.cards_affected == ["agent-reliability"]

    def test_invalid_source_status_rejected(self):
        with pytest.raises(ValidationError) as exc:
            SourceCoverage(source_type=SourceType.GITHUB, status="half-done")
        assert exc.value.errors()[0]["type"] == "enum"

    def test_invalid_source_type_rejected(self):
        with pytest.raises(ValidationError):
            SourceCoverage(source_type="mastodon", status=SourceStatus.COMPLETE)

    def test_naive_run_at_rejected(self):
        with pytest.raises(ValidationError, match="timezone-aware"):
            RadarRunPayload(radar="r", run_at=datetime(2026, 9, 1, 12, 0, 0))

    def test_empty_radar_name_rejected(self):
        with pytest.raises(ValidationError):
            RadarRunPayload(radar="")


# ── JSON schema generation ──

class TestJsonSchema:
    @pytest.mark.parametrize(
        "model",
        [
            ComponentScores,
            SmallestExperiment,
            ConceptCard,
            ConceptEvidence,
            RadarReview,
            SourceCoverage,
            RadarRunPayload,
        ],
    )
    def test_schema_generation_succeeds(self, model: type[BaseModel]):
        schema = model.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "title" in schema

    def test_concept_card_schema_nests_experiment_and_scores(self):
        schema = ConceptCard.model_json_schema()
        assert schema["properties"]["smallest_experiment"]["anyOf"][0]["$ref"] == "#/$defs/SmallestExperiment"
        assert schema["properties"]["component_scores"]["$ref"] == "#/$defs/ComponentScores"
        assert "SmallestExperiment" in schema["$defs"]
        assert "ComponentScores" in schema["$defs"]

    def test_utc_datetime_type_usable(self):
        # UtcDatetime must be usable as a field annotation and enforce UTC.
        class T(BaseModel):
            ts: UtcDatetime

        with pytest.raises(ValidationError, match="UTC"):
            T(ts=datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=2))))
        t = T(ts=utc_now())
        assert t.ts.utcoffset() == timedelta(0)
