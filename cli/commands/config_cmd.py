"""config — inspect and validate BuilderDNA configuration."""

from pathlib import Path

import typer

from config import load_config
import time as _time

from observability import OutputLevel, vprint, record_command


def _mask_token(token: str) -> str:
    """Mask a token, showing only the last 4 characters."""
    if not token:
        return "<empty>"
    if len(token) <= 8:
        return token[:4] + "****"
    return token[:4] + "****" + token[-4:]


def config(
    show: bool = typer.Option(False, "--show", help="Print resolved configuration"),
    config_path: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
) -> None:
    """Inspect BuilderDNA configuration."""
    t0 = _time.time()
    if not show:
        vprint("[yellow]Use --show to display resolved configuration[/yellow]",
               level=OutputLevel.NORMAL)
        record_command(
            command="config",
            domain="",
            flags={"show": False, "config_path": config_path},
            output_path="",
            user_dna_used=False,
            elapsed_seconds=round(_time.time() - t0, 2),
            status="success",
        )
        return

    cfg_path = Path(config_path)
    if not cfg_path.exists():
        vprint(f"[red]Config file not found: {config_path}[/red]", level=OutputLevel.QUIET)
        raise typer.Exit(1)

    cfg = load_config(config_path)

    vprint("", level=OutputLevel.NORMAL)
    vprint("[bold]BuilderDNA Configuration[/bold]", level=OutputLevel.NORMAL)
    vprint("─" * 50, level=OutputLevel.NORMAL)

    # GitHub
    vprint("[bold]GitHub[/bold]", level=OutputLevel.NORMAL)
    vprint(f"  Token:        {_mask_token(cfg.github.token)}", level=OutputLevel.NORMAL)
    vprint(f"  Cache Dir:    {cfg.github.cache_dir}", level=OutputLevel.NORMAL)
    vprint(f"  Max Concurrent: {cfg.github.max_concurrent}", level=OutputLevel.NORMAL)
    vprint(f"  Rate Margin:  {cfg.github.rate_limit_margin}", level=OutputLevel.NORMAL)
    vprint("", level=OutputLevel.NORMAL)

    # Embedding
    vprint("[bold]Embedding[/bold]", level=OutputLevel.NORMAL)
    vprint(f"  Model:   {cfg.embedding.model}", level=OutputLevel.NORMAL)
    vprint(f"  Base URL: {cfg.embedding.base_url}", level=OutputLevel.NORMAL)
    vprint("", level=OutputLevel.NORMAL)

    # Output
    vprint("[bold]Output[/bold]", level=OutputLevel.NORMAL)
    vprint(f"  Dir:     {cfg.output.dir}", level=OutputLevel.NORMAL)
    vprint(f"  Formats: {', '.join(cfg.output.formats)}", level=OutputLevel.NORMAL)
    vprint("", level=OutputLevel.NORMAL)

    # Accounts
    vprint("[bold]Accounts[/bold]", level=OutputLevel.NORMAL)
    vprint(f"  Accounts: {', '.join(cfg.accounts) if cfg.accounts else '(none)'}",
           level=OutputLevel.NORMAL)
    vprint("", level=OutputLevel.NORMAL)

    # Domains
    vprint("[bold]Domains[/bold]", level=OutputLevel.NORMAL)
    for domain_name, domain_cfg in cfg.domains.items():
        topics = domain_cfg.get("topics", []) if isinstance(domain_cfg, dict) else []
        vprint(f"  {domain_name}: {', '.join(topics[:5])}{'...' if len(topics) > 5 else ''}",
               level=OutputLevel.NORMAL)
    vprint("", level=OutputLevel.NORMAL)

    # Vendors
    vprint("[bold]Vendors[/bold]", level=OutputLevel.NORMAL)
    vprint(f"  Domestic: {', '.join(cfg.vendors.domestic) if cfg.vendors.domestic else '(none)'}",
           level=OutputLevel.NORMAL)
    vprint(f"  Overseas: {', '.join(cfg.vendors.overseas) if cfg.vendors.overseas else '(none)'}",
           level=OutputLevel.NORMAL)
    vprint("", level=OutputLevel.NORMAL)

    # Collect
    vprint("[bold]Collect[/bold]", level=OutputLevel.NORMAL)
    vprint(f"  Time Range: {cfg.collect.time_range_days} days", level=OutputLevel.NORMAL)
    vprint("─" * 50, level=OutputLevel.NORMAL)

    record_command(
        command="config",
        domain="",
        flags={"show": True, "config_path": config_path},
        output_path="",
        user_dna_used=False,
        elapsed_seconds=round(_time.time() - t0, 2),
        status="success",
    )
