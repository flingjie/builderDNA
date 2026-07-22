"""collect — fetch GitHub repos and issues for a domain, output structured signals."""
import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console

from config import load_config
from collector.github.client import GitHubClient
from collector.github.repo import fetch_top_repos
from collector.github.issue import fetch_issues, DEMAND_LABELS
from collector.normalizer import normalize_all
from models.payload import SandboxResult, CollectPayload, RepoSignal, IssueSignal

console = Console()
DEMAND_SET = set(DEMAND_LABELS)


async def _run_collect(
    domain: str, window: int, output: str, config_path: str
) -> None:
    cfg = load_config(config_path)
    domain_config = cfg.domains.get(domain)
    if not domain_config:
        console.print(f"[red]Unknown domain: {domain}[/red]")
        raise typer.Exit(1)

    topics = domain_config.get("topics", [])
    client = GitHubClient(
        token=cfg.github.token,
        cache_dir=cfg.github.cache_dir,
        max_concurrent=cfg.github.max_concurrent,
        rate_limit_margin=cfg.github.rate_limit_margin,
    )

    all_repos: list[dict] = []
    all_issues: list[dict] = []
    seen_repos: set[str] = set()

    try:
        # Step 1: Topic repos
        for topic in topics:
            repos = await fetch_top_repos(client, topic)
            for r in repos:
                fn = r.get("full_name", "")
                if fn in seen_repos:
                    continue
                seen_repos.add(fn)
                all_repos.append(r)

        # Step 2: Demand issues from top repos
        top_names = [r["full_name"] for r in all_repos[:5] if r.get("full_name")]
        issue_tasks = [fetch_issues(client, name, max_issues=30) for name in top_names]
        issue_results = await asyncio.gather(*issue_tasks, return_exceptions=True)
        for issues in issue_results:
            if isinstance(issues, list):
                for iss in issues:
                    iss_labels = iss.get("labels", [])
                    if (any(lbl in DEMAND_SET for lbl in iss_labels)
                            or iss.get("reactions", 0) >= 5
                            or iss.get("comments", 0) >= 10):
                        all_issues.append(iss)

        # Step 3: Vendor + account repos
        vendor_accounts: list[tuple[str, str]] = []
        for account in cfg.accounts:
            vendor_accounts.append((account, "account"))
        for account in cfg.vendors.domestic:
            vendor_accounts.append((account, "domestic"))
        for account in cfg.vendors.overseas:
            vendor_accounts.append((account, "overseas"))

        seen_vendor: set[str] = set()
        for account, tag in vendor_accounts:
            if account in seen_vendor:
                continue
            seen_vendor.add(account)
            try:
                repos = await client.get_repos(account)
                repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
                for r in repos[:5]:
                    fn = r.get("full_name", "")
                    if fn not in seen_repos:
                        seen_repos.add(fn)
                        all_repos.append(r)
            except Exception:
                pass
    finally:
        await client.close()

    # Normalize to unified signals
    signals = normalize_all(raw_repos=all_repos, raw_issues=all_issues)

    # Build payload
    repo_signals = []
    issue_signals = []
    for s in signals:
        if s.type in ("repo_created", "star_growth"):
            repo_signals.append(RepoSignal(
                full_name=s.target_repo,
                owner=s.actor,
                stars=s.payload.get("stars", 0),
                forks=s.payload.get("forks", 0),
                contributors=s.payload.get("contributors", 0),
                velocity=s.velocity,
                topics=s.payload.get("topics", []),
                description=s.payload.get("description", ""),
                language=s.payload.get("language", ""),
                created_at=str(s.payload.get("created_at", "")),
            ))
        elif s.type == "issue_opened":
            issue_signals.append(IssueSignal(
                repo=s.target_repo,
                issue_number=s.payload.get("issue_number", 0),
                title=s.payload.get("title", ""),
                body=s.payload.get("body", ""),
                comments=s.payload.get("comments", 0),
                participants=s.payload.get("participants", 0),
                reactions=s.payload.get("reactions", 0),
                labels=s.payload.get("labels", []),
                url=s.payload.get("url", ""),
            ))

    result = SandboxResult(
        command="collect",
        domain=domain,
        payload=CollectPayload(repos=repo_signals, issues=issue_signals).model_dump(),
        stats={
            "total_signals": len(signals),
            "repos": len(repo_signals),
            "issues": len(issue_signals),
            "topics_searched": len(topics),
            "vendors_scanned": len(vendor_accounts),
        },
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    console.print(f"[green]Collected {len(repo_signals)} repos + {len(issue_signals)} issues → {output}[/green]")


def collect(
    domain: str = typer.Argument(..., help="Domain to collect signals for"),
    window: int = typer.Option(60, "--window", "-w", help="Time window in days"),
    output: str = typer.Option("output/signals.json", "--output", "-o", help="Output JSON file"),
    config: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
) -> None:
    """Collect GitHub signals for a domain."""
    asyncio.run(_run_collect(domain, window, output, config))
