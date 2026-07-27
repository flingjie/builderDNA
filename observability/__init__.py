"""Observability module — telemetry, output level control, and diagnostics.

Provides:
  - RunTelemetry: run-level metrics collection (elapsed, errors, cache, API usage)
  - OutputLevel: global --verbose / --quiet control
  - get_console / vprint: level-aware console output
  - behavior tracking: command invocation logging, config change detection
  - mismatch detection: DNA vs behavior gap analysis
  - prediction snapshots: time-based validation framework
"""

from observability.telemetry import RunTelemetry
from observability.output import (
    OutputLevel,
    set_output_level,
    get_output_level,
    get_console,
    vprint,
)
from observability.behavior import (
    record_command,
    record_output_retention,
    detect_config_change,
    detect_mismatches,
    save_mismatch_report,
    BEHAVIOR_LOG_PATH,
    MISMATCH_THRESHOLD,
)
from observability.snapshot import (
    save_trend_snapshot,
    save_pain_snapshot,
    save_opportunity_snapshot,
    compare_snapshots,
    PREDICTIONS_DIR,
)
from observability.hypothesis import (
    HypothesisManager,
)
from observability.diagnostics import (
    generate_parameter_sensitivity,
    record_bootstrap,
    get_bootstrap_hints,
    compare_diagnostics,
    BOOTSTRAP_PATH,
)

__all__ = [
    # telemetry
    "RunTelemetry",
    # output
    "OutputLevel",
    "set_output_level",
    "get_output_level",
    "get_console",
    "vprint",
    # behavior
    "record_command",
    "record_output_retention",
    "detect_config_change",
    "detect_mismatches",
    "save_mismatch_report",
    "BEHAVIOR_LOG_PATH",
    "MISMATCH_THRESHOLD",
    # snapshot
    "save_trend_snapshot",
    "save_pain_snapshot",
    "save_opportunity_snapshot",
    "compare_snapshots",
    "PREDICTIONS_DIR",
    # hypothesis
    "HypothesisManager",
    # diagnostics
    "generate_parameter_sensitivity",
    "record_bootstrap",
    "get_bootstrap_hints",
    "compare_diagnostics",
    "BOOTSTRAP_PATH",
]
