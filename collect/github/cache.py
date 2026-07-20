"""HTTP response cache with ETag support for GitHub API.

Caches responses on the filesystem under the configured cache directory.
Each cached entry is two files:
  <key>.json  — {status, headers, body}
  <key>.meta  — {etag, cached_at, ttl}
"""

import hashlib
import json
import time
from pathlib import Path


def _get_ttl(url: str) -> int:
    """Determine TTL for a URL based on endpoint type.

    Checks more specific patterns first to avoid false matches
    (e.g. /search/repositories containing /repos).
    """
    if "/search/" in url:
        return 300   # search results: 5m
    if "/starred" in url:
        return 1800  # starred repos: 30m
    if "/commits" in url:
        return 600   # commits: 10m
    if "/repos" in url:
        return 3600  # repo listings: 1h
    if "/users/" in url:
        return 86400  # user profiles: 24h
    return 3600  # default: 1h


class CacheStore:
    """Filesystem-based HTTP response cache with ETag-based conditional requests."""

    def __init__(self, cache_dir: str | Path = "snapshots/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, method: str, url: str, params: dict[str, str] | None = None) -> str:
        """Generate a deterministic cache key from method, url, and params."""
        raw = f"{method}:{url}"
        if params:
            sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            raw += f"?{sorted_params}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _json_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _meta_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.meta"

    def get(self, method: str, url: str, params: dict[str, str] | None = None) -> tuple[int, dict, str] | None:
        """Retrieve a cached response if fresh.

        Returns:
            (status_code, headers_dict, body_string) or None if cache miss or stale.
        """
        key = self._cache_key(method, url, params)
        json_file = self._json_path(key)
        meta_file = self._meta_path(key)

        if not json_file.exists() or not meta_file.exists():
            return None

        try:
            meta = json.loads(meta_file.read_text())
            ttl = meta.get("ttl", _get_ttl(url))
            if time.time() - meta.get("cached_at", 0) > ttl:
                return None  # stale

            data = json.loads(json_file.read_text())
            return data["status"], data["headers"], data["body"]
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def get_etag(self, method: str, url: str, params: dict[str, str] | None = None) -> str | None:
        """Get the saved ETag for a request, regardless of freshness."""
        key = self._cache_key(method, url, params)
        meta_file = self._meta_path(key)
        if not meta_file.exists():
            return None
        try:
            meta = json.loads(meta_file.read_text())
            return meta.get("etag")
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, method: str, url: str, params: dict[str, str] | None,
            status: int, headers: dict[str, str], body: str) -> None:
        """Cache a response."""
        key = self._cache_key(method, url, params)
        etag = headers.get("etag", headers.get("ETag", ""))

        data = {"status": status, "headers": dict(headers), "body": body}
        meta = {"etag": etag, "cached_at": time.time(), "ttl": _get_ttl(url)}

        self._json_path(key).write_text(json.dumps(data, ensure_ascii=False))
        self._meta_path(key).write_text(json.dumps(meta))

    def update_from_304(self, method: str, url: str, params: dict[str, str] | None,
                        headers: dict[str, str]) -> None:
        """Update cache metadata on a 304 Not Modified response.

        The body stays the same; we just bump cached_at and update etag.
        """
        key = self._cache_key(method, url, params)
        meta_file = self._meta_path(key)
        new_etag = headers.get("etag", headers.get("ETag", ""))

        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
            except (json.JSONDecodeError, OSError):
                meta = {}
        else:
            meta = {}

        meta["etag"] = new_etag
        meta["cached_at"] = time.time()
        meta_file.write_text(json.dumps(meta))

    def clear(self) -> int:
        """Delete all cached files. Returns count of deleted entries."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        for f in self.cache_dir.glob("*.meta"):
            f.unlink()
            count += 1
        return count // 2  # json+meta = 1 entry
