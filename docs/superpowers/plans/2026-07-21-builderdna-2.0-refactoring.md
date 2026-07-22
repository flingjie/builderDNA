# BuilderDNA 2.0 Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor BuilderDNA from a dual-pipeline architecture into a unified Signal Graph + Intelligence Engine system with Human Control Plane and Builder Memory — without breaking the existing FastAPI backend or Next.js frontend.

**Architecture:** Three-phase incremental migration. Phase 1 adds Signal Lake + Collector alongside existing code (no deletions). Phase 2 migrates analysis engines to `intelligence/` and removes deprecated code. Phase 3 wraps everything in LangGraph orchestration with HCP feedback gates. Each phase produces a fully runnable system.

**Tech Stack:** Python 3.12+ / uv / Pydantic v2 / Typer / LangGraph / DuckDB / ChromaDB / HDBSCAN / NetworkX / httpx / SQLite / FastAPI / Next.js 14

## Global Constraints

- **每步可运行** — the system must be fully functional after each task commit, not just after each phase
- SQLite stores follow existing pattern: `__init__(db_path)` → `_init_db()` → `save(snapshot)` → `get_latest(domain)`
- New models are Pydantic v2 BaseModel with `uuid4().hex[:8]` default IDs
- All new engine modules wrapped in try/except — failures never block the pipeline
- Follow existing `collect/github/client.py` pattern for HTTP (httpx + rate limiting + caching)
- Tests: class-based pytest, `tmp_path` for store tests
- Chinese for user-facing CLI text, English for code identifiers and comments
- Frontend is NOT modified in this refactoring plan

---

## File Map

### Phase 1: Base Layer (New files alongside existing, NO deletions)

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `signal/__init__.py` | Package init |
| Create | `signal/models.py` | Unified `Signal`, aggregate views (`TopicTrend`, `RepoTrend`, `VendorProfile`, `DiscoveredTheme`) |
| Create | `signal/store.py` | `SignalStore` — SQLite (transactions) + DuckDB (analytics) |
| Create | `signal/graph.py` | `SignalGraph` — NetworkX MultiDiGraph builder + query API |
| Create | `collector/__init__.py` | Package init |
| Create | `collector/github/__init__.py` | Package init |
| Create | `collector/github/client.py` | Copy from `collect/github/client.py` (unchanged) |
| Create | `collector/github/cache.py` | Copy from `collect/github/cache.py` (unchanged) |
| Create | `collector/github/repo.py` | Repo & Release collector |
| Create | `collector/github/issue.py` | Issue & Discussion collector |
| Create | `collector/github/star_history.py` | Star time-series collector |
| Create | `collector/normalizer.py` | GitHub API dict → `Signal` unified normalizer |
| Create | `llm/prompts/__init__.py` | Package init |
| Create | `llm/prompts/trend.py` | Trend detection prompt templates |
| Create | `llm/prompts/pain.py` | Pain mining prompt templates |
| Create | `llm/prompts/opportunity.py` | Opportunity generation prompt templates |
| Create | `intelligence/__init__.py` | Package init |
| Create | `intelligence/trend/__init__.py` | Package init |
| Create | `intelligence/pain/__init__.py` | Package init |
| Create | `intelligence/opportunity/__init__.py` | Package init |
| Create | `control_plane/__init__.py` | Package init |
| Create | `pipeline/__init__.py` | Package init |
| Modify | `pyproject.toml` | Add new dependencies |
| Create | `tests/test_signal/__init__.py` | Package init |
| Create | `tests/test_signal/test_models.py` | Signal model tests |
| Create | `tests/test_signal/test_store.py` | SignalStore tests |
| Create | `tests/test_signal/test_graph.py` | SignalGraph tests |
| Create | `tests/test_collector/__init__.py` | Package init |
| Create | `tests/test_collector/test_normalizer.py` | Normalizer tests |

### Phase 2: Engine Layer Migration (Create + Delete)

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `intelligence/trend/detector.py` | Merged Trend engine (from radar.py + discovery.py + vendor.py) |
| Create | `intelligence/trend/velocity.py` | Second-derivative velocity computation |
| Create | `intelligence/pain/models.py` | PainIssue, PainCluster, PainSnapshot models |
| Create | `intelligence/pain/issue_miner.py` | Issue fetch + embedding (from pain.py) |
| Create | `intelligence/pain/cluster.py` | HDBSCAN clustering |
| Create | `intelligence/pain/severity.py` | Pain score computation |
| Create | `intelligence/opportunity/models.py` | OpportunityCard + CriticReview + ValidationResult |
| Create | `intelligence/opportunity/generator.py` | LLM opportunity generation (merged from 2 sources) |
| Create | `intelligence/opportunity/critic.py` | Critic Agent — independent LLM review |
| Create | `intelligence/opportunity/scorer.py` | Multi-factor scoring + validation |
| Create | `tests/test_intelligence/__init__.py` | Package init |
| Create | `tests/test_intelligence/test_trend/__init__.py` | Package init |
| Create | `tests/test_intelligence/test_trend/test_detector.py` | Trend detector tests |
| Create | `tests/test_intelligence/test_trend/test_velocity.py` | Velocity computation tests |
| Create | `tests/test_intelligence/test_pain/__init__.py` | Package init |
| Create | `tests/test_intelligence/test_pain/test_cluster.py` | Clustering tests |
| Create | `tests/test_intelligence/test_pain/test_severity.py` | Severity tests |
| Create | `tests/test_intelligence/test_opportunity/__init__.py` | Package init |
| Create | `tests/test_intelligence/test_opportunity/test_critic.py` | Critic tests |
| Create | `tests/test_intelligence/test_opportunity/test_scorer.py` | Scorer tests |
| Delete | `insight/` | Replaced by Signal Graph + HDBSCAN |
| Delete | `opportunity/` | Merged to intelligence/opportunity |
| Delete | `follow/` | Merged to intelligence/trend |
| Delete | `backend/engine/discovery.py` | Merged to intelligence/trend |
| Delete | `backend/engine/vendor.py` | Merged to intelligence/trend |
| Delete | `backend/store/discovery_store.py` | DuckDB replaces |
| Delete | `backend/store/vendor_store.py` | DuckDB replaces |
| Delete | `backend/models/discovery.py` | Merged to signal/models.py |
| Delete | `backend/models/vendor.py` | Merged to signal/models.py |
| Delete | `backend/models/validation.py` | Merged to intelligence/opportunity/models.py |
| Delete | `models/insight.py` | Replaced by PainCluster + TopicTrend |
| Modify | `backend/engine/radar.py` | Redirect to `intelligence/trend/detector.py` |
| Modify | `backend/engine/pain.py` | Redirect to `intelligence/pain/` |
| Modify | `backend/engine/opportunity.py` | Redirect to `intelligence/opportunity/generator.py` |
| Modify | `backend/router/radar.py` | Update imports to intelligence/ |

### Phase 3: LangGraph + HCP + CLI Migration

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `pipeline/graph.py` | LangGraph DAG orchestration |
| Create | `pipeline/state.py` | `AgentState` typed dict |
| Create | `pipeline/gates.py` | Feedback Gate middleware |
| Create | `control_plane/hcp.py` | Human Control Plane main |
| Create | `control_plane/policy.py` | Trigger Score computation |
| Create | `control_plane/memory.py` | Builder Memory (SQLite + ChromaDB) |
| Create | `cli/__init__.py` | Package init |
| Create | `cli/main.py` | Typer CLI (builderdna radar/opportunities/analyze) |
| Create | `cli/formatters.py` | Rich table/Markdown formatters |
| Create | `report/__init__.py` | Package init |
| Create | `report/builder_report.py` | Migrated from output/ |
| Create | `tests/test_control_plane/__init__.py` | Package init |
| Create | `tests/test_control_plane/test_policy.py` | Trigger Score tests |
| Create | `tests/test_control_plane/test_memory.py` | Builder Memory tests |
| Create | `tests/test_pipeline/__init__.py` | Package init |
| Create | `tests/test_pipeline/test_graph.py` | LangGraph integration test |
| Delete | `pipeline.py` | Replaced by pipeline/graph.py |
| Delete | `cli.py` | Replaced by cli/main.py |
| Delete | `output/` | Replaced by report/ |

---

### Task 1: Install New Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Interfaces:**
- Produces: All new packages available via `uv sync`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Add to the `[project]` dependencies list in `pyproject.toml`:

```toml
dependencies = [
    # ... existing deps ...
    "typer>=0.12",
    "langgraph>=0.2",
    "duckdb>=1.0",
    "chromadb>=0.5",
    "hdbscan>=0.8",
    "networkx>=3.3",
    "scikit-learn>=1.5",
]
```

- [ ] **Step 2: Sync dependencies**

```bash
uv sync
```

Expected: All new packages installed successfully.

- [ ] **Step 3: Verify imports work**

```bash
uv run python -c "import typer, langgraph, duckdb, chromadb, hdbscan, networkx, sklearn; print('All OK')"
```

Expected: `All OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add 2.0 dependencies (typer, langgraph, duckdb, chromadb, hdbscan, networkx, scikit-learn)"
```

---

### Task 2: Unified Signal Model

**Files:**
- Create: `signal/__init__.py`
- Create: `signal/models.py`
- Create: `tests/test_signal/__init__.py`
- Create: `tests/test_signal/test_models.py`

**Interfaces:**
- Produces: `Signal(id, source, type, actor, target_repo, timestamp, velocity, impact, payload)`
- Produces: `AggregateTopicTrend`, `AggregateRepoTrend`, `AggregateVendorProfile` (views over Signal)
- Migrates from: `models/signal.py`, `backend/models/trend.py`, `backend/models/discovery.py`, `backend/models/vendor.py`

- [ ] **Step 1: Write model tests**

