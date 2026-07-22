"""Tests for intelligence/opportunity/critic.py."""
import pytest

from intelligence.opportunity.critic import review_opportunities


class MockLLM:
    """Mock LLM that returns a canned review dict."""

    def complete(self, prompt, response_format=None):
        return {
            "feasibility": 6,
            "market_size": 5,
            "timing": 7,
            "blind_spots": ["competitor risk"],
            "counter_view": "Strong incumbents may block entry.",
        }


class FailingMockLLM:
    """Mock LLM that raises on every call."""

    def complete(self, prompt, response_format=None):
        msg = "Simulated LLM failure"
        raise RuntimeError(msg)


class TestReviewOpportunities:
    def test_returns_correct_structure(self):
        """review_opportunities returns a list of review dicts."""
        import asyncio

        opportunities = [
            {"title": "AI Dev Tool", "score": 7},
            {"title": "Cloud IDE", "score": 6},
        ]
        llm = MockLLM()
        reviews = asyncio.run(review_opportunities(opportunities, llm))

        assert len(reviews) == 2
        for r in reviews:
            assert "feasibility" in r
            assert "market_size" in r
            assert "timing" in r
            assert "blind_spots" in r
            assert "counter_view" in r
            assert isinstance(r["feasibility"], int)
            assert isinstance(r["blind_spots"], list)

    def test_fallback_on_llm_error(self):
        """review_opportunities should return fallback on LLM error."""
        opportunities = [{"title": "Fail Opp", "score": 5}]
        llm = FailingMockLLM()

        import asyncio

        reviews = asyncio.run(review_opportunities(opportunities, llm))

        assert len(reviews) == 1
        assert reviews[0]["feasibility"] == 0
        assert reviews[0]["market_size"] == 0
        assert reviews[0]["timing"] == 0
        assert reviews[0]["blind_spots"] == []
        assert reviews[0]["counter_view"] == "LLM error"

    def test_empty_input(self):
        """review_opportunities returns empty list for empty input."""
        llm = MockLLM()

        import asyncio

        reviews = asyncio.run(review_opportunities([], llm))
        assert reviews == []
