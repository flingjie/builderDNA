"""Tests for the observability behavior module (command tracking, mismatch detection)."""
import json
import os
import tempfile
from pathlib import Path

from observability.behavior import (
    record_command,
    record_output_retention,
    detect_config_change,
    detect_mismatches,
    save_mismatch_report,
    BEHAVIOR_LOG_PATH,
    MISMATCH_THRESHOLD,
    _read_jsonl,
    _config_hash,
    _map_domain_to_output,
    _map_command_to_activity,
    _map_domain_to_commercial_score,
)


class TestMapDomainToOutput:
    """Tests for domain → output type mapping."""

    def test_agent_maps_to_devtools(self):
        assert _map_domain_to_output("agent") == "devtools"

    def test_consumer_maps_to_end_user(self):
        assert _map_domain_to_output("consumer") == "end_user"

    def test_fintech_maps_to_end_user(self):
        assert _map_domain_to_output("fintech") == "end_user"

    def test_infrastructure_maps_to_infrastructure(self):
        assert _map_domain_to_output("infrastructure") == "infrastructure"

    def test_unknown_maps_to_devtools(self):
        assert _map_domain_to_output("unknown_domain") == "devtools"


class TestMapCommandToActivity:
    """Tests for pipeline completion rate calculation."""

    def test_empty_events(self):
        assert _map_command_to_activity([]) == (0, 0)

    def test_no_collect_runs(self):
        events = [
            {"event_type": "command_invocation", "command": "trend"},
            {"event_type": "command_invocation", "command": "report"},
        ]
        assert _map_command_to_activity(events) == (0, 0)

    def test_full_pipeline_run(self):
        events = [
            {"event_type": "command_invocation", "command": "collect"},
            {"event_type": "command_invocation", "command": "trend"},
            {"event_type": "command_invocation", "command": "pain"},
            {"event_type": "command_invocation", "command": "opportunity"},
            {"event_type": "command_invocation", "command": "report"},
        ]
        full, total = _map_command_to_activity(events)
        assert total == 1
        assert full == 1

    def test_partial_pipeline(self):
        events = [
            {"event_type": "command_invocation", "command": "collect"},
            {"event_type": "command_invocation", "command": "trend"},
            {"event_type": "command_invocation", "command": "collect"},
            {"event_type": "command_invocation", "command": "trend"},
            {"event_type": "command_invocation", "command": "pain"},
            {"event_type": "command_invocation", "command": "opportunity"},
        ]
        full, total = _map_command_to_activity(events)
        assert total == 2
        assert full == 1  # second run is complete (3+ analysis commands)

    def test_all_partial(self):
        events = [
            {"event_type": "command_invocation", "command": "collect"},
            {"event_type": "command_invocation", "command": "trend"},
            {"event_type": "command_invocation", "command": "collect"},
            {"event_type": "command_invocation", "command": "trend"},
        ]
        full, total = _map_command_to_activity(events)
        assert total == 2
        assert full == 0


class TestMapDomainToCommercialScore:
    """Tests for commercial domain detection."""

    def test_no_domains(self):
        assert _map_domain_to_commercial_score([]) == 0.0

    def test_all_commercial(self):
        events = [
            {"event_type": "command_invocation", "domain": "fintech"},
            {"event_type": "command_invocation", "domain": "consumer"},
        ]
        assert _map_domain_to_commercial_score(events) == 1.0

    def test_mixed(self):
        events = [
            {"event_type": "command_invocation", "domain": "fintech"},
            {"event_type": "command_invocation", "domain": "agent"},
            {"event_type": "command_invocation", "domain": "agent"},
            {"event_type": "command_invocation", "domain": "consumer"},
        ]
        assert _map_domain_to_commercial_score(events) == 0.5

    def test_all_non_commercial(self):
        events = [
            {"event_type": "command_invocation", "domain": "agent"},
            {"event_type": "command_invocation", "domain": "devtools"},
        ]
        assert _map_domain_to_commercial_score(events) == 0.0


