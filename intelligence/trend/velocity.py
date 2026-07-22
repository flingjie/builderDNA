"""Velocity computation — first and second derivative (acceleration) of trend signals.

This is the core metric engine for the Trend Intelligence layer.
Use from detector.py for the unified pipeline import path.
"""

from datetime import datetime, timezone, timedelta

from signals.models import Signal


def compute_acceleration(signals: list[Signal], window_days: int = 30) -> float:
    """Compute second derivative: acceleration of signal velocity.

    Splits the signal history into two equal windows (recent vs previous)
    and computes the rate of change of average velocity between them.

    Args:
        signals: List of Signal objects, each with a .timestamp and .velocity.
        window_days: Size of the recent window in days.

    Returns:
        Acceleration value (velocity change per day), rounded to 4 decimals.
        Returns 0.0 if fewer than 2 signals are provided.
    """
    if len(signals) < 2:
        return 0.0
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    mid_cutoff = now - timedelta(days=window_days * 2)

    recent = [s for s in signals if s.timestamp >= cutoff]
    previous = [s for s in signals if mid_cutoff <= s.timestamp < cutoff]

    if not recent or not previous:
        return 0.0

    v2 = sum(s.velocity for s in recent) / len(recent)
    v1 = sum(s.velocity for s in previous) / len(previous)
    dt = max(1, window_days)
    return round((v2 - v1) / dt, 4)


def compute_velocity(stars: int, days_since_creation: int) -> float:
    """Compute first derivative: star velocity for a repo.

    Args:
        stars: Total star count.
        days_since_creation: Days since the repo was created.

    Returns:
        Velocity as stars per day, rounded to 2 decimals.
        Returns float(stars) if days_since_creation <= 0 to avoid
        division by zero.
    """
    if days_since_creation <= 0:
        return float(stars)
    return round(stars / days_since_creation, 2)


def compute_confidence(
    repo_count: int,
    avg_velocity: float,
    velocity_variance: float,
) -> float:
    """Compute a confidence score for a trend signal.

    Balances two factors:
      - Count factor: saturates at 10+ repos.
      - Variance penalty: high variance reduces confidence.

    Args:
        repo_count: Number of repos contributing to the signal.
        avg_velocity: Average velocity across repos (used as normalizer).
        velocity_variance: Variance of repo velocities (spread indicator).

    Returns:
        Confidence score between 0.0 and 1.0, rounded to 2 decimals.
    """
    if repo_count <= 0:
        return 0.0
    count_factor = min(1.0, repo_count / 10.0)
    variance_penalty = 1.0 / (1.0 + velocity_variance)
    return round(count_factor * 0.5 + variance_penalty * 0.5, 2)
