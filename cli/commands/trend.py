"""trend — compute topic-level trend velocity and staging from signals."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from signals.store import SignalStore
from signals.models import Signal
from intelligence.trend.velocity import compute_acceleration
from models.payload import (
    SandboxResult, TrendPayload, TopicTrend, RepoSummary,
)

console = Console()


def _resolve_stage(velocity: float, acceleration: float, confidence: float) -> str:
    """Assign lifecycle stage based on velocity + acceleration."""
    if acceleration > 2.0 and confidence > 0.6:
        return "accelerating"
    if acceleration > 0.5 and confidence > 0.3:
        return "emerging"
    if acceleration < -1.0:
        return "declining"
    return "mainstream"


def trend(
    domain: str = typer.Argument(..., help="Domain name"),
    data: str = typer.Option("output/signals.json", "--data", "-d", help="Input signals JSON"),
    window: int = typer.Option(60, "--window", "-w", help="Time window in days"),
    output: str = typer.Option("output/trends.json", "--output", "-o", help="Output JSON file"),
) -> None:
    """Compute topic trends from collected signals."""
    data_path = Path(data)
    if not data_path.exists():
        console.print(f"[red]Input file not found: {data}[/red]")
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
        t.stage = _resolve_stage(t.growth_velocity, accel, t.confidence)

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

    result = SandboxResult(
        command="trend",
        domain=domain,
        payload=TrendPayload(trends=trends, domain=domain, window_days=window).model_dump(),
        stats={"total_trends": len(trends)},
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    console.print(f"[green]{len(trends)} trends computed → {output}[/green]")
    for t in trends[:5]:
        console.print(f"  {t.stage:15s} {t.topic:25s} v={t.growth_velocity:.1f}")
