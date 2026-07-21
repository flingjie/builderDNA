"""BuilderDNA CLI entry point."""

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from config import load_config
from collect.github.client import GitHubClient
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
@click.argument("domain")
@click.option("--window", "-w", default=60, help="Time window in days")
@click.option("--refresh/--no-refresh", default=False, help="Force refresh data")
@click.option("--web/--no-web", default=True, help="Start web server")
def radar(domain: str, window: int, refresh: bool, web: bool):
    """Run Trend Radar analysis for a DOMAIN (e.g. 'agent')."""
    from backend.dependencies import get_github_client, get_domain_config
    from backend.store.trend_store import TrendStore
    from backend.engine.radar import run_radar

    client = get_github_client()
    store = TrendStore()
    domain_config = get_domain_config(domain)
    domain_config.window_days = window

    with console.status(f"[bold green]Scanning {domain}...[/bold green]"):
        snapshot = asyncio.run(run_radar(client, domain_config, store))
        asyncio.run(client.close())

    # Terminal summary
    console.print()
    console.print(Text(f" BuilderDNA Radar · {domain_config.name} ", style="bold white on blue"))
    console.print(f" {snapshot.created_at.strftime('%Y-%m-%d')} · Last {window} Days")
    console.print("─" * 40)
    console.print()

    # Top 3 topics
    console.print("[bold]\U0001f525 Top Trends[/bold]\n")
    for i, t in enumerate(snapshot.topics[:3], 1):
        emoji = {"accelerating": "\U0001f680", "emerging": "↑", "mainstream": "→", "declining": "↓"}
        color = {"accelerating": "green", "emerging": "yellow", "mainstream": "dim", "declining": "red"}
        score_color = color.get(t.stage, "white")
        console.print(
            f" {i:>2}  {t.topic:<25} [{score_color}]{t.growth_velocity:>5.0f}[/{score_color}]  "
            f"{emoji.get(t.stage, '')} {t.stage}"
        )

    # Emerging signals
    console.print()
    console.print("[bold]\U0001f4c8 Emerging Signals[/bold]\n")
    for t in snapshot.topics:
        if t.stage in ("accelerating", "emerging"):
            console.print(f" {emoji.get(t.stage, '↑')} {t.topic:<25} +{t.evidence_count} repos")

    # GitHub stats
    console.print()
    console.print(f"[GitHub] {client.rate_limiter.usage_summary()}")

    # Web
    if web:
        console.print("\n[bold green]\U0001f4ca Starting web dashboard...[/bold green]")
        console.print("   Open http://localhost:8000\n")
        # Start FastAPI server (blocking)
        import uvicorn
        uvicorn.run("backend.main:app", host="0.0.0.0", port=8000)


@main.command()
@click.argument("accounts", nargs=-1)
@click.option("--config", "-c", default=DEFAULT_CONFIG, help="Path to config.yaml")
@click.option("--top", "-n", default=0, help="Show only top N results per group")
@click.option("--from-config", is_flag=True, help="Read groups from config.yaml follow_groups")
@click.option("--diff", is_flag=True, help="Show trend vs last snapshot")
def follow(accounts: tuple[str], config: str, top: int, from_config: bool, diff: bool):
    """Evaluate GitHub ACCOUNTS for follow-worthiness by stars and followers."""
    from follow.store import FollowStore

    cfg = load_config(Path(config))
    store = FollowStore()

    # Determine account list and grouping mode
    grouped_mode = False
    if from_config and cfg.follow_groups:
        grouped_mode = True
        groups = cfg.follow_groups
    elif from_config and cfg.follow_accounts:
        accounts = tuple(cfg.follow_accounts)
    elif not accounts:
        console.print("[red]请提供账号列表，或使用 --from-config[/red]")
        return

    gh = GitHubClient(
        token=cfg.github.token,
        cache_dir=cfg.github.cache_dir,
        max_concurrent=cfg.github.max_concurrent,
        rate_limit_margin=cfg.github.rate_limit_margin,
    )

    if grouped_mode:
        _run_grouped(gh, groups, store, top, diff)
    else:
        _run_flat(gh, accounts, top)


async def _fetch_metrics_async(gh: GitHubClient, actors: list[str]) -> list[dict]:
    """Fetch stars and followers for a list of actors concurrently.

    Uses Search API for total stars (1 call) instead of paginating all repos.
    """

    async def fetch_one(actor: str) -> dict:
        try:
            profile_task = gh.get_user(actor)
            stars_task = gh.get_total_stars(actor)

            profile, (total_stars, _repo_count) = await asyncio.gather(
                profile_task, stars_task
            )

            if profile is None:
                return {"actor": actor, "stars": 0, "followers": 0,
                        "error": f"账号 {actor} 不存在 (404)"}

            return {
                "actor": actor,
                "stars": total_stars,
                "followers": profile.get("followers", 0),
                "error": "",
            }
        except Exception as e:
            return {"actor": actor, "stars": 0, "followers": 0, "error": str(e)}

    return await asyncio.gather(*[fetch_one(a) for a in actors])


async def _run_flat_async(gh, accounts: list[str], top: int) -> None:
    """Run flat (non-grouped) evaluation (async core)."""
    from follow.scorer import score
    metrics = await _fetch_metrics_async(gh, list(accounts))
    results = score(metrics)
    if top > 0:
        results = results[:top]
    await gh.close()
    _render_follow_table(results)
    print(f"[GitHub] {gh.rate_limiter.usage_summary()}")


