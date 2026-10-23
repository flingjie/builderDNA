"""User DNA alignment engine — personalized opportunity scoring.

Computes an alignment_multiplier (0.7-1.3) from BuilderInterestProfile fields:
  - domains → output match
  - learning_goals → activity match
  - build_constraints → environment match
  - problem_preferences → reward match

The multiplier starts at 0.7 (neutral alignment, slight penalty for total
mismatch). Perfect alignment produces 1.3, a modest boost that can lift
a good opportunity above a slightly-higher-gap but misaligned one without
drowning the gap signal entirely.
"""
import math
import re

from models.builder_interest_profile import BuilderInterestProfile


# ── Mapping tables (profile fields → internal scoring dimensions) ──

_DOMAIN_TO_OUTPUT = {
    "agent": "infrastructure", "infrastructure": "infrastructure",
    "devtools": "devtools", "developer": "devtools", "tooling": "devtools",
    "consumer": "end_user", "b2c": "end_user", "end-user": "end_user",
    "knowledge": "knowledge", "education": "knowledge", "tutorial": "knowledge",
}

_GOAL_TO_ACTIVITY = {
    "build": "creation", "create": "creation", "prototype": "creation",
    "explore": "exploration", "learn": "exploration", "research": "exploration",
    "deepen": "optimization", "optimize": "optimization", "improve": "optimization",
    "ship": "execution", "launch": "execution", "productionize": "execution",
}

_CONSTRAINT_TO_ENV = {
    "solo": "autonomy", "independent": "autonomy", "autonomy": "autonomy",
    "collaborative": "collaboration", "team": "collaboration", "oss": "collaboration",
    "stable": "stability", "mature": "stability",
    "competitive": "competition", "fast-moving": "competition",
}

_PREF_TO_REWARD = {
    "growth": "growth", "learning": "growth",
    "mastery": "mastery", "depth": "mastery", "craft": "mastery",
    "recognition": "recognition", "visibility": "recognition",
    "revenue": "wealth", "commercial": "wealth", "wealth": "wealth",
}

# Output dimension → topics for matching
OUTPUT_DOMAIN_MAP: dict[str, dict] = {
    "devtools": {
        "domain": "devtools",
    },
    "infrastructure": {
        "domain": "agent",
        "topics_filter": ["mcp", "tool-calling", "runtime", "networking", "infrastructure"],
    },
    "end_user": {
        "domain": "consumer",
    },
    "knowledge": {
        "domain": None,
        "topics_append": ["tutorial", "best-practices", "documentation", "awesome-list"],
    },
}


def _scores(ranking: list[str]) -> dict[str, float]:
    """Rank-based scoring: rank 0 gets 10, decaying down the list."""
    n = len(ranking)
    return {v: max(1.0, 10.0 - (i * 9.0 / max(1, n - 1))) for i, v in enumerate(ranking)}


def _derive_dimension_weights(
    output_ranking: list[str],
    activity_ranking: list[str],
    env_ranking: list[str],
    reward_ranking: list[str],
) -> dict[str, float]:
    """Derive per-dimension weights from ranking lengths.

    Each dimension gets weight proportional to its number of items (more items = more signal).
    Falls back to equal 0.25 weights if no items.
    """
    dim_counts = {
        "environment": len(env_ranking),
        "activity": len(activity_ranking),
        "output": len(output_ranking),
        "reward": len(reward_ranking),
    }
    total = sum(dim_counts.values())
    if total <= 0:
        return {"environment": 0.25, "activity": 0.25, "output": 0.25, "reward": 0.25}
    return {k: round(v / total, 4) for k, v in dim_counts.items()}


def _tokenize(topic: str) -> set[str]:
    """Split a topic string into tokens for robust matching.

    'agent-framework' → {'agent', 'framework'}
    'tool_calling' → {'tool', 'calling'}
    'mcp' → {'mcp'}
    """
    return set(re.split(r"[-_]", topic.lower()))


def _compute_output_match(
    opportunity_topic: str,
    profile: BuilderInterestProfile,
) -> float:
    """Match output preference vs opportunity domain/topics."""
    if not profile.domains:
        return 0.5  # Neutral

    opp_tokens = _tokenize(opportunity_topic)
    output_ranking = [_DOMAIN_TO_OUTPUT.get(d.value.lower(), "devtools") for d in profile.domains]
    output_scores = _scores(output_ranking)

    for i, output_val in enumerate(output_ranking):
        mapping = OUTPUT_DOMAIN_MAP.get(output_val, {})
        match_topics = (
            mapping.get("topics", [])
            or mapping.get("topics_filter", [])
            or mapping.get("topics_append", [])
        )
        if any(bool(opp_tokens & _tokenize(t)) for t in match_topics):
            rank_score = {0: 1.0, 1: 0.7, 2: 0.4, 3: 0.2}.get(i, 0.1)
            return rank_score

    return 0.2  # No clear match


