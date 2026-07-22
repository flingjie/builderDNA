# Dual-Loop Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor BuilderDNA from a monolithic LLM-powered LangGraph pipeline into 5 composable sandbox CLI commands that Claude Code orchestrates.

**Architecture:** Remove pipeline/control_plane/backend/llm layers. Keep collector/signals/intelligence as deterministic compute. Add 5 independent CLI commands (collect/trend/pain/opportunity/report) each outputting schema-enforced JSON. Claude Code + Skill replaces LangGraph orchestration and LLM analysis.

**Tech Stack:** Python 3.11+, Typer, Pydantic, DuckDB, HDBSCAN, httpx, NetworkX

## Global Constraints

- Python >= 3.11
- All commands use `PYTHONPATH=.` prefix from project root
- All commands support `--data FILE` (input) and `--output FILE` (output) flags
- All commands output JSON matching models/payload.py schemas
- No LLM API calls (Claude handles all semantic reasoning)
- Embedding API call ONLY in pain command (HDBSCAN requires vectors)
- config.yaml simplified: remove llm, weights, compare, discovery, follow_groups
- .env simplified: remove OPENAI_API_KEY, LLM_BASE_URL
- All old files (pipeline/, control_plane/, backend/, llm/, cli.py, cli/main.py, pipeline.py, output/cli.py) deleted

---

### Task 1: Foundation — Payload Models

**Files:**
- Create: `models/payload.py`
- Modify: `models/__init__.py`

**Interfaces:**
- Produces: `SandboxResult`, `SignalEntry`, `TopicTrend`, `RepoSummary`, `PainCluster`, `IssueSummary`, `OpportunityCard` — all Pydantic BaseModel

- [ ] **Step 1: Write models/payload.py**

```python
"""Schema-enforced output models for all sandbox commands.

Every command outputs a SandboxResult wrapper containing typed payload data.
Claude Code reads these JSON outputs — the schemas here are the contract.
"""
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class SandboxResult(BaseModel):
    """Every sandbox command wraps its output in this."""
    command: str
    domain: str
    computed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: dict[str, Any]
    stats: dict[str, Any] = Field(default_factory=dict)


# ── collect command output ──

class RepoSignal(BaseModel):
    """A single repo signal from the collect command."""
    full_name: str
    owner: str
    stars: int = 0
    forks: int = 0
    contributors: int = 0
    velocity: float = 0.0
    topics: list[str] = Field(default_factory=list)
    description: str = ""
    language: str = ""
    created_at: str = ""


class IssueSignal(BaseModel):
    """A single issue signal from the collect command."""
    repo: str
    issue_number: int
    title: str
    body: str = ""
    comments: int = 0
    participants: int = 0
    reactions: int = 0
    labels: list[str] = Field(default_factory=list)
    url: str = ""


class CollectPayload(BaseModel):
    """Payload for collect command output."""
    repos: list[RepoSignal] = Field(default_factory=list)
    issues: list[IssueSignal] = Field(default_factory=list)


# ── trend command output ──

class RepoSummary(BaseModel):
    """Trend command's repo summary."""
    full_name: str
    stars: int
    stars_delta: int = 0
    forks: int
    contributors: int = 0
    velocity: float
    description: str = ""


class TopicTrend(BaseModel):
    """A single topic trend from the trend command."""
    topic: str
    stage: Literal["accelerating", "emerging", "mainstream", "declining"]
    confidence: float
    growth_velocity: float
    acceleration: float = 0.0
    evidence_count: int
    top_repos: list[RepoSummary] = Field(default_factory=list)


class TrendPayload(BaseModel):
    """Payload for trend command output."""
    trends: list[TopicTrend] = Field(default_factory=list)
    domain: str
    window_days: int


# ── pain command output ──

class IssueSummary(BaseModel):
    """Pain command's issue summary."""
    repo: str
    issue_number: int
    title: str
    pain_score: float


class PainCluster(BaseModel):
    """A single pain cluster from the pain command."""
    cluster_id: int
    title: str
    severity: float
    frequency: int
    affected_repos: list[str] = Field(default_factory=list)
    top_issues: list[IssueSummary] = Field(default_factory=list)


class PainPayload(BaseModel):
    """Payload for pain command output."""
    clusters: list[PainCluster] = Field(default_factory=list)
    issue_count: int = 0
    repos_analyzed: list[str] = Field(default_factory=list)


# ── opportunity command output ──

class OpportunityCard(BaseModel):
    """A single opportunity from the rule-engine scorer."""
    title: str
    demand_score: float
    competition_score: float
    gap_score: float
    signals: list[str] = Field(default_factory=list)
    recommended_action: str = ""


class OpportunityPayload(BaseModel):
    """Payload for opportunity command output."""
    opportunities: list[OpportunityCard] = Field(default_factory=list)
```

- [ ] **Step 2: Update models/__init__.py — add payload re-exports**

```python
from models.payload import (
    SandboxResult,
    RepoSignal, IssueSignal, CollectPayload,
    TopicTrend, RepoSummary, TrendPayload,
    PainCluster, IssueSummary, PainPayload,
    OpportunityCard, OpportunityPayload,
)
```

- [ ] **Step 3: Verify imports work**

