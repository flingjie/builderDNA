"""Tests for intelligence/opportunity/models.py."""
import pytest
from pydantic import ValidationError

from intelligence.opportunity.models import (
    CriticReview,
    OpportunityCard,
    OpportunityEvidence,
    OpportunitySnapshot,
)


class TestCriticReview:
    def test_default_construction(self):
        """CriticReview should create with all-zero defaults."""
        r = CriticReview()
        assert r.feasibility == 0
        assert r.market_size == 0
        assert r.timing == 0
        assert r.blind_spots == []
        assert r.counter_view == ""

    def test_full_construction(self):
        """CriticReview should accept all fields."""
        r = CriticReview(
            feasibility=7,
            market_size=5,
            timing=8,
            blind_spots=["team too small", "market crowded"],
            counter_view="Will struggle against incumbents.",
        )
        assert r.feasibility == 7
        assert r.market_size == 5
        assert r.timing == 8
        assert r.blind_spots == ["team too small", "market crowded"]
        assert r.counter_view == "Will struggle against incumbents."

    def test_feasibility_bounds(self):
        """feasibility accepts any int; business logic enforces 0-10."""
        r = CriticReview(feasibility=15)
        assert r.feasibility == 15  # Pydantic does not constrain int range


class TestOpportunityEvidence:
    def test_default_construction(self):
        ev = OpportunityEvidence()
        assert ev.trends == []
        assert ev.pain_clusters == []
        assert ev.key_issues == []
        assert ev.key_repos == []

    def test_full_construction(self):
        ev = OpportunityEvidence(
            trends=["AI Agents"],
            pain_clusters=["slow CI"],
            key_issues=["#42"],
            key_repos=["owner/repo"],
        )
        assert ev.trends == ["AI Agents"]
        assert ev.pain_clusters == ["slow CI"]
        assert ev.key_issues == ["#42"]
        assert ev.key_repos == ["owner/repo"]


class TestOpportunityCard:
    def test_minimal(self):
        """OpportunityCard requires only title."""
        card = OpportunityCard(title="Test Opp")
        assert card.title == "Test Opp"
        assert card.score == 0.0
        assert card.risk == "medium"
        assert card.validation is None
        assert card.critic_review is None
        assert isinstance(card.evidence, OpportunityEvidence)

    def test_with_critic_review(self):
        """OpportunityCard should accept a CriticReview."""
        review = CriticReview(feasibility=6, market_size=7, timing=5)
        card = OpportunityCard(
            title="Test",
            score=7.0,
            critic_review=review,
        )
        assert card.critic_review is not None
        assert card.critic_review.feasibility == 6

    def test_risk_literal(self):
        """risk must be one of low/medium/high."""
        OpportunityCard(title="X", risk="low")
        OpportunityCard(title="X", risk="medium")
        OpportunityCard(title="X", risk="high")
        with pytest.raises(ValidationError):
            OpportunityCard(title="X", risk="extreme")


class TestOpportunitySnapshot:
    def test_default_construction(self):
        snap = OpportunitySnapshot(domain="test-domain")
        assert snap.domain == "test-domain"
        assert snap.cards == []

    def test_with_cards(self):
        cards = [OpportunityCard(title="A"), OpportunityCard(title="B")]
        snap = OpportunitySnapshot(domain="d", cards=cards)
        assert len(snap.cards) == 2
