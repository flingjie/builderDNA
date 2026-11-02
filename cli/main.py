"""BuilderDNA CLI entry point."""
import typer
from rich.console import Console

from observability.output import OutputLevel, set_output_level
from cli.commands.config_cmd import config
from cli.commands.concept import concept
from cli.commands.radar import radar_app
from cli.commands.investigate import investigate


app = typer.Typer(
    name="builderdna",
    help="BuilderDNA — Technology Intelligence Sandbox Toolkit",
)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: int = typer.Option(0, "--verbose", "-v", count=True,
                                help="Increase verbosity (-v, -vv)"),
    quiet: bool = typer.Option(False, "--quiet", "-q",
                               help="Suppress all non-error output"),
) -> None:
    """Global options: --verbose / --quiet control output level."""
    if quiet:
        set_output_level(OutputLevel.QUIET)
    elif verbose >= 2:
        set_output_level(OutputLevel.DEBUG)
    elif verbose >= 1:
        set_output_level(OutputLevel.VERBOSE)
    else:
        set_output_level(OutputLevel.NORMAL)

    if ctx.invoked_subcommand is None:
        console.print("[yellow]Please specify a subcommand.[/yellow]")
        raise typer.Exit()


app.command(name="config")(config)
app.add_typer(concept, name="concept")
app.add_typer(radar_app, name="radar")
app.add_typer(investigate, name="investigate")

if __name__ == "__main__":
    app()
