"""Generate a bounded, falsifiable experiment from a validated concept card.

Pure function, no I/O. Fails closed: raises ``ExperimentGenerationError`` when
a success/failure threshold, a time/cost budget, a stop condition, or a minimal
artifact cannot be resolved from the inputs, instead of silently emitting a
vague placeholder or a feature backlog.
"""
from __future__ import annotations

from experiments.models import Experiment
from models.concept import ConceptCard, ConceptEvidence, EvidenceRole, SmallestExperiment


class ExperimentGenerationError(ValueError):
    """Raised when a bounded, falsifiable experiment cannot be generated."""


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def generate_experiment(
    card: ConceptCard,
    evidence: list[ConceptEvidence] | None = None,
    *,
    budget: str | None = None,
    evidence_to_collect: list[str] | None = None,
    confirmed_followup: str | None = None,
) -> Experiment:
    """Produce a bounded, falsifiable experiment from a concept card.

    The bounded, falsifiable core (hypothesis, target, minimal artifact,
    success/failure thresholds, stop condition) is reused from
    ``card.smallest_experiment``. ``budget`` is a required keyword argument
    because it has no honest default and is not present on a concept card;
    passing it explicitly is what makes the generator fail closed rather than
    invent a placeholder budget.

    ``evidence_to_collect`` and ``confirmed_followup`` may be passed explicitly
    or are derived deterministically from the inputs when omitted.
    """
    evidence = list(evidence) if evidence is not None else []

    smallest = card.smallest_experiment
    if smallest is None:
        raise ExperimentGenerationError(
            f"concept {card.id!r}: no smallest experiment is defined, so the "
            "success/failure thresholds and stop condition are absent; define a "
            "bounded smallest experiment before generating one."
        )

    # Defensive re-validation: the core may have been built without validation
    # (e.g. loaded leniently), so fail closed on any blank required field
    # rather than trusting it. This is where an absent threshold or stop
    # condition is surfaced.
    missing = [
        name
        for name, value in (
            ("hypothesis", smallest.hypothesis),
            ("target", smallest.target),
            ("artifact", smallest.artifact),
            ("success_threshold", smallest.success_threshold),
            ("failure_threshold", smallest.failure_threshold),
            ("stop_condition", smallest.stop_condition),
        )
        if _blank(value)
    ]
    if missing:
        raise ExperimentGenerationError(
            f"concept {card.id!r}: cannot generate an experiment — the smallest "
            f"experiment is missing required field(s): {', '.join(missing)}."
        )

    if smallest.success_threshold.strip() == smallest.failure_threshold.strip():
        raise ExperimentGenerationError(
            f"concept {card.id!r}: success and failure thresholds are identical "
            f"({smallest.success_threshold!r}); they must be distinct and "
            "observable for the hypothesis to be falsifiable."
        )

    if _blank(budget):
        raise ExperimentGenerationError(
            f"concept {card.id!r}: cannot generate an experiment without a "
            "time/cost budget; pass budget=... explicitly."
        )

    return Experiment(
        concept_id=card.id,
        core=smallest,
        evidence_to_collect=_resolve_evidence_to_collect(
            smallest, evidence, evidence_to_collect
        ),
        budget=budget.strip(),
        confirmed_followup=_resolve_followup(confirmed_followup),
    )


def _resolve_evidence_to_collect(
    smallest: SmallestExperiment,
    evidence: list[ConceptEvidence],
    explicit: list[str] | None,
) -> list[str]:
    if explicit is not None:
        cleaned = [item.strip() for item in explicit if item and item.strip()]
        if cleaned:
            return cleaned
    return _derive_evidence_to_collect(smallest, evidence)


def _derive_evidence_to_collect(
    smallest: SmallestExperiment,
    evidence: list[ConceptEvidence],
) -> list[str]:
    """Derive grounded evidence to collect: the measurements the thresholds
    require, plus any evidence role the concept is still missing."""
    lines = [
        f"record whether {smallest.target} meets the success threshold: "
        f"{smallest.success_threshold}",
        f"record any outcome that meets the failure threshold: "
        f"{smallest.failure_threshold}",
    ]
    present = {item.role for item in evidence}
    for role, label in (
        (EvidenceRole.PROBLEM, "problem evidence that the failure occurs for the target"),
        (EvidenceRole.IMPLEMENTATION, "implementation evidence that the artifact works end to end"),
        (EvidenceRole.ADOPTION, "adoption evidence that real users act on the artifact"),
    ):
        if role not in present:
            lines.append(label)
    return lines


def _resolve_followup(explicit: str | None) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()
    return _derive_followup()


def _derive_followup() -> str:
    """A deterministic, grounded next step when the hypothesis is confirmed."""
    return (
        "if confirmed, advance the concept by running the next smallest increment "
        "against a larger or harder target, and record the confirmed outcome and "
        "lesson on the concept card."
    )