def _run_flat(gh, accounts: list[str], top: int) -> None:
    """Sync entry for flat evaluation."""
    asyncio.run(_run_flat_async(gh, accounts, top))


async def _run_grouped_async(gh, groups: dict[str, list[str]], store, top: int, show_diff: bool) -> None:
    """Run grouped evaluation with optional trend diff (async core)."""
    from follow.scorer import score_grouped, apply_delta

    # Collect all unique actors
    all_actors: list[str] = []
    seen: set[str] = set()
    for actors in groups.values():
        for a in actors:
            if a not in seen:
                seen.add(a)
                all_actors.append(a)

    # Fetch all metrics concurrently
    console.status("[bold green]Fetching account data...[/bold green]")
    metrics = await _fetch_metrics_async(gh, all_actors)
    metrics_map = {m["actor"]: m for m in metrics}

    # Build per-group metrics
    group_metrics: dict[str, list[dict]] = {}
    for group_name, actors in groups.items():
        group_metrics[group_name] = [metrics_map[a] for a in actors]

    # Score
    results = score_grouped(group_metrics)

    # Save snapshot
    snap_id = store.save(results)

    # Apply delta if requested
    if show_diff:
        prev = store.get_previous(snap_id)
        if prev:
            results = apply_delta(results, prev)
        else:
            console.print("[yellow]暂无历史快照，无法对比趋势[/yellow]")

    # Close client
    await gh.close()

    _render_grouped_table(results, top, show_diff, snap_id)
    print(f"[GitHub] {gh.rate_limiter.usage_summary()}")


def _run_grouped(gh, groups: dict[str, list[str]], store, top: int, show_diff: bool) -> None:
    """Sync entry for grouped evaluation."""
    asyncio.run(_run_grouped_async(gh, groups, store, top, show_diff))


def _render_grouped_table(results: list, top: int, show_diff: bool, snap_id: str) -> None:
    """Render grouped follow results."""
    console.print()
    console.print(Text("GitHub 账号关注价值评估（分组）", style="bold white on blue"))
    console.print(f"  快照: {snap_id}")
    if show_diff:
        console.print("  🔥↑ 涨幅≥10  📉↓ 跌幅≥5")
    console.print()

    for grp in results:
        accounts = grp.accounts
        if top > 0:
            accounts = accounts[:top]

        # Group header
        console.print(Text(f"▸ {grp.group_name}", style="bold cyan"))
        console.print()

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("#", justify="right")
        table.add_column("账号")
        table.add_column("Stars", justify="right")
        table.add_column("Followers", justify="right")
        table.add_column("综合分", justify="right")
        if show_diff:
            table.add_column("趋势")
        table.add_column("建议")

        for i, a in enumerate(accounts, 1):
            star_str = f"{a.total_stars:,}" if a.total_stars > 0 and not a.error else "-"
            follower_str = f"{a.followers:,}" if a.followers > 0 and not a.error else "-"
            score_color = "green" if a.composite >= 60 else "yellow" if a.composite >= 30 else "red"
            rating = a.rating
            if a.error:
                rating = f"❌ {a.error[:30]}"
            row = [
                str(i), a.actor, star_str, follower_str,
                f"[{score_color}]{a.composite:.1f}[/{score_color}]",
            ]
            if show_diff and hasattr(a, 'trend'):
                trend = a.trend
                if a.delta != 0 and trend:
                    trend_color = "green" if a.delta > 0 else "red"
                    trend_str = f"[{trend_color}]{trend} {a.delta:+.1f}[/{trend_color}]"
                else:
                    trend_str = trend or "-"
                row.append(trend_str)
            row.append(rating)
            table.add_row(*row)

        console.print(table)
        console.print()

    console.print("评分规则: Stars 30% + Followers 70%  |  组内独立归一化  |  ≥60 值得  |  30-59 观望  |  <30 暂不")


def _render_follow_table(results: list) -> None:
    """Render flat follow-worthiness results as a Rich table."""
    console.print()
    console.print(Text("GitHub 账号关注价值评估", style="bold white on blue"))
    console.print()

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("#", justify="right")
    table.add_column("账号")
    table.add_column("Stars", justify="right")
    table.add_column("Followers", justify="right")
    table.add_column("综合分", justify="right")
    table.add_column("建议")

    for i, r in enumerate(results, 1):
        star_str = f"{r.total_stars:,}" if r.total_stars > 0 and not r.error else "-"
        follower_str = f"{r.followers:,}" if r.followers > 0 and not r.error else "-"
        score_color = "green" if r.composite >= 60 else "yellow" if r.composite >= 30 else "red"
        rating = r.rating
        if r.error:
            rating = f"❌ {r.error[:30]}"
        table.add_row(
            str(i), r.actor, star_str, follower_str,
            f"[{score_color}]{r.composite:.1f}[/{score_color}]", rating,
        )

    console.print(table)
    console.print()
    console.print("评分规则: Stars 30% + Followers 70%  |  ≥60 值得  |  30-59 观望  |  <30 暂不")


if __name__ == "__main__":
    main()
