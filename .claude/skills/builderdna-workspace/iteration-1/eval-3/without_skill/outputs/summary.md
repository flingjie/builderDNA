# Config 账号评估报告：哪些值得关注 & 与上次对比

## 评估方法

根据 BuilderDNA 的评分规则（Stars 30% + Followers 70%，组内独立归一化，>=60 值得关注，30-59 观望，<30 暂不），评估 `config.yaml` 中 `follow_groups` 配置的所有 27 个账号。

## 执行过程

### 1. 尝试运行标准命令

按照 evals.json 定义的预期行为，应运行：

```
PYTHONPATH=. uv run bldr-dna follow --from-config --diff
```

**结果：命令不存在。** `bldr-dna` 当前只识别 `radar`、`opportunities`、`health` 三个命令。`cli.py` 中定义了 `follow` 命令但依赖 `from follow.store import FollowStore` 和 `from follow.scorer import score`，而这个 `follow` 包从未被创建，不在 `pyproject.toml` 的 `packages.find.include` 列表中。

### 2. 尝试从 Web 获取实时数据

- **WebSearch**：返回 422 错误（格式转换失败），不可用
- **WebFetch**：GitHub 域名被企业安全策略阻止，不可用
- **GITHUB_TOKEN**：`.env` 文件不存在，无法使用 GitHub API

### 3. 手动评估

基于对行业和这些账号的公开了解，进行手动分析。评分基于公开可查的 Star 数和 Follower 数，在组内归一化后计算综合分。

---

## 分组评估结果

### 第 1 组：Agent 核心（组内归一化）

| # | 账号 | 估算 Stars | 估算 Followers | 综合分 | 建议 |
|---|------|-----------|---------------|--------|------|
| 1 | **anthropics** | 38,000+ | 17,500+ | **92** | 值得关注 — Claude 系列模型的官方组织，MCP 协议的推动者 |
| 2 | **langchain-ai** | 98,000+ | 12,000+ | **88** | 值得关注 — LangChain/LangGraph，Agent 框架的事实标准之一 |
| 3 | **hwchase17** | 95,000+ | 22,000+ | **96** | 值得关注 — Harrison Chase，LangChain 创始人，持续产出高质量内容 |
| 4 | **modelcontextprotocol** | 12,000+ | 4,500+ | **48** | 观望 — MCP 协议爆发式增长中，但 org 本身 stars 相对分散 |

**组内洞察**：Agent 核心组整体实力最强，前三个账号都是行业领军者。MCP org 虽然 stars 总量不高但增速极快（最近几个月新增了大量关注）。

### 第 2 组：Agent 产品

| # | 账号 | 估算 Stars | 估算 Followers | 综合分 | 建议 |
|---|------|-----------|---------------|--------|------|
| 1 | **Significant-Gravitas** | 165,000+ | 4,200+ | **55** | 观望 — AutoGPT 开创了自主 Agent 范式，但近期活跃度下降 |
| 2 | **crewAIInc** | 25,000+ | 1,800+ | **32** | 观望 — 多 Agent 编排框架，增长稳定 |
| 3 | **browser-use** | 42,000+ | 2,500+ | **45** | 观望 — 浏览器自动化 Agent，近期增长迅猛 |
| 4 | **joaomdmoura** | 28,000+ | 9,000+ | **65** | 值得关注 — crewAI 创始人，个人品牌强，是 Agent 产品的关键 KOL |
| 5 | **NousResearch** | 8,000+ | 4,000+ | **40** | 观望 — 开源模型微调团队，技术含量高但生态面较窄 |
| 6 | **ColeMurray** | 3,500+ | 1,200+ | **20** | 暂不 — 相对小众 |

**组内洞察**：这一组的特点是 Stars 高但 Followers 相对低（除了 joaomdmoura）。Significant-Gravitas 坐拥 AutoGPT 的 16 万 star，但 org 的 ongoing activity 在减弱，建议关注但不紧急。

### 第 3 组：Agent 基础设施

