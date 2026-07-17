"""Tests for config loading."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from config import Config, load_config


VALID_CONFIG = {
    "accounts": ["alice", "bob"],
    "github": {"token": "ghp_test123"},
    "llm": {"provider": "openai", "model": "gpt-4o", "api_key": "sk-test"},
    "weights": {"repo": 5.0, "commit": 3.0, "pr": 2.5, "issue": 1.5, "star": 1.0},
    "output": {"dir": "./output", "formats": ["markdown", "json"]},
    "compare": {"enabled": True},
}


@pytest.fixture
def config_file():
    """Create a temporary config.yaml."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        yaml.dump(VALID_CONFIG, f)
        path = f.name
    yield path
    os.unlink(path)


class TestLoadConfig:
    def test_loads_valid_config(self, config_file):
        cfg = load_config(config_file)
        assert cfg.accounts == ["alice", "bob"]
        assert cfg.github.token == "ghp_test123"
        assert cfg.llm.model == "gpt-4o"
        assert cfg.weights.repo == 5.0
        assert cfg.output.formats == ["markdown", "json"]
        assert cfg.compare.enabled is True

    def test_env_var_substitution(self):
        os.environ["TEST_GH_TOKEN"] = "ghp_from_env"
        os.environ["TEST_OAI_KEY"] = "sk_from_env"
        cfg_data = dict(VALID_CONFIG)
        cfg_data["github"]["token"] = "${TEST_GH_TOKEN}"
        cfg_data["llm"]["api_key"] = "${TEST_OAI_KEY}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(cfg_data, f)
            path = f.name
        try:
            cfg = load_config(path)
            assert cfg.github.token == "ghp_from_env"
            assert cfg.llm.api_key == "sk_from_env"
        finally:
            os.unlink(path)
            del os.environ["TEST_GH_TOKEN"]
            del os.environ["TEST_OAI_KEY"]

    def test_loads_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")


class TestConfigModel:
    def test_default_compare(self, config_file):
        cfg = load_config(config_file)
        assert cfg.compare.enabled is True
