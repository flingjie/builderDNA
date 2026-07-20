"""Configuration system for BuilderDNA.

Loads config.yaml with environment variable substitution (${VAR} syntax).
Auto-loads .env file if present.
"""

import os
import re
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


class GitHubConfig(BaseModel):
    """GitHub API configuration."""

    token: str = Field(description="GitHub Personal Access Token")
    cache_dir: str = Field(default="snapshots/cache", description="Directory for HTTP cache")
    max_concurrent: int = Field(default=5, ge=1, le=20, description="Max concurrent API requests")
    rate_limit_margin: int = Field(default=50, ge=10, le=500,
                                   description="Pause when remaining calls below this")


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = Field(default="openai", description="LLM provider name")
    model: str = Field(default="gpt-4o", description="Model ID")
    api_key: str = Field(description="API key for the LLM provider")
    base_url: str = Field(default="", description="Optional base URL for the LLM API endpoint")


class WeightConfig(BaseModel):
    """Signal weight configuration."""

    repo: float = 5.0
    commit: float = 3.0
    pr: float = 2.5
    issue: float = 1.5
    star: float = 1.0


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


class CompareConfig(BaseModel):
    """Incremental comparison configuration."""

    enabled: bool = Field(default=True, description="Enable incremental comparison")


class Config(BaseModel):
    """Root configuration for BuilderDNA."""

    accounts: list[str] = Field(description="GitHub accounts to analyze")
    follow_accounts: list[str] = Field(
        default_factory=list, description="GitHub accounts recommended to follow (flat)"
    )
    follow_groups: dict[str, list[str]] = Field(
        default_factory=dict, description="Follow accounts grouped by domain"
    )
    github: GitHubConfig
    llm: LLMConfig
    weights: WeightConfig = Field(default_factory=WeightConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    collect: CollectConfig = Field(default_factory=CollectConfig)
    compare: CompareConfig = Field(default_factory=CompareConfig)


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _resolve_env(value: str) -> str:
    """Replace ${VAR} patterns with environment variable values."""
    if not isinstance(value, str):
        return value
    return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)


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
