"""Tests for BuilderInterestProfile — the converged user-interest model (P4)."""

import json
from pathlib import Path

import pytest

from models.builder_interest_profile import (
    BuilderInterestProfile,
    InterestItem,
    load_profile,
)


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

    def test_profile_roundtrip(self, tmp_path):
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
        # Serialize and reload
        profile_file = tmp_path / "profile.json"
        profile_file.write_text(p.model_dump_json(indent=2))
        loaded = load_profile(str(profile_file))
        assert loaded is not None
        assert len(loaded.domains) == 2
        assert len(loaded.learning_goals) == 1


class TestLoadProfile:
    def test_load_profile_returns_none_on_missing(self, tmp_path):
        assert load_profile(str(tmp_path / "nope.json")) is None

    def test_load_profile_returns_none_on_empty(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text(json.dumps({"version": 1, "domains": [], "learning_goals": []}))
        assert load_profile(str(p)) is None
