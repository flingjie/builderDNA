"""CLI tests for the ``radar-cycle`` command group (Task 11).

These tests drive the ``radar-cycle`` Typer group through
``typer.testing.CliRunner`` against a locally-constructed app (never
``cli.main.app``) and a per-test ``tmp_path`` state dir. No network, no LLM.

Covered behaviours (the Task 11 acceptance list):

- ``start`` creates a checkpoint and returns the first ``NextAction`` (``validate``);
- ``import`` validates the current phase, imports the handoff atomically,
  advances to the next phase, and a duplicate import imports 0 records;
- ``resume`` re-checks the config fingerprint and returns the first incomplete
  phase without re-running completed phases;
- ``resume`` fails closed when the config fingerprint changed since ``start``;
- ``decide`` scores reviewed concepts, records the Build-decision count under
  ``checkpoint.counts[decide]``, and gates ``experiment``;
- ``finalize`` refuses while a required phase is blocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
import yaml
from typer.testing import CliRunner

from cli.commands.radar_cycle_cmd import radar_cycle
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
from radar_cycles import checkpoint
from radar_cycles.models import Mode, PhaseName

# ── Fixtures / helpers ──

VALID_RADAR = {
    "version": 1,
    "name": "agent-reliability",
    "description": "test radar",
    "neighborhoods": [
        {"id": "n1", "label": "One", "focus": "first"},
        {"id": "n2", "label": "Two", "focus": "second"},
        {"id": "n3", "label": "Three", "focus": "third"},
    ],
    "daily_card_cap": 3,
    "weekly_build_cap": 1,
}


def make_app() -> typer.Typer:
    app = typer.Typer()
    app.add_typer(radar_cycle, name="radar-cycle")
    return app


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def config_dirs(tmp_path):
    """Write a valid radar config and an empty reddit preset dir under tmp_path."""
    radar_dir = tmp_path / "config" / "radars"
    radar_dir.mkdir(parents=True)
    (radar_dir / "agent-reliability.yaml").write_text(
        yaml.safe_dump(VALID_RADAR, sort_keys=False), encoding="utf-8"
    )
    reddit_dir = tmp_path / "config" / "reddit_feeds"
    reddit_dir.mkdir(parents=True)
    return str(radar_dir), str(reddit_dir)


def invoke(app, runner, tmp_path, config_dirs, *args):
    radar_dir, reddit_dir = config_dirs
    full = [
        "radar-cycle",
        *args,
        "--state-dir", str(tmp_path),
        "--config-dir", radar_dir,
        "--reddit-dir", reddit_dir,
    ]
    return runner.invoke(app, full)


def load(result):
    return json.loads(result.stdout)


def start_run(app, runner, tmp_path, config_dirs, mode="weekly"):
    result = invoke(
        app, runner, tmp_path, config_dirs,
        "start", "--radar", "agent-reliability", "--mode", mode, "--json",
    )
    assert result.exit_code == 0, result.output
    return load(result)


def checkpoint_dir(tmp_path):
    return str(tmp_path / "radar_cycles")


def complete_phase(tmp_path, run_id, phase):
    """Drive a phase pending -> running -> completed via the checkpoint layer."""
    store_dir = checkpoint_dir(tmp_path)
    checkpoint.transition(run_id, phase, "running", store_dir=store_dir)
    checkpoint.transition(run_id, phase, "completed", store_dir=store_dir)


def block_phase(tmp_path, run_id, phase):
    """Drive a phase pending -> running -> blocked via the checkpoint layer."""
    store_dir = checkpoint_dir(tmp_path)
    checkpoint.transition(run_id, phase, "running", store_dir=store_dir)
    checkpoint.transition(run_id, phase, "blocked", store_dir=store_dir)


def x_handoff() -> dict:
    return {
        "schema_version": 1,
        "source_phase": "x-discovery",
        "coverage": "partial",
        "coverage_notes": ["X thread replies unavailable"],
        "items": [
            {
                "source": "x",
                "role": "problem",
                "author": "alice_dev",
                "url": "https://x.com/alice_dev/status/1234567890",
                "excerpt": "Long-running agents silently drift from their stated goals.",
                "directness": "direct",
                "strength": "moderate",
                "proposed_concept": {
                    "title": "Agent goal-drift detector",
                    "problem": "Long-running agents silently drift from their stated goals",
                    "why_now": "More teams run agents for hours at a time",
                },
            }
        ],
    }


def write_handoff(tmp_path, name="x.json", **overrides):
    envelope = x_handoff()
    envelope.update(overrides)
    path = tmp_path / name
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return str(path)


# ── start ──


class TestStart:
    def test_start_returns_validate_action(self, app, runner, tmp_path, config_dirs):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        assert payload["ok"] is True
        assert payload["schema"] == "builderdna.radar-cycle.v1"
        assert payload["data"]["radar"] == "agent-reliability"
        assert payload["data"]["mode"] == "weekly"
        assert payload["data"]["next_action"]["phase"] == "validate"
        assert payload["data"]["next_action"]["required_handoff"] is None

        run_id = payload["data"]["run_id"]
        assert run_id
        # a checkpoint file now exists on disk
        assert (tmp_path / "radar_cycles" / f"{run_id}.json").exists()


# ── complete (local phases) ──


class TestComplete:
    def test_complete_advances_local_phase(self, app, runner, tmp_path, config_dirs):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        run_id = payload["data"]["run_id"]

        result = invoke(app, runner, tmp_path, config_dirs,
                        "complete", run_id, "validate", "--json")
        assert result.exit_code == 0, result.output
        data = load(result)["data"]
        assert data["phase"] == "validate"
        assert data["next_action"]["phase"] == "x-discovery"
        assert data["phase_status"]["validate"] == "completed"
        run = checkpoint.load(run_id, store_dir=checkpoint_dir(tmp_path))
        assert run.checkpoint.status_of(PhaseName.VALIDATE).value == "completed"

    def test_complete_rejects_source_phase(self, app, runner, tmp_path, config_dirs):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        run_id = payload["data"]["run_id"]
        complete_phase(tmp_path, run_id, "validate")

        result = invoke(app, runner, tmp_path, config_dirs,
                        "complete", run_id, "x-discovery", "--json")
        assert result.exit_code != 0
        body = load(result)
        assert body["ok"] is False
        assert "import" in body["error"].lower()


# ── import ──


class TestImport:
    def test_import_advances_to_next_phase(self, app, runner, tmp_path, config_dirs):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        run_id = payload["data"]["run_id"]
        complete_phase(tmp_path, run_id, "validate")

        path = write_handoff(tmp_path)
        result = invoke(app, runner, tmp_path, config_dirs,
                        "import", run_id, "x-discovery", "--file", path)
        assert result.exit_code == 0, result.output
        data = load(result)["data"]
        assert data["import"]["imported"] == 1
        assert data["next_action"]["phase"] == "reddit-scan"
        # the phase is now completed on disk
        run = checkpoint.load(run_id, store_dir=checkpoint_dir(tmp_path))
        assert run.checkpoint.status_of(PhaseName.X_DISCOVERY).value == "completed"
        # exactly one evidence record landed in the store
        store = ConceptStore(state_dir=tmp_path)
        assert len(store.list_evidence()) == 1

    def test_duplicate_import_imports_zero(self, app, runner, tmp_path, config_dirs):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        run_id = payload["data"]["run_id"]
        complete_phase(tmp_path, run_id, "validate")

        path = write_handoff(tmp_path)
        first = invoke(app, runner, tmp_path, config_dirs,
                       "import", run_id, "x-discovery", "--file", path)
        assert first.exit_code == 0
        assert load(first)["data"]["import"]["imported"] == 1

        second = invoke(app, runner, tmp_path, config_dirs,
                        "import", run_id, "x-discovery", "--file", path)
        assert second.exit_code == 0, second.output
        data = load(second)["data"]
        assert data["import"]["imported"] == 0
        # the next action is unchanged — no double advance
        assert data["next_action"]["phase"] == "reddit-scan"
        # no new evidence records were created
        store = ConceptStore(state_dir=tmp_path)
        assert len(store.list_evidence()) == 1

    def test_mismatched_phase_is_rejected(self, app, runner, tmp_path, config_dirs):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        run_id = payload["data"]["run_id"]
        complete_phase(tmp_path, run_id, "validate")

        path = write_handoff(tmp_path)
        # the current incomplete phase is x-discovery, not reddit-scan
        result = invoke(app, runner, tmp_path, config_dirs,
                        "import", run_id, "reddit-scan", "--file", path)
        assert result.exit_code != 0
        body = load(result)
        assert body["ok"] is False
        assert "mismatch" in body["error"].lower() or "current" in body["error"].lower()


# ── resume ──


class TestResume:
    def test_resume_returns_first_incomplete_phase(self, app, runner, tmp_path, config_dirs):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        run_id = payload["data"]["run_id"]
        complete_phase(tmp_path, run_id, "validate")
        complete_phase(tmp_path, run_id, "x-discovery")
        complete_phase(tmp_path, run_id, "reddit-scan")

        result = invoke(app, runner, tmp_path, config_dirs, "resume", run_id, "--json")
        assert result.exit_code == 0, result.output
        data = load(result)["data"]
        assert data["next_action"]["phase"] == "reduce"
        # completed phases were skipped, not re-run
        status = data["phase_status"]
        assert status["validate"] == "completed"
        assert status["x-discovery"] == "completed"
        assert status["reddit-scan"] == "completed"

    def test_resume_fails_on_changed_fingerprint(self, app, runner, tmp_path, config_dirs):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        run_id = payload["data"]["run_id"]

        # mutate the radar config after start
        radar_dir, _ = config_dirs
        changed = {**VALID_RADAR, "description": "changed description"}
        (Path(radar_dir) / "agent-reliability.yaml").write_text(
            yaml.safe_dump(changed, sort_keys=False), encoding="utf-8"
        )

        result = invoke(app, runner, tmp_path, config_dirs, "resume", run_id, "--json")
        assert result.exit_code != 0
        body = load(result)
        assert body["ok"] is False
        assert "fingerprint" in body["error"].lower()


# ── decide ──


def seed_build_eligible_card(tmp_path):
    """Seed a VERIFY-stage card whose evidence passes all six build gates."""
    store = ConceptStore(state_dir=tmp_path)
    store.upsert_concept(
        ConceptCard(
            id="agent-goal-drift-detector",
            title="Agent goal-drift detector",
            stage=PortfolioStage.VERIFY,
            smallest_experiment=SmallestExperiment(
                hypothesis="drift is detectable from goal-trace deltas",
                target="long-running agents",
                artifact="a trace-diff probe",
                success_threshold="drift detected before failure in 80% of runs",
                failure_threshold="drift undetected before failure in most runs",
                stop_condition="50 runs or 1 hour",
            ),
        )
    )
    store.add_evidence(ConceptEvidence(
        id="e1", concept_id="agent-goal-drift-detector",
        source_type=SourceType.GITHUB, source_url="https://github.com/x/y",
        role=EvidenceRole.IMPLEMENTATION, directness=Directness.DIRECT,
        strength=EvidenceStrength.STRONG, independence_key="chain-a",
    ))
    store.add_evidence(ConceptEvidence(
        id="e2", concept_id="agent-goal-drift-detector",
        source_type=SourceType.REDDIT, source_url="https://reddit.com/r/x/1",
        role=EvidenceRole.PROBLEM, directness=Directness.DIRECT,
        strength=EvidenceStrength.MODERATE, independence_key="chain-b",
    ))


def seed_verify_card_without_experiment(tmp_path):
    """Seed a VERIFY-stage card whose evidence passes the decision gates but
    which has no smallest_experiment yet (the real-world decide input)."""
    store = ConceptStore(state_dir=tmp_path)
    store.upsert_concept(
        ConceptCard(
            id="agent-timeout-guard",
            title="Agent timeout guard",
            stage=PortfolioStage.VERIFY,
        )
    )
    store.add_evidence(ConceptEvidence(
        id="e1", concept_id="agent-timeout-guard",
        source_type=SourceType.GITHUB, source_url="https://github.com/x/y",
        role=EvidenceRole.IMPLEMENTATION, directness=Directness.DIRECT,
        strength=EvidenceStrength.STRONG, independence_key="chain-a",
    ))
    store.add_evidence(ConceptEvidence(
        id="e2", concept_id="agent-timeout-guard",
        source_type=SourceType.REDDIT, source_url="https://reddit.com/r/x/1",
        role=EvidenceRole.PROBLEM, directness=Directness.DIRECT,
        strength=EvidenceStrength.MODERATE, independence_key="chain-b",
    ))


class TestDecide:
    def test_decide_records_build_count_and_gates_experiment(
        self, app, runner, tmp_path, config_dirs
    ):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        run_id = payload["data"]["run_id"]
        for phase in ("validate", "x-discovery", "reddit-scan", "reduce", "verify"):
            complete_phase(tmp_path, run_id, phase)

        seed_build_eligible_card(tmp_path)

        result = invoke(app, runner, tmp_path, config_dirs, "decide", run_id, "--json")
        assert result.exit_code == 0, result.output
        data = load(result)["data"]
        assert data["build_decisions"] == 1
        # the engine now requires experiment because one Build passed
        assert data["next_action"]["phase"] == "experiment"
        # the count is persisted on the checkpoint (the contract the engine reads)
        run = checkpoint.load(run_id, store_dir=checkpoint_dir(tmp_path))
        assert run.checkpoint.counts[PhaseName.DECIDE] == 1
        assert run.checkpoint.status_of(PhaseName.DECIDE).value == "completed"

    def test_decide_promotes_card_without_experiment(self, app, runner, tmp_path, config_dirs):
        """decide uses decision gates (evidence), not the experiment gates, and
        promotes a build-worthy VERIFY card to BUILD even when it has no
        smallest_experiment yet (attaching a draft)."""
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        run_id = payload["data"]["run_id"]
        for phase in ("validate", "x-discovery", "reddit-scan", "reduce", "verify"):
            complete_phase(tmp_path, run_id, phase)

        seed_verify_card_without_experiment(tmp_path)

        result = invoke(app, runner, tmp_path, config_dirs, "decide", run_id, "--json")
        assert result.exit_code == 0, result.output
        data = load(result)["data"]
        assert data["build_decisions"] == 1
        assert data["decisions"][0]["promoted"] is True
        # the card was promoted to BUILD with a smallest_experiment attached
        card = ConceptStore(state_dir=tmp_path).get_concept("agent-timeout-guard")
        assert card.stage == PortfolioStage.BUILD
        assert card.smallest_experiment is not None
        assert data["next_action"]["phase"] == "experiment"

    def test_decide_fails_on_changed_fingerprint(self, app, runner, tmp_path, config_dirs):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
        run_id = payload["data"]["run_id"]
        for phase in ("validate", "x-discovery", "reddit-scan", "reduce", "verify"):
            complete_phase(tmp_path, run_id, phase)
        seed_verify_card_without_experiment(tmp_path)

        radar_dir, _ = config_dirs
        changed = {**VALID_RADAR, "description": "changed after start"}
        (Path(radar_dir) / "agent-reliability.yaml").write_text(
            yaml.safe_dump(changed, sort_keys=False), encoding="utf-8"
        )

        result = invoke(app, runner, tmp_path, config_dirs, "decide", run_id, "--json")
        assert result.exit_code != 0
        assert "fingerprint" in load(result)["error"].lower()


# ── finalize ──


class TestFinalize:
    def test_finalize_refuses_while_a_phase_is_blocked(
        self, app, runner, tmp_path, config_dirs
    ):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="daily")
        run_id = payload["data"]["run_id"]
        complete_phase(tmp_path, run_id, "validate")
        block_phase(tmp_path, run_id, "x-discovery")

        result = invoke(app, runner, tmp_path, config_dirs, "finalize", run_id, "--json")
        assert result.exit_code != 0
        body = load(result)
        assert body["ok"] is False
        assert "blocked" in body["error"].lower()
        # the run must remain un-finalized
        assert checkpoint.run_status_of(run_id, store_dir=checkpoint_dir(tmp_path)) == "running"

    def test_finalize_writes_report_and_finishes(self, app, runner, tmp_path, config_dirs):
        payload = start_run(app, runner, tmp_path, config_dirs, mode="daily")
        run_id = payload["data"]["run_id"]
        for phase in ("validate", "x-discovery", "reddit-scan", "reduce"):
            complete_phase(tmp_path, run_id, phase)

        out_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "radar-cycle", "finalize", run_id, "--json",
                "--state-dir", str(tmp_path),
                "--config-dir", config_dirs[0],
                "--reddit-dir", config_dirs[1],
                "--out-dir", str(out_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        body = load(result)
        assert body["ok"] is True
        assert body["action"] == "finalized"
        assert body["data"]["run_status"] == "completed"
        # the report files were written
        assert (out_dir / f"{run_id}.json").exists()
        assert (out_dir / f"{run_id}.md").exists()
        # the run is persisted as finished
        assert checkpoint.run_status_of(run_id, store_dir=checkpoint_dir(tmp_path)) == "completed"
        run = checkpoint.load(run_id, store_dir=checkpoint_dir(tmp_path))
        assert run.checkpoint.status_of(PhaseName.REPORT).value == "completed"