```bash
PYTHONPATH=. python -c "from models.payload import SandboxResult, TopicTrend, PainCluster, OpportunityCard; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add models/payload.py models/__init__.py
git commit -m "feat: add sandbox payload models for dual-loop refactor"
```

---

### Task 2: Simplify Config

**Files:**
- Modify: `config.py`
- Modify: `config.yaml`

**Interfaces:**
- Produces: `load_config(path) -> Config` — simplified, no LLM/weights/compare/discovery

- [ ] **Step 1: Rewrite config.py**

```python
"""Configuration system for BuilderDNA.

Loads config.yaml with environment variable substitution (${VAR} syntax).
Auto-loads .env file if present.
"""
import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, val = line.partition('=')
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = val


_load_dotenv(Path(".env"))


class GitHubConfig(BaseModel):
    token: str
    cache_dir: str = "snapshots/cache"
    max_concurrent: int = Field(default=5, ge=1, le=20)
    rate_limit_margin: int = Field(default=50, ge=10, le=500)


class EmbeddingConfig(BaseModel):
    model: str = "bge-m3:latest"
    base_url: str = "http://localhost:11434/v1"


class OutputConfig(BaseModel):
    dir: str = "./output"
    formats: list[str] = ["markdown", "json"]


class VendorConfig(BaseModel):
    domestic: list[str] = Field(default_factory=list)
    overseas: list[str] = Field(default_factory=list)


class Config(BaseModel):
    accounts: list[str] = Field(default_factory=list)
    domains: dict[str, dict] = Field(default_factory=dict)
    github: GitHubConfig
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    vendors: VendorConfig = Field(default_factory=VendorConfig)


_ENV_VAR_RE = re.compile(r"\$\{(\w+(?::-[^}]*)?)\}")


def _resolve_env(value: str) -> str:
    if not isinstance(value, str):
        return value

    def _replace(m):
        expr = m.group(1)
        if ":-" in expr:
            var, default = expr.split(":-", 1)
            return os.environ.get(var, default)
        return os.environ.get(expr, m.group(0))

    return _ENV_VAR_RE.sub(_replace, value)


def _resolve_config(data: dict) -> dict:
    resolved = {}
    for key, value in data.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_config(value)
        elif isinstance(value, str):
            resolved[key] = _resolve_env(value)
        elif isinstance(value, list):
            resolved[key] = [
                _resolve_env(v) if isinstance(v, str) else v for v in value
            ]
        else:
            resolved[key] = value
    return resolved


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        raw = yaml.safe_load(f)
    resolved = _resolve_config(raw)
    return Config(**resolved)
```

- [ ] **Step 2: Rewrite config.yaml**

```yaml
accounts:
  - hwchase17

github:
  token: ${GITHUB_TOKEN}
  cache_dir: snapshots/cache
  max_concurrent: 5
  rate_limit_margin: 50

embedding:
  model: bge-m3:latest
  base_url: ${EMBEDDING_BASE_URL:-http://localhost:11434/v1}

domains:
  agent:
    topics:
      - mcp
      - langchain
      - agent-framework
      - llm
      - rag
      - tool-calling
      - multi-agent

vendors:
  domestic:
    - deepseek-ai
    - QwenLM
    - THUDM
    - MoonshotAI
  overseas:
    - anthropics
    - langchain-ai
    - browser-use
    - crewAIInc
    - modelcontextprotocol

output:
  dir: ./output
  formats:
    - markdown
    - json
```

- [ ] **Step 3: Verify config loads**

```bash
PYTHONPATH=. python -c "from config import load_config; c = load_config('config.yaml'); print(f'accounts={c.accounts}, domains={list(c.domains.keys())}')"
```

Expected: `accounts=['hwchase17'], domains=['agent']`

- [ ] **Step 4: Commit**

```bash
git add config.py config.yaml
git commit -m "refactor: simplify config — remove LLM/weights/compare/discovery/follow_groups"
```

---

### Task 3: Collect Command

**Files:**
- Create: `cli/commands/__init__.py`
- Create: `cli/commands/collect.py`

**Interfaces:**
- Consumes: `config.load_config`, `collector.github.repo.fetch_top_repos`, `collector.github.issue.fetch_issues`, `collector.github.client.GitHubClient`, `collector.normalizer.normalize_all`, `models.payload.*`
- Produces: `cli/commands/collect.py` — Typer command `collect` that outputs `signals.json`

- [ ] **Step 1: Create cli/commands/__init__.py (empty)**

```python
"""BuilderDNA sandbox commands."""
```

- [ ] **Step 2: Write cli/commands/collect.py**

