"""GitHub API client with caching, rate limiting, and concurrency control.

Fetches raw data from GitHub REST API. LLM is NOT involved at this layer.
Uses httpx.AsyncClient with filesystem cache, proactive rate limit
management, and semaphore-based concurrency control.
"""

import asyncio
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
        try:
            return await self._paginate(f"/users/{actor}/repos", extra_params=params)
        finally:
            self._force_refresh.discard(f"/users/{actor}/repos")

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
            across all search results. Falls back to summing repo pages if
            search is unavailable.
        """
        try:
            params: dict[str, str] = {
                "q": f"user:{actor}+fork:true",
                "per_page": "100",
            }
            results = await self._paginate("/search/repositories", extra_params=params)
            total_stars = sum(r.get("stargazers_count", 0) for r in results)
            repo_count = len(results)
        except Exception:
            # Fallback: sum stars from the repos endpoint
            # Fallback: sum stars from the repos endpoint
            repos = await self.get_repos(actor)
            total_stars = sum(r.get("stargazers_count", 0) for r in repos)
            repo_count = len(repos)

        return total_stars, repo_count

    # ── Internal methods ──────────────────────────────────────────

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
            all_items.extend(self._extract_items(response))
            url = self._next_page_url(response)
            first_page = False

        return all_items

    async def _request(
        self, method: str, url: str, params: dict[str, str] | None = None
    ) -> httpx.Response | None:
        """Make an HTTP request with caching, rate limiting, and retry.

        Flow:
        1. Check cache (unless force_refresh)
        2. Send conditional request with ETag if cached
        3. On 304 → update cache ts, return cached body
        4. On success → cache response, update rate limit state
        5. On 429/403 rate limit → wait and retry
        6. On 5xx/network → exponential backoff

        Returns None for 404 (skip this resource).
        Raises httpx.HTTPStatusError on 401.
        """
        skip_cache = url in self._force_refresh

        # Try cache first with conditional request
        if not skip_cache:
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
                    self.cache.update_from_304(method, url, params, dict(resp.headers))
                    cached = self.cache.get(method, url, params)
                    if cached is not None:
                        return self._build_cached_response(cached[2], cached[1])

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

                    # 403: secondary rate limit or access denied
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
        """Build an httpx.Response from cached data.

        Drop Content-Encoding headers since the cached body is already decoded.
        """
        request = httpx.Request("GET", "https://api.github.com/")
        clean_headers = {k: v for k, v in headers.items()
                         if k.lower() not in ("content-encoding", "transfer-encoding")}
        return httpx.Response(
            status_code=200,
            headers=clean_headers,
            content=body.encode(),
            request=request,
        )

    @staticmethod
    def _extract_items(response: httpx.Response) -> list[dict[str, Any]]:
        """Extract list of items from a response, handling search API format.

        Most GitHub endpoints return a JSON array. The search API returns
        a dict with an 'items' key.
        """
        data = response.json()
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return data if isinstance(data, list) else []

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
