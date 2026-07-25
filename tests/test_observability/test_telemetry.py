"""Tests for the observability telemetry module."""

import time
from observability.telemetry import RunTelemetry


class TestRunTelemetry:
    """Tests for RunTelemetry — operational metrics collection."""

    def test_creation_has_start_time(self):
        """RunTelemetry records a start_time on creation."""
        tel = RunTelemetry()
        assert tel.start_time > 0
        assert tel.elapsed_seconds >= 0

    def test_elapsed_seconds_increases(self):
        """elapsed_seconds reflects real time passage."""
        tel = RunTelemetry()
        t0 = tel.elapsed_seconds
        time.sleep(0.02)
        t1 = tel.elapsed_seconds
        assert t1 >= t0

    def test_initial_state_is_empty(self):
        """New RunTelemetry has zero counters and empty lists."""
        tel = RunTelemetry()
        assert tel.cache_hits == 0
        assert tel.cache_misses == 0
        assert tel.cache_total == 0
        assert tel.cache_hit_rate == 0.0
        assert tel.api_calls == 0
        assert tel.api_waited == 0
        assert tel.errors == []
        assert tel.warnings == []
        assert tel.retry_exhausted == []
        assert not tel.has_issues()

    def test_record_cache_hit(self):
        """record_cache(hit=True) increments cache_hits."""
        tel = RunTelemetry()
        tel.record_cache(hit=True)
        assert tel.cache_hits == 1
        assert tel.cache_misses == 0
        assert tel.cache_total == 1
        assert tel.cache_hit_rate == 1.0

    def test_record_cache_miss(self):
        """record_cache(hit=False) increments cache_misses."""
        tel = RunTelemetry()
        tel.record_cache(hit=False)
        assert tel.cache_hits == 0
        assert tel.cache_misses == 1
        assert tel.cache_total == 1
        assert tel.cache_hit_rate == 0.0

    def test_cache_hit_rate_mixed(self):
        """cache_hit_rate calculates correctly with mixed hits/misses."""
        tel = RunTelemetry()
        tel.record_cache(hit=True)
        tel.record_cache(hit=True)
        tel.record_cache(hit=False)
        assert tel.cache_total == 3
        assert tel.cache_hit_rate == round(2 / 3, 2)

    def test_cache_hit_rate_zero_total(self):
        """cache_hit_rate returns 0.0 when no cache operations recorded."""
        tel = RunTelemetry()
        assert tel.cache_hit_rate == 0.0

    def test_record_api_call(self):
        """record_api_call increments api_calls."""
        tel = RunTelemetry()
        tel.record_api_call()
        tel.record_api_call()
        assert tel.api_calls == 2

    def test_record_api_waited(self):
        """record_api_waited increments api_waited."""
        tel = RunTelemetry()
        tel.record_api_waited()
        assert tel.api_waited == 1

    def test_add_error(self):
        """add_error records structured error info."""
        tel = RunTelemetry()
        tel.add_error("/search/repos", "Timeout", attempts=3)
        assert len(tel.errors) == 1
        assert tel.errors[0]["url"] == "/search/repos"
        assert tel.errors[0]["reason"] == "Timeout"
        assert tel.errors[0]["attempts"] == 3
        assert tel.has_issues()

    def test_add_error_default_attempts(self):
        """add_error defaults attempts to 0."""
        tel = RunTelemetry()
        tel.add_error("/foo", "boom")
        assert tel.errors[0]["attempts"] == 0

    def test_add_warning(self):
        """add_warning records warning messages."""
        tel = RunTelemetry()
        tel.add_warning("Low disk space")
        tel.add_warning("Slow response")
        assert len(tel.warnings) == 2
        assert tel.warnings[0] == "Low disk space"
        assert tel.has_issues()

    def test_add_retry_exhausted(self):
        """add_retry_exhausted records retry exhaustion details."""
        tel = RunTelemetry()
        tel.add_retry_exhausted("/api/repos", "429", 3)
        assert len(tel.retry_exhausted) == 1
        assert tel.retry_exhausted[0]["url"] == "/api/repos"
        assert tel.retry_exhausted[0]["reason"] == "429"
        assert tel.retry_exhausted[0]["attempts"] == 3
        assert tel.has_issues()

    def test_has_issues_false_when_empty(self):
        """has_issues returns False when no errors/warnings/retry exhaustions."""
        tel = RunTelemetry()
        assert not tel.has_issues()

    def test_has_issues_true_with_errors(self):
        """has_issues returns True when there are errors."""
        tel = RunTelemetry()
        tel.add_error("/x", "fail")
        assert tel.has_issues()

    def test_has_issues_true_with_warnings(self):
        """has_issues returns True when there are warnings."""
        tel = RunTelemetry()
        tel.add_warning("something")
        assert tel.has_issues()

    def test_has_issues_true_with_retry_exhausted(self):
        """has_issues returns True when retries were exhausted."""
        tel = RunTelemetry()
        tel.add_retry_exhausted("/a", "500", 2)
        assert tel.has_issues()


