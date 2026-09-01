"""Pure, JSON-first rendering helpers for concept lifecycle records.

These helpers are deliberately *presentation over plain data*: each takes a
``dict`` (the ``mode="json"`` dump of a model) and returns a single line of
Markdown text. They never import the report models, so they stay free of import
cycles and can be reused anywhere a JSON-shaped concept/decision/evidence record
needs a human-readable line — including the radar cycle report renderer in
``radar_cycles/rendering.py``.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "render_concept_card_summary",
    "render_decision_line",
    "render_evidence_summary",
]


def _join(*parts: Any) -> str:
    """Join non-empty parts with ' · '."""
    return " · ".join(str(part) for part in parts if part not in (None, ""))


def render_concept_card_summary(data: dict) -> str:
    """Render one line summarizing a concept card (a JSON-mode card dump)."""
    title = data.get("title") or data.get("id") or ""
    concept_id = data.get("id") or ""
    stage = data.get("stage") or ""
    maturity = data.get("maturity") or ""
    scores = data.get("component_scores") or {}
    total = scores.get("total")
    problem = data.get("problem") or ""

    head = _join(f"{title} [{concept_id}]", f"stage={stage}", f"maturity={maturity}")
    if total is not None:
        head = _join(head, f"priority={total}")
    if problem:
        head = f"{head} — {problem}"
    return head


def render_decision_line(data: dict) -> str:
    """Render one line describing a portfolio decision (concept id + stage + reason)."""
    concept_id = data.get("concept_id") or ""
    stage = data.get("stage") or ""
    reason = data.get("reason") or ""
    line = f"{concept_id} → {stage}"
    if reason:
        line = f"{line}: {reason}"
    return line


def render_evidence_summary(data: dict) -> str:
    """Render one line summarizing a piece of evidence (top support / counterevidence)."""
    evidence_id = data.get("evidence_id") or ""
    concept_id = data.get("concept_id") or ""
    source_type = data.get("source_type") or ""
    role = data.get("role") or ""
    strength = data.get("strength") or ""
    directness = data.get("directness") or ""
    note = data.get("note") or ""

    meta = "/".join(
        part for part in (source_type, role, strength, directness) if part
    )
    line = f"{evidence_id} [{meta}]"
    if note:
        line = f"{line}: {note}"
    line = f"{line} (concept {concept_id})"
    return line
