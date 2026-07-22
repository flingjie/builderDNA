"""Critic Agent — independent skeptical LLM review of opportunities."""
from llm.prompts.opportunity import build_critic_prompt


async def review_opportunities(opportunities: list[dict], llm) -> list[dict]:
    """Run the Critic Agent over a list of opportunity dicts.

    Each opportunity is independently reviewed by the LLM using a skeptical
    VC-style prompt. On error the review is zeroed out with a placeholder
    counter-view.

    Args:
        opportunities: List of opportunity dicts with title, why_now, problem,
                       mvp, score, risk keys.
        llm: LLM client with a ``complete(prompt, response_format=dict)`` method.

    Returns:
        List of review dicts, each with keys: feasibility, market_size, timing,
        blind_spots, counter_view.
    """
    reviews: list[dict] = []
    for opp in opportunities:
        try:
            prompt = build_critic_prompt(opp)
            response = llm.complete(prompt, response_format=dict)
            reviews.append(response)
        except Exception:
            reviews.append(
                {
                    "feasibility": 0,
                    "market_size": 0,
                    "timing": 0,
                    "blind_spots": [],
                    "counter_view": "LLM error",
                }
            )
    return reviews
