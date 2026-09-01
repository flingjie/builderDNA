"""Tests for intelligence/opportunity/scoring.py."""

import math

from intelligence.opportunity.scoring import (
    compute_demand,
    compute_competition,
    compute_gap,
    compute_market_size,
    compute_confidence,
    classify_quadrant,
    recommend_action,
    match_pains_to_trend,
)


# ── compute_demand ────────────────────────────────────────────────────

class TestComputeDemand:
    def test_empty_inputs_returns_zero(self):
        assert compute_demand([], []) == 0.0

    def test_default_weights(self):
        """Default 0.4/0.4/0.2 weights."""
        trends = [{"growth_velocity": 50}]  # vel_score = min(10, 50/10) = 5
        # avg_severity = 5 → pain_score = min(10, 5*2) = 10
        # freq = 10 → freq_score = min(10, log(11)*3) ≈ min(10, 7.2) = 7.2
        pains = [{"severity": 5, "frequency": 10}]
        # demand = 5*0.4 + 10*0.4 + 7.2*0.2 = 2 + 4 + 1.44 = 7.44 → 7.4
        result = compute_demand(trends, pains)
        assert result == 7.4
        assert 0 <= result <= 10

    def test_custom_weights(self):
        trends = [{"growth_velocity": 50}]  # vel_score = 5
        pains = [{"severity": 5, "frequency": 10}]  # pain=10, freq≈7.2
        weights = {"velocity": 0.6, "severity": 0.3, "frequency": 0.1}
        # demand = 5*0.6 + 10*0.3 + 7.2*0.1 = 3 + 3 + 0.72 = 6.72 → 6.7
        result = compute_demand(trends, pains, weights=weights)
        assert result == 6.7

    def test_velocity_only_weight(self):
        trends = [{"growth_velocity": 50}]  # vel_score = 5
        pains = [{"severity": 5, "frequency": 10}]
        weights = {"velocity": 1.0, "severity": 0.0, "frequency": 0.0}
        result = compute_demand(trends, pains, weights=weights)
        assert result == 5.0

    def test_capped_at_10(self):
        """Demand should never exceed 10 regardless of inputs."""
        trends = [{"growth_velocity": 1000}]
        pains = [{"severity": 100, "frequency": 100000}]
        result = compute_demand(trends, pains)
        assert result <= 10.0

    def test_no_pain_data(self):
        """Trend-only demand — frequency and severity are 0."""
        trends = [{"growth_velocity": 30}]  # vel_score = 3
        result = compute_demand(trends, [])
        # 3*0.4 + 0*0.4 + log(1)*3*0.2 = 1.2 + 0 + 0 = 1.2
        assert result == 1.2


# ── compute_competition ───────────────────────────────────────────────

class TestComputeCompetition:
    def test_empty_trends_returns_zero(self):
        assert compute_competition([]) == 0.0

    def test_single_log_term(self):
        """No more collinear log(repos+1) term — single log(evidence+1)*2."""
        # evidence=5 → log(6)*2 ≈ 1.79*2 = 3.58 → 3.6
        trends = [{"evidence_count": 5}]
        result = compute_competition(trends)
        expected = round(min(10, math.log(6) * 2.0), 1)
        assert result == expected

    def test_no_floor(self):
        """Competition < 1.0 is allowed (no artificial floor)."""
        trends = [{"evidence_count": 0}]  # log(1)*2 = 0
        assert compute_competition(trends) == 0.0

    def test_capped_at_10(self):
        trends = [{"evidence_count": 100000}]
        result = compute_competition(trends)
        assert result <= 10.0

    def test_aggregates_across_trends(self):
        trends = [
            {"evidence_count": 3},
            {"evidence_count": 4},
        ]  # total=7 → log(8)*2 ≈ 2.08*2 = 4.16 → 4.2
        result = compute_competition(trends)
        expected = round(min(10, math.log(8) * 2.0), 1)
        assert result == expected


# ── compute_gap ───────────────────────────────────────────────────────

class TestComputeGap:
    def test_normal_case(self):
        assert compute_gap(6.0, 3.0) == 2.0

    def test_division_by_zero_protected(self):
        """max(0.1, competition) prevents division by zero."""
        assert compute_gap(3.0, 0.0) == 30.0  # 3.0 / 0.1

    def test_high_gap_low_competition(self):
        """This produces a suspiciously high gap — confidence should flag it."""
        gap = compute_gap(3.0, 0.1)
        assert gap > 10


# ── compute_market_size ───────────────────────────────────────────────

class TestComputeMarketSize:
    def test_empty_returns_zero(self):
        assert compute_market_size([]) == 0.0

    def test_no_repos(self):
        trends = [{"top_repos": []}]
        assert compute_market_size(trends) == 0.0

    def test_single_repo(self):
        trends = [{"top_repos": [{"stars": 1000}]}]
        # log(1001)*1.5 ≈ 6.91*1.5 = 10.36 → capped at 10
        result = compute_market_size(trends)
        assert 0 < result <= 10

    def test_aggregates_across_trends(self):
        trends = [
            {"top_repos": [{"stars": 100}, {"stars": 200}]},
            {"top_repos": [{"stars": 300}]},
        ]  # total = 600
        result = compute_market_size(trends)
        expected = round(min(10, math.log(601) * 1.5), 1)
        assert result == expected

    def test_small_market(self):
        trends = [{"top_repos": [{"stars": 10}]}]
        result = compute_market_size(trends)
        assert result < 5.0


# ── compute_confidence ────────────────────────────────────────────────

