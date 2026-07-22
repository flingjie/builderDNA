"""Redirect: use intelligence/opportunity/ instead."""
from intelligence.opportunity.generator import (  # noqa
    format_trends_for_llm,
    format_pains_for_llm,
    generate_opportunities,
    run_opportunity_engine,
)
from intelligence.opportunity.critic import review_opportunities  # noqa
from intelligence.opportunity.scorer import score_opportunity, rank_opportunities  # noqa
