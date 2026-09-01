"""Export an FDE-Gym scenario proposal from a validated concept card.

FDE-Gym (Failure-Driven Environments) is a benchmark where an agent is dropped
into a simulated environment that reproduces a real, observed failure mode. A
scenario encodes the environment, the agent's visible goal, the hidden
constraints the agent is not told about, the observable success criteria, a
concrete counterexample where naive behaviour fails, and the reset/replay
requirements that make the scenario deterministic.

This module produces a *proposal*, not a mutation: it is a pure function that
returns a serializable, versioned model. Nothing here writes to FDE-Gym or any
other external system, so a human can review the proposal before it is
committed upstream.

Design rules enforced structurally here:

- **Link evidence, never copy prose.** The proposal carries ``concept_id`` and
  ``evidence_ids`` and deliberately does not inline raw evidence text. The
  observed pain comes from the concept card's own ``problem`` field; anything
  that needs source context is referenced by evidence ID. The export can
  additionally verify (when evidence records are supplied) that every linked ID
  actually resolves, so a proposal cannot ship a dangling reference.
- **Compose the ``Experiment``, not a duplicate.** The bounded, falsifiable
  core already lives on ``experiments.models.Experiment`` (from Task 5.1). The
  smallest prototype and success criteria are taken from that core when an
  ``Experiment`` is available, falling back to the card's ``SmallestExperiment``.
- **Fail closed.** Semantic scenario fields with no honest default (failure
  mode, environment, agent goal, hidden constraints, counterexample, and
  replay/reset requirements) must be supplied explicitly; the export raises
  ``ScenarioExportError`` rather than inventing a placeholder.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from experiments.models import Experiment
from models.concept import ConceptCard, ConceptEvidence, SmallestExperiment


class ScenarioExportError(ValueError):
    """Raised when an FDE-Gym scenario proposal cannot be exported."""


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


class FdeGymScenarioProposal(BaseModel):
    """A reviewable, versioned FDE-Gym scenario proposal.

    JSON-first: every field is a plain string or list of strings, so the
    proposal serializes and reconstructs without loss. ``schema_version`` lets a
    reviewer detect which contract a proposal was produced under.
    """

    schema_version: str = Field(
        default="1.0",
        description="Version of the FDE-Gym scenario proposal contract",
    )
    concept_id: str = Field(
        min_length=1,
        description="Stable concept ID this scenario is derived from",
    )
    scenario_name: str = Field(
        min_length=1,
        description="Human-readable name of the scenario",
    )
    observed_pain: str = Field(
        min_length=1,
        description="The job or failure the concept addresses (the card's problem statement)",
    )
    evidence_ids: list[str] = Field(
        min_length=1,
        description="IDs of ConceptEvidence records backing the scenario — linked, not copied",
    )
    failure_mode: str = Field(
        min_length=1,
        description="The specific failure the simulated environment reproduces",
    )
    environment: str = Field(
        min_length=1,
        description="The simulated environment the agent operates in (state, tools, feedback)",
    )
    agent_goal: str = Field(
        min_length=1,
        description="The visible goal/instruction given to the agent in the scenario",
    )
    hidden_constraints: list[str] = Field(
        min_length=1,
        description="Constraints the agent must satisfy but is not told about",
    )
    success_criteria: list[str] = Field(
        min_length=1,
        description="Observable criteria that determine scenario success",
    )
    counterexample: str = Field(
        min_length=1,
        description="A concrete case where naive behaviour exhibits the failure mode",
    )
    replay_reset_requirements: str = Field(
        min_length=1,
        description="How the scenario resets and replays deterministically",
    )
    smallest_prototype: str = Field(
        min_length=1,
        description="The minimal prototype/artifact the scenario exercises",
    )

    @field_validator(
        "schema_version",
        "concept_id",
        "scenario_name",
        "observed_pain",
        "failure_mode",
        "environment",
        "agent_goal",
        "counterexample",
        "replay_reset_requirements",
        "smallest_prototype",
    )
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("evidence_ids", "hidden_constraints", "success_criteria")
    @classmethod
    def _reject_blank_items(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("must contain at least one non-empty item")
        return cleaned

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the proposal to JSON (the canonical reviewable form)."""
        return self.model_dump_json(indent=indent)


