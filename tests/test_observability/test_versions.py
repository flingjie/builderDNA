"""Tests for algorithm/weight versioning (P8)."""

from observability.versions import (
    ALGORITHM_VERSIONS,
    algorithm_version,
    record_algorithm_change,
    read_algorithm_changes,
)


class TestAlgorithmVersion:
    def test_known_component_has_version(self):
        assert algorithm_version("trend") == ALGORITHM_VERSIONS["trend"]
        assert algorithm_version("opportunity")

    def test_unknown_component_is_empty(self):
        assert algorithm_version("nope") == ""


class TestRecordAlgorithmChange:
    def test_records_and_updates_registry(self, tmp_path, monkeypatch):
        import observability.versions as v
        monkeypatch.setattr(v, "CHANGE_LOG_PATH", str(tmp_path / "changes.jsonl"))

        entry = record_algorithm_change(
            "trend", "1.1", "wider window → more samples",
            reason="tune window default",
        )
        assert entry["old_version"] == "1.0"
        assert entry["new_version"] == "1.1"
        assert algorithm_version("trend") == "1.1"

        # Registry update is persisted in-memory only; log is on disk.
        logged = read_algorithm_changes("trend")
        assert len(logged) == 1
        assert logged[0]["component"] == "trend"
        assert logged[0]["expected_impact"] == "wider window → more samples"

    def test_read_filters_by_component(self, tmp_path, monkeypatch):
        import observability.versions as v
        monkeypatch.setattr(v, "CHANGE_LOG_PATH", str(tmp_path / "changes.jsonl"))

        record_algorithm_change("trend", "1.1", "a")
        record_algorithm_change("pain", "1.1", "b")

        assert len(read_algorithm_changes()) == 2
        assert len(read_algorithm_changes("trend")) == 1
        assert len(read_algorithm_changes("pain")) == 1
        assert len(read_algorithm_changes("nope")) == 0

    def test_read_missing_log_is_empty(self, tmp_path, monkeypatch):
        import observability.versions as v
        monkeypatch.setattr(v, "CHANGE_LOG_PATH", str(tmp_path / "none.jsonl"))
        assert read_algorithm_changes() == []
