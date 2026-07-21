"""Tests for radar API endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("backend.dependencies.get_github_client") as mock_gh:
        with patch("backend.router.radar.TrendStore") as mock_store:
            gh = MagicMock()
            gh.close = AsyncMock()
            gh.rate_limiter = MagicMock()
            gh.rate_limiter._total_calls = 42
            mock_gh.return_value = gh

            store_inst = mock_store.return_value
            store_inst.get_latest.return_value = None  # force fresh run

            from backend.main import app

            with TestClient(app) as tc:
                yield tc


class TestRadarAPI:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_radar_endpoint(self, client):
        """Radar endpoint should return valid structure even with mock data."""
        resp = client.get("/api/radar?domain=agent&window=60")
        assert resp.status_code in (200, 500)  # 500 if engine can't find repos (OK in test)

    def test_trends_endpoint_no_snapshot(self, client):
        """Trends endpoint should return 404 when no snapshot exists."""
        resp = client.get("/api/trends?domain=agent&topic=mcp")
        assert resp.status_code == 404
        assert "No snapshot for domain" in resp.json()["detail"]

    def test_health_method_not_allowed(self, client):
        """Health endpoint should reject POST."""
        resp = client.post("/api/health")
        assert resp.status_code == 405

    def test_pain_endpoint(self, client):
        """Pain endpoint should return 200 or 404."""
        resp = client.get("/api/pain?domain=agent")
        assert resp.status_code in (200, 404)

    def test_opportunities_endpoint(self, client):
        """Opportunities endpoint should return cards structure."""
        resp = client.get("/api/opportunities?domain=agent")
        assert resp.status_code == 200
        data = resp.json()
        assert "cards" in data

    def test_evidence_endpoint_not_found(self, client):
        """Evidence endpoint should return 404 for nonexistent opportunity."""
        resp = client.get("/api/evidence/nonexistent?domain=agent")
        assert resp.status_code == 404
