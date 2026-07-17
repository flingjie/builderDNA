"""Signal Store — SQLite persistence for signals, clusters, insights, and opportunities.

Manages the snapshots/ directory, including schema creation, CRUD operations,
and snapshot metadata for incremental comparison.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.signal import Signal


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    created_at TEXT,
    accounts TEXT,
    signal_count INTEGER DEFAULT 0,
    insight_count INTEGER DEFAULT 0,
    opportunity_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    source TEXT,
    type TEXT,
    timestamp TEXT,
    weight REAL,
    actor TEXT,
    target TEXT,
    meta TEXT,
    raw TEXT,
    snapshot_id TEXT REFERENCES snapshots(id)
);

CREATE TABLE IF NOT EXISTS signal_clusters (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(id),
    topics TEXT,
    languages TEXT,
    total_weight REAL,
    time_span_days INTEGER,
    growth_rate REAL
);

CREATE TABLE IF NOT EXISTS insights (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(id),
    tags TEXT,
    summary TEXT,
    strength REAL,
    trend TEXT,
    signal_count INTEGER,
    evidence TEXT
);

CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(id),
    title TEXT,
    pain_point TEXT,
    demand_score REAL,
    competition_score REAL,
    gap_score REAL,
    recommended_action TEXT,
    source_insights TEXT
);
"""


class SignalStore:
    """SQLite-backed store for all BuilderDNA data."""

    def __init__(self, db_path: str | Path):
        """Initialize the store and create tables if needed.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create schema if not exists."""
        import sqlite3

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def create_snapshot(self, accounts: list[str]) -> str:
        """Create a new snapshot record."""
        sid = str(uuid.uuid4())[:8]
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO snapshots (id, created_at, accounts) VALUES (?, ?, ?)",
                (sid, datetime.now(timezone.utc).isoformat(), json.dumps(accounts)),
            )
            conn.commit()
        return sid

    def get_last_snapshot(self) -> dict | None:
        """Get the most recent snapshot."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        """Get a snapshot by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_snapshots(self) -> list[dict]:
        """List all snapshots ordered by creation time."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshots ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def insert_signals(self, signals: list[Signal], snapshot_id: str) -> int:
        """Insert signals, skipping duplicates by ID."""
        count = 0
        with self._get_conn() as conn:
            for s in signals:
                try:
                    conn.execute(
                        """INSERT INTO signals (id, source, type, timestamp, weight,
                           actor, target, meta, raw, snapshot_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            s.id, s.source, s.type, s.timestamp.isoformat(),
                            s.weight, s.actor, s.target,
                            json.dumps(s.meta), json.dumps(s.raw), snapshot_id,
                        ),
                    )
                    count += 1
                except Exception:
                    pass
            conn.execute(
                "UPDATE snapshots SET signal_count = signal_count + ? WHERE id = ?",
                (count, snapshot_id),
            )
            conn.commit()
        return count

    def get_signals_by_actor(self, actor: str) -> list[Signal]:
        """Get all signals for a specific actor."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE actor = ? ORDER BY timestamp DESC",
                (actor,),
            ).fetchall()
            return [self._row_to_signal(dict(r)) for r in rows]

    def get_all_signals(self) -> list[Signal]:
        """Get all signals in the store."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY timestamp DESC"
            ).fetchall()
            return [self._row_to_signal(dict(r)) for r in rows]

    def get_signals_since(self, since: str) -> list[Signal]:
        """Get signals created after a given ISO timestamp."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE timestamp > ? ORDER BY timestamp DESC",
                (since,),
            ).fetchall()
            return [self._row_to_signal(dict(r)) for r in rows]

    @staticmethod
    def _row_to_signal(row: dict) -> Signal:
        """Convert a DB row dict to a Signal object."""
        return Signal(
            id=row["id"], source=row["source"], type=row["type"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            weight=row["weight"], actor=row["actor"], target=row["target"],
            meta=json.loads(row["meta"]) if row["meta"] else {},
            raw=json.loads(row["raw"]) if row["raw"] else {},
        )

    def insert_signal_clusters(self, clusters: list[dict[str, Any]], snapshot_id: str) -> None:
        """Insert signal clusters for a snapshot (replaces existing)."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM signal_clusters WHERE snapshot_id = ?", (snapshot_id,))
            for c in clusters:
                conn.execute(
                    """INSERT INTO signal_clusters
                       (id, snapshot_id, topics, languages, total_weight, time_span_days, growth_rate)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (c["id"], snapshot_id, json.dumps(c["topics"]), json.dumps(c["languages"]),
                     c["total_weight"], c["time_span_days"], c["growth_rate"]),
                )
            conn.commit()

    def get_signal_clusters(self, snapshot_id: str) -> list[dict]:
        """Get all signal clusters for a snapshot."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM signal_clusters WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchall()
            return [{
                "id": r["id"], "topics": json.loads(r["topics"]),
                "languages": json.loads(r["languages"]), "total_weight": r["total_weight"],
                "time_span_days": r["time_span_days"], "growth_rate": r["growth_rate"],
            } for r in rows]

    def insert_insights(self, insights: list[dict[str, Any]], snapshot_id: str) -> None:
        """Insert insights for a snapshot."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM insights WHERE snapshot_id = ?", (snapshot_id,))
            for i in insights:
                conn.execute(
                    """INSERT INTO insights
                       (id, snapshot_id, tags, summary, strength, trend, signal_count, evidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (i["id"], snapshot_id, json.dumps(i["tags"]), i["summary"],
                     i["strength"], i["trend"], i["signal_count"], json.dumps(i["evidence"])),
                )
            conn.execute(
                "UPDATE snapshots SET insight_count = ? WHERE id = ?",
                (len(insights), snapshot_id),
            )
            conn.commit()

    def get_insights(self, snapshot_id: str) -> list[dict]:
        """Get all insights for a snapshot."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM insights WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchall()
            return [{
                "id": r["id"], "tags": json.loads(r["tags"]), "summary": r["summary"],
                "strength": r["strength"], "trend": r["trend"],
                "signal_count": r["signal_count"], "evidence": json.loads(r["evidence"]),
            } for r in rows]

    def insert_opportunities(self, opportunities: list[dict[str, Any]], snapshot_id: str) -> None:
        """Insert opportunities for a snapshot."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM opportunities WHERE snapshot_id = ?", (snapshot_id,))
            for o in opportunities:
                conn.execute(
                    """INSERT INTO opportunities
                       (id, snapshot_id, title, pain_point, demand_score,
                        competition_score, gap_score, recommended_action, source_insights)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (o["id"], snapshot_id, o["title"], o["pain_point"],
                     o["demand_score"], o["competition_score"], o["gap_score"],
                     o["recommended_action"], json.dumps(o["source_insights"])),
                )
            conn.execute(
                "UPDATE snapshots SET opportunity_count = ? WHERE id = ?",
                (len(opportunities), snapshot_id),
            )
            conn.commit()

    def get_opportunities(self, snapshot_id: str) -> list[dict]:
        """Get all opportunities for a snapshot."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM opportunities WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchall()
            return [{
                "id": r["id"], "title": r["title"], "pain_point": r["pain_point"],
                "demand_score": r["demand_score"], "competition_score": r["competition_score"],
                "gap_score": r["gap_score"], "recommended_action": r["recommended_action"],
                "source_insights": json.loads(r["source_insights"]),
            } for r in rows]
