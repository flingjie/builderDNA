"""Deterministic candidate matching for concept capture (no embeddings).

Given a newly captured concept and the existing cards, decide whether it already
exists by matching on four signals:

- **normalized names** — exact normalized title equality,
- **explicit aliases** — a title matching an alias in either direction (this is
  how a renamed old idea matches, e.g. the old title listed in a new card's
  ``aliases``),
- **URLs** — shared source-evidence URLs, and
- **problem fingerprints** — normalized problem text (exact equality or token
  Jaccard overlap).

Names and aliases match only on *exact* normalized equality — never fuzzy / edit
distance — so superficially similar names with different users, failure modes, or
interventions do not merge. Each candidate is returned with a ranked score plus
the reasons it matched, and ``is_ambiguous`` flags merges that require human
confirmation (near-ties, or a strong name match whose problems actually differ).

``classify_match`` layers a clean ``"exact"`` / ``"suggested"`` / ``"none"``
decision over those signals, honouring the ordered-signal contract:

1. normalized canonical URL / content fingerprint;
2. exact normalized name or alias;
3. explicit upstream origin (repost-chain independence key);
4. deterministic problem fingerprint;
5. ranked suggestions requiring semantic-agent confirmation.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from models.concept import ConceptCard


# ── Normalization (deterministic, no embeddings) ──

def normalize_name(name: str) -> str:
    """Lowercase and strip punctuation/whitespace, collapsing runs to single spaces."""
    return _normalize_text(name)


def normalize_problem(text: str) -> str:
    """Normalize free text for problem-fingerprint comparison."""
    return _normalize_text(text)


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def tokenize(text: str) -> frozenset[str]:
    """A normalized set of word tokens for Jaccard overlap."""
    return frozenset(_normalize_text(text).split())


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def normalize_url(url: str) -> str:
    """Normalize a source URL: lowercase, drop fragment, strip trailing slash."""
    u = url.strip().lower()
    u = u.split("#", 1)[0]
    return u.rstrip("/")


# ── Signal scores (documented constants) ──

NAME_EXACT_SCORE = 1.0
ALIAS_SCORE = 0.9
URL_SCORE = 0.8
UPSTREAM_SCORE = 0.75
PROBLEM_EXACT_SCORE = 0.7
PROBLEM_JACCARD_WEIGHT = 0.6


# ── Results ──

@dataclass(frozen=True)
class MatchReason:
    """Why one candidate matched, with that signal's sub-score."""

    signal: str  # "name" | "alias" | "url" | "upstream" | "problem"
    detail: str
    score: float


@dataclass(frozen=True)
class CandidateMatch:
    """A ranked candidate with the reasons it matched."""

    concept_id: str
    title: str
    score: float
    name_score: float
    url_score: float
    problem_score: float
    both_have_problem: bool
    reasons: tuple[MatchReason, ...]
    upstream_score: float = 0.0


def _name_scores(
    candidate: ConceptCard, card: ConceptCard
) -> tuple[float, MatchReason | None]:
    """Return the name/alias sub-score and its reason, or (0.0, None)."""
    cand_name = normalize_name(candidate.title)
    card_name = normalize_name(card.title)

    if cand_name and card_name and cand_name == card_name:
        return NAME_EXACT_SCORE, MatchReason(
            "name", f"normalized title equality: {cand_name!r}", NAME_EXACT_SCORE
        )

    cand_aliases = {normalize_name(a) for a in candidate.aliases if normalize_name(a)}
    card_aliases = {normalize_name(a) for a in card.aliases if normalize_name(a)}

    if cand_name and cand_name in card_aliases:
        return ALIAS_SCORE, MatchReason(
            "alias",
            f"candidate title {cand_name!r} matches an alias of {card.id!r}",
            ALIAS_SCORE,
        )
    if card_name and card_name in cand_aliases:
        return ALIAS_SCORE, MatchReason(
            "alias",
            f"candidate alias {card_name!r} matches the title of {card.id!r}",
            ALIAS_SCORE,
        )
    shared = cand_aliases & card_aliases
    if shared:
        return ALIAS_SCORE, MatchReason(
            "alias", f"shared alias {sorted(shared)[0]!r}", ALIAS_SCORE
        )
    return 0.0, None


