"""Configuration system for BuilderDNA.

Loads config.yaml with environment variable substitution (${VAR} and ${VAR:-default} syntax).
Auto-loads .env file if present.
"""

import os
import re
import warnings
from pathlib import Path
from typing import Literal


def _load_dotenv(path: Path) -> None:
    """Load key=value pairs from a .env file into os.environ."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, val = line.partition('=')
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = val

import yaml
from pydantic import BaseModel, Field

# Auto-load .env file at import time
_load_dotenv(Path(".env"))


class GitHubConfig(BaseModel):
    """GitHub API configuration."""

    token: str = Field(description="GitHub Personal Access Token")
    cache_dir: str = Field(default="snapshots/cache", description="Directory for HTTP cache")
    max_concurrent: int = Field(default=5, ge=1, le=20, description="Max concurrent API requests")
    rate_limit_margin: int = Field(default=50, ge=10, le=500,
                                   description="Pause when remaining calls below this")


class EmbeddingConfig(BaseModel):
    """Embedding model configuration (local Ollama, no API key needed)."""

    model: str = Field(default="bge-m3:latest", description="Embedding model ID (config.yaml overrides)")
    base_url: str = Field(default="http://localhost:11434/v1", description="Embedding API base URL")


class OutputConfig(BaseModel):
    """Output configuration."""

    dir: str = Field(default="./output", description="Output directory")
    formats: list[Literal["markdown", "json"]] = Field(
        default=["markdown", "json"], description="Output formats to generate"
    )


class CollectConfig(BaseModel):
    """Data collection configuration."""

    time_range_days: int = Field(
        default=365, description="Only collect signals within this many days"
    )


class OpportunityWeights(BaseModel):
    """Demand scoring weights for opportunity detection.

    Configurable via config.yaml so weights can be tuned without code changes.
    Bootstrap-driven weight optimization (L3) can read/write these values.
    """
    velocity: float = Field(default=0.4, ge=0.0, le=1.0, description="Weight for trend velocity in demand score")
    severity: float = Field(default=0.4, ge=0.0, le=1.0, description="Weight for pain severity in demand score")
    frequency: float = Field(default=0.2, ge=0.0, le=1.0, description="Weight for pain frequency in demand score")


class OpportunityConfig(BaseModel):
    """Opportunity scoring configuration."""
    weights: OpportunityWeights = Field(default_factory=OpportunityWeights)
    gap_threshold_high: float = Field(
        default=1.5, description="Gap score above this threshold → Build or Niche quadrant"
    )
    market_size_threshold: float = Field(
        default=5.0, description="Market size above this threshold → Build or Monitor quadrant"
    )


class VendorConfig(BaseModel):
    """Vendor tracking configuration."""

    domestic: list[str] = Field(default_factory=list, description="Domestic vendor GitHub orgs")
    overseas: list[str] = Field(default_factory=list, description="Overseas vendor GitHub orgs")


class Config(BaseModel):
    """Root configuration for BuilderDNA."""

    accounts: list[str] = Field(description="GitHub accounts to analyze")
    domains: dict[str, dict] = Field(
        default_factory=dict, description="Radar domain configurations (e.g. agent.topics)"
    )
    github: GitHubConfig
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    collect: CollectConfig = Field(default_factory=CollectConfig)
    vendors: VendorConfig = Field(default_factory=VendorConfig)
    opportunity: OpportunityConfig = Field(default_factory=OpportunityConfig)


_ENV_VAR_RE = re.compile(r"\$\{(\w+)(?::-([^}]*))?\}")


def _resolve_env(value: str) -> str:
    """Replace ${VAR} and ${VAR:-default} patterns with environment variable values."""
    if not isinstance(value, str):
        return value

    def _replacer(m: re.Match) -> str:
        var = m.group(1)
        default = m.group(2)
        if default is not None:
            return os.environ.get(var, default)
        if var not in os.environ:
            warnings.warn(f"Unresolved config variable: ${{{var}}} has no environment value and no default")
        return os.environ.get(var, m.group(0))

    return _ENV_VAR_RE.sub(_replacer, value)


def _resolve_config(data: dict) -> dict:
    """Recursively resolve environment variables in config dict."""
    resolved = {}
    for key, value in data.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_config(value)
        elif isinstance(value, str):
            resolved[key] = _resolve_env(value)
        elif isinstance(value, list):
            resolved[key] = [
                _resolve_env(v) if isinstance(v, str) else v for v in value
            ]
        else:
            resolved[key] = value
    return resolved


def load_config(path: str | Path) -> Config:
    """Load and validate configuration from a YAML file.

    Args:
        path: Path to config.yaml.

    Returns:
        Validated Config object.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    resolved = _resolve_config(raw)
    return Config(**resolved)
