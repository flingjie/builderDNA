# Radar-Core Slimdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以 concept + radar 为保留内核，删除所有未使用的管道（collect/trend/pain/opportunity/dna/builders/observability 诊断）及其模型、测试、skill，并同步文档与依赖。

**Architecture:** 纯删除 + 随动收缩，不重构保留集内部。按依赖方向从 CLI 层到引擎包到配置逐层删除，每个任务结束时测试套件必须全绿。保留边界已在 spec 中验证闭合：`concepts/` + `investigations/` + `experiments/` + `cli/commands/{concept,radar,investigate,config_cmd}.py` + `models/{concept,radar_payload}.py` + `signals/models.py` + `state/jsonl.py` + `observability/{telemetry,output}.py`。

**Tech Stack:** Python 3 / uv / pytest / Typer。所有命令在项目根目录运行。

**Spec:** `docs/superpowers/specs/2026-11-02-radar-core-slimdown-design.md`

## Global Constraints

- 每个任务结束时 `uv run pytest tests/ -q` 必须 0 failed（警告可忽略）。
- 不改变保留命令（concept/radar/investigate/config）的行为与输出 schema。
- 删除即删除，不留注释掉的代码、不留兼容 shim。
- `from signals.models import Signal` 与 `from state.jsonl import ...` 导入路径保持不变。
- 保留 skill：`concept-radar`、`reddit-opportunity`、`twitter-learning`、`repo-trend`、`repo-awesome`、`repo-evolution-learning`。
- `config/radars/`、`config/reddit_feeds/`、`tests/fixtures/radar/` 不动。

---

### Task 1: 删除 CLI 层死命令并改写 main.py

**Files:**
- Delete: `cli/commands/collect.py`, `cli/commands/trend.py`, `cli/commands/pain.py`, `cli/commands/pain_finalize.py`, `cli/commands/opportunity.py`, `cli/commands/report_cmd.py`, `cli/commands/observability_cmd.py`, `cli/commands/dna.py`, `cli/commands/builders.py`, `cli/commands/schema_validation.py`
- Delete: `tests/test_cli/`（整目录，仅含 `test_pain_finalize.py`）, `tests/test_opportunity_evidence.py`, `tests/test_schema_validation.py`
- Modify: `cli/main.py`

**Interfaces:**
- Produces: `cli/main.py` 只注册 config、concept、radar、investigate 四个命令。后续任务依赖此文件不再引用任何被删模块。

- [ ] **Step 1: 删除命令文件与对应测试**

```bash
git rm cli/commands/collect.py cli/commands/trend.py cli/commands/pain.py \
  cli/commands/pain_finalize.py cli/commands/opportunity.py cli/commands/report_cmd.py \
  cli/commands/observability_cmd.py cli/commands/dna.py cli/commands/builders.py \
  cli/commands/schema_validation.py
git rm -r tests/test_cli
git rm tests/test_opportunity_evidence.py tests/test_schema_validation.py
```

- [ ] **Step 2: 改写 `cli/main.py` 为以下完整内容**

```python
"""BuilderDNA CLI entry point."""
import typer
from rich.console import Console

from observability.output import OutputLevel, set_output_level
from cli.commands.config_cmd import config
from cli.commands.concept import concept
from cli.commands.radar import radar_app
from cli.commands.investigate import investigate


app = typer.Typer(
    name="builderdna",
    help="BuilderDNA — Technology Intelligence Sandbox Toolkit",
)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: int = typer.Option(0, "--verbose", "-v", count=True,
                                help="Increase verbosity (-v, -vv)"),
    quiet: bool = typer.Option(False, "--quiet", "-q",
                               help="Suppress all non-error output"),
) -> None:
    """Global options: --verbose / --quiet control output level."""
    if quiet:
        set_output_level(OutputLevel.QUIET)
    elif verbose >= 2:
        set_output_level(OutputLevel.DEBUG)
    elif verbose >= 1:
        set_output_level(OutputLevel.VERBOSE)
    else:
        set_output_level(OutputLevel.NORMAL)

    if ctx.invoked_subcommand is None:
        console.print("[yellow]Please specify a subcommand.[/yellow]")
        raise typer.Exit()


app.command(name="config")(config)
app.add_typer(concept, name="concept")
app.add_typer(radar_app, name="radar")
app.add_typer(investigate, name="investigate")

if __name__ == "__main__":
    app()
```

