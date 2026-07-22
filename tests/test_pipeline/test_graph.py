"""Tests for LangGraph pipeline."""
import pytest
from pipeline.graph import build_pipeline


class TestPipeline:

    def test_builds_full_auto_pipeline(self):
        graph = build_pipeline("full_auto")
        assert graph is not None

    def test_builds_supervised_pipeline(self):
        graph = build_pipeline("supervised")
        assert graph is not None

    @pytest.mark.asyncio
    async def test_pipeline_empty_run(self):
        graph = build_pipeline("full_auto")
        config = {"configurable": {"thread_id": "test-1"}}
        result = await graph.ainvoke({
            "domain": "agent",
            "window_days": 30,
            "mode": "full_auto",
        }, config)
        assert result is not None
        assert "domain" in result
