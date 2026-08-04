"""Velocity computation — first and second derivative (acceleration) of trend signals.

This is the core metric engine for the Trend Intelligence layer.
Use from detector.py for the unified pipeline import path.
"""

from datetime import datetime, timezone, timedelta

from signals.models import Signal


def _resolve_stage(velocity: float, acceleration: float, confidence: float) -> tuple[str, str]:
    """Assign lifecycle stage based on velocity + acceleration.

    Returns:
        (stage, reason) — stage string and human-readable justification.
    """
    if acceleration > 2.0 and confidence > 0.6:
        return "accelerating", f"acceleration={acceleration:.1f} (>2.0) + confidence={confidence:.2f} (>0.6) → accelerating"
    if acceleration > 0.5 and confidence > 0.3:
        return "emerging", f"acceleration={acceleration:.1f} (>0.5) + confidence={confidence:.2f} (>0.3) → emerging"
    if acceleration < -1.0:
        return "declining", f"acceleration={acceleration:.1f} (<-1.0) → declining"
    return "mainstream", f"acceleration={acceleration:.1f}, confidence={confidence:.2f} → mainstream (default)"


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