```python
"""Tests for unified Signal model and aggregate views."""
from datetime import datetime, timezone
from signal.models import Signal, AggregateTopicTrend, AggregateRepoTrend


class TestSignal:
    def test_minimal_signal(self):
        s = Signal(
            id="sig-001",
            source="github",
            type="repo_created",
            actor="test-dev",
            target_repo="org/repo",
            timestamp=datetime.now(timezone.utc),
        )
        assert s.source == "github"
        assert s.velocity == 0.0
        assert s.impact == 0.0
        assert s.payload == {}

    def test_full_signal(self):
        s = Signal(
            id="sig-002",
            source="github",
            type="star_growth",
            actor="star-user",
            target_repo="org/popular",
            timestamp=datetime.now(timezone.utc),
            velocity=15.5,
            impact=0.8,
            payload={"stars_before": 100, "stars_after": 200},
        )
        assert s.velocity == 15.5
        assert s.payload["stars_before"] == 100

    def test_signal_type_validation(self):
        valid_types = [
            "repo_created", "star_growth", "issue_opened",
            "issue_commented", "release", "fork", "discussion",
        ]
        for t in valid_types:
            s = Signal(
                id="s",
                source="github",
                type=t,
                actor="a",
                target_repo="a/b",
                timestamp=datetime.now(timezone.utc),
            )
            assert s.type == t


class TestAggregateTopicTrend:
    def test_from_signals(self):
        signals = [
            Signal(
                id="s1", source="github", type="repo_created",
                actor="dev", target_repo="org/repo1",
                timestamp=datetime.now(timezone.utc), velocity=5.0,
                payload={"topics": ["agent", "mcp"]},
            ),
            Signal(
                id="s2", source="github", type="star_growth",
                actor="dev2", target_repo="org/repo2",
                timestamp=datetime.now(timezone.utc), velocity=3.0,
                payload={"topics": ["agent", "langchain"]},
            ),
        ]
        trends = AggregateTopicTrend.from_signals(signals)
        assert len(trends) > 0


class TestAggregateRepoTrend:
    def test_defaults(self):
        r = AggregateRepoTrend(full_name="a/b", stars=100, velocity=5.0)
        assert r.stars == 100
        assert r.trend_score == 0.0
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_signal/test_models.py -v
```

Expected: ModuleNotFoundError

- [ ] **Step 3: Write signal/models.py**

```python
"""Unified Signal model and aggregate views for BuilderDNA 2.0.

All upstream data (GitHub API responses) normalizes into Signal.
Aggregate views (TopicTrend, RepoTrend, VendorProfile) are computed
from Signal collections, not stored as independent models.
"""
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Signal(BaseModel):
    """Unified immutable event. All data sources normalize to this."""

    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    source: Literal["github"] = "github"
    type: Literal[
        "repo_created",      # new repository
        "star_growth",       # star increase event
        "issue_opened",      # issue created (contains body text)
        "issue_commented",   # issue discussion activity
        "release",           # version release
        "fork",              # fork event
        "discussion",        # discussion created
    ]
    actor: str                                # developer or org login
    target_repo: str                          # full_name e.g. "org/repo"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    velocity: float = 0.0                     # instantaneous growth rate
    impact: float = 0.0                       # influence weight (0-1)
    payload: dict[str, Any] = Field(default_factory=dict)  # raw snapshot


class AggregateRepoTrend(BaseModel):
    """Computed view: velocity and trend for a single repo."""
    full_name: str
    stars: int = 0
    stars_delta: int = 0
    forks: int = 0
    contributors: int = 0
    contributor_growth: float = 0.0
    velocity: float = 0.0
    trend_score: float = 0.0
    days_since_first_release: int = 0
    topics: list[str] = Field(default_factory=list)


class AggregateTopicTrend(BaseModel):
    """Computed view: aggregated trend for a topic."""
    topic: str
    stage: Literal["emerging", "accelerating", "mainstream", "declining"] = "emerging"
    confidence: float = 0.0
    growth_velocity: float = 0.0
    evidence_count: int = 0
    top_repos: list[AggregateRepoTrend] = Field(default_factory=list)

    @classmethod
    def from_signals(cls, signals: list[Signal]) -> list["AggregateTopicTrend"]:
        """Build topic trends from a flat list of signals."""
        topic_signals: dict[str, list[Signal]] = {}
        for s in signals:
            for topic in s.payload.get("topics", []):
                topic_signals.setdefault(topic, []).append(s)

        results = []
        for topic, sigs in topic_signals.items():
            velocities = [s.velocity for s in sigs if s.velocity > 0]
            avg_vel = sum(velocities) / len(velocities) if velocities else 0.0
            confidence = min(1.0, len(sigs) / 10.0)
            results.append(cls(
                topic=topic,
                confidence=round(confidence, 2),
                growth_velocity=round(avg_vel, 2),
                evidence_count=len(sigs),
            ))
        results.sort(key=lambda t: t.growth_velocity, reverse=True)
        return results


class AggregateVendorProfile(BaseModel):
    """Computed view: vendor activity abstracted from signals."""
    name: str
    display_name: str = ""
    tags: list[str] = Field(default_factory=list)
    comparison_group: str = ""
    active_topics: list[str] = Field(default_factory=list)
    total_repos: int = 0
    total_stars: int = 0
    recent_signal_count: int = 0
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_signal/test_models.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add signal/ tests/test_signal/
git commit -m "feat: add unified Signal model with aggregate views"
```

---

### Task 3: Signal Store (SQLite + DuckDB)

**Files:**
- Create: `signal/store.py`
- Create: `tests/test_signal/test_store.py`

**Interfaces:**
- Consumes: `Signal` from Task 2
- Produces: `SignalStore(db_path)` — `.insert(signals)`, `.query_velocity(top_n, days)`, `.get_topic_trends(days)`, `.create_snapshot(accounts)`, `.save_snapshot(snapshot_id)`

- [ ] **Step 1: Write store tests**

```python
"""Tests for SignalStore (SQLite transactions + DuckDB analytics)."""
import pytest
from datetime import datetime, timezone, timedelta
from signal.models import Signal
from signal.store import SignalStore


class TestSignalStore:
    def test_insert_and_query(self, tmp_path):
        store = SignalStore(str(tmp_path / "signal.db"))
        signals = [
            Signal(
                id=f"sig-{i}", source="github", type="star_growth",
                actor="dev", target_repo="org/repo",
                timestamp=datetime.now(timezone.utc) - timedelta(days=i),
                velocity=10.0 - i, impact=0.5,
                payload={"topics": ["agent"]},
            )
            for i in range(5)
        ]
        count = store.insert(signals)
        assert count == 5
        assert store.count() == 5

    def test_query_velocity(self, tmp_path):
        store = SignalStore(str(tmp_path / "velocity.db"))
        signals = [
            Signal(
                id=f"sig-{i}", source="github", type="star_growth",
                actor="dev", target_repo="org/repo",
                timestamp=datetime.now(timezone.utc) - timedelta(days=i),
                velocity=float(10 - i), impact=0.5,
            )
            for i in range(50)
        ]
        store.insert(signals)
        results = store.query_velocity(top_n=5, days=30)
        assert len(results) <= 5

    def test_get_topic_trends(self, tmp_path):
        store = SignalStore(str(tmp_path / "topics.db"))
        signals = [
            Signal(
                id=f"sig-{i}", source="github", type="repo_created",
                actor="dev", target_repo=f"org/repo{i}",
                timestamp=datetime.now(timezone.utc),
                velocity=5.0,
                payload={"topics": ["agent", "mcp"]},
            )
            for i in range(10)
        ]
        store.insert(signals)
        trends = store.get_topic_trends(days=30)
        assert len(trends) >= 1

    def test_empty_store(self, tmp_path):
        store = SignalStore(str(tmp_path / "empty.db"))
        assert store.count() == 0
        assert store.query_velocity(5, 30) == []
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_signal/test_store.py -v
```

Expected: ModuleNotFoundError

- [ ] **Step 3: Write signal/store.py**

```python
"""SignalStore — SQLite for transactions + DuckDB for analytics.

SQLite stores snapshot metadata and signal blobs (existing pattern).
DuckDB provides time-series analytics queries (velocity, topic trends).
"""
import json
import math
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone, timedelta

from signal.models import Signal, AggregateTopicTrend


class SignalStore:
    """Dual-engine signal storage.

    SQLite: transactional — snapshots, feedback, audit log.
    DuckDB: analytical — time series, aggregations, trending queries.
    """

    def __init__(self, db_path: str = "snapshots/signals.db"):
        import sqlite3
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                type TEXT NOT NULL,
                actor TEXT NOT NULL,
                target_repo TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                velocity REAL DEFAULT 0,
                impact REAL DEFAULT 0,
                payload_json TEXT DEFAULT '{}'
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_timestamp
            ON signals(timestamp DESC)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(type)
        """)
        self._conn.commit()

    def insert(self, signals: list[Signal]) -> int:
        rows = [
            (s.id, s.source, s.type, s.actor, s.target_repo,
             s.timestamp.isoformat(), s.velocity, s.impact,
             json.dumps(s.payload))
            for s in signals
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO signals (id, source, type, actor, target_repo, timestamp, velocity, impact, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]

    def query_velocity(self, top_n: int = 10, days: int = 30) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self._conn.execute(
            "SELECT target_repo, AVG(velocity) as avg_v, COUNT(*) as cnt FROM signals WHERE timestamp >= ? AND velocity > 0 GROUP BY target_repo ORDER BY avg_v DESC LIMIT ?",
            (since, top_n),
        ).fetchall()
        return [{"target_repo": r["target_repo"], "avg_velocity": round(r["avg_v"], 2), "count": r["cnt"]} for r in rows]

    def get_topic_trends(self, days: int = 30) -> list[AggregateTopicTrend]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self._conn.execute(
            "SELECT payload_json, velocity FROM signals WHERE timestamp >= ?",
            (since,),
        ).fetchall()

        topic_velocities: dict[str, list[float]] = {}
        for row in rows:
            payload = json.loads(row["payload_json"])
            velocity = row["velocity"]
            for topic in payload.get("topics", []):
                topic_velocities.setdefault(topic, []).append(velocity)

        results = []
        for topic, velocities in topic_velocities.items():
            valid = [v for v in velocities if v > 0]
            avg_v = sum(valid) / len(valid) if valid else 0.0
            results.append(AggregateTopicTrend(
                topic=topic,
                confidence=min(1.0, len(velocities) / 10.0),
                growth_velocity=round(avg_v, 2),
                evidence_count=len(velocities),
            ))
        results.sort(key=lambda t: t.growth_velocity, reverse=True)
        return results

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_signal/test_store.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add signal/store.py tests/test_signal/test_store.py
git commit -m "feat: add SignalStore with SQLite transactions and analytics queries"
```

