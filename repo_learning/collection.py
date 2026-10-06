"""GitHub collection for repo-evolution-learning.

The thin adapter that turns raw GitHub API dicts into :class:`SourceRecord`
lines in the run workspace. It does no web search and no content fetching — those
are skill-owned. It reuses the existing :class:`GitHubClient` (cache + rate limit
+ retry) and the raw fetchers in ``collector/github/{metadata,pull}.py``.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from config import Config
from collector.github.client import GitHubClient
from collector.github import metadata as gh_metadata
from collector.github import pull as gh_pull
from repo_learning.models import (
    FetchStatus,
    SourceKind,
    SourceRecord,
)
from repo_learning.request import RequestSpec, parse_repo_ref
from repo_learning import workspace

# Closing keywords used to discover linked issues from a PR body.
_CLOSE_KEYWORDS = re.compile(
    r"(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+#?(\d+)",
    re.IGNORECASE,
)
_PLAIN_REF = re.compile(r"#(\d+)")


def _parse_dt(value) -> datetime | None:
    """Parse a GitHub ISO-8601 timestamp to aware UTC, or None when absent."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sha1(body: str) -> str:
    return hashlib.sha1(body.encode("utf-8")).hexdigest() if body else ""


def _src(
    id_: str,
    kind: SourceKind,
    url: str,
    author: str,
    published_at,
    body: str,
    *,
    fetch_status: FetchStatus = FetchStatus.FULL,
    missing_scope: list[str] | None = None,
) -> SourceRecord:
    return SourceRecord(
        id=id_,
        kind=kind,
        url=url or "",
        canonical_url=url or "",
        author=author,
        published_at=_parse_dt(published_at),
        body=body,
        fetch_status=fetch_status,
        missing_scope=missing_scope or [],
        content_hash=_sha1(body),
    )


def _pull_number(entry_url: str | None) -> int | None:
    """Extract a PR number from a ``/pull/<n>`` entry URL, else None."""
    if not entry_url:
        return None
    m = re.search(r"/pull/(\d+)", entry_url)
    return int(m.group(1)) if m else None


def _issue_number(entry_url: str | None) -> int | None:
    if not entry_url:
        return None
    m = re.search(r"/issues/(\d+)", entry_url)
    return int(m.group(1)) if m else None


def _linked_issue_numbers(pr_body: str, limit: int = 5) -> list[int]:
    """Discover linked issue numbers from closing keywords and plain ``#N`` refs."""
    closing = [int(m) for m in _CLOSE_KEYWORDS.findall(pr_body or "")]
    plain = [int(m) for m in _PLAIN_REF.findall(pr_body or "")]
    seen: list[int] = []
    for n in closing + plain:
        if n not in seen and n > 0:
            seen.append(n)
        if len(seen) >= limit:
            break
    return seen


