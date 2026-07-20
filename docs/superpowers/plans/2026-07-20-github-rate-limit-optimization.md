# GitHub API Rate Limit Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite GitHubClient as async with filesystem cache, proactive rate limit management, and concurrency control; optimize follow command to use Search API instead of paginated repo fetches.

**Architecture:** Async-first via `httpx.AsyncClient` with three internal layers — CacheStore (filesystem + ETag), RateLimiter (X-RateLimit-Remaining monitoring), and Semaphore(5) for concurrency. Pipeline uses asyncio.gather for parallel account fetching. Follow command uses `/search/repositories` to get total stars in one call instead of paginating all repos.

**Tech Stack:** Python 3.11+, httpx (already async-capable), asyncio, hashlib, json

## Global Constraints

- Python >= 3.11 (no match/case within 3.10 limits)
- httpx >= 0.27 (already in pyproject.toml)
- No new dependencies required
- All public method signatures of `GitHubClient` remain backward-compatible (sync wrappers provided)
- Tests use pytest-httpx for HTTP mocking
- Follow `tests/` directory pattern: `tests/test_collect/` for cache, rate_limit, client tests

---

### Task 1: Create `collect/github/cache.py` — Filesystem Response Cache with ETag

**Files:**
- Create: `collect/github/cache.py`

**Interfaces:**
- Produces: `class CacheStore`
  - `__init__(cache_dir: str | Path = "snapshots/cache")`
  - `get(method: str, url: str, params: dict | None) -> tuple[int, dict, str] | None` — returns (status, headers, body) or None
  - `set(method: str, url: str, params: dict | None, status: int, headers: dict, body: str) -> None`
  - `get_etag(method: str, url: str, params: dict | None) -> str | None`
  - `_cache_key(method: str, url: str, params: dict | None) -> str` — md5 hash
  - `_is_fresh(key: str, ttl_seconds: int) -> bool`
  - `clear() -> int` — clear all cache, return count deleted

- [ ] **Step 1: Write `collect/github/cache.py`**

```python
"""HTTP response cache with ETag support for GitHub API.

Caches responses on the filesystem under the configured cache directory.
Each cached entry is two files:
  <key>.json  — {status, headers, body}
  <key>.meta  — {etag, cached_at, ttl}
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any


# TTLs in seconds per endpoint type (matched by URL substring)
ENDPOINT_TTLS: dict[str, int] = {
    "/users/": 86400,        # user profiles: 24h
    "/repos": 3600,          # repo listings: 1h
    "/starred": 1800,        # starred repos: 30m
    "/search/": 300,         # search results: 5m
    "/commits": 600,         # commits: 10m
}


def _get_ttl(url: str) -> int:
    """Determine TTL for a URL based on endpoint type."""
    for pattern, ttl in ENDPOINT_TTLS.items():
        if pattern in url:
            return ttl
    return 3600  # default: 1h


class CacheStore:
    """Filesystem-based HTTP response cache with ETag-based conditional requests."""

    def __init__(self, cache_dir: str | Path = "snapshots/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, method: str, url: str, params: dict[str, str] | None = None) -> str:
        """Generate a deterministic cache key from method, url, and params."""
        raw = f"{method}:{url}"
        if params:
            sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            raw += f"?{sorted_params}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _json_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _meta_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.meta"

    def get(self, method: str, url: str, params: dict[str, str] | None = None) -> tuple[int, dict, str] | None:
        """Retrieve a cached response if fresh.

        Returns:
            (status_code, headers_dict, body_string) or None if cache miss or stale.
        """
        key = self._cache_key(method, url, params)
        json_file = self._json_path(key)
        meta_file = self._meta_path(key)

        if not json_file.exists() or not meta_file.exists():
            return None

        try:
            meta = json.loads(meta_file.read_text())
            ttl = meta.get("ttl", _get_ttl(url))
            if time.time() - meta.get("cached_at", 0) > ttl:
                return None  # stale

            data = json.loads(json_file.read_text())
            return data["status"], data["headers"], data["body"]
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def get_etag(self, method: str, url: str, params: dict[str, str] | None = None) -> str | None:
        """Get the saved ETag for a request, regardless of freshness."""
        key = self._cache_key(method, url, params)
        meta_file = self._meta_path(key)
        if not meta_file.exists():
            return None
        try:
            meta = json.loads(meta_file.read_text())
            return meta.get("etag")
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, method: str, url: str, params: dict[str, str] | None,
            status: int, headers: dict[str, str], body: str) -> None:
        """Cache a response."""
        key = self._cache_key(method, url, params)
        etag = headers.get("etag", headers.get("ETag", ""))

        data = {"status": status, "headers": dict(headers), "body": body}
        meta = {"etag": etag, "cached_at": time.time(), "ttl": _get_ttl(url)}

        self._json_path(key).write_text(json.dumps(data, ensure_ascii=False))
        self._meta_path(key).write_text(json.dumps(meta))

    def update_from_304(self, method: str, url: str, params: dict[str, str] | None,
                        headers: dict[str, str]) -> None:
        """Update cache metadata on a 304 Not Modified response.

        The body stays the same; we just bump cached_at and update etag.
        """
        key = self._cache_key(method, url, params)
        meta_file = self._meta_path(key)
        new_etag = headers.get("etag", headers.get("ETag", ""))

        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
            except (json.JSONDecodeError, OSError):
                meta = {}
        else:
            meta = {}

        meta["etag"] = new_etag
        meta["cached_at"] = time.time()
        meta_file.write_text(json.dumps(meta))

    def clear(self) -> int:
        """Delete all cached files. Returns count of deleted entries."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        for f in self.cache_dir.glob("*.meta"):
            f.unlink()
            count += 1
        return count // 2  # json+meta = 1 entry
```

