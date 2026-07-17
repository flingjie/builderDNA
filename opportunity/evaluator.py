"""Opportunity Evaluator — deterministic gap scoring. No LLM involved."""

from models.opportunity import Opportunity


def evaluate(opportunities: list[Opportunity]) -> list[Opportunity]:
    """Evaluate and rank opportunities by gap score."""
    for op in opportunities:
        op.gap_score = (
            op.demand_score / op.competition_score
            if op.competition_score > 0 else op.demand_score
        )
    opportunities.sort(key=lambda o: o.gap_score, reverse=True)
    return opportunities
