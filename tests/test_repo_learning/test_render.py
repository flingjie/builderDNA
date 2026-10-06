"""Tests for HTML rendering safety + self-containment."""

import json
import re

from repo_learning import workspace
from repo_learning.models import (
    Analysis,
    Episode,
    RepoIdentity,
    RunManifest,
    SourceKind,
    SourceRecord,
    SourceRef,
    StageStatus,
)
from repo_learning.render import _tojson_embed, render
from repo_learning.request import RequestSpec, save_request


def _setup(tmp_path):
    ref = SourceRef(source_id="s1", excerpt="</script><script>alert(1)</script>")
    analysis = Analysis(
        repo_identity=RepoIdentity(owner="o", name="r", canonical_url="https://github.com/o/r"),
        episode=Episode(id="e", title="t", problem="p", source_refs=[ref]),
    )
    (tmp_path / workspace.ANALYSIS_FILE).write_text(
        analysis.model_dump_json(indent=2), encoding="utf-8"
    )
    manifest = RunManifest(run_id="r1", request_hash="h", stage_status={"init": StageStatus.COMPLETED})
    workspace.save_manifest(tmp_path, manifest)
    save_request(tmp_path, RequestSpec(repo="https://github.com/o/r"))
    workspace.append_source(
        tmp_path, SourceRecord(id="s1", kind=SourceKind.WEB_ARTICLE, body="body")
    )
    return tmp_path


def test_tojson_embed_neutralizes_script_breakout():
    s = str(_tojson_embed({"x": "</script><script>alert(1)</script>"}))
    assert "</script>" not in s
    assert "<\\/script>" in s


def test_render_is_self_contained(tmp_path):
    report = render(_setup(tmp_path))
    html = report.read_text(encoding="utf-8")
    assert "<script src=" not in html
    assert "<link " not in html
    assert html.lstrip().startswith("<!doctype html>")


def test_embedded_json_parses(tmp_path):
    report = render(_setup(tmp_path))
    html = report.read_text(encoding="utf-8")
    m = re.search(
        r'<script type="application/json" id="report-data">(.*?)</script>', html, re.DOTALL
    )
    assert m is not None
    data = json.loads(m.group(1))
    assert data["analysis"]["repo_identity"]["name"] == "r"
    assert data["analysis"]["episode"]["title"] == "t"


def test_render_scrubs_credential(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "SECRETTOKEN123")
    rd = _setup(tmp_path)
    workspace.append_source(
        rd, SourceRecord(id="s2", kind=SourceKind.WEB_ARTICLE, body="token=SECRETTOKEN123")
    )
    report = render(rd)
    html = report.read_text(encoding="utf-8")
    assert "SECRETTOKEN123" not in html
