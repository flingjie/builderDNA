"""User DNA alignment engine — personalized opportunity scoring.

Computes an alignment_multiplier (0.7-1.3) from 4 value dimensions:
  - Output match: does this opportunity serve the user's preferred output type?
  - Activity match: does this stage match the user's preferred activity?
  - Environment match: do the repos match the user's preferred work environment?
  - Reward match: does the opportunity offer the user's preferred rewards?

Dimension weights are derived from user_dna scores — users who strongly
prefer one dimension get proportionally more weight there.

The multiplier starts at 0.7 (neutral alignment, slight penalty for total
mismatch). Perfect alignment produces 1.3, a modest boost that can lift
a good opportunity above a slightly-higher-gap but misaligned one without
drowning the gap signal entirely.
"""
import math
import re

from models.user_dna_schema import (
    UserDNA, Values,
    OUTPUT_DOMAIN_MAP,
)


def _derive_dimension_weights(values: Values) -> dict[str, float]:
    """Derive per-dimension weights from user_dna value scores.

    Sums scores within each dimension, then normalizes across the 4
    dimensions so they sum to 1.0. Falls back to equal 0.25 weights
    if no scores are available.

    Example:
        env scores  {8,8,6,3} → sum=25
        activity   {9,7,7,4} → sum=27
        output     {9,7,5,4} → sum=25
        reward     {10,7,7,3} → sum=27
        total=104 → weights ≈ {env:0.24, activity:0.26, output:0.24, reward:0.26}
    """
    dim_sums = {
        "environment": sum(values.environment.scores.values()),
        "activity": sum(values.activity.scores.values()),
        "output": sum(values.output.scores.values()),
        "reward": sum(values.reward.scores.values()),
    }
    total = sum(dim_sums.values())
    if total <= 0:
        return {"environment": 0.25, "activity": 0.25, "output": 0.25, "reward": 0.25}
    return {k: round(v / total, 4) for k, v in dim_sums.items()}


def _tokenize(topic: str) -> set[str]:
    """Split a topic string into tokens for robust matching.

    'agent-framework' → {'agent', 'framework'}
    'tool_calling' → {'tool', 'calling'}
    'mcp' → {'mcp'}
    """
    return set(re.split(r"[-_]", topic.lower()))


