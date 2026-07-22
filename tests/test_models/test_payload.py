"""Tests for payload models — the sandbox command output contracts."""

import pytest

from models.payload import (
    SandboxResult,
    RepoSignal,
    IssueSignal,
    CollectPayload,
    RepoSummary,
    TopicTrend,
    TrendPayload,
    IssueSummary,
    PainCluster,
    PainPayload,
    OpportunityCard,
    OpportunityPayload,
)


class TestSandboxResult:
    def test_creation_minimal(self):
        r = SandboxResult(command="collect", domain="test", payload={})
        assert r.command == "collect"
        assert r.domain == "test"
        assert r.payload == {}
        assert r.stats == {}
        assert isinstance(r.computed_at, str)

    def test_creation_full(self):
        r = SandboxResult(
            command="trend",
            domain="ai",
            payload={"trends": []},
            stats={"elapsed_ms": 123},
        )
        assert r.command == "trend"
        assert r.stats["elapsed_ms"] == 123

    def test_computed_at_defaults_to_iso(self):
        r = SandboxResult(command="x", domain="y", payload={})
        assert "T" in r.computed_at
        assert r.computed_at.endswith("Z") or "+" in r.computed_at


class TestRepoSignal:
    def test_creation_minimal(self):
        rs = RepoSignal(full_name="owner/repo", owner="owner")
        assert rs.full_name == "owner/repo"
        assert rs.stars == 0
        assert rs.topics == []
        assert rs.description == ""

    def test_creation_full(self):
        rs = RepoSignal(
            full_name="owner/repo",
            owner="owner",
            stars=100,
            forks=20,
            contributors=5,
            velocity=3.5,
            topics=["python", "cli"],
            description="A CLI tool",
            language="Python",
            created_at="2024-01-01",
        )
        assert rs.stars == 100
        assert rs.velocity == 3.5
        assert rs.language == "Python"


class TestIssueSignal:
    def test_creation_minimal(self):
        iss = IssueSignal(repo="owner/repo", issue_number=1, title="Bug")
        assert iss.body == ""
        assert iss.comments == 0
        assert iss.labels == []

    def test_creation_full(self):
        iss = IssueSignal(
            repo="owner/repo",
            issue_number=42,
            title="Crash on startup",
            body="Details...",
            comments=5,
            participants=3,
            reactions=10,
            labels=["bug", "critical"],
            url="https://github.com/owner/repo/issues/42",
        )
        assert iss.issue_number == 42
        assert iss.reactions == 10
        assert "critical" in iss.labels


class TestCollectPayload:
    def test_defaults_to_empty_lists(self):
        cp = CollectPayload()
        assert cp.repos == []
        assert cp.issues == []

    def test_with_data(self):
        rs = RepoSignal(full_name="a/b", owner="a")
        iss = IssueSignal(repo="a/b", issue_number=1, title="T")
        cp = CollectPayload(repos=[rs], issues=[iss])
        assert len(cp.repos) == 1
        assert len(cp.issues) == 1


class TestRepoSummary:
    def test_creation(self):
        rs = RepoSummary(
            full_name="a/b", stars=50, forks=10, velocity=2.0
        )
        assert rs.stars_delta == 0
        assert rs.description == ""


class TestTopicTrend:
    def test_creation_minimal(self):
        tt = TopicTrend(
            topic="LLM Agents",
            stage="accelerating",
            confidence=0.85,
            growth_velocity=0.5,
            evidence_count=100,
        )
        assert tt.acceleration == 0.0
        assert tt.top_repos == []

    def test_valid_stages(self):
        for stage in ("accelerating", "emerging", "mainstream", "declining"):
            tt = TopicTrend(
                topic="X",
                stage=stage,  # type: ignore[arg-type]
                confidence=0.5,
                growth_velocity=0.1,
                evidence_count=10,
            )
            assert tt.stage == stage

    def test_invalid_stage(self):
        with pytest.raises(ValueError):
            TopicTrend(
                topic="X",
                stage="invalid_stage",  # type: ignore[arg-type]
                confidence=0.5,
                growth_velocity=0.1,
                evidence_count=10,
            )


class TestTrendPayload:
    def test_creation(self):
        tp = TrendPayload(domain="ai", window_days=90)
        assert tp.trends == []

    def test_with_trends(self):
        tt = TopicTrend(
            topic="Agents",
            stage="emerging",
            confidence=0.7,
            growth_velocity=0.3,
            evidence_count=50,
        )
        tp = TrendPayload(trends=[tt], domain="ai", window_days=90)
        assert len(tp.trends) == 1


class TestIssueSummary:
    def test_creation(self):
        iss = IssueSummary(
            repo="a/b", issue_number=5, title="Bug", pain_score=0.9
        )
        assert iss.pain_score == 0.9


class TestPainCluster:
    def test_creation_minimal(self):
        pc = PainCluster(
            cluster_id=1, title="Slow builds", severity=0.8, frequency=10
        )
        assert pc.affected_repos == []
        assert pc.top_issues == []

    def test_with_issues(self):
        iss = IssueSummary(repo="a/b", issue_number=1, title="X", pain_score=0.5)
        pc = PainCluster(
            cluster_id=2,
            title="Test flakiness",
            severity=0.6,
            frequency=5,
            affected_repos=["a/b"],
            top_issues=[iss],
        )
        assert pc.cluster_id == 2
        assert len(pc.top_issues) == 1


class TestPainPayload:
    def test_defaults(self):
        pp = PainPayload()
        assert pp.clusters == []
        assert pp.issue_count == 0
        assert pp.repos_analyzed == []


class TestOpportunityCard:
    def test_creation_minimal(self):
        oc = OpportunityCard(
            title="Build an X", demand_score=0.8, competition_score=0.3, gap_score=2.5
        )
        assert oc.signals == []
        assert oc.recommended_action == ""

    def test_creation_full(self):
        oc = OpportunityCard(
            title="Build an X",
            demand_score=0.8,
            competition_score=0.3,
            gap_score=2.5,
            signals=["signal_1", "signal_2"],
            recommended_action="Build MVP",
        )
        assert len(oc.signals) == 2


class TestOpportunityPayload:
    def test_defaults(self):
        op = OpportunityPayload()
        assert op.opportunities == []

    def test_with_opportunities(self):
        oc = OpportunityCard(
            title="X", demand_score=0.9, competition_score=0.2, gap_score=4.5
        )
        op = OpportunityPayload(opportunities=[oc])
        assert len(op.opportunities) == 1
