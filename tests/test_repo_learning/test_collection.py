"""Tests for GitHub collection mapping helpers (no network)."""

import asyncio

from repo_learning import collection
from repo_learning.models import SourceKind


def test_parse_dt_utc():
    dt = collection._parse_dt("2020-01-01T00:00:00Z")
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


def test_parse_dt_absent_is_none():
    assert collection._parse_dt(None) is None
    assert collection._parse_dt("") is None


def test_pull_number_extraction():
    assert collection._pull_number("https://github.com/o/r/pull/123") == 123
    assert collection._pull_number("https://github.com/o/r") is None
    assert collection._pull_number(None) is None


def test_linked_issue_numbers_dedup_and_priority():
    body = "Closes #12 and fixes #34. Also mentions #12 and #99."
    assert collection._linked_issue_numbers(body) == [12, 34, 99]


def test_src_id_and_content_hash():
    rec = collection._src(
        "github_pr:o/r#1",
        SourceKind.GITHUB_PR,
        "https://github.com/o/r/pull/1",
        "alice",
        "2020-01-01T00:00:00Z",
        "body",
    )
    assert rec.id == "github_pr:o/r#1"
    assert rec.content_hash != ""
    assert rec.author == "alice"
    assert rec.published_at is not None


def test_count_by_kind():
    records = [
        collection._src("a", SourceKind.GITHUB_PR, "u1", "", None, "x"),
        collection._src("b", SourceKind.GITHUB_REVIEW, "u2", "", None, "x"),
        collection._src("c", SourceKind.GITHUB_REVIEW, "u3", "", None, "x"),
    ]
    counts = collection._count_by_kind(records)
    assert counts == {"github_pr": 1, "github_review": 2}


def test_collect_pr_maps_records(monkeypatch):
    from collector.github import pull as gh_pull

    async def fake_pull(client, repo, number):
        return {
            "number": number,
            "html_url": f"https://github.com/{repo}/pull/{number}",
            "title": "t",
            "body": "b",
            "user": {"login": "a"},
            "created_at": "2020-01-01T00:00:00Z",
        }

    async def fake_list(client, repo, number):
        return []

    async def fake_diff(client, repo, number):
        return "diff text"

    monkeypatch.setattr(gh_pull, "fetch_pull", fake_pull)
    monkeypatch.setattr(gh_pull, "fetch_pull_reviews", fake_list)
    monkeypatch.setattr(gh_pull, "fetch_pull_review_comments", fake_list)
    monkeypatch.setattr(gh_pull, "fetch_issue_comments", fake_list)
    monkeypatch.setattr(gh_pull, "fetch_pull_commits", fake_list)
    monkeypatch.setattr(gh_pull, "fetch_pull_files", fake_list)
    monkeypatch.setattr(gh_pull, "fetch_pull_diff", fake_diff)

    records = asyncio.run(collection._collect_pr(None, "o/r", 1))
    kinds = {r.kind for r in records}
    assert SourceKind.GITHUB_PR in kinds
    assert SourceKind.GITHUB_DIFF in kinds
    diff = next(r for r in records if r.kind == SourceKind.GITHUB_DIFF)
    assert diff.body == "diff text"
