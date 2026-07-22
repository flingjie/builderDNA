"""Tests for collector normalizer."""
from datetime import datetime, timezone
from collector.normalizer import normalize_repo, normalize_issue, normalize_all


class TestNormalizeRepo:
    def test_normalizes_minimal_repo(self):
        raw = {
            "full_name": "org/repo",
            "owner": {"login": "org"},
            "stargazers_count": 100,
            "forks_count": 20,
            "topics": ["agent"],
            "description": "Test repo",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-06-01T00:00:00Z",
        }
        signal = normalize_repo(raw)
        assert signal.type == "repo_created"
        assert signal.target_repo == "org/repo"
        assert signal.actor == "org"
        assert signal.velocity > 0
        assert "topics" in signal.payload

    def test_normalizes_repo_without_topics(self):
        raw = {
            "full_name": "org/bare",
            "owner": {"login": "dev"},
            "stargazers_count": 0,
            "forks_count": 0,
            "topics": [],
            "description": "",
            "created_at": "2026-01-01T00:00:00Z",
        }
        signal = normalize_repo(raw)
        assert signal.payload["topics"] == []


class TestNormalizeIssue:
    def test_normalizes_issue(self):
        raw = {
            "repo": "org/repo",
            "issue_number": 42,
            "title": "Bug: crash on start",
            "body": "App crashes when...",
            "comments": 15,
            "participants": 8,
            "labels": ["bug", "critical"],
            "url": "https://github.com/org/repo/issues/42",
            "user_login": "reporter",
        }
        signal = normalize_issue(raw)
        assert signal.type == "issue_opened"
        assert signal.target_repo == "org/repo"
        assert signal.actor == "reporter"
        assert signal.payload["issue_number"] == 42


class TestNormalizeAll:
    def test_normalizes_batch(self):
        repos = [{
            "full_name": "org/repo1",
            "owner": {"login": "org"},
            "stargazers_count": 500,
            "forks_count": 20,
            "topics": ["agent"],
            "description": "Repo 1",
            "created_at": "2026-06-01T00:00:00Z",
        }]
        issues = [{
            "repo": "org/repo1",
            "issue_number": 1,
            "title": "Issue 1",
            "body": "Body",
            "comments": 5,
            "participants": 3,
            "labels": [],
            "url": "https://github.com/org/repo1/issues/1",
            "user_login": "dev",
        }]
        signals = normalize_all(raw_repos=repos, raw_issues=issues, raw_stars=[])
        assert len(signals) == 2
        types = {s.type for s in signals}
        assert "repo_created" in types
        assert "issue_opened" in types
