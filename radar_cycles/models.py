"""Radar-cycle domain models — the run/checkpoint contracts for a resumable radar.

A radar cycle is a state machine over named phases. The machine contract lives
here; persistence and the driving engine live in ``radar_cycles/checkpoint.py``
and ``radar_cycles/engine.py`` (later waves).

Design rules enforced structurally here:

- **Modes** are a closed set: ``daily``, ``weekly``, ``monthly``, ``full``,
  ``resume``.
- **Phase statuses** are a closed set with a strict transition table (see
  ``PhaseCheckpoint.ALLOWED_TRANSITIONS``): a phase starts ``pending``, moves to
  ``running``, then to a terminal status; ``partial``/``failed`` may retry once;
  ``blocked`` may resume only after changed input; ``completed`` is terminal.
- **Retry counts** are tracked per phase so a read-only retry cannot loop.
- **UTC-only timestamps** via the shared ``UtcDatetime`` contract from
  ``models.concept``.
- **``SourceCoverage``** is reused from ``models.radar_payload`` — it is not
  redefined here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, Field

from models.concept import UtcDatetime
from models.radar_payload import SourceCoverage, SourceStatus

__all__ = [
    "Mode",
    "PhaseName",
    "PhaseStatus",
    "Limits",
    "PhaseCheckpoint",
    "RadarCycleRun",
    "SourceCoverage",
    "SourceStatus",
]


class Mode(str, Enum):
    """How a radar cycle selects its phase sequence."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    FULL = "full"
    RESUME = "resume"


