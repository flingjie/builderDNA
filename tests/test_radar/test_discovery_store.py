"""Tests for discovery store."""
from backend.models.discovery import DiscoveredTheme, DiscoverySnapshot
from backend.store.discovery_store import DiscoveryStore


class TestDiscoveryStore:
    def test_save_and_retrieve(self, tmp_path):
        store = DiscoveryStore(str(tmp_path / "discovery.db"))
        snap = DiscoverySnapshot(
            domain="agent", window_days=60,
            themes=[DiscoveredTheme(
                topic="ai-terminal", description="test",
                repo_count=5, avg_stars=100.0, velocity=1.0,
                stage="emerging", sample_repos=["a/b"],
            )],
        )
        sid = store.save(snap)
        assert sid == snap.id

        loaded = store.get_latest("agent")
        assert loaded is not None
        assert loaded.domain == "agent"
        assert len(loaded.themes) == 1
        assert loaded.themes[0].topic == "ai-terminal"

    def test_get_latest_empty_returns_none(self, tmp_path):
        store = DiscoveryStore(str(tmp_path / "empty.db"))
        assert store.get_latest("agent") is None

    def test_get_all_returns_latest_first(self, tmp_path):
        store = DiscoveryStore(str(tmp_path / "multi.db"))
        s1 = DiscoverySnapshot(domain="agent", window_days=60)
        s2 = DiscoverySnapshot(domain="agent", window_days=60)
        store.save(s1)
        store.save(s2)

        snaps = store.get_all("agent")
        assert len(snaps) == 2
        # Latest first
        assert snaps[0].id == s2.id
