"""Tests for Insight model."""

from datetime import datetime

from models.insight import Insight


class TestInsight:
    def test_insight_creation(self):
        i = Insight(
            id="insight_001",
            tags=["MCP", "Agent"],
            summary="Heavy investment in MCP-based agent tooling",
            strength=35.5,
            trend="rising",
            signal_count=12,
            evidence=["alice/mcp-server", "alice/agent-kit"],
        )
        assert i.id == "insight_001"
        assert "MCP" in i.tags
        assert i.trend == "rising"
        assert len(i.evidence) == 2
        assert isinstance(i.created_at, datetime)

    def test_insight_defaults(self):
        i = Insight(
            id="insight_002",
            tags=["Rust"],
            summary="Exploring Rust for systems programming",
            strength=8.0,
            trend="stable",
            signal_count=3,
        )
        assert i.evidence == []
        assert i.created_at is not None
