"""Tests for the atomic JSONL concept store (concepts/store.py).

Covers the hard requirements:
- Atomic writes: same-directory temp file + os.replace; an interrupted write
  never truncates prior state.
- Robust reads: corrupt lines are skipped and reported (not raised); blank lines
  are ignored; duplicate IDs de-duplicate deterministically (last wins).
- Corruption guard on write: >50% corrupt lines refuses the write.
- Append-only evidence/reviews: duplicate IDs raise, never silently clobber.
- One current snapshot per concept ID.
"""

import threading
from datetime import datetime, timedelta, timezone

import pytest

from concepts.store import (
    ConceptStore,
    ConceptStoreError,
    ConflictError,
    CorruptionError,
    DuplicateRecordError,
)
from models.concept import (
    ConceptCard,
    ConceptEvidence,
    Directness,
    EvidenceRole,
    EvidenceStrength,
    PortfolioStage,
    RadarReview,
    SourceType,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_card(**overrides) -> ConceptCard:
    fields = dict(id="c1", title="Agent Reliability")
    fields.update(overrides)
    return ConceptCard(**fields)


def make_evidence(**overrides) -> ConceptEvidence:
    fields = dict(
        id="ev1",
        concept_id="c1",
        source_type=SourceType.GITHUB,
        source_url="https://github.com/example/repo",
        role=EvidenceRole.IMPLEMENTATION,
        directness=Directness.DIRECT,
        strength=EvidenceStrength.STRONG,
        independence_key="github.com/example/repo",
    )
    fields.update(overrides)
    return ConceptEvidence(**fields)


def make_review(**overrides) -> RadarReview:
    fields = dict(
        id="rev1",
        concept_id="c1",
        from_stage=PortfolioStage.INBOX,
        to_stage=PortfolioStage.WATCH,
        reason="Enough signal to watch",
        expected_evidence="A second independent source",
        review_date=utc_now(),
    )
    fields.update(overrides)
    return RadarReview(**fields)


@pytest.fixture
def store(tmp_path):
    return ConceptStore(state_dir=tmp_path)


# ── Concepts: snapshot round-trip and upsert ──

class TestConceptSnapshots:
    def test_files_created_on_first_use(self, tmp_path):
        s = ConceptStore(state_dir=tmp_path)
        assert not (tmp_path / "concepts.jsonl").exists()
        assert not (tmp_path / "concept_evidence.jsonl").exists()
        assert not (tmp_path / "radar_reviews.jsonl").exists()
        s.upsert_concept(make_card())
        assert (tmp_path / "concepts.jsonl").exists()

    def test_upsert_get_list_round_trip(self, store):
        store.upsert_concept(make_card(id="c1", title="Agent Reliability"))
        got = store.get_concept("c1")
        assert got is not None
        assert got.title == "Agent Reliability"
        assert len(store.list_concepts()) == 1

    def test_get_missing_returns_none(self, store):
        assert store.get_concept("nope") is None

    def test_upsert_is_atomic_per_id(self, store):
        store.upsert_concept(make_card(id="c1", title="First"))
        store.upsert_concept(make_card(id="c1", title="Second"))
        store.upsert_concept(make_card(id="c2", title="Other"))
        cards = {c.id: c for c in store.list_concepts()}
        assert set(cards) == {"c1", "c2"}
        assert cards["c1"].title == "Second"
        # one line per concept id — no duplicate snapshot lines remain
        lines = [l for l in store.concepts_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_upsert_preserves_created_at_bumps_updated_at(self, store):
        created = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        store.upsert_concept(make_card(id="c1", created_at=created))
        before = store.get_concept("c1")
        store.upsert_concept(make_card(id="c1", title="Renamed"))
        after = store.get_concept("c1")
        assert after.created_at == created
        assert after.updated_at >= before.updated_at

    def test_upsert_returns_written_snapshot(self, store):
        out = store.upsert_concept(make_card(id="c1", title="X"))
        assert out.id == "c1"
        assert out.updated_at.utcoffset() == timedelta(0)


# ── Robust reads ──

class TestRobustReads:
    def test_corrupt_line_skipped_and_reported(self, store):
        store.concepts_path.write_text(
            '{"id":"ok","title":"Good"}\n'
            'this is not json\n'
            '{"id":"also","title":"Also Good"}\n',
            encoding="utf-8",
        )
        cards = store.list_concepts()
        assert {c.id for c in cards} == {"ok", "also"}
        corrupt = store.corrupt_lines()
        assert len(corrupt) == 1
        assert corrupt[0].line_no == 2

    def test_blank_lines_ignored_not_corrupt(self, store):
        store.concepts_path.write_text(
            '{"id":"a","title":"A"}\n\n   \n{"id":"b","title":"B"}\n',
            encoding="utf-8",
        )
        cards = store.list_concepts()
        assert {c.id for c in cards} == {"a", "b"}
        assert store.corrupt_lines() == []

    def test_valid_json_wrong_shape_counts_corrupt(self, store):
        # Missing required "title" -> model validation failure, not a crash.
        store.concepts_path.write_text(
            '{"id":"only-id"}\n{"id":"ok","title":"Good"}\n', encoding="utf-8"
        )
        cards = store.list_concepts()
        assert {c.id for c in cards} == {"ok"}
        assert len(store.corrupt_lines()) == 1

    def test_duplicate_id_last_wins(self, store):
        store.concepts_path.write_text(
            '{"id":"c1","title":"Old"}\n{"id":"c1","title":"New"}\n', encoding="utf-8"
        )
        cards = store.list_concepts()
        assert len(cards) == 1
        assert cards[0].title == "New"

    def test_read_missing_file_returns_empty(self, store):
        assert store.list_concepts() == []
        assert store.list_evidence() == []
        assert store.list_reviews() == []
        assert store.corrupt_lines() == []


# ── Atomic writes ──

class TestAtomicWrites:
    def test_write_leaves_no_temp_files(self, store):
        store.upsert_concept(make_card(id="c1"))
        store.add_evidence(make_evidence(id="ev1"))
        store.add_review(make_review(id="rev1"))
        assert list(store.state_dir.glob("*.tmp")) == []

    def test_interrupted_write_preserves_prior_state(self, store, monkeypatch):
        store.upsert_concept(make_card(id="c1", title="Original"))
        original = store.concepts_path.read_text()

        def boom(src, dst):
            raise RuntimeError("simulated crash during replace")

        monkeypatch.setattr("os.replace", boom)
        with pytest.raises(RuntimeError):
            store.upsert_concept(make_card(id="c1", title="Should Not Land"))
        assert store.concepts_path.read_text() == original
        assert list(store.state_dir.glob("*.tmp")) == []

    def test_write_is_valid_jsonl(self, store):
        store.upsert_concept(make_card(id="c1"))
        store.upsert_concept(make_card(id="c2", title="Two"))
        import json

        lines = [json.loads(l) for l in store.concepts_path.read_text().splitlines() if l.strip()]
        assert {d["id"] for d in lines} == {"c1", "c2"}


# ── Corruption guard on write ──

class TestCorruptionGuard:
    def test_majority_corrupt_refuses_concept_write(self, store):
        store.concepts_path.write_text(
            '{"id":"ok","title":"Good"}\nBROKEN LINE\nALSO BROKEN\n', encoding="utf-8"
        )
        with pytest.raises(CorruptionError):
            store.upsert_concept(make_card(id="c2"))
        # file untouched by the refused write
        assert "BROKEN LINE" in store.concepts_path.read_text()

    def test_majority_corrupt_refuses_evidence_write(self, store):
        store.evidence_path.write_text("bad1\nbad2\n", encoding="utf-8")
        with pytest.raises(CorruptionError):
            store.add_evidence(make_evidence(id="ev1"))

    def test_exactly_half_corrupt_is_allowed(self, store):
        store.concepts_path.write_text(
            '{"id":"ok","title":"Good"}\nBROKEN\n', encoding="utf-8"
        )
        store.upsert_concept(make_card(id="c2", title="Two"))
        assert {c.id for c in store.list_concepts()} == {"ok", "c2"}

    def test_all_corrupt_refuses(self, store):
        store.concepts_path.write_text("a\nb\nc\n", encoding="utf-8")
        with pytest.raises(CorruptionError):
            store.upsert_concept(make_card(id="c1"))

    def test_empty_file_writes_fine(self, store):
        store.concepts_path.write_text("", encoding="utf-8")
        store.upsert_concept(make_card(id="c1"))
        assert store.get_concept("c1") is not None


# ── Evidence: append-only, no silent clobber ──

class TestEvidence:
    def test_add_and_list(self, store):
        store.add_evidence(make_evidence(id="ev1", concept_id="c1"))
        store.add_evidence(make_evidence(id="ev2", concept_id="c1"))
        assert {e.id for e in store.list_evidence()} == {"ev1", "ev2"}

    def test_list_filters_by_concept(self, store):
        store.add_evidence(make_evidence(id="ev1", concept_id="c1"))
        store.add_evidence(make_evidence(id="ev2", concept_id="c2"))
        assert {e.id for e in store.list_evidence("c1")} == {"ev1"}
        assert {e.id for e in store.list_evidence("c2")} == {"ev2"}

    def test_get_evidence(self, store):
        store.add_evidence(make_evidence(id="ev1"))
        assert store.get_evidence("ev1").id == "ev1"
        assert store.get_evidence("nope") is None

    def test_duplicate_id_raises(self, store):
        store.add_evidence(make_evidence(id="ev1", note="original"))
        with pytest.raises(ConflictError):
            store.add_evidence(make_evidence(id="ev1", note="clobbered"))

    def test_duplicate_id_never_silently_clobbers(self, store):
        store.add_evidence(make_evidence(id="ev1", note="original"))
        with pytest.raises(ConflictError):
            store.add_evidence(make_evidence(id="ev1", note="clobbered"))
        assert store.get_evidence("ev1").note == "original"
        assert len(store.list_evidence()) == 1

    def test_evidence_records_are_immutable(self, store):
        store.add_evidence(make_evidence(id="ev1"))
        ev = store.get_evidence("ev1")
        with pytest.raises(Exception):
            ev.note = "mutated"  # frozen model


# ── Reviews: append-only ──

class TestReviews:
    def test_add_and_list(self, store):
        store.add_review(make_review(id="rev1", concept_id="c1"))
        store.add_review(make_review(id="rev2", concept_id="c2"))
        assert {r.id for r in store.list_reviews()} == {"rev1", "rev2"}
        assert {r.id for r in store.list_reviews("c1")} == {"rev1"}

    def test_get_review(self, store):
        store.add_review(make_review(id="rev1"))
        assert store.get_review("rev1").to_stage == PortfolioStage.WATCH
        assert store.get_review("nope") is None

    def test_duplicate_review_id_raises(self, store):
        store.add_review(make_review(id="rev1", reason="first"))
        with pytest.raises(ConflictError):
            store.add_review(make_review(id="rev1", reason="clobbered"))
        assert store.get_review("rev1").reason == "first"


# ── Deterministic de-duplication across a corrupted file ──

class TestDedupAfterCorruption:
    def test_last_valid_duplicate_wins_across_corrupt_lines(self, store):
        store.concepts_path.write_text(
            '{"id":"c1","title":"First"}\n'
            'CORRUPT\n'
            '{"id":"c1","title":"Last"}\n',
            encoding="utf-8",
        )
        cards = store.list_concepts()
        assert len(cards) == 1
        assert cards[0].title == "Last"


# ── Idempotent replay: identical ID + identical payload is a no-op ──

class TestIdempotentReplay:
    def test_identical_evidence_replay_is_noop(self, store):
        store.add_evidence(make_evidence(id="ev1", note="same note"))
        replay = make_evidence(id="ev1", note="same note")
        returned = store.add_evidence(replay)
        assert returned.id == "ev1"
        assert returned.note == "same note"
        # no second record was created
        assert len(store.list_evidence()) == 1

    def test_identical_review_replay_is_noop(self, store):
        review_date = datetime(2026, 9, 8, 0, 0, 0, tzinfo=timezone.utc)
        store.add_review(make_review(id="rev1", reason="first", review_date=review_date))
        replay = make_review(id="rev1", reason="first", review_date=review_date)
        returned = store.add_review(replay)
        assert returned.id == "rev1"
        assert len(store.list_reviews()) == 1

    def test_replay_ignores_evidence_write_timestamp(self, store):
        # Same logical evidence but a different `captured_at` (the write
        # timestamp) must still be an idempotent replay, not a conflict.
        store.add_evidence(make_evidence(id="ev1", note="same", captured_at=utc_now()))
        replay = make_evidence(
            id="ev1", note="same", captured_at=datetime(2020, 1, 1, tzinfo=timezone.utc)
        )
        returned = store.add_evidence(replay)
        assert returned.id == "ev1"
        assert len(store.list_evidence()) == 1

    def test_replay_ignores_review_write_timestamp_not_review_date(self, store):
        review_date = datetime(2026, 9, 8, 0, 0, 0, tzinfo=timezone.utc)
        store.add_review(make_review(id="rev1", reason="first", review_date=review_date))
        # Different `recorded_at` (write timestamp) -> idempotent replay.
        replay = make_review(
            id="rev1",
            reason="first",
            review_date=review_date,
            recorded_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        returned = store.add_review(replay)
        assert returned.id == "rev1"
        assert len(store.list_reviews()) == 1
        # Different `review_date` (semantic field, not a write timestamp) -> conflict.
        with pytest.raises(ConflictError):
            store.add_review(
                make_review(
                    id="rev1",
                    reason="first",
                    review_date=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc),
                )
            )

    def test_idempotent_replay_returns_existing_record(self, store):
        store.add_evidence(make_evidence(id="ev1", note="original"))
        returned = store.add_evidence(make_evidence(id="ev1", note="original"))
        assert returned.note == "original"


# ── Conflict: identical ID + different payload raises ConflictError ──

class TestConflict:
    def test_conflict_error_is_distinct_and_catchable(self):
        # Distinct from the old broad duplicate error, but still a
        # DuplicateRecordError / ConceptStoreError so existing handlers keep working.
        assert ConflictError is not DuplicateRecordError
        assert issubclass(ConflictError, DuplicateRecordError)
        assert issubclass(DuplicateRecordError, ConceptStoreError)

    def test_different_evidence_payload_raises_conflict(self, store):
        store.add_evidence(make_evidence(id="ev1", note="original"))
        with pytest.raises(ConflictError):
            store.add_evidence(make_evidence(id="ev1", note="different"))

    def test_different_review_payload_raises_conflict(self, store):
        store.add_review(make_review(id="rev1", reason="first"))
        with pytest.raises(ConflictError):
            store.add_review(make_review(id="rev1", reason="different"))

    def test_conflict_does_not_append(self, store):
        store.add_evidence(make_evidence(id="ev1", note="original"))
        with pytest.raises(ConflictError):
            store.add_evidence(
                make_evidence(id="ev1", source_url="https://other.example/repo")
            )
        assert len(store.list_evidence()) == 1
        assert store.get_evidence("ev1").source_url == "https://github.com/example/repo"


# ── Process-local lock: concurrent calls cannot interleave ──

class TestConcurrency:
    def test_store_has_functional_process_local_lock(self, store):
        lock = store._lock
        assert lock.acquire(blocking=False)
        lock.release()

    def test_concurrent_identical_appends_are_idempotent(self, store):
        n = 16
        errors: list[Exception] = []
        barrier = threading.Barrier(n)

        def worker():
            try:
                barrier.wait()
                store.add_evidence(make_evidence(id="ev1", note="same"))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(store.list_evidence()) == 1

    def test_concurrent_distinct_appends_lose_nothing(self, store):
        n = 24
        errors: list[Exception] = []
        barrier = threading.Barrier(n)

        def worker(i: int):
            try:
                barrier.wait()
                store.add_evidence(make_evidence(id=f"ev{i}", concept_id="c1"))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(store.list_evidence()) == n
        assert {e.id for e in store.list_evidence()} == {f"ev{i}" for i in range(n)}
