"""BuilderDNA CLI entry point."""

import sys
from pathlib import Path

import click
from rich.console import Console

from config import load_config
from pipeline import Pipeline
from output.cli import render as render_cli
from output.markdown import write_markdown
from output.json_out import write_json

console = Console()
DEFAULT_CONFIG = "config.yaml"


@click.group()
@click.version_option(version="0.1.0", prog_name="bldr-dna")
def main():
    """BuilderDNA — Analyze GitHub builders, extract tech DNA, discover opportunities."""


@main.command()
@click.option("--config", "-c", default=DEFAULT_CONFIG, help="Path to config.yaml")
@click.option("--compare/--no-compare", default=None, help="Force incremental comparison mode")
def run(config: str, compare: bool | None):
    """Run the full BuilderDNA analysis pipeline."""
    config_path = Path(config)
    if not config_path.exists():
        console.print(f"[red]Config file not found: {config_path}[/red]")
        sys.exit(1)

    cfg = load_config(config_path)
    do_compare = compare if compare is not None else cfg.compare.enabled
    if do_compare:
        console.print("[yellow]Running in compare mode[/yellow]")

    pipeline = Pipeline(cfg)
    with console.status("[bold green]Analyzing...[/bold green]") as status:
        status.update("[bold green]Collecting signals...[/bold green]")
        result = pipeline.run(compare=do_compare)

    render_cli(result)

    output_dir = Path(cfg.output.dir)
    report_paths = []
    for fmt in cfg.output.formats:
        if fmt == "markdown":
            path = write_markdown(result, output_dir)
            report_paths.append(("Markdown", path))
        elif fmt == "json":
            path = write_json(result, output_dir)
            report_paths.append(("JSON", path))

    if report_paths:
        console.print("\n[bold]Generated reports:[/bold]")
        for label, path in report_paths:
            console.print(f"  {label}: {path}")

    console.print("\n[bold green]Done![/bold green]")


@main.command()
@click.argument("account")
def show(account: str):
    """Show latest analysis for an ACCOUNT."""
    from collect.store import SignalStore
    store = SignalStore(Path("snapshots") / "builderdna.db")
    signals = store.get_signals_by_actor(account)

    if not signals:
        console.print(f"[yellow]No signals found for {account}[/yellow]"); return

    console.print(f"\n[bold]Signals for {account}: {len(signals)} total[/bold]")
    by_type: dict[str, int] = {}
    for s in signals:
        by_type[s.type] = by_type.get(s.type, 0) + 1
    for stype, count in sorted(by_type.items()):
        console.print(f"  {stype}: {count}")


@main.command()
def snapshots():
    """List all snapshots."""
    from collect.store import SignalStore
    from rich.table import Table
    store = SignalStore(Path("snapshots") / "builderdna.db")
    snaps = store.list_snapshots()

    if not snaps:
        console.print("[yellow]No snapshots found[/yellow]"); return

    table = Table(title="Snapshots")
    for col in ["ID", "Created", "Accounts", "Signals", "Insights", "Opportunities"]:
        table.add_column(col)
    for s in snaps:
        table.add_row(s["id"], (s.get("created_at", "") or "")[:19],
                      s.get("accounts", "-"), str(s.get("signal_count", 0)),
                      str(s.get("insight_count", 0)), str(s.get("opportunity_count", 0)))
    console.print(table)


@main.command()
@click.argument("snapshot_id_1")
@click.argument("snapshot_id_2")
def diff(snapshot_id_1: str, snapshot_id_2: str):
    """Compare two snapshots by ID."""
    from collect.store import SignalStore
    from rich.table import Table
    store = SignalStore(Path("snapshots") / "builderdna.db")
    snap1 = store.get_snapshot(snapshot_id_1)
    snap2 = store.get_snapshot(snapshot_id_2)

    if not snap1:
        console.print(f"[red]Snapshot not found: {snapshot_id_1}[/red]"); sys.exit(1)
    if not snap2:
        console.print(f"[red]Snapshot not found: {snapshot_id_2}[/red]"); sys.exit(1)

    table = Table(title=f"Diff: {snapshot_id_1} vs {snapshot_id_2}")
    table.add_column("Metric"); table.add_column(snapshot_id_1)
    table.add_column(snapshot_id_2); table.add_column("Change")
    for metric in ["signal_count", "insight_count", "opportunity_count"]:
        v1 = snap1.get(metric, 0); v2 = snap2.get(metric, 0)
        change = v2 - v1
        change_str = f"+{change}" if change > 0 else str(change)
        table.add_row(metric.replace("_", " ").title(), str(v1), str(v2), change_str)
    console.print(table)


if __name__ == "__main__":
    main()
