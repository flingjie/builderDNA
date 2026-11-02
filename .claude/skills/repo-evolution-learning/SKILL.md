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
  outcome), searches the project's public promotion content via Tavily Search API, analyzes per-platform
  expression and user feedback, and links feedback to development (explicit/possible/unconfirmed).
  Important: GitHub-only discovery goes to repo-trend; developer DNA to builderdna; cross-source
  concept validation to concept-radar; X-only learning to twitter-learning. This skill never posts,
  replies, or contacts authors.
---

# repo-evolution-learning Skill

你重建一个仓库/PR/功能的开发迭代，分析项目的对外传播与用户反馈，并生成一份自包含的交互式 HTML 学习报告。你编排 `gh` CLI（GitHub 采集）、Tavily Search API（搜索）、opencli（正文采集）；语义分析与 HTML 渲染也由你完成——本仓不再提供 `builderdna repo-learning` Python 命令。

## 这个 Skill 做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 重建一个开发迭代（问题→方案→约束→决策→验证→结果）| 发现/评估/追踪 GitHub repo（那是 repo-trend 的事）|
| 搜索并采集项目对外传播内容（Tavily + opencli）| 分析开发者技术 DNA（那是 builderdna 的事）|
| 分析各平台表达与用户反馈 | 跨源验证概念生命周期（那是 concept-radar 的事）|
| 把反馈关联到开发（explicit/possible/unconfirmed）| 回复/发帖/联系作者（本项目明确不支持）|
| 提炼带小实验的关键决策卡，渲染 HTML | 修改被分析仓库、运行被分析仓库的代码 |

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
You (Claude) — 编排 gh + Tavily + opencli + 本地工作区
       │
       ├─► mkdir output/repo-learning/<run_id>/ ；写 request.yaml
       ├─► gh api / gh pr view / gh api repos/.../pulls/.../reviews|comments|files
       ├─► python <skill_dir>/scripts/tavily_search.py --query …  → search-log.jsonl
       ├─► opencli <site> read / web read  → sources.jsonl
       ├─► 你写 analysis.json（Episode / Narrative / DecisionCard / PromotionContent / FeedbackLink）
       ├─► 按 references/output-contract.md 自检（error 必须修，warning 复核）
       ├─► 复制 references/report-template.html → report.html，替换 __REPORT_DATA_JSON__
       └─► 交付 run_dir/report.html + 简短摘要（不在聊天里重复整份报告）
```

## Quick Reference

| User says | You do |
|-----------|--------|
| "分析这个 PR 的设计取舍" | 建工作区(entry-url) → gh 采集 → 重建决策 → 自检 → 渲染 |
| "复盘这个仓库如何做任务恢复" | 建工作区(repo) → 轻量采集候选 → 选一个迭代 → 深采 → 分析 → 渲染 |
| "这个项目怎么宣传的" | 建工作区 → gh 采集 → Tavily + opencli → 文章/平台分析 → 渲染 |
| "生成交互式 HTML" | 走完采集/分析 → 自检 → 渲染，报告 run_dir/report.html |
| "guided 模式" | request.mode=guided；渲染后先隐藏决策，用户写判断后再揭示 |

## 执行流程

### 1. 确认仓库身份（spec 步骤 A）

1. 校验 `owner/repo` 或 `https://github.com/…`（含 PR URL）。
2. 建工作区：`output/repo-learning/<run_id>/`（`run_id` 用时间戳或短 hash），写入 `request.yaml`（至少含 `repo`、可选 `entry_url`、`mode: report|guided`、`output.language`）。
3. 用 `gh` 采集仓库元数据与 README：
   - `gh repo view <owner>/<repo> --json nameWithOwner,description,url,homepageUrl,createdAt,updatedAt,primaryLanguage,stargazerCount`
   - `gh api repos/<owner>/<repo>/readme --jq .content`（base64 解码）
4. 若入口是 PR：`gh pr view <url> --json number,title,body,author,createdAt,mergedAt,commits,files,reviews,comments`；再用 `gh api` 拉 review comments / issue comments / files patch（按需）。
5. 每条来源追加到 `sources.jsonl`（按 `references/output-contract.md`），确认别名/官网/作者账号写入 `analysis.json` 的 `repo_identity`。排除同名项目。

### 2. 选择开发迭代（spec 步骤 B）

- **默认轻量**：只拉 README、项目介绍、公开时间线 + 候选 PR 列表（`gh pr list --repo … --limit 20 --json …`），`fetch_status=partial`。从这些轻量来源识别**最多 3 个**有证据的决策候选。
- 只有用户主动深入、或满足 `references/episode-analysis.md` 的深入触发条件时，才对选中 PR 拉全量 Issue / PR / review / diff。
- 不要把 README 当前架构解释直接当早期设计理由；Squash 或缺早期提交时说明无法完整还原。

### 3. 重建决策（spec 步骤 C）

按时间整理：问题出现 → 初始方案 → 评审反馈 → 实现调整 → 验证 → 后续结果。每个决策回答：作者当时知道什么？有哪些选项？什么约束推动选择？牺牲了什么？最终验证了什么？作者没提过的替代方案标「分析者提出」，不要写成作者已比较过的方案。

