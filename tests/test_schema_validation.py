"""Tests for input schema validation (P3: collect → trend/pain → opportunity)."""

from cli.commands.schema_validation import (
    validate_collect_payload,
    validate_trend_payload,
    validate_pain_payload,
)


class TestValidateCollectPayload:
    def test_valid_full_collect_output(self):
        payload = {
            "repos": [{"full_name": "a/b"}],
            "issues": [{"repo": "a/b", "issue_number": 1}],
            "signals": [{}],
        }
        assert validate_collect_payload(payload) == []

    def test_empty_repos_and_signals_is_invalid(self):
        assert validate_collect_payload({}) != []

    def test_repos_must_be_a_list(self):
        assert validate_collect_payload({"repos": "not-a-list"}) != []

    def test_repo_missing_full_name(self):
        errors = validate_collect_payload({"repos": [{"stars": 5}]})
        assert any("full_name" in e for e in errors)

    def test_issue_missing_repo(self):
        errors = validate_collect_payload({"repos": [], "issues": [{"title": "x"}]})
        assert any("repo" in e for e in errors)


class TestValidateTrendPayload:
    def test_valid(self):
        assert validate_trend_payload({"trends": [{"topic": "mcp"}]}) == []

    def test_missing_trends(self):
        assert validate_trend_payload({}) != []

    def test_trend_missing_topic(self):
        errors = validate_trend_payload({"trends": [{"stage": "emerging"}]})
        assert any("topic" in e for e in errors)


class TestValidatePainPayload:
    def test_valid_empty_clusters(self):
        assert validate_pain_payload({"clusters": []}) == []

    def test_missing_clusters(self):
        assert validate_pain_payload({}) != []
