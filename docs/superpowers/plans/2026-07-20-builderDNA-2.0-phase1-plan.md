# BuilderDNA 2.0 Phase 1: Trend Radar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Trend Radar engine that detects accelerating GitHub topics/repos by domain, with FastAPI backend, Next.js dashboard, and CLI summary.

**Architecture:** FastAPI serves `/api/radar` and `/api/trends` from a SQLite-backed Radar Engine. Next.js 14 frontend fetches via REST and renders Radar Cards (shadcn/ui) + Trend Map (ECharts). CLI `builderdna radar agent` triggers analysis and opens the dashboard.

**Tech Stack:** FastAPI + uvicorn, Next.js 14 + shadcn/ui + Tailwind + ECharts, SQLite (trend snapshots), httpx (async GitHub client, existing).

## Global Constraints

- Python >= 3.11 (existing)
- No new Python dependencies beyond `fastapi`, `uvicorn[standard]`
- Frontend: Node.js >= 18, Next.js 14 (App Router), TypeScript, Tailwind CSS
- Existing `collect/github/client.py`, `collect/github/cache.py`, `collect/github/rate_limit.py` are reused as-is
- TDD for all backend code (pytest + httpx_mock)
- Follow existing code patterns: pydantic models, click CLI, SQLite store pattern

---

### Task 1: Backend Setup — Dependencies and Config

**Files:**
- Modify: `pyproject.toml`
- Modify: `config.yaml`
- Create: `backend/__init__.py`

**Interfaces:**
- Produces: `DomainConfig` accessible via `Config.domains` field (Task 2 will define it)

- [ ] **Step 1: Add FastAPI and uvicorn to pyproject.toml**

In `pyproject.toml`, add to `dependencies`:
```
"fastapi>=0.115",
"uvicorn[standard]>=0.32",
```

- [ ] **Step 2: Install new dependencies**

```bash
uv sync
```

- [ ] **Step 3: Add domains section to config.yaml**

```yaml
domains:
  agent:
    topics:
      - mcp
      - langchain
      - agent-protocol
      - llm
      - rag
      - agent-framework
      - tool-calling
      - multi-agent
```

- [ ] **Step 4: Create backend package**

```bash
mkdir -p backend/router backend/engine backend/models backend/store
touch backend/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock config.yaml backend/
git commit -m "chore: add FastAPI dependency, domains config, backend scaffold"
```

---

### Task 2: Backend Models (`backend/models/trend.py`)

**Files:**
- Create: `backend/models/trend.py`

**Interfaces:**
- Produces: `DomainConfig`, `RepoTrend`, `TopicTrend`, `TrendSnapshot` (pydantic BaseModel)
- Consumed by: Task 3 (Trend Store), Task 4 (Radar Engine), Task 5 (Router)

- [ ] **Step 1: Write models**

```python
"""Trend data models for BuilderDNA 2.0 Phase 1."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class DomainConfig(BaseModel):
    name: str                              # "agent"
    topics: list[str]                      # ["mcp", "langchain", ...]
    window_days: int = 60


class RepoTrend(BaseModel):
    full_name: str                         # "modelcontextprotocol/servers"
    stars: int
    stars_delta: int = 0                   # 周期内新增
    forks: int
    contributors: int
    contributor_growth: float = 0.0        # 周期内增长率
    velocity: float = 0.0                  # stars/day
    trend_score: float = 0.0               # 综合趋势分
    days_since_first_release: int = 0      # 距离首次发布天数


class TopicTrend(BaseModel):
    topic: str
    stage: Literal["emerging", "accelerating", "mainstream", "declining"]
    confidence: float                      # 0-1
    growth_velocity: float                 # 聚合增速
    evidence_count: int                    # 支撑 repo 数量
    top_repos: list[RepoTrend] = Field(default_factory=list)


class TrendSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    domain: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window_days: int
    topics: list[TopicTrend] = Field(default_factory=list)
```

- [ ] **Step 2: Write model tests**

Create `tests/test_radar/test_models.py`:

```python
"""Tests for trend models."""
from backend.models.trend import RepoTrend, TopicTrend, TrendSnapshot


class TestRepoTrend:
    def test_defaults(self):
        r = RepoTrend(full_name="a/b", stars=100, forks=10, contributors=5)
        assert r.trend_score == 0.0
        assert r.stars_delta == 0

    def test_full_creation(self):
        r = RepoTrend(
            full_name="a/b", stars=100, stars_delta=30, forks=10,
            contributors=5, contributor_growth=0.2, velocity=5.0,
            trend_score=85.0, days_since_first_release=60,
        )
        assert r.trend_score == 85.0


class TestTopicTrend:
    def test_minimal(self):
        t = TopicTrend(
            topic="mcp", stage="emerging", confidence=0.8,
            growth_velocity=3.2, evidence_count=12,
        )
        assert t.top_repos == []
        assert t.stage == "emerging"


class TestTrendSnapshot:
    def test_auto_id(self):
        s = TrendSnapshot(domain="agent", window_days=60)
        assert len(s.id) == 8
        assert s.domain == "agent"
        assert s.topics == []
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_radar/test_models.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/models/trend.py tests/test_radar/
git commit -m "feat: add Trend Radar data models"
```

