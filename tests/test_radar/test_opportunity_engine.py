"""Tests for opportunity engine."""

import json
import pytest
from datetime import datetime, timezone

from backend.engine.opportunity import (
    format_trends_for_llm,
    format_pains_for_llm,
    generate_opportunities,
    run_opportunity_engine,
)
from backend.models.trend import TrendSnapshot, TopicTrend, RepoTrend
from backend.models.pain import PainSnapshot, PainCluster
from backend.models.opportunity import (
    OpportunityCard,
    OpportunityEvidence,
    OpportunitySnapshot,
)


# Mock LLM client for testing
class MockLLM:
    def __init__(self, response_data=None, error=None):
        self.response_data = response_data
        self.error = error

    def complete(self, prompt, response_format=None):
        if self.error:
            raise self.error
        if self.response_data:
            return self.response_data
        # Default mock response
        return {
            "opportunities": [
                {
                    "title": "Test Opportunity",
                    "why_now": "Because now is the time",
                    "problem": "There is a problem",
                    "evidence": {
                        "trends": ["test_trend"],
                        "pain_clusters": ["test_pain"],
                        "key_issues": ["repo/issue#1"],
                        "key_repos": ["repo/user"],
                    },
                    "existing_solutions": ["old_tool"],
                    "gap": "No good solution exists",
                    "mvp": "1. Build it\n2. Test it",
                    "score": 7.5,
                    "risk": "medium",
                }
            ]
        }


class FakeLLMResponse:
    def __init__(self, content):
        self.content = content


class TestFormatTrendsForLLM:
    def test_empty_snapshot(self):
        snapshot = TrendSnapshot(domain="test", window_days=30)
        result = format_trends_for_llm(snapshot)
        assert result == ""

    def test_single_topic(self):
        snapshot = TrendSnapshot(
            domain="test",
            window_days=30,
            topics=[
                TopicTrend(
                    topic="agent",
                    stage="accelerating",
                    confidence=0.8,
                    growth_velocity=25.5,
                    evidence_count=10,
                    top_repos=[
                        RepoTrend(
                            full_name="agent-org/agent",
                            stars=1000,
                            stars_delta=100,
                            forks=50,
                            contributors=20,
                            velocity=1.5,
                            trend_score=50.0,
                            days_since_first_release=30,
                        )
                    ],
                )
            ],
        )
        result = format_trends_for_llm(snapshot)
        assert "Topic: agent" in result
        assert "Stage: accelerating" in result
        assert "Velocity: 25.50" in result
        assert "agent-org/agent" in result

    def test_multiple_topics(self):
        snapshot = TrendSnapshot(
            domain="test",
            window_days=30,
            topics=[
                TopicTrend(
                    topic=f"topic{i}",
                    stage="emerging",
                    confidence=0.5,
                    growth_velocity=10.0,
                    evidence_count=5,
                    top_repos=[RepoTrend(full_name=f"repo{i}", stars=100, stars_delta=10, forks=5, contributors=10, velocity=1.0, trend_score=20.0, days_since_first_release=60)]
                )
                for i in range(7)
            ],
        )
        result = format_trends_for_llm(snapshot)
        lines = result.split("\n")
        assert len(lines) == 5  # Max 5 topics

    def test_format_structure(self):
        snapshot = TrendSnapshot(
            domain="test",
            window_days=30,
            topics=[
                TopicTrend(
                    topic="mcp",
                    stage="emerging",
                    confidence=0.7,
                    growth_velocity=15.3,
                    evidence_count=8,
                    top_repos=[
                        RepoTrend(full_name="org/repo1", stars=500, stars_delta=50, forks=25, contributors=15, velocity=2.0, trend_score=30.0, days_since_first_release=45),
                        RepoTrend(full_name="org/repo2", stars=300, stars_delta=30, forks=15, contributors=10, velocity=1.5, trend_score=20.0, days_since_first_release=50),
                        RepoTrend(full_name="org/repo3", stars=200, stars_delta=20, forks=10, contributors=8, velocity=1.0, trend_score=15.0, days_since_first_release=55),
                        RepoTrend(full_name="org/repo4", stars=100, stars_delta=10, forks=5, contributors=5, velocity=0.5, trend_score=10.0, days_since_first_release=60),
                    ],
                )
            ],
        )
        result = format_trends_for_llm(snapshot)
        assert "Topic: mcp" in result
        assert "Stage: emerging" in result
        assert "Velocity: 15.30" in result
        # Should only include top 3 repos
        assert "org/repo1" in result
        assert "org/repo2" in result
        assert "org/repo3" in result
        assert "org/repo4" not in result