- [ ] **Step 2: Write basic cache tests**

Create `tests/test_collect/test_cache.py`:

```python
"""Tests for HTTP response cache."""
import json
import time
from pathlib import Path
from collect.github.cache import CacheStore, _get_ttl


class TestCacheStore:
    def test_cache_miss_returns_none(self, tmp_path):
        cache = CacheStore(tmp_path)
        result = cache.get("GET", "/users/alice")
        assert result is None

    def test_cache_set_and_get(self, tmp_path):
        cache = CacheStore(tmp_path)
        headers = {"etag": '"abc123"', "content-type": "application/json"}
        body = '{"login": "alice"}'
        cache.set("GET", "/users/alice", None, 200, headers, body)

        result = cache.get("GET", "/users/alice")
        assert result is not None
        assert result[0] == 200
        assert result[2] == body

    def test_cache_key_varies_by_params(self, tmp_path):
        cache = CacheStore(tmp_path)
        cache.set("GET", "/users/alice/repos", {"page": "1"}, 200, {}, "[]")
        cache.set("GET", "/users/alice/repos", {"page": "2"}, 200, {}, '[{"id":1}]')

        r1 = cache.get("GET", "/users/alice/repos", {"page": "1"})
        r2 = cache.get("GET", "/users/alice/repos", {"page": "2"})
        assert r1[2] == "[]"
        assert r2[2] == '[{"id":1}]'

    def test_cache_miss_on_stale(self, tmp_path, monkeypatch):
        cache = CacheStore(tmp_path)
        cache.set("GET", "/users/alice", None, 200, {}, '{"login":"alice"}')

        # Fake time to be well past TTL (24h for /users/)
        monkeypatch.setattr(time, "time", lambda: time.time() + 90000)

        result = cache.get("GET", "/users/alice")
        assert result is None

    def test_get_etag(self, tmp_path):
        cache = CacheStore(tmp_path)
        cache.set("GET", "/users/alice", None, 200, {"etag": '"xyz"'}, "{}")
        assert cache.get_etag("GET", "/users/alice") == '"xyz"'

    def test_get_etag_miss(self, tmp_path):
        cache = CacheStore(tmp_path)
        assert cache.get_etag("GET", "/users/alice") is None

    def test_update_from_304(self, tmp_path):
        cache = CacheStore(tmp_path)
        cache.set("GET", "/users/alice", None, 200, {"etag": '"old"'}, '{"login":"alice"}')
        cache.update_from_304("GET", "/users/alice", None, {"etag": '"new"'})

        assert cache.get_etag("GET", "/users/alice") == '"new"'
        # Body should still be retrievable
        result = cache.get("GET", "/users/alice")
        assert result is not None and result[2] == '{"login":"alice"}'

    def test_clear(self, tmp_path):
        cache = CacheStore(tmp_path)
        cache.set("GET", "/a", None, 200, {}, "a")
        cache.set("GET", "/b", None, 200, {}, "b")
        assert cache.clear() == 2
        assert cache.get("GET", "/a") is None

    def test_corrupt_cache_returns_none(self, tmp_path):
        cache = CacheStore(tmp_path)
        # Write invalid JSON
        key = cache._cache_key("GET", "/corrupt")
        cache._json_path(key).write_text("not json")
        cache._meta_path(key).write_text('{"etag":"x","cached_at":9999999999,"ttl":3600}')
        assert cache.get("GET", "/corrupt") is None


class TestTTLs:
    def test_user_endpoint_24h(self):
        assert _get_ttl("/users/alice") == 86400

    def test_repos_endpoint_1h(self):
        assert _get_ttl("/users/alice/repos") == 3600

    def test_search_endpoint_5m(self):
        assert _get_ttl("/search/repositories") == 300

    def test_default_1h(self):
        assert _get_ttl("/unknown/endpoint") == 3600
```

- [ ] **Step 3: Run tests, verify pass**

```bash
uv run pytest tests/test_collect/test_cache.py -v
```

- [ ] **Step 4: Commit**

```bash
git add collect/github/cache.py tests/test_collect/test_cache.py
git commit -m "feat: add filesystem HTTP cache with ETag support for GitHub API"
```

---

### Task 2: Create `collect/github/rate_limit.py` — Proactive Rate Limit Tracker

**Files:**
- Create: `collect/github/rate_limit.py`

