"""SignalStore -- SQLite for transactions + DuckDB for analytics.

SQLite stores snapshot metadata and signal blobs (existing pattern).
DuckDB provides time-series analytics queries (velocity, topic trends).
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from signals.models import Signal, AggregateTopicTrend


class SignalStore:
    """Dual-engine signal storage.

    SQLite: transactional -- snapshots, feedback, audit log.
    DuckDB: analytical -- time series, aggregations, trending queries.
    """

    def __init__(self, db_path: str = "snapshots/signals.db"):
        import sqlite3

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

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

    def get_topic_trends(self, days: int = 30) -> list[AggregateTopicTrend]:
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
            results.append(AggregateTopicTrend(
                topic=topic,
                confidence=min(1.0, len(velocities) / 10.0),
                growth_velocity=round(avg_v, 2),
                evidence_count=len(velocities),
            ))
        results.sort(key=lambda t: t.growth_velocity, reverse=True)
        return results

    def close(self) -> None:
        self._conn.close()
