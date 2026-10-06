"""Analysis validation for repo-evolution-learning.

Checks the skill-written ``analysis.json`` against the collected ``sources.jsonl``
and ``search-log.jsonl``. Each finding carries a ``{field, message, severity}``
triple; ``valid`` is False when any ``error``-severity finding exists. Warnings
are things the validator flags but the skill confirms (spec §7: automatic checks
cannot prove STE compliance).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from repo_learning.models import (
    Analysis,
    EvidenceStatus,
    Relation,
    SourceKind,
    SourceRecord,
    SourceRef,
)
from repo_learning.request import RequestSpec
from repo_learning import workspace

# Spec §7/§9 disabled evaluative expressions (validator flags, skill confirms).
_DISABLED_EXPRESSIONS = re.compile(
    r"显著|先进|强大|颠覆|行业领先|业界第一|顶级|最佳|完美|极致|遥遥领先|革命性|划时代"
)

# Any string carrying a URI scheme must be http/https.
_SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.-]*):", re.IGNORECASE)

_CREDENTIAL_PATTERN = re.compile(
    r"(token|secret|api[_-]?key|client[_-]?secret|access[_-]?key|password)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def _walk_strings(obj, path: str = ""):
    """Yield ``(path, value)`` for every string in a JSON-like structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def _collect_refs(analysis: Analysis):
    """Yield ``(field_path, SourceRef)`` for every SourceRef in the analysis."""
    yield from (("repo_identity.identity_evidence", r) for r in analysis.repo_identity.identity_evidence)
    yield from (("episode.source_refs", r) for r in analysis.episode.source_refs)
    for i, claim in enumerate(analysis.episode.alternatives):
        yield from ((f"episode.alternatives[{i}]", r) for r in claim.source_refs)
    for i, claim in enumerate(analysis.episode.decisions):
        yield from ((f"episode.decisions[{i}]", r) for r in claim.source_refs)
    for i, claim in enumerate(analysis.episode.validation):
        yield from ((f"episode.validation[{i}]", r) for r in claim.source_refs)
    for i, claim in enumerate(analysis.claims):
        yield from ((f"claims[{i}]", r) for r in claim.source_refs)
    for i, link in enumerate(analysis.feedback_links):
        yield from ((f"feedback_links[{i}].feedback_refs", r) for r in link.feedback_refs)
        yield from ((f"feedback_links[{i}].development_refs", r) for r in link.development_refs)
    for i, card in enumerate(analysis.learning_cards):
        yield from ((f"learning_cards[{i}]", r) for r in card.source_refs)


def _required_checks(analysis: Analysis):
    """Yield findings for required fields that must be non-empty."""
    if not analysis.repo_identity.owner:
        yield "repo_identity.owner", "owner is empty", "error"
    if not analysis.repo_identity.name:
        yield "repo_identity.name", "name is empty", "error"
    if not analysis.repo_identity.canonical_url:
        yield "repo_identity.canonical_url", "canonical_url is empty", "error"
    if not analysis.episode.problem:
        yield "episode.problem", "problem is empty", "error"
    if not analysis.episode.title:
        yield "episode.title", "title is empty", "error"

    def _claim_texts():
        yield "episode.alternatives", analysis.episode.alternatives
        yield "episode.decisions", analysis.episode.decisions
        yield "episode.validation", analysis.episode.validation
        yield "claims", analysis.claims

    for label, claims in _claim_texts():
        for i, c in enumerate(claims):
            if not c.text:
                yield f"{label}[{i}].text", "claim text is empty", "error"
            if c.evidence_status == EvidenceStatus.SOURCED and not c.source_refs:
                yield f"{label}[{i}]", "sourced claim has no source_refs", "warning"

    for i, card in enumerate(analysis.learning_cards):
        if not card.decision:
            yield f"learning_cards[{i}].decision", "decision is empty", "error"
        if not card.small_experiment.hypothesis:
            yield f"learning_cards[{i}].small_experiment.hypothesis", "hypothesis is empty", "error"
        if not card.small_experiment.stop_condition:
            yield f"learning_cards[{i}].small_experiment.stop_condition", "stop_condition is empty", "error"

    for i, link in enumerate(analysis.feedback_links):
        if not link.rationale:
            yield f"feedback_links[{i}].rationale", "rationale is empty", "error"
        if link.relation == Relation.EXPLICIT and (not link.feedback_refs or not link.development_refs):
            yield (
                f"feedback_links[{i}]",
                "explicit relation requires both feedback_refs and development_refs",
                "warning",
            )