def find_candidates(
    candidate: ConceptCard,
    existing: Sequence[ConceptCard],
    candidate_urls: Sequence[str] = (),
    existing_urls: Mapping[str, Sequence[str]] | None = None,
    min_score: float = 0.0,
) -> list[CandidateMatch]:
    """Rank existing cards that could be the same concept as ``candidate``.

    Returns only cards with a positive score (``> min_score``), sorted by score
    descending, then by concept ID ascending for determinism. Each result carries
    the per-signal sub-scores and the reasons it matched.
    """
    existing_urls = existing_urls or {}

    cand_problem_norm = normalize_problem(candidate.problem)
    cand_problem_tokens = tokenize(candidate.problem)
    cand_urls = {normalize_url(u) for u in candidate_urls}
    cand_urls.discard("")

    results: list[CandidateMatch] = []
    for card in existing:
        reasons: list[MatchReason] = []

        name_score, name_reason = _name_scores(candidate, card)
        if name_reason is not None:
            reasons.append(name_reason)

        url_score = 0.0
        existing_url_set = {normalize_url(u) for u in existing_urls.get(card.id, ())}
        existing_url_set.discard("")
        shared_urls = cand_urls & existing_url_set
        if shared_urls:
            url_score = URL_SCORE
            reasons.append(
                MatchReason("url", f"shared source URL: {sorted(shared_urls)[0]}", url_score)
            )

        problem_score = 0.0
        both_have_problem = bool(cand_problem_norm) and bool(normalize_problem(card.problem))
        if both_have_problem:
            card_problem_norm = normalize_problem(card.problem)
            if cand_problem_norm == card_problem_norm:
                problem_score = PROBLEM_EXACT_SCORE
                reasons.append(
                    MatchReason("problem", "normalized problem equality", problem_score)
                )
            else:
                sim = jaccard(cand_problem_tokens, tokenize(card.problem))
                if sim > 0.0:
                    problem_score = PROBLEM_JACCARD_WEIGHT * sim
                    reasons.append(
                        MatchReason(
                            "problem",
                            f"problem fingerprint overlap {sim:.3f}",
                            round(problem_score, 6),
                        )
                    )

        score = max(name_score, url_score, problem_score)
        if score <= 0.0 or score < min_score:
            continue

        results.append(
            CandidateMatch(
                concept_id=card.id,
                title=card.title,
                score=score,
                name_score=name_score,
                url_score=url_score,
                problem_score=problem_score,
                both_have_problem=both_have_problem,
                reasons=tuple(reasons),
            )
        )

    results.sort(key=lambda m: (-m.score, m.concept_id))
    return results


def is_ambiguous(
    matches: Sequence[CandidateMatch],
    *,
    tie_tolerance: float = 1e-9,
    problem_similarity_threshold: float = 0.5,
) -> bool:
    """Return True when a merge requires human confirmation.

    A merge is ambiguous when:

    1. the top candidate matched strongly on name/alias but its problems are both
       present and *different* (name-similar but problem-different), or
    2. two or more candidates tie for the top score.

    Ambiguous cases must never be auto-merged.
    """
    if not matches:
        return False

    top = matches[0]
    if (
        top.name_score >= ALIAS_SCORE
        and top.both_have_problem
        and top.problem_score < problem_similarity_threshold
    ):
        return True

    if len(matches) >= 2:
        second = matches[1]
        if top.score > 0 and abs(top.score - second.score) <= tie_tolerance:
            return True

    return False


# ── Classification (exact / suggested / none) ──

@dataclass(frozen=True)
class MatchClassification:
    """The classification of a capture against existing concept cards.

    ``kind`` is one of ``"exact"``, ``"suggested"``, or ``"none"``:

    - ``"exact"`` — an unambiguous fingerprint (URL / upstream origin) or exact
      name/alias match; safe to merge without human confirmation.
    - ``"suggested"`` — ranked candidates exist but the match is ambiguous: a
      strong identity signal whose mechanism differs, a near-tie, or
      problem-origin overlap with no strong identity signal. Never auto-merge.
    - ``"none"`` — no candidate matched.

    ``candidates`` carries the ranked ``CandidateMatch`` list, each with its own
    per-signal ``reasons``; ``top`` is the highest-ranked candidate (``None``
    when ``kind == "none"``).
    """

    kind: str
    candidates: tuple[CandidateMatch, ...]
    top: CandidateMatch | None
    reason: str


def _problem_overlap(candidate: ConceptCard, card: ConceptCard) -> tuple[bool, float]:
    """Return ``(both_have_problem, problem_score)`` for the ambiguity check."""
    cand_norm = normalize_problem(candidate.problem)
    card_norm = normalize_problem(card.problem)
    both = bool(cand_norm) and bool(card_norm)
    if not both:
        return False, 0.0
    if cand_norm == card_norm:
        return True, PROBLEM_EXACT_SCORE
    sim = jaccard(tokenize(candidate.problem), tokenize(card.problem))
    return True, PROBLEM_JACCARD_WEIGHT * sim


