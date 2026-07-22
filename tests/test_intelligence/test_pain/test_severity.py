"""Tests for intelligence/pain/severity.py — severity computation."""

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
        # "BUG ERROR CRASH" = 3 hits => >=2 but <5 => 1.2
        assert compute_sentiment_multiplier("BUG ERROR CRASH") == 1.2


class TestComputeSeverity:
    def test_zero_comments_and_participants_returns_zero(self):
        assert compute_severity(0, 0, "text") == 0.0

    def test_negative_comments_returns_zero(self):
        assert compute_severity(-1, 0, "text") == 0.0

    def test_negative_participants_returns_zero(self):
        assert compute_severity(0, -1, "text") == 0.0

    def test_single_comment_single_participant(self):
        # log(1+1) * log(1+1) * 1.0 = log(2)^2 ≈ 0.48
        expected = round(math.log(2) * math.log(2) * 1.0, 2)
        assert compute_severity(1, 1, "text") == expected

    def test_severity_increases_with_comments(self):
        low = compute_severity(1, 1, "text")
        high = compute_severity(10, 1, "text")
        assert high > low

    def test_severity_increases_with_participants(self):
        low = compute_severity(1, 1, "text")
        high = compute_severity(1, 5, "text")
        assert high > low

    def test_sentiment_multiplier_applied(self):
        neutral = compute_severity(5, 3, "minor ui glitch")
        negative = compute_severity(5, 3, "broken crash bug fail error")
        assert negative > neutral

    def test_known_value(self):
        # log(5+1) * log(3+1) * 1.0
        expected = round(math.log(6) * math.log(4) * 1.0, 2)
        assert compute_severity(5, 3, "text") == expected

    def test_rounding_to_two_decimals(self):
        result = compute_severity(7, 4, "text")
        result_str = str(result)
        assert "." in result_str
        assert len(result_str.split(".")[1]) <= 2
