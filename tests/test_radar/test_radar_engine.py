"""Tests for radar engine trend computation."""
import math
from datetime import datetime, timezone, timedelta

import pytest

from backend.engine.radar import compute_repo_trend, aggregate_topic, get_stage, _days_since
from backend.models.trend import RepoTrend, TopicTrend, TrendSnapshot


class TestComputeRepoTrend:
    def test_first_run_uses_velocity(self):
        """First run uses days_since_first_release for velocity."""
        repo_data = {
            "full_name": "org/repo",
            "stargazers_count": 600,
            "forks_count": 50,
            "created_at": "2026-05-01T00:00:00Z",
        }
        result = compute_repo_trend(repo_data, prev_snapshot=None, contributors=10)
        assert result.full_name == "org/repo"
        assert result.stars == 600
        assert result.forks == 50
        assert result.velocity > 0
        assert result.trend_score > 0
        assert result.days_since_first_release > 0

    def test_second_run_uses_acceleration(self):
        """Second run compares against previous snapshot for acceleration."""
        repo_data = {
            "full_name": "org/repo",
            "stargazers_count": 900,
            "forks_count": 60,
            "created_at": "2026-01-01T00:00:00Z",
        }
        prev = TrendSnapshot(
            domain="agent", window_days=60,
            topics=[TopicTrend(
                topic="mcp", stage="emerging", confidence=0.8,
                growth_velocity=1.0, evidence_count=1,
                top_repos=[RepoTrend(
                    full_name="org/repo", stars=600, forks=50,
                    contributors=8, velocity=5.0, trend_score=50.0,
                )],
            )],
        )
        prev.created_at = datetime.now(timezone.utc) - timedelta(days=30)

        result = compute_repo_trend(repo_data, prev_snapshot=prev, contributors=12)

        assert result.stars == 900
        assert result.velocity > 5.0  # velocity should increase from 5.0
        assert result.trend_score != 0.0
        assert result.contributor_growth == 0.5  # (12-8)/8

    def test_no_prev_repo_falls_back_to_velocity(self):
        """If repo not found in previous snapshot, use 1st-order."""
        repo_data = {
            "full_name": "new/repo",
            "stargazers_count": 300,
            "forks_count": 10,
            "created_at": "2026-06-01T00:00:00Z",
        }
        prev = TrendSnapshot(domain="agent", window_days=60)
        result = compute_repo_trend(repo_data, prev_snapshot=prev, contributors=3)
        assert result.full_name == "new/repo"
        assert result.stars == 300
        assert result.velocity > 0


class TestGetStage:
    def test_stage_boundaries(self):
        assert get_stage(85.0) == "accelerating"
        assert get_stage(60.0) == "emerging"
        assert get_stage(35.0) == "mainstream"
        assert get_stage(10.0) == "declining"

    def test_exact_boundaries(self):
        assert get_stage(80.0) == "accelerating"
        assert get_stage(50.0) == "emerging"
        assert get_stage(20.0) == "mainstream"


class TestAggregateTopic:
    def test_aggregates_and_sorts_repos(self):
        repos = [
            RepoTrend(full_name="a/r1", stars=100, forks=5, contributors=3,
                      trend_score=90.0, velocity=3.0),
            RepoTrend(full_name="b/r2", stars=200, forks=8, contributors=5,
                      trend_score=70.0, velocity=2.0),
            RepoTrend(full_name="c/r3", stars=50, forks=2, contributors=1,
                      trend_score=15.0, velocity=1.0),
        ]
        result = aggregate_topic(repos, "mcp")
        assert result.topic == "mcp"
        assert result.evidence_count == 3
        assert len(result.top_repos) == 3
        # Sorted desc by trend_score
        assert result.top_repos[0].trend_score == 90.0
        assert result.top_repos[1].trend_score == 70.0
        # Stage: avg of top 5 = (90+70+15)/3 ≈ 58.3 → emerging
        assert result.stage == "emerging"

    def test_empty_repos(self):
        result = aggregate_topic([], "empty")
        assert result.stage == "declining"
        assert result.evidence_count == 0
        assert result.top_repos == []

    def test_top_5_limit(self):
        repos = [
            RepoTrend(full_name=f"a/r{i}", stars=100, forks=5, contributors=3,
                      trend_score=100.0 - i, velocity=1.0)
            for i in range(10)
        ]
        result = aggregate_topic(repos, "big")
        assert len(result.top_repos) == 5  # capped at 5
        assert result.evidence_count == 10  # total count preserved
