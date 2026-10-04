"""Tests for cli/commands/pain_finalize.py — reference validation + finalization."""

import json

import pytest
import typer

from cli.commands.pain_finalize import pain_finalize


def _candidates_payload():
    return {
        "groups": [
            {
                "group_id": 0,
                "issues": [
                    {
                        "issue_key": "org/a#1", "repo": "org/a", "issue_number": 1,
                        "title": "timeout", "body": "", "url": "", "labels": [],
                        "comments": 5, "participants": 3, "reactions": 2,
                        "created_at": "2026-01-01T00:00:00Z",
                        "error_codes": ["Timeout"], "components": [],
                    },
                    {
                        "issue_key": "org/a#2", "repo": "org/a", "issue_number": 2,
                        "title": "timeout again", "body": "", "url": "", "labels": [],
                        "comments": 1, "participants": 1, "reactions": 0,
                        "created_at": "2026-01-10T00:00:00Z",
                        "error_codes": ["Timeout"], "components": [],
                    },
                ],
                "shared_features": {"error_codes": ["Timeout"], "components": [], "labels": []},
                "mean_similarity": 0.8,
            },
        ],
        "noise": [],
        "issue_count": 2,
        "noise_count": 0,
        "repos_analyzed": ["org/a"],
    }


def _write_candidates(tmp_path):
    path = tmp_path / "pain_candidates.json"
    path.write_text(json.dumps({"command": "pain", "domain": "agent", "payload": _candidates_payload()}))
    return str(path)


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    monkeypatch.setattr("cli.commands.pain_finalize.record_command", lambda **kw: None)
    monkeypatch.setattr("cli.commands.pain_finalize.record_output_retention", lambda *a, **kw: None)
    monkeypatch.setattr("cli.commands.pain_finalize.save_pain_snapshot", lambda **kw: None)


class TestDeterministicPromotion:
    def test_promotes_candidate_groups_without_confirmations(self, tmp_path):
        candidates = _write_candidates(tmp_path)
        output = str(tmp_path / "pain_clusters.json")
        pain_finalize(domain="agent", candidates=candidates, confirmations=None, output=output)

        result = json.loads(tmp_path.joinpath("pain_clusters.json").read_text())
        clusters = result["payload"]["clusters"]
        assert len(clusters) == 1
        assert clusters[0]["frequency"] == 2
        assert clusters[0]["title"] == "Timeout issues"
        assert result["command"] == "pain-finalize"


class TestConfirmationPath:
    def test_split_confirmation_produces_two_clusters(self, tmp_path):
        candidates = _write_candidates(tmp_path)
        confirmations = tmp_path / "confirmations.json"
        confirmations.write_text(json.dumps({
            "clusters": [
                {"title": "Config timeout", "issue_keys": ["org/a#1"], "rationale": "config"},
                {"title": "Recovery timeout", "issue_keys": ["org/a#2"], "rationale": "recovery"},
            ]
        }))
        output = str(tmp_path / "pain_clusters.json")
        pain_finalize(domain="agent", candidates=candidates,
                      confirmations=str(confirmations), output=output)

        clusters = json.loads(tmp_path.joinpath("pain_clusters.json").read_text())["payload"]["clusters"]
        assert len(clusters) == 2
        titles = {c["title"] for c in clusters}
        assert titles == {"Config timeout", "Recovery timeout"}
        assert all(c["frequency"] == 1 for c in clusters)

    def test_unknown_issue_key_aborts(self, tmp_path):
        candidates = _write_candidates(tmp_path)
        confirmations = tmp_path / "confirmations.json"
        confirmations.write_text(json.dumps({
            "clusters": [{"title": "X", "issue_keys": ["org/missing#99"], "rationale": ""}]
        }))
        with pytest.raises(typer.Exit):
            pain_finalize(domain="agent", candidates=candidates,
                          confirmations=str(confirmations), output=str(tmp_path / "out.json"))

    def test_duplicate_issue_key_skipped(self, tmp_path):
        candidates = _write_candidates(tmp_path)
        confirmations = tmp_path / "confirmations.json"
        confirmations.write_text(json.dumps({
            "clusters": [
                {"title": "A", "issue_keys": ["org/a#1"], "rationale": ""},
                {"title": "B", "issue_keys": ["org/a#1"], "rationale": ""},
            ]
        }))
        output = str(tmp_path / "pain_clusters.json")
        pain_finalize(domain="agent", candidates=candidates,
                      confirmations=str(confirmations), output=output)
        clusters = json.loads(tmp_path.joinpath("pain_clusters.json").read_text())["payload"]["clusters"]
        # Only the first cluster holds the issue; the second is empty and dropped.
        assert len(clusters) == 1
