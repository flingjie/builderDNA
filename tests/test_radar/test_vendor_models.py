"""Tests for vendor models."""
from backend.models.vendor import VendorProfile, VendorSnapshot, VendorDiff, VendorDirection, VendorSignal


class TestVendorDirection:
    def test_creation(self):
        d = VendorDirection(topic="agent-framework", intensity=0.8, trend="↑")
        assert d.topic == "agent-framework"
        assert d.intensity == 0.8


class TestVendorProfile:
    def test_creation(self):
        profile = VendorProfile(
            name="deepseek-ai",
            display_name="DeepSeek",
            accounts=["deepseek-ai"],
            tags=["🇨🇳 国产", "大模型"],
            comparison_group="domestic",
        )
        assert profile.name == "deepseek-ai"
        assert profile.active_directions == []
        assert profile.recent_signals == []

    def test_with_directions(self):
        profile = VendorProfile(
            name="anthropics",
            display_name="Anthropic",
            accounts=["anthropics"],
            tags=["🌍 海外", "Agent"],
            comparison_group="overseas",
            active_directions=[
                VendorDirection(topic="mcp", intensity=0.9, trend="↑"),
                VendorDirection(topic="agent-framework", intensity=0.7, trend="→"),
            ],
            recent_signals=[
                VendorSignal(type="new_repo", repo="anthropics/mcp-python", timestamp="2026-07-01T00:00:00Z")
            ],
        )
        assert len(profile.active_directions) == 2
        assert len(profile.recent_signals) == 1


class TestVendorSnapshot:
    def test_auto_id(self):
        s = VendorSnapshot(domain="agent", window_days=60)
        assert len(s.id) == 8
        assert s.profiles == []


class TestVendorDiff:
    def test_creation(self):
        diff = VendorDiff(
            dimension="agent-framework",
            domestic_summary="国产偏应用集成",
            overseas_summary="海外偏协议标准",
            common_patterns="都在卷工具调用",
            domestic_vendors=["MoonshotAI"],
            overseas_vendors=["anthropics"],
        )
        assert diff.domestic_summary == "国产偏应用集成"
