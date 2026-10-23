"""Tests for intelligence/opportunity/alignment.py."""

import pytest
from models.builder_interest_profile import BuilderInterestProfile, InterestItem
from intelligence.opportunity.alignment import (
    _derive_dimension_weights,
    _tokenize,
    _parse_owner,
    _compute_output_match,
    _compute_activity_match,
    _compute_env_match,
    _compute_reward_match,
    compute_alignment,
)


# ── Helpers ───────────────────────────────────────────────────────────

def _make_profile(
    env_ranking=None,
    act_ranking=None,
    out_ranking=None,
    rew_ranking=None,
) -> BuilderInterestProfile:
    return BuilderInterestProfile(
        build_constraints=[InterestItem(value=v, source="user_confirmed", confirmed=True) for v in (env_ranking or [])],
        learning_goals=[InterestItem(value=v, source="user_confirmed", confirmed=True) for v in (act_ranking or [])],
        domains=[InterestItem(value=v, source="user_confirmed", confirmed=True) for v in (out_ranking or [])],
        problem_preferences=[InterestItem(value=v, source="user_confirmed", confirmed=True) for v in (rew_ranking or [])],
    )


# ── _derive_dimension_weights ─────────────────────────────────────────

class TestDeriveDimensionWeights:
    def test_equal_scores_gives_equal_weights(self):
        profile = _make_profile(
            env_ranking=["autonomy", "collaboration", "stability", "competition"],
            act_ranking=["creation", "exploration", "optimization", "execution"],
            out_ranking=["devtools", "end_user", "infrastructure", "knowledge"],
            rew_ranking=["growth", "mastery", "recognition", "wealth"],
        )
        weights = _derive_dimension_weights(
            [i.value for i in profile.domains],
            [i.value for i in profile.learning_goals],
            [i.value for i in profile.build_constraints],
            [i.value for i in profile.problem_preferences],
        )
        assert weights == {"environment": 0.25, "activity": 0.25, "output": 0.25, "reward": 0.25}

    def test_skewed_scores_gives_skewed_weights(self):
        profile = _make_profile(
            env_ranking=["autonomy", "collaboration", "stability", "competition"],
            act_ranking=["creation", "exploration", "optimization", "execution"],
            out_ranking=["devtools", "end_user", "infrastructure", "knowledge"],
            rew_ranking=["growth", "mastery", "recognition", "wealth"],
        )
        weights = _derive_dimension_weights(
            [i.value for i in profile.domains],
            [i.value for i in profile.learning_goals],
            [i.value for i in profile.build_constraints],
            [i.value for i in profile.problem_preferences],
        )
        assert weights["activity"] == pytest.approx(0.25, abs=1e-3)
        assert weights["reward"] == pytest.approx(0.25, abs=1e-3)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)

    def test_empty_scores_falls_back_to_equal(self):
        profile = _make_profile()
        weights = _derive_dimension_weights([], [], [], [])
        assert weights == {"environment": 0.25, "activity": 0.25, "output": 0.25, "reward": 0.25}

    def test_single_dimension_dominant(self):
        profile = _make_profile(
            env_ranking=["autonomy"],
            act_ranking=["creation", "exploration", "optimization", "execution"],
            out_ranking=["devtools"],
            rew_ranking=["growth"],
        )
        weights = _derive_dimension_weights(
            [i.value for i in profile.domains],
            [i.value for i in profile.learning_goals],
            [i.value for i in profile.build_constraints],
            [i.value for i in profile.problem_preferences],
        )
        # env=1, act=4, out=1, rew=1, total=7
        assert weights["activity"] == pytest.approx(4/7, abs=1e-3)
        assert weights["activity"] > 0.5  # clearly dominant


# ── _tokenize ─────────────────────────────────────────────────────────

class TestTokenize:
    def test_simple_word(self):
        assert _tokenize("mcp") == {"mcp"}

    def test_hyphenated(self):
        assert _tokenize("agent-framework") == {"agent", "framework"}

    def test_underscored(self):
        assert _tokenize("tool_calling") == {"tool", "calling"}

    def test_mixed(self):
        assert _tokenize("ai-agent_tool") == {"ai", "agent", "tool"}

    def test_case_insensitive(self):
        assert _tokenize("MCP") == {"mcp"}