def _strong_identity(match: CandidateMatch) -> bool:
    """True when a match carries a strong identity signal (not problem-only)."""
    return (
        match.name_score >= ALIAS_SCORE
        or match.url_score > 0.0
        or match.upstream_score > 0.0
    )


def _is_exact(
    ranked: Sequence[CandidateMatch],
    *,
    problem_similarity_threshold: float = 0.5,
) -> bool:
    """True when the top candidate is an unambiguous strong-identity match."""
    if not ranked:
        return False
    top = ranked[0]
    if not _strong_identity(top):
        return False
    if is_ambiguous(ranked, problem_similarity_threshold=problem_similarity_threshold):
        return False
    # A fingerprint (URL/upstream) whose mechanism differs is still ambiguous:
    # two cards can share a source yet describe different concepts.
    if (
        (top.url_score > 0.0 or top.upstream_score > 0.0)
        and top.both_have_problem
        and top.problem_score < problem_similarity_threshold
    ):
        return False
    return True


def classify_match(
    candidate: ConceptCard,
    existing: Sequence[ConceptCard],
    candidate_urls: Sequence[str] = (),
    existing_urls: Mapping[str, Sequence[str]] | None = None,
    candidate_upstream_origins: Sequence[str] = (),
    existing_upstream_origins: Mapping[str, Sequence[str]] | None = None,
    min_score: float = 0.0,
) -> MatchClassification:
    """Classify ``candidate`` against ``existing`` using the ordered signals.

    Signal order (strongest identity first):

    1. normalized canonical URL / content fingerprint;
    2. exact normalized name or alias;
    3. explicit upstream origin (repost-chain independence key);
    4. deterministic problem fingerprint;
    5. ranked suggestions requiring semantic-agent confirmation.

    ``"exact"`` requires an unambiguous fingerprint or exact name/alias match.
    Anything ambiguous — a strong identity signal whose problem differs, a
    near-tie, or problem-only overlap — is ``"suggested"`` and must never be
    auto-merged. ``"none"`` means no candidate matched at all.
    """
    base = find_candidates(candidate, existing, candidate_urls, existing_urls, min_score)
    by_id: dict[str, CandidateMatch] = {m.concept_id: m for m in base}

    cand_upstream = {normalize_url(o) for o in candidate_upstream_origins}
    cand_upstream.discard("")
    if cand_upstream:
        existing_upstream_origins = existing_upstream_origins or {}
        for card in existing:
            card_upstream = {
                normalize_url(o) for o in existing_upstream_origins.get(card.id, ())
            }
            card_upstream.discard("")
            shared = cand_upstream & card_upstream
            if not shared:
                continue
            upstream_reason = MatchReason(
                "upstream",
                f"shared upstream origin: {sorted(shared)[0]}",
                UPSTREAM_SCORE,
            )
            prev = by_id.get(card.id)
            if prev is not None:
                by_id[card.id] = replace(
                    prev,
                    upstream_score=UPSTREAM_SCORE,
                    score=max(prev.score, UPSTREAM_SCORE),
                    reasons=prev.reasons + (upstream_reason,),
                )
            elif UPSTREAM_SCORE >= min_score:
                both, pscore = _problem_overlap(candidate, card)
                by_id[card.id] = CandidateMatch(
                    concept_id=card.id,
                    title=card.title,
                    score=UPSTREAM_SCORE,
                    name_score=0.0,
                    url_score=0.0,
                    problem_score=pscore,
                    both_have_problem=both,
                    upstream_score=UPSTREAM_SCORE,
                    reasons=(upstream_reason,),
                )

    ranked = sorted(by_id.values(), key=lambda m: (-m.score, m.concept_id))
    if not ranked:
        return MatchClassification(
            kind="none", candidates=(), top=None, reason="no candidate matched"
        )

    top = ranked[0]
    if _is_exact(ranked):
        driver = top.reasons[0].signal if top.reasons else "identity"
        return MatchClassification(
            kind="exact",
            candidates=tuple(ranked),
            top=top,
            reason=f"unambiguous {driver} match on {top.concept_id!r}",
        )
    return MatchClassification(
        kind="suggested",
        candidates=tuple(ranked),
        top=top,
        reason=(
            f"ambiguous or weak match (top: {top.concept_id!r}); "
            "requires human confirmation"
        ),
    )
