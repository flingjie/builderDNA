"""Tests for intelligence/pain/candidates.py — TF-IDF candidate grouping."""

from intelligence.pain.candidates import (
    build_candidate_groups,
    build_candidates,
    extract_components,
    extract_error_codes,
)


def _issue(**overrides) -> dict:
    fields = {
        "repo": "org/repo",
        "issue_number": 1,
        "title": "Agent hangs on timeout",
        "body": "When calling a tool the agent hangs until timeout.",
        "url": "",
        "labels": [],
    }
    fields.update(overrides)
    return fields


class TestFeatureExtraction:
    def test_extract_error_codes(self):
        codes = extract_error_codes("Error E1001 timeout HTTP 500")
        assert "E1001" in codes
        assert "500" in codes or "HTTP 500" in codes

    def test_extract_exception_names(self):
        codes = extract_error_codes("TimeoutError while streaming")
        assert "TimeoutError" in codes

    def test_extract_components_from_labels(self):
        comps = extract_components(["area:runtime", "component:mcp"], "")
        assert "runtime" in comps
        assert "mcp" in comps

    def test_plain_label_kept(self):
        assert "bug" in extract_components(["bug"], "")


class TestBuildCandidates:
    def test_annotates_error_codes_and_components(self):
        cand = build_candidates([_issue(title="Error E1001", labels=["area:runtime"])])[0]
        assert "E1001" in cand.error_codes
        assert "runtime" in cand.components
        assert cand.issue_key == "org/repo#1"


class TestBuildCandidateGroups:
    def test_similar_issues_group(self):
        issues = [
            _issue(issue_number=1, title="Agent hangs on timeout", body="tool call times out and agent hangs"),
            _issue(issue_number=2, title="Agent hangs when tool times out", body="agent hangs until tool timeout"),
        ]
        groups, noise = build_candidate_groups(issues)
        assert len(groups) == 1
        assert len(noise) == 0
        assert len(groups[0].issues) == 2

    def test_dissimilar_issues_are_noise(self):
        issues = [
            _issue(issue_number=1, title="Agent hangs on timeout", body="tool call times out"),
            _issue(issue_number=2, title="Database migration fails", body="schema migration does not apply"),
        ]
        groups, noise = build_candidate_groups(issues)
        assert len(groups) == 0
        assert len(noise) == 2

    def test_single_issue_is_noise(self):
        groups, noise = build_candidate_groups([_issue()])
        assert groups == []
        assert len(noise) == 1

    def test_empty_is_empty(self):
        groups, noise = build_candidate_groups([])
        assert groups == []
        assert noise == []

    def test_chinese_issues_group(self):
        issues = [
            _issue(issue_number=1, title="配置错误导致超时", body="超时导致挂起"),
            _issue(issue_number=2, title="配置错误导致超时挂起", body="超时挂起"),
        ]
        groups, noise = build_candidate_groups(issues)
        assert len(groups) == 1
        assert len(noise) == 0

    def test_shared_features_computed(self):
        issues = [
            _issue(issue_number=1, title="Error E1001", labels=["area:runtime"]),
            _issue(issue_number=2, title="E1001 failure", labels=["area:runtime"]),
        ]
        groups, _ = build_candidate_groups(issues)
        assert len(groups) == 1
        assert "E1001" in groups[0].shared_features.get("error_codes", [])
        assert "runtime" in groups[0].shared_features.get("components", [])
