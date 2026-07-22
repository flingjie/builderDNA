"""Policy: compute trigger score for human-in-the-loop gating."""


def compute_trigger_score(confidence: float, impact: float, familiarity: float) -> float:
    return round((1.0 - confidence) * impact * (1.0 - familiarity), 4)
