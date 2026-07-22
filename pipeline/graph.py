"""LangGraph DAG pipeline for BuilderDNA 2.0."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from pipeline.state import AgentState
from pipeline.gates import feedback_gate


def build_pipeline(mode: str = "full_auto"):
    workflow = StateGraph(AgentState)
    workflow.add_node("collect", _collect_signals)
    workflow.add_node("trend", _detect_trends)
    workflow.add_node("pain", _mine_pain)
    workflow.add_node("opportunity", _generate_opportunities)
    workflow.add_node("evidence", _enrich_evidence)
    workflow.add_node("critic", _review_opportunities)
    workflow.add_node("report", _generate_report)

    workflow.set_entry_point("collect")
    workflow.add_edge("collect", "trend")
    workflow.add_edge("trend", "pain")
    workflow.add_edge("pain", "opportunity")
    workflow.add_conditional_edges(
        "opportunity", feedback_gate,
        {"continue": "evidence", "interrupt": END},
    )
    workflow.add_edge("evidence", "critic")
    workflow.add_edge("critic", "report")
    workflow.add_edge("report", END)

    interrupt_before = ["opportunity"] if mode != "full_auto" else []
    return workflow.compile(checkpointer=MemorySaver(), interrupt_before=interrupt_before)


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

async def _collect_signals(state: AgentState) -> AgentState:
    """Collect signals from GitHub: demand issues first, then repos.

    Order matters for API quota: issues (fewer calls) → topic repos →
    vendor repos (bulk, REST API).

    Deduplicates repos by full_name across all sources.
    Vendor repos are capped at top 5 per account (by stars).
    """
    import asyncio
    from collector.github.repo import fetch_top_repos
    from collector.github.issue import fetch_issues, DEMAND_LABELS
    from collector.normalizer import normalize_all
    from backend.dependencies import get_github_client, get_domain_config, get_config

    # Demand labels for client-side filtering (more reliable than Search API)
    DEMAND_SET = set(DEMAND_LABELS)

    config = get_config()
    domain_config = get_domain_config(state["domain"])
    client = get_github_client()

    seen_repos: set[str] = set()
    all_repos: list[dict] = []
    all_issues: list[dict] = []

    try:
        # ── Step 1: Topic repos (needed to know WHICH repos to pull issues from) ──
        for topic in domain_config.topics:
            repos = await fetch_top_repos(client, topic)
            for r in repos:
                fn = r.get("full_name", "")
                if fn in seen_repos:
                    continue
                seen_repos.add(fn)
                all_repos.append(r)

        # ── Step 2: Demand issues from top repos ──
        # Use REST API fetch_issues (NOT search — Search API label index unreliable)
        # then filter client-side by demand labels
        top_names = [r["full_name"] for r in all_repos[:5] if r.get("full_name")]
        issue_tasks = [fetch_issues(client, name, max_issues=30) for name in top_names]
        issue_results = await asyncio.gather(*issue_tasks, return_exceptions=True)
        for issues in issue_results:
            if isinstance(issues, list):
                for iss in issues:
                    iss_labels = iss.get("labels", [])
                    # Keep issues that match demand labels, OR have high engagement
                    if (any(lbl in DEMAND_SET for lbl in iss_labels)
                            or iss.get("reactions", 0) >= 5
                            or iss.get("comments", 0) >= 10):
                        all_issues.append(iss)

        all_signals = normalize_all(raw_repos=all_repos, raw_issues=all_issues)

        # ── Step 3: Vendor + follow_group account repos ──
        vendor_accounts: list[tuple[str, str]] = []
        for account in config.vendors.domestic:
            vendor_accounts.append((account, "🇨🇳"))
        for account in config.vendors.overseas:
            vendor_accounts.append((account, "🌍"))
        for group_name, accounts in config.follow_groups.items():
            for account in accounts:
                vendor_accounts.append((account, group_name))

        seen_vendor: set[str] = set()

        async def _collect_vendor(account: str, tag: str):
            if account in seen_vendor:
                return []
            seen_vendor.add(account)
            try:
                repos = await client.get_repos(account)
                # Cap: top 5 by stars, only new repos
                repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
                new = []
                for r in repos[:5]:
                    fn = r.get("full_name", "")
                    if fn not in seen_repos:
                        seen_repos.add(fn)
                        new.append(r)
                return normalize_all(raw_repos=new)
            except Exception:
                return []

        vendor_tasks = [_collect_vendor(a, t) for a, t in vendor_accounts
                        if a not in seen_vendor]
        vendor_results = await asyncio.gather(*vendor_tasks, return_exceptions=True)
        for result in vendor_results:
            if isinstance(result, list):
                all_signals.extend(result)
    finally:
        await client.close()

    state["signals"] = all_signals
    return state


async def _detect_trends(state: AgentState) -> AgentState:
    state["topic_trends"] = []
    return state


async def _mine_pain(state: AgentState) -> AgentState:
    state["pain_clusters"] = []
    return state


async def _generate_opportunities(state: AgentState) -> AgentState:
    state["opportunities"] = []
    return state


async def _enrich_evidence(state: AgentState) -> AgentState:
    """Enrich each opportunity card with related fast-growing repos.

    For each opportunity's evidence.trends tags:
      1. Fetch top repos per trend from GitHub Search API
      2. Deduplicate by full_name
      3. Compute velocity (stars / days_since_creation)
      4. Tag repos from known vendors (🇨🇳/🌍)
      5. Sort by trend_score desc, keep top 5
    """
    import math
    from datetime import datetime, timezone
    from collector.github.repo import fetch_top_repos
    from backend.dependencies import get_github_client, get_config

    opportunities = state.get("opportunities", [])
    if not opportunities:
        return state

    # Build vendor lookup: account → (display_tag, group)
    config = get_config()
    vendor_map: dict[str, str] = {}
    for account in config.vendors.domestic:
        vendor_map[account] = "🇨🇳"
    for account in config.vendors.overseas:
        vendor_map[account] = "🌍"

    for group_name, accounts in config.follow_groups.items():
        for account in accounts:
            if account not in vendor_map:
                vendor_map[account] = group_name

    client = get_github_client()
    try:
        for opp in opportunities:
            evidence = opp.get("evidence", {})
            trends = evidence.get("trends", []) if isinstance(evidence, dict) else []

            seen: set[str] = set()
            all_repos: list[dict] = []

            for trend in trends[:3]:
                repos = await fetch_top_repos(client, trend, max_results=5)
                for r in repos:
                    full_name = r.get("full_name", "")
                    if full_name in seen:
                        continue
                    seen.add(full_name)

                    stars = r.get("stargazers_count", 0)
                    created_at = r.get("created_at", "")
                    days = 365
                    if created_at:
                        try:
                            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            days = max(1, (datetime.now(timezone.utc) - dt).days)
                        except (ValueError, TypeError):
                            pass

                    velocity = round(stars / days, 2)
                    trend_score = velocity * math.log10(r.get("forks_count", 0) + 1)

                    # Tag vendor affiliation from repo owner
                    owner = r.get("owner", {})
                    owner_login = owner.get("login", "") if isinstance(owner, dict) else ""
                    vendor_tag = vendor_map.get(owner_login)
                    # Also check if owner is part of a known org (orgs own repos)
                    if not vendor_tag and "/" in full_name:
                        org_name = full_name.split("/")[0]
                        vendor_tag = vendor_map.get(org_name)

                    all_repos.append({
                        "full_name": full_name,
                        "stars": stars,
                        "velocity": velocity,
                        "trend_score": round(trend_score, 2),
                        "topic": trend,
                        "description": r.get("description", "") or "",
                        "url": r.get("html_url", ""),
                        "vendor_tag": vendor_tag,       # 🇨🇳 / 🌍 / group_name / null
                    })

            all_repos.sort(key=lambda r: r["trend_score"], reverse=True)
            opp["related_repos"] = all_repos[:5]
    finally:
        await client.close()

    return state


async def _review_opportunities(state: AgentState) -> AgentState:
    state["critic_reviews"] = []
    return state


def _generate_report(state: AgentState) -> AgentState:
    state["report_path"] = ""
    return state