---

### Task 4: Signal Graph (NetworkX)

**Files:**
- Create: `signal/graph.py`
- Create: `tests/test_signal/test_graph.py`

**Interfaces:**
- Consumes: `Signal` from Task 2, `SignalStore` from Task 3
- Produces: `SignalGraph` — `.build_from_signals(signals)`, `.get_co_occurring_topics(min_weight)`, `.find_bridging_repos(topic_a, topic_b)`, `.get_developer_influence(login)`

- [ ] **Step 1: Write graph tests**

```python
"""Tests for SignalGraph (NetworkX)."""
from datetime import datetime, timezone
from signal.models import Signal
from signal.graph import SignalGraph


class TestSignalGraph:
    def test_builds_graph_from_signals(self):
        signals = [
            Signal(
                id="s1", source="github", type="repo_created",
                actor="dev1", target_repo="org/repo1",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["agent", "mcp"]},
            ),
            Signal(
                id="s2", source="github", type="repo_created",
                actor="dev2", target_repo="org/repo2",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["agent", "rag"]},
            ),
        ]
        graph = SignalGraph()
        graph.build_from_signals(signals)
        assert graph.node_count() > 0
        assert graph.edge_count() > 0

    def test_co_occurring_topics(self):
        signals = [
            Signal(
                id=f"s{i}", source="github", type="repo_created",
                actor="dev", target_repo=f"org/repo{i}",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["agent", "mcp"]},
            )
            for i in range(5)
        ] + [
            Signal(
                id=f"sa{i}", source="github", type="repo_created",
                actor="dev", target_repo=f"org/other{i}",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["rag", "vector"]},
            )
            for i in range(2)
        ]
        graph = SignalGraph()
        graph.build_from_signals(signals)
        pairs = graph.get_co_occurring_topics(min_weight=2)
        assert len(pairs) >= 1
        assert ("agent", "mcp") in pairs or ("mcp", "agent") in pairs

    def test_developer_influence(self):
        signals = []
        for i in range(10):
            signals.append(Signal(
                id=f"d1-{i}", source="github", type="repo_created",
                actor="influential_dev", target_repo=f"org/repo{i}",
                timestamp=datetime.now(timezone.utc), impact=0.9,
            ))
        for i in range(2):
            signals.append(Signal(
                id=f"d2-{i}", source="github", type="star_growth",
                actor="regular_dev", target_repo="org/other",
                timestamp=datetime.now(timezone.utc), impact=0.1,
            ))
        graph = SignalGraph()
        graph.build_from_signals(signals)
        inf = graph.get_developer_influence("influential_dev")
        reg = graph.get_developer_influence("regular_dev")
        assert inf > reg

    def test_find_bridging_repos(self):
        signals = [
            Signal(
                id="bridge", source="github", type="repo_created",
                actor="dev", target_repo="org/bridge",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["agent", "blockchain"]},
            ),
            Signal(
                id="agent-only", source="github", type="repo_created",
                actor="dev", target_repo="org/agent-tool",
                timestamp=datetime.now(timezone.utc),
                payload={"topics": ["agent"]},
            ),
        ]
        graph = SignalGraph()
        graph.build_from_signals(signals)
        bridges = graph.find_bridging_repos("agent", "blockchain")
        assert "org/bridge" in bridges

    def test_empty_graph(self):
        graph = SignalGraph()
        graph.build_from_signals([])
        assert graph.node_count() == 0
        assert graph.get_co_occurring_topics(1) == []
        assert graph.find_bridging_repos("a", "b") == []
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_signal/test_graph.py -v
```

Expected: ModuleNotFoundError

- [ ] **Step 3: Write signal/graph.py**

```python
"""Signal Graph — NetworkX-based relationship graph for BuilderDNA signals.

Builds a MultiDiGraph from Signal collections. Supports:
- Co-occurring topic detection
- Bridging repo discovery (repos connecting two distinct topics)
- Developer influence scoring via PageRank
- Subgraph export for individual engines
"""
from collections import defaultdict

import networkx as nx


class SignalGraph:
    """In-memory NetworkX MultiDiGraph built from Signal collections.

    Not persisted — rebuilt each run from Signal Lake. Signal Lake (DuckDB/SQLite)
    is the source of truth. The graph is an in-memory index for relationship queries.
    """

    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def build_from_signals(self, signals: list) -> None:
        """Build the full graph from signal list.

        Adds nodes for developers, repos, topics.
        Adds edges for CREATES, STARS, BELONGS_TO relationships.
        """
        self.graph.clear()

        # Track edge weights for co-occurrence
        topic_co_occurrence: dict[tuple[str, str], int] = defaultdict(int)
        repo_topics: dict[str, set[str]] = defaultdict(set)

        for sig in signals:
            # Ensure nodes exist
            if sig.actor and sig.actor not in self.graph:
                self.graph.add_node(sig.actor, kind="developer")
            if sig.target_repo and sig.target_repo not in self.graph:
                self.graph.add_node(sig.target_repo, kind="repo")

            # Developer → Repo edges
            if sig.type == "repo_created":
                self.graph.add_edge(sig.actor, sig.target_repo, kind="CREATES", weight=1.0)
            elif sig.type == "star_growth":
                self.graph.add_edge(sig.actor, sig.target_repo, kind="STARS", weight=sig.impact)

            # Topic nodes from payload
            topics = sig.payload.get("topics", [])
            for topic in topics:
                if topic not in self.graph:
                    self.graph.add_node(topic, kind="topic")
                self.graph.add_edge(sig.target_repo, topic, kind="BELONGS_TO", weight=sig.velocity)
                repo_topics[sig.target_repo].add(topic)

            # Co-occurrence: every pair of topics on the same signal
            topic_list = list(topics)
            for i in range(len(topic_list)):
                for j in range(i + 1, len(topic_list)):
                    pair = tuple(sorted([topic_list[i], topic_list[j]]))
                    topic_co_occurrence[pair] += 1

        # Store co-occurrence on graph for fast lookup
        for (t1, t2), weight in topic_co_occurrence.items():
            self.graph.add_edge(t1, t2, kind="CO_OCCURS", weight=weight)

        # Store repo-topic index on graph
        self.graph.graph["repo_topics"] = dict(repo_topics)

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def get_co_occurring_topics(self, min_weight: int = 3) -> list[tuple[str, str]]:
        """Return topic pairs that frequently appear together."""
        result = []
        for u, v, data in self.graph.edges(data=True):
            if data.get("kind") == "CO_OCCURS" and data.get("weight", 0) >= min_weight:
                result.append((u, v))
        return result

    def find_bridging_repos(self, topic_a: str, topic_b: str) -> list[str]:
        """Find repos that have BOTH of the given topics."""
        repo_topics = self.graph.graph.get("repo_topics", {})
        return [
            repo for repo, topics in repo_topics.items()
            if topic_a in topics and topic_b in topics
        ]

    def get_developer_influence(self, login: str) -> float:
        """Compute developer influence via PageRank."""
        if self.graph.number_of_nodes() == 0:
            return 0.0
        try:
            pr = nx.pagerank(self.graph, weight="weight")
            return round(pr.get(login, 0.0), 4)
        except Exception:
            return 0.0

    def export_for_engine(self, engine: str) -> dict:
        """Export relevant subgraph data for a specific engine.

        Args:
            engine: "trend" | "pain" | "opportunity"

        Returns:
            dict with engine-specific data.
        """
        if engine == "trend":
            return {
                "co_occurring_topics": self.get_co_occurring_topics(min_weight=2),
                "topic_count": sum(1 for n, d in self.graph.nodes(data=True) if d.get("kind") == "topic"),
            }
        elif engine == "opportunity":
            repo_topics = self.graph.graph.get("repo_topics", {})
            return {
                "repo_count": len(repo_topics),
                "bridging_repos": [
                    (repo, list(topics))
                    for repo, topics in repo_topics.items()
                    if len(topics) >= 2
                ][:10],
            }
        return {}
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_signal/test_graph.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add signal/graph.py tests/test_signal/test_graph.py
git commit -m "feat: add SignalGraph with NetworkX co-occurrence, bridging, and PageRank"
```

---

### Task 5: Collector GitHub Modules (Repo, Issue, Star History)

**Files:**
- Create: `collector/__init__.py`
- Create: `collector/github/__init__.py`
- Create: `collector/github/client.py` (copy from `collect/github/client.py`)
- Create: `collector/github/cache.py` (copy from `collect/github/cache.py`)
- Create: `collector/github/repo.py`
- Create: `collector/github/issue.py`
- Create: `collector/github/star_history.py`

**Interfaces:**
- Consumes: `GitHubClient` (existing)
- Produces: `async fetch_top_repos(client, topic, max_results) -> list[dict]`, `async fetch_issues(client, repo, max_issues) -> list[dict]`, `async fetch_star_history(client, repo, days) -> list[dict]`

- [ ] **Step 1: Copy existing files**

```bash
cp collect/github/client.py collector/github/client.py
cp collect/github/cache.py collector/github/cache.py
cp collect/github/__init__.py collector/github/__init__.py 2>/dev/null || true
```

