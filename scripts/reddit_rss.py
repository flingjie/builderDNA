#!/usr/bin/env python3
"""Fetch a subreddit's public RSS feed and emit posts as JSON.

Stdlib only — no Reddit API key, no scraper. Uses the public .rss endpoint.
Respect Reddit: set a real User-Agent; callers space requests (~1/min).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

DEFAULT_USER_AGENT = "BuilderDNA/0.1 (reddit RSS research; local use)"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
TIMEOUT = 15
DEFAULT_PROXY = "http://127.0.0.1:7890"


def build_url(subreddit: str, sort: str, limit: int) -> str:
    """Return the public RSS URL for a subreddit (sort validated by argparse)."""
    return f"https://www.reddit.com/r/{subreddit}/.rss?sort={sort}&limit={limit}"


def parse_atom(xml_text: str) -> list[dict]:
    """Parse an Atom feed into a list of post dicts.

    Fields: id, title, author, permalink, published, selftext, category.
    Missing fields become empty strings (never raises on missing elements).
    """
    root = ET.fromstring(xml_text)
    posts: list[dict] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = (entry.findtext("atom:title", "", ATOM_NS) or "").strip()
        author_el = entry.find("atom:author/atom:name", ATOM_NS)
        author = (author_el.text or "").strip() if author_el is not None else ""
        link_el = entry.find("atom:link", ATOM_NS)
        permalink = link_el.get("href", "") if link_el is not None else ""
        published = entry.findtext("atom:published", "", ATOM_NS) or ""
        selftext = (entry.findtext("atom:content", "", ATOM_NS) or "").strip()
        cat_el = entry.find("atom:category", ATOM_NS)
        category = cat_el.get("term", "") if cat_el is not None else ""
        post_id = entry.findtext("atom:id", "", ATOM_NS) or ""
        posts.append({
            "id": post_id.strip(),
            "title": title,
            "author": author,
            "permalink": permalink,
            "published": published,
            "selftext": selftext,
            "category": category,
        })
    return posts


def fetch(url: str, timeout: int = TIMEOUT, proxy: str | None = None) -> str:
    """Fetch a URL and return the response body as decoded text.

    When `proxy` is set, route the request through it; otherwise use the
    default opener (which respects HTTP(S)_PROXY environment variables).
    """
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    with opener.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subreddit", help="subreddit name without r/ (e.g. 'SaaS')")
    parser.add_argument("--sort", choices=["hot", "new", "top"], default="new")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--proxy", default=DEFAULT_PROXY,
        help="HTTP(S) proxy for fetching (default http://127.0.0.1:7890; empty string = direct)",
    )
    args = parser.parse_args(argv)

    url = build_url(args.subreddit, args.sort, args.limit)
    try:
        xml_text = fetch(url, timeout=TIMEOUT, proxy=args.proxy or None)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            print(json.dumps({
                "error": "rate_limited", "code": exc.code,
                "retry_after": exc.headers.get("retry-after", "60"),
            }))
            return 2
        if exc.code == 404:
            print(json.dumps({
                "error": "not_found",
                "message": f"r/{args.subreddit} does not exist or is private",
            }))
            return 3
        print(json.dumps({"error": "http_error", "code": exc.code}))
        return 1
    except urllib.error.URLError as exc:
        print(json.dumps({"error": "network_error", "message": str(exc.reason)}))
        return 1

    try:
        posts = parse_atom(xml_text)
    except ET.ParseError as exc:
        print(json.dumps({"error": "parse_error", "message": str(exc)}))
        return 1

    print(json.dumps(posts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