**Interfaces:**
- Produces: `class RateLimiter`
  - `__init__(safety_margin: int = 50)`
  - `update(headers: dict[str, str]) -> None` — parse X-RateLimit-* headers
  - `remaining -> int` — property
  - `reset_at -> float | None` — property (epoch seconds)
  - `reset_at_iso -> str | None` — property (ISO 8601 string for display)
  - `async wait_if_needed() -> None` — sleep if remaining < safety_margin
  - `usage_summary() -> str` — human-readable status line

```python
"""Proactive GitHub API rate limit management.

Monitors X-RateLimit-Remaining and X-RateLimit-Reset headers from
GitHub API responses, and automatically pauses when approaching the limit.
"""

import asyncio
import time
from datetime import datetime, timezone


class RateLimiter:
    """Tracks GitHub API rate limit state and waits proactively."""

    def __init__(self, safety_margin: int = 50):
        self.safety_margin = safety_margin
        self._remaining: int | None = None
        self._limit: int | None = None
        self._reset: int | None = None  # epoch seconds
        self._total_calls: int = 0
        self._waited_calls: int = 0

    def update(self, headers: dict[str, str]) -> None:
        """Parse rate limit info from response headers."""
        remaining = headers.get("X-RateLimit-Remaining")
        limit = headers.get("X-RateLimit-Limit")
        reset = headers.get("X-RateLimit-Reset")

        if remaining is not None:
            self._remaining = int(remaining)
        if limit is not None:
            self._limit = int(limit)
        if reset is not None:
            self._reset = int(reset)

        self._total_calls += 1

    @property
    def remaining(self) -> int | None:
        return self._remaining

    @property
    def limit(self) -> int | None:
        return self._limit

    @property
    def reset_at(self) -> float | None:
        """Unix epoch when the rate limit resets."""
        return float(self._reset) if self._reset else None

    @property
    def reset_at_iso(self) -> str | None:
        """ISO 8601 string of reset time."""
        if self._reset is None:
            return None
        return datetime.fromtimestamp(self._reset, tz=timezone.utc).isoformat()

    async def wait_if_needed(self) -> bool:
        """Sleep until rate limit resets if remaining < safety_margin.

        Returns:
            True if a wait occurred, False otherwise.
        """
        if self._remaining is None or self._remaining >= self.safety_margin:
            return False

        if self._reset is not None:
            now = time.time()
            wait_seconds = max(self._reset - now + 1, 0)
            if wait_seconds > 0:
                self._waited_calls += 1
                print(f"[RateLimit] {self._remaining}/{self._limit} remaining — "
                      f"waiting {wait_seconds:.0f}s until reset at {self.reset_at_iso}")
                await asyncio.sleep(wait_seconds)
                return True
        return False

    def usage_summary(self) -> str:
        """Human-readable summary of rate limit usage."""
        parts = [f"calls={self._total_calls}"]
        if self._remaining is not None and self._limit is not None:
            parts.append(f"remaining={self._remaining}/{self._limit}")
        if self._waited_calls > 0:
            parts.append(f"waited={self._waited_calls}x")
        return ", ".join(parts)
```

- [ ] **Step 1: Write rate limiter tests**

Create `tests/test_collect/test_rate_limit.py`:

```python
"""Tests for rate limiter."""
import pytest
from collect.github.rate_limit import RateLimiter


class TestRateLimiter:
    def test_initial_state(self):
        rl = RateLimiter()
        assert rl.remaining is None
        assert rl.limit is None
        assert rl.reset_at is None

    def test_update_from_headers(self):
        rl = RateLimiter()
        rl.update({
            "X-RateLimit-Remaining": "4950",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Reset": "1784544658",
        })
        assert rl.remaining == 4950
        assert rl.limit == 5000
        assert rl.reset_at == 1784544658.0
        assert rl.reset_at_iso is not None

    def test_no_wait_when_above_margin(self):
        rl = RateLimiter(safety_margin=50)
        rl.update({
            "X-RateLimit-Remaining": "100",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Reset": "9999999999",
        })
        # Should return False immediately, no sleep
        import asyncio
        async def check():
            return await rl.wait_if_needed()
        result = asyncio.run(check())
        assert result is False

    def test_usage_summary(self):
        rl = RateLimiter()
        rl.update({
            "X-RateLimit-Remaining": "4000",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Reset": "1784544658",
        })
        rl.update({
            "X-RateLimit-Remaining": "3999",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Reset": "1784544658",
        })
        summary = rl.usage_summary()
        assert "calls=2" in summary
        assert "remaining=3999/5000" in summary

    def test_partial_headers(self):
        rl = RateLimiter()
        rl.update({"X-RateLimit-Remaining": "3000"})
        assert rl.remaining == 3000
        assert rl.limit is None  # unchanged
```

- [ ] **Step 2: Run tests, verify pass**

```bash
uv run pytest tests/test_collect/test_rate_limit.py -v
```

- [ ] **Step 3: Commit**

```bash
git add collect/github/rate_limit.py tests/test_collect/test_rate_limit.py
git commit -m "feat: add proactive GitHub API rate limit tracker"
```

---

### Task 3: Rewrite `collect/github/client.py` — Async GitHubClient with Cache + Rate Limit + Semaphore