```python
"""collect — fetch GitHub repos and issues for a domain, output structured signals."""
import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console

from config import load_config
from collector.github.client import GitHubClient
from collector.github.repo import fetch_top_repos
from collector.github.issue import fetch_issues, DEMAND_LABELS
from collector.normalizer import normalize_all
from models.payload import SandboxResult, CollectPayload, RepoSignal, IssueSignal

console = Console()
DEMAND_SET = set(DEMAND_LABELS)


async def _run_collect(
    domain: str, window: int, output: str, config_path: str
) -> None:
    cfg = load_config(config_path)
    domain_config = cfg.domains.get(domain)
    if not domain_config:
        console.print(f"[red]Unknown domain: {domain}[/red]")
        raise typer.Exit(1)

    topics = domain_config.get("topics", [])
    client = GitHubClient(
        token=cfg.github.token,
        cache_dir=cfg.github.cache_dir,
        max_concurrent=cfg.github.max_concurrent,
        rate_limit_margin=cfg.github.rate_limit_margin,
    )

    all_repos: list[dict] = []
    all_issues: list[dict] = []
    seen_repos: set[str] = set()

    try:
        # Step 1: Topic repos
        for topic in topics:
            repos = await fetch_top_repos(client, topic)
            for r in repos:
                fn = r.get("full_name", "")
                if fn in seen_repos:
                    continue
                seen_repos.add(fn)
                all_repos.append(r)

        # Step 2: Demand issues from top repos
        top_names = [r["full_name"] for r in all_repos[:5] if r.get("full_name")]
        issue_tasks = [fetch_issues(client, name, max_issues=30) for name in top_names]
        issue_results = await asyncio.gather(*issue_tasks, return_exceptions=True)
        for issues in issue_results:
            if isinstance(issues, list):
                for iss in issues:
                    iss_labels = iss.get("labels", [])
                    if (any(lbl in DEMAND_SET for lbl in iss_labels)
                            or iss.get("reactions", 0) >= 5
                            or iss.get("comments", 0) >= 10):
                        all_issues.append(iss)

        # Step 3: Vendor + account repos
        vendor_accounts: list[tuple[str, str]] = []
        for account in cfg.accounts:
            vendor_accounts.append((account, "account"))
        for account in cfg.vendors.domestic:
            vendor_accounts.append((account, "domestic"))
        for account in cfg.vendors.overseas:
            vendor_accounts.append((account, "overseas"))

        seen_vendor: set[str] = set()
        for account, tag in vendor_accounts:
            if account in seen_vendor:
                continue
            seen_vendor.add(account)
            try:
                repos = await client.get_repos(account)
                repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
                for r in repos[:5]:
                    fn = r.get("full_name", "")
                    if fn not in seen_repos:
                        seen_repos.add(fn)
                        all_repos.append(r)
            except Exception:
                pass
    finally:
        await client.close()

    # Normalize to unified signals
    signals = normalize_all(raw_repos=all_repos, raw_issues=all_issues)

    # Build payload
    repo_signals = []
    issue_signals = []
    for s in signals:
        if s.type in ("repo_created", "star_growth"):
            repo_signals.append(RepoSignal(
                full_name=s.target_repo,
                owner=s.actor,
                stars=s.payload.get("stars", 0),
                forks=s.payload.get("forks", 0),
                contributors=s.payload.get("contributors", 0),
                velocity=s.velocity,
                topics=s.payload.get("topics", []),
                description=s.payload.get("description", ""),
                language=s.payload.get("language", ""),
                created_at=str(s.payload.get("created_at", "")),
            ))
        elif s.type == "issue_opened":
            issue_signals.append(IssueSignal(
                repo=s.target_repo,
                issue_number=s.payload.get("issue_number", 0),
                title=s.payload.get("title", ""),
                body=s.payload.get("body", ""),
                comments=s.payload.get("comments", 0),
                participants=s.payload.get("participants", 0),
                reactions=s.payload.get("reactions", 0),
                labels=s.payload.get("labels", []),
                url=s.payload.get("url", ""),
            ))

    result = SandboxResult(
        command="collect",
        domain=domain,
        payload=CollectPayload(repos=repo_signals, issues=issue_signals).model_dump(),
        stats={
            "total_signals": len(signals),
            "repos": len(repo_signals),
            "issues": len(issue_signals),
            "topics_searched": len(topics),
            "vendors_scanned": len(vendor_accounts),
        },
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    console.print(f"[green]Collected {len(repo_signals)} repos + {len(issue_signals)} issues → {output}[/green]")


def collect(
    domain: str = typer.Argument(..., help="Domain to collect signals for"),
    window: int = typer.Option(60, "--window", "-w", help="Time window in days"),
    output: str = typer.Option("output/signals.json", "--output", "-o", help="Output JSON file"),
    config: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
) -> None:
    """Collect GitHub signals for a domain."""
    asyncio.run(_run_collect(domain, window, output, config))
```

- [ ] **Step 3: Verify the command exists and help works**

```bash
PYTHONPATH=. python -c "from cli.commands.collect import collect; print('import OK')"
```

- [ ] **Step 4: Commit**

```bash
git add cli/commands/__init__.py cli/commands/collect.py
git commit -m "feat: add collect sandbox command"
```

---

### Task 4: Trend Command

**Files:**
- Create: `cli/commands/trend.py`

**Interfaces:**
- Consumes: `models.payload.*`, `signals.store.SignalStore`, `signals.graph.SignalGraph`, `intelligence.trend.velocity.compute_acceleration`
- Produces: Typer command `trend` that reads signals JSON, outputs `trends.json`

- [ ] **Step 1: Write cli/commands/trend.py**

