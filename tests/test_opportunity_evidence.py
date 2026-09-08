"""Tests for P6: evidence-backed opportunity/trend/pain judgment."""

from cli.commands.opportunity import _generate_cards
from models.payload import OpportunityCard, TopicTrend, PainCluster


class TestOpportunityEvidence:
    def _trend(self, **overrides):
        base = {
            "topic": "mcp",
            "stage": "accelerating",
            "growth_velocity": 50,
            "evidence_count": 1,
            "top_repos": [{"full_name": "a/b", "stars": 5000, "forks": 100}],
        }
        base.update(overrides)
        return base

    def test_every_card_names_why_now_and_invalidation(self):
        cards = _generate_cards([self._trend()], [])
        for c in cards:
            assert c.why_now, "opportunity must state why now"
            assert c.invalidation_condition, "opportunity must state what disproves it"
            assert c.minimal_validation_action, "opportunity must propose a bounded validation action"
            assert c.demand_evidence
            assert c.competition_evidence

    def test_single_source_is_flagged_and_downgraded(self):
        cards = _generate_cards([self._trend(evidence_count=1, top_repos=[{"full_name": "a/b", "stars": 5000, "forks": 100}])], [])
        card = cards[0]
        assert any("单源" in ce or "样本" in ce for ce in card.counter_evidence)
        assert card.confidence <= 0.4

    def test_multi_source_not_downgraded(self):
        trend = self._trend(
            evidence_count=5,
            top_repos=[
                {"full_name": "a/b", "stars": 5000, "forks": 100},
                {"full_name": "c/d", "stars": 3000, "forks": 80},
                {"full_name": "e/f", "stars": 2000, "forks": 50},
            ],
        )
        cards = _generate_cards([trend], [])
        # With 3 repos, no single-source downgrade is applied (confidence is
        # only whatever compute_confidence yields, not capped to 0.4).
        assert cards[0].counter_evidence == [] or not any("单源" in ce for ce in cards[0].counter_evidence)


class TestP6SchemaFields:
    def test_topic_trend_has_coverage_fields(self):
        t = TopicTrend(topic="x", stage="emerging", confidence=0.5, growth_velocity=1.0, evidence_count=3)
        assert t.sample_coverage == 0.0
        assert t.distinct_repos == 0

    def test_pain_cluster_has_evidence_fields(self):
        p = PainCluster(cluster_id=1, title="x", severity=0.5, frequency=3)
        assert p.independent_repo_count == 0
        assert p.time_span_days == 0
        assert p.existing_workarounds == []

    def test_opportunity_card_has_evidence_fields(self):
        o = OpportunityCard(title="x", demand_score=1.0, competition_score=1.0, gap_score=1.0)
        assert o.demand_evidence == []
        assert o.competition_evidence == []
        assert o.counter_evidence == []
        assert o.minimal_validation_action == ""
        assert o.why_now == ""
        assert o.invalidation_condition == ""
