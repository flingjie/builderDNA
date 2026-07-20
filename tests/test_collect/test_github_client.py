"""Tests for async GitHub API client."""
import asyncio
import pytest
from collect.github.client import GitHubClient


@pytest.fixture
def client():
    return GitHubClient(token="ghp_test")


class TestGitHubClient:
    def test_get_repos_success(self, httpx_mock, client):
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated&type=owner",
            json=[{
                "id": 1, "full_name": "alice/toolkit", "language": "Python",
                "topics": ["llm", "agent"], "description": "An LLM agent toolkit",
                "stargazers_count": 42, "forks_count": 5,
                "updated_at": "2026-01-15T00:00:00Z",
            }],
            headers={"X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000",
                     "X-RateLimit-Reset": "9999999999"},
        )

        async def run():
            return await client.get_repos("alice")

        repos = asyncio.run(run())
        assert len(repos) == 1
        assert repos[0]["full_name"] == "alice/toolkit"

    def test_get_repos_404_returns_empty(self, httpx_mock, client):
        httpx_mock.add_response(
            url="https://api.github.com/users/nonexistent/repos?per_page=100&sort=updated&type=owner",
            status_code=404,
            headers={"X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000",
                     "X-RateLimit-Reset": "9999999999"},
        )

        async def run():
            return await client.get_repos("nonexistent")

        repos = asyncio.run(run())
        assert repos == []

    def test_get_repos_401_raises(self, httpx_mock):
        c = GitHubClient(token="bad_token")
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated&type=owner",
            status_code=401,
        )

        async def run():
            return await c.get_repos("alice")

        with pytest.raises(Exception):
            asyncio.run(run())

    def test_get_starred_success(self, httpx_mock, client):
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/starred?per_page=100",
            json=[{
                "id": 100, "full_name": "fastapi/fastapi", "language": "Python",
                "topics": ["web", "api"], "description": "FastAPI framework",
                "stargazers_count": 80000,
            }],
            headers={"X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000",
                     "X-RateLimit-Reset": "9999999999"},
        )

        async def run():
            return await client.get_starred("alice")

        starred = asyncio.run(run())
        assert len(starred) == 1
        assert starred[0]["full_name"] == "fastapi/fastapi"

    def test_get_user_success(self, httpx_mock, client):
        httpx_mock.add_response(
            url="https://api.github.com/users/alice",
            json={"login": "alice", "followers": 100, "public_repos": 50},
            headers={"etag": '"abc"', "X-RateLimit-Remaining": "4999",
                     "X-RateLimit-Limit": "5000", "X-RateLimit-Reset": "9999999999"},
        )

        async def run():
            return await client.get_user("alice")

        user = asyncio.run(run())
        assert user["login"] == "alice"
        assert user["followers"] == 100

    def test_rate_limit_429_handling(self, httpx_mock):
        c = GitHubClient(token="ghp_test")
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated&type=owner",
            status_code=429,
            headers={"Retry-After": "0", "X-RateLimit-Remaining": "0",
                     "X-RateLimit-Limit": "5000", "X-RateLimit-Reset": "9999999999"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated&type=owner",
            json=[],
            headers={"X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000",
                     "X-RateLimit-Reset": "9999999999"},
        )

        async def run():
            return await c.get_repos("alice")

        repos = asyncio.run(run())
        assert repos == []

    def test_cache_hit_on_etag_304(self, httpx_mock, tmp_path):
        c = GitHubClient(token="ghp_test", cache_dir=str(tmp_path))

        # First call: normal 200 response
        httpx_mock.add_response(
            url="https://api.github.com/users/alice",
            json={"login": "alice", "followers": 100},
            headers={"etag": '"v1"', "X-RateLimit-Remaining": "4999",
                     "X-RateLimit-Limit": "5000", "X-RateLimit-Reset": "9999999999"},
        )
        # Second call: 304 (cached, not modified)
        httpx_mock.add_response(
            url="https://api.github.com/users/alice",
            status_code=304,
            headers={"etag": '"v1"', "X-RateLimit-Remaining": "4998",
                     "X-RateLimit-Limit": "5000", "X-RateLimit-Reset": "9999999999"},
        )

        async def run():
            u1 = await c.get_user("alice")
            u2 = await c.get_user("alice")
            return u1, u2

        u1, u2 = asyncio.run(run())
        assert u1["login"] == "alice"
        assert u2["login"] == "alice"

    def test_get_total_stars_via_search(self, httpx_mock, tmp_path):
        c = GitHubClient(token="ghp_test", cache_dir=str(tmp_path))
        httpx_mock.add_response(
            url="https://api.github.com/search/repositories?q=user%3Aalice%2Bfork%3Atrue&per_page=100",
            json={
                "total_count": 150,
                "items": [
                    {"id": 1, "full_name": "alice/repo1", "stargazers_count": 30},
                    {"id": 2, "full_name": "alice/repo2", "stargazers_count": 12},
                ],
            },
            headers={"X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000",
                     "X-RateLimit-Reset": "9999999999"},
        )

        async def run():
            return await c.get_total_stars("alice")

        total_stars, repo_count = asyncio.run(run())
        assert total_stars == 42  # 30 + 12
        assert repo_count == 2

    def test_pagination_follows_link_header(self, httpx_mock, client):
        page1_url = "https://api.github.com/users/alice/repos?per_page=100&sort=updated&type=owner"
        page2_url = "https://api.github.com/users/alice/repos?page=2&per_page=100"

        httpx_mock.add_response(
            url=page1_url,
            json=[{"id": 1, "full_name": "alice/r1", "updated_at": "2026-01-01T00:00:00Z"}],
            headers={
                "Link": f'<{page2_url}>; rel="next"',
                "X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000",
                "X-RateLimit-Reset": "9999999999",
            },
        )
        httpx_mock.add_response(
            url=page2_url,
            json=[{"id": 2, "full_name": "alice/r2", "updated_at": "2026-01-02T00:00:00Z"}],
            headers={"X-RateLimit-Remaining": "4998", "X-RateLimit-Limit": "5000",
                     "X-RateLimit-Reset": "9999999999"},
        )

        async def run():
            return await client.get_repos("alice")

        repos = asyncio.run(run())
        assert len(repos) == 2
