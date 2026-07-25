"""Global output level control for CLI commands.

Provides OutputLevel enum and a singleton Rich Console that respects
the current output level. Commands use vprint() to output at the
appropriate level.
"""

from enum import Enum

from rich.console import Console


class OutputLevel(Enum):
    """Output verbosity levels.

    QUIET:   Only errors (red messages) — for CI/scripting.
    NORMAL:  Errors + success summaries — default interactive use.
    VERBOSE: Normal + step progress + dim diagnostic messages.
    DEBUG:   Verbose + full request/response details, stack traces.
    """
    QUIET = 0
    NORMAL = 1
    VERBOSE = 2
    DEBUG = 3


# Global output level, modifiable via --verbose/--quiet flags
_current_level: OutputLevel = OutputLevel.NORMAL

# Singleton Rich Console
_console: Console | None = None


def set_output_level(level: OutputLevel) -> None:
    """Set the global output level."""
    global _current_level
    _current_level = level


def get_output_level() -> OutputLevel:
    """Get the current global output level."""
    return _current_level


def get_console() -> Console:
    """Get (or create) the singleton Rich Console instance."""
    global _console
    if _console is None:
        _console = Console()
    return _console


def vprint(
    *args,
    level: OutputLevel = OutputLevel.NORMAL,
    **kwargs,
) -> None:
    """Print to console only if the current output level >= `level`.

    Usage:
        vprint("[green]Done in 3.2s[/green]")                      # NORMAL (default)
        vprint("[dim]Step 1/3: Fetching topics...[/dim]",           # VERBOSE
               level=OutputLevel.VERBOSE)
        vprint(f"Request: GET {url}", level=OutputLevel.DEBUG)      # DEBUG
        vprint("[red]Token invalid![/red]", level=OutputLevel.QUIET) # always

    Args:
        *args: Positional args passed to console.print().
        level: Minimum output level required to print.
        **kwargs: Keyword args passed to console.print().
    """
    if _current_level.value >= level.value:
        get_console().print(*args, **kwargs)
