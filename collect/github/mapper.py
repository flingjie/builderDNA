"""GitHub data → Signal mapper.

Transforms raw GitHub API responses into the unified Signal model.
No LLM involvement. Pure data transformation.
"""

from datetime import datetime
from typing import Any

from models.signal import Signal


def map_repo(raw: dict[str, Any], actor: str, weight: float) -> Signal:
    """Map a raw GitHub repo dict to a Signal.

    Args:
        raw: Raw repo object from GitHub API.
        actor: The builder account being analyzed.
        weight: Signal weight from config.

    Returns:
        A Signal of type 'repo'.
    """
    repo_id = raw.get("id", raw.get("full_name", "unknown"))
    return Signal(
        id=f"gh_repo_{actor}_{raw.get('full_name', repo_id).replace('/', '_')}",
        source="github",
        type="repo",
        timestamp=datetime.fromisoformat(
            raw.get("updated_at", raw.get("created_at", "1970-01-01T00:00:00Z")).replace("Z", "+00:00")
        ),
        weight=weight,
        actor=actor,
        target=raw.get("full_name", ""),
        meta={
            "language": raw.get("language") or "",
            "topics": raw.get("topics", []),
            "description": raw.get("description") or "",
            "stars": raw.get("stargazers_count", 0),
            "forks": raw.get("forks_count", 0),
        },
        raw=raw,
    )


def map_star(raw: dict[str, Any], actor: str, weight: float) -> Signal:
    """Map a raw starred repo dict to a Signal.

    Args:
        raw: Raw repo object (from /starred endpoint).
        actor: The builder account.
        weight: Signal weight from config.

    Returns:
        A Signal of type 'star'.
    """
    repo_id = raw.get("id", raw.get("full_name", "unknown"))
    return Signal(
        id=f"gh_star_{repo_id}",
        source="github",
        type="star",
        timestamp=datetime.fromisoformat(
            raw.get("updated_at", raw.get("created_at", "1970-01-01T00:00:00Z")).replace("Z", "+00:00")
        ),
        weight=weight,
        actor=actor,
        target=raw.get("full_name", ""),
        meta={
            "language": raw.get("language") or "",
            "topics": raw.get("topics", []),
            "description": raw.get("description") or "",
            "stars": raw.get("stargazers_count", 0),
        },
        raw=raw,
    )


def map_commit(raw: dict[str, Any], actor: str, weight: float) -> Signal:
    """Map a raw commit dict to a Signal.

    Args:
        raw: Raw commit object from GitHub API.
        actor: The builder account.
        weight: Signal weight from config.

    Returns:
        A Signal of type 'commit'.
    """
    sha = raw.get("sha", "")
    commit_data = raw.get("commit", {})
    author = commit_data.get("author", {})
    date_str = author.get("date", "1970-01-01T00:00:00Z")

    # Extract repo full_name from html_url or fallback
    html_url = raw.get("html_url", "")
    parts = html_url.split("/")
    repo_full_name = "/".join(parts[3:5]) if len(parts) >= 5 else ""

    return Signal(
        id=f"gh_commit_{sha}",
        source="github",
        type="commit",
        timestamp=datetime.fromisoformat(date_str.replace("Z", "+00:00")),
        weight=weight,
        actor=actor,
        target=commit_data.get("message", ""),
        meta={
            "repo": repo_full_name,
            "message": commit_data.get("message", ""),
            "url": html_url,
        },
        raw=raw,
    )


def map_all(
    raw_repos: list[dict[str, Any]],
    raw_starred: list[dict[str, Any]],
    raw_commits_by_repo: dict[str, list[dict[str, Any]]],
    actor: str,
    repo: float = 5.0,
    star: float = 1.0,
    commit: float = 3.0,
) -> list[Signal]:
    """Map all raw GitHub data for one actor into Signals.

    Args:
        raw_repos: Raw repo dicts from /users/{actor}/repos.
        raw_starred: Raw repo dicts from /users/{actor}/starred.
        raw_commits_by_repo: Dict mapping repo full_name → list of commit dicts.
        actor: The builder account.
        repo: Weight for repo signals.
        star: Weight for star signals.
        commit: Weight for commit signals.

    Returns:
        Flat list of all Signals.
    """
    signals: list[Signal] = []

    for r in raw_repos:
        repo_data = r.get("repo_data", r)
        signals.append(map_repo(repo_data, actor, repo))

    for s in raw_starred:
        star_data = s.get("repo_data", s)
        signals.append(map_star(star_data, actor, star))

    for _repo_name, commits in raw_commits_by_repo.items():
        for c in commits:
            commit_data = c.get("commit_data", c)
            signals.append(map_commit(commit_data, actor, commit))

    return signals
