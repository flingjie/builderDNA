"""Tests for the Pipeline orchestrator."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from models.signal import Signal
from models.insight import Insight
from models.opportunity import Opportunity
from config import Config, GitHubConfig, LLMConfig, WeightConfig, OutputConfig, CompareConfig
from pipeline import Pipeline


@pytest.fixture
def sample_config():
    return Config(
        accounts=["alice"],
        github=GitHubConfig(token="ghp_test"),
        llm=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        weights=WeightConfig(), output=OutputConfig(dir="./test_output"),
        compare=CompareConfig(enabled=True),
    )


@pytest.fixture
def sample_signals():
    return [Signal(
        id=f"s{i}", source="github", type="repo",
        timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc), weight=5.0,
        actor="alice", target="alice/repo",
        meta={"language": "Python", "topics": ["llm"], "description": ""}, raw={},
    ) for i in range(3)]


@pytest.fixture
def sample_insights():
    return [Insight(
        id="in_001", tags=["LLM"], summary="Focus on LLM", strength=15.0,
        trend="rising", signal_count=3, evidence=["alice/repo"],
    )]


@pytest.fixture
def sample_opportunities():
    return [Opportunity(
        id="op_001", title="Agent Tool", pain_point="Missing testing",
        demand_score=4.0, competition_score=2.0, gap_score=2.0,
        recommended_action="Build", source_insights=["in_001"],
    )]


class TestPipelineRun:
    def test_collect_phase(self, sample_config, sample_signals, sample_insights, sample_opportunities):
        pipeline = Pipeline(sample_config)
        with patch.object(pipeline, "_collect_for_account", new=AsyncMock()) as mock_collect:
            mock_collect.return_value = sample_signals
            with patch.object(pipeline, "_run_understand") as mock_understand:
                mock_understand.return_value = ([], sample_insights)
                with patch.object(pipeline, "_run_recommend") as mock_recommend:
                    mock_recommend.return_value = sample_opportunities
                    with patch.object(pipeline.store, "create_snapshot", return_value="snap_001"):
                        with patch.object(pipeline.github, "close", AsyncMock()):
                            result = pipeline.run()
        assert result["snapshot_id"] == "snap_001"
        assert len(result["signals"]) == 3
        assert len(result["insights"]) == 1
        assert len(result["opportunities"]) == 1
