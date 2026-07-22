"""Proactive GitHub API rate limit management.

Monitors X-RateLimit-Remaining and X-RateLimit-Reset headers from
GitHub API responses, and automatically pauses when approaching the limit.
"""

import asyncio
import time
from datetime import datetime, timezone


class RateLimiter:
    """Tracks GitHub API rate limit state and waits proactively."""

    def __init__(self, safety_margin: int = 50):
        self.safety_margin = safety_margin
        self._remaining: int | None = None
        self._limit: int | None = None
        self._reset: int | None = None  # epoch seconds
        self._total_calls: int = 0
        self._waited_calls: int = 0

    def update(self, headers: dict[str, str]) -> None:
        """Parse rate limit info from response headers."""
        remaining = headers.get("X-RateLimit-Remaining")
        limit = headers.get("X-RateLimit-Limit")
        reset = headers.get("X-RateLimit-Reset")

        if remaining is not None:
            self._remaining = int(remaining)
        if limit is not None:
            self._limit = int(limit)
        if reset is not None:
            self._reset = int(reset)

        self._total_calls += 1

    @property
    def remaining(self) -> int | None:
        return self._remaining

    @property
    def limit(self) -> int | None:
        return self._limit

    @property
    def reset_at(self) -> float | None:
        """Unix epoch when the rate limit resets."""
        return float(self._reset) if self._reset else None

    @property
    def reset_at_iso(self) -> str | None:
        """ISO 8601 string of reset time."""
        if self._reset is None:
            return None
        return datetime.fromtimestamp(self._reset, tz=timezone.utc).isoformat()

    async def wait_if_needed(self) -> bool:
        """Sleep until rate limit resets if remaining < safety_margin.

        Returns:
            True if a wait occurred, False otherwise.
        """
        if self._remaining is None or self._remaining >= self.safety_margin:
            return False

        if self._reset is not None:
            now = time.time()
            wait_seconds = max(self._reset - now + 1, 0)
            if wait_seconds > 0:
                self._waited_calls += 1
                print(f"[RateLimit] {self._remaining}/{self._limit} remaining — "
                      f"waiting {wait_seconds:.0f}s until reset at {self.reset_at_iso}")
                await asyncio.sleep(wait_seconds)
                return True
        return False

    def usage_summary(self) -> str:
        """Human-readable summary of rate limit usage."""
        parts = [f"calls={self._total_calls}"]
        if self._remaining is not None and self._limit is not None:
            parts.append(f"remaining={self._remaining}/{self._limit}")
        if self._waited_calls > 0:
            parts.append(f"waited={self._waited_calls}x")
        return ", ".join(parts)
