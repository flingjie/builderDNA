"""Radar run payloads — structured run summaries from which Markdown is rendered.

A radar run scans one configured radar across its sources and updates concept
cards. The payload records, per source, whether the source was complete, partial,
unavailable, or not requested, plus the cards affected by the run.
"""
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from models.concept import SourceType, UtcDatetime


class SourceStatus(str, Enum):
    """Coverage status of one source type in a radar run."""
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    NOT_REQUESTED = "not_requested"


class SourceCoverage(BaseModel):
    """Coverage status for one source type in a radar run."""
    source_type: SourceType = Field(description="Source type covered by this run")
    status: SourceStatus = Field(
        description="complete, partial, unavailable, or not requested",
    )
    note: str = Field(
        default="",
        description="What was covered, or the explicit gap when partial/unavailable",
    )


class RadarRunPayload(BaseModel):
    """A structured run summary from which Markdown is rendered.

    Records, per source, whether the source was complete, partial, unavailable,
    or not requested, plus the cards affected by the run. A partial source
    failure yields a usable partial run with explicit gaps — it never silently
    substitutes another source.
    """
    radar: str = Field(min_length=1, description="Radar name (e.g. 'agent-reliability')")
    period: str = Field(
        default="",
        description="Review period label, e.g. '2026-W36'",
    )
    run_at: UtcDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this run executed (UTC)",
    )
    sources: list[SourceCoverage] = Field(
        default_factory=list,
        description="Per-source coverage status for this run",
    )
    cards_affected: list[str] = Field(
        default_factory=list,
        description="IDs of concept cards affected by this run",
    )
    summary: str = Field(
        default="",
        description="Human-readable run summary",
    )
    gaps: list[str] = Field(
        default_factory=list,
        description="Explicit source gaps discovered during the run",
    )