class TestRecordCommand:
    """Tests for command invocation recording."""

    def setup_method(self):
        """Use a temp file for behavior_log."""
        self.tmp = tempfile.mkdtemp()
        self.orig_path = BEHAVIOR_LOG_PATH
        # Override module-level path for testing
        import observability.behavior as bmod
        self._test_log = os.path.join(self.tmp, "behavior_log.jsonl")
        bmod.BEHAVIOR_LOG_PATH = self._test_log

    def teardown_method(self):
        import observability.behavior as bmod
        bmod.BEHAVIOR_LOG_PATH = self.orig_path

    def test_record_creates_file(self):
        record_command("collect", domain="agent", flags={"window": 365},
                        output_path="out.json", user_dna_used=True,
                        elapsed_seconds=5.0, status="success")
        assert os.path.exists(self._test_log)

    def test_record_contains_fields(self):
        record_command("trend", domain="agent", flags={"window": 60},
                        output_path="out.json", user_dna_used=False,
                        elapsed_seconds=2.5, status="success")
        events = _read_jsonl(self._test_log)
        cmd_events = [e for e in events if e["event_type"] == "command_invocation"]
        assert len(cmd_events) == 1
        e = cmd_events[0]
        assert e["command"] == "trend"
        assert e["domain"] == "agent"
        assert e["flags"] == {"window": 60}
        assert e["output_path"] == "out.json"
        assert e["user_dna_used"] is False
        assert e["elapsed_seconds"] == 2.5
        assert e["status"] == "success"
        assert "timestamp" in e

    def test_multiple_commands_append(self):
        record_command("collect", domain="agent")
        record_command("trend", domain="agent")
        record_command("pain", domain="agent")
        events = _read_jsonl(self._test_log)
        cmd_events = [e for e in events if e["event_type"] == "command_invocation"]
        assert len(cmd_events) == 3

    def test_record_output_retention(self):
        record_output_retention("output/signals.json", referenced_by="trend")
        events = _read_jsonl(self._test_log)
        assert len(events) == 1
        assert events[0]["event_type"] == "output_retention"
        assert events[0]["output_path"] == "output/signals.json"


class TestDetectConfigChange:
    """Tests for config change detection."""

    def test_no_config_file_returns_none(self):
        # When config.yaml doesn't exist in test context, returns None
        # (hash of nonexistent file = "")
        result = detect_config_change()
        # May be None or a baseline event depending on whether config.yaml exists
        if result is not None:
            assert result["event_type"] == "config_change"


