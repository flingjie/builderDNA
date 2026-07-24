"""Tests for intelligence/trend/velocity.py — acceleration, velocity, confidence."""

from datetime import datetime, timezone, timedelta

import pytest

from intelligence.trend.velocity import (
    compute_acceleration,
    compute_velocity,
)


# ── compute_velocity ──────────────────────────────────────────────────────


class TestComputeVelocity:
    def test_zero_days_returns_stars(self):
        """When days_since_creation is <= 0, return the raw star count."""
        assert compute_velocity(100, 0) == 100.0
        assert compute_velocity(100, -5) == 100.0

    def test_normal_velocity(self):
        """100 stars over 50 days = 2.0 stars/day."""
        assert compute_velocity(100, 50) == 2.0

    def test_fractional_velocity(self):
        """1 star over 3 days = 0.33 stars/day."""
        assert compute_velocity(1, 3) == 0.33

    def test_large_values(self):
        """10_000 stars over 365 days ≈ 27.4 stars/day."""
        assert compute_velocity(10000, 365) == 27.4

    def test_zero_stars(self):
        """0 stars always returns 0.0."""
        assert compute_velocity(0, 30) == 0.0


# ── compute_acceleration ──────────────────────────────────────────────────


class MockSignal:
    """Minimal signal stand-in for acceleration tests."""
    def __init__(self, timestamp: datetime, velocity: float):
        self.timestamp = timestamp
        self.velocity = velocity


class TestComputeAcceleration:
    def test_fewer_than_two_signals_returns_zero(self):
        assert compute_acceleration([]) == 0.0
        assert compute_acceleration([MockSignal(datetime.now(timezone.utc), 5.0)]) == 0.0

    def test_flat_velocity_returns_zero(self):
        """If recent and previous windows have the same average velocity, acceleration is 0."""
        now = datetime.now(timezone.utc)
        signals = [
            MockSignal(now - timedelta(days=60), 10.0),
            MockSignal(now - timedelta(days=50), 10.0),
            MockSignal(now - timedelta(days=40), 10.0),
            MockSignal(now - timedelta(days=20), 10.0),
            MockSignal(now - timedelta(days=10), 10.0),
        ]
        # With window_days=30:
        #   recent = signals[-2:] (day 20, 10)   → avg 10.0
        #   previous = signals[:3]  (day 60, 50, 40) → avg 10.0
        #   acceleration = (10 - 10) / 30 = 0.0
        assert compute_acceleration(signals, window_days=30) == 0.0

    def test_positive_acceleration(self):
        """When recent velocity > previous velocity, acceleration is positive."""
        now = datetime.now(timezone.utc)
        signals = [
            MockSignal(now - timedelta(days=60), 5.0),
            MockSignal(now - timedelta(days=50), 5.0),
            MockSignal(now - timedelta(days=20), 20.0),
            MockSignal(now - timedelta(days=10), 20.0),
        ]
        # recent avg = 20.0, previous avg = 5.0
        # accel = (20 - 5) / 30 = 0.5
        assert compute_acceleration(signals, window_days=30) == 0.5

    def test_negative_acceleration(self):
        """When recent velocity < previous velocity, acceleration is negative."""
        now = datetime.now(timezone.utc)
        signals = [
            MockSignal(now - timedelta(days=60), 30.0),
            MockSignal(now - timedelta(days=50), 30.0),
            MockSignal(now - timedelta(days=20), 5.0),
            MockSignal(now - timedelta(days=10), 5.0),
        ]
        # recent avg = 5.0, previous avg = 30.0
        # accel = (5 - 30) / 30 = -0.8333...
        assert compute_acceleration(signals, window_days=30) == pytest.approx(-0.8333, abs=0.001)

    def test_no_previous_signals_returns_zero(self):
        """If no signals fall in the previous window, return 0.0."""
        now = datetime.now(timezone.utc)
        signals = [
            MockSignal(now - timedelta(days=5), 10.0),
            MockSignal(now - timedelta(days=1), 20.0),
        ]
        # window_days=30, mid_cutoff = 60 days ago
        # recent: both signals (within 30 days)
        # previous: none
        assert compute_acceleration(signals, window_days=30) == 0.0

    def test_no_recent_signals_returns_zero(self):
        """If no signals fall in the recent window, return 0.0."""
        now = datetime.now(timezone.utc)
        signals = [
            MockSignal(now - timedelta(days=100), 10.0),
            MockSignal(now - timedelta(days=90), 20.0),
        ]
        # window_days=30 → cutoff = 30 days ago
        # recent: none (both are older than 30 days)
        # previous: both (within 60-30 day range)
        assert compute_acceleration(signals, window_days=30) == 0.0
