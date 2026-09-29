"""Tests for the investigate CLI command group (via Typer CliRunner)."""
import json

import pytest
from typer.testing import CliRunner

from cli.commands.investigate import investigate

runner = CliRunner()


def test_init_prints_json(tmp_path):
    result = runner.invoke(investigate, ["init", "--topic", "agent reliability", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["investigation"]["id"] == "inv_1"


def test_init_requires_topic(tmp_path):
    result = runner.invoke(investigate, ["init", "--state-dir", str(tmp_path)])
    assert result.exit_code == 2  # validation error


def test_run_action_round_trip(tmp_path):
    runner.invoke(investigate, ["init", "--topic", "agent reliability", "--state-dir", str(tmp_path)])
    result = runner.invoke(
        investigate,
        ["run", "--id", "inv_1", "--action", "ask_user", "--reason", "fork to user", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["status"] == "completed"
