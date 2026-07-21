"""Tests for opportunity models."""
from backend.models.opportunity import OpportunityCard, OpportunitySnapshot, OpportunityEvidence


class TestOpportunityEvidence:
    def test_defaults(self):
        e = OpportunityEvidence()
        assert e.trends == []
        assert e.pain_clusters == []
        assert e.key_issues == []
        assert e.key_repos == []


class TestOpportunityCard:
    def test_defaults(self):
        c = OpportunityCard(title="Test Opportunity")
        assert len(c.id) == 8
        assert c.why_now == ""
        assert c.problem == ""
        assert c.evidence.trends == []
        assert c.existing_solutions == []
        assert c.gap == ""
        assert c.mvp == ""
        assert c.score == 0.0
        assert c.risk == "medium"

    def test_evidence_can_be_populated(self):
        e = OpportunityEvidence(
            trends=["trend1", "trend2"],
            pain_clusters=["Cluster A"],
            key_issues=["Issue 1"],
            key_repos=["org/repo"],
        )
        c = OpportunityCard(title="Test", evidence=e)
        assert len(c.evidence.trends) == 2
        assert "Cluster A" in c.evidence.pain_clusters

    def test_risk_default_medium(self):
        c = OpportunityCard(title="Risk Test")
        assert c.risk == "medium"

    def test_score_default_zero(self):
        c = OpportunityCard(title="Score Test")
        assert c.score == 0.0


class TestOpportunitySnapshot:
    def test_auto_id(self):
        s = OpportunitySnapshot(domain="agent")
        assert len(s.id) == 8
        assert s.domain == "agent"
        assert s.cards == []
