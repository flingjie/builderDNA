"""Trend Detector — unified import path for trend analysis.

Re-exports core logic from the radar engine and the velocity computation
module so the main pipeline can import from a single path.
"""

from backend.engine.radar import (
    collect_topic_data,
    compute_repo_trend,
    aggregate_topic,
    get_stage,
    run_radar,
)

from intelligence.trend.velocity import (
    compute_acceleration,
    compute_velocity,
    compute_confidence,
)

__all__ = [
    "collect_topic_data",
    "compute_repo_trend",
    "aggregate_topic",
    "get_stage",
    "run_radar",
    "compute_acceleration",
    "compute_velocity",
    "compute_confidence",
]
