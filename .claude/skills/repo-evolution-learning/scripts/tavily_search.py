#!/usr/bin/env python3
"""Tavily search adapter for repo-evolution-learning.

This script is deliberately dependency-free. It reads ``TAVILY_API_KEY`` from the
environment (or ``--api-key``) and emits one JSON object to stdout. The returned
shape maps directly into a ``SearchRecord``:

    engine       -> "tavily"
    query        -> query
    searched_at  -> searched_at
    results      -> [{"title", "url", "snippet", "score", "raw_content"}]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request


TAVILY_URL = "https://api.tavily.com/search"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            values[key] = value
    return values


def _emit(payload: dict, exit_code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search Tavily and emit a SearchRecord-compatible JSON object.")
    parser.add_argument("--query", required=True, help="Search query.")
    parser.add_argument("--max-results", type=int, default=10, help="Number of results, 1-20.")
    parser.add_argument("--search-depth", choices=("basic", "advanced"), default="basic", help="Tavily search depth.")
    parser.add_argument("--topic", choices=("general", "news", "finance"), default="general", help="Tavily topic.")
    parser.add_argument("--include-answer", action="store_true", help="Include Tavily's synthesized answer.")
    parser.add_argument("--include-raw-content", action="store_true", help="Include raw_content in each result.")
    parser.add_argument("--include-domains", default="", help="Comma-separated domains to restrict the search.")
    parser.add_argument("--exclude-domains", default="", help="Comma-separated domains to exclude.")
    parser.add_argument("--days", type=int, default=None, help="Only include results from the last N days.")
    parser.add_argument("--api-key", default=None, help="Tavily API key. Prefer TAVILY_API_KEY.")
    parser.add_argument("--env-file", default=None, help="Optional .env file containing TAVILY_API_KEY.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    return parser.parse_args(argv)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.max_results <= 20:
        return _emit({"ok": False, "error": "max_results must be between 1 and 20"}, 2)

    env_file_values: dict[str, str] = {}
    if args.env_file:
        env_file_values = _load_env_file(Path(args.env_file))
    else:
        candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[4] / ".env"]
        for candidate in candidates:
            if candidate.exists():
                env_file_values = _load_env_file(candidate)
                break

    api_key = args.api_key or os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        api_key = env_file_values.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return _emit(
            {
                "ok": False,
                "engine": "tavily",
                "query": args.query,
                "searched_at": _now_iso(),
                "results": [],
                "coverage_notes": ["engine unavailable: TAVILY_API_KEY is not set"],
            },
            2,
        )

    payload: dict = {
        "api_key": api_key,
        "query": args.query,
        "max_results": args.max_results,
        "search_depth": args.search_depth,
        "topic": args.topic,
        "include_answer": args.include_answer,
        "include_raw_content": args.include_raw_content,
    }
    if args.days is not None:
        payload["days"] = args.days
    if _csv(args.include_domains):
        payload["include_domains"] = _csv(args.include_domains)
    if _csv(args.exclude_domains):
        payload["exclude_domains"] = _csv(args.exclude_domains)

    try:
        req = request.Request(
            TAVILY_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=args.timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return _emit(
            {
                "ok": False,
                "engine": "tavily",
                "query": args.query,
                "searched_at": _now_iso(),
                "results": [],
                "coverage_notes": [f"engine unavailable: HTTP {exc.code}: {detail}"],
            },
            1,
        )
    except (error.URLError, TimeoutError, OSError) as exc:
        return _emit(
            {
                "ok": False,
                "engine": "tavily",
                "query": args.query,
                "searched_at": _now_iso(),
                "results": [],
                "coverage_notes": [f"engine unavailable: {exc}"],
            },
            1,
        )

    results = []
    for item in raw.get("results", []):
        result = {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": (item.get("content") or "")[:1200],
            "score": item.get("score"),
        }
        if args.include_raw_content:
            result["raw_content"] = item.get("raw_content")
        results.append(result)

    payload_out = {
        "ok": True,
        "engine": "tavily",
        "query": args.query,
        "searched_at": _now_iso(),
        "results": results,
        "coverage_notes": [],
    }
    if args.include_answer:
        payload_out["answer"] = raw.get("answer")
    if raw.get("images"):
        payload_out["images"] = raw.get("images")
    return _emit(payload_out)


if __name__ == "__main__":
    sys.exit(main())
