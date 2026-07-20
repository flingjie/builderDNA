"""Tests for HTTP response cache."""
import time
from collect.github.cache import CacheStore, _get_ttl


class TestCacheStore:
    def test_cache_miss_returns_none(self, tmp_path):
        cache = CacheStore(tmp_path)
        result = cache.get("GET", "/users/alice")
        assert result is None

    def test_cache_set_and_get(self, tmp_path):
        cache = CacheStore(tmp_path)
        headers = {"etag": '"abc123"', "content-type": "application/json"}
        body = '{"login": "alice"}'
        cache.set("GET", "/users/alice", None, 200, headers, body)

        result = cache.get("GET", "/users/alice")
        assert result is not None
        assert result[0] == 200
        assert result[2] == body

    def test_cache_key_varies_by_params(self, tmp_path):
        cache = CacheStore(tmp_path)
        cache.set("GET", "/users/alice/repos", {"page": "1"}, 200, {}, "[]")
        cache.set("GET", "/users/alice/repos", {"page": "2"}, 200, {}, '[{"id":1}]')

        r1 = cache.get("GET", "/users/alice/repos", {"page": "1"})
        r2 = cache.get("GET", "/users/alice/repos", {"page": "2"})
        assert r1[2] == "[]"
        assert r2[2] == '[{"id":1}]'

    def test_cache_miss_on_stale(self, tmp_path, monkeypatch):
        cache = CacheStore(tmp_path)
        cache.set("GET", "/users/alice", None, 200, {}, '{"login":"alice"}')

        # Fake time to be well past TTL (24h for /users/)
        future = time.time() + 90000
        monkeypatch.setattr(time, "time", lambda f=future: f)

        result = cache.get("GET", "/users/alice")
        assert result is None

    def test_get_etag(self, tmp_path):
        cache = CacheStore(tmp_path)
        cache.set("GET", "/users/alice", None, 200, {"etag": '"xyz"'}, "{}")
        assert cache.get_etag("GET", "/users/alice") == '"xyz"'

    def test_get_etag_miss(self, tmp_path):
        cache = CacheStore(tmp_path)
        assert cache.get_etag("GET", "/users/alice") is None

    def test_update_from_304(self, tmp_path):
        cache = CacheStore(tmp_path)
        cache.set("GET", "/users/alice", None, 200, {"etag": '"old"'}, '{"login":"alice"}')
        cache.update_from_304("GET", "/users/alice", None, {"etag": '"new"'})

        assert cache.get_etag("GET", "/users/alice") == '"new"'
        # Body should still be retrievable
        result = cache.get("GET", "/users/alice")
        assert result is not None and result[2] == '{"login":"alice"}'

    def test_clear(self, tmp_path):
        cache = CacheStore(tmp_path)
        cache.set("GET", "/a", None, 200, {}, "a")
        cache.set("GET", "/b", None, 200, {}, "b")
        assert cache.clear() == 2
        assert cache.get("GET", "/a") is None

    def test_corrupt_cache_returns_none(self, tmp_path):
        cache = CacheStore(tmp_path)
        # Write invalid JSON
        key = cache._cache_key("GET", "/corrupt")
        cache._json_path(key).write_text("not json")
        cache._meta_path(key).write_text('{"etag":"x","cached_at":9999999999,"ttl":3600}')
        assert cache.get("GET", "/corrupt") is None


class TestTTLs:
    def test_user_endpoint_24h(self):
        assert _get_ttl("/users/alice") == 86400

    def test_repos_endpoint_1h(self):
        assert _get_ttl("/users/alice/repos") == 3600

    def test_search_endpoint_5m(self):
        assert _get_ttl("/search/repositories") == 300

    def test_default_1h(self):
        assert _get_ttl("/unknown/endpoint") == 3600