- [ ] **Step 3: 检查 `cli/commands/__init__.py` 是否 re-export 被删命令**

Run: `cat cli/commands/__init__.py`
若 import 了被删文件，删掉那些行，只保留对 config_cmd/concept/radar/investigate 的引用（或留空 docstring）。

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/ -q`
Expected: 大量测试因 Task 2 的包还在而继续通过；0 failed。若有 collection error，按报错删掉遗漏的引用。

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor: remove dead CLI commands, keep concept/radar/investigate/config"
```

---

### Task 2: 删除引擎包与死模型

**Files:**
- Delete: `intelligence/`（整包）, `collector/`（整包）, `signals/store.py`, `models/payload.py`, `models/builder_problem.py`, `models/builder_interest_profile.py`, `concepts/adapters/github.py`
- Delete tests: `tests/test_intelligence/`, `tests/test_collector/`, `tests/test_signal/test_store.py`, `tests/test_builder_problems.py`, `tests/test_builder_interest_profile.py`, `tests/test_developer_dna.py`, `tests/test_integration.py`, `tests/test_pain_time_span.py`, `tests/test_github_evidence_adapter.py`, `tests/test_models/`（整目录，仅含 `test_payload.py`）
- Modify: `signals/__init__.py`, `models/__init__.py`, `concepts/adapters/__init__.py`（如有 re-export）

**Interfaces:**
- Consumes: Task 1 之后 `cli/` 不再引用这些包。
- Produces: `signals/` 只剩 `models.py`；`models/` 只剩 `concept.py` 和 `radar_payload.py`。

- [ ] **Step 1: 删除包与模型**

```bash
git rm -r intelligence collector tests/test_intelligence tests/test_collector tests/test_models
git rm signals/store.py tests/test_signal/test_store.py
git rm models/payload.py models/builder_problem.py models/builder_interest_profile.py
git rm concepts/adapters/github.py
git rm tests/test_builder_problems.py tests/test_builder_interest_profile.py \
  tests/test_developer_dna.py tests/test_integration.py tests/test_pain_time_span.py \
  tests/test_github_evidence_adapter.py
```

- [ ] **Step 2: 清理 `__init__.py` 残留 re-export**

Run: `rg "store|payload|builder_problem|builder_interest|github" signals/__init__.py models/__init__.py concepts/adapters/__init__.py`
删掉命中的 import/`__all__` 条目。

- [ ] **Step 3: 全仓扫描残留引用**

Run: `rg "from intelligence|import intelligence|from collector|import collector|signals.store|models.payload|models.builder_problem|models.builder_interest_profile|adapters.github" --type py`
Expected: 无输出。有则逐个删除引用处。

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/ -q`
Expected: 0 failed（预计剩约 400–500 个测试）。

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor: remove collect/trend/pain/opportunity engines and dead models"
```

---

### Task 3: 收缩 observability 为 telemetry + output

**Files:**
- Delete: `observability/behavior.py`, `observability/snapshot.py`, `observability/hypothesis.py`, `observability/diagnostics.py`, `observability/metrics.py`, `observability/versions.py`, `predictions/`（快照数据目录）
- Delete tests: `tests/test_observability/test_behavior.py`, `test_hypothesis.py`, `test_metrics.py`, `test_snapshot.py`, `test_versions.py`（保留 `test_output.py`, `test_telemetry.py`）
- Modify: `observability/__init__.py`, `cli/commands/config_cmd.py`

**Interfaces:**
- Produces: `observability` 包只导出 `RunTelemetry`, `OutputLevel`, `set_output_level`, `get_output_level`, `get_console`, `vprint`。保留集的四处 import（concept.py 的 RunTelemetry、radar.py 的 OutputLevel/vprint、investigate.py 的 RunTelemetry、config_cmd.py 的 OutputLevel/vprint）继续可用。

- [ ] **Step 1: 删除模块与测试**

```bash
git rm observability/behavior.py observability/snapshot.py observability/hypothesis.py \
  observability/diagnostics.py observability/metrics.py observability/versions.py
git rm tests/test_observability/test_behavior.py tests/test_observability/test_hypothesis.py \
  tests/test_observability/test_metrics.py tests/test_observability/test_snapshot.py \
  tests/test_observability/test_versions.py
git rm -r predictions 2>/dev/null || rm -rf predictions
```

- [ ] **Step 2: 改写 `observability/__init__.py` 为以下完整内容**

