"""Run-level telemetry — metrics collected during command execution.

Provides RunTelemetry, a lightweight dataclass that collects operational
metrics (elapsed time, errors, warnings, cache stats, API usage, retry
exhaustions) and serializes them into SandboxResult.stats.
"""

import time
from dataclasses import dataclass, field


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
