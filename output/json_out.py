"""JSON report generator."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_json(result: dict[str, Any], output_dir: str | Path) -> Path:
    """Write a JSON report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_id = result.get("snapshot_id", "unknown")
    filepath = output_dir / f"report-{ts}-{snapshot_id}.json"

    data = {
        "snapshot_id": snapshot_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signals": [_serialize_signal(s) for s in result.get("signals", [])],
        "insights": [_serialize_insight(i) for i in result.get("insights", [])],
        "opportunities": [_serialize_opportunity(o) for o in result.get("opportunities", [])],
    }
    if result.get("diff"):
        data["diff"] = result["diff"]

    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return filepath


def _serialize_signal(s):
    return {"id": s.id, "source": s.source, "type": s.type, "timestamp": s.timestamp.isoformat(),
            "weight": s.weight, "actor": s.actor, "target": s.target, "meta": s.meta, "raw": s.raw}


def _serialize_insight(i):
    return {"id": i.id, "tags": i.tags, "summary": i.summary, "strength": i.strength,
            "trend": i.trend, "signal_count": i.signal_count, "evidence": i.evidence,
            "created_at": i.created_at.isoformat()}


def _serialize_opportunity(o):
    return {"id": o.id, "title": o.title, "pain_point": o.pain_point, "demand_score": o.demand_score,
            "competition_score": o.competition_score, "gap_score": o.gap_score,
            "recommended_action": o.recommended_action, "source_insights": o.source_insights,
            "created_at": o.created_at.isoformat()}
