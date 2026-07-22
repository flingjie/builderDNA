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
    state["signals"] = []
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
      4. Sort by trend_score desc, keep top 5
    """
    import math
    from datetime import datetime, timezone
    from collector.github.repo import fetch_top_repos
    from backend.dependencies import get_github_client

    opportunities = state.get("opportunities", [])
    if not opportunities:
        return state

    client = get_github_client()
    try:
        for opp in opportunities:
            evidence = opp.get("evidence", {})
            trends = evidence.get("trends", []) if isinstance(evidence, dict) else []

            seen: set[str] = set()
            all_repos: list[dict] = []

            for trend in trends[:3]:  # max 3 trends to limit API calls
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

                    all_repos.append({
                        "full_name": full_name,
                        "stars": stars,
                        "velocity": velocity,
                        "trend_score": round(trend_score, 2),
                        "topic": trend,
                        "description": r.get("description", "") or "",
                        "url": r.get("html_url", ""),
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
