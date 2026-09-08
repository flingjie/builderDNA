"""Algorithm & weight versioning (P8).

A single registry of algorithm-component versions, plus an append-only change
log so every algorithm/weight change records its version bump and the expected
impact. The registry is the source of truth for the ``algorithm_version`` that
each command stamps into its SandboxResult stats; the change log makes
before/after results comparable (the optimize skill can cite it when proposing
parameter changes).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# Component → current version. Bump via ``record_algorithm_change`` (which also
# writes the log); keep this in sync with the change log, not edited by hand.
ALGORITHM_VERSIONS: dict[str, str] = {
    "trend": "1.0",
    "pain": "1.0",
    "opportunity": "1.0",
    "collect": "1.0",
    "developer_dna": "1.0",
    "alignment": "1.0",
    "concept_scoring": "1.0",
    "radar_gate": "1.0",
}

CHANGE_LOG_PATH = "state/algorithm_changes.jsonl"


def algorithm_version(component: str) -> str:
    """Current version for a component (empty string when unknown)."""
    return ALGORITHM_VERSIONS.get(component, "")


def _append_jsonl(path: str, entry: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record_algorithm_change(
    component: str,
    new_version: str,
    expected_impact: str,
    *,
    old_version: str | None = None,
    reason: str = "",
) -> dict:
    """Record an algorithm/weight change and update the registry.

    Appends an immutable entry to ``state/algorithm_changes.jsonl`` and updates
    ``ALGORITHM_VERSIONS`` in place. ``old_version`` defaults to the registry's
    current value so a bump reads naturally.
    """
    old = old_version if old_version is not None else ALGORITHM_VERSIONS.get(component, "unknown")
    entry = {
        "component": component,
        "old_version": old,
        "new_version": new_version,
        "expected_impact": expected_impact,
        "reason": reason,
        "changed_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_jsonl(CHANGE_LOG_PATH, entry)
    ALGORITHM_VERSIONS[component] = new_version
    return entry


def read_algorithm_changes(component: str | None = None) -> list[dict]:
    """Read the change log, optionally filtered to one component."""
    p = Path(CHANGE_LOG_PATH)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if component is None or entry.get("component") == component:
            out.append(entry)
    return out
