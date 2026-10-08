# 输出契约 (output contract)

本文件是 `analysis.json`、`sources.jsonl`、`search-log.jsonl` 的精确 schema。Python 端的权威实现是 `repo_learning/models.py`（Pydantic）；`validate` 与 `render` 按此契约读取。你写 JSON 时必须匹配这些字段名与枚举值。

## 通用规则

- 所有时间戳是带时区的 UTC ISO-8601（如 `2026-10-06T16:59:00+00:00`）；未知时间用 `null`，**不用 `0`，不用空字符串**。
- 枚举值全小写。
- 每个 JSONL 记录必须有 `id`（按 `id` 去重，last-wins）。
- `SourceRef.source_id` 必须指向 `sources.jsonl` 里已采集的记录；只读过搜索摘要时，对应的 `SourceRecord.kind` 应是 `search_result` 且 `fetch_status=partial`。

## sources.jsonl（每行一个 SourceRecord）

```json
{
  "id": "web_article:https://example.com/post",
  "kind": "web_article",
  "url": "https://example.com/post?utm=x",
  "canonical_url": "https://example.com/post",
  "author": "作者名",
  "published_at": "2026-01-01T00:00:00+00:00",
  "fetched_at": "2026-10-06T16:59:00+00:00",
  "body": "正文…",
  "fetch_status": "full",
  "missing_scope": [],
  "content_hash": "sha1"
}
```

- `kind`（枚举，全小写）：`github_repo` `github_readme` `github_pr` `github_issue` `github_review` `github_review_comment` `github_issue_comment` `github_commit` `github_diff` `github_file` `web_article` `web_discussion` `search_result`
- `fetch_status`：`full` `partial` `blocked` `failed`
- GitHub 记录由 `collect` 写入；`web_article` / `web_discussion` / `search_result` 由你（skill）写入。

## search-log.jsonl（每行一个 SearchRecord）

```json
{
  "id": "tavily:2026-10-06T16:59:00+00:00:ab12cd34ef56",
  "query": "\"项目名\" launch",
  "engine": "tavily",
  "searched_at": "2026-10-06T16:59:00+00:00",
  "period": "",
  "results": [{"title": "…", "url": "https://…", "snippet": "…"}],
  "coverage_notes": []
}
```

- `id` 建议形如 `{engine}:{searched_at}:{sha1(query)[:12]}`。
- 本 skill 使用 Tavily，`engine` 写 `tavily`；`results[].snippet` 使用 Tavily 的 `content` 摘要。
- Tavily 不可用时：写一条 `coverage_notes=["engine unavailable: …"]` 且 `results=[]`，不要用仓库搜索冒充全网覆盖。

## analysis.json（Analysis 根对象）

```json
{
  "schema_version": 1,
  "repo_identity": {
    "owner": "octocat",
    "name": "hello-world",
    "canonical_url": "https://github.com/octocat/hello-world",
    "project_names": [],
    "author_accounts": [],
    "website": "",
    "identity_evidence": []
  },
  "episode": {
    "id": "pr-1",
    "title": "…",
    "problem": "…",
    "constraints": [],
    "alternatives": [],
    "decisions": [],
    "implementation_changes": [],
    "validation": [],
    "outcome": "",
    "source_refs": []
  },
  "narrative": {
    "headline": "…",
    "problem": "…",
    "root_cause": "…",
    "what_changed": "…",
    "tradeoff": "",
    "evidence": "…",
    "lesson": "…",
    "small_experiment": "…",
    "guess_question": "",
    "guess_answer": "",
    "source_refs": []
  },
  "claims": [],
  "promotion_contents": [],
  "feedback_links": [],
  "learning_cards": [],
  "platform_stats": [],
  "coverage_notes": [],
  "generated_at": "2026-10-06T16:59:00+00:00"
}
```

### Claim（alternatives / decisions / validation / claims 的元素）

```json
{
  "text": "陈述",
  "evidence_status": "sourced",
  "source_refs": [{"source_id": "…", "locator": "", "excerpt": "", "supports": []}],
  "limitations": []
}
```

