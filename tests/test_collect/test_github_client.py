"""Tests for GitHub API client."""

import pytest

from collect.github.client import GitHubClient


class TestGitHubClient:
    def test_get_repos_success(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated",
            json=[
                {
                    "id": 1,
                    "full_name": "alice/toolkit",
                    "language": "Python",
                    "topics": ["llm", "agent"],
                    "description": "An LLM agent toolkit",
                    "stargazers_count": 42,
                    "forks_count": 5,
                    "updated_at": "2026-01-15T00:00:00Z",
                }
            ],
        )
        client = GitHubClient(token="ghp_test")
        repos = client.get_repos("alice")
        assert len(repos) == 1
        assert repos[0]["full_name"] == "alice/toolkit"

    def test_get_repos_404_returns_empty(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.github.com/users/nonexistent/repos?per_page=100&sort=updated",
            status_code=404,
        )
        client = GitHubClient(token="ghp_test")
        repos = client.get_repos("nonexistent")
        assert repos == []

    def test_get_repos_401_raises(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated",
            status_code=401,
        )
        client = GitHubClient(token="bad_token")
        with pytest.raises(Exception):
            client.get_repos("alice")

    def test_get_starred_success(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/starred?per_page=100&sort=updated",
            json=[
                {
                    "id": 100,
                    "full_name": "fastapi/fastapi",
                    "language": "Python",
                    "topics": ["web", "api"],
                    "description": "FastAPI framework",
                    "stargazers_count": 80000,
                }
            ],
        )
        client = GitHubClient(token="ghp_test")
        starred = client.get_starred("alice")
        assert len(starred) == 1
        assert starred[0]["full_name"] == "fastapi/fastapi"

    def test_rate_limit_handling(self, httpx_mock):
        """Rate limit should retry after waiting."""
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated",
            status_code=403,
            headers={"X-RateLimit-Remaining": "0", "Retry-After": "0"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated",
            json=[],
        )
        client = GitHubClient(token="ghp_test", max_retries=1, base_delay=0.0)
        repos = client.get_repos("alice")
        assert repos == []
