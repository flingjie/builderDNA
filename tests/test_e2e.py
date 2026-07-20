"""End-to-end integration tests for the full BuilderDNA pipeline."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Config, GitHubConfig, LLMConfig, WeightConfig, OutputConfig, CompareConfig
from pipeline import Pipeline


MOCK_LLM_INSIGHT_RESPONSE = {"insights": [{
    "id": "in_001", "tags": ["llm", "agent", "python"],
    "summary": "Deep investment in LLM agent frameworks",
    "strength": 15.0, "trend": "rising", "signal_count": 3,
    "evidence": ["alice/toolkit"],
}]}

MOCK_LLM_OPPORTUNITY_RESPONSE = {"opportunities": [{
    "id": "op_001", "title": "Agent Testing Framework",
    "pain_point": "No good way to test LLM agent behavior",
    "demand_score": 4.5, "competition_score": 2.0,
    "recommended_action": "Build pytest plugin",
    "source_insights": ["in_001"],
}]}


@pytest.fixture
def e2e_config():
    return Config(
        accounts=["alice"],
        github=GitHubConfig(token="ghp_test"),
        llm=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        weights=WeightConfig(), output=OutputConfig(dir="./test_output"),
        compare=CompareConfig(enabled=False),
    )


class TestE2E:
    def test_full_pipeline_with_mocks(self, e2e_config, tmp_path):
        """Full pipeline run with mocked GitHub and LLM."""
        with patch("pipeline.GitHubClient") as MockGH, \
             patch("pipeline.OpenAIClient") as MockLLM, \
             patch("pipeline.SignalStore") as MockStoreCls:

            mock_gh = MockGH.return_value
            mock_gh.get_repos = AsyncMock(return_value=[{
                "id": 1, "full_name": "alice/toolkit", "language": "Python",
                "topics": ["llm", "agent"], "description": "An LLM agent toolkit",
                "stargazers_count": 42, "forks_count": 5,
                "updated_at": "2026-01-15T00:00:00Z", "created_at": "2025-01-01T00:00:00Z",
            }])
            mock_gh.get_starred = AsyncMock(return_value=[{
                "id": 100, "full_name": "fastapi/fastapi", "language": "Python",
                "topics": ["web", "api"], "description": "FastAPI framework",
                "stargazers_count": 80000,
                "updated_at": "2026-01-15T00:00:00Z",
            }])
            mock_gh.get_commits = AsyncMock(return_value=[{
                "sha": "abc123",
                "commit": {"author": {"name": "Alice", "date": "2026-03-01T10:00:00Z"},
                           "message": "Add MCP server for tool discovery"},
                "html_url": "https://github.com/alice/toolkit/commit/abc123",
            }])
            mock_gh.close = AsyncMock()
            mock_gh.rate_limiter = MagicMock()
            mock_gh.rate_limiter.usage_summary.return_value = "calls=2, remaining=4998/5000"

            mock_llm = MockLLM.return_value
            mock_llm.complete.side_effect = [MOCK_LLM_INSIGHT_RESPONSE, MOCK_LLM_OPPORTUNITY_RESPONSE]

            mock_store = MockStoreCls.return_value
            mock_store.create_snapshot.return_value = "snap_001"
            mock_store.get_last_snapshot.return_value = None

            pipeline = Pipeline(e2e_config)
            pipeline.store = mock_store
            pipeline.github = mock_gh
            pipeline.llm = mock_llm

            result = pipeline.run()

            assert len(result["signals"]) >= 2
            signal_types = {s.type for s in result["signals"]}
            assert signal_types >= {"repo", "star"}
            assert len(result["insights"]) == 1
            assert result["insights"][0].trend == "rising"
            assert len(result["opportunities"]) == 1
            assert result["opportunities"][0].gap_score > 0
            mock_store.create_snapshot.assert_called_once()
            mock_store.insert_signals.assert_called_once()

    def test_pipeline_handles_empty_account(self, e2e_config):
        """Pipeline should handle empty data gracefully."""
        with patch("pipeline.GitHubClient") as MockGH, \
             patch("pipeline.OpenAIClient"), \
             patch("pipeline.SignalStore") as MockStoreCls:

            mock_gh = MockGH.return_value
            mock_gh.get_repos = AsyncMock(return_value=[])
            mock_gh.get_starred = AsyncMock(return_value=[])
            mock_gh.close = AsyncMock()
            mock_gh.rate_limiter = MagicMock()
            mock_gh.rate_limiter.usage_summary.return_value = "calls=2"

            mock_store = MockStoreCls.return_value
            mock_store.create_snapshot.return_value = "empty_snap"

            pipeline = Pipeline(e2e_config)
            pipeline.store = mock_store
            pipeline.github = mock_gh

            result = pipeline.run()
            assert result["signals"] == []
            assert result["insights"] == []
            assert result["opportunities"] == []
