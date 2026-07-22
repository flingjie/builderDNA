"""Tests for config loading."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from config import Config, GitHubConfig, EmbeddingConfig, load_config


VALID_CONFIG = {
    "accounts": ["alice", "bob"],
    "github": {"token": "ghp_test123"},
    "output": {"dir": "./output", "formats": ["markdown", "json"]},
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
        assert cfg.embedding.model == "bge-m3:latest"
        assert cfg.output.formats == ["markdown", "json"]

    def test_env_var_substitution(self):
        os.environ["TEST_GH_TOKEN"] = "ghp_from_env"
        cfg_data = dict(VALID_CONFIG)
        cfg_data["github"]["token"] = "${TEST_GH_TOKEN}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(cfg_data, f)
            path = f.name
        try:
            cfg = load_config(path)
            assert cfg.github.token == "ghp_from_env"
        finally:
            os.unlink(path)
            del os.environ["TEST_GH_TOKEN"]

    def test_env_var_with_default(self):
        """${VAR:-default} syntax uses default when env var is not set."""
        cfg_data = dict(VALID_CONFIG)
        cfg_data["github"]["token"] = "${UNDEFINED_VAR:-fallback_token}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(cfg_data, f)
            path = f.name
        try:
            cfg = load_config(path)
            assert cfg.github.token == "fallback_token"
        finally:
            os.unlink(path)

    def test_env_var_with_default_falls_back_when_var_unset(self):
        """${VAR:-default} falls back to default when var is unset."""
        # Ensure var is not set
        os.environ.pop("MAYBE_TOKEN", None)
        cfg_data = dict(VALID_CONFIG)
        cfg_data["github"]["token"] = "${MAYBE_TOKEN:-default_key}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(cfg_data, f)
            path = f.name
        try:
            cfg = load_config(path)
            assert cfg.github.token == "default_key"
        finally:
            os.unlink(path)

    def test_env_var_with_default_uses_env_when_set(self):
        """${VAR:-default} uses env var when it IS set."""
        os.environ["MAYBE_TOKEN"] = "env_value"
        cfg_data = dict(VALID_CONFIG)
        cfg_data["github"]["token"] = "${MAYBE_TOKEN:-default_key}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(cfg_data, f)
            path = f.name
        try:
            cfg = load_config(path)
            assert cfg.github.token == "env_value"
        finally:
            os.unlink(path)
            del os.environ["MAYBE_TOKEN"]

    def test_loads_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")

    def test_embedding_defaults(self):
        """EmbeddingConfig uses defaults when not specified."""
        cfg = Config(
            accounts=["test"],
            github=GitHubConfig(token="test"),
        )
        assert cfg.embedding.model == "bge-m3:latest"
        assert cfg.embedding.base_url == "http://localhost:11434/v1"
        assert cfg.embedding.api_key == ""

    def test_embedding_override(self):
        """EmbeddingConfig fields can be overridden."""
        cfg = Config(
            accounts=["test"],
            github=GitHubConfig(token="test"),
            embedding=EmbeddingConfig(
                api_key="sk-test",
                model="custom-model",
                base_url="http://custom:11434/v1",
            ),
        )
        assert cfg.embedding.api_key == "sk-test"
        assert cfg.embedding.model == "custom-model"
        assert cfg.embedding.base_url == "http://custom:11434/v1"

    def test_env_var_substitution_preserves_no_match(self):
        """A ${...} pattern with no matching env var is kept as-is (no default syntax)."""
        cfg_data = dict(VALID_CONFIG)
        cfg_data["github"]["token"] = "${NONEXISTENT_VAR}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(cfg_data, f)
            path = f.name
        try:
            cfg = load_config(path)
            assert cfg.github.token == "${NONEXISTENT_VAR}"
        finally:
            os.unlink(path)


class TestConfigModel:
    def test_embedding_defaults_on_empty_config(self):
        """Config can be created without explicit embedding section."""
        cfg_data = dict(VALID_CONFIG)
        # Remove llm section but keep everything else valid
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(cfg_data, f)
            path = f.name
        try:
            cfg = load_config(path)
            assert cfg.embedding.model == "bge-m3:latest"
        finally:
            os.unlink(path)