def _is_url_field(path: str) -> bool:
    """True when ``path`` names a URL-bearing field (not arbitrary free text)."""
    leaf = re.split(r"[.\[]", path)[-1].lower()
    return "url" in leaf or leaf in ("website", "homepage", "link", "permalink")


def _check_scheme(value, field: str, errors: list) -> None:
    """Reject any non-http(s) URI scheme on a URL field."""
    text = (value or "").strip()
    if not text:
        return
    m = _SCHEME_RE.match(text)
    if m and m.group(1).lower() not in ("http", "https"):
        errors.append({
            "field": field,
            "message": f"non-http(s) URL scheme {m.group(1)!r}",
            "severity": "error",
        })


def validate(request: RequestSpec, run_dir: Path) -> dict:
    """Validate ``analysis.json`` against collected material.

    Returns ``{valid, errors, warnings, counts}`` where ``errors``/``warnings``
    are lists of ``{field, message, severity}``.
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    # 1. Load analysis (validating against the schema for clean error paths).
    analysis_path = run_dir / workspace.ANALYSIS_FILE
    if not analysis_path.exists():
        return {
            "valid": False,
            "errors": [{"field": "analysis.json", "message": "analysis.json not found", "severity": "error"}],
            "warnings": [],
            "counts": {"sources": 0, "refs": 0, "unresolved_refs": 0},
        }
    raw = analysis_path.read_text(encoding="utf-8")
    try:
        analysis = Analysis.model_validate_json(raw)
    except Exception as exc:
        return {
            "valid": False,
            "errors": [{"field": "analysis.json", "message": f"invalid analysis: {exc}", "severity": "error"}],
            "warnings": [],
            "counts": {"sources": 0, "refs": 0, "unresolved_refs": 0},
        }

    # 2. Load collected material.
    sources = workspace.read_sources(run_dir)
    by_id: dict[str, SourceRecord] = {s.id: s for s in sources.records}

    # 3. SourceRef integrity.
    refs = list(_collect_refs(analysis))
    unresolved = 0
    for field, ref in refs:
        source = by_id.get(ref.source_id)
        if source is None:
            errors.append({
                "field": field,
                "message": f"SourceRef points to missing source {ref.source_id!r}",
                "severity": "error",
            })
            unresolved += 1
        elif source.kind == SourceKind.SEARCH_RESULT:
            warnings.append({
                "field": field,
                "message": f"SourceRef {ref.source_id!r} is a search summary only (marked partial)",
                "severity": "warning",
            })

    # 4. Required fields.
    for field, message, severity in _required_checks(analysis):
        (errors if severity == "error" else warnings).append(
            {"field": field, "message": message, "severity": severity}
        )

    # 5. Disabled expressions over analysis free text.
    dumped = analysis.model_dump(mode="json")
    for path, value in _walk_strings(dumped):
        m = _DISABLED_EXPRESSIONS.search(value)
        if m:
            warnings.append({
                "field": path,
                "message": f"disabled evaluative expression in text: {m.group(0)!r}",
                "severity": "warning",
            })

    # 6. URL scheme on URL fields only (analysis + collected sources).
    for path, value in _walk_strings(dumped):
        if _is_url_field(path):
            _check_scheme(value, path, errors)
    for s in sources.records:
        _check_scheme(s.url, f"source.{s.id}.url", errors)
        _check_scheme(s.canonical_url, f"source.{s.id}.canonical_url", errors)

    # 7. Credential leak — analysis + sources + search-log.
    token = os.environ.get("GITHUB_TOKEN", "")
    scan_strings = [v for _, v in _walk_strings(dumped)]
    scan_strings += [s.body for s in sources.records]
    scan_strings += [s.url for s in sources.records]
    scan_strings += [s.canonical_url for s in sources.records]
    search_log = workspace.read_search(run_dir)
    scan_strings += [r.model_dump_json() for r in search_log.records]
    for value in scan_strings:
        if token and token in value:
            errors.append({"field": "content", "message": "credential (GITHUB_TOKEN) leaked into content", "severity": "error"})
            break
        if _CREDENTIAL_PATTERN.search(value):
            errors.append({"field": "content", "message": "credential-like pattern found in content", "severity": "error"})
            break

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "sources": len(sources.records),
            "refs": len(refs),
            "unresolved_refs": unresolved,
        },
    }
