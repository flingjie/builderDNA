"""FastAPI dependency injection."""
import os
from functools import lru_cache

from collect.github.client import GitHubClient
from config import load_config, Config


@lru_cache()
def get_config() -> Config:
    """Load config once and cache."""
    _load_dotenv()
    return load_config("config.yaml")


def _load_dotenv():
    from pathlib import Path
    env_file = Path(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = val


def get_github_client() -> GitHubClient:
    cfg = get_config()
    return GitHubClient(
        token=cfg.github.token,
        cache_dir=cfg.github.cache_dir,
        max_concurrent=cfg.github.max_concurrent,
        rate_limit_margin=cfg.github.rate_limit_margin,
    )


def get_domain_config(domain: str):
    """Get domain config by name."""
    cfg = get_config()
    from backend.models.trend import DomainConfig

    domains_raw = cfg.model_dump().get("domains", {})
    if domain in domains_raw:
        d = domains_raw[domain]
        return DomainConfig(
            name=domain,
            topics=d.get("topics", []),
            window_days=d.get("window_days", 60),
        )
    # Fallback: treat domain as topic list from config
    return DomainConfig(name=domain, topics=[domain])
