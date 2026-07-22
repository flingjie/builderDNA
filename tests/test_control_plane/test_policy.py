"""Tests for control_plane.policy — compute_trigger_score formula."""
import pytest
from control_plane.policy import compute_trigger_score


class TestComputeTriggerScore:
    def test_zero_confidence_max_trigger(self):
        """When confidence is 0 and familiarity is 0, trigger should equal impact."""
        score = compute_trigger_score(confidence=0.0, impact=0.8, familiarity=0.0)
        assert score == 0.8

    def test_full_confidence_no_trigger(self):
        """When confidence is 1.0, trigger should be 0 regardless of other params."""
        score = compute_trigger_score(confidence=1.0, impact=0.9, familiarity=0.0)
        assert score == 0.0

    def test_full_familiarity_no_trigger(self):
        """When familiarity is 1.0, trigger should be 0 regardless of other params."""
        score = compute_trigger_score(confidence=0.0, impact=0.9, familiarity=1.0)
        assert score == 0.0

    def test_mid_values(self):
        """Spot-check: (0.5 confidence, 0.6 impact, 0.2 fam) => 0.5*0.6*0.8 = 0.24."""
        score = compute_trigger_score(confidence=0.5, impact=0.6, familiarity=0.2)
        assert score == 0.24

    def test_rounding_to_four_decimals(self):
        """Result is rounded to 4 decimal places."""
        score = compute_trigger_score(
            confidence=1 / 3, impact=0.7, familiarity=1 / 3
        )
        # (1 - 1/3) * 0.7 * (1 - 1/3) = (2/3) * 0.7 * (2/3) = 0.3111...
        assert score == 0.3111

    def test_zero_impact_zero_trigger(self):
        """When impact is 0, trigger should be 0."""
        score = compute_trigger_score(confidence=0.3, impact=0.0, familiarity=0.0)
        assert score == 0.0