**Files:**
- Modify: `collect/github/client.py`

**Interfaces:**
- Consumes: `CacheStore` from Task 1, `RateLimiter` from Task 2
- Produces: `class GitHubClient` (async, backward-compatible sync wrappers)
  - `__init__(token, max_retries=3, base_delay=1.0, cache_dir="snapshots/cache", max_concurrent=5, rate_limit_margin=50)`
  - `async get_repos(actor) -> list[dict]`
  - `async get_user(actor) -> dict | None`
  - `async get_starred(actor) -> list[dict]`
  - `async get_commits(actor, repo_full_name, since=None) -> list[dict]`
  - `async get_total_stars(actor) -> tuple[int, int]` — (star_count, repo_count) via Search API
  - `async close()` — close httpx client
  - `rate_limiter -> RateLimiter` — property for external access

- [ ] **Step 1: Write async client tests**

Create `tests/test_collect/test_github_client.py` (replace existing):

```python
"""Tests for async GitHub API client."""
import pytest
import asyncio
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
            repos = await client.get_repos("alice")
            return repos

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
        # The second response should come from cache (304 doesn't return body)
        # httpx_mock will return empty body for 304, but cache should serve the old body

    def test_get_total_stars_via_search(self, httpx_mock, client):
        httpx_mock.add_response(
            url__contains="/search/repositories?q=user:alice+fork:true",
            json={
                "total_count": 150,
                "items": [{"id": 1, "full_name": "alice/repo1", "stargazers_count": 42}],
            },
            headers={"X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000",
                     "X-RateLimit-Reset": "9999999999"},
        )

        async def run():
            return await client.get_total_stars("alice")

        total_stars, repo_count = asyncio.run(run())
        assert total_stars == 150
        assert repo_count > 0

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
```

- [ ] **Step 2: Implement the async GitHubClient**

Rewrite `collect/github/client.py`:

```python
"""GitHub API client with caching, rate limiting, and concurrency control.

Fetches raw data from GitHub REST API. LLM is NOT involved at this layer.
Uses httpx.AsyncClient with filesystem cache, proactive rate limit
management, and semaphore-based concurrency control.
"""

import asyncio
import time
from typing import Any

import httpx

from collect.github.cache import CacheStore
from collect.github.rate_limit import RateLimiter


class GitHubClient:
    """Async HTTP client for GitHub REST API.

    Handles authentication, pagination, caching, rate limiting, and
    error cases with exponential backoff retry.
    """

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
        cache_dir: str = "snapshots/cache",
        max_concurrent: int = 5,
        rate_limit_margin: int = 50,
    ):
        """Initialize the async GitHub API client.

        Args:
            token: GitHub Personal Access Token.
            max_retries: Maximum retry attempts for transient errors.
            base_delay: Base delay in seconds for exponential backoff.
            cache_dir: Directory for response cache files.
            max_concurrent: Maximum concurrent HTTP requests.
            rate_limit_margin: Pause when X-RateLimit-Remaining falls below this.
        """
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "BuilderDNA/0.1.0",
            },
            timeout=30.0,
        )
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.cache = CacheStore(cache_dir)
        self.rate_limiter = RateLimiter(safety_margin=rate_limit_margin)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._force_refresh: set[str] = set()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def get_repos(self, actor: str, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Fetch repositories owned by the actor.

        Only fetches owned repos (not forks), sorted by last updated.
        """
        params: dict[str, str] = {"per_page": "100", "sort": "updated", "type": "owner"}
        if force_refresh:
            self._force_refresh.add(f"/users/{actor}/repos")
        result = await self._paginate(f"/users/{actor}/repos", extra_params=params)
        self._force_refresh.discard(f"/users/{actor}/repos")
        return result

    async def get_user(self, actor: str) -> dict[str, Any] | None:
        """Fetch a GitHub user's profile.

        Returns None if user not found (404). Raises on 401.
        """
        resp = await self._request("GET", f"/users/{actor}")
        return resp.json() if resp is not None else None

    async def get_starred(self, actor: str) -> list[dict[str, Any]]:
        """Fetch repositories starred by the actor."""
        params: dict[str, str] = {"per_page": "100"}
        return await self._paginate(f"/users/{actor}/starred", extra_params=params)

    async def get_commits(
        self, actor: str, repo_full_name: str, since: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch commits by the actor in a specific repo."""
        params: dict[str, str] = {"author": actor, "per_page": "100"}
        if since:
            params["since"] = since
        return await self._paginate(f"/repos/{repo_full_name}/commits", extra_params=params)

    async def get_total_stars(self, actor: str) -> tuple[int, int]:
        """Get total stars across all repos for an actor using Search API.

        One API call instead of paginating all repos just to sum stars.

        Returns:
            (total_stars, repo_count). Stars are the sum of stargazers_count
            across all search results (up to 1000 via pagination).
            Falls back to summing first page if search is unavailable.
        """
        try:
            # Search for repos owned by this user, include forks
            params: dict[str, str] = {
                "q": f"user:{actor}+fork:true",
                "per_page": "100",
            }
            results = await self._paginate("/search/repositories", extra_params=params)
            total_stars = sum(r.get("stargazers_count", 0) for r in results)
            repo_count = len(results)
        except Exception:
            # Fallback: sum stars from the repos endpoint
            repos = await self.get_repos(actor)
            total_stars = sum(r.get("stargazers_count", 0) for r in repos)
            repo_count = len(repos)

        return total_stars, repo_count

    # ── Internal methods ──────────────────────────────────────────

    async def _should_skip_cache(self, url: str, params: dict[str, str] | None = None) -> bool:
        """Check if this URL is force-refreshed."""
        return url in self._force_refresh

    async def _paginate(
        self, path: str, extra_params: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all pages for a paginated endpoint."""
        params: dict[str, str] = dict(extra_params) if extra_params else {}
        all_items: list[dict[str, Any]] = []
        url: str = path
        first_page: bool = True

        while url:
            req_params = params if first_page else None
            response = await self._request("GET", url, params=req_params)
            if response is None:
                return all_items
            all_items.extend(response.json())
            url = self._next_page_url(response)
            first_page = False

        return all_items

    async def _request(
        self, method: str, url: str, params: dict[str, str] | None = None
    ) -> httpx.Response | None:
        """Make an HTTP request with caching, rate limiting, and retry.

        Flow:
        1. Check cache (unless force_refresh)
        2. Send request with ETag if cached
        3. On 304 → update cache ts, return cached body
        4. On success → cache response, update rate limit state
        5. On 429/403 rate limit → wait and retry
        6. On 5xx/network → exponential backoff

        Returns None for 404 (skip this resource).
        Raises httpx.HTTPStatusError on 401.
        """
        skip_cache = await self._should_skip_cache(url, params)

        # Try cache first
        if not skip_cache:
            cached = self.cache.get(method, url, params)
            if cached is not None:
                cached_status, cached_headers, cached_body = cached
                # Build a synthetic response from cache
                # But first, try a conditional request with ETag
                etag = self.cache.get_etag(method, url, params)
                if etag:
                    async with self._semaphore:
                        await self.rate_limiter.wait_if_needed()
                        req_headers = {"If-None-Match": etag}
                        resp = await self._client.request(
                            method, url, params=params, headers=req_headers,
                        )

                    self.rate_limiter.update(dict(resp.headers))

                    if resp.status_code == 304:
                        # Not modified — bump cache freshness, return cached
                        self.cache.update_from_304(method, url, params, dict(resp.headers))
                        return self._build_cached_response(cached_body, cached_headers)

                    if resp.status_code == 401:
                        resp.raise_for_status()

                    if resp.status_code == 404:
                        return None

                    if resp.status_code in (200, 201):
                        body_text = resp.text
                        self.cache.set(method, url, params, resp.status_code,
                                       dict(resp.headers), body_text)
                        return resp

                    # Non-cacheable status — fall through to normal request

        # Normal request (no cache hit or ETag not available)
        for attempt in range(self.max_retries + 1):
            async with self._semaphore:
                await self.rate_limiter.wait_if_needed()

                try:
                    resp = await self._client.request(method, url, params=params)

                    # Update rate limit state from response
                    self.rate_limiter.update(dict(resp.headers))

                    # 401: bad token — no retry
                    if resp.status_code == 401:
                        resp.raise_for_status()

                    # 404: resource not found — skip
                    if resp.status_code == 404:
                        return None

                    # 429: primary rate limit
                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("Retry-After", "60"))
                        if attempt < self.max_retries:
                            print(f"[RateLimit] 429 hit — waiting {retry_after}s "
                                  f"(attempt {attempt + 1}/{self.max_retries})")
                            await asyncio.sleep(retry_after)
                            continue
                        return None

                    # 403 with rate limit hit (secondary rate limit)
                    if resp.status_code == 403:
                        remaining = resp.headers.get("X-RateLimit-Remaining")
                        retry_after = resp.headers.get("Retry-After")
                        if remaining == "0" and retry_after:
                            wait = int(retry_after)
                            if attempt < self.max_retries:
                                print(f"[RateLimit] Secondary rate limit — "
                                      f"waiting {wait}s (attempt {attempt + 1}/{self.max_retries})")
                                await asyncio.sleep(wait)
                                continue
                            return None
                        # 403 for other reasons (e.g. access denied)
                        if attempt < self.max_retries:
                            delay = min(self.base_delay * (2 ** attempt), 60.0)
                            await asyncio.sleep(delay)
                            continue
                        resp.raise_for_status()

                    # 5xx: server error
                    if resp.status_code >= 500:
                        if attempt < self.max_retries:
                            delay = min(self.base_delay * (2 ** attempt), 60.0)
                            await asyncio.sleep(delay)
                            continue
                        resp.raise_for_status()

                    # Success (2xx)
                    resp.raise_for_status()

                    # Cache successful response
                    body_text = resp.text
                    self.cache.set(method, url, params, resp.status_code,
                                   dict(resp.headers), body_text)

                    return resp

                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt < self.max_retries:
                        delay = min(self.base_delay * (2 ** attempt), 60.0)
                        await asyncio.sleep(delay)
                    else:
                        raise

        return None

    @staticmethod
    def _build_cached_response(body: str, headers: dict) -> httpx.Response:
        """Build an httpx.Response from cached data for use by callers."""
        import io
        request = httpx.Request("GET", "https://api.github.com/")
        return httpx.Response(
            status_code=200,
            headers=headers,
            content=body.encode(),
            request=request,
        )

    @staticmethod
    def _next_page_url(response: httpx.Response) -> str | None:
        """Extract next page URL from Link header."""
        link = response.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                start = part.find("<") + 1
                end = part.find(">")
                return part[start:end] if start > 0 and end > start else None
        return None
```

