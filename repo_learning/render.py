"""HTML report rendering for repo-evolution-learning.

Renders the validated ``analysis.json`` into a self-contained interactive HTML
file via a jinja2 template. The template is vanilla JS + inline CSS with no
external CDN (offline core reading). All collected content is embedded as a
JSON blob and rendered client-side via ``textContent`` — never ``innerHTML``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from repo_learning import workspace
from repo_learning.models import SourceRecord
from repo_learning.request import load_request


def _tojson_embed(value) -> Markup:
    """Serialize ``value`` to a JSON string safe to embed inside ``<script>``.

    Neutralizes a closing-script breakout (``</`` is rewritten) and the JS line
    separators U+2028 / U+2029. Returns Markup so jinja2 autoescape does not
    double-escape the JSON.
    """
    s = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    s = s.replace("</", "<\\/")
    s = s.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return Markup(s)


def _scrub_credentials(data, token: str):
    """Defensively replace a known token value in every string before embedding.

    Validation catches credential leaks with a clear error; this is a second
    layer so a render run without a prior validate still never embeds the token.
    """
    if not token:
        return data

    def walk(obj):
        if isinstance(obj, dict):
            return {k: walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [walk(v) for v in obj]
        if isinstance(obj, str):
            return obj.replace(token, "[redacted]")
        return obj

    return walk(data)


def _sources_index(sources: list[SourceRecord]) -> dict[str, dict]:
    return {
        s.id: {
            "id": s.id,
            "kind": s.kind.value,
            "url": s.url,
            "canonical_url": s.canonical_url,
            "author": s.author,
            "published_at": s.published_at.isoformat() if s.published_at else None,
            "fetch_status": s.fetch_status.value,
            "body": s.body,
            "missing_scope": s.missing_scope,
        }
        for s in sources
    }


def render(run_dir: Path, template_path: str | Path | None = None) -> Path:
    """Render ``report.html`` into the run workspace and return its path."""
    analysis = workspace.load_analysis(run_dir)
    manifest = workspace.load_manifest(run_dir)
    request = load_request(run_dir)
    sources = workspace.read_sources(run_dir).records

    data = {
        "analysis": analysis.model_dump(mode="json"),
        "manifest": manifest.model_dump(mode="json"),
        "request": request.model_dump(mode="json"),
        "sources_index": _sources_index(sources),
    }
    data = _scrub_credentials(data, os.environ.get("GITHUB_TOKEN", ""))

    if template_path:
        loader_dir = str(Path(template_path).parent)
        template_name = Path(template_path).name
    else:
        loader_dir = str(Path(__file__).parent / "templates")
        template_name = "report.html"

    env = Environment(
        loader=FileSystemLoader(loader_dir),
        autoescape=select_autoescape(["html", "htm", "xml"]),
    )
    env.filters["tojson_embed"] = _tojson_embed

    html = env.get_template(template_name).render(
        report_data=_tojson_embed(data),
        mode=request.mode,
        output_language=request.output.language,
    )

    out = run_dir / workspace.REPORT_FILE
    out.write_text(html, encoding="utf-8")
    return out
