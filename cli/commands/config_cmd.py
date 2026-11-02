"""config — inspect and validate BuilderDNA configuration."""

from pathlib import Path

import typer

from config import load_config

from observability import OutputLevel, vprint


def config(
    show: bool = typer.Option(False, "--show", help="Print resolved configuration"),
    config_path: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
) -> None:
    """Inspect BuilderDNA configuration."""
    if not show:
        vprint("[yellow]Use --show to display resolved configuration[/yellow]",
               level=OutputLevel.NORMAL)
        return

    cfg_path = Path(config_path)
    if not cfg_path.exists():
        vprint(f"[red]Config file not found: {config_path}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    cfg = load_config(config_path)

    vprint("", level=OutputLevel.NORMAL)
    vprint("[bold]BuilderDNA Configuration[/bold]", level=OutputLevel.NORMAL)
    vprint("─" * 50, level=OutputLevel.NORMAL)

    # Output
    vprint("[bold]Output[/bold]", level=OutputLevel.NORMAL)
    vprint(f"  Dir:     {cfg.output.dir}", level=OutputLevel.NORMAL)
    vprint(f"  Formats: {', '.join(cfg.output.formats)}", level=OutputLevel.NORMAL)
    vprint("─" * 50, level=OutputLevel.NORMAL)