```python
"""trend — compute topic-level trend velocity and staging from signals."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from signals.store import SignalStore
from signals.graph import SignalGraph
from signals.models import Signal
from intelligence.trend.velocity import compute_acceleration
from models.payload import (
    SandboxResult, TrendPayload, TopicTrend, RepoSummary,
)

console = Console()


def _resolve_stage(velocity: float, acceleration: float, confidence: float) -> str:
    """Assign lifecycle stage based on velocity + acceleration."""
    if acceleration > 2.0 and confidence > 0.6:
        return "accelerating"
    if acceleration > 0.5 and confidence > 0.3:
        return "emerging"
    if acceleration < -1.0:
        return "declining"
    return "mainstream"


def trend(
    domain: str = typer.Argument(..., help="Domain name"),
    data: str = typer.Option("output/signals.json", "--data", "-d", help="Input signals JSON"),
    window: int = typer.Option(60, "--window", "-w", help="Time window in days"),
    output: str = typer.Option("output/trends.json", "--output", "-o", help="Output JSON file"),
) -> None:
    """Compute topic trends from collected signals."""
    data_path = Path(data)
    if not data_path.exists():
        console.print(f"[red]Input file not found: {data}[/red]")
        raise typer.Exit(1)

    raw = json.loads(data_path.read_text())
    payload = raw.get("payload", raw)

    # Reconstruct signals
    repo_signals = []
    for r in payload.get("repos", []):
        s = Signal(
            source="github",
            type="repo_created",
            actor=r.get("owner", ""),
            target_repo=r.get("full_name", ""),
            velocity=r.get("velocity", 0),
            impact=min(1.0, r.get("stars", 0) / 10000.0),
            payload={
                "topics": r.get("topics", []),
                "stars": r.get("stars", 0),
                "forks": r.get("forks", 0),
                "contributors": r.get("contributors", 0),
                "description": r.get("description", ""),
                "created_at": r.get("created_at", ""),
            },
        )
        repo_signals.append(s)

    # Insert into store and graph
    store = SignalStore()
    store.insert(repo_signals)
    trend_rows = store.get_topic_trends(days=window)

    graph = SignalGraph()
    graph.build_from_signals(repo_signals)

    # Group signals by topic
    topic_signals: dict[str, list[Signal]] = {}
    for s in repo_signals:
        for topic in s.payload.get("topics", []):
            topic_signals.setdefault(topic, []).append(s)

    # Build trend output
    trends = []
    for t in trend_rows:
        sigs = topic_signals.get(t.topic, [])
        accel = compute_acceleration(sigs, window_days=window)
        stage = _resolve_stage(t.growth_velocity, accel, t.confidence)

        top_repos = []
        for rt in t.top_repos[:5]:
            top_repos.append(RepoSummary(
                full_name=rt.full_name,
                stars=rt.stars,
                stars_delta=rt.stars_delta,
                forks=rt.forks,
                contributors=rt.contributors,
                velocity=rt.velocity,
                description="",
            ))

        trends.append(TopicTrend(
            topic=t.topic,
            stage=stage,
            confidence=t.confidence,
            growth_velocity=t.growth_velocity,
            acceleration=round(accel, 2),
            evidence_count=t.evidence_count,
            top_repos=top_repos,
        ))

    trends.sort(key=lambda x: x.growth_velocity, reverse=True)

    result = SandboxResult(
        command="trend",
        domain=domain,
        payload=TrendPayload(trends=trends, domain=domain, window_days=window).model_dump(),
        stats={"total_trends": len(trends)},
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    console.print(f"[green]{len(trends)} trends computed → {output}[/green]")
    for t in trends[:5]:
        console.print(f"  {t.stage:15s} {t.topic:25s} v={t.growth_velocity:.1f}")
```

- [ ] **Step 2: Verify import**

```bash
PYTHONPATH=. python -c "from cli.commands.trend import trend; print('import OK')"
```

- [ ] **Step 3: Commit**

```bash
git add cli/commands/trend.py
git commit -m "feat: add trend sandbox command"
```

---

### Task 5: Pain Command

**Files:**
- Create: `cli/commands/pain.py`

**Interfaces:**
- Consumes: `models.payload.*`, `intelligence.pain.cluster.PainClusterer`, `intelligence.pain.severity.compute_severity`, embedding API
- Produces: Typer command `pain` that reads signals JSON, outputs `pain_clusters.json`

- [ ] **Step 1: Write cli/commands/pain.py**