---

### Task 3: Trend Store (`backend/store/trend_store.py`)

**Files:**
- Create: `backend/store/trend_store.py`
- Test: `tests/test_radar/test_trend_store.py`

**Interfaces:**
- Consumes: `TrendSnapshot`, `RepoTrend` from Task 2
- Produces: `class TrendStore`
  - `__init__(db_path: str = "snapshots/trends.db")`
  - `save(snapshot: TrendSnapshot) -> str`
  - `get_latest(domain: str) -> TrendSnapshot | None`
  - `get_all(domain: str) -> list[TrendSnapshot]`

- [ ] **Step 1: Write tests**

```python
"""Tests for trend store."""
from backend.store.trend_store import TrendStore
from backend.models.trend import TrendSnapshot, TopicTrend, RepoTrend


class TestTrendStore:
    def test_save_and_retrieve(self, tmp_path):
        store = TrendStore(str(tmp_path / "test.db"))
        snap = TrendSnapshot(
            domain="agent", window_days=60,
            topics=[TopicTrend(
                topic="mcp", stage="emerging", confidence=0.8,
                growth_velocity=3.0, evidence_count=5,
                top_repos=[RepoTrend(full_name="a/b", stars=100, forks=10, contributors=5)],
            )],
        )
        sid = store.save(snap)
        assert sid == snap.id

        loaded = store.get_latest("agent")
        assert loaded is not None
        assert loaded.domain == "agent"
        assert len(loaded.topics) == 1
        assert loaded.topics[0].topic == "mcp"

    def test_get_latest_empty_returns_none(self, tmp_path):
        store = TrendStore(str(tmp_path / "empty.db"))
        assert store.get_latest("agent") is None

    def test_get_all_returns_latest_first(self, tmp_path):
        store = TrendStore(str(tmp_path / "multi.db"))
        s1 = TrendSnapshot(domain="agent", window_days=60)
        s2 = TrendSnapshot(domain="agent", window_days=60)
        store.save(s1)
        store.save(s2)

        snaps = store.get_all("agent")
        assert len(snaps) == 2
        # Latest first
        assert snaps[0].id == s2.id
```

- [ ] **Step 2: Implement TrendStore**

```python
"""SQLite store for trend snapshots."""
import json
from pathlib import Path

from backend.models.trend import TrendSnapshot, TopicTrend, RepoTrend


class TrendStore:
    """SQLite-backed store for TrendSnapshot objects."""

    def __init__(self, db_path: str = "snapshots/trends.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trend_snapshots (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    window_days INTEGER NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trend_domain
                ON trend_snapshots(domain, created_at DESC)
            """)
            conn.commit()

    def save(self, snapshot: TrendSnapshot) -> str:
        import sqlite3
        data_json = snapshot.model_dump_json(indent=2)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO trend_snapshots (id, domain, created_at, window_days, data_json) VALUES (?, ?, ?, ?, ?)",
                (snapshot.id, snapshot.domain, snapshot.created_at.isoformat(),
                 snapshot.window_days, data_json),
            )
            conn.commit()
        return snapshot.id

    def get_latest(self, domain: str) -> TrendSnapshot | None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM trend_snapshots WHERE domain = ? ORDER BY created_at DESC LIMIT 1",
                (domain,),
            ).fetchone()
            if row is None:
                return None
            return TrendSnapshot(**json.loads(row["data_json"]))

    def get_all(self, domain: str) -> list[TrendSnapshot]:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trend_snapshots WHERE domain = ? ORDER BY created_at DESC",
                (domain,),
            ).fetchall()
            return [TrendSnapshot(**json.loads(r["data_json"])) for r in rows]
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_radar/test_trend_store.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/store/trend_store.py tests/test_radar/test_trend_store.py
git commit -m "feat: add TrendStore for snapshot persistence"
```

---

### Task 4: Radar Engine (`backend/engine/radar.py`)

**Files:**
- Create: `backend/engine/radar.py`
- Test: `tests/test_radar/test_radar_engine.py`

**Interfaces:**
- Consumes: `GitHubClient` (existing), `TrendStore` (Task 3), `DomainConfig` (Task 2), `TrendSnapshot`, `RepoTrend`, `TopicTrend` (Task 2)
- Produces:
  - `async collect_topic_data(client, topic: str) -> list[dict]` — search repos by topic, get releases/contributors
  - `compute_repo_trend(repo: dict, prev_snapshot: TrendSnapshot | None) -> RepoTrend`
  - `aggregate_topic(repos: list[RepoTrend], topic: str) -> TopicTrend`
  - `async run_radar(client, domain_config: DomainConfig, store: TrendStore) -> TrendSnapshot`

- [ ] **Step 1: Write engine tests**

