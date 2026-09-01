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
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

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
PROBLEM_EXACT_SCORE = 0.7
PROBLEM_JACCARD_WEIGHT = 0.6


# ── Results ──

@dataclass(frozen=True)
class MatchReason:
    """Why one candidate matched, with that signal's sub-score."""

    signal: str  # "name" | "alias" | "url" | "problem"
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
