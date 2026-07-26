"""User DNA alignment engine — personalized opportunity scoring.

Computes an alignment_multiplier (0.5-1.5) from 4 value dimensions:
  - Output match: does this opportunity serve the user's preferred output type?
  - Activity match: does this stage match the user's preferred activity?
  - Environment match: do the repos match the user's preferred work environment?
  - Reward match: does the opportunity offer the user's preferred rewards?

Each dimension contributes equally. The multiplier starts at 0.5 (neutral = 1.0).
"""
import math

from models.user_dna_schema import (
    UserDNA, Values,
    OUTPUT_DOMAIN_MAP,
)


def _compute_output_match(
    opportunity_topic: str,
    values: Values,
) -> float:
    """Match output preference vs opportunity domain/topics."""
    ranking = values.output.ranking
    if not ranking:
        return 0.5  # Neutral

    for i, output_val in enumerate(ranking):
        mapping = OUTPUT_DOMAIN_MAP.get(output_val, {})
        match_topics = (
            mapping.get("topics", [])
            or mapping.get("topics_filter", [])
            or mapping.get("topics_append", [])
        )
        if any(
            t.lower() in opportunity_topic.lower()
            or opportunity_topic.lower() in t.lower()
            for t in match_topics
        ):
            rank_score = {0: 1.0, 1: 0.7, 2: 0.4, 3: 0.2}.get(i, 0.1)
            return rank_score

    return 0.2  # No clear match


def _compute_activity_match(trend: dict, values: Values) -> float:
    """Match activity preference vs opportunity stage and scores."""
    ranking = values.activity.ranking
    scores = values.activity.scores
    if not ranking:
        return 0.5

    stage = trend.get("stage", "mainstream")
    evidence_count = trend.get("evidence_count", 0)
    growth_velocity = trend.get("growth_velocity", 0)

    activity_scores = {
        "creation": 1.0 if stage in ("emerging", "accelerating") and evidence_count < 20 else 0.3,
        "exploration": 1.0 if stage in ("emerging", "accelerating") else 0.5,
        "optimization": 1.0 if stage in ("mainstream", "declining") and growth_velocity > 0 else 0.3,
        "execution": 1.0 if stage == "mainstream" and evidence_count > 30 else 0.4,
    }

    total = 0.0
    total_weight = 0.0
    for i, act in enumerate(ranking):
        w = scores.get(act, 5) / 10
        total += w * activity_scores.get(act, 0.3)
        total_weight += w
    return total / max(0.1, total_weight)


def _compute_env_match(repos: list[dict], values: Values) -> float:
    """Match environment preference vs repo characteristics."""
    ranking = values.environment.ranking
    scores = values.environment.scores
    if not ranking or not repos:
        return 0.5

    personal_count = 0
    for r in repos:
        owner_info = r.get("owner", {})
        if isinstance(owner_info, dict) and owner_info.get("type") == "User":
            personal_count += 1
        elif not isinstance(owner_info, dict):
            if r.get("stars", 0) < 1000:
                personal_count += 1
    org_count = len(repos) - personal_count
    avg_stars = sum(r.get("stars", 0) for r in repos) / max(1, len(repos))
    avg_contributors = sum(r.get("contributors", 0) for r in repos) / max(1, len(repos))
    num_repos = len(repos)

    env_scores = {
        "autonomy": personal_count / max(1, len(repos)),
        "stability": min(1.0, avg_stars / 5000) * (org_count / max(1, len(repos))),
        "collaboration": min(1.0, avg_contributors / 50),
        "competition": min(1.0, num_repos / 10),
    }

    total = 0.0
    total_weight = 0.0
    for i, env in enumerate(ranking):
        w = scores.get(env, 5) / 10
        total += w * env_scores.get(env, 0.3)
        total_weight += w
    return total / max(0.1, total_weight)


def _compute_reward_match(repos: list[dict], trend: dict, values: Values) -> float:
    """Match reward preference vs opportunity rewards."""
    ranking = values.reward.ranking
    scores = values.reward.scores
    if not ranking:
        return 0.5

    avg_stars = sum(r.get("stars", 0) for r in repos) / max(1, len(repos))
    avg_velocity = trend.get("growth_velocity", 0)
    avg_contributors = sum(r.get("contributors", 0) for r in repos) / max(1, len(repos))
    has_sponsors = any(r.get("has_sponsors", False) for r in repos)

    reward_scores = {
        "growth": min(1.0, avg_velocity / 100),
        "recognition": min(1.0, math.log(avg_stars + 1) / math.log(100001)),
        "wealth": 0.8 if has_sponsors else 0.2,
        "mastery": min(1.0, avg_contributors / 200) + (0.2 if avg_stars < 1000 else 0),
    }

    total = 0.0
    total_weight = 0.0
    for i, rw in enumerate(ranking):
        w = scores.get(rw, 5) / 10
        total += w * reward_scores.get(rw, 0.3)
        total_weight += w
    return total / max(0.1, total_weight)


def compute_alignment(
    trend: dict,
    repos: list[dict],
    user_dna: UserDNA,
) -> tuple[float, str]:
    """Compute alignment_multiplier and generate reason string."""
    values = user_dna.values

    output_match = _compute_output_match(trend.get("topic", ""), values)
    activity_match = _compute_activity_match(trend, values)
    env_match = _compute_env_match(repos, values)
    reward_match = _compute_reward_match(repos, trend, values)

    raw_multiplier = 0.5 + 0.5 * (
        0.25 * output_match
        + 0.25 * activity_match
        + 0.25 * env_match
        + 0.25 * reward_match
    )

    # Build alignment reason from top 2 contributing dimensions
    dims = [
        ("output", output_match, values.output.ranking[0] if values.output.ranking else ""),
        ("activity", activity_match, values.activity.ranking[0] if values.activity.ranking else ""),
        ("environment", env_match, values.environment.ranking[0] if values.environment.ranking else ""),
        ("reward", reward_match, values.reward.ranking[0] if values.reward.ranking else ""),
    ]
    dims.sort(key=lambda d: d[1], reverse=True)
    top_two = [d for d in dims[:2] if d[1] > 0.3]

    reason_parts = []
    dim_labels = {
        "output": lambda v: f"匹配你对**产出**的偏好（倾向 {v}）",
        "activity": lambda v: f"匹配你对**活动**的偏好（倾向 {v}）",
        "environment": lambda v: f"匹配你对**环境**的偏好（倾向 {v}）",
        "reward": lambda v: f"匹配你对**回报**的偏好（倾向 {v}）",
    }
    for dim_name, match_val, top_val in top_two:
        label_fn = dim_labels.get(dim_name, lambda v: v)
        reason_parts.append(label_fn(top_val))

    reason = "；".join(reason_parts) if reason_parts else "与你的价值观无明显冲突"
    return round(raw_multiplier, 3), reason
