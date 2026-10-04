# BuilderDNA

**Technology Intelligence Sandbox Toolkit** —— 分析开发者、仓库和社区信号，理解技术变化，发现痛点，验证值得学习或构建的方向。

核心闭环：

```text
采集外部信号
→ 识别趋势与痛点
→ 形成可证伪假设
→ 跨源验证
→ 决定 Watch / Verify / Build / Drop
→ 用后续事实校准判断
```

北极星指标：**有多少技术判断经后续证据验证，并真正改变了学习或构建决策。**

## 架构

BuilderDNA 是一组可组合的 CLI 沙盒命令。每个命令：**结构化 JSON 输入 → 确定性计算 → 结构化 JSON 输出**。Claude Code 负责语义推理和编排，读取 JSON 输出。无 LLM（除本地 Ollama 嵌入）、无 Web 服务、无通用 Agent Runtime。

```
Claude Code（编排 + 语义判断）── 读取 state/*.json，决定跑什么
    │
    ▼
确定性沙盒 CLI（独立、JSON in/out）
  采集:   collect            —— GitHub 信号（repos + issues）
  分析:   trend / pain       —— 趋势速度 · 痛点聚类
  机会:   opportunity        —— 规则引擎生成机会卡片
  验证:   concept / radar / radar-cycle —— 跨源概念生命周期
  人物问题: builders           —— 问题记录、实践轨迹、跨人比较、可验证机会卡
  校准:   observability      —— 预测 vs 后续事实
  工具:   report / config    —— 渲染 · 配置
    │
    ▼
持久化 — SQLite（signals）+ output/*.json + state/*.json
```

命令之间通过 JSON 文件传递数据：`collect` 产出 `signals.json` → `trend`/`pain` 消费 → `opportunity` 消费两者 → `report` 渲染任意结果。跨源验证走 `concept`/`radar`/`radar-cycle`。

## 快速开始

```bash
# 环境：Python >= 3.11，GitHub Token，可选 Ollama（pain 命令需要）
uv sync --dev

# 配置 .env
echo 'GITHUB_TOKEN=ghp_xxx' > .env
# 可选: EMBEDDING_BASE_URL=http://localhost:11434/v1

# 编辑 config.yaml 中的 accounts 和 domains
```

## 命令

```bash
# 采集信号 — 从 GitHub 拉取 repos 和 issues
PYTHONPATH=. uv run builderdna collect agent --window 365 --output output/signals.json

# 趋势分析 — 从信号计算主题趋势（速度、阶段）
PYTHONPATH=. uv run builderdna trend agent --data output/signals.json

# 痛点挖掘 — HDBSCAN 聚类 issue 文本（需要 Ollama + bge-m3）
PYTHONPATH=. uv run builderdna pain agent --data output/signals.json

# 机会发现 — 规则引擎，gap_score = demand / competition
PYTHONPATH=. uv run builderdna opportunity --trends output/trends.json --pains output/pain_clusters.json

# 概念验证 — 跨源生命周期（capture / scan / verify / build / source-audit）
PYTHONPATH=. uv run builderdna concept capture --help
PYTHONPATH=. uv run builderdna radar scan agent-reliability
PYTHONPATH=. uv run builderdna radar-cycle start agent-reliability

# Builder 问题与实践轨迹
PYTHONPATH=. uv run builderdna builders capture alice --statement "修改 prompt 后难以确认旧问题是否修复" --job-to-be-done "确认历史失败案例是否修复" --trigger-context "修改 prompt 或工具实现后"
PYTHONPATH=. uv run builderdna builders compare
PYTHONPATH=. uv run builderdna builders opportunity

# 校准 — 对比历史预测与后续事实
PYTHONPATH=. uv run builderdna observability --all --domain agent

# 渲染报告 — 任意 SandboxResult → Markdown 或 JSON
PYTHONPATH=. uv run builderdna report --data output/opportunities.json --format md

# 运行测试
uv run pytest tests/ -v
```