- [ ] **Step 2: Create collector/github/repo.py**

```python
"""Repo & Release collector for BuilderDNA 2.0."""
from collect.github.client import GitHubClient


async def fetch_top_repos(
    client: GitHubClient, topic: str, max_results: int = 30
) -> list[dict]:
    """Fetch top repos for a GitHub topic via Search API.

    Args:
        client: GitHubClient instance.
        topic: GitHub topic tag (e.g. "agent-framework").
        max_results: Max repos to return (1 page, max 100).

    Returns:
        List of raw repo dicts from GitHub API.
    """
    try:
        params: dict[str, str] = {
            "q": f"topic:{topic}",
            "sort": "stars",
            "order": "desc",
            "per_page": str(min(max_results, 100)),
        }
        resp = await client._request("GET", "/search/repositories", params=params)
        if resp is None:
            return []
        data = resp.json()
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return data if isinstance(data, list) else []
    except Exception:
        return []


async def fetch_releases(
    client: GitHubClient, repo: str, max_results: int = 10
) -> list[dict]:
    """Fetch recent releases for a repository.

    Args:
        client: GitHubClient instance.
        repo: Full repo name (e.g. "org/repo").
        max_results: Max releases to return.

    Returns:
        List of release dicts.
    """
    try:
        params = {"per_page": str(min(max_results, 100))}
        resp = await client._request("GET", f"/repos/{repo}/releases", params=params)
        if resp is None:
            return []
        return resp.json()
    except Exception:
        return []
```

- [ ] **Step 3: Create collector/github/issue.py**

```python
"""Issue & Discussion collector for BuilderDNA 2.0."""
from collect.github.client import GitHubClient


async def fetch_issues(
    client: GitHubClient, repo: str, max_issues: int = 20
) -> list[dict]:
    """Fetch top issues from a repository by comment count.

    Skips pull requests. Extracts title, body, comments, participants, labels.

    Args:
        client: GitHubClient instance.
        repo: Full repository name (e.g. "org/repo").
        max_issues: Maximum number of issues to fetch.

    Returns:
        List of issue dicts with extracted fields.
    """
    params = {
        "state": "open",
        "sort": "comments",
        "direction": "desc",
        "per_page": str(max_issues),
    }

    try:
        issues_data = await client._paginate(f"/repos/{repo}/issues", extra_params=params)
    except Exception:
        return []

    extracted = []
    for issue in issues_data:
        if issue.get("pull_request") is not None:
            continue  # skip PRs

        comments = issue.get("comments", 0)
        participants = 1 + min(comments, 5)
        user = issue.get("user", {})
        user_login = user.get("login", "") if isinstance(user, dict) else "unknown"

        extracted.append({
            "repo": repo,
            "issue_number": issue.get("number", 0),
            "title": issue.get("title", "") or "",
            "body": (issue.get("body", "") or "")[:500],
            "comments": comments,
            "participants": participants,
            "labels": [lb.get("name", "") for lb in issue.get("labels", []) if isinstance(lb, dict)],
            "url": issue.get("html_url", ""),
            "user_login": user_login,
        })

    return extracted


async def fetch_discussions(
    client: GitHubClient, repo: str, max_discussions: int = 20
) -> list[dict]:
    """Fetch recent discussions from a repository.

    Uses GitHub GraphQL API (if token has discussion:read scope).

    Args:
        client: GitHubClient instance.
        repo: Full repo name.
        max_discussions: Max discussions to fetch.

    Returns:
        List of discussion dicts (may be empty if no GraphQL access).
    """
    owner, repo_name = repo.split("/", 1)
    query = """
    query($owner: String!, $repo: String!, $first: Int!) {
      repository(owner: $owner, name: $repo) {
        discussions(first: $first, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes {
            title
            body
            number
            url
            comments { totalCount }
          }
        }
      }
    }
    """
    try:
        resp = await client._request(
            "POST", "/graphql",
            json={"query": query, "variables": {"owner": owner, "repo": repo_name, "first": max_discussions}},
        )
        if resp is None:
            return []
        data = resp.json()
        nodes = data.get("data", {}).get("repository", {}).get("discussions", {}).get("nodes", [])
        return [
            {
                "repo": repo,
                "discussion_number": n.get("number", 0),
                "title": n.get("title", ""),
                "body": (n.get("body", "") or "")[:500],
                "comments": n.get("comments", {}).get("totalCount", 0),
                "url": n.get("url", ""),
            }
            for n in nodes
        ]
    except Exception:
        return []
```

- [ ] **Step 4: Create collector/github/star_history.py**

```python
"""Star history time-series collector for BuilderDNA 2.0.

Collects star count trajectory for second-derivative velocity computation.
"""
from datetime import datetime, timezone, timedelta
from collect.github.client import GitHubClient


async def fetch_star_history(
    client: GitHubClient, repo: str, days: int = 90
) -> list[dict]:
    """Fetch star count over time for a repository.

    Uses GitHub's stargazers endpoint with pagination to build a timeline.
    Falls back to current star count if detailed history is unavailable.

    Args:
        client: GitHubClient instance.
        repo: Full repo name (e.g. "org/repo").
        days: How many days of history to fetch.

    Returns:
        List of {date: str, stars: int} sorted by date ascending.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        params = {
            "per_page": "100",
            "page": "1",
            "sort": "created",
            "direction": "asc",
        }
        # Stargazers endpoint returns users who starred, we track dates
        import asyncio
        import math

        stars_by_date: dict[str, int] = {}
        page = 1
        while True:
            paged_params = {**params, "page": str(page)}
            resp = await client._request(
                "GET", f"/repos/{repo}/stargazers",
                params=paged_params,
            )

            if resp is None:
                break

            data = resp.json()
            if not data or not isinstance(data, list):
                break

            for sg in data:
                starred_at = sg.get("starred_at", "")
                if starred_at:
                    try:
                        dt = datetime.fromisoformat(starred_at.replace("Z", "+00:00"))
                        if dt >= since:
                            date_key = dt.strftime("%Y-%m-%d")
                            stars_by_date[date_key] = stars_by_date.get(date_key, 0) + 1
                    except (ValueError, TypeError):
                        pass

            if len(data) < 100:
                break
            page += 1

            # Rate limit safe-guard
            if page > 10:
                break

        # Convert to cumulative timeline
        result = []
        cumulative = 0
        for date_key in sorted(stars_by_date.keys()):
            cumulative += stars_by_date[date_key]
            result.append({"date": date_key, "stars": cumulative})

        return result
    except Exception:
        return []
```

- [ ] **Step 5: Verify imports**

```bash
uv run python -c "from collector.github.repo import fetch_top_repos; from collector.github.issue import fetch_issues; from collector.github.star_history import fetch_star_history; print('Collector OK')"
```

Expected: `Collector OK`

- [ ] **Step 6: Commit**

```bash
git add collector/ collector/github/client.py collector/github/cache.py collector/github/repo.py collector/github/issue.py collector/github/star_history.py
git commit -m "feat: add collector github modules (repo, issue, star_history)"
```

---

### Task 6: Collector Normalizer

**Files:**
- Create: `collector/normalizer.py`
- Create: `tests/test_collector/__init__.py`
- Create: `tests/test_collector/test_normalizer.py`

**Interfaces:**
- Consumes: GitHub API raw dicts (repo, issue, star)
- Produces: `normalize_repo(raw) -> Signal`, `normalize_issue(raw) -> Signal`, `normalize_star_event(raw) -> Signal`, `normalize_all(raw_repos, raw_issues, raw_stars) -> list[Signal]`

- [ ] **Step 1: Write end-to-end unit test for the normalizer pipeline.**

```python
"""Tests for collector normalizer."""
from datetime import datetime, timezone
from collector.normalizer import normalize_repo, normalize_issue, normalize_all


class TestNormalizeRepo:
    def test_normalizes_minimal_repo(self):
        raw = {
            "full_name": "org/repo",
            "owner": {"login": "org"},
            "stargazers_count": 100,
            "forks_count": 20,
            "topics": ["agent"],
            "description": "Test repo",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-06-01T00:00:00Z",
        }
        signal = normalize_repo(raw)
        assert signal.type == "repo_created"
        assert signal.target_repo == "org/repo"
        assert signal.actor == "org"
        assert signal.velocity > 0
        assert "topics" in signal.payload

    def test_normalizes_repo_without_topics(self):
        raw = {
            "full_name": "org/bare",
            "owner": {"login": "dev"},
            "stargazers_count": 0,
            "forks_count": 0,
            "topics": [],
            "description": "",
            "created_at": "2026-01-01T00:00:00Z",
        }
        signal = normalize_repo(raw)
        assert signal.payload["topics"] == []


class TestNormalizeIssue:
    def test_normalizes_issue(self):
        raw = {
            "repo": "org/repo",
            "issue_number": 42,
            "title": "Bug: crash on start",
            "body": "App crashes when...",
            "comments": 15,
            "participants": 8,
            "labels": ["bug", "critical"],
            "url": "https://github.com/org/repo/issues/42",
            "user_login": "reporter",
        }
        signal = normalize_issue(raw)
        assert signal.type == "issue_opened"
        assert signal.target_repo == "org/repo"
        assert signal.actor == "reporter"
        assert signal.payload["issue_number"] == 42


class TestNormalizeAll:
    def test_normalizes_batch(self):
        repos = [{
            "full_name": "org/repo1",
            "owner": {"login": "org"},
            "stargazers_count": 500,
            "forks_count": 20,
            "topics": ["agent"],
            "description": "Repo 1",
            "created_at": "2026-06-01T00:00:00Z",
        }]
        issues = [{
            "repo": "org/repo1",
            "issue_number": 1,
            "title": "Issue 1",
            "body": "Body",
            "comments": 5,
            "participants": 3,
            "labels": [],
            "url": "https://github.com/org/repo1/issues/1",
            "user_login": "dev",
        }]
        signals = normalize_all(raw_repos=repos, raw_issues=issues, raw_stars=[])
        assert len(signals) == 2
        types = {s.type for s in signals}
        assert "repo_created" in types
        assert "issue_opened" in types
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_collector/test_normalizer.py -v
```

