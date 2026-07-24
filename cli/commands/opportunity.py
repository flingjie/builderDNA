"""opportunity — generate opportunity cards from trends + pain clusters.

Delegates scoring to intelligence/opportunity/scoring.py and alignment
to intelligence/opportunity/alignment.py. The CLI command is a thin
orchestrator: read inputs → score → render → write output.

With User DNA integration:
  personalized_score = gap_score × alignment_multiplier
"""
import json
from pathlib import Path

import typer
from rich.console import Console

from models.payload import (
    SandboxResult, OpportunityPayload, OpportunityCard,
)
from state.user_dna_schema import load_user_dna
from intelligence.opportunity.scoring import (
    compute_demand, compute_competition, compute_gap, recommend_action,
)
from intelligence.opportunity.alignment import compute_alignment

console = Console()


def _generate_cards(
    trends: list[dict],
    pain_clusters: list[dict],
    user_dna= None,
) -> list[OpportunityCard]:
    """Generate opportunity cards from trend + pain intersections."""
    cards = []
    top_trends = sorted(trends, key=lambda t: t.get("growth_velocity", 0), reverse=True)[:5]
    top_pains = sorted(pain_clusters, key=lambda p: p.get("severity", 0), reverse=True)[:5]

    for trend in top_trends:
        topic = trend.get("topic", "unknown")

        related_pains = [
            p for p in top_pains
            if any(topic.lower() in r.lower() for r in p.get("affected_repos", []))
        ] or top_pains[:2]

        demand = compute_demand([trend], related_pains)
        competition = compute_competition([trend])
        gap = compute_gap(demand, competition)

        signals = []
        top_repos = trend.get("top_repos", [])
        for r in top_repos[:3]:
            signals.append(f"{r.get('full_name', '')} ({r.get('stars', 0)}★)")
        for p in related_pains[:1]:
            for iss in p.get("top_issues", [])[:2]:
                signals.append(f"Issue: {iss.get('title', '')[:60]}")

        action = recommend_action(topic, gap)

        # Alignment
        personalized_score = None
        alignment_reason = ""
        alignment_multiplier = 1.0
        if user_dna:
            alignment_multiplier, alignment_reason = compute_alignment(
                trend, top_repos, user_dna
            )
            personalized_score = round(gap * alignment_multiplier, 1)

        cards.append(OpportunityCard(
            title=f"{topic} — gap={gap}",
            demand_score=demand,
            competition_score=competition,
            gap_score=gap,
            signals=signals[:5],
            recommended_action=action,
            personalized_score=personalized_score,
            alignment_reason=alignment_reason,
            alignment_multiplier=alignment_multiplier,
        ))

    cards.sort(key=lambda c: c.personalized_score if c.personalized_score is not None else c.gap_score, reverse=True)
    return cards


def opportunity(
    trends: str = typer.Option(..., "--trends", "-t", help="Input trends JSON"),
    pains: str = typer.Option(..., "--pains", "-p", help="Input pain clusters JSON"),
    output: str = typer.Option("output/opportunities.json", "--output", "-o", help="Output JSON file"),
    user_dna: str = typer.Option("state/user_dna.json", "--user-dna", help="User DNA file for personalization"),
) -> None:
    """Generate opportunity cards from trends and pain clusters (rule engine).

    Optionally applies User DNA for personalized scoring.
    """
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

    # Load User DNA if available
    dna = load_user_dna(user_dna)
    if dna:
        console.print(f"[dim]User DNA loaded — applying personalized alignment[/dim]")

    cards = _generate_cards(trend_list, pain_list, dna)

    result = SandboxResult(
        command="opportunity",
        domain=t_payload.get("domain", ""),
        payload=OpportunityPayload(opportunities=cards).model_dump(),
        stats={
            "total": len(cards),
            "avg_gap": round(sum(c.gap_score for c in cards) / max(1, len(cards)), 2),
            "personalized": dna is not None,
        },
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    console.print(f"[green]{len(cards)} opportunities → {output}[/green]")
    for c in cards[:5]:
        base = f"gap={c.gap_score:.1f}"
        if c.personalized_score is not None:
            base += f"  personal={c.personalized_score:.1f} (×{c.alignment_multiplier:.2f})"
        console.print(f"  {base}  {c.title}")
