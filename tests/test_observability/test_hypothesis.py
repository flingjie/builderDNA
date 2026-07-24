"""Tests for the observability hypothesis module (hypothesis tree lifecycle)."""
import json
import os
import tempfile
from pathlib import Path

from observability.hypothesis import (
    HypothesisManager,
    HYPOTHESES_PATH,
    _days_ago,
    _generate_id,
)


class TestDaysAgo:
    """Tests for date calculation utility."""

    def test_empty_string_is_infinite(self):
        assert _days_ago("") == float("inf")

    def test_valid_date_positive(self):
        # A date far in the past
        days = _days_ago("2020-01-01T00:00:00+00:00")
        assert days > 1000

    def test_future_date(self):
        days = _days_ago("2099-01-01T00:00:00+00:00")
        assert days < 0  # future date returns negative

    def test_invalid_date_returns_inf(self):
        assert _days_ago("not-a-date") == float("inf")


class TestGenerateId:
    """Tests for hypothesis ID generation."""

    def test_empty_nodes(self):
        assert _generate_id([]) == "hyp_001"

    def test_sequential(self):
        nodes = [{"id": "hyp_001"}, {"id": "hyp_002"}]
        assert _generate_id(nodes) == "hyp_003"

    def test_gap_in_sequence(self):
        nodes = [{"id": "hyp_001"}, {"id": "hyp_005"}]
        assert _generate_id(nodes) == "hyp_006"

    def test_mixed_ids(self):
        nodes = [{"id": "hyp_001"}, {"id": "something_else"}]
        assert _generate_id(nodes) == "hyp_002"


class TestHypothesisManager:
    """Tests for hypothesis CRUD and lifecycle."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.test_path = os.path.join(self.tmp, "hypotheses.json")
        self.hm = HypothesisManager(path=self.test_path)

    def test_empty_manager_reads_skeleton(self):
        nodes = self.hm.get_all()
        assert nodes == []

    def test_add_creates_node(self):
        node_id = self.hm.add(
            "Agent State Engine market opportunity",
            domain="agent",
            source="opportunity analysis — gap_score=2.3",
            confidence=0.65,
        )
        assert node_id.startswith("hyp_")
        nodes = self.hm.get_all()
        assert len(nodes) == 1
        assert nodes[0]["title"] == "Agent State Engine market opportunity"
        assert nodes[0]["domain"] == "agent"
        assert nodes[0]["status"] == "exploring"
        assert nodes[0]["confidence"] == 0.65
        assert nodes[0]["source"] == "opportunity analysis — gap_score=2.3"
        assert "created_at" in nodes[0]
        assert "updated_at" in nodes[0]
        assert "evidence_log" in nodes[0]

    def test_add_multiple_nodes(self):
        self.hm.add("H1", domain="agent", source="test", confidence=0.5)
        self.hm.add("H2", domain="agent", source="test", confidence=0.7)
        self.hm.add("H3", domain="devtools", source="test", confidence=0.9)
        nodes = self.hm.get_all()
        assert len(nodes) == 3
        ids = [n["id"] for n in nodes]
        assert ids == ["hyp_001", "hyp_002", "hyp_003"]

    def test_get_returns_node(self):
        node_id = self.hm.add("test", domain="agent", source="test")
        node = self.hm.get(node_id)
        assert node is not None
        assert node["title"] == "test"

    def test_get_nonexistent(self):
        assert self.hm.get("hyp_999") is None

    def test_update_status(self):
        node_id = self.hm.add("test", domain="agent", source="test", confidence=0.5)
        assert self.hm.update_status(node_id, "validated", confidence=0.9)
        node = self.hm.get(node_id)
        assert node["status"] == "validated"
        assert node["confidence"] == 0.9

    def test_update_status_nonexistent(self):
        assert not self.hm.update_status("hyp_999", "validated")

    def test_add_evidence(self):
        node_id = self.hm.add("test", domain="agent", source="test")
        assert self.hm.add_evidence(node_id, "supporting",
                                     "collect → 3 new repos")
        node = self.hm.get(node_id)
        assert len(node["evidence_log"]) == 1
        assert node["evidence_log"][0]["type"] == "supporting"

    def test_add_evidence_nonexistent(self):
        assert not self.hm.add_evidence("hyp_999", "supporting", "nah")

    def test_multiple_evidence_entries(self):
        node_id = self.hm.add("test", domain="agent", source="test")
        self.hm.add_evidence(node_id, "supporting", "good signal 1")
        self.hm.add_evidence(node_id, "supporting", "good signal 2")
        self.hm.add_evidence(node_id, "contradicting", "bad signal")
        node = self.hm.get(node_id)
        assert len(node["evidence_log"]) == 3


class TestHypothesisPruning:
    """Tests for pruning detection logic."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.test_path = os.path.join(self.tmp, "hypotheses.json")
        self.hm = HypothesisManager(path=self.test_path)

    def test_no_pruning_for_fresh_exploring(self):
        node_id = self.hm.add("fresh", domain="agent", source="test")
        proposal = self.hm.check_pruning(node_id)
        assert proposal is None

    def test_pruning_from_contradicting_evidence(self):
        node_id = self.hm.add("doomed", domain="agent", source="test")
        # Add 3 contradicting entries in a row
        self.hm.add_evidence(node_id, "contradicting", "negative 1")
        self.hm.add_evidence(node_id, "contradicting", "negative 2")
        self.hm.add_evidence(node_id, "contradicting", "negative 3")
        proposal = self.hm.check_pruning(node_id)
        assert proposal is not None
        assert proposal["reason"] == "evidence_contradiction"
        assert proposal["severity"] == "high"

    def test_no_pruning_with_mixed_evidence(self):
        node_id = self.hm.add("mixed", domain="agent", source="test")
        self.hm.add_evidence(node_id, "contradicting", "bad 1")
        self.hm.add_evidence(node_id, "supporting", "good 1")
        self.hm.add_evidence(node_id, "supporting", "good 2")
        proposal = self.hm.check_pruning(node_id)
        # 2 supporting, 1 contradicting → only 1 contradict in last 3 → < threshold 2
        assert proposal is None

    def test_already_pruned_returns_none(self):
        node_id = self.hm.add("done", domain="agent", source="test")
        self.hm.update_status(node_id, "pruned")
        proposal = self.hm.check_pruning(node_id)
        assert proposal is None

    def test_check_all_pruning(self):
        self.hm.add("h1", domain="agent", source="test")
        n2 = self.hm.add("h2", domain="agent", source="test")
        # Make h2 have contradicting evidence
        self.hm.add_evidence(n2, "contradicting", "no 1")
        self.hm.add_evidence(n2, "contradicting", "no 2")
        self.hm.add_evidence(n2, "contradicting", "no 3")
        proposals = self.hm.check_all_pruning()
        assert len(proposals) == 1
        assert proposals[0]["node_id"] == n2


