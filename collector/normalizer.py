"""Signal normalizer — GitHub API raw dicts → unified Signal model."""
from datetime import datetime, timezone
from uuid import uuid4

from signals.models import Signal


def _parse_time(date_str: str | None) -> datetime:
    """Parse ISO timestamp from raw data, fall back to now."""
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _days_since(date_str: str | None) -> int:
    """Days between date_str and now."""
    if not date_str:
        return 365
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return max(1, (datetime.now(timezone.utc) - dt).days)
    except (ValueError, TypeError):
        return 365


def _compute_velocity(stars: int, created_at: str | None) -> float:
    """Simple velocity: stars / days_since_creation."""
    days = _days_since(created_at)
    return round(stars / max(1, days), 2)


def normalize_repo(raw: dict) -> Signal:
    """GitHub repo API response → Signal."""
    full_name = raw.get("full_name", "")
    owner = raw.get("owner", {})
    actor = owner.get("login", "") if isinstance(owner, dict) else str(owner)
    stars = raw.get("stargazers_count", 0)
    created_at = raw.get("created_at")
    velocity = _compute_velocity(stars, created_at)

    return Signal(
        source="github",
        type="repo_created",
        actor=actor,
        target_repo=full_name,
        timestamp=_parse_time(created_at),
        velocity=velocity,
        impact=min(1.0, stars / 10000.0),
        payload={
            "topics": raw.get("topics", []),
            "description": raw.get("description", ""),
            "stars": stars,
            "forks": raw.get("forks_count", 0),
            "language": raw.get("language", ""),
            "created_at": created_at,
        },
    )


def normalize_issue(raw: dict) -> Signal:
    """GitHub issue (pre-processed by collector) → Signal."""
    reactions = raw.get("reactions", 0)
    participants = raw.get("participants", 0)
    # Impact: engagement strength — participants + reactions together
    impact = min(1.0, (participants + reactions / 5.0) / 10.0)

    return Signal(
        source="github",
        type="issue_opened",
        actor=raw.get("user_login", "unknown"),
        target_repo=raw.get("repo", ""),
        timestamp=_parse_time(raw.get("created_at")),
        impact=impact,
        payload={
            "issue_number": raw.get("issue_number", 0),
            "title": raw.get("title", ""),
            "body": raw.get("body", ""),
            "comments": raw.get("comments", 0),
            "participants": participants,
            "reactions": reactions,
            "labels": raw.get("labels", []),
            "url": raw.get("url", ""),
        },
    )


def normalize_star_event(raw: dict, repo_name: str) -> Signal:
    """Star growth data point → Signal."""
    return Signal(
        source="github",
        type="star_growth",
        actor="",
        target_repo=repo_name,
        timestamp=_parse_time(raw.get("created_at")),
        velocity=raw.get("stars", 0),
        payload=raw,
    )


def normalize_all(
    raw_repos: list[dict] | None = None,
    raw_issues: list[dict] | None = None,
    raw_stars: list[dict] | None = None,
) -> list[Signal]:
    """Normalize all raw data into a unified Signal list."""
    signals: list[Signal] = []

    for r in (raw_repos or []):
        signals.append(normalize_repo(r))

    for i in (raw_issues or []):
        signals.append(normalize_issue(i))

    for s in (raw_stars or []):
        signals.append(normalize_star_event(s, s.get("repo", "")))

    return signals
