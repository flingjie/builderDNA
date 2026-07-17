# BuilderDNA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build BuilderDNA — an AI Agent that analyzes GitHub accounts, extracts tech stacks and interests, and generates actionable Opportunity insights via a Collect→Understand→Recommend pipeline.

**Architecture:** Three-layer pipeline (Collect → Understand → Recommend) with Signal as the unified input model, Insight as the semantic middle layer, and Opportunity as the SSOT output. LLM is a utility called at specific points (L2 classification, opportunity detection), not a system layer. SQLite stores snapshots for incremental comparison.

**Tech Stack:** Python 3.11+, pydantic v2, httpx, openai, click, rich, pyyaml, pytest, sqlite3 (stdlib)

## Global Constraints

- Python >= 3.11
- LLM is a Utility, not a layer — no LLM calls in Collect phase
- Signal is the unified input model; all future data sources normalize to it
- Opportunity is SSOT — CLI/Markdown/JSON are just Views
- v1 scope: GitHub only, signal types `repo`/`star`/`commit`, OpenAI only
- Error handling per spec section 6: retry with backoff, LLM degradation, skip-and-continue for non-fatal errors
- All code uses type hints; all public functions have docstrings
- Test files mirror source structure under tests/

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `models/__init__.py`
- Create: `collect/__init__.py`
- Create: `collect/github/__init__.py`
- Create: `insight/__init__.py`
- Create: `opportunity/__init__.py`
- Create: `output/__init__.py`
- Create: `llm/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_models/__init__.py`
- Create: `tests/test_collect/__init__.py`
- Create: `tests/test_insight/__init__.py`
- Create: `tests/test_opportunity/__init__.py`
- Create: `tests/test_llm/__init__.py`
- Create: `tests/test_pipeline/__init__.py`
- Create: `config.yaml`
- Create: `snapshots/.gitkeep`
- Create: `output/.gitkeep`

**Interfaces:**
- Consumes: nothing
- Produces: project directory structure, dependency declarations

- [ ] **Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "builderdna"
version = "0.1.0"
description = "Analyze GitHub builders, extract tech DNA, and discover opportunities"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "httpx>=0.27",
    "openai>=1.0",
    "click>=8.0",
    "rich>=13.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-httpx>=0.30",
]

[project.scripts]
bldr-dna = "cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: Write requirements.txt**

```
pydantic>=2.0
httpx>=0.27
openai>=1.0
click>=8.0
rich>=13.0
pyyaml>=6.0
pytest>=8.0
pytest-httpx>=0.30
```

- [ ] **Step 3: Write .gitignore**

```
__pycache__/
*.pyc
.env
snapshots/*.db
output/*.md
output/*.json
.venv/
```

- [ ] **Step 4: Create all __init__.py files and directory structure**

Run: 
```bash
mkdir -p models collect/github insight opportunity output llm
mkdir -p tests/test_models tests/test_collect tests/test_insight tests/test_opportunity tests/test_llm tests/test_pipeline
mkdir -p snapshots output
touch models/__init__.py collect/__init__.py collect/github/__init__.py insight/__init__.py opportunity/__init__.py output/__init__.py llm/__init__.py
touch tests/__init__.py tests/test_models/__init__.py tests/test_collect/__init__.py tests/test_insight/__init__.py tests/test_opportunity/__init__.py tests/test_llm/__init__.py tests/test_pipeline/__init__.py
touch snapshots/.gitkeep output/.gitkeep
```

- [ ] **Step 5: Write config.yaml template**

```yaml
accounts:
  - placeholder_username

github:
  token: ${GITHUB_TOKEN}

llm:
  provider: openai
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}

weights:
  repo: 5.0
  commit: 3.0
  pr: 2.5
  issue: 1.5
  star: 1.0

output:
  dir: ./output
  formats:
    - markdown
    - json

compare:
  enabled: true
```

- [ ] **Step 6: Verify scaffold**

Run: `python -c "import models; import collect; import insight; import opportunity; import output; import llm; print('All packages importable')"`
Expected: `All packages importable`

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: scaffold project structure and dependencies"
```

---
### Task 2: Domain Models

**Files:**
- Create: `models/signal.py`
- Create: `models/insight.py`
- Create: `models/opportunity.py`
- Modify: `models/__init__.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Signal(id, source, type, timestamp, weight, actor, target, meta, raw)`, `SignalCluster(signals, topics, languages, total_weight, time_span_days, growth_rate)`, `Insight(id, tags, summary, strength, trend, signal_count, evidence, created_at)`, `Opportunity(id, title, pain_point, demand_score, competition_score, gap_score, recommended_action, source_insights, created_at)`

- [ ] **Step 1: Write models/signal.py**

```python
"""Signal domain model — the unified input model for BuilderDNA."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Signal(BaseModel):
    """A unified signal representing one unit of builder activity.

    All data sources (GitHub, future Twitter/ArXiv/etc.) normalize to this model.
    """

    id: str = Field(description="Unique identifier, e.g. 'gh_repo_user_toolkit'")
    source: str = Field(description="Signal source, e.g. 'github'")
    type: str = Field(description="Signal type: 'repo', 'star', 'commit'")
    timestamp: datetime = Field(description="When the signal occurred")
    weight: float = Field(description="Preset weight from config, e.g. 5.0 for repo")
    actor: str = Field(description="The builder account being analyzed")
    target: str = Field(description="Entity identifier, e.g. repo full_name")
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured summary: language, topics, description, etc.",
    )
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Complete raw API response, never discard information",
    )


class SignalCluster(BaseModel):
    """L1 product: a quantitative cluster of related Signals.

    Internal-only — not exposed to output. Feeds into L2 Insight generation.
    """

    signals: list[str] = Field(description="Signal IDs participating in this cluster")
    topics: list[str] = Field(description="Union of all topics across signals")
    languages: list[str] = Field(description="Union of all languages across signals")
    total_weight: float = Field(description="Sum of signal weights")
    time_span_days: int = Field(description="Days between earliest and latest signal")
    growth_rate: float = Field(
        description="Recent 30-day weight / total weight. 0.0 to 1.0"
    )
```

- [ ] **Step 2: Write models/insight.py**

```python
"""Insight domain model — semantic understanding derived from Signal clusters."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Insight(BaseModel):
    """A semantic insight distilled from one or more SignalClusters.

    L2 (LLM) is responsible for generating the summary and tags.
    If LLM is unavailable, a rule-based fallback produces a minimal Insight.
    """

    id: str = Field(description="Unique insight ID, e.g. 'insight_001'")
    tags: list[str] = Field(description="Technology tags, e.g. ['MCP', 'Agent']")
    summary: str = Field(description="One-sentence description of the insight")
    strength: float = Field(description="Weighted sum of supporting signals")
    trend: str = Field(description="'rising' | 'stable' | 'fading'")
    signal_count: int = Field(description="Number of signals supporting this insight")
    evidence: list[str] = Field(
        default_factory=list,
        description="Key evidence: repo names, commit message excerpts",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this insight was generated",
    )
```

- [ ] **Step 3: Write models/opportunity.py**

```python
"""Opportunity domain model — the SSOT output of BuilderDNA."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Opportunity(BaseModel):
    """A product/tool opportunity derived from builder insights.

    Opportunity is the single source of truth. CLI, Markdown, JSON, and
    future dashboards are all just different Views of this model.
    """

    id: str = Field(description="Unique opportunity ID, e.g. 'opp_001'")
    title: str = Field(description="Opportunity direction, e.g. 'Agent Replay Visualizer'")
    pain_point: str = Field(description="Core pain point this opportunity addresses")
    demand_score: float = Field(description="Demand heat 1-5", ge=1.0, le=5.0)
    competition_score: float = Field(
        description="Competition intensity 1-5 (lower = less competition)", ge=1.0, le=5.0
    )
    gap_score: float = Field(
        description="demand / competition — higher means more worth pursuing"
    )
    recommended_action: str = Field(description="Suggested next step")
    source_insights: list[str] = Field(
        description="Insight IDs that support this opportunity"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this opportunity was generated",
    )
```

- [ ] **Step 4: Update models/__init__.py**

```python
"""BuilderDNA domain models."""

from models.signal import Signal, SignalCluster
from models.insight import Insight
from models.opportunity import Opportunity

__all__ = ["Signal", "SignalCluster", "Insight", "Opportunity"]
```

- [ ] **Step 5: Write and run model tests**

Create `tests/test_models/test_signal.py`:

```python
"""Tests for Signal and SignalCluster models."""

from datetime import datetime, timezone

import pytest

from models.signal import Signal, SignalCluster


class TestSignal:
    def test_signal_creation_minimal(self):
        s = Signal(
            id="gh_repo_alice_toolkit",
            source="github",
            type="repo",
            timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc),
            weight=5.0,
            actor="alice",
            target="alice/toolkit",
        )
        assert s.id == "gh_repo_alice_toolkit"
        assert s.source == "github"
        assert s.type == "repo"
        assert s.weight == 5.0
        assert s.meta == {}
        assert s.raw == {}

    def test_signal_creation_full(self):
        s = Signal(
            id="gh_star_alice_fastapi",
            source="github",
            type="star",
            timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
            weight=1.0,
            actor="alice",
            target="tiangolo/fastapi",
            meta={"language": "Python", "topics": ["web", "api"]},
            raw={"full_name": "tiangolo/fastapi", "stargazers_count": 80000},
        )
        assert s.meta["language"] == "Python"
        assert "web" in s.meta["topics"]
        assert s.raw["stargazers_count"] == 80000

    def test_signal_invalid_type(self):
        with pytest.raises(ValueError):
            Signal(
                id="test",
                source="github",
                type="repo",
                timestamp="not-a-datetime",  # type: ignore
                weight=5.0,
                actor="alice",
                target="t",
            )


class TestSignalCluster:
    def test_cluster_creation(self):
        c = SignalCluster(
            signals=["s1", "s2", "s3"],
            topics=["llm", "agent"],
            languages=["Python"],
            total_weight=15.0,
            time_span_days=45,
            growth_rate=0.6,
        )
        assert len(c.signals) == 3
        assert c.total_weight == 15.0
        assert c.growth_rate == 0.6

    def test_cluster_growth_rate_bounds(self):
        c = SignalCluster(
            signals=["s1"],
            topics=["ai"],
            languages=["Rust"],
            total_weight=5.0,
            time_span_days=10,
            growth_rate=1.0,
        )
        assert 0.0 <= c.growth_rate <= 1.0
```

Create `tests/test_models/test_insight.py`:

```python
"""Tests for Insight model."""

from datetime import datetime, timezone

from models.insight import Insight


class TestInsight:
    def test_insight_creation(self):
        i = Insight(
            id="insight_001",
            tags=["MCP", "Agent"],
            summary="Heavy investment in MCP-based agent tooling",
            strength=35.5,
            trend="rising",
            signal_count=12,
            evidence=["alice/mcp-server", "alice/agent-kit"],
        )
        assert i.id == "insight_001"
        assert "MCP" in i.tags
        assert i.trend == "rising"
        assert len(i.evidence) == 2
        assert isinstance(i.created_at, datetime)

    def test_insight_defaults(self):
        i = Insight(
            id="insight_002",
            tags=["Rust"],
            summary="Exploring Rust for systems programming",
            strength=8.0,
            trend="stable",
            signal_count=3,
        )
        assert i.evidence == []
        assert i.created_at is not None
```

Create `tests/test_models/test_opportunity.py`:

```python
"""Tests for Opportunity model."""

from models.opportunity import Opportunity


class TestOpportunity:
    def test_opportunity_creation(self):
        o = Opportunity(
            id="opp_001",
            title="Agent Testing Framework",
            pain_point="No good way to test LLM agent behavior",
            demand_score=4.5,
            competition_score=2.0,
            gap_score=2.25,
            recommended_action="Build MVP with pytest integration",
            source_insights=["insight_001", "insight_002"],
        )
        assert o.id == "opp_001"
        assert o.gap_score == 2.25
        assert len(o.source_insights) == 2

    def test_score_bounds(self):
        import pytest

        with pytest.raises(ValueError):
            Opportunity(
                id="bad",
                title="Bad",
                pain_point="x",
                demand_score=6.0,  # out of range
                competition_score=1.0,
                gap_score=6.0,
                recommended_action="don't",
                source_insights=[],
            )
```

- [ ] **Step 6: Run model tests**

Run: `python -m pytest tests/test_models/ -v`
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add models/ tests/test_models/
git commit -m "feat: add domain models — Signal, SignalCluster, Insight, Opportunity"
```

---
### Task 3: Config System

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: `config.yaml`
- Produces: `Config(accounts, github, llm, weights, output, compare)`, `GitHubConfig(token)`, `LLMConfig(provider, model, api_key)`, `WeightConfig(repo, commit, pr, issue, star)`, `OutputConfig(dir, formats)`, `CompareConfig(enabled)`, `load_config(path)` function

- [ ] **Step 1: Write failing tests for config**

Create `tests/test_config.py`:

```python
"""Tests for config loading."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from config import Config, load_config


VALID_CONFIG = {
    "accounts": ["alice", "bob"],
    "github": {"token": "ghp_test123"},
    "llm": {"provider": "openai", "model": "gpt-4o", "api_key": "sk-test"},
    "weights": {"repo": 5.0, "commit": 3.0, "pr": 2.5, "issue": 1.5, "star": 1.0},
    "output": {"dir": "./output", "formats": ["markdown", "json"]},
    "compare": {"enabled": True},
}