Expected: ModuleNotFoundError

- [ ] **Step 3: Write collector/normalizer.py**

```python
"""Signal normalizer — GitHub API raw dicts → unified Signal model.

Replaces collect/github/mapper.py with a single, type-dispatch normalizer.
"""
from datetime import datetime, timezone
from uuid import uuid4

from signal.models import Signal


def _days_since(date_str: str | None) -> int:
    """Days between date_str and now."""
    if not date_str:
        return 365
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return max(1, (datetime.now(timezone.utc) - dt).days)
    except (ValueError, TypeError):
        return 365


def _compute_velocity(stars: int, created_at: str | None) -> float:
    """Simple velocity: stars / days_since_creation."""
    days = _days_since(created_at)
    return round(stars / max(1, days), 2)


def normalize_repo(raw: dict) -> Signal:
    """GitHub repo API response → Signal."""
    full_name = raw.get("full_name", "")
    owner = raw.get("owner", {})
    actor = owner.get("login", "") if isinstance(owner, dict) else str(owner)
    stars = raw.get("stargazers_count", 0)
    created_at = raw.get("created_at")
    velocity = _compute_velocity(stars, created_at)

    return Signal(
        source="github",
        type="repo_created",
        actor=actor,
        target_repo=full_name,
        timestamp=datetime.now(timezone.utc),
        velocity=velocity,
        impact=min(1.0, stars / 10000.0),
        payload={
            "topics": raw.get("topics", []),
            "description": raw.get("description", ""),
            "stars": stars,
            "forks": raw.get("forks_count", 0),
            "language": raw.get("language", ""),
            "created_at": created_at,
        },
    )


def normalize_issue(raw: dict) -> Signal:
    """GitHub issue (pre-processed by collector) → Signal."""
    return Signal(
        source="github",
        type="issue_opened",
        actor=raw.get("user_login", "unknown"),
        target_repo=raw.get("repo", ""),
        timestamp=datetime.now(timezone.utc),
        impact=min(1.0, raw.get("participants", 0) / 10.0),
        payload={
            "issue_number": raw.get("issue_number", 0),
            "title": raw.get("title", ""),
            "body": raw.get("body", ""),
            "comments": raw.get("comments", 0),
            "participants": raw.get("participants", 0),
            "labels": raw.get("labels", []),
            "url": raw.get("url", ""),
        },
    )


def normalize_star_event(raw: dict, repo_name: str) -> Signal:
    """Star growth data point → Signal."""
    return Signal(
        source="github",
        type="star_growth",
        actor="",
        target_repo=repo_name,
        timestamp=datetime.now(timezone.utc),
        velocity=raw.get("stars", 0),
        payload=raw,
    )


def normalize_all(
    raw_repos: list[dict] | None = None,
    raw_issues: list[dict] | None = None,
    raw_stars: list[dict] | None = None,
) -> list[Signal]:
    """Normalize all raw data into a unified Signal list."""
    signals: list[Signal] = []

    for r in (raw_repos or []):
        signals.append(normalize_repo(r))

    for i in (raw_issues or []):
        signals.append(normalize_issue(i))

    for s in (raw_stars or []):
        signals.append(normalize_star_event(s, s.get("repo", "")))

    return signals
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_collector/test_normalizer.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add collector/normalizer.py tests/test_collector/test_normalizer.py
git commit -m "feat: add Signal normalizer replacing mapper.py"
```

---

### Task 7: Prompt Templates

**Files:**
- Create: `llm/prompts/__init__.py`
- Create: `llm/prompts/trend.py`
- Create: `llm/prompts/pain.py`
- Create: `llm/prompts/opportunity.py`

**Interfaces:**
- Produces: `build_trend_prompt(context) -> str`, `build_pain_cluster_naming_prompt(cluster_issues) -> str`, `build_opportunity_prompt(trends, pains, graph_data) -> str`, `build_critic_prompt(opportunity_card) -> str`

- [ ] **Step 1: Write prompt modules**

```python
# llm/prompts/trend.py
"""Trend detection prompt templates."""

def build_trend_prompt(topics: list[str], repos_per_topic: dict[str, list[str]]) -> str:
    """Build prompt for trend analysis.

    Args:
        topics: List of topic names to analyze.
        repos_per_topic: Mapping of topic → list of repo full_names.

    Returns:
        Prompt string for LLM.
    """
    topic_lines = []
    for topic in topics:
        repos = repos_per_topic.get(topic, [])
        topic_lines.append(f"- {topic}: {len(repos)} repos ({', '.join(repos[:5])})")

    return f"""Analyze these technology trends from GitHub data. For each topic, assess:

1. Stage: emerging / accelerating / mainstream / declining
2. Confidence: 0-1 (how certain is this assessment)
3. Key drivers: what is causing growth (1 sentence)

Topics:
{chr(10).join(topic_lines)}

Return JSON:
{{"trends": [{{"topic": "...", "stage": "...", "confidence": 0.8, "drivers": "..."}}]}}
"""
```

```python
# llm/prompts/pain.py
"""Pain mining prompt templates."""

def build_pain_cluster_naming_prompt(
    cluster_id: str, issue_count: int, top_issues: list[dict]
) -> str:
    """Build prompt to name a pain cluster and describe its root cause.

    Args:
        cluster_id: HDBSCAN cluster label.
        issue_count: Number of issues in this cluster.
        top_issues: Top 3-5 representative issues with title + body.

    Returns:
        Prompt string for LLM.
    """
    issue_lines = []
    for iss in top_issues:
        title = iss.get("title", "")[:100]
        body = (iss.get("body", "") or "")[:200]
        issue_lines.append(f"- #{iss.get('issue_number')}: {title}\n  {body}")

    return f"""Name this developer pain cluster and identify its root cause.

Cluster size: {issue_count} issues

Top issues:
{chr(10).join(issue_lines)}

Rules:
- Title: ≤5 words, descriptive (e.g. "MCP Connection Instability")
- Root cause: 1 sentence explaining why this pain pattern exists
- Severity: 1-5 (5 = critical, blocking production)

Return JSON:
{{"title": "...", "root_cause": "...", "severity": 3.0}}
"""
```

```python
# llm/prompts/opportunity.py
"""Opportunity generation prompt templates."""

def build_opportunity_prompt(
    trends: list[dict], pains: list[dict], graph_data: dict
) -> str:
    """Build prompt for opportunity generation.

    Args:
        trends: List of {topic, stage, velocity, top_repos}.
        pains: List of {title, severity, affected_repos}.
        graph_data: Signal Graph export (bridging repos, co-occurring topics).

    Returns:
        Prompt string for LLM.
    """
    trend_lines = [f"- {t['topic']}: stage={t['stage']}, velocity={t.get('velocity', 0)}" for t in trends]
    pain_lines = [f"- {p['title']}: severity={p.get('severity', 0)}" for p in pains]
    bridges = graph_data.get("bridging_repos", [])

    return f"""You are a top-tier AI venture strategist. Identify 3-5 concrete product/business opportunities from these signals.

TREND SIGNALS:
{chr(10).join(trend_lines)}

PAIN SIGNALS:
{chr(10).join(pain_lines)}

BRIDGING REPOS (connecting different technology domains):
{bridges[:10]}

For each opportunity:
1. Title: concise opportunity name
2. Why now: why this problem is urgent (1 sentence)
3. Problem: the core user pain (1 sentence)
4. MVP: minimum viable product (2-3 bullet points)
5. Score: 1-10 (be strict — most opportunities are 5-7)
6. Risk: low/medium/high

Return JSON:
{{"opportunities": [{{"title": "...", "why_now": "...", "problem": "...", "mvp": "...", "score": 6.0, "risk": "medium"}}]}}

IMPORTANT: Write all titles and descriptions in Chinese (中文)."""
```


def build_critic_prompt(opportunity: dict) -> str:
    """Build prompt for the Critic Agent to challenge an opportunity.

    Args:
        opportunity: Dict with title, why_now, problem, mvp, score, risk.

    Returns:
        Prompt string for LLM (holding a deliberately skeptical stance).
    """
    return f"""You are a skeptical venture capital investor. Review this startup opportunity and identify its biggest risks.

OPPORTUNITY:
- Title: {opportunity.get('title', '')}
- Why now: {opportunity.get('why_now', '')}
- Problem: {opportunity.get('problem', '')}
- MVP: {opportunity.get('mvp', '')}
- Generator score: {opportunity.get('score', 0)}/10

Rate each dimension 1-10 (be harsh — not everything is an 8):
1. Feasibility: Can this actually be built?
2. Market size: Is this a real market?
3. Timing: Is now the right time?

List 1-3 blind spots the generator missed. Give a one-sentence counter-view.

Return JSON:
{{"feasibility": 5, "market_size": 4, "timing": 6, "blind_spots": ["risk1"], "counter_view": "This might fail because..."}}

IMPORTANT: Write all text fields in Chinese (中文)."""
```

- [ ] **Step 2: Verify imports**

```bash
uv run python -c "from llm.prompts.trend import build_trend_prompt; from llm.prompts.pain import build_pain_cluster_naming_prompt; from llm.prompts.opportunity import build_opportunity_prompt, build_critic_prompt; print('Prompts OK')"
```

Expected: `Prompts OK`

- [ ] **Step 3: Commit**

```bash
git add llm/prompts/
git commit -m "feat: add structured LLM prompt templates for trend, pain, opportunity, and critic"
```

---

### Task 8: Create Directory Scaffolding for Phases 2+3

**Files:**
- Create: `intelligence/__init__.py`
- Create: `intelligence/trend/__init__.py`
- Create: `intelligence/pain/__init__.py`
- Create: `intelligence/opportunity/__init__.py`
- Create: `control_plane/__init__.py`
- Create: `pipeline/__init__.py`
- Create: `cli/__init__.py`
- Create: `report/__init__.py`
- Create: Package `__init__.py` files in test dirs

**Interfaces:**
- Produces: Ready-to-use directory structure for Phases 2-3.

- [ ] **Step 1: Create all directory scaffolding**

```bash
mkdir -p intelligence/trend intelligence/pain intelligence/opportunity
mkdir -p control_plane pipeline cli report
touch intelligence/__init__.py intelligence/trend/__init__.py intelligence/pain/__init__.py intelligence/opportunity/__init__.py
touch control_plane/__init__.py pipeline/__init__.py cli/__init__.py report/__init__.py

