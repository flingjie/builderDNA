"""Tests for discovery models."""
from backend.models.discovery import DiscoveredTheme, DiscoverySnapshot


class TestDiscoveredTheme:
    def test_defaults(self):
        t = DiscoveredTheme(
            topic="ai-native-terminal",
            description="AI-powered terminal emulators and CLI tools",
            repo_count=37,
            avg_stars=1200.0,
            velocity=5.2,
            stage="emerging",
            sample_repos=["a/b", "c/d"],
        )
        assert t.is_new is True        # default
        assert t.suggested_as_topic is True  # default
        assert t.stage == "emerging"
        assert t.repo_count == 37

    def test_existing_theme(self):
        t = DiscoveredTheme(
            topic="agent-framework",
            description="Already tracked",
            repo_count=10,
            avg_stars=500.0,
            velocity=2.0,
            stage="stable",
            sample_repos=[],
            is_new=False,
            suggested_as_topic=False,
        )
        assert not t.is_new
        assert not t.suggested_as_topic


class TestDiscoverySnapshot:
    def test_auto_id(self):
        s = DiscoverySnapshot(domain="agent", window_days=60)
        assert len(s.id) == 8
        assert s.domain == "agent"
        assert s.themes == []

    def test_with_themes(self):
        theme = DiscoveredTheme(
            topic="test-theme",
            description="desc",
            repo_count=5,
            avg_stars=100.0,
            velocity=1.0,
            stage="emerging",
            sample_repos=["x/y"],
        )
        s = DiscoverySnapshot(
            domain="agent", window_days=60, themes=[theme]
        )
        assert len(s.themes) == 1
        assert s.themes[0].topic == "test-theme"