async def collect_github(
    request: RequestSpec,
    cfg: Config,
    run_dir: Path,
    *,
    entry_url: str | None = None,
    no_cache: bool = False,
) -> dict:
    """Collect GitHub material for the request into the run workspace.

    Fetches repo metadata + README always. When an entry PR is known (from
    ``entry_url`` override or the request), fetches its full detail (reviews,
    review comments, discussion, commits, files, diff), linked issues, and
    bounded follow-ups. Otherwise fetches a bounded list of recent PR metadata
    for the skill to select from.
    """
    repo = request.full_name
    effective_entry = entry_url or request.entry_url
    pr_number = _pull_number(effective_entry)
    issue_number = _issue_number(effective_entry)
    limits = request.limits

    client = GitHubClient(
        token=cfg.github.token,
        cache_dir=cfg.github.cache_dir,
        max_concurrent=cfg.github.max_concurrent,
        rate_limit_margin=cfg.github.rate_limit_margin,
        disable_cache=no_cache,
    )

    records: list[SourceRecord] = []
    warnings: list[str] = []
    observation_cutoff: datetime | None = None

    try:
        # 1. Repo metadata + README
        meta = await gh_metadata.fetch_repo_metadata(client, repo)
        if meta:
            records.append(
                _src(
                    f"github_repo:{repo}",
                    SourceKind.GITHUB_REPO,
                    meta.get("html_url", f"https://github.com/{repo}"),
                    meta.get("owner", {}).get("login", "") if isinstance(meta.get("owner"), dict) else "",
                    meta.get("created_at"),
                    meta.get("description", "") or "",
                )
            )
        else:
            warnings.append(f"repo metadata not found for {repo}")

        readme = await gh_metadata.fetch_readme(client, repo)
        if readme:
            records.append(
                _src(
                    f"github_readme:{repo}",
                    SourceKind.GITHUB_README,
                    f"https://github.com/{repo}#readme",
                    "",
                    None,
                    readme,
                )
            )

        # 2. Entry PR detail (or recent-PR candidates)
        if pr_number:
            records.extend(await _collect_pr(client, repo, pr_number))
            pr = await gh_pull.fetch_pull(client, repo, pr_number)
            if pr:
                observation_cutoff = _parse_dt(pr.get("merged_at") or pr.get("created_at"))
                records.extend(await _collect_followups(client, repo, pr))
        elif issue_number:
            issue = await gh_pull.fetch_issue(client, repo, issue_number)
            if issue:
                records.append(
                    _src(
                        f"github_issue:{repo}#{issue_number}",
                        SourceKind.GITHUB_ISSUE,
                        issue.get("html_url", ""),
                        (issue.get("user") or {}).get("login", ""),
                        issue.get("created_at"),
                        f"{issue.get('title', '')}\n\n{issue.get('body', '') or ''}",
                    )
                )
        else:
            records.extend(await _collect_recent_prs(client, repo, limits))

    finally:
        await client.close()

    for r in records:
        workspace.append_source(run_dir, r)

    return {
        "records": len(records),
        "by_kind": _count_by_kind(records),
        "warnings": warnings,
        "observation_cutoff": observation_cutoff,
    }


