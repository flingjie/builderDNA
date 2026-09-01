"""Migration/compatibility tests for the cross-source Signal extension (Task 3.1).

Covers:
  - new source values and generic/fallback `type`
  - nullable evidence metadata (role, directness, strength, independence_key)
  - store round-trip of the new fields
  - backward compatibility with pre-extension databases (guarded ALTER TABLE)
  - payload stays the source-specific extensibility point
"""
import sqlite3
from datetime import datetime, timezone

import pytest

from signals.models import Signal, GITHUB_EVENT_TYPES, GENERIC_EVENT_TYPES
from signals.store import SignalStore


class TestSourceExtension:
    def test_all_sources_accepted(self):
        for source in ("x", "reddit", "github", "paper", "official_doc", "manual"):
            s = Signal(
                source=source,
                type="signal",
                actor="a",
                target_repo="t",
                timestamp=datetime.now(timezone.utc),
            )
            assert s.source == source

    def test_invalid_source_rejected(self):
        with pytest.raises(Exception):
            Signal(
                source="tiktok",
                type="signal",
                actor="a",
                target_repo="t",
            )

    def test_github_event_types_still_valid(self):
        for t in GITHUB_EVENT_TYPES:
            s = Signal(source="github", type=t, actor="a", target_repo="a/b")
            assert s.type == t

    def test_type_is_extensible_free_string(self):
        # New sources can introduce their own labels without a schema change.
        s = Signal(
            source="reddit",
            type="community_rss_finding",
            actor="u/author",
            target_repo="r/SaaS",
        )
        assert s.type == "community_rss_finding"

    def test_generic_type_fallback(self):
        # Omitting `type` yields the generic fallback.
        s = Signal(source="manual", actor="me", target_repo="https://example.com")
        assert s.type == "signal"


class TestEvidenceMetadata:
    def test_metadata_defaults_to_none(self):
        s = Signal(source="github", type="repo_created", actor="a", target_repo="a/b")
        assert s.evidence_role is None
        assert s.directness is None
        assert s.strength is None
        assert s.independence_key is None

    def test_metadata_settable(self):
        s = Signal(
            source="reddit",
            type="evidence",
            actor="u/author",
            target_repo="r/AgentDev",
            evidence_role="problem",
            directness="L1",
            strength=0.9,
            independence_key="https://reddit.com/r/AgentDev/comments/abc",
        )
        assert s.evidence_role == "problem"
        assert s.directness == "L1"
        assert s.strength == 0.9
        assert s.independence_key == "https://reddit.com/r/AgentDev/comments/abc"


class TestStoreRoundTrip:
    def test_new_record_round_trips(self, tmp_path):
        store = SignalStore(str(tmp_path / "roundtrip.db"))
        signal = Signal(
            id="reddit-1",
            source="reddit",
            type="evidence",
            actor="u/author",
            target_repo="r/AgentDev",
            timestamp=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            velocity=0.0,
            impact=0.4,
            evidence_role="problem",
            directness="L1",
            strength=0.85,
            independence_key="https://reddit.com/r/AgentDev/comments/abc",
            payload={"title": "agents forget context", "url": "https://reddit.com/..."},
        )
        store.insert([signal])

        loaded = store.get("reddit-1")
        assert loaded is not None
        assert loaded.source == "reddit"
        assert loaded.type == "evidence"
        assert loaded.evidence_role == "problem"
        assert loaded.directness == "L1"
        assert loaded.strength == 0.85
        assert loaded.independence_key == "https://reddit.com/r/AgentDev/comments/abc"
        # Source-specific payload survives untouched (extensibility point).
        assert loaded.payload == {"title": "agents forget context", "url": "https://reddit.com/..."}
        assert loaded.timestamp == datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_github_record_without_metadata_round_trips(self, tmp_path):
        store = SignalStore(str(tmp_path / "github_roundtrip.db"))
        signal = Signal(
            id="gh-1",
            source="github",
            type="star_growth",
            actor="dev",
            target_repo="org/repo",
            timestamp=datetime.now(timezone.utc),
            velocity=12.0,
            impact=0.6,
            payload={"topics": ["agent"]},
        )
        store.insert([signal])

        loaded = store.get("gh-1")
        assert loaded is not None
        assert loaded.source == "github"
        assert loaded.type == "star_growth"
        # New metadata is None for records that never set it.
        assert loaded.evidence_role is None
        assert loaded.directness is None
        assert loaded.strength is None
        assert loaded.independence_key is None
        assert loaded.payload == {"topics": ["agent"]}

    def test_all_returns_models(self, tmp_path):
        store = SignalStore(str(tmp_path / "all.db"))
        store.insert([
            Signal(id="a", source="github", type="repo_created", actor="x", target_repo="a/b"),
            Signal(id="b", source="x", type="note", actor="y", target_repo="https://x.com/..."),
        ])
        ids = {s.id for s in store.all()}
        assert ids == {"a", "b"}


class TestBackwardCompatibility:
    def test_pre_extension_database_opens_and_backfills(self, tmp_path):
        """A database created with the old GitHub-only schema still opens."""
        db_path = str(tmp_path / "legacy.db")

        # Build the pre-extension schema by hand (no evidence columns).
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE signals (
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
        conn.execute(
            "INSERT INTO signals (id, source, type, actor, target_repo, timestamp, velocity, impact, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-1", "github", "star_growth", "dev", "org/repo",
             datetime.now(timezone.utc).isoformat(), 5.0, 0.5, '{"topics": ["agent"]}'),
        )
        conn.commit()
        conn.close()

        # Opening with SignalStore runs the guarded migration, then old rows load.
        store = SignalStore(db_path)
        assert store.count() == 1
        loaded = store.get("legacy-1")
        assert loaded is not None
        assert loaded.source == "github"
        assert loaded.type == "star_growth"
        assert loaded.actor == "dev"
        assert loaded.target_repo == "org/repo"
        assert loaded.payload == {"topics": ["agent"]}
        # Old rows get None for the new metadata.
        assert loaded.evidence_role is None
        assert loaded.strength is None

        # The new columns now exist so new records can round-trip.
        col_names = {r["name"] for r in store._conn.execute("PRAGMA table_info(signals)").fetchall()}
        assert {"evidence_role", "directness", "strength", "independence_key"} <= col_names

    def test_payload_not_polluted_by_metadata(self, tmp_path):
        """Normalized metadata lives in columns, not inside payload_json."""
        store = SignalStore(str(tmp_path / "clean.db"))
        store.insert([
            Signal(
                id="p1",
                source="paper",
                type="evidence",
                actor="arxiv",
                target_repo="arxiv:2401.00001",
                evidence_role="validation",
                directness="L3",
                strength=0.7,
                independence_key="arxiv:2401.00001",
                payload={"title": "A paper", "doi": "10.xxxx"},
            )
        ])
        row = store._conn.execute("SELECT payload_json FROM signals WHERE id = ?", ("p1",)).fetchone()
        assert "evidence_role" not in row["payload_json"]
        assert "independence_key" not in row["payload_json"]
        # The normalized field is stored in its own column.
        row2 = store._conn.execute("SELECT evidence_role, independence_key FROM signals WHERE id = ?", ("p1",)).fetchone()
        assert row2["evidence_role"] == "validation"
        assert row2["independence_key"] == "arxiv:2401.00001"