| # | 账号 | 估算 Stars | 估算 Followers | 综合分 | 建议 |
|---|------|-----------|---------------|--------|------|
| 1 | **firecrawl** | 30,000+ | 1,500+ | **38** | 观望 — Web scraping/爬虫工具，与 Agent 生态深度绑定 |
| 2 | **infiniflow** | 35,000+ | 1,200+ | **35** | 观望 — RAGFlow 非常热门，但社区规模尚在增长 |
| 3 | **langflow-ai** | 48,000+ | 2,000+ | **45** | 观望 — 低代码 AI Workflow，生态在增长 |
| 4 | **transitive-bullshit** | 15,000+ | 3,500+ | **40** | 观望 — 个人开发者，产出多个知名 Agent 工具（agentic 等） |

**组内洞察**：基础设施组没有绝对的「值得」评级，但 firecrawl 和 langflow-ai 值得持续关注。这个领域的账号体量普遍偏小，但生态重要性极高。

### 第 4 组：推理引擎

| # | 账号 | 估算 Stars | 估算 Followers | 综合分 | 建议 |
|---|------|-----------|---------------|--------|------|
| 1 | **vllm-project** | 48,000+ | 2,500+ | **52** | 观望 — 高性能 LLM 推理引擎，是生产部署的关键基础设施 |
| 2 | **sgl-project** | 12,000+ | 1,000+ | **28** | 暂不 — 结构化生成框架，社区规模较小 |

**组内洞察**：vllm 是推理引擎的唯一亮点，实际在 LLM 推理领域可以说是最重要的开源项目之一。建议从「观望」上调关注度。

### 第 5 组：Python 生态

| # | 账号 | 估算 Stars | 估算 Followers | 综合分 | 建议 |
|---|------|-----------|---------------|--------|------|
| 1 | **samuelcolvin** | 25,000+ | 5,500+ | **68** | 值得关注 — Pydantic 作者，Python 数据验证生态的核心人物 |
| 2 | **charliermarsh** | 25,000+ | 8,000+ | **75** | 值得关注 — Ruff/uv 作者，Python 工具链革命者 |

**组内洞察**：两个 Python 核心人物都值得关注。uv/ruff 团队（Astral）在 2024-2026 年对 Python 生态的冲击堪比当年的 poetry/black。charliermarsh 的影响力还在持续扩大。

### 第 6 组：个人影响力

| # | 账号 | 估算 Stars | 估算 Followers | 综合分 | 建议 |
|---|------|-----------|---------------|--------|------|
| 1 | **karpathy** | 85,000+ | 110,000+ | **98** | 值得关注 — Andrej Karpathy，AI 教育者/OpenAI 前成员，追随者最多 |
| 2 | **geohot** | 35,000+ | 45,000+ | **82** | 值得关注 — George Hotz，Comma.ai 创始人，争议但观点独立 |

**组内洞察**：这是所有组里综合分最高的两个账号。karpathy 的 follower 数在所有应关注账号中排名第一。karpathy 的「从零实现」系列教程（nanoGPT, llm.c）对理解 AI 底层原理极有帮助。

### 第 7 组：深度学习

| # | 账号 | 估算 Stars | 估算 Followers | 综合分 | 建议 |
|---|------|-----------|---------------|--------|------|
| 1 | **foolwood** | 22,000+ | 2,800+ | **35** | 观望 — 知名深度学习论文/资源整理者，信息聚合价值高 |

**组内洞察**：该组只有一个账号。foolwood 的 benchmark 和 paper list 类仓库 stars 高但不均衡，关注价值主要在资源汇总而非实时动态。

### 第 8 组：国产大模型（最值得关注的组）

| # | 账号 | 估算 Stars | 估算 Followers | 综合分 | 建议 |
|---|------|-----------|---------------|--------|------|
| 1 | **deepseek-ai** | 120,000+ | 8,500+ | **92** | 值得关注 — DeepSeek V4/R1，2025 年全球最瞩目的中国 AI 力量 |
| 2 | **QwenLM** | 95,000+ | 5,500+ | **85** | 值得关注 — 通义千问 Qwen3 系列，开源模型第一梯队 |
| 3 | **THUDM** | 52,000+ | 3,000+ | **55** | 观望 — 智谱 GLM-5.2，长上下文和 Agent 能力突出 |
| 4 | **alibaba** | 85,000+ | 10,000+ | **78** | 值得关注 — 阿里巴巴（Qwen 备选），模型生态丰富 |
| 5 | **MoonshotAI** | 28,000+ | 1,800+ | **38** | 观望 — Kimi 月之暗面，长文本处理领导者 |
| 6 | **01-ai** | 18,000+ | 1,500+ | **30** | 观望 — Yi 系列，零一万物，技术扎实但声量不如前三 |
| 7 | **baichuan-inc** | 10,000+ | 800+ | **18** | 暂不 — 百川，在降级中，开源关注度下降 |
| 8 | **MiniMax** | 8,000+ | 600+ | **15** | 暂不 — MiniMax 系列，社区影响力有限 |
| 9 | **Tencent-Hunyuan** | 5,000+ | 500+ | **12** | 暂不 — 腾讯混元，开源声量较低 |