def _compute_output_match(
    opportunity_topic: str,
    values: Values,
) -> float:
    """Match output preference vs opportunity domain/topics.

    Uses token-based matching: splits both the opportunity topic and
    the mapped topics by hyphens/underscores, then checks for any
    token overlap. This is more robust than substring matching.
    """
    ranking = values.output.ranking
    if not ranking:
        return 0.5  # Neutral

    opp_tokens = _tokenize(opportunity_topic)

    for i, output_val in enumerate(ranking):
        mapping = OUTPUT_DOMAIN_MAP.get(output_val, {})
        match_topics = (
            mapping.get("topics", [])
            or mapping.get("topics_filter", [])
            or mapping.get("topics_append", [])
        )
        # Token-based matching: any overlap between opp_tokens and match topic tokens
        if any(
            bool(opp_tokens & _tokenize(t))
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


def _parse_owner(full_name: str) -> str:
    """Extract owner name from 'owner/repo' format."""
    return full_name.split("/")[0] if "/" in full_name else ""


def _compute_env_match(
    repos: list[dict],
    values: Values,
    known_orgs: set[str] | None = None,
) -> float:
    """Match environment preference vs repo characteristics.

    Parses owner from full_name (e.g. 'langchain-ai/langchain' → 'langchain-ai').
    Checks against known_orgs (from config accounts+vendors) to distinguish
    org-owned repos from personal projects.

    Uses forks as a proxy for collaboration (since contributors is always 0
    due to GitHub Search API limitations).
    """
    ranking = values.environment.ranking
    scores = values.environment.scores
    if not ranking or not repos:
        return 0.5

    known = known_orgs or set()

    personal_count = 0
    for r in repos:
        full_name = r.get("full_name", "")
        owner = _parse_owner(full_name)
        if owner and owner not in known:
            personal_count += 1

    org_count = len(repos) - personal_count
    avg_stars = sum(r.get("stars", 0) for r in repos) / max(1, len(repos))
    avg_forks = sum(r.get("forks", 0) for r in repos) / max(1, len(repos))
    num_repos = len(repos)

    env_scores = {
        "autonomy": personal_count / max(1, len(repos)),
        "stability": min(1.0, avg_stars / 5000) * (org_count / max(1, len(repos))),
        "collaboration": min(1.0, avg_forks / 100),      # forks as proxy for collaboration
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
    """Match reward preference vs opportunity rewards.

    Uses stars (>5000) as a proxy for wealth/commercialization potential
    (replaces the non-existent has_sponsors field).

    Uses velocity as a proxy for mastery depth (replaces contributors,
    which is always 0 due to GitHub Search API limitations).
    """
    ranking = values.reward.ranking
    scores = values.reward.scores
    if not ranking:
        return 0.5

    avg_stars = sum(r.get("stars", 0) for r in repos) / max(1, len(repos))
    avg_velocity = trend.get("growth_velocity", 0)
    avg_forks = sum(r.get("forks", 0) for r in repos) / max(1, len(repos))
    # Stars > 5000 as commercialization proxy (replaces has_sponsors)
    has_high_stars = any(r.get("stars", 0) > 5000 for r in repos)

    reward_scores = {
        "growth": min(1.0, avg_velocity / 100),
        "recognition": min(1.0, math.log(avg_stars + 1) / math.log(100001)),
        "wealth": 0.8 if has_high_stars else 0.2,
        "mastery": min(1.0, avg_forks / 200) + (0.2 if avg_stars < 1000 else 0),  # forks + small-project bonus as mastery proxy
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
    known_orgs: set[str] | None = None,
) -> tuple[float, str]:
    """Compute alignment_multiplier and generate reason string.

    Args:
        trend: Topic trend dict with topic, stage, growth_velocity, evidence_count.
        repos: List of repo dicts (RepoSummary) with full_name, stars, forks, velocity.
        user_dna: User cognitive model from value-discovery skill.
        known_orgs: Set of known organization names (from config accounts + vendors).
                    Used to distinguish org-owned repos from personal projects.

    Returns:
        (multiplier, reason) tuple. Multiplier range is [0.7, 1.3]:
          - 0.7: complete mismatch across all dimensions
          - 1.0: neutral (default when no alignment data)
          - 1.3: perfect alignment, modest boost over neutral
    """
    values = user_dna.values

    # Derive dimension weights from user_dna scores (Issue #6)
    dim_weights = _derive_dimension_weights(values)

    output_match = _compute_output_match(trend.get("topic", ""), values)
    activity_match = _compute_activity_match(trend, values)
    env_match = _compute_env_match(repos, values, known_orgs)
    reward_match = _compute_reward_match(repos, trend, values)

    # Issue #1 fix: 0.7 + 0.6 * weighted_avg → range [0.7, 1.3]
    # (was: 0.5 + 0.5 * weighted_avg → [0.5, 1.0] — acted as attenuator only)
    weighted_avg = (
        dim_weights["output"] * output_match
        + dim_weights["activity"] * activity_match
        + dim_weights["environment"] * env_match
        + dim_weights["reward"] * reward_match
    )

    raw_multiplier = 0.7 + 0.6 * weighted_avg

    # Build alignment reason from top 2 contributing dimensions
    dims = [
        ("output", output_match, values.output.ranking[0] if values.output.ranking else ""),
        ("activity", activity_match, values.activity.ranking[0] if values.activity.ranking else ""),
        ("environment", env_match, values.environment.ranking[0] if values.environment.ranking else ""),
        ("reward", reward_match, values.reward.ranking[0] if values.reward.ranking else ""),
    ]
    dims.sort(key=lambda d: d[1], reverse=True)
    top_two = [d for d in dims[:2] if d[1] > 0.3 and d[2]]

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
