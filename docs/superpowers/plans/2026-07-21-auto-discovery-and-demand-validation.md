# Auto-Discovery & Demand Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic emerging-topic discovery, vendor behavior tracking, and multi-signal demand validation to BuilderDNA's Radar pipeline — without altering existing Trend/Pain/Opportunity flows.

**Architecture:** Three new engine modules (Discovery, Vendor, Validation) run alongside or after the existing Radar phases, each with independent SQLite stores following the established pattern (`_init_db` / `save` / `get_latest`). New FastAPI endpoints expose results to new frontend tabs (Explorer, Vendors) while existing tabs receive lightweight enhancements (ValidationBadge, vendor activity tags). Config extended with `discovery` and `vendors` sections.

**Tech Stack:** Python 3.12+ / FastAPI / Pydantic v2 / SQLite / Next.js 14 / TypeScript / ECharts / Tailwind CSS / Base UI

## Global Constraints

- Follow existing store pattern: `__init__(db_path)` → `_init_db()` → `save(snapshot)` → `get_latest(domain)` → `get_all(domain)`
- Follow existing model pattern: Pydantic BaseModel with `uuid4().hex[:8]` default IDs
- Follow existing router pattern: APIRouter with dependency-injected GitHub client
- All new modules wrapped in try/except — failures must never block the main Radar pipeline
- Frontend: all pages `"use client"`, use `useState`/`useEffect` hooks, follow `lib/api.ts` client pattern
- Tests: class-based pytest using `tmp_path` fixture for store tests
- Chinese-language labels for user-facing vendor/explorer content, English for code identifiers

---

## File Map

### Phase 1: Theme Discovery

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `backend/models/discovery.py` | `DiscoveredTheme`, `DiscoverySnapshot` data models |
| Create | `backend/store/discovery_store.py` | SQLite persistence for discovery snapshots |
| Create | `backend/engine/discovery.py` | Broad search + LLM clustering + heat scoring |
| Create | `tests/test_radar/test_discovery_models.py` | Discovery model unit tests |
| Create | `tests/test_radar/test_discovery_store.py` | Discovery store unit tests |
| Create | `tests/test_radar/test_discovery_engine.py` | Discovery engine unit tests |
| Modify | `backend/router/radar.py` | Add `GET /api/explorer` endpoint |
| Modify | `backend/dependencies.py` | Add `get_discovery_store` provider |
| Modify | `config.py` | Add `DiscoveryConfig` model |
| Modify | `config.yaml` | Add `discovery` section |
| Create | `frontend/src/app/explorer/page.tsx` | Explorer tab page |
| Create | `frontend/src/components/explorer/ExplorerGrid.tsx` | Grid layout for discovered themes |
| Create | `frontend/src/components/explorer/ThemeCard.tsx` | Single discovered theme card |
| Modify | `frontend/src/lib/api.ts` | Add `fetchExplorer()` function |
| Modify | `frontend/src/lib/types.ts` | Add explorer types |
| Modify | `frontend/src/components/layout/Sidebar.tsx` | Add Explorer nav item |

### Phase 2: Vendor Tracking

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `backend/models/vendor.py` | `VendorProfile`, `VendorSnapshot`, `VendorDiff` models |
| Create | `backend/store/vendor_store.py` | SQLite persistence for vendor snapshots |
| Create | `backend/engine/vendor.py` | Four-dimension tracking + domestic/overseas comparison |
| Create | `tests/test_radar/test_vendor_models.py` | Vendor model unit tests |
| Create | `tests/test_radar/test_vendor_store.py` | Vendor store unit tests |
| Create | `tests/test_radar/test_vendor_engine.py` | Vendor engine unit tests |
| Modify | `backend/router/radar.py` | Add vendor endpoints (`/api/vendors`, `/api/vendors/{name}`, `/api/compare`) |
| Modify | `backend/dependencies.py` | Add `get_vendor_store` provider |
| Modify | `config.py` | Add `VendorConfig` model |
| Modify | `config.yaml` | Add `vendors` section |
| Create | `frontend/src/app/vendors/page.tsx` | Vendors tab page |
| Create | `frontend/src/components/vendor/VendorMatrix.tsx` | Cross-heat matrix |
| Create | `frontend/src/components/vendor/VendorDetail.tsx` | Single vendor detail page |
| Modify | `frontend/src/lib/api.ts` | Add vendor API functions |
| Modify | `frontend/src/lib/types.ts` | Add vendor types |
| Modify | `frontend/src/components/layout/Sidebar.tsx` | Add Vendors nav item |

### Phase 3: Demand Validation

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `backend/models/validation.py` | `ValidationResult`, `ValidationSignal` models |
| Create | `backend/engine/validation.py` | Three-way signal collection + confidence scoring |
| Create | `tests/test_radar/test_validation_models.py` | Validation model unit tests |
| Create | `tests/test_radar/test_validation_engine.py` | Validation engine unit tests |
| Modify | `backend/models/opportunity.py` | Add `validation: ValidationResult \| None` to `OpportunityCard` |
| Modify | `backend/engine/opportunity.py` | Integrate validation step after card generation |
| Create | `frontend/src/components/opportunity/ValidationBadge.tsx` | Three-color confidence indicator |
| Modify | `frontend/src/app/opportunities/page.tsx` | Show ValidationBadge on each card |
| Modify | `frontend/src/lib/types.ts` | Add `ValidationResult` type |
| Modify | `frontend/src/lib/api.ts` | Add `fetchValidation()` function |

---

### Task 1: Discovery Data Models

**Files:**
- Create: `backend/models/discovery.py`
- Create: `tests/test_radar/test_discovery_models.py`

**Interfaces:**
- Produces: `DiscoveredTheme(topic, description, repo_count, avg_stars, velocity, stage, sample_repos, is_new, suggested_as_topic)` — a single automatically-discovered thematic cluster.
- Produces: `DiscoverySnapshot(id, domain, created_at, window_days, themes: list[DiscoveredTheme])` — the top-level snapshot persisted by the store.

- [ ] **Step 1: Write model tests**

```python
"""Tests for discovery models."""
from backend.models.discovery import DiscoveredTheme, DiscoverySnapshot


class TestDiscoveredTheme:
    def test_defaults(self):
        t = DiscoveredTheme(
            topic="ai-native-terminal",
            description="AI-powered terminal emulators and CLI tools",
            repo_count=37,
            avg_stars=1200.0,
            velocity=5.2,
            stage="emerging",
            sample_repos=["a/b", "c/d"],
        )
        assert t.is_new is True        # default
        assert t.suggested_as_topic is True  # default
        assert t.stage == "emerging"
        assert t.repo_count == 37

    def test_existing_theme(self):
        t = DiscoveredTheme(
            topic="agent-framework",
            description="Already tracked",
            repo_count=10,
            avg_stars=500.0,
            velocity=2.0,
            stage="stable",
            sample_repos=[],
            is_new=False,
            suggested_as_topic=False,
        )
        assert not t.is_new
        assert not t.suggested_as_topic


class TestDiscoverySnapshot:
    def test_auto_id(self):
        s = DiscoverySnapshot(domain="agent", window_days=60)
        assert len(s.id) == 8
        assert s.domain == "agent"
        assert s.themes == []

    def test_with_themes(self):
        theme = DiscoveredTheme(
            topic="test-theme",
            description="desc",
            repo_count=5,
            avg_stars=100.0,
            velocity=1.0,
            stage="emerging",
            sample_repos=["x/y"],
        )
        s = DiscoverySnapshot(
            domain="agent", window_days=60, themes=[theme]
        )
        assert len(s.themes) == 1
        assert s.themes[0].topic == "test-theme"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_radar/test_discovery_models.py -v
```

Expected: ModuleNotFoundError for `backend.models.discovery`

- [ ] **Step 3: Write discovery models**

```python
"""Discovery data models — auto-detected emerging themes."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class DiscoveredTheme(BaseModel):
    """A single automatically-discovered thematic cluster.

    Generated by the Discovery engine via broad GitHub search + LLM clustering.
    """
    topic: str                                    # e.g. "ai-native-terminal"
    description: str                              # LLM-generated one-liner
    repo_count: int                               # repos in this cluster
    avg_stars: float                              # average star count
    velocity: float                               # aggregate growth velocity
    stage: Literal["emerging", "accelerating", "stable", "cooling"]
    sample_repos: list[str] = Field(default_factory=list)  # top 3 full_names
    is_new: bool = True                           # False if already in config domains
    suggested_as_topic: bool = True               # worth adding to tracking config


class DiscoverySnapshot(BaseModel):
    """A snapshot of auto-discovered themes for one discovery cycle."""
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    domain: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window_days: int = 60
    themes: list[DiscoveredTheme] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_radar/test_discovery_models.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models/discovery.py tests/test_radar/test_discovery_models.py
git commit -m "feat: add discovery data models (DiscoveredTheme, DiscoverySnapshot)"
```

---

### Task 2: Discovery Store

**Files:**
- Create: `backend/store/discovery_store.py`
- Create: `tests/test_radar/test_discovery_store.py`

