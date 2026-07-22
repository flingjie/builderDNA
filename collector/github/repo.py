"""Repo & Release collector for BuilderDNA 2.0."""
from collector.github.client import GitHubClient


async def fetch_top_repos(
    client: GitHubClient, topic: str, max_results: int = 30
) -> list[dict]:
    """Fetch top repos for a GitHub topic via Search API.

    Args:
        client: GitHubClient instance.
        topic: GitHub topic tag (e.g. "agent-framework").
        max_results: Max repos to return (1 page, max 100).

    Returns:
        List of raw repo dicts from GitHub API.
    """
    try:
        params: dict[str, str] = {
            "q": f"topic:{topic}",
            "sort": "stars",
            "order": "desc",
            "per_page": str(min(max_results, 100)),
        }
        resp = await client._request("GET", "/search/repositories", params=params)
        if resp is None:
            return []
        data = resp.json()
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return data if isinstance(data, list) else []
    except Exception:
        return []


async def fetch_releases(
    client: GitHubClient, repo: str, max_results: int = 10
) -> list[dict]:
    """Fetch recent releases for a repository.

    Args:
        client: GitHubClient instance.
        repo: Full repo name (e.g. "org/repo").
        max_results: Max releases to return.

    Returns:
        List of release dicts.
    """
    try:
        params = {"per_page": str(min(max_results, 100))}
        resp = await client._request("GET", f"/repos/{repo}/releases", params=params)
        if resp is None:
            return []
        return resp.json()
    except Exception:
        return []