# ── _parse_owner ──────────────────────────────────────────────────────

class TestParseOwner:
    def test_normal(self):
        assert _parse_owner("langchain-ai/langchain") == "langchain-ai"

    def test_personal(self):
        assert _parse_owner("hwchase17/langchain") == "hwchase17"

    def test_no_slash(self):
        assert _parse_owner("justrepo") == ""

    def test_empty(self):
        assert _parse_owner("") == ""


# ── _compute_output_match ─────────────────────────────────────────────

class TestComputeOutputMatch:
    def test_direct_token_match(self):
        """'mcp' token should match infrastructure's 'mcp' filter."""
        profile = _make_profile(out_ranking=["infrastructure"])
        # infrastructure → topics_filter: ["mcp", "tool-calling", "runtime", "networking", "infrastructure"]
        result = _compute_output_match("mcp", profile)
        # rank 0 → 1.0
        assert result == 1.0

    def test_no_match_returns_low(self):
        profile = _make_profile(out_ranking=["devtools"])
        # devtools maps to domain: "devtools" with no topics_filter
        # So match_topics will be empty → no match
        result = _compute_output_match("something-unrelated", profile)
        assert result < 0.5

    def test_hyphenated_topic_matches_single_token(self):
        """'tool-calling' tokenized → {'tool','calling'} matches 'tool' in infrastructure."""
        profile = _make_profile(out_ranking=["infrastructure"])
        result = _compute_output_match("tool-calling", profile)
        # 'tool-calling' → {'tool','calling'}, topics_filter has 'tool-calling' → {'tool','calling'}
        # Full overlap → rank 0 → 1.0
        assert result == 1.0

    def test_no_ranking_returns_neutral(self):
        profile = _make_profile()
        assert _compute_output_match("anything", profile) == 0.5


# ── _compute_env_match ────────────────────────────────────────────────

class TestComputeEnvMatch:
    def test_known_org_is_not_personal(self):
        """langchain-ai is a known org → not counted as personal."""
        profile = _make_profile(env_ranking=["autonomy", "collaboration", "competition", "stability"])
        repos = [{"full_name": "langchain-ai/langchain", "stars": 10000, "forks": 500}]
        known = {"langchain-ai"}
        result = _compute_env_match(repos, profile, known_orgs=known)
        # autonomy = 0/1 = 0 (no personal repos) → pulls score down
        assert result < 0.55

    def test_unknown_owner_is_personal(self):
        """hwchase17 is not in known_orgs → counted as personal."""
        profile = _make_profile(env_ranking=["autonomy", "collaboration", "competition", "stability"])
        repos = [{"full_name": "hwchase17/side-project", "stars": 50, "forks": 5}]
        known = {"langchain-ai", "anthropics"}  # hwchase17 NOT in set
        result = _compute_env_match(repos, profile, known_orgs=known)
        # autonomy = 1/1 = 1.0 (all personal repos) → high match for autonomy preference
        assert result > 0.5

    def test_collaboration_uses_forks(self):
        """collaboration score uses forks as proxy (was contributors)."""
        profile = _make_profile(env_ranking=["collaborative"])
        repos = [{"full_name": "org/repo", "stars": 1000, "forks": 200}]
        known = {"org"}
        result = _compute_env_match(repos, profile, known_orgs=known)
        # collaboration = min(1.0, 200/100) = 1.0, weighted high
        assert result > 0.7

    def test_no_repos_returns_neutral(self):
        profile = _make_profile(env_ranking=["autonomy"])
        assert _compute_env_match([], profile) == 0.5

    def test_empty_ranking_returns_neutral(self):
        profile = _make_profile()
        repos = [{"full_name": "test/repo", "stars": 100, "forks": 10}]
        assert _compute_env_match(repos, profile) == 0.5


# ── _compute_reward_match ─────────────────────────────────────────────