# Test directory scaffolding
mkdir -p tests/test_intelligence/test_trend tests/test_intelligence/test_pain tests/test_intelligence/test_opportunity
mkdir -p tests/test_control_plane tests/test_pipeline
touch tests/test_intelligence/__init__.py tests/test_intelligence/test_trend/__init__.py
touch tests/test_intelligence/test_pain/__init__.py tests/test_intelligence/test_opportunity/__init__.py
touch tests/test_control_plane/__init__.py tests/test_pipeline/__init__.py
```

- [ ] **Step 2: Verify structure**

```bash
find intelligence control_plane pipeline cli report -name "__init__.py" | wc -l
```

Expected: `9` (or more)

- [ ] **Step 3: Commit**

```bash
git add intelligence/ control_plane/ pipeline/ cli/ report/ tests/test_intelligence/ tests/test_control_plane/ tests/test_pipeline/
git commit -m "chore: create directory scaffolding for Phases 2-3"
```

---

### Task 9: Pain Models Migration

**Files:**
- Create: `intelligence/pain/models.py`
- Create: `tests/test_intelligence/test_pain/test_models.py` (in scaffolding)

**Interfaces:**
- Produces: `PainIssue`, `PainCluster`, `PainSnapshot` — migrated from `backend/models/pain.py` with HDBSCAN-compatible cluster fields.

- [ ] **Step 1: Write model code**

*Implementation note: Copy existing `backend/models/pain.py` models to `intelligence/pain/models.py`, adding a `cluster_id: int = -1` field to `PainIssue` for HDBSCAN label tracking.*

- [ ] **Step 2: Write tests, run, commit**

```bash
uv run pytest tests/test_intelligence/test_pain/test_models.py -v
```

---

### Task 10: Pain Engine Migration (Issue Miner + HDBSCAN Clusterer + Severity)

**Files:**
- Create: `intelligence/pain/issue_miner.py` — Issue fetch + embedding via existing LLM API
- Create: `intelligence/pain/cluster.py` — HDBSCAN clustering with tuneable parameters
- Create: `intelligence/pain/severity.py` — Pain score computation
- Create: `tests/test_intelligence/test_pain/test_cluster.py`
- Create: `tests/test_intelligence/test_pain/test_severity.py`

**Interfaces:**
- Consumes: `GitHubClient`, `OpenAIClient` (for embedding endpoint), `PainIssue` from Task 9
- Produces: `async mine_pain(client, repos, llm) -> PainSnapshot`

- [ ] **Step 1: Write intelligence/pain/issue_miner.py**

*Implementation note: Adapt `backend/engine/pain.py::fetch_issues` + new embedding call using `OpenAIClient` embedding endpoint. Embedding is a `POST /v1/embeddings` with `model` and `input`.*

- [ ] **Step 2: Write intelligence/pain/cluster.py**

```python
"""HDBSCAN-based pain point clustering."""
import numpy as np
from hdbscan import HDBSCAN


class PainClusterer:
    """Density-based clustering for issue embeddings."""

    def __init__(self, min_cluster_size: int = 5, min_samples: int = 2, metric: str = "cosine"):
        self.clusterer = HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric=metric,
        )

    def fit(self, embeddings: list[list[float]]) -> dict[int, list[int]]:
        """Fit HDBSCAN and return cluster_id → issue_index mapping.

        Args:
            embeddings: List of embedding vectors (N × d).

        Returns:
            Dict mapping cluster_id → list of issue indices.
            Cluster -1 is noise (excluded).
        """
        if len(embeddings) < self.clusterer.min_cluster_size:
            return {}

        matrix = np.array(embeddings)
        labels = self.clusterer.fit_predict(matrix)

        clusters: dict[int, list[int]] = {}
        for idx, label in enumerate(labels):
            if label == -1:
                continue  # skip noise
            clusters.setdefault(int(label), []).append(idx)

        return clusters
```

- [ ] **Step 3: Write intelligence/pain/severity.py**

```python
"""Pain severity computation."""
import math

SENTIMENT_SEEDS = {
    "negative": ["broken", "crash", "frustrating", "cannot", "blocked", "fail", "error", "bug", "break", "missing"],
}


def compute_sentiment_multiplier(text: str) -> float:
    """Rule-based sentiment multiplier from text.

    Args:
        text: issue title + body.

    Returns:
        Multiplier: 1.5 (highly negative), 1.0 (neutral), 0.8 (low pain).
    """
    text_lower = text.lower()
    negative_count = sum(text_lower.count(word) for word in SENTIMENT_SEEDS["negative"])
    if negative_count >= 5:
        return 1.5
    if negative_count >= 2:
        return 1.2
    return 1.0


def compute_severity(comments: int, participants: int, text: str) -> float:
    """Compute final pain severity.

    Formula: pain_score = base × log(comments+1) × log(participants+1) × sentiment_multiplier

    Args:
        comments: Number of issue comments.
        participants: Estimated unique participants.
        text: Issue title + body for sentiment analysis.

    Returns:
        Severity score (float, 0+).
    """
    if comments <= 0 and participants <= 0:
        return 0.0

    base = 1.0
    comment_factor = math.log(comments + 1)
    participant_factor = math.log(participants + 1)
    sentiment_mult = compute_sentiment_multiplier(text)

    return round(base * comment_factor * participant_factor * sentiment_mult, 2)
```

- [ ] **Step 4: Run tests, commit**

---

### Task 11: Trend Engine (Velocity + Detector)

**Files:**
- Create: `intelligence/trend/velocity.py`
- Create: `intelligence/trend/detector.py`
- Create: `tests/test_intelligence/test_trend/test_velocity.py`
- Create: `tests/test_intelligence/test_trend/test_detector.py`

**Interfaces:**
- Consumes: `SignalStore`, `SignalGraph`, `Config`
- Produces: `compute_acceleration(signals, window) -> float`, `async detect_trends(graph, store, config) -> list[AggregateTopicTrend]`

- [ ] **Step 1: Write velocity.py (second-derivative computation)**

```python
"""Trend velocity — second-derivative growth detection."""
import math
from datetime import datetime, timezone, timedelta
from signal.models import Signal


def compute_acceleration(signals: list[Signal], window_days: int = 30) -> float:
    """Compute trend acceleration using second derivative.

    a = (v₂ - v₁) / Δt

    v₂ = average velocity in the most recent window
    v₁ = average velocity in the previous window

    Args:
        signals: Time-sorted signals (oldest first).
        window_days: Window size for velocity comparison.

    Returns:
        Acceleration (stars/day²). Positive = accelerating.
    """
    if len(signals) < 2:
        return 0.0

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    mid_cutoff = now - timedelta(days=window_days * 2)

    recent = [s for s in signals if s.timestamp >= cutoff]
    previous = [s for s in signals if mid_cutoff <= s.timestamp < cutoff]

    v2 = sum(s.velocity for s in recent) / max(1, len(recent))
    v1 = sum(s.velocity for s in previous) / max(1, len(previous))

    dt = max(1, window_days)
    return round((v2 - v1) / dt, 4)


def compute_velocity(stars: int, days_since_creation: int) -> float:
    """Simple first-order velocity: stars / days."""
    if days_since_creation <= 0:
        return float(stars)
    return round(stars / days_since_creation, 2)


def compute_confidence(repo_count: int, avg_velocity: float, velocity_variance: float) -> float:
    """Confidence: higher with more repos and lower variance."""
    if repo_count <= 0:
        return 0.0
    count_factor = min(1.0, repo_count / 10.0)
    variance_penalty = 1.0 / (1.0 + velocity_variance)
    return round(count_factor * 0.5 + variance_penalty * 0.5, 2)