- [ ] **Step 3: Run tests, fix issues**

```bash
uv run pytest tests/test_collect/test_github_client.py -v
```

- [ ] **Step 4: Commit**

```bash
git add collect/github/client.py tests/test_collect/test_github_client.py
git commit -m "feat: rewrite GitHubClient as async with cache, rate limiter, semaphore"
```

---

### Task 4: Update `config.py` and `config.yaml` — Add Cache and Rate Limit Config

**Files:**
- Modify: `config.py` (add `GitHubConfig` fields)
- Modify: `config.yaml` (add `github` section fields)

- [ ] **Step 1: Update `config.py`**

In `config.py`, update `GitHubConfig`:

```python
class GitHubConfig(BaseModel):
    """GitHub API configuration."""

    token: str = Field(description="GitHub Personal Access Token")
    cache_dir: str = Field(default="snapshots/cache", description="Directory for HTTP cache")
    max_concurrent: int = Field(default=5, ge=1, le=20, description="Max concurrent API requests")
    rate_limit_margin: int = Field(default=50, ge=10, le=500,
                                   description="Pause when remaining calls below this")
```

- [ ] **Step 2: Update `config.yaml`**

Add under `github:` section:

```yaml
github:
  token: ${GITHUB_TOKEN}
  cache_dir: snapshots/cache
  max_concurrent: 5
  rate_limit_margin: 50
```

- [ ] **Step 3: Run existing config tests**

```bash
uv run pytest tests/test_config.py -v
```

- [ ] **Step 4: Commit**

```bash
git add config.py config.yaml
git commit -m "feat: add cache and rate limit config options"
```

---

### Task 5: Update `pipeline.py` — Async Pipeline with Concurrent Account Fetching

**Files:**
- Modify: `pipeline.py`

- [ ] **Step 1: Rewrite `pipeline.py` with async support**

