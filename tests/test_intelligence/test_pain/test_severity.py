"""Tests for intelligence/pain/severity.py — severity computation (additive formula)."""

import math

from intelligence.pain.severity import (
    compute_severity,
    compute_sentiment_multiplier,
    SENTIMENT_SEEDS,
)


class TestComputeSentimentMultiplier:
    def test_negative_words_empty_string(self):
        assert compute_sentiment_multiplier("") == 1.0

    def test_negative_words_few(self):
        text = "This is a minor issue with the UI"
        assert compute_sentiment_multiplier(text) == 1.0

    def test_negative_words_moderate(self):
        text = "This bug is broken and frustrating"
        assert compute_sentiment_multiplier(text) == 1.2

    def test_negative_words_high(self):
        text = "broken crash bug error missing fail blocked frustrating cannot break"
        assert compute_sentiment_multiplier(text) == 1.5

    def test_case_insensitive(self):
        # "BUG ERROR CRASH" = 3 hits → >=2 but <5 → 1.2
        assert compute_sentiment_multiplier("BUG ERROR CRASH") == 1.2


class TestComputeSeverity:
    # ── Additive formula: (log(c+1) + log(p+1) + log(r/2+1)) * sentiment ──

    def test_all_zero_returns_zero(self):
        """All three channels zero → returns 0.0."""
        assert compute_severity(0, 0, "text", reactions=0) == 0.0

    def test_negative_comments_returns_zero(self):
        """Negative comments + zero others → 0.0 (max(x,0) floors negatives)."""
        assert compute_severity(-1, 0, "text", reactions=0) == 0.0

    def test_negative_participants_returns_zero(self):
        assert compute_severity(0, -1, "text", reactions=0) == 0.0

    def test_reactions_only_returns_nonzero(self):
        """BUG FIX: c=0, p=0, r=50 should produce non-zero severity.
        Old multiplicative formula: log(1)*log(1)*log(50/2+1)*sentiment = 0.
        New additive formula: (log(1)+log(1)+log(50/2+1))*1.0 = log(26) ≈ 3.26.
        """
        result = compute_severity(0, 0, "text", reactions=50)
        expected = round(math.log(50 / 2.0 + 1), 2)  # log(26) ≈ 3.26
        assert result == expected
        assert result > 0

    def test_reactions_only_small(self):
        """c=0, p=0, r=2 → log(2/2+1) = log(2) ≈ 0.69."""
        result = compute_severity(0, 0, "text", reactions=2)
        expected = round(math.log(2), 2)  # ≈ 0.69
        assert result == expected

    def test_single_comment_single_participant(self):
        # log(1+1) + log(1+1) + 0 = log(2) + log(2) ≈ 1.39
        expected = round(math.log(2) + math.log(2), 2)
        assert compute_severity(1, 1, "text") == expected

    def test_severity_increases_with_comments(self):
        low = compute_severity(1, 1, "text")
        high = compute_severity(10, 1, "text")
        assert high > low

    def test_severity_increases_with_participants(self):
        low = compute_severity(1, 1, "text")
        high = compute_severity(1, 5, "text")
        assert high > low

    def test_severity_increases_with_reactions(self):
        low = compute_severity(1, 1, "text", reactions=0)
        high = compute_severity(1, 1, "text", reactions=50)
        assert high > low

    def test_sentiment_multiplier_applied(self):
        neutral = compute_severity(5, 3, "minor ui glitch")
        negative = compute_severity(5, 3, "broken crash bug fail error")
        assert negative > neutral

    def test_known_value(self):
        # log(5+1) + log(3+1) + 0 = log(6) + log(4) ≈ 1.79 + 1.39 = 3.18
        expected = round(math.log(6) + math.log(4), 2)
        assert compute_severity(5, 3, "text") == expected

    def test_rounding_to_two_decimals(self):
        result = compute_severity(7, 4, "text")
        result_str = str(result)
        assert "." in result_str
        assert len(result_str.split(".")[1]) <= 2