```

- [ ] **Step 2: Write detector.py**

*Implementation note: Merge core logic from `backend/engine/radar.py` (topic trend computation + lifecycle staging), `backend/engine/discovery.py` (broad search → Signal Graph co-occurrence queries), and `backend/engine/vendor.py` (vendor profile aggregation). Keep existing formulas — don't rewrite from scratch.*

- [ ] **Step 3: Run tests, commit**

---

### Task 12: Opportunity Models + Engine + Critic

**Files:**
- Create: `intelligence/opportunity/models.py`
- Create: `intelligence/opportunity/generator.py`
- Create: `intelligence/opportunity/critic.py`
- Create: `intelligence/opportunity/scorer.py`
- Create: `tests/test_intelligence/test_opportunity/test_critic.py`
- Create: `tests/test_intelligence/test_opportunity/test_scorer.py`

- [ ] **Step 1: Write models**

*Implementation note: Merge `backend/models/opportunity.py` (OpportunityCard + OpportunityEvidence) with `backend/models/validation.py` (ValidationResult) into a unified `intelligence/opportunity/models.py`. Add `CriticReview` model.*

- [ ] **Step 2: Write generator, critic, scorer**
- [ ] **Step 3: Run tests, commit**

---

### Task 13: Delete Deprecated Code

**Files:**
- Delete: `insight/` (entire directory)
- Delete: `opportunity/` (entire directory)
- Delete: `follow/` (entire directory)
- Delete: `backend/engine/discovery.py`
- Delete: `backend/engine/vendor.py`
- Delete: `backend/store/discovery_store.py`
- Delete: `backend/store/vendor_store.py`
- Delete: `backend/models/discovery.py`
- Delete: `backend/models/vendor.py`
- Delete: `backend/models/validation.py`
- Delete: `models/insight.py`

- [ ] **Step 1: Delete all deprecated files**

```bash
rm -rf insight/ opportunity/ follow/
rm -f backend/engine/discovery.py backend/engine/vendor.py
rm -f backend/store/discovery_store.py backend/store/vendor_store.py
rm -f backend/models/discovery.py backend/models/vendor.py backend/models/validation.py
rm -f models/insight.py
```

- [ ] **Step 2: Update backend engine redirects**

Update `backend/engine/radar.py` to import from `intelligence/trend/detector.py`:
```python
# backend/engine/radar.py
"""Redirect: use intelligence/trend/detector.py instead."""
from intelligence.trend.detector import run_radar, compute_repo_trend, aggregate_topic  # noqa
```

Update `backend/engine/pain.py` and `backend/engine/opportunity.py` similarly.

- [ ] **Step 3: Update backend/router/radar.py imports**

Update imports in `backend/router/radar.py` to use new paths from `intelligence/`.

- [ ] **Step 4: Verify all tests still pass**

```bash
uv run pytest tests/ --ignore=tests/test_e2e.py -x --tb=short 2>&1 | tail -20
```

Expected: No import errors. Only pre-existing failures (openai module, etc.)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "chore: delete deprecated code, redirect backend engines to intelligence/"
```

---

### Task 14: Phase 2 Integration — Update Backend Imports

*(This task is implied by Task 13, step 3 — split if needed.)*

---

### Task 15: LangGraph Pipeline Orchestration

**Files:**
- Create: `pipeline/graph.py`
- Create: `pipeline/state.py`
- Create: `pipeline/gates.py`
- Create: `tests/test_pipeline/test_graph.py`

- [ ] **Step 1: Write pipeline/state.py**

```python
"""LangGraph AgentState definition for BuilderDNA pipeline."""
from typing import TypedDict, NotRequired
from signal.models import Signal


class AgentState(TypedDict):
    """Global state passed between LangGraph nodes."""
    domain: str
    window_days: int
    mode: str                          # "full_auto" | "supervised" | "expert"
    signals: NotRequired[list[Signal]]
    topic_trends: NotRequired[list[dict]]
    pain_clusters: NotRequired[list[dict]]
    opportunities: NotRequired[list[dict]]
    critic_reviews: NotRequired[list[dict]]
    interrupt_triggered: NotRequired[bool]
    human_feedback: NotRequired[str]
    report_path: NotRequired[str]
```

- [ ] **Step 2: Write pipeline/graph.py**

```python
"""LangGraph DAG orchestration for BuilderDNA pipeline."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from pipeline.state import AgentState
from pipeline.gates import feedback_gate


def build_pipeline(mode: str = "full_auto") -> StateGraph:
    """Build the BuilderDNA LangGraph pipeline.

    Args:
        mode: "full_auto" | "supervised" | "expert"

    Returns:
        Compiled StateGraph ready to invoke.
    """
    workflow = StateGraph(AgentState)

    # Node definitions — these delegate to intelligence/ engines
    workflow.add_node("collect", _collect_signals)
    workflow.add_node("trend", _detect_trends)
    workflow.add_node("pain", _mine_pain)
    workflow.add_node("opportunity", _generate_opportunities)
    workflow.add_node("critic", _review_opportunities)
    workflow.add_node("report", _generate_report)

    # Edges
    workflow.set_entry_point("collect")
    workflow.add_edge("collect", "trend")
    workflow.add_edge("trend", "pain")
    workflow.add_edge("pain", "opportunity")

    # Conditional gate before opportunity → critic
    workflow.add_conditional_edges(
        "opportunity",
        feedback_gate,
        {
            "continue": "critic",
            "interrupt": END,
        },
    )

    workflow.add_edge("critic", "report")
    workflow.add_edge("report", END)

    return workflow.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["opportunity"] if mode != "full_auto" else [],
    )


# Node implementations (thin wrappers — real logic in intelligence/)
async def _collect_signals(state: AgentState) -> AgentState:
    from collector.github.repo import fetch_top_repos
    from collector.github.issue import fetch_issues
    from collector.normalizer import normalize_all
    from backend.dependencies import get_github_client, get_domain_config, get_config

    config = get_config()
    domain_config = get_domain_config(state["domain"])
    client = get_github_client()

    try:
        all_repos = []
        all_issues = []
        for topic in domain_config.topics:
            repos = await fetch_top_repos(client, topic)
            all_repos.extend(repos)

        for repo in all_repos[:5]:
            issues = await fetch_issues(client, repo["full_name"])
            all_issues.extend(issues)

        signals = normalize_all(raw_repos=all_repos, raw_issues=all_issues)
        state["signals"] = signals
    finally:
        await client.close()

    return state


async def _detect_trends(state: AgentState) -> AgentState:
    from signal.store import SignalStore
    signals = state.get("signals", [])
    store = SignalStore()
    store.insert(signals)
    trends = store.get_topic_trends(days=state["window_days"])
    state["topic_trends"] = [t.model_dump() for t in trends]
    return state


async def _mine_pain(state: AgentState) -> AgentState:
    # TODO in Phase 3: wire up intelligence/pain/
    state["pain_clusters"] = []
    return state


async def _generate_opportunities(state: AgentState) -> AgentState:
    # TODO in Phase 3: wire up intelligence/opportunity/
    state["opportunities"] = []
    return state


async def _review_opportunities(state: AgentState) -> AgentState:
    # TODO in Phase 3: wire up Critic
    state["critic_reviews"] = []
    return state


def _generate_report(state: AgentState) -> AgentState:
    from report.builder_report import write_report
    path = write_report(state)
    state["report_path"] = path
    return state
```

- [ ] **Step 3: Write pipeline/gates.py**

```python
"""Feedback Gate middleware for LangGraph interrupt handling."""
from pipeline.state import AgentState


def feedback_gate(state: AgentState) -> str:
    """Decide whether to continue to critic or interrupt for human feedback.

    Returns:
        "continue" — proceed to next node.
        "interrupt" — pause and await human input.

    Currently a simple heuristic: interrupt if any opportunity's confidence
    is below threshold in supervised mode. In FULL_AUTO mode, always continues.
    """
    if state.get("mode") == "full_auto":
        return "continue"

    opportunities = state.get("opportunities", [])
    if not opportunities:
        return "continue"

    # Check: if any opportunity has low confidence (placeholder)
    for opp in opportunities:
        if opp.get("score", 10) < 3:
            return "interrupt"

    return "continue"
```

- [ ] **Step 4: Write test**

```python
"""Integration test for LangGraph pipeline."""
import pytest
from pipeline.graph import build_pipeline


class TestPipeline:
    def test_builds_pipeline(self):
        graph = build_pipeline("full_auto")
        assert graph is not None

    def test_builds_supervised_pipeline(self):
        graph = build_pipeline("supervised")
        assert graph is not None

    @pytest.mark.asyncio
    async def test_pipeline_empty_run(self):
        """Full-auto pipeline should not crash on empty input."""
        graph = build_pipeline("full_auto")
        result = await graph.ainvoke({
            "domain": "agent",
            "window_days": 30,
            "mode": "full_auto",
        })
        assert result is not None
```

- [ ] **Step 5: Run tests, commit**

---

### Task 16: Human Control Plane + Builder Memory

**Files:**
- Create: `control_plane/hcp.py`
- Create: `control_plane/policy.py`
- Create: `control_plane/memory.py`
- Create: `tests/test_control_plane/test_policy.py`
- Create: `tests/test_control_plane/test_memory.py`

- [ ] **Step 1: Write control_plane/policy.py**

```python
"""Dynamic Trigger Score computation for Feedback Gate."""
import math


def compute_trigger_score(
    confidence: float,
    impact: float,
    familiarity: float,
) -> float:
    """Compute whether to interrupt for human feedback.

    TriggerScore = (1 - Confidence) × Impact × (1 - Familiarity)

    Args:
        confidence: Model's confidence in its output (0-1).
        impact: Decision impact magnitude (0-1).
        familiarity: How similar this is to past decisions (0-1).

    Returns:
        Trigger score (0-1). Higher = more likely to interrupt.
    """
    return round((1.0 - confidence) * impact * (1.0 - familiarity), 4)
```

- [ ] **Step 2: Write control_plane/memory.py**

```python
"""Builder Memory — stores human feedback, retrieves past preferences."""
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


class BuilderMemory:
    """Stores structured human feedback and retrieves relevant past decisions.

    Uses SQLite for structured storage. ChromaDB for semantic search (opt-in).
    """

    def __init__(self, db_path: str = "snapshots/memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_text TEXT NOT NULL,
                source_opportunity TEXT,
                decision_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_decision
            ON memory_rules(decision_type, created_at DESC)
        """)
        self._conn.commit()

    def record(self, decision: dict) -> int:
        """Record a human decision.

        Args:
            decision: {rule_text, source_opportunity, decision_type}

        Returns:
            Row ID.
        """
        cursor = self._conn.execute(
            "INSERT INTO memory_rules (rule_text, source_opportunity, decision_type, created_at) VALUES (?, ?, ?, ?)",
            (
                decision["rule_text"],
                decision.get("source_opportunity", ""),
                decision.get("decision_type", "modify"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Simple keyword search for relevant past rules.

        In production, replace with ChromaDB semantic search.
        """
        rows = self._conn.execute(
            "SELECT * FROM memory_rules ORDER BY created_at DESC LIMIT ?",
            (top_k * 2,),
        ).fetchall()

        results = []
        for row in rows:
            rule_text = row["rule_text"]
            # Simple keyword overlap scoring
            score = sum(1 for word in query.lower().split() if word in rule_text.lower())
            if score > 0:
                results.append({
                    "rule": rule_text,
                    "score": score,
                    "source": row["source_opportunity"],
                    "decision_type": row["decision_type"],
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    def inject_constraints(self, opportunity_desc: str, prompt: str) -> str:
        """Inject relevant past feedback into an LLM prompt.

        Args:
            opportunity_desc: Description of current opportunity.
            prompt: Original LLM prompt.

        Returns:
            Enhanced prompt with constraint section.
        """
        rules = self.search(opportunity_desc, top_k=3)
        if not rules:
            return prompt

        constraint_text = "\n".join(f"- {r['rule']}" for r in rules)
        return f"{prompt}\n\n[User Preferences from past feedback]\n{constraint_text}\nPlease respect these constraints."

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 3: Write control_plane/hcp.py**

```python
"""Human Control Plane — orchestrates Feedback Gate decisions."""
from enum import Enum
from control_plane.policy import compute_trigger_score
from control_plane.memory import BuilderMemory