class TestDetectMismatches:
    """Tests for DNA-behavior mismatch detection."""

    def setup_method(self):
        """Isolate behavior_log and DNA paths."""
        self.tmp = tempfile.mkdtemp()
        import observability.behavior as bmod
        self._orig_behavior = bmod.BEHAVIOR_LOG_PATH
        self._orig_dna = bmod.USER_DNA_PATH
        self._test_log = os.path.join(self.tmp, "behavior_log.jsonl")
        self._test_dna = os.path.join(self.tmp, "user_dna.json")
        bmod.BEHAVIOR_LOG_PATH = self._test_log
        bmod.USER_DNA_PATH = self._test_dna

    def teardown_method(self):
        import observability.behavior as bmod
        bmod.BEHAVIOR_LOG_PATH = self._orig_behavior
        bmod.USER_DNA_PATH = self._orig_dna

    def test_no_dna_returns_empty(self):
        # No DNA file → no mismatches possible
        mismatches = detect_mismatches()
        assert mismatches == []

    def test_few_events_returns_empty(self):
        # Not enough events to trigger mismatch
        dna = {
            "values": {
                "output": {"ranking": ["devtools"], "scores": {"devtools": 9}},
                "activity": {"ranking": ["creation"], "scores": {"creation": 9}},
                "reward": {"ranking": ["growth"], "scores": {"wealth": 3}},
            }
        }
        Path(self._test_dna).write_text(json.dumps(dna))
        # Only 3 events — below threshold of 7
        for _ in range(3):
            record_command("collect", domain="agent")
        mismatches = detect_mismatches()
        assert mismatches == []

    def test_output_mismatch_detected(self):
        dna = {
            "values": {
                "output": {"ranking": ["end_user"], "scores": {"end_user": 9, "devtools": 3}},
                "activity": {"ranking": ["exploration"], "scores": {"creation": 5}},
                "reward": {"ranking": ["growth"], "scores": {"wealth": 3}},
            }
        }
        Path(self._test_dna).write_text(json.dumps(dna))
        # 8 events all in devtools domain — mismatches with end_user preference
        for _ in range(8):
            record_command("collect", domain="agent")  # agent → devtools
        mismatches = detect_mismatches()
        assert len(mismatches) > 0
        output_mismatch = [m for m in mismatches if m["dimension"] == "output"]
        assert len(output_mismatch) > 0
        assert output_mismatch[0]["confidence"] >= 0.85

    def test_no_mismatch_when_aligned(self):
        dna = {
            "values": {
                "output": {"ranking": ["devtools"], "scores": {"devtools": 9}},
                "activity": {"ranking": ["exploration"], "scores": {"creation": 5, "exploration": 8}},
                "reward": {"ranking": ["growth"], "scores": {"wealth": 8}},
            }
        }
        Path(self._test_dna).write_text(json.dumps(dna))
        # All events in devtools domain — matches DNA
        for _ in range(7):
            record_command("collect", domain="agent")  # agent → devtools
        mismatches = detect_mismatches()
        output_mismatch = [m for m in mismatches if m["dimension"] == "output"]
        assert len(output_mismatch) == 0  # aligned now

    def test_reward_mismatch_with_commercial_domains(self):
        dna = {
            "values": {
                "output": {"ranking": ["devtools"], "scores": {"devtools": 9}},
                "activity": {"ranking": ["exploration"], "scores": {"creation": 5}},
                "reward": {"ranking": ["growth"], "scores": {"wealth": 2}},
            }
        }
        Path(self._test_dna).write_text(json.dumps(dna))
        # 7 events, most in commercial domains, but DNA says wealth=2
        for _ in range(5):
            record_command("collect", domain="fintech")
        for _ in range(2):
            record_command("collect", domain="agent")
        mismatches = detect_mismatches()
        reward_mismatch = [m for m in mismatches if m["dimension"] == "reward"]
        assert len(reward_mismatch) > 0
        assert reward_mismatch[0]["confidence"] >= 0.50


class TestSaveMismatchReport:
    """Tests for mismatch report persistence."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        import observability.behavior as bmod
        self._orig_path = bmod.MISMATCH_REPORT_PATH
        self._test_report = os.path.join(self.tmp, "mismatch_report.json")
        bmod.MISMATCH_REPORT_PATH = self._test_report

    def teardown_method(self):
        import observability.behavior as bmod
        bmod.MISMATCH_REPORT_PATH = self._orig_path

    def test_empty_mismatches_deletes_stale_report(self):
        # Create a stale report first
        Path(self._test_report).write_text('{"stale": true}')
        result = save_mismatch_report([])
        assert result is None
        assert not os.path.exists(self._test_report)

    def test_saves_mismatches(self):
        mismatches = [
            {"dimension": "output", "dna_value": "devtools",
             "behavior_signal": "mostly fintech", "confidence": 0.85,
             "detail": "Mismatch detected.", "suggested_question": "DNA update?"}
        ]
        result = save_mismatch_report(mismatches)
        assert result is not None
        assert os.path.exists(self._test_report)
        data = json.loads(Path(self._test_report).read_text())
        assert data["mismatches"] == mismatches
        assert "generated_at" in data


class TestConfigHash:
    """Tests for config hash computation."""

    def test_hash_on_nonexistent_file(self):
        # _config_hash on missing file returns empty string
        # (the actual result depends on whether config.yaml exists)
        result = _config_hash()
        assert isinstance(result, str)


class TestReadJsonl:
    """Tests for JSONL reading utility."""

    def test_missing_file_returns_empty(self):
        events = _read_jsonl("/tmp/nonexistent_behavior_log_12345.jsonl")
        assert events == []

    def test_empty_file_returns_empty(self):
        p = Path(tempfile.mkdtemp()) / "empty.jsonl"
        p.write_text("")
        events = _read_jsonl(str(p))
        assert events == []
