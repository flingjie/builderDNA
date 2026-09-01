"""Richer, runnable experiment model produced by the smallest-experiment generator.

Relationship to ``SmallestExperiment``
--------------------------------------
``models/concept.py`` already defines ``SmallestExperiment`` as the bounded,
falsifiable *core* a card must carry before it may reach Build: hypothesis,
target, minimal artifact, success/failure thresholds, and a stop condition.

``Experiment`` is a clear superset that *composes* that core rather than
duplicating it. It reuses ``SmallestExperiment`` via the ``core`` field and
adds the three things the lifecycle needs to actually run an experiment and
close the loop:

- ``evidence_to_collect`` — the observable data the experiment records to
  evaluate the success/failure thresholds.
- ``budget`` — the time/cost allocation committed to the run.
- ``confirmed_followup`` — the next bounded action if the hypothesis is confirmed.

Composition keeps the two models consistent: ``SmallestExperiment`` stays the
bounded, falsifiable essence a Build card must already carry, while
``Experiment`` is the fuller operational record produced at generation time.
``stop_condition`` (the rule that ends evidence collection) and ``budget`` (the
resource allocation) are kept distinct here even though both concern limits:
a budget is the committed resource, a stop condition is the termination rule
that fires when the budget or a sample bound is reached.

``Experiment`` also enforces the falsifiability invariants the generator
depends on: a non-blank minimal artifact, and distinct success/failure
thresholds.
"""
from pydantic import BaseModel, Field, field_validator, model_validator

from models.concept import SmallestExperiment


class Experiment(BaseModel):
    """A bounded, falsifiable experiment derived from a validated concept card.

    Composes the ``SmallestExperiment`` core (hypothesis / target / minimal
    artifact / success and failure thresholds / stop condition) and adds the
    operational fields needed to run the experiment and follow up on its
    outcome.
    """

    concept_id: str = Field(
        min_length=1,
        description="Stable concept ID this experiment tests",
    )
    core: SmallestExperiment = Field(
        description="The bounded, falsifiable core reused from the concept card",
    )
    evidence_to_collect: list[str] = Field(
        min_length=1,
        description="Observable data the experiment records to evaluate the thresholds",
    )
    budget: str = Field(
        min_length=1,
        description="Time/cost budget committed to the run",
    )
    confirmed_followup: str = Field(
        min_length=1,
        description="Next bounded action if the hypothesis is confirmed",
    )

    @field_validator("budget", "confirmed_followup")
    @classmethod
    def _reject_blank_string(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("evidence_to_collect")
    @classmethod
    def _reject_blank_items(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError(
                "evidence_to_collect must contain at least one non-empty item"
            )
        return cleaned

    @model_validator(mode="after")
    def _require_minimal_artifact(self) -> "Experiment":
        if not self.core.artifact.strip():
            raise ValueError(
                "a smallest experiment must expose a minimal artifact, not a "
                "feature backlog; provide a concrete, smallest artifact"
            )
        return self

    @model_validator(mode="after")
    def _require_distinct_thresholds(self) -> "Experiment":
        if self.core.success_threshold.strip() == self.core.failure_threshold.strip():
            raise ValueError(
                "success and failure thresholds must be distinct and observable "
                "for the hypothesis to be falsifiable"
            )
        return self