```python
"""pain — cluster issue signals via HDBSCAN, output pain clusters."""
import json
import math
from pathlib import Path

import typer
from rich.console import Console

from intelligence.pain.cluster import PainClusterer
from intelligence.pain.severity import compute_severity
from models.payload import (
    SandboxResult, PainPayload, PainCluster, IssueSummary,
)

console = Console()


def _get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embeddings for a list of texts."""
    import os
    from openai import OpenAI

    base_url = os.environ.get("EMBEDDING_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("EMBEDDING_MODEL", "bge-m3:latest")
    client = OpenAI(base_url=base_url, api_key="ollama")

    embeddings = []
    for i in range(0, len(texts), 50):
        batch = texts[i:i + 50]
        resp = client.embeddings.create(model=model, input=batch)
        embeddings.extend([d.embedding for d in resp.data])
    return embeddings


def pain(
    domain: str = typer.Argument(..., help="Domain name"),
    data: str = typer.Option("output/signals.json", "--data", "-d", help="Input signals JSON"),
    output: str = typer.Option("output/pain_clusters.json", "--output", "-o", help="Output JSON file"),
) -> None:
    """Mine pain points from collected issue signals."""
    data_path = Path(data)
    if not data_path.exists():
        console.print(f"[red]Input file not found: {data}[/red]")
        raise typer.Exit(1)

    raw = json.loads(data_path.read_text())
    payload = raw.get("payload", raw)
    issues = payload.get("issues", [])

    if not issues:
        result = SandboxResult(
            command="pain",
            domain=domain,
            payload=PainPayload().model_dump(),
            stats={"issue_count": 0, "repos_analyzed": []},
        )
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
        console.print("[yellow]No issues to cluster[/yellow]")
        return

    # Build texts for embedding
    texts = [f"{iss.get('title', '')}\n{iss.get('body', '')}"[:1000] for iss in issues]

    # Get embeddings and cluster
    try:
        embeddings = _get_embeddings(texts)
    except Exception as e:
        console.print(f"[yellow]Embedding failed: {e}. Falling back to title-based grouping.[/yellow]")
        embeddings = []

    pain_clusters_list = []
    if embeddings:
        clusterer = PainClusterer(min_cluster_size=3)
        clusters = clusterer.fit(embeddings)
        for cluster_id, indices in clusters.items():
            cluster_issues = [issues[i] for i in indices]
            severities = [
                compute_severity(
                    iss.get("comments", 0),
                    iss.get("participants", 0),
                    (iss.get("title", "") + " " + iss.get("body", ""))[:500],
                    iss.get("reactions", 0),
                )
                for iss in cluster_issues
            ]
            repos = list(set(iss.get("repo", "") for iss in cluster_issues))
            top = sorted(cluster_issues, key=lambda x: x.get("reactions", 0) + x.get("comments", 0), reverse=True)[:3]

            pain_clusters_list.append(PainCluster(
                cluster_id=cluster_id,
                title=f"Pain Cluster {cluster_id}",
                severity=round(sum(severities) / len(severities), 2),
                frequency=len(cluster_issues),
                affected_repos=repos,
                top_issues=[
                    IssueSummary(
                        repo=iss.get("repo", ""),
                        issue_number=iss.get("issue_number", 0),
                        title=iss.get("title", "")[:100],
                        pain_score=compute_severity(
                            iss.get("comments", 0),
                            iss.get("participants", 0),
                            (iss.get("title", "") + " " + iss.get("body", ""))[:500],
                            iss.get("reactions", 0),
                        ),
                    )
                    for iss in top
                ],
            ))

    result = SandboxResult(
        command="pain",
        domain=domain,
        payload=PainPayload(
            clusters=pain_clusters_list,
            issue_count=len(issues),
            repos_analyzed=list(set(iss.get("repo", "") for iss in issues)),
        ).model_dump(),
        stats={"clusters": len(pain_clusters_list), "issues_analyzed": len(issues)},
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    console.print(f"[green]{len(pain_clusters_list)} pain clusters → {output}[/green]")
```

- [ ] **Step 2: Verify import**

```bash
PYTHONPATH=. python -c "from cli.commands.pain import pain; print('import OK')"
```

- [ ] **Step 3: Commit**

```bash
git add cli/commands/pain.py
git commit -m "feat: add pain sandbox command"
```

---

### Task 6: Opportunity Command (Rule Engine)

**Files:**
- Create: `cli/commands/opportunity.py`

**Interfaces:**
- Consumes: `models.payload.*`
- Produces: Typer command `opportunity` — pure rule-engine scoring, no LLM

- [ ] **Step 1: Write cli/commands/opportunity.py**

