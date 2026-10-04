"""Deterministic candidate grouping via TF-IDF + cosine similarity.

No embeddings, no network. Groups issues into *candidate* groups using lexical
recall only — text similarity is a recall hint, never proof of the same pain
point. Two issues discussing "timeout" may be a config error vs. an execution
recovery failure; the skill's Agent confirmation step decides that. Issues that
do not group with anyone are returned as noise.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from intelligence.pain.clean import clean_issue_text, issue_key
from models.payload import CandidateGroup, PainCandidate

# Structured signals that strengthen recall beyond raw text overlap.
_ERROR_CODE_RE = re.compile(r"\bE\d{2,}\b")
_HTTP_STATUS_RE = re.compile(r"\b(?:HTTP\s*)?(?:4\d\d|5\d\d)\b")
_EXCEPTION_RE = re.compile(r"\b[A-Z][a-zA-Z0-9]*(?:Error|Exception|Failure|Timeout)\b")
_COMPONENT_PREFIX_RE = re.compile(r"^(?:area|component|scope)[:/]\s*(.+)$", re.IGNORECASE)


def extract_error_codes(text: str) -> list[str]:
    """Extract error codes, exception names, and HTTP status from issue text."""
    codes: list[str] = []
    codes.extend(_ERROR_CODE_RE.findall(text))
    codes.extend(_HTTP_STATUS_RE.findall(text))
    codes.extend(_EXCEPTION_RE.findall(text))
    return list(dict.fromkeys(codes))  # dedupe, preserve order


def extract_components(labels: Sequence[str], text: str) -> list[str]:
    """Map issue labels (and ``area:``/``component:`` prefixes) to component names."""
    comps: list[str] = []
    for label in labels:
        m = _COMPONENT_PREFIX_RE.match(label.strip())
        comps.append(m.group(1).strip() if m else label.strip())
    return list(dict.fromkeys(comps))


def build_candidates(issues: Sequence[dict]) -> list[PainCandidate]:
    """Turn raw issue dicts into cleaned, feature-annotated candidates."""
    candidates: list[PainCandidate] = []
    for iss in issues:
        title = iss.get("title", "")
        body = iss.get("body", "")
        labels = iss.get("labels", []) or []
        text = f"{title}\n{body}"
        candidates.append(
            PainCandidate(
                issue_key=issue_key(iss),
                repo=iss.get("repo", ""),
                issue_number=iss.get("issue_number", 0),
                title=title,
                body=body,
                url=iss.get("url", ""),
                labels=labels,
                comments=iss.get("comments", 0),
                participants=iss.get("participants", 0),
                reactions=iss.get("reactions", 0),
                created_at=iss.get("created_at", ""),
                error_codes=extract_error_codes(text),
                components=extract_components(labels, text),
            )
        )
    return candidates


def _connected_components(n: int, pairs: list[tuple[int, int]]) -> list[list[int]]:
    """Union-find connected components over edges ``pairs``."""
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    comps: dict[int, list[int]] = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    return list(comps.values())


def _mean_pairwise(sim, indices: list[int]) -> float:
    if len(indices) < 2:
        return 0.0
    vals = [sim[i][j] for a, i in enumerate(indices) for j in indices[a + 1:]]
    return sum(vals) / len(vals)


def shared_features(members: list[PainCandidate]) -> dict:
    def common(attr: str) -> list[str]:
        sets = [set(getattr(m, attr)) for m in members if getattr(m, attr)]
        if not sets:
            return []
        result = sets[0]
        for s in sets[1:]:
            result &= s
        return sorted(result)

    return {
        "error_codes": common("error_codes"),
        "components": common("components"),
        "labels": common("labels"),
    }


def build_candidate_groups(
    issues: Sequence[dict],
    *,
    similarity_threshold: float = 0.35,
) -> tuple[list[CandidateGroup], list[PainCandidate]]:
    """Group issues into candidate groups by TF-IDF cosine similarity.

    Returns ``(groups, noise_candidates)`` where ``groups`` is sorted by member
    count descending and ``noise_candidates`` lists issues assigned to no group.
    """
    candidates = build_candidates(issues)
    n = len(candidates)
    if n < 2:
        return [], candidates

    texts = [clean_issue_text(c.title, c.body) for c in candidates]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        # Empty vocabulary (all texts blank / too short to n-gram).
        return [], candidates

    sim = cosine_similarity(matrix)
    pairs = [
        (i, j)
        for i in range(n)
        for j in range(i + 1, n)
        if sim[i][j] >= similarity_threshold
    ]
    components = _connected_components(n, pairs)

    groups: list[CandidateGroup] = []
    noise: list[PainCandidate] = []
    for group_id, indices in enumerate(sorted(components, key=len, reverse=True)):
        if len(indices) < 2:
            noise.extend(candidates[i] for i in indices)
            continue
        members = [candidates[i] for i in indices]
        groups.append(
            CandidateGroup(
                group_id=group_id,
                issues=members,
                shared_features=shared_features(members),
                mean_similarity=round(_mean_pairwise(sim, indices), 4),
            )
        )

    return groups, noise
