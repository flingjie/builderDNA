# BuilderDNA Skill Evaluation: follow --from-config --diff

## Task

评估 config 里配置的那些账号哪些值得关注，看看跟上次比有什么变化。

(Evaluate which accounts configured in config are worth following, see what changed vs. last snapshot.)

## Skill Interpretation

根据 BuilderDNA SKILL.md 的快速命令映射表：

| 用户说 | 运行命令 | CLI |
|--------|---------|-----|
| "evaluate these accounts" / "who should I follow" | `PYTHONPATH=. uv run bldr-dna follow <accounts...>` | v1 |
| "evaluate follow groups" | `PYTHONPATH=. uv run bldr-dna follow --from-config` | v1 |

Skill 中还明确建议："When the user asks 'who should I follow', always suggest `--from-config --diff` first — it shows both the current ranking AND what changed."

因此正确的命令是：`PYTHONPATH=. uv run bldr-dna follow --from-config --diff`

## 配置文件分析 (config.yaml)

从 `config.yaml` 中读取到的 `follow_groups` 包含 9 个分组，共 29 个账号：

| 分组 | 账号 | 数量 |
|------|------|------|
| Agent 核心 | anthropics, langchain-ai, modelcontextprotocol, hwchase17 | 4 |
| Agent 产品 | NousResearch, Significant-Gravitas, browser-use, crewAIInc, joaomdmoura, ColeMurray | 6 |
| Agent 基础设施 | firecrawl, langflow-ai, infiniflow, transitive-bullshit | 4 |
| 推理引擎 | vllm-project, sgl-project | 2 |
| 代码生成 | antonosika, assafelovic | 2 |
| Python 生态 | samuelcolvin, charliermarsh | 2 |
| 个人影响力 | karpathy, geohot | 2 |
| 深度学习 | foolwood | 1 |
| 国产大模型 | deepseek-ai, QwenLM, alibaba, THUDM, MoonshotAI, 01-ai, baichuan-inc, MiniMax, Tencent-Hunyuan | 9 |

## 执行尝试

### 尝试 1: 通过 uv run 入口点

```bash
cd /path/to/project && PYTHONPATH=. uv run bldr-dna follow --from-config --diff
```

**结果**: `Error: No such command 'follow'.`

`follow` 命令在 Click CLI 组中没有注册。`cli.py` 中确实定义了 `@main.command()` 的 `follow` 函数，但包安装的版本可能不是最新的。

### 尝试 2: 直接运行 cli.py

```bash
PYTHONPATH=. python cli.py follow --from-config --diff
```

**结果**: `ImportError: cannot import name 'Pipeline' from 'pipeline'`

原因：`cli.py` 顶部有 `from pipeline import Pipeline`，但存在 `pipeline.py` 模块和 `pipeline/` 包目录（含空 `__init__.py`）。Python 优先加载包目录，而其中没有 `Pipeline` 类。

## 阻塞问题清单

1. **缺少 `.env` 文件** — 没有 `GITHUB_TOKEN`、`OPENAI_API_KEY`、`LLM_BASE_URL`。无 GitHub Token 则所有 API 调用返回 403/401。

2. **`follow` 命令在入口点未注册** — `uv run bldr-dna` 不识别 `follow` 子命令，需重新安装包。

3. **`pipeline` 模块导入冲突** — `pipeline.py` 与 `pipeline/` 目录共存，Python 解析到空目录。修复方法：在 `pipeline/__init__.py` 中重新导出 `from pipeline import Pipeline`（但这是循环引用），或重命名模块以消除歧义。

4. **`follow` 模块完全缺失** — `cli.py` 依赖 `follow.store.FollowStore` 和 `follow.scorer.score_grouped/apply_delta`，但代码库中不存在 `follow/` 包。这是一个未实现的 feature stub——`cli.py` 中约 160 行 follow 相关代码（L171-L389）都是 skeleton，核心逻辑（scorer、store）尚未编写。

5. **无历史快照** — `snapshots/` 仅含 `.gitkeep`，`--diff` 无法对比。代码会输出 "暂无历史快照，无法对比趋势"。

## 成功运行后的预期行为

根据 `cli.py` 中 `_run_grouped_async` 的设计：

1. GitHub API 并发拉取 29 个账号的 Stars 和 Followers
2. 评分公式：Stars(30%) + Followers(70%)，组内独立归一化
3. 综合评分 >= 60 = "值得关注"，30-59 = "观望"，< 30 = "暂不关注"
4. 快照保存到 SQLite
5. `--diff` 对比上一快照展示 delta 和趋势箭头

## 反馈循环 - 改进建议

按照技能文档要求的 "(1) Present → (2) Ask → (3) Act → (4) Repeat" 循环：

1. **分组微调**: 「国产大模型」组有 9 个账号，归一化后分数可能稀释严重，建议拆分为「大模型创业公司」和「大厂模型」两个子组。

2. **补充账号**: 可加入近期热门的 Agent/LLM 账号如 OpenAI、meta-llama、google-gemini 的开源 org。

3. **权重调整**: 当前 Stars 30% + Followers 70%。若更关注「实际产出」而非「社区影响力」，可提高 Stars 权重到 50%+。

4. **先修阻塞，再跑数据**: 按优先级修复：补 `.env` → 创建 `follow/` 模块 → 解决 `pipeline` 导入冲突 → `uv pip install -e .` 重新安装。

## 总结

任务正确映射到 `bldr-dna follow --from-config --diff` 命令。当前因 5 个阻塞问题（缺环境变量、入口点未注册、模块导入冲突、follow 包缺失、无历史快照）无法执行。修复后，该命令将为 9 组 29 个账号提供分组归一化评分，并通过 diff 展示与历次快照的趋势对比。
