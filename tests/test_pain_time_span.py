"""Tests for PainCluster time-span computation (P6)."""

from cli.commands.pain import _compute_time_span_days


class TestComputeTimeSpanDays:
    def test_span_across_dated_issues(self):
        issues = [
            {"created_at": "2026-01-01T00:00:00Z"},
            {"created_at": "2026-01-11T00:00:00Z"},
            {"created_at": "2026-01-06T00:00:00Z"},
        ]
        assert _compute_time_span_days(issues) == 10  # Jan 1 → Jan 11

    def test_single_issue_is_zero(self):
        assert _compute_time_span_days([{"created_at": "2026-01-01T00:00:00Z"}]) == 0

    def test_missing_dates_are_ignored(self):
        issues = [
            {"created_at": "2026-01-01T00:00:00Z"},
            {"created_at": ""},
            {"created_at": "not-a-date"},
            {"created_at": "2026-01-05T00:00:00Z"},
        ]
        assert _compute_time_span_days(issues) == 4

    def test_no_dates_is_zero(self):
        assert _compute_time_span_days([{}, {"title": "x"}]) == 0