@pytest.fixture
def config_file():
    """Create a temporary config.yaml."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        yaml.dump(VALID_CONFIG, f)
        path = f.name
    yield path
    os.unlink(path)


class TestLoadConfig:
    def test_loads_valid_config(self, config_file):
        cfg = load_config(config_file)
        assert cfg.accounts == ["alice", "bob"]
        assert cfg.github.token == "ghp_test123"
        assert cfg.llm.model == "gpt-4o"
        assert cfg.weights.repo == 5.0
        assert cfg.output.formats == ["markdown", "json"]
        assert cfg.compare.enabled is True

    def test_env_var_substitution(self):
        os.environ["TEST_GH_TOKEN"] = "ghp_from_env"
        os.environ["TEST_OAI_KEY"] = "sk_from_env"
        cfg_data = dict(VALID_CONFIG)
        cfg_data["github"]["token"] = "${TEST_GH_TOKEN}"
        cfg_data["llm"]["api_key"] = "${TEST_OAI_KEY}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(cfg_data, f)
            path = f.name
        try:
            cfg = load_config(path)
            assert cfg.github.token == "ghp_from_env"
            assert cfg.llm.api_key == "sk_from_env"
        finally:
            os.unlink(path)
            del os.environ["TEST_GH_TOKEN"]
            del os.environ["TEST_OAI_KEY"]

    def test_loads_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")


class TestConfigModel:
    def test_default_compare(self, config_file):
        cfg = load_config(config_file)
        assert cfg.compare.enabled is True
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write config.py**

```python
"""Configuration system for BuilderDNA.

Loads config.yaml with environment variable substitution (${VAR} syntax).
"""

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class GitHubConfig(BaseModel):
    """GitHub API configuration."""

    token: str = Field(description="GitHub Personal Access Token")


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = Field(default="openai", description="LLM provider name")
    model: str = Field(default="gpt-4o", description="Model ID")
    api_key: str = Field(description="API key for the LLM provider")


class WeightConfig(BaseModel):
    """Signal weight configuration."""

    repo: float = 5.0
    commit: float = 3.0
    pr: float = 2.5
    issue: float = 1.5
    star: float = 1.0


class OutputConfig(BaseModel):
    """Output configuration."""

    dir: str = Field(default="./output", description="Output directory")
    formats: list[Literal["markdown", "json"]] = Field(
        default=["markdown", "json"], description="Output formats to generate"
    )


class CompareConfig(BaseModel):
    """Incremental comparison configuration."""

    enabled: bool = Field(default=True, description="Enable incremental comparison")


class Config(BaseModel):
    """Root configuration for BuilderDNA."""

    accounts: list[str] = Field(description="GitHub accounts to analyze")
    github: GitHubConfig
    llm: LLMConfig
    weights: WeightConfig = Field(default_factory=WeightConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    compare: CompareConfig = Field(default_factory=CompareConfig)


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _resolve_env(value: str) -> str:
    """Replace ${VAR} patterns with environment variable values."""
    if not isinstance(value, str):
        return value
    return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)


def _resolve_config(data: dict) -> dict:
    """Recursively resolve environment variables in config dict."""
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
    """Load and validate configuration from a YAML file.

    Args:
        path: Path to config.yaml.

    Returns:
        Validated Config object.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    resolved = _resolve_config(raw)
    return Config(**resolved)
```

- [ ] **Step 4: Run config tests**

Run: `python -m pytest tests/test_config.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add config system with YAML loading and env var substitution"
```

---
### Task 4: LLM Client

**Files:**
- Create: `llm/client.py`
- Modify: `llm/__init__.py`
- Create: `tests/test_llm/test_client.py`

**Interfaces:**
- Consumes: `LLMConfig`
- Produces: `LLMClient.complete(prompt, response_format)` Protocol, `OpenAIClient` implementation, `LLMError` exception, `DEFAULT_RETRY_CONFIG`

- [ ] **Step 1: Write failing test**

Create `tests/test_llm/test_client.py`:

```python
"""Tests for LLM client."""

import json
import time

import pytest
from openai import APIError

from llm.client import (
    LLMError,
    OpenAIClient,
    DEFAULT_RETRY_CONFIG,
    LLMClient,
)


class FakeResponse:
    """Simulates an OpenAI API response."""
    def __init__(self, content: str):
        self.choices = [
            type("Choice", (), {"message": type("Message", (), {"content": content})})()
        ]


class TestOpenAIClient:
    def test_complete_success(self, mocker):
        mock_client_cls = mocker.patch("llm.client.OpenAI")
        mock_client = mock_client_cls.return_value
        mock_client.chat.completions.create.return_value = FakeResponse(
            json.dumps({"items": [{"name": "test", "score": 5}]})
        )

        class TestModel:
            name: str
            score: int

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        result = client.complete("Test prompt", response_format=TestModel)

        assert result is not None
        mock_client.chat.completions.create.assert_called_once()

    def test_complete_retry_then_success(self, mocker):
        mock_client_cls = mocker.patch("llm.client.OpenAI")
        mock_client = mock_client_cls.return_value
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                raise APIError("temporary error", response=None, body=None)
            return FakeResponse(json.dumps({"items": []}))

        mock_client.chat.completions.create.side_effect = side_effect

        client = OpenAIClient(
            api_key="sk-test",
            model="gpt-4o",
            retry_config={**DEFAULT_RETRY_CONFIG, "max_retries": 2, "base_delay": 0.01},
        )
        result = client.complete("prompt", response_format=dict)
        assert result is not None
        assert call_count[0] == 2

    def test_complete_max_retries_exceeded(self, mocker):
        mock_client_cls = mocker.patch("llm.client.OpenAI")
        mock_client = mock_client_cls.return_value
        mock_client.chat.completions.create.side_effect = APIError(
            "persistent error", response=None, body=None
        )

        client = OpenAIClient(
            api_key="sk-test",
            model="gpt-4o",
            retry_config={**DEFAULT_RETRY_CONFIG, "max_retries": 2, "base_delay": 0.01},
        )
        with pytest.raises(LLMError, match="LLM call failed after"):
            client.complete("prompt", response_format=dict)

    def test_parse_failure_retries(self, mocker):
        mock_client_cls = mocker.patch("llm.client.OpenAI")
        mock_client = mock_client_cls.return_value
        mock_client.chat.completions.create.return_value = FakeResponse(
            "not valid json {{{"
        )

        client = OpenAIClient(
            api_key="sk-test",
            model="gpt-4o",
            retry_config={**DEFAULT_RETRY_CONFIG, "max_retries": 1, "base_delay": 0.01},
        )
        with pytest.raises(LLMError, match="Failed to parse LLM response"):
            client.complete("prompt", response_format=dict)
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_llm/test_client.py -v`
Expected: FAIL (module not found or import error)

- [ ] **Step 3: Write llm/client.py**

```python
"""LLM Client — a utility, not a layer.

Provides the LLMClient Protocol and an OpenAI implementation.
Called by insight/classifier and opportunity/detector only.
"""

import json
import time
from typing import Any, Protocol

from openai import APIError, OpenAI


class LLMError(Exception):
    """Raised when an LLM call fails after all retries."""


class LLMClient(Protocol):
    """Protocol for LLM interaction.

    The LLM is a utility — like a database or a math library.
    Any provider can implement this protocol.
    """

    def complete(self, prompt: str, response_format: type) -> Any:
        """Call the LLM and return a parsed response of the given type.

        Args:
            prompt: The prompt to send.
            response_format: A type to parse the response into (currently unused
                at the protocol level; implementations handle parsing).

        Returns:
            Parsed response object.

        Raises:
            LLMError: On failure after all retries.
        """
        ...


DEFAULT_RETRY_CONFIG = {
    "max_retries": 2,
    "base_delay": 1.0,
    "max_delay": 30.0,
}


class OpenAIClient:
    """OpenAI implementation of LLMClient.

    Handles API calls with exponential backoff retry for transient errors
    and response parsing with one retry on parse failure.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        retry_config: dict | None = None,
    ):
        """Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key.
            model: Model ID to use.
            retry_config: Override default retry settings.
        """
        self._client = OpenAI(api_key=api_key)
        self.model = model
        self.retry = retry_config or DEFAULT_RETRY_CONFIG

    def complete(self, prompt: str, response_format: type) -> Any:
        """Call OpenAI chat completions and parse the structured response.

        The prompt should instruct the model to return JSON matching
        the expected schema. This method wraps the call with retry logic.

        Args:
            prompt: The full prompt text.
            response_format: Expected output type (used only in prompt; the
                actual response is parsed from JSON).

        Returns:
            Parsed JSON response as a dict or list.

        Raises:
            LLMError: If the call or parsing fails after all retries.
        """
        last_error = None
        for attempt in range(self.retry["max_retries"] + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert technical analyst. Always respond with valid JSON exactly matching the requested schema.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                )
                content = response.choices[0].message.content
                return self._parse_response(content, prompt, response_format)
            except APIError as e:
                last_error = e
                if attempt < self.retry["max_retries"]:
                    delay = min(
                        self.retry["base_delay"] * (2**attempt),
                        self.retry["max_delay"],
                    )
                    time.sleep(delay)
                else:
                    raise LLMError(
                        f"LLM call failed after {self.retry['max_retries'] + 1} attempts: {e}"
                    ) from e

        raise LLMError(f"LLM call failed: {last_error}")

    def _parse_response(
        self, raw: str, prompt: str, response_format: type
    ) -> Any:
        """Parse LLM JSON response, with one retry on failure.

        Args:
            raw: Raw response text from the LLM.
            prompt: Original prompt (for stricter retry).
            response_format: Expected output type.

        Returns:
            Parsed dict or list.

        Raises:
            LLMError: If parsing fails after retry.
        """
        for attempt in range(2):
            try:
                # Strip markdown code fences if present
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[: cleaned.rfind("```")].strip()
                return json.loads(cleaned)
            except json.JSONDecodeError:
                if attempt == 0:
                    # Retry with stricter prompt
                    retry_response = self._client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You MUST respond with ONLY valid JSON. No markdown fences, no commentary, just the JSON object."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.1,
                    )
                    raw = retry_response.choices[0].message.content
                else:
                    raise LLMError(
                        f"Failed to parse LLM response after retry. Raw: {raw[:200]}"
                    )
        return None  # unreachable
```

- [ ] **Step 4: Update llm/__init__.py**

```python
"""LLM utility module."""

from llm.client import LLMClient, LLMError, OpenAIClient

__all__ = ["LLMClient", "LLMError", "OpenAIClient"]
```

- [ ] **Step 5: Run LLM client tests**

Run: `python -m pytest tests/test_llm/test_client.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add llm/ tests/test_llm/
git commit -m "feat: add LLM client with OpenAI implementation and retry logic"
```

---
### Task 5: GitHub API Client

**Files:**
- Create: `collect/github/client.py`
- Create: `tests/test_collect/test_github_client.py`

**Interfaces:**
- Consumes: GitHub token (str)
- Produces: `GitHubClient` class with `get_repos(actor)`, `get_starred(actor)`, `get_commits(actor, repo_full_name, since)` methods returning raw API data
- Implements retry with backoff, rate-limit handling, 404 skip, 401 abort

- [ ] **Step 1: Write failing test**

Create `tests/test_collect/test_github_client.py`:

```python
"""Tests for GitHub API client."""

import pytest
import httpx

from collect.github.client import GitHubClient


class TestGitHubClient:
    def test_get_repos_success(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated",
            json=[
                {
                    "id": 1,
                    "full_name": "alice/toolkit",
                    "language": "Python",
                    "topics": ["llm", "agent"],
                    "description": "An LLM agent toolkit",
                    "stargazers_count": 42,
                    "forks_count": 5,
                    "updated_at": "2026-01-15T00:00:00Z",
                }
            ],
        )
        client = GitHubClient(token="ghp_test")
        repos = client.get_repos("alice")
        assert len(repos) == 1
        assert repos[0]["full_name"] == "alice/toolkit"

    def test_get_repos_404_returns_empty(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.github.com/users/nonexistent/repos?per_page=100&sort=updated",
            status_code=404,
        )
        client = GitHubClient(token="ghp_test")
        repos = client.get_repos("nonexistent")
        assert repos == []

    def test_get_repos_401_raises(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated",
            status_code=401,
        )
        client = GitHubClient(token="bad_token")
        with pytest.raises(httpx.HTTPStatusError, match="401"):
            client.get_repos("alice")

    def test_get_starred_success(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/starred?per_page=100&sort=updated",
            json=[
                {
                    "id": 100,
                    "full_name": "fastapi/fastapi",
                    "language": "Python",
                    "topics": ["web", "api"],
                    "description": "FastAPI framework",
                    "stargazers_count": 80000,
                }
            ],
        )
        client = GitHubClient(token="ghp_test")
        starred = client.get_starred("alice")
        assert len(starred) == 1
        assert starred[0]["full_name"] == "fastapi/fastapi"

    def test_rate_limit_handling(self, httpx_mock):
        """Rate limit should retry after waiting."""
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated",
            status_code=403,
            headers={"X-RateLimit-Remaining": "0", "Retry-After": "0"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/users/alice/repos?per_page=100&sort=updated",
            json=[],
        )
        client = GitHubClient(token="ghp_test", max_retries=1, base_delay=0.0)
        repos = client.get_repos("alice")
        assert repos == []
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_collect/test_github_client.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write collect/github/client.py**

```python
"""GitHub API client with retry and error handling.

