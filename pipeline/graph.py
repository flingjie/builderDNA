"""LangGraph DAG pipeline for auto-discovery and demand validation."""
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
    workflow.add_node("critic", _review_opportunities)
    workflow.add_node("report", _generate_report)

    workflow.set_entry_point("collect")
    workflow.add_edge("collect", "trend")
    workflow.add_edge("trend", "pain")
    workflow.add_edge("pain", "opportunity")
    workflow.add_conditional_edges(
        "opportunity", feedback_gate,
        {"continue": "critic", "interrupt": END},
    )
    workflow.add_edge("critic", "report")
    workflow.add_edge("report", END)

    interrupt_before = ["opportunity"] if mode != "full_auto" else []
    return workflow.compile(checkpointer=MemorySaver(), interrupt_before=interrupt_before)


# ---------------------------------------------------------------------------
# Placeholder node implementations (real logic delegated to intelligence/)
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


async def _review_opportunities(state: AgentState) -> AgentState:
    state["critic_reviews"] = []
    return state


def _generate_report(state: AgentState) -> AgentState:
    state["report_path"] = ""
    return state
