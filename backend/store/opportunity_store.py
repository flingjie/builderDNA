"""SQLite store for opportunity snapshots."""
import json
from pathlib import Path

from backend.models.opportunity import OpportunitySnapshot


class OpportunityStore:
    """SQLite-backed store for OpportunitySnapshot objects."""

    def __init__(self, db_path: str = "snapshots/opportunities.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opportunity_snapshots (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_opportunity_domain
                ON opportunity_snapshots(domain, created_at DESC)
            """)
            conn.commit()

    def save(self, snapshot: OpportunitySnapshot) -> str:
        import sqlite3
        data_json = snapshot.model_dump_json(indent=2)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO opportunity_snapshots (id, domain, created_at, data_json) VALUES (?, ?, ?, ?)",
                (snapshot.id, snapshot.domain, snapshot.created_at.isoformat(), data_json),
            )
            conn.commit()
        return snapshot.id

    def get_latest(self, domain: str) -> OpportunitySnapshot | None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM opportunity_snapshots WHERE domain = ? ORDER BY created_at DESC LIMIT 1",
                (domain,),
            ).fetchone()
            if row is None:
                return None
            return OpportunitySnapshot(**json.loads(row["data_json"]))
