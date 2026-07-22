"""BuilderDNA 2.0 CLI — Typer entry point."""
import asyncio
import typer
from rich.console import Console

app = typer.Typer(name="builderdna", help="BuilderDNA — Technology Evolution Intelligence Engine")
console = Console()


@app.command()
def radar(
    domain: str = typer.Argument("agent", help="Domain to analyze"),
    window: int = typer.Option(60, "--window", "-w"),
    mode: str = typer.Option("full_auto", "--mode", "-m"),
):
    """Run Trend Radar analysis."""
    console.print(f"[bold]BuilderDNA Radar[/bold] — {domain} ({window}d)")


@app.command()
def opportunities(domain: str = typer.Argument("agent")):
    """Generate technology/business opportunities."""
    console.print(f"[bold]Opportunity Intelligence[/bold] — {domain}")


@app.command()
def health():
    """Check system health."""
    console.print("[green]BuilderDNA 2.0 ready.[/green]")


if __name__ == "__main__":
    app()
