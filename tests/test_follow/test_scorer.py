"""Tests for follow-worthiness scorer."""

from follow.scorer import score, score_grouped, apply_delta, _normalize, AccountScoreWithDelta, GroupResult


class TestNormalize:
    def test_equal_values(self):
        assert _normalize([10, 10, 10]) == [100.0, 100.0, 100.0]

    def test_log_scale_compresses_extremes(self):
        # 1000x difference in linear, but compressed under log
        result = _normalize([1, 1000])
        assert result[1] == 100.0
        # log1p(1) ≈ 0.69, log1p(1000) ≈ 6.91 → ~10%, not 0.1%
        assert 5 < result[0] < 20

    def test_zero_values(self):
        assert _normalize([0, 0]) == [0.0, 0.0]

    def test_empty(self):
        assert _normalize([]) == []


class TestScore:
    def test_scores_and_ranks(self):
        metrics = [
            {"actor": "alice", "stars": 100, "followers": 1000},
            {"actor": "bob", "stars": 10, "followers": 10},
            {"actor": "carol", "stars": 1, "followers": 1},
        ]
        results = score(metrics)
        assert len(results) == 3
        # alice should rank first
        assert results[0].actor == "alice"
        assert results[0].composite > results[1].composite > results[2].composite

    def test_error_account_gets_zero(self):
        metrics = [
            {"actor": "ok", "stars": 100, "followers": 100},
            {"actor": "bad", "stars": 0, "followers": 0, "error": "timeout"},
        ]
        results = score(metrics)
        bad = [r for r in results if r.actor == "bad"][0]
        assert bad.composite == 0.0
        assert bad.rating == "❌ 获取失败"

    def test_empty_input(self):
        assert score([]) == []

    def test_single_account_gets_100(self):
        results = score([{"actor": "solo", "stars": 42, "followers": 7}])
        assert results[0].composite == 100.0
        assert results[0].star_score == 100.0
        assert results[0].follower_score == 100.0

    def test_weight_split(self):
        metrics = [
            {"actor": "star_heavy", "stars": 10000, "followers": 1},
            {"actor": "follower_heavy", "stars": 1, "followers": 10000},
        ]
        results = score(metrics)
        assert results[0].actor == "follower_heavy"


class TestScoreGrouped:
    def test_groups_scored_independently(self):
        """Each group normalizes independently — mega-account in one group
        doesn't compress scores in another."""
        groups = {
            "Big": [
                {"actor": "giant", "stars": 100000, "followers": 100000},
                {"actor": "small", "stars": 10, "followers": 10},
            ],
            "Small": [
                {"actor": "tiny1", "stars": 10, "followers": 10},
                {"actor": "tiny2", "stars": 5, "followers": 5},
            ],
        }
        results = score_grouped(groups)
        assert len(results) == 2

        # In "Big" group: small should still have a clear score (not crushed to near-zero)
        big = next(g for g in results if g.group_name == "Big")
        small_score = next(a for a in big.accounts if a.actor == "small")
        # Log-normalized: log1p(10)/log1p(100000) ≈ 2.40/11.51 ≈ 0.208 → ~20.8
        assert 15 < small_score.composite < 50

        # In "Small" group: both get independent normalization
        small_grp = next(g for g in results if g.group_name == "Small")
        tiny1 = next(a for a in small_grp.accounts if a.actor == "tiny1")
        assert tiny1.composite == 100.0  # top in its own group

    def test_empty_groups(self):
        assert score_grouped({}) == []


class TestApplyDelta:
    def test_applies_trend(self):
        grp = GroupResult(group_name="Test", accounts=[])
        # We need to populate accounts manually
        from follow.scorer import AccountScore
        grp.accounts = [
            AccountScore(actor="rising", total_stars=100, followers=100,
                         star_score=90, follower_score=90, composite=90, rating="✅ 值得关注"),
            AccountScore(actor="falling", total_stars=10, followers=10,
                         star_score=50, follower_score=50, composite=50, rating="⚠️ 可以观望"),
            AccountScore(actor="newbie", total_stars=5, followers=5,
                         star_score=20, follower_score=20, composite=20, rating="❌ 暂不推荐"),
        ]
        previous = {
            "Test": {"rising": 75.0, "falling": 60.0},  # no "newbie" → no previous
        }
        result = apply_delta([grp], previous)
        updated = result[0].accounts
        assert isinstance(updated[0], AccountScoreWithDelta)

        rising = next(a for a in updated if a.actor == "rising")
        assert rising.delta == 15.0
        assert "🔥" in rising.trend

        falling = next(a for a in updated if a.actor == "falling")
        assert falling.delta == -10.0
        assert "📉" in falling.trend

        newbie = next(a for a in updated if a.actor == "newbie")
        assert newbie.delta == 0.0
        assert newbie.trend == ""
