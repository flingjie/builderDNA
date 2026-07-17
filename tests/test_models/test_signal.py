"""Tests for Signal and SignalCluster models."""

from datetime import datetime, timezone

import pytest

from models.signal import Signal, SignalCluster


class TestSignal:
    def test_signal_creation_minimal(self):
        s = Signal(
            id="gh_repo_alice_toolkit",
            source="github",
            type="repo",
            timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc),
            weight=5.0,
            actor="alice",
            target="alice/toolkit",
        )
        assert s.id == "gh_repo_alice_toolkit"
        assert s.source == "github"
        assert s.type == "repo"
        assert s.weight == 5.0
        assert s.meta == {}
        assert s.raw == {}

    def test_signal_creation_full(self):
        s = Signal(
            id="gh_star_alice_fastapi",
            source="github",
            type="star",
            timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
            weight=1.0,
            actor="alice",
            target="tiangolo/fastapi",
            meta={"language": "Python", "topics": ["web", "api"]},
            raw={"full_name": "tiangolo/fastapi", "stargazers_count": 80000},
        )
        assert s.meta["language"] == "Python"
        assert "web" in s.meta["topics"]
        assert s.raw["stargazers_count"] == 80000

    def test_signal_invalid_type(self):
        with pytest.raises(ValueError):
            Signal(
                id="test",
                source="github",
                type="repo",
                timestamp="not-a-datetime",  # type: ignore
                weight=5.0,
                actor="alice",
                target="t",
            )


class TestSignalCluster:
    def test_cluster_creation(self):
        c = SignalCluster(
            signals=["s1", "s2", "s3"],
            topics=["llm", "agent"],
            languages=["Python"],
            total_weight=15.0,
            time_span_days=45,
            growth_rate=0.6,
        )
        assert len(c.signals) == 3
        assert c.total_weight == 15.0
        assert c.growth_rate == 0.6

    def test_cluster_growth_rate_bounds(self):
        c = SignalCluster(
            signals=["s1"],
            topics=["ai"],
            languages=["Rust"],
            total_weight=5.0,
            time_span_days=10,
            growth_rate=1.0,
        )
        assert 0.0 <= c.growth_rate <= 1.0