class TestComputeConfidence:
    def test_high_confidence(self):
        """Strong evidence → high confidence."""
        result = compute_confidence(demand=7.0, competition=5.0, total_evidence=20, total_pain_issues=50)
        assert result >= 0.9

    def test_low_competition_penalty(self):
        """comp < 1.0 → confidence penalized (uncertainty about market existence)."""
        high = compute_confidence(demand=3.0, competition=0.5, total_evidence=3, total_pain_issues=1)
        assert high < 1.0
        # comp=0.1 → max(0.3, 0.1) = 0.3 penalty on the comp axis
        very_low = compute_confidence(demand=3.0, competition=0.1, total_evidence=3, total_pain_issues=1)
        assert very_low < high

    def test_low_evidence_penalty(self):
        """< 3 evidence → confidence penalized."""
        result = compute_confidence(demand=5.0, competition=5.0, total_evidence=1, total_pain_issues=1)
        assert result < 0.8  # 0.5 + 0.17*1 = 0.67 on evidence axis

    def test_no_pain_data_penalty(self):
        with_pain = compute_confidence(demand=5.0, competition=5.0, total_evidence=10, total_pain_issues=5)
        without_pain = compute_confidence(demand=5.0, competition=5.0, total_evidence=10, total_pain_issues=0)
        assert without_pain < with_pain  # 0.85 penalty

    def test_never_below_zero(self):
        result = compute_confidence(demand=0.0, competition=0.0, total_evidence=0, total_pain_issues=0)
        assert result >= 0.0

    def test_never_above_one(self):
        result = compute_confidence(demand=10.0, competition=10.0, total_evidence=100, total_pain_issues=1000)
        assert result <= 1.0


# ── classify_quadrant ─────────────────────────────────────────────────

class TestClassifyQuadrant:
    def test_build(self):
        """High gap + big market → Build."""
        assert classify_quadrant(gap=3.0, market_size=8.0) == "Build"

    def test_niche(self):
        """High gap + small market → Niche."""
        assert classify_quadrant(gap=3.0, market_size=3.0) == "Niche"

    def test_monitor(self):
        """Low gap + big market → Monitor."""
        assert classify_quadrant(gap=1.0, market_size=8.0) == "Monitor"

    def test_avoid(self):
        """Low gap + small market → Avoid."""
        assert classify_quadrant(gap=1.0, market_size=3.0) == "Avoid"

    def test_boundaries(self):
        """Exactly at thresholds."""
        # gap=1.5 is NOT > 1.5 → low gap
        assert classify_quadrant(gap=1.5, market_size=5.0) == "Avoid"
        assert classify_quadrant(gap=1.51, market_size=5.01) == "Build"
        assert classify_quadrant(gap=1.51, market_size=5.0) == "Niche"
        assert classify_quadrant(gap=1.5, market_size=5.01) == "Monitor"

    def test_custom_thresholds(self):
        """gap=2.5 > 2.0 (high), market=3.0 NOT > 3.0 (small) → Niche."""
        assert classify_quadrant(gap=2.5, market_size=3.0, gap_threshold=2.0, market_threshold=3.0) == "Niche"
        # gap=2.5 > 2.0, market=3.1 > 3.0 → Build
        assert classify_quadrant(gap=2.5, market_size=3.1, gap_threshold=2.0, market_threshold=3.0) == "Build"


# ── recommend_action ──────────────────────────────────────────────────

class TestRecommendAction:
    def test_build_action(self):
        action = recommend_action("agent", gap=3.0, quadrant="Build", market_size=8.0, confidence=0.9)
        assert "强烈推荐" in action
        assert "agent" in action
        assert "大市场" in action

    def test_niche_action(self):
        action = recommend_action("mcp", gap=3.0, quadrant="Niche", market_size=3.0, confidence=0.8)
        assert "利基" in action
        assert "mcp" in action

    def test_monitor_action(self):
        action = recommend_action("langchain", gap=1.0, quadrant="Monitor", market_size=8.0, confidence=0.7)
        assert "密切关注" in action

    def test_avoid_action(self):
        action = recommend_action("sdk", gap=0.5, quadrant="Avoid", market_size=2.0, confidence=0.6)
        assert "暂不建议" in action

    def test_low_confidence_warning(self):
        action = recommend_action("agent", gap=3.0, quadrant="Build", market_size=8.0, confidence=0.3)
        assert "信号较弱" in action
        assert "验证需求" in action

    def test_high_confidence_no_warning(self):
        action = recommend_action("agent", gap=3.0, quadrant="Build", market_size=8.0, confidence=0.9)
        assert "信号较弱" not in action


# ── match_pains_to_trend ──────────────────────────────────────────────

class TestMatchPainsToTrend:
    def test_requires_repo_overlap(self):
        """A pain cluster attaches to a trend only when they share a repo."""
        trend = {"top_repos": [{"full_name": "org-a/agent-repo0"}]}
        pains = [
            {"affected_repos": ["org-a/agent-repo0"], "severity": 8.0},
            {"affected_repos": ["org-b/unrelated"], "severity": 9.0},
        ]
        result = match_pains_to_trend(trend, pains)
        assert len(result) == 1
        assert result[0]["severity"] == 8.0

    def test_no_fallback_when_no_overlap(self):
        """No repo overlap means no pain — demand stays trend-only, never top-N."""
        trend = {"top_repos": [{"full_name": "org-x/solo"}]}
        pains = [{"affected_repos": ["org-b/unrelated"], "severity": 9.0}]
        assert match_pains_to_trend(trend, pains) == []

    def test_empty_trend_repos_returns_empty(self):
        trend = {"top_repos": []}
        pains = [{"affected_repos": ["org-b/unrelated"], "severity": 9.0}]
        assert match_pains_to_trend(trend, pains) == []
