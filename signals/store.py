"""SignalStore -- SQLite-backed signal persistence and aggregation.

Stores normalized Signal events and provides analytical queries
(topic trends, velocity) that return canonical payload types.

DuckDB integration is planned for future scale, but currently
SQLite handles both transactional and analytical workloads.
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from signals.models import Signal
from models.payload import TopicTrend


class SignalStore:
    """SQLite-backed signal storage with analytical query methods."""

    def __init__(self, db_path: str = "snapshots/signals.db"):
        import sqlite3

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._closed = False
        self._init_db()

    def __enter__(self) -> "SignalStore":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                type TEXT NOT NULL,
                actor TEXT NOT NULL,
                target_repo TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                velocity REAL DEFAULT 0,
                impact REAL DEFAULT 0,
                payload_json TEXT DEFAULT '{}'
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_timestamp
            ON signals(timestamp DESC)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(type)
        """)
        self._conn.commit()

    def insert(self, signals: list[Signal]) -> int:
        rows = [
            (s.id, s.source, s.type, s.actor, s.target_repo,
             s.timestamp.isoformat(), s.velocity, s.impact,
             json.dumps(s.payload))
            for s in signals
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO signals (id, source, type, actor, target_repo, timestamp, velocity, impact, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]

    def query_velocity(self, top_n: int = 10, days: int = 30) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self._conn.execute(
            "SELECT target_repo, AVG(velocity) as avg_v, COUNT(*) as cnt FROM signals WHERE timestamp >= ? AND velocity > 0 GROUP BY target_repo ORDER BY avg_v DESC LIMIT ?",
            (since, top_n),
        ).fetchall()
        return [{"target_repo": r["target_repo"], "avg_velocity": round(r["avg_v"], 2), "count": r["cnt"]} for r in rows]

    def get_topic_trends(self, days: int = 30) -> list[TopicTrend]:
        """Compute topic-level trend aggregations from the signal table.

        Returns canonical TopicTrend objects (acceleration and top_repos
        are left at defaults — callers enrich them as needed).
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self._conn.execute(
            "SELECT payload_json, velocity FROM signals WHERE timestamp >= ?",
            (since,),
        ).fetchall()

        topic_velocities: dict[str, list[float]] = {}
        for row in rows:
            payload = json.loads(row["payload_json"])
            velocity = row["velocity"]
            for topic in payload.get("topics", []):
                topic_velocities.setdefault(topic, []).append(velocity)

        results = []
        for topic, velocities in topic_velocities.items():
            valid = [v for v in velocities if v > 0]
            avg_v = sum(valid) / len(valid) if valid else 0.0
            results.append(TopicTrend(
                topic=topic,
                stage="emerging",
                confidence=min(1.0, len(velocities) / 10.0),
                growth_velocity=round(avg_v, 2),
                acceleration=0.0,
                evidence_count=len(velocities),
            ))
        results.sort(key=lambda t: t.growth_velocity, reverse=True)
        return results

    def close(self) -> None:
        if not self._closed:
            self._conn.close()
            self._closed = True
