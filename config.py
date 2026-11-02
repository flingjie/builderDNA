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


class OutputConfig(BaseModel):
    """Output configuration."""

    dir: str = Field(default="./output", description="Output directory")
    formats: list[Literal["markdown", "json", "html"]] = Field(
        default=["markdown", "json"], description="Output formats to generate"
    )


class Config(BaseModel):
    """Root configuration for BuilderDNA."""

    output: OutputConfig = Field(default_factory=OutputConfig)


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
