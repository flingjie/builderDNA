# BuilderDNA

**Concept-radar lifecycle + signal-source skill orchestration** —— 从弱信号与单源发现中形成可证伪概念，跨源验证证据，经 Inbox → Watch → Verify → Build/Drop 决定下一步值得研究或构建什么。

核心闭环：

```text
单源发现（repo / X / Reddit / awesome）
→ 选中线索进入概念 Inbox
→ 跨源验证与评分
→ 决定 Watch / Verify / Build / Drop
→ 用后续结果证据校准判断
```

北极星指标：**有多少技术判断经后续证据验证，并真正改变了学习或构建决策。**

## 架构

BuilderDNA 是一组可组合的 CLI 沙盒命令。每个命令：**结构化 JSON 输入 → 确定性计算 → 结构化 JSON 输出**。Claude Code 负责语义推理和编排（含信号源 skill），读取 CLI JSON 与 `state/` / `output/`。无云 LLM、无 Web 服务、无通用 Agent Runtime。

```
Claude Code（编排 + 语义判断）── 读取 state/*.json，决定跑什么
    │
    ▼
确定性沙盒 CLI（独立、JSON in/out）
  验证:   concept / radar    —— 跨源概念生命周期与门禁
  调查:   investigate        —— Reddit 有界痛点调查控制面
  工具:   config             —— 配置检视
    │
    ▼
持久化 — state/*.jsonl + output/*.json
```

跨源验证走 `concept`/`radar`（由 `concept-radar` skill 编排）；Reddit 单源调查走 `investigate`（由 `reddit-opportunity` skill 编排）。产品边界见 `docs/product-contract.md`。

## 快速开始

```bash
# 环境：Python >= 3.11
uv sync --dev

# 配置 .env（可选）
cp .env.example .env
# 可选: TAVILY_API_KEY=...（repo-evolution-learning）
```

## 命令

```bash
# 配置检视（敏感值脱敏）
PYTHONPATH=. uv run builderdna config --show

# 概念生命周期 — capture / list / show / move / merge / score / outcome / review
PYTHONPATH=. uv run builderdna concept capture --title "..." --problem "..."
PYTHONPATH=. uv run builderdna concept list

# 雷达门禁 — scan / verify / experiment / review / source-audit
PYTHONPATH=. uv run builderdna radar scan agent-reliability
PYTHONPATH=. uv run builderdna radar verify <CONCEPT_ID>

# Reddit 有界调查 — init / run / status / propose / finish / resume
PYTHONPATH=. uv run builderdna investigate init --topic "production agent failures"
PYTHONPATH=. uv run builderdna investigate --help

# 运行测试
uv run pytest tests/ -v
```

## 项目结构

```
BuilderDNA/
├── cli/main.py                # Typer 入口
├── cli/commands/              # concept / radar / investigate / config
├── config.py                  # 配置系统（YAML + ${ENV} 变量替换）
├── config.yaml                # 输出等配置
├── config/radars/             # 雷达 YAML（如 agent-reliability）
│
├── concepts/                  # 概念证据、适配器、评分、持久化、radar_config
├── investigations/            # Reddit 痛点调查控制面
├── experiments/               # ExperimentProposal + FDE-Gym 导出
│
├── signals/models.py          # Signal（适配器归一化目标类型）
├── state/jsonl.py             # 共享 JSONL 存储原语
├── observability/             # telemetry.py + output.py
│
├── models/concept.py          # ConceptCard / ConceptEvidence 等契约
├── models/radar_payload.py    # RadarRunPayload
├── schema.md                  # 人类可读的 schema 参考
├── docs/product-contract.md   # 产品边界：核心对象、非目标、Skill 路由
│
├── state/                     # 概念 / 调查 JSONL + skill 状态
├── output/                    # JSON + Markdown 结果
├── .claude/skills/            # Claude Code 的 skills（见下）
└── tests/                     # 测试套件
```

## Skills

技术情报与构建决策的工具集，按职责路由（详见 `docs/product-contract.md`）：

| 职责 | Skill |
|------|-------|
| 跨源概念验证 + Build/Drop + 完整雷达循环 | `concept-radar` |
| GitHub 仓库发现与趋势评估 | `repo-trend` |
| Awesome List 策展发现 | `repo-awesome` |
| 仓库迭代复盘 + HTML 学习报告（`gh` 编排） | `repo-evolution-learning` |
| X 技术信号学习 | `twitter-learning` |
| Reddit 痛点与机会发现 | `reddit-opportunity` |

**X 可提供公开问题线索；Reddit 可提供痛点与机会线索；跨源整合归 `concept-radar`。** 本项目不生成社交回复、不做获客、不维护关系。

## 设计原则

| 原则 | 说明 |
|------|------|
| 沙盒独立 | 每个命令可单独运行，不需要全局状态 |
| JSON 契约 | CLI 输出为结构化 JSON envelope；概念契约在 `models/concept.py` |
| 确定性计算 | 评分与门禁不依赖 LLM，全部是规则与确定性逻辑 |
| 不可变事件 | 追加事件不可变，更正通过 supersedes/replace 引用表达 |
| 证据可追溯 | 每个概念判断可回溯到原始证据与置信度 |
| 无服务层 | 纯 CLI 工具，无 FastAPI/Web 层 |

## 许可证

MIT
