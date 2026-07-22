"""BuilderMemory: SQLite-backed persistent memory for user feedback rules."""
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


class BuilderMemory:
    def __init__(self, db_path: str = "snapshots/memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS memory_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_text TEXT NOT NULL,
            source_opportunity TEXT,
            decision_type TEXT NOT NULL,
            created_at TEXT NOT NULL)"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_decision "
            "ON memory_rules(decision_type, created_at DESC)"
        )
        self._conn.commit()

    def record(self, decision: dict) -> int:
        cursor = self._conn.execute(
            "INSERT INTO memory_rules (rule_text, source_opportunity, decision_type, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                decision["rule_text"],
                decision.get("source_opportunity", ""),
                decision.get("decision_type", "modify"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM memory_rules ORDER BY created_at DESC LIMIT ?",
            (top_k * 2,),
        ).fetchall()
        results = []
        for row in rows:
            rule_text = row["rule_text"]
            score = sum(
                1 for word in query.lower().split() if word in rule_text.lower()
            )
            if score > 0:
                results.append(
                    {
                        "rule": rule_text,
                        "score": score,
                        "source": row["source_opportunity"],
                        "decision_type": row["decision_type"],
                    }
                )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    def inject_constraints(self, opportunity_desc: str, prompt: str) -> str:
        rules = self.search(opportunity_desc, top_k=3)
        if not rules:
            return prompt
        constraint_text = "\n".join(f"- {r['rule']}" for r in rules)
        return (
            f"{prompt}\n\n"
            f"[User Preferences from past feedback]\n"
            f"{constraint_text}\n"
            f"Please respect these constraints."
        )

    def close(self):
        self._conn.close()
