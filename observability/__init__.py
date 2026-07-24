"""Observability module — telemetry, output level control, and diagnostics.

Provides:
  - RunTelemetry: run-level metrics collection (elapsed, errors, cache, API usage)
  - OutputLevel: global --verbose / --quiet control
  - get_console / vprint: level-aware console output
"""

from observability.telemetry import RunTelemetry
from observability.output import (
    OutputLevel,
    set_output_level,
    get_output_level,
    get_console,
    vprint,
)

__all__ = [
    "RunTelemetry",
    "OutputLevel",
    "set_output_level",
    "get_output_level",
    "get_console",
    "vprint",
]
