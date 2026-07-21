"""Tests for vendor engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.models.vendor import VendorProfile, VendorSnapshot, VendorDiff, VendorDirection
from backend.engine.vendor import _track_single_vendor, _build_comparison_prompt, run_vendor_tracking


class TestTrackSingleVendor:
    @pytest.mark.asyncio
    async def test_returns_profile(self):
        mock_client = AsyncMock()
        mock_client.get_repos = AsyncMock(return_value=[
            {"full_name": "org/repo1", "stargazers_count": 100, "topics": ["ai", "agent"], "description": "test", "updated_at": "2026-06-01T00:00:00Z"},
        ])
        profile = await _track_single_vendor(
            client=mock_client,
            org_name="test-org",
            display_name="Test Org",
            tags=["🏷️ test"],
            comparison_group="domestic",
        )
        assert profile is not None
        assert profile.name == "test-org"
        assert profile.comparison_group == "domestic"

    @pytest.mark.asyncio
    async def test_handles_api_error(self):
        mock_client = AsyncMock()
        mock_client.get_repos = AsyncMock(side_effect=Exception("API Error"))
        profile = await _track_single_vendor(
            client=mock_client,
            org_name="bad-org",
            display_name="Bad Org",
            tags=[],
            comparison_group="domestic",
        )
        assert profile is not None
        assert profile.total_public_repos == 0


class TestBuildComparisonPrompt:
    def test_formats_profiles(self):
        profiles = [
            VendorProfile(name="org-a", display_name="Org A", accounts=["org-a"], tags=["🇨🇳"], comparison_group="domestic",
                          active_directions=[VendorDirection(topic="ai", intensity=0.8, trend="↑")]),
            VendorProfile(name="org-b", display_name="Org B", accounts=["org-b"], tags=["🌍"], comparison_group="overseas",
                          active_directions=[VendorDirection(topic="ai", intensity=0.6, trend="→")]),
        ]
        prompt = _build_comparison_prompt(profiles)
        assert "Org A" in prompt
        assert "Org B" in prompt
        assert "ai" in prompt


class TestRunVendorTracking:
    @pytest.mark.asyncio
    async def test_returns_snapshot(self, tmp_path):
        config = MagicMock()
        config.vendors.domestic = ["org-a"]
        config.vendors.overseas = ["org-b"]

        mock_client = AsyncMock()
        mock_client.get_repos = AsyncMock(return_value=[
            {"full_name": "org/repo1", "stargazers_count": 100, "topics": ["ai"], "description": "test", "updated_at": "2026-06-01T00:00:00Z"},
        ])

        mock_llm = MagicMock()
        mock_llm.complete = MagicMock(return_value={"diffs": []})

        from backend.store.vendor_store import VendorStore
        store = VendorStore(str(tmp_path / "vendor.db"))
        snapshot = await run_vendor_tracking(mock_client, config, mock_llm, store)
        assert snapshot is not None
        assert len(snapshot.profiles) == 2
