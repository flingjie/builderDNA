"""SQLite store for vendor snapshots."""
import json
from pathlib import Path

from backend.models.vendor import VendorSnapshot, VendorProfile


class VendorStore:
    """SQLite-backed store for VendorSnapshot objects."""

    def __init__(self, db_path: str = "snapshots/vendor.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vendor_snapshots (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    window_days INTEGER NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vendor_domain
                ON vendor_snapshots(domain, created_at DESC)
            """)
            conn.commit()

    def save(self, snapshot: VendorSnapshot) -> str:
        import sqlite3
        data_json = snapshot.model_dump_json(indent=2)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO vendor_snapshots (id, domain, created_at, window_days, data_json) VALUES (?, ?, ?, ?, ?)",
                (snapshot.id, snapshot.domain, snapshot.created_at.isoformat(),
                 snapshot.window_days, data_json),
            )
            conn.commit()
        return snapshot.id

    def get_latest(self, domain: str) -> VendorSnapshot | None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM vendor_snapshots WHERE domain = ? ORDER BY created_at DESC LIMIT 1",
                (domain,),
            ).fetchone()
            if row is None:
                return None
            return VendorSnapshot(**json.loads(row["data_json"]))

    def get_all(self, domain: str) -> list[VendorSnapshot]:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM vendor_snapshots WHERE domain = ? ORDER BY created_at DESC",
                (domain,),
            ).fetchall()
            return [VendorSnapshot(**json.loads(r["data_json"])) for r in rows]

    def get_profiles_by_group(self, group: str) -> list[VendorProfile]:
        """Get profiles from the latest snapshot filtered by comparison_group."""
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM vendor_snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return []
            snapshot = VendorSnapshot(**json.loads(row["data_json"]))
            return [p for p in snapshot.profiles if p.comparison_group == group]