```python
"""opportunity — rule-engine scorer that generates opportunity cards.

No LLM calls. Uses deterministic formulas:
  demand_score = f(trend_velocity, pain_severity, pain_frequency)
  competition_score = f(evidence_count, repo_maturity)
  gap_score = demand / competition
"""
import json
import math
from pathlib import Path

import typer
from rich.console import Console

from models.payload import (
    SandboxResult, OpportunityPayload, OpportunityCard,
)

console = Console()


def _compute_demand(trends: list[dict], pain_clusters: list[dict]) -> float:
    """Demand score from trend velocity + pain intensity."""
    avg_velocity = sum(t.get("growth_velocity", 0) for t in trends) / max(1, len(trends))
    avg_severity = sum(p.get("severity", 0) for p in pain_clusters) / max(1, len(pain_clusters))
    total_frequency = sum(p.get("frequency", 0) for p in pain_clusters)

    # Normalize to 1-10
    vel_score = min(10, avg_velocity / 10)  # velocity 100 → 10
    pain_score = min(10, avg_severity * 2)  # severity 5 → 10
    freq_score = min(10, math.log(total_frequency + 1) * 3)  # log scale

    return round((vel_score * 0.4 + pain_score * 0.4 + freq_score * 0.2), 1)


def _compute_competition(trends: list[dict]) -> float:
    """Competition score: more evidence → more crowded."""
    total_evidence = sum(t.get("evidence_count", 0) for t in trends)
    total_repos = sum(len(t.get("top_repos", [])) for t in trends)

    # More repos + higher count = more competition
    raw = math.log(total_evidence + 1) * 1.5 + math.log(total_repos + 1)
    return round(min(10, max(1, raw)), 1)


def _generate_actions(trends: list[dict], pain_clusters: list[dict]) -> list[OpportunityCard]:
    """Generate opportunity cards from trend + pain intersections."""
    cards = []
    top_trends = sorted(trends, key=lambda t: t.get("growth_velocity", 0), reverse=True)[:5]
    top_pains = sorted(pain_clusters, key=lambda p: p.get("severity", 0), reverse=True)[:5]

    for trend in top_trends:
        topic = trend.get("topic", "unknown")
        velocity = trend.get("growth_velocity", 0)

        # Find intersecting pain clusters
        related_pains = [
            p for p in top_pains
            if any(topic.lower() in r.lower() for r in p.get("affected_repos", []))
        ] or top_pains[:2]

        demand = _compute_demand([trend], related_pains)
        competition = _compute_competition([trend])
        gap = round(demand / max(0.1, competition), 1)

        # Signal list from evidence
        signals = []
        for r in trend.get("top_repos", [])[:3]:
            signals.append(f"{r.get('full_name', '')} ({r.get('stars', 0)}★)")
        for p in related_pains[:1]:
            for iss in p.get("top_issues", [])[:2]:
                signals.append(f"Issue: {iss.get('title', '')[:60]}")

        # Heuristic action recommendation
        if gap > 2.0:
            action = f"强烈推荐在 {topic} 方向创业或立项，缺口显著"
        elif gap > 1.5:
            action = f"密切关注 {topic}，需求强但已有竞争，需差异化切入"
        elif gap > 1.0:
            action = f"跟踪 {topic} 发展，等待更明确的市场信号"
        else:
            action = f"暂不建议进入 {topic}，竞争饱和或需求不足"

        cards.append(OpportunityCard(
            title=f"{topic} — gap={gap}",
            demand_score=demand,
            competition_score=competition,
            gap_score=gap,
            signals=signals[:5],
            recommended_action=action,
        ))

    cards.sort(key=lambda c: c.gap_score, reverse=True)
    return cards


def opportunity(
    trends: str = typer.Option(..., "--trends", "-t", help="Input trends JSON"),
    pains: str = typer.Option(..., "--pains", "-p", help="Input pain clusters JSON"),
    output: str = typer.Option("output/opportunities.json", "--output", "-o", help="Output JSON file"),
) -> None:
    """Generate opportunity cards from trends and pain clusters (rule engine)."""
    trends_path = Path(trends)
    pains_path = Path(pains)
    if not trends_path.exists():
        console.print(f"[red]Trends file not found: {trends}[/red]")
        raise typer.Exit(1)
    if not pains_path.exists():
        console.print(f"[yellow]Pain file not found: {pains}. Continuing without pain data.[/yellow]")
        pains_data = {"payload": {"clusters": []}}
    else:
        pains_data = json.loads(pains_path.read_text())

    trends_data = json.loads(trends_path.read_text())
    t_payload = trends_data.get("payload", trends_data)
    p_payload = pains_data.get("payload", pains_data)

    trend_list = t_payload.get("trends", [])
    pain_list = p_payload.get("clusters", [])

    cards = _generate_actions(trend_list, pain_list)

    result = SandboxResult(
        command="opportunity",
        domain=t_payload.get("domain", ""),
        payload=OpportunityPayload(opportunities=cards).model_dump(),
        stats={
            "total": len(cards),
            "avg_gap": round(sum(c.gap_score for c in cards) / max(1, len(cards)), 2),
        },
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    console.print(f"[green]{len(cards)} opportunities → {output}[/green]")
    for c in cards[:5]:
        console.print(f"  gap={c.gap_score:.1f}  {c.title}")
```

- [ ] **Step 2: Verify import**

```bash
PYTHONPATH=. python -c "from cli.commands.opportunity import opportunity; print('import OK')"
```

- [ ] **Step 3: Commit**

```bash
git add cli/commands/opportunity.py
git commit -m "feat: add opportunity sandbox command (rule engine)"
```

---

### Task 7: Report Command

**Files:**
- Create: `cli/commands/report_cmd.py`

**Interfaces:**
- Consumes: `models.payload.*`, `report/builder_report.py`
- Produces: Typer command `report` — read any structured result JSON, render markdown

- [ ] **Step 1: Write cli/commands/report_cmd.py**