```python
"""Observability module — run telemetry and output level control."""

from observability.telemetry import RunTelemetry
from observability.output import (
    OutputLevel,
    set_output_level,
    get_output_level,
    get_console,
    vprint,
)

__all__ = [
    "RunTelemetry",
    "OutputLevel",
    "set_output_level",
    "get_output_level",
    "get_console",
    "vprint",
]
```

- [ ] **Step 3: 从 `cli/commands/config_cmd.py` 剥离 record_command**

把 `from observability import OutputLevel, vprint, record_command` 改为
`from observability import OutputLevel, vprint`，并删除文件内所有 `record_command(...)` 调用语句（用 `rg -n "record_command" cli/commands/config_cmd.py` 定位）。

- [ ] **Step 4: 确认 telemetry.py/output.py 不反向依赖被删模块**

Run: `rg "behavior|snapshot|hypothesis|diagnostics|metrics|versions" observability/telemetry.py observability/output.py`
Expected: 无输出（或仅注释）。有 import 则删除。

- [ ] **Step 5: 跑测试 + Commit**

Run: `uv run pytest tests/ -q` → 0 failed

```bash
git add -A && git commit -m "refactor: shrink observability to telemetry + output"
```

---

### Task 4: 瘦身 config.py / config.yaml / .env.example

**Files:**
- Modify: `config.py`, `config.yaml`, `tests/test_config.py`, `cli/commands/config_cmd.py`, `.env.example`

**Interfaces:**
- Produces: `Config` 模型只含 `output: OutputConfig`。`load_config(path) -> Config` 签名不变，env 替换（`${VAR}` / `${VAR:-default}`）行为不变。

- [ ] **Step 1: 改写 `config.py`**

保留现有文件的 `_load_dotenv`、`_ENV_VAR_RE`、`_resolve_env`、`_resolve_config`、`load_config` 原样不动；删除 `GitHubConfig`、`EmbeddingConfig`、`CollectConfig`、`OpportunityWeights`、`OpportunityConfig`、`VendorConfig` 六个类；把 `Config` 改为：

```python
class Config(BaseModel):
    """Root configuration for BuilderDNA."""

    output: OutputConfig = Field(default_factory=OutputConfig)
```

（`OutputConfig` 保留原样。）

- [ ] **Step 2: 改写 `config.yaml` 为以下完整内容**

```yaml
output:
  dir: ./output
  formats:
    - markdown
    - json
```

- [ ] **Step 3: 适配 `cli/commands/config_cmd.py`**

Run: `rg -n "github|embedding|accounts|vendors|opportunity|collect|mask" cli/commands/config_cmd.py`
删除对已移除字段的展示/掩码逻辑（如 `_mask_token` 及其调用）。`config --show` 输出剩余的 resolved config 即可。

- [ ] **Step 4: 改写 `tests/test_config.py` 为以下完整内容**

```python
"""Tests for the slimmed config system (output section + env substitution)."""

import os

import pytest

from config import Config, OutputConfig, load_config


def test_load_minimal_config(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  dir: ./output\n  formats:\n    - json\n")
    cfg = load_config(cfg_file)
    assert isinstance(cfg, Config)
    assert cfg.output.dir == "./output"
    assert cfg.output.formats == ["json"]


def test_defaults_when_empty_sections(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("{}\n")
    cfg = load_config(cfg_file)
    assert cfg.output == OutputConfig()


def test_env_substitution_with_default(tmp_path, monkeypatch):
    monkeypatch.delenv("BDNA_TEST_DIR", raising=False)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  dir: ${BDNA_TEST_DIR:-./fallback}\n")
    cfg = load_config(cfg_file)
    assert cfg.output.dir == "./fallback"


def test_env_substitution_from_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("BDNA_TEST_DIR", "/tmp/bdna")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  dir: ${BDNA_TEST_DIR}\n")
    cfg = load_config(cfg_file)
    assert cfg.output.dir == "/tmp/bdna"


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent/config.yaml")
```

- [ ] **Step 5: 清理 `.env.example`**

删除 `GITHUB_TOKEN`、`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL` 条目及其注释（代码已不消费）；保留 `TAVILY_API_KEY`（repo-evolution-learning skill 用）和 `OPENCLI_WINDOW`。

- [ ] **Step 6: 跑测试 + Commit**

Run: `uv run pytest tests/ -q` → 0 failed

