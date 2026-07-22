"""Human Control Plane: gated decision engine with builder memory."""
from enum import Enum
from control_plane.policy import compute_trigger_score
from control_plane.memory import BuilderMemory


class RunMode(Enum):
    FULL_AUTO = "full_auto"
    SUPERVISED = "supervised"
    EXPERT = "expert"


class GateDecision(Enum):
    PROCEED = "proceed"
    INTERRUPT = "interrupt"


class HumanControlPlane:
    def __init__(self, mode: RunMode = RunMode.FULL_AUTO, threshold: float = 0.5):
        self.mode = mode
        self.threshold = threshold
        self.memory = BuilderMemory()

    async def evaluate(
        self, confidence: float, impact: float, opportunity_desc: str
    ) -> GateDecision:
        if self.mode == RunMode.FULL_AUTO:
            return GateDecision.PROCEED
        if self.mode == RunMode.EXPERT:
            return GateDecision.INTERRUPT
        # SUPERVISED mode
        rules = self.memory.search(opportunity_desc, top_k=3)
        familiarity = (
            sum(r["score"] for r in rules) / max(1, len(rules)) / 10.0
        )
        familiarity = min(1.0, familiarity)
        trigger = compute_trigger_score(confidence, impact, familiarity)
        return (
            GateDecision.INTERRUPT
            if trigger > self.threshold
            else GateDecision.PROCEED
        )