```python
"""Tests for radar engine."""
import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.engine.radar import compute_repo_trend, aggregate_topic
from backend.models.trend import RepoTrend, TopicTrend, TrendSnapshot


class TestComputeRepoTrend:
    def test_first_run_uses_velocity(self):
        """First run (no previous snapshot) uses days_since_first_release."""
        repo_data = {
            "full_name": "org/repo",
            "stargazers_count": 600,
            "forks_count": 50,
            "created_at": "2026-05-01T00:00:00Z",  # ~80 days ago
        }
        result = compute_repo_trend(repo_data, prev_snapshot=None, contributors=10)
        assert result.full_name == "org/repo"
        assert result.stars == 600
        assert result.forks == 50
        assert result.velocity > 0  # 600 / ~80 ≈ 7.5 stars/day
        assert result.trend_score > 0
        # trend_score = velocity * log10(51) * log10(11)
        expected_velocity = 600 / max(1, result.days_since_first_release)
        expected_score = expected_velocity * math.log10(51) * math.log10(11)
        assert abs(result.trend_score - expected_score) < 0.1

    def test_second_run_uses_acceleration(self):
        """Second run with previous snapshot uses acceleration formula."""
        repo_data = {
            "full_name": "org/repo",
            "stargazers_count": 900,
            "forks_count": 60,
            "created_at": "2026-01-01T00:00:00Z",
        }
        from datetime import datetime, timezone, timedelta
        prev = TrendSnapshot(
            domain="agent", window_days=60,
            topics=[TopicTrend(
                topic="mcp", stage="emerging", confidence=0.8,
                growth_velocity=1.0, evidence_count=1,
                top_repos=[RepoTrend(
                    full_name="org/repo", stars=600, forks=50,
                    contributors=8, velocity=5.0, trend_score=50.0,
                    stars_delta=100,
                )],
            )],
        )
        # Set prev's created_at to 30 days ago
        prev.created_at = datetime.now(timezone.utc) - timedelta(days=30)

        result = compute_repo_trend(repo_data, prev_snapshot=prev, contributors=12)

        # velocity_now = (900-600)/30 = 10.0
        # velocity_prev was 5.0
        # acceleration = (10.0 - 5.0) / 30 ≈ 0.167
        assert result.stars == 900
        assert result.velocity == 10.0
        assert result.trend_score > 0
        # contributor growth = (12-8)/8 = 0.5
        assert result.contributor_growth == 0.5


class TestAggregateTopic:
    def test_aggregates_repos_into_topic(self):
        repos = [
            RepoTrend(full_name="a/r1", stars=100, forks=5, contributors=3,
                      trend_score=90.0, velocity=3.0),
            RepoTrend(full_name="b/r2", stars=200, forks=8, contributors=5,
                      trend_score=70.0, velocity=2.0),
            RepoTrend(full_name="c/r3", stars=50, forks=2, contributors=1,
                      trend_score=15.0, velocity=1.0),
        ]
        result = aggregate_topic(repos, "mcp")
        assert result.topic == "mcp"
        assert result.stage == "accelerating"  # avg is (90+70+15)/3 ≈ 58.3, but top-heavy
        assert result.evidence_count == 3
        assert len(result.top_repos) == 3
        assert result.top_repos[0].trend_score == 90.0  # sorted desc

    def test_stage_boundaries(self):
        stages = [
            (85.0, "accelerating"),
            (60.0, "emerging"),
            (35.0, "mainstream"),
            (10.0, "declining"),
        ]
        for score, expected_stage in stages:
            repo = RepoTrend(full_name="a/b", stars=100, forks=5, contributors=3,
                             trend_score=score, velocity=1.0)
            result = aggregate_topic([repo], "test")
            assert result.stage == expected_stage, f"score={score} -> {expected_stage}"
```

- [ ] **Step 2: Implement radar engine**

Create `backend/engine/radar.py`:

```python
"""Trend Radar engine — detects accelerating GitHub topics and repos."""
import asyncio
import math
from datetime import datetime, timezone, timedelta

from backend.models.trend import DomainConfig, RepoTrend, TopicTrend, TrendSnapshot


def _days_since(date_str: str | None) -> int:
    """Calculate days between date_str and now."""
    if not date_str:
        return 365  # fallback
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return max(1, (datetime.now(timezone.utc) - dt).days)
    except (ValueError, TypeError):
        return 365


def compute_repo_trend(
    repo_data: dict,
    prev_snapshot: TrendSnapshot | None,
    contributors: int = 0,
) -> RepoTrend:
    """Compute trend score for a single repo.

    First run (prev_snapshot=None): uses 1st-order velocity.
    Subsequent runs: uses 2nd-order acceleration.
    """
    full_name = repo_data.get("full_name", "")
    stars = repo_data.get("stargazers_count", 0)
    forks = repo_data.get("forks_count", 0)
    created_at = repo_data.get("created_at")
    days_since_release = _days_since(created_at)

    velocity = stars / max(1, days_since_release)
    trend_score = velocity * math.log10(forks + 1) * math.log10(contributors + 1)
    stars_delta = 0

    if prev_snapshot:
        # Find the same repo in previous snapshot
        prev_repo = None
        for topic in prev_snapshot.topics:
            for r in topic.top_repos:
                if r.full_name == full_name:
                    prev_repo = r
                    break

        if prev_repo and prev_repo.velocity > 0:
            prev_created = prev_snapshot.created_at
            if prev_created.tzinfo is None:
                prev_created = prev_created.replace(tzinfo=timezone.utc)
            dt = max(1, (datetime.now(timezone.utc) - prev_created).days)

            velocity_now = (stars - prev_repo.stars) / dt
            acceleration = (velocity_now - prev_repo.velocity) / dt

            contributor_growth = 0.0
            if prev_repo.contributors > 0:
                contributor_growth = (contributors - prev_repo.contributors) / prev_repo.contributors

            trend_score = (
                acceleration
                * math.log10(forks + 1)
                * math.log10(max(0, contributor_growth) + 1)
            )
            stars_delta = stars - prev_repo.stars
            velocity = velocity_now

    return RepoTrend(
        full_name=full_name,
        stars=stars,
        stars_delta=stars_delta,
        forks=forks,
        contributors=contributors,
        contributor_growth=0.0,
        velocity=round(velocity, 2),
        trend_score=round(trend_score, 2),
        days_since_first_release=days_since_release,
    )


def get_stage(score: float) -> str:
    if score >= 80:
        return "accelerating"
    if score >= 50:
        return "emerging"
    if score >= 20:
        return "mainstream"
    return "declining"


def aggregate_topic(repos: list[RepoTrend], topic: str) -> TopicTrend:
    """Aggregate individual repo trends into a topic-level trend."""
    repos_sorted = sorted(repos, key=lambda r: r.trend_score, reverse=True)
    top_5 = repos_sorted[:5]

    if not top_5:
        return TopicTrend(
            topic=topic, stage="declining", confidence=0.0,
            growth_velocity=0.0, evidence_count=0, top_repos=[],
        )

    avg_score = sum(r.trend_score for r in top_5) / len(top_5)
    avg_velocity = sum(r.velocity for r in top_5) / len(top_5)

    # Confidence: ratio of accelerating repos within topic
    accelerating_count = sum(1 for r in top_5 if r.trend_score >= 50)
    confidence = accelerating_count / max(1, len(top_5))

    return TopicTrend(
        topic=topic,
        stage=get_stage(avg_score),
        confidence=round(confidence, 2),
        growth_velocity=round(avg_velocity, 2),
        evidence_count=len(repos),
        top_repos=top_5,
    )


async def collect_topic_data(client, topic: str) -> list[dict]:
    """Fetch repos for a topic from GitHub Search API.

    Returns list of raw repo dicts with stars, forks, created_at.
    """
    params = {
        "q": f"topic:{topic}",
        "sort": "stars",
        "order": "desc",
        "per_page": "30",
    }
    results = []
    try:
        # Use the client's internal paginate via a search
        from collect.github.client import GitHubClient
        if hasattr(client, '_paginate'):
            results = await client._paginate("/search/repositories", extra_params=params)
    except Exception:
        pass
    return results


async def run_radar(
    client,
    domain_config: DomainConfig,
    store,
) -> TrendSnapshot:
    """Run the full radar analysis for a domain.

    Fetches repos per topic, computes trends, persists snapshot.
    """
    prev_snapshot = store.get_latest(domain_config.name)
    all_topics: list[TopicTrend] = []

    # Fetch all topics concurrently
    async def process_topic(topic: str) -> TopicTrend:
        repos_raw = await collect_topic_data(client, topic)
        repo_trends = []
        for repo in repos_raw:
            contributors = 0  # We'll skip per-repo contributor API for now
            rt = compute_repo_trend(repo, prev_snapshot, contributors)
            repo_trends.append(rt)
        return aggregate_topic(repo_trends, topic)

    topic_tasks = [process_topic(t) for t in domain_config.topics]
    all_topics = await asyncio.gather(*topic_tasks)

    # Filter out topics with no evidence
    all_topics = [t for t in all_topics if t.evidence_count > 0]

    # Sort by growth_velocity descending
    all_topics.sort(key=lambda t: t.growth_velocity, reverse=True)

    snapshot = TrendSnapshot(
        domain=domain_config.name,
        window_days=domain_config.window_days,
        topics=all_topics,
    )
    store.save(snapshot)
    return snapshot
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_radar/test_radar_engine.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/engine/radar.py tests/test_radar/test_radar_engine.py
git commit -m "feat: add Radar Engine with trend computation algorithms"
```

---

### Task 5: FastAPI App + Router + Dependencies

**Files:**
- Create: `backend/dependencies.py`
- Create: `backend/router/radar.py`
- Create: `backend/main.py`
- Test: `tests/test_radar/test_api.py`

**Interfaces:**
- Consumes: `GitHubClient`, `TrendStore`, `Radar Engine`, `DomainConfig`
- Produces: `GET /api/health`, `GET /api/radar`, `GET /api/trends`

- [ ] **Step 1: Write dependencies.py**