def _compute_activity_match(trend: dict, profile: BuilderInterestProfile) -> float:
    """Match activity preference vs opportunity stage and scores."""
    if not profile.learning_goals:
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

    activity_ranking = [_GOAL_TO_ACTIVITY.get(g.value.lower(), "exploration") for g in profile.learning_goals]
    scores = _scores(activity_ranking)

    total = 0.0
    total_weight = 0.0
    for i, act in enumerate(activity_ranking):
        w = scores.get(act, 5) / 10
        total += w * activity_scores.get(act, 0.3)
        total_weight += w
    return total / max(0.1, total_weight)


def _parse_owner(full_name: str) -> str:
    """Extract owner name from 'owner/repo' format."""
    return full_name.split("/")[0] if "/" in full_name else ""


def _compute_env_match(
    repos: list[dict],
    profile: BuilderInterestProfile,
    known_orgs: set[str] | None = None,
) -> float:
    """Match environment preference vs repo characteristics."""
    if not profile.build_constraints or not repos:
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
        "collaboration": min(1.0, avg_forks / 100),
        "competition": min(1.0, num_repos / 10),
    }

    env_ranking = [_CONSTRAINT_TO_ENV.get(c.value.lower(), "autonomy") for c in profile.build_constraints]
    scores = _scores(env_ranking)

    total = 0.0
    total_weight = 0.0
    for i, env in enumerate(env_ranking):
        w = scores.get(env, 5) / 10
        total += w * env_scores.get(env, 0.3)
        total_weight += w
    return total / max(0.1, total_weight)


def _compute_reward_match(repos: list[dict], trend: dict, profile: BuilderInterestProfile) -> float:
    """Match reward preference vs opportunity rewards."""
    if not profile.problem_preferences:
        return 0.5

    avg_stars = sum(r.get("stars", 0) for r in repos) / max(1, len(repos))
    avg_velocity = trend.get("growth_velocity", 0)
    avg_forks = sum(r.get("forks", 0) for r in repos) / max(1, len(repos))
    has_high_stars = any(r.get("stars", 0) > 5000 for r in repos)

    reward_scores = {
        "growth": min(1.0, avg_velocity / 100),
        "recognition": min(1.0, math.log(avg_stars + 1) / math.log(100001)),
        "wealth": 0.8 if has_high_stars else 0.2,
        "mastery": min(1.0, avg_forks / 200) + (0.2 if avg_stars < 1000 else 0),
    }

    reward_ranking = [_PREF_TO_REWARD.get(p.value.lower(), "growth") for p in profile.problem_preferences]
    scores = _scores(reward_ranking)

    total = 0.0
    total_weight = 0.0
    for i, rw in enumerate(reward_ranking):
        w = scores.get(rw, 5) / 10
        total += w * reward_scores.get(rw, 0.3)
        total_weight += w
    return total / max(0.1, total_weight)


def compute_alignment(
    trend: dict,
    repos: list[dict],
    profile: BuilderInterestProfile,
    known_orgs: set[str] | None = None,
) -> tuple[float, str]:
    """Compute alignment_multiplier and generate reason string.

    Args:
        trend: Topic trend dict with topic, stage, growth_velocity, evidence_count.
        repos: List of repo dicts (RepoSummary) with full_name, stars, forks, velocity.
        profile: BuilderInterestProfile with 6-field interest model.
        known_orgs: Set of known organization names (from config accounts + vendors).

    Returns:
        (multiplier, reason) tuple. Multiplier range is [0.7, 1.3].
    """
    # Extract rankings from profile fields
    output_ranking = [_DOMAIN_TO_OUTPUT.get(d.value.lower(), "devtools") for d in profile.domains]
    activity_ranking = [_GOAL_TO_ACTIVITY.get(g.value.lower(), "exploration") for g in profile.learning_goals]
    env_ranking = [_CONSTRAINT_TO_ENV.get(c.value.lower(), "autonomy") for c in profile.build_constraints]
    reward_ranking = [_PREF_TO_REWARD.get(p.value.lower(), "growth") for p in profile.problem_preferences]

    # Derive dimension weights from ranking lengths
    dim_weights = _derive_dimension_weights(
        output_ranking, activity_ranking, env_ranking, reward_ranking
    )

    output_match = _compute_output_match(trend.get("topic", ""), profile)
    activity_match = _compute_activity_match(trend, profile)
    env_match = _compute_env_match(repos, profile, known_orgs)
    reward_match = _compute_reward_match(repos, trend, profile)

    # 0.7 + 0.6 * weighted_avg → range [0.7, 1.3]
    weighted_avg = (
        dim_weights["output"] * output_match
        + dim_weights["activity"] * activity_match
        + dim_weights["environment"] * env_match
        + dim_weights["reward"] * reward_match
    )

    raw_multiplier = 0.7 + 0.6 * weighted_avg

    # Build alignment reason from top 2 contributing dimensions
    dims = [
        ("output", output_match, output_ranking[0] if output_ranking else ""),
        ("activity", activity_match, activity_ranking[0] if activity_ranking else ""),
        ("environment", env_match, env_ranking[0] if env_ranking else ""),
        ("reward", reward_match, reward_ranking[0] if reward_ranking else ""),
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