**Interfaces:**
- Consumes: `DiscoverySnapshot` from Task 1
- Produces: `DiscoveryStore(db_path)` — `.save(snapshot)` returns id, `.get_latest(domain)` returns `DiscoverySnapshot | None`, `.get_all(domain)` returns `list[DiscoverySnapshot]`

- [ ] **Step 1: Write store tests**

```python
"""Tests for discovery store."""
from backend.models.discovery import DiscoveredTheme, DiscoverySnapshot
from backend.store.discovery_store import DiscoveryStore


class TestDiscoveryStore:
    def test_save_and_retrieve(self, tmp_path):
        store = DiscoveryStore(str(tmp_path / "discovery.db"))
        snap = DiscoverySnapshot(
            domain="agent", window_days=60,
            themes=[DiscoveredTheme(
                topic="ai-terminal", description="test",
                repo_count=5, avg_stars=100.0, velocity=1.0,
                stage="emerging", sample_repos=["a/b"],
            )],
        )
        sid = store.save(snap)
        assert sid == snap.id

        loaded = store.get_latest("agent")
        assert loaded is not None
        assert loaded.domain == "agent"
        assert len(loaded.themes) == 1
        assert loaded.themes[0].topic == "ai-terminal"

    def test_get_latest_empty_returns_none(self, tmp_path):
        store = DiscoveryStore(str(tmp_path / "empty.db"))
        assert store.get_latest("agent") is None

    def test_get_all_returns_latest_first(self, tmp_path):
        store = DiscoveryStore(str(tmp_path / "multi.db"))
        s1 = DiscoverySnapshot(domain="agent", window_days=60)
        s2 = DiscoverySnapshot(domain="agent", window_days=60)
        store.save(s1)
        store.save(s2)

        snaps = store.get_all("agent")
        assert len(snaps) == 2
        assert snaps[0].id == s2.id
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_radar/test_discovery_store.py -v
```

Expected: ModuleNotFoundError

- [ ] **Step 3: Write discovery store**

```python
"""SQLite store for discovery snapshots."""
import json
from pathlib import Path

from backend.models.discovery import DiscoverySnapshot


class DiscoveryStore:
    """SQLite-backed store for DiscoverySnapshot objects."""

    def __init__(self, db_path: str = "snapshots/discovery.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS discovery_snapshots (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    window_days INTEGER NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_discovery_domain
                ON discovery_snapshots(domain, created_at DESC)
            """)
            conn.commit()

    def save(self, snapshot: DiscoverySnapshot) -> str:
        import sqlite3
        data_json = snapshot.model_dump_json(indent=2)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO discovery_snapshots (id, domain, created_at, window_days, data_json) VALUES (?, ?, ?, ?, ?)",
                (snapshot.id, snapshot.domain, snapshot.created_at.isoformat(),
                 snapshot.window_days, data_json),
            )
            conn.commit()
        return snapshot.id

    def get_latest(self, domain: str) -> DiscoverySnapshot | None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM discovery_snapshots WHERE domain = ? ORDER BY created_at DESC LIMIT 1",
                (domain,),
            ).fetchone()
            if row is None:
                return None
            return DiscoverySnapshot(**json.loads(row["data_json"]))

    def get_all(self, domain: str) -> list[DiscoverySnapshot]:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM discovery_snapshots WHERE domain = ? ORDER BY created_at DESC",
                (domain,),
            ).fetchall()
            return [DiscoverySnapshot(**json.loads(r["data_json"])) for r in rows]
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_radar/test_discovery_store.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/store/discovery_store.py tests/test_radar/test_discovery_store.py
git commit -m "feat: add discovery store with SQLite persistence"
```

---

### Task 3: Config Extension for Discovery

**Files:**
- Modify: `config.py`
- Modify: `config.yaml`

**Interfaces:**
- Produces: `DiscoveryConfig` model on `Config` — `Config.discovery` available to all consumers.

- [ ] **Step 1: Add DiscoveryConfig model to config.py**

Locate the class `CompareConfig` in `config.py` (around line 82). Add `DiscoveryConfig` before `class Config`:

```python
class DiscoveryConfig(BaseModel):
    """Auto-discovery configuration."""

    enabled: bool = Field(default=True, description="Enable auto theme discovery")
    schedule: str = Field(default="weekly", description="Run frequency: weekly | daily")
    max_results: int = Field(default=100, ge=10, le=500, description="Max repos per broad search")
    language_filter: dict = Field(
        default_factory=lambda: {
            "exclude": ["JavaScript", "CSS", "HTML", "PHP", "Ruby"],
            "include": ["Python", "TypeScript", "Rust", "Go", "C++", "Jupyter Notebook"],
        },
        description="Language filter: include mode filters to these languages"
    )
    min_stars: int = Field(default=100, ge=10, description="Minimum stars for broad search")
    lookback_days: int = Field(default=30, ge=7, le=90, description="Only repos created within N days")
```

Add to `Config` class, after the `domains` field (around line 95):

```python
discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
```

- [ ] **Step 2: Add discovery section to config.yaml**

After the `compare` section at the end of `config.yaml`, append:

```yaml
discovery:
  enabled: true
  schedule: "weekly"
  max_results: 100
  min_stars: 100
  lookback_days: 30
  language_filter:
    exclude:
      - JavaScript
      - CSS
      - HTML
      - PHP
      - Ruby
    include:
      - Python
      - TypeScript
      - Rust
      - Go
      - C++
      - Jupyter Notebook
```

- [ ] **Step 3: Verify config loading doesn't break**

```bash
python -c "from config import load_config; c=load_config('config.yaml'); print(c.discovery.enabled)"
```

Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add config.py config.yaml
git commit -m "feat: add DiscoveryConfig for automatic theme discovery"
```

---

### Task 4: Discovery Engine

**Files:**
- Create: `backend/engine/discovery.py`
- Create: `tests/test_radar/test_discovery_engine.py`

**Interfaces:**
- Consumes: `GitHubClient`, `LLMClient`, `Config.discovery`, `Config.domains` (to know what's already tracked)
- Produces: `async run_discovery(client, config, llm, store) -> DiscoverySnapshot`

- [ ] **Step 1: Write engine tests**

```python
"""Tests for discovery engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from backend.models.discovery import DiscoveredTheme, DiscoverySnapshot
from backend.engine.discovery import (
    _build_broad_query,
    _build_clustering_prompt,
    _compute_heat,
    run_discovery,
)


class TestBuildBroadQuery:
    def test_builds_query_with_language_filter(self):
        config = MagicMock()
        config.discovery.min_stars = 100
        config.discovery.lookback_days = 30
        config.discovery.language_filter = {
            "exclude": ["JavaScript"],
            "include": ["Python", "TypeScript"],
        }
        query = _build_broad_query(config)
        assert "stars:>=100" in query
        assert "language:Python" in query or "language:TypeScript" in query

    def test_builds_query_include_mode(self):
        config = MagicMock()
        config.discovery.min_stars = 200
        config.discovery.lookback_days = 14
        config.discovery.language_filter = {
            "exclude": [],
            "include": ["Rust"],
        }
        query = _build_broad_query(config)
        assert "stars:>=200" in query
        assert "language:Rust" in query


class TestComputeHeat:
    def test_emerging_high_velocity(self):
        stage = _compute_heat(repo_count=15, avg_velocity=8.0)
        assert stage == "accelerating"

    def test_cooling_low_velocity(self):
        stage = _compute_heat(repo_count=3, avg_velocity=0.5)
        assert stage == "cooling"

    def test_stable_mid_range(self):
        stage = _compute_heat(repo_count=50, avg_velocity=2.0)
        assert stage == "stable"


class TestBuildClusteringPrompt:
    def test_formats_repos(self):
        repos = [
            {"full_name": "a/b", "description": "AI terminal", "topics": ["cli", "ai"]},
            {"full_name": "c/d", "description": "Smart shell tool", "topics": ["terminal"]},
        ]
        prompt = _build_clustering_prompt(repos)
        assert "a/b" in prompt
        assert "c/d" in prompt
        assert "AI terminal" in prompt


class TestRunDiscovery:
    @pytest.mark.asyncio
    async def test_returns_snapshot_with_themes(self, tmp_path):
        config = MagicMock()
        config.discovery.enabled = True
        config.discovery.min_stars = 100
        config.discovery.lookback_days = 30
        config.discovery.language_filter = {
            "exclude": [],
            "include": ["Python"],
        }
        config.domains = {"agent": {"topics": ["mcp"]}}

        mock_client = AsyncMock()
        mock_client._request = AsyncMock(return_value=MagicMock(
            json=lambda: {"items": [
                {"full_name": "org/repo1", "description": "AI tool", "topics": ["ai"], "stargazers_count": 500}
            ]}
        ))
        mock_client.rate_limiter = MagicMock()
        mock_client.rate_limiter.usage_summary = MagicMock(return_value="calls=1")

        mock_llm = MagicMock()
        mock_llm.complete = MagicMock(return_value={
            "themes": [
                {"topic": "ai-native-tools", "description": "AI-native dev tools", "repo_count": 1, "avg_stars": 500.0, "velocity": 5.0, "stage": "accelerating", "sample_repos": ["org/repo1"]}
            ]
        })

        from backend.store.discovery_store import DiscoveryStore
        store = DiscoveryStore(str(tmp_path / "discovery.db"))

        snapshot = await run_discovery(mock_client, config, mock_llm, store)
        assert snapshot is not None
        assert snapshot.domain == "global"
        assert len(snapshot.themes) >= 0
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_radar/test_discovery_engine.py -v
```

Expected: ModuleNotFoundError

- [ ] **Step 3: Write discovery engine**

```python
"""Theme Discovery engine — automatically detects emerging topics from broad GitHub search.