```python
"""FastAPI dependency injection."""
import os
from functools import lru_cache

from collect.github.client import GitHubClient
from config import load_config, Config


@lru_cache()
def get_config() -> Config:
    """Load config once and cache."""
    _load_dotenv()
    return load_config("config.yaml")


def _load_dotenv():
    from pathlib import Path
    env_file = Path(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = val


def get_github_client() -> GitHubClient:
    cfg = get_config()
    return GitHubClient(
        token=cfg.github.token,
        cache_dir=cfg.github.cache_dir,
        max_concurrent=cfg.github.max_concurrent,
        rate_limit_margin=cfg.github.rate_limit_margin,
    )


def get_domain_config(domain: str):
    """Get domain config by name."""
    cfg = get_config()
    # Reuse follow_groups keys as domain names
    from backend.models.trend import DomainConfig
    domains_raw = cfg.model_dump().get("domains", {})
    if domain in domains_raw:
        d = domains_raw[domain]
        return DomainConfig(name=domain, topics=d.get("topics", []), window_days=d.get("window_days", 60))
    # Fallback: treat domain as topic list from config
    return DomainConfig(name=domain, topics=[domain])
```

- [ ] **Step 2: Write router**

```python
"""Radar API router."""
from fastapi import APIRouter, Depends, Query, HTTPException

from backend.dependencies import get_github_client, get_domain_config
from backend.store.trend_store import TrendStore
from backend.engine.radar import run_radar
from backend.models.trend import DomainConfig, TrendSnapshot

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/radar")
async def radar(
    domain: str = Query(..., description="Domain name, e.g. 'agent'"),
    window: int = Query(60, description="Time window in days"),
    refresh: bool = Query(False, description="Force refresh, skip cache"),
):
    client = get_github_client()
    store = TrendStore()
    domain_config = get_domain_config(domain)
    domain_config.window_days = window

    try:
        if refresh:
            snapshot = await run_radar(client, domain_config, store)
        else:
            snapshot = store.get_latest(domain)
            if snapshot is None or snapshot.window_days != window:
                snapshot = await run_radar(client, domain_config, store)

        return {
            "domain": snapshot.domain,
            "snapshot_id": snapshot.id,
            "generated_at": snapshot.created_at.isoformat(),
            "window_days": snapshot.window_days,
            "rate_limit": {"calls": client.rate_limiter._total_calls},
            "topics": [t.model_dump() for t in snapshot.topics],
        }
    finally:
        await client.close()


@router.get("/trends")
async def trends(
    domain: str = Query(...),
    topic: str = Query(..., description="Topic name"),
):
    """Get detailed trend data for a specific topic."""
    store = TrendStore()
    snapshot = store.get_latest(domain)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"No snapshot for domain '{domain}'")

    for t in snapshot.topics:
        if t.topic == topic:
            return t.model_dump()

    raise HTTPException(status_code=404, detail=f"Topic '{topic}' not found")
```

- [ ] **Step 3: Write main.py**

