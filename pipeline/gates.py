from pipeline.state import AgentState


def feedback_gate(state: AgentState) -> str:
    if state.get("mode") == "full_auto":
        return "continue"
    opportunities = state.get("opportunities", [])
    if not opportunities:
        return "continue"
    for opp in opportunities:
        if opp.get("score", 10) < 3:
            return "interrupt"
    return "continue"
