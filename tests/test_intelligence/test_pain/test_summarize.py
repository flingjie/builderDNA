"""Tests for intelligence/pain/summarize.py — final cluster summary."""

from intelligence.pain.candidates import build_candidates
from intelligence.pain.summarize import summarize_cluster, title_hint
from models.payload import CandidateGroup


def _candidates(*issues: dict):
    return build_candidates(list(issues))


def _issue(repo="org/a", issue_number=1, title="timeout", body="", comments=0, participants=0, reactions=0, created_at="", labels=None):
    return {
        "repo": repo,
        "issue_number": issue_number,
        "title": title,
        "body": body,
        "comments": comments,
        "participants": participants,
        "reactions": reactions,
        "created_at": created_at,
        "labels": labels or [],
    }


class TestSummarizeCluster:
    def test_computes_frequency_and_repos(self):
        candidates = _candidates(
            _issue(issue_number=1),
            _issue(issue_number=2),
        )
        cluster = summarize_cluster(candidates, cluster_id=0, title="Timeout")
        assert cluster.frequency == 2
        assert cluster.affected_repos == ["org/a"]
        assert cluster.independent_repo_count == 1

    def test_cross_repo_count_dedupes(self):
        candidates = _candidates(
            _issue(repo="org/a", issue_number=1),
            _issue(repo="org/b", issue_number=1),
        )
        cluster = summarize_cluster(candidates, cluster_id=0, title="Timeout")
        assert cluster.frequency == 2
        assert cluster.independent_repo_count == 2

    def test_time_span(self):
        candidates = _candidates(
            _issue(issue_number=1, created_at="2026-01-01T00:00:00Z"),
            _issue(issue_number=2, created_at="2026-01-11T00:00:00Z"),
        )
        cluster = summarize_cluster(candidates, cluster_id=0, title="Timeout")
        assert cluster.time_span_days == 10

    def test_severity_positive_with_engagement(self):
        candidates = _candidates(_issue(comments=5, participants=3, reactions=2))
        cluster = summarize_cluster(candidates, cluster_id=0, title="Timeout")
        assert cluster.severity > 0

    def test_top_issues_capped_at_three(self):
        candidates = _candidates(*[_issue(issue_number=i, reactions=i) for i in range(1, 6)])
        cluster = summarize_cluster(candidates, cluster_id=0, title="Timeout")
        assert len(cluster.top_issues) == 3


class TestTitleHint:
    def test_prefers_error_code(self):
        candidates = _candidates(_issue(title="Error E1001 timeout"))
        group = CandidateGroup(
            group_id=0,
            issues=candidates,
            shared_features={"error_codes": ["E1001"], "components": [], "labels": []},
            mean_similarity=1.0,
        )
        assert title_hint(group) == "E1001 issues"

    def test_falls_back_to_component(self):
        candidates = _candidates(_issue(title="some title"))
        group = CandidateGroup(
            group_id=0,
            issues=candidates,
            shared_features={"error_codes": [], "components": ["runtime"], "labels": []},
            mean_similarity=1.0,
        )
        assert title_hint(group) == "runtime issues"

    def test_falls_back_to_title(self):
        candidates = _candidates(_issue(title="Agent hangs"))
        group = CandidateGroup(
            group_id=0,
            issues=candidates,
            shared_features={},
            mean_similarity=1.0,
        )
        assert title_hint(group) == "Agent hangs"
