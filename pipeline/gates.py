"""Feedback Gate — delegates to Human Control Plane for interrupt decisions."""
import asyncio
from pipeline.state import AgentState
from control_plane.hcp import HumanControlPlane, RunMode, GateDecision


async def feedback_gate(state: AgentState) -> str:
    """Decide whether to continue to evidence node or interrupt for human review.

    Uses the HCP's Trigger Score formula:
      TriggerScore = (1 - Confidence) × Impact × (1 - Familiarity)

    Returns:
        "continue" — proceed to evidence → critic → report
        "interrupt" — pause pipeline, wait for human input
    """
    mode_str = state.get("mode", "full_auto")
    try:
        mode = RunMode(mode_str)
    except ValueError:
        mode = RunMode.FULL_AUTO

    hcp = HumanControlPlane(mode=mode)

    opportunities = state.get("opportunities", [])
    if not opportunities:
        return "continue"

    # Evaluate first opportunity as representative signal
    first_opp = opportunities[0]
    confidence = max(0.1, min(1.0, first_opp.get("score", 5) / 10.0))
    impact = min(1.0, first_opp.get("score", 5) / 7.0)

    decision = await hcp.evaluate(
        confidence=confidence,
        impact=impact,
        opportunity_desc=first_opp.get("title", ""),
    )
    return "continue" if decision == GateDecision.PROCEED else "interrupt"
