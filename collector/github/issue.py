"""Issue & Discussion collector for BuilderDNA 2.0."""
from collect.github.client import GitHubClient


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
    except Exception:
        return []

    extracted = []
    for issue in issues_data:
        if issue.get("pull_request") is not None:
            continue  # skip PRs

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
    owner, repo_name = repo.split("/", 1)
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
    except Exception:
        return []