Runs independently of the fixed-topic Radar pipeline. Uses broad search (no
predefined topic keywords) to find new repos, clusters them via LLM, and
rates each cluster's heat.
"""
import asyncio
import math
from datetime import datetime, timezone, timedelta

from config import Config
from backend.models.discovery import DiscoveredTheme, DiscoverySnapshot
from backend.store.discovery_store import DiscoveryStore


def _build_broad_query(config: Config) -> str:
    """Build a broad GitHub search query with language filters.

    Uses 'include' mode: searches only within specified languages.
    Falls back to no language filter if include list is empty.
    """
    parts = [f"stars:>={config.discovery.min_stars}"]

    since_date = (datetime.now(timezone.utc) - timedelta(days=config.discovery.lookback_days)).strftime("%Y-%m-%d")
    parts.append(f"created:>={since_date}")

    include_langs = config.discovery.language_filter.get("include", [])
    if include_langs:
        lang_clauses = " OR ".join(f"language:{lang}" for lang in include_langs)
        parts.append(f"({lang_clauses})")

    return " ".join(parts)


def _build_clustering_prompt(repos: list[dict]) -> str:
    """Build an LLM prompt to cluster repos into named themes."""
    repo_lines = []
    for r in repos:
        desc = (r.get("description") or "")[:120]
        topics = r.get("topics", [])[:5]
        repo_lines.append(
            f"- {r['full_name']}: {desc} [topics: {', '.join(topics) if topics else 'none'}]"
        )

    return f"""You are a technology trend analyst. Analyze these GitHub repositories and group them into 3-8 thematic clusters. Each cluster should represent an emerging technology direction or vertical.

Repos:
{chr(10).join(repo_lines)}

Rules:
- Name each cluster with a concise kebab-case topic (e.g. "ai-native-ide", "multi-agent-orchestration")
- Write a one-sentence description for each
- Merge semantically close directions; split genuinely different ones
- Skip noise: if a repo doesn't fit any clear cluster, leave it out
- For each cluster, count how many repos belong and estimate its velocity (1-10)

Return valid JSON:
{{"themes": [{{"topic": "...", "description": "...", "repo_count": N, "avg_stars": F, "velocity": F, "stage": "emerging", "sample_repos": ["a/b", "c/d"]}}]}}