class TestHypothesisSummary:
    """Tests for session-start summary generation."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.test_path = os.path.join(self.tmp, "hypotheses.json")
        self.hm = HypothesisManager(path=self.test_path)

    def test_empty_summary(self):
        summary = self.hm.get_summary()
        assert summary["total"] == 0
        assert summary["summary_line"] == ""
        assert summary["exploring"] == 0

    def test_summary_with_exploring_nodes(self):
        self.hm.add("H1", domain="agent", source="test", confidence=0.5)
        self.hm.add("H2", domain="agent", source="test", confidence=0.7)
        summary = self.hm.get_summary()
        assert summary["total"] == 2
        assert summary["exploring"] == 2
        assert "exploring" in summary["summary_line"]

    def test_ready_to_validate_detected(self):
        self.hm.add("H1", domain="agent", source="test", confidence=0.85)
        self.hm.add("H2", domain="agent", source="test", confidence=0.5)
        summary = self.hm.get_summary()
        assert len(summary["ready_to_validate"]) == 1
        assert summary["ready_to_validate"][0]["confidence"] == 0.85

    def test_mixed_status_summary(self):
        n1 = self.hm.add("H1", domain="agent", source="test")
        n2 = self.hm.add("H2", domain="agent", source="test")
        self.hm.update_status(n1, "validated", confidence=0.9)
        summary = self.hm.get_summary()
        assert summary["exploring"] == 1
        assert summary["validated"] == 1

    def test_summary_includes_pruning(self):
        n1 = self.hm.add("doomed", domain="agent", source="test")
        self.hm.add_evidence(n1, "contradicting", "bad")
        self.hm.add_evidence(n1, "contradicting", "bad")
        self.hm.add_evidence(n1, "contradicting", "bad")
        summary = self.hm.get_summary()
        assert summary["pending_prune_count"] == 1
        assert "prune" in summary["summary_line"].lower()


class TestHypothesisPersistence:
    """Tests for file round-trip integrity."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.test_path = os.path.join(self.tmp, "hypotheses.json")
        self.hm = HypothesisManager(path=self.test_path)

    def test_data_survives_round_trip(self):
        node_id = self.hm.add("round trip test", domain="agent",
                               source="test source", confidence=0.75)
        self.hm.add_evidence(node_id, "supporting", "evidence 1")
        self.hm.update_status(node_id, "validated", confidence=0.9)

        # Re-read from file
        hm2 = HypothesisManager(path=self.test_path)
        node = hm2.get(node_id)
        assert node is not None
        assert node["title"] == "round trip test"
        assert node["status"] == "validated"
        assert node["confidence"] == 0.9
        assert len(node["evidence_log"]) == 1

    def test_corrupted_file_handled(self):
        Path(self.test_path).write_text("not valid json {{{")
        hm2 = HypothesisManager(path=self.test_path)
        nodes = hm2.get_all()
        assert nodes == []  # returns empty on corruption
