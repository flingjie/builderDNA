"""Workspace persistence + dedup tests."""

from repo_learning import workspace
from repo_learning.models import SourceKind, SourceRecord


def test_append_and_read_roundtrip(tmp_path):
    workspace.append_source(
        tmp_path, SourceRecord(id="a", kind=SourceKind.WEB_ARTICLE, body="hello")
    )
    result = workspace.read_sources(tmp_path)
    assert len(result.records) == 1
    assert result.records[0].id == "a"
    assert result.records[0].body == "hello"


def test_idempotent_append_last_wins(tmp_path):
    workspace.append_source(
        tmp_path, SourceRecord(id="a", kind=SourceKind.WEB_ARTICLE, body="v1")
    )
    workspace.append_source(
        tmp_path, SourceRecord(id="a", kind=SourceKind.WEB_ARTICLE, body="v2")
    )
    result = workspace.read_sources(tmp_path)
    assert len(result.records) == 1
    assert result.records[0].body == "v2"


def test_manifest_roundtrip(tmp_path):
    from repo_learning.models import RunManifest, StageStatus

    manifest = RunManifest(
        run_id="r1", request_hash="abc", stage_status={"init": StageStatus.COMPLETED}
    )
    workspace.save_manifest(tmp_path, manifest)
    loaded = workspace.load_manifest(tmp_path)
    assert loaded.run_id == "r1"
    assert loaded.stage_status["init"] == StageStatus.COMPLETED


def test_normalize_url_for_repost_dedup():
    from concepts.matching import normalize_url

    assert normalize_url("https://EXAMPLE.com/a/#frag") == "https://example.com/a"
    assert normalize_url("https://example.com/a/") == "https://example.com/a"
    assert normalize_url("https://example.com/a?utm=x") != "https://example.com/a"