```python
"""report — render structured results to Markdown or JSON."""
import json
from pathlib import Path
from datetime import datetime

import typer
from rich.console import Console

console = Console()


def _render_md(data: dict, output_path: Path) -> str:
    """Render a structured result dict to Markdown."""
    payload = data.get("payload", data)
    lines = [
        f"# BuilderDNA Report\n",
        f"**Command:** {data.get('command', 'unknown')}",
        f"**Domain:** {data.get('domain', '')}",
        f"**Generated:** {datetime.now().isoformat()}\n",
    ]

    # Trends section
    trends = payload.get("trends", [])
    if trends:
        lines.append("## Trends\n")
        lines.append("| Topic | Stage | Velocity | Evidence |")
        lines.append("|-------|-------|----------|----------|")
        for t in trends:
            lines.append(f"| {t.get('topic', '')} | {t.get('stage', '')} | {t.get('growth_velocity', 0):.1f} | {t.get('evidence_count', 0)} |")
        lines.append("")

    # Pain clusters
    clusters = payload.get("clusters", [])
    if clusters:
        lines.append("## Pain Points\n")
        for c in clusters:
            lines.append(f"### {c.get('title', '')}")
            lines.append(f"- Severity: {c.get('severity', 0):.1f}")
            lines.append(f"- Frequency: {c.get('frequency', 0)} issues")
            lines.append(f"- Affected: {', '.join(c.get('affected_repos', []))}")
            lines.append("")

    # Opportunities
    opps = payload.get("opportunities", [])
    if opps:
        lines.append("## Opportunities\n")
        for i, o in enumerate(opps, 1):
            lines.append(f"### {i}. {o.get('title', '')}")
            lines.append(f"- **Gap Score:** {o.get('gap_score', 0):.1f}")
            lines.append(f"- Demand: {o.get('demand_score', 0):.1f} / Competition: {o.get('competition_score', 0):.1f}")
            lines.append(f"- Action: {o.get('recommended_action', '')}")
            signals = o.get("signals", [])
            if signals:
                lines.append(f"- Signals: {'; '.join(signals[:3])}")
            lines.append("")

    content = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
    return str(output_path)


def report(
    data: str = typer.Option(..., "--data", "-d", help="Input result JSON"),
    fmt: str = typer.Option("md", "--format", "-f", help="Output format: md or json"),
    output_dir: str = typer.Option("./output", "--output-dir", "-o", help="Output directory"),
) -> None:
    """Render structured results to a report."""
    data_path = Path(data)
    if not data_path.exists():
        console.print(f"[red]Input file not found: {data}[/red]")
        raise typer.Exit(1)

    raw = json.loads(data_path.read_text())
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")

    if fmt == "json":
        out = Path(output_dir) / f"report-{ts}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
    else:
        out = Path(output_dir) / f"report-{ts}.md"
        _render_md(raw, out)

    console.print(f"[green]Report → {out}[/green]")
```

- [ ] **Step 2: Verify import**

```bash
PYTHONPATH=. python -c "from cli.commands.report_cmd import report; print('import OK')"
```

- [ ] **Step 3: Commit**

```bash
git add cli/commands/report_cmd.py
git commit -m "feat: add report sandbox command"
```

---

### Task 8: CLI Entry Point

**Files:**
- Create: `cli/main.py`

**Interfaces:**
- Consumes: All `cli/commands/*.py`
- Produces: `builderdna` Typer app with 5 subcommands

- [ ] **Step 1: Write cli/main.py**

```python
"""BuilderDNA CLI entry point."""
import typer
from rich.console import Console

from cli.commands.collect import collect
from cli.commands.trend import trend
from cli.commands.pain import pain
from cli.commands.opportunity import opportunity
from cli.commands.report_cmd import report

app = typer.Typer(
    name="builderdna",
    help="BuilderDNA — Technology Intelligence Sandbox Toolkit",
)
console = Console()

app.command(name="collect")(collect)
app.command(name="trend")(trend)
app.command(name="pain")(pain)
app.command(name="opportunity")(opportunity)
app.command(name="report")(report)

if __name__ == "__main__":
    app()
```

- [ ] **Step 2: Verify CLI loads**

```bash
PYTHONPATH=. python cli/main.py --help
```

Expected: shows collect, trend, pain, opportunity, report commands

- [ ] **Step 3: Commit**

```bash
git add cli/main.py
git commit -m "feat: add unified CLI entry point for sandbox commands"
```

---

### Task 9: Hypothesis Tree, User Weights, and Schema Doc

**Files:**
- Create: `state/hypotheses.json`
- Create: `state/user_weights.json`
- Create: `schema.md`

- [ ] **Step 1: Create state/hypotheses.json**

```json
{
  "version": 1,
  "last_updated": "",
  "domain": "agent",
  "nodes": []
}
```

- [ ] **Step 2: Create state/user_weights.json**

```json
{
  "preferred_domains": [],
  "avoid_tags": [],
  "scoring_bias": {},
  "feedback_log": []
}
```

- [ ] **Step 3: Create schema.md**

Write a Claude-readable schema reference:

```markdown
# BuilderDNA Sandbox Schema Reference

Claude Code reads these JSON outputs. Every command wraps results in `SandboxResult`.

## Common Wrapper

```json
{"command": "<name>", "domain": "<domain>", "computed_at": "<ISO8601>", "payload": {...}, "stats": {...}}
```

## collect → output/signals.json

payload.repos[]: { full_name, owner, stars, forks, contributors, velocity, topics[], description, language, created_at }
payload.issues[]: { repo, issue_number, title, body, comments, participants, reactions, labels[], url }

stats: { total_signals, repos, issues, topics_searched, vendors_scanned }

## trend → output/trends.json

payload.trends[]: { topic, stage (accelerating|emerging|mainstream|declining), confidence, growth_velocity, acceleration, evidence_count, top_repos[{full_name, stars, stars_delta, forks, contributors, velocity, description}] }
stats: { total_trends }

## pain → output/pain_clusters.json

payload.clusters[]: { cluster_id, title, severity, frequency, affected_repos[], top_issues[{repo, issue_number, title, pain_score}] }
stats: { clusters, issues_analyzed }

## opportunity → output/opportunities.json

payload.opportunities[]: { title, demand_score, competition_score, gap_score, signals[], recommended_action }
stats: { total, avg_gap }

## report → output/report-*.md|json

Renders any SandboxResult to Markdown tables or JSON.
```

