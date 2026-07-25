"""Prediction snapshots and time-based validation.

Saves prediction snapshots after each pipeline run (trend, pain, opportunity)
to predictions/{domain}/{timestamp}.json. Provides comparison logic for
validating past predictions against new data.

Usage:
    from observability.snapshot import save_trend_snapshot, compare_snapshots

    # After trend command succeeds:
    save_trend_snapshot(domain="agent", trends=trend_list, window_days=60)

    # Compare old predictions with latest results:
    comparisons = compare_snapshots(domain="agent")
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

PREDICTIONS_DIR = "predictions"
MIN_COMPARISON_AGE_DAYS = 90  # days before a snapshot is eligible for validation


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _timestamp() -> str:
    """Filesystem-safe timestamp: YYYY-MM-DD-HHMMSS."""
    return datetime.now().strftime("%Y-%m-%d-%H%M%S")


def _ensure_dir(filepath: str) -> None:
    """Ensure parent directory exists for a file path."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)


def _snapshot_dir(domain: str) -> Path:
    """Get (and create) the snapshot directory for a domain."""
    d = Path(PREDICTIONS_DIR) / domain
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_snapshots(domain: str) -> list[Path]:
    """List all snapshot files for a domain, sorted oldest-first."""
    d = Path(PREDICTIONS_DIR) / domain
    if not d.exists():
        return []
    files = sorted(d.glob("*.json"))
    return files


