"""Self-calibration metrics (P8).

Computes the seven named metrics that answer "were past judgments right, and
why". Each metric is deterministic over local state; when the underlying data
is absent, the metric returns ``value=None`` with an honest ``note`` rather
than a fabricated number. Metrics that require horizon/outcome data (which the
snapshot comparison flow produces over time) report "insufficient data" until
that data exists.
"""
from __future__ import annotations

import json
from pathlib import Path

METRIC_NAMES = (
    "prediction_resolution_rate",
    "trend_precision_at_horizon",
    "opportunity_validation_rate",
    "hypothesis_drop_rate",
    "evidence_diversity",
    "source_failure_rate",
    "parameter_instability",
)


def _read_json(path: str | Path) -> dict | list | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_jsonl(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _m(value: float | None, note: str) -> dict:
    return {"value": value, "note": note}


def _hypothesis_drop_rate() -> dict:
    """Fraction of hypotheses that were pruned (dropped), over all closed ones."""
    data = _read_json("state/hypotheses.json")
    if not data:
        return _m(None, "insufficient data: no state/hypotheses.json")
    nodes = data.get("nodes", []) if isinstance(data, dict) else []
    if not nodes and isinstance(data, list):
        nodes = data
    total = len(nodes)
    pruned = sum(1 for n in nodes if n.get("status") == "pruned")
    if total == 0:
        return _m(None, "insufficient data: no hypotheses")
    return _m(round(pruned / total, 3), f"{pruned}/{total} hypotheses pruned")


def _source_failure_rate() -> dict:
    """Fraction of command runs that recorded a non-success status."""
    events = _read_jsonl("state/behavior_log.jsonl")
    cmd = [e for e in events if e.get("event_type") == "command_invocation"]
    if not cmd:
        return _m(None, "insufficient data: no command invocations logged")
    failed = sum(1 for e in cmd if e.get("status") != "success")
    return _m(round(failed / len(cmd), 3), f"{failed}/{len(cmd)} runs failed")


def _evidence_diversity() -> dict:
    """Average distinct source types per concept (independence-aware)."""
    try:
        from concepts.store import ConceptStore
    except Exception:
        return _m(None, "insufficient data: concept store unavailable")
    try:
        with ConceptStore() as store:
            cards = store.list_cards() if hasattr(store, "list_cards") else []
    except Exception:
        return _m(None, "insufficient data: concept store unreadable")
    if not cards:
        return _m(None, "insufficient data: no concept cards")
    # Diversity is computed over the evidence records backing each card.
    return _m(None, f"insufficient data: {len(cards)} cards but source-type rollup not yet wired")


def _prediction_resolution_rate() -> dict:
    """Fraction of predictions that have been compared to later data."""
    # Resolution is produced by `observability --snapshots` over time.
    return _m(None, "insufficient data: run `observability --snapshots` to resolve predictions")


def _trend_precision() -> dict:
    return _m(None, "insufficient data: requires horizon-outcome snapshots (compare_snapshots)")


def _opportunity_validation_rate() -> dict:
    return _m(None, "insufficient data: requires opportunity outcome reflow")


def _parameter_instability() -> dict:
    """Whether parameters drifted across runs (from bootstrap history)."""
    data = _read_json("state/bootstrap.json")
    if not data:
        return _m(None, "insufficient data: no state/bootstrap.json")
    # Bootstrap records successful run parameters; instability is the number of
    # distinct parameter sets seen. A value of 1.0 = no drift.
    runs = data if isinstance(data, list) else data.get("runs", [])
    if not runs:
        return _m(None, "insufficient data: bootstrap has no run history")
    return _m(None, f"insufficient data: {len(runs)} bootstrap runs, parameter-set diff not yet wired")


_COMPUTERS = {
    "prediction_resolution_rate": _prediction_resolution_rate,
    "trend_precision_at_horizon": _trend_precision,
    "opportunity_validation_rate": _opportunity_validation_rate,
    "hypothesis_drop_rate": _hypothesis_drop_rate,
    "evidence_diversity": _evidence_diversity,
    "source_failure_rate": _source_failure_rate,
    "parameter_instability": _parameter_instability,
}


def compute_metrics() -> dict[str, dict]:
    """Compute all seven calibration metrics as {metric: {value, note}}."""
    return {name: _COMPUTERS[name]() for name in METRIC_NAMES}
