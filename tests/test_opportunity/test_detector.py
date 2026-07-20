"""Tests for Opportunity Detector and Evaluator."""

from unittest.mock import MagicMock

from models.insight import Insight
from models.opportunity import Opportunity
from opportunity.detector import detect, build_detection_prompt, build_fallback_opportunities
from opportunity.evaluator import evaluate


LLM_RESPONSE = {"opportunities": [{
    "id": "op_001", "title": "Agent Testing Framework",
    "pain_point": "No good way to test LLM agent behavior",
    "demand_score": 4.5, "competition_score": 2.0,
    "recommended_action": "Build pytest plugin",
    "source_insights": ["in_001"],
}]}


class TestDetect:
    def test_detect_returns_opportunities(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLM_RESPONSE
        insights = [Insight(
            id="in_001", tags=["LLM", "Agent"], summary="LLM focus",
            strength=35.5, trend="rising", signal_count=12,
            evidence=["alice/agent-kit"],
        )]
        ops = detect(insights, mock_llm)
        assert len(ops) == 1
        assert ops[0].title == "Agent Testing Framework"

    def test_detect_llm_error_falls_back(self):
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = Exception("API down")
        insights = [Insight(
            id="in_001", tags=["LLM"], summary="LLM focus",
            strength=20.0, trend="rising", signal_count=8, evidence=[],
        )]
        ops = detect(insights, mock_llm)
        assert len(ops) >= 1
        assert ops[0].recommended_action == "进一步探索该方向"

    def test_fallback_creates_minimal_ops(self):
        insights = [Insight(
            id="in_001", tags=["Python"], summary="Python focus",
            strength=15.0, trend="rising", signal_count=5, evidence=[],
        )]
        ops = build_fallback_opportunities(insights)
        assert len(ops) == 1
        assert ops[0].demand_score == 3.0


class TestEvaluate:
    def test_computes_gap_scores(self):
        ops = [
            Opportunity(id="op_001", title="A", pain_point="x",
                        demand_score=4.0, competition_score=2.0, gap_score=0.0,
                        recommended_action="Build", source_insights=["in_001"]),
            Opportunity(id="op_002", title="B", pain_point="y",
                        demand_score=3.0, competition_score=4.0, gap_score=0.0,
                        recommended_action="Wait", source_insights=["in_002"]),
        ]
        scored = evaluate(ops)
        assert scored[0].gap_score == 2.0
        assert scored[0].id == "op_001"  # higher gap first

    def test_empty_list(self):
        assert evaluate([]) == []
