"""trend — compute topic-level trend velocity and staging from signals."""
import json
import math
from pathlib import Path

import typer

from signals.store import SignalStore
from signals.models import Signal
from intelligence.trend.velocity import compute_acceleration
from models.payload import (
    SandboxResult, TrendPayload, TopicTrend, RepoSummary,
    Diagnostics, DataQualityDiag, ConfidenceDiag,
)
from observability import RunTelemetry, OutputLevel, vprint, record_command, record_output_retention
from observability.snapshot import save_trend_snapshot


def _resolve_stage(velocity: float, acceleration: float, confidence: float) -> tuple[str, str]:
    """Assign lifecycle stage based on velocity + acceleration.

    Returns:
        (stage, reason) — stage string and human-readable justification.
    """
    if acceleration > 2.0 and confidence > 0.6:
        return "accelerating", f"acceleration={acceleration:.1f} (>2.0) + confidence={confidence:.2f} (>0.6) → accelerating"
    if acceleration > 0.5 and confidence > 0.3:
        return "emerging", f"acceleration={acceleration:.1f} (>0.5) + confidence={confidence:.2f} (>0.3) → emerging"
    if acceleration < -1.0:
        return "declining", f"acceleration={acceleration:.1f} (<-1.0) → declining"
    return "mainstream", f"acceleration={acceleration:.1f}, confidence={confidence:.2f} → mainstream (default)"


def trend(
    domain: str = typer.Argument(..., help="Domain name"),
    data: str = typer.Option("output/signals.json", "--data", "-d", help="Input signals JSON"),
    window: int = typer.Option(365, "--window", "-w", help="Time window in days"),
    output: str = typer.Option("output/trends.json", "--output", "-o", help="Output JSON file"),
) -> None:
    """Compute topic trends from collected signals."""
    tel = RunTelemetry()
    data_path = Path(data)
    if not data_path.exists():
        vprint(f"[red]Input file not found: {data}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    raw = json.loads(data_path.read_text())
    payload = raw.get("payload", raw)

    # Reconstruct Signal objects — prefer normalized signals when available
    signal_dicts = payload.get("signals", [])
    if signal_dicts:
        repo_signals = [Signal(**s) for s in signal_dicts]
    else:
        # Fallback: reconstruct from flat repo signals (older collect output format)
        repo_signals = []
        for r in payload.get("repos", []):
            s = Signal(
                source="github",
                type="repo_created",
                actor=r.get("owner", ""),
                target_repo=r.get("full_name", ""),
                velocity=r.get("velocity", 0),
                impact=min(1.0, r.get("stars", 0) / 10000.0),
                payload={
                    "topics": r.get("topics", []),
                    "stars": r.get("stars", 0),
                    "forks": r.get("forks", 0),
                    "contributors": r.get("contributors", 0),
                    "description": r.get("description", ""),
                    "created_at": r.get("created_at", ""),
                },
            )
            repo_signals.append(s)

    # Insert into store and query aggregated trends
    with SignalStore() as store:
        store.insert(repo_signals)
        trend_rows = store.get_topic_trends(days=window)

    # Group signals by topic
    topic_signals: dict[str, list[Signal]] = {}
    for s in repo_signals:
        for topic in s.payload.get("topics", []):
            topic_signals.setdefault(topic, []).append(s)

    # Build trend output — enrich store results with acceleration, stage, top_repos
    trends = []
    for t in trend_rows:
        sigs = topic_signals.get(t.topic, [])
        accel = compute_acceleration(sigs, window_days=window)
        t.acceleration = round(accel, 2)
        stage, reason = _resolve_stage(t.growth_velocity, accel, t.confidence)
        t.stage = stage
        t.classification_reason = reason

        # Build top_repos from raw signal data
        topic_repos: dict[str, dict] = {}
        for s in sigs:
            name = s.target_repo
            if name not in topic_repos:
                payload = s.payload
                topic_repos[name] = {
                    "full_name": name,
                    "stars": payload.get("stars", 0),
                    "forks": payload.get("forks", 0),
                    "contributors": payload.get("contributors", 0),
                    "velocity": s.velocity,
                }
        sorted_repos = sorted(
            topic_repos.values(), key=lambda r: r["stars"], reverse=True
        )[:5]
        t.top_repos = [
            RepoSummary(
                full_name=r["full_name"],
                stars=r["stars"],
                forks=r["forks"],
                contributors=r["contributors"],
                velocity=r["velocity"],
            )
            for r in sorted_repos
        ]

        trends.append(t)

    trends.sort(key=lambda x: x.growth_velocity, reverse=True)

    # ── Build diagnostics ──────────────────────────────────────────
    diag = Diagnostics()

    # data_quality: topics with zero matching repos
    topic_with_signals: set[str] = set()
    for s in repo_signals:
        for t in s.payload.get("topics", []):
            topic_with_signals.add(t)

    # Get all topic names from trend rows
    all_trend_topics = {t.topic for t in trends}
    for topic in all_trend_topics:
        if topic not in topic_with_signals:
            diag.data_quality.coverage_gaps.append(
                f"topic '{topic}' has no matching repos in signals — may be from stored data or empty"
            )

    if len(repo_signals) < 10:
        diag.data_quality.sample_size_warning = (
            f"Only {len(repo_signals)} signals available — trend confidence will be low. "
            f"Consider re-running collect with more topics or a longer window."
        )

    # confidence: low-evidence trends
    for t in trends:
        if t.evidence_count < 3:
            diag.confidence.low_confidence_items.append({
                "item": t.topic,
                "confidence": round(t.confidence, 2),
                "reason": f"only {t.evidence_count} repo(s) support this trend — need ≥3 for reliable signal",
            })
        if t.confidence < 0.2:
            diag.confidence.low_confidence_items.append({
                "item": t.topic,
                "confidence": round(t.confidence, 2),
                "reason": "confidence below 0.2 — this trend may be noise; consider adjusting topic scope or window",
            })

    result = SandboxResult(
        command="trend",
        domain=domain,
        payload=TrendPayload(trends=trends, domain=domain, window_days=window).model_dump(),
        stats={"total_trends": len(trends), **tel.to_stats()},
        diagnostics=diag,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2))
    vprint(f"[green]{len(trends)} trends computed → {output}[/green]", level=OutputLevel.NORMAL)
    vprint(f"[dim]Done in {tel.elapsed_seconds}s[/dim]", level=OutputLevel.NORMAL)
    for t in trends[:5]:
        vprint(f"  {t.stage:15s} {t.topic:25s} v={t.growth_velocity:.1f}", level=OutputLevel.NORMAL)
        vprint(f"    {t.classification_reason}", level=OutputLevel.VERBOSE)

    # Behavior tracking + prediction snapshot
    trend_dicts = [t.model_dump() for t in trends]
    record_command(
        command="trend",
        domain=domain,
        flags={"window": window, "data": data},
        output_path=output,
        user_dna_used=False,
        elapsed_seconds=tel.elapsed_seconds,
        status="success",
    )
    record_output_retention(output)
    save_trend_snapshot(domain=domain, trends=trend_dicts, window_days=window)