Fetches raw data from GitHub REST API. LLM is NOT involved at this layer.
"""

import time
from typing import Any

import httpx


class GitHubClient:
    """HTTP client for GitHub REST API.

    Handles authentication, pagination, rate limiting, and error cases
    per the spec's error handling table.
    """

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        """Initialize the GitHub API client.

        Args:
            token: GitHub Personal Access Token.
            max_retries: Maximum retry attempts for transient errors.
            base_delay: Base delay in seconds for exponential backoff.
        """
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "BuilderDNA/0.1.0",
            },
            timeout=30.0,
        )
        self.max_retries = max_retries
        self.base_delay = base_delay

    def get_repos(self, actor: str) -> list[dict[str, Any]]:
        """Fetch repositories owned by the actor.

        Args:
            actor: GitHub username.

        Returns:
            List of raw repo dicts from GitHub API. Empty if user not found.

        Raises:
            httpx.HTTPStatusError: On 401 (bad token).
        """
        return self._paginate(f"/users/{actor}/repos")

    def get_starred(self, actor: str) -> list[dict[str, Any]]:
        """Fetch repositories starred by the actor.

        Args:
            actor: GitHub username.

        Returns:
            List of raw repo dicts from GitHub API. Empty if user not found.

        Raises:
            httpx.HTTPStatusError: On 401 (bad token).
        """
        return self._paginate(f"/users/{actor}/starred")

    def get_commits(
        self, actor: str, repo_full_name: str, since: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch commits by the actor in a specific repo.

        Args:
            actor: GitHub username (used to filter commits by author).
            repo_full_name: Full repo name, e.g. 'alice/toolkit'.
            since: ISO 8601 timestamp for incremental fetch.

        Returns:
            List of raw commit dicts. Empty on 404 or no commits found.
        """
        params: dict[str, str] = {"author": actor, "per_page": "100"}
        if since:
            params["since"] = since
        return self._paginate(f"/repos/{repo_full_name}/commits", extra_params=params)

    def _paginate(
        self, path: str, extra_params: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all pages for a paginated endpoint.

        Args:
            path: API path, e.g. '/users/alice/repos'.
            extra_params: Additional query parameters.

        Returns:
            Concatenated list of all items across pages.
        """
        params: dict[str, str] = {"per_page": "100", "sort": "updated"}
        if extra_params:
            params.update(extra_params)

        all_items: list[dict[str, Any]] = []
        url = path

        while url:
            response = self._request_with_retry("GET", url, params=params if url == path else None)
            if response is None:
                return all_items
            all_items.extend(response.json())
            url = self._next_page_url(response)

        return all_items

    def _request_with_retry(
        self, method: str, url: str, params: dict | None = None
    ) -> httpx.Response | None:
        """Make an HTTP request with exponential backoff retry.

        Args:
            method: HTTP method.
            url: Request URL (may be absolute for pagination).
            params: Query parameters.

        Returns:
            Response object, or None if the resource should be skipped (404).

        Raises:
            httpx.HTTPStatusError: On 401 (bad token — no retry).
        """
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.request(method, url, params=params)

                if resp.status_code == 401:
                    resp.raise_for_status()  # immediate abort

                if resp.status_code == 404:
                    return None  # skip this resource

                if resp.status_code == 403 and "rate limit" in resp.text.lower():
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    if attempt < self.max_retries:
                        time.sleep(retry_after)
                        continue
                    return None

                if resp.status_code >= 500:
                    if attempt < self.max_retries:
                        delay = min(self.base_delay * (2**attempt), 60.0)
                        time.sleep(delay)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                return resp

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2**attempt), 60.0)
                    time.sleep(delay)
                else:
                    raise

        return None

    @staticmethod
    def _next_page_url(response: httpx.Response) -> str | None:
        """Extract next page URL from Link header."""
        link = response.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                start = part.find("<") + 1
                end = part.find(">")
                return part[start:end] if start > 0 and end > start else None
        return None
```

- [ ] **Step 4: Run GitHub client tests**

Run: `python -m pytest tests/test_collect/test_github_client.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add collect/github/client.py tests/test_collect/
git commit -m "feat: add GitHub API client with retry and error handling"
```

---
### Task 6: GitHub Mapper — Raw API → Signal

**Files:**
- Create: `collect/github/mapper.py`
- Create: `tests/test_collect/test_mapper.py`

**Interfaces:**
- Consumes: raw GitHub API dicts, `WeightConfig`
- Produces: `Signal[]` — `map_repo(raw, actor, weight)`, `map_star(raw, actor, weight)`, `map_commit(raw, actor, weight)`, `map_all(raw_repos, raw_starred, raw_commits_grouped, actor, weights)`

- [ ] **Step 1: Write failing test**

Create `tests/test_collect/test_mapper.py`:

```python
"""Tests for GitHub data → Signal mapping."""

from datetime import datetime, timezone

import pytest

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
        "author": {
            "name": "Alice",
            "date": "2026-03-01T10:00:00Z",
        },
        "message": "Add MCP server implementation for tool discovery",
    },
    "html_url": "https://github.com/alice/toolkit/commit/abc123",
}


class TestMapRepo:
    def test_maps_basic_repo(self):
        s = map_repo(REPO_RAW, "alice", 5.0)
        assert isinstance(s, Signal)
        assert s.id == "gh_repo_alice_toolkit"
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
        repos = [{"repo_data": REPO_RAW}]
        starred = [{"repo_data": STAR_RAW}]
        commits_by_repo = {
            "alice/toolkit": [COMMIT_RAW],
        }
        signals = map_all(repos, starred, commits_by_repo, "alice", repo=5.0, star=1.0, commit=3.0)
        assert len(signals) >= 3
        types = {s.type for s in signals}
        assert types == {"repo", "star", "commit"}

    def test_empty_inputs(self):
        signals = map_all([], [], {}, "alice", repo=5.0, star=1.0, commit=3.0)
        assert signals == []
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_collect/test_mapper.py -v`
Expected: FAIL

- [ ] **Step 3: Write collect/github/mapper.py**

```python
"""GitHub data → Signal mapper.

Transforms raw GitHub API responses into the unified Signal model.
No LLM involvement. Pure data transformation.
"""

from datetime import datetime
from typing import Any

from models.signal import Signal


def map_repo(raw: dict[str, Any], actor: str, weight: float) -> Signal:
    """Map a raw GitHub repo dict to a Signal.

    Args:
        raw: Raw repo object from GitHub API.
        actor: The builder account being analyzed.
        weight: Signal weight from config.

    Returns:
        A Signal of type 'repo'.
    """
    repo_id = raw.get("id", raw.get("full_name", "unknown"))
    return Signal(
        id=f"gh_repo_{actor}_{raw.get('full_name', repo_id).replace('/', '_')}",
        source="github",
        type="repo",
        timestamp=datetime.fromisoformat(
            raw.get("updated_at", raw.get("created_at", "1970-01-01T00:00:00Z")).replace("Z", "+00:00")
        ),
        weight=weight,
        actor=actor,
        target=raw.get("full_name", ""),
        meta={
            "language": raw.get("language") or "",
            "topics": raw.get("topics", []),
            "description": raw.get("description") or "",
            "stars": raw.get("stargazers_count", 0),
            "forks": raw.get("forks_count", 0),
        },
        raw=raw,
    )


def map_star(raw: dict[str, Any], actor: str, weight: float) -> Signal:
    """Map a raw starred repo dict to a Signal.

    Args:
        raw: Raw repo object (from /starred endpoint).
        actor: The builder account.
        weight: Signal weight from config.

    Returns:
        A Signal of type 'star'.
    """
    repo_id = raw.get("id", raw.get("full_name", "unknown"))
    return Signal(
        id=f"gh_star_{repo_id}",
        source="github",
        type="star",
        timestamp=datetime.fromisoformat(
            raw.get("updated_at", raw.get("created_at", "1970-01-01T00:00:00Z")).replace("Z", "+00:00")
        ),
        weight=weight,
        actor=actor,
        target=raw.get("full_name", ""),
        meta={
            "language": raw.get("language") or "",
            "topics": raw.get("topics", []),
            "description": raw.get("description") or "",
            "stars": raw.get("stargazers_count", 0),
        },
        raw=raw,
    )


def map_commit(raw: dict[str, Any], actor: str, weight: float) -> Signal:
    """Map a raw commit dict to a Signal.

    Args:
        raw: Raw commit object from GitHub API.
        actor: The builder account.
        weight: Signal weight from config.

    Returns:
        A Signal of type 'commit'.
    """
    sha = raw.get("sha", "")
    commit_data = raw.get("commit", {})
    author = commit_data.get("author", {})
    date_str = author.get("date", "1970-01-01T00:00:00Z")

    # Extract repo full_name from html_url or fallback
    html_url = raw.get("html_url", "")
    # URL format: https://github.com/owner/repo/commit/sha
    parts = html_url.split("/")
    repo_full_name = "/".join(parts[3:5]) if len(parts) >= 5 else ""

    return Signal(
        id=f"gh_commit_{sha}",
        source="github",
        type="commit",
        timestamp=datetime.fromisoformat(date_str.replace("Z", "+00:00")),
        weight=weight,
        actor=actor,
        target=commit_data.get("message", ""),
        meta={
            "repo": repo_full_name,
            "message": commit_data.get("message", ""),
            "url": html_url,
        },
        raw=raw,
    )


def map_all(
    raw_repos: list[dict[str, Any]],
    raw_starred: list[dict[str, Any]],
    raw_commits_by_repo: dict[str, list[dict[str, Any]]],
    actor: str,
    repo: float = 5.0,
    star: float = 1.0,
    commit: float = 3.0,
) -> list[Signal]:
    """Map all raw GitHub data for one actor into Signals.

    Args:
        raw_repos: Raw repo dicts from /users/{actor}/repos.
        raw_starred: Raw repo dicts from /users/{actor}/starred.
        raw_commits_by_repo: Dict mapping repo full_name → list of commit dicts.
        actor: The builder account.
        repo: Weight for repo signals.
        star: Weight for star signals.
        commit: Weight for commit signals.

    Returns:
        Flat list of all Signals.
    """
    signals: list[Signal] = []

    for r in raw_repos:
        repo_data = r.get("repo_data", r)  # support both raw and wrapped
        signals.append(map_repo(repo_data, actor, repo))

    for s in raw_starred:
        star_data = s.get("repo_data", s)
        signals.append(map_star(star_data, actor, star))

    for _repo_name, commits in raw_commits_by_repo.items():
        for c in commits:
            commit_data = c.get("commit_data", c)
            signals.append(map_commit(commit_data, actor, commit))

    return signals
```

- [ ] **Step 4: Run mapper tests**

Run: `python -m pytest tests/test_collect/test_mapper.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add collect/github/mapper.py tests/test_collect/test_mapper.py
git commit -m "feat: add GitHub data to Signal mapper"
```

---
### Task 7: Signal Store — SQLite Persistence

**Files:**
- Create: `collect/store.py`
- Create: `tests/test_collect/test_store.py`

**Interfaces:**
- Consumes: `Signal[]`, SQLite db path
- Produces: `SignalStore` class with `insert_signals(signals, snapshot_id)`, `get_signals_by_actor(actor)`, `get_all_signals()`, `create_snapshot(accounts)`, `get_last_snapshot()`, `get_snapshot(snapshot_id)`, `list_snapshots()`

- [ ] **Step 1: Write failing test**

Create `tests/test_collect/test_store.py`:

```python
"""Tests for SignalStore — SQLite persistence layer."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from models.signal import Signal
from collect.store import SignalStore


@pytest.fixture
def store():
    """Create a store with a temporary database."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        s = SignalStore(db_path)
        yield s


@pytest.fixture
def sample_signals():
    return [
        Signal(
            id="gh_repo_alice_toolkit",
            source="github",
            type="repo",
            timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc),
            weight=5.0,
            actor="alice",
            target="alice/toolkit",
            meta={"language": "Python", "topics": ["llm"]},
            raw={"id": 1},
        ),
        Signal(
            id="gh_star_200",
            source="github",
            type="star",
            timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
            weight=1.0,
            actor="alice",
            target="fastapi/fastapi",
            meta={"language": "Python", "topics": ["web"]},
            raw={"id": 200},
        ),
    ]


class TestSignalStore:
    def test_insert_and_retrieve_signals(self, store, sample_signals):
        sid = store.create_snapshot(["alice"])
        store.insert_signals(sample_signals, sid)
        all_sigs = store.get_all_signals()
        assert len(all_sigs) == 2

    def test_get_signals_by_actor(self, store, sample_signals):
        sid = store.create_snapshot(["alice"])
        store.insert_signals(sample_signals, sid)
        result = store.get_signals_by_actor("alice")
        assert len(result) == 2
        assert all(s.actor == "alice" for s in result)

    def test_insert_dedup_by_id(self, store, sample_signals):
        sid = store.create_snapshot(["alice"])
        store.insert_signals(sample_signals, sid)
        store.insert_signals(sample_signals, sid)  # insert again
        all_sigs = store.get_all_signals()
        assert len(all_sigs) == 2  # still 2, no duplicates

    def test_snapshot_lifecycle(self, store, sample_signals):
        sid = store.create_snapshot(["alice", "bob"])
        assert sid is not None

        store.insert_signals(sample_signals, sid)

        snap = store.get_snapshot(sid)
        assert snap is not None
        assert snap["signal_count"] == 2
        assert "alice" in snap["accounts"]

        last = store.get_last_snapshot()
        assert last["id"] == sid

    def test_list_snapshots(self, store, sample_signals):
        sid1 = store.create_snapshot(["alice"])
        sid2 = store.create_snapshot(["alice"])
        store.insert_signals(sample_signals, sid1)
        snaps = store.list_snapshots()
        assert len(snaps) == 2

    def test_insert_clusters_insights_opportunities(self, store, sample_signals):
        sid = store.create_snapshot(["alice"])
        store.insert_signals(sample_signals, sid)

        store.insert_signal_clusters(
            [
                {
                    "id": "cl_001",
                    "topics": ["llm"],
                    "languages": ["Python"],
                    "total_weight": 5.0,
                    "time_span_days": 30,
                    "growth_rate": 0.5,
                }
            ],
            sid,
        )
        store.insert_insights(
            [
                {
                    "id": "in_001",
                    "tags": ["LLM"],
                    "summary": "Focus on LLM tooling",
                    "strength": 5.0,
                    "trend": "rising",
                    "signal_count": 1,
                    "evidence": ["alice/toolkit"],
                }
            ],
            sid,
        )
        store.insert_opportunities(
            [
                {
                    "id": "op_001",
                    "title": "Agent Tool",
                    "pain_point": "No good agent testing",
                    "demand_score": 4.0,
                    "competition_score": 2.0,
                    "gap_score": 2.0,
                    "recommended_action": "Build MVP",
                    "source_insights": ["in_001"],
                }
            ],
            sid,
        )

        clusters = store.get_signal_clusters(sid)
        insights = store.get_insights(sid)
        opportunities = store.get_opportunities(sid)

        assert len(clusters) == 1
        assert len(insights) == 1
        assert len(opportunities) == 1
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_collect/test_store.py -v`
Expected: FAIL

- [ ] **Step 3: Write collect/store.py**

```python
"""Signal Store — SQLite persistence for signals, clusters, insights, and opportunities.

Manages the snapshots/ directory, including schema creation, CRUD operations,
and snapshot metadata for incremental comparison.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.signal import Signal


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    created_at TEXT,
    accounts TEXT,
    signal_count INTEGER DEFAULT 0,
    insight_count INTEGER DEFAULT 0,
    opportunity_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    source TEXT,
    type TEXT,
    timestamp TEXT,
    weight REAL,
    actor TEXT,
    target TEXT,
    meta TEXT,
    raw TEXT,
    snapshot_id TEXT REFERENCES snapshots(id)
);

