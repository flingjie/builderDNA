"""Deterministic experiment-priority scoring and hard build gates.

This module computes the six :class:`~models.concept.ComponentScores` inputs —
``problem``, ``evidence``, ``reach``, ``user_alignment``, ``hype``, and
``competition`` — from a concept card and its evidence records, and evaluates
the hard gates that must pass before a concept may advance to ``build``.

It deliberately does **not** re-implement the priority total. The model owns
that: ``ComponentScores.total`` is always recomputed by its after-validator as
``2P + 2E + R + A - 2H - C``. This module only supplies the component integers
plus a per-component reason string, so every number is auditable.

Design rules honoured here:

- **Pure functions** of ``(card, evidence records)`` — no store import, no I/O.
- **Deterministic** — identical inputs yield identical scores, reasons, and gates.
- **``hype`` and ``competition`` are penalty terms** — they can only lower total.
- **``user_alignment`` is caller-supplied**, never inferred from evidence, and it
  has no effect on the build gates.
- **Gates are separate from the total** — they check structural evidence
  requirements, never a numeric threshold.

Component name mapping (concept-radar-loop plan ↔ ``ComponentScores``):

- ``pain_recurrence``        ↔ ``ComponentScores.problem``
- ``evidence_strength``      ↔ ``ComponentScores.evidence``
- ``independent_recurrence`` ↔ ``ComponentScores.reach``
- ``implementation_cost``    ↔ ``ComponentScores.competition``

The plan's formula uses those names, but the model (``models/concept.py``)
already owns the identical arithmetic ``2P + 2E + R + A - 2H - C``, so this
module keeps the existing field names and reuses ``ComponentScores.total``
unchanged.

Component heuristics (all on a 0-3 integer scale):

- ``problem``      — count/strength of ``problem``-role evidence and how many
                     independent chains those records span.
- ``evidence``     — number of independent chains (via ``independence_key``)
                     crossed with the number of distinct source types, using
                     supporting evidence only (counterevidence is excluded).
- ``reach``        — keyword magnitude hints in ``problem``/``why_now``/evidence
                     notes; conservative default 0 when nothing is found.
- ``user_alignment`` — caller-supplied; default 0 and never inferred.
- ``hype``         — caller-supplied flag when given, else hype keyword groups
                     in ``why_now``/notes; default 0 when absent.
- ``competition``  — adoption-role evidence density plus existing-solution
                     keyword hints; default 0 when absent.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from models.concept import (
    ComponentScores,
    ConceptCard,
    ConceptEvidence,
    EvidenceRole,
    EvidenceStrength,
    MaturityStage,
)

# The model clamps every component to [0, 3]; this is the ceiling for any
# heuristic that accumulates signals.
MAX_SCORE = 3

_STRENGTH_WEIGHT = {
    EvidenceStrength.WEAK: 1,
    EvidenceStrength.MODERATE: 2,
    EvidenceStrength.STRONG: 3,
}


# ── Individual component heuristics ──
#
# Each returns ``(score, reason)``. Reasons name the actual inputs observed so a
# human can trace any number back to the evidence that produced it.


def _score_problem(records: Sequence[ConceptEvidence]) -> tuple[int, str]:
    """Score problem severity from ``problem``-role evidence.

    Base 1 for any problem evidence; 2 when it is strong or spans multiple
    independent chains; 3 only when both hold.
    """
    problems = [e for e in records if e.role == EvidenceRole.PROBLEM]
    if not problems:
        return 0, "no problem-role evidence"

    chains = {e.independence_key for e in problems}
    max_weight = max(_STRENGTH_WEIGHT[e.strength] for e in problems)
    strong = max_weight == _STRENGTH_WEIGHT[EvidenceStrength.STRONG]

    score = 1
    if strong and len(chains) >= 2:
        score = 3
    elif strong or len(chains) >= 2:
        score = 2

    notes = []
    if strong:
        notes.append("strong signal")
    if len(chains) >= 2:
        notes.append(f"{len(chains)} independent chains")
    reason = f"{len(problems)} problem record(s) across {len(chains)} chain(s)"
    if notes:
        reason += " (" + "; ".join(notes) + ")"
    return score, reason


def _score_evidence(records: Sequence[ConceptEvidence]) -> tuple[int, str]:
    """Score supporting evidence from independent chains x source types.

    Counterevidence is excluded: it is handled separately by the gates, not
    counted as support for the concept.
    """
    supporting = [e for e in records if e.role != EvidenceRole.COUNTER]
    chains = {e.independence_key for e in supporting}
    source_types = {e.source_type for e in supporting}
    n_chains = len(chains)
    n_types = len(source_types)

    if n_chains == 0:
        return 0, "no supporting evidence"
    if n_chains >= 2 and n_types >= 2:
        score = 3
    elif n_chains >= 2 or n_types >= 2:
        score = 2
    else:
        score = 1

    return score, f"{n_chains} independent chain(s) across {n_types} source type(s)"


# Reach magnitude keywords, checked most-significant tier first. These are
# deliberately conservative: no hint -> 0 rather than a guessed population.
_REACH_TIER_3 = (
    "million", "millions", "100k", "100,000", "10k", "10,000",
    "tens of thousands", "hundreds of thousands", "majority of",
    "most teams", "industry-wide",
)
_REACH_TIER_2 = (
    "thousand", "thousands", "hundreds", "dozens", "widespread",
    "many teams", "multiple teams", "several teams", "in production",
    "production systems", "enterprise",
)
_REACH_TIER_1 = (
    "a team", "one team", "single team", "internal", "a few",
    "few users", "single user", "one user", "a couple",
)
_REACH_TIERS = ((3, _REACH_TIER_3), (2, _REACH_TIER_2), (1, _REACH_TIER_1))


def _score_reach(
    card: ConceptCard, records: Sequence[ConceptEvidence]
) -> tuple[int, str]:
    """Score reach from magnitude keywords in problem/why-now/notes.

    The evidence model carries no numeric population field, so reach is read
    from free text. Absent any hint the component stays at a conservative 0 —
    we never invent an affected-population count.
    """
    text = " ".join(
        [card.problem, card.why_now] + [e.note for e in records]
    ).lower()
    for tier, keywords in _REACH_TIERS:
        for keyword in keywords:
            if keyword in text:
                return tier, f"reach hint '{keyword}' found in problem/note text"
    return 0, "no reach signal in problem/note text; conservative default"


def _score_user_alignment(value: int) -> tuple[int, str]:
    """Pass through the caller-supplied alignment, never inferred from evidence."""
    if value:
        return value, f"caller-supplied ({value})"
    return 0, "caller-supplied default 0 (never inferred from evidence)"


_HYPE_GROUPS = (
    ("hype", "hyped", "overhyped", "hype cycle"),
    ("viral", "going viral", "viral growth"),
    ("trending", "exploding", "blowing up", "taking off", "hot topic"),
    ("stars", "starred", "github trending", "thousands of stars", "most starred"),
)


def _score_hype(
    card: ConceptCard,
    records: Sequence[ConceptEvidence],
    override: int | None,
) -> tuple[int, str]:
    """Score hype from a caller flag or keyword groups in why-now/notes.

    A caller-supplied value always wins (explicit beats inferred). Otherwise the
    number of distinct hype keyword groups matched, capped at 3, is used. Absent
    any signal the penalty stays at 0.
    """
    if override is not None:
        return override, f"caller-supplied hype flag ({override})"

    text = " ".join([card.why_now] + [e.note for e in records]).lower()
    groups = sum(1 for group in _HYPE_GROUPS if any(k in text for k in group))
    if groups == 0:
        return 0, "no hype signal in notes"
    return min(groups, MAX_SCORE), f"{groups} hype keyword group(s) matched in notes"


_COMPETITION_HINTS = (
    "existing solution", "already solved", "incumbent", "competitor",
    "competitors", "crowded", "alternatives", "many solutions", "saturated",
)


def _score_competition(
    card: ConceptCard, records: Sequence[ConceptEvidence]
) -> tuple[int, str]:
    """Score competition from adoption-role density + existing-solution hints.

    Adoption evidence is treated as a competition signal: people already using a
    solution means the space is occupied. Explicit existing-solution keywords in
    the problem/notes reinforce it.
    """
    adoption = [e for e in records if e.role == EvidenceRole.ADOPTION]
    n_chains = len({e.independence_key for e in adoption})
    max_weight = max(
        (_STRENGTH_WEIGHT[e.strength] for e in adoption), default=0
    )
    strong = max_weight == _STRENGTH_WEIGHT[EvidenceStrength.STRONG]

    text = " ".join(
        [card.problem, card.why_now] + [e.note for e in records]
    ).lower()
    hint = any(k in text for k in _COMPETITION_HINTS)

    if n_chains == 0 and not hint:
        return 0, "no adoption evidence and no existing-solution signal"

    score = 1
    if n_chains >= 2 or strong or (hint and n_chains >= 1):
        score = 2
    if (strong and n_chains >= 2) or (hint and n_chains >= 2):
        score = 3

    reason = f"{n_chains} adoption chain(s)"
    if hint:
        reason += " + existing-solution hint"
    details = []
    if strong:
        details.append("strong adoption")
    if n_chains >= 2:
        details.append(f"{n_chains} chains")
    if hint:
        details.append("existing-solution hint")
    if details:
        reason += " (" + "; ".join(details) + ")"
    return score, reason


# ── Public API ──


@dataclass(frozen=True)
class ScoredComponents:
    """The derived component scores plus one reason string per component."""

    scores: ComponentScores
    reasons: dict[str, str]


def score_components(
    card: ConceptCard,
    evidence_records: Sequence[ConceptEvidence],
    *,
    user_alignment: int = 0,
    hype: int | None = None,
) -> ScoredComponents:
    """Derive :class:`ComponentScores` (and per-component reasons) from a card.

    ``user_alignment`` must be supplied by the caller; it is never inferred from
    evidence and defaults to 0. ``hype`` may be supplied by the caller; when it
    is ``None`` the heuristic derives it from evidence notes. All other
    components are derived from the card and evidence records.
    """
    problem, problem_reason = _score_problem(evidence_records)
    evidence, evidence_reason = _score_evidence(evidence_records)
    reach, reach_reason = _score_reach(card, evidence_records)
    alignment, alignment_reason = _score_user_alignment(user_alignment)
    hype_score, hype_reason = _score_hype(card, evidence_records, hype)
    competition, competition_reason = _score_competition(card, evidence_records)

    scores = ComponentScores(
        problem=problem,
        evidence=evidence,
        reach=reach,
        user_alignment=alignment,
        hype=hype_score,
        competition=competition,
    )
    reasons = {
        "problem": problem_reason,
        "evidence": evidence_reason,
        "reach": reach_reason,
        "user_alignment": alignment_reason,
        "hype": hype_reason,
        "competition": competition_reason,
    }
    return ScoredComponents(scores=scores, reasons=reasons)


@dataclass(frozen=True)
class BuildGateResult:
    """Outcome of the hard build gate: passed plus the missing requirements."""

    passed: bool
    missing: tuple[str, ...]

    def __bool__(self) -> bool:
        return self.passed


def _counterevidence_reviewed(
    card: ConceptCard, records: Sequence[ConceptEvidence]
) -> tuple[bool, str]:
    """Whether any counterevidence on record has been reviewed/resolved.

    ``MaturityStage.CONTESTED`` is the model's explicit "counterevidence present
    and unresolved" state, so it is the one maturity value that fails this
    requirement. No counterevidence on record passes vacuously (nothing to
    review); counterevidence combined with any non-contested maturity is treated
    as reviewed.
    """
    counter = [e for e in records if e.role == EvidenceRole.COUNTER]
    if not counter:
        return True, "no counterevidence on record"
    if card.maturity != MaturityStage.CONTESTED:
        return True, (
            f"counterevidence present and resolved "
            f"(maturity '{card.maturity.value}')"
        )
    return False, "counterevidence present but unresolved (maturity is 'contested')"


def evaluate_build_gate(
    card: ConceptCard,
    evidence_records: Sequence[ConceptEvidence],
) -> BuildGateResult:
    """Evaluate the hard gates for advancing a concept to ``build``.

    Per the plan invariant, ``build`` requires four structural conditions, none
    of which is a threshold on ``total``:

    1. at least two source types,
    2. at least two independent supporting chains (counterevidence excluded),
    3. reviewed counterevidence (no counterevidence, or it is resolved), and
    4. a bounded smallest experiment (``card.smallest_experiment`` present).

    The result lists every missing requirement, so the caller can surface a
    precise, actionable reason rather than a bare pass/fail.
    """
    missing: list[str] = []

    source_types = {e.source_type for e in evidence_records}
    if len(source_types) < 2:
        missing.append(f"two source types (have {len(source_types)})")

    supporting = [e for e in evidence_records if e.role != EvidenceRole.COUNTER]
    chains = {e.independence_key for e in supporting}
    if len(chains) < 2:
        missing.append(f"two independent supporting chains (have {len(chains)})")

    reviewed, review_reason = _counterevidence_reviewed(card, evidence_records)
    if not reviewed:
        missing.append(f"reviewed counterevidence — {review_reason}")

    if card.smallest_experiment is None:
        missing.append("a bounded smallest experiment")

    return BuildGateResult(passed=not missing, missing=tuple(missing))


# ── Unified score + six named gates ──
#
# ``score()`` composes ``score_components()`` with an extended six-gate build
# check. ``score_components()`` and ``evaluate_build_gate()`` remain intact for
# backward compatibility; this section only *adds* a richer surface on top of
# them, so the CLI's existing four-gate behaviour is unchanged.

# Stable gate names — these are the public contract consumed by later waves
# (the cycle engine, the report renderer, and the Skill evals).
GATE_TWO_SOURCE_TYPES = "two_source_types"
GATE_TWO_INDEPENDENT_CHAINS = "two_independent_chains"
GATE_COUNTEREVIDENCE_REVIEWED = "counterevidence_reviewed"
GATE_SMALLEST_EXPERIMENT_PRESENT = "smallest_experiment_present"
GATE_EXPERIMENT_THRESHOLDS_AND_BUDGET = "experiment_thresholds_and_budget"
GATE_WEEKLY_BUILDS_AVAILABLE = "weekly_builds_available"

GATE_ORDER = (
    GATE_TWO_SOURCE_TYPES,
    GATE_TWO_INDEPENDENT_CHAINS,
    GATE_COUNTEREVIDENCE_REVIEWED,
    GATE_SMALLEST_EXPERIMENT_PRESENT,
    GATE_EXPERIMENT_THRESHOLDS_AND_BUDGET,
    GATE_WEEKLY_BUILDS_AVAILABLE,
)

# Human description per gate, so a caller can render a precise reason for any
# failed gate without re-deriving the check.
GATE_DESCRIPTIONS = {
    GATE_TWO_SOURCE_TYPES: "at least two source types",
    GATE_TWO_INDEPENDENT_CHAINS: "at least two independent evidence chains",
    GATE_COUNTEREVIDENCE_REVIEWED: "counterevidence reviewed",
    GATE_SMALLEST_EXPERIMENT_PRESENT: "smallest experiment present",
    GATE_EXPERIMENT_THRESHOLDS_AND_BUDGET: (
        "experiment contains success threshold, failure threshold, budget, "
        "and stop condition"
    ),
    GATE_WEEKLY_BUILDS_AVAILABLE: "current run has not exhausted weekly_builds",
}

# ``SmallestExperiment`` has no separate ``budget`` field: its ``stop_condition``
# is documented in ``models/concept.py`` as the "Bounded stop condition (time or
# cost budget) that ends the experiment". That is where the budget lives on the
# core a Build card must carry, so the budget sub-requirement is satisfied when
# ``stop_condition`` is non-blank. The richer ``experiments.models.Experiment``
# (which does carry a distinct ``budget`` field) is produced by the experiment
# generator in a later phase and is not the input to this scoring gate.
_EXPERIMENT_BUDGET_FIELDS = ("success_threshold", "failure_threshold", "stop_condition")


@dataclass(frozen=True)
class ScoreResult:
    """Unified scoring outcome: components, reasons, and named gate results.

    ``total`` mirrors ``components.total`` (the model-recomputed
    ``2P + 2E + R + A - 2H - C``). ``passed_gates`` and ``failed_gates`` list
    the names of the six hard build gates in the two partitions; a card must
    satisfy *all six* — a high ``total`` or high ``user_alignment`` never
    overrides a failed gate.
    """

    total: int
    components: ComponentScores
    reasons: dict[str, str]
    passed_gates: list[str]
    failed_gates: list[str]


def _evaluate_named_gates(
    card: ConceptCard,
    evidence_records: Sequence[ConceptEvidence],
    *,
    weekly_builds_used: int,
    weekly_builds_cap: int,
) -> tuple[list[str], list[str]]:
    """Evaluate the six hard build gates, returning (passed, failed) gate names.

    Deterministic and side-effect free. Gate names are stable constants (see
    ``GATE_ORDER``); the order of both lists follows ``GATE_ORDER``.
    """
    passed: list[str] = []
    failed: list[str] = []

    def check(name: str, ok: bool) -> None:
        (passed if ok else failed).append(name)

    source_types = {e.source_type for e in evidence_records}
    check(GATE_TWO_SOURCE_TYPES, len(source_types) >= 2)

    supporting = [e for e in evidence_records if e.role != EvidenceRole.COUNTER]
    chains = {e.independence_key for e in supporting}
    check(GATE_TWO_INDEPENDENT_CHAINS, len(chains) >= 2)

    reviewed, _ = _counterevidence_reviewed(card, evidence_records)
    check(GATE_COUNTEREVIDENCE_REVIEWED, reviewed)

    experiment = card.smallest_experiment
    check(GATE_SMALLEST_EXPERIMENT_PRESENT, experiment is not None)

    # success/failure thresholds + stop condition (the budget carrier) must all
    # be non-blank on the smallest experiment.
    thresholds_present = experiment is not None and all(
        bool(getattr(experiment, field, "").strip())
        for field in _EXPERIMENT_BUDGET_FIELDS
    )
    check(GATE_EXPERIMENT_THRESHOLDS_AND_BUDGET, thresholds_present)

    check(GATE_WEEKLY_BUILDS_AVAILABLE, weekly_builds_used < weekly_builds_cap)

    return passed, failed


def score(
    card: ConceptCard,
    evidence_records: Sequence[ConceptEvidence],
    *,
    user_alignment: int = 0,
    hype: int | None = None,
    weekly_builds_used: int = 0,
    weekly_builds_cap: int = 1,
) -> ScoreResult:
    """Score a card and evaluate all six hard build gates in one call.

    Composes :func:`score_components` (component integers + per-component
    reasons) with :func:`_evaluate_named_gates` (the six named build gates).
    ``total`` is ``components.total``, always recomputed by the model — it can
    never override a failed gate, and ``user_alignment`` can never satisfy a
    truth gate. ``weekly_builds_used < weekly_builds_cap`` is the last gate;
    when they are equal the current run has exhausted its weekly build budget.
    """
    scored = score_components(
        card, evidence_records, user_alignment=user_alignment, hype=hype
    )
    passed, failed = _evaluate_named_gates(
        card,
        evidence_records,
        weekly_builds_used=weekly_builds_used,
        weekly_builds_cap=weekly_builds_cap,
    )
    return ScoreResult(
        total=scored.scores.total,
        components=scored.scores,
        reasons=scored.reasons,
        passed_gates=passed,
        failed_gates=failed,
    )
