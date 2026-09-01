# BuilderDNA

分析 GitHub 开发者，提取技术 DNA，发现产品机会。

## 架构

BuilderDNA 是 7 个独立沙盒 CLI 命令的组合工具箱。每个命令：**结构化 JSON 输入 → 确定性计算 → 结构化 JSON 输出**。Claude Code 负责语义推理和编排。

```
Claude Code（编排 + 解读）── 读取 state/hypotheses.json，决定跑什么
    │
    ▼
7 个沙盒 CLI 命令（独立、JSON in/out）
  collect → trend → pain → opportunity → report → config → observability
    │
    ▼
全局记忆 — SQLite + output/*.json + state/*.json
```

命令之间通过 JSON 文件传递数据：`collect` 产出 `signals.json` → `trend` 和 `pain` 消费它 → `opportunity` 消费两者 → `report` 渲染任意结果。

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

# 渲染报告 — 任意 SandboxResult → Markdown 或 JSON
PYTHONPATH=. uv run builderdna report --data output/opportunities.json --format md

# 运行测试
uv run pytest tests/ -v   # 268 tests
```

## 项目结构

```
BuilderDNA/
├── cli/main.py                # Typer 入口，7 个命令
├── cli/commands/              # collect.py, trend.py, pain.py, opportunity.py, report_cmd.py, observability_cmd.py, config_cmd.py
├── config.py                  # 配置系统（YAML + ${ENV} 变量替换）
├── config.yaml                # accounts, domains, vendors, embedding
│
├── collector/github/          # GitHub API 客户端（httpx, cache, rate limiter）
├── collector/normalizer.py    # 原始 API 响应 → Signal 统一模型
│
├── intelligence/trend/        # 趋势计算（velocity, clustering）
├── intelligence/pain/         # 痛点挖掘（HDBSCAN + embeddings）
├── intelligence/opportunity/  # 机会评分（规则引擎）
│
├── signals/
│   ├── models.py              # Signal（统一事件模型）
│   └── store.py               # SQLite 持久化
│
├── models/payload.py          # 所有命令的输出 schema（Claude Code 读取的契约）
├── schema.md                  # 人类可读的 schema 参考
│
├── state/
│   ├── hypotheses.json        # 跨对话的探索状态追踪
│   ├── user_weights.json      # 用户偏好权重
│   ├── user_dna.json          # 用户认知模型
│   ├── reflections.jsonl      # 复盘事件日志
│   └── watches.json           # 已保存的 repo 搜索（repo-trend skill）
│
├── output/                    # JSON + Markdown 结果
├── .claude/skills/            # Claude Code 的 skills
│   ├── builderdna/            #   7 命令编排 + 假设树管理
│   ├── concept-radar/         #   跨源概念雷达：弱信号 → 验证 → 构建/否决
│   ├── repo-trend/            #   趋势 repo 发现 + 3 阶评估
│   ├── repo-awesome/          #   Awesome List 挖掘 + 策展评分
│   ├── reflect/               #   多轮对抗式复盘
│   └── distill/               #   阶段性合成蒸馏
└── tests/                     # 268 个测试
```

新增 `concept-radar` skill：跨源合成 + `Inbox → Watch → Verify → Build/Drop` 概念生命周期。单源请求仍走专家 skill（`twitter-learning` / `twitter-discussion` / `reddit-opportunity` / `repo-trend`）。

## 配置

```yaml
# config.yaml
accounts:
  - hwchase17                     # 分析的 GitHub 账号

domains:
  agent:                          # 域名（topic 集合）
    topics:
      - mcp
      - langchain
      - agent-framework
      - multi-agent

github:
  token: ${GITHUB_TOKEN}          # 从 .env 加载
  max_concurrent: 5

embedding:
  model: bge-m3:latest            # pain 命令使用
  base_url: ${EMBEDDING_BASE_URL:-http://localhost:11434/v1}

vendors:
  domestic: [deepseek-ai, QwenLM] # 国内厂商追踪
  overseas: [anthropics, langchain-ai]
```

## 设计原则

| 原则 | 说明 |
|------|------|
| 沙盒独立 | 每个命令可单独运行，不需要全局状态 |
| JSON 契约 | 所有输出通过 `models/payload.py` 定义，Claude Code 可直接读取 |
| 确定性计算 | 聚类、评分不依赖 LLM，全部是规则和统计算法 |
| 无服务层 | 纯 CLI 工具，无 FastAPI/Web 层 |
| 管道可组合 | 命令通过文件连接，顺序灵活 |

## 许可证

MIT
