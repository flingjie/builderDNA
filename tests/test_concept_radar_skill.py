"""Phase 0 tests for the concept-radar skill topology and config.

These tests assert that routing decisions are observable in the repo — no network,
no Python models. They read the SKILL.md files and the radar/feed YAML configs and
check the routing lines, caps, and community coverage.
"""

from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONCEPT_RADAR_SKILL = PROJECT_ROOT / ".claude/skills/concept-radar/SKILL.md"
CONCEPT_RADAR_SCHEMA = (
    PROJECT_ROOT / ".claude/skills/concept-radar/references/schema.md"
)
TWITTER_LEARNING_SKILL = PROJECT_ROOT / ".claude/skills/twitter-learning/SKILL.md"
TWITTER_DISCUSSION_SKILL = (
    PROJECT_ROOT / ".claude/skills/twitter-discussion/SKILL.md"
)
RADAR_CONFIG = PROJECT_ROOT / "config/radars/agent-reliability.yaml"
REDDIT_FEED = (
    PROJECT_ROOT / "config/reddit_feeds/production-agent-failures.yaml"
)

SPECIALIST_SKILLS = (
    "twitter-learning",
    "twitter-discussion",
    "reddit-opportunity",
    "repo-trend",
)

RADAR_MODES = ("capture", "scan", "verify", "review", "build", "source-audit")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def frontmatter(text: str) -> str:
    return text.split("---", 2)[1]


# --- Task 0.1: routing is observable ----------------------------------------


def test_concept_radar_skill_exists():
    assert CONCEPT_RADAR_SKILL.exists()


def test_concept_radar_frontmatter_triggers_on_weak_signal_requests():
    fm = frontmatter(read_text(CONCEPT_RADAR_SKILL))
    collapsed = " ".join(fm.split())

    assert "name: concept-radar" in fm
    assert "validate an idea" in collapsed
    assert "weak signals to validated builds" in collapsed
    assert "Inbox" in collapsed and "Build" in collapsed


def test_concept_radar_routes_to_specialist_skills():
    body = read_text(CONCEPT_RADAR_SKILL)

    for skill in SPECIALIST_SKILLS:
        assert skill in body, f"concept-radar must route to {skill}"

    # Cross-source synthesis routes to itself.
    assert "concept-radar" in body


def test_concept_radar_documents_modes():
    body = read_text(CONCEPT_RADAR_SKILL)

    for mode in RADAR_MODES:
        assert f"`{mode}`" in body, f"concept-radar must document mode {mode}"


def test_concept_radar_schema_documents_contracts_and_invariants():
    body = read_text(CONCEPT_RADAR_SCHEMA)

    for contract in (
        "ConceptCard",
        "ConceptEvidence",
        "RadarReview",
        "RadarRunPayload",
    ):
        assert contract in body

    for invariant in (
        "immutable",
        "atomic",
        "Maturity describes evidence status",
        "independence_key",
        "user_alignment",
        "two source types",
    ):
        assert invariant in body


def test_twitter_learning_clarifies_x_only_and_radar_feed():
    body = read_text(TWITTER_LEARNING_SKILL)

    # X-only learning and knowledge-base requests route here.
    assert "concept-radar" in body
    assert "twitter-learning" in body
    # Selected findings may enter cross-source validation; never the reverse.
    assert "跨源验证" in body


def test_twitter_discussion_clarifies_engagement_only():
    body = read_text(TWITTER_DISCUSSION_SKILL)

    assert "concept-radar" in body
    # Owns outward engagement only, never concept cards.
    assert "outward engagement" in body
    assert "概念卡片" in body


# --- Task 0.2: Agent Reliability radar config -------------------------------


def test_radar_config_is_valid_yaml_with_caps():
    cfg = yaml.safe_load(RADAR_CONFIG.read_text(encoding="utf-8"))

    assert cfg["version"] == 1
    assert cfg["name"] == "agent-reliability"
    assert cfg["daily_card_cap"] == 3
    assert cfg["weekly_build_cap"] == 1


def test_radar_config_has_three_to_five_neighborhoods():
    cfg = yaml.safe_load(RADAR_CONFIG.read_text(encoding="utf-8"))

    neighborhoods = cfg["neighborhoods"]
    assert 3 <= len(neighborhoods) <= 5

    for nb in neighborhoods:
        assert nb["id"]
        assert nb["label"]
        assert nb["focus"]


def test_radar_config_has_explicit_exclusions():
    cfg = yaml.safe_load(RADAR_CONFIG.read_text(encoding="utf-8"))

    assert isinstance(cfg["exclusions"], list)
    assert cfg["exclusions"]
    assert all(isinstance(item, str) and item for item in cfg["exclusions"])


def test_radar_config_has_problem_and_solution_communities():
    cfg = yaml.safe_load(RADAR_CONFIG.read_text(encoding="utf-8"))

    communities = cfg["reddit_communities"]
    assert communities

    roles = {c["role"] for c in communities}
    assert "problem" in roles
    assert "solution" in roles

    # Each community entry carries the fields the radar needs.
    for c in communities:
        assert c["subreddit"]
        assert c["segment"]


def test_reddit_feed_preset_is_valid_yaml():
    preset = yaml.safe_load(REDDIT_FEED.read_text(encoding="utf-8"))

    assert preset["name"] == "production-agent-failures"
    assert preset["description"]
    assert preset["scan"]["sort"] in {"new", "hot", "top"}
    assert 1 <= preset["scan"]["limit"] <= 25

    feeds = preset["feeds"]
    assert feeds

    subreddits = [f["subreddit"] for f in feeds]
    assert len(subreddits) == len(set(subreddits)), "subreddits must be unique"

    for feed in feeds:
        assert feed["subreddit"]
        assert feed["segment"]
        assert feed["language"] in {"en", "zh"}

    # Includes both problem-side and solution-side communities.
    segments = {f["segment"] for f in feeds}
    assert "agent-users" in segments
    assert "agent-builders" in segments


def test_radar_and_feed_share_community_intent():
    """The feed preset and radar config agree on problem/solution sides."""
    radar = yaml.safe_load(RADAR_CONFIG.read_text(encoding="utf-8"))
    feed = yaml.safe_load(REDDIT_FEED.read_text(encoding="utf-8"))

    radar_problem = {
        c["subreddit"]
        for c in radar["reddit_communities"]
        if c["role"] == "problem"
    }
    feed_problem = {
        f["subreddit"] for f in feed["feeds"] if f["segment"] == "agent-users"
    }
    # The problem-side communities configured in the radar are present in the feed.
    assert radar_problem <= feed_problem
