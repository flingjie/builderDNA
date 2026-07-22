"""Tests for unified Signal model and aggregate views."""
from datetime import datetime, timezone
from signals.models import Signal, AggregateTopicTrend, AggregateRepoTrend


class TestSignal:
    def test_minimal_signal(self):
        s = Signal(
            id="sig-001",
            source="github",
            type="repo_created",
            actor="test-dev",
            target_repo="org/repo",
            timestamp=datetime.now(timezone.utc),
        )
        assert s.source == "github"
        assert s.velocity == 0.0
        assert s.impact == 0.0
        assert s.payload == {}

    def test_full_signal(self):
        s = Signal(
            id="sig-002",
            source="github",
            type="star_growth",
            actor="star-user",
            target_repo="org/popular",
            timestamp=datetime.now(timezone.utc),
            velocity=15.5,
            impact=0.8,
            payload={"stars_before": 100, "stars_after": 200},
        )
        assert s.velocity == 15.5
        assert s.payload["stars_before"] == 100

    def test_signal_type_validation(self):
        valid_types = [
            "repo_created", "star_growth", "issue_opened",
            "issue_commented", "release", "fork", "discussion",
        ]
        for t in valid_types:
            s = Signal(
                id="s",
                source="github",
                type=t,
                actor="a",
                target_repo="a/b",
                timestamp=datetime.now(timezone.utc),
            )
            assert s.type == t


class TestAggregateTopicTrend:
    def test_from_signals(self):
        signals = [
            Signal(
                id="s1", source="github", type="repo_created",
                actor="dev", target_repo="org/repo1",
                timestamp=datetime.now(timezone.utc), velocity=5.0,
                payload={"topics": ["agent", "mcp"]},
            ),
            Signal(
                id="s2", source="github", type="star_growth",
                actor="dev2", target_repo="org/repo2",
                timestamp=datetime.now(timezone.utc), velocity=3.0,
                payload={"topics": ["agent", "langchain"]},
            ),
        ]
        trends = AggregateTopicTrend.from_signals(signals)
        assert len(trends) > 0


class TestAggregateRepoTrend:
    def test_defaults(self):
        r = AggregateRepoTrend(full_name="a/b", stars=100, velocity=5.0)
        assert r.stars == 100
        assert r.trend_score == 0.0
