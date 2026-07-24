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
    url = f"/search/repositories?q=topic:{topic}"
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
    except Exception as e:
        tel = client.telemetry
        if tel:
            tel.add_error(url, str(e))
        return []