class TestRunTelemetryToStats:
    """Tests for to_stats() serialization."""

    def test_to_stats_minimal(self):
        """to_stats always includes elapsed_seconds."""
        tel = RunTelemetry()
        stats = tel.to_stats()
        assert "elapsed_seconds" in stats
        assert isinstance(stats["elapsed_seconds"], float)

    def test_to_stats_excludes_empty_fields(self):
        """to_stats omits fields with zero/empty values."""
        tel = RunTelemetry()
        stats = tel.to_stats()
        assert "errors" not in stats
        assert "warnings" not in stats
        assert "cache_hits" not in stats
        assert "api_calls" not in stats
        assert "retry_exhausted" not in stats

    def test_to_stats_includes_errors(self):
        """to_stats includes error count and details when errors exist."""
        tel = RunTelemetry()
        tel.add_error("/a", "fail")
        stats = tel.to_stats()
        assert stats["errors"] == 1
        assert len(stats["error_details"]) == 1

    def test_to_stats_includes_warnings(self):
        """to_stats includes warning count and details when warnings exist."""
        tel = RunTelemetry()
        tel.add_warning("w1")
        stats = tel.to_stats()
        assert stats["warnings"] == 1
        assert len(stats["warning_details"]) == 1

    def test_to_stats_includes_cache(self):
        """to_stats includes cache stats when cache was used."""
        tel = RunTelemetry()
        tel.record_cache(hit=True)
        tel.record_cache(hit=False)
        stats = tel.to_stats()
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
        assert stats["cache_hit_rate"] == 0.5

    def test_to_stats_includes_api_usage(self):
        """to_stats includes api_calls and api_waited when > 0."""
        tel = RunTelemetry()
        tel.record_api_call()
        tel.record_api_waited()
        stats = tel.to_stats()
        assert stats["api_calls"] == 1
        assert stats["api_waited"] == 1

    def test_to_stats_includes_retry_exhausted(self):
        """to_stats includes retry stats when retries were exhausted."""
        tel = RunTelemetry()
        tel.add_retry_exhausted("/x", "429", 3)
        stats = tel.to_stats()
        assert stats["retry_exhausted"] == 1
        assert len(stats["retry_exhausted_details"]) == 1

    def test_to_stats_full(self):
        """to_stats with all fields populated."""
        tel = RunTelemetry()
        tel.record_cache(hit=True)
        tel.record_cache(hit=True)
        tel.record_cache(hit=False)
        tel.record_api_call()
        tel.record_api_waited()
        tel.add_error("/e", "fail")
        tel.add_warning("warn")
        tel.add_retry_exhausted("/r", "500", 2)

        stats = tel.to_stats()
        assert stats["errors"] == 1
        assert stats["warnings"] == 1
        assert stats["cache_hits"] == 2
        assert stats["cache_misses"] == 1
        assert stats["api_calls"] == 1
        assert stats["api_waited"] == 1
        assert stats["retry_exhausted"] == 1

    def test_to_stats_is_mergeable(self):
        """to_stats dict can be merged with command-specific stats."""
        cmd_stats = {"total_trends": 10}
        tel = RunTelemetry()
        merged = {**cmd_stats, **tel.to_stats()}
        assert merged["total_trends"] == 10
        assert "elapsed_seconds" in merged
