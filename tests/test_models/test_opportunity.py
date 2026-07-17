"""Tests for Opportunity model."""

import pytest

from models.opportunity import Opportunity


class TestOpportunity:
    def test_opportunity_creation(self):
        o = Opportunity(
            id="op_001",
            title="Agent Testing Framework",
            pain_point="No good way to test LLM agent behavior",
            demand_score=4.5,
            competition_score=2.0,
            gap_score=2.25,
            recommended_action="Build MVP with pytest integration",
            source_insights=["insight_001", "insight_002"],
        )
        assert o.id == "op_001"
        assert o.gap_score == 2.25
        assert len(o.source_insights) == 2

    def test_score_bounds(self):
        with pytest.raises(ValueError):
            Opportunity(
                id="bad",
                title="Bad",
                pain_point="x",
                demand_score=6.0,  # out of range
                competition_score=1.0,
                gap_score=6.0,
                recommended_action="don't",
                source_insights=[],
            )
