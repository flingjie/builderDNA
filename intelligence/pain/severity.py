"""Pain severity — computes severity scores from issue metadata and text sentiment.

Migrated from backend/engine/pain.py (Phase 2) with explicit
sentiment seed words for negative language detection.
"""

import math

SENTIMENT_SEEDS: dict[str, list[str]] = {
    "negative": [
        "broken", "crash", "frustrating", "cannot", "blocked",
        "fail", "error", "bug", "break", "missing",
    ],
}


def compute_sentiment_multiplier(text: str) -> float:
    """Compute a severity multiplier based on negative language density.

    Counts occurrences of negative seed words in the text.
    Returns 1.5 for high negativity (>=5 hits), 1.2 for moderate (>=2),
    and 1.0 otherwise.

    Args:
        text: Issue title + body text to analyse.

    Returns:
        Multiplier in {1.0, 1.2, 1.5}.
    """
    text_lower = text.lower()
    negative_count = sum(text_lower.count(word) for word in SENTIMENT_SEEDS["negative"])
    if negative_count >= 5:
        return 1.5
    if negative_count >= 2:
        return 1.2
    return 1.0


def compute_severity(comments: int, participants: int, text: str, reactions: int = 0) -> float:
    """Compute a composite pain severity score.

    Formula:
        log(comments + 1) * log(participants + 1) * log(reactions/2 + 1) * sentiment_multiplier

    Reactions (👍❤️🎉) indicate broader demand alignment — an issue with 50 👍
    but few comments is still a clear signal of widespread need.

    Args:
        comments: Number of comments on the issue.
        participants: Estimated unique participants.
        text: Issue title + body text for sentiment analysis.
        reactions: Total reaction count (across all types).

    Returns:
        Severity score rounded to 2 decimal places. Returns 0.0 when
        both comments and participants are zero or negative.
    """
    if comments <= 0 and participants <= 0:
        # Reactions alone can be a signal even without comments
        if reactions <= 0:
            return 0.0

    comment_factor = math.log(comments + 1)
    participant_factor = math.log(participants + 1)
    # reactions/2 dampens so 2 reactions ≈ 1 comment equivalent; floor at 1.0 when no reactions
    reaction_factor = math.log(reactions / 2.0 + 1) if reactions > 0 else 1.0
    sentiment_mult = compute_sentiment_multiplier(text)

    return round(comment_factor * participant_factor * reaction_factor * sentiment_mult, 2)
