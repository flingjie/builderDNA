"""Tests for the observability snapshot module (prediction snapshots, validation)."""
import json
import os
import tempfile
from pathlib import Path

from observability.snapshot import (
    save_trend_snapshot,
    save_pain_snapshot,
    save_opportunity_snapshot,
    compare_snapshots,
    PREDICTIONS_DIR,
    _compare_trend,
    _match_trend_by_topic,
    _compare_trend_snapshots,
    _compare_opportunity_snapshots,
    _compare_pain_snapshots,
    _list_snapshots,
)


class TestCompareTrend:
    """Tests for trend prediction validation logic."""

    def test_validated_accelerating_to_accelerating(self):
        old = {"topic": "agent-memory", "stage": "accelerating",
               "growth_velocity": 3.0}
        new = {"topic": "agent-memory", "stage": "accelerating",
               "growth_velocity": 4.0}
        result = _compare_trend(old, new)
        assert result["status"] == "validated"

    def test_validated_emerging_to_accelerating(self):
        old = {"topic": "mcp-tools", "stage": "emerging",
               "growth_velocity": 1.5}
        new = {"topic": "mcp-tools", "stage": "accelerating",
               "growth_velocity": 2.0}
        result = _compare_trend(old, new)
        assert result["status"] == "validated"

    def test_validated_declining_continues(self):
        old = {"topic": "legacy-lib", "stage": "declining",
               "growth_velocity": -2.0}
        new = {"topic": "legacy-lib", "stage": "declining",
               "growth_velocity": -2.5}
        result = _compare_trend(old, new)
        assert result["status"] == "validated"

    def test_miss_accelerating_to_declining(self):
        old = {"topic": "hot-topic", "stage": "accelerating",
               "growth_velocity": 3.0}
        new = {"topic": "hot-topic", "stage": "declining",
               "growth_velocity": -1.0}
        result = _compare_trend(old, new)
        assert result["status"] == "miss"

    def test_miss_jump_two_stages(self):
        old = {"topic": "fast-grower", "stage": "emerging",
               "growth_velocity": 1.0}
        new = {"topic": "fast-grower", "stage": "accelerating",
               "growth_velocity": 8.0}
        # emerging(2) → accelerating(3) is only +1, not +2, so not a "miss" by jump
        # Actually: stage_order = {"accelerating": 3, "emerging": 2, "mainstream": 1, "declining": 0}
        # emerging→accelerating = 2→3 = +1, which doesn't trigger stage_delta >= 2
        # Let me use a case that does: emerging→mainstream is -1, not +2
        # OK what about declining→accelerating = 0→3 = +3 ✓
        old2 = {"topic": "reviving", "stage": "declining", "growth_velocity": -2.0}
        new2 = {"topic": "reviving", "stage": "accelerating", "growth_velocity": 5.0}
        result = _compare_trend(old2, new2)
        assert result["status"] == "miss"
        assert "jumped" in result["detail"].lower() or "too fast" in result["detail"].lower()

    def test_neutral_mainstream_stable(self):
        old = {"topic": "stable-topic", "stage": "mainstream",
               "growth_velocity": 0.5}
        new = {"topic": "stable-topic", "stage": "mainstream",
               "growth_velocity": 0.6}
        result = _compare_trend(old, new)
        assert result["status"] == "neutral"

    def test_velocity_change_pct_calculated(self):
        old = {"topic": "test", "stage": "accelerating",
               "growth_velocity": 2.0}
        new = {"topic": "test", "stage": "accelerating",
               "growth_velocity": 3.0}
        result = _compare_trend(old, new)
        assert result["velocity_change_pct"] == 50.0

    def test_zero_old_velocity(self):
        old = {"topic": "test", "stage": "emerging",
               "growth_velocity": 0}
        new = {"topic": "test", "stage": "emerging",
               "growth_velocity": 5.0}
        result = _compare_trend(old, new)
        assert result["velocity_change_pct"] == float("inf")


class TestMatchTrendByTopic:
    """Tests for fuzzy topic matching."""

    def test_exact_match(self):
        trends = [{"topic": "agent-memory"}, {"topic": "mcp"}]
        result = _match_trend_by_topic("agent-memory", trends)
        assert result is not None
        assert result["topic"] == "agent-memory"

    def test_case_insensitive(self):
        trends = [{"topic": "Agent-Memory"}]
        result = _match_trend_by_topic("agent-memory", trends)
        assert result is not None

    def test_no_match(self):
        trends = [{"topic": "mcp"}]
        result = _match_trend_by_topic("agent-memory", trends)
        assert result is None


