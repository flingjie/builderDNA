"""Tests for L2 Insight Classifier."""

from unittest.mock import MagicMock

from models.signal import SignalCluster
from insight.classifier import classify, build_classification_prompt, build_fallback_insights


LLM_RESPONSE = {"insights": [{
    "id": "in_001", "tags": ["LLM", "Agent", "Python"],
    "summary": "Deep investment in LLM agent frameworks",
    "strength": 35.5, "trend": "rising", "signal_count": 12,
    "evidence": ["alice/agent-kit"],
}]}


class TestClassify:
    def test_classify_returns_insights(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLM_RESPONSE
        clusters = [SignalCluster(
            signals=["s1", "s2"], topics=["llm", "agent"],
            languages=["Python"], total_weight=35.5,
            time_span_days=60, growth_rate=0.6,
        )]
        insights = classify(clusters, mock_llm, "alice")
        assert len(insights) == 1
        assert insights[0].trend == "rising"

    def test_classify_llm_error_falls_back(self):
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = Exception("API down")
        clusters = [SignalCluster(
            signals=["s1"], topics=["llm"], languages=["Python"],
            total_weight=5.0, time_span_days=10, growth_rate=0.5,
        )]
        insights = classify(clusters, mock_llm, "alice")
        assert len(insights) == 1
        assert "alice" in insights[0].summary

    def test_builds_fallback(self):
        clusters = [
            SignalCluster(signals=["s1"], topics=["rust"], languages=["Rust"],
                          total_weight=10.0, time_span_days=20, growth_rate=0.3),
            SignalCluster(signals=["s2"], topics=["web"], languages=["JS"],
                          total_weight=3.0, time_span_days=5, growth_rate=0.0),
        ]
        insights = build_fallback_insights(clusters, "alice")
        assert len(insights) == 2
        assert insights[0].id.startswith("in_fallback")

    def test_prompt_contains_actor(self):
        clusters = [SignalCluster(
            signals=["s1"], topics=["llm"], languages=["Python"],
            total_weight=5.0, time_span_days=30, growth_rate=0.5,
        )]
        prompt = build_classification_prompt(clusters, "alice")
        assert "alice" in prompt
        assert "llm" in prompt