CREATE TABLE IF NOT EXISTS signal_clusters (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(id),
    topics TEXT,
    languages TEXT,
    total_weight REAL,
    time_span_days INTEGER,
    growth_rate REAL
);

CREATE TABLE IF NOT EXISTS insights (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(id),
    tags TEXT,
    summary TEXT,
    strength REAL,
    trend TEXT,
    signal_count INTEGER,
    evidence TEXT
);

CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(id),
    title TEXT,
    pain_point TEXT,
    demand_score REAL,
    competition_score REAL,
    gap_score REAL,
    recommended_action TEXT,
    source_insights TEXT
);
"""


class SignalStore:
    """SQLite-backed store for all BuilderDNA data."""

    def __init__(self, db_path: str | Path):
        """Initialize the store and create tables if needed.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create schema if not exists."""
        import sqlite3

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def create_snapshot(self, accounts: list[str]) -> str:
        """Create a new snapshot record.

        Args:
            accounts: List of account names being analyzed.

        Returns:
            The new snapshot ID.
        """
        sid = str(uuid.uuid4())[:8]
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO snapshots (id, created_at, accounts) VALUES (?, ?, ?)",
                (sid, datetime.now(timezone.utc).isoformat(), json.dumps(accounts)),
            )
            conn.commit()
        return sid

    def get_last_snapshot(self) -> dict | None:
        """Get the most recent snapshot.

        Returns:
            Snapshot dict or None if no snapshots exist.
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        """Get a snapshot by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_snapshots(self) -> list[dict]:
        """List all snapshots ordered by creation time."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshots ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def insert_signals(self, signals: list[Signal], snapshot_id: str) -> int:
        """Insert signals, skipping duplicates by ID.

        Args:
            signals: Signals to insert.
            snapshot_id: Current snapshot ID.

        Returns:
            Number of signals actually inserted.
        """
        count = 0
        with self._get_conn() as conn:
            for s in signals:
                try:
                    conn.execute(
                        """INSERT INTO signals (id, source, type, timestamp, weight,
                           actor, target, meta, raw, snapshot_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            s.id,
                            s.source,
                            s.type,
                            s.timestamp.isoformat(),
                            s.weight,
                            s.actor,
                            s.target,
                            json.dumps(s.meta),
                            json.dumps(s.raw),
                            snapshot_id,
                        ),
                    )
                    count += 1
                except Exception:
                    pass  # duplicate ID, skip
            conn.execute(
                "UPDATE snapshots SET signal_count = signal_count + ? WHERE id = ?",
                (count, snapshot_id),
            )
            conn.commit()
        return count

    def get_signals_by_actor(self, actor: str) -> list[Signal]:
        """Get all signals for a specific actor."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE actor = ? ORDER BY timestamp DESC",
                (actor,),
            ).fetchall()
            return [self._row_to_signal(dict(r)) for r in rows]

    def get_all_signals(self) -> list[Signal]:
        """Get all signals in the store."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY timestamp DESC"
            ).fetchall()
            return [self._row_to_signal(dict(r)) for r in rows]

    def get_signals_since(self, since: str) -> list[Signal]:
        """Get signals created after a given ISO timestamp."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE timestamp > ? ORDER BY timestamp DESC",
                (since,),
            ).fetchall()
            return [self._row_to_signal(dict(r)) for r in rows]

    @staticmethod
    def _row_to_signal(row: dict) -> Signal:
        """Convert a DB row dict to a Signal object."""
        return Signal(
            id=row["id"],
            source=row["source"],
            type=row["type"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            weight=row["weight"],
            actor=row["actor"],
            target=row["target"],
            meta=json.loads(row["meta"]) if row["meta"] else {},
            raw=json.loads(row["raw"]) if row["raw"] else {},
        )

    def insert_signal_clusters(
        self, clusters: list[dict[str, Any]], snapshot_id: str
    ) -> None:
        """Insert signal clusters for a snapshot (replaces existing)."""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM signal_clusters WHERE snapshot_id = ?", (snapshot_id,)
            )
            for c in clusters:
                conn.execute(
                    """INSERT INTO signal_clusters
                       (id, snapshot_id, topics, languages, total_weight, time_span_days, growth_rate)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        c["id"],
                        snapshot_id,
                        json.dumps(c["topics"]),
                        json.dumps(c["languages"]),
                        c["total_weight"],
                        c["time_span_days"],
                        c["growth_rate"],
                    ),
                )
            conn.commit()

    def get_signal_clusters(self, snapshot_id: str) -> list[dict]:
        """Get all signal clusters for a snapshot."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM signal_clusters WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "topics": json.loads(r["topics"]),
                    "languages": json.loads(r["languages"]),
                    "total_weight": r["total_weight"],
                    "time_span_days": r["time_span_days"],
                    "growth_rate": r["growth_rate"],
                }
                for r in rows
            ]

    def insert_insights(
        self, insights: list[dict[str, Any]], snapshot_id: str
    ) -> None:
        """Insert insights for a snapshot."""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM insights WHERE snapshot_id = ?", (snapshot_id,)
            )
            for i in insights:
                conn.execute(
                    """INSERT INTO insights
                       (id, snapshot_id, tags, summary, strength, trend, signal_count, evidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        i["id"],
                        snapshot_id,
                        json.dumps(i["tags"]),
                        i["summary"],
                        i["strength"],
                        i["trend"],
                        i["signal_count"],
                        json.dumps(i["evidence"]),
                    ),
                )
            conn.execute(
                "UPDATE snapshots SET insight_count = ? WHERE id = ?",
                (len(insights), snapshot_id),
            )
            conn.commit()

    def get_insights(self, snapshot_id: str) -> list[dict]:
        """Get all insights for a snapshot."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM insights WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "tags": json.loads(r["tags"]),
                    "summary": r["summary"],
                    "strength": r["strength"],
                    "trend": r["trend"],
                    "signal_count": r["signal_count"],
                    "evidence": json.loads(r["evidence"]),
                }
                for r in rows
            ]

    def insert_opportunities(
        self, opportunities: list[dict[str, Any]], snapshot_id: str
    ) -> None:
        """Insert opportunities for a snapshot."""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM opportunities WHERE snapshot_id = ?", (snapshot_id,)
            )
            for o in opportunities:
                conn.execute(
                    """INSERT INTO opportunities
                       (id, snapshot_id, title, pain_point, demand_score,
                        competition_score, gap_score, recommended_action, source_insights)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        o["id"],
                        snapshot_id,
                        o["title"],
                        o["pain_point"],
                        o["demand_score"],
                        o["competition_score"],
                        o["gap_score"],
                        o["recommended_action"],
                        json.dumps(o["source_insights"]),
                    ),
                )
            conn.execute(
                "UPDATE snapshots SET opportunity_count = ? WHERE id = ?",
                (len(opportunities), snapshot_id),
            )
            conn.commit()

    def get_opportunities(self, snapshot_id: str) -> list[dict]:
        """Get all opportunities for a snapshot."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM opportunities WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "pain_point": r["pain_point"],
                    "demand_score": r["demand_score"],
                    "competition_score": r["competition_score"],
                    "gap_score": r["gap_score"],
                    "recommended_action": r["recommended_action"],
                    "source_insights": json.loads(r["source_insights"]),
                }
                for r in rows
            ]
```

- [ ] **Step 4: Run store tests**

Run: `python -m pytest tests/test_collect/test_store.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add collect/store.py tests/test_collect/test_store.py
git commit -m "feat: add SQLite SignalStore for snapshots and persistence"
```

---
### Task 8: Insight Aggregator — L1 Rule-Based Clustering

**Files:**
- Create: `insight/aggregator.py`
- Create: `tests/test_insight/test_aggregator.py`

**Interfaces:**
- Consumes: `Signal[]`
- Produces: `SignalCluster[]` — `aggregate(signals, window_days=30)` function

- [ ] **Step 1: Write failing test**

Create `tests/test_insight/test_aggregator.py`:

```python
"""Tests for L1 Insight Aggregator."""

from datetime import datetime, timezone

from models.signal import Signal, SignalCluster
from insight.aggregator import aggregate


def _make_signal(id_, actor, type_, topics, language, weight, days_ago=0):
    """Helper to create a test signal."""
    return Signal(
        id=id_,
        source="github",
        type=type_,
        timestamp=datetime(2026, 7, 15, tzinfo=timezone.utc),
        weight=weight,
        actor=actor,
        target=f"{actor}/repo_{id_}",
        meta={"language": language, "topics": topics, "description": ""},
        raw={},
    )


class TestAggregate:
    def test_single_topic_cluster(self):
        signals = [
            _make_signal("s1", "alice", "repo", ["llm"], "Python", 5.0),
            _make_signal("s2", "alice", "star", ["llm", "agent"], "Python", 1.0),
            _make_signal("s3", "alice", "commit", ["llm"], "Python", 3.0),
        ]
        clusters = aggregate(signals)
        assert len(clusters) >= 1
        # Should find a cluster around "llm"
        llm_clusters = [c for c in clusters if "llm" in c.topics]
        assert len(llm_clusters) >= 1
        assert llm_clusters[0].total_weight == 9.0

    def test_multiple_disjoint_clusters(self):
        signals = [
            _make_signal("s1", "alice", "repo", ["llm", "agent"], "Python", 5.0),
            _make_signal("s2", "alice", "repo", ["rust", "systems"], "Rust", 5.0),
        ]
        clusters = aggregate(signals)
        assert len(clusters) >= 2

    def test_empty_signals(self):
        clusters = aggregate([])
        assert clusters == []

    def test_cluster_fields_populated(self):
        signals = [
            _make_signal("s1", "alice", "repo", ["llm", "agent"], "Python", 5.0),
            _make_signal("s2", "alice", "star", ["llm"], "Python", 1.0),
        ]
        clusters = aggregate(signals)
        for c in clusters:
            assert len(c.signals) > 0
            assert len(c.topics) > 0
            assert c.total_weight > 0
            assert 0.0 <= c.growth_rate <= 1.0
            assert c.time_span_days >= 0

    def test_language_grouping(self):
        signals = [
            _make_signal("s1", "alice", "repo", ["web"], "Python", 5.0),
            _make_signal("s2", "alice", "star", ["web"], "JavaScript", 1.0),
        ]
        clusters = aggregate(signals)
        # Both signals share topic "web", so they should be in one cluster
        web_clusters = [c for c in clusters if "web" in c.topics]
        assert len(web_clusters) >= 1
        languages = set()
        for c in web_clusters:
            languages.update(c.languages)
        assert "Python" in languages
        assert "JavaScript" in languages
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_insight/test_aggregator.py -v`
Expected: FAIL

- [ ] **Step 3: Write insight/aggregator.py**

```python
"""L1 Insight Aggregator — rule-based Signal clustering.

Groups related Signals by topic co-occurrence using Jaccard similarity.
No LLM involved. Outputs SignalCluster objects for L2 processing.
"""

from collections import defaultdict

from models.signal import Signal, SignalCluster

# Minimum Jaccard similarity for two signals to be clustered together
JACCARD_THRESHOLD = 0.3

# Recent window in days for growth_rate calculation
RECENT_WINDOW_DAYS = 30


def aggregate(signals: list[Signal], window_days: int = RECENT_WINDOW_DAYS) -> list[SignalCluster]:
    """Aggregate signals into clusters based on topic co-occurrence.

    Uses Jaccard similarity on topic sets to group related signals.
    Each cluster becomes a SignalCluster with computed metrics.

    Args:
        signals: All signals to cluster.
        window_days: Days to consider as "recent" for growth_rate.

    Returns:
        List of SignalCluster objects, sorted by total_weight descending.
    """
    if not signals:
        return []

    # Build topic→signals index
    topic_index: dict[str, set[int]] = defaultdict(set)
    signal_map: dict[int, Signal] = {}
    for idx, s in enumerate(signals):
        signal_map[idx] = s
        for topic in s.meta.get("topics", []):
            topic_index[topic].add(idx)

    # Use union-find to cluster signals that share topics above threshold
    n = len(signals)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Union signals that share the same topic
    for topic_signals in topic_index.values():
        indices = list(topic_signals)
        for i in range(1, len(indices)):
            union(indices[0], indices[i])

    # Also union by Jaccard similarity on topic sets
    for i in range(n):
        topics_i = set(signals[i].meta.get("topics", []))
        if not topics_i:
            continue
        for j in range(i + 1, n):
            topics_j = set(signals[j].meta.get("topics", []))
            if not topics_j:
                continue
            intersection = len(topics_i & topics_j)
            union_size = len(topics_i | topics_j)
            if union_size > 0 and intersection / union_size >= JACCARD_THRESHOLD:
                union(i, j)

    # Collect clusters
    clusters_map: dict[int, list[int]] = defaultdict(list)
    for idx in range(n):
        clusters_map[find(idx)].append(idx)

    # Find the most recent timestamp for growth rate calculation
    all_timestamps = [s.timestamp for s in signals]
    latest_ts = max(all_timestamps) if all_timestamps else None

    result: list[SignalCluster] = []
    for indices in clusters_map.values():
        cluster_signals = [signals[i] for i in indices]
        signal_ids = [s.id for s in cluster_signals]

        # Collect all unique topics and languages
        all_topics: set[str] = set()
        all_languages: set[str] = set()
        for s in cluster_signals:
            all_topics.update(s.meta.get("topics", []))
            lang = s.meta.get("language", "")
            if lang:
                all_languages.add(lang)

        total_weight = sum(s.weight for s in cluster_signals)

        # Time span
        timestamps = [s.timestamp for s in cluster_signals]
        time_span = 0
        if timestamps:
            time_span = int((max(timestamps) - min(timestamps)).total_seconds() / 86400)

        # Growth rate: weight in recent window / total weight
        growth_rate = 0.0
        if latest_ts and total_weight > 0:
            recent_weight = sum(
                s.weight
                for s in cluster_signals
                if (latest_ts - s.timestamp).total_seconds() / 86400 <= window_days
            )
            growth_rate = recent_weight / total_weight

        result.append(
            SignalCluster(
                signals=signal_ids,
                topics=sorted(all_topics),
                languages=sorted(all_languages),
                total_weight=total_weight,
                time_span_days=time_span,
                growth_rate=round(growth_rate, 3),
            )
        )

    # Sort by total_weight descending
    result.sort(key=lambda c: c.total_weight, reverse=True)
    return result
