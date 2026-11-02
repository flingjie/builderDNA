"""Tests for the slimmed config system (output section + env substitution)."""

import os

import pytest

from config import Config, OutputConfig, load_config


def test_load_minimal_config(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  dir: ./output\n  formats:\n    - json\n")
    cfg = load_config(cfg_file)
    assert isinstance(cfg, Config)
    assert cfg.output.dir == "./output"
    assert cfg.output.formats == ["json"]


def test_defaults_when_empty_sections(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("{}\n")
    cfg = load_config(cfg_file)
    assert cfg.output == OutputConfig()


def test_env_substitution_with_default(tmp_path, monkeypatch):
    monkeypatch.delenv("BDNA_TEST_DIR", raising=False)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  dir: ${BDNA_TEST_DIR:-./fallback}\n")
    cfg = load_config(cfg_file)
    assert cfg.output.dir == "./fallback"


def test_env_substitution_from_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("BDNA_TEST_DIR", "/tmp/bdna")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  dir: ${BDNA_TEST_DIR}\n")
    cfg = load_config(cfg_file)
    assert cfg.output.dir == "/tmp/bdna"


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent/config.yaml")