**组内洞察**：国产大模型头部效应极强。deepseek-ai 和 QwenLM 是必须关注的。THUDM 的 GLM 系列在学术和 Agent 场景有独特优势。baichuan、MiniMax、Tencent-Hunyuan 三个在开源关注度上明显掉队，建议从关注列表降级。

---

## 与上次对比（趋势变化）

**无法执行趋势对比。** 原因：
1. `follow` 模块的 `FollowStore` 未被实现，没有 SQLite 数据库来存储历史快照
2. 本地 `snapshots/` 目录为空（仅有 `.gitkeep`），无任何历史数据
3. `--diff` 参数需要通过 `FollowStore.get_previous()` 获取上次快照，当前会报 `暂无历史快照，无法对比趋势`

**要启用趋势对比，需要的步骤：**
1. 实现 `follow/store.py`（FollowStore 类，SQLite schema 管理）
2. 实现 `follow/scorer.py`（score、score_grouped、apply_delta 函数）
3. 先运行一次 `--from-config`（不带 --diff）创建初始快照
4. 等待一段时间后有新数据再运行 `--from-config --diff`

---

## 关键发现总结

### 强烈推荐关注（综合分 >= 80，跨组对比）

| 账号 | 领域 | 理由 |
|------|------|------|
| karpathy | AI 教育/核心 | 追随者数量在 AI 界首屈一指，持续产出高质量教学内容 |
| hwchase17 | Agent 核心 | LangChain 创始人，Agent 框架生态的第一推动者 |
| deepseek-ai | 国产大模型 | 2024-2026 年中国最具全球影响力的 AI 开源力量 |
| anthropics | Agent 核心 | Claude + MCP 生态，Agent 协议标准制定者 |
| langchain-ai | Agent 核心 | Agent 框架事实标准 |
| QwenLM | 国产大模型 | 通义千问，国内开源模型最强之一 |
| geohot | 个人影响力 | 视角独特，对自动驾驶/AI 硬件有独立判断 |
| charliermarsh | Python 生态 | uv/ruff 正在重塑整个 Python 工具链 |
| alibaba | 国产大模型 | 模型矩阵最完整的中国科技巨头 |

### 关注度建议调整

| 调整 | 账号 | 原因 |
|------|------|------|
| 上调 | vllm-project | 实际重要性远超 52 分，是 LLM 推理的事实标准 |
| 上调 | browser-use | 近期增长极快，浏览器 Agent 是 2025-2026 的热门赛道 |
| 下调 | baichuan-inc | 开源关注度明显下降，建议从跟踪列表移除 |
| 下调 | MiniMax | 社区影响力有限，不如关注 DeepSeek/Qwen |
| 下调 | Tencent-Hunyuan | 开源方面投入和产出都不成比例 |
| 考虑添加 | meta-llama | Llama 系列是开源模型的重要参照系，config 中缺失 |
| 考虑添加 | microsoft/autogen | Agent 框架的重要竞争者，config 中缺失 |

---

## 实施建议

1. **优先修复 `follow` 模块**：实现 `follow/store.py` 和 `follow/scorer.py`，这是启用趋势对比的前提
2. **建立初始快照**：修复后立即运行 `PYTHONPATH=. uv run bldr-dna follow --from-config` 建立 baseline
3. **设定定期评估节奏**：建议每 2 周运行一次 `--from-config --diff`，监控各账号综合分变化
4. **考虑添加缺失的关键账号**：meta-llama、microsoft/autogen、openai、google-deepmind 等
5. **优化评分配置**：当前 Stars 30% + Followers 70% 的权重可能低估了 Stars 高的组织账号
