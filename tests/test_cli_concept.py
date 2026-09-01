"""CLI tests for the concept command group (Task 2.1).

These tests exercise the ``concept`` Typer group through
``typer.testing.CliRunner`` against a locally-constructed app (never
``cli.main.app``) and a per-test ``tmp_path`` store (never the real ``state/``
directory). A few direct unit tests of the core helpers (``capture``,
``slugify``, ``derive_title``) round out coverage.

Assertions target the JSON-first contract: stdout is a versioned JSON payload,
``action`` distinguishes created / merged / already_captured, and every
mutation is described in ``changed``.
"""

import json
from datetime import datetime, timezone

import pytest
import typer
from typer.testing import CliRunner

from cli.commands.concept import (
    concept as concept_group,
    capture,
    derive_title,
    slugify,
)
from concepts.store import ConceptStore
from models.concept import (
    ConceptCard,
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    PortfolioStage,
    SourceType,
)


def make_app() -> typer.Typer:
    app = typer.Typer()
    app.add_typer(concept_group, name="concept")
    return app


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def store(tmp_path):
    return ConceptStore(state_dir=tmp_path)


def invoke(app, runner, tmp_path, subcommand, *args, input=None):
    full = ["concept", subcommand, "--state-dir", str(tmp_path), *args]
    return runner.invoke(app, full, input=input)


def load(result):
    return json.loads(result.stdout)


# ── capture ──


class TestCapture:
    def test_creates_new_card(self, app, runner, tmp_path):
        result = invoke(
            app, runner, tmp_path, "capture",
            "--note", "Agents lose state in production.",
            "--title", "Agent Reliability",
        )
        assert result.exit_code == 0, result.stdout
        payload = load(result)
        assert payload["schema"] == "builderdna.concept.v1"
        assert payload["ok"] is True
        assert payload["action"] == "created"
        assert payload["data"]["concept"]["id"] == "agent-reliability"
        assert "concept created" in payload["changed"]
        assert "evidence appended" in payload["changed"]
        # store now has exactly one card and one evidence record
        s = ConceptStore(state_dir=tmp_path)
        assert len(s.list_concepts()) == 1
        assert len(s.list_evidence()) == 1

    def test_idempotent_by_url(self, app, runner, tmp_path):
        args = ["--url", "https://x.com/u/status/1", "--note", "Agents flake.", "--title", "Agent Reliability"]
        first = invoke(app, runner, tmp_path, "capture", *args)
        second = invoke(app, runner, tmp_path, "capture", *args)
        assert first.exit_code == 0
        assert second.exit_code == 0
        assert load(first)["action"] == "created"
        assert load(second)["action"] == "already_captured"
        s = ConceptStore(state_dir=tmp_path)
        assert len(s.list_concepts()) == 1
        assert len(s.list_evidence()) == 1  # no duplicate evidence

    def test_merges_on_name_match(self, app, runner, tmp_path):
        first = invoke(app, runner, tmp_path, "capture", "--title", "Agent Reliability", "--note", "a", "--problem", "same problem")
        second = invoke(app, runner, tmp_path, "capture", "--title", "Agent Reliability", "--note", "b", "--problem", "same problem")
        assert first.exit_code == 0
        assert second.exit_code == 0
        assert load(first)["action"] == "created"
        second_payload = load(second)
        assert second_payload["action"] == "merged"
        assert second_payload["data"]["merged_into"] == "agent-reliability"
        s = ConceptStore(state_dir=tmp_path)
        assert len(s.list_concepts()) == 1
        assert len(s.list_evidence()) == 2  # two notes, two evidence records

    def test_ambiguous_requires_disambiguation(self, app, runner, tmp_path):
        # Seed an existing card with the same title but a different problem.
        s = ConceptStore(state_dir=tmp_path)
        s.upsert_concept(ConceptCard(id="existing", title="Agent Reliability", problem="hallucinations in production"))

        result = invoke(
            app, runner, tmp_path, "capture",
            "--title", "Agent Reliability",
            "--problem", "exceeding latency budgets",
            "--note", "latency",
        )
        assert result.exit_code == 1
        payload = load(result)
        assert payload["ok"] is False
        assert "ambiguous" in payload["error"]
        # nothing new was created
        assert len(s.list_concepts()) == 1

        # disambiguate with --into
        resolved = invoke(
            app, runner, tmp_path, "capture",
            "--title", "Agent Reliability",
            "--problem", "exceeding latency budgets",
            "--note", "latency",
            "--into", "existing",
        )
        assert resolved.exit_code == 0
        assert load(resolved)["action"] == "merged"
        assert load(resolved)["data"]["merged_into"] == "existing"

    def test_stdin_structured_import(self, app, runner, tmp_path):
        capture_obj = {
            "source": "x",
            "url": "https://x.com/u/status/7",
            "note": "Quoting: \"agents still fail\"",
            "title": "Stdin Concept",
            "aliases": ["Old Name"],
        }
        result = invoke(
            app, runner, tmp_path, "capture", "--stdin",
            input=json.dumps(capture_obj),
        )
        assert result.exit_code == 0, result.stdout
        payload = load(result)
        assert payload["action"] == "created"
        assert payload["data"]["concept"]["id"] == "stdin-concept"
        assert payload["data"]["concept"]["aliases"] == ["Old Name"]

    def test_markdown_format(self, app, runner, tmp_path):
        result = invoke(
            app, runner, tmp_path, "capture",
            "--title", "Agent Reliability", "--note", "n",
            "--format", "md",
        )
        assert result.exit_code == 0
        assert "## concept.capture" in result.stdout
        assert "agent-reliability" in result.stdout


