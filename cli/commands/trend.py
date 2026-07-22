"""trend — compute topic-level trend velocity and staging from signals."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from signals.store import SignalStore
from signals.graph import SignalGraph
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

    # Reconstruct signals
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

    # Insert into store and graph
    store = SignalStore()
    store.insert(repo_signals)
    trend_rows = store.get_topic_trends(days=window)

    graph = SignalGraph()
    graph.build_from_signals(repo_signals)

    # Group signals by topic
    topic_signals: dict[str, list[Signal]] = {}
    for s in repo_signals:
        for topic in s.payload.get("topics", []):
            topic_signals.setdefault(topic, []).append(s)

    # Build trend output
    trends = []
    for t in trend_rows:
        sigs = topic_signals.get(t.topic, [])
        accel = compute_acceleration(sigs, window_days=window)
        stage = _resolve_stage(t.growth_velocity, accel, t.confidence)

        top_repos = []
        for rt in t.top_repos[:5]:
            top_repos.append(RepoSummary(
                full_name=rt.full_name,
                stars=rt.stars,
                stars_delta=rt.stars_delta,
                forks=rt.forks,
                contributors=rt.contributors,
                velocity=rt.velocity,
                description="",
            ))

        trends.append(TopicTrend(
            topic=t.topic,
            stage=stage,
            confidence=t.confidence,
            growth_velocity=t.growth_velocity,
            acceleration=round(accel, 2),
            evidence_count=t.evidence_count,
            top_repos=top_repos,
        ))

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