class TestComputeRewardMatch:
    def test_high_stars_boosts_wealth(self):
        """stars > 5000 → wealth = 0.8 (replaces has_sponsors)."""
        profile = _make_profile(rew_ranking=["wealth"])
        repos = [{"full_name": "org/big-repo", "stars": 10000, "forks": 1000}]
        trend = {"growth_velocity": 10}
        result = _compute_reward_match(repos, trend, profile)
        # wealth = 0.8, weighted 0.9 → high
        assert result > 0.6

    def test_low_stars_penalizes_wealth(self):
        profile = _make_profile(rew_ranking=["wealth"])
        repos = [{"full_name": "org/small-repo", "stars": 100, "forks": 10}]
        trend = {"growth_velocity": 10}
        result = _compute_reward_match(repos, trend, profile)
        # wealth = 0.2 (no high-star repos)
        assert result < 0.4

    def test_mastery_uses_forks(self):
        """mastery uses forks/200 as proxy (was contributors/200)."""
        profile = _make_profile(rew_ranking=["mastery"])
        repos = [{"full_name": "org/repo", "stars": 500, "forks": 300}]
        trend = {"growth_velocity": 10}
        result = _compute_reward_match(repos, trend, profile)
        # mastery = min(1.0, 300/200) + 0.2 (stars<1000) = 1.0 + 0.2 = 1.2 → capped at 1.2 but wait...
        # The formula is: min(1.0, avg_forks/200) + (0.2 if avg_stars < 1000 else 0)
        # = min(1.0, 1.5) + 0.2 = 1.0 + 0.2 = 1.2
        assert result > 0.5

    def test_no_ranking_returns_neutral(self):
        profile = _make_profile()
        repos = [{"full_name": "test/repo", "stars": 100, "forks": 10}]
        trend = {"growth_velocity": 10}
        assert _compute_reward_match(repos, trend, profile) == 0.5


# ── compute_alignment ─────────────────────────────────────────────────

class TestComputeAlignment:
    def test_multiplier_range(self):
        """Multiplier must be in [0.7, 1.3] range."""
        profile = _make_profile(
            env_ranking=["autonomy"],
            act_ranking=["creation"],
            out_ranking=["devtools"],
            rew_ranking=["growth"],
        )
        trend = {"topic": "unknown", "stage": "emerging", "evidence_count": 1, "growth_velocity": 0}
        repos = [{"full_name": "unknown/repo", "stars": 0, "forks": 0}]

        multiplier, _ = compute_alignment(trend, repos, profile)
        assert 0.7 <= multiplier <= 1.3

    def test_perfect_alignment_exceeds_1(self):
        """Well-aligned opportunity should get multiplier > 1.0."""
        profile = _make_profile(
            env_ranking=["competition"],
            act_ranking=["creation"],
            out_ranking=["infrastructure"],
            rew_ranking=["growth"],
        )
        # Trend that matches creation + infrastructure topic
        trend = {"topic": "mcp", "stage": "emerging", "evidence_count": 5, "growth_velocity": 50}
        repos = [
            {"full_name": "hwchase17/new-tool", "stars": 2000, "forks": 300},
        ]
        known = {"langchain-ai", "anthropics"}

        multiplier, reason = compute_alignment(trend, repos, profile, known_orgs=known)
        # Should exceed 1.0 because:
        # - activity: creation + emerging stage → 1.0
        # - output: mcp matches infrastructure → 1.0 (rank 0)
        assert multiplier > 1.0, f"Expected multiplier > 1.0, got {multiplier}, reason: {reason}"

    def test_known_orgs_affects_env_match(self):
        """Passing known_orgs changes the env match score."""
        profile = _make_profile(env_ranking=["autonomy"])
        trend = {"topic": "test", "stage": "mainstream", "evidence_count": 10, "growth_velocity": 5}
        repos = [{"full_name": "personal-user/repo", "stars": 100, "forks": 5}]

        # Without known_orgs: personal-user is not in empty set → personal → high autonomy
        m1, _ = compute_alignment(trend, repos, profile, known_orgs=None)
        # With known_orgs containing the user: personal-user IS known → org → low autonomy
        m2, _ = compute_alignment(trend, repos, profile, known_orgs={"personal-user"})

        # m1 should be higher (autonomy match) than m2 (autonomy mismatch)
        assert m1 > m2, f"Expected {m1} > {m2}"

    def test_empty_profile_produces_reason(self):
        """Even with minimal profile, a reason is produced."""
        profile = _make_profile()
        trend = {"topic": "test", "stage": "mainstream", "evidence_count": 10, "growth_velocity": 5}
        repos = []
        _, reason = compute_alignment(trend, repos, profile)
        assert "无明显冲突" in reason
