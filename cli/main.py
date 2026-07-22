"""BuilderDNA CLI entry point."""
import typer
from rich.console import Console

from cli.commands.collect import collect
from cli.commands.trend import trend
from cli.commands.pain import pain
from cli.commands.opportunity import opportunity
from cli.commands.report_cmd import report

app = typer.Typer(
    name="builderdna",
    help="BuilderDNA — Technology Intelligence Sandbox Toolkit",
)
console = Console()

app.command(name="collect")(collect)
app.command(name="trend")(trend)
app.command(name="pain")(pain)
app.command(name="opportunity")(opportunity)
app.command(name="report")(report)

if __name__ == "__main__":
    app()
