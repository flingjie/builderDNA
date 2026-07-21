"""Tests for validation models."""
from backend.models.validation import ValidationResult, ValidationSignal


class TestValidationSignal:
    def test_creation(self):
        s = ValidationSignal(
            source="demand",
            score=0.8,
            evidence=["issue #123", "discussion #45"],
        )
        assert s.source == "demand"
        assert s.score == 0.8


class TestValidationResult:
    def test_creation(self):
        v = ValidationResult(
            demand_score=0.8,
            supply_score=0.5,
            adoption_score=0.3,
            confidence="medium",
            summary="需求信号强但供给不足",
        )
        assert v.confidence == "medium"
        assert v.demand_score == 0.8

    def test_defaults(self):
        v = ValidationResult()
        assert v.demand_score == 0.0
        assert v.confidence == "low"
