"""Reddit evidence adapter — normalize RSS findings into ``ConceptEvidence``.

Bridges Reddit RSS title/body findings (and, when an authenticated or publicly
supported path exists, comments and linked primary artifacts) into the immutable
``ConceptEvidence`` model.

Directness mapping (plan's L1/L2/L3 -> ``Directness``, by INTENT not label):

- primary first-hand source                    -> ``Directness.DIRECT``
  * a Reddit post whose body is the author's own first-person report
    (plan's "L1"), and
  * a linked primary artifact cited by a post, e.g. a linked GitHub issue
    (plan's "L3" — preserved as a primary source, not a tertiary note).
- second-hand report / repost / summary        -> ``Directness.INDIRECT``
  * comments, aggregate/roundup posts, crossposts, and reposts of another
    user's claim (plan's "L2").
- note-taker inference with no primary link    -> ``Directness.INFERRED``

``Signal.evidence_role`` / ``directness`` / ``strength`` are free-form strings
(or ``None``); they are mapped onto the strict enums here with explicit defaults,
never by inventing new enum values.

Coverage: RSS returns only title/body — no comments, no scores. ``comments_read``
defaults to ``False`` and is carried on the returned :class:`RedditEvidence`, so a
report must state "comments were not read" rather than describe RSS-only findings
as community consensus or production validation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
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
    "attempted_solution": EvidenceRole.PROBLEM,  # failed/attempted fixes are problem-side
    "implementation": EvidenceRole.IMPLEMENTATION,
    "adoption": EvidenceRole.ADOPTION,
    "validation": EvidenceRole.ADOPTION,
    "counterexample": EvidenceRole.COUNTER,
    "counterevidence": EvidenceRole.COUNTER,
    "counter": EvidenceRole.COUNTER,
    # "context" is deliberately unmapped -> falls back to the adapter default.
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
    "l3": Directness.INFERRED,  # note-taker's tertiary inference about a linked artifact
}

_STRENGTH_HINT: dict[str, EvidenceStrength] = {
    "weak": EvidenceStrength.WEAK,
    "low": EvidenceStrength.WEAK,
    "moderate": EvidenceStrength.MODERATE,
    "medium": EvidenceStrength.MODERATE,
    "strong": EvidenceStrength.STRONG,
    "high": EvidenceStrength.STRONG,
}

# First-person narration suggests a first-hand report; explicit second-hand
# markers always win over it (conservative). RSS gives no flag for this, so
# when neither is present we default to INDIRECT rather than over-claim.
_FIRST_PERSON_RE = re.compile(
    r"\b(?:i|i'm|im|me|my|mine|we|we're|we've|our|ours|us|i've|i'd|i'll)\b",
    re.IGNORECASE,
)
_SECOND_HAND_RE = re.compile(
    r"\b(?:crosspost|cross-post|repost|re-post|reposted|tldr|tl;dr|summary|"
    r"aggregate|roundup|round-up|megathread|mega-thread|recap|compilation|"
    r"digest|weekly thread)\b",
    re.IGNORECASE,
)

# Explicit keys a caller may use to hand us a linked primary artifact without
# having to parse the body text.
_LINKED_KEYS = ("linked_primary_url", "quoted_source_url", "upstream_url", "source_url")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_url(url: str) -> str:
    """Lowercase a URL and strip scheme/www for a stable, dedup-friendly key."""
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
    # Signal.strength is a float; assume a 0-1 scale, clamped defensively.
    if f <= 0.33:
        return EvidenceStrength.WEAK
    if f <= 0.66:
        return EvidenceStrength.MODERATE
    return EvidenceStrength.STRONG


def _default_strength(directness: Directness) -> EvidenceStrength:
    if directness is Directness.DIRECT:
        return EvidenceStrength.MODERATE  # a single first-hand report, not proof
    return EvidenceStrength.WEAK


def _extract_primary_link(post: dict) -> str:
    """Return the first linked primary artifact, if any, from a post dict."""
    for key in _LINKED_KEYS:
        value = str(post.get(key) or "").strip()
        if value:
            return value
    text = " ".join(
        str(post.get(k) or "") for k in ("selftext", "body", "title")
    )
    urls = re.findall(r"https?://[^\s\"'<>]+", text)
    return urls[0] if urls else ""


def infer_directness(post: dict, *, default: Directness = Directness.INDIRECT) -> Directness:
    """Infer directness from an RSS post (title/body only).

    Conservative: a post is DIRECT only when it reads as a first-hand report and
    carries no repost/summary marker; otherwise INDIRECT.
    """
    text = " ".join(str(post.get(k) or "") for k in ("title", "selftext", "body"))
    if _SECOND_HAND_RE.search(text):
        return Directness.INDIRECT
    if _FIRST_PERSON_RE.search(text):
        return Directness.DIRECT
    return default


def independence_key_for_post(post: dict, *, upstream_url: str | None = None) -> str:
    """Derive an independence key from the upstream claim, not raw post count.

    A post that cites an upstream primary source shares that source's key, so
    the same claim reposted across communities collapses to one independent
    chain. A first-hand post with no upstream link keys off its own permalink.
    """
    anchor = upstream_url or _extract_primary_link(post)
    if anchor:
        return f"upstream:{_normalize_url(anchor)}"
    own = str(post.get("permalink") or post.get("url") or post.get("id") or "")
    return f"post:{_normalize_url(own)}"


def _evidence_id(post: dict) -> str:
    raw = str(post.get("id") or post.get("permalink") or "").strip()
    if not raw:
        raise ValueError("Reddit post requires an 'id' or 'permalink' to build a stable evidence id")
    return f"reddit:{raw}"


def _build_note(post: dict) -> str:
    parts: list[str] = []
    title = str(post.get("title") or "").strip()
    body = str(post.get("selftext") or post.get("body") or "").strip()
    if title:
        parts.append(title)
    if body:
        parts.append(body[:500])
    if not str(post.get("author") or "").strip():
        parts.append("[coverage gap: author unknown]")
    return "\n".join(parts)


def post_to_evidence(
    post: dict,
    concept_id: str,
    *,
    role: EvidenceRole | str | None = None,
    strength: EvidenceStrength | str | float | None = None,
    directness: Directness | str | None = None,
    upstream_url: str | None = None,
    independence_key: str | None = None,
    comments_read: bool = False,
    captured_at: datetime | None = None,
) -> "RedditEvidence":
    """Normalize one Reddit RSS post (title/body) into ``ConceptEvidence``.

    ``comments_read`` defaults to ``False`` (RSS returns no comments), so callers
    that did not read comments can state that coverage gap explicitly.
    """
    resolved_role = _role_from_hint(role, EvidenceRole.PROBLEM)
    resolved_directness = _directness_from_hint(directness)
    if resolved_directness is None:
        resolved_directness = infer_directness(post)
    resolved_strength = _strength_from_hint(strength, _default_strength(resolved_directness))

    evidence = ConceptEvidence(
        id=_evidence_id(post),
        concept_id=concept_id,
        source_type=SourceType.REDDIT,
        source_url=str(post.get("permalink") or ""),
        role=resolved_role,
        directness=resolved_directness,
        strength=resolved_strength,
        independence_key=(
            independence_key
            or independence_key_for_post(post, upstream_url=upstream_url)
        ),
        note=_build_note(post),
        captured_at=captured_at or _now(),
    )
    return RedditEvidence(evidence=evidence, comments_read=comments_read)


def comment_to_evidence(
    comment: dict,
    concept_id: str,
    *,
    post: dict | None = None,
    role: EvidenceRole | str | None = None,
    strength: EvidenceStrength | str | float | None = None,
    captured_at: datetime | None = None,
) -> ConceptEvidence:
    """Normalize one comment into INDIRECT evidence.

    Only import comments when an authenticated/publicly-supported path exists.
    Comments are second-hand discussion, so directness is always INDIRECT, and
    they share the parent post's independence key so they do not inflate
    recurrence.
    """
    raw_id = str(comment.get("id") or comment.get("permalink") or "").strip()
    if not raw_id:
        raise ValueError("Reddit comment requires an 'id' or 'permalink'")
    if post is not None:
        key = independence_key_for_post(post)
        source_url = str(comment.get("permalink") or post.get("permalink") or "")
    else:
        key = f"post:{_normalize_url(str(comment.get('permalink') or raw_id))}"
        source_url = str(comment.get("permalink") or "")

    return ConceptEvidence(
        id=f"reddit_comment:{raw_id}",
        concept_id=concept_id,
        source_type=SourceType.REDDIT,
        source_url=source_url,
        role=_role_from_hint(role, EvidenceRole.PROBLEM),
        directness=Directness.INDIRECT,
        strength=_strength_from_hint(strength, EvidenceStrength.WEAK),
        independence_key=key,
        note=str(comment.get("body") or comment.get("selftext") or "")[:500],
        captured_at=captured_at or _now(),
    )


def linked_artifact_to_evidence(
    artifact_url: str,
    concept_id: str,
    *,
    source_type: SourceType = SourceType.GITHUB,
    role: EvidenceRole | str | None = None,
    strength: EvidenceStrength | str | float | None = None,
    note: str = "",
    captured_at: datetime | None = None,
) -> ConceptEvidence:
    """Preserve a linked primary artifact (e.g. a GitHub issue) as DIRECT evidence.

    The artifact itself is the primary source, so it is recorded DIRECT with an
    independence key derived from its own URL; the Reddit post that linked it is
    the INDIRECT carrier, not the evidence.
    """
    if not str(artifact_url).strip():
        raise ValueError("linked artifact requires a non-empty URL")
    return ConceptEvidence(
        id=f"linked:{_normalize_url(artifact_url)}",
        concept_id=concept_id,
        source_type=source_type,
        source_url=str(artifact_url),
        role=_role_from_hint(role, EvidenceRole.IMPLEMENTATION),
        directness=Directness.DIRECT,
        strength=_strength_from_hint(strength, EvidenceStrength.MODERATE),
        independence_key=f"upstream:{_normalize_url(artifact_url)}",
        note=note,
        captured_at=captured_at or _now(),
    )


def from_signal(signal: Signal, concept_id: str, *, comments_read: bool = False) -> "RedditEvidence":
    """Bridge a cross-source ``Signal`` (source="reddit") into ``ConceptEvidence``.

    Maps the nullable ``evidence_role`` / ``directness`` / ``strength`` string
    hints onto the strict enums; content inference fills any gaps.
    """
    post = {
        "id": signal.id,
        "title": str(signal.payload.get("title") or ""),
        "selftext": str(signal.payload.get("selftext") or signal.payload.get("body") or ""),
        "permalink": str(
            signal.payload.get("permalink")
            or signal.payload.get("url")
            or signal.target_repo
            or ""
        ),
        "author": signal.actor,
        "subreddit": str(signal.payload.get("subreddit") or ""),
    }
    return post_to_evidence(
        post,
        concept_id,
        role=signal.evidence_role,
        strength=signal.strength,
        directness=signal.directness,
        independence_key=signal.independence_key or None,
        comments_read=comments_read,
    )


@dataclass(frozen=True)
class RedditEvidence:
    """A ``ConceptEvidence`` plus the Reddit-specific coverage gap.

    ``comments_read`` is ``False`` for RSS-only import, so a report can state
    "comments were not read" instead of claiming community consensus or
    production validation.
    """

    evidence: ConceptEvidence
    comments_read: bool = False
