"""GitHub API client with caching, rate limiting, and concurrency control.

Fetches raw data from GitHub REST API. LLM is NOT involved at this layer.
Uses httpx.AsyncClient with filesystem cache, proactive rate limit
management, and semaphore-based concurrency control.
"""

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, TYPE_CHECKING

import httpx

from collector.github.cache import CacheStore
from collector.github.rate_limit import RateLimiter
from observability.output import OutputLevel, get_console, vprint

if TYPE_CHECKING:
    from observability.telemetry import RunTelemetry


def _parse_retry_after(raw: str, default: int = 60) -> int:
    """Parse a Retry-After header value per RFC 7231.

    The header can be either an integer number of seconds or an HTTP-date.
    """
    try:
        return max(1, int(raw))
    except ValueError:
        retry_time = parsedate_to_datetime(raw)
        return max(1, int((retry_time - datetime.now(timezone.utc)).total_seconds()))


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
        telemetry: "RunTelemetry | None" = None,
        disable_cache: bool = False,
    ):
        """Initialize the async GitHub API client.

        Args:
            token: GitHub Personal Access Token.
            max_retries: Maximum retry attempts for transient errors.
            base_delay: Base delay in seconds for exponential backoff.
            cache_dir: Directory for response cache files.
            max_concurrent: Maximum concurrent HTTP requests.
            rate_limit_margin: Pause when X-RateLimit-Remaining falls below this.
            telemetry: Optional RunTelemetry for observability metrics.
            disable_cache: If True, bypass all cache reads (writes still happen).
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
        self._telemetry = telemetry
        self._disable_cache = disable_cache

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    @property
    def telemetry(self) -> "RunTelemetry | None":
        """Access the telemetry instance for recording errors/stats."""
        return self._telemetry

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

    # ── Internal methods ──────────────────────────────────────────

    async def _wait_if_needed(self) -> bool:
        """Wait if rate limit is approaching, with telemetry tracking."""
        waited = await self.rate_limiter.wait_if_needed()
        if waited and self._telemetry:
            self._telemetry.record_api_waited()
        return waited

    async def _paginate(
        self, path: str, extra_params: dict[str, str] | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch pages for a paginated endpoint, up to max_pages if given."""
        params: dict[str, str] = dict(extra_params) if extra_params else {}
        all_items: list[dict[str, Any]] = []
        url: str = path
        first_page: bool = True

        while url:
            if max_pages is not None and len(all_items) >= max_pages * int(params.get("per_page", "30")):
                break
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
        1. Check cache (unless force_refresh or disable_cache)
        2. Send conditional request with ETag if cached
        3. On 304 → update cache ts, return cached body
        4. On success → cache response, update rate limit state
        5. On 429/403 rate limit → wait and retry
        6. On 5xx/network → exponential backoff

        Returns None for 404 (skip this resource).
        Raises httpx.HTTPStatusError on 401.
        """
        tel = self._telemetry
        skip_cache = url in self._force_refresh or self._disable_cache
        console = get_console()

        # Try cache first with conditional request
        if not skip_cache:
            etag = self.cache.get_etag(method, url, params)
            if etag:
                async with self._semaphore:
                    await self._wait_if_needed()
                    req_headers = {"If-None-Match": etag}
                    resp = await self._client.request(
                        method, url, params=params, headers=req_headers,
                    )

                self.rate_limiter.update(dict(resp.headers))

                if resp.status_code == 304:
                    self.cache.update_from_304(method, url, params, dict(resp.headers))
                    cached = self.cache.get(method, url, params)
                    if cached is not None:
                        if tel:
                            tel.record_cache(hit=True)
                        return self._build_cached_response(cached[2], cached[1], url)

                if resp.status_code == 401:
                    resp.raise_for_status()

                if resp.status_code == 404:
                    return None

                if resp.status_code in (200, 201):
                    body_text = resp.text
                    self.cache.set(method, url, params, resp.status_code,
                                   dict(resp.headers), body_text)
                    if tel:
                        tel.record_cache(hit=False)
                    return resp

                # Non-cacheable status — fall through to normal request

        # Normal request (no cache hit or ETag not available)
        for attempt in range(self.max_retries + 1):
            async with self._semaphore:
                await self._wait_if_needed()

                try:
                    resp = await self._client.request(method, url, params=params)

                    # Update rate limit state from response
                    self.rate_limiter.update(dict(resp.headers))
                    if tel:
                        tel.record_api_call()

                    # 401: bad token — no retry
                    if resp.status_code == 401:
                        resp.raise_for_status()

                    # 404: resource not found — skip
                    if resp.status_code == 404:
                        return None

                    # 429: primary rate limit
                    if resp.status_code == 429:
                        retry_after = _parse_retry_after(resp.headers.get("Retry-After", "60"))
                        if attempt < self.max_retries:
                            vprint(f"[RateLimit] 429 hit — waiting {retry_after}s "
                                   f"(attempt {attempt + 1}/{self.max_retries})",
                                   level=OutputLevel.NORMAL)
                            await asyncio.sleep(retry_after)
                            continue
                        if tel:
                            tel.add_retry_exhausted(url, "429 rate limit exhausted", attempt)
                        return None

                    # 403: secondary rate limit or access denied
                    if resp.status_code == 403:
                        remaining = resp.headers.get("X-RateLimit-Remaining")
                        retry_after = resp.headers.get("Retry-After")
                        if remaining == "0" and retry_after:
                            wait = _parse_retry_after(retry_after)
                            if attempt < self.max_retries:
                                vprint(f"[RateLimit] Secondary rate limit — "
                                       f"waiting {wait}s (attempt {attempt + 1}/{self.max_retries})",
                                       level=OutputLevel.NORMAL)
                                await asyncio.sleep(wait)
                                continue
                            if tel:
                                tel.add_retry_exhausted(url, "403 secondary rate limit exhausted", attempt)
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
                    if tel:
                        tel.record_cache(hit=False)

                    return resp

                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt < self.max_retries:
                        delay = min(self.base_delay * (2 ** attempt), 60.0)
                        await asyncio.sleep(delay)
                    else:
                        raise

        return None

    @staticmethod
    def _build_cached_response(body: str, headers: dict, url: str) -> httpx.Response:
        """Build an httpx.Response from cached data.

        Drop Content-Encoding headers since the cached body is already decoded.
        """
        request = httpx.Request("GET", url)
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
