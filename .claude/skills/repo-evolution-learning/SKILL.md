---
name: repo-evolution-learning
description: >
  ALWAYS use this skill when the user wants to reconstruct a GitHub repo/PR/feature's
  development episode, analyze how a project promotes itself, or link public feedback to
  later development — and render it as an interactive HTML learning report. Covers: "分析这个
  PR 的设计取舍", "复盘这个仓库的迭代", "这个项目怎么宣传的", "学习这个仓库如何设计 X",
  "generate a dev-episode learning report", "repo evolution learning", "interactive HTML
  learning report", and any request to learn a project's design tradeoffs and promotion methods.
  It reconstructs one episode (problem → alternatives → constraints → decisions → validation →
  outcome), searches the project's public promotion content via opencli, analyzes per-platform
  expression and user feedback, and links feedback to development (explicit/possible/unconfirmed).
  Important: GitHub-only discovery goes to repo-trend; developer DNA to builderdna; cross-source
  concept validation to concept-radar; X-only learning to twitter-learning. This skill never posts,
  replies, or contacts authors.
---

# repo-evolution-learning Skill

你重建一个仓库/PR/功能的开发迭代，分析项目的对外传播与用户反馈，并生成一份自包含的交互式 HTML 学习报告。你编排 opencli（搜索 + 正文采集）与 `builderdna repo-learning`（GitHub 采集、校验、渲染）。搜索与语义分析是你的职责；GitHub 采集、校验、HTML 渲染是确定性 Python 工具。

## 这个 Skill 做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 重建一个开发迭代（问题→方案→约束→决策→验证→结果）| 发现/评估/追踪 GitHub repo（那是 repo-trend 的事）|
| 搜索并采集项目对外传播内容（opencli）| 分析开发者技术 DNA（那是 builderdna 的事）|
| 分析各平台表达与用户反馈 | 跨源验证概念生命周期（那是 concept-radar 的事）|
| 把反馈关联到开发（explicit/possible/unconfirmed）| 回复/发帖/联系作者（本项目明确不支持）|
| 提炼带小实验的迁移学习卡，渲染 HTML | 修改被分析仓库、运行被分析仓库的代码 |

## 路由 (Routing)

| 请求 | 路由 |
|------|------|
| 重建迭代取舍 + 传播/反馈分析 + HTML 报告 | **`repo-evolution-learning`**（本 skill）|
| 只发现/评估 GitHub repo | `repo-trend` |
| 分析 GitHub 开发者技术 DNA | `builderdna` |
| 跨源验证概念 | `concept-radar` |
| X 情报/学习 | `twitter-learning` |

## Architecture

```
User: "分析这个 PR 的设计取舍，生成 HTML 报告"
       │
       ▼
You (Claude) — 编排 opencli + gh + builderdna repo-learning
       │
       ├─► builderdna repo-learning init --repo … --entry-url …   (建 run 工作区)
       ├─► builderdna repo-learning collect --run-dir …           (GitHub: PR/review/diff/后续)
       ├─► opencli / smart-search  搜索传播内容 → search-log.jsonl
       ├─► opencli <site> read / web read  采集正文 → sources.jsonl
       ├─► 你写 analysis.json（Episode / PromotionContent / FeedbackLink / LearningCard）
       ├─► builderdna repo-learning validate --run-dir …
       ├─► builderdna repo-learning render --run-dir …            (生成 report.html)
       └─► 报告 run_dir/report.html + 简短摘要（不在聊天里重复整份报告）
```

## Quick Reference

| User says | You do |
|-----------|--------|
| "分析这个 PR 的设计取舍" | init(entry-url) → collect → 重建决策 → validate → render |
| "复盘这个仓库如何做任务恢复" | init(repo) → collect(候选) → 选一个迭代 → collect(entry-url) → 分析 → render |
| "这个项目怎么宣传的" | init → collect → opencli 搜索 + 采集 → 文章/平台分析 → render |
| "生成交互式 HTML" | 走完 collect/分析 → validate → render，报告 run_dir/report.html |
| "guided 模式" | init --mode guided；渲染时先隐藏决策，用户写判断后再揭示 |

## 执行流程

### 1. 确认仓库身份（spec 步骤 A）

1. 校验 `--repo` / `--entry-url`（`owner/repo` 或 `https://github.com/…`）。
2. 运行 `builderdna repo-learning init --repo … [--entry-url …] [--mode report|guided]`，记下返回的 `run_id` 与 `run_dir`。
3. 运行 `builderdna repo-learning collect --run-dir <dir>`（若入口是 PR，用 `--entry-url <PR>`）。
4. 从 `sources.jsonl` 读 `github_repo` 元数据 + `github_readme`，确认项目别名、官网、公开作者账号，写入 `analysis.json` 的 `repo_identity`。排除同名项目（无证据的搜索结果只进候选区）。

### 2. 选择开发迭代（spec 步骤 B）

- PR 入口优先：只扩读相关 Issue、代码与后续记录。
- 仓库入口：从 `collect` 得到的候选 PR（`fetch_status=partial`）里选一个「有清楚问题/讨论/验证」的迭代，记录选择与排除理由；然后 `collect --run-dir <dir> --entry-url <选中 PR>` 拉全量详情。
- 不要把 README 当前架构解释直接当早期设计理由；Squash 或缺早期提交时说明无法完整还原。

