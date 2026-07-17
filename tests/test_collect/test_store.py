"""Tests for SignalStore."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from models.signal import Signal
from collect.store import SignalStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        s = SignalStore(db_path)
        yield s


@pytest.fixture
def sample_signals():
    return [
        Signal(
            id="gh_repo_alice_toolkit", source="github", type="repo",
            timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc), weight=5.0,
            actor="alice", target="alice/toolkit",
            meta={"language": "Python", "topics": ["llm"]}, raw={"id": 1},
        ),
        Signal(
            id="gh_star_200", source="github", type="star",
            timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc), weight=1.0,
            actor="alice", target="fastapi/fastapi",
            meta={"language": "Python", "topics": ["web"]}, raw={"id": 200},
        ),
    ]


class TestSignalStore:
    def test_insert_and_retrieve_signals(self, store, sample_signals):
        sid = store.create_snapshot(["alice"])
        store.insert_signals(sample_signals, sid)
        all_sigs = store.get_all_signals()
        assert len(all_sigs) == 2

    def test_get_signals_by_actor(self, store, sample_signals):
        sid = store.create_snapshot(["alice"])
        store.insert_signals(sample_signals, sid)
        result = store.get_signals_by_actor("alice")
        assert len(result) == 2

    def test_insert_dedup_by_id(self, store, sample_signals):
        sid = store.create_snapshot(["alice"])
        store.insert_signals(sample_signals, sid)
        store.insert_signals(sample_signals, sid)
        assert len(store.get_all_signals()) == 2

    def test_snapshot_lifecycle(self, store, sample_signals):
        sid = store.create_snapshot(["alice", "bob"])
        store.insert_signals(sample_signals, sid)
        snap = store.get_snapshot(sid)
        assert snap is not None
        assert snap["signal_count"] == 2
        assert store.get_last_snapshot()["id"] == sid

    def test_list_snapshots(self, store, sample_signals):
        sid1 = store.create_snapshot(["alice"])
        sid2 = store.create_snapshot(["alice"])
        store.insert_signals(sample_signals, sid1)
        assert len(store.list_snapshots()) == 2

    def test_insert_clusters_insights_opportunities(self, store, sample_signals):
        sid = store.create_snapshot(["alice"])
        store.insert_signals(sample_signals, sid)

        store.insert_signal_clusters([
            {"id": "cl_001", "topics": ["llm"], "languages": ["Python"],
             "total_weight": 5.0, "time_span_days": 30, "growth_rate": 0.5}
        ], sid)
        store.insert_insights([
            {"id": "in_001", "tags": ["LLM"], "summary": "LLM focus",
             "strength": 5.0, "trend": "rising", "signal_count": 1, "evidence": ["alice/toolkit"]}
        ], sid)
        store.insert_opportunities([
            {"id": "op_001", "title": "Agent Tool", "pain_point": "Testing",
             "demand_score": 4.0, "competition_score": 2.0, "gap_score": 2.0,
             "recommended_action": "Build", "source_insights": ["in_001"]}
        ], sid)

        assert len(store.get_signal_clusters(sid)) == 1
        assert len(store.get_insights(sid)) == 1
        assert len(store.get_opportunities(sid)) == 1