def export_fde_gym_scenario(
    card: ConceptCard,
    evidence: list[ConceptEvidence] | None = None,
    experiment: Experiment | None = None,
    *,
    scenario_name: str | None = None,
    failure_mode: str | None = None,
    environment: str | None = None,
    agent_goal: str | None = None,
    hidden_constraints: list[str] | None = None,
    success_criteria: list[str] | None = None,
    counterexample: str | None = None,
    replay_reset_requirements: str | None = None,
    smallest_prototype: str | None = None,
) -> FdeGymScenarioProposal:
    """Produce a reviewable FDE-Gym scenario proposal from a concept card.

    Derives what is deterministically derivable and fails closed on the rest:

    - ``concept_id``, ``observed_pain`` (``card.problem``) and ``evidence_ids``
      (``card.evidence_ids``) come from the card; the export links evidence by
      ID and never inlines evidence text.
    - ``smallest_prototype`` and ``success_criteria`` prefer the bounded core on
      the supplied ``Experiment``, falling back to the card's
      ``SmallestExperiment``.
    - ``scenario_name`` defaults to the card title.
    - ``failure_mode``, ``environment``, ``agent_goal``, ``hidden_constraints``,
      ``counterexample`` and ``replay_reset_requirements`` describe the
      simulation and have no honest default, so they must be passed explicitly.

    ``evidence``, when provided, lets the export verify that every linked
    ``evidence_id`` resolves to a real record; a dangling ID raises
    ``ScenarioExportError``.
    """
    evidence_ids = _resolve_evidence_ids(card, evidence)

    problem = card.problem.strip()
    if not problem:
        raise ScenarioExportError(
            f"concept {card.id!r}: cannot export an FDE-Gym scenario without an "
            "observed pain; the concept card's `problem` field is empty."
        )

    name = (scenario_name if scenario_name is not None else card.title).strip()
    if not name:
        name = f"{card.id} scenario"

    smallest = card.smallest_experiment
    core = experiment.core if experiment is not None else None

    return FdeGymScenarioProposal(
        concept_id=card.id,
        scenario_name=name,
        observed_pain=problem,
        evidence_ids=evidence_ids,
        failure_mode=_resolve_required("failure_mode", failure_mode, card.id),
        environment=_resolve_required("environment", environment, card.id),
        agent_goal=_resolve_required("agent_goal", agent_goal, card.id),
        hidden_constraints=_resolve_required_list(
            "hidden_constraints", hidden_constraints, card.id
        ),
        success_criteria=_resolve_success_criteria(
            success_criteria, core, smallest, card.id
        ),
        counterexample=_resolve_required("counterexample", counterexample, card.id),
        replay_reset_requirements=_resolve_required(
            "replay_reset_requirements", replay_reset_requirements, card.id
        ),
        smallest_prototype=_resolve_smallest_prototype(
            smallest_prototype, core, smallest, card.id
        ),
    )


def _resolve_evidence_ids(
    card: ConceptCard,
    evidence: list[ConceptEvidence] | None,
) -> list[str]:
    ids = [item.strip() for item in card.evidence_ids if item and item.strip()]
    if not ids:
        raise ScenarioExportError(
            f"concept {card.id!r}: cannot export an FDE-Gym scenario without "
            "linked evidence; the card must reference at least one evidence ID "
            "(card.evidence_ids). The export links evidence rather than copying "
            "unverifiable prose."
        )
    if evidence is not None:
        available = {item.id for item in evidence}
        missing = [item for item in ids if item not in available]
        if missing:
            raise ScenarioExportError(
                f"concept {card.id!r}: evidence IDs {missing} are not present in "
                "the provided evidence records; the export links evidence by ID "
                "and cannot ship a dangling reference."
            )
    return ids


def _resolve_required(name: str, value: str | None, card_id: str) -> str:
    if _blank(value):
        raise ScenarioExportError(
            f"concept {card_id!r}: cannot export an FDE-Gym scenario without a "
            f"{name}; pass {name}=... explicitly."
        )
    return value.strip()


def _resolve_required_list(
    name: str, value: list[str] | None, card_id: str
) -> list[str]:
    if value is None:
        raise ScenarioExportError(
            f"concept {card_id!r}: cannot export an FDE-Gym scenario without "
            f"{name}; pass {name}=[...] explicitly."
        )
    cleaned = [item.strip() for item in value if item and item.strip()]
    if not cleaned:
        raise ScenarioExportError(
            f"concept {card_id!r}: {name} must contain at least one non-empty item."
        )
    return cleaned


def _resolve_smallest_prototype(
    explicit: str | None,
    core: SmallestExperiment | None,
    smallest: SmallestExperiment | None,
    card_id: str,
) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()
    if core is not None and core.artifact.strip():
        return core.artifact.strip()
    if smallest is not None and smallest.artifact.strip():
        return smallest.artifact.strip()
    raise ScenarioExportError(
        f"concept {card_id!r}: cannot export an FDE-Gym scenario without a "
        "smallest prototype; pass smallest_prototype=... or provide an "
        "Experiment/card whose core carries a minimal artifact."
    )


def _resolve_success_criteria(
    explicit: list[str] | None,
    core: SmallestExperiment | None,
    smallest: SmallestExperiment | None,
    card_id: str,
) -> list[str]:
    if explicit is not None:
        cleaned = [item.strip() for item in explicit if item and item.strip()]
        if cleaned:
            return cleaned
    if core is not None and core.success_threshold.strip():
        return [core.success_threshold.strip()]
    if smallest is not None and smallest.success_threshold.strip():
        return [smallest.success_threshold.strip()]
    raise ScenarioExportError(
        f"concept {card_id!r}: cannot export an FDE-Gym scenario without "
        "success criteria; pass success_criteria=[...] or provide an "
        "Experiment/card whose core carries a success threshold."
    )
