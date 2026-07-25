"""collect — fetch GitHub repos and issues for a domain, output structured signals.

Supports User DNA personalization: reads state/user_dna.json and applies
4 mapping rules to customize domain, topics, window, and repo sorting.
"""
import asyncio
import json
import math
from pathlib import Path

import typer

from config import load_config
from collector.github.client import GitHubClient
from collector.github.repo import fetch_top_repos
from collector.github.issue import fetch_issues, DEMAND_LABELS
from collector.normalizer import normalize_all
from models.payload import SandboxResult, CollectPayload, RepoSignal, IssueSignal
from observability import RunTelemetry, OutputLevel, vprint, record_command, record_output_retention
from state.user_dna_schema import (
    load_user_dna, UserDNA,
    OUTPUT_DOMAIN_MAP, ACTIVITY_CONFIG,
    REWARD_WEIGHTS, ENVIRONMENT_SOURCE_MIX,
)

DEMAND_SET = set(DEMAND_LABELS)


def _apply_user_dna_rules(
    domain: str,
    cfg: dict,
    user_dna: UserDNA,
) -> tuple[str, list[str], int, dict, dict]:
    """Apply 4 mapping rules from User DNA to collect parameters.

    Returns: (domain, topics, window_days, repo_sort_weights, source_mix)

    Rules are applied in priority order:
      1. output → domain + topics
      2. activity → window + filter thresholds
      3. reward → repo sort weights
      4. environment → data source mix
    """
    output_ranking = user_dna.values.output.ranking
    activity_ranking = user_dna.values.activity.ranking
    reward_ranking = user_dna.values.reward.ranking
    env_ranking = user_dna.values.environment.ranking

    # ── Rule 1: output → domain + topics ──
    final_domain = domain
    final_topics: list[str] = []
    domain_config = cfg.get("domains", {}).get(domain, {})

    if output_ranking:
        top_output = output_ranking[0]
        mapping = OUTPUT_DOMAIN_MAP.get(top_output, {})
        new_domain = mapping.get("domain")

        if new_domain and new_domain != domain and new_domain in cfg.get("domains", {}):
            final_domain = new_domain
            final_topics = cfg["domains"][final_domain].get("topics", [])
        elif "topics_filter" in mapping:
            # Filter current domain topics
            all_topics = domain_config.get("topics", [])
            final_topics = [t for t in all_topics if any(
                kw in t.lower() for kw in mapping["topics_filter"]
            )] or all_topics
        elif "topics_append" in mapping:
            final_topics = list(domain_config.get("topics", [])) + mapping["topics_append"]

    if not final_topics:
        final_topics = domain_config.get("topics", [])

    # ── Rule 2: activity → window + filter thresholds ──
    window_days = 365
    repo_filter = {"min_stars": 0, "boost": "velocity"}

    if activity_ranking:
        top_activity = activity_ranking[0]
        act_cfg = ACTIVITY_CONFIG.get(top_activity, ACTIVITY_CONFIG["exploration"])
        window_days = act_cfg["window"]
        repo_filter = {"min_stars": act_cfg["min_stars"], "boost": act_cfg["boost"]}

    # ── Rule 3: reward → repo sort weights ──
    repo_sort_weights = REWARD_WEIGHTS.get("growth", REWARD_WEIGHTS["growth"])
    if reward_ranking:
        # Blend top 2: ranking[0] gets 0.5, ranking[1] gets 0.3, rest gets 0.2 distributed
        primary = REWARD_WEIGHTS.get(reward_ranking[0], REWARD_WEIGHTS["growth"])
        if len(reward_ranking) > 1:
            secondary = REWARD_WEIGHTS.get(reward_ranking[1], REWARD_WEIGHTS["growth"])
            repo_sort_weights = {
                k: primary.get(k, 0) * 0.6 + secondary.get(k, 0) * 0.3
                for k in primary
            }
        else:
            repo_sort_weights = dict(primary)

    # ── Rule 4: environment → data source mix ──
    source_mix = ENVIRONMENT_SOURCE_MIX.get("autonomy", ENVIRONMENT_SOURCE_MIX["autonomy"])
    if env_ranking:
        source_mix = ENVIRONMENT_SOURCE_MIX.get(
            env_ranking[0], ENVIRONMENT_SOURCE_MIX["autonomy"]
        )

    return final_domain, final_topics, window_days, repo_sort_weights, source_mix


def _score_repo(repo: dict, weights: dict) -> float:
    """Score a repo by reward weights for personalized sorting."""
    max_stars = 100000
    max_forks = 50000
    max_contribs = 5000

    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)
    velocity = repo.get("velocity", 0) or 0
    # open_issues as rough proxy for contributor activity
    open_issues = repo.get("open_issues_count", 0)

    stars_log = math.log(stars + 1) / math.log(max_stars + 1)
    forks_log = math.log(forks + 1) / math.log(max_forks + 1)
    velocity_norm = min(1.0, velocity / 100)
    contribs_norm = min(1.0, open_issues / max_contribs)
    commercial = 1.0 if repo.get("has_sponsors") or repo.get("topics") and "enterprise" in repo.get("topics", []) else 0.3

    score = (
        weights.get("velocity", 0.2) * velocity_norm
        + weights.get("stars_log", 0.2) * stars_log
        + weights.get("commercial", 0.2) * commercial
        + weights.get("contributors", 0.2) * contribs_norm
    ) * 10
    return score