class TestFormatPainsForLLM:
    def test_empty_snapshot(self):
        snapshot = PainSnapshot(domain="test")
        result = format_pains_for_llm(snapshot)
        assert result == ""

    def test_single_cluster(self):
        snapshot = PainSnapshot(
            domain="test",
            clusters=[
                PainCluster(
                    id="cluster1",
                    title="Debugging Issues",
                    severity=3.5,
                    frequency=5,
                    description="Lack of agent state persistence",
                    affected_repos=["org/agent1", "org/agent2"],
                )
            ],
        )
        result = format_pains_for_llm(snapshot)
        assert "Pain: Debugging Issues" in result
        assert "Severity: 3.50" in result
        assert "Lack of agent state persistence" in result
        assert "org/agent1" in result

    def test_multiple_clusters(self):
        snapshot = PainSnapshot(
            domain="test",
            clusters=[
                PainCluster(
                    title=f"pain{i}",
                    severity=float(i),
                    frequency=3,
                    description=f"root cause {i}",
                    affected_repos=[f"repo{i}"],
                )
                for i in range(7)
            ],
        )
        result = format_pains_for_llm(snapshot)
        lines = result.split("\n")
        assert len(lines) == 5  # Max 5 clusters

    def test_max_3_affected_repos(self):
        snapshot = PainSnapshot(
            domain="test",
            clusters=[
                PainCluster(
                    title="MultiRepo Pain",
                    severity=2.5,
                    frequency=3,
                    description="Some problem",
                    affected_repos=["r1", "r2", "r3", "r4", "r5"],
                )
            ],
        )
        result = format_pains_for_llm(snapshot)
        assert "r1" in result
        assert "r2" in result
        assert "r3" in result
        assert "r4" not in result
        assert "r5" not in result


class TestGenerateOpportunitiesWithMockLLM:
    @pytest.mark.asyncio
    async def test_success_generation(self):
        mock_llm = MockLLM()
        trend = TrendSnapshot(domain="test", window_days=30)
        pain = PainSnapshot(domain="test")

        cards = await generate_opportunities(trend, pain, mock_llm)

        assert len(cards) == 1
        assert cards[0].title == "Test Opportunity"
        assert cards[0].why_now == "Because now is the time"
        assert cards[0].score == 7.5
        assert cards[0].risk == "medium"

    @pytest.mark.asyncio
    async def test_empty_opportunities_list(self):
        mock_llm = MockLLM(response_data={"opportunities": []})
        trend = TrendSnapshot(domain="test", window_days=30)
        pain = PainSnapshot(domain="test")

        cards = await generate_opportunities(trend, pain, mock_llm)

        assert len(cards) == 0

    @pytest.mark.asyncio
    async def test_missing_opportunities_key(self):
        mock_llm = MockLLM(response_data={"other_key": []})
        trend = TrendSnapshot(domain="test", window_days=30)
        pain = PainSnapshot(domain="test")

        cards = await generate_opportunities(trend, pain, mock_llm)

        assert len(cards) == 0


class TestGenerateEmptyOnLLMError:
    @pytest.mark.asyncio
    async def test_llm_error_returns_empty_list(self):
        class ErrorLLM:
            def complete(self, prompt, response_format=None):
                raise Exception("API Error")

        mock_llm = ErrorLLM()
        trend = TrendSnapshot(domain="test", window_days=30)
        pain = PainSnapshot(domain="test")

        cards = await generate_opportunities(trend, pain, mock_llm)

        assert cards == []

    @pytest.mark.asyncio
    async def test_invalid_json_response(self):
        class BadJSONLLM:
            def complete(self, prompt, response_format=None):
                # Returns something that's not JSON and not parseable
                raise json.JSONDecodeError("Invalid", "", 0)

        mock_llm = BadJSONLLM()
        trend = TrendSnapshot(domain="test", window_days=30)
        pain = PainSnapshot(domain="test")

        cards = await generate_opportunities(trend, pain, mock_llm)

        assert cards == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
