"""Tests for pain models."""
from backend.models.pain import PainIssue, PainCluster, PainSnapshot


class TestPainIssue:
    def test_pain_issue_defaults(self):
        p = PainIssue(repo="a/b", issue_number=1, title="bug: crash on startup")
        assert p.body == ""
        assert p.comments == 0
        assert p.participants == 0
        assert p.pain_score == 0.0
        assert p.labels == []
        assert p.url == ""


class TestPainCluster:
    def test_pain_cluster_auto_id(self):
        c = PainCluster(title="Agent State Debugging", severity=8.5, frequency=5)
        assert len(c.id) == 8
        assert c.title == "Agent State Debugging"
        assert c.severity == 8.5
        assert c.frequency == 5
        assert c.description == ""
        assert c.evidence == []
        assert c.affected_repos == []


class TestPainSnapshot:
    def test_pain_snapshot_auto_id(self):
        s = PainSnapshot(domain="agent")
        assert len(s.id) == 8
        assert s.domain == "agent"
        assert s.clusters == []
        assert s.issue_count == 0
        assert s.repos_analyzed == []
