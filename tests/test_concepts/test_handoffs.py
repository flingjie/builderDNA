"""Tests for the source handoff envelope (concepts/handoffs.py).

Covers the plan's Task 6 contract:
- envelope validation (schema_version, source_phase, coverage, items);
- unknown schema version rejected;
- missing provenance rejected (a url or upstream_origin must be present when
  directness != inferred — manual inference must remain directness=inferred);
- valid fixtures load and round-trip;
- item directness / strength / role enum validation;
- paper/doc novelty claims require a primary-source URL.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from concepts.handoffs import (
    CoverageStatus,
    ImportResult,
    ProposedConcept,
    SourceHandoffEnvelope,
    SourceHandoffItem,
    SourcePhase,
    UNASSIGNED_CONCEPT_ID,
    import_handoff,
    normalize_handoff,
)
from concepts.store import ConceptStore
from models.concept import (
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    SourceType,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "radar"


def make_envelope(**overrides) -> SourceHandoffEnvelope:
    fields = dict(schema_version=1, source_phase="x-discovery", coverage="partial")
    fields.update(overrides)
    return SourceHandoffEnvelope(**fields)


def make_item(**overrides) -> dict:
    fields = dict(
        source="x",
        role="problem",
        author="alice_dev",
        url="https://x.com/alice_dev/status/123456",
        excerpt="A paraphrased note about the claim.",
        directness="direct",
        strength="moderate",
    )
    fields.update(overrides)
    return fields


# ── Envelope validation ──

class TestEnvelope:
    def test_empty_items_valid(self):
        env = make_envelope()
        assert env.items == []
        assert env.coverage_notes == []

    def test_defaults(self):
        env = make_envelope(coverage="complete")
        assert env.coverage == CoverageStatus.COMPLETE
        assert env.source_phase == SourcePhase.X_DISCOVERY
        assert env.schema_version == 1

    def test_json_schema_succeeds(self):
        assert SourceHandoffEnvelope.model_json_schema() is not None

    def test_rejects_invalid_item_atomically(self):
        with pytest.raises(ValidationError):
            SourceHandoffEnvelope(
                schema_version=1,
                source_phase="x-discovery",
                coverage="partial",
                items=[
                    make_item(),
                    make_item(directness="direct", url="", upstream_origin=None),
                ],
            )


class TestSchemaVersion:
    def test_unknown_version_rejected(self):
        with pytest.raises(ValidationError):
            make_envelope(schema_version=2)

    def test_zero_version_rejected(self):
        with pytest.raises(ValidationError):
            make_envelope(schema_version=0)

    def test_missing_version_rejected(self):
        with pytest.raises(ValidationError):
            SourceHandoffEnvelope(source_phase="x-discovery", coverage="partial")


class TestEnums:
    @pytest.mark.parametrize("field", ["source", "role", "directness", "strength"])
    def test_invalid_item_enum_rejected(self, field):
        with pytest.raises(ValidationError):
            SourceHandoffItem(**make_item(**{field: "not-a-real-value"}))

    @pytest.mark.parametrize("value", ["not-a-phase", "", "report"])
    def test_invalid_source_phase_rejected(self, value):
        with pytest.raises(ValidationError):
            make_envelope(source_phase=value)

    @pytest.mark.parametrize("value", ["not-a-coverage", "not_requested"])
    def test_invalid_coverage_rejected(self, value):
        with pytest.raises(ValidationError):
            make_envelope(coverage=value)


# ── Provenance rules ──

class TestProvenance:
    @pytest.mark.parametrize("directness", ["direct", "indirect"])
    def test_missing_provenance_rejected_when_not_inferred(self, directness):
        with pytest.raises(ValidationError):
            SourceHandoffItem(
                **make_item(directness=directness, url="", upstream_origin=None)
            )

    def test_upstream_origin_satisfies_provenance(self):
        item = SourceHandoffItem(
            **make_item(directness="direct", url="", upstream_origin="https://github.com/o/r/issues/1")
        )
        assert item.directness == Directness.DIRECT

    def test_manual_inference_requires_inferred(self):
        item = SourceHandoffItem(
            **make_item(directness="inferred", url="", upstream_origin=None)
        )
        assert item.directness == Directness.INFERRED

    def test_inferred_with_url_is_valid(self):
        item = SourceHandoffItem(**make_item(directness="inferred"))
        assert item.directness == Directness.INFERRED


class TestPaperDocRule:
    @pytest.mark.parametrize("source", ["paper", "official_doc"])
    def test_requires_primary_source_url(self, source):
        with pytest.raises(ValidationError):
            SourceHandoffItem(
                **make_item(source=source, directness="inferred", url="", upstream_origin=None)
            )

    def test_paper_with_url_valid(self):
        item = SourceHandoffItem(
            **make_item(source="paper", directness="direct", url="https://arxiv.org/abs/1234.5678")
        )
        assert item.source == SourceType.PAPER


class TestTimestamps:
    def test_naive_published_at_rejected(self):
        with pytest.raises(ValidationError):
            SourceHandoffItem(**make_item(published_at=datetime(2026, 1, 1)))

    def test_non_utc_published_at_rejected(self):
        with pytest.raises(ValidationError):
            SourceHandoffItem(
                **make_item(
                    published_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))
                )
            )

    def test_utc_published_at_accepted(self):
        item = SourceHandoffItem(
            **make_item(published_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        assert item.published_at.utcoffset() == timedelta(0)


class TestProposedConcept:
    def test_optional_proposed_concept(self):
        item = SourceHandoffItem(
            **make_item(
                proposed_concept={
                    "title": "Agent goal-drift detector",
                    "problem": "Agents silently drift from stated goals",
                }
            )
        )
        assert isinstance(item.proposed_concept, ProposedConcept)
        assert item.proposed_concept.title == "Agent goal-drift detector"
        assert item.proposed_concept.aliases == []

    def test_proposed_concept_requires_title(self):
        with pytest.raises(ValidationError):
            ProposedConcept(title="")


# ── Fixtures ──

class TestFixtures:
    @pytest.mark.parametrize(
        "name,source_phase,source",
        [
            ("x_learning_handoff.json", "x-discovery", "x"),
            ("reddit_handoff.json", "reddit-scan", "reddit"),
            ("github_handoff.json", "verify", "github"),
        ],
    )
    def test_fixture_loads_and_round_trips(self, name, source_phase, source):
        path = FIXTURE_DIR / name
        raw = path.read_text()
        assert json.loads(raw) is not None  # valid JSON, not a JSON error

        env = SourceHandoffEnvelope.model_validate_json(raw)
        assert env.schema_version == 1
        assert env.source_phase.value == source_phase
        assert len(env.items) >= 1
        assert env.items[0].source.value == source

        # Round-trip: dump then re-validate.
        round_tripped = SourceHandoffEnvelope.model_validate_json(env.model_dump_json())
        assert round_tripped.items[0].source == env.items[0].source
        assert round_tripped.items[0].url == env.items[0].url


# ── Normalization (envelope item -> ConceptEvidence) ──

class TestNormalizeHandoff:
    def test_x_learning_defaults_to_discovery_problem_without_first_hand_evidence(self):
        item = SourceHandoffItem(
            **make_item(
                role="adoption",
                strength="strong",
                directness="inferred",
                url="",
                upstream_origin=None,
            )
        )
        env = make_envelope(items=[item])
        [evidence] = normalize_handoff(env)

        assert isinstance(evidence, ConceptEvidence)
        assert evidence.role == EvidenceRole.PROBLEM
        assert evidence.directness == Directness.INFERRED
        assert evidence.strength == EvidenceStrength.WEAK

    def test_x_learning_with_first_hand_evidence_keeps_role_and_strength(self):
        item = SourceHandoffItem(
            **make_item(role="adoption", strength="strong", directness="direct")
        )
        env = make_envelope(items=[item])
        [evidence] = normalize_handoff(env)

        assert evidence.role == EvidenceRole.ADOPTION
        assert evidence.directness == Directness.DIRECT
        assert evidence.strength == EvidenceStrength.STRONG

    def test_reddit_records_comments_not_read(self):
        item = SourceHandoffItem(**make_item(source="reddit", directness="direct"))
        env = make_envelope(source_phase="reddit-scan", items=[item])
        [evidence] = normalize_handoff(env)

        assert evidence.directness == Directness.DIRECT
        assert "comments not read" in evidence.note

    def test_reddit_not_labeled_consensus(self):
        item = SourceHandoffItem(
            **make_item(source="reddit", role="adoption", directness="direct")
        )
        env = make_envelope(source_phase="reddit-scan", items=[item])
        [evidence] = normalize_handoff(env)

        assert evidence.role != EvidenceRole.ADOPTION
        assert evidence.role == EvidenceRole.PROBLEM

    def test_github_stars_only_becomes_implementation(self):
        item = SourceHandoffItem(
            **make_item(
                source="github",
                role="adoption",
                author="",
                url="https://github.com/exampleorg/example-repo",
                directness="indirect",
            )
        )
        env = make_envelope(source_phase="verify", items=[item])
        [evidence] = normalize_handoff(env)

        assert evidence.role == EvidenceRole.IMPLEMENTATION

    def test_github_external_use_keeps_adoption(self):
        item = SourceHandoffItem(
            **make_item(
                source="github",
                role="adoption",
                author="external_user",
                url="https://github.com/exampleorg/example-repo/issues/42",
                directness="direct",
            )
        )
        env = make_envelope(source_phase="verify", items=[item])
        [evidence] = normalize_handoff(env)

        assert evidence.role == EvidenceRole.ADOPTION

    def test_manual_inference_forces_inferred(self):
        item = SourceHandoffItem(
            **make_item(
                source="manual",
                directness="direct",
                url="https://example.com/x",
                strength="strong",
            )
        )
        env = make_envelope(items=[item])
        [evidence] = normalize_handoff(env)

        assert evidence.directness == Directness.INFERRED

    def test_repost_chain_collapses_to_one_independence_key(self):
        a = SourceHandoffItem(
            **make_item(
                url="https://x.com/bob/status/2",
                upstream_origin="https://github.com/o/r/issues/1",
                directness="indirect",
            )
        )
        b = SourceHandoffItem(
            **make_item(
                url="https://x.com/carol/status/3",
                upstream_origin="https://github.com/o/r/issues/1",
                directness="indirect",
            )
        )
        env = make_envelope(items=[a, b])
        records = normalize_handoff(env)

        assert records[0].independence_key == records[1].independence_key
        assert records[0].independence_key == "upstream:github.com/o/r/issues/1"

    def test_independence_key_url_fallback(self):
        item = SourceHandoffItem(**make_item(url="https://x.com/a/status/1"))
        [evidence] = normalize_handoff(make_envelope(items=[item]))

        assert evidence.independence_key == "x:x.com/a/status/1"

    def test_independence_key_content_hash_fallback(self):
        item = SourceHandoffItem(
            **make_item(
                url="",
                upstream_origin=None,
                directness="inferred",
                author="alice",
                excerpt="a unique claim nobody else has made",
            )
        )
        env = make_envelope(items=[item])
        [evidence] = normalize_handoff(env)

        assert evidence.independence_key.startswith("x:hash:")

    def test_proposed_concept_derives_concept_id(self):
        item = SourceHandoffItem(
            **make_item(proposed_concept={"title": "Agent goal-drift detector"})
        )
        env = make_envelope(items=[item])
        [evidence] = normalize_handoff(env)

        assert evidence.concept_id == "agent-goal-drift-detector"

    def test_item_without_proposed_concept_uses_unassigned(self):
        item = SourceHandoffItem(**make_item())
        env = make_envelope(items=[item])
        [evidence] = normalize_handoff(env)

        assert evidence.concept_id == UNASSIGNED_CONCEPT_ID


# ── Atomic import (envelope -> store) ──

class TestImportHandoff:
    def test_import_returns_counts_and_affected_concepts(self, tmp_path):
        store = ConceptStore(state_dir=tmp_path)
        item = SourceHandoffItem(
            **make_item(proposed_concept={"title": "Agent goal-drift detector"})
        )
        env = make_envelope(items=[item])

        result = import_handoff(store, env)

        assert isinstance(result, ImportResult)
        assert result.imported == 1
        assert result.skipped_idempotent == 0
        assert result.conflicts == []
        assert result.concept_ids_affected == ["agent-goal-drift-detector"]
        assert len(store.list_evidence()) == 1

    def test_replaying_identical_handoff_is_idempotent(self, tmp_path):
        store = ConceptStore(state_dir=tmp_path)
        env = make_envelope(items=[make_item()])

        first = import_handoff(store, env)
        second = import_handoff(store, env)

        assert first.imported == 1
        assert first.skipped_idempotent == 0
        assert second.imported == 0
        assert second.skipped_idempotent == 1
        assert len(store.list_evidence()) == 1

    def test_structurally_invalid_item_rejects_whole_handoff(self, tmp_path):
        store = ConceptStore(state_dir=tmp_path)
        envelope_dict = {
            "schema_version": 1,
            "source_phase": "x-discovery",
            "coverage": "partial",
            "items": [
                make_item(),  # valid
                # invalid: paper novelty claim without a primary-source url
                make_item(source="paper", url="", upstream_origin=None, directness="inferred"),
            ],
        }

        with pytest.raises(ValidationError):
            import_handoff(store, envelope_dict)

        # No partial writes: the valid first item must not have been imported.
        assert store.list_evidence() == []

    def test_conflict_is_recorded_not_raised(self, tmp_path):
        store = ConceptStore(state_dir=tmp_path)
        # A pre-existing record with the same evidence ID but a different payload.
        store.add_evidence(
            ConceptEvidence(
                id="x:x.com/alice_dev/status/123456",
                concept_id=UNASSIGNED_CONCEPT_ID,
                source_type=SourceType.X,
                source_url="https://x.com/alice_dev/status/123456",
                role=EvidenceRole.PROBLEM,
                directness=Directness.DIRECT,
                strength=EvidenceStrength.MODERATE,
                independence_key="x:x.com/alice_dev/status/123456",
                note="a different pre-existing payload",
            )
        )
        env = make_envelope(items=[make_item()])

        result = import_handoff(store, env)

        assert result.imported == 0
        assert result.conflicts  # the same-ID/different-payload conflict is reported
        assert len(store.list_evidence()) == 1
