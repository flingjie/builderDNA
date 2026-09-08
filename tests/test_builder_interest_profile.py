"""Tests for BuilderInterestProfile — the converged user-interest model (P4)."""

import json
from pathlib import Path

import pytest

from models.builder_interest_profile import (
    BuilderInterestProfile,
    InterestItem,
    load_profile,
    migrate_user_dna,
)
from models.user_dna_schema import UserDNA, Values, ValueDimension


def _profile(**overrides) -> BuilderInterestProfile:
    base = dict(
        domains=[InterestItem(value="agent", source="user_confirmed", confirmed=True)],
        learning_goals=[InterestItem(value="build", source="user_confirmed", confirmed=True)],
    )
    base.update(overrides)
    return BuilderInterestProfile(**base)


class TestInterestItemProvenance:
    def test_defaults_are_inferred_and_unconfirmed(self):
        item = InterestItem(value="mcp")
        assert item.source == "inferred"
        assert item.confirmed is False
        assert item.updated_at  # non-empty timestamp

    def test_confirmed_item_carries_source(self):
        item = InterestItem(value="agent", source="user_confirmed", confirmed=True)
        assert item.source == "user_confirmed"
        assert item.confirmed is True


class TestBuilderInterestProfile:
    def test_only_serves_learning_and_building(self):
        p = _profile()
        # The public contract has exactly the 6 fields + provenance + metadata.
        fields = set(BuilderInterestProfile.model_fields)
        assert fields == {
            "version", "extracted_at",
            "domains", "technical_adjacencies", "problem_preferences",
            "build_constraints", "learning_goals", "risk_tolerance",
            "migrated_from",
        }

    def test_to_values_produces_valid_internal_values(self):
        p = _profile(
            domains=[
                InterestItem(value="agent", source="user_confirmed", confirmed=True),
                InterestItem(value="devtools", source="user_confirmed", confirmed=True),
            ],
            learning_goals=[
                InterestItem(value="build", source="user_confirmed", confirmed=True),
            ],
            build_constraints=[
                InterestItem(value="solo", source="user_confirmed", confirmed=True),
            ],
            problem_preferences=[
                InterestItem(value="mastery", source="user_confirmed", confirmed=True),
            ],
        )
        values = p.to_values()
        assert isinstance(values, Values)
        assert values.output.ranking  # domains → output ranking
        assert values.activity.ranking  # learning_goals → activity
        assert values.environment.ranking  # build_constraints → environment
        assert values.reward.ranking  # problem_preferences → reward

    def test_empty_profile_uses_fallback_rankings(self):
        values = BuilderInterestProfile().to_values()
        assert values.output.ranking
        assert values.activity.ranking
        assert values.environment.ranking
        assert values.reward.ranking


class TestMigration:
    def _legacy_dna(self) -> dict:
        return {
            "version": 1,
            "extracted_at": "2026-01-01T00:00:00+00:00",
            "values": {
                "environment": {
                    "ranking": ["autonomy", "collaboration"],
                    "scores": {"autonomy": 9, "collaboration": 6},
                },
                "activity": {
                    "ranking": ["creation", "exploration"],
                    "scores": {"creation": 9, "exploration": 8},
                },
                "output": {
                    "ranking": ["infrastructure", "devtools"],
                    "scores": {"infrastructure": 9, "devtools": 7},
                },
                "reward": {
                    "ranking": ["growth", "mastery"],
                    "scores": {"growth": 9, "mastery": 8},
                },
            },
            "beliefs": [], "criteria": [], "preferences": {}, "evidence_log": [],
        }

    def test_migration_writes_profile_and_backup(self, tmp_path):
        old = tmp_path / "user_dna.json"
        new = tmp_path / "builder_interest_profile.json"
        old.write_text(json.dumps(self._legacy_dna()))

        profile = migrate_user_dna(str(old), str(new), backup=True)

        assert profile.domains[0].value == "agent"  # infrastructure → agent
        assert profile.learning_goals[0].value == "build"  # creation → build
        assert profile.build_constraints[0].value == "solo"  # autonomy → solo
        assert profile.problem_preferences[0].value == "growth"  # growth → growth
        assert profile.migrated_from == str(old)
        assert all(item.confirmed for item in profile.domains)

        # Backup of the legacy file exists and is unchanged.
        backup = Path(str(old) + ".bak")
        assert backup.exists()
        assert json.loads(backup.read_text()) == self._legacy_dna()

        # New profile file is loadable.
        assert load_profile(str(new)) is not None

    def test_migration_is_idempotent(self, tmp_path):
        old = tmp_path / "user_dna.json"
        new = tmp_path / "builder_interest_profile.json"
        old.write_text(json.dumps(self._legacy_dna()))

        first = migrate_user_dna(str(old), str(new))
        second = migrate_user_dna(str(old), str(new))

        # Second run returns the already-written profile, does not re-migrate.
        assert second == first

    def test_load_profile_returns_none_on_missing(self, tmp_path):
        assert load_profile(str(tmp_path / "nope.json")) is None

    def test_load_profile_returns_none_on_empty(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text(json.dumps({"version": 1, "domains": [], "learning_goals": []}))
        assert load_profile(str(p)) is None
