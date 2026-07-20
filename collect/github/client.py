"""GitHub API client with retry and error handling.

Fetches raw data from GitHub REST API. LLM is NOT involved at this layer.
"""

import time
from typing import Any

import httpx


class GitHubClient:
    """HTTP client for GitHub REST API.

    Handles authentication, pagination, rate limiting, and error cases
    per the spec's error handling table.
    """

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        """Initialize the GitHub API client.

        Args:
            token: GitHub Personal Access Token.
            max_retries: Maximum retry attempts for transient errors.
            base_delay: Base delay in seconds for exponential backoff.
        """
        self._client = httpx.Client(
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

    def get_repos(self, actor: str) -> list[dict[str, Any]]:
        """Fetch repositories owned by the actor.

        Args:
            actor: GitHub username.

        Returns:
            List of raw repo dicts from GitHub API. Empty if user not found.

        Raises:
            httpx.HTTPStatusError: On 401 (bad token).
        """
        return self._paginate(f"/users/{actor}/repos")

    def get_user(self, actor: str) -> dict[str, Any] | None:
        """Fetch a GitHub user's profile.

        Args:
            actor: GitHub username.

        Returns:
            Raw user dict from GitHub API. None if user not found (404).

        Raises:
            httpx.HTTPStatusError: On 401 (bad token).
        """
        resp = self._request_with_retry("GET", f"/users/{actor}")
        return resp.json() if resp is not None else None

    def get_starred(self, actor: str) -> list[dict[str, Any]]:
        """Fetch repositories starred by the actor.

        Args:
            actor: GitHub username.

        Returns:
            List of raw repo dicts from GitHub API. Empty if user not found.

        Raises:
            httpx.HTTPStatusError: On 401 (bad token).
        """
        return self._paginate(f"/users/{actor}/starred")

    def get_commits(
        self, actor: str, repo_full_name: str, since: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch commits by the actor in a specific repo.

        Args:
            actor: GitHub username (used to filter commits by author).
            repo_full_name: Full repo name, e.g. 'alice/toolkit'.
            since: ISO 8601 timestamp for incremental fetch.

        Returns:
            List of raw commit dicts. Empty on 404 or no commits found.
        """
        params: dict[str, str] = {"author": actor, "per_page": "100"}
        if since:
            params["since"] = since
        return self._paginate(f"/repos/{repo_full_name}/commits", extra_params=params)

    def _paginate(
        self, path: str, extra_params: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all pages for a paginated endpoint.

        Args:
            path: API path, e.g. '/users/alice/repos'.
            extra_params: Additional query parameters.

        Returns:
            Concatenated list of all items across pages.
        """
        params: dict[str, str] = {"per_page": "100", "sort": "updated"}
        if extra_params:
            params.update(extra_params)

        all_items: list[dict[str, Any]] = []
        url = path

        while url:
            response = self._request_with_retry("GET", url, params=params if url == path else None)
            if response is None:
                return all_items
            all_items.extend(response.json())
            url = self._next_page_url(response)

        return all_items

    def _request_with_retry(
        self, method: str, url: str, params: dict | None = None
    ) -> httpx.Response | None:
        """Make an HTTP request with exponential backoff retry.

        Args:
            method: HTTP method.
            url: Request URL (may be absolute for pagination).
            params: Query parameters.

        Returns:
            Response object, or None if the resource should be skipped (404).

        Raises:
            httpx.HTTPStatusError: On 401 (bad token — no retry).
        """
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.request(method, url, params=params)

                if resp.status_code == 401:
                    resp.raise_for_status()  # immediate abort

                if resp.status_code == 404:
                    return None  # skip this resource

                if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    if attempt < self.max_retries:
                        time.sleep(retry_after)
                        continue
                    return None

                if resp.status_code >= 500:
                    if attempt < self.max_retries:
                        delay = min(self.base_delay * (2**attempt), 60.0)
                        time.sleep(delay)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                return resp

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2**attempt), 60.0)
                    time.sleep(delay)
                else:
                    raise

        return None

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