## 项目结构

```
BuilderDNA/
├── cli/main.py                # Typer 入口
├── cli/commands/              # collect / trend / pain / opportunity / report / config / observability / concept / radar / radar-cycle / builders
├── config.py                  # 配置系统（YAML + ${ENV} 变量替换）
├── config.yaml                # accounts, domains, vendors, embedding
│
├── collector/github/          # GitHub API 客户端（httpx, cache, rate limiter）
├── collector/normalizer.py    # 原始 API 响应 → Signal 统一模型
│
├── intelligence/trend/        # 趋势计算（velocity, stage）
├── intelligence/pain/         # 痛点挖掘（HDBSCAN + embeddings）
├── intelligence/opportunity/  # 机会评分（规则引擎）
├── intelligence/builder_problems/ # Builder 问题快照、轨迹事件、跨人比较、机会卡
│
├── concepts/                  # 概念证据、适配器、评分、持久化
├── radar_cycles/              # 可恢复的雷达周期状态机（checkpoint / engine / config）
│
├── signals/
│   ├── models.py              # Signal（统一不可变事件模型）
│   └── store.py               # SQLite 持久化
│
├── models/payload.py          # 所有命令的输出 schema（Claude Code 读取的契约）
├── schema.md                  # 人类可读的 schema 参考
├── docs/product-contract.md   # 产品边界：核心对象、非目标、Skill 路由
│
├── state/
│   ├── hypotheses.json        # 跨对话的探索状态追踪
│   ├── user_weights.json      # 用户偏好权重（只影响排序）
│   ├── builder_interest_profile.json  # 用户兴趣画像（只影响优先级）
│   ├── builders/              # builders.jsonl 问题快照 + events.jsonl 轨迹事件
│   ├── reflections.jsonl      # 技术复盘事件日志
│   └── watches.json           # 已保存的 repo 搜索（repo-trend skill）
│
├── output/                    # JSON + Markdown 结果
├── .claude/skills/            # Claude Code 的 skills（见下）
└── tests/                     # 测试套件
```

## Skills

技术情报与构建决策的工具集，按职责路由（详见 `docs/product-contract.md`）：

| 职责 | Skill |
|------|-------|
| 编排 Python sandbox（collect/trend/pain/opportunity） | `builderdna` |
| 跨源概念验证 + Build/Drop 决策 | `concept-radar` |
| 可恢复的确定性雷达周期 | `concept-radar-loop` |
| GitHub 仓库发现与趋势评估 | `repo-trend` |
| Awesome List 策展发现 | `repo-awesome` |
| X 技术信号学习 | `twitter-learning` |
| Reddit 痛点与机会发现 | `reddit-opportunity` |
| 预测校准与诊断 | `observability` |
| 确定性分析能力优化 | `optimize` |
| 技术判断复盘 / 合成 / 校验 / 记录 | `reflect` / `distill` / `digest` / `note` |
| 用户兴趣画像（BuilderInterestProfile） | `value-discovery` |
| 工具执行轨迹分析 | `trace-classify` |

**X 只负责学习信号；Reddit 只负责痛点和机会信号。** 本项目不生成社交回复、不做获客、不维护关系。

## 设计原则

| 原则 | 说明 |
|------|------|
| 沙盒独立 | 每个命令可单独运行，不需要全局状态 |
| JSON 契约 | 所有输出通过 `models/payload.py` 定义，Claude Code 可直接读取 |
| 确定性计算 | 聚类、评分不依赖 LLM，全部是规则和统计算法 |
| 不可变事件 | 追加事件不可变，更正通过 supersedes/replace 引用表达 |
| 证据可追溯 | 每个趋势/痛点/机会/DNA 判断都可回溯到原始证据与置信度 |
| 无服务层 | 纯 CLI 工具，无 FastAPI/Web 层 |
| 管道可组合 | 命令通过文件连接，顺序灵活 |

## 许可证

MIT