class PhaseStatus(str, Enum):
    """Lifecycle status of a single phase in a radar cycle."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class PhaseName(str, Enum):
    """The named phases a radar cycle can execute.

    ``x-discovery``, ``reddit-scan``, ``verify`` and ``source-audit`` are the
    source-producing phases; the rest are reduction/decision/reporting phases.
    """
    VALIDATE = "validate"
    X_DISCOVERY = "x-discovery"
    REDDIT_SCAN = "reddit-scan"
    REDUCE = "reduce"
    VERIFY = "verify"
    DECIDE = "decide"
    EXPERIMENT = "experiment"
    CALIBRATION = "calibration"
    SOURCE_AUDIT = "source-audit"
    REPORT = "report"


class Limits(BaseModel):
    """Daily and weekly build caps for one radar cycle."""
    daily_builds: int = Field(
        default=0,
        ge=0,
        description="Maximum Build decisions allowed per day",
    )
    weekly_builds: int = Field(
        default=0,
        ge=0,
        description="Maximum Build decisions allowed per week",
    )


class PhaseCheckpoint(BaseModel):
    """The current, resumable state of one radar cycle.

    Carries the config fingerprint (so a config change cannot silently alter an
    in-progress run), the mode, the daily/weekly caps, per-phase status and
    counts, the error list, and per-phase retry counts. Transitions are enforced
    by :meth:`transition`; construction never applies the transition rules
    (a loaded checkpoint may already hold any recorded status).
    """

    #: The only transitions the state machine permits. ``partial``/``failed``
    #: may retry (``running``) once, and ``blocked`` may return to ``running``
    #: only after changed input — both are guarded inside :meth:`transition`.
    ALLOWED_TRANSITIONS: ClassVar[dict[PhaseStatus, set[PhaseStatus]]] = {
        PhaseStatus.PENDING: {PhaseStatus.RUNNING},
        PhaseStatus.RUNNING: {
            PhaseStatus.COMPLETED,
            PhaseStatus.PARTIAL,
            PhaseStatus.BLOCKED,
            PhaseStatus.FAILED,
        },
        PhaseStatus.PARTIAL: {PhaseStatus.RUNNING},
        PhaseStatus.FAILED: {PhaseStatus.RUNNING},
        PhaseStatus.BLOCKED: {PhaseStatus.RUNNING},
        PhaseStatus.COMPLETED: set(),
    }

    config_fingerprint: str = Field(
        min_length=1,
        description="SHA-256 fingerprint of the normalized radar configuration",
    )
    mode: Mode = Field(description="Mode this checkpoint was started under")
    limits: Limits = Field(
        default_factory=Limits,
        description="Daily/weekly build caps for the run",
    )
    phases: dict[PhaseName, PhaseStatus] = Field(
        default_factory=dict,
        description="Per-phase state (phase name -> status)",
    )
    counts: dict[PhaseName, int] = Field(
        default_factory=dict,
        description="Per-phase item counts (e.g. evidence imported per phase)",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Errors recorded during the run",
    )
    retry_counts: dict[PhaseName, int] = Field(
        default_factory=dict,
        description="How many read-only retries each phase has used",
    )
    created_at: UtcDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the checkpoint was first created (UTC)",
    )
    updated_at: UtcDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the checkpoint was last updated (UTC)",
    )

    def status_of(self, phase: PhaseName | str) -> PhaseStatus:
        """Current status of ``phase``; ``pending`` when never recorded."""
        phase = PhaseName(phase)
        return self.phases.get(phase, PhaseStatus.PENDING)

    def transition(
        self,
        phase: PhaseName | str,
        new_status: PhaseStatus | str,
        *,
        allow_unblock: bool = False,
    ) -> "PhaseCheckpoint":
        """Apply an allowed transition to ``phase``, mutating and returning self.

        Enforces the plan's transition table:

        - ``pending -> running``;
        - ``running -> completed | partial | blocked | failed``;
        - ``partial | failed -> running`` exactly once (a read-only retry);
        - ``blocked -> running`` only with ``allow_unblock=True`` (changed
          input / user direction);
        - ``completed`` never returns to ``running``.

        ``phase`` and ``new_status`` may be passed as strings; they are coerced
        to the corresponding enums. An illegal transition raises ``ValueError``
        and leaves the checkpoint unchanged.
        """
        phase = PhaseName(phase)
        new_status = PhaseStatus(new_status)
        current = self.status_of(phase)

        if new_status == PhaseStatus.RUNNING:
            if current == PhaseStatus.PENDING:
                pass
            elif current in (PhaseStatus.PARTIAL, PhaseStatus.FAILED):
                retries = self.retry_counts.get(phase, 0)
                if retries >= 1:
                    raise ValueError(
                        f"phase {phase.value!r} already used its one read-only "
                        "retry; it cannot return to running again"
                    )
                self.retry_counts[phase] = retries + 1
            elif current == PhaseStatus.BLOCKED:
                if not allow_unblock:
                    raise ValueError(
                        f"phase {phase.value!r} is blocked; resuming requires "
                        "changed input or user direction (pass allow_unblock=True)"
                    )
            elif current == PhaseStatus.COMPLETED:
                raise ValueError(
                    f"phase {phase.value!r} is completed and cannot return to running"
                )
            elif current == PhaseStatus.RUNNING:
                raise ValueError(f"phase {phase.value!r} is already running")
            else:  # pragma: no cover - unreachable for the closed enum
                raise ValueError(
                    f"cannot transition phase {phase.value!r} from {current.value!r} to running"
                )
        elif new_status in (
            PhaseStatus.COMPLETED,
            PhaseStatus.PARTIAL,
            PhaseStatus.BLOCKED,
            PhaseStatus.FAILED,
        ):
            if current != PhaseStatus.RUNNING:
                raise ValueError(
                    f"cannot transition phase {phase.value!r} from "
                    f"{current.value!r} to {new_status.value!r}; it must be running"
                )
        elif new_status == PhaseStatus.PENDING:
            raise ValueError(f"phase {phase.value!r} cannot return to pending")
        else:  # pragma: no cover - unreachable for the closed enum
            raise ValueError(f"unknown phase status {new_status!r}")

        self.phases[phase] = new_status
        self.updated_at = datetime.now(timezone.utc)
        return self


class RadarCycleRun(BaseModel):
    """Metadata for one radar cycle, with its single current checkpoint.

    One current checkpoint per run: resuming rewrites the checkpoint in place
    (atomically, at the checkpoint-store layer) rather than appending history.
    """
    id: str = Field(min_length=1, description="Stable run ID")
    radar: str = Field(min_length=1, description="Radar name (e.g. 'agent-reliability')")
    mode: Mode = Field(description="Mode this run was started under")
    created_at: UtcDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the run was created (UTC)",
    )
    updated_at: UtcDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the run was last updated (UTC)",
    )
    checkpoint: PhaseCheckpoint = Field(
        description="The current checkpoint for this run",
    )
