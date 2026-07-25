"""BuilderDNA CLI entry point."""
import typer
from rich.console import Console

from observability.output import OutputLevel, set_output_level
from cli.commands.collect import collect
from cli.commands.trend import trend
from cli.commands.pain import pain
from cli.commands.opportunity import opportunity
from cli.commands.report_cmd import report
from cli.commands.config_cmd import config
from cli.commands.observability_cmd import observability


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


app.command(name="collect")(collect)
app.command(name="trend")(trend)
app.command(name="pain")(pain)
app.command(name="opportunity")(opportunity)
app.command(name="report")(report)
app.command(name="config")(config)
app.command(name="observability")(observability)

if __name__ == "__main__":
    app()
