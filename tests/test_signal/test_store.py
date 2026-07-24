"""Tests for SignalStore (SQLite-backed signal storage and aggregation)."""
import pytest
from datetime import datetime, timezone, timedelta
from signals.models import Signal
from signals.store import SignalStore


class TestSignalStore:
    def test_insert_and_query(self, tmp_path):
        store = SignalStore(str(tmp_path / "signal.db"))
        signals = [
            Signal(
                id=f"sig-{i}", source="github", type="star_growth",
                actor="dev", target_repo="org/repo",
                timestamp=datetime.now(timezone.utc) - timedelta(days=i),
                velocity=10.0 - i, impact=0.5,
                payload={"topics": ["agent"]},
            )
            for i in range(5)
        ]
        count = store.insert(signals)
        assert count == 5
        assert store.count() == 5

    def test_query_velocity(self, tmp_path):
        store = SignalStore(str(tmp_path / "velocity.db"))
        signals = [
            Signal(
                id=f"sig-{i}", source="github", type="star_growth",
                actor="dev", target_repo="org/repo",
                timestamp=datetime.now(timezone.utc) - timedelta(days=i),
                velocity=float(10 - i), impact=0.5,
            )
            for i in range(50)
        ]
        store.insert(signals)
        results = store.query_velocity(top_n=5, days=30)
        assert len(results) <= 5

    def test_get_topic_trends(self, tmp_path):
        store = SignalStore(str(tmp_path / "topics.db"))
        signals = [
            Signal(
                id=f"sig-{i}", source="github", type="repo_created",
                actor="dev", target_repo=f"org/repo{i}",
                timestamp=datetime.now(timezone.utc),
                velocity=5.0,
                payload={"topics": ["agent", "mcp"]},
            )
            for i in range(10)
        ]
        store.insert(signals)
        trends = store.get_topic_trends(days=30)
        assert len(trends) >= 1

    def test_empty_store(self, tmp_path):
        store = SignalStore(str(tmp_path / "empty.db"))
        assert store.count() == 0
        assert store.query_velocity(5, 30) == []
