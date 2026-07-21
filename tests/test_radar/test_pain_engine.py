"""Tests for pain mining engine."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from backend.engine.pain import (
    _compute_pain_score,
    _issue_to_pain_issue,
    fetch_issues,
    score_issues,
    cluster_pains,
    run_pain_mining,
)
from backend.models.pain import PainIssue, PainCluster, PainSnapshot


class FakeLLM:
    """Mock LLM client for testing."""

    def __init__(self, mock_response=None, side_effect=None):
        self.mock_response = mock_response or {}
        self.side_effect = side_effect
        self.call_count = 0
        self.last_prompt = None

    def complete(self, prompt, response_format=None):
        self.call_count += 1
        self.last_prompt = prompt
        if self.side_effect:
            raise self.side_effect
        return self.mock_response


class FakeGitHubClient:
    """Mock GitHub client for testing."""

    def __init__(self, issues_data=None):
        self.issues_data = issues_data or []

    async def _paginate(self, path, extra_params=None):
        if isinstance(self.issues_data, Exception):
            raise self.issues_data
        return self.issues_data


class TestComputePainScore:
    def test_base_pain_score(self):
        """Compute pain score with base score 3."""
        issue = PainIssue(
            repo="a/b", issue_number=1, title="test",
            comments=10, participants=5,
        )
        score = _compute_pain_score(issue, 3)
        # score = 3 * log(11) * log(6) ≈ 3 * 2.398 * 1.792 ≈ 12.86
        assert score > 0
        assert score < 50

    def test_no_comments_low_score(self):
        """Low comment count results in lower pain score."""
        issue = PainIssue(
            repo="a/b", issue_number=1, title="test",
            comments=0, participants=1,
        )
        score = _compute_pain_score(issue, 3)
        # score = 3 * log(1) * log(1) = 3 * 0 * 0 = 0
        assert score == 0

    def test_high_comments_high_score(self):
        """High comment count increases pain score."""
        issue = PainIssue(
            repo="a/b", issue_number=1, title="test",
            comments=100, participants=50,
        )
        score = _compute_pain_score(issue, 4)
        # score = 4 * log(101) * log(51) > 0
        assert score > 10


class TestIssueToPainIssue:
    def test_converts_raw_issue(self):
        """Convert raw dict to PainIssue."""
        raw = {
            "repo": "org/repo",
            "issue_number": 42,
            "title": "Bug: crashes on startup",
            "body": "Steps to reproduce...",
            "comments": 5,
            "participants": 6,
            "labels": ["bug", "critical"],
            "url": "https://github.com/org/repo/issues/42",
        }
        result = _issue_to_pain_issue(raw)
        assert result.repo == "org/repo"
        assert result.issue_number == 42
        assert result.title == "Bug: crashes on startup"
        assert result.body == "Steps to reproduce..."
        assert result.comments == 5
        assert result.participants == 6
        assert result.labels == ["bug", "critical"]
        assert result.url == "https://github.com/org/repo/issues/42"
        assert result.pain_score == 0.0

    def test_missing_fields(self):
        """Handle missing optional fields."""
        raw = {"repo": "a/b", "issue_number": 1}
        result = _issue_to_pain_issue(raw)
        assert result.repo == "a/b"
        assert result.title == ""
        assert result.body == ""
        assert result.comments == 0
        assert result.labels == []


class TestFetchIssues:
    @pytest.mark.asyncio
    async def test_fetches_issues_from_repo(self, mocker):
        """Fetch top issues from repository."""
        mock_client = FakeGitHubClient([
            {
                "number": 1,
                "title": "Crash on startup",
                "body": "App crashes immediately",
                "comments": 10,
                "html_url": "https://github.com/a/b/issues/1",
                "user": {"login": "user1"},
                "labels": [{"name": "bug"}, {"name": "critical"}],
                "pull_request": None,
            },
            {
                "number": 2,
                "title": "Memory leak",
                "body": "Memory grows over time",
                "comments": 5,
                "html_url": "https://github.com/a/b/issues/2",
                "user": {"login": "user2"},
                "labels": [{"name": "bug"}],
                "pull_request": None,
            },
        ])

        result = await fetch_issues(mock_client, "a/b", max_issues=20)

        assert len(result) == 2
        assert result[0]["repo"] == "a/b"
        assert result[0]["issue_number"] == 1
        assert result[0]["title"] == "Crash on startup"
        assert result[0]["comments"] == 10
        assert result[0]["participants"] == 6  # 1 + min(10, 5)
        assert result[0]["labels"] == ["bug", "critical"]

    @pytest.mark.asyncio
    async def test_skips_pull_requests(self, mocker):
        """PRs should be filtered out."""
        mock_client = FakeGitHubClient([
            {"number": 1, "title": "Issue", "body": "", "comments": 0,
             "html_url": "", "user": {}, "labels": [], "pull_request": None},
            {"number": 2, "title": "PR", "body": "", "comments": 0,
             "html_url": "", "user": {}, "labels": [], "pull_request": {}},
        ])

        result = await fetch_issues(mock_client, "a/b")
        assert len(result) == 1
        assert result[0]["issue_number"] == 1

    @pytest.mark.asyncio
    async def test_handles_empty_result(self, mocker):
        """Handle no issues found."""
        mock_client = FakeGitHubClient([])
        result = await fetch_issues(mock_client, "a/b")
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_error(self, mocker):
        """Handle API errors gracefully."""
        mock_client = FakeGitHubClient(Exception("API error"))
        result = await fetch_issues(mock_client, "a/b")
        assert result == []


class TestScoreIssues:
    @pytest.mark.asyncio
    async def test_scores_issues(self, mocker):
        """Score issues with LLM."""
        mock_llm = FakeLLM(mock_response={
            "scores": [
                {"issue_number": 1, "score": 5, "key_phrase": "crash"},
                {"issue_number": 2, "score": 2, "key_phrase": "slow"},
            ]
        })

        issues = [
            {"repo": "a/b", "issue_number": 1, "title": "Crash", "body": "",
             "comments": 10, "participants": 11, "labels": [], "url": ""},
            {"repo": "a/b", "issue_number": 2, "title": "Slow", "body": "",
             "comments": 5, "participants": 6, "labels": [], "url": ""},
        ]

        result = await score_issues(issues, mock_llm)

        assert len(result) == 2
        assert result[0].issue_number == 1
        assert result[0].pain_score > 0
        assert result[1].issue_number == 2
        assert result[1].pain_score > 0
        assert mock_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_input(self, mocker):
        """Handle empty issues list."""
        mock_llm = FakeLLM()

        result = await score_issues([], mock_llm)

        assert result == []
        assert mock_llm.call_count == 0

    @pytest.mark.asyncio
    async def test_llm_error_fallback(self, mocker):
        """Fallback when LLM fails."""
        mock_llm = FakeLLM(side_effect=Exception("LLM error"))

        issues = [
            {"repo": "a/b", "issue_number": 1, "title": "Crash", "body": "",
             "comments": 10, "participants": 11, "labels": [], "url": ""},
        ]

        result = await score_issues(issues, mock_llm)

        # Should return issues with pain_score=0 (base score 1 * log(1) * log(1) = 0)
        assert len(result) == 1
        assert result[0].pain_score == 0.0

    @pytest.mark.asyncio
    async def test_partial_llm_response(self, mocker):
        """Handle incomplete LLM response."""
        mock_llm = FakeLLM(mock_response={"scores": []})

        issues = [
            {"repo": "a/b", "issue_number": 1, "title": "Crash", "body": "",
             "comments": 10, "participants": 11, "labels": [], "url": ""},
        ]

        result = await score_issues(issues, mock_llm)

        assert len(result) == 1
        # Falls back to base score 1, which gives pain_score = 1 * log(11) * log(11) > 0
        assert result[0].pain_score > 0


class TestClusterPains:
    @pytest.mark.asyncio
    async def test_clusters_issues(self, mocker):
        """Cluster scored issues."""
        mock_llm = FakeLLM(mock_response={
            "clusters": [
                {
                    "title": "Crash Issues",
                    "root_cause": "Memory management problems",
                    "issue_numbers": [1, 3],
                    "severity": 4.5,
                },
                {
                    "title": "Performance",
                    "root_cause": "Inefficient algorithms",
                    "issue_numbers": [2],
                    "severity": 3.0,
                },
            ]
        })

        issues = [
            PainIssue(repo="a/b", issue_number=1, title="Crash", comments=10, participants=11, pain_score=5.0, labels=[]),
            PainIssue(repo="a/b", issue_number=2, title="Slow", comments=5, participants=6, pain_score=3.0, labels=[]),
            PainIssue(repo="a/b", issue_number=3, title="Another Crash", comments=8, participants=9, pain_score=4.0, labels=[]),
        ]

        result = await cluster_pains(issues, mock_llm)

        assert len(result) == 2
        assert result[0].title == "Crash Issues"
        assert result[0].severity == 4.5
        assert result[0].frequency == 2
        assert len(result[0].evidence) == 2
        assert result[1].title == "Performance"
        assert mock_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_input(self, mocker):
        """Handle empty issues list."""
        mock_llm = FakeLLM()

        result = await cluster_pains([], mock_llm)

        assert result == []
        assert mock_llm.call_count == 0

    @pytest.mark.asyncio
    async def test_llm_error_fallback(self, mocker):
        """Fallback when LLM fails - creates single cluster."""
        mock_llm = FakeLLM(side_effect=Exception("LLM error"))

        issues = [
            PainIssue(repo="a/b", issue_number=1, title="Crash", comments=10, participants=11, pain_score=4.0, labels=[]),
            PainIssue(repo="a/b", issue_number=2, title="Slow", comments=5, participants=6, pain_score=2.0, labels=[]),
        ]

        result = await cluster_pains(issues, mock_llm)

        assert len(result) == 1
        assert result[0].title == "Uncategorized Pain"
        assert result[0].frequency == 2

    @pytest.mark.asyncio
    async def test_no_issue_numbers_match(self, mocker):
        """Handle cluster with no matching issues."""
        mock_llm = FakeLLM(mock_response={
            "clusters": [
                {"title": "Test", "root_cause": "No issues", "issue_numbers": [999], "severity": 3.0},
            ]
        })

        issues = [
            PainIssue(repo="a/b", issue_number=1, title="Crash", comments=10, participants=11, pain_score=4.0, labels=[]),
        ]

        result = await cluster_pains(issues, mock_llm)

        assert len(result) == 1
        assert result[0].frequency == 0  # No matching issues
        assert result[0].affected_repos == []


class TestRunPainMining:
    @pytest.mark.asyncio
    async def test_runs_full_pipeline(self, mocker):
        """Run full pain mining pipeline."""
        # Mock GitHub client
        mock_client = FakeGitHubClient([
            {
                "number": 1,
                "title": "Critical Bug",
                "body": "Crashes the app",
                "comments": 20,
                "html_url": "https://github.com/a/b/issues/1",
                "user": {"login": "user1"},
                "labels": [{"name": "bug"}],
                "pull_request": None,
            },
        ])

        # Mock LLM
        mock_llm = FakeLLM(mock_response={
            "scores": [{"issue_number": 1, "score": 5, "key_phrase": "critical crash"}],
            "clusters": [{"title": "Critical Issues", "root_cause": "Bug in core", "issue_numbers": [1], "severity": 5}],
        })

        # Mock store
        mock_store = mocker.MagicMock()

        result = await run_pain_mining(mock_client, ["a/b"], mock_llm, mock_store)

        assert result.issue_count == 1
        assert result.repos_analyzed == ["a/b"]
        assert len(result.clusters) == 1
        assert result.clusters[0].title == "Critical Issues"
        mock_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_repos(self, mocker):
        """Handle empty repo list."""
        mock_client = mocker.MagicMock()
        mock_llm = FakeLLM()
        mock_store = mocker.MagicMock()

        result = await run_pain_mining(mock_client, [], mock_llm, mock_store)

        assert result.issue_count == 0
        assert result.clusters == []
        mock_store.save.assert_called_once()