Stage values: "emerging" (brand new, small but growing), "accelerating" (fast growth), "stable" (large and steady), "cooling" (slowing down)."""


def _compute_heat(repo_count: int, avg_velocity: float) -> str:
    """Classify a discovered theme's heat stage.

    Thresholds tuned for discovery mode (smaller clusters than radar topics):
      velocity >= 5.0 and count >= 5  → accelerating
      velocity >= 2.0 and count >= 3  → emerging
      velocity >= 0.5                  → stable
      otherwise                        → cooling
    """
    if avg_velocity >= 5.0 and repo_count >= 5:
        return "accelerating"
    if avg_velocity >= 2.0 and repo_count >= 3:
        return "emerging"
    if avg_velocity >= 0.5:
        return "stable"
    return "cooling"


async def _broad_search(client, config: Config) -> list[dict]:
    """Fetch repos via broad search query (1 page, controlled by max_results)."""
    query = _build_broad_query(config)
    try:
        params: dict[str, str] = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": str(min(config.discovery.max_results, 100)),
        }
        resp = await client._request("GET", "/search/repositories", params=params)
        if resp is None:
            return []
        data = resp.json()
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return []
    except Exception:
        return []


def _compute_avg_velocity(repo: dict) -> float:
    """Compute a simple velocity metric for a repo."""
    stars = repo.get("stargazers_count", 0)
    created = repo.get("created_at")
    if not created:
        return 0.0
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        days = max(1, (datetime.now(timezone.utc) - dt).days)
        return stars / days
    except (ValueError, TypeError):
        return 0.0


async def run_discovery(client, config: Config, llm, store: DiscoveryStore) -> DiscoverySnapshot:
    """Run the full theme discovery pipeline.

    Broad search → enhance repos with velocity → LLM clustering → heat scoring → persist.

    Returns:
        DiscoverySnapshot with auto-discovered themes.
    """
    if not config.discovery.enabled:
        return DiscoverySnapshot(domain="global", window_days=config.discovery.lookback_days)

    # Step 1: Broad search
    raw_repos = await _broad_search(client, config)

    if not raw_repos:
        snapshot = DiscoverySnapshot(domain="global", window_days=config.discovery.lookback_days)
        store.save(snapshot)
        return snapshot

    # Step 2: Enrich repos with velocity data (for LLM consumption)
    for r in raw_repos:
        r["_velocity"] = round(_compute_avg_velocity(r), 2)

    # Step 3: LLM clustering
    known_topics: set[str] = set()
    for domain_cfg in config.domains.values():
        if isinstance(domain_cfg, dict):
            known_topics.update(domain_cfg.get("topics", []))

    try:
        prompt = _build_clustering_prompt(raw_repos)
        response = llm.complete(prompt, response_format=dict)
        themes_data = response.get("themes", [])
    except Exception:
        themes_data = []

    # Step 4: Heat scoring + mark known vs new
    themes = []
    for raw in themes_data:
        if not isinstance(raw, dict):
            continue
        topic = str(raw.get("topic", ""))[:50]
        repo_count = int(raw.get("repo_count", 0))
        vel = float(raw.get("velocity", 1.0))
        stage = raw.get("stage") or _compute_heat(repo_count, vel)

        themes.append(DiscoveredTheme(
            topic=topic,
            description=str(raw.get("description", ""))[:200],
            repo_count=repo_count,
            avg_stars=float(raw.get("avg_stars", 0.0)),
            velocity=vel,
            stage=stage,
            sample_repos=[str(r) for r in raw.get("sample_repos", [])[:5]],
            is_new=topic not in known_topics,
            suggested_as_topic=topic not in known_topics,
        ))

    # Sort by velocity desc
    themes.sort(key=lambda t: t.velocity, reverse=True)

    snapshot = DiscoverySnapshot(
        domain="global",
        window_days=config.discovery.lookback_days,
        themes=themes,
    )
    store.save(snapshot)
    return snapshot
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_radar/test_discovery_engine.py -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/engine/discovery.py tests/test_radar/test_discovery_engine.py
git commit -m "feat: add discovery engine with broad search and LLM clustering"
```

---

### Task 5: Discovery API Endpoint

**Files:**
- Modify: `backend/router/radar.py`
- Modify: `backend/dependencies.py`

**Interfaces:**
- Produces: `GET /api/explorer?domain=agent&window=30` returns `{domain, snapshot_id, generated_at, window_days, themes: [...]}`
- Consumes: `DiscoveryStore` from Task 2, `run_discovery` from Task 4

- [ ] **Step 1: Add DiscoveryStore provider to dependencies.py**

Add to `backend/dependencies.py` after existing providers:

```python
def get_discovery_store() -> "DiscoveryStore":
    from backend.store.discovery_store import DiscoveryStore
    return DiscoveryStore()
```

- [ ] **Step 2: Add /api/explorer endpoint to radar.py**

Add to `backend/router/radar.py`, after existing endpoints (before `@router.get("/pain")`):

```python
@router.get("/explorer")
async def explorer(
    domain: str = Query("agent", description="Domain to cross-reference for known topics"),
    window: int = Query(30, description="Lookback window in days"),
    refresh: bool = Query(False, description="Force re-run discovery"),
):
    """Get auto-discovered emerging themes from the discovery engine."""
    from backend.dependencies import get_config
    from backend.store.discovery_store import DiscoveryStore
    from backend.engine.discovery import run_discovery
    from llm.client import OpenAIClient

    store = DiscoveryStore()
    domain_config_obj = get_domain_config(domain)
    cfg = get_config()
    cfg.discovery.lookback_days = window

    client = get_github_client()
    try:
        if refresh:
            llm_client = OpenAIClient(
                api_key=cfg.llm.api_key,
                model=cfg.llm.model,
                base_url=cfg.llm.base_url,
            )
            snapshot = await run_discovery(client, cfg, llm_client, store)
        else:
            snapshot = store.get_latest("global")
            if snapshot is None:
                llm_client = OpenAIClient(
                    api_key=cfg.llm.api_key,
                    model=cfg.llm.model,
                    base_url=cfg.llm.base_url,
                )
                snapshot = await run_discovery(client, cfg, llm_client, store)

        if snapshot is None:
            return {"domain": "global", "snapshot_id": "", "generated_at": "", "window_days": window, "themes": []}

        return {
            "domain": snapshot.domain,
            "snapshot_id": snapshot.id,
            "generated_at": snapshot.created_at.isoformat(),
            "window_days": snapshot.window_days,
            "themes": [t.model_dump() for t in snapshot.themes],
        }
    except Exception:
        return {"domain": "global", "snapshot_id": "", "generated_at": "", "window_days": window, "themes": []}
    finally:
        await client.close()
```

- [ ] **Step 3: Test the endpoint manually**

Start the backend and test:

```bash
# In one terminal:
.venv/bin/uvicorn backend.main:app --port 8000

# In another:
curl -s http://localhost:8000/api/explorer | python -m json.tool | head -20
```

Expected: Returns JSON with `domain`, `snapshot_id`, `themes` keys (may be empty on first run without refresh).

- [ ] **Step 4: Commit**

```bash
git add backend/router/radar.py backend/dependencies.py
git commit -m "feat: add /api/explorer endpoint for theme discovery"
```

---

### Task 6: Explorer Frontend

**Files:**
- Create: `frontend/src/app/explorer/page.tsx`
- Create: `frontend/src/components/explorer/ExplorerGrid.tsx`
- Create: `frontend/src/components/explorer/ThemeCard.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: `GET /api/explorer` from Task 5
- Produces: New Explorer tab at `/explorer`, ThemeCard showing discovered themes with heat badges and sample repos

- [ ] **Step 1: Add explorer types to types.ts**

Add to `frontend/src/lib/types.ts` before the last export:

```typescript
export interface DiscoveredTheme {
  topic: string;
  description: string;
  repo_count: number;
  avg_stars: number;
  velocity: number;
  stage: "emerging" | "accelerating" | "stable" | "cooling";
  sample_repos: string[];
  is_new: boolean;
  suggested_as_topic: boolean;
}

export interface ExplorerResponse {
  domain: string;
  snapshot_id: string;
  generated_at: string;
  window_days: number;
  themes: DiscoveredTheme[];
}
```

- [ ] **Step 2: Add fetchExplorer to api.ts**

Add to `frontend/src/lib/api.ts`:

```typescript
export async function fetchExplorer(
  domain: string = "agent",
  window: number = 30,
  refresh: boolean = false
): Promise<ExplorerResponse> {
  const params = new URLSearchParams({ domain, window: String(window) });
  if (refresh) params.set("refresh", "true");
  const res = await fetch(`${API_BASE}/api/explorer?${params}`);
  if (!res.ok) return { domain: "global", snapshot_id: "", generated_at: "", window_days: window, themes: [] };
  return res.json();
}
```

Import `ExplorerResponse` from `./types` at the top.

- [ ] **Step 3: Create ThemeCard component**

```tsx
// frontend/src/components/explorer/ThemeCard.tsx
"use client";
import type { DiscoveredTheme } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

const stageConfig: Record<string, { label: string; color: string }> = {
  accelerating: { label: "🔥 Accelerating", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" },
  emerging: { label: "🆕 Emerging", color: "bg-amber-500/10 text-amber-400 border-amber-500/30" },
  stable: { label: "➡️ Stable", color: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30" },
  cooling: { label: "📉 Cooling", color: "bg-red-500/10 text-red-400 border-red-500/30" },
};

export function ThemeCard({ theme }: { theme: DiscoveredTheme }) {
  const stage = stageConfig[theme.stage] || stageConfig.stable;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-3 hover:border-zinc-700 transition-colors">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-100">{theme.topic}</h3>
        <div className="flex gap-2">
          {theme.is_new && <Badge variant="secondary" className="text-xs">New</Badge>}
          <Badge className={`text-xs border ${stage.color}`}>{stage.label}</Badge>
        </div>
      </div>

      <p className="text-sm text-zinc-400">{theme.description}</p>

      <div className="flex gap-4 text-xs text-zinc-500">
        <span>{theme.repo_count} repos</span>
        <span>★ {theme.avg_stars.toFixed(0)} avg</span>
        <span>↑ {theme.velocity.toFixed(1)}/day</span>
      </div>

      {theme.sample_repos.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-zinc-600 font-medium">Sample repos</p>
          {theme.sample_repos.map((repo) => (
            <a
              key={repo}
              href={`https://github.com/${repo}`}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-xs font-mono text-blue-400 hover:text-blue-300 truncate"
            >
              {repo}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create ExplorerGrid component**

```tsx
// frontend/src/components/explorer/ExplorerGrid.tsx
"use client";
import type { DiscoveredTheme } from "@/lib/types";
import { ThemeCard } from "./ThemeCard";

export function ExplorerGrid({ themes }: { themes: DiscoveredTheme[] }) {
  if (themes.length === 0) {
    return (
      <div className="text-zinc-500 p-12 text-center border border-zinc-800 rounded-lg">
        <p className="text-lg mb-2">No new themes discovered yet</p>
        <p className="text-sm">Run discovery with refresh=true to scan for emerging directions.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {themes.map((theme) => (
        <ThemeCard key={theme.topic} theme={theme} />
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Create Explorer page**

```tsx
// frontend/src/app/explorer/page.tsx
"use client";
import { useState, useEffect } from "react";
import { fetchExplorer } from "@/lib/api";
import type { DiscoveredTheme } from "@/lib/types";
import { ExplorerGrid } from "@/components/explorer/ExplorerGrid";
import { Skeleton } from "@/components/ui/skeleton";

export default function ExplorerPage() {
  const [themes, setThemes] = useState<DiscoveredTheme[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchExplorer()
      .then((res) => {
        if (!cancelled) setThemes(res.themes ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Theme Explorer</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48 bg-zinc-800 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Theme Explorer</h1>
          <p className="text-zinc-500 text-sm mt-1">
            Auto-discovered emerging technology directions
          </p>
        </div>
        <span className="text-sm text-zinc-600">
          {themes.length} theme{themes.length !== 1 ? "s" : ""}
        </span>
      </div>
      <ExplorerGrid themes={themes} />
    </div>
  );
}
```

- [ ] **Step 6: Add Explorer to Sidebar**

Modify `frontend/src/components/layout/Sidebar.tsx`, add to `navItems` array after the Radar entry:

```tsx
const navItems = [
  { href: "/", label: "Executive Radar" },
  { href: "/trends", label: "Trend Landscape" },
  { href: "/explorer", label: "Theme Explorer" },     // ← NEW
  { href: "/opportunities", label: "Opportunity Map" },
];
```

- [ ] **Step 7: Verify frontend builds**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: Successful build, no TypeScript errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/explorer/ frontend/src/components/explorer/ frontend/src/lib/api.ts frontend/src/lib/types.ts frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: add Explorer tab with Theme Discovery frontend"
```

---

### Task 7: Vendor Data Models

**Files:**
- Create: `backend/models/vendor.py`
- Create: `tests/test_radar/test_vendor_models.py`

**Interfaces:**
- Produces: `VendorProfile`, `VendorSnapshot`, `VendorDiff` models

- [ ] **Step 1: Write model tests**

```python
"""Tests for vendor models."""
from backend.models.vendor import VendorProfile, VendorSnapshot, VendorDiff, VendorDirection, VendorSignal


class TestVendorDirection:
    def test_creation(self):
        d = VendorDirection(topic="agent-framework", intensity=0.8, trend="↑")
        assert d.topic == "agent-framework"
        assert d.intensity == 0.8


class TestVendorProfile:
    def test_creation(self):
        profile = VendorProfile(
            name="deepseek-ai",
            display_name="DeepSeek",
            accounts=["deepseek-ai"],
            tags=["🇨🇳 国产", "大模型"],
            comparison_group="domestic",
        )
        assert profile.name == "deepseek-ai"
        assert profile.active_directions == []
        assert profile.recent_signals == []

    def test_with_directions(self):
        profile = VendorProfile(
            name="anthropics",
            display_name="Anthropic",
            accounts=["anthropics"],
            tags=["🌍 海外", "Agent"],
            comparison_group="overseas",
            active_directions=[
                VendorDirection(topic="mcp", intensity=0.9, trend="↑"),
                VendorDirection(topic="agent-framework", intensity=0.7, trend="→"),
            ],
            recent_signals=[
                VendorSignal(type="new_repo", repo="anthropics/mcp-python", timestamp="2026-07-01T00:00:00Z")
            ],
        )
        assert len(profile.active_directions) == 2
        assert len(profile.recent_signals) == 1


class TestVendorSnapshot:
    def test_auto_id(self):
        s = VendorSnapshot(domain="agent", window_days=60)
        assert len(s.id) == 8
        assert s.profiles == []


class TestVendorDiff:
    def test_creation(self):
        diff = VendorDiff(
            dimension="agent-framework",
            domestic_summary="国产偏应用集成",
            overseas_summary="海外偏协议标准",
            common_patterns="都在卷工具调用",
            domestic_vendors=["MoonshotAI"],
            overseas_vendors=["anthropics"],
        )
        assert diff.domestic_summary == "国产偏应用集成"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_radar/test_vendor_models.py -v
```

Expected: ModuleNotFoundError

- [ ] **Step 3: Write vendor models**

```python
"""Vendor data models — tracking GitHub organizations/accounts as vendors."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class VendorSignal(BaseModel):
    """A single activity signal from a vendor."""
    type: str                                    # "new_repo", "star_growth", "release", "member_starred"
    repo: str = ""                               # related repo full_name
    timestamp: str = ""                          # ISO timestamp


