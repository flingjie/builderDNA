"""SQLite store for trend snapshots."""
import json
from pathlib import Path

from backend.models.trend import TrendSnapshot


class TrendStore:
    """SQLite-backed store for TrendSnapshot objects."""

    def __init__(self, db_path: str = "snapshots/trends.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trend_snapshots (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    window_days INTEGER NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trend_domain
                ON trend_snapshots(domain, created_at DESC)
            """)
            conn.commit()

    def save(self, snapshot: TrendSnapshot) -> str:
        import sqlite3
        data_json = snapshot.model_dump_json(indent=2)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO trend_snapshots (id, domain, created_at, window_days, data_json) VALUES (?, ?, ?, ?, ?)",
                (snapshot.id, snapshot.domain, snapshot.created_at.isoformat(),
                 snapshot.window_days, data_json),
            )
            conn.commit()
        return snapshot.id

    def get_latest(self, domain: str) -> TrendSnapshot | None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM trend_snapshots WHERE domain = ? ORDER BY created_at DESC LIMIT 1",
                (domain,),
            ).fetchone()
            if row is None:
                return None
            return TrendSnapshot(**json.loads(row["data_json"]))

    def get_all(self, domain: str) -> list[TrendSnapshot]:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trend_snapshots WHERE domain = ? ORDER BY created_at DESC",
                (domain,),
            ).fetchall()
            return [TrendSnapshot(**json.loads(r["data_json"])) for r in rows]