### 3. 重建决策（spec 步骤 C）

按时间整理：问题出现 → 初始方案 → 评审反馈 → 实现调整 → 验证 → 后续结果。每个决策回答：作者当时知道什么？有哪些选项？什么约束推动选择？牺牲了什么？最终验证了什么？作者没提过的替代方案标「分析者提出」，不要写成作者已比较过的方案。

### 4. 搜索传播内容（spec 步骤 D）

- 先用 opencli/smart-search 做全网检索（见 `references/promotion-analysis.md` 的查询模板）。搜索引擎不可用时记录失败，不要用仓库搜索替代全网覆盖结论。
- 按 canonical URL 与正文相似度去重，保留转载关系；平台原生与转载分别计数。
- 把每次查询记入 `search-log.jsonl`（SearchRecord），命中的摘要记入 `sources.jsonl`（`kind=search_result`）。

### 5. 拉取文章与讨论（spec 步骤 E）

- 用 opencli（`<site> read` / `web read` / 站点适配器）拉取首发、重要发布、深度解释、用户实践、有依据质疑的正文。
- 保留正文、发布时间、身份、链接与可见指标；`fetch_status=full|partial|blocked|failed` 记录真实状态，`missing_scope` 记录缺什么。
- 访问受限时保存可读摘要与缺失范围；评论只代表采集到的讨论，不代表全部用户。

### 6. 分析表达与反馈（spec 步骤 F）

- 文章分析：目标读者、痛点、核心承诺、开场方法、解释结构、演示证据、行动要求、承诺边界。复用 `twitter-learning/references/analysis-guide.md` 的七角分析契约，不要复制整份提示词。
- 反馈分析：理解困难、安装障碍、功能需求、实际使用案例、替代方案、质疑、失败报告。
- 比较同一项目不同平台的表达（优先接近的版本/时间）。不要因高互动直接归因于写法。

### 7. 连接反馈与开发（spec 步骤 G）

- `explicit`：开发记录明确引用反馈，或作者明确说明反馈推动修改。
- `possible`：主题和时间相符，但无直接引用。
- `unconfirmed`：只能确定时间先后，或材料不足。
- 显示关联证据，把「可能」写成待验证假设；不要以同关键词或时间邻近自动判定因果。

### 8. 写 analysis.json 与收尾

1. 按 `references/output-contract.md` 的 schema 写 `analysis.json` 到 run_dir（`Analysis` 根对象：repo_identity、episode、claims、promotion_contents、feedback_links、learning_cards、platform_stats、coverage_notes）。
2. 默认生成 1–3 张学习卡（`references/evidence-rules.md` 的证据/表达规则）。
3. `builderdna repo-learning validate --run-dir <dir>`，修掉 error，复核 warning。
4. `builderdna repo-learning render --run-dir <dir>`。
5. 交付：报告路径 + 一行关键发现 + 分析范围。不要整份贴进聊天。

## 运行工作区

`init` 在 `<out_dir>/repo-learning/<run_id>/` 建立：

```
request.yaml      sources.jsonl    search-log.jsonl
analysis.json     manifest.json    report.html
```

- `sources.jsonl` / `search-log.jsonl` 由你（skill）追加 `web_article`/`web_discussion`/`search_result` 记录；GitHub 记录由 `collect` 追加。两条 JSONL 都按 `id` 去重。
- `manifest.json` 是 checkpoint：`stage_status`（init/collect/search/content/analyze/validate/render）与 `budgets_used`。
- 中断后 `builderdna repo-learning resume --run-dir <dir>` 返回下一个未完成阶段；`request.yaml` 变更会 fail-closed。

## 预算与错误

- `request.yaml` 的 `limits` 是初始预算，不是目标；材料不足时报告缺口，不硬凑数量。
- 预算耗尽返回部分材料；报告显示截断范围（`coverage_notes` / `missing_scope`）。
- 搜索或正文失败：记录失败，不阻塞已有分析；短时网络失败有限重试，访问限制不无限重试。
- 文章采集用有限并发；需要浏览器的操作按 opencli 工具约束串行执行。

## Reference Files

| When to read | Which file |
|--------------|-----------|
| 身份确认 / 迭代选择 / 决策重建（步骤 A–C）| `references/episode-analysis.md` |
| 搜索 / 平台归类 / 去重 / 文章与反馈分析（步骤 D–F）| `references/promotion-analysis.md` |
| evidence_status / relation / 事实-推断-未知 / 禁用表达 | `references/evidence-rules.md` |
| analysis.json / sources.jsonl / search-log.jsonl 精确 schema | `references/output-contract.md` |
| 中文简明表达规则（spec §7 中文适配）| `references/writing-rules.md` |

## Conversational flow

1. 解析 `--repo` 或 `--entry-url`，判断是 PR 入口还是仓库入口。
2. `init` → `collect`，确认仓库身份。
3. （仓库入口）选一个迭代 → 二次 `collect --entry-url` 拉全量。
4. opencli 搜索 + 采集传播内容。
5. 重建决策 + 分析表达/反馈 + 关联反馈与开发 + 提炼学习卡。
6. 写 `analysis.json` → `validate` → `render`。
7. 交付报告路径 + 简短摘要，问是否深挖或 refine。
