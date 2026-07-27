"""Run-level telemetry — metrics collected during command execution.

Provides RunTelemetry, a lightweight dataclass that collects operational
metrics (elapsed time, errors, warnings, cache stats, API usage, retry
exhaustions) and serializes them into SandboxResult.stats.

Also provides persist_run_stats() to write command-level timing data to
state/run_stats.json for use by the GOAP A* planner's cost function.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

RUN_STATS_PATH = "state/run_stats.json"


def _resolve_run_stats_path() -> Path:
    """Resolve run_stats.json relative to the project root.

    When running from any subdirectory, locate the project root by walking
    up until we find a config.yaml (BuilderDNA's project marker).
    Falls back to the original relative path if config.yaml is not found.
    """
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "config.yaml").exists():
            return parent / RUN_STATS_PATH
    return Path(RUN_STATS_PATH)


def _load_run_stats() -> dict:
    """Load run_stats.json, returning skeleton if missing or corrupt."""
    path = _resolve_run_stats_path()
    if not path.exists():
        return {"command_stats": {}}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        # Corrupt file — back up and start fresh so data isn't silently lost
        backup = path.with_suffix(".json.bak")
        try:
            path.rename(backup)
        except OSError:
            pass
        return {"command_stats": {}}
    except OSError:
        return {"command_stats": {}}


def persist_run_stats(command: str, elapsed_s: float) -> None:
    """Update the rolling average duration for a command in run_stats.json.

    Called after each CLI command completes. Uses Welford-style incremental
    average to avoid storing all individual durations.

    Args:
        command: command name (e.g. 'collect', 'trend', 'pain')
        elapsed_s: duration in seconds for this run
    """
    data = _load_run_stats()
    stats = data.setdefault("command_stats", {})

    if command in stats:
        entry = stats[command]
        n = entry.get("n", 0)
        old_avg = entry.get("avg_s", 0)
        # Incremental average: new_avg = old_avg + (x - old_avg) / (n + 1)
        new_n = n + 1
        new_avg = round(old_avg + (elapsed_s - old_avg) / new_n, 2)
        stats[command] = {"avg_s": new_avg, "n": new_n}
    else:
        stats[command] = {"avg_s": round(elapsed_s, 2), "n": 1}

    path = _resolve_run_stats_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def get_command_cost(command: str) -> float:
    """Get the estimated cost (seconds) for a command.

    Returns the historical average if available, otherwise a conservative default.
    Used by the GOAP A* planner's g(n) and h(n) computation.
    """
    # Conservative defaults for cold starts — must match plan_state.json action_catalog avg_cost_s
    FALLBACKS = {
        "collect": 45.0,
        "trend": 8.0,
        "pain": 92.0,
        "opportunity": 3.0,
        "report": 1.0,
        "config": 1.0,
        "observability": 12.0,
    }
    data = _load_run_stats()
    entry = data.get("command_stats", {}).get(command)
    if entry and entry.get("n", 0) > 0:
        return entry["avg_s"]
    return FALLBACKS.get(command, 10.0)


@dataclass
class RunTelemetry:
    """Collects run-level operational metrics for observability.

    Usage:
        tel = RunTelemetry()
        tel.record_api_call()
        tel.record_cache(hit=True)
        ...
        stats = tel.to_stats()  # → dict ready for SandboxResult.stats
    """

    start_time: float = field(default_factory=time.time)

    # Error/Warning tracking
    errors: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Cache
    cache_hits: int = 0
    cache_misses: int = 0

    # API usage
    api_calls: int = 0
    api_waited: int = 0

    # Retry exhaustion
    retry_exhausted: list[dict] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        """Seconds elapsed since telemetry was created."""
        return round(time.time() - self.start_time, 2)

    @property
    def cache_total(self) -> int:
        """Total cache lookups (hits + misses)."""
        return self.cache_hits + self.cache_misses

    @property
    def cache_hit_rate(self) -> float:
        """Cache hit rate as a fraction (0.0–1.0)."""
        if self.cache_total == 0:
            return 0.0
        return round(self.cache_hits / self.cache_total, 2)

    # ── Recording methods ──────────────────────────────────────

    def add_error(self, url: str, reason: str, attempts: int = 0) -> None:
        """Record a non-fatal error that occurred during execution."""
        self.errors.append({
            "url": url,
            "reason": str(reason),
            "attempts": attempts,
        })

    def add_warning(self, message: str) -> None:
        """Record a warning message."""
        self.warnings.append(message)

    def record_cache(self, hit: bool = True) -> None:
        """Record a cache hit or miss."""
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

    def record_api_call(self) -> None:
        """Increment API call counter."""
        self.api_calls += 1

    def record_api_waited(self) -> None:
        """Increment API wait counter (rate-limit induced pauses)."""
        self.api_waited += 1

    def add_retry_exhausted(self, url: str, reason: str, attempts: int) -> None:
        """Record a request that failed after exhausting all retries."""
        self.retry_exhausted.append({
            "url": url,
            "reason": reason,
            "attempts": attempts,
        })

    def has_issues(self) -> bool:
        """True if there are any errors, warnings, or retry exhaustions."""
        return bool(self.errors or self.warnings or self.retry_exhausted)

    # ── Serialization ──────────────────────────────────────────

    def to_stats(self) -> dict:
        """Serialize telemetry to a dict suitable for SandboxResult.stats.

        Does NOT overwrite existing stats keys — callers should merge
        with their command-specific stats (e.g. `{**cmd_stats, **tel.to_stats()}`).
        """
        stats: dict = {
            "elapsed_seconds": self.elapsed_seconds,
        }

        if self.errors:
            stats["errors"] = len(self.errors)
            stats["error_details"] = self.errors

        if self.warnings:
            stats["warnings"] = len(self.warnings)
            stats["warning_details"] = self.warnings

        if self.cache_total > 0:
            stats["cache_hits"] = self.cache_hits
            stats["cache_misses"] = self.cache_misses
            stats["cache_hit_rate"] = self.cache_hit_rate

        if self.api_calls > 0:
            stats["api_calls"] = self.api_calls

        if self.api_waited > 0:
            stats["api_waited"] = self.api_waited

        if self.retry_exhausted:
            stats["retry_exhausted"] = len(self.retry_exhausted)
            stats["retry_exhausted_details"] = self.retry_exhausted

        return stats
