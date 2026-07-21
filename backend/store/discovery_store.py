"""SQLite store for discovery snapshots."""
import json
from pathlib import Path

from backend.models.discovery import DiscoverySnapshot


class DiscoveryStore:
    """SQLite-backed store for DiscoverySnapshot objects."""

    def __init__(self, db_path: str = "snapshots/discovery.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS discovery_snapshots (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    window_days INTEGER NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_discovery_domain
                ON discovery_snapshots(domain, created_at DESC)
            """)
            conn.commit()

    def save(self, snapshot: DiscoverySnapshot) -> str:
        import sqlite3
        data_json = snapshot.model_dump_json(indent=2)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO discovery_snapshots (id, domain, created_at, window_days, data_json) VALUES (?, ?, ?, ?, ?)",
                (snapshot.id, snapshot.domain, snapshot.created_at.isoformat(),
                 snapshot.window_days, data_json),
            )
            conn.commit()
        return snapshot.id

    def get_latest(self, domain: str) -> DiscoverySnapshot | None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM discovery_snapshots WHERE domain = ? ORDER BY created_at DESC LIMIT 1",
                (domain,),
            ).fetchone()
            if row is None:
                return None
            return DiscoverySnapshot(**json.loads(row["data_json"]))

    def get_all(self, domain: str) -> list[DiscoverySnapshot]:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM discovery_snapshots WHERE domain = ? ORDER BY created_at DESC",
                (domain,),
            ).fetchall()
            return [DiscoverySnapshot(**json.loads(r["data_json"])) for r in rows]