- `evidence_status`：`sourced` `inferred` `unknown`
- `sourced` 必须带 ≥1 个 `source_refs`；`sourced` 只表示材料直接支持该陈述。作者宣称性能提升时写「作者称」，不要改写为已验证结果。

### Narrative（读者视图的 5 问叙事，必填）

```json
{
  "headline": "Archify：生成失败，为什么检查仍然通过？",
  "problem": "第一次生成成功，目录里留下一个 HTML 文件。第二次向同一路径生成失败，但旧文件仍然存在。检查程序检查了旧文件，随后报告通过。",
  "root_cause": "检查程序能判断文件是否合格，却无法确认它是否来自本次生成。",
  "what_changed": "作者让系统记录交付状态。生成失败后，后续检查会读到失败记录，阻止旧文件被当成新结果。",
  "tradeoff": "自动清理遗留锁可能误删其他进程正在使用的锁。最终方案保留锁，要求人工确认后恢复。代价是恢复多了一步操作。",
  "evidence": "问题报告人验证了原故障场景，相关回归测试和跨平台 CI 通过。材料尚未证明长期使用效果。",
  "lesson": "当多个步骤通过文件传递结果时，需要确认文件属于哪次任务。文件存在，不足以证明当前任务成功。",
  "small_experiment": "先成功生成，再向相同路径故意生成失败。检查下一步会不会继续使用旧结果。",
  "guess_question": "第二次生成失败，但旧文件还在。下一步检查通过，能证明本次任务成功吗？",
  "guess_answer": "不能。旧文件存在，不能证明本次任务成功。",
  "source_refs": []
}
```

- `headline` / `problem` / `root_cause` / `what_changed` / `evidence` / `lesson` / `small_experiment` 必填（`min_length=1`）。
- `tradeoff` 可空；无次要取舍时留空。
- `guess_question` / `guess_answer` 可空，但应成对出现（`validate` 对单边出现给 warning）。
- 正文是「重新选择 + 重写」后的读者视图，不是原始 Episode 字段的拼接；原始 `alternatives` / `decisions` / `validation` / `implementation_changes` 保留完整，折叠进「展开证据」。
- 写作规则见 `references/writing-rules.md`；正文约 800–1200 中文字，只保留 1 主要教训 + 1 次要取舍 + 1 小实验。

### PromotionContent

```json
{
  "id": "…",
  "source_id": "web_article:…",
  "platform": "hackernews",
  "actor_type": "author",
  "repo_match": "confirmed",
  "featured": false,
  "content_type": "launch",
  "audience": "…",
  "hook": "…",
  "promise": "…",
  "proof": "…",
  "borrowable": "…",
  "call_to_action": "…"
}
```

- `platform`：`x` `hackernews` `reddit` `linkedin` `producthunt` `v2ex` `juejin` `zhihu` `wechat` `xiaohongshu` `dev` `medium` `blog` `other`
- `actor_type`：`author` `contributor` `third_party` `user` `unknown`
- `repo_match`：`confirmed` `probable` `rejected`
- `featured`：`true` 表示进入学传播正文的两篇有差异内容；其余保留完整但折叠进证据。
- `borrowable`：哪句表达/框架值得借用、为什么（featured 内容必填，其余可空）。

### FeedbackLink

```json
{
  "feedback_refs": [],
  "development_refs": [],
  "relation": "possible",
  "rationale": "…"
}
```

- `relation`：`explicit` `possible` `unconfirmed`

### LearningCard

```json
{
  "problem": "…",
  "decision": "…",
  "tradeoff": "…",
  "applicable_when": "…",
  "avoid_when": "…",
  "small_experiment": {
    "hypothesis": "…",
    "minimal_change": "…",
    "observe_method": "…",
    "stop_condition": "…"
  },
  "source_refs": []
}
```

### platform_stats

自由结构，但每条保留统计范围（采集到多少、什么时候采集、用什么口径）。不同平台指标不相加。

```json
{"platform": "hackernews", "count": 3, "scope": "本次检索到的独立内容", "measured_at": "…"}
```

## HTML 模板位置

权威模板是 Python 包内的 `repo_learning/templates/report.html`；`render --template <path>` 可覆盖。不要另存副本以免漂移。
