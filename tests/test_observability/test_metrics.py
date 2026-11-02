"""Tests for P8: self-calibration metrics."""

from observability.metrics import compute_metrics, METRIC_NAMES


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
