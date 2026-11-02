"""Migration/compatibility tests for the cross-source Signal extension (Task 3.1).

Covers:
  - new source values and generic/fallback `type`
  - nullable evidence metadata (role, directness, strength, independence_key)
  - payload stays the source-specific extensibility point
"""
from datetime import datetime, timezone

import pytest

from signals.models import Signal, GITHUB_EVENT_TYPES, GENERIC_EVENT_TYPES


class TestSourceExtension:
    def test_all_sources_accepted(self):
        for source in ("x", "reddit", "github", "paper", "official_doc", "manual"):
            s = Signal(
                source=source,
                type="signal",
                actor="a",
                target_repo="t",
                timestamp=datetime.now(timezone.utc),
            )
            assert s.source == source

    def test_invalid_source_rejected(self):
        with pytest.raises(Exception):
            Signal(
                source="tiktok",
                type="signal",
                actor="a",
                target_repo="t",
            )

    def test_github_event_types_still_valid(self):
        for t in GITHUB_EVENT_TYPES:
            s = Signal(source="github", type=t, actor="a", target_repo="a/b")
            assert s.type == t

    def test_type_is_extensible_free_string(self):
        # New sources can introduce their own labels without a schema change.
        s = Signal(
            source="reddit",
            type="community_rss_finding",
            actor="u/author",
            target_repo="r/SaaS",
        )
        assert s.type == "community_rss_finding"

    def test_generic_type_fallback(self):
        # Omitting `type` yields the generic fallback.
        s = Signal(source="manual", actor="me", target_repo="https://example.com")
        assert s.type == "signal"


class TestEvidenceMetadata:
    def test_metadata_defaults_to_none(self):
        s = Signal(source="github", type="repo_created", actor="a", target_repo="a/b")
        assert s.evidence_role is None
        assert s.directness is None
        assert s.strength is None
        assert s.independence_key is None

    def test_metadata_settable(self):
        s = Signal(
            source="reddit",
            type="evidence",
            actor="u/author",
            target_repo="r/AgentDev",
            evidence_role="problem",
            directness="L1",
            strength=0.9,
            independence_key="https://reddit.com/r/AgentDev/comments/abc",
        )
        assert s.evidence_role == "problem"
        assert s.directness == "L1"
        assert s.strength == 0.9
        assert s.independence_key == "https://reddit.com/r/AgentDev/comments/abc"