def _read_json(path: str | Path) -> dict | None:
    """Read a JSON file. Returns None if missing or invalid."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ── Snapshot saving ──────────────────────────────────────────────

def _save_snapshot(domain: str, snapshot_type: str, data: dict) -> str:
    """Save a prediction snapshot.

    Args:
        domain: Domain name (e.g. 'agent').
        snapshot_type: 'trend', 'pain', or 'opportunity'.
        data: The prediction data to store (trend/pain/opportunity results).

    Returns:
        Path to the saved snapshot file.
    """
    snapshot = {
        "snapshot_type": snapshot_type,
        "domain": domain,
        "created_at": _now_iso(),
        "threshold_version": "v1",  # current threshold version
        "predictions": data,
    }
    filename = f"{_timestamp()}-{snapshot_type}.json"
    filepath = _snapshot_dir(domain) / filename
    filepath.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    return str(filepath)


def save_trend_snapshot(domain: str, trends: list[dict], window_days: int) -> str:
    """Save trend predictions for future validation.

    Stores each topic's stage, velocity, acceleration, and confidence
    as a prediction to be validated against future runs.
    """
    predictions = []
    for t in trends:
        predictions.append({
            "topic": t.get("topic", ""),
            "stage": t.get("stage", ""),
            "growth_velocity": t.get("growth_velocity", 0),
            "acceleration": t.get("acceleration", 0),
            "confidence": t.get("confidence", 0),
            "evidence_count": t.get("evidence_count", 0),
        })
    return _save_snapshot(domain, "trend", {
        "window_days": window_days,
        "trends": predictions,
    })


def save_pain_snapshot(domain: str, clusters: list[dict], issue_count: int, noise_count: int) -> str:
    """Save pain cluster predictions for future validation.

    Stores each cluster's severity, frequency, and affected repos.
    """
    predictions = []
    for c in clusters:
        predictions.append({
            "cluster_id": c.get("cluster_id", 0),
            "title": c.get("title", ""),
            "severity": c.get("severity", 0),
            "frequency": c.get("frequency", 0),
            "affected_repos": c.get("affected_repos", []),
        })
    return _save_snapshot(domain, "pain", {
        "clusters": predictions,
        "issue_count": issue_count,
        "noise_count": noise_count,
    })


def save_opportunity_snapshot(domain: str, cards: list[dict]) -> str:
    """Save opportunity predictions for future validation.

    Stores each card's gap_score, demand_score, competition_score,
    and recommended_action.
    """
    predictions = []
    for c in cards:
        predictions.append({
            "title": c.get("title", ""),
            "gap_score": c.get("gap_score", 0),
            "demand_score": c.get("demand_score", 0),
            "competition_score": c.get("competition_score", 0),
            "recommended_action": c.get("recommended_action", ""),
        })
    return _save_snapshot(domain, "opportunity", {
        "cards": predictions,
    })


# ── Snapshot comparison ──────────────────────────────────────────

def _days_between(iso1: str, iso2: str) -> float:
    """Compute days between two ISO timestamps."""
    try:
        dt1 = datetime.fromisoformat(iso1.replace("Z", "+00:00"))
        dt2 = datetime.fromisoformat(iso2.replace("Z", "+00:00"))
        return abs((dt2 - dt1).total_seconds()) / 86400.0
    except (ValueError, TypeError):
        return 0


def _compare_trend(old: dict, new: dict) -> dict:
    """Compare an old trend prediction with new trend data.

    Returns a comparison result dict with match status.
    Conservative validation: ±20% velocity, strict staging.
    """
    old_stage = old.get("stage", "")
    new_stage = new.get("stage", "")
    old_vel = old.get("growth_velocity", 0)
    new_vel = new.get("growth_velocity", 0)

    result = {
        "topic": old.get("topic", ""),
        "old_stage": old_stage,
        "new_stage": new_stage,
        "old_velocity": old_vel,
        "new_velocity": new_vel,
        "velocity_change_pct": 0.0,
        "status": "unmatched",  # topic not found in new data
    }

    # Compare stages
    stage_order = {"accelerating": 3, "emerging": 2, "mainstream": 1, "declining": 0}
    old_rank = stage_order.get(old_stage, -1)
    new_rank = stage_order.get(new_stage, -1)
    stage_delta = new_rank - old_rank

    # Velocity comparison
    if old_vel != 0:
        vel_change_pct = (new_vel - old_vel) / abs(old_vel)
    else:
        vel_change_pct = 0.0 if new_vel == 0 else float("inf")
    result["velocity_change_pct"] = round(vel_change_pct * 100, 1)

    # Validation logic (conservative: ±20%, strict staging)
    if old_stage in ("accelerating", "emerging") and new_stage in ("accelerating", "emerging") and vel_change_pct >= -0.20:
        # Predicted growth direction, and it continued or held within 20% decline tolerance
        if vel_change_pct >= 0:
            result["status"] = "validated"
            result["detail"] = f"Predicted {old_stage} growth — verified: velocity {'+' if vel_change_pct >= 0 else ''}{vel_change_pct*100:.0f}%, stage={new_stage}"
        else:
            result["status"] = "validated"
            result["detail"] = f"Predicted {old_stage} growth — held within tolerance: velocity {vel_change_pct*100:.0f}%, stage={new_stage}"
    elif old_stage == "declining" and new_stage in ("declining", "mainstream") and vel_change_pct <= 0.20:
        result["status"] = "validated"
        result["detail"] = f"Predicted decline — verified: velocity {vel_change_pct*100:.0f}%, stage={new_stage}"
    elif stage_delta >= 2:
        # Jumped two stages (e.g. emerging → accelerating, skipping)
        result["status"] = "miss"
        result["detail"] = f"Predicted {old_stage} but jumped to {new_stage} (velocity {vel_change_pct*100:+.0f}%) — too fast for prediction"
    elif stage_delta <= -2:
        result["status"] = "miss"
        result["detail"] = f"Predicted {old_stage} but dropped to {new_stage} (velocity {vel_change_pct*100:+.0f}%) — direction reversed"
    elif old_stage in ("accelerating", "emerging") and new_stage == "declining":
        result["status"] = "miss"
        result["detail"] = f"Predicted growth ({old_stage}) but declined (velocity {vel_change_pct*100:+.0f}%) — complete reversal"
    elif old_stage == "mainstream" and new_stage == "mainstream":
        result["status"] = "neutral"
        result["detail"] = f"Stayed mainstream — stable, velocity {vel_change_pct*100:+.0f}%"
    else:
        result["status"] = "neutral"
        result["detail"] = f"Stage: {old_stage}→{new_stage}, velocity {vel_change_pct*100:+.0f}% — within tolerance"

    return result


def compare_snapshots(domain: str) -> list[dict]:
    """Compare old prediction snapshots with the latest run for a domain.

    Finds the oldest snapshot ≥90 days old and compares it with the most
    recent snapshot of the same type.

    Returns a list of comparison results, one per snapshot type.
    """
    files = _list_snapshots(domain)
    if len(files) < 2:
        return []

    now = _now_iso()
    comparisons = []

    # Group by snapshot type
    by_type: dict[str, list[Path]] = {}
    for f in files:
        snap = _read_json(f)
        if not snap:
            continue
        stype = snap.get("snapshot_type", "")
        by_type.setdefault(stype, []).append(f)

    for stype, type_files in by_type.items():
        if len(type_files) < 2:
            continue

        # Oldest = first (files sorted by name/date), newest = last
        oldest_file = type_files[0]
        newest_file = type_files[-1]

        old_snap = _read_json(oldest_file)
        new_snap = _read_json(newest_file)
        if not old_snap or not new_snap:
            continue

        old_date = old_snap.get("created_at", "")
        days_old = _days_between(old_date, now)
        if days_old < MIN_COMPARISON_AGE_DAYS:
            continue

        # Compare based on type
        old_preds = old_snap.get("predictions", {})
        new_preds = new_snap.get("predictions", {})

        if stype == "trend":
            results = _compare_trend_snapshots(old_preds, new_preds)
        elif stype == "opportunity":
            results = _compare_opportunity_snapshots(old_preds, new_preds)
        elif stype == "pain":
            results = _compare_pain_snapshots(old_preds, new_preds)
        else:
            continue

        comparisons.append({
            "snapshot_type": stype,
            "old_date": old_date,
            "new_date": new_snap.get("created_at", ""),
            "days_elapsed": round(days_old, 1),
            "results": results,
        })

    return comparisons


def _match_trend_by_topic(topic: str, trends: list[dict]) -> dict | None:
    """Find a trend by topic name (fuzzy match)."""
    for t in trends:
        if t.get("topic", "").lower() == topic.lower():
            return t
    return None


def _compare_trend_snapshots(old_preds: dict, new_preds: dict) -> list[dict]:
    """Compare trend predictions across two snapshots."""
    old_trends = old_preds.get("trends", [])
    new_trends = new_preds.get("trends", [])

    results = []
    for old_t in old_trends:
        new_t = _match_trend_by_topic(old_t.get("topic", ""), new_trends)
        if new_t:
            results.append(_compare_trend(old_t, new_t))
        else:
            results.append({
                "topic": old_t.get("topic", ""),
                "status": "unmatched",
                "detail": "Topic no longer present in latest analysis",
            })
    return results


def _compare_opportunity_snapshots(old_preds: dict, new_preds: dict) -> list[dict]:
    """Compare opportunity predictions across two snapshots (numeric only).

    Opportunity validation is numeric comparison only — semantic interpretation
    is left to the builderdna skill.
    """
    old_cards = old_preds.get("cards", [])
    new_cards = new_preds.get("cards", [])

    results = []
    for old_c in old_cards:
        old_title = old_c.get("title", "")
        old_gap = old_c.get("gap_score", 0)

        # Find best match by title prefix (titles are like "topic — gap=X.X")
        old_topic = old_title.split(" — ")[0] if " — " in old_title else old_title
        new_c = None
        for nc in new_cards:
            nc_topic = nc.get("title", "").split(" — ")[0] if " — " in nc.get("title", "") else nc.get("title", "")
            if nc_topic.lower() == old_topic.lower():
                new_c = nc
                break

        if new_c:
            new_gap = new_c.get("gap_score", 0)
            gap_change = new_gap - old_gap
            results.append({
                "title": old_title,
                "old_gap": old_gap,
                "new_gap": new_gap,
                "gap_delta": round(gap_change, 2),
                "old_action": old_c.get("recommended_action", ""),
                "new_action": new_c.get("recommended_action", ""),
                "status": "compared",
            })
        else:
            results.append({
                "title": old_title,
                "status": "unmatched",
                "detail": "Opportunity no longer present in latest analysis",
            })

    return results


def _compare_pain_snapshots(old_preds: dict, new_preds: dict) -> list[dict]:
    """Compare pain cluster predictions across two snapshots."""
    old_clusters = old_preds.get("clusters", [])
    new_clusters = new_preds.get("clusters", [])

    results = []
    for old_c in old_clusters:
        old_id = old_c.get("cluster_id", -1)
        new_c = None
        for nc in new_clusters:
            if nc.get("cluster_id") == old_id:
                new_c = nc
                break

        if new_c:
            old_sev = old_c.get("severity", 0)
            new_sev = new_c.get("severity", 0)
            sev_change_pct = (new_sev - old_sev) / max(0.1, old_sev) * 100
            results.append({
                "cluster_id": old_id,
                "title": old_c.get("title", ""),
                "old_severity": old_sev,
                "new_severity": new_sev,
                "severity_change_pct": round(sev_change_pct, 1),
                "old_frequency": old_c.get("frequency", 0),
                "new_frequency": new_c.get("frequency", 0),
                "status": "compared",
            })
        else:
            results.append({
                "cluster_id": old_id,
                "title": old_c.get("title", ""),
                "status": "unmatched",
                "detail": "Cluster no longer present in latest analysis",
            })

    return results
