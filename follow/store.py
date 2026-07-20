"""Follow snapshot store — persists follow evaluation results for trend tracking."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from follow.scorer import GroupResult, AccountScore


class FollowStore:
    """SQLite store for follow evaluation snapshots.

    Each snapshot records the grouped scoring results so trend analysis
    can compare current vs previous.
    """

    def __init__(self, db_path: str | Path = "snapshots/follow.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS follow_snapshots (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)

    def save(self, groups: list[GroupResult]) -> str:
        """Save a snapshot of group results.

        Returns:
            The snapshot ID.
        """
        snap_id = uuid4().hex[:8]
        created_at = datetime.now(timezone.utc).isoformat()
        data = {
            "groups": {
                g.group_name: {a.actor: a.composite for a in g.accounts}
                for g in groups
            }
        }
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO follow_snapshots (id, created_at, data_json) VALUES (?, ?, ?)",
                (snap_id, created_at, json.dumps(data)),
            )
        return snap_id

    def get_last(self) -> dict[str, dict[str, float]] | None:
        """Get the most recent snapshot's group data.

        Returns:
            {group_name: {actor: composite_score}} or None.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT data_json FROM follow_snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            data = json.loads(row[0])
            return data.get("groups", {})

    def list_snapshots(self) -> list[dict]:
        """List all snapshots."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT id, created_at FROM follow_snapshots ORDER BY created_at DESC"
            ).fetchall()
            return [{"id": r[0], "created_at": r[1]} for r in rows]

    def get_previous(self, current_snap_id: str) -> dict[str, dict[str, float]] | None:
        """Get the snapshot immediately before `current_snap_id`.

        Returns:
            {group_name: {actor: composite_score}} or None if no previous snapshot.
        """
        snaps = self.list_snapshots()
        found_current = False
        for s in snaps:
            if s["id"] == current_snap_id:
                found_current = True
                continue
            if found_current:
                with sqlite3.connect(str(self.db_path)) as conn:
                    row = conn.execute(
                        "SELECT data_json FROM follow_snapshots WHERE id = ?",
                        (s["id"],)
                    ).fetchone()
                    if row:
                        return json.loads(row[0]).get("groups", {})
        return None
