"""Offline end-to-end tests for the resumable concept-radar loop (Task 15).

These tests drive the ``radar-cycle`` Typer group end-to-end against per-test
``tmp_path`` state/config directories, using only the fixture handoffs under
``tests/fixtures/radar/`` — no network, no LLM. They exercise the full
start -> import -> decide -> finalize state machine plus the interrupt/resume
idempotency guarantees, and the deterministic concept/scoring/matching layers
that the loop delegates to.

Scenario coverage (see the Task 15 plan):

1.  uninterrupted full run                    -> ``test_uninterrupted_full_run_produces_report``
2.  interruption after every phase + resume   -> ``test_interruption_after_every_phase_resumes_at_first_incomplete``
3.  X unavailable, Reddit/GitHub succeed      -> ``test_x_unavailable_reddit_github_succeed_with_explicit_gap``
4.  partial Reddit / absent comments          -> ``test_partial_reddit_feed_shows_absent_comments_gap``
5.  duplicate propagation chains collapse     -> ``test_duplicate_propagation_chains_collapse_to_one_independence_key``
6.  ambiguous merge preserves two cards       -> ``test_ambiguous_merge_preserves_two_cards``
7.  high-hype / high-alignment fails Build    -> ``test_high_alignment_and_hype_cannot_override_a_failed_gate``
8.  one Build + second blocked by weekly cap  -> ``test_one_build_and_second_blocked_by_weekly_limit``
9.  render failure then render-only resume    -> ``test_report_render_failure_followed_by_render_only_resume``
10. changed config fingerprint blocks resume  -> ``test_changed_config_fingerprint_blocks_resume``
11. duplicate handoff replay -> no records    -> ``test_duplicate_handoff_replay_produces_no_new_records``
12. monthly calibration preserves predictions -> ``test_monthly_calibration_preserves_original_predictions``

Acceptance invariant (asserted explicitly): an interrupted-then-resumed run
produces equivalent concept/evidence/review/decision state to an uninterrupted
run. This is asserted in
``test_interrupted_and_uninterrupted_runs_produce_equivalent_state`` by
comparing the persisted ``RadarCycleRun`` checkpoint documents (phase statuses,
counts, fingerprint, retry counts, outputs, coverage, run status) plus the full
concept store contents (concepts, evidence, reviews) after stripping the
write-only timestamps that legitimately differ between runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
import yaml
from typer.testing import CliRunner

import radar_cycles.rendering as rendering_module
from cli.commands.radar_cycle_cmd import radar_cycle
from concepts.handoffs import import_handoff, normalize_handoff
from concepts.scoring import GATE_TWO_SOURCE_TYPES, score as score_concept
from concepts.service import ConceptValidationError, capture, record_outcome
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
from radar_cycles.models import PhaseName

# ── Constants / fixtures ──

FIXTURES = Path(__file__).parent / "fixtures" / "radar"

BASE_RADAR = {
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

WEEKLY_PHASES = [
    "validate",
    "x-discovery",
    "reddit-scan",
    "reduce",
    "verify",
    "decide",
    "experiment",
    "calibration",
    "report",
]


# ── Fixtures ──


@pytest.fixture
def app():
    app = typer.Typer()
    app.add_typer(radar_cycle, name="radar-cycle")
    return app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def config_dirs(tmp_path):
    """Write a valid radar config (and an empty reddit preset dir) under tmp_path."""
    return write_radar_config(tmp_path)


# ── Helpers ──


def write_radar_config(tmp_path, radar=None):
    radar = radar or BASE_RADAR
    radar_dir = tmp_path / "config" / "radars"
    radar_dir.mkdir(parents=True, exist_ok=True)
    (radar_dir / f"{radar['name']}.yaml").write_text(
        yaml.safe_dump(radar, sort_keys=False), encoding="utf-8"
    )
    reddit_dir = tmp_path / "config" / "reddit_feeds"
    reddit_dir.mkdir(parents=True, exist_ok=True)
    return str(radar_dir), str(reddit_dir)


def write_handoff(tmp_path, envelope, name):
    handoff_dir = tmp_path / "handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    path = handoff_dir / name
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return str(path)


def load(result):
    return json.loads(result.stdout)


def invoke(app, runner, state_dir, config_dirs, *args, out_dir=None):
    radar_dir, reddit_dir = config_dirs
    full = [
        "radar-cycle",
        *args,
        "--state-dir",
        str(state_dir),
        "--config-dir",
        radar_dir,
        "--reddit-dir",
        reddit_dir,
    ]
    if out_dir is not None:
        full += ["--out-dir", str(out_dir)]
    return runner.invoke(app, full)


def checkpoint_dir(state_dir):
    return str(Path(state_dir) / "radar_cycles")


def start_run(app, runner, state_dir, config_dirs, mode="weekly"):
    result = invoke(
        app, runner, state_dir, config_dirs,
        "start", "--radar", "agent-reliability", "--mode", mode, "--json",
    )
    assert result.exit_code == 0, result.output
    return load(result)


def complete_phase(state_dir, run_id, phase):
    """Drive a local phase pending -> running -> completed via the checkpoint layer."""
    store_dir = checkpoint_dir(state_dir)
    checkpoint.transition(run_id, phase, "running", store_dir=store_dir)
    checkpoint.transition(run_id, phase, "completed", store_dir=store_dir)


def import_phase(app, runner, state_dir, config_dirs, run_id, phase, path):
    result = invoke(
        app, runner, state_dir, config_dirs,
        "import", run_id, phase, "--file", path, "--json",
    )
    assert result.exit_code == 0, result.output
    return load(result)["data"]


def resume_next_phase(app, runner, state_dir, config_dirs, run_id):
    result = invoke(app, runner, state_dir, config_dirs, "resume", run_id, "--json")
    assert result.exit_code == 0, result.output
    return load(result)["data"]["next_action"]


def seed_build_eligible_card(
    state_dir, concept_id="goal-drift-detector", title="Goal drift detector"
):
    """Seed a VERIFY-stage card whose evidence passes all six build gates."""
    store = ConceptStore(state_dir=state_dir)
    store.upsert_concept(
        ConceptCard(
            id=concept_id,
            title=title,
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
    store.add_evidence(
        ConceptEvidence(
            id=f"e-{concept_id}-1",
            concept_id=concept_id,
            source_type=SourceType.GITHUB,
            source_url="https://github.com/x/y",
            role=EvidenceRole.IMPLEMENTATION,
            directness=Directness.DIRECT,
            strength=EvidenceStrength.STRONG,
            independence_key="chain-a",
        )
    )
    store.add_evidence(
        ConceptEvidence(
            id=f"e-{concept_id}-2",
            concept_id=concept_id,
            source_type=SourceType.REDDIT,
            source_url="https://reddit.com/r/x/1",
            role=EvidenceRole.PROBLEM,
            directness=Directness.DIRECT,
            strength=EvidenceStrength.MODERATE,
            independence_key="chain-b",
        )
    )


def drive_full_weekly(app, runner, state_dir, config_dirs, *, resume_between=False):
    """Drive a complete weekly run (with one Build) and finalize it.

    When ``resume_between`` is True, ``resume`` is invoked before every step and
    asserted to return the first incomplete phase — simulating an interruption
    after every phase and a restart that resumes exactly where it left off.
    Returns ``(run_id, out_dir)``.
    """
    out_dir = Path(state_dir) / "out"
    seed_build_eligible_card(state_dir)

    payload = start_run(app, runner, state_dir, config_dirs, mode="weekly")
    run_id = payload["data"]["run_id"]

    def expect_next(expected):
        if resume_between:
            next_action = resume_next_phase(app, runner, state_dir, config_dirs, run_id)
            assert next_action is not None
            assert next_action["phase"] == expected, (
                f"expected resume to return {expected!r}, got {next_action['phase']!r}"
            )

    expect_next("validate")
    complete_phase(state_dir, run_id, "validate")

    expect_next("x-discovery")
    import_phase(
        app, runner, state_dir, config_dirs, run_id,
        "x-discovery", str(FIXTURES / "x_learning_handoff.json"),
    )

    expect_next("reddit-scan")
    import_phase(
        app, runner, state_dir, config_dirs, run_id,
        "reddit-scan", str(FIXTURES / "reddit_handoff.json"),
    )

    expect_next("reduce")
    complete_phase(state_dir, run_id, "reduce")

    expect_next("verify")
    import_phase(
        app, runner, state_dir, config_dirs, run_id,
        "verify", str(FIXTURES / "github_handoff.json"),
    )

    expect_next("decide")
    decide = invoke(app, runner, state_dir, config_dirs, "decide", run_id, "--json")
    assert decide.exit_code == 0, decide.output
    assert load(decide)["data"]["build_decisions"] == 1

    expect_next("experiment")
    complete_phase(state_dir, run_id, "experiment")

    expect_next("calibration")
    complete_phase(state_dir, run_id, "calibration")

    expect_next("report")
    finalize = invoke(
        app, runner, state_dir, config_dirs,
        "finalize", run_id, "--json", out_dir=out_dir,
    )
    assert finalize.exit_code == 0, finalize.output

    return run_id, out_dir


# ── State snapshots (acceptance invariant) ──


def _strip_write_timestamps(data: dict) -> dict:
    for key in ("captured_at", "recorded_at", "created_at", "updated_at"):
        data.pop(key, None)
    return data


def store_snapshot(state_dir):
    store = ConceptStore(state_dir=state_dir)
    return {
        "concepts": sorted(
            [_strip_write_timestamps(c.model_dump(mode="json")) for c in store.list_concepts()],
            key=lambda d: d["id"],
        ),
        "evidence": sorted(
            [_strip_write_timestamps(e.model_dump(mode="json")) for e in store.list_evidence()],
            key=lambda d: d["id"],
        ),
        "reviews": sorted(
            [_strip_write_timestamps(r.model_dump(mode="json")) for r in store.list_reviews()],
            key=lambda d: d["id"],
        ),
    }


def checkpoint_snapshot(state_dir, run_id):
    doc = checkpoint.load_document(run_id, store_dir=checkpoint_dir(state_dir))
    run = doc.run
    return {
        "radar": run.radar,
        "mode": run.mode.value,
        "config_fingerprint": run.checkpoint.config_fingerprint,
        "phases": {p.value: run.checkpoint.status_of(p).value for p in PhaseName},
        "counts": {p.value: count for p, count in run.checkpoint.counts.items()},
        "errors": list(run.checkpoint.errors),
        "retry_counts": {p.value: count for p, count in run.checkpoint.retry_counts.items()},
        "outputs": {key: list(paths) for key, paths in doc.outputs.items()},
        "coverage": [c.model_dump(mode="json") for c in doc.coverage],
        "run_status": doc.run_status,
    }


def full_snapshot(state_dir, run_id):
    return {
        "checkpoint": checkpoint_snapshot(state_dir, run_id),
        "store": store_snapshot(state_dir),
    }


# ── 1. Uninterrupted full run ──


def test_uninterrupted_full_run_produces_report(app, runner, tmp_path, config_dirs):
    run_id, out_dir = drive_full_weekly(app, runner, tmp_path, config_dirs)

    assert (out_dir / f"{run_id}.json").exists()
    assert (out_dir / f"{run_id}.md").exists()

    report = json.loads((out_dir / f"{run_id}.json").read_text(encoding="utf-8"))
    assert report["run"]["id"] == run_id
    # JSON-first report carries decisions and coverage gaps sections.
    assert "decisions" in report
    assert "coverage_gaps" in report

    statuses = checkpoint_snapshot(tmp_path, run_id)["phases"]
    for phase in WEEKLY_PHASES:
        assert statuses[phase] == "completed", (phase, statuses[phase])
    assert statuses["source-audit"] == "pending"

    assert checkpoint.run_status_of(run_id, store_dir=checkpoint_dir(tmp_path)) == "completed"


# ── 2. Interruption after every phase + resume ──


def test_interruption_after_every_phase_resumes_at_first_incomplete(
    app, runner, tmp_path, config_dirs
):
    run_id, out_dir = drive_full_weekly(app, runner, tmp_path, config_dirs, resume_between=True)

    # The run completed and the report exists.
    assert (out_dir / f"{run_id}.json").exists()
    assert checkpoint.run_status_of(run_id, store_dir=checkpoint_dir(tmp_path)) == "completed"

    # After finalize there is nothing left to resume.
    assert resume_next_phase(app, runner, tmp_path, config_dirs, run_id) is None


# ── 3. X unavailable but Reddit/GitHub successful ──


def test_x_unavailable_reddit_github_succeed_with_explicit_gap(
    app, runner, tmp_path, config_dirs
):
    payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
    run_id = payload["data"]["run_id"]
    complete_phase(tmp_path, run_id, "validate")

    x_unavailable = {
        "schema_version": 1,
        "source_phase": "x-discovery",
        "coverage": "unavailable",
        "coverage_notes": ["X API authentication failed; no posts retrieved"],
        "items": [
            {
                "source": "x",
                "role": "problem",
                "author": "",
                "url": "",
                "excerpt": "X was unavailable this cycle; no first-hand posts collected.",
                "directness": "inferred",
                "strength": "weak",
                "topics": ["agent-reliability"],
                "proposed_concept": None,
            }
        ],
    }
    x_path = write_handoff(tmp_path, x_unavailable, "x-unavailable.json")
    import_phase(app, runner, tmp_path, config_dirs, run_id, "x-discovery", x_path)

    import_phase(
        app, runner, tmp_path, config_dirs, run_id,
        "reddit-scan", str(FIXTURES / "reddit_handoff.json"),
    )
    complete_phase(tmp_path, run_id, "reduce")
    import_phase(
        app, runner, tmp_path, config_dirs, run_id,
        "verify", str(FIXTURES / "github_handoff.json"),
    )

    decide = invoke(app, runner, tmp_path, config_dirs, "decide", run_id, "--json")
    assert decide.exit_code == 0, decide.output

    complete_phase(tmp_path, run_id, "calibration")
    out_dir = tmp_path / "out"
    finalize = invoke(
        app, runner, tmp_path, config_dirs, "finalize", run_id, "--json", out_dir=out_dir
    )
    assert finalize.exit_code == 0, finalize.output

    # The X source gap is recorded explicitly on the checkpoint coverage.
    doc = checkpoint.load_document(run_id, store_dir=checkpoint_dir(tmp_path))
    coverage = {c.source_type.value: c for c in doc.coverage}
    assert coverage["x"].status.value == "unavailable"
    assert coverage["reddit"].status.value == "partial"
    assert coverage["github"].status.value == "complete"

    # And it surfaces in the report's coverage gaps.
    report = json.loads((out_dir / f"{run_id}.json").read_text(encoding="utf-8"))
    assert any("authentication failed" in gap for gap in report["coverage_gaps"])


# ── 4. Partial Reddit feed / absent comments ──


def test_partial_reddit_feed_shows_absent_comments_gap(app, runner, tmp_path, config_dirs):
    payload = start_run(app, runner, tmp_path, config_dirs, mode="daily")
    run_id = payload["data"]["run_id"]
    complete_phase(tmp_path, run_id, "validate")
    import_phase(
        app, runner, tmp_path, config_dirs, run_id,
        "x-discovery", str(FIXTURES / "x_learning_handoff.json"),
    )
    import_phase(
        app, runner, tmp_path, config_dirs, run_id,
        "reddit-scan", str(FIXTURES / "reddit_handoff.json"),
    )
    complete_phase(tmp_path, run_id, "reduce")

    out_dir = tmp_path / "out"
    finalize = invoke(
        app, runner, tmp_path, config_dirs, "finalize", run_id, "--json", out_dir=out_dir
    )
    assert finalize.exit_code == 0, finalize.output

    doc = checkpoint.load_document(run_id, store_dir=checkpoint_dir(tmp_path))
    coverage = {c.source_type.value: c for c in doc.coverage}
    assert coverage["reddit"].status.value == "partial"

    report = json.loads((out_dir / f"{run_id}.json").read_text(encoding="utf-8"))
    assert any("comments not read" in gap.lower() for gap in report["coverage_gaps"])

    # The absent-comments gap is baked into the normalized Reddit evidence note.
    store = ConceptStore(state_dir=tmp_path)
    reddit_evidence = [
        e for e in store.list_evidence() if e.source_type == SourceType.REDDIT
    ]
    assert reddit_evidence
    assert all("comments not read" in e.note.lower() for e in reddit_evidence)


# ── 5. Duplicate propagation chains collapse to one independence key ──


def test_duplicate_propagation_chains_collapse_to_one_independence_key(tmp_path):
    envelope = {
        "schema_version": 1,
        "source_phase": "x-discovery",
        "coverage": "complete",
        "coverage_notes": [],
        "items": [
            {
                "source": "x",
                "role": "problem",
                "author": "reposter1",
                "url": "https://x.com/reposter1/status/1",
                "excerpt": "Repost of the drift claim",
                "directness": "indirect",
                "strength": "weak",
                "upstream_origin": "https://x.com/original/status/100",
                "topics": ["drift"],
                "proposed_concept": None,
            },
            {
                "source": "x",
                "role": "problem",
                "author": "reposter2",
                "url": "https://x.com/reposter2/status/2",
                "excerpt": "Another repost of the drift claim",
                "directness": "indirect",
                "strength": "weak",
                "upstream_origin": "https://x.com/original/status/100",
                "topics": ["drift"],
                "proposed_concept": None,
            },
        ],
    }

    records = normalize_handoff(envelope)
    assert len(records) == 2
    # Both reposts collapse onto the single upstream independence key.
    assert {r.independence_key for r in records} == {"upstream:x.com/original/status/100"}

    # Importing them yields two evidence records but a single independence key.
    store = ConceptStore(state_dir=tmp_path)
    result = import_handoff(store, envelope)
    assert result.imported == 2
    assert len({e.independence_key for e in store.list_evidence()}) == 1


# ── 6. Ambiguous merge preserves two cards ──


def test_ambiguous_merge_preserves_two_cards(tmp_path):
    store = ConceptStore(state_dir=tmp_path)
    store.upsert_concept(
        ConceptCard(id="card-a", title="Shared Failure", problem="failures in deployment pipelines")
    )
    store.upsert_concept(
        ConceptCard(id="card-b", title="Shared Failure", problem="failures in agent memory")
    )

    # Two cards share the candidate's exact title -> a tie -> ambiguous, never
    # auto-merged. Capture must raise rather than destroy either card.
    with pytest.raises(ConceptValidationError) as excinfo:
        capture(
            store,
            source="x",
            url="https://x.com/u/status/999",
            note="a new shared failure signal",
            title="Shared Failure",
            problem="a third failure kind",
        )
    assert "ambiguous" in str(excinfo.value).lower()

    cards = store.list_concepts()
    assert {c.id for c in cards} == {"card-a", "card-b"}
    assert all(c.stage == PortfolioStage.INBOX for c in cards)


# ── 7. High-hype / high-alignment concept fails Build ──


def test_high_alignment_and_hype_cannot_override_a_failed_gate():
    card = ConceptCard(
        id="high-alignment",
        title="High alignment concept",
        stage=PortfolioStage.VERIFY,
        smallest_experiment=SmallestExperiment(
            hypothesis="h",
            target="t",
            artifact="a",
            success_threshold="s",
            failure_threshold="f",
            stop_condition="stop",
        ),
    )
    # Two independent chains but a single source type -> two_source_types fails.
    evidence = [
        ConceptEvidence(
            id="e1", concept_id="high-alignment", source_type=SourceType.GITHUB,
            source_url="https://github.com/a/b", role=EvidenceRole.PROBLEM,
            directness=Directness.DIRECT, strength=EvidenceStrength.STRONG,
            independence_key="chain-a",
        ),
        ConceptEvidence(
            id="e2", concept_id="high-alignment", source_type=SourceType.GITHUB,
            source_url="https://github.com/a/c", role=EvidenceRole.PROBLEM,
            directness=Directness.DIRECT, strength=EvidenceStrength.STRONG,
            independence_key="chain-b",
        ),
    ]

    high_alignment = score_concept(card, evidence, user_alignment=3, hype=0)
    high_hype = score_concept(card, evidence, user_alignment=0, hype=3)

    # Alignment cannot satisfy a truth gate.
    assert high_alignment.failed_gates == [GATE_TWO_SOURCE_TYPES]
    assert GATE_TWO_SOURCE_TYPES not in high_alignment.passed_gates
    assert high_alignment.components.user_alignment == 3

    # Hype is a penalty and never flips a failed gate.
    assert high_hype.failed_gates == [GATE_TWO_SOURCE_TYPES]
    assert high_hype.total < high_alignment.total


# ── 8. One Build allowed, second blocked by weekly limit ──


def test_one_build_and_second_blocked_by_weekly_limit(app, runner, tmp_path, config_dirs):
    payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
    run_id = payload["data"]["run_id"]
    for phase in ("validate", "x-discovery", "reddit-scan", "reduce", "verify"):
        complete_phase(tmp_path, run_id, phase)

    seed_build_eligible_card(tmp_path, concept_id="aaa-goal-drift", title="Goal drift detector")
    seed_build_eligible_card(
        tmp_path, concept_id="bbb-goal-drift", title="Second goal drift detector"
    )

    decide = invoke(app, runner, tmp_path, config_dirs, "decide", run_id, "--json")
    assert decide.exit_code == 0, decide.output
    data = load(decide)["data"]

    assert data["weekly_build_cap"] == 1
    assert data["build_decisions"] == 1

    decisions = data["decisions"]
    assert len(decisions) == 2
    assert decisions[0]["concept_id"] == "aaa-goal-drift"
    assert decisions[0]["passed"] is True
    assert decisions[1]["concept_id"] == "bbb-goal-drift"
    assert decisions[1]["passed"] is False
    assert "weekly_builds_available" in decisions[1]["failed_gates"]

    # One Build passed -> the engine requires exactly the experiment phase next.
    assert data["next_action"]["phase"] == "experiment"


# ── 9. Report render failure followed by render-only resume ──


def test_report_render_failure_followed_by_render_only_resume(
    app, runner, tmp_path, config_dirs, monkeypatch
):
    payload = start_run(app, runner, tmp_path, config_dirs, mode="daily")
    run_id = payload["data"]["run_id"]
    for phase in ("validate", "x-discovery", "reddit-scan", "reduce"):
        complete_phase(tmp_path, run_id, phase)
    out_dir = tmp_path / "out"

    original = rendering_module.render_run_markdown

    def boom(report):
        raise RuntimeError("synthetic markdown failure")

    # First finalize: Markdown rendering fails, but the JSON report is kept.
    monkeypatch.setattr(rendering_module, "render_run_markdown", boom)
    failed = invoke(
        app, runner, tmp_path, config_dirs, "finalize", run_id, "--json", out_dir=out_dir
    )
    assert failed.exit_code != 0
    assert load(failed)["ok"] is False
    assert (out_dir / f"{run_id}.json").exists()
    assert checkpoint.run_status_of(run_id, store_dir=checkpoint_dir(tmp_path)) == "running"
    run = checkpoint.load(run_id, store_dir=checkpoint_dir(tmp_path))
    assert run.checkpoint.status_of(PhaseName.REPORT).value == "pending"

    # Render-only resume: re-running finalize completes rendering + the run.
    monkeypatch.setattr(rendering_module, "render_run_markdown", original)
    resumed = invoke(
        app, runner, tmp_path, config_dirs, "finalize", run_id, "--json", out_dir=out_dir
    )
    assert resumed.exit_code == 0, resumed.output
    assert (out_dir / f"{run_id}.md").exists()
    assert checkpoint.run_status_of(run_id, store_dir=checkpoint_dir(tmp_path)) == "completed"
    run = checkpoint.load(run_id, store_dir=checkpoint_dir(tmp_path))
    assert run.checkpoint.status_of(PhaseName.REPORT).value == "completed"


# ── 10. Changed config fingerprint blocks resume ──


def test_changed_config_fingerprint_blocks_resume(app, runner, tmp_path, config_dirs):
    payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
    run_id = payload["data"]["run_id"]

    # Mutate the (tmp copy of the) radar config after start.
    radar_dir, _ = config_dirs
    changed = {**BASE_RADAR, "description": "changed description"}
    (Path(radar_dir) / "agent-reliability.yaml").write_text(
        yaml.safe_dump(changed, sort_keys=False), encoding="utf-8"
    )

    result = invoke(app, runner, tmp_path, config_dirs, "resume", run_id, "--json")
    assert result.exit_code != 0
    body = load(result)
    assert body["ok"] is False
    assert "fingerprint" in body["error"].lower()


# ── 11. Duplicate handoff replay produces no new records ──


def test_duplicate_handoff_replay_produces_no_new_records(app, runner, tmp_path, config_dirs):
    payload = start_run(app, runner, tmp_path, config_dirs, mode="weekly")
    run_id = payload["data"]["run_id"]
    complete_phase(tmp_path, run_id, "validate")

    x_path = str(FIXTURES / "x_learning_handoff.json")
    first = import_phase(app, runner, tmp_path, config_dirs, run_id, "x-discovery", x_path)
    assert first["import"]["imported"] == 1

    replay = import_phase(app, runner, tmp_path, config_dirs, run_id, "x-discovery", x_path)
    assert replay["import"]["imported"] == 0
    assert replay["import"]["skipped_idempotent"] == 0
    assert replay["next_action"]["phase"] == "reddit-scan"

    store = ConceptStore(state_dir=tmp_path)
    assert len(store.list_evidence()) == 1


# ── 12. Monthly calibration preserves original predictions ──


def test_monthly_calibration_preserves_original_predictions(app, runner, tmp_path, config_dirs):
    # A monthly cycle completes with the calibration phase in its sequence.
    payload = start_run(app, runner, tmp_path, config_dirs, mode="monthly")
    run_id = payload["data"]["run_id"]
    complete_phase(tmp_path, run_id, "validate")
    complete_phase(tmp_path, run_id, "source-audit")
    complete_phase(tmp_path, run_id, "calibration")

    out_dir = tmp_path / "out"
    finalize = invoke(
        app, runner, tmp_path, config_dirs, "finalize", run_id, "--json", out_dir=out_dir
    )
    assert finalize.exit_code == 0, finalize.output
    statuses = checkpoint_snapshot(tmp_path, run_id)["phases"]
    for phase in ("validate", "source-audit", "calibration", "report"):
        assert statuses[phase] == "completed"
    assert statuses["x-discovery"] == "pending"

    # The calibration invariant: recording an outcome never rewrites the original
    # prediction recorded on entry to Build.
    store = ConceptStore(state_dir=tmp_path)
    store.upsert_concept(
        ConceptCard(
            id="build-card",
            title="Build card",
            stage=PortfolioStage.BUILD,
            prediction="drift is detectable before failure in 80% of runs",
            smallest_experiment=SmallestExperiment(
                hypothesis="h",
                target="t",
                artifact="a",
                success_threshold="s",
                failure_threshold="f",
                stop_condition="stop",
            ),
        )
    )

    result = record_outcome(
        store, "build-card", "partially_confirmed", "domain narrower than predicted"
    )
    assert result["data"]["prediction_preserved"] is True
    assert result["data"]["original_prediction"] == (
        "drift is detectable before failure in 80% of runs"
    )

    updated = store.get_concept("build-card")
    assert updated.prediction == "drift is detectable before failure in 80% of runs"
    assert updated.outcome.value == "partially_confirmed"


# ── Acceptance invariant: interrupted == uninterrupted ──


def test_interrupted_and_uninterrupted_runs_produce_equivalent_state(
    app, runner, tmp_path, config_dirs
):
    state_a = tmp_path / "state-uninterrupted"
    state_b = tmp_path / "state-interrupted"

    run_a, _ = drive_full_weekly(app, runner, state_a, config_dirs, resume_between=False)
    run_b, _ = drive_full_weekly(app, runner, state_b, config_dirs, resume_between=True)

    snap_a = full_snapshot(state_a, run_a)
    snap_b = full_snapshot(state_b, run_b)

    assert snap_a == snap_b