# ── list / show ──


class TestListShow:
    def test_list_all_and_filter_by_stage(self, app, runner, tmp_path):
        invoke(app, runner, tmp_path, "capture", "--title", "Alpha", "--note", "a")
        invoke(app, runner, tmp_path, "capture", "--title", "Beta", "--note", "b")
        # move Beta to watch
        s = ConceptStore(state_dir=tmp_path)
        beta = s.get_concept("beta")
        s.upsert_concept(beta.model_copy(update={"stage": PortfolioStage.WATCH}))

        all_result = invoke(app, runner, tmp_path, "list")
        assert load(all_result)["data"]["count"] == 2

        watch_result = invoke(app, runner, tmp_path, "list", "--stage", "watch")
        payload = load(watch_result)
        assert payload["data"]["count"] == 1
        assert payload["data"]["cards"][0]["id"] == "beta"

    def test_show_returns_card_evidence_reviews(self, app, runner, tmp_path):
        invoke(app, runner, tmp_path, "capture", "--title", "Agent Reliability", "--note", "n")
        result = invoke(app, runner, tmp_path, "show", "agent-reliability")
        assert result.exit_code == 0
        payload = load(result)
        assert payload["data"]["concept"]["id"] == "agent-reliability"
        assert len(payload["data"]["evidence"]) == 1
        assert isinstance(payload["data"]["reviews"], list)

    def test_show_missing_card_errors(self, app, runner, tmp_path):
        result = invoke(app, runner, tmp_path, "show", "nope")
        assert result.exit_code == 1
        assert load(result)["ok"] is False


# ── move ──


class TestMove:
    def test_move_to_build_requires_prediction_flags(self, app, runner, tmp_path):
        s = ConceptStore(state_dir=tmp_path)
        s.upsert_concept(ConceptCard(id="c1", title="C1", stage=PortfolioStage.VERIFY))
        result = invoke(app, runner, tmp_path, "move", "c1", "build", "--reason", "r")
        assert result.exit_code == 1
        error = load(result)["error"]
        assert "--prediction" in error
        assert "--expected-evidence" in error
        assert "--review-date" in error

    def test_move_to_build_gate_failure_lists_missing(self, app, runner, tmp_path):
        s = ConceptStore(state_dir=tmp_path)
        s.upsert_concept(ConceptCard(id="c1", title="C1", stage=PortfolioStage.VERIFY))
        experiment = json.dumps({
            "hypothesis": "h", "target": "t", "artifact": "a",
            "success_threshold": "s", "failure_threshold": "f",
            "stop_condition": "stop",
        })
        result = invoke(
            app, runner, tmp_path, "move", "c1", "build",
            "--reason", "r", "--prediction", "p", "--expected-evidence", "e",
            "--review-date", "2026-09-08T00:00:00Z",
            "--experiment", experiment,
        )
        assert result.exit_code == 1
        payload = load(result)
        assert payload["ok"] is False
        joined = " ".join(payload["details"]["missing"])
        assert "two source types" in joined
        assert "two independent supporting chains" in joined

    def test_move_to_watch_succeeds_and_writes_review(self, app, runner, tmp_path):
        invoke(app, runner, tmp_path, "capture", "--title", "Agent Reliability", "--note", "n")
        result = invoke(app, runner, tmp_path, "move", "agent-reliability", "watch", "--reason", "enough signal")
        assert result.exit_code == 0, result.stdout
        payload = load(result)
        assert payload["action"] == "moved"
        assert payload["data"]["concept"]["stage"] == "watch"
        assert payload["data"]["review"]["reason"] == "enough signal"
        s = ConceptStore(state_dir=tmp_path)
        assert s.get_concept("agent-reliability").stage == PortfolioStage.WATCH
        assert len(s.list_reviews("agent-reliability")) == 1

    def test_move_to_build_succeeds_with_gate_satisfied(self, app, runner, tmp_path):
        s = ConceptStore(state_dir=tmp_path)
        s.upsert_concept(ConceptCard(id="agent-reliability", title="Agent Reliability", stage=PortfolioStage.VERIFY))
        s.add_evidence(ConceptEvidence(
            id="e1", concept_id="agent-reliability", source_type=SourceType.GITHUB,
            source_url="https://github.com/x/y", role=EvidenceRole.IMPLEMENTATION,
            directness=Directness.DIRECT, strength=EvidenceStrength.STRONG,
            independence_key="gh-a",
        ))
        s.add_evidence(ConceptEvidence(
            id="e2", concept_id="agent-reliability", source_type=SourceType.REDDIT,
            source_url="https://reddit.com/r/x", role=EvidenceRole.PROBLEM,
            directness=Directness.DIRECT, strength=EvidenceStrength.MODERATE,
            independence_key="reddit-b",
        ))
        experiment = json.dumps({
            "hypothesis": "h", "target": "t", "artifact": "a",
            "success_threshold": "s", "failure_threshold": "f",
            "stop_condition": "stop",
        })
        result = invoke(
            app, runner, tmp_path, "move", "agent-reliability", "build",
            "--reason", "ready", "--prediction", "agents will fail 30% less",
            "--expected-evidence", "10-user pilot", "--review-date", "2026-09-08T00:00:00Z",
            "--experiment", experiment,
        )
        assert result.exit_code == 0, result.stdout
        payload = load(result)
        assert payload["data"]["concept"]["stage"] == "build"
        assert payload["data"]["concept"]["prediction"] == "agents will fail 30% less"
        s = ConceptStore(state_dir=tmp_path)
        assert s.get_concept("agent-reliability").prediction == "agents will fail 30% less"

    def test_move_same_stage_aborts(self, app, runner, tmp_path):
        invoke(app, runner, tmp_path, "capture", "--title", "Agent Reliability", "--note", "n")
        result = invoke(app, runner, tmp_path, "move", "agent-reliability", "inbox", "--reason", "r")
        assert result.exit_code == 1
        assert "already in stage" in load(result)["error"]


