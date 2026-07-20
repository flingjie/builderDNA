"""Account Follow-Worthiness Scorer.

Evaluates GitHub accounts based on total repo stars (30%) and followers (70%),
normalized within the batch or within groups. No LLM involved.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


import math


STAR_WEIGHT = 0.3
FOLLOWER_WEIGHT = 0.7

THRESHOLD_WORTHY = 60
THRESHOLD_MAYBE = 30

# Change thresholds
DELTA_HOT = 10.0     # >= 10 point increase → 🔥
DELTA_COLD = -5.0    # <= -5 point decrease → 📉


@dataclass
class AccountScore:
    """Scoring result for a single GitHub account."""

    actor: str
    total_stars: int
    followers: int
    star_score: float       # 0–100, normalized
    follower_score: float   # 0–100, normalized
    composite: float        # weighted total 0–100
    rating: str             # "✅ 值得关注" | "⚠️ 可以观望" | "❌ 暂不推荐"
    error: str = ""


@dataclass
class AccountScoreWithDelta(AccountScore):
    """AccountScore with change from previous snapshot."""

    prev_composite: float = 0.0
    delta: float = 0.0          # composite - prev_composite
    trend: str = ""             # "↑" | "↓" | "→" | "" (no previous data)


@dataclass
class GroupResult:
    """Scoring result for one group of accounts."""

    group_name: str
    accounts: list[AccountScore]  # sorted by composite desc
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def score(metrics: list[dict]) -> list[AccountScore]:
    """Score a batch of accounts by stars and followers.

    Args:
        metrics: List of {"actor": str, "stars": int, "followers": int, "error": str}.
                 error is optional; if present, the account gets zero scores.

    Returns:
        Sorted list of AccountScore, highest composite first.
    """
    if not metrics:
        return []

    stars = [m.get("stars", 0) for m in metrics]
    followers = [m.get("followers", 0) for m in metrics]

    star_scores = _normalize(stars)
    follower_scores = _normalize(followers)

    results: list[AccountScore] = []
    for i, m in enumerate(metrics):
        actor = m["actor"]
        err = m.get("error", "")
        if err:
            results.append(AccountScore(
                actor=actor, total_stars=0, followers=0,
                star_score=0, follower_score=0, composite=0,
                rating="❌ 获取失败", error=err,
            ))
            continue

        s = star_scores[i]
        f = follower_scores[i]
        composite = round(s * STAR_WEIGHT + f * FOLLOWER_WEIGHT, 1)

        if composite >= THRESHOLD_WORTHY:
            rating = "✅ 值得关注"
        elif composite >= THRESHOLD_MAYBE:
            rating = "⚠️ 可以观望"
        else:
            rating = "❌ 暂不推荐"

        results.append(AccountScore(
            actor=actor, total_stars=stars[i], followers=followers[i],
            star_score=s, follower_score=f,
            composite=composite, rating=rating,
        ))

    results.sort(key=lambda r: r.composite, reverse=True)
    return results


def _normalize(values: list[int]) -> list[float]:
    """Normalize ints to 0–100 using log1p scale for balanced distribution."""
    if not values:
        return []
    m = max(values)
    if m == 0:
        return [0.0] * len(values)
    log_max = math.log1p(m)
    return [round(math.log1p(v) / log_max * 100, 1) for v in values]


def score_grouped(groups: dict[str, list[dict]]) -> list[GroupResult]:
    """Score accounts within each group independently.

    Args:
        groups: {"Group Name": [{"actor": ..., "stars": ..., ...}, ...]}

    Returns:
        List of GroupResult, each containing sorted AccountScore list.
    """
    results: list[GroupResult] = []
    for group_name, metrics in groups.items():
        scored = score(metrics)
        results.append(GroupResult(group_name=group_name, accounts=scored))
    return results


def apply_delta(
    current: list[GroupResult], previous: dict[str, dict[str, float]]
) -> list[GroupResult]:
    """Annotate current results with deltas from a previous snapshot.

    Args:
        current: Freshly scored group results.
        previous: {group_name: {actor: composite_score}} from last snapshot.

    Returns:
        Current results with AccountScore replaced by AccountScoreWithDelta.
    """
    for grp in current:
        prev_group = previous.get(grp.group_name, {})
        new_accounts: list[AccountScoreWithDelta] = []
        for a in grp.accounts:
            prev = prev_group.get(a.actor)
            if prev is not None and prev > 0:
                delta = round(a.composite - prev, 1)
                if delta >= DELTA_HOT:
                    trend = "🔥↑"
                elif delta <= DELTA_COLD:
                    trend = "📉↓"
                elif delta > 0:
                    trend = "↑"
                elif delta < 0:
                    trend = "↓"
                else:
                    trend = "→"
            else:
                delta = 0.0
                trend = ""
            new_accounts.append(AccountScoreWithDelta(
                actor=a.actor, total_stars=a.total_stars, followers=a.followers,
                star_score=a.star_score, follower_score=a.follower_score,
                composite=a.composite, rating=a.rating, error=a.error,
                prev_composite=prev if prev else 0.0, delta=delta, trend=trend,
            ))
        grp.accounts = new_accounts

    return current
