from rich.console import Console
from rich.table import Table

console = Console()


def render_trends(trends: list[dict]):
    table = Table(title="Trend Radar")
    table.add_column("Topic", style="cyan")
    table.add_column("Stage")
    table.add_column("Velocity")
    table.add_column("Confidence")
    for t in trends:
        stage_color = {
            "accelerating": "green",
            "emerging": "yellow",
            "mainstream": "dim",
            "declining": "red",
        }
        stage = t.get("stage", "unknown")
        table.add_row(
            t.get("topic", ""),
            f"[{stage_color.get(stage, 'white')}]{stage}[/{stage_color.get(stage, 'white')}]",
            f"{t.get('growth_velocity', 0):.1f}",
            f"{t.get('confidence', 0):.0%}",
        )
    console.print(table)


def render_opportunities(opportunities: list[dict]):
    for i, opp in enumerate(opportunities, 1):
        title = opp.get("title", "Untitled")
        score = opp.get("score", 0)
        risk = opp.get("risk", "unknown")
        rc = {"low": "green", "high": "red"}.get(risk, "yellow")
        console.print(f"\n[bold]#{i} {title}[/bold]")
        console.print(f"  Score: {score}/10 | Risk: [{rc}]{risk}[/{rc}]")
        console.print(f"  Why now: {opp.get('why_now', '')}")
        console.print(f"  Problem: {opp.get('problem', '')}")

        repos = opp.get("related_repos", [])
        if repos:
            console.print("  [dim]Related repos:[/dim]")
            for r in repos:
                tag = r.get("vendor_tag", "")
                tag_str = f" [{tag}]" if tag else ""
                console.print(
                    f"    [cyan]{r['full_name']}[/cyan]{tag_str}"
                    f" ★ {r['stars']}  ↑ {r['velocity']:.1f}/d  "
                    f"[dim]{r.get('description', '')[:60]}[/dim]"
                )
