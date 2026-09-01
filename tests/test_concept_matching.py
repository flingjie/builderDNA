"""Tests for deterministic concept matching (concepts/matching.py).

Covers the hard requirements:
- A renamed old idea matches as an alias (old title in a new card's aliases).
- Normalized name equality and explicit aliases drive name matching (never fuzzy).
- Shared source URLs and normalized problem fingerprints drive evidence matching.
- Ranked candidates carry reasons (why they matched, with a score).
- Concepts with different users, failure modes, or interventions stay separate
  even when names are superficially similar.
- Ambiguous merges (near-ties, or name-similar but problem-different) are flagged
  for human confirmation and never auto-merged.
"""

from models.concept import ConceptCard

from concepts.matching import (
    ALIAS_SCORE,
    NAME_EXACT_SCORE,
    PROBLEM_EXACT_SCORE,
    URL_SCORE,
    find_candidates,
    is_ambiguous,
    normalize_name,
    normalize_url,
)


def card(**overrides) -> ConceptCard:
    fields = dict(id="c1", title="Agent Reliability")
    fields.update(overrides)
    return ConceptCard(**fields)


# ── Normalization ──

class TestNormalization:
    def test_name_lowercases_strips_punctuation_collapses_whitespace(self):
        assert normalize_name("  Agent Reliability! ") == "agent reliability"
        assert normalize_name("MCP-Servers") == "mcp servers"

    def test_url_lowercases_drops_fragment_and_trailing_slash(self):
        assert normalize_url("HTTPS://Example.com/repo/") == "https://example.com/repo"
        assert normalize_url("https://example.com/repo#section") == "https://example.com/repo"


# ── Name / alias matching ──

class TestNameMatching:
    def test_exact_normalized_name_matches(self):
        existing = [card(id="a", title="Agent Reliability")]
        candidate = card(id="b", title="Agent Reliability")
        matches = find_candidates(candidate, existing)
        assert len(matches) == 1
        assert matches[0].name_score == NAME_EXACT_SCORE
        assert matches[0].reasons[0].signal == "name"

    def test_renamed_old_idea_matches_via_alias(self):
        # The old title lives in the new card's aliases.
        existing = [card(id="a", title="Hallucination Guard")]
        candidate = card(id="b", title="Agent Reliability", aliases=["Hallucination Guard"])
        matches = find_candidates(candidate, existing)
        assert len(matches) == 1
        assert matches[0].concept_id == "a"
        assert matches[0].name_score == ALIAS_SCORE
        assert matches[0].reasons[0].signal == "alias"

    def test_candidate_title_in_existing_aliases_matches(self):
        existing = [card(id="a", title="Agent Reliability", aliases=["Hallucination Guard"])]
        candidate = card(id="b", title="Hallucination Guard")
        matches = find_candidates(candidate, existing)
        assert len(matches) == 1
        assert matches[0].name_score == ALIAS_SCORE
        assert matches[0].reasons[0].signal == "alias"

    def test_superficially_similar_names_do_not_match(self):
        existing = [card(id="a", title="Agent Reliability", problem="hallucinations in prod")]
        candidate = card(id="b", title="Agent Reliability Framework", problem="cost overruns")
        assert find_candidates(candidate, existing) == []


# ── URL matching ──

class TestUrlMatching:
    def test_shared_url_matches(self):
        existing = [card(id="a", title="Agent Reliability")]
        candidate = card(id="b", title="Totally Different Name")
        matches = find_candidates(
            candidate,
            existing,
            candidate_urls=["https://github.com/x/y"],
            existing_urls={"a": ["https://github.com/x/y"]},
        )
        assert len(matches) == 1
        assert matches[0].url_score == URL_SCORE
        assert matches[0].reasons[0].signal == "url"

    def test_different_urls_do_not_match(self):
        existing = [card(id="a", title="Agent Reliability")]
        candidate = card(id="b", title="Agent Reliability")
        matches = find_candidates(
            candidate,
            existing,
            candidate_urls=["https://github.com/x/y"],
            existing_urls={"a": ["https://github.com/x/other"]},
        )
        # name equality still matches, but the url signal should be absent
        assert len(matches) == 1
        assert matches[0].url_score == 0.0


# ── Problem fingerprint matching ──

