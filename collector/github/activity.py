"""Limited evidence collection for DeveloperDNA (P5).

Fetches a bounded summary of a repo's activity — PRs, releases, commits, and
CI/test presence — so the DeveloperDNA computation can populate
``build_patterns``, ``iteration_style``, and ``testing_reliability_signals``
rather than reporting ``unknown``. Bounded by design: fixed per-page caps and a
single page per endpoint.
"""
from collector.github.client import GitHubClient


async def _path_exists(client: GitHubClient, path: str) -> bool:
    """Whether a contents path exists (non-404)."""
    try:
        resp = await client._request("GET", path)
        return resp is not None
    except Exception:
        return False


async def fetch_repo_activity(client: GitHubClient, repo: str) -> dict:
    """Fetch a bounded activity summary for one repo.

    Bounded: 30 PRs, 10 releases, 30 commits, plus a best-effort CI/test check.
    Never raises — returns zero/default fields on any per-endpoint error so a
    partial fetch still yields a usable (if sparse) summary.
    """
    summary: dict = {
        "repo": repo,
        "open_prs": 0,
        "merged_prs": 0,
        "recent_commits": 0,
        "releases": 0,
        "has_ci": False,
        "has_tests": False,
    }

    try:
        prs = await client._paginate(
            f"/repos/{repo}/pulls",
            extra_params={"state": "all", "per_page": "30"},
            max_pages=1,
        )
        summary["open_prs"] = sum(1 for p in prs if p.get("state") == "open")
        summary["merged_prs"] = sum(1 for p in prs if p.get("merged_at") is not None)
    except Exception:
        pass

    try:
        releases = await client._paginate(
            f"/repos/{repo}/releases",
            extra_params={"per_page": "10"},
            max_pages=1,
        )
        summary["releases"] = len(releases)
    except Exception:
        pass

    try:
        commits = await client._paginate(
            f"/repos/{repo}/commits",
            extra_params={"per_page": "30"},
            max_pages=1,
        )
        summary["recent_commits"] = len(commits)
    except Exception:
        pass

    summary["has_ci"] = await _path_exists(client, f"/repos/{repo}/contents/.github/workflows")
    summary["has_tests"] = await _path_exists(client, f"/repos/{repo}/contents/tests")
    return summary
