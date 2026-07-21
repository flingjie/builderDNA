"""Tests for trend models."""
from backend.models.trend import RepoTrend, TopicTrend, TrendSnapshot


class TestRepoTrend:
    def test_defaults(self):
        r = RepoTrend(full_name="a/b", stars=100, forks=10, contributors=5)
        assert r.trend_score == 0.0
        assert r.stars_delta == 0

    def test_full_creation(self):
        r = RepoTrend(
            full_name="a/b", stars=100, stars_delta=30, forks=10,
            contributors=5, contributor_growth=0.2, velocity=5.0,
            trend_score=85.0, days_since_first_release=60,
        )
        assert r.trend_score == 85.0


class TestTopicTrend:
    def test_minimal(self):
        t = TopicTrend(
            topic="mcp", stage="emerging", confidence=0.8,
            growth_velocity=3.2, evidence_count=12,
        )
        assert t.top_repos == []
        assert t.stage == "emerging"


class TestTrendSnapshot:
    def test_auto_id(self):
        s = TrendSnapshot(domain="agent", window_days=60)
        assert len(s.id) == 8
        assert s.domain == "agent"
        assert s.topics == []
