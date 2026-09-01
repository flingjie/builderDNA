"""Tests for the radar configuration loader (radar_cycles/config.py).

A radar config lives in ``config/radars/<name>.yaml`` and may reference a Reddit
feed preset in ``config/reddit_feeds/<preset>.yaml``. The loader:

- parses and validates the radar YAML into a typed :class:`RadarConfig`,
- resolves the referenced Reddit preset to its full validated contents,
- rejects configs that violate the radar rules (3-5 neighborhoods, unique
  topics/neighborhoods, supported sources/roles, non-negative caps, existing
  preset, no unknown top-level fields), and
- derives a deterministic SHA-256 fingerprint over the resolved config (preset
  contents included) so an in-progress run can fail closed on any config change.

Tests that mutate a config write a copy under ``tmp_path``; the real
``config/radars/agent-reliability.yaml`` is only ever read.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from radar_cycles.config import (
    RadarConfig,
    RadarConfigError,
    RedditPreset,
    fingerprint,
    load_radar_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_RADAR_DIR = REPO_ROOT / "config" / "radars"
REAL_REDDIT_DIR = REPO_ROOT / "config" / "reddit_feeds"


def load_real(name: str = "agent-reliability") -> RadarConfig:
    return load_radar_config(name, REAL_RADAR_DIR, REAL_REDDIT_DIR)


# ── Fixtures / helpers ──

# A minimal valid radar config (exactly 3 neighborhoods, no preset).
VALID_RADAR: dict = {
    "version": 1,
    "name": "agent-reliability",
    "description": "test radar",
    "neighborhoods": [
        {"id": "n1", "label": "One", "focus": "first"},
        {"id": "n2", "label": "Two", "focus": "second"},
        {"id": "n3", "label": "Three", "focus": "third"},
    ],
}

# A minimal valid Reddit feed preset.
VALID_PRESET: dict = {
    "name": "production-agent-failures",
    "description": "test preset",
    "scan": {
        "sort": "new",
        "limit": 25,
        "request_interval_seconds": 60,
        "retry_after_rate_limit_seconds": 60,
        "retry_limit": 1,
    },
    "feeds": [
        {"subreddit": "ChatGPT", "segment": "agent-users", "language": "en"},
        {"subreddit": "AI_Agents", "segment": "agent-builders", "language": "en"},
    ],
}


def write_radar(tmp_path: Path, data: dict) -> Path:
    """Write ``data`` to ``<tmp_path>/radars/<data["name"]>.yaml`` and return that dir."""
    radar_dir = tmp_path / "radars"
    radar_dir.mkdir(parents=True, exist_ok=True)
    (radar_dir / f'{data["name"]}.yaml').write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    return radar_dir


def write_preset(tmp_path: Path, data: dict) -> Path:
    """Write ``data`` to ``<tmp_path>/reddit_feeds/<data["name"]>.yaml`` and return that dir."""
    reddit_dir = tmp_path / "reddit_feeds"
    reddit_dir.mkdir(parents=True, exist_ok=True)
    (reddit_dir / f'{data["name"]}.yaml').write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    return reddit_dir


def empty_reddit_dir(tmp_path: Path) -> Path:
    reddit_dir = tmp_path / "reddit_feeds"
    reddit_dir.mkdir(parents=True, exist_ok=True)
    return reddit_dir


# ── Loading the real config ──

class TestLoadRealConfig:
    def test_agent_reliability_loads_and_validates(self):
        cfg = load_real("agent-reliability")
        assert cfg.name == "agent-reliability"
        assert cfg.version == 1
        assert len(cfg.neighborhoods) == 5
        assert len(cfg.exclusions) == 4
        assert cfg.daily_card_cap == 3
        assert cfg.weekly_build_cap == 1
        assert len(cfg.reddit_communities) == 7
        assert {c.role for c in cfg.reddit_communities} == {"problem", "solution"}
        # no preset referenced by the real config → resolved preset is None
        assert cfg.reddit_preset is None
        assert cfg.reddit is None

    def test_neighborhood_ids_are_unique_and_nonempty(self):
        cfg = load_real("agent-reliability")
        ids = [n.id for n in cfg.neighborhoods]
        assert len(ids) == len(set(ids)) == 5
        assert all(n.label for n in cfg.neighborhoods)

    def test_limits_reuse_radar_cycles_limits(self):
        cfg = load_real("agent-reliability")
        assert cfg.limits.daily_builds == cfg.daily_card_cap
        assert cfg.limits.weekly_builds == cfg.weekly_build_cap

    def test_missing_file_rejected(self, tmp_path):
        with pytest.raises(RadarConfigError):
            load_radar_config("no-such-radar", tmp_path / "radars", empty_reddit_dir(tmp_path))


# ── Structural validation ──

class TestValidation:
    def test_missing_reddit_preset_rejected(self, tmp_path):
        radar_dir = write_radar(tmp_path, {**VALID_RADAR, "reddit_preset": "does-not-exist"})
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, empty_reddit_dir(tmp_path))

    def test_unknown_top_level_field_rejected(self, tmp_path):
        radar_dir = write_radar(tmp_path, {**VALID_RADAR, "mystery_field": 123})
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, empty_reddit_dir(tmp_path))

    def test_less_than_three_neighborhoods_rejected(self, tmp_path):
        radar_dir = write_radar(
            tmp_path, {**VALID_RADAR, "neighborhoods": VALID_RADAR["neighborhoods"][:2]}
        )
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, empty_reddit_dir(tmp_path))

    def test_more_than_five_neighborhoods_rejected(self, tmp_path):
        neighborhoods = [
            {"id": f"n{i}", "label": f"Label {i}"} for i in range(6)
        ]
        radar_dir = write_radar(tmp_path, {**VALID_RADAR, "neighborhoods": neighborhoods})
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, empty_reddit_dir(tmp_path))

    def test_duplicate_neighborhood_ids_rejected(self, tmp_path):
        neighborhoods = [
            {"id": "dup", "label": "One"},
            {"id": "dup", "label": "Two"},
            {"id": "n3", "label": "Three"},
        ]
        radar_dir = write_radar(tmp_path, {**VALID_RADAR, "neighborhoods": neighborhoods})
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, empty_reddit_dir(tmp_path))

    def test_duplicate_topics_rejected(self, tmp_path):
        radar_dir = write_radar(tmp_path, {**VALID_RADAR, "topics": ["agent", "agent"]})
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, empty_reddit_dir(tmp_path))

    def test_unsupported_source_type_rejected(self, tmp_path):
        radar_dir = write_radar(
            tmp_path, {**VALID_RADAR, "sources": ["github", "not-a-source"]}
        )
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, empty_reddit_dir(tmp_path))

    def test_unsupported_role_rejected(self, tmp_path):
        radar_dir = write_radar(
            tmp_path,
            {
                **VALID_RADAR,
                "reddit_communities": [{"subreddit": "ChatGPT", "role": "bogus"}],
            },
        )
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, empty_reddit_dir(tmp_path))

    def test_negative_daily_cap_rejected(self, tmp_path):
        radar_dir = write_radar(tmp_path, {**VALID_RADAR, "daily_card_cap": -1})
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, empty_reddit_dir(tmp_path))

    def test_negative_weekly_cap_rejected(self, tmp_path):
        radar_dir = write_radar(tmp_path, {**VALID_RADAR, "weekly_build_cap": -2})
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, empty_reddit_dir(tmp_path))


# ── Reddit preset resolution ──

class TestPresetResolution:
    def test_referenced_preset_resolves_to_full_contents(self, tmp_path):
        reddit_dir = write_preset(tmp_path, VALID_PRESET)
        radar_dir = write_radar(
            tmp_path, {**VALID_RADAR, "reddit_preset": "production-agent-failures"}
        )
        cfg = load_radar_config("agent-reliability", radar_dir, reddit_dir)
        assert isinstance(cfg.reddit, RedditPreset)
        assert cfg.reddit.name == "production-agent-failures"
        assert cfg.reddit_preset == "production-agent-failures"
        assert [f.subreddit for f in cfg.reddit.feeds] == ["ChatGPT", "AI_Agents"]
        assert cfg.reddit.scan.limit == 25

    def test_preset_with_invalid_yaml_rejected(self, tmp_path):
        reddit_dir = tmp_path / "reddit_feeds"
        reddit_dir.mkdir(parents=True)
        (reddit_dir / "broken.yaml").write_text(": : not: [valid", encoding="utf-8")
        radar_dir = write_radar(tmp_path, {**VALID_RADAR, "reddit_preset": "broken"})
        with pytest.raises(RadarConfigError):
            load_radar_config("agent-reliability", radar_dir, reddit_dir)


# ── Fingerprint ──

class TestFingerprint:
    def test_stable_for_equal_config(self):
        a = load_real("agent-reliability")
        b = load_real("agent-reliability")
        assert fingerprint(a) == fingerprint(b)
        assert a.fingerprint == b.fingerprint
        assert len(a.fingerprint) == 64  # sha256 hex digest

    def test_changes_when_a_field_changes(self, tmp_path):
        radar_dir = write_radar(tmp_path, VALID_RADAR)
        reddit_dir = empty_reddit_dir(tmp_path)
        a = load_radar_config("agent-reliability", radar_dir, reddit_dir)

        write_radar(tmp_path, {**VALID_RADAR, "description": "changed description"})
        b = load_radar_config("agent-reliability", radar_dir, reddit_dir)
        assert fingerprint(a) != fingerprint(b)

    def test_includes_resolved_preset_contents(self, tmp_path):
        reddit_dir = write_preset(tmp_path, VALID_PRESET)
        radar_dir = write_radar(
            tmp_path, {**VALID_RADAR, "reddit_preset": "production-agent-failures"}
        )
        a = load_radar_config("agent-reliability", radar_dir, reddit_dir)

        # Same radar config, but the referenced preset's contents change.
        changed_preset = {
            **VALID_PRESET,
            "scan": {**VALID_PRESET["scan"], "limit": 10},
        }
        write_preset(tmp_path, changed_preset)
        b = load_radar_config("agent-reliability", radar_dir, reddit_dir)
        assert fingerprint(a) != fingerprint(b)
