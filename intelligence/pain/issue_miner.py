"""Issue miner — fetches and extracts GitHub issues for pain analysis.

Migrated from backend/engine/pain.py (Phase 2).
GitHub client import lives at collect/github/client.py.
"""

from collect.github.client import GitHubClient


async def fetch_issues(client: GitHubClient, repo: str, max_issues: int = 20) -> list[dict]:
    """Fetch top issues from a repository by comment count.

    GitHub API: GET /repos/{repo}/issues?state=open&sort=comments&per_page={max_issues}

    Args:
        client: GitHubClient instance for API calls.
        repo: Full repository name (e.g., "org/repo").
        max_issues: Maximum number of issues to fetch.

    Returns:
        List of issue dictionaries with extracted fields.
    """
    params = {
        "state": "open",
        "sort": "comments",
        "direction": "desc",
        "per_page": str(max_issues),
    }

    try:
        issues_data = await client._paginate(f"/repos/{repo}/issues", extra_params=params)
    except Exception:
        return []

    extracted = []
    for issue in issues_data:
        if issue.get("pull_request") is not None:
            continue

        comments = issue.get("comments", 0)
        participants = 1 + min(comments, 5)
        user = issue.get("user", {})
        user_login = user.get("login", "") if isinstance(user, dict) else "unknown"

        extracted.append({
            "repo": repo,
            "issue_number": issue.get("number", 0),
            "title": issue.get("title", "") or "",
            "body": (issue.get("body", "") or "")[:500],
            "comments": comments,
            "participants": participants,
            "labels": [lb.get("name", "") for lb in issue.get("labels", []) if isinstance(lb, dict)],
            "url": issue.get("html_url", ""),
            "user_login": user_login,
        })

    return extracted