```

- [ ] **Step 4: Run aggregator tests**

Run: `python -m pytest tests/test_insight/test_aggregator.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add insight/aggregator.py tests/test_insight/
git commit -m "feat: add L1 insight aggregator with topic-based clustering"
```

---
### Task 9: Insight Classifier — L2 LLM Semantic Classification

**Files:**
- Create: `insight/classifier.py`
- Create: `tests/test_insight/test_classifier.py`

**Interfaces:**
- Consumes: `SignalCluster[]`, `LLMClient`, actor name, optional previous insights
- Produces: `Insight[]` — `classify(clusters, llm, actor, previous_insights=None)` function, `build_fallback_insights(clusters, actor)` for LLM degradation

- [ ] **Step 1: Write failing test**

Create `tests/test_insight/test_classifier.py`:

```python
"""Tests for L2 Insight Classifier."""

import json
from unittest.mock import MagicMock

from models.signal import SignalCluster
from insight.classifier import classify, build_classification_prompt, build_fallback_insights


LLM_RESPONSE = {
    "insights": [
        {
            "id": "in_001",
            "tags": ["LLM", "Agent", "Python"],
            "summary": "Deep investment in LLM agent frameworks with rising activity",
            "strength": 35.5,
            "trend": "rising",
            "signal_count": 12,
            "evidence": ["alice/agent-kit", "alice/llm-tools"],
        }
    ]
}


class TestBuildPrompt:
    def test_prompt_contains_actor(self):
        clusters = [
            SignalCluster(
                signals=["s1"],
                topics=["llm"],
                languages=["Python"],
                total_weight=5.0,
                time_span_days=30,
                growth_rate=0.5,
            )
        ]
        prompt = build_classification_prompt(clusters, "alice")
        assert "alice" in prompt
        assert "llm" in prompt
        assert "Python" in prompt

    def test_prompt_with_previous_insights(self):
        clusters = [
            SignalCluster(
                signals=["s1"],
                topics=["web"],
                languages=["JS"],
                total_weight=3.0,
                time_span_days=10,
                growth_rate=1.0,
            )
        ]
        previous = [
            {
                "tags": ["LLM"],
                "summary": "LLM focus",
                "strength": 20.0,
                "trend": "stable",
                "signal_count": 5,
                "evidence": [],
            }
        ]
        prompt = build_classification_prompt(clusters, "alice", previous)
        assert "previous" in prompt.lower() or "Previous" in prompt
        assert "LLM" in prompt