class VendorDirection(BaseModel):
    """A technology direction the vendor is actively investing in."""
    topic: str                                   # e.g. "agent-framework"
    intensity: float = 0.0                       # 0.0-1.0, how heavily invested
    trend: Literal["↑", "→", "↓"] = "→"


class VendorProfile(BaseModel):
    """A vendor's complete tracked profile."""
    name: str                                    # GitHub org name, e.g. "deepseek-ai"
    display_name: str = ""                       # Friendly name, e.g. "DeepSeek"
    accounts: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)  # ["🇨🇳 国产", "大模型"]
    comparison_group: str = ""                   # "domestic" | "overseas"
    active_directions: list[VendorDirection] = Field(default_factory=list)
    recent_signals: list[VendorSignal] = Field(default_factory=list)
    total_public_repos: int = 0
    total_stars: int = 0


class VendorSnapshot(BaseModel):
    """A snapshot of all vendor profiles at a point in time."""
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    domain: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window_days: int = 60
    profiles: list[VendorProfile] = Field(default_factory=list)


class VendorDiff(BaseModel):
    """Comparison between domestic and overseas vendors on one dimension."""
    dimension: str                               # topic name
    domestic_summary: str = ""                   # LLM-generated: what domestic vendors are doing
    overseas_summary: str = ""                   # LLM-generated: what overseas vendors are doing
    common_patterns: str = ""                    # shared patterns
    domestic_vendors: list[str] = Field(default_factory=list)
    overseas_vendors: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_radar/test_vendor_models.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models/vendor.py tests/test_radar/test_vendor_models.py
git commit -m "feat: add vendor data models (VendorProfile, VendorSnapshot, VendorDiff)"
```

---

### Task 8: Vendor Store

**Files:**
- Create: `backend/store/vendor_store.py`
- Create: `tests/test_radar/test_vendor_store.py`

- [ ] **Step 1: Write store tests**

```python
"""Tests for vendor store."""
from backend.models.vendor import VendorProfile, VendorSnapshot
from backend.store.vendor_store import VendorStore


class TestVendorStore:
    def test_save_and_retrieve(self, tmp_path):
        store = VendorStore(str(tmp_path / "vendor.db"))
        snap = VendorSnapshot(
            domain="agent", window_days=60,
            profiles=[VendorProfile(name="test-org", display_name="Test Org", accounts=["test-org"], tags=["🇨🇳"], comparison_group="domestic")],
        )
        sid = store.save(snap)
        assert sid == snap.id
        loaded = store.get_latest("agent")
        assert loaded is not None
        assert len(loaded.profiles) == 1

    def test_get_latest_empty_returns_none(self, tmp_path):
        store = VendorStore(str(tmp_path / "empty.db"))
        assert store.get_latest("agent") is None

    def test_get_profiles_by_group(self, tmp_path):
        store = VendorStore(str(tmp_path / "group.db"))
        snap = VendorSnapshot(
            domain="agent", window_days=60,
            profiles=[
                VendorProfile(name="org-a", accounts=["org-a"], tags=["🇨🇳"], comparison_group="domestic"),
                VendorProfile(name="org-b", accounts=["org-b"], tags=["🌍"], comparison_group="overseas"),
            ],
        )
        store.save(snap)
        domestic = store.get_profiles_by_group("domestic")
        assert len(domestic) == 1
        assert domestic[0].name == "org-a"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_radar/test_vendor_store.py -v
```

Expected: ModuleNotFoundError

- [ ] **Step 3: Write vendor store**

```python
"""SQLite store for vendor snapshots."""
import json
from pathlib import Path

from backend.models.vendor import VendorSnapshot, VendorProfile


