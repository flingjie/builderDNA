"""Tests for P8: self-calibration metrics and confidence-in-report."""

from pathlib import Path

from observability.metrics import compute_metrics, METRIC_NAMES
from cli.commands.report_cmd import _render_md


class TestMetrics:
    def test_computes_all_seven_metrics(self):
        m = compute_metrics()
        assert set(m.keys()) == set(METRIC_NAMES)

    def test_each_metric_has_value_and_note(self):
        m = compute_metrics()
        for name, entry in m.items():
            assert "value" in entry, f"{name} missing value"
            assert "note" in entry, f"{name} missing note"

    def test_missing_state_is_honest_not_fabricated(self):
        """With no local state, metrics return None value + a note (not a guess)."""
        m = compute_metrics()
        for name, entry in m.items():
            if entry["value"] is None:
                assert entry["note"], f"{name} returned None without a note"


class TestReportShowsConfidence:
    def test_low_confidence_trend_is_not_hidden(self, tmp_path):
        data = {
            "command": "trend",
            "domain": "agent",
            "payload": {"trends": [
                {"topic": "x", "stage": "emerging", "growth_velocity": 1.0,
                 "evidence_count": 1, "confidence": 0.2},
            ]},
            "stats": {"total_trends": 1},
        }
        out = tmp_path / "r.md"
        _render_md(data, out, verbose=False)
        content = out.read_text()
        assert "0.20" in content  # confidence rendered even in non-verbose
        assert "⚠" in content  # low-confidence marker present

    def test_opportunity_counter_evidence_rendered(self, tmp_path):
        data = {
            "command": "opportunity",
            "domain": "agent",
            "payload": {"opportunities": [
                {"title": "x", "gap_score": 2.0, "demand_score": 3.0,
                 "competition_score": 1.5, "confidence": 0.3,
                 "counter_evidence": ["单源：仅 1 个 repo 支撑该主题"],
                 "why_now": "emerging", "invalidation_condition": "gap<1.5",
                 "minimal_validation_action": "5 次访谈"},
            ]},
        }
        out = tmp_path / "r.md"
        _render_md(data, out, verbose=False)
        content = out.read_text()
        assert "0.30" in content  # confidence rendered
        assert "反证" in content  # counter-evidence surfaced
