"""Deterministic issue cleaning and dedup for the pain pipeline.

No embeddings, no network. Prepares issue signals for candidate grouping:

- ``issue_key`` — the stable reference used by the Agent confirmation step and
  the finalize step's reference validation.
- ``dedupe_issues`` — drop duplicate issues by canonical URL, then by
  ``(repo, issue_number)``.
- ``body_fingerprint`` — a short hash of the normalized body, used to spot
  template / duplicated-log issues.
- ``clean_issue_text`` — strip markdown code blocks, GitHub issue-template
  headers and repeated log lines, producing the text used ONLY for TF-IDF
  feature extraction (never stored back into issue summaries).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_MD_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+.*$", re.MULTILINE)
_FIELD_RE = re.compile(r"^\s{0,3}\*\*[^*]+\*\*:.*$", re.MULTILINE)


def issue_key(issue: Mapping) -> str:
    """Stable reference ``<repo>#<issue_number>`` for a single issue."""
    return f"{issue.get('repo', '')}#{issue.get('issue_number', 0)}"


def _normalize_url(url: str) -> str:
    return url.strip().lower().rstrip("/")


def dedupe_issues(issues: list[dict]) -> tuple[list[dict], int]:
    """Return ``(unique_issues, removed_count)``.

    Deduplicates by canonical URL first (strongest identity), then falls back to
    ``(repo, issue_number)`` for issues without a URL. First occurrence wins.
    """
    unique: list[dict] = []
    seen_urls: set[str] = set()
    seen_keys: set[tuple[str, int]] = set()
    removed = 0

    for iss in issues:
        url = _normalize_url(iss.get("url", ""))
        key = (iss.get("repo", ""), iss.get("issue_number", 0))

        if url and url in seen_urls:
            removed += 1
            continue
        if key in seen_keys:
            removed += 1
            continue

        if url:
            seen_urls.add(url)
        seen_keys.add(key)
        unique.append(iss)

    return unique, removed


def body_fingerprint(body: str) -> str:
    """Short hash of a normalized body (lowercase, punctuation/whitespace collapsed).

    Two issues with near-identical bodies (template noise, duplicated logs) share
    a fingerprint. Returns the first 16 hex chars of a SHA-256 digest.
    """
    normalized = re.sub(r"[^a-z0-9㐀-䶿一-鿿]", "", body.lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def clean_issue_text(title: str, body: str) -> str:
    """Strip boilerplate for TF-IDF features only.

    Drops markdown code blocks, GitHub issue-template section headers
    (``### …``), ``**Field:**`` boilerplate lines, and repeated lines
    (stack traces / duplicated logs). Title is always kept.
    """
    text = f"{title}\n{body or ''}"
    text = _CODE_BLOCK_RE.sub(" ", text)
    text = _MD_HEADER_RE.sub(" ", text)
    text = _FIELD_RE.sub(" ", text)

    seen: set[str] = set()
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(s)

    return " ".join(lines)