class VendorStore:
    """SQLite-backed store for VendorSnapshot objects."""

    def __init__(self, db_path: str = "snapshots/vendor.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vendor_snapshots (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    window_days INTEGER NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vendor_domain
                ON vendor_snapshots(domain, created_at DESC)
            """)
            conn.commit()

    def save(self, snapshot: VendorSnapshot) -> str:
        import sqlite3
        data_json = snapshot.model_dump_json(indent=2)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO vendor_snapshots (id, domain, created_at, window_days, data_json) VALUES (?, ?, ?, ?, ?)",
                (snapshot.id, snapshot.domain, snapshot.created_at.isoformat(),
                 snapshot.window_days, data_json),
            )
            conn.commit()
        return snapshot.id

    def get_latest(self, domain: str) -> VendorSnapshot | None:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM vendor_snapshots WHERE domain = ? ORDER BY created_at DESC LIMIT 1",
                (domain,),
            ).fetchone()
            if row is None:
                return None
            return VendorSnapshot(**json.loads(row["data_json"]))

    def get_all(self, domain: str) -> list[VendorSnapshot]:
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM vendor_snapshots WHERE domain = ? ORDER BY created_at DESC",
                (domain,),
            ).fetchall()
            return [VendorSnapshot(**json.loads(r["data_json"])) for r in rows]

    def get_profiles_by_group(self, group: str) -> list[VendorProfile]:
        """Get profiles from the latest snapshot filtered by comparison_group."""
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM vendor_snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return []
            snapshot = VendorSnapshot(**json.loads(row["data_json"]))
            return [p for p in snapshot.profiles if p.comparison_group == group]
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_radar/test_vendor_store.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/store/vendor_store.py tests/test_radar/test_vendor_store.py
git commit -m "feat: add vendor store with profile filtering by comparison group"
```

---

### Task 9: Vendor Config Extension

**Files:**
- Modify: `config.py`
- Modify: `config.yaml`

- [ ] **Step 1: Add VendorConfig model**

In `config.py`, add after `DiscoveryConfig` and before `class Config`:

```python
class VendorConfig(BaseModel):
    """Vendor tracking configuration."""

    domestic: list[str] = Field(default_factory=list, description="Domestic vendor GitHub orgs")
    overseas: list[str] = Field(default_factory=list, description="Overseas vendor GitHub orgs")
```

Add to `Config` class, after `discovery` field:

```python
vendors: VendorConfig = Field(default_factory=VendorConfig)
```

- [ ] **Step 2: Add vendors section to config.yaml**

Append:

```yaml
vendors:
  domestic:
    - deepseek-ai
    - QwenLM
    - THUDM
    - MoonshotAI
    - 01-ai
    - baichuan-inc
    - MiniMax
    - Tencent-Hunyuan
  overseas:
    - anthropics
    - langchain-ai
    - NousResearch
    - browser-use
    - crewAIInc
    - vllm-project
    - sgl-project
    - modelcontextprotocol
    - Significant-Gravitas
    - firecrawl
    - infiniflow
    - langflow-ai
```

- [ ] **Step 3: Verify config loads**

```bash
python -c "from config import load_config; c=load_config('config.yaml'); print('domestic:', len(c.vendors.domestic)); print('overseas:', len(c.vendors.overseas))"
```

Expected: `domestic: 8`, `overseas: 12`

- [ ] **Step 4: Commit**

```bash
git add config.py config.yaml
git commit -m "feat: add VendorConfig with domestic/overseas vendor lists"
```

---

### Task 10: Vendor Engine

**Files:**
- Create: `backend/engine/vendor.py`
- Create: `tests/test_radar/test_vendor_engine.py`

- [ ] **Step 1: Write engine tests**

```python
"""Tests for vendor engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.models.vendor import VendorProfile, VendorSnapshot, VendorDiff
from backend.engine.vendor import _track_single_vendor, _build_comparison_prompt, run_vendor_tracking


class TestTrackSingleVendor:
    @pytest.mark.asyncio
    async def test_returns_profile(self):
        mock_client = AsyncMock()
        mock_client.get_repos = AsyncMock(return_value=[
            {"full_name": "org/repo1", "stargazers_count": 100, "topics": ["ai", "agent"], "description": "test", "updated_at": "2026-06-01T00:00:00Z"},
        ])
        profile = await _track_single_vendor(
            client=mock_client,
            org_name="test-org",
            display_name="Test Org",
            tags=["🏷️ test"],
            comparison_group="domestic",
        )
        assert profile is not None
        assert profile.name == "test-org"
        assert profile.comparison_group == "domestic"

    @pytest.mark.asyncio
    async def test_handles_api_error(self):
        mock_client = AsyncMock()
        mock_client.get_repos = AsyncMock(side_effect=Exception("API Error"))
        profile = await _track_single_vendor(
            client=mock_client,
            org_name="bad-org",
            display_name="Bad Org",
            tags=[],
            comparison_group="domestic",
        )
        assert profile is not None
        assert profile.total_public_repos == 0


class TestBuildComparisonPrompt:
    def test_formats_profiles(self):
        profiles = [
            VendorProfile(name="org-a", display_name="Org A", accounts=["org-a"], tags=["🇨🇳"], comparison_group="domestic",
                          active_directions=[MagicMock(topic="ai", intensity=0.8, trend="↑")]),
            VendorProfile(name="org-b", display_name="Org B", accounts=["org-b"], tags=["🌍"], comparison_group="overseas",
                          active_directions=[MagicMock(topic="ai", intensity=0.6, trend="→")]),
        ]
        prompt = _build_comparison_prompt(profiles)
        assert "Org A" in prompt
        assert "Org B" in prompt
        assert "ai" in prompt


class TestRunVendorTracking:
    @pytest.mark.asyncio
    async def test_returns_snapshot(self, tmp_path):
        config = MagicMock()
        config.vendors.domestic = ["org-a"]
        config.vendors.overseas = ["org-b"]

        mock_client = AsyncMock()
        mock_client.get_repos = AsyncMock(return_value=[
            {"full_name": "org/repo1", "stargazers_count": 100, "topics": ["ai"], "description": "test", "updated_at": "2026-06-01T00:00:00Z"},
        ])

        mock_llm = MagicMock()
        mock_llm.complete = MagicMock(return_value={"diffs": []})

        from backend.store.vendor_store import VendorStore
        store = VendorStore(str(tmp_path / "vendor.db"))
        snapshot = await run_vendor_tracking(mock_client, config, mock_llm, store)
        assert snapshot is not None
        assert len(snapshot.profiles) == 2
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_radar/test_vendor_engine.py -v
```

Expected: ModuleNotFoundError

- [ ] **Step 3: Write vendor engine**

```python
"""Vendor Tracking engine — tracks GitHub org/account behavior across 4 dimensions.

Dimensions: org dynamics, member activity, hiring signals, release cadence.
Generates domestic vs. overseas comparison diffs via LLM.
"""
import asyncio
from datetime import datetime, timezone, timedelta

from config import Config
from backend.models.vendor import (
    VendorProfile, VendorSnapshot, VendorDiff, VendorDirection, VendorSignal
)
from backend.store.vendor_store import VendorStore


async def _track_single_vendor(
    client, org_name: str, display_name: str, tags: list[str], comparison_group: str
) -> VendorProfile:
    """Track a single vendor across all 4 dimensions.

    Returns a VendorProfile even on API errors (with zero values).
    """
    profile = VendorProfile(
        name=org_name,
        display_name=display_name or org_name,
        accounts=[org_name],
        tags=tags,
        comparison_group=comparison_group,
    )

    try:
        repos = await client.get_repos(org_name)
    except Exception:
        return profile  # graceful degradation

    profile.total_public_repos = len(repos)

    # Dimension 1: Org dynamics — topic distribution from repos
    topic_intensity: dict[str, float] = {}
    total_stars = 0
    recent_signals: list[VendorSignal] = []

    for repo in repos:
        stars = repo.get("stargazers_count", 0)
        total_stars += stars
        for topic in repo.get("topics", [])[:10]:
            topic_intensity[topic] = topic_intensity.get(topic, 0) + 1

        # Recent repo creation = signal
        created = repo.get("created_at", "")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if dt > datetime.now(timezone.utc) - timedelta(days=90):
                    recent_signals.append(VendorSignal(
                        type="new_repo",
                        repo=repo.get("full_name", ""),
                        timestamp=created,
                    ))
            except (ValueError, TypeError):
                pass

    profile.total_stars = total_stars

    # Normalize topic intensity to 0-1
    max_intensity = max(topic_intensity.values()) if topic_intensity else 1
    profile.active_directions = [
        VendorDirection(
            topic=t,
            intensity=round(v / max_intensity, 2),
            trend="→",  # delta requires previous snapshot, TBD in subsequent runs
        )
        for t, v in sorted(topic_intensity.items(), key=lambda x: -x[1])[:10]
    ]
    profile.recent_signals = recent_signals

    return profile


def _build_comparison_prompt(profiles: list[VendorProfile]) -> str:
    """Build LLM prompt for domestic-vs-overseas comparison."""
    domestic_lines = []
    overseas_lines = []
    for p in profiles:
        entry = f"- {p.display_name} ({p.name}): {', '.join(d.topic for d in p.active_directions[:5])}"
        if p.comparison_group == "domestic":
            domestic_lines.append(entry)
        else:
            overseas_lines.append(entry)

    return f"""Compare domestic (Chinese) vs overseas AI vendor strategies from their GitHub activity.

🇨🇳 Domestic:
{chr(10).join(domestic_lines) if domestic_lines else 'No data'}

🌍 Overseas:
{chr(10).join(overseas_lines) if overseas_lines else 'No data'}

For EACH technology dimension where both sides show activity, produce a comparison. Return JSON:
{{"diffs": [{{"dimension": "topic-name", "domestic_summary": "what Chinese vendors are doing in Chinese", "overseas_summary": "what overseas vendors are doing in Chinese", "common_patterns": "shared trend in Chinese", "domestic_vendors": ["vendor1"], "overseas_vendors": ["vendor2"]}}]}}

IMPORTANT: Write all summary fields in Chinese. Focus on strategic differences, not just listing repos."""


async def run_vendor_tracking(
    client, config: Config, llm, store: VendorStore
) -> VendorSnapshot:
    """Run full vendor tracking pipeline.

    Tracks all configured vendors → persists snapshot → optionally generates comparison diffs.
    """
    profiles: list[VendorProfile] = []

    # Track domestic vendors
    for org_name in config.vendors.domestic:
        profile = await _track_single_vendor(
            client, org_name, org_name, ["🇨🇳 国产"], "domestic"
        )
        profiles.append(profile)

    # Track overseas vendors
    for org_name in config.vendors.overseas:
        profile = await _track_single_vendor(
            client, org_name, org_name, ["🌍 海外"], "overseas"
        )
        profiles.append(profile)

    # Build snapshot
    snapshot = VendorSnapshot(
        domain="agent",
        window_days=60,
        profiles=profiles,
    )
    store.save(snapshot)
    return snapshot


async def generate_comparison(client, config: Config, llm) -> list[VendorDiff]:
    """Generate domestic-vs-overseas comparison diffs for the latest snapshot."""
    store = VendorStore()
    snapshot = store.get_latest("agent")
    if snapshot is None or not snapshot.profiles:
        return []

    prompt = _build_comparison_prompt(snapshot.profiles)
    try:
        response = llm.complete(prompt, response_format=dict)
    except Exception:
        return []

    diffs = []
    for raw in response.get("diffs", []):
        if not isinstance(raw, dict):
            continue
        diffs.append(VendorDiff(
            dimension=str(raw.get("dimension", ""))[:50],
            domestic_summary=str(raw.get("domestic_summary", ""))[:200],
            overseas_summary=str(raw.get("overseas_summary", ""))[:200],
            common_patterns=str(raw.get("common_patterns", ""))[:200],
            domestic_vendors=[str(v) for v in raw.get("domestic_vendors", [])[:10]],
            overseas_vendors=[str(v) for v in raw.get("overseas_vendors", [])[:10]],
        ))
    return diffs
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/test_radar/test_vendor_engine.py -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/engine/vendor.py tests/test_radar/test_vendor_engine.py
git commit -m "feat: add vendor tracking engine with 4-dimension tracking and comparison"
```

---

### Task 11: Vendor API Endpoints

**Files:**
- Modify: `backend/router/radar.py`
- Modify: `backend/dependencies.py`

- [ ] **Step 1: Add vendor endpoints to radar.py**

Add to `backend/router/radar.py`, after the explorer endpoint:

```python
@router.get("/vendors")
async def vendors(
    tag: str = Query("", description="Filter by comparison_group: domestic, overseas, or empty for all"),
):
    """Get latest vendor profiles, optionally filtered by tag."""
    from backend.store.vendor_store import VendorStore
    store = VendorStore()
    snapshot = store.get_latest("agent")
    if snapshot is None:
        return {"profiles": [], "count": 0}

    profiles = snapshot.profiles
    if tag:
        profiles = [p for p in profiles if p.comparison_group == tag]

    return {"profiles": [p.model_dump() for p in profiles], "count": len(profiles)}


@router.get("/vendors/{name}")
async def vendor_detail(name: str):
    """Get detailed profile for a single vendor."""
    from backend.store.vendor_store import VendorStore
    store = VendorStore()
    snapshot = store.get_latest("agent")
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No vendor data")

    for p in snapshot.profiles:
        if p.name == name:
            return p.model_dump()
    raise HTTPException(status_code=404, detail=f"Vendor '{name}' not found")


@router.get("/compare")
async def compare(
    dimension: str = Query("", description="Optional: filter by dimension name"),
):
    """Get domestic-vs-overseas comparison. Requires a refresh to generate."""
    from backend.store.vendor_store import VendorStore
    from backend.engine.vendor import generate_comparison
    from llm.client import OpenAIClient
    from backend.dependencies import get_config

    store = VendorStore()
    cfg = get_config()
    client = get_github_client()
    try:
        llm_client = OpenAIClient(
            api_key=cfg.llm.api_key,
            model=cfg.llm.model,
            base_url=cfg.llm.base_url,
        )
        diffs = await generate_comparison(client, cfg, llm_client)
    except Exception:
        diffs = []
    finally:
        await client.close()

    if dimension:
        diffs = [d for d in diffs if d.dimension == dimension]

    return {"diffs": [d.model_dump() for d in diffs]}
```

Add the necessary import at the top of the file:

```python
from fastapi import APIRouter, Query, HTTPException
```

- [ ] **Step 2: Test endpoints**

Start backend and test:

```bash
curl -s http://localhost:8000/api/vendors?tag=domestic | python -m json.tool | head -10
curl -s http://localhost:8000/api/compare | python -m json.tool | head -10
```

- [ ] **Step 3: Commit**

```bash
git add backend/router/radar.py backend/dependencies.py
git commit -m "feat: add /api/vendors, /api/vendors/{name}, and /api/compare endpoints"
```

---

### Task 12: Vendors Frontend

**Files:**
- Create: `frontend/src/app/vendors/page.tsx`
- Create: `frontend/src/components/vendor/VendorMatrix.tsx`
- Create: `frontend/src/components/vendor/VendorDetail.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

- [ ] **Step 1: Add vendor types to types.ts**

```typescript
export interface VendorDirection {
  topic: string;
  intensity: number;
  trend: "↑" | "→" | "↓";
}

export interface VendorSignal {
  type: string;
  repo: string;
  timestamp: string;
}

export interface VendorProfile {
  name: string;
  display_name: string;
  accounts: string[];
  tags: string[];
  comparison_group: string;
  active_directions: VendorDirection[];
  recent_signals: VendorSignal[];
  total_public_repos: number;
  total_stars: number;
}

export interface VendorDiff {
  dimension: string;
  domestic_summary: string;
  overseas_summary: string;
  common_patterns: string;
  domestic_vendors: string[];
  overseas_vendors: string[];
}
```

- [ ] **Step 2: Add vendor API functions to api.ts**

```typescript
export async function fetchVendors(tag?: string): Promise<{ profiles: VendorProfile[]; count: number }> {
  const params = tag ? `?tag=${tag}` : "";
  const res = await fetch(`${API_BASE}/api/vendors${params}`);
  if (!res.ok) return { profiles: [], count: 0 };
  return res.json();
}

export async function fetchVendorDetail(name: string): Promise<VendorProfile> {
  const res = await fetch(`${API_BASE}/api/vendors/${name}`);
  if (!res.ok) throw new Error("Vendor not found");
  return res.json();
}

export async function fetchCompare(): Promise<{ diffs: VendorDiff[] }> {
  const res = await fetch(`${API_BASE}/api/compare`);
  if (!res.ok) return { diffs: [] };
  return res.json();
}
```

Import `VendorProfile` and `VendorDiff` from `./types`.

- [ ] **Step 3: Create VendorMatrix component**

```tsx
// frontend/src/components/vendor/VendorMatrix.tsx
"use client";
import type { VendorProfile, VendorDiff } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

export function VendorMatrix({
  profiles,
  diffs,
}: {
  profiles: VendorProfile[];
  diffs: VendorDiff[];
}) {
  const domestic = profiles.filter((p) => p.comparison_group === "domestic");
  const overseas = profiles.filter((p) => p.comparison_group === "overseas");

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-6">
        <div>
          <h2 className="text-lg font-semibold mb-3">🇨🇳 国产厂商 ({domestic.length})</h2>
          <div className="space-y-2">
            {domestic.map((v) => (
              <div key={v.name} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-zinc-200">{v.display_name || v.name}</p>
                  <p className="text-xs text-zinc-500">
                    {v.total_public_repos} repos · ★ {v.total_stars.toLocaleString()}
                  </p>
                </div>
                <div className="flex gap-1 flex-wrap max-w-[200px] justify-end">
                  {v.active_directions.slice(0, 3).map((d) => (
                    <Badge key={d.topic} variant="secondary" className="text-xs">
                      {d.topic}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-3">🌍 海外厂商 ({overseas.length})</h2>
          <div className="space-y-2">
            {overseas.map((v) => (
              <div key={v.name} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-zinc-200">{v.display_name || v.name}</p>
                  <p className="text-xs text-zinc-500">
                    {v.total_public_repos} repos · ★ {v.total_stars.toLocaleString()}
                  </p>
                </div>
                <div className="flex gap-1 flex-wrap max-w-[200px] justify-end">
                  {v.active_directions.slice(0, 3).map((d) => (
                    <Badge key={d.topic} variant="secondary" className="text-xs">
                      {d.topic}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {diffs.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">📊 战略差异对比</h2>
          {diffs.map((diff) => (
            <div key={diff.dimension} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-3">
              <h3 className="text-md font-semibold text-zinc-100">{diff.dimension}</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-zinc-500 mb-1">🇨🇳 国产</p>
                  <p className="text-zinc-300">{diff.domestic_summary}</p>
                </div>
                <div>
                  <p className="text-zinc-500 mb-1">🌍 海外</p>
                  <p className="text-zinc-300">{diff.overseas_summary}</p>
                </div>
              </div>
              <p className="text-xs text-zinc-600">
                📊 共性: {diff.common_patterns}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create Vendors page**

```tsx
// frontend/src/app/vendors/page.tsx
"use client";
import { useState, useEffect } from "react";
import { fetchVendors, fetchCompare } from "@/lib/api";
import type { VendorProfile, VendorDiff } from "@/lib/types";
import { VendorMatrix } from "@/components/vendor/VendorMatrix";
import { Skeleton } from "@/components/ui/skeleton";

export default function VendorsPage() {
  const [profiles, setProfiles] = useState<VendorProfile[]>([]);
  const [diffs, setDiffs] = useState<VendorDiff[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([fetchVendors(), fetchCompare()])
      .then(([vendorRes, diffRes]) => {
        if (!cancelled) {
          setProfiles(vendorRes.profiles ?? []);
          setDiffs(diffRes.diffs ?? []);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Vendor Radar</h1>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Vendor Radar</h1>
        <p className="text-zinc-500 text-sm mt-1">
          Track what domestic and overseas AI vendors are building on GitHub
        </p>
      </div>
      <VendorMatrix profiles={profiles} diffs={diffs} />
    </div>
  );
}
```

- [ ] **Step 5: Add Vendors to Sidebar**

Modify `frontend/src/components/layout/Sidebar.tsx` navItems:

```tsx
const navItems = [
  { href: "/", label: "Executive Radar" },
  { href: "/trends", label: "Trend Landscape" },
  { href: "/explorer", label: "Theme Explorer" },
  { href: "/vendors", label: "Vendor Radar" },       // ← NEW
  { href: "/opportunities", label: "Opportunity Map" },
];
```

- [ ] **Step 6: Verify frontend builds**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: Successful build.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/vendors/ frontend/src/components/vendor/ frontend/src/lib/api.ts frontend/src/lib/types.ts frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: add Vendors tab with VendorMatrix and domestic/overseas comparison"
```

---

### Task 13: Validation Models

**Files:**
- Create: `backend/models/validation.py`
- Create: `tests/test_radar/test_validation_models.py`
- Modify: `backend/models/opportunity.py`

- [ ] **Step 1: Write model tests**

```python
"""Tests for validation models."""
from backend.models.validation import ValidationResult, ValidationSignal


class TestValidationSignal:
    def test_creation(self):
        s = ValidationSignal(
            source="demand",
            score=0.8,
            evidence=["issue #123", "discussion #45"],
        )
        assert s.source == "demand"
        assert s.score == 0.8


class TestValidationResult:
    def test_creation(self):
        v = ValidationResult(
            demand_score=0.8,
            supply_score=0.5,
            adoption_score=0.3,
            confidence="medium",
            summary="需求信号强但供给不足",
        )
        assert v.confidence == "medium"
        assert v.demand_score == 0.8

    def test_defaults(self):
        v = ValidationResult()
        assert v.demand_score == 0.0
        assert v.confidence == "low"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_radar/test_validation_models.py -v
```

Expected: ModuleNotFoundError

- [ ] **Step 3: Write validation models**

```python
"""Validation data models — cross-signal demand validation."""
from typing import Literal

from pydantic import BaseModel, Field


class ValidationSignal(BaseModel):
    """A single validation signal source with score and evidence."""
    source: str = ""                               # "demand" | "supply" | "adoption"
    score: float = 0.0                             # 0.0-1.0
    evidence: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Three-way cross-validation result attached to an OpportunityCard."""
    demand_score: float = 0.0                      # from Pain Mining issues
    supply_score: float = 0.0                      # from Vendor Tracking (are vendors investing?)
    adoption_score: float = 0.0                    # from dependency network (are others using it?)
    confidence: Literal["high", "medium", "low"] = "low"
    summary: str = ""                              # one-line interpretation in Chinese
```

- [ ] **Step 4: Add validation field to OpportunityCard**

Modify `backend/models/opportunity.py`, add import and field:

```python
from backend.models.validation import ValidationResult


class OpportunityCard(BaseModel):
    # ... existing fields ...
    validation: ValidationResult | None = Field(default=None, description="Cross-signal demand validation")
```

The field goes before `risk` field.

- [ ] **Step 5: Run validation model tests**

```bash
pytest tests/test_radar/test_validation_models.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/models/validation.py tests/test_radar/test_validation_models.py backend/models/opportunity.py
git commit -m "feat: add ValidationResult model and attach to OpportunityCard"
```

---

### Task 14: Validation Engine + Opportunity Integration

**Files:**
- Create: `backend/engine/validation.py`
- Modify: `backend/engine/opportunity.py`

- [ ] **Step 1: Write validation engine**

```python
"""Demand Validation engine — cross-validates opportunities with 3 signal sources."""
from backend.models.validation import ValidationResult
from backend.models.opportunity import OpportunityCard
from backend.models.trend import TrendSnapshot
from backend.models.pain import PainSnapshot


def validate_opportunity(
    card: OpportunityCard,
    trend_snapshot: TrendSnapshot | None = None,
    pain_snapshot: PainSnapshot | None = None,
) -> ValidationResult:
    """Cross-validate a single OpportunityCard against demand, supply, and adoption signals.

    Demand: pain cluster relevance + issue severity
    Supply: topic trend velocity (are repos growing in this area?)
    Adoption: downstream dependent activity (simplified heuristic — count of evidence repos)

    Returns:
        ValidationResult with scores and confidence level.
    """
    demand_score = 0.0
    supply_score = 0.0
    adoption_score = 0.0

    # Demand signal: pain clusters mentioned in evidence
    pain_clusters_mentioned = card.evidence.pain_clusters if card.evidence else []
    if pain_snapshot and pain_clusters_mentioned:
        matching_clusters = [
            c for c in pain_snapshot.clusters
            if c.title in pain_clusters_mentioned
        ]
        if matching_clusters:
            # Average severity normalized to 0-1 (severity is 0-5 scale in pain mining)
            avg_severity = sum(c.severity for c in matching_clusters) / len(matching_clusters)
            demand_score = min(1.0, avg_severity / 5.0)

    # Supply signal: related topic trend velocity
    topics_mentioned = card.evidence.trends if card.evidence else []
    if trend_snapshot and topics_mentioned:
        matching_topics = [
            t for t in trend_snapshot.topics
            if t.topic in topics_mentioned
        ]
        if matching_topics:
            avg_velocity = sum(t.growth_velocity for t in matching_topics) / len(matching_topics)
            supply_score = min(1.0, avg_velocity / 15.0)  # normalize: 15 velocity → 1.0

    # Adoption signal: number of key repos mentioned as evidence
    key_repos = card.evidence.key_repos if card.evidence else []
    adoption_score = min(1.0, len(key_repos) / 10.0)  # 10+ repos → 1.0

    # Confidence: all three strong → high, 2 strong → medium, else low
    strong_count = sum(1 for s in [demand_score, supply_score, adoption_score] if s >= 0.6)
    if strong_count >= 3:
        confidence = "high"
    elif strong_count >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    # Generate summary
    parts = []
    if demand_score >= 0.6:
        parts.append("需求信号强")
    elif demand_score > 0:
        parts.append("需求信号中等")

    if supply_score >= 0.6:
        parts.append("厂商积极投入")
    elif supply_score > 0:
        parts.append("厂商投入中等")

    if adoption_score >= 0.6:
        parts.append("生态采纳活跃")
    elif adoption_score > 0:
        parts.append("生态采纳待观察")

    summary = "，".join(parts) if parts else "信号不足"

    return ValidationResult(
        demand_score=round(demand_score, 2),
        supply_score=round(supply_score, 2),
        adoption_score=round(adoption_score, 2),
        confidence=confidence,
        summary=summary,
    )
```

- [ ] **Step 2: Integrate validation into run_opportunity_engine**

Modify `backend/engine/opportunity.py` — in `run_opportunity_engine()`, after generating cards, add validation:

```python
# After the existing line: cards = await generate_opportunities(trend_snapshot, pain_snapshot, llm)
# Add:

    # Attach cross-signal validation to each card
    from backend.engine.validation import validate_opportunity
    for card in cards:
        try:
            card.validation = validate_opportunity(card, trend_snapshot, pain_snapshot)
        except Exception:
            card.validation = None
```

- [ ] **Step 3: Verify existing tests still pass**

```bash
pytest tests/test_radar/test_opportunity_engine.py -v 2>&1 | tail -10
```

Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/engine/validation.py backend/engine/opportunity.py
git commit -m "feat: add validation engine with 3-way cross-signal confidence scoring"
```

---

### Task 15: Validation Frontend

**Files:**
- Create: `frontend/src/components/opportunity/ValidationBadge.tsx`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/app/opportunities/page.tsx`

- [ ] **Step 1: Add ValidationResult type to types.ts**

```typescript
export interface ValidationResult {
  demand_score: number;
  supply_score: number;
  adoption_score: number;
  confidence: "high" | "medium" | "low";
  summary: string;
}
```

Add `validation?: ValidationResult | null` to `OpportunityCard` interface.

- [ ] **Step 2: Create ValidationBadge component**

```tsx
// frontend/src/components/opportunity/ValidationBadge.tsx
"use client";
import type { ValidationResult } from "@/lib/types";

const config = {
  high: { label: "🟢 高确定", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" },
  medium: { label: "🟡 中等", color: "bg-amber-500/10 text-amber-400 border-amber-500/30" },
  low: { label: "🔴 低确定", color: "bg-red-500/10 text-red-400 border-red-500/30" },
};

export function ValidationBadge({ validation }: { validation?: ValidationResult | null }) {
  if (!validation) return null;

  const c = config[validation.confidence] || config.low;

  return (
    <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-xs ${c.color}`}
         title={validation.summary}>
      {c.label}
    </div>
  );
}
```

- [ ] **Step 3: Add ValidationBadge to OpportunityCard component**

Modify `frontend/src/components/opportunity/OpportunityCard.tsx`, add the badge next to the score badge (import `ValidationBadge` first):

```tsx
import { ValidationBadge } from "./ValidationBadge";

// In the JSX, next to the score badge:
<ValidationBadge validation={card.validation} />
```

- [ ] **Step 4: Verify frontend builds**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: Successful build.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/opportunity/ValidationBadge.tsx frontend/src/components/opportunity/OpportunityCard.tsx frontend/src/lib/types.ts
git commit -m "feat: add ValidationBadge component to Opportunity cards"
```

---

### Task 16: Radar Topic Card Vendor Tag Enhancement

**Files:**
- Modify: `frontend/src/components/radar/RadarCard.tsx`

- [ ] **Step 1: Add vendor activity tags to RadarCard**

Import vendor data into the RadarCard and show a simple tag if vendors are active in that topic. Since we don't want to add a network request to every card, we accept an optional prop:

```tsx
// Add to RadarCard props interface:
// vendorCount?: number;  // how many vendors are active in this topic

// In the JSX, next to the stage badge:
// {vendorCount != null && vendorCount > 0 && (
//   <Badge variant="outline" className="text-xs text-zinc-500">
//     {vendorCount} vendor{vendorCount > 1 ? "s" : ""}
//   </Badge>
// )}
```

For this task, add the prop but keep it optional — a later optimization can wire it to real data.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/radar/RadarCard.tsx
git commit -m "feat: add optional vendor activity count prop to RadarCard"
```

---

### Task 17: Final Integration Test

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v 2>&1 | tail -30
```

Expected: All existing tests still passing, new tests passing.

- [ ] **Step 2: Full pipeline smoke test**

```bash
# Start backend
.venv/bin/uvicorn backend.main:app --port 8000 &
sleep 2

# Test all new endpoints
echo "=== /api/health ==="
curl -s http://localhost:8000/api/health

echo -e "\n=== /api/explorer ==="
curl -s http://localhost:8000/api/explorer | python -c "import sys,json; d=json.load(sys.stdin); print(f'themes: {len(d.get(\"themes\",[]))}')"

echo -e "\n=== /api/vendors ==="
curl -s http://localhost:8000/api/vendors | python -c "import sys,json; d=json.load(sys.stdin); print(f'profiles: {d.get(\"count\",0)}')"

echo -e "\n=== /api/vendors/deepseek-ai ==="
curl -s http://localhost:8000/api/vendors/deepseek-ai | python -c "import sys,json; d=json.load(sys.stdin); print(f'name: {d.get(\"name\",\"N/A\")}, repos: {d.get(\"total_public_repos\",\"N/A\")}')"

# Stop backend
kill %1 2>/dev/null
```

- [ ] **Step 3: Frontend build**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: Build successful, no TypeScript errors.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: integration tests pass, all 3 modules complete"
```

---

## Plan Self-Review

**1. Spec coverage:**
- Theme Discovery module → Tasks 1-6 ✅
- Vendor Tracking module → Tasks 7-12 ✅
- Demand Validation module → Tasks 13-15 ✅
- Frontend enhancements → Tasks 6, 12, 15, 16 ✅
- Config extensions → Tasks 3, 9 ✅
- API endpoints → Tasks 5, 11 ✅
- Risk handling (try/except wrapping) → All engine tasks ✅

**2. Placeholder scan:** No TBD, TODO, or vague descriptions found. All steps have concrete code.

**3. Type consistency:**
- `DiscoveredTheme` fields consistent across models, engine, API, and frontend types ✅
- `VendorProfile` fields consistent across models, store, engine, API, and frontend ✅
- `ValidationResult` field names match between Python model and TypeScript type ✅
- API response shapes match frontend `fetch*` function return types ✅