class TestSaveTrendSnapshot:
    """Tests for trend snapshot persistence."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        import observability.snapshot as smod
        self._orig_dir = smod.PREDICTIONS_DIR
        self._test_dir = os.path.join(self.tmp, "predictions")
        smod.PREDICTIONS_DIR = self._test_dir

    def teardown_method(self):
        import observability.snapshot as smod
        smod.PREDICTIONS_DIR = self._orig_dir

    def test_save_creates_file(self):
        trends = [
            {"topic": "agent-memory", "stage": "accelerating",
             "growth_velocity": 3.0, "acceleration": 2.5,
             "confidence": 0.8, "evidence_count": 12},
        ]
        path = save_trend_snapshot("agent", trends, window_days=60)
        assert os.path.exists(path)

    def test_snapshot_has_correct_structure(self):
        trends = [{"topic": "mcp", "stage": "emerging",
                    "growth_velocity": 1.5, "acceleration": 0.8,
                    "confidence": 0.6, "evidence_count": 5}]
        path = save_trend_snapshot("agent", trends, window_days=90)
        data = json.loads(Path(path).read_text())
        assert data["snapshot_type"] == "trend"
        assert data["domain"] == "agent"
        assert data["threshold_version"] == "v1"
        assert "created_at" in data
        preds = data["predictions"]
        assert preds["window_days"] == 90
        assert len(preds["trends"]) == 1
        assert preds["trends"][0]["topic"] == "mcp"


class TestSavePainSnapshot:
    """Tests for pain cluster snapshot persistence."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        import observability.snapshot as smod
        self._orig_dir = smod.PREDICTIONS_DIR
        self._test_dir = os.path.join(self.tmp, "predictions")
        smod.PREDICTIONS_DIR = self._test_dir

    def teardown_method(self):
        import observability.snapshot as smod
        smod.PREDICTIONS_DIR = self._orig_dir

    def test_save_pain_snapshot(self):
        clusters = [
            {"cluster_id": 0, "title": "Auth pain", "severity": 3.5,
             "frequency": 15, "affected_repos": ["repo/a"]},
        ]
        path = save_pain_snapshot("agent", clusters, issue_count=100, noise_count=20)
        assert os.path.exists(path)
        data = json.loads(Path(path).read_text())
        assert data["snapshot_type"] == "pain"
        assert data["predictions"]["issue_count"] == 100
        assert data["predictions"]["noise_count"] == 20


class TestSaveOpportunitySnapshot:
    """Tests for opportunity snapshot persistence."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        import observability.snapshot as smod
        self._orig_dir = smod.PREDICTIONS_DIR
        self._test_dir = os.path.join(self.tmp, "predictions")
        smod.PREDICTIONS_DIR = self._test_dir

    def teardown_method(self):
        import observability.snapshot as smod
        smod.PREDICTIONS_DIR = self._orig_dir

    def test_save_opportunity_snapshot(self):
        cards = [
            {"title": "agent-memory — gap=2.3", "gap_score": 2.3,
             "demand_score": 6.5, "competition_score": 2.8,
             "recommended_action": "strong opportunity"},
        ]
        path = save_opportunity_snapshot("agent", cards)
        assert os.path.exists(path)
        data = json.loads(Path(path).read_text())
        assert data["snapshot_type"] == "opportunity"
        assert len(data["predictions"]["cards"]) == 1


class TestCompareSnapshots:
    """Tests for snapshot comparison (integration)."""

    def test_no_snapshots_returns_empty(self):
        # With no prediction files
        result = compare_snapshots("nonexistent_domain_xyz")
        assert result == []


class TestCompareTrendSnapshots:
    """Tests for trend-to-trend comparison across snapshots."""

    def test_matched_topics(self):
        old_preds = {"trends": [
            {"topic": "agent-memory", "stage": "accelerating",
             "growth_velocity": 3.0}
        ]}
        new_preds = {"trends": [
            {"topic": "agent-memory", "stage": "accelerating",
             "growth_velocity": 4.0}
        ]}
        results = _compare_trend_snapshots(old_preds, new_preds)
        assert len(results) == 1
        assert results[0]["status"] == "validated"

    def test_unmatched_topic(self):
        old_preds = {"trends": [
            {"topic": "dead-topic", "stage": "accelerating",
             "growth_velocity": 2.0}
        ]}
        new_preds = {"trends": [
            {"topic": "new-hotness", "stage": "accelerating",
             "growth_velocity": 5.0}
        ]}
        results = _compare_trend_snapshots(old_preds, new_preds)
        assert len(results) == 1
        assert results[0]["status"] == "unmatched"


class TestCompareOpportunitySnapshots:
    """Tests for opportunity comparison."""

    def test_matched_opportunity(self):
        old_preds = {"cards": [
            {"title": "agent-memory — gap=2.3", "gap_score": 2.3,
             "demand_score": 6.0, "competition_score": 2.6,
             "recommended_action": "strong opportunity"},
        ]}
        new_preds = {"cards": [
            {"title": "agent-memory — gap=1.8", "gap_score": 1.8,
             "demand_score": 5.0, "competition_score": 2.8,
             "recommended_action": "moderate opportunity"},
        ]}
        results = _compare_opportunity_snapshots(old_preds, new_preds)
        assert len(results) == 1
        assert results[0]["status"] == "compared"
        assert results[0]["gap_delta"] == -0.5

    def test_unmatched_opportunity(self):
        old_preds = {"cards": [
            {"title": "old-opp — gap=1.5", "gap_score": 1.5,
             "demand_score": 3.0, "competition_score": 2.0,
             "recommended_action": "monitor"},
        ]}
        new_preds = {"cards": []}
        results = _compare_opportunity_snapshots(old_preds, new_preds)
        assert len(results) == 1
        assert results[0]["status"] == "unmatched"


class TestComparePainSnapshots:
    """Tests for pain cluster comparison."""

    def test_matched_cluster(self):
        old_preds = {"clusters": [
            {"cluster_id": 0, "title": "Auth pain", "severity": 3.5,
             "frequency": 15},
        ]}
        new_preds = {"clusters": [
            {"cluster_id": 0, "title": "Auth pain", "severity": 2.0,
             "frequency": 10},
        ]}
        results = _compare_pain_snapshots(old_preds, new_preds)
        assert len(results) == 1
        assert results[0]["status"] == "compared"
        assert results[0]["severity_change_pct"] < 0  # severity went down

    def test_unmatched_cluster(self):
        old_preds = {"clusters": [
            {"cluster_id": 99, "title": "Old cluster", "severity": 1.0,
             "frequency": 5},
        ]}
        new_preds = {"clusters": []}
        results = _compare_pain_snapshots(old_preds, new_preds)
        assert len(results) == 1
        assert results[0]["status"] == "unmatched"