# ── merge ──


class TestMerge:
    def test_merge_preserves_aliases_and_repoints_evidence(self, app, runner, tmp_path):
        s = ConceptStore(state_dir=tmp_path)
        s.upsert_concept(ConceptCard(id="survivor", title="Agent Reliability", aliases=["Reliability"]))
        s.upsert_concept(ConceptCard(id="merged", title="Hallucination Guard", aliases=["Guard"]))
        s.add_evidence(ConceptEvidence(
            id="e1", concept_id="merged", source_type=SourceType.X,
            source_url="https://x.com/u/1", role=EvidenceRole.PROBLEM,
            directness=Directness.INFERRED, strength=EvidenceStrength.WEAK,
            independence_key="x-1",
        ))

        result = invoke(app, runner, tmp_path, "merge", "survivor", "merged")
        assert result.exit_code == 0, result.stdout
        payload = load(result)
        assert payload["action"] == "merged"
        survivor = payload["data"]["survivor"]
        # aliases are the union of both cards plus the merged-away title
        assert set(survivor["aliases"]) == {"Reliability", "Guard", "Hallucination Guard"}
        assert payload["data"]["repointed_evidence_ids"] == ["e1->survivor"]

        s2 = ConceptStore(state_dir=tmp_path)
        # surviving card now carries the re-pointed evidence id
        assert "e1->survivor" in s2.get_concept("survivor").evidence_ids
        # the re-pointed evidence record points back at the original (lineage)
        repointed = s2.get_evidence("e1->survivor")
        assert repointed.concept_id == "survivor"
        assert repointed.supersedes == "e1"
        # the merged-away card is dropped
        assert s2.get_concept("merged").stage == PortfolioStage.DROP

    def test_merge_missing_card_errors(self, app, runner, tmp_path):
        invoke(app, runner, tmp_path, "capture", "--title", "Agent Reliability", "--note", "n")
        result = invoke(app, runner, tmp_path, "merge", "agent-reliability", "nope")
        assert result.exit_code == 1
        assert load(result)["ok"] is False


# ── score ──


class TestScore:
    def test_score_returns_components_and_gate(self, app, runner, tmp_path):
        s = ConceptStore(state_dir=tmp_path)
        s.upsert_concept(ConceptCard(id="c1", title="C1", problem="agents fail in production"))
        s.add_evidence(ConceptEvidence(
            id="e1", concept_id="c1", source_type=SourceType.X,
            source_url="https://x.com/u/1", role=EvidenceRole.PROBLEM,
            directness=Directness.DIRECT, strength=EvidenceStrength.STRONG,
            independence_key="x-1", note="millions of users",
        ))
        result = invoke(app, runner, tmp_path, "score", "c1")
        assert result.exit_code == 0
        payload = load(result)
        data = payload["data"]
        assert set(data["scores"]) >= {"problem", "evidence", "reach", "user_alignment", "hype", "competition", "total"}
        assert set(data["reasons"]) == {"problem", "evidence", "reach", "user_alignment", "hype", "competition"}
        assert data["gate"]["passed"] is False
        assert any("two source types" in m for m in data["gate"]["missing"])


# ── direct unit tests of core helpers ──


class TestHelpers:
    def test_slugify(self):
        assert slugify("Agent Reliability!") == "agent-reliability"
        assert slugify("MCP-Servers") == "mcp-servers"

    def test_derive_title(self):
        assert derive_title("First line\nsecond line") == "First line"
        assert derive_title("   ") == ""

    def test_capture_core_idempotent(self, store):
        out1 = capture(store, source="x", url="https://x.com/u/1", note="n", title="T")
        out2 = capture(store, source="x", url="https://x.com/u/1", note="n", title="T")
        assert out1["action"] == "created"
        assert out2["action"] == "already_captured"
        assert len(store.list_concepts()) == 1
