"""Tests for GitHub data → Signal mapping."""

from models.signal import Signal
from collect.github.mapper import map_repo, map_star, map_commit, map_all


REPO_RAW = {
    "id": 100,
    "full_name": "alice/toolkit",
    "language": "Python",
    "topics": ["llm", "agent"],
    "description": "An LLM agent toolkit",
    "stargazers_count": 42,
    "forks_count": 5,
    "updated_at": "2026-01-15T00:00:00Z",
    "created_at": "2025-06-01T00:00:00Z",
}

STAR_RAW = {
    "id": 200,
    "full_name": "fastapi/fastapi",
    "language": "Python",
    "topics": ["web", "api"],
    "description": "FastAPI framework",
    "stargazers_count": 80000,
}

COMMIT_RAW = {
    "sha": "abc123",
    "commit": {
        "author": {"name": "Alice", "date": "2026-03-01T10:00:00Z"},
        "message": "Add MCP server implementation for tool discovery",
    },
    "html_url": "https://github.com/alice/toolkit/commit/abc123",
}


class TestMapRepo:
    def test_maps_basic_repo(self):
        s = map_repo(REPO_RAW, "alice", 5.0)
        assert isinstance(s, Signal)
        assert s.id == "gh_repo_alice_alice_toolkit"
        assert s.source == "github"
        assert s.type == "repo"
        assert s.weight == 5.0
        assert s.actor == "alice"
        assert s.target == "alice/toolkit"
        assert s.meta["language"] == "Python"
        assert "llm" in s.meta["topics"]
        assert s.raw == REPO_RAW

    def test_repo_without_language(self):
        raw = {**REPO_RAW, "language": None, "topics": []}
        s = map_repo(raw, "alice", 5.0)
        assert s.meta["language"] == ""
        assert s.meta["topics"] == []


class TestMapStar:
    def test_maps_basic_star(self):
        s = map_star(STAR_RAW, "alice", 1.0)
        assert s.id == "gh_star_200"
        assert s.type == "star"
        assert s.weight == 1.0
        assert s.target == "fastapi/fastapi"


class TestMapCommit:
    def test_maps_commit(self):
        s = map_commit(COMMIT_RAW, "alice", 3.0)
        assert s.id == "gh_commit_abc123"
        assert s.type == "commit"
        assert s.weight == 3.0
        assert s.meta["repo"] == "alice/toolkit"


class TestMapAll:
    def test_maps_all_sources(self):
        repos = [REPO_RAW]
        starred = [STAR_RAW]
        commits_by_repo = {"alice/toolkit": [COMMIT_RAW]}
        signals = map_all(repos, starred, commits_by_repo, "alice", repo=5.0, star=1.0, commit=3.0)
        assert len(signals) >= 3
        types = {s.type for s in signals}
        assert types == {"repo", "star", "commit"}

    def test_empty_inputs(self):
        signals = map_all([], [], {}, "alice", repo=5.0, star=1.0, commit=3.0)
        assert signals == []
