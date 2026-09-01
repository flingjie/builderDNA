"""Radar configuration loader — typed, validated, fingerprinted.

Loads a radar config from ``config/radars/<name>.yaml`` into a
:class:`RadarConfig`, resolves any referenced Reddit feed preset
(``config/reddit_feeds/<preset>.yaml``) to its full validated contents, and
derives a deterministic SHA-256 fingerprint over the *resolved* config.

The fingerprint is what ``resume`` checks: if any field of the radar config or
its referenced Reddit preset changes, the fingerprint changes and an in-progress
run fails closed instead of silently continuing under different configuration.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from models.concept import SourceType
from radar_cycles.models import Limits

__all__ = [
    "RadarConfigError",
    "Neighborhood",
    "RedditCommunity",
    "RedditFeed",
    "RedditScan",
    "RedditPreset",
    "RadarConfig",
    "load_radar_config",
    "fingerprint",
]


class RadarConfigError(Exception):
    """Raised when a radar config (or its referenced preset) is missing, unparsable, or invalid."""


# ── Radar config sub-models ──

class Neighborhood(BaseModel):
    """One exploration neighborhood / lens over the radar's sources."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="Stable neighborhood id (must be unique)")
    label: str = Field(min_length=1, description="Human-readable label")
    focus: str = Field(default="", description="What this lens watches for")


class RedditCommunity(BaseModel):
    """A Reddit community watched by the radar (problem or solution side)."""

    model_config = ConfigDict(extra="forbid")

    subreddit: str = Field(min_length=1, description="Subreddit name, e.g. 'ChatGPT'")
    role: Literal["problem", "solution"] = Field(
        description="Evidence role: 'problem' (users complaining) or 'solution' (builders fixing)"
    )
    segment: str = Field(default="", description="Audience segment label")


# ── Reddit feed preset sub-models ──

class RedditFeed(BaseModel):
    """One subreddit feed inside a Reddit preset."""

    model_config = ConfigDict(extra="forbid")

    subreddit: str = Field(min_length=1, description="Subreddit name")
    segment: str = Field(default="", description="Audience segment label")
    language: str = Field(default="en", description="Feed language code (e.g. 'en', 'zh')")
    include_keywords: list[str] = Field(
        default_factory=list, description="Optional keyword filter for this feed"
    )


class RedditScan(BaseModel):
    """Scan policy for a Reddit preset."""

    model_config = ConfigDict(extra="forbid")

    sort: Literal["new", "hot", "top"] = Field(default="new", description="Feed sort order")
    limit: int = Field(default=25, ge=1, description="Posts per feed")
    request_interval_seconds: int = Field(default=60, ge=0, description="Seconds between requests")
    retry_after_rate_limit_seconds: int = Field(default=60, ge=0, description="Wait after rate-limit")
    retry_limit: int = Field(default=1, ge=0, description="Retries per feed")


