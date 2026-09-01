"""Source handoff envelope — the inter-phase contract for source workflows.

A specialist skill (X learning, Reddit scanning, GitHub verification, paper/doc
verification) produces one envelope per source phase. The Python engine imports
the envelope, validates every item atomically (one invalid item rejects the whole
handoff), and only then normalizes items into ``ConceptEvidence``.

Envelope contract (plan Task 6):

.. code-block:: json

    {
      "schema_version": 1,
      "source_phase": "x-discovery",
      "coverage": "partial",
      "coverage_notes": ["X thread replies unavailable"],
      "items": []
    }

Source rules enforced structurally here:

- **Unknown ``schema_version`` is rejected** — the envelope is pinned to ``1``.
- **Missing provenance is rejected** — a ``url`` or ``upstream_origin`` must be
  present when ``directness != inferred``; equivalently, manual inference must
  remain ``directness=inferred``.
- **Paper / official-doc novelty claims require a primary-source ``url``.**
- ``source_phase``, ``coverage``, item ``source``/``role``/``directness``/
  ``strength``, and timestamps are all validated against closed enums and the
  UTC-only timestamp contract.

The content/signal-type rules (X defaults to a discovery role, Reddit RSS
cannot imply comment consensus, GitHub stars/velocity cannot become adoption)
are enforced by :func:`normalize_handoff` below — the normalization layer this
module also provides — because they depend on content and signal type, not
envelope shape.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from concepts.store import ConceptStore, ConflictError
from models.concept import (
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    SourceType,
    UtcDatetime,
)

__all__ = [
    "SourcePhase",
    "CoverageStatus",
    "ProposedConcept",
    "SourceHandoffItem",
    "SourceHandoffEnvelope",
    "ImportResult",
    "UNASSIGNED_CONCEPT_ID",
    "normalize_handoff",
    "import_handoff",
]


class SourcePhase(str, Enum):
    """The phases that produce a source handoff.

    Mirrors the source-producing members of ``radar_cycles.models.PhaseName``.
    (The CLI layer may alias ``verification`` to ``verify``; this enum keeps the
    canonical phase name.)
    """
    X_DISCOVERY = "x-discovery"
    REDDIT_SCAN = "reddit-scan"
    VERIFY = "verify"
    SOURCE_AUDIT = "source-audit"


class CoverageStatus(str, Enum):
    """Coverage of one source handoff as a whole."""
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class ProposedConcept(BaseModel):
    """A lightweight concept suggestion carried by a handoff item.

    Becomes a ``ConceptCard`` on capture (the engine assigns the stable ID and
    portfolio stage); only the identity and problem fields travel in the handoff.
    """
    title: str = Field(min_length=1, description="Display name of the proposed concept")
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names the concept has been captured under",
    )
    problem: str = Field(
        default="",
        description="The job or failure the concept addresses",
    )
    why_now: str = Field(
        default="",
        description="What changed that makes this worth acting on now",
    )


class SourceHandoffItem(BaseModel):
    """One source record, paraphrased and normalized enough to become evidence.

    ``excerpt`` is the note-taker's paraphrase (never a verbatim scrape of
    protected content). Provenance is carried by ``url`` (the item's own source)
    and/or ``upstream_origin`` (the primary claim this item cites/reposts);
    ``independence_key`` groups reposts of one upstream claim so recurrence is
    not inflated.
    """
    source: SourceType = Field(description="Where this record came from")
    role: EvidenceRole = Field(
        description="Role this record plays: problem, implementation, adoption, or counterevidence",
    )
    author: str = Field(default="", description="Author / actor handle")
    url: str = Field(default="", description="URL of this record, when available")
    published_at: UtcDatetime | None = Field(
        default=None,
        description="When the record was published (UTC), when known",
    )
    excerpt: str = Field(
        min_length=1,
        description="Paraphrased excerpt of the claim",
    )
    directness: Directness = Field(
        description="How directly the source speaks to the claim",
    )
    strength: EvidenceStrength = Field(
        description="How strong the source is as evidence",
    )
    upstream_origin: str | None = Field(
        default=None,
        description="The primary claim this record cites or reposts, when known",
    )
    independence_key: str | None = Field(
        default=None,
        description="Explicit grouping key; derived from upstream_origin/url when omitted",
    )
    topics: list[str] = Field(
        default_factory=list,
        description="Topic tags for this record",
    )
    proposed_concept: ProposedConcept | None = Field(
        default=None,
        description="Optional concept suggestion derived from this record",
    )

    @model_validator(mode="after")
    def _enforce_provenance(self) -> "SourceHandoffItem":
        url = self.url.strip()
        upstream = (self.upstream_origin or "").strip()

        if self.directness != Directness.INFERRED and not url and not upstream:
            raise ValueError(
                "a url or upstream_origin is required when directness is "
                f"{self.directness.value!r}; manual inference must remain "
                "directness='inferred'"
            )

        if self.source in (SourceType.PAPER, SourceType.OFFICIAL_DOC) and not url:
            raise ValueError(
                f"{self.source.value} novelty claims require a primary-source url"
            )

        return self


class SourceHandoffEnvelope(BaseModel):
    """One validated source handoff from a specialist skill to the engine.

    ``schema_version`` is pinned to ``1``; an unknown version is rejected so the
    engine never silently misinterprets a newer contract.
    """
    schema_version: Literal[1] = Field(
        description="Handoff contract version; only 1 is accepted",
    )
    source_phase: SourcePhase = Field(
        description="Which radar phase produced this handoff",
    )
    coverage: CoverageStatus = Field(
        description="Whether this source phase's coverage was complete, partial, or unavailable",
    )
    coverage_notes: list[str] = Field(
        default_factory=list,
        description="Explicit coverage gaps (e.g. 'comments not read')",
    )
    items: list[SourceHandoffItem] = Field(
        default_factory=list,
        description="Normalized source records; one invalid item rejects the whole envelope",
    )


# ── Normalization + atomic import (plan Task 6) ──

UNASSIGNED_CONCEPT_ID = "unassigned"
"""Placeholder ``concept_id`` for handoff items that carry no ``proposed_concept``.

Verification items (GitHub / paper / official doc) attach to an *existing*
concept the envelope does not name — the capture/matching layer assigns the real
card ID later. The store still needs a non-empty, stable ``concept_id`` so
evidence can be imported atomically and replayed idempotently.
"""

_COMMENTS_NOT_READ_MARKER = "comments not read"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(title: str) -> str:
    """Derive a stable concept-ID slug from a display title."""
    norm = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return norm or "concept"


def _normalize_url(url: str) -> str:
    """Lowercase a URL, strip scheme/www, and drop the trailing slash."""
    out = (url or "").strip().lower()
    out = re.sub(r"^https?://", "", out)
    out = re.sub(r"^www\.", "", out)
    return out.rstrip("/")


def _content_digest(item: SourceHandoffItem) -> str:
    """Deterministic content hash for URL-less items (author + excerpt)."""
    payload = f"{item.author}|{item.excerpt}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


def _concept_id_for(item: SourceHandoffItem) -> str:
    proposed = item.proposed_concept
    if proposed is not None and proposed.title.strip():
        return _slugify(proposed.title)
    return UNASSIGNED_CONCEPT_ID


def _evidence_id_for(item: SourceHandoffItem) -> str:
    """Stable evidence ID: normalized URL, else an author|excerpt content hash."""
    url = item.url.strip()
    if url:
        return f"{item.source.value}:{_normalize_url(url)}"
    return f"{item.source.value}:{_content_digest(item)}"


def _independence_key_for(item: SourceHandoffItem) -> str:
    """Derive ``independence_key`` from upstream_origin -> url -> content hash.

    Reposts of one upstream claim share the upstream key; a first-hand item keys
    off its own URL; a URL-less inference keys off a content hash. An explicit
    ``independence_key`` on the item wins.
    """
    explicit = (item.independence_key or "").strip()
    if explicit:
        return explicit
    upstream = (item.upstream_origin or "").strip()
    if upstream:
        return f"upstream:{_normalize_url(upstream)}"
    url = item.url.strip()
    if url:
        return f"{item.source.value}:{_normalize_url(url)}"
    return f"{item.source.value}:hash:{_content_digest(item)}"


def _github_owner(url: str) -> str:
    match = re.search(r"github\.com/([^/?#]+)", url or "", re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _github_has_external_use(item: SourceHandoffItem) -> bool:
    """External-use evidence: a non-empty author who is not the repo owner.

    Stars/velocity signals carry no actor at all, so an empty author (or the
    repo owner themself) is not external use.
    """
    author = (item.author or "").strip()
    if not author:
        return False
    owner = _github_owner(item.url or "")
    return not owner or author.lower() != owner


def _build_note(item: SourceHandoffItem, extra_gaps: list[str]) -> str:
    """Paraphrased excerpt plus explicit ``[coverage gap: ...]`` annotations."""
    parts: list[str] = []
    if item.excerpt.strip():
        parts.append(item.excerpt.strip())
    gaps = list(extra_gaps)
    if not item.author.strip():
        gaps.append("author unknown")
    if not item.url.strip():
        gaps.append("source URL unknown")
    if gaps:
        parts.append("[coverage gap: " + "; ".join(gaps) + "]")
    return "\n".join(parts)


def _normalize_item(item: SourceHandoffItem) -> ConceptEvidence:
    """Apply the plan's source rules to one validated handoff item."""
    role = item.role
    directness = item.directness
    strength = item.strength
    extra_gaps: list[str] = []

    # X-learning defaults to a discovery/problem role unless it links first-hand
    # evidence (a url or upstream_origin, which makes it more direct/strong).
    if item.source == SourceType.X:
        has_first_hand = bool(item.url.strip()) or bool(
            (item.upstream_origin or "").strip()
        )
        if not has_first_hand:
            role = EvidenceRole.PROBLEM
            directness = Directness.INFERRED
            strength = EvidenceStrength.WEAK

    # Reddit RSS is L1 (direct) but must record "comments not read" and must
    # never be described as community consensus (an adoption role).
    if item.source == SourceType.REDDIT:
        if _COMMENTS_NOT_READ_MARKER not in item.excerpt.lower():
            extra_gaps.append(_COMMENTS_NOT_READ_MARKER)
        if role == EvidenceRole.ADOPTION:
            role = EvidenceRole.PROBLEM

    # GitHub stars/velocity cannot become adoption without external-use evidence.
    if item.source == SourceType.GITHUB:
        if role == EvidenceRole.ADOPTION and not _github_has_external_use(item):
            role = EvidenceRole.IMPLEMENTATION

    # Manual inference must stay directness=inferred.
    if item.source == SourceType.MANUAL:
        directness = Directness.INFERRED

    return ConceptEvidence(
        id=_evidence_id_for(item),
        concept_id=_concept_id_for(item),
        source_type=item.source,
        source_url=item.url,
        role=role,
        directness=directness,
        strength=strength,
        independence_key=_independence_key_for(item),
        note=_build_note(item, extra_gaps),
        captured_at=_now(),
    )


def normalize_handoff(
    envelope: SourceHandoffEnvelope | dict,
) -> list[ConceptEvidence]:
    """Normalize every item of a handoff into ``ConceptEvidence``.

    Accepts a validated :class:`SourceHandoffEnvelope` or a raw dict (validated
    here first, so a structurally invalid item raises ``ValidationError`` before
    any record is produced). Source limitations are baked into the resulting
    evidence: X defaults to discovery/problem, Reddit records "comments not
    read" and is never consensus/adoption, GitHub stars/velocity stays
    implementation, manual inference stays inferred, and repost chains collapse
    to one ``independence_key``. Paper / official-doc primary-source URL is
    enforced by the envelope validator above.
    """
    if isinstance(envelope, dict):
        envelope = SourceHandoffEnvelope.model_validate(envelope)
    return [_normalize_item(item) for item in envelope.items]


@dataclass(frozen=True)
class ImportResult:
    """Outcome of one atomic handoff import."""

    imported: int
    skipped_idempotent: int
    conflicts: list[str] = field(default_factory=list)
    concept_ids_affected: list[str] = field(default_factory=list)


def import_handoff(
    store: ConceptStore, envelope: SourceHandoffEnvelope | dict
) -> ImportResult:
    """Normalize a handoff and import all valid records atomically.

    Normalization (including structural validation of a raw dict) completes
    before any write, so one structurally invalid item rejects the whole handoff
    with no partial writes. Per-record import uses the store's idempotent-replay
    semantics: an identical replay imports nothing new, and a same-ID/different-
    payload record is reported as a conflict rather than raised.
    """
    records = normalize_handoff(envelope)

    # Atomicity: pre-check every record for a same-ID/different-payload conflict
    # against the store BEFORE writing anything, so a conflicted handoff imports
    # nothing (no partial write), per the plan's "import all valid records
    # atomically per handoff".
    conflicts = store.evidence_conflicts(records)
    if conflicts:
        return ImportResult(
            imported=0,
            skipped_idempotent=0,
            conflicts=conflicts,
            concept_ids_affected=sorted({r.concept_id for r in records}),
        )

    imported = 0
    skipped = 0

    for record in records:
        try:
            stored = store.add_evidence(record)
        except ConflictError as exc:
            # Intra-handoff duplicate ID (rare); the pre-check already covered
            # conflicts against pre-existing store data.
            conflicts.append(str(exc))
            continue
        # ``add_evidence`` returns the input record on a fresh append and the
        # pre-existing record on an idempotent replay.
        if stored is record:
            imported += 1
        else:
            skipped += 1

    return ImportResult(
        imported=imported,
        skipped_idempotent=skipped,
        conflicts=conflicts,
        concept_ids_affected=sorted({r.concept_id for r in records}),
    )
