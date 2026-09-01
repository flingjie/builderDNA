"""Tests for the radar CLI command group (cli/commands/radar.py).

Deterministic-sandbox tests: no network, no LLM. We build a ``typer.Typer``
instance (``radar_app``) directly and drive it with ``typer.testing.CliRunner``.
All state lives in ``tmp_path`` — the real ``state/`` and ``output/`` dirs are
never touched. Config-loading tests point at a temp copy of a radar YAML.

Covered behaviours:

- versioned YAML config loading and validation,
- per-source coverage recording (complete / partial / unavailable / not_requested),
- partial source failure producing a usable partial run with explicit gaps
  (never silently substituting another source),
- daily_card_cap / weekly_build_cap enforcement with an ``--override`` escape hatch,
- JSON-first output: JSON written and re-validated before Markdown rendering,
- ``verify`` reporting the four build-gate requirements and what is missing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cli.commands.radar import (
    RadarConfigError,
    load_radar_config,
    radar_app,
)
from concepts.store import ConceptStore
from models.concept import (
    ConceptCard,
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    PortfolioStage,
    SmallestExperiment,
    SourceType,
)
from models.radar_payload import (
    RadarRunPayload,
    SourceStatus,
)


runner = CliRunner()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Fixtures ──

MINIMAL_RADAR = {
    "version": 1,
    "name": "agent-reliability",
    "description": "test radar",
    "neighborhoods": [
        {"id": "failure-modes", "label": "Failure modes", "focus": "how agents fail"},
    ],
    "exclusions": ["pure benchmarks"],
    "daily_card_cap": 3,
    "weekly_build_cap": 1,
    "reddit_communities": [
        {"subreddit": "ChatGPT", "role": "problem", "segment": "agent-users"},
        {"subreddit": "AI_Agents", "role": "solution", "segment": "agent-builders"},
    ],
}


@pytest.fixture
def config_dir(tmp_path):
    """A temp copy of a versioned radar YAML at <dir>/agent-reliability.yaml."""
    radar_dir = tmp_path / "config" / "radars"
    radar_dir.mkdir(parents=True)
    (radar_dir / "agent-reliability.yaml").write_text(
        yaml.safe_dump(MINIMAL_RADAR, sort_keys=False), encoding="utf-8"
    )
    return str(radar_dir)


@pytest.fixture
def store(tmp_path):
    return ConceptStore(state_dir=tmp_path / "state")


def make_card(**overrides) -> ConceptCard:
    fields = dict(id="c1", title="Agent Reliability")
    fields.update(overrides)
    return ConceptCard(**fields)


def make_evidence(**overrides) -> ConceptEvidence:
    fields = dict(
        id="ev1",
        concept_id="c1",
        source_type=SourceType.GITHUB,
        source_url="https://github.com/example/repo",
        role=EvidenceRole.IMPLEMENTATION,
        directness=Directness.DIRECT,
        strength=EvidenceStrength.STRONG,
        independence_key="chain-a",
    )
    fields.update(overrides)
    return ConceptEvidence(**fields)


def make_smallest_experiment() -> SmallestExperiment:
    return SmallestExperiment(
        hypothesis="guardrails prevent agent loops",
        target="production agent runs",
        artifact="a stop-condition harness",
        success_threshold="loops terminate within budget",
        failure_threshold="loops continue past budget",
        stop_condition="100 runs or 2 hours",
    )


def run_radar(*args):
    return runner.invoke(radar_app, list(args))


def read_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_payload_model(path: Path) -> RadarRunPayload:
    return RadarRunPayload.model_validate_json(path.read_text(encoding="utf-8"))


# ── Config loading ──

class TestRadarConfigLoading:
    def test_load_roundtrip(self, config_dir):
        cfg = load_radar_config("agent-reliability", config_dir)
        assert cfg.name == "agent-reliability"
        assert cfg.version == 1
        assert cfg.daily_card_cap == 3
        assert cfg.weekly_build_cap == 1
        assert len(cfg.neighborhoods) == 1
        assert {c.role for c in cfg.reddit_communities} == {"problem", "solution"}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(RadarConfigError):
            load_radar_config("nope", tmp_path)

    def test_name_mismatch_raises(self, tmp_path):
        radar_dir = tmp_path / "radars"
        radar_dir.mkdir()
        (radar_dir / "agent-reliability.yaml").write_text(
            yaml.safe_dump({**MINIMAL_RADAR, "name": "other-radar"}),
            encoding="utf-8",
        )
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir)

    def test_missing_version_is_invalid(self, tmp_path):
        radar_dir = tmp_path / "radars"
        radar_dir.mkdir()
        cfg = {k: v for k, v in MINIMAL_RADAR.items() if k != "version"}
        (radar_dir / "agent-reliability.yaml").write_text(
            yaml.safe_dump(cfg), encoding="utf-8"
        )
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            load_radar_config("agent-reliability", radar_dir)


# ── scan: source coverage recording ──

class TestScanSourceCoverage:
    def test_empty_store_marks_all_sources_unavailable(self, config_dir, tmp_path):
        out_json = tmp_path / "scan.json"
        result = run_radar(
            "scan", "agent-reliability",
            "--state-dir", str(tmp_path / "state"),
            "--output", str(out_json),
            "--config-dir", config_dir,
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        assert {s.source_type for s in payload.sources} == set(SourceType)
        assert all(s.status == SourceStatus.UNAVAILABLE for s in payload.sources)
        assert payload.cards_affected == []
        # explicit gaps recorded, one per unavailable source
        assert len(payload.gaps) == len(payload.sources)

    def test_complete_partial_and_unavailable_are_distinguished(self, config_dir, store, tmp_path):
        # complete: github evidence, no gaps
        store.add_evidence(make_evidence(id="g1", source_type=SourceType.GITHUB, note="repo code"))
        # partial: reddit RSS evidence (comments not read)
        store.add_evidence(make_evidence(id="r1", source_type=SourceType.REDDIT, note="post body"))
        # partial via explicit gap marker: manual note with missing URL
        store.add_evidence(make_evidence(
            id="m1", source_type=SourceType.MANUAL,
            note="my inference [coverage gap: source URL unknown]",
        ))

        out_json = tmp_path / "scan.json"
        result = run_radar(
            "scan", "agent-reliability",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        by_source = {s.source_type: s for s in payload.sources}
        assert by_source[SourceType.GITHUB].status == SourceStatus.COMPLETE
        assert by_source[SourceType.REDDIT].status == SourceStatus.PARTIAL
        assert "comments not read" in by_source[SourceType.REDDIT].note
        assert by_source[SourceType.MANUAL].status == SourceStatus.PARTIAL
        assert "coverage gap" in by_source[SourceType.MANUAL].note
        assert by_source[SourceType.X].status == SourceStatus.UNAVAILABLE
        assert by_source[SourceType.PAPER].status == SourceStatus.UNAVAILABLE
        assert by_source[SourceType.OFFICIAL_DOC].status == SourceStatus.UNAVAILABLE

    def test_not_requested_via_sources_flag(self, config_dir, store, tmp_path):
        store.add_evidence(make_evidence(id="g1", source_type=SourceType.GITHUB))
        out_json = tmp_path / "scan.json"
        result = run_radar(
            "scan", "agent-reliability",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
            "--sources", "github",
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        by_source = {s.source_type: s for s in payload.sources}
        assert by_source[SourceType.GITHUB].status == SourceStatus.COMPLETE
        for source_type in (SourceType.X, SourceType.REDDIT, SourceType.PAPER,
                            SourceType.OFFICIAL_DOC, SourceType.MANUAL):
            assert by_source[source_type].status == SourceStatus.NOT_REQUESTED

    def test_invalid_sources_flag_exits_nonzero(self, config_dir, store, tmp_path):
        out_json = tmp_path / "scan.json"
        result = run_radar(
            "scan", "agent-reliability",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
            "--sources", "github,not-a-source",
        )
        assert result.exit_code != 0
        assert "unknown source type" in result.output


# ── scan: partial failure is usable and never substitutes ──

class TestScanPartialFailure:
    def test_unavailable_source_never_substituted(self, config_dir, store, tmp_path):
        # Only github evidence is present; reddit must be unavailable, not
        # "filled in" by github data.
        store.add_evidence(make_evidence(id="g1", source_type=SourceType.GITHUB, note="code"))
        out_json = tmp_path / "scan.json"
        result = run_radar(
            "scan", "agent-reliability",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        by_source = {s.source_type: s for s in payload.sources}
        assert by_source[SourceType.GITHUB].status == SourceStatus.COMPLETE
        assert by_source[SourceType.REDDIT].status == SourceStatus.UNAVAILABLE
        assert "unavailable" in by_source[SourceType.REDDIT].note
        assert any("reddit" in g for g in payload.gaps)

    def test_partial_run_has_explicit_gaps(self, config_dir, store, tmp_path):
        store.add_evidence(make_evidence(id="g1", source_type=SourceType.GITHUB, note="code"))
        out_json = tmp_path / "scan.json"
        result = run_radar(
            "scan", "agent-reliability",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        unavailable = [s for s in payload.sources if s.status == SourceStatus.UNAVAILABLE]
        assert len(unavailable) == 5  # everything except github
        assert len(payload.gaps) == 5


# ── scan: daily cap enforcement ──

class TestScanDailyCap:
    def _store_with_cards(self, store, n):
        for i in range(1, n + 1):
            store.add_evidence(make_evidence(
                id=f"g{i}", concept_id=f"c{i}",
                source_type=SourceType.GITHUB,
                independence_key=f"chain-{i}",
            ))

    def test_daily_cap_enforced_by_default(self, config_dir, store, tmp_path):
        self._store_with_cards(store, 5)
        out_json = tmp_path / "scan.json"
        result = run_radar(
            "scan", "agent-reliability",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        assert len(payload.cards_affected) == 3
        assert any("daily_card_cap=3" in g for g in payload.gaps)

    def test_daily_cap_bypassed_with_override(self, config_dir, store, tmp_path):
        self._store_with_cards(store, 5)
        out_json = tmp_path / "scan.json"
        result = run_radar(
            "scan", "agent-reliability",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
            "--override",
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        assert len(payload.cards_affected) == 5
        assert not any("daily_card_cap" in g for g in payload.gaps)


# ── scan: JSON-first + Markdown rendering ──

class TestScanOutput:
    def test_writes_json_first_then_markdown(self, config_dir, store, tmp_path):
        store.add_evidence(make_evidence(id="g1", source_type=SourceType.GITHUB, note="code"))
        out_json = tmp_path / "scan.json"
        result = run_radar(
            "scan", "agent-reliability",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
        )
        assert result.exit_code == 0, result.output
        assert out_json.exists()
        md_path = out_json.with_suffix(".md")
        assert md_path.exists()

        # The JSON is the canonical artifact and validates as RadarRunPayload.
        payload = read_payload_model(out_json)
        assert payload.radar == "agent-reliability"

        md = md_path.read_text(encoding="utf-8")
        assert "Source coverage" in md
        assert "github" in md


# ── verify ──

class TestVerify:
    def test_verify_reports_passed_gate(self, store, tmp_path):
        card = make_card(
            id="c-pass", title="Passing card", stage=PortfolioStage.VERIFY,
            smallest_experiment=make_smallest_experiment(),
        )
        store.upsert_concept(card)
        store.add_evidence(make_evidence(
            id="g1", concept_id="c-pass", source_type=SourceType.GITHUB,
            role=EvidenceRole.IMPLEMENTATION, independence_key="chain-a",
        ))
        store.add_evidence(make_evidence(
            id="r1", concept_id="c-pass", source_type=SourceType.REDDIT,
            role=EvidenceRole.PROBLEM, independence_key="chain-b",
        ))
        out_json = tmp_path / "verify.json"
        result = run_radar(
            "verify", "c-pass",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 0, result.output
        payload = read_payload(out_json)
        assert payload["passed"] is True
        assert payload["missing"] == []
        assert len(payload["requirements"]) == 6
        assert all(r["met"] for r in payload["requirements"])

    def test_verify_reports_missing_requirements(self, store, tmp_path):
        card = make_card(id="c-fail", title="Failing card", stage=PortfolioStage.VERIFY)
        store.upsert_concept(card)
        out_json = tmp_path / "verify.json"
        result = run_radar(
            "verify", "c-fail",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 0, result.output
        payload = read_payload(out_json)
        assert payload["passed"] is False
        assert len(payload["requirements"]) == 6
        missing = payload["missing"]
        assert "two_source_types" in missing
        assert "two_independent_chains" in missing
        assert "smallest_experiment_present" in missing
        assert "experiment_thresholds_and_budget" in missing

    def test_verify_missing_concept_exits_nonzero(self, store, tmp_path):
        out_json = tmp_path / "verify.json"
        result = run_radar(
            "verify", "nope",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_verify_writes_markdown(self, store, tmp_path):
        card = make_card(id="c1", title="Card")
        store.upsert_concept(card)
        out_json = tmp_path / "verify.json"
        result = run_radar(
            "verify", "c1",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 0, result.output
        md = out_json.with_suffix(".md").read_text(encoding="utf-8")
        assert "Build-gate verification" in md
        assert "Requirements" in md


# ── verify --handoff ──

def _write_handoff(tmp_path, *, name="github_handoff.json", items=None):
    """Write a verification handoff JSON file into ``tmp_path``."""
    envelope = {
        "schema_version": 1,
        "source_phase": "verify",
        "coverage": "complete",
        "coverage_notes": [],
        "items": items
        if items is not None
        else [
            {
                "source": "github",
                "role": "adoption",
                "author": "external_user",
                "url": "https://github.com/exampleorg/example-repo/issues/42",
                "published_at": "2026-08-26T15:00:00Z",
                "excerpt": (
                    "An external user filed an issue that the agent produced a "
                    "plausible but incorrect SQL migration."
                ),
                "directness": "direct",
                "strength": "moderate",
                "upstream_origin": None,
                "independence_key": "github:exampleorg/example-repo:actor:external_user",
                "topics": ["agent-reliability"],
                "proposed_concept": None,
            }
        ],
    }
    path = tmp_path / name
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return path


class TestVerifyHandoff:
    def test_handoff_imports_evidence_and_reports_six_gates(self, store, tmp_path):
        card = make_card(
            id="c-pass", title="Passing card", stage=PortfolioStage.VERIFY,
            smallest_experiment=make_smallest_experiment(),
        )
        store.upsert_concept(card)
        store.add_evidence(make_evidence(
            id="r1", concept_id="c-pass", source_type=SourceType.REDDIT,
            role=EvidenceRole.PROBLEM, independence_key="chain-b",
        ))
        handoff = _write_handoff(tmp_path)
        out_json = tmp_path / "verify.json"
        result = run_radar(
            "verify", "c-pass",
            "--handoff", str(handoff),
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 0, result.output
        payload = read_payload(out_json)
        assert payload["handoff"]["imported"] == 1
        assert payload["handoff"]["attached_evidence_ids"]
        # six gates, all passed: github + reddit, two chains, experiment present
        assert len(payload["requirements"]) == 6
        assert all(r["met"] for r in payload["requirements"])
        assert payload["passed"] is True
        assert payload["missing"] == []
        # the imported github evidence is now attached to the concept in the store
        attached = [
            e for e in store.list_evidence("c-pass")
            if e.source_type == SourceType.GITHUB
        ]
        assert attached

    def test_handoff_missing_file_exits_nonzero(self, store, tmp_path):
        card = make_card(id="c1", title="Card")
        store.upsert_concept(card)
        out_json = tmp_path / "verify.json"
        result = run_radar(
            "verify", "c1",
            "--handoff", str(tmp_path / "nope.json"),
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_handoff_invalid_envelope_exits_nonzero(self, store, tmp_path):
        card = make_card(id="c1", title="Card")
        store.upsert_concept(card)
        # A direct github item with no url/upstream_origin is structurally invalid,
        # so the whole handoff is rejected with no partial import.
        handoff = _write_handoff(tmp_path, items=[
            {
                "source": "github",
                "role": "problem",
                "excerpt": "a claim",
                "directness": "direct",
                "strength": "moderate",
                "url": "",
                "upstream_origin": None,
            }
        ])
        out_json = tmp_path / "verify.json"
        result = run_radar(
            "verify", "c1",
            "--handoff", str(handoff),
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 1


# ── experiment ──

EXPERIMENT_SIMULATION = dict(
    failure_mode="the agent silently skips a post-run cleanup step",
    environment="a sandboxed shell with a persistent working directory",
    agent_goal="complete the assigned task and exit cleanly",
    hidden_constraints=["the working directory must be empty on exit"],
    counterexample="a naive agent reports success while intermediate files remain",
    replay_reset="reset the working directory to a fixed seed state before each run",
)


class TestExperiment:
    def _add_buildable_card(self, store):
        card = make_card(
            id="c1", title="Agent Reliability",
            problem="operators lose time to uncaught failures",
            evidence_ids=["ev1", "ev2"],
            smallest_experiment=make_smallest_experiment(),
        )
        store.upsert_concept(card)
        store.add_evidence(make_evidence(
            id="ev1", concept_id="c1", source_type=SourceType.GITHUB,
            role=EvidenceRole.IMPLEMENTATION, independence_key="chain-a",
            note="UNVERIFIABLE TRANSCRIPT: the agent skipped cleanup at 03:12 UTC",
        ))
        store.add_evidence(make_evidence(
            id="ev2", concept_id="c1", source_type=SourceType.REDDIT,
            role=EvidenceRole.PROBLEM, independence_key="chain-b",
        ))
        return card

    def test_experiment_produces_proposal_with_linked_evidence(self, store, tmp_path):
        self._add_buildable_card(store)
        out_json = tmp_path / "experiment.json"
        result = run_radar(
            "experiment", "c1",
            "--format", "fde-gym",
            "--budget", "4 hours",
            "--failure-mode", EXPERIMENT_SIMULATION["failure_mode"],
            "--environment", EXPERIMENT_SIMULATION["environment"],
            "--agent-goal", EXPERIMENT_SIMULATION["agent_goal"],
            "--hidden-constraint", EXPERIMENT_SIMULATION["hidden_constraints"][0],
            "--counterexample", EXPERIMENT_SIMULATION["counterexample"],
            "--replay-reset", EXPERIMENT_SIMULATION["replay_reset"],
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 0, result.output
        payload = read_payload(out_json)
        assert payload["concept_id"] == "c1"
        assert payload["evidence_ids"] == ["ev1", "ev2"]
        # evidence is linked, not copied: unverifiable prose never leaks into the export
        assert "UNVERIFIABLE TRANSCRIPT" not in out_json.read_text(encoding="utf-8")

    def test_experiment_rejects_without_smallest_experiment(self, store, tmp_path):
        card = make_card(id="c1", title="Card", evidence_ids=["ev1"])
        store.upsert_concept(card)
        store.add_evidence(make_evidence(id="ev1", concept_id="c1"))
        out_json = tmp_path / "experiment.json"
        result = run_radar(
            "experiment", "c1",
            "--budget", "4 hours",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 1
        assert "Build-gated" in result.output
        assert not out_json.exists()

    def test_experiment_rejects_identical_thresholds(self, store, tmp_path):
        experiment = make_smallest_experiment().model_copy(
            update={"success_threshold": "same", "failure_threshold": "same"}
        )
        card = make_card(id="c1", title="Card", smallest_experiment=experiment)
        store.upsert_concept(card)
        out_json = tmp_path / "experiment.json"
        result = run_radar(
            "experiment", "c1",
            "--budget", "4 hours",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 1
        assert "distinct" in result.output or "falsifiable" in result.output

    def test_experiment_rejects_missing_budget(self, store, tmp_path):
        card = make_card(
            id="c1", title="Card", smallest_experiment=make_smallest_experiment()
        )
        store.upsert_concept(card)
        out_json = tmp_path / "experiment.json"
        result = run_radar(
            "experiment", "c1",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 1
        assert "budget" in result.output

    def test_experiment_missing_concept_exits_nonzero(self, store, tmp_path):
        out_json = tmp_path / "experiment.json"
        result = run_radar(
            "experiment", "nope",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
        )
        assert result.exit_code == 1
        assert "not found" in result.output


# ── review ──

def _add_eligible_card(store, concept_id, *, github_key, reddit_key):
    """Add a VERIFY-stage card whose evidence passes the build gate."""
    card = make_card(
        id=concept_id, title=concept_id, stage=PortfolioStage.VERIFY,
        smallest_experiment=make_smallest_experiment(),
    )
    store.upsert_concept(card)
    store.add_evidence(make_evidence(
        id=f"{concept_id}-g", concept_id=concept_id, source_type=SourceType.GITHUB,
        role=EvidenceRole.IMPLEMENTATION, independence_key=github_key,
    ))
    store.add_evidence(make_evidence(
        id=f"{concept_id}-r", concept_id=concept_id, source_type=SourceType.REDDIT,
        role=EvidenceRole.PROBLEM, independence_key=reddit_key,
    ))


class TestReview:
    def test_review_promotes_eligible_and_records_period(self, config_dir, store, tmp_path):
        _add_eligible_card(store, "c-a", github_key="chain-a", reddit_key="chain-a2")
        _add_eligible_card(store, "c-b", github_key="chain-b", reddit_key="chain-b2")
        out_json = tmp_path / "review.json"
        result = run_radar(
            "review", "agent-reliability",
            "--period", "2026-W36",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        assert payload.period == "2026-W36"
        # weekly_build_cap=1 caps the promotions
        assert len(payload.cards_affected) == 1
        assert any("weekly_build_cap=1" in g for g in payload.gaps)
        assert payload.sources, "review records per-source coverage"

    def test_review_override_bypasses_weekly_cap(self, config_dir, store, tmp_path):
        _add_eligible_card(store, "c-a", github_key="chain-a", reddit_key="chain-a2")
        _add_eligible_card(store, "c-b", github_key="chain-b", reddit_key="chain-b2")
        out_json = tmp_path / "review.json"
        result = run_radar(
            "review", "agent-reliability",
            "--period", "2026-W36",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
            "--override",
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        assert set(payload.cards_affected) == {"c-a", "c-b"}
        assert not any("weekly_build_cap" in g for g in payload.gaps)

    def test_review_skips_non_verify_cards(self, config_dir, store, tmp_path):
        # A Build-stage card is already built, not a promotion candidate.
        card = make_card(
            id="c-built", title="Built", stage=PortfolioStage.BUILD,
            smallest_experiment=make_smallest_experiment(),
        )
        store.upsert_concept(card)
        store.add_evidence(make_evidence(
            id="c-built-g", concept_id="c-built", source_type=SourceType.GITHUB,
            role=EvidenceRole.IMPLEMENTATION, independence_key="chain-a",
        ))
        store.add_evidence(make_evidence(
            id="c-built-r", concept_id="c-built", source_type=SourceType.REDDIT,
            role=EvidenceRole.PROBLEM, independence_key="chain-b",
        ))
        out_json = tmp_path / "review.json"
        result = run_radar(
            "review", "agent-reliability",
            "--period", "2026-W36",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        assert payload.cards_affected == []


# ── source-audit ──

class TestSourceAudit:
    def test_source_audit_lists_per_source_coverage(self, config_dir, store, tmp_path):
        store.add_evidence(make_evidence(id="g1", source_type=SourceType.GITHUB, note="code"))
        store.add_evidence(make_evidence(id="r1", source_type=SourceType.REDDIT, note="post"))
        out_json = tmp_path / "audit.json"
        result = run_radar(
            "source-audit", "agent-reliability",
            "--state-dir", str(store.state_dir),
            "--output", str(out_json),
            "--config-dir", config_dir,
        )
        assert result.exit_code == 0, result.output
        payload = read_payload_model(out_json)
        by_source = {s.source_type: s for s in payload.sources}
        assert by_source[SourceType.GITHUB].status == SourceStatus.COMPLETE
        assert by_source[SourceType.REDDIT].status == SourceStatus.PARTIAL
        assert by_source[SourceType.X].status == SourceStatus.UNAVAILABLE
        assert payload.cards_affected == []
        assert payload.summary
