"""Opportunity Generator — re-exports from backend opportunity engine."""
from backend.engine.opportunity import (
    format_pains_for_llm,
    format_trends_for_llm,
    generate_opportunities,
    run_opportunity_engine,
)

__all__ = [
    "format_trends_for_llm",
    "format_pains_for_llm",
    "generate_opportunities",
    "run_opportunity_engine",
]
