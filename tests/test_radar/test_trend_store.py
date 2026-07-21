"""Tests for trend store."""
from backend.models.trend import TrendSnapshot, TopicTrend, RepoTrend
from backend.store.trend_store import TrendStore


class TestTrendStore:
    def test_save_and_retrieve(self, tmp_path):
        store = TrendStore(str(tmp_path / "test.db"))
        snap = TrendSnapshot(
            domain="agent", window_days=60,
            topics=[TopicTrend(
                topic="mcp", stage="emerging", confidence=0.8,
                growth_velocity=3.0, evidence_count=5,
                top_repos=[RepoTrend(full_name="a/b", stars=100, forks=10, contributors=5)],
            )],
        )
        sid = store.save(snap)
        assert sid == snap.id

        loaded = store.get_latest("agent")
        assert loaded is not None
        assert loaded.domain == "agent"
        assert len(loaded.topics) == 1
        assert loaded.topics[0].topic == "mcp"

    def test_get_latest_empty_returns_none(self, tmp_path):
        store = TrendStore(str(tmp_path / "empty.db"))
        assert store.get_latest("agent") is None

    def test_get_all_returns_latest_first(self, tmp_path):
        store = TrendStore(str(tmp_path / "multi.db"))
        s1 = TrendSnapshot(domain="agent", window_days=60)
        s2 = TrendSnapshot(domain="agent", window_days=60)
        store.save(s1)
        store.save(s2)

        snaps = store.get_all("agent")
        assert len(snaps) == 2
        # Latest first
        assert snaps[0].id == s2.id