class TestProblemMatching:
    def test_exact_normalized_problem_matches(self):
        existing = [card(id="a", title="Alpha", problem="Agents hallucinate in production")]
        candidate = card(id="b", title="Beta", problem="Agents hallucinate in production!")
        matches = find_candidates(candidate, existing)
        assert len(matches) == 1
        assert matches[0].problem_score == PROBLEM_EXACT_SCORE
        assert matches[0].reasons[0].signal == "problem"

    def test_partial_problem_overlap_scores_below_exact(self):
        existing = [card(id="a", title="Alpha", problem="agents hallucinate in production")]
        candidate = card(id="b", title="Beta", problem="agents hallucinate in testing")
        matches = find_candidates(candidate, existing)
        assert len(matches) == 1
        assert 0.0 < matches[0].problem_score < PROBLEM_EXACT_SCORE

    def test_disjoint_problems_do_not_match(self):
        existing = [card(id="a", title="Alpha", problem="hallucination")]
        candidate = card(id="b", title="Beta", problem="latency budgets")
        assert find_candidates(candidate, existing) == []


# ── Ranking and reasons ──

class TestRanking:
    def test_ranked_by_score_then_id(self):
        existing = [
            card(id="z", title="Agent Reliability"),
            card(id="a", title="agent reliability"),
        ]
        candidate = card(id="c", title="Agent Reliability")
        matches = find_candidates(candidate, existing)
        # equal scores -> deterministic tie-break by ascending concept id
        assert [m.concept_id for m in matches] == ["a", "z"]
        assert matches[0].score == matches[1].score

    def test_min_score_filters(self):
        existing = [card(id="a", title="Agent Reliability")]
        candidate = card(id="b", title="Agent Reliability")
        assert find_candidates(candidate, existing, min_score=NAME_EXACT_SCORE + 0.1) == []
        assert len(find_candidates(candidate, existing, min_score=NAME_EXACT_SCORE)) == 1

    def test_reasons_carry_signal_and_score(self):
        existing = [card(id="a", title="Agent Reliability")]
        candidate = card(id="b", title="Agent Reliability")
        m = find_candidates(candidate, existing)[0]
        assert m.reasons[0].score == NAME_EXACT_SCORE
        assert m.score == NAME_EXACT_SCORE


# ── Staying separate for different users / failure modes / interventions ──

class TestStaySeparate:
    def test_different_failure_mode_same_name_is_ambiguous(self):
        existing = [card(id="a", title="Agent Reliability", problem="hallucinations in production")]
        candidate = card(id="b", title="Agent Reliability", problem="exceeding latency budgets")
        matches = find_candidates(candidate, existing)
        assert len(matches) == 1
        assert matches[0].name_score == NAME_EXACT_SCORE
        assert is_ambiguous(matches) is True

    def test_different_user_similar_name_stays_separate(self):
        existing = [card(id="a", title="Agent Reliability", problem="solo builders")]
        candidate = card(id="b", title="Agent Reliability Framework", problem="enterprise platform teams")
        assert find_candidates(candidate, existing) == []

    def test_different_intervention_stays_separate(self):
        existing = [card(id="a", title="Agent Watchdog", problem="uncaught agent failures")]
        candidate = card(id="b", title="Agent Guardrail", problem="prompt injection exploits")
        assert find_candidates(candidate, existing) == []

    def test_same_name_same_problem_is_not_ambiguous(self):
        existing = [card(id="a", title="Agent Reliability", problem="hallucinations in production")]
        candidate = card(id="b", title="Agent Reliability", problem="hallucinations in production")
        matches = find_candidates(candidate, existing)
        assert len(matches) == 1
        assert is_ambiguous(matches) is False


# ── Ambiguity ──

class TestAmbiguity:
    def test_no_matches_not_ambiguous(self):
        assert is_ambiguous([]) is False

    def test_tie_at_top_is_ambiguous(self):
        existing = [
            card(id="a", title="Agent Reliability"),
            card(id="b", title="Agent Reliability"),
        ]
        candidate = card(id="c", title="Agent Reliability")
        matches = find_candidates(candidate, existing)
        assert len(matches) == 2
        assert is_ambiguous(matches) is True

    def test_clear_winner_not_ambiguous(self):
        existing = [
            card(id="a", title="Agent Reliability"),
            card(id="b", title="Other", problem="hallucinations in production"),
        ]
        candidate = card(id="c", title="Agent Reliability", problem="hallucinations in production")
        matches = find_candidates(candidate, existing)
        # a matches by name AND problem; b matches only by problem -> clear winner
        assert len(matches) == 2
        assert matches[0].concept_id == "a"
        assert is_ambiguous(matches) is False

    def test_name_match_with_empty_existing_problem_not_flagged(self):
        existing = [card(id="a", title="Agent Reliability", problem="")]
        candidate = card(id="b", title="Agent Reliability", problem="hallucinations")
        matches = find_candidates(candidate, existing)
        assert len(matches) == 1
        assert is_ambiguous(matches) is False