```bash
git add -A && git commit -m "refactor: slim config to output section only"
```

---

### Task 5: 删除死 skill、state 文件、references，并改写路由测试

**Files:**
- Delete: `.claude/skills/builderdna/`, `.claude/skills/observability/`, `.claude/skills/optimize/`, `.claude/skills/value-discovery/`, `.claude/skills/trace-classify/`
- Delete: `state/hypotheses.json`, `state/behavior_log.jsonl`, `state/builder_interest_profile.json`, `state/bootstrap.json`（保留 `state/jsonl.py` 及 concepts/investigations 的数据文件）
- Delete: `references/builder-lens.md`, `references/cases/`（仅被 builderdna skill 与 CLAUDE.md 引用；保留 `references/repo-scout/`，repo-trend/repo-awesome 仍引用）
- Modify: `tests/test_skill_routing.py`

**Interfaces:**
- Produces: skill 目录只剩 6 个保留 skill；路由测试与新拓扑一致。

- [ ] **Step 1: 删除 skill、state、references**

```bash
git rm -r .claude/skills/builderdna .claude/skills/observability .claude/skills/optimize \
  .claude/skills/value-discovery .claude/skills/trace-classify
git rm -r references/cases
git rm references/builder-lens.md
rm -f state/hypotheses.json state/behavior_log.jsonl state/builder_interest_profile.json state/bootstrap.json
git rm --cached --ignore-unmatch state/hypotheses.json state/behavior_log.jsonl state/builder_interest_profile.json state/bootstrap.json 2>/dev/null || true
```

- [ ] **Step 2: 改写 `tests/test_skill_routing.py`**

对现有文件做以下修改（其余保留）：
1. `ROUTING_EDGES` 删除 `"builderdna"` 和 `"observability"` 两个 key；
2. 其余 owner 的边里删除所有指向 `builderdna` 的元组（`repo-trend`、`repo-awesome`、`repo-evolution-learning` 各删一条 "routes developer DNA to builderdna"）；
3. 删除整个 `test_builderdna_does_not_replace_specialists` 函数；
4. `test_engagement_and_outreach_have_no_owner` 的遍历列表从 `("concept-radar", "twitter-learning", "builderdna")` 改为 `("concept-radar", "twitter-learning", "reddit-opportunity")`；
5. 文件顶部注释中 "eight owners" 改为实际数量（6 个保留 skill）。

- [ ] **Step 3: 清理保留 skill 中指向被删 skill 的路由行**

Run: `rg -n "builderdna|value-discovery|observability skill|optimize" .claude/skills/concept-radar .claude/skills/repo-trend .claude/skills/repo-awesome .claude/skills/reddit-opportunity .claude/skills/twitter-learning .claude/skills/repo-evolution-learning`
在命中的 SKILL.md 中删除指向已删 skill 的路由条目/表行（注意不要误删普通词 "observability"，只删 skill 路由语境的行）。

- [ ] **Step 4: 跑测试 + Commit**

Run: `uv run pytest tests/ -q`（重点看 `tests/test_skill_routing.py` 与 `tests/test_concept_radar_skill.py` 通过）

```bash
git add -A && git commit -m "refactor: remove skills orchestrating deleted pipelines, sync routing contract"
```

---

### Task 6: 依赖与打包清理

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 确认 httpx/openai/sklearn/hdbscan 无保留集引用**

Run: `rg -l "httpx|openai|sklearn|hdbscan" --type py | grep -v tests`
Expected: 无输出。若 `investigations/` 等命中 httpx，则 httpx 保留，其余照删。

- [ ] **Step 2: 修改 `pyproject.toml`**

`dependencies` 改为（若 Step 1 发现 httpx 被使用则保留 `"httpx>=0.27"`）：

```toml
dependencies = [
    "pydantic>=2.0",
    "click>=8.0",
    "rich>=13.0",
    "pyyaml>=6.0",
    "typer>=0.12",
]
```

dev 依赖删除 `"pytest-httpx>=0.30"`（若 httpx 保留且有测试用到则一并保留，以 `rg "pytest_httpx|httpx" tests/ -l` 为准）。

`[tool.setuptools.packages.find]` 的 include 改为：

```toml
include = ["models*", "signals*", "cli*", "observability*", "concepts*", "experiments*", "investigations*", "state*"]
```

- [ ] **Step 3: 重建环境并跑测试**