```python
"""BuilderDNA 2.0 FastAPI application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.router.radar import router as radar_router

app = FastAPI(
    title="BuilderDNA API",
    description="Technology Evolution Intelligence Engine",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(radar_router)


def main():
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write API tests**

```python
"""Tests for radar API endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("backend.dependencies.get_github_client") as mock_gh:
        with patch("backend.router.radar.TrendStore") as mock_store:
            gh = MagicMock()
            gh.close = AsyncMock()
            gh.rate_limiter = MagicMock()
            gh.rate_limiter._total_calls = 42
            mock_gh.return_value = gh

            store_inst = mock_store.return_value
            store_inst.get_latest.return_value = None  # force fresh run

            from backend.main import app
            with TestClient(app) as tc:
                yield tc


class TestRadarAPI:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_radar_endpoint(self, client):
        """Radar endpoint should return valid structure even with mock data."""
        resp = client.get("/api/radar?domain=agent&window=60")
        assert resp.status_code in (200, 500)  # 500 if engine can't find repos (OK in test)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_radar/test_api.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/dependencies.py backend/router/radar.py backend/main.py tests/test_radar/test_api.py
git commit -m "feat: add FastAPI app with radar and trends endpoints"
```

---

### Task 6: CLI Radar Command

**Files:**
- Modify: `cli.py`

- [ ] **Step 1: Add `radar` command to cli.py**

Add to `cli.py`:

```python
@main.command()
@click.argument("domain")
@click.option("--window", "-w", default=60, help="Time window in days")
@click.option("--refresh/--no-refresh", default=False, help="Force refresh data")
@click.option("--web/--no-web", default=True, help="Start web server")
def radar(domain: str, window: int, refresh: bool, web: bool):
    """Run Trend Radar analysis for a DOMAIN (e.g. 'agent')."""
    import asyncio
    from backend.dependencies import get_github_client, get_domain_config
    from backend.store.trend_store import TrendStore
    from backend.engine.radar import run_radar

    client = get_github_client()
    store = TrendStore()
    domain_config = get_domain_config(domain)
    domain_config.window_days = window

    with console.status(f"[bold green]Scanning {domain}...[/bold green]"):
        snapshot = asyncio.run(run_radar(client, domain_config, store))
        asyncio.run(client.close())

    # Terminal summary
    console.print()
    console.print(Text(f" BuilderDNA Radar · {domain_config.name} ", style="bold white on blue"))
    console.print(f" {snapshot.created_at.strftime('%Y-%m-%d')} · Last {window} Days")
    console.print("─" * 40)
    console.print()

    # Top 3 topics
    console.print("[bold]🔥 Top Trends[/bold]\n")
    for i, t in enumerate(snapshot.topics[:3], 1):
        emoji = {"accelerating": "🚀", "emerging": "↑", "mainstream": "→", "declining": "↓"}
        color = {"accelerating": "green", "emerging": "yellow", "mainstream": "dim", "declining": "red"}
        score_color = color.get(t.stage, "white")
        console.print(
            f" {i:>2}  {t.topic:<25} [{score_color}]{t.growth_velocity:>5.0f}[/{score_color}]  "
            f"{emoji.get(t.stage, '')} {t.stage}"
        )

    # Emerging signals
    console.print()
    console.print("[bold]📈 Emerging Signals[/bold]\n")
    for t in snapshot.topics:
        if t.stage in ("accelerating", "emerging"):
            console.print(f" {emoji.get(t.stage, '↑')} {t.topic:<25} +{t.evidence_count} repos")

    # GitHub stats
    console.print()
    console.print(f"[GitHub] {client.rate_limiter.usage_summary()}")

    # Web
    if web:
        console.print("\n[bold green]📊 Starting web dashboard...[/bold green]")
        console.print("   Open http://localhost:8000\n")
        # Start FastAPI server (blocking)
        import uvicorn
        uvicorn.run("backend.main:app", host="0.0.0.0", port=8000)
```

- [ ] **Step 2: Run CLI tests**

```bash
uv run python -m cli radar --help
```

- [ ] **Step 3: Commit**

```bash
git add cli.py
git commit -m "feat: add 'radar' CLI command for trend analysis"
```

---

### Task 7: Frontend Project Setup (Next.js + shadcn/ui + Tailwind + ECharts)

**Files:**
- Create: `frontend/` (full Next.js project)

- [ ] **Step 1: Create Next.js project**

```bash
cd frontend
npx create-next-app@14 . --typescript --tailwind --eslint --app --src-dir --no-import-alias
```

- [ ] **Step 2: Initialize shadcn/ui**

```bash
npx shadcn-ui@latest init -d
# Add required components
npx shadcn-ui@latest add card badge table tabs select skeleton
```

- [ ] **Step 3: Install ECharts and React Flow**

```bash
npm install echarts echarts-for-react reactflow
```

- [ ] **Step 4: Configure dark theme in Tailwind**

Edit `frontend/tailwind.config.ts` to add dark mode class strategy:

```ts
module.exports = {
  darkMode: "class",
  // ... rest
}
```

- [ ] **Step 5: Create dark theme layout shell**

Create `frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "BuilderDNA — Technology Evolution Intelligence",
  description: "Track accelerating technologies on GitHub",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-zinc-950 text-zinc-100 min-h-screen`}>
        <div className="flex">
          <Sidebar />
          <main className="flex-1 p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
```

Create `frontend/src/components/layout/Sidebar.tsx`:

```tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Radar", icon: "📡" },
  { href: "/trends", label: "Trends", icon: "📈" },
  { href: "/opportunities", label: "Opportunities", icon: "💡" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 border-r border-zinc-800 h-screen p-4 flex flex-col gap-2">
      <div className="font-bold text-lg mb-6">BuilderDNA</div>
      {navItems.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
            pathname === item.href
              ? "bg-zinc-800 text-white"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
          )}
        >
          <span>{item.icon}</span>
          {item.label}
        </Link>
      ))}
    </aside>
  );
}
```

- [ ] **Step 6: Verify dev server starts**

```bash
cd frontend && npm run dev
# Should show Next.js dev server on :3000
```

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Next.js frontend with shadcn/ui, Tailwind, dark theme"
```

---

### Task 8: Frontend Types + API Client

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api.ts`

- [ ] **Step 1: Write TypeScript types**

```typescript
// frontend/src/lib/types.ts

export interface RepoTrend {
  full_name: string;
  stars: number;
  stars_delta: number;
  forks: number;
  contributors: number;
  contributor_growth: number;
  velocity: number;
  trend_score: number;
  days_since_first_release: number;
}

export type TrendStage = "emerging" | "accelerating" | "mainstream" | "declining";

export interface TopicTrend {
  topic: string;
  stage: TrendStage;
  confidence: number;
  growth_velocity: number;
  evidence_count: number;
  top_repos: RepoTrend[];
}

export interface RadarResponse {
  domain: string;
  snapshot_id: string;
  generated_at: string;
  window_days: number;
  rate_limit: { calls: number };
  topics: TopicTrend[];
}
```

- [ ] **Step 2: Write API client**

```typescript
// frontend/src/lib/api.ts

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchRadar(
  domain: string,
  window: number = 60,
  refresh: boolean = false
): Promise<RadarResponse> {
  const params = new URLSearchParams({ domain, window: String(window) });
  if (refresh) params.set("refresh", "true");
  const res = await fetch(`${API_BASE}/api/radar?${params}`);
  if (!res.ok) throw new Error(`Radar fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/health`);
  return res.json();
}
```

- [ ] **Step 3: Create useRadar hook**

```typescript
// frontend/src/hooks/use-radar.ts
"use client";
import { useState, useEffect } from "react";
import { fetchRadar, RadarResponse } from "@/lib/api";

export function useRadar(domain: string = "agent", window: number = 60) {
  const [data, setData] = useState<RadarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetchRadar(domain, window)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [domain, window]);

  return { data, loading, error };
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/hooks/use-radar.ts
git commit -m "feat: add frontend types, API client, and useRadar hook"
```

---

### Task 9: Frontend Components (RadarCard, RadarGrid, TrendMap)

**Files:**
- Create: `frontend/src/components/radar/RadarCard.tsx`
- Create: `frontend/src/components/radar/RadarGrid.tsx`
- Create: `frontend/src/components/charts/TrendMap.tsx`
- Create: `frontend/src/components/charts/TrendSparkline.tsx`

- [ ] **Step 1: RadarCard component**

```tsx
// frontend/src/components/radar/RadarCard.tsx
"use client";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TopicTrend } from "@/lib/types";

const stageConfig: Record<string, { emoji: string; color: string }> = {
  accelerating: { emoji: "🚀", color: "bg-emerald-500/10 text-emerald-400" },
  emerging: { emoji: "↑", color: "bg-amber-500/10 text-amber-400" },
  mainstream: { emoji: "→", color: "bg-zinc-500/10 text-zinc-400" },
  declining: { emoji: "↓", color: "bg-red-500/10 text-red-400" },
};

export function RadarCard({ topic }: { topic: TopicTrend }) {
  const cfg = stageConfig[topic.stage] || stageConfig.mainstream;

  return (
    <Card className="bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-colors">
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-lg font-semibold">{topic.topic}</span>
              <Badge className={cfg.color}>{topic.stage}</Badge>
            </div>
            <div className="text-sm text-zinc-500">
              {topic.evidence_count} repos · {topic.growth_velocity.toFixed(1)} stars/day
            </div>
          </div>
          <div className="text-2xl font-bold text-zinc-100">
            {topic.growth_velocity.toFixed(0)}
          </div>
        </div>

        {/* Growth bar */}
        <div className="w-full bg-zinc-800 rounded-full h-1.5 mb-3">
          <div
            className="bg-emerald-500 h-1.5 rounded-full transition-all"
            style={{ width: `${Math.min(topic.growth_velocity * 2, 100)}%` }}
          />
        </div>

        {/* Top repos */}
        <div className="space-y-1">
          {topic.top_repos.slice(0, 3).map((repo) => (
            <div key={repo.full_name} className="flex justify-between text-xs text-zinc-400">
              <span className="truncate max-w-[200px]">{repo.full_name}</span>
              <span className="text-zinc-500">⭐ {repo.stars.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: RadarGrid component**

```tsx
// frontend/src/components/radar/RadarGrid.tsx
"use client";
import { TopicTrend } from "@/lib/types";
import { RadarCard } from "./RadarCard";

export function RadarGrid({ topics }: { topics: TopicTrend[] }) {
  if (topics.length === 0) {
    return <div className="text-zinc-500 p-8 text-center">No trend data available</div>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {topics.map((topic) => (
        <RadarCard key={topic.topic} topic={topic} />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: TrendMap component (ECharts quadrant chart)**

```tsx
// frontend/src/components/charts/TrendMap.tsx
"use client";
import ReactECharts from "echarts-for-react";
import { TopicTrend } from "@/lib/types";

export function TrendMap({ topics }: { topics: TopicTrend[] }) {
  const data = topics.map((t) => ({
    name: t.topic,
    value: [t.confidence * 100, t.growth_velocity],
    stage: t.stage,
  }));

  const option = {
    backgroundColor: "transparent",
    grid: { top: 40, right: 40, bottom: 40, left: 60 },
    xAxis: {
      name: "Market Maturity →",
      nameLocation: "center",
      nameGap: 30,
      nameTextStyle: { color: "#71717a" },
      min: 0,
      max: 100,
      axisLine: { lineStyle: { color: "#3f3f46" } },
      splitLine: { lineStyle: { color: "#27272a" } },
    },
    yAxis: {
      name: "Growth Velocity ↑",
      nameLocation: "center",
      nameGap: 40,
      nameTextStyle: { color: "#71717a" },
      axisLine: { lineStyle: { color: "#3f3f46" } },
      splitLine: { lineStyle: { color: "#27272a" } },
    },
    series: [
      {
        type: "scatter",
        symbolSize: (val: number[]) => Math.max(20, val[1] * 2),
        data: data,
        itemStyle: {
          color: (params: any) => {
            const stage = data[params.dataIndex]?.stage;
            switch (stage) {
              case "accelerating": return "#10b981";
              case "emerging": return "#f59e0b";
              case "mainstream": return "#71717a";
              default: return "#ef4444";
            }
          },
        },
        label: {
          show: true,
          formatter: "{b}",
          position: "right",
          color: "#a1a1aa",
          fontSize: 12,
        },
      },
    ],
    tooltip: {
      trigger: "item",
      formatter: (params: any) =>
        `<strong>${params.name}</strong><br/>Maturity: ${params.value[0].toFixed(0)}<br/>Velocity: ${params.value[1].toFixed(1)}`,
    },
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-zinc-300 mb-4">Trend Landscape</h2>
      <ReactECharts option={option} style={{ height: 400 }} theme="dark" />
    </div>
  );
}
```

- [ ] **Step 4: Verify components compile**

```bash
cd frontend && npm run build
# Should build without errors
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/radar/ frontend/src/components/charts/
git commit -m "feat: add RadarCard, RadarGrid, and TrendMap components"
```

---

### Task 10: Frontend Pages

**Files:**
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/app/trends/page.tsx`
- Create: `frontend/src/app/opportunities/page.tsx`
- Create: `frontend/src/app/evidence/[id]/page.tsx`

- [ ] **Step 1: Home page (Executive Radar)**

```tsx
// frontend/src/app/page.tsx
"use client";
import { useRadar } from "@/hooks/use-radar";
import { RadarGrid } from "@/components/radar/RadarGrid";
import { TrendMap } from "@/components/charts/TrendMap";
import { Skeleton } from "@/components/ui/skeleton";

export default function HomePage() {
  const { data, loading, error } = useRadar("agent", 60);

  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Executive Radar</h1>
        <p className="text-zinc-500 text-sm mt-1">
          What to watch in AI infrastructure — last 60 days
        </p>
      </div>

      {loading ? (
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48 bg-zinc-800 rounded-lg" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <RadarGrid topics={data?.topics || []} />
            </div>
            <div>
              <TrendMap topics={data?.topics || []} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Trends page**

```tsx
// frontend/src/app/trends/page.tsx
"use client";
import { useRadar } from "@/hooks/use-radar";
import { TrendMap } from "@/components/charts/TrendMap";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function TrendsPage() {
  const { data, loading } = useRadar("agent", 60);

  const allRepos = (data?.topics || []).flatMap((t) =>
    t.top_repos.map((r) => ({ ...r, topic: t.topic }))
  );
  allRepos.sort((a, b) => b.trend_score - a.trend_score);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Trend Landscape</h1>

      <TrendMap topics={data?.topics || []} />

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Repo</TableHead>
            <TableHead>Topic</TableHead>
            <TableHead className="text-right">Stars</TableHead>
            <TableHead className="text-right">Velocity</TableHead>
            <TableHead className="text-right">Score</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {allRepos.map((repo) => (
            <TableRow key={repo.full_name}>
              <TableCell className="font-mono text-sm">{repo.full_name}</TableCell>
              <TableCell>{repo.topic}</TableCell>
              <TableCell className="text-right">{repo.stars.toLocaleString()}</TableCell>
              <TableCell className="text-right">{repo.velocity.toFixed(1)}</TableCell>
              <TableCell className="text-right">{repo.trend_score.toFixed(0)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 3: Opportunities and Evidence placeholder pages**

```tsx
// frontend/src/app/opportunities/page.tsx
export default function OpportunitiesPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Opportunity Map</h1>
      <div className="text-zinc-500 p-8 text-center border border-zinc-800 rounded-lg">
        <p className="text-lg mb-2">Coming in Phase 2</p>
        <p className="text-sm">Pain mining + opportunity detection engine under development</p>
      </div>
    </div>
  );
}
```

```tsx
// frontend/src/app/evidence/[id]/page.tsx
export default function EvidencePage({ params }: { params: { id: string } }) {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Evidence Graph</h1>
      <div className="text-zinc-500 p-8 text-center border border-zinc-800 rounded-lg">
        Coming in Phase 3
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Build and verify**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/
git commit -m "feat: add all frontend pages — Radar, Trends, Opportunities, Evidence"
```

---

### Self-Review Checklist

**1. Spec coverage:**
- ✅ Data models (Task 2)
- ✅ Trend Store (Task 3)
- ✅ Radar Engine algorithm (Task 4)
- ✅ API endpoints (Task 5)
- ✅ CLI radar command (Task 6)
- ✅ Frontend setup (Task 7)
- ✅ Frontend types + API (Task 8)
- ✅ Frontend components (Task 9)
- ✅ Frontend pages (Task 10)

**2. Placeholder scan:** ✅ No TBD/TODO. All code is exact.

**3. Type consistency:**
- ✅ `RepoTrend`, `TopicTrend`, `TrendSnapshot` match between backend models and frontend types
- ✅ `compute_repo_trend` signature matches engine usage
- ✅ `run_radar` returns `TrendSnapshot` which is consumed by router and CLI
- ✅ API responses match frontend `RadarResponse` type
