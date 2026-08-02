"""Pain severity — computes severity scores from issue metadata and text sentiment.
"""

import math
import re

SENTIMENT_SEEDS: dict[str, list[str]] = {
    "negative": [
        "broken", "crash", "frustrating", "cannot", "blocked",
        "fail", "error", "bug", "break", "missing",
    ],
}


def compute_sentiment_multiplier(text: str) -> float:
    """Compute a severity multiplier based on negative language density.

    Uses word-boundary matching to avoid false positives
    (e.g. 'error' matches 'error' but not 'terror').

    Returns 1.5 for high negativity (>=5 hits), 1.2 for moderate (>=2),
    and 1.0 otherwise.
    """
    text_lower = text.lower()
    negative_count = 0
    for word in SENTIMENT_SEEDS["negative"]:
        negative_count += len(re.findall(rf"\b{re.escape(word)}\b", text_lower))
    if negative_count >= 5:
        return 1.5
    if negative_count >= 2:
        return 1.2
    return 1.0


def compute_severity(comments: int, participants: int, text: str, reactions: int = 0) -> float:
    """Compute a composite pain severity score.

    Formula (additive):
        (log(c+1) + log(p+1) + log(r/2+1)) * sentiment_multiplier

    Additive so each signal channel contributes independently. An issue
    with 50 👍 but zero comments still gets a non-zero score from reactions
    alone — a clear signal of widespread but silent demand.

    Args:
        comments: Number of comments on the issue.
        participants: Estimated unique participants.
        text: Issue title + body text for sentiment analysis.
        reactions: Total reaction count (across all types).

    Returns:
        Severity score rounded to 2 decimal places. Returns 0.0 only when
        all three channels (comments, participants, reactions) are zero or negative.
    """
    if comments <= 0 and participants <= 0 and reactions <= 0:
        return 0.0

    comment_factor = math.log(max(comments, 0) + 1)
    participant_factor = math.log(max(participants, 0) + 1)
    # reactions/2 dampens so 2 reactions ≈ 1 comment equivalent
    reaction_factor = math.log(reactions / 2.0 + 1) if reactions > 0 else 0.0
    sentiment_mult = compute_sentiment_multiplier(text)

    return round((comment_factor + participant_factor + reaction_factor) * sentiment_mult, 2)