class TestClassify:
    def test_classify_returns_insights(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLM_RESPONSE

        clusters = [
            SignalCluster(
                signals=["s1", "s2"],
                topics=["llm", "agent"],
                languages=["Python"],
                total_weight=35.5,
                time_span_days=60,
                growth_rate=0.6,
            )
        ]
        insights = classify(clusters, mock_llm, "alice")
        assert len(insights) == 1
        assert insights[0].id == "in_001"
        assert insights[0].trend == "rising"
        assert "LLM" in insights[0].tags

    def test_classify_llm_error_falls_back(self):
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = Exception("API down")

        clusters = [
            SignalCluster(
                signals=["s1"],
                topics=["llm"],
                languages=["Python"],
                total_weight=5.0,
                time_span_days=10,
                growth_rate=0.5,
            )
        ]
        insights = classify(clusters, mock_llm, "alice")
        assert len(insights) == 1
        assert "llm" in insights[0].tags
        assert "alice" in insights[0].summary


class TestFallbackInsights:
    def test_builds_fallback_for_each_cluster(self):
        clusters = [
            SignalCluster(
                signals=["s1"],
                topics=["rust", "systems"],
                languages=["Rust"],
                total_weight=10.0,
                time_span_days=20,
                growth_rate=0.3,
            ),
            SignalCluster(
                signals=["s2"],
                topics=["web"],
                languages=["JS"],
                total_weight=3.0,
                time_span_days=5,
                growth_rate=0.0,
            ),
        ]
        insights = build_fallback_insights(clusters, "alice")
        assert len(insights) == 2
        assert all(i.trend == "stable" for i in insights)
        assert insights[0].id.startswith("in_fallback")
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_insight/test_classifier.py -v`
Expected: FAIL

- [ ] **Step 3: Write insight/classifier.py**

```python
"""L2 Insight Classifier — LLM-powered semantic understanding.

Converts L1 quantitative SignalClusters into semantic Insights.
LLM is a utility called only here for classification.
Falls back to rule-based summaries if LLM is unavailable.
"""

from datetime import datetime, timezone
from typing import Any

from models.insight import Insight
from models.signal import SignalCluster
from llm.client import LLMClient


def build_classification_prompt(
    clusters: list[SignalCluster],
    actor: str,
    previous_insights: list[dict[str, Any]] | None = None,
) -> str:
    """Build the prompt for L2 classification.

    Args:
        clusters: L1 signal clusters with quantitative metrics.
        actor: The builder being analyzed.
        previous_insights: Previous run's insights for trend comparison.

    Returns:
        Prompt string for the LLM.
    """
    cluster_lines = []
    for i, c in enumerate(clusters):
        cluster_lines.append(
            f"Cluster {i+1}:\n"
            f"  Topics: {', '.join(c.topics)}\n"
            f"  Languages: {', '.join(c.languages)}\n"
            f"  Total Weight: {c.total_weight}\n"
            f"  Time Span: {c.time_span_days} days\n"
            f"  Growth Rate: {c.growth_rate}\n"
            f"  Signals: {len(c.signals)}"
        )

    previous_text = ""
    if previous_insights:
        previous_text = "\nPrevious analysis insights:\n"
        for pi in previous_insights:
            previous_text += (
                f"- Tags: {pi['tags']}, Summary: {pi['summary']}, "
                f"Trend: {pi['trend']}, Strength: {pi['strength']}\n"
            )
        previous_text += (
            "\nCompare current clusters with previous insights. "
            "Update trend to 'rising', 'stable', or 'fading' based on changes.\n"
        )

    return f"""Analyze the following technical activity data for builder '{actor}'.

{previous_text}
Quantitative signal clusters:
{''.join(cluster_lines)}

Return a JSON object with an 'insights' array. For each cluster, generate one insight:
- id: "in_NNN" (sequential)
- tags: array of technology labels (lowercase, e.g. "llm", "agent", "python")
- summary: one sentence describing the builder's focus in this area
- strength: the cluster's total_weight
- trend: "rising" if growth_rate > 0.5, "stable" if 0.2-0.5, "fading" if < 0.2
- signal_count: number of signals
- evidence: array of key references (repo names, etc.) if available

Respond with ONLY valid JSON, no markdown fences."""


def build_fallback_insights(
    clusters: list[SignalCluster], actor: str
) -> list[Insight]:
    """Generate rule-based insights when LLM is unavailable.

    Args:
        clusters: L1 signal clusters.
        actor: The builder being analyzed.

    Returns:
        List of basic Insight objects without LLM semantics.
    """
    insights: list[Insight] = []
    for i, c in enumerate(clusters):
        topic_str = ", ".join(c.topics[:5]) if c.topics else "general development"
        lang_str = f" (using {', '.join(c.languages)})" if c.languages else ""
        summary = f"{actor} focuses on {topic_str}{lang_str}"

        trend = "stable"
        if c.growth_rate > 0.5:
            trend = "rising"
        elif c.growth_rate < 0.2:
            trend = "fading"

        insights.append(
            Insight(
                id=f"in_fallback_{i+1}",
                tags=c.topics[:5],
                summary=summary,
                strength=c.total_weight,
                trend=trend,
                signal_count=len(c.signals),
                evidence=[],
            )
        )
    return insights


def classify(
    clusters: list[SignalCluster],
    llm: LLMClient,
    actor: str,
    previous_insights: list[dict[str, Any]] | None = None,
) -> list[Insight]:
    """Classify signal clusters into semantic insights using LLM.

    Args:
        clusters: L1 quantitative signal clusters.
        llm: LLM client for semantic understanding.
        actor: The builder being analyzed.
        previous_insights: Previous run's insights for trend comparison.

    Returns:
        List of Insight objects. Falls back to rule-based if LLM fails.
    """
    if not clusters:
        return []

    try:
        prompt = build_classification_prompt(clusters, actor, previous_insights)
        response = llm.complete(prompt, response_format=dict)
        raw_insights = response.get("insights", [])
    except Exception:
        return build_fallback_insights(clusters, actor)

    insights: list[Insight] = []
    for raw in raw_insights:
        insights.append(
            Insight(
                id=raw.get("id", f"in_{len(insights)+1}"),
                tags=raw.get("tags", []),
                summary=raw.get("summary", ""),
                strength=raw.get("strength", 0.0),
                trend=raw.get("trend", "stable"),
                signal_count=raw.get("signal_count", 0),
                evidence=raw.get("evidence", []),
                created_at=datetime.now(timezone.utc),
            )
        )
    return insights
```

- [ ] **Step 4: Run classifier tests**

Run: `python -m pytest tests/test_insight/test_classifier.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add insight/classifier.py tests/test_insight/test_classifier.py
git commit -m "feat: add L2 insight classifier with LLM and fallback"
```

---
### Task 10: Opportunity Detector & Evaluator

**Files:**
- Create: `opportunity/detector.py`
- Create: `opportunity/evaluator.py`
- Create: `tests/test_opportunity/test_detector.py`
- Create: `tests/test_opportunity/test_evaluator.py`

**Interfaces:**
- Consumes: `Insight[]`, `LLMClient`; then `Opportunity[]`
- Produces: `detect(insights, llm)` → `Opportunity[]` (with LLM); `evaluate(opportunities)` → scored `Opportunity[]` (no LLM); `build_fallback_opportunities(insights)` for LLM degradation

- [ ] **Step 1: Write failing tests**

Create `tests/test_opportunity/test_detector.py`:

```python
"""Tests for Opportunity Detector."""

from unittest.mock import MagicMock

from models.insight import Insight
from opportunity.detector import detect, build_detection_prompt, build_fallback_opportunities


LLM_RESPONSE = {
    "opportunities": [
        {
            "id": "op_001",
            "title": "Agent Testing Framework",
            "pain_point": "No good way to test LLM agent behavior systematically",
            "demand_score": 4.5,
            "competition_score": 2.0,
            "recommended_action": "Build pytest plugin with agent replay capability",
            "source_insights": ["in_001"],
        }
    ]
}


class TestDetect:
    def test_detect_returns_opportunities(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLM_RESPONSE

        insights = [
            Insight(
                id="in_001",
                tags=["LLM", "Agent", "Python"],
                summary="Heavy investment in LLM agent frameworks",
                strength=35.5,
                trend="rising",
                signal_count=12,
                evidence=["alice/agent-kit"],
            )
        ]
        opportunities = detect(insights, mock_llm)
        assert len(opportunities) == 1
        assert opportunities[0].title == "Agent Testing Framework"
        assert opportunities[0].demand_score == 4.5
        assert opportunities[0].competition_score == 2.0

    def test_detect_llm_error_falls_back(self):
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = Exception("API down")

        insights = [
            Insight(
                id="in_001",
                tags=["LLM", "Agent"],
                summary="LLM agent focus",
                strength=20.0,
                trend="rising",
                signal_count=8,
                evidence=["alice/agent"],
            )
        ]
        opportunities = detect(insights, mock_llm)
        assert len(opportunities) >= 1
        assert opportunities[0].recommended_action == "Explore further"


class TestBuildPrompt:
    def test_prompt_contains_insights(self):
        insights = [
            Insight(
                id="in_001",
                tags=["Rust"],
                summary="Rust exploration",
                strength=10.0,
                trend="rising",
                signal_count=4,
                evidence=[],
            )
        ]
        prompt = build_detection_prompt(insights)
        assert "Rust" in prompt
        assert "opportunities" in prompt.lower()


class TestFallback:
    def test_fallback_creates_minimal_opportunities(self):
        insights = [
            Insight(
                id="in_001",
                tags=["Python"],
                summary="Python focus",
                strength=15.0,
                trend="rising",
                signal_count=5,
                evidence=[],
            )
        ]
        ops = build_fallback_opportunities(insights)
        assert len(ops) == 1
        assert ops[0].demand_score == 3.0
        assert ops[0].competition_score == 3.0
        assert ops[0].recommended_action == "Explore further"
```

Create `tests/test_opportunity/test_evaluator.py`:

```python
"""Tests for Opportunity Evaluator (no LLM)."""

from models.opportunity import Opportunity
from opportunity.evaluator import evaluate


class TestEvaluate:
    def test_computes_gap_scores(self):
        opportunities = [
            Opportunity(
                id="op_001",
                title="Tool A",
                pain_point="Pain A",
                demand_score=4.0,
                competition_score=2.0,
                gap_score=0.0,  # placeholder
                recommended_action="Build",
                source_insights=["in_001"],
            ),
            Opportunity(
                id="op_002",
                title="Tool B",
                pain_point="Pain B",
                demand_score=3.0,
                competition_score=4.0,
                gap_score=0.0,
                recommended_action="Wait",
                source_insights=["in_002"],
            ),
        ]
        scored = evaluate(opportunities)
        assert scored[0].gap_score == 2.0  # 4/2
        assert scored[1].gap_score == 0.75  # 3/4
        # Higher gap_score should come first
        assert scored[0].id == "op_001"

    def test_empty_list(self):
        assert evaluate([]) == []

    def test_single_opportunity(self):
        opp = Opportunity(
            id="op_001",
            title="Solo",
            pain_point="x",
            demand_score=5.0,
            competition_score=1.0,
            gap_score=99.0,
            recommended_action="Go",
            source_insights=[],
        )
        result = evaluate([opp])
        assert result[0].gap_score == 5.0  # recalculated
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_opportunity/ -v`
Expected: FAIL

- [ ] **Step 3: Write opportunity/detector.py**

```python
"""Opportunity Detector — LLM-powered opportunity discovery.

Converts semantic Insights into actionable Opportunities.
LLM is a utility called for reasoning.
Falls back to basic opportunities if LLM unavailable.
"""

from datetime import datetime, timezone
from typing import Any

from models.insight import Insight
from models.opportunity import Opportunity
from llm.client import LLMClient


def build_detection_prompt(insights: list[Insight]) -> str:
    """Build the prompt for opportunity detection.

    Args:
        insights: Semantic insights about the builder.

    Returns:
        Prompt string for the LLM.
    """
    insight_lines = []
    for i, ins in enumerate(insights):
        insight_lines.append(
            f"Insight {i+1}:\n"
            f"  Tags: {ins.tags}\n"
            f"  Summary: {ins.summary}\n"
            f"  Strength: {ins.strength}\n"
            f"  Trend: {ins.trend}\n"
            f"  Signal Count: {ins.signal_count}\n"
            f"  Evidence: {ins.evidence}"
        )

    return f"""Based on the following builder insights, identify product/tool opportunities.

Insights:
{''.join(insight_lines)}

For each opportunity, consider:
- What problems does this builder community face?
- What tools are missing or immature?
- Where is there high demand but low competition?

Return a JSON object with an 'opportunities' array. For each:
- id: "op_NNN" (sequential)
- title: concise opportunity name
- pain_point: the core problem being solved
- demand_score: 1-5 (how much demand exists)
- competition_score: 1-5 (how much existing competition; lower = less competition)
- recommended_action: concrete next step suggestion
- source_insights: array of insight IDs that support this

Respond with ONLY valid JSON, no markdown fences."""


def build_fallback_opportunities(insights: list[Insight]) -> list[Opportunity]:
    """Build basic opportunities when LLM is unavailable.

    Args:
        insights: Semantic insights.

    Returns:
        List of minimal Opportunity objects.
    """
    opportunities: list[Opportunity] = []
    for i, ins in enumerate(insights):
        opportunities.append(
            Opportunity(
                id=f"op_fallback_{i+1}",
                title=f"Tooling for {', '.join(ins.tags[:3])}",
                pain_point=f"Builders investing in {', '.join(ins.tags[:3])} may need better tooling",
                demand_score=3.0,
                competition_score=3.0,
                gap_score=1.0,
                recommended_action="Explore further",
                source_insights=[ins.id],
            )
        )
    return opportunities


def detect(
    insights: list[Insight],
    llm: LLMClient,
) -> list[Opportunity]:
    """Detect opportunities from insights using LLM reasoning.

    Args:
        insights: Semantic insights.
        llm: LLM client for reasoning.

    Returns:
        List of Opportunity objects with initial scores.
        Falls back to basic opportunities if LLM fails.
    """
    if not insights:
        return []

    try:
        prompt = build_detection_prompt(insights)
        response = llm.complete(prompt, response_format=dict)
        raw_ops = response.get("opportunities", [])
    except Exception:
        return build_fallback_opportunities(insights)

    opportunities: list[Opportunity] = []
    for raw in raw_ops:
        demand = max(1.0, min(5.0, raw.get("demand_score", 3.0)))
        competition = max(1.0, min(5.0, raw.get("competition_score", 3.0)))
        opportunities.append(
            Opportunity(
                id=raw.get("id", f"op_{len(opportunities)+1}"),
                title=raw.get("title", ""),
                pain_point=raw.get("pain_point", ""),
                demand_score=demand,
                competition_score=competition,
                gap_score=demand / competition if competition > 0 else demand,
                recommended_action=raw.get("recommended_action", ""),
                source_insights=raw.get("source_insights", []),
                created_at=datetime.now(timezone.utc),
            )
        )
    return opportunities
```

- [ ] **Step 4: Write opportunity/evaluator.py**

```python
"""Opportunity Evaluator — deterministic gap scoring.

Computes gap_score = demand / competition and ranks opportunities.
No LLM involved. Pure calculation.
"""

from models.opportunity import Opportunity


def evaluate(opportunities: list[Opportunity]) -> list[Opportunity]:
    """Evaluate and rank opportunities by gap score.

    Recalculates gap_score and sorts descending (best opportunities first).

    Args:
        opportunities: Opportunities with initial demand/competition scores.

    Returns:
        Same opportunities with recalculated gap_score, sorted descending.
    """
    for op in opportunities:
        op.gap_score = (
            op.demand_score / op.competition_score
            if op.competition_score > 0
            else op.demand_score
        )

    opportunities.sort(key=lambda o: o.gap_score, reverse=True)
    return opportunities
```

- [ ] **Step 5: Run opportunity tests**

Run: `python -m pytest tests/test_opportunity/ -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add opportunity/ tests/test_opportunity/
git commit -m "feat: add opportunity detector and evaluator"
```

---
### Task 11: Pipeline — Orchestration Layer

**Files:**
- Create: `pipeline.py`
- Create: `tests/test_pipeline/test_pipeline.py`

**Interfaces:**
- Consumes: `Config`, `GitHubClient`, `LLMClient`, `SignalStore`
- Produces: `run(config)` → `dict` with snapshot_id, signals, insights, opportunities, diff; `run_compare(config)` → `dict` with diff data

- [ ] **Step 1: Write failing test**

Create `tests/test_pipeline/test_pipeline.py`:

```python
"""Tests for the Pipeline orchestrator."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from models.signal import Signal
from models.insight import Insight
from models.opportunity import Opportunity
from config import Config, GitHubConfig, LLMConfig, WeightConfig, OutputConfig, CompareConfig
from pipeline import Pipeline


@pytest.fixture
def sample_config():
    return Config(
        accounts=["alice"],
        github=GitHubConfig(token="ghp_test"),
        llm=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        weights=WeightConfig(repo=5.0, commit=3.0, star=1.0),
        output=OutputConfig(dir="./test_output", formats=["markdown", "json"]),
        compare=CompareConfig(enabled=True),
    )


@pytest.fixture
def sample_signals():
    return [
        Signal(
            id=f"s{i}",
            source="github",
            type="repo",
            timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc),
            weight=5.0,
            actor="alice",
            target="alice/repo",
            meta={"language": "Python", "topics": ["llm"], "description": ""},
            raw={},
        )
        for i in range(3)
    ]


@pytest.fixture
def sample_insights():
    return [
        Insight(
            id="in_001",
            tags=["LLM", "Python"],
            summary="Focus on LLM tools",
            strength=15.0,
            trend="rising",
            signal_count=3,
            evidence=["alice/repo"],
        )
    ]


@pytest.fixture
def sample_opportunities():
    return [
        Opportunity(
            id="op_001",
            title="Agent Tool",
            pain_point="Missing agent testing",
            demand_score=4.0,
            competition_score=2.0,
            gap_score=2.0,
            recommended_action="Build",
            source_insights=["in_001"],
        )
    ]


class TestPipelineRun:
    def test_collect_phase(self, sample_config, sample_signals):
        """Collect should fetch and map signals."""
        pipeline = Pipeline(sample_config)

        with patch.object(pipeline, "_collect_for_account") as mock_collect:
            mock_collect.return_value = sample_signals
            with patch.object(pipeline, "_run_understand") as mock_understand:
                mock_understand.return_value = sample_insights
                with patch.object(pipeline, "_run_recommend") as mock_recommend:
                    mock_recommend.return_value = sample_opportunities
                    with patch.object(pipeline.store, "create_snapshot", return_value="snap_001"):
                        result = pipeline.run()

        assert result["snapshot_id"] == "snap_001"
        assert len(result["signals"]) == 3
        assert len(result["insights"]) == 1
        assert len(result["opportunities"]) == 1

    def test_compare_mode_loads_previous(self, sample_config, sample_signals, sample_insights, sample_opportunities):
        """Compare mode should load previous snapshot and compute diff."""
        pipeline = Pipeline(sample_config)

        # Simulate a previous snapshot
        pipeline.store.create_snapshot = MagicMock(return_value="snap_prev")
        last = {
            "id": "prev_001",
            "created_at": "2026-07-01T00:00:00",
            "accounts": '["alice"]',
            "signal_count": 2,
            "insight_count": 1,
            "opportunity_count": 1,
        }
        pipeline.store.get_last_snapshot = MagicMock(return_value=last)

        with patch.object(pipeline, "_collect_for_account") as mock_collect:
            mock_collect.return_value = sample_signals
            with patch.object(pipeline, "_run_understand") as mock_understand:
                mock_understand.return_value = sample_insights
                with patch.object(pipeline, "_run_recommend") as mock_recommend:
                    mock_recommend.return_value = sample_opportunities

                    result = pipeline.run(compare=True)

        assert result["diff"] is not None
        assert "new_signals" in result["diff"]
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_pipeline/test_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Write pipeline.py**

```python
"""Pipeline — orchestrates the full Collect→Understand→Recommend flow.

The only module that knows the global process. Every other module is a pure
function or class that can be tested independently.
"""

from pathlib import Path
from typing import Any

from config import Config
from collect.github.client import GitHubClient
from collect.github.mapper import map_all
from collect.store import SignalStore
from insight.aggregator import aggregate
from insight.classifier import classify, build_fallback_insights
from opportunity.detector import detect, build_fallback_opportunities
from opportunity.evaluator import evaluate
from llm.client import OpenAIClient


class Pipeline:
    """Orchestrates the BuilderDNA analysis pipeline."""

    def __init__(self, config: Config):
        """Initialize the pipeline with configuration.

        Args:
            config: Validated configuration.
        """
        self.config = config
        self.github = GitHubClient(token=config.github.token)
        self.llm = OpenAIClient(
            api_key=config.llm.api_key, model=config.llm.model
        )
        self.store = SignalStore(Path("snapshots") / "builderdna.db")

    def run(self, compare: bool = False) -> dict[str, Any]:
        """Execute the full analysis pipeline.

        Args:
            compare: If True, run incremental comparison against last snapshot.

        Returns:
            Dict with snapshot_id, signals, insights, opportunities, and optional diff.
        """
        snapshot_id = self.store.create_snapshot(self.config.accounts)

        # Phase 1: Collect
        all_signals = self._collect_all(compare)

        if not all_signals:
            return {
                "snapshot_id": snapshot_id,
                "signals": [],
                "insights": [],
                "opportunities": [],
                "diff": None,
            }

        # Persistent store
        self.store.insert_signals(all_signals, snapshot_id)

        # Phase 2: Understand
        insights = self._run_understand(all_signals, compare, snapshot_id)

        # Phase 3: Recommend
        opportunities = self._run_recommend(insights, snapshot_id)

        # Phase 4: Diff (if compare mode)
        diff = None
        if compare:
            last = self.store.get_last_snapshot()
            if last:
                diff = self._compute_diff(all_signals, last)

        return {
            "snapshot_id": snapshot_id,
            "signals": all_signals,
            "insights": insights,
            "opportunities": opportunities,
            "diff": diff,
        }

    def _collect_all(self, compare: bool = False) -> list:
        """Collect signals for all configured accounts.

        Args:
            compare: If True, only fetch since last snapshot.

        Returns:
            Flat list of all Signals.
        """
        since = None
        if compare:
            last = self.store.get_last_snapshot()
            if last:
                since = last["created_at"]

        all_signals = []
        for account in self.config.accounts:
            try:
                account_signals = self._collect_for_account(account, since)
                all_signals.extend(account_signals)
            except Exception as e:
                print(f"Warning: failed to collect for {account}: {e}")
                continue

        return all_signals

    def _collect_for_account(self, actor: str, since: str | None = None) -> list:
        """Fetch and map all signals for one account.

        Args:
            actor: GitHub username.
            since: ISO timestamp for incremental fetch.

        Returns:
            List of Signals for this account.
        """
        # Fetch raw data
        raw_repos = self.github.get_repos(actor)
        raw_starred = self.github.get_starred(actor)

        # Fetch commits for each repo
        raw_commits: dict[str, list] = {}
        for repo in raw_repos:
            full_name = repo.get("full_name", "")
            if full_name:
                try:
                    commits = self.github.get_commits(actor, full_name, since=since)
                    if commits:
                        raw_commits[full_name] = commits
                except Exception:
                    continue  # skip repos where commit fetch fails

        # Map to Signals
        return map_all(
            raw_repos=raw_repos,
            raw_starred=raw_starred,
            raw_commits_by_repo=raw_commits,
            actor=actor,
            repo=self.config.weights.repo,
            star=self.config.weights.star,
            commit=self.config.weights.commit,
        )

    def _run_understand(
        self, signals: list, compare: bool, snapshot_id: str
    ) -> list:
        """Run L1 aggregation + L2 classification.

        Args:
            signals: All signals.
            compare: Whether this is a comparison run.
            snapshot_id: Current snapshot ID.

        Returns:
            List of Insight objects.
        """
        # L1: Aggregate
        clusters = aggregate(signals)

        # Store clusters
        cluster_dicts = [c.model_dump() for c in clusters]
        self.store.insert_signal_clusters(cluster_dicts, snapshot_id)

        # L2: Classify
        previous = None
        if compare:
            last = self.store.get_last_snapshot()
            if last:
                previous = self.store.get_insights(last["id"])

        # Group clusters per actor (all signals share actor in v1, but multi-account)
        actor = self.config.accounts[0] if self.config.accounts else "unknown"
        insights = classify(clusters, self.llm, actor, previous)

        # Store insights
        insight_dicts = [i.model_dump() for i in insights]
        self.store.insert_insights(insight_dicts, snapshot_id)

        return insights

    def _run_recommend(self, insights: list, snapshot_id: str) -> list:
        """Run opportunity detection and evaluation.

        Args:
            insights: Semantic insights.
            snapshot_id: Current snapshot ID.

        Returns:
            List of scored Opportunity objects.
        """
        if not insights:
            return []

        opportunities = detect(insights, self.llm)
        opportunities = evaluate(opportunities)

        # Store opportunities
        opp_dicts = [o.model_dump() for o in opportunities]
        self.store.insert_opportunities(opp_dicts, snapshot_id)

        return opportunities

    def _compute_diff(self, signals: list, last_snapshot: dict) -> dict:
        """Compute difference between current and previous run.

        Args:
            signals: Current signals.
            last_snapshot: Previous snapshot metadata.

        Returns:
            Diff dict with new signal counts by type and topic weight changes.
        """
        previous_signals = self.store.get_signals_since("1970-01-01")
        prev_count = len(previous_signals)
        new_count = len(signals)

        # Count by type
        new_by_type: dict[str, int] = {}
        prev_by_type: dict[str, int] = {}
        for s in signals:
            new_by_type[s.type] = new_by_type.get(s.type, 0) + 1
        for s in previous_signals:
            prev_by_type[s.type] = prev_by_type.get(s.type, 0) + 1

        # Weight by topic
        new_topic_weight: dict[str, float] = {}
        prev_topic_weight: dict[str, float] = {}
        for s in signals:
            for t in s.meta.get("topics", []):
                new_topic_weight[t] = new_topic_weight.get(t, 0) + s.weight
        for s in previous_signals:
            for t in s.meta.get("topics", []):
                prev_topic_weight[t] = prev_topic_weight.get(t, 0) + s.weight

        # Topic changes
        topic_changes = {}
        all_topics = set(new_topic_weight) | set(prev_topic_weight)
        for t in all_topics:
            prev_w = prev_topic_weight.get(t, 0)
            new_w = new_topic_weight.get(t, 0)
            if prev_w > 0:
                change_pct = round((new_w - prev_w) / prev_w * 100, 1)
            else:
                change_pct = 100.0  # new topic
            topic_changes[t] = {"previous": prev_w, "current": new_w, "change_pct": change_pct}

        return {
            "new_signals": new_count - prev_count,
            "total_signals": new_count,
            "signals_by_type": {"previous": prev_by_type, "current": new_by_type},
            "topic_weight_changes": topic_changes,
            "previous_snapshot_id": last_snapshot["id"],
        }
```

- [ ] **Step 4: Run pipeline tests**

Run: `python -m pytest tests/test_pipeline/test_pipeline.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline.py tests/test_pipeline/
git commit -m "feat: add pipeline orchestrator for Collect→Understand→Recommend"
```

---
### Task 12: Output — CLI Renderer

**Files:**
- Create: `output/cli.py`
- Create: `tests/test_output/test_cli.py` (if applicable; smoke test via pipeline)

**Interfaces:**
- Consumes: pipeline result `dict` with signals, insights, opportunities, diff
- Produces: `render(result, output_dir)` — terminal output via `rich`

- [ ] **Step 1: Write output/cli.py**

```python
"""CLI output renderer using Rich.

Produces styled terminal output from pipeline results.
Opportunity is SSOT — CLI is just a View.
"""

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def render(result: dict[str, Any]) -> None:
    """Render pipeline results to the terminal.

    Args:
        result: Pipeline result dict with signals, insights, opportunities, diff.
    """
    signals = result.get("signals", [])
    insights = result.get("insights", [])
    opportunities = result.get("opportunities", [])
    diff = result.get("diff")

    # Header
    console.print()
    console.print(
        Panel.fit(
            Text("BuilderDNA Analysis", style="bold white on blue"),
            subtitle=f"Snapshot: {result.get('snapshot_id', 'unknown')}",
        )
    )

    # Diff section (compare mode)
    if diff:
        _render_diff(diff)

    # Signal summary
    _render_signal_summary(signals)

    # Insights
    _render_insights(insights)

    # Opportunities (SSOT)
    _render_opportunities(opportunities)

    console.print()


def _render_diff(diff: dict) -> None:
    """Render the comparison diff section."""
    console.print()
    console.print(Text("Changes Since Last Run", style="bold yellow"))

    new_count = diff.get("new_signals", 0)
    total = diff.get("total_signals", 0)
    color = "green" if new_count > 0 else "yellow" if new_count == 0 else "red"
    console.print(f"  New signals: [{color}]{new_count:+d}[/{color}] (total: {total})")

    # By type
    by_type = diff.get("signals_by_type", {})
    current = by_type.get("current", {})
    previous = by_type.get("previous", {})
    if current:
        type_table = Table(show_header=True, box=None, padding=(0, 2))
        type_table.add_column("Type")
        type_table.add_column("Previous")
        type_table.add_column("Current")
        type_table.add_column("Change")
        for stype in sorted(set(current) | set(previous)):
            prev = previous.get(stype, 0)
            curr = current.get(stype, 0)
            change = curr - prev
            change_str = f"[green]+{change}[/green]" if change > 0 else f"[red]{change}[/red]"
            type_table.add_row(stype, str(prev), str(curr), change_str)
        console.print(type_table)

    # Topic changes
    topic_changes = diff.get("topic_weight_changes", {})
    if topic_changes:
        console.print()
        console.print(Text("Topic Weight Changes:", style="bold"))
        for topic, data in sorted(topic_changes.items(), key=lambda x: abs(x[1]["change_pct"]), reverse=True)[:5]:
            pct = data["change_pct"]
            arrow = "↑" if pct > 0 else "↓" if pct < 0 else "→"
            color = "green" if pct > 20 else "red" if pct < -20 else "yellow"
            console.print(
                f"  [{color}]{arrow} {topic}: {data['previous']:.1f} → {data['current']:.1f} "
                f"({pct:+.1f}%)[/{color}]"
            )


def _render_signal_summary(signals: list) -> None:
    """Render signal count and type breakdown."""
    console.print()
    console.print(Text("Signal Summary", style="bold cyan"))

    if not signals:
        console.print("  No signals collected.")
        return

    # Count by type
    by_type: dict[str, int] = {}
    for s in signals:
        by_type[s.type] = by_type.get(s.type, 0) + 1

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Type")
    table.add_column("Count")
    table.add_column("Total Weight")
    for stype in sorted(by_type):
        total_w = sum(s.weight for s in signals if s.type == stype)
        table.add_row(stype, str(by_type[stype]), f"{total_w:.1f}")
    table.add_row("TOTAL", str(len(signals)), f"{sum(s.weight for s in signals):.1f}", style="bold")
    console.print(table)


def _render_insights(insights: list) -> None:
    """Render insight cards."""
    console.print()
    console.print(Text("Insights", style="bold cyan"))

    if not insights:
        console.print("  No insights generated.")
        return

    for ins in insights[:10]:  # limit to top 10 for terminal
        trend_color = {"rising": "green", "stable": "yellow", "fading": "red"}.get(
            ins.trend, "white"
        )
        tags_str = ", ".join(ins.tags[:5])
        panel = Panel(
            f"{ins.summary}\n\n"
            f"Strength: {ins.strength:.1f} | Trend: [{trend_color}]{ins.trend}[/{trend_color}] | "
            f"Signals: {ins.signal_count}",
            title=f"[bold]{tags_str}[/bold]",
            border_style=trend_color,
        )
        console.print(panel)


def _render_opportunities(opportunities: list) -> None:
    """Render opportunity rankings (SSOT)."""
    console.print()
    console.print(Text("Opportunities (SSOT)", style="bold green"))

    if not opportunities:
        console.print("  No opportunities detected.")
        return

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("#")
    table.add_column("Title")
    table.add_column("Demand")
    table.add_column("Comp.")
    table.add_column("Gap")
    table.add_column("Action")

    for i, op in enumerate(opportunities[:10], 1):
        gap_color = "green" if op.gap_score >= 2.0 else "yellow" if op.gap_score >= 1.0 else "red"
        table.add_row(
            str(i),
            op.title,
            f"{op.demand_score:.1f}",
            f"{op.competition_score:.1f}",
            f"[{gap_color}]{op.gap_score:.2f}[/{gap_color}]",
            op.recommended_action[:60],
        )

    console.print(table)
```

- [ ] **Step 2: Verify output/cli.py imports work**

Run: `python -c "from output.cli import render; print('CLI renderer importable')"`
Expected: `CLI renderer importable`

- [ ] **Step 3: Commit**

```bash
git add output/cli.py
git commit -m "feat: add CLI output renderer with Rich"
```

---
### Task 13: Output — Markdown & JSON Report Generators

**Files:**
- Create: `output/markdown.py`
- Create: `output/json_out.py`

**Interfaces:**
- Consumes: pipeline result `dict`, output directory path
- Produces: `write_markdown(result, output_dir)` → `.md` file; `write_json(result, output_dir)` → `.json` file

- [ ] **Step 1: Write output/markdown.py**

```python
"""Markdown report generator.

Generates a structured .md file from pipeline results.
Opportunity is SSOT — Markdown is just a View.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_markdown(result: dict[str, Any], output_dir: str | Path) -> Path:
    """Write a Markdown report to the output directory.

    Args:
        result: Pipeline result dict.
        output_dir: Directory to write the report to.

    Returns:
        Path to the generated file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_id = result.get("snapshot_id", "unknown")
    filename = f"report-{ts}-{snapshot_id}.md"
    filepath = output_dir / filename

    signals = result.get("signals", [])
    insights = result.get("insights", [])
    opportunities = result.get("opportunities", [])
    diff = result.get("diff")

    lines = [
        f"# BuilderDNA Analysis Report",
        f"",
        f"**Snapshot:** `{snapshot_id}`",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"",
    ]

    # Diff section
    if diff:
        lines += _md_diff(diff)

    # Signal summary
    lines += _md_signal_summary(signals)

    # Insights
    lines += _md_insights(insights)

    # Opportunities
    lines += _md_opportunities(opportunities)

    filepath.write_text("\n".join(lines))
    return filepath


def _md_diff(diff: dict) -> list[str]:
    """Render diff section in Markdown."""
    lines = ["## Changes Since Last Run", ""]
    new_count = diff.get("new_signals", 0)
    lines.append(f"- **New signals:** {new_count:+d} (total: {diff.get('total_signals', 0)})")
    lines.append("")

    topic_changes = diff.get("topic_weight_changes", {})
    if topic_changes:
        lines.append("### Topic Weight Changes")
        lines.append("")
        lines.append("| Topic | Previous | Current | Change |")
        lines.append("|-------|----------|---------|--------|")
        for topic, data in sorted(
            topic_changes.items(), key=lambda x: abs(x[1]["change_pct"]), reverse=True
        )[:10]:
            lines.append(
                f"| {topic} | {data['previous']:.1f} | {data['current']:.1f} | "
                f"{data['change_pct']:+.1f}% |"
            )
        lines.append("")

    return lines


def _md_signal_summary(signals: list) -> list[str]:
    """Render signal summary table."""
    lines = ["## Signal Summary", ""]
    if not signals:
        lines.append("_No signals collected._")
        lines.append("")
        return lines

    by_type: dict[str, dict] = {}
    for s in signals:
        if s.type not in by_type:
            by_type[s.type] = {"count": 0, "weight": 0.0}
        by_type[s.type]["count"] += 1
        by_type[s.type]["weight"] += s.weight

    lines.append("| Type | Count | Total Weight |")
    lines.append("|------|-------|-------------|")
    total_count = 0
    total_weight = 0.0
    for stype in sorted(by_type):
        data = by_type[stype]
        total_count += data["count"]
        total_weight += data["weight"]
        lines.append(f"| {stype} | {data['count']} | {data['weight']:.1f} |")
    lines.append(f"| **TOTAL** | **{total_count}** | **{total_weight:.1f}** |")
    lines.append("")

    return lines


def _md_insights(insights: list) -> list[str]:
    """Render insights section."""
    lines = ["## Insights", ""]
    if not insights:
        lines.append("_No insights generated._")
        lines.append("")
        return lines

    for ins in insights:
        trend_emoji = {"rising": "🔺", "stable": "🟡", "fading": "🔻"}.get(ins.trend, "")
        lines.append(f"### {', '.join(ins.tags[:5])} {trend_emoji}")
        lines.append(f"")
        lines.append(f"- **Summary:** {ins.summary}")
        lines.append(f"- **Strength:** {ins.strength:.1f}")
        lines.append(f"- **Trend:** {ins.trend}")
        lines.append(f"- **Signal Count:** {ins.signal_count}")
        if ins.evidence:
            lines.append(f"- **Evidence:** {', '.join(ins.evidence[:5])}")
        lines.append("")

    return lines


def _md_opportunities(opportunities: list) -> list[str]:
    """Render opportunities section (SSOT)."""
    lines = ["## Opportunities (SSOT)", ""]
    if not opportunities:
        lines.append("_No opportunities detected._")
        lines.append("")
        return lines

    lines.append("| # | Title | Demand | Competition | Gap | Action |")
    lines.append("|---|-------|--------|-------------|-----|--------|")
    for i, op in enumerate(opportunities, 1):
        lines.append(
            f"| {i} | **{op.title}** | {op.demand_score:.1f} | "
            f"{op.competition_score:.1f} | {op.gap_score:.2f} | {op.recommended_action} |"
        )
    lines.append("")

    # Detail sections for top opportunities
    lines.append("## Top Opportunity Details")
    lines.append("")
    for i, op in enumerate(opportunities[:5], 1):
        lines.append(f"### {i}. {op.title}")
        lines.append(f"")
        lines.append(f"- **Pain Point:** {op.pain_point}")
        lines.append(f"- **Gap Score:** {op.gap_score:.2f}")
        lines.append(f"- **Recommended Action:** {op.recommended_action}")
        lines.append(f"- **Source Insights:** {', '.join(op.source_insights)}")
        lines.append("")

    return lines
```

- [ ] **Step 2: Write output/json_out.py**

```python
"""JSON report generator.

Generates a structured JSON file from pipeline results.
The JSON contains the complete dataset: signals, insights, opportunities.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def serialize_signal(signal: Any) -> dict:
    """Serialize a Signal to a JSON-compatible dict."""
    return {
        "id": signal.id,
        "source": signal.source,
        "type": signal.type,
        "timestamp": signal.timestamp.isoformat(),
        "weight": signal.weight,
        "actor": signal.actor,
        "target": signal.target,
        "meta": signal.meta,
        "raw": signal.raw,
    }


def serialize_insight(insight: Any) -> dict:
    """Serialize an Insight to a JSON-compatible dict."""
    return {
        "id": insight.id,
        "tags": insight.tags,
        "summary": insight.summary,
        "strength": insight.strength,
        "trend": insight.trend,
        "signal_count": insight.signal_count,
        "evidence": insight.evidence,
        "created_at": insight.created_at.isoformat(),
    }


def serialize_opportunity(opportunity: Any) -> dict:
    """Serialize an Opportunity to a JSON-compatible dict."""
    return {
        "id": opportunity.id,
        "title": opportunity.title,
        "pain_point": opportunity.pain_point,
        "demand_score": opportunity.demand_score,
        "competition_score": opportunity.competition_score,
        "gap_score": opportunity.gap_score,
        "recommended_action": opportunity.recommended_action,
        "source_insights": opportunity.source_insights,
        "created_at": opportunity.created_at.isoformat(),
    }


def write_json(result: dict[str, Any], output_dir: str | Path) -> Path:
    """Write a JSON report to the output directory.

    Args:
        result: Pipeline result dict.
        output_dir: Directory to write the report to.

    Returns:
        Path to the generated file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_id = result.get("snapshot_id", "unknown")
    filename = f"report-{ts}-{snapshot_id}.json"
    filepath = output_dir / filename

    data = {
        "snapshot_id": snapshot_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signals": [serialize_signal(s) for s in result.get("signals", [])],
        "insights": [serialize_insight(i) for i in result.get("insights", [])],
        "opportunities": [
            serialize_opportunity(o) for o in result.get("opportunities", [])
        ],
    }

    if result.get("diff"):
        data["diff"] = result["diff"]

    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return filepath
```

- [ ] **Step 3: Verify imports**

Run: `python -c "from output.markdown import write_markdown; from output.json_out import write_json; print('Output modules importable')"`
Expected: `Output modules importable`

- [ ] **Step 4: Commit**

```bash
git add output/markdown.py output/json_out.py
git commit -m "feat: add Markdown and JSON report generators"
```

---
### Task 14: CLI Entry Point

**Files:**
- Create: `cli.py`

**Interfaces:**
- Consumes: `Config`, `Pipeline`, output modules
- Produces: `bldr-dna` CLI with `run`, `show`, `snapshots`, `diff` commands

- [ ] **Step 1: Write cli.py**

```python
"""BuilderDNA CLI entry point.

Commands:
  bldr-dna run              Full analysis
  bldr-dna run --compare    Incremental comparison
  bldr-dna show <account>   View latest snapshot for an account
  bldr-dna snapshots        List all snapshots
  bldr-dna diff <id1> <id2> Compare two snapshots
"""

import sys
from pathlib import Path

import click
from rich.console import Console

from config import load_config
from pipeline import Pipeline
from output.cli import render as render_cli
from output.markdown import write_markdown
from output.json_out import write_json

console = Console()

DEFAULT_CONFIG = "config.yaml"


@click.group()
@click.version_option(version="0.1.0", prog_name="bldr-dna")
def main():
    """BuilderDNA — Analyze GitHub builders, extract tech DNA, discover opportunities."""


@main.command()
@click.option(
    "--config", "-c", default=DEFAULT_CONFIG, help="Path to config.yaml"
)
@click.option(
    "--compare/--no-compare", default=None, help="Force incremental comparison mode"
)
def run(config: str, compare: bool | None):
    """Run the full BuilderDNA analysis pipeline."""
    config_path = Path(config)
    if not config_path.exists():
        console.print(f"[red]Config file not found: {config_path}[/red]")
        sys.exit(1)

    cfg = load_config(config_path)

    # Determine compare mode: CLI flag > config setting
    do_compare = compare if compare is not None else cfg.compare.enabled
    if do_compare:
        console.print("[yellow]Running in compare mode[/yellow]")

    pipeline = Pipeline(cfg)

    with console.status("[bold green]Analyzing...[/bold green]") as status:
        status.update("[bold green]Collecting signals...[/bold green]")
        result = pipeline.run(compare=do_compare)

    # Terminal output
    render_cli(result)

    # File output
    output_dir = Path(cfg.output.dir)
    report_paths = []

    for fmt in cfg.output.formats:
        if fmt == "markdown":
            path = write_markdown(result, output_dir)
            report_paths.append(("Markdown", path))
        elif fmt == "json":
            path = write_json(result, output_dir)
            report_paths.append(("JSON", path))

    if report_paths:
        console.print("\n[bold]Generated reports:[/bold]")
        for label, path in report_paths:
            console.print(f"  {label}: {path}")

    console.print("\n[bold green]Done![/bold green]")


@main.command()
@click.argument("account")
@click.option(
    "--config", "-c", default=DEFAULT_CONFIG, help="Path to config.yaml"
)
def show(account: str, config: str):
    """Show latest analysis for an ACCOUNT."""
    config_path = Path(config)
    if not config_path.exists():
        console.print(f"[red]Config file not found: {config_path}[/red]")
        sys.exit(1)

    from collect.store import SignalStore

    store = SignalStore(Path("snapshots") / "builderdna.db")
    signals = store.get_signals_by_actor(account)

    if not signals:
        console.print(f"[yellow]No signals found for {account}[/yellow]")
        return

    console.print(f"\n[bold]Signals for {account}: {len(signals)} total[/bold]")
    by_type: dict[str, int] = {}
    for s in signals:
        by_type[s.type] = by_type.get(s.type, 0) + 1
    for stype, count in sorted(by_type.items()):
        console.print(f"  {stype}: {count}")


@main.command()
@click.option(
    "--config", "-c", default=DEFAULT_CONFIG, help="Path to config.yaml"
)
def snapshots(config: str):
    """List all snapshots."""
    from collect.store import SignalStore
    from rich.table import Table

    store = SignalStore(Path("snapshots") / "builderdna.db")
    snaps = store.list_snapshots()

    if not snaps:
        console.print("[yellow]No snapshots found[/yellow]")
        return

    table = Table(title="Snapshots")
    table.add_column("ID")
    table.add_column("Created")
    table.add_column("Accounts")
    table.add_column("Signals")
    table.add_column("Insights")
    table.add_column("Opportunities")

    for s in snaps:
        table.add_row(
            s["id"],
            s["created_at"][:19] if s["created_at"] else "-",
            s.get("accounts", "-"),
            str(s.get("signal_count", 0)),
            str(s.get("insight_count", 0)),
            str(s.get("opportunity_count", 0)),
        )

    console.print(table)


@main.command()
@click.argument("snapshot_id_1")
@click.argument("snapshot_id_2")
def diff(snapshot_id_1: str, snapshot_id_2: str):
    """Compare two snapshots by ID."""
    from collect.store import SignalStore
    from rich.table import Table

    store = SignalStore(Path("snapshots") / "builderdna.db")
    snap1 = store.get_snapshot(snapshot_id_1)
    snap2 = store.get_snapshot(snapshot_id_2)

    if not snap1:
        console.print(f"[red]Snapshot not found: {snapshot_id_1}[/red]")
        sys.exit(1)
    if not snap2:
        console.print(f"[red]Snapshot not found: {snapshot_id_2}[/red]")
        sys.exit(1)

    table = Table(title=f"Diff: {snapshot_id_1} vs {snapshot_id_2}")
    table.add_column("Metric")
    table.add_column(snapshot_id_1)
    table.add_column(snapshot_id_2)
    table.add_column("Change")

    for metric in ["signal_count", "insight_count", "opportunity_count"]:
        v1 = snap1.get(metric, 0)
        v2 = snap2.get(metric, 0)
        change = v2 - v1
        change_str = f"+{change}" if change > 0 else str(change)
        table.add_row(metric.replace("_", " ").title(), str(v1), str(v2), change_str)

    console.print(table)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI loads**

Run: `python cli.py --help`
Expected: Help text with run, show, snapshots, diff commands

- [ ] **Step 3: Commit**

```bash
git add cli.py
git commit -m "feat: add CLI entry point with run, show, snapshots, diff commands"
```

---
### Task 15: End-to-End Integration Test

**Files:**
- Create: `tests/test_e2e.py`

**Interfaces:**
- Consumes: all modules
- Produces: full pipeline test with mock GitHub API and mock LLM

- [ ] **Step 1: Write e2e test**

Create `tests/test_e2e.py`:

```python
"""End-to-end integration tests for the full BuilderDNA pipeline."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import Config, GitHubConfig, LLMConfig, WeightConfig, OutputConfig, CompareConfig
from pipeline import Pipeline


MOCK_LLM_INSIGHT_RESPONSE = {
    "insights": [
        {
            "id": "in_001",
            "tags": ["llm", "agent", "python"],
            "summary": "Deep investment in LLM agent frameworks with rising activity",
            "strength": 15.0,
            "trend": "rising",
            "signal_count": 3,
            "evidence": ["alice/toolkit"],
        }
    ]
}

MOCK_LLM_OPPORTUNITY_RESPONSE = {
    "opportunities": [
        {
            "id": "op_001",
            "title": "Agent Testing Framework",
            "pain_point": "No good way to test LLM agent behavior",
            "demand_score": 4.5,
            "competition_score": 2.0,
            "recommended_action": "Build pytest plugin for agent replay",
            "source_insights": ["in_001"],
        }
    ]
}


@pytest.fixture
def e2e_config():
    return Config(
        accounts=["alice"],
        github=GitHubConfig(token="ghp_test"),
        llm=LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test"),
        weights=WeightConfig(repo=5.0, commit=3.0, star=1.0),
        output=OutputConfig(dir="./test_output", formats=["markdown", "json"]),
        compare=CompareConfig(enabled=False),
    )


class TestE2E:
    def test_full_pipeline_with_mocks(self, e2e_config, tmp_path):
        """Full pipeline run with mocked GitHub and LLM."""
        # Setup: redirect snapshots to temp dir
        db_path = tmp_path / "snapshots" / "test.db"
        
        with patch("pipeline.GitHubClient") as MockGH, \
             patch("pipeline.OpenAIClient") as MockLLM, \
             patch("pipeline.SignalStore") as MockStoreCls:
            
            # Mock GitHub client
            mock_gh = MockGH.return_value
            mock_gh.get_repos.return_value = [
                {
                    "id": 1,
                    "full_name": "alice/toolkit",
                    "language": "Python",
                    "topics": ["llm", "agent"],
                    "description": "An LLM agent toolkit",
                    "stargazers_count": 42,
                    "forks_count": 5,
                    "updated_at": "2026-01-15T00:00:00Z",
                    "created_at": "2025-01-01T00:00:00Z",
                }
            ]
            mock_gh.get_starred.return_value = [
                {
                    "id": 100,
                    "full_name": "fastapi/fastapi",
                    "language": "Python",
                    "topics": ["web", "api"],
                    "description": "FastAPI framework",
                    "stargazers_count": 80000,
                }
            ]
            mock_gh.get_commits.return_value = [
                {
                    "sha": "abc123",
                    "commit": {
                        "author": {"name": "Alice", "date": "2026-03-01T10:00:00Z"},
                        "message": "Add MCP server for tool discovery",
                    },
                    "html_url": "https://github.com/alice/toolkit/commit/abc123",
                }
            ]

            # Mock LLM client
            mock_llm = MockLLM.return_value
            mock_llm.complete.side_effect = [
                MOCK_LLM_INSIGHT_RESPONSE,
                MOCK_LLM_OPPORTUNITY_RESPONSE,
            ]

            # Mock store
            mock_store = MockStoreCls.return_value
            mock_store.create_snapshot.return_value = "snap_001"
            mock_store.get_last_snapshot.return_value = None

            # Create pipeline with real config
            pipeline = Pipeline(e2e_config)
            pipeline.store = mock_store
            pipeline.github = mock_gh
            pipeline.llm = mock_llm

            result = pipeline.run()

            # Verify signals
            assert len(result["signals"]) >= 3  # 1 repo + 1 star + 1 commit
            signal_types = {s.type for s in result["signals"]}
            assert "repo" in signal_types
            assert "star" in signal_types
            assert "commit" in signal_types

            # Verify insights
            assert len(result["insights"]) == 1
            assert result["insights"][0].trend == "rising"

            # Verify opportunities
            assert len(result["opportunities"]) == 1
            assert result["opportunities"][0].gap_score > 0

            # Verify store interactions
            mock_store.create_snapshot.assert_called_once()
            mock_store.insert_signals.assert_called_once()

    def test_pipeline_handles_empty_account(self, e2e_config):
        """Pipeline should handle an account with no data gracefully."""
        with patch("pipeline.GitHubClient") as MockGH, \
             patch("pipeline.OpenAIClient"), \
             patch("pipeline.SignalStore") as MockStoreCls:
            
            mock_gh = MockGH.return_value
            mock_gh.get_repos.return_value = []
            mock_gh.get_starred.return_value = []

            mock_store = MockStoreCls.return_value
            mock_store.create_snapshot.return_value = "empty_snap"

            pipeline = Pipeline(e2e_config)
            pipeline.store = mock_store
            pipeline.github = mock_gh

            result = pipeline.run()

            assert result["signals"] == []
            assert result["insights"] == []
            assert result["opportunities"] == []
```

- [ ] **Step 2: Run e2e test**

Run: `python -m pytest tests/test_e2e.py -v`
Expected: all tests PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add end-to-end pipeline integration test"
```

---
