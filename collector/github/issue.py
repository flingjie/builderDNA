"""Issue & Discussion collector for BuilderDNA 2.0."""
from collector.github.client import GitHubClient

# Labels that directly signal developer demand / pain / contribution gaps
DEMAND_LABELS = [
    "feature-request",    # explicit feature demand
    "enhancement",        # improvement request
    "help wanted",        # contribution gap → productization opportunity
    "good first issue",   # adoption friction → onboarding opportunity
    "bug",                # quality pain
]


async def fetch_issues(
    client: GitHubClient, repo: str, max_issues: int = 20
) -> list[dict]:
    """Fetch top issues from a repository by comment count.

    Skips pull requests. Extracts title, body, comments, participants, labels.

    Args:
        client: GitHubClient instance.
        repo: Full repository name (e.g. "org/repo").
        max_issues: Maximum number of issues to fetch.

    Returns:
        List of issue dicts with extracted fields.
    """
    params = {
        "state": "open",
        "sort": "comments",
        "direction": "desc",
        "per_page": str(max_issues),
    }

    try:
        issues_data = await client._paginate(f"/repos/{repo}/issues", extra_params=params, max_pages=3)
    except Exception as e:
        tel = client.telemetry
        if tel:
            tel.add_error(f"/repos/{repo}/issues", str(e))
        return []

    return _extract_issues(issues_data, repo)


def _extract_issues(issues_data: list[dict], repo: str) -> list[dict]:
    """Extract normalized fields from GitHub issue API responses."""
    extracted = []
    for issue in issues_data:
        if issue.get("pull_request") is not None:
            continue  # skip PRs

        comments = issue.get("comments", 0)
        participants = 1 + min(comments, 5)

        # Reactions count — aggregate all reaction types
        reactions = issue.get("reactions", {})
        total_reactions = sum(
            reactions.get(k, 0) for k in ("+1", "-1", "laugh", "hooray", "confused", "heart", "rocket", "eyes")
        )

        user = issue.get("user", {})
        user_login = user.get("login", "") if isinstance(user, dict) else "unknown"

        extracted.append({
            "repo": repo,
            "issue_number": issue.get("number", 0),
            "title": issue.get("title", "") or "",
            "body": (issue.get("body", "") or "")[:500],
            "comments": comments,
            "participants": participants,
            "reactions": total_reactions,
            "labels": [lb.get("name", "") for lb in issue.get("labels", []) if isinstance(lb, dict)],
            "url": issue.get("html_url", ""),
            "user_login": user_login,
            "created_at": issue.get("created_at", ""),
        })

    return extracted
