"""GitHub evidence adapter — normalize repo signals into ``ConceptEvidence``.

Bridges GitHub ``Signal`` records (repo code/tests/releases, and external-user
issues/docs) into the immutable ``ConceptEvidence`` model, separating
*implementation* evidence from *adoption* evidence.

Directness mapping (plan's L1/L2/L3 -> ``Directness``, by INTENT not label):

- primary first-hand source -> ``Directness.DIRECT``: the repo's own code,
  tests, and releases are the primary artifact of implementation, and an
  external user's issue or discussion is their first-hand report of adoption.
- second-hand report / repost / summary -> ``Directness.INDIRECT``: any
  second-hand writeup that merely references the repo.
- note-taker inference with no primary link -> ``Directness.INFERRED``.

Role classification (authoritative, by signal type + external flag):

- ``repo_created`` / ``release``            -> ``IMPLEMENTATION``
- ``issue_opened`` / ``issue_commented`` / ``discussion``
  - external user (actor != repo owner)     -> ``ADOPTION``
  - repo owner / unknown                    -> ``IMPLEMENTATION`` (dev-side)
- ``star_growth`` / ``fork``                -> retrieval hints, NOT evidence.

Stars and velocity are retrieval hints only: a popular demo can never
independently satisfy adoption — adoption requires an external-user signal.
URLs and provenance are preserved on ``source_url`` and ``note``.
"""
from __future__ import annotations

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

# Signal types that are retrieval hints, never evidence.
RETRIEVAL_HINT_TYPES = ("star_growth", "fork")

# Signal types that map to implementation evidence (the repo's own artifact).
_IMPLEMENTATION_TYPES = ("repo_created", "release")

# Signal types that become adoption evidence only from an external user.
_ADOPTION_CANDIDATE_TYPES = ("issue_opened", "issue_commented", "discussion")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce(signal: Signal | dict) -> Signal:
    if isinstance(signal, Signal):
        return signal
    if isinstance(signal, dict):
        return Signal(**signal)
    raise TypeError("github adapter expects a Signal or a signal-shaped dict")


def _role_from_hint(value, default: EvidenceRole | None) -> EvidenceRole | None:
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


def is_external_user(signal: Signal | dict, *, external: bool | None = None) -> bool:
    """True when the actor is an external user of the repo (an adoption signal).

    An explicit ``external`` override wins; otherwise the actor is compared
    against the repo owner. Unknown actors are treated as non-external so the
    adapter never over-claims adoption.
    """
    sig = _coerce(signal)
    if external is not None:
        return bool(external)
    actor = (sig.actor or "").strip().lower()
    owner = (sig.target_repo or "").split("/", 1)[0].strip().lower()
    if not actor or not owner:
        return False
    return actor != owner


def classify_role(signal: Signal | dict, *, external: bool | None = None) -> EvidenceRole | None:
    """Classify a GitHub signal's evidence role.

    Returns ``None`` for retrieval hints (stars/forks/velocity) which are never
    evidence. A popular demo can only ever be IMPLEMENTATION; adoption requires
    an external-user issue or discussion.
    """
    sig = _coerce(signal)
    if sig.type in RETRIEVAL_HINT_TYPES:
        return None
    if sig.type in _IMPLEMENTATION_TYPES:
        return EvidenceRole.IMPLEMENTATION
    if sig.type in _ADOPTION_CANDIDATE_TYPES:
        if is_external_user(sig, external=external):
            return EvidenceRole.ADOPTION
        return EvidenceRole.IMPLEMENTATION
    # Unknown type: conservatively treat repo-side activity as implementation.
    return EvidenceRole.IMPLEMENTATION


def _default_directness(role: EvidenceRole) -> Directness:
    # Repo code/tests/releases and an external user's own issue are both
    # first-hand primary sources.
    return Directness.DIRECT


def _default_strength(signal: Signal, role: EvidenceRole) -> EvidenceStrength:
    if role is EvidenceRole.ADOPTION:
        return EvidenceStrength.MODERATE  # a real signal, but one user's report
    if signal.type == "release":
        return EvidenceStrength.STRONG  # shipped code is strong implementation evidence
    if signal.type in _ADOPTION_CANDIDATE_TYPES:
        return EvidenceStrength.WEAK  # owner/dev-side issue, not adoption
    return EvidenceStrength.MODERATE  # repo_created


def independence_key_for_signal(signal: Signal | dict, *, external: bool | None = None) -> str:
    """Independence key: one chain per repo (implementation) or per external
    user (adoption), so duplicate propagation does not inflate recurrence."""
    sig = _coerce(signal)
    full = (sig.target_repo or "").strip().lower()
    if classify_role(sig, external=external) is EvidenceRole.ADOPTION:
        actor = (sig.actor or "").strip().lower() or "unknown"
        return f"github:{full}:actor:{actor}"
    return f"github:{full}"


def source_url_for(signal: Signal | dict) -> str:
    """Preserve the most specific URL available, falling back to the repo URL."""
    sig = _coerce(signal)
    url = (
        sig.payload.get("html_url")
        or sig.payload.get("url")
        or sig.payload.get("permalink")
        or ""
    )
    if url:
        return str(url)
    return f"https://github.com/{sig.target_repo}"


def _note_for(signal: Signal, role: EvidenceRole) -> str:
    parts: list[str] = []
    text = (
        signal.payload.get("description")
        or signal.payload.get("title")
        or signal.payload.get("body")
        or ""
    )
    if text:
        parts.append(str(text)[:500])
    if role is EvidenceRole.ADOPTION:
        parts.append(f"[adoption: external user {signal.actor}]")
    parts.append(f"[signal type: {signal.type}]")
    return "\n".join(parts)


def to_evidence(
    signal: Signal | dict,
    concept_id: str,
    *,
    role: EvidenceRole | str | None = None,
    strength: EvidenceStrength | str | float | None = None,
    directness: Directness | str | None = None,
    external: bool | None = None,
    captured_at: datetime | None = None,
) -> ConceptEvidence | None:
    """Convert a GitHub signal into ``ConceptEvidence``, or ``None`` for a
    retrieval hint (stars/forks/velocity are never evidence).

    Role is authoritative by signal type + external flag; an explicit ``role``
    hint only overrides it for non-retrieval signals. URLs and provenance are
    preserved on ``source_url`` and ``note``.
    """
    sig = _coerce(signal)
    if sig.type in RETRIEVAL_HINT_TYPES:
        return None

    resolved_role = _role_from_hint(role, None)
    if resolved_role is None:
        resolved_role = classify_role(sig, external=external)
    assert resolved_role is not None  # non-retrieval signals always classify

    resolved_directness = _directness_from_hint(directness) or _default_directness(resolved_role)
    resolved_strength = _strength_from_hint(strength, _default_strength(sig, resolved_role))

    return ConceptEvidence(
        id=f"github:{sig.id}",
        concept_id=concept_id,
        source_type=SourceType.GITHUB,
        source_url=source_url_for(sig),
        role=resolved_role,
        directness=resolved_directness,
        strength=resolved_strength,
        independence_key=independence_key_for_signal(sig, external=external),
        note=_note_for(sig, resolved_role),
        captured_at=captured_at or _now(),
    )