async def _run_collect(
    domain: str, output: str, config_path: str,
    user_dna_path: str = "state/user_dna.json",
    window_days: int | None = None,
    no_cache: bool = False,
    clear_cache: bool = False,
) -> None:
    cfg = load_config(config_path)
    tel = RunTelemetry()

    # Clear cache if requested
    if clear_cache:
        from collector.github.cache import CacheStore
        store = CacheStore(cfg.github.cache_dir)
        count = store.clear()
        vprint(f"[dim]Cleared {count} cache entries[/dim]", level=OutputLevel.NORMAL)

    # Load User DNA and apply mapping rules
    user_dna = load_user_dna(user_dna_path)
    if user_dna:
        final_domain, topics, w_days, sort_weights, source_mix = _apply_user_dna_rules(
            domain, cfg, user_dna
        )
        vprint(f"[dim]User DNA loaded → domain={final_domain}, window={w_days}d, "
               f"topics={topics[:3]}...[/dim]", level=OutputLevel.VERBOSE)
    else:
        domain_config = cfg.domains.get(domain)
        if not domain_config:
            vprint(f"[red]Unknown domain: {domain}[/red]", level=OutputLevel.QUIET)
            raise typer.Exit(1)
        final_domain = domain
        topics = domain_config.get("topics", [])
        w_days = window_days or 365
        sort_weights = REWARD_WEIGHTS["growth"]
        source_mix = ENVIRONMENT_SOURCE_MIX["autonomy"]

    client = GitHubClient(
        token=cfg.github.token,
        cache_dir=cfg.github.cache_dir,
        max_concurrent=cfg.github.max_concurrent,
        rate_limit_margin=cfg.github.rate_limit_margin,
        telemetry=tel,
        disable_cache=no_cache,
    )

    all_repos: list[dict] = []
    all_issues: list[dict] = []
    seen_repos: set[str] = set()
    topics_with_results: int = 0

    try:
        # Step 1: Topic repos
        vprint(f"[dim]⏳ Step 1/3: Searching {len(topics)} topics for repos...[/dim]",
               level=OutputLevel.VERBOSE)
        topics_with_results = 0
        for topic in topics:
            repos = await fetch_top_repos(client, topic)
            if repos:
                topics_with_results += 1
            vprint(f"[dim]  ✓ {topic}: {len(repos)} repos[/dim]", level=OutputLevel.VERBOSE)
            for r in repos:
                fn = r.get("full_name", "")
                if fn in seen_repos:
                    continue
                seen_repos.add(fn)
                all_repos.append(r)

        # Step 2: Demand issues from top repos (sorted by personalized weights)
        scored = [(r, _score_repo(r, sort_weights)) for r in all_repos]
        scored.sort(key=lambda x: x[1], reverse=True)
        sorted_repos = [r for r, _ in scored]

        top_names = [r.get("full_name", "") for r in sorted_repos[:5] if r.get("full_name")]
        vprint(f"[dim]⏳ Step 2/3: Fetching issues from {len(top_names)} repos...[/dim]",
               level=OutputLevel.VERBOSE)
        issue_tasks = [fetch_issues(client, name, max_issues=30) for name in top_names]
        issue_results = await asyncio.gather(*issue_tasks, return_exceptions=True)
        for name, issues in zip(top_names, issue_results):
            if isinstance(issues, list):
                demand_issues = [iss for iss in issues if (
                    any(lbl in DEMAND_SET for lbl in iss.get("labels", []))
                    or iss.get("reactions", 0) >= 5
                    or iss.get("comments", 0) >= 10
                )]
                vprint(f"[dim]  ✓ {name}: {len(demand_issues)} demand issues[/dim]",
                       level=OutputLevel.VERBOSE)
                all_issues.extend(demand_issues)
            elif isinstance(issues, Exception):
                tel.add_error(f"fetch_issues({name})", str(issues))

        # Step 3: Vendor + account repos (weighted by environment source_mix)
        vendor_accounts: list[tuple[str, str]] = []
        for account in cfg.accounts:
            vendor_accounts.append((account, "account"))
        for account in cfg.vendors.domestic:
            vendor_accounts.append((account, "domestic"))
        for account in cfg.vendors.overseas:
            vendor_accounts.append((account, "overseas"))

        vprint(f"[dim]⏳ Step 3/3: Scanning {len(vendor_accounts)} vendor/account repos...[/dim]",
               level=OutputLevel.VERBOSE)
        seen_vendor: set[str] = set()
        for account, source_type in vendor_accounts:
            if account in seen_vendor:
                continue
            seen_vendor.add(account)
            try:
                repos = await client.get_repos(account)
                repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
                # Environment mix: adjust repo limit by source type weight
                limit = 5
                if source_type == "account":
                    limit = max(1, int(5 * source_mix.get("accounts", 0.3)))
                elif source_type in ("domestic", "overseas"):
                    limit = max(1, int(5 * source_mix.get("vendors", 0.3)))
                for r in repos[:limit]:
                    fn = r.get("full_name", "")
                    if fn not in seen_repos:
                        seen_repos.add(fn)
                        all_repos.append(r)
            except Exception as e:
                tel.add_error(f"get_repos({account})", str(e))
                vprint(f"[yellow]Warning: failed to fetch repos for {account}: {e}[/yellow]",
                       level=OutputLevel.NORMAL)
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
                full_name=s.target_repo or "",
                owner=s.actor or "",
                stars=s.payload.get("stars", 0),
                forks=s.payload.get("forks", 0),
                contributors=s.payload.get("contributors", 0),
                velocity=s.velocity,
                topics=s.payload.get("topics") or [],
                description=s.payload.get("description") or "",
                language=s.payload.get("language") or "",
                created_at=str(s.payload.get("created_at", "")),
            ))
        elif s.type == "issue_opened":
            issue_signals.append(IssueSignal(
                repo=s.target_repo or "",
                issue_number=s.payload.get("issue_number", 0),
                title=s.payload.get("title") or "",
                body=s.payload.get("body") or "",
                comments=s.payload.get("comments", 0),
                participants=s.payload.get("participants", 0),
                reactions=s.payload.get("reactions", 0),
                labels=s.payload.get("labels") or [],
                url=s.payload.get("url") or "",
            ))

    # Serialize normalized signals for downstream consumption
    signal_dicts = [s.model_dump() for s in signals]

    # Build stats with telemetry
    cmd_stats = {
        "total_signals": len(signals),
        "repos": len(repo_signals),
        "issues": len(issue_signals),
        "topics_searched": len(topics),
        "topics_with_results": topics_with_results,
        "vendors_scanned": len(vendor_accounts),
        "personalized": user_dna is not None,
    }

    result = SandboxResult(
        command="collect",
        domain=final_domain,
        payload=CollectPayload(
            repos=repo_signals,
            issues=issue_signals,
            signals=signal_dicts,
        ).model_dump(),
        stats={**cmd_stats, **tel.to_stats()},
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))

    # End-of-run summary
    cache_info = ""
    if tel.cache_total > 0:
        cache_info = f", cache: {tel.cache_hits} hits/{tel.cache_misses} misses ({int(tel.cache_hit_rate * 100)}% hit)"
    rate_info = ""
    if client.rate_limiter._total_calls > 0:
        rate_info = f", API: {client.rate_limiter._total_calls} calls"
        if client.rate_limiter._waited_calls > 0:
            rate_info += f" (waited {client.rate_limiter._waited_calls}x)"
    error_info = ""
    if tel.errors:
        error_info = f", {len(tel.errors)} errors"
    if tel.retry_exhausted:
        error_info += f", {len(tel.retry_exhausted)} retry exhaustions"

    vprint(f"[green]Collected {len(repo_signals)} repos + {len(issue_signals)} issues → {output}[/green]",
           level=OutputLevel.NORMAL)
    vprint(f"[dim]Done in {tel.elapsed_seconds}s{cache_info}{rate_info}{error_info}[/dim]",
           level=OutputLevel.NORMAL)
    if tel.has_issues():
        for err in tel.errors:
            vprint(f"[yellow]  ⚠ {err['url']}: {err['reason']}[/yellow]", level=OutputLevel.NORMAL)
        for retry in tel.retry_exhausted:
            vprint(f"[yellow]  ⚠ Retry exhausted: {retry['url']} ({retry['reason']}, {retry['attempts']} attempts)[/yellow]",
                   level=OutputLevel.NORMAL)

    # Behavior tracking
    record_command(
        command="collect",
        domain=final_domain,
        flags={"window": w_days, "no_cache": no_cache, "clear_cache": clear_cache,
               "user_dna": user_dna is not None},
        output_path=output,
        user_dna_used=user_dna is not None,
        elapsed_seconds=tel.elapsed_seconds,
        status="success",
    )
    record_output_retention(output)


def collect(
    domain: str = typer.Argument(..., help="Domain to collect signals for"),
    output: str = typer.Option("output/signals.json", "--output", "-o", help="Output JSON file"),
    config: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
    user_dna: str = typer.Option("state/user_dna.json", "--user-dna", help="User DNA file for personalization"),
    window: int = typer.Option(None, "--window", "-w", help="Analysis window in days (overrides DNA)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Disable HTTP cache (all requests go to API)"),
    clear_cache: bool = typer.Option(False, "--clear-cache", help="Clear cache before collecting"),
) -> None:
    """Collect GitHub signals for a domain (optionally personalized via User DNA)."""
    asyncio.run(_run_collect(domain, output, config, user_dna, window, no_cache, clear_cache))
