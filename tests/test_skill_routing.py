"""Routing-contract tests for the skill topology (Phase 2).

These tests assert that each core intelligence skill declares a clear "做/不做"
boundary and routes adjacent requests to exactly one specialist, so a single user
request maps to a single owning skill. No network, no Python models — they read
the SKILL.md files directly.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def skill(name: str) -> Path:
    return PROJECT_ROOT / f".claude/skills/{name}/SKILL.md"


def read(name: str) -> str:
    return skill(name).read_text(encoding="utf-8")


# The eight owners from docs/product-contract.md §4.1 — one owner per request.
ROUTING_EDGES = {
    "builderdna": [
        ("repo-trend", "builderdna routes repo discovery to repo-trend"),
        ("repo-awesome", "builderdna routes awesome-list curation to repo-awesome"),
        ("twitter-learning", "builderdna routes X learning to twitter-learning"),
        ("reddit-opportunity", "builderdna routes Reddit pain to reddit-opportunity"),
        ("concept-radar", "builderdna routes cross-source validation to concept-radar"),
    ],
    "repo-trend": [
        ("repo-awesome", "repo-trend routes awesome-list to repo-awesome"),
        ("builderdna", "repo-trend routes developer DNA to builderdna"),
        ("concept-radar", "repo-trend routes cross-source to concept-radar"),
    ],
    "repo-awesome": [
        ("repo-trend", "repo-awesome routes API search to repo-trend"),
        ("builderdna", "repo-awesome routes developer DNA to builderdna"),
        ("concept-radar", "repo-awesome routes cross-source to concept-radar"),
    ],
    "reddit-opportunity": [
        ("twitter-learning", "reddit-opportunity routes X learning to twitter-learning"),
        ("concept-radar", "reddit-opportunity routes cross-source to concept-radar"),
    ],
    "repo-evolution-learning": [
        ("repo-trend", "repo-evolution-learning routes GitHub-only discovery to repo-trend"),
        ("builderdna", "repo-evolution-learning routes developer DNA to builderdna"),
        ("concept-radar", "repo-evolution-learning routes cross-source to concept-radar"),
        ("twitter-learning", "repo-evolution-learning routes X learning to twitter-learning"),
    ],
    "observability": [
        ("optimize", "observability routes improvement proposals to optimize"),
    ],
}


def test_each_skill_declares_routing_boundary():
    """Each routing-bearing skill has a 做/不做 and a routing table."""
    for owner in ROUTING_EDGES:
        body = read(owner)
        assert "做什么" in body and "不做什么" in body, f"{owner} lacks 做/不做"
        assert "路由" in body or "Routing" in body, f"{owner} lacks a routing table"


def test_single_source_routes_to_exactly_one_specialist():
    """Every owner routes its adjacent requests to the declared specialist."""
    for owner, edges in ROUTING_EDGES.items():
        body = read(owner)
        for target, reason in edges:
            assert target in body, f"{owner}: {reason}"


def test_builderdna_does_not_replace_specialists():
    body = read("builderdna")
    assert "只编排 Python sandbox" in body
    assert "不替代专家 Skill" in body


def test_concept_radar_receives_selected_findings_not_search():
    """concept-radar owns synthesis, not single-source search."""
    body = read("concept-radar")
    assert "单源" in body
    # Routing to specialists, never the reverse for single-source search.
    for target in ("twitter-learning", "reddit-opportunity", "repo-trend"):
        assert target in body


def test_engagement_and_outreach_have_no_owner():
    """X reply/engagement and customer outreach must not be owned by any skill."""
    for name in ("concept-radar", "twitter-learning", "builderdna"):
        body = read(name)
        assert "twitter-discussion" not in body, f"{name} routes to a deleted skill"
        assert "reddit-outreach" not in body, f"{name} routes to a deleted skill"