class RedditPreset(BaseModel):
    """A fully validated Reddit feed preset, resolved from ``config/reddit_feeds/<name>.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Preset name (matches the filename stem)")
    description: str = Field(default="", description="What this preset scans")
    scan: RedditScan = Field(default_factory=RedditScan, description="Scan policy")
    feeds: list[RedditFeed] = Field(default_factory=list, description="Subreddit feeds")


# ── Radar config ──

class RadarConfig(BaseModel):
    """Versioned radar configuration loaded from ``config/radars/<name>.yaml``.

    ``reddit_preset`` is the *filename stem* of a referenced Reddit feed preset;
    ``reddit`` is that preset resolved to its full validated contents (populated
    by :func:`load_radar_config`, never from the YAML itself).
    """

    model_config = ConfigDict(extra="forbid")

    version: int = Field(description="Config schema version")
    name: str = Field(min_length=1, description="Radar name (matches the filename stem)")
    description: str = Field(default="", description="What this radar watches")
    neighborhoods: list[Neighborhood] = Field(
        default_factory=list, description="3-5 exploration neighborhoods (unique ids)"
    )
    topics: list[str] = Field(
        default_factory=list, description="Topic tags (must be unique)"
    )
    sources: list[SourceType] = Field(
        default_factory=list, description="Source types this radar watches"
    )
    exclusions: list[str] = Field(
        default_factory=list, description="Signals the radar explicitly ignores"
    )
    daily_card_cap: int = Field(default=3, ge=0, description="Max new concept cards per day")
    weekly_build_cap: int = Field(default=1, ge=0, description="Max Build promotions per week")
    reddit_communities: list[RedditCommunity] = Field(
        default_factory=list, description="Reddit communities with problem/solution roles"
    )
    reddit_preset: str | None = Field(
        default=None, description="Referenced Reddit feed preset filename stem"
    )
    reddit: RedditPreset | None = Field(
        default=None, description="Resolved Reddit preset contents (loader-populated)"
    )

    @property
    def limits(self) -> Limits:
        """The radar's two caps surfaced as a :class:`Limits` for checkpoint reuse.

        ``daily_card_cap`` occupies the daily slot and ``weekly_build_cap`` the
        weekly slot, so the checkpoint carries both non-negative caps.
        """
        return Limits(
            daily_builds=self.daily_card_cap,
            weekly_builds=self.weekly_build_cap,
        )

    @property
    def fingerprint(self) -> str:
        """SHA-256 fingerprint of this resolved config (see :func:`fingerprint`)."""
        return fingerprint(self)

    @model_validator(mode="after")
    def _validate_radar(self) -> "RadarConfig":
        if not 3 <= len(self.neighborhoods) <= 5:
            raise ValueError(
                f"radar config requires 3-5 exploration neighborhoods; "
                f"got {len(self.neighborhoods)}"
            )
        neighborhood_ids = [n.id for n in self.neighborhoods]
        if len(neighborhood_ids) != len(set(neighborhood_ids)):
            raise ValueError(
                "radar config neighborhoods must have unique ids; "
                f"duplicate found in {neighborhood_ids!r}"
            )
        if len(self.topics) != len(set(self.topics)):
            raise ValueError(
                f"radar config topics must be unique; duplicate found in {self.topics!r}"
            )
        if len(self.sources) != len(set(self.sources)):
            raise ValueError(
                f"radar config sources must be unique; duplicate found in {self.sources!r}"
            )
        return self


# ── Fingerprint ──

def _canonicalize(value):
    """Recursively sort dict keys so equal structures serialize identically."""
    if isinstance(value, dict):
        return {key: _canonicalize(val) for key, val in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value


def fingerprint(config: RadarConfig) -> str:
    """Return a deterministic SHA-256 hex digest of the resolved config.

    The digest covers every field of ``config`` *and* the full contents of any
    resolved Reddit preset (``config.reddit``), so any change — to the radar
    YAML or to a referenced preset file — changes the fingerprint.
    """
    data = _canonicalize(config.model_dump(mode="json"))
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Preset loading ──

def _load_reddit_preset(name: str, reddit_dir: str | Path) -> RedditPreset:
    """Load and validate a Reddit feed preset from ``<reddit_dir>/<name>.yaml``."""
    path = Path(reddit_dir) / f"{name}.yaml"
    if not path.exists():
        raise RadarConfigError(f"reddit preset not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RadarConfigError(f"invalid YAML in reddit preset {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RadarConfigError(f"reddit preset {path} must be a YAML mapping")
    try:
        preset = RedditPreset.model_validate(raw)
    except ValidationError as exc:
        raise RadarConfigError(f"invalid reddit preset {path}: {exc}") from exc
    if preset.name != name:
        raise RadarConfigError(
            f"reddit preset name {preset.name!r} does not match requested preset {name!r}"
        )
    return preset


# ── Radar config loading ──

def load_radar_config(
    name: str,
    config_dir: str | Path = "config/radars",
    reddit_dir: str | Path = "config/reddit_feeds",
) -> RadarConfig:
    """Load, validate, and resolve a radar config from ``<config_dir>/<name>.yaml``.

    Follows the ``config.load_config`` convention (YAML -> Pydantic validation),
    then resolves the referenced Reddit preset (if any) to its full validated
    contents before returning.

    Raises :class:`RadarConfigError` for a missing/unparsable/invalid radar
    config, a mismatched ``name`` field, or a missing/unparsable/invalid
    referenced Reddit preset.
    """
    path = Path(config_dir) / f"{name}.yaml"
    if not path.exists():
        raise RadarConfigError(f"radar config not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RadarConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RadarConfigError(f"radar config {path} must be a YAML mapping")

    try:
        config = RadarConfig.model_validate(raw)
    except ValidationError as exc:
        raise RadarConfigError(f"invalid radar config {path}: {exc}") from exc

    if config.name != name:
        raise RadarConfigError(
            f"radar config name {config.name!r} does not match requested radar {name!r}"
        )

    resolved_preset = (
        _load_reddit_preset(config.reddit_preset, reddit_dir)
        if config.reddit_preset
        else None
    )
    if config.reddit_preset is not None:
        return config.model_copy(update={"reddit": resolved_preset})
    return config
