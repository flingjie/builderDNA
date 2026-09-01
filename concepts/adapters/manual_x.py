"""Manual X capture adapter — normalize hand-curated X posts into ``ConceptEvidence``.

Bridges a manually captured X post (URL, author, user note, quoted-source URL,
optional upstream origin) into the immutable ``ConceptEvidence`` model. This is
the first-release path for X evidence; automated X collection is deferred until
100-200 curated captures reveal useful query patterns.

Directness mapping (plan's L1/L2/L3 -> ``Directness``, by INTENT not label):

- primary first-hand source -> ``Directness.DIRECT``: the note contains a
  verbatim quote of primary content, or the capture IS the primary source.
- second-hand report / repost / summary -> ``Directness.INDIRECT``: the note
  links (but does not quote) a primary source.
- note-taker inference with no primary link -> ``Directness.INFERRED``: the
  default for a manual note that neither quotes nor links primary content.

Repost chains share an ``independence_key`` when the upstream source is known
(derived from the quoted/upstream URL); otherwise the note keys off its own URL.
Unavailable fields are stored as unknown (``""``) and the coverage gap is
recorded explicitly in ``note``.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from models.concept import (
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    SourceType,
)
from signals.models import Signal

# ── Free-form string hints -> strict enums (Signal nullable fields) ─────────

_ROLE_HINT: dict[str, EvidenceRole] = {
    "problem": EvidenceRole.PROBLEM,
    "attempted_solution": EvidenceRole.PROBLEM,
    "implementation": EvidenceRole.IMPLEMENTATION,
    "adoption": EvidenceRole.ADOPTION,
    "validation": EvidenceRole.ADOPTION,
    "counterexample": EvidenceRole.COUNTER,
    "counterevidence": EvidenceRole.COUNTER,
    "counter": EvidenceRole.COUNTER,
}

_DIRECTNESS_HINT: dict[str, Directness] = {
    "direct": Directness.DIRECT,
    "primary": Directness.DIRECT,
    "l1": Directness.DIRECT,
    "first_hand": Directness.DIRECT,
    "first-hand": Directness.DIRECT,
    "indirect": Directness.INDIRECT,
    "secondary": Directness.INDIRECT,
    "l2": Directness.INDIRECT,
    "derived": Directness.INDIRECT,
    "second_hand": Directness.INDIRECT,
    "second-hand": Directness.INDIRECT,
    "repost": Directness.INDIRECT,
    "summary": Directness.INDIRECT,
    "inferred": Directness.INFERRED,
    "inference": Directness.INFERRED,
    "note": Directness.INFERRED,
    "l3": Directness.INFERRED,
}

_STRENGTH_HINT: dict[str, EvidenceStrength] = {
    "weak": EvidenceStrength.WEAK,
    "low": EvidenceStrength.WEAK,
    "moderate": EvidenceStrength.MODERATE,
    "medium": EvidenceStrength.MODERATE,
    "strong": EvidenceStrength.STRONG,
    "high": EvidenceStrength.STRONG,
}

# A verbatim quote is detected as a pair of straight or curly double quotes
# containing at least a few characters of quoted primary content.
_QUOTE_RE = re.compile(r'"[^"]{3,}"|“[^”]{3,}”')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_url(url: str) -> str:
    out = url.strip().lower()
    out = re.sub(r"^https?://", "", out)
    out = re.sub(r"^www\.", "", out)
    return out.rstrip("/")


def _role_from_hint(value, default: EvidenceRole) -> EvidenceRole:
    if value is None:
        return default
    if isinstance(value, EvidenceRole):
        return value
    return _ROLE_HINT.get(str(value).strip().lower(), default)


def _directness_from_hint(value) -> Directness | None:
    if value is None:
        return None
    if isinstance(value, Directness):
        return value
    return _DIRECTNESS_HINT.get(str(value).strip().lower())


def _strength_from_hint(value, default: EvidenceStrength) -> EvidenceStrength:
    if value is None:
        return default
    if isinstance(value, EvidenceStrength):
        return value
    if isinstance(value, str):
        return _STRENGTH_HINT.get(value.strip().lower(), default)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if f <= 0.33:
        return EvidenceStrength.WEAK
    if f <= 0.66:
        return EvidenceStrength.MODERATE
    return EvidenceStrength.STRONG


def _has_verbatim_quote(note: str) -> bool:
    return bool(_QUOTE_RE.search(note or ""))


def infer_directness(note: str, quoted_source_url: str | None) -> Directness:
    """A manual note is INFERRED unless it quotes or links primary content.

    - no quoted source -> INFERRED (note-taker inference, no primary link)
    - verbatim quote of primary content -> DIRECT
    - links but does not quote -> INDIRECT (second-hand pointer to primary)
    """
    if not quoted_source_url:
        return Directness.INFERRED
    if _has_verbatim_quote(note):
        return Directness.DIRECT
    return Directness.INDIRECT


def _default_strength(directness: Directness) -> EvidenceStrength:
    if directness is Directness.DIRECT:
        return EvidenceStrength.MODERATE
    return EvidenceStrength.WEAK


def independence_key(
    *,
    url: str = "",
    quoted_source_url: str | None = None,
    upstream_origin: str | None = None,
    source_type: SourceType = SourceType.X,
) -> str:
    """Repost chains share a key when the upstream source is known.

    The anchor is the upstream origin when known, else the quoted source, else
    the note's own URL — so reposts/citations of one claim collapse to a single
    independent chain rather than inflating recurrence.
    """
    anchor = upstream_origin or quoted_source_url or url
    return f"{source_type.value}:{_normalize_url(anchor)}"


def _evidence_id(
    *,
    url: str = "",
    author: str = "",
    note: str = "",
    source_type: SourceType = SourceType.X,
) -> str:
    if url.strip():
        return f"{source_type.value}:{_normalize_url(url)}"
    digest = hashlib.sha1(f"{author}|{note}".encode("utf-8")).hexdigest()[:12]
    return f"{source_type.value}:{digest}"


def _build_note(note: str, author: str, url: str) -> str:
    parts: list[str] = []
    if note.strip():
        parts.append(note.strip())
    gaps: list[str] = []
    if not author.strip():
        gaps.append("author unknown")
    if not url.strip():
        gaps.append("source URL unknown")
    if gaps:
        parts.append("[coverage gap: " + "; ".join(gaps) + "]")
    return "\n".join(parts)


def to_evidence(
    *,
    concept_id: str,
    url: str = "",
    author: str = "",
    note: str = "",
    quoted_source_url: str | None = None,
    upstream_origin: str | None = None,
    role: EvidenceRole | str | None = None,
    strength: EvidenceStrength | str | float | None = None,
    directness: Directness | str | None = None,
    source_type: SourceType = SourceType.X,
    captured_at: datetime | None = None,
) -> ConceptEvidence:
    """Build a ``ConceptEvidence`` from a manual X capture.

    Unavailable fields stay ``""``; the coverage gap is recorded explicitly in
    ``note``. A note without a quoted/upstream primary source is labeled
    INFERRED (or INDIRECT for a link-only note, DIRECT for a verbatim quote).
    """
    resolved_role = _role_from_hint(role, EvidenceRole.PROBLEM)
    resolved_directness = _directness_from_hint(directness)
    if resolved_directness is None:
        resolved_directness = infer_directness(note, quoted_source_url)
    resolved_strength = _strength_from_hint(strength, _default_strength(resolved_directness))

    return ConceptEvidence(
        id=_evidence_id(url=url, author=author, note=note, source_type=source_type),
        concept_id=concept_id,
        source_type=source_type,
        source_url=url,
        role=resolved_role,
        directness=resolved_directness,
        strength=resolved_strength,
        independence_key=independence_key(
            url=url,
            quoted_source_url=quoted_source_url,
            upstream_origin=upstream_origin,
            source_type=source_type,
        ),
        note=_build_note(note, author, url),
        captured_at=captured_at or _now(),
    )


def from_signal(signal: Signal, concept_id: str, *, source_type: SourceType = SourceType.X) -> ConceptEvidence:
    """Bridge a cross-source ``Signal`` (source="x"/"manual") into ``ConceptEvidence``.

    Maps the nullable ``evidence_role`` / ``directness`` / ``strength`` string
    hints onto the strict enums; content inference fills any gaps.
    """
    return to_evidence(
        concept_id=concept_id,
        url=str(signal.payload.get("url") or signal.target_repo or ""),
        author=signal.actor,
        note=str(signal.payload.get("note") or signal.payload.get("body") or ""),
        quoted_source_url=str(signal.payload.get("quoted_source_url") or ""),
        upstream_origin=str(signal.payload.get("upstream_origin") or ""),
        role=signal.evidence_role,
        strength=signal.strength,
        directness=signal.directness,
        source_type=source_type,
    )
