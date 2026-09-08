"""Tests for the deterministic DeveloperDNA computation (P5)."""

import pytest

from models.payload import DeveloperDNA
from intelligence.developer_dna import (
    DIMENSIONS,
    compute_developer_dna,
    merge_developer_dna,
)


def _repos():
    return [
        {"full_name": "dev/mcp-tool", "language": "Python", "topics": ["mcp", "agent"],
         "stars": 2000, "forks": 150, "velocity": 2.5, "created_at": "2026-08-01T00:00:00Z"},
        {"full_name": "dev/langgraph-sdk", "language": "TypeScript", "topics": ["agent-framework"],
         "stars": 500, "forks": 20, "velocity": 0.2, "created_at": "2024-01-01T00:00:00Z"},
    ]


def _issues():
    return [
        {"repo": "dev/mcp-tool", "issue_number": 1, "title": "state lost on retry", "labels": ["reliability"]},
        {"repo": "dev/mcp-tool", "issue_number": 2, "title": "auth fails", "labels": ["reliability", "security"]},
    ]


class TestComputeDeveloperDNA:
    def test_all_eight_dimensions_present(self):
        dna = compute_developer_dna("dev", _repos(), _issues())
        names = [d.dimension for d in dna.dimensions]
        assert set(names) == set(DIMENSIONS)
        assert len(names) == len(DIMENSIONS)  # no duplicates

    def test_technology_choices_observed(self):
        dna = compute_developer_dna("dev", _repos(), _issues())
        tech = next(d for d in dna.dimensions if d.dimension == "technology_choices")
        assert tech.status == "observed"
        assert "Python" in tech.summary
        assert tech.evidence  # backed by repo facts

    def test_problem_domains_observed_from_issue_labels(self):
        dna = compute_developer_dna("dev", _repos(), _issues())
        pd = next(d for d in dna.dimensions if d.dimension == "problem_domains")
        assert pd.status == "observed"
        assert "reliability" in pd.summary
        assert all(e.kind == "issue" for e in pd.evidence)

    def test_dimensions_without_commit_data_are_unknown(self):
        """No commit/PR/CI data in signals → these must be unknown, not fabricated."""
        dna = compute_developer_dna("dev", _repos(), _issues())
        for name in ("build_patterns", "iteration_style", "testing_reliability_signals"):
            d = next(x for x in dna.dimensions if x.dimension == name)
            assert d.status == "unknown"
            assert d.evidence == []

    def test_activity_populates_commit_backed_dimensions(self):
        activity = [
            {"repo": "dev/mcp-tool", "merged_prs": 8, "open_prs": 2, "recent_commits": 40,
             "releases": 3, "has_ci": True, "has_tests": True},
        ]
        dna = compute_developer_dna("dev", _repos(), _issues(), activity=activity)
        bp = next(d for d in dna.dimensions if d.dimension == "build_patterns")
        it = next(d for d in dna.dimensions if d.dimension == "iteration_style")
        tr = next(d for d in dna.dimensions if d.dimension == "testing_reliability_signals")

        assert bp.status != "unknown"
        assert "PR" in bp.summary
        assert it.status != "unknown"
        assert tr.status == "observed"  # CI/test presence is a direct fact
        assert any("CI" in s for s in tr.summary.split("；"))

    def test_sparse_activity_stays_unknown_where_no_data(self):
        # Activity present but no PR/commit signal → those stay unknown (honest).
        activity = [{"repo": "dev/x", "merged_prs": 0, "open_prs": 0, "recent_commits": 0,
                     "releases": 0, "has_ci": False, "has_tests": False}]
        dna = compute_developer_dna("dev", _repos(), _issues(), activity=activity)
        bp = next(d for d in dna.dimensions if d.dimension == "build_patterns")
        assert bp.status == "unknown"

    def test_empty_input_produces_unknowns_not_stories(self):
        dna = compute_developer_dna("nobody", [], [])
        for d in dna.dimensions:
            if d.status == "unknown":
                assert d.evidence == []
                assert d.confidence == 0.0
        # Nothing fabricated: every observed/inferred dim must cite evidence.
        for d in dna.dimensions:
            if d.status != "unknown":
                assert d.evidence, f"{d.dimension} claimed {d.status} without evidence"

    def test_deterministic_same_input_same_output(self):
        a = compute_developer_dna("dev", _repos(), _issues())
        b = compute_developer_dna("dev", _repos(), _issues())
        # computed_at is a metadata timestamp; the computed content must be stable.
        assert a.dimensions == b.dimensions
        assert a.source_repos == b.source_repos
        assert a.source_issues == b.source_issues

    def test_every_non_unknown_dimension_cites_evidence(self):
        dna = compute_developer_dna("dev", _repos(), _issues())
        for d in dna.dimensions:
            if d.status in ("observed", "inferred"):
                assert d.evidence, f"{d.dimension} lacks evidence"


class TestMerge:
    def test_unchanged_sources_return_previous(self):
        prev = compute_developer_dna("dev", _repos(), _issues())
        cur = compute_developer_dna("dev", _repos(), _issues())
        merged, changed = merge_developer_dna(prev, cur)
        assert changed is False
        assert merged is prev

    def test_changed_sources_return_current(self):
        prev = compute_developer_dna("dev", _repos(), _issues())
        new_repos = _repos() + [
            {"full_name": "dev/new-thing", "language": "Rust", "topics": ["cli"],
             "stars": 10, "forks": 0, "velocity": 0.0, "created_at": "2026-09-01T00:00:00Z"}
        ]
        cur = compute_developer_dna("dev", new_repos, _issues())
        merged, changed = merge_developer_dna(prev, cur)
        assert changed is True
        assert merged is cur
        assert len(merged.source_repos) == 3


class TestSchema:
    def test_developer_dna_model(self):
        dna = DeveloperDNA(developer="dev")
        assert dna.dimensions == []
        assert dna.source_repos == []
        assert dna.source_issues == 0
