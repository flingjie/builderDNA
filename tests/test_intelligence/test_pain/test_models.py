"""Tests for intelligence/pain/models.py."""

from intelligence.pain.models import PainIssue, PainCluster, PainSnapshot


class TestPainIssue:
    def test_minimal_creation(self):
        issue = PainIssue(repo="owner/repo", issue_number=42, title="Bug: crash on login")
        assert issue.repo == "owner/repo"
        assert issue.issue_number == 42
        assert issue.title == "Bug: crash on login"
        assert issue.body == ""
        assert issue.comments == 0
        assert issue.participants == 0
        assert issue.pain_score == 0.0
        assert issue.labels == []
        assert issue.url == ""
        assert issue.cluster_id == -1

    def test_full_creation(self):
        issue = PainIssue(
            repo="org/repo",
            issue_number=7,
            title="Slow query",
            body="Takes 30s to load",
            comments=5,
            participants=3,
            pain_score=8.4,
            labels=["performance", "bug"],
            url="https://github.com/org/repo/issues/7",
            cluster_id=2,
        )
        assert issue.cluster_id == 2

    def test_cluster_id_defaults_to_minus_one(self):
        issue = PainIssue(repo="a/b", issue_number=1, title="x")
        assert issue.cluster_id == -1


class TestPainCluster:
    def test_minimal_creation(self):
        cluster = PainCluster(title="Agent State Debugging", severity=7.5, frequency=3)
        assert cluster.title == "Agent State Debugging"
        assert cluster.severity == 7.5
        assert cluster.frequency == 3
        assert cluster.description == ""
        assert cluster.evidence == []
        assert cluster.affected_repos == []
        assert len(cluster.id) == 8

    def test_with_evidence(self):
        issue = PainIssue(repo="a/b", issue_number=1, title="x")
        cluster = PainCluster(
            title="Logging Issues",
            severity=3.0,
            frequency=1,
            description="Root cause: excessive logging",
            evidence=[issue],
            affected_repos=["a/b"],
        )
        assert len(cluster.evidence) == 1
        assert cluster.evidence[0].title == "x"


class TestPainSnapshot:
    def test_minimal_creation(self):
        snap = PainSnapshot(domain="frontend")
        assert snap.domain == "frontend"
        assert snap.clusters == []
        assert snap.issue_count == 0
        assert snap.repos_analyzed == []
        assert len(snap.id) == 8
        assert snap.created_at is not None

    def test_with_clusters(self):
        cluster = PainCluster(title="Build Failures", severity=9.0, frequency=5)
        snap = PainSnapshot(
            domain="ci",
            clusters=[cluster],
            issue_count=5,
            repos_analyzed=["org/repo"],
        )
        assert len(snap.clusters) == 1
        assert snap.clusters[0].title == "Build Failures"
        assert snap.issue_count == 5
