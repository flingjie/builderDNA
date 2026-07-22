"""BuilderDNA 2.0 CLI — Typer entry point."""
import asyncio
import typer
from rich.console import Console

from cli.formatters import render_trends, render_opportunities
from pipeline.graph import build_pipeline

app = typer.Typer(name="builderdna", help="BuilderDNA — Technology Evolution Intelligence Engine")
console = Console()


@app.command()
def radar(
    domain: str = typer.Argument("agent", help="Domain to analyze"),
    window: int = typer.Option(60, "--window", "-w"),
    mode: str = typer.Option("full_auto", "--mode", "-m"),
):
    """Run the full 8-node analysis pipeline.

    collect → trend → pain → opportunity → [gate] → evidence → critic → report
    """
    console.print(f"[bold]BuilderDNA Radar[/bold] — {domain} ({window}d, {mode})")

    async def _run():
        graph = build_pipeline(mode)
        state = await graph.ainvoke(
            {
                "domain": domain,
                "window_days": window,
                "mode": mode,
            },
            {"configurable": {"thread_id": f"cli-{domain}"}},
        )
        trends = state.get("topic_trends", [])
        opportunities = state.get("opportunities", [])

        if trends:
            render_trends(trends)
        else:
            console.print("[yellow]No trends detected — collect node may have returned empty.[/yellow]")

        if opportunities:
            render_opportunities(opportunities)

        report = state.get("report_path", "")
        if report:
            for path in report.split("\n"):
                if path.strip():
                    console.print(f"[dim]Report: {path}[/dim]")
        console.print("\n[bold green]Done![/bold green]")

    asyncio.run(_run())


@app.command()
def opportunities(domain: str = typer.Argument("agent")):
    """Generate technology/business opportunities."""
    console.print(f"[bold]Opportunity Intelligence[/bold] — {domain}")
    console.print("[dim]Run 'builderdna radar <domain>' for full analysis.[/dim]")


@app.command()
def health():
    """Check system health."""
    from backend.dependencies import get_config
    cfg = get_config()
    console.print("[green]BuilderDNA 2.0 ready.[/green]")
    console.print(f"  Embedding: {cfg.embedding.model} @ {cfg.embedding.base_url}")
    console.print(f"  Domain: {list(cfg.domains.keys())}")


if __name__ == "__main__":
    app()
