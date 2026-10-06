"""Repo metadata and README fetchers for repo-evolution-learning.

Thin async functions over :class:`GitHubClient` that fetch a single repo's
metadata and README. They never raise on 404 — a missing resource returns
``None``/``""`` so a partial fetch still yields a usable workspace.
"""
import base64

from collector.github.client import GitHubClient


async def fetch_repo_metadata(client: GitHubClient, repo: str) -> dict | None:
    """Fetch ``GET /repos/{repo}`` (full repo metadata)."""
    resp = await client._request("GET", f"/repos/{repo}")
    if resp is None:
        return None
    return resp.json()


async def fetch_readme(client: GitHubClient, repo: str) -> str:
    """Fetch the raw README text, decoding the base64 JSON ``content``.

    The client's global ``Accept: application/vnd.github+json`` means the
    ``/readme`` endpoint returns JSON with a base64 ``content`` field rather than
    the raw text.
    """
    resp = await client._request("GET", f"/repos/{repo}/readme")
    if resp is None:
        return ""
    try:
        data = resp.json()
        encoded = data.get("content", "") or ""
        return base64.b64decode(encoded).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""
