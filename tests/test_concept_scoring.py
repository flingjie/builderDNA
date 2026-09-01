"""Tests for deterministic experiment-priority scoring and hard build gates.

Covers the acceptance criteria for ``concepts/scoring.py``:

- High hype cannot improve priority (raising hype strictly lowers ``total``).
- High user alignment cannot pass a missing-evidence gate.
- Identical components always produce identical totals (determinism).
- One source type / one chain does not pass the Build gate; two source types +
  two independent chains + reviewed counterevidence + a bounded smallest
  experiment do.
"""
from datetime import datetime, timezone

from concepts.scoring import (
    BuildGateResult,
    ScoredComponents,
    evaluate_build_gate,
    score_components,
)
from models.concept import (
    ComponentScores,
    ConceptCard,
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    MaturityStage,
    PortfolioStage,
    SmallestExperiment,
    SourceType,
)

SCORE_COMPONENTS = {"problem", "evidence", "reach", "user_alignment", "hype", "competition"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_experiment(**overrides) -> SmallestExperiment:
    fields = dict(
        hypothesis="Users will complete the task unaided",
        target="first-time users of an agent CLI",
        artifact="a 20-line prototype script",
        success_threshold=">= 5 of 10 users complete the task in under 2 minutes",
        failure_threshold="< 3 of 10 users complete the task",
        stop_condition="stop after 10 users or 2 hours, whichever first",
    )
    fields.update(overrides)
    return SmallestExperiment(**fields)


def make_card(**overrides) -> ConceptCard:
    fields = dict(id="agent-reliability", title="Agent Reliability")
    fields.update(overrides)
    return ConceptCard(**fields)


def make_evidence(**overrides) -> ConceptEvidence:
    fields = dict(
        id="ev1",
        concept_id="agent-reliability",
        source_type=SourceType.GITHUB,
        source_url="https://github.com/example/repo",
        role=EvidenceRole.PROBLEM,
        directness=Directness.DIRECT,
        strength=EvidenceStrength.STRONG,
        independence_key="github.com/example/repo",
    )
    fields.update(overrides)
    return ConceptEvidence(**fields)


# ── Priority invariants ──


class TestPriorityInvariants:
    def test_high_hype_lowers_total(self):
        card = make_card()
        evidence = [
            make_evidence(
                id="e1",
                role=EvidenceRole.PROBLEM,
                strength=EvidenceStrength.STRONG,
                independence_key="chain-a",
            ),
            make_evidence(
                id="e2",
                role=EvidenceRole.PROBLEM,
                independence_key="chain-b",
            ),
        ]
        low_hype = score_components(card, evidence, hype=0)
        high_hype = score_components(card, evidence, hype=3)
        # Hype is a penalty term: identical everything else, more hype = lower total.
        assert high_hype.scores.hype == 3
        assert low_hype.scores.hype == 0
        assert high_hype.scores.total < low_hype.scores.total

    def test_high_alignment_cannot_pass_missing_evidence_gate(self):
        # A single source type + single chain is missing-evidence territory.
        evidence = [
            make_evidence(
                id="e1",
                source_type=SourceType.GITHUB,
                role=EvidenceRole.PROBLEM,
                independence_key="chain-a",
            ),
        ]
        card = make_card(smallest_experiment=make_experiment(), maturity=MaturityStage.VERIFIED)

        # Even with maximum user alignment, the gate must still fail.
        scored = score_components(card, evidence, user_alignment=3)
        gate = evaluate_build_gate(card, evidence)

        assert scored.scores.user_alignment == 3
        assert not gate.passed
        assert any("two source types" in m for m in gate.missing)
        assert any("two independent supporting chains" in m for m in gate.missing)

    def test_deterministic_identical_totals(self):
        card = make_card()
        evidence = [
            make_evidence(id="e1", role=EvidenceRole.PROBLEM, independence_key="a"),
            make_evidence(
                id="e2",
                source_type=SourceType.REDDIT,
                role=EvidenceRole.ADOPTION,
                independence_key="b",
                note="Used by thousands of teams in production",
            ),
        ]
        first = score_components(card, evidence, user_alignment=2, hype=1)
        second = score_components(card, evidence, user_alignment=2, hype=1)

        assert first.scores == second.scores
        assert first.scores.total == second.scores.total
        assert first.reasons == second.reasons

    def test_total_is_recomputed_not_supplied(self):
        card = make_card()
        evidence = [make_evidence(role=EvidenceRole.PROBLEM, independence_key="a")]
        scored = score_components(card, evidence)
        expected = (
            2 * scored.scores.problem
            + 2 * scored.scores.evidence
            + scored.scores.reach
            + scored.scores.user_alignment
            - 2 * scored.scores.hype
            - scored.scores.competition
        )
        assert scored.scores.total == expected


# ── Component derivation ──


class TestComponentDerivation:
    def test_problem_from_strong_independent_evidence(self):
        card = make_card()
        evidence = [
            make_evidence(id="e1", role=EvidenceRole.PROBLEM, strength=EvidenceStrength.STRONG, independence_key="a"),
            make_evidence(id="e2", source_type=SourceType.REDDIT, role=EvidenceRole.PROBLEM, strength=EvidenceStrength.STRONG, independence_key="b"),
        ]
        scored = score_components(card, evidence)
        assert scored.scores.problem == 3
        assert "strong" in scored.reasons["problem"]
        assert "2 independent chains" in scored.reasons["problem"]

    def test_problem_defaults_to_zero_without_problem_evidence(self):
        card = make_card()
        evidence = [make_evidence(role=EvidenceRole.IMPLEMENTATION, independence_key="a")]
        scored = score_components(card, evidence)
        assert scored.scores.problem == 0
        assert "no problem-role evidence" in scored.reasons["problem"]

    def test_evidence_counts_independent_chains_and_source_types(self):
        card = make_card()
        one_chain_one_type = [
            make_evidence(id="e1", role=EvidenceRole.IMPLEMENTATION, independence_key="a"),
            make_evidence(id="e2", role=EvidenceRole.ADOPTION, independence_key="a"),
        ]
        assert score_components(card, one_chain_one_type).scores.evidence == 1

        two_chains_two_types = [
            make_evidence(id="e1", source_type=SourceType.GITHUB, role=EvidenceRole.IMPLEMENTATION, independence_key="a"),
            make_evidence(id="e2", source_type=SourceType.REDDIT, role=EvidenceRole.PROBLEM, independence_key="b"),
        ]
        assert score_components(card, two_chains_two_types).scores.evidence == 3

    def test_evidence_excludes_counterevidence_from_support(self):
        card = make_card()
        evidence = [
            make_evidence(id="e1", role=EvidenceRole.IMPLEMENTATION, independence_key="a"),
            make_evidence(id="e2", source_type=SourceType.REDDIT, role=EvidenceRole.COUNTER, independence_key="b"),
        ]
        # One supporting chain + one counter chain is not two supporting chains.
        assert score_components(card, evidence).scores.evidence == 1

    def test_reach_from_note_hint_and_conservative_default(self):
        card = make_card()
        hinted = [make_evidence(role=EvidenceRole.PROBLEM, independence_key="a", note="Millions of users affected")]
        assert score_components(card, hinted).scores.reach == 3

        silent = [make_evidence(role=EvidenceRole.PROBLEM, independence_key="a")]
        scored = score_components(card, silent)
        assert scored.scores.reach == 0
        assert "conservative default" in scored.reasons["reach"]

    def test_user_alignment_is_caller_supplied_never_inferred(self):
        card = make_card()
        evidence = [make_evidence(role=EvidenceRole.PROBLEM, independence_key="a")]
        # No evidence can imply alignment; default is 0 with an explicit reason.
        scored = score_components(card, evidence)
        assert scored.scores.user_alignment == 0
        assert "never inferred" in scored.reasons["user_alignment"]

        supplied = score_components(card, evidence, user_alignment=3)
        assert supplied.scores.user_alignment == 3
        assert "caller-supplied" in supplied.reasons["user_alignment"]

    def test_hype_from_caller_flag_or_note(self):
        card = make_card()
        evidence = [make_evidence(role=EvidenceRole.PROBLEM, independence_key="a")]

        flagged = score_components(card, evidence, hype=2)
        assert flagged.scores.hype == 2
        assert "caller-supplied hype flag" in flagged.reasons["hype"]

        hyped_note = [make_evidence(role=EvidenceRole.PROBLEM, independence_key="a", note="going viral")]
        derived = score_components(card, hyped_note)
        assert derived.scores.hype >= 1
        assert "hype keyword group" in derived.reasons["hype"]

        quiet = score_components(card, evidence)
        assert quiet.scores.hype == 0

    def test_competition_from_adoption_evidence(self):
        card = make_card()
        none = [make_evidence(role=EvidenceRole.PROBLEM, independence_key="a")]
        assert score_components(card, none).scores.competition == 0

        adopted = [
            make_evidence(id="e1", role=EvidenceRole.ADOPTION, independence_key="a"),
            make_evidence(id="e2", source_type=SourceType.REDDIT, role=EvidenceRole.ADOPTION, strength=EvidenceStrength.STRONG, independence_key="b"),
        ]
        assert score_components(card, adopted).scores.competition == 3

    def test_reasons_cover_all_six_components(self):
        card = make_card()
        evidence = [make_evidence(role=EvidenceRole.PROBLEM, independence_key="a")]
        scored = score_components(card, evidence)
        assert set(scored.reasons) == SCORE_COMPONENTS
        assert isinstance(scored, ScoredComponents)
        assert isinstance(scored.scores, ComponentScores)


# ── Build gate ──


class TestBuildGate:
    def test_one_source_one_chain_does_not_pass(self):
        evidence = [
            make_evidence(id="e1", source_type=SourceType.GITHUB, role=EvidenceRole.IMPLEMENTATION, independence_key="chain-a"),
            make_evidence(id="e2", source_type=SourceType.GITHUB, role=EvidenceRole.ADOPTION, independence_key="chain-a"),
        ]
        card = make_card(maturity=MaturityStage.VERIFIED, smallest_experiment=make_experiment())
        gate = evaluate_build_gate(card, evidence)

        assert not gate.passed
        assert any("two source types" in m for m in gate.missing)
        assert any("two independent supporting chains" in m for m in gate.missing)

    def test_two_sources_two_chains_reviewed_counter_and_experiment_pass(self):
        evidence = [
            make_evidence(id="e1", source_type=SourceType.GITHUB, role=EvidenceRole.IMPLEMENTATION, independence_key="gh-repo-a"),
            make_evidence(id="e2", source_type=SourceType.REDDIT, role=EvidenceRole.PROBLEM, independence_key="reddit-thread-1"),
            make_evidence(id="e3", source_type=SourceType.GITHUB, role=EvidenceRole.COUNTER, independence_key="gh-counter-1"),
        ]
        card = make_card(
            maturity=MaturityStage.VERIFIED,
            stage=PortfolioStage.VERIFY,
            smallest_experiment=make_experiment(),
        )
        gate = evaluate_build_gate(card, evidence)

        assert gate.passed
        assert gate.missing == ()
        assert isinstance(gate, BuildGateResult)

    def test_no_counterevidence_passes_review_requirement_vacuously(self):
        evidence = [
            make_evidence(id="e1", source_type=SourceType.GITHUB, role=EvidenceRole.IMPLEMENTATION, independence_key="a"),
            make_evidence(id="e2", source_type=SourceType.REDDIT, role=EvidenceRole.PROBLEM, independence_key="b"),
        ]
        card = make_card(maturity=MaturityStage.VERIFIED, smallest_experiment=make_experiment())
        assert evaluate_build_gate(card, evidence).passed

    def test_unresolved_counterevidence_blocks_build(self):
        evidence = [
            make_evidence(id="e1", source_type=SourceType.GITHUB, role=EvidenceRole.IMPLEMENTATION, independence_key="a"),
            make_evidence(id="e2", source_type=SourceType.REDDIT, role=EvidenceRole.PROBLEM, independence_key="b"),
            make_evidence(id="e3", source_type=SourceType.GITHUB, role=EvidenceRole.COUNTER, independence_key="c"),
        ]
        card = make_card(maturity=MaturityStage.CONTESTED, smallest_experiment=make_experiment())
        gate = evaluate_build_gate(card, evidence)

        assert not gate.passed
        assert any("reviewed counterevidence" in m for m in gate.missing)

    def test_missing_smallest_experiment_blocks_build(self):
        evidence = [
            make_evidence(id="e1", source_type=SourceType.GITHUB, role=EvidenceRole.IMPLEMENTATION, independence_key="a"),
            make_evidence(id="e2", source_type=SourceType.REDDIT, role=EvidenceRole.PROBLEM, independence_key="b"),
        ]
        card = make_card(maturity=MaturityStage.VERIFIED)  # no smallest_experiment
        gate = evaluate_build_gate(card, evidence)

        assert not gate.passed
        assert any("smallest experiment" in m for m in gate.missing)

    def test_gate_is_not_a_total_threshold(self):
        # A high-total card can still fail the gate: total and gates are separate.
        evidence = [
            make_evidence(id="e1", source_type=SourceType.GITHUB, role=EvidenceRole.PROBLEM, strength=EvidenceStrength.STRONG, independence_key="a"),
        ]
        card = make_card(maturity=MaturityStage.VERIFIED, smallest_experiment=make_experiment())
        scored = score_components(card, evidence, user_alignment=3, hype=0)
        assert scored.scores.total >= 3  # numerically respectable...
        assert not evaluate_build_gate(card, evidence).passed  # ...but gated out structurally

    def test_gate_failure_lists_all_missing_requirements(self):
        card = make_card()  # no experiment, default SIGNAL maturity
        evidence = []  # no evidence at all
        gate = evaluate_build_gate(card, evidence)

        assert not gate.passed
        joined = " ".join(gate.missing)
        assert "two source types" in joined
        assert "two independent supporting chains" in joined
        assert "smallest experiment" in joined
