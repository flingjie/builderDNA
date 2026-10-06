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
  "id": "google:2026-10-06T16:59:00+00:00:ab12cd34ef56",
  "query": "\"项目名\" launch",
  "engine": "google",
  "searched_at": "2026-10-06T16:59:00+00:00",
  "period": "",
  "results": [{"title": "…", "url": "https://…", "snippet": "…"}],
  "coverage_notes": []
}
```

- `id` 建议形如 `{engine}:{searched_at}:{sha1(query)[:12]}`。
- 搜索引擎不可用时：写一条 `coverage_notes=["engine unavailable: …"]` 且 `results=[]`，不要用仓库搜索冒充全网覆盖。

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

### PromotionContent

```json
{
  "id": "…",
  "source_id": "web_article:…",
  "platform": "hackernews",
  "actor_type": "author",
  "repo_match": "confirmed",
  "content_type": "launch",
  "audience": "…",
  "hook": "…",
  "promise": "…",
  "proof": "…",
  "call_to_action": "…"
}
```

- `platform`：`x` `hackernews` `reddit` `linkedin` `producthunt` `v2ex` `juejin` `zhihu` `wechat` `xiaohongshu` `dev` `medium` `blog` `other`
- `actor_type`：`author` `contributor` `third_party` `user` `unknown`
- `repo_match`：`confirmed` `probable` `rejected`

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