```bash
uv sync --all-extras
uv run pytest tests/ -q
```
Expected: 0 failed。

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: drop unused deps (hdbscan, scikit-learn, openai) and prune package list"
```

---

### Task 7: 文档同步

**Files:**
- Modify: `CLAUDE.md`, `schema.md`, `docs/product-contract.md`

- [ ] **Step 1: 重写 `CLAUDE.md`**

逐节修改：
- **Overview**：产品定位改为 "concept-radar 生命周期 + 信号源 skill 编排"，删除对 collect/trend/pain/opportunity 管道的描述。
- **Commands**：只留 `concept`、`radar`、`investigate`、`config` 四组命令示例（从现有文件中原样保留这四组的命令行），删除其余。
- **Architecture 图**：重画为三支——`concepts/`（store/service/scoring/matching/handoffs/radar_config + adapters/{manual_x,reddit}）、`investigations/`（Reddit 调查控制平面 → 经 adapters/reddit 摄入 concept evidence）、`experiments/`（radar experiment 的 FDE-Gym 导出）；底部注明 `signals/models.py`（Signal 类型）、`state/jsonl.py`（JSONL 存储原语）、`observability/`（telemetry + output）为共享基础。
- **Key Design Decisions**：删除 LLM-free pipeline 中关于 TF-IDF/Ollama/HDBSCAN 的例外描述、collector cache、SQLite signals、contributors 限制四条；保留两循环架构与 Config via YAML + env。
- **Skills 表**：只留 6 个保留 skill 的行；删除 value-discovery 相关说明与 `references/cases` 的 Key Files 行。
- **Key Files 表**：删除已删文件的行（payload.py、builder_problem.py、builder_interest_profile.py、signals/store.py、intelligence/*、observability/metrics.py、state/bootstrap.json、state/builder_interest_profile.json、state/behavior_log.jsonl、state/hypotheses.json、state/watches.json 若 repo-trend 还在则保留 watches、references/cases、.env 行更新为仅 TAVILY_API_KEY）。
- **Cross-source routing 段**：删除指向被删 skill 的句子。

- [ ] **Step 2: 收缩 `schema.md`**

只保留 SandboxResult 通用结构说明 + concept/radar/investigate 相关 payload 的小节；删除 RepoSignal/IssueSignal/TopicTrend/RepoSummary/CandidateGroup/PainCandidate/PainCluster/IssueSummary/OpportunityCard/DeveloperDNA 小节。

- [ ] **Step 3: 更新 `docs/product-contract.md`**

产品边界改为「concept-radar 生命周期 + 信号源 skill」；routing 规则（§4.1 owner 列表）删除 builderdna/observability/optimize/value-discovery/trace-classify 条目，owner 数量同步为 6；非目标保持不变。

- [ ] **Step 4: 交叉检查文档与现实一致**

Run: `rg -n "builderdna collect|builderdna trend|builderdna pain|builderdna opportunity|builderdna report|builderdna dna|builderdna builders|builderdna observability" CLAUDE.md schema.md docs/ .claude/skills/`
Expected: 无输出。

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "docs: sync CLAUDE.md, schema.md, product contract after radar-core slimdown"
```

---

### Task 8: 终验

- [ ] **Step 1: 全量测试**

Run: `uv run pytest tests/ -v 2>&1 | tail -5`
Expected: 全部通过，0 failed。

- [ ] **Step 2: 保留命令冒烟**

```bash
PYTHONPATH=. uv run builderdna --help
PYTHONPATH=. uv run builderdna config --show
PYTHONPATH=. uv run builderdna concept list
PYTHONPATH=. uv run builderdna radar scan --radar agent-reliability
PYTHONPATH=. uv run builderdna investigate --help
```
Expected: 全部正常退出（radar scan 若因无新证据输出空结果也算通过；`--radar` 名以 `ls config/radars/` 实际存在的为准）。

- [ ] **Step 3: 零残留扫描**

```bash
rg -n "from intelligence|from collector|models.payload|models.builder_problem|models.builder_interest|signals.store|observability.behavior|observability.snapshot|observability.hypothesis|observability.diagnostics|observability.metrics|schema_validation" \
  --type py --type md -g '!docs/superpowers/**'
```
Expected: 无输出（spec/plan 文档自身除外，已被 glob 排除）。

- [ ] **Step 4: 收尾 Commit（如有改动）**

```bash
git add -A && git commit -m "chore: final verification fixes for radar-core slimdown"
```