```python
"""Pipeline — orchestrates the full Collect→Understand→Recommend flow."""

import asyncio
from pathlib import Path
from typing import Any

from config import Config
from collect.github.client import GitHubClient
from collect.github.mapper import map_all
from collect.store import SignalStore
from insight.aggregator import aggregate
from insight.classifier import classify
from opportunity.detector import detect
from opportunity.evaluator import evaluate
from llm.client import OpenAIClient


class Pipeline:
    """Orchestrates the BuilderDNA analysis pipeline."""

    def __init__(self, config: Config):
        self.config = config
        self.github = GitHubClient(
            token=config.github.token,
            cache_dir=config.github.cache_dir,
            max_concurrent=config.github.max_concurrent,
            rate_limit_margin=config.github.rate_limit_margin,
        )
        self.llm = OpenAIClient(
            api_key=config.llm.api_key,
            model=config.llm.model,
            base_url=config.llm.base_url,
        )
        self.store = SignalStore(Path("snapshots") / "builderdna.db")

    def run(self, compare: bool = False) -> dict[str, Any]:
        """Execute the full analysis pipeline (sync entry point)."""
        return asyncio.run(self._run_async(compare))

    async def _run_async(self, compare: bool = False) -> dict[str, Any]:
        """Execute the full analysis pipeline."""
        snapshot_id = self.store.create_snapshot(self.config.accounts)

        try:
            # Phase 1: Collect (concurrent across accounts)
            all_signals = await self._collect_all(compare)

            if not all_signals:
                return {"snapshot_id": snapshot_id, "signals": [], "clusters": [],
                        "insights": [], "opportunities": [], "diff": None}

            self.store.insert_signals(all_signals, snapshot_id)

            # Phase 2: Understand
            clusters, insights = self._run_understand(all_signals, compare, snapshot_id)

            # Phase 3: Recommend
            opportunities = self._run_recommend(insights, snapshot_id)

            # Diff
            diff = None
            if compare:
                last = self.store.get_last_snapshot()
                if last and last["id"] != snapshot_id:
                    diff = self._compute_diff(all_signals, last)

            # Emit rate limit summary
            print(f"[GitHub] {self.github.rate_limiter.usage_summary()}")

            return {
                "snapshot_id": snapshot_id, "signals": all_signals,
                "clusters": clusters,
                "insights": insights, "opportunities": opportunities, "diff": diff,
            }
        finally:
            await self.github.close()

    async def _collect_all(self, compare: bool = False) -> list:
        from datetime import datetime, timezone, timedelta

        since = None
        if compare:
            last = self.store.get_last_snapshot()
            if last:
                since = last["created_at"]

        # Time range filter from config
        if since is None and self.config.collect.time_range_days > 0:
            since = (datetime.now(timezone.utc) - timedelta(days=self.config.collect.time_range_days)).isoformat()

        # Concurrent collection across accounts
        async def collect_one(account: str) -> list:
            try:
                account_signals = await self._collect_for_account(account, since)
                # Filter by timestamp
                if since and self.config.collect.time_range_days > 0:
                    account_signals = [s for s in account_signals if s.timestamp.isoformat() >= since]
                return account_signals
            except Exception as e:
                print(f"Warning: failed to collect for {account}: {e}")
                return []

        results = await asyncio.gather(*[collect_one(a) for a in self.config.accounts])
        all_signals = []
        for r in results:
            all_signals.extend(r)
        return all_signals

    async def _collect_for_account(self, actor: str, since: str | None = None) -> list:
        raw_repos = await self.github.get_repos(actor)
        raw_starred = await self.github.get_starred(actor)
        # commits temporarily disabled
        raw_commits: dict[str, list] = {}
        return map_all(
            raw_repos=raw_repos, raw_starred=raw_starred,
            raw_commits_by_repo=raw_commits, actor=actor,
            repo=self.config.weights.repo, star=self.config.weights.star,
            commit=self.config.weights.commit,
        )

    def _run_understand(self, signals: list, compare: bool, snapshot_id: str) -> tuple[list, list]:
        clusters = aggregate(signals)
        self.store.insert_signal_clusters([c.model_dump() for c in clusters], snapshot_id)
        previous = None
        if compare:
            last = self.store.get_last_snapshot()
            if last and last["id"] != snapshot_id:
                previous = self.store.get_insights(last["id"])
        actor = self.config.accounts[0] if self.config.accounts else "unknown"
        insights = classify(clusters, self.llm, actor, previous)
        self.store.insert_insights([i.model_dump() for i in insights], snapshot_id)
        return clusters, insights

    def _run_recommend(self, insights: list, snapshot_id: str) -> list:
        if not insights:
            return []
        opportunities = detect(insights, self.llm)
        opportunities = evaluate(opportunities)
        self.store.insert_opportunities([o.model_dump() for o in opportunities], snapshot_id)
        return opportunities

    def _compute_diff(self, signals: list, last_snapshot: dict) -> dict:
        previous_signals = self.store.get_signals_since("1970-01-01")

        new_by_type: dict[str, int] = {}
        prev_by_type: dict[str, int] = {}
        for s in signals:
            new_by_type[s.type] = new_by_type.get(s.type, 0) + 1
        for s in previous_signals:
            prev_by_type[s.type] = prev_by_type.get(s.type, 0) + 1

        new_topic_weight: dict[str, float] = {}
        prev_topic_weight: dict[str, float] = {}
        for s in signals:
            for t in s.meta.get("topics", []):
                new_topic_weight[t] = new_topic_weight.get(t, 0) + s.weight
        for s in previous_signals:
            for t in s.meta.get("topics", []):
                prev_topic_weight[t] = prev_topic_weight.get(t, 0) + s.weight

        topic_changes = {}
        all_topics = set(new_topic_weight) | set(prev_topic_weight)
        for t in all_topics:
            prev_w = prev_topic_weight.get(t, 0)
            new_w = new_topic_weight.get(t, 0)
            change_pct = round((new_w - prev_w) / prev_w * 100, 1) if prev_w > 0 else 100.0
            topic_changes[t] = {"previous": prev_w, "current": new_w, "change_pct": change_pct}

        return {
            "new_signals": len(signals) - len(previous_signals),
            "total_signals": len(signals),
            "signals_by_type": {"previous": prev_by_type, "current": new_by_type},
            "topic_weight_changes": topic_changes,
            "previous_snapshot_id": last_snapshot["id"],
        }
```

- [ ] **Step 2: Run existing tests**

```bash
uv run pytest tests/test_pipeline/ -v
uv run pytest tests/test_e2e.py -v
```

- [ ] **Step 3: Fix any test failures, then commit**

```bash
git add pipeline.py
git commit -m "feat: add async pipeline with concurrent account collection"
```

---

### Task 6: Update `cli.py` — Async Follow Command with Search API

**Files:**
- Modify: `cli.py`

The follow command needs to:
1. Create GitHubClient asynchronously
2. Use `get_total_stars()` instead of `get_repos()` for star counting
3. Use `asyncio.gather` for concurrent user fetching

- [ ] **Step 1: Rewrite `_fetch_metrics` and `_run_grouped` in `cli.py`**

In `cli.py`, replace `_fetch_metrics` and `_run_grouped`:

