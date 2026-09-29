"""Action executor — maps domain actions to deterministic RSS-backed operations.

The control plane executes the *mechanism* (fetch, group, search, record); the
Agent supplies the *judgment* (which gap to pursue, what counts as a workaround).
Each action returns ``{"status", "observation", "new_evidence", "budget_delta"}``.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable

from concepts.adapters.reddit import independence_key_for_post, infer_directness
from concepts.handoffs import SourceHandoffItem
from investigations.models import EvidenceRecord
from models.concept import Directness, EvidenceRole, EvidenceStrength, SourceType

Fetcher = Callable[[str, str, int], list[dict]]

_WORKAROUND_MARKERS = re.compile(
    r"\b(?:workaround|worked around|we use|i use|we use|using|temporarily|"
    r"manual|spreadsheet|zapier|copy-paste|copy paste|hack)\b",
    re.IGNORECASE,
)
_COUNTER_MARKERS = re.compile(
    r"\b(?:already exists|solved|solution exists|there's a tool|there is a tool|"
    r"built-in|out of the box|paid for)\b",
    re.IGNORECASE,
)


def default_fetcher(subreddit: str, sort: str = "new", limit: int = 25) -> list[dict]:
    """Fetch and parse a subreddit's RSS feed via the stdlib helper."""
    from scripts.reddit_rss import build_url, fetch, parse_atom

    xml_text = fetch(build_url(subreddit, sort, limit))
    return parse_atom(xml_text)


def _post_text(post: dict) -> str:
    return " ".join(str(post.get(k) or "") for k in ("title", "selftext", "body"))


def normalize_post(post: dict, investigation_id: str) -> EvidenceRecord:
    """Normalize one RSS post into an ``EvidenceRecord`` (a ``SourceHandoffItem``)."""
    raw_id = str(post.get("id") or "").strip()
    directness = infer_directness(post)
    item = SourceHandoffItem(
        source=SourceType.REDDIT,
        role=EvidenceRole.PROBLEM,
        author=str(post.get("author") or ""),
        url=str(post.get("permalink") or ""),
        published_at=_parse_published(post.get("published")),
        excerpt=_post_text(post)[:500],
        directness=directness,
        strength=EvidenceStrength.MODERATE if directness == Directness.DIRECT else EvidenceStrength.WEAK,
        independence_key=independence_key_for_post(post),
    )
    return EvidenceRecord(
        id=f"reddit:{raw_id}", investigation_id=investigation_id, item=item,
    )


def _parse_published(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


# ── Action executors ──

def _search_discussions(params, fetcher, evidence, investigation_id):
    subreddit = str(params.get("subreddit") or "").strip()
    if not subreddit:
        return {"status": "invalid_action", "observation": {"summary": "missing subreddit"}, "new_evidence": [], "budget_delta": {}}
    sort = params.get("sort", "new")
    limit = int(params.get("limit", 25))
    try:
        posts = fetcher(subreddit, sort, limit)
    except Exception as exc:  # network / HTTP / parse
        return {"status": "source_failure", "observation": {"summary": str(exc)}, "new_evidence": [], "budget_delta": {"evidence_rounds": 1}}
    known_ids = {e.id for e in evidence}
    new_evidence: list[EvidenceRecord] = []
    for post in posts:
        rec = normalize_post(post, investigation_id)
        if rec.id not in known_ids:
            new_evidence.append(rec)
            known_ids.add(rec.id)
    if not new_evidence:
        return {"status": "no_results", "observation": {"summary": "no new posts"}, "new_evidence": [], "budget_delta": {"evidence_rounds": 1}}
    return {"status": "completed", "observation": {"evidence_ids": [e.id for e in new_evidence], "summary": f"{len(new_evidence)} new posts"}, "new_evidence": new_evidence, "budget_delta": {"evidence_rounds": 1}}


def _inspect_thread(params, fetcher, evidence):
    target = str(params.get("permalink") or params.get("id") or "").strip()
    if not target:
        return {"status": "invalid_action", "observation": {"summary": "missing permalink/id"}, "new_evidence": [], "budget_delta": {}}
    for rec in evidence:
        if rec.item.url == target or rec.id == target or rec.id == f"reddit:{target}":
            return {"status": "completed", "observation": {"post": rec.item.model_dump(mode="json")}, "new_evidence": [], "budget_delta": {}}
    return {"status": "no_results", "observation": {"summary": "thread not in collected evidence"}, "new_evidence": [], "budget_delta": {}}


def _find_similar_cases(params, fetcher, evidence):
    groups: dict[str, dict] = defaultdict(lambda: {"independence_key": "", "count": 0, "authors": set(), "ids": []})
    for rec in evidence:
        key = rec.item.independence_key
        g = groups[key]
        g["independence_key"] = key
        g["count"] += 1
        g["ids"].append(rec.id)
        if rec.item.author:
            g["authors"].add(rec.item.author)
    out = []
    for g in groups.values():
        out.append({
            "independence_key": g["independence_key"],
            "count": g["count"],
            "authors": sorted(g["authors"]),
            "evidence_ids": g["ids"],
        })
    return {"status": "completed", "observation": {"groups": out}, "new_evidence": [], "budget_delta": {}}


def _seek_workaround(params, fetcher, evidence):
    matches = []
    for rec in evidence:
        text = rec.item.excerpt
        if _WORKAROUND_MARKERS.search(text):
            matches.append({
                "evidence_id": rec.id,
                "excerpt": text,
                "directness": rec.item.directness.value,
            })
    return {"status": "completed", "observation": {"matches": matches}, "new_evidence": [], "budget_delta": {}}


def _seek_counterevidence(params, fetcher, evidence):
    matches = []
    for rec in evidence:
        if _COUNTER_MARKERS.search(rec.item.excerpt):
            matches.append({"evidence_id": rec.id, "excerpt": rec.item.excerpt})
    return {
        "status": "completed",
        "observation": {
            "found": bool(matches),
            "matches": matches,
            "coverage": f"searched {len(evidence)} collected posts for solution markers; comments not read",
        },
        "new_evidence": [],
        "budget_delta": {},
    }


_EXECUTORS = {
    "search_discussions": _search_discussions,
    "inspect_thread": _inspect_thread,
    "find_similar_cases": _find_similar_cases,
    "seek_workaround": _seek_workaround,
    "seek_counterevidence": _seek_counterevidence,
}


def execute(action: str, params: dict, *, fetcher: Fetcher, evidence: list[EvidenceRecord], investigation_id: str = "") -> dict:
    executor = _EXECUTORS.get(action)
    if executor is None:
        return {"status": "invalid_action", "observation": {"summary": f"unknown action {action!r}"}, "new_evidence": [], "budget_delta": {}}
    if action == "search_discussions":
        return executor(params, fetcher, evidence, investigation_id)
    return executor(params, fetcher, evidence)
