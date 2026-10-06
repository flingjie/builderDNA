"""Tests for analysis validation."""

from repo_learning import workspace
from repo_learning.models import (
    Analysis,
    Episode,
    RepoIdentity,
    SourceKind,
    SourceRecord,
    SourceRef,
)
from repo_learning.request import RequestSpec
from repo_learning.validation import validate


def _base_analysis(source_id="s1", *, canonical_url="https://github.com/o/r", outcome=""):
    ref = SourceRef(source_id=source_id)
    return Analysis(
        repo_identity=RepoIdentity(owner="o", name="r", canonical_url=canonical_url),
        episode=Episode(id="e", title="t", problem="p", outcome=outcome, source_refs=[ref]),
    )


def _write(tmp_path, analysis, sources=None):
    (tmp_path / workspace.ANALYSIS_FILE).write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
    for s in (sources or []):
        workspace.append_source(tmp_path, s)
    return tmp_path


def test_valid_analysis_passes(tmp_path):
    src = SourceRecord(id="s1", kind=SourceKind.GITHUB_PR, url="https://github.com/o/r/pull/1")
    _write(tmp_path, _base_analysis("s1"), [src])
    result = validate(RequestSpec(repo="https://github.com/o/r"), tmp_path)
    assert result["valid"] is True


def test_unresolved_ref_is_error(tmp_path):
    _write(tmp_path, _base_analysis("missing"), [])
    result = validate(RequestSpec(repo="o/r"), tmp_path)
    assert result["valid"] is False
    assert any(e["severity"] == "error" for e in result["errors"])
    assert result["counts"]["unresolved_refs"] == 1


def test_disabled_expression_warns(tmp_path):
    src = SourceRecord(id="s1", kind=SourceKind.GITHUB_PR)
    _write(tmp_path, _base_analysis("s1", outcome="显著提升了鲁棒性"), [src])
    result = validate(RequestSpec(repo="o/r"), tmp_path)
    assert any(w["severity"] == "warning" for w in result["warnings"])


def test_non_http_scheme_is_error(tmp_path):
    src = SourceRecord(id="s1", kind=SourceKind.GITHUB_PR)
    _write(tmp_path, _base_analysis("s1", canonical_url="javascript:alert(1)"), [src])
    result = validate(RequestSpec(repo="o/r"), tmp_path)
    assert any(e["severity"] == "error" for e in result["errors"])


def test_plain_text_colon_is_not_scheme_error(tmp_path):
    # Body text like "note: …" must not trip the URL-scheme check.
    src = SourceRecord(id="s1", kind=SourceKind.WEB_ARTICLE, body="note: this is fine")
    _write(tmp_path, _base_analysis("s1"), [src])
    result = validate(RequestSpec(repo="o/r"), tmp_path)
    assert not any(e["severity"] == "error" for e in result["errors"])


def test_credential_leak_is_error(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "SECRETTOKEN123")
    src = SourceRecord(id="s1", kind=SourceKind.WEB_ARTICLE, body="api_key=SECRETTOKEN123")
    _write(tmp_path, _base_analysis("s1"), [src])
    result = validate(RequestSpec(repo="o/r"), tmp_path)
    assert any(e["severity"] == "error" for e in result["errors"])


def test_missing_analysis(tmp_path):
    result = validate(RequestSpec(repo="o/r"), tmp_path)
    assert result["valid"] is False
    assert "not found" in result["errors"][0]["message"]
