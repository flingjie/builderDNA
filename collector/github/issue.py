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
        issues_data = await client._paginate(f"/repos/{repo}/issues", extra_params=params)
    except Exception as e:
        tel = client.telemetry
        if tel:
            tel.add_error(f"/repos/{repo}/issues", str(e))
        return []

    return _extract_issues(issues_data, repo)


async def fetch_demand_issues(
    client: GitHubClient, repo: str, max_issues: int = 20
) -> list[dict]:
    """Fetch issues with demand-signal labels only.

    Uses GitHub Search API with label qualifiers to find issues that
    explicitly express developer needs: feature requests, enhancements,
    help-wanted gaps, and bugs that signal quality pain.

    Args:
        client: GitHubClient instance.
        repo: Full repository name (e.g. "org/repo").
        max_issues: Maximum number of issues to fetch.

    Returns:
        List of issue dicts filtered by demand-signal labels.
    """
    label_query = " OR ".join(f"label:{lbl}" for lbl in DEMAND_LABELS)
    query = f"repo:{repo} is:issue is:open ({label_query})"

    params: dict[str, str] = {
        "q": query,
        "sort": "interactions",
        "order": "desc",
        "per_page": str(min(max_issues, 100)),
    }

    try:
        resp = await client._request("GET", "/search/issues", params=params)
        if resp is None:
            return []
        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else []
        return _extract_issues(items, repo)
    except Exception as e:
        tel = client.telemetry
        if tel:
            tel.add_error(f"/search/issues?q=repo:{repo}", str(e))
        return []


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


async def fetch_discussions(
    client: GitHubClient, repo: str, max_discussions: int = 20
) -> list[dict]:
    """Fetch recent discussions from a repository.

    Uses GitHub GraphQL API (if token has discussion:read scope).

    Args:
        client: GitHubClient instance.
        repo: Full repo name.
        max_discussions: Max discussions to fetch.

    Returns:
        List of discussion dicts (may be empty if no GraphQL access).
    """
    try:
        owner, repo_name = repo.split("/", 1)
    except ValueError:
        return []
    query = """
    query($owner: String!, $repo: String!, $first: Int!) {
      repository(owner: $owner, name: $repo) {
        discussions(first: $first, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes {
            title
            body
            number
            url
            comments { totalCount }
          }
        }
      }
    }
    """
    try:
        resp = await client._request(
            "POST", "/graphql",
            json={"query": query, "variables": {"owner": owner, "repo": repo_name, "first": max_discussions}},
        )
        if resp is None:
            return []
        data = resp.json()
        nodes = data.get("data", {}).get("repository", {}).get("discussions", {}).get("nodes", [])
        return [
            {
                "repo": repo,
                "discussion_number": n.get("number", 0),
                "title": n.get("title", ""),
                "body": (n.get("body", "") or "")[:500],
                "comments": n.get("comments", {}).get("totalCount", 0),
                "url": n.get("url", ""),
            }
            for n in nodes
        ]
    except Exception as e:
        tel = client.telemetry
        if tel:
            tel.add_error(f"/graphql discussions for {repo}", str(e))
        return []
