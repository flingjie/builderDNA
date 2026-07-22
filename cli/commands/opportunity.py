"""opportunity — rule-engine scorer that generates opportunity cards.

No LLM calls. Uses deterministic formulas:
  demand_score = f(trend_velocity, pain_severity, pain_frequency)
  competition_score = f(evidence_count, repo_maturity)
  gap_score = demand / competition
"""
import json
import math
from pathlib import Path

import typer
from rich.console import Console

from models.payload import (
    SandboxResult, OpportunityPayload, OpportunityCard,
)

console = Console()


def _compute_demand(trends: list[dict], pain_clusters: list[dict]) -> float:
    """Demand score from trend velocity + pain intensity."""
    avg_velocity = sum(t.get("growth_velocity", 0) for t in trends) / max(1, len(trends))
    avg_severity = sum(p.get("severity", 0) for p in pain_clusters) / max(1, len(pain_clusters))
    total_frequency = sum(p.get("frequency", 0) for p in pain_clusters)

    # Normalize to 1-10
    vel_score = min(10, avg_velocity / 10)  # velocity 100 → 10
    pain_score = min(10, avg_severity * 2)  # severity 5 → 10
    freq_score = min(10, math.log(total_frequency + 1) * 3)  # log scale

    return round((vel_score * 0.4 + pain_score * 0.4 + freq_score * 0.2), 1)


def _compute_competition(trends: list[dict]) -> float:
    """Competition score: more evidence → more crowded."""
    total_evidence = sum(t.get("evidence_count", 0) for t in trends)
    total_repos = sum(len(t.get("top_repos", [])) for t in trends)

    # More repos + higher count = more competition
    raw = math.log(total_evidence + 1) * 1.5 + math.log(total_repos + 1)
    return round(min(10, max(1, raw)), 1)


def _generate_actions(trends: list[dict], pain_clusters: list[dict]) -> list[OpportunityCard]:
    """Generate opportunity cards from trend + pain intersections."""
    cards = []
    top_trends = sorted(trends, key=lambda t: t.get("growth_velocity", 0), reverse=True)[:5]
    top_pains = sorted(pain_clusters, key=lambda p: p.get("severity", 0), reverse=True)[:5]

    for trend in top_trends:
        topic = trend.get("topic", "unknown")
        velocity = trend.get("growth_velocity", 0)

        # Find intersecting pain clusters
        related_pains = [
            p for p in top_pains
            if any(topic.lower() in r.lower() for r in p.get("affected_repos", []))
        ] or top_pains[:2]

        demand = _compute_demand([trend], related_pains)
        competition = _compute_competition([trend])
        gap = round(demand / max(0.1, competition), 1)

        # Signal list from evidence
        signals = []
        for r in trend.get("top_repos", [])[:3]:
            signals.append(f"{r.get('full_name', '')} ({r.get('stars', 0)}★)")
        for p in related_pains[:1]:
            for iss in p.get("top_issues", [])[:2]:
                signals.append(f"Issue: {iss.get('title', '')[:60]}")

        # Heuristic action recommendation
        if gap > 2.0:
            action = f"强烈推荐在 {topic} 方向创业或立项，缺口显著"
        elif gap > 1.5:
            action = f"密切关注 {topic}，需求强但已有竞争，需差异化切入"
        elif gap > 1.0:
            action = f"跟踪 {topic} 发展，等待更明确的市场信号"
        else:
            action = f"暂不建议进入 {topic}，竞争饱和或需求不足"

        cards.append(OpportunityCard(
            title=f"{topic} — gap={gap}",
            demand_score=demand,
            competition_score=competition,
            gap_score=gap,
            signals=signals[:5],
            recommended_action=action,
        ))

    cards.sort(key=lambda c: c.gap_score, reverse=True)
    return cards


def opportunity(
    trends: str = typer.Option(..., "--trends", "-t", help="Input trends JSON"),
    pains: str = typer.Option(..., "--pains", "-p", help="Input pain clusters JSON"),
    output: str = typer.Option("output/opportunities.json", "--output", "-o", help="Output JSON file"),
) -> None:
    """Generate opportunity cards from trends and pain clusters (rule engine)."""
    trends_path = Path(trends)
    pains_path = Path(pains)
    if not trends_path.exists():
        console.print(f"[red]Trends file not found: {trends}[/red]")
        raise typer.Exit(1)
    if not pains_path.exists():
        console.print(f"[yellow]Pain file not found: {pains}. Continuing without pain data.[/yellow]")
        pains_data = {"payload": {"clusters": []}}
    else:
        pains_data = json.loads(pains_path.read_text())

    trends_data = json.loads(trends_path.read_text())
    t_payload = trends_data.get("payload", trends_data)
    p_payload = pains_data.get("payload", pains_data)

    trend_list = t_payload.get("trends", [])
    pain_list = p_payload.get("clusters", [])

    cards = _generate_actions(trend_list, pain_list)

    result = SandboxResult(
        command="opportunity",
        domain=t_payload.get("domain", ""),
        payload=OpportunityPayload(opportunities=cards).model_dump(),
        stats={
            "total": len(cards),
            "avg_gap": round(sum(c.gap_score for c in cards) / max(1, len(cards)), 2),
        },
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    console.print(f"[green]{len(cards)} opportunities → {output}[/green]")
    for c in cards[:5]:
        console.print(f"  gap={c.gap_score:.1f}  {c.title}")