### 4. 搜索传播内容（spec 步骤 D）

- 先调用本 skill 的 `<skill_dir>/scripts/tavily_search.py` 做全网检索。必须配置 `TAVILY_API_KEY`；不要硬编码或把密钥写入日志。查询模板与参数见 `references/tavily-search.md`。
- Tavily 不可用或缺少密钥时，写 `coverage_notes=["engine unavailable: …"]` 且 `results=[]`，不要用仓库搜索冒充全网覆盖结论。
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

### 8. 写 analysis.json、自检与渲染

1. 按 `references/output-contract.md` 写 `analysis.json`（`Analysis` 根对象：repo_identity、episode、narrative、claims、promotion_contents、feedback_links、decision_cards、platform_stats、coverage_notes）。
2. 先写 `narrative`（5 问叙事 + 标题 + 可选猜题），遵循 `references/writing-rules.md`：约 600–1000 中文字；原始 episode / decision_cards 保留完整作为折叠证据。
3. 从 `promotion_contents` 选 2 篇有差异的内容标 `featured=true` 并各写 `borrowable`；其余折叠。
4. 默认最多 3 张决策卡（`references/evidence-rules.md` + `episode-analysis.md`）；正文只突出叙事里的 1 个主要教训。
5. **自检清单（替代原 validate 命令）**：
   - 必填字段齐全；枚举值合法；时间戳为 UTC ISO-8601 或 null。
   - 每个 `SourceRef.source_id` 都能在 `sources.jsonl` 找到。
   - `evidence_status` / `relation` 与正文表述一致；禁用表达见 `evidence-rules.md`。
   - 报告数据中不得出现 `GITHUB_TOKEN` / `TAVILY_API_KEY` 明文。
6. **渲染**：复制 `references/report-template.html` 为 `run_dir/report.html`，把占位符 `__REPORT_DATA_JSON__` 替换为下面结构的 JSON（单行或紧凑均可；须转义 `</` 为 `<\/`，并替换 U+2028/U+2029）：

```json
{
  "analysis": { },
  "manifest": {
    "run_id": "...",
    "stage_status": {
      "init": "completed",
      "collect": "completed",
      "search": "completed",
      "content": "completed",
      "analyze": "completed",
      "validate": "completed",
      "render": "completed"
    },
    "budgets_used": {}
  },
  "request": { },
  "sources_index": {
    "<source_id>": {
      "id": "...", "kind": "...", "url": "...", "canonical_url": "...",
      "author": "...", "published_at": null, "fetch_status": "full",
      "body": "...", "missing_scope": []
    }
  }
}
```

7. 交付：报告路径 + 一行关键发现 + 分析范围。不要整份贴进聊天。

## 运行工作区

```
output/repo-learning/<run_id>/
  request.yaml      sources.jsonl    search-log.jsonl
  analysis.json     manifest.json    report.html
```

- `sources.jsonl` / `search-log.jsonl` 由你追加；两条 JSONL 都按 `id` 去重（last-wins）。
- `manifest.json` 记录 `stage_status` 与 `budgets_used`；中断后读它从最近未完成阶段继续。`request.yaml` 若中途变更，fail-closed 并说明原因。

## 预算与错误

- `request.yaml` 的 `limits`（若有）是初始预算，不是目标；材料不足时报告缺口，不硬凑数量。
- 预算耗尽返回部分材料；报告显示截断范围（`coverage_notes` / `missing_scope`）。
- Tavily 搜索或正文失败：记录失败，不阻塞已有分析；短时网络失败有限重试，访问限制不无限重试。
- 文章采集用有限并发；需要浏览器的操作按 opencli 工具约束串行执行。

## Reference Files

| When to read | Which file |
|--------------|-----------|
| 身份确认 / 迭代选择 / 决策重建（步骤 A–C）| `references/episode-analysis.md` |
| Tavily 调用、查询模板与 SearchRecord 映射（步骤 D）| `references/tavily-search.md` |
| 搜索 / 平台归类 / 去重 / 文章与反馈分析（步骤 D–F）| `references/promotion-analysis.md` |
| evidence_status / relation / 事实-推断-未知 / 禁用表达 | `references/evidence-rules.md` |
| analysis.json / sources.jsonl / search-log.jsonl 精确 schema | `references/output-contract.md` |
| 中文简明表达规则 | `references/writing-rules.md` |
| 交互式 HTML 报告模板 | `references/report-template.html` |

## Conversational flow

1. 解析 repo 或 entry-url，判断是 PR 入口还是仓库入口。
2. 建工作区 → `gh` 采集，确认仓库身份。
3. （仓库入口）选一个迭代 → 深采选中 PR。
4. Tavily 搜索 + opencli 采集传播内容。
5. 重建决策 + 分析表达/反馈 + 关联反馈与开发 + 提炼学习卡。
6. 写 `narrative` + featured 传播内容 → `analysis.json` → 自检 → 渲染 HTML。
7. 交付报告路径 + 简短摘要，问是否深挖或 refine。
