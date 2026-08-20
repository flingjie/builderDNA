from pathlib import Path

import yaml

PRESET_PATH = Path("config/reddit_feeds/agent-startup.yaml")
EXPECTED_FEEDS = {
    "AI_Agents": ("agent-builders", "en"),
    "LangChain": ("agent-builders", "en"),
    "LocalLLaMA": ("agent-builders", "en"),
    "LLMDevs": ("agent-builders", "en"),
    "SaaS": ("founders", "en"),
    "startups": ("founders", "en"),
    "SideProject": ("founders", "en"),
    "indiehackers": ("founders", "en"),
    "microSaaS": ("founders", "en"),
    "automation": ("automation-buyers", "en"),
    "n8n": ("automation-buyers", "en"),
    "smallbusiness": ("automation-buyers", "en"),
    "China_irl": ("chinese-market", "zh"),
}
REQUIRED_ZH_KEYWORDS = {
    "AI Agent",
    "智能体",
    "AI 代理",
    "大模型",
    "自动化",
    "工作流",
    "SaaS",
    "创业",
    "独立开发",
    "获客",
    "降本增效",
}


def load_preset() -> dict:
    return yaml.safe_load(PRESET_PATH.read_text(encoding="utf-8"))


def test_agent_startup_scan_policy():
    preset = load_preset()

    assert preset["name"] == "agent-startup"
    assert preset["description"]
    assert preset["scan"] == {
        "sort": "new",
        "limit": 25,
        "request_interval_seconds": 60,
        "retry_after_rate_limit_seconds": 60,
        "retry_limit": 1,
    }


def test_agent_startup_feed_inventory():
    feeds = load_preset()["feeds"]
    actual = {
        feed["subreddit"]: (feed["segment"], feed["language"])
        for feed in feeds
    }

    assert len(feeds) == 13
    assert len(actual) == len(feeds)
    assert actual == EXPECTED_FEEDS


def test_chinese_feeds_require_keywords():
    chinese_feeds = [
        feed for feed in load_preset()["feeds"] if feed["language"] == "zh"
    ]

    assert chinese_feeds
    for feed in chinese_feeds:
        keywords = feed.get("include_keywords")
        assert isinstance(keywords, list)
        assert keywords

    china_irl = next(
        feed for feed in chinese_feeds if feed["subreddit"] == "China_irl"
    )
    assert set(china_irl["include_keywords"]) == REQUIRED_ZH_KEYWORDS


def test_feed_fields_use_supported_values():
    preset = load_preset()
    assert preset["scan"]["sort"] in {"new", "hot", "top"}
    assert 1 <= preset["scan"]["limit"] <= 25

    for feed in preset["feeds"]:
        assert set(feed) >= {"subreddit", "segment", "language"}
        assert feed["segment"] in {
            "agent-builders",
            "founders",
            "automation-buyers",
            "chinese-market",
        }
        assert feed["language"] in {"en", "zh"}


SKILL_PATH = Path(".claude/skills/reddit-opportunity/SKILL.md")


def test_skill_documents_agent_startup_preset_resolution():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "config/reddit_feeds/{preset}.yaml" in skill
    assert "/reddit-opportunity agent-startup" in skill
    assert "Explicit subreddit wins" in skill
    assert "Do not silently default to a preset" in skill
    assert "single mode" in skill
    assert "preset mode" in skill


def test_skill_frontmatter_mentions_feed_presets():
    skill = SKILL_PATH.read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]

    assert "feed preset" in frontmatter
    assert "Agent startup" in frontmatter


def test_skill_documents_multi_feed_acquisition_contract():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    for phrase in (
        "## 2A. Single-subreddit fetch",
        "## 2B. Preset fetch loop",
        "Keyword filtering",
        "title + selftext",
        "raw feed's newest post",
        "request_interval_seconds",
        "retry_after_rate_limit_seconds",
        "retry_limit",
    ):
        assert phrase in skill


def test_skill_documents_every_feed_status():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    for status in (
        "scanned",
        "no-new-posts",
        "filtered-empty",
        "missing/private",
        "rate-limited",
        "failed",
    ):
        assert f"`{status}`" in skill


def test_skill_documents_cross_segment_ranking():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    for phrase in (
        "Technical recurrence",
        "Commercial recurrence",
        "Buyer recurrence",
        "Cross-segment validation",
        "source_subreddits",
        "source_segments",
    ):
        assert phrase in skill


def test_skill_preserves_single_output_and_adds_preset_output():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert '"subreddit": "SaaS"' in skill
    assert '"preset": "agent-startup"' in skill
    assert '"scan_summary"' in skill
    assert '"subreddits"' in skill
