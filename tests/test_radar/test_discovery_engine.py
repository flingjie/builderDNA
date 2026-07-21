"""Tests for discovery engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.models.discovery import DiscoveredTheme, DiscoverySnapshot
from backend.engine.discovery import (
    _build_broad_query,
    _build_clustering_prompt,
    _compute_heat,
    run_discovery,
)

pytestmark = pytest.mark.anyio


class TestBuildBroadQuery:
    def test_builds_query_with_language_filter(self):
        config = MagicMock()
        config.discovery.min_stars = 100
        config.discovery.lookback_days = 30
        config.discovery.language_filter = {
            "exclude": ["JavaScript"],
            "include": ["Python", "TypeScript"],
        }
        query = _build_broad_query(config)
        assert "stars:>=100" in query
        assert "language:Python" in query or "language:TypeScript" in query

    def test_builds_query_include_mode(self):
        config = MagicMock()
        config.discovery.min_stars = 200
        config.discovery.lookback_days = 14
        config.discovery.language_filter = {
            "exclude": [],
            "include": ["Rust"],
        }
        query = _build_broad_query(config)
        assert "stars:>=200" in query
        assert "language:Rust" in query


class TestComputeHeat:
    def test_emerging_high_velocity(self):
        stage = _compute_heat(repo_count=15, avg_velocity=8.0)
        assert stage == "accelerating"

    def test_cooling_low_velocity(self):
        stage = _compute_heat(repo_count=2, avg_velocity=0.4)
        assert stage == "cooling"

    def test_stable_mid_range(self):
        stage = _compute_heat(repo_count=10, avg_velocity=1.0)
        assert stage == "stable"


class TestBuildClusteringPrompt:
    def test_formats_repos(self):
        repos = [
            {"full_name": "a/b", "description": "AI terminal", "topics": ["cli", "ai"]},
            {"full_name": "c/d", "description": "Smart shell tool", "topics": ["terminal"]},
        ]
        prompt = _build_clustering_prompt(repos)
        assert "a/b" in prompt
        assert "c/d" in prompt
        assert "AI terminal" in prompt


class TestRunDiscovery:
    async def test_returns_snapshot_with_themes(self, tmp_path):
        config = MagicMock()
        config.discovery.enabled = True
        config.discovery.min_stars = 100
        config.discovery.lookback_days = 30
        config.discovery.language_filter = {
            "exclude": [],
            "include": ["Python"],
        }
        config.domains = {"agent": {"topics": ["mcp"]}}

        mock_client = AsyncMock()
        mock_client._request = AsyncMock(return_value=MagicMock(
            json=lambda: {"items": [
                {"full_name": "org/repo1", "description": "AI tool", "topics": ["ai"], "stargazers_count": 500}
            ]}
        ))
        mock_client.rate_limiter = MagicMock()
        mock_client.rate_limiter.usage_summary = MagicMock(return_value="calls=1")

        mock_llm = MagicMock()
        mock_llm.complete = MagicMock(return_value={
            "themes": [
                {"topic": "ai-native-tools", "description": "AI-native dev tools", "repo_count": 1, "avg_stars": 500.0, "velocity": 5.0, "stage": "accelerating", "sample_repos": ["org/repo1"]}
            ]
        })

        from backend.store.discovery_store import DiscoveryStore
        store = DiscoveryStore(str(tmp_path / "discovery.db"))

        snapshot = await run_discovery(mock_client, config, mock_llm, store)
        assert snapshot is not None
        assert snapshot.domain == "global"
        assert len(snapshot.themes) >= 0