- [ ] **Step 4: Commit**

```bash
git add state/hypotheses.json state/user_weights.json schema.md
git commit -m "feat: add hypothesis tree, user weights, and schema doc"
```

---

### Task 10: Delete Old Files

**Files to delete:**
- `pipeline/` (entire directory)
- `pipeline.py`
- `control_plane/` (entire directory)
- `backend/` (entire directory)
- `llm/` (entire directory, except if embeddings used elsewhere)
- `cli.py`
- `cli/formatters.py`
- `output/cli.py`

- [ ] **Step 1: Delete old directories and files**

```bash
rm -rf pipeline/ pipeline.py control_plane/ backend/ llm/
rm -f cli.py cli/formatters.py output/cli.py
```

- [ ] **Step 2: Verify no broken imports**

```bash
PYTHONPATH=. python -c "from cli.main import app; print('CLI OK')"
PYTHONPATH=. python -c "from config import load_config; print('Config OK')"
PYTHONPATH=. python -c "from models.payload import SandboxResult; print('Models OK')"
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: delete LangGraph pipeline, HCP, backend, LLM, and old CLI"
```

---

### Task 11: Update pyproject.toml and .env

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env`

- [ ] **Step 1: Update pyproject.toml**

Remove unused dependencies: `langgraph`, `openai`, `fastapi`, `uvicorn`, `chromadb`. Remove old entry points. Set new entry point to `cli.main:app`.

```toml
[project.scripts]
builderdna = "cli.main:app"
```

Remove from `packages.find.include`: `backend*`, `pipeline*`, `control_plane*`, `llm*`

- [ ] **Step 2: Update .env**

Remove `OPENAI_API_KEY` and `LLM_BASE_URL`. Keep `GITHUB_TOKEN` and `EMBEDDING_BASE_URL`.

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
EMBEDDING_BASE_URL=http://localhost:11434/v1
```

- [ ] **Step 3: Verify entry point**

```bash
uv pip install -e .
PYTHONPATH=. builderdna --help
```

Expected: shows all 5 commands

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml .env
git commit -m "chore: update dependencies, entry point, and env for dual-loop refactor"
```

---

### Task 12: Update Skill

**Files:**
- Modify: `.claude/skills/builderdna/SKILL.md`

Update the SKILL.md to match the new 5-command architecture plus hypothesis tree workflow.

Key changes:
- Replace command map with new 5 commands
- Add hypothesis tree workflow section
- Add user weights application
- Remove v1/v2 references
- Add `schema.md` reference

- [ ] **Step 1: Rewrite SKILL.md**

Key changes from current version:
1. Command map → 5 new commands (collect/trend/pain/opportunity/report)
2. Add hypothesis tree workflow section
3. Add schema.md reference
4. Remove v1/v2 and LLM pipeline sections
5. New section: "Hypothesis Tree Workflow" — read hypotheses.json → run sandboxes → update nodes → present findings

Write the updated SKILL.md with these sections:
- Quick command map (5 commands with natural language triggers)
- Hypothesis tree workflow (read/update/prune cycle)
- User weights application (read user_weights.json, bias interpretation)
- Config management (simplified — just accounts, domains, vendors, embedding)
- Schema reference (pointer to schema.md)
- Troubleshooting (GITHUB_TOKEN, embedding endpoint, rate limits)

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/builderdna/SKILL.md
git commit -m "docs: update skill for dual-loop refactor"
```

---

### Task 13: End-to-End Verification

- [ ] **Step 1: Full pipeline test**

```bash
PYTHONPATH=. builderdna collect agent -w 30 -o /tmp/test_signals.json
PYTHONPATH=. builderdna trend agent -d /tmp/test_signals.json -o /tmp/test_trends.json
PYTHONPATH=. builderdna pain agent -d /tmp/test_signals.json -o /tmp/test_pains.json
PYTHONPATH=. builderdna opportunity -t /tmp/test_trends.json -p /tmp/test_pains.json -o /tmp/test_opps.json
PYTHONPATH=. builderdna report -d /tmp/test_opps.json -f md -o /tmp/
```

Each command should succeed and produce valid JSON output.

- [ ] **Step 2: JSON validation**

```bash
PYTHONPATH=. python -c "
from models.payload import SandboxResult
import json
for f in ['/tmp/test_signals.json', '/tmp/test_trends.json', '/tmp/test_pains.json', '/tmp/test_opps.json']:
    data = json.loads(open(f).read())
    r = SandboxResult(**data)
    print(f'{f}: {r.command} OK, stats={r.stats}')
"
```

- [ ] **Step 3: Verify all old imports are gone**

```bash
grep -r "from pipeline\|from control_plane\|from backend\|from llm.client\|from cli import\|from output.cli" --include="*.py" . | grep -v __pycache__ | grep -v ".git/" | grep -v ".claude/"
```

Expected: no results

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "verify: end-to-end dual-loop pipeline passes"
```
