"""Pull-request / review / commit / diff fetchers for repo-evolution-learning.

Thin async functions over :class:`GitHubClient`. Each uses ``_request`` or
``_paginate`` (which already apply cache + rate limit + retry) and returns an
empty ``list``/``None``/``""`` on 404 rather than raising, so a partial fetch
still yields a usable workspace.
"""
from collector.github.client import GitHubClient


async def fetch_pull(client: GitHubClient, repo: str, number: int) -> dict | None:
    """Fetch ``GET /repos/{repo}/pulls/{number}`` (PR metadata)."""
    resp = await client._request("GET", f"/repos/{repo}/pulls/{number}")
    if resp is None:
        return None
    return resp.json()


async def fetch_pull_reviews(client: GitHubClient, repo: str, number: int) -> list[dict]:
    """Fetch PR reviews (approvals/change-requests with bodies), bounded."""
    return await client._paginate(
        f"/repos/{repo}/pulls/{number}/reviews", extra_params={"per_page": "100"}, max_pages=1
    )


async def fetch_pull_review_comments(client: GitHubClient, repo: str, number: int) -> list[dict]:
    """Fetch inline review comments on a PR's diff, bounded."""
    return await client._paginate(
        f"/repos/{repo}/pulls/{number}/comments", extra_params={"per_page": "100"}, max_pages=1
    )


async def fetch_issue_comments(client: GitHubClient, repo: str, number: int) -> list[dict]:
    """Fetch the PR discussion comments (a PR is also an issue), bounded."""
    return await client._paginate(
        f"/repos/{repo}/issues/{number}/comments", extra_params={"per_page": "100"}, max_pages=2
    )


async def fetch_pull_commits(client: GitHubClient, repo: str, number: int) -> list[dict]:
    """Fetch the commits in a PR, bounded."""
    return await client._paginate(
        f"/repos/{repo}/pulls/{number}/commits", extra_params={"per_page": "100"}, max_pages=1
    )


async def fetch_pull_files(client: GitHubClient, repo: str, number: int) -> list[dict]:
    """Fetch the changed files of a PR (each may carry a per-file ``patch``)."""
    return await client._paginate(
        f"/repos/{repo}/pulls/{number}/files", extra_params={"per_page": "100"}, max_pages=2
    )


async def fetch_pull_diff(client: GitHubClient, repo: str, number: int) -> str:
    """Fetch the full PR diff as text.

    The client's global ``Accept`` is JSON, so this requests the diff media type
    explicitly. The ``media=diff`` param only varies the cache key (GitHub ignores
    unknown params) so the diff response never collides with the JSON PR fetch.
    """
    resp = await client._request(
        "GET",
        f"/repos/{repo}/pulls/{number}",
        params={"media": "diff"},
        headers={"Accept": "application/vnd.github.diff"},
    )
    if resp is None:
        return ""
    return resp.text


async def fetch_issue(client: GitHubClient, repo: str, number: int) -> dict | None:
    """Fetch a single issue (for linked-issue context)."""
    resp = await client._request("GET", f"/repos/{repo}/issues/{number}")
    if resp is None:
        return None
    return resp.json()


async def fetch_repo_issues_since(
    client: GitHubClient, repo: str, since_iso: str, per_page: int = 30
) -> list[dict]:
    """Fetch issues/PRs updated since ``since_iso`` (follow-up material)."""
    return await client._paginate(
        f"/repos/{repo}/issues",
        extra_params={"state": "all", "since": since_iso, "per_page": str(per_page)},
        max_pages=1,
    )


async def fetch_recent_pulls(client: GitHubClient, repo: str, per_page: int = 10) -> list[dict]:
    """Fetch the most recently updated PRs (candidate episodes for selection)."""
    return await client._paginate(
        f"/repos/{repo}/pulls",
        extra_params={
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": str(per_page),
        },
        max_pages=1,
    )


async def fetch_commit(client: GitHubClient, repo: str, sha: str) -> dict | None:
    """Fetch a single commit by SHA (before/after code context)."""
    resp = await client._request("GET", f"/repos/{repo}/commits/{sha}")
    if resp is None:
        return None
    return resp.json()
