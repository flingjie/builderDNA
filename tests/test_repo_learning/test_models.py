"""Contract tests for repo-evolution-learning data models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from repo_learning.models import (
    FetchStatus,
    SearchRecord,
    SourceKind,
    SourceRecord,
)


def test_timestamps_must_be_utc():
    with pytest.raises(ValidationError):
        SourceRecord(
            id="x",
            kind=SourceKind.WEB_ARTICLE,
            published_at=datetime(2020, 1, 1),  # naive
        )


def test_unknown_timestamp_is_none_not_zero():
    record = SourceRecord(id="x", kind=SourceKind.WEB_ARTICLE)
    assert record.published_at is None
    assert record.body == ""


def test_source_record_roundtrip():
    record = SourceRecord(
        id="web_article:https://example.com/a",
        kind=SourceKind.WEB_ARTICLE,
        url="https://example.com/a",
        canonical_url="https://example.com/a",
        author="alice",
        published_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        body="hello",
        fetch_status=FetchStatus.PARTIAL,
    )
    dumped = record.model_dump(mode="json")
    assert dumped["published_at"] == "2020-01-01T00:00:00Z"
    assert SourceRecord.model_validate(dumped) == record


def test_search_record_requires_id():
    with pytest.raises(ValidationError):
        SearchRecord(query="q", engine="google")
    rec = SearchRecord(id="google:1", query="q", engine="google")
    assert rec.id == "google:1"


def test_fetch_status_enum_rejects_unknown():
    with pytest.raises(ValidationError):
        SourceRecord(id="x", kind=SourceKind.WEB_ARTICLE, fetch_status="nope")  # type: ignore[arg-type]
