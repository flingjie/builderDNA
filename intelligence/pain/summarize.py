"""Deterministic cluster summary for the pain pipeline's finalize step.

Turns a set of confirmed issues (resolved from the Agent's confirmation, or
promoted from a candidate group) into a final ``PainCluster`` with severity,
frequency, cross-repo reach, recurrence span, and workarounds. Reuses the
deterministic severity scorer from ``intelligence/pain/severity.py``.
"""

from __future__ import annotations

from datetime import datetime

from intelligence.pain.severity import compute_severity
from models.payload import CandidateGroup, IssueSummary, PainCluster

_WORKAROUND_KEYWORDS = (
    "workaround", "hack", "temporary fix", "patch it", "bypass",
    "绕过", "临时", "规避", "替代方案", "换一个", "先用",
)


def _extract_workarounds(issues: list[dict]) -> list[str]:
    """Deterministic scan for workarounds the community already uses.

    Best-effort keyword match over title+body; empty when none found. This is
    a deterministic hint, not a semantic judgment.
    """
    found: list[str] = []
    for iss in issues:
        text = f"{iss.get('title', '')} {iss.get('body', '')}".lower()
        for kw in _WORKAROUND_KEYWORDS:
            idx = text.find(kw)
            if idx >= 0:
                snippet = text[max(0, idx - 20):idx + 40].strip()
                if snippet not in found:
                    found.append(snippet)
                break
    return found[:5]


def _compute_time_span_days(issues: list[dict]) -> int:
    """Days between the earliest and latest issue in a cluster (recurrence span).

    Returns 0 when there are fewer than two dated issues (span unknown).
    """
    dates = []
    for iss in issues:
        ca = (iss.get("created_at") or "").strip()
        if not ca:
            continue
        try:
            dates.append(datetime.fromisoformat(ca.replace("Z", "+00:00")))
        except (ValueError, TypeError):
            continue
    if len(dates) < 2:
        return 0
    return max(0, (max(dates) - min(dates)).days)


def title_hint(group: CandidateGroup) -> str:
    """A deterministic fallback title for a candidate group.

    The Agent confirmation step supplies real titles; this is only a label for
    the no-confirmation path. Prefers a shared error code, then a shared
    component, then the first member's title.
    """
    shared = group.shared_features or {}
    codes = shared.get("error_codes") or []
    if codes:
        return f"{codes[0]} issues"
    comps = shared.get("components") or []
    if comps:
        return f"{comps[0]} issues"
    titles = [c.title.strip() for c in group.issues if c.title.strip()]
    return titles[0][:80] if titles else f"Pain Cluster {group.group_id}"


def summarize_cluster(
    candidates,
    *,
    cluster_id: int,
    title: str,
) -> PainCluster:
    """Compute the final ``PainCluster`` for a resolved set of candidates.

    ``candidates`` are ``PainCandidate`` objects (or anything exposing
    ``model_dump()`` with repo/issue_number/title/body/comments/participants/
    reactions/created_at).
    """
    issues = [c.model_dump() for c in candidates]
    severities = [
        compute_severity(
            iss.get("comments", 0),
            iss.get("participants", 0),
            (iss.get("title", "") + " " + iss.get("body", ""))[:500],
            iss.get("reactions", 0),
        )
        for iss in issues
    ]
    repos = list(dict.fromkeys(iss.get("repo", "") for iss in issues))
    top = sorted(
        issues,
        key=lambda x: x.get("reactions", 0) + x.get("comments", 0),
        reverse=True,
    )[:3]

    return PainCluster(
        cluster_id=cluster_id,
        title=title,
        severity=round(sum(severities) / len(severities), 2),
        frequency=len(issues),
        affected_repos=repos,
        independent_repo_count=len(repos),
        time_span_days=_compute_time_span_days(issues),
        existing_workarounds=_extract_workarounds(issues),
        top_issues=[
            IssueSummary(
                repo=iss.get("repo", ""),
                issue_number=iss.get("issue_number", 0),
                title=iss.get("title", "")[:100],
                pain_score=compute_severity(
                    iss.get("comments", 0),
                    iss.get("participants", 0),
                    (iss.get("title", "") + " " + iss.get("body", ""))[:500],
                    iss.get("reactions", 0),
                ),
            )
            for iss in top
        ],
    )