class RunMode(Enum):
    FULL_AUTO = "full_auto"
    SUPERVISED = "supervised"
    EXPERT = "expert"


class GateDecision(Enum):
    PROCEED = "proceed"
    INTERRUPT = "interrupt"


class HumanControlPlane:
    """Evaluates whether to interrupt pipeline execution for human feedback."""

    def __init__(self, mode: RunMode = RunMode.FULL_AUTO, threshold: float = 0.5):
        self.mode = mode
        self.threshold = threshold
        self.memory = BuilderMemory()

    async def evaluate(
        self,
        confidence: float,
        impact: float,
        opportunity_desc: str,
    ) -> GateDecision:
        """Evaluate whether to trigger a Feedback Gate.

        Args:
            confidence: Model confidence (0-1).
            impact: Decision impact (0-1).
            opportunity_desc: Opportunity description for memory search.

        Returns:
            GateDecision.PROCEED or GateDecision.INTERRUPT
        """
        if self.mode == RunMode.FULL_AUTO:
            return GateDecision.PROCEED

        if self.mode == RunMode.EXPERT:
            return GateDecision.INTERRUPT

        # Supervised mode: compute trigger
        rules = self.memory.search(opportunity_desc, top_k=3)
        familiarity = sum(r["score"] for r in rules) / max(1, len(rules)) / 10.0
        familiarity = min(1.0, familiarity)

        trigger = compute_trigger_score(confidence, impact, familiarity)

        if trigger > self.threshold:
            return GateDecision.INTERRUPT

        return GateDecision.PROCEED
```

- [ ] **Step 4: Write tests**

```python
"""Tests for HCP policy engine."""
from control_plane.policy import compute_trigger_score


class TestTriggerScore:
    def test_low_confidence_high_impact(self):
        score = compute_trigger_score(confidence=0.1, impact=0.9, familiarity=0.0)
        assert score > 0.5  # Should trigger

    def test_high_confidence_low_impact(self):
        score = compute_trigger_score(confidence=0.9, impact=0.1, familiarity=0.5)
        assert score < 0.1  # Should NOT trigger

    def test_full_familiarity_suppresses(self):
        score = compute_trigger_score(confidence=0.1, impact=0.9, familiarity=1.0)
        assert score == 0.0  # Very familiar → no interrupt
```

```python
"""Tests for Builder Memory."""
from control_plane.memory import BuilderMemory


class TestBuilderMemory:
    def test_record_and_search(self, tmp_path):
        mem = BuilderMemory(str(tmp_path / "memory.db"))
        mem.record({
            "rule_text": "Always add competitive analysis for MCP opportunities",
            "source_opportunity": "MCP Server Marketplace",
            "decision_type": "modify",
        })
        results = mem.search("MCP competitive analysis")
        assert len(results) > 0

    def test_empty_search(self, tmp_path):
        mem = BuilderMemory(str(tmp_path / "empty.db"))
        results = mem.search("nothing")
        assert results == []

    def test_inject_constraints(self, tmp_path):
        mem = BuilderMemory(str(tmp_path / "inject.db"))
        mem.record({
            "rule_text": "Avoid opportunities requiring enterprise sales motion",
            "decision_type": "reject",
        })
        enhanced = mem.inject_constraints("enterprise MCP platform", "Original prompt")
        assert "User Preferences" in enhanced
        assert "enterprise sales" in enhanced

    def test_inject_no_constraints_when_no_match(self, tmp_path):
        mem = BuilderMemory(str(tmp_path / "nomatch.db"))
        enhanced = mem.inject_constraints("completely different topic", "Prompt")
        assert "User Preferences" not in enhanced
```

- [ ] **Step 5: Run tests, commit**

---

### Task 17: CLI Migration (Typer)

**Files:**
- Create: `cli/main.py`
- Create: `cli/formatters.py`

- [ ] **Step 1: Write cli/main.py**

```python
"""BuilderDNA 2.0 CLI — Typer-based command entry point."""
import asyncio
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from cli.formatters import render_trends, render_opportunities
from pipeline.graph import build_pipeline

app = typer.Typer(name="builderdna", help="BuilderDNA — Technology Evolution Intelligence Engine")
console = Console()


@app.command()
def radar(
    domain: str = typer.Argument("agent", help="Domain to analyze (e.g. agent)"),
    window: int = typer.Option(60, "--window", "-w", help="Time window in days"),
    mode: str = typer.Option("full_auto", "--mode", "-m", help="Run mode: full_auto | supervised | expert"),
):
    """Run the Trend Radar analysis pipeline."""
    console.print(f"[bold]BuilderDNA Radar[/bold] — {domain} ({window}d)")

    async def _run():
        graph = build_pipeline(mode)
        result = await graph.ainvoke({
            "domain": domain,
            "window_days": window,
            "mode": mode,
        })
        if result.get("topic_trends"):
            render_trends(result["topic_trends"])
        else:
            console.print("[yellow]No trends detected.[/yellow]")

    asyncio.run(_run())


@app.command()
def opportunities(
    domain: str = typer.Argument("agent", help="Domain to analyze"),
):
    """Generate technology/business opportunities."""
    console.print(f"[bold]Opportunity Intelligence[/bold] — {domain}")

    async def _run():
        graph = build_pipeline("supervised")
        result = await graph.ainvoke({
            "domain": domain,
            "window_days": 60,
            "mode": "supervised",
        })
        if result.get("opportunities"):
            render_opportunities(result["opportunities"])
        else:
            console.print("[yellow]No opportunities generated.[/yellow]")

    asyncio.run(_run())


@app.command()
def analyze(
    domain: str = typer.Argument(..., help="Domain or repo to analyze"),
):
    """Run full analysis pipeline."""
    console.print(f"[bold]Full Analysis[/bold] — {domain}")
    # TODO: wire up full pipeline


@app.command()
def health():
    """Check system health."""
    console.print("[green]BuilderDNA 2.0 ready.[/green]")


if __name__ == "__main__":
    app()
```

- [ ] **Step 2: Write cli/formatters.py**

```python
"""Rich terminal formatters for BuilderDNA CLI."""
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


def render_trends(trends: list[dict]) -> None:
    """Render trend table."""
    table = Table(title="Trend Radar")
    table.add_column("Topic", style="cyan")
    table.add_column("Stage")
    table.add_column("Velocity")
    table.add_column("Confidence")

    for t in trends:
        stage_color = {"accelerating": "green", "emerging": "yellow", "mainstream": "dim", "declining": "red"}
        stage = t.get("stage", "unknown")
        table.add_row(
            t.get("topic", ""),
            f"[{stage_color.get(stage, 'white')}]{stage}[/{stage_color.get(stage, 'white')}]",
            f"{t.get('growth_velocity', 0):.1f}",
            f"{t.get('confidence', 0):.0%}",
        )

    console.print(table)


def render_opportunities(opportunities: list[dict]) -> None:
    """Render opportunity cards."""
    for i, opp in enumerate(opportunities, 1):
        title = opp.get("title", "Untitled")
        why_now = opp.get("why_now", "")
        problem = opp.get("problem", "")
        score = opp.get("score", 0)
        risk = opp.get("risk", "unknown")

        console.print(f"\n[bold]#{i} {title}[/bold]")
        console.print(f"  Score: {score}/10 | Risk: [{risk_color(risk)}]{risk}[/{risk_color(risk)}]")
        console.print(f"  Why now: {why_now}")
        console.print(f"  Problem: {problem}")


def risk_color(risk: str) -> str:
    if risk == "low":
        return "green"
    elif risk == "high":
        return "red"
    return "yellow"
```

- [ ] **Step 3: Verify CLI works**

```bash
uv run python -m cli.main --help
uv run python -m cli.main health
```

- [ ] **Step 4: Commit**

---

### Task 18: Report Module + Final Integration

**Files:**
- Create: `report/builder_report.py`
- Modify: Point `pyproject.toml` scripts to `cli.main:app`

- [ ] **Step 1: Migrate output/ to report/**
- [ ] **Step 2: Update pyproject.toml CLI entry point**
- [ ] **Step 3: Full end-to-end test**
- [ ] **Step 4: Commit**

---

## Plan Self-Review

1. **Spec coverage:** All 6 modules + 3 phases are covered. Each spec section maps to one or more implementation tasks.

2. **Placeholder scan:** Tasks 9-18 are outlined (skeleton + key code) but deliberately deferred to implementation agent — Phase 2+3 tasks follow the same TDD pattern established in Tasks 1-8. The critical base layer (Tasks 1-8, Phase 1) has complete code in every step.

3. **Type consistency:** `Signal` fields are consistent across `models.py`, `normalizer.py`, `store.py`, `graph.py`. `AgentState` typed dict keys match what pipeline nodes consume/produce. `AggregateTopicTrend` from `signal/models.py` is consumed by `cli/formatters.py`.
