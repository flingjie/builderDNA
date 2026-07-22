"""Tests for intelligence/opportunity/scorer.py."""
import pytest

from intelligence.opportunity.scorer import rank_opportunities, score_opportunity


class TestScoreOpportunity:
    def test_no_critic(self):
        """Without critic review, final score equals base score."""
        assert score_opportunity({"score": 7.0}) == 7.0

    def test_with_critic_review(self):
        """With critic review, final score is blended 60/40."""
        card = {"score": 8.0}
        review = {"feasibility": 6, "market_size": 4, "timing": 5}
        # base * 0.6 + avg(6,4,5) * 0.4 = 4.8 + 2.0 = 6.8
        assert score_opportunity(card, review) == 6.8

    def test_zero_score(self):
        """Zero base score with neutral critic."""
        card = {"score": 0.0}
        review = {"feasibility": 5, "market_size": 5, "timing": 5}
        # 0 * 0.6 + 5 * 0.4 = 2.0
        assert score_opportunity(card, review) == 2.0

    def test_critic_all_zero(self):
        """Critic all zeros should lower the score."""
        card = {"score": 8.0}
        review = {"feasibility": 0, "market_size": 0, "timing": 0}
        # 8 * 0.6 + 0 * 0.4 = 4.8
        assert score_opportunity(card, review) == 4.8

    def test_default_score_is_zero(self):
        """Missing score key defaults to 0."""
        assert score_opportunity({}) == 0.0


class TestRankOpportunities:
    def test_ranks_descending(self):
        """rank_opportunities sorts by final_score descending."""
        cards = [
            {"title": "A", "score": 5.0},
            {"title": "B", "score": 8.0},
            {"title": "C", "score": 6.0},
        ]
        reviews = [
            {"feasibility": 5, "market_size": 5, "timing": 5},
            {"feasibility": 5, "market_size": 5, "timing": 5},
            {"feasibility": 5, "market_size": 5, "timing": 5},
        ]
        ranked = rank_opportunities(cards, reviews)
        assert ranked[0]["title"] == "B"
        assert ranked[1]["title"] == "C"
        assert ranked[2]["title"] == "A"

    def test_final_score_added(self):
        """Each card gets a final_score key."""
        cards = [{"title": "X", "score": 7.0}]
        reviews = [{"feasibility": 8, "market_size": 6, "timing": 7}]
        ranked = rank_opportunities(cards, reviews)
        assert "final_score" in ranked[0]

    def test_mismatched_reviews(self):
        """If reviews list is shorter, remaining cards get no critic adjustment."""
        cards = [
            {"title": "A", "score": 5.0},
            {"title": "B", "score": 7.0},
        ]
        reviews = [{"feasibility": 5, "market_size": 5, "timing": 5}]
        ranked = rank_opportunities(cards, reviews)
        # A has critic -> score influenced, B has no critic -> base score
        assert "final_score" in ranked[0]
        assert "final_score" in ranked[1]

    def test_empty_input(self):
        """Empty lists return empty list."""
        assert rank_opportunities([], []) == []