def _count_by_kind(records: list[SourceRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        counts[r.kind.value] = counts.get(r.kind.value, 0) + 1
    return counts


async def _collect_pr(client: GitHubClient, repo: str, number: int) -> list[SourceRecord]:
    """Fetch full detail for one PR."""
    records: list[SourceRecord] = []

    pr = await gh_pull.fetch_pull(client, repo, number)
    if pr:
        records.append(
            _src(
                f"github_pr:{repo}#{number}",
                SourceKind.GITHUB_PR,
                pr.get("html_url", ""),
                (pr.get("user") or {}).get("login", ""),
                pr.get("created_at"),
                f"{pr.get('title', '')}\n\n{pr.get('body', '') or ''}",
            )
        )

    for review in await gh_pull.fetch_pull_reviews(client, repo, number):
        rid = review.get("id") or review.get("node_id") or review.get("submitted_at", "")
        records.append(
            _src(
                f"github_review:{repo}#{number}:{rid}",
                SourceKind.GITHUB_REVIEW,
                review.get("html_url", ""),
                (review.get("user") or {}).get("login", ""),
                review.get("submitted_at"),
                f"[{review.get('state', '')}] {review.get('body', '') or ''}",
            )
        )

    for comment in await gh_pull.fetch_pull_review_comments(client, repo, number):
        cid = comment.get("id") or comment.get("node_id", "")
        path = comment.get("path", "")
        body = f"{path}:{comment.get('line', '')}\n{comment.get('body', '') or ''}"
        records.append(
            _src(
                f"github_review_comment:{repo}#{number}:{cid}",
                SourceKind.GITHUB_REVIEW_COMMENT,
                comment.get("html_url", ""),
                (comment.get("user") or {}).get("login", ""),
                comment.get("created_at"),
                body,
            )
        )

    for comment in await gh_pull.fetch_issue_comments(client, repo, number):
        cid = comment.get("id") or comment.get("node_id", "")
        records.append(
            _src(
                f"github_issue_comment:{repo}#{number}:{cid}",
                SourceKind.GITHUB_ISSUE_COMMENT,
                comment.get("html_url", ""),
                (comment.get("user") or {}).get("login", ""),
                comment.get("created_at"),
                comment.get("body", "") or "",
            )
        )

    for commit in await gh_pull.fetch_pull_commits(client, repo, number):
        sha = commit.get("sha", "") or (commit.get("commit", {}) or {}).get("node_id", "")
        msg = (commit.get("commit") or {}).get("message", "")
        records.append(
            _src(
                f"github_commit:{repo}@{sha[:12]}",
                SourceKind.GITHUB_COMMIT,
                commit.get("html_url", ""),
                (commit.get("author") or {}).get("login", ""),
                (commit.get("commit") or {}).get("author", {}).get("date"),
                msg,
            )
        )

    for f in await gh_pull.fetch_pull_files(client, repo, number):
        filename = f.get("filename", "")
        patch = f.get("patch", "") or ""
        body = f"{filename} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})\n{patch}"
        missing = [] if patch else ["per-file patch omitted (large file)"]
        records.append(
            _src(
                f"github_file:{repo}#{number}:{filename}",
                SourceKind.GITHUB_FILE,
                f.get("blob_url", "") or "",
                "",
                None,
                body,
                fetch_status=FetchStatus.PARTIAL if missing else FetchStatus.FULL,
                missing_scope=missing,
            )
        )

    diff = await gh_pull.fetch_pull_diff(client, repo, number)
    if diff:
        records.append(
            _src(
                f"github_diff:{repo}#{number}",
                SourceKind.GITHUB_DIFF,
                f"https://github.com/{repo}/pull/{number}.diff",
                "",
                None,
                diff,
            )
        )

    return records


async def _collect_followups(
    client: GitHubClient, repo: str, pr: dict
) -> list[SourceRecord]:
    """Fetch linked issues and bounded follow-up issues for a PR."""
    records: list[SourceRecord] = []
    number = pr.get("number", 0)

    # Linked issues referenced in the PR body.
    for linked in _linked_issue_numbers(pr.get("body", "") or ""):
        issue = await gh_pull.fetch_issue(client, repo, linked)
        if issue and not issue.get("pull_request"):
            records.append(
                _src(
                    f"github_issue:{repo}#{linked}",
                    SourceKind.GITHUB_ISSUE,
                    issue.get("html_url", ""),
                    (issue.get("user") or {}).get("login", ""),
                    issue.get("created_at"),
                    f"{issue.get('title', '')}\n\n{issue.get('body', '') or ''}",
                )
            )

    # Bounded follow-ups since the PR's creation/merge.
    since = pr.get("merged_at") or pr.get("created_at")
    if since:
        followups = await gh_pull.fetch_repo_issues_since(
            client, repo, since, per_page=30
        )
        for issue in followups:
            if issue.get("number") == number:
                continue
            records.append(
                _src(
                    f"github_issue:{repo}#{issue.get('number')}",
                    SourceKind.GITHUB_ISSUE,
                    issue.get("html_url", ""),
                    (issue.get("user") or {}).get("login", ""),
                    issue.get("created_at"),
                    f"{issue.get('title', '')}\n\n{(issue.get('body') or '')[:2000]}",
                    fetch_status=FetchStatus.PARTIAL,
                    missing_scope=["follow-up metadata only"],
                )
            )

    return records


async def _collect_recent_prs(client: GitHubClient, repo: str, limits) -> list[SourceRecord]:
    """Fetch metadata for a bounded list of recent PRs (for the skill to select)."""
    records: list[SourceRecord] = []
    cap = limits.candidate_episodes
    for pr in await gh_pull.fetch_recent_pulls(client, repo, per_page=cap):
        number = pr.get("number", 0)
        records.append(
            _src(
                f"github_pr:{repo}#{number}",
                SourceKind.GITHUB_PR,
                pr.get("html_url", ""),
                (pr.get("user") or {}).get("login", ""),
                pr.get("created_at"),
                f"{pr.get('title', '')}\n\n{(pr.get('body') or '')[:2000]}",
                fetch_status=FetchStatus.PARTIAL,
                missing_scope=["PR metadata only; run collect --entry-url <PR> for detail"],
            )
        )
    return records
