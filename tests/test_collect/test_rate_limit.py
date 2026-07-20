"""Tests for rate limiter."""
import asyncio
import pytest
from collect.github.rate_limit import RateLimiter


class TestRateLimiter:
    def test_initial_state(self):
        rl = RateLimiter()
        assert rl.remaining is None
        assert rl.limit is None
        assert rl.reset_at is None

    def test_update_from_headers(self):
        rl = RateLimiter()
        rl.update({
            "X-RateLimit-Remaining": "4950",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Reset": "1784544658",
        })
        assert rl.remaining == 4950
        assert rl.limit == 5000
        assert rl.reset_at == 1784544658.0
        assert rl.reset_at_iso is not None

    def test_no_wait_when_above_margin(self):
        rl = RateLimiter(safety_margin=50)
        rl.update({
            "X-RateLimit-Remaining": "100",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Reset": "9999999999",
        })

        async def check():
            return await rl.wait_if_needed()

        result = asyncio.run(check())
        assert result is False

    def test_usage_summary(self):
        rl = RateLimiter()
        rl.update({
            "X-RateLimit-Remaining": "4000",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Reset": "1784544658",
        })
        rl.update({
            "X-RateLimit-Remaining": "3999",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Reset": "1784544658",
        })
        summary = rl.usage_summary()
        assert "calls=2" in summary
        assert "remaining=3999/5000" in summary

    def test_partial_headers(self):
        rl = RateLimiter()
        rl.update({"X-RateLimit-Remaining": "3000"})
        assert rl.remaining == 3000
        assert rl.limit is None  # unchanged
