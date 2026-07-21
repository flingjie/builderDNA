"""Pain Mining Engine — automatically extracts and clusters developer pain points from GitHub issues.

Phase 2: Issues → LLM scores → clusters of pain patterns.
"""
import asyncio
import math
from typing import cast

from backend.models.pain import PainIssue, PainCluster, PainSnapshot
from backend.store.pain_store import PainStore


async def fetch_issues(client, repo: str, max_issues: int = 20) -> list[dict]:
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
            # Skip pull requests, only want issues
            continue

        # Estimate unique participants: author + min(comments, 5) as upper bound
        # A single person posting N comments is 1 participant, not N
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


async def score_issues(issues: list[dict], llm) -> list[PainIssue]:
    """Score issues by pain level using LLM.

    Rate each issue 1-5 (5=critical/blocking, 3=annoying, 1=minor).
    Be strict — most issues should be 2-3.

    Pain Score = score × log(comments + 1) × log(participants + 1)

    Args:
        issues: List of issue dictionaries from fetch_issues.
        llm: LLM client instance with complete() method.

    Returns:
        List of PainIssue with pain_score computed.
    """
    if not issues:
        return []

    # Build prompt listing all issues
    issues_list = []
    for issue in issues:
        repo = issue.get("repo", "")
        num = issue.get("issue_number", 0)
        title = issue.get("title", "")[:100]
        body = issue.get("body", "")[:200]
        issues_list.append(f"#{num} [{repo}] {title}: {body}")

    prompt = f"""Rate the pain level (1-5) of each GitHub issue below.
5 = critical, blocking production, no workaround. 3 = annoying, slows development. 1 = minor, cosmetic.
Be strict — most issues should be 2-3.

Issues:
{chr(10).join(issues_list)}

Return JSON: {{"scores": [{{"issue_number": N, "score": S, "key_phrase": "brief pain phrase"}}, ...]}}
"""

    try:
        response = llm.complete(prompt, response_format=dict)
    except Exception:
        # Return issues with base pain_score of 0 if LLM fails
        return [_issue_to_pain_issue(issue, 1.0) for issue in issues]

    scores = response.get("scores", [])
    score_map = {s.get("issue_number"): s for s in scores if isinstance(s, dict)}

    result = []
    for issue in issues:
        num = issue.get("issue_number", 0)
        if num in score_map:
            score = score_map[num].get("score", 1)
        else:
            score = 1

        pain_issue = _issue_to_pain_issue(issue, score)
        pain_issue.pain_score = _compute_pain_score(pain_issue, score)
        result.append(pain_issue)

    return result


def _issue_to_pain_issue(issue: dict, base_score: int = 1) -> PainIssue:
    """Convert raw issue dict to PainIssue with base values."""
    return PainIssue(
        repo=issue.get("repo", ""),
        issue_number=issue.get("issue_number", 0),
        title=issue.get("title", ""),
        body=issue.get("body", ""),
        comments=issue.get("comments", 0),
        participants=issue.get("participants", 0),
        pain_score=0.0,
        labels=issue.get("labels", []),
        url=issue.get("url", ""),
    )


def _compute_pain_score(issue: PainIssue, score: int | float) -> float:
    """Compute final pain score.

    Formula: score × log(comments + 1) × log(participants + 1)
    """
    if issue.comments <= 0 and issue.participants <= 0:
        return float(score)

    comment_factor = math.log(issue.comments + 1)
    participant_factor = math.log(issue.participants + 1)

    return score * comment_factor * participant_factor


async def cluster_pains(issues: list[PainIssue], llm) -> list[PainCluster]:
    """Cluster pain issues into patterns using LLM.

    Group into 3-5 patterns, name each, describe root cause.

    LLM prompt lists all issues with scores, asks for patterns.

    Returns:
        List of PainCluster objects.
    """
    if not issues:
        return []

    # Build prompt with scored issues
    issues_list = []
    for issue in issues:
        title = issue.title[:80]
        score = int(issue.pain_score) if issue.pain_score < 5 else 5
        key_phrase = getattr(issue, "key_phrase", "") or ""
        issues_list.append(f"#{issue.issue_number} [score={score}] {key_phrase}: {title}")

    prompt = f"""Group these developer pain points into 3-5 patterns. Each pattern = a recurring pain.

Issues (with scores):
{chr(10).join(issues_list)}

Return JSON: {{"clusters": [{{"title": "≤5 words", "root_cause": "1 sentence why", "issue_numbers": [N,N], "severity": avg_score}}]}}
"""

    try:
        response = llm.complete(prompt, response_format=dict)
    except Exception:
        # Fallback: create a single cluster with all issues
        avg_score = sum(i.pain_score for i in issues) / len(issues) if issues else 0
        return [
            PainCluster(
                title="Uncategorized Pain",
                severity=avg_score,
                frequency=len(issues),
                description="Could not cluster issues due to LLM error",
                evidence=issues[:5],
                affected_repos=list(set(i.repo for i in issues)),
            )
        ]

    clusters_data = response.get("clusters", [])
    result = []

    for cluster in clusters_data:
        if not isinstance(cluster, dict):
            continue

        title = cluster.get("title", "Unknown Pattern")[:50]
        root_cause = cluster.get("root_cause", "")
        issue_numbers = cluster.get("issue_numbers", [])
        severity = cluster.get("severity", 1.0)

        # Map issue_numbers to actual PainIssue objects
        evidence = [i for i in issues if i.issue_number in issue_numbers]
        affected_repos = list(set(i.repo for i in evidence))

        # Recompute severity as avg of included issues if not provided
        if not cluster.get("severity"):
            severity = sum(i.pain_score for i in evidence) / len(evidence) if evidence else 1.0

        result.append(
            PainCluster(
                title=title,
                severity=round(severity, 2),
                frequency=len(evidence),
                description=root_cause,
                evidence=evidence[:10],  # Top 10 evidence
                affected_repos=affected_repos,
            )
        )

    return result


async def run_pain_mining(client, top_repos: list[str], llm, store) -> PainSnapshot:
    """Run the complete pain mining pipeline.

    For each repo: fetch_issues → score_issues → cluster_pains.
    Build PainSnapshot, save, return.

    Args:
        client: GitHubClient instance.
        top_repos: List of repository full names.
        llm: LLM client instance.
        store: PainStore instance for persistence.

    Returns:
        PainSnapshot with clusters, issue_count, repos_analyzed.
    """
    all_issues: list[PainIssue] = []

    # Fetch and process issues for each repo
    for repo in top_repos:
        raw_issues = await fetch_issues(client, repo)
        scored = await score_issues(raw_issues, llm)
        all_issues.extend(scored)

    # Cluster all aggregated pain points
    clusters = await cluster_pains(all_issues, llm)

    # Build snapshot
    snapshot = PainSnapshot(
        domain="developer_pain",
        clusters=clusters,
        issue_count=len(all_issues),
        repos_analyzed=top_repos,
    )

    # Save to store
    store.save(snapshot)

    return snapshot