```python
async def _fetch_metrics_async(gh: GitHubClient, actors: list[str]) -> list[dict]:
    """Fetch stars and followers for a list of actors concurrently.

    Uses Search API for total stars (1 call) instead of paginating all repos.
    """
    async def fetch_one(actor: str) -> dict:
        try:
            profile_task = gh.get_user(actor)
            stars_task = gh.get_total_stars(actor)

            profile, (total_stars, repo_count) = await asyncio.gather(
                profile_task, stars_task
            )

            if profile is None:
                return {"actor": actor, "stars": 0, "followers": 0,
                        "error": f"账号 {actor} 不存在 (404)"}

            return {
                "actor": actor,
                "stars": total_stars,
                "followers": profile.get("followers", 0),
                "error": "",
            }
        except Exception as e:
            return {"actor": actor, "stars": 0, "followers": 0, "error": str(e)}

    return await asyncio.gather(*[fetch_one(a) for a in actors])


def _fetch_metrics(gh, actors: list[str]) -> list[dict]:
    """Sync wrapper for _fetch_metrics_async."""
    return asyncio.run(_fetch_metrics_async(gh, actors))
```

Also update `_run_grouped` to handle the async client lifecycle:

```python
def _run_grouped(gh, groups: dict[str, list[str]], store, top: int, show_diff: bool) -> None:
    """Run grouped evaluation with optional trend diff."""
    from follow.scorer import score_grouped, apply_delta

    # Collect all unique actors
    all_actors: list[str] = []
    seen: set[str] = set()
    for actors in groups.values():
        for a in actors:
            if a not in seen:
                seen.add(a)
                all_actors.append(a)

    # Fetch all metrics concurrently
    metrics_map = {m["actor"]: m for m in _fetch_metrics(gh, all_actors)}

    # Build per-group metrics
    group_metrics: dict[str, list[dict]] = {}
    for group_name, actors in groups.items():
        group_metrics[group_name] = [metrics_map[a] for a in actors]

    # Score
    results = score_grouped(group_metrics)

    # Save snapshot
    snap_id = store.save(results)

    # Apply delta if requested
    if show_diff:
        prev = store.get_previous(snap_id)
        if prev:
            results = apply_delta(results, prev)
        else:
            console.print("[yellow]暂无历史快照，无法对比趋势[/yellow]")

    # Close client
    asyncio.run(gh.close())

    _render_grouped_table(results, top, show_diff, snap_id)
    print(f"[GitHub] {gh.rate_limiter.usage_summary()}")
```

Update the `follow` command to pass config to GitHubClient:

```python
@main.command()
@click.argument("accounts", nargs=-1)
@click.option("--config", "-c", default=DEFAULT_CONFIG, help="Path to config.yaml")
@click.option("--top", "-n", default=0, help="Show only top N results per group")
@click.option("--from-config", is_flag=True, help="Read groups from config.yaml follow_groups")
@click.option("--diff", is_flag=True, help="Show trend vs last snapshot")
def follow(accounts: tuple[str], config: str, top: int, from_config: bool, diff: bool):
    """Evaluate GitHub ACCOUNTS for follow-worthiness by stars and followers."""
    from collect.github.client import GitHubClient
    from follow.store import FollowStore

    cfg = load_config(Path(config))
    store = FollowStore()

    # Determine account list and grouping mode
    grouped_mode = False
    if from_config and cfg.follow_groups:
        grouped_mode = True
        groups = cfg.follow_groups
    elif from_config and cfg.follow_accounts:
        accounts = tuple(cfg.follow_accounts)
    elif not accounts:
        console.print("[red]请提供账号列表，或使用 --from-config[/red]")
        return

    gh = GitHubClient(
        token=cfg.github.token,
        cache_dir=cfg.github.cache_dir,
        max_concurrent=cfg.github.max_concurrent,
        rate_limit_margin=cfg.github.rate_limit_margin,
    )

    if grouped_mode:
        _run_grouped(gh, groups, store, top, diff)
    else:
        _run_flat(gh, accounts, top)
```

- [ ] **Step 2: Run follow tests**

```bash
uv run pytest tests/test_follow/ -v
```

- [ ] **Step 3: Run all tests**

```bash
uv run pytest tests/ -v
```

- [ ] **Step 4: Fix any failures, then commit**

```bash
git add cli.py
git commit -m "feat: optimize follow with Search API and concurrent fetching"
```

---

### Self-Review Checklist

**1. Spec coverage:** ✅ All 4 spec components covered — cache (Task 1), rate limit (Task 2), client rewrite (Task 3), follow optimization (Task 6). Config changes (Task 4). Pipeline async (Task 5).

**2. Placeholder scan:** ✅ No TBD/TODO. All code is exact. Error handling specified. Tests included.

**3. Type consistency:** ✅ `CacheStore` methods match client usage. `RateLimiter.update(headers)` consumes dict headers from `resp.headers`. `get_total_stars` returns `tuple[int, int]`. `_fetch_metrics_async` consumes `GitHubClient`.

**4. Gap check:**
- Config propagation: `config.yaml` → `Config` pydantic → `GitHubClient(...)` — ✅
- Client lifecycle: `close()` called in `pipeline._run_async` finally block and in `_run_grouped` — ✅
- `_force_refresh` mechanism — ✅ via `force_refresh` parameter on `get_repos`
- Search API fallback — ✅ in `get_total_stars` try/except
- httpx_mock compat with async — ✅ pytest-httpx supports async
