"""Tests for investigations/actions.py — deterministic action executors."""
from investigations.actions import (
    execute,
    normalize_post,
)
from investigations.models import EvidenceRecord


SAMPLE_POST = {
    "id": "abc123",
    "title": "We keep copy-pasting onboarding steps",
    "author": "alice",
    "permalink": "https://www.reddit.com/r/SaaS/comments/abc123/onboarding",
    "published": "2026-09-01T10:00:00Z",
    "selftext": "Every new customer we copy-paste the same steps. It's manual and error-prone.",
    "category": "",
}


def test_normalize_post_builds_evidence_record():
    rec = normalize_post(SAMPLE_POST, "inv_1")
    assert isinstance(rec, EvidenceRecord)
    assert rec.investigation_id == "inv_1"
    assert rec.item.source.value == "reddit"
    assert rec.item.url == SAMPLE_POST["permalink"]
    assert rec.item.author == "alice"
    # first-person body -> DIRECT
    assert rec.item.directness.value == "direct"


def test_search_discussions_no_results():
    def empty_fetcher(subreddit, sort, limit):
        return []

    out = execute("search_discussions", {"subreddit": "SaaS"}, fetcher=empty_fetcher, evidence=[])
    assert out["status"] == "no_results"
    assert out["new_evidence"] == []


def test_search_discussions_collects_posts():
    def two_fetcher(subreddit, sort, limit):
        return [SAMPLE_POST, {**SAMPLE_POST, "id": "def456"}]

    out = execute("search_discussions", {"subreddit": "SaaS"}, fetcher=two_fetcher, evidence=[], investigation_id="inv_1")
    assert out["status"] == "completed"
    assert len(out["new_evidence"]) == 2
    ids = {e.id for e in out["new_evidence"]}
    assert ids == {"reddit:abc123", "reddit:def456"}


def test_search_discussions_dedupes_against_existing():
    existing = normalize_post(SAMPLE_POST, "inv_1")

    def one_fetcher(subreddit, sort, limit):
        return [SAMPLE_POST]

    out = execute("search_discussions", {"subreddit": "SaaS"}, fetcher=one_fetcher, evidence=[existing], investigation_id="inv_1")
    assert out["status"] == "no_results"  # only post already known
    assert out["new_evidence"] == []


def test_search_discussions_source_failure():
    def failing_fetcher(subreddit, sort, limit):
        raise RuntimeError("network down")

    out = execute("search_discussions", {"subreddit": "SaaS"}, fetcher=failing_fetcher, evidence=[])
    assert out["status"] == "source_failure"


def test_find_similar_cases_groups_by_independence_key():
    # Both posts cite the same upstream URL, so they share independence key
    post_with_upstream = {**SAMPLE_POST, "selftext": "this is a problem https://github.com/acme/tool"}
    a = normalize_post(post_with_upstream, "inv_1")
    repost = {**SAMPLE_POST, "id": "xyz", "selftext": "repost of https://github.com/acme/tool"}
    b = normalize_post(repost, "inv_1")
    out = execute("find_similar_cases", {}, fetcher=None, evidence=[a, b])
    assert out["status"] == "completed"
    keys = {g["independence_key"] for g in out["observation"]["groups"]}
    assert keys == {a.item.independence_key}


def test_seek_counterevidence_records_coverage():
    out = execute("seek_counterevidence", {"query": "existing tool"}, fetcher=None, evidence=[])
    assert out["status"] == "completed"
    assert "coverage" in out["observation"]
