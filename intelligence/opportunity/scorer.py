"""Multi-factor opportunity scorer. Merges evaluator + validation logic."""


def score_opportunity(
    card: dict, critic_review: dict | None = None
) -> float:
    """Compute a blended final score from the generator score and critic review.

    The generator's base score contributes 60 % and the critic's average
    of feasibility / market_size / timing contributes 40 %.

    Args:
        card: Opportunity dict with a ``score`` key (float).
        critic_review: Optional review dict with feasibility, market_size,
                       timing keys (int).

    Returns:
        Rounded float score (0-10 scale).
    """
    base = float(card.get("score", 0))
    if critic_review:
        critic_avg = (
            critic_review.get("feasibility", 0)
            + critic_review.get("market_size", 0)
            + critic_review.get("timing", 0)
        ) / 3
        return round((base * 0.6 + critic_avg * 0.4), 1)
    return round(base, 1)


def rank_opportunities(
    cards: list[dict], reviews: list[dict]
) -> list[dict]:
    """Rank a list of opportunity cards by blended final score in descending order.

    Each card gets a ``final_score`` key.  Cards are sorted in-place and
    returned.

    Args:
        cards: List of opportunity dicts.
        reviews: List of critic review dicts, parallel to ``cards``.

    Returns:
        Same list of dicts, sorted descending by ``final_score``.
    """
    for i, card in enumerate(cards):
        review = reviews[i] if i < len(reviews) else None
        card["final_score"] = score_opportunity(card, review)
    cards.sort(key=lambda c: c.get("final_score", 0), reverse=True)
    return cards
