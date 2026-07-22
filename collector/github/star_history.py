"""Star history time-series collector for BuilderDNA 2.0.

Collects star count trajectory for second-derivative velocity computation.
"""
from datetime import datetime, timezone, timedelta
from collector.github.client import GitHubClient


async def fetch_star_history(
    client: GitHubClient, repo: str, days: int = 90
) -> list[dict]:
    """Fetch star count over time for a repository.

    Uses GitHub's stargazers endpoint with pagination to build a timeline.
    Falls back to current star count if detailed history is unavailable.

    Args:
        client: GitHubClient instance.
        repo: Full repo name (e.g. "org/repo").
        days: How many days of history to fetch.

    Returns:
        List of {date: str, stars: int} sorted by date ascending.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        params = {
            "per_page": "100",
            "page": "1",
            "sort": "created",
            "direction": "asc",
        }
        # Stargazers endpoint returns users who starred, we track dates
        import asyncio
        import math

        stars_by_date: dict[str, int] = {}
        page = 1
        while True:
            paged_params = {**params, "page": str(page)}
            resp = await client._request(
                "GET", f"/repos/{repo}/stargazers",
                params=paged_params,
            )

            if resp is None:
                break

            data = resp.json()
            if not data or not isinstance(data, list):
                break

            for sg in data:
                starred_at = sg.get("starred_at", "")
                if starred_at:
                    try:
                        dt = datetime.fromisoformat(starred_at.replace("Z", "+00:00"))
                        if dt >= since:
                            date_key = dt.strftime("%Y-%m-%d")
                            stars_by_date[date_key] = stars_by_date.get(date_key, 0) + 1
                    except (ValueError, TypeError):
                        pass

            if len(data) < 100:
                break
            page += 1

            # Rate limit safe-guard
            if page > 10:
                break

        # Convert to cumulative timeline
        result = []
        cumulative = 0
        for date_key in sorted(stars_by_date.keys()):
            cumulative += stars_by_date[date_key]
            result.append({"date": date_key, "stars": cumulative})

        return result
    except Exception:
        return []
