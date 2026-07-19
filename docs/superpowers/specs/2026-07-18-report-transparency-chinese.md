# Report Transparency & Chinese Localization

**Date:** 2026-07-18
**Status:** approved

## Goals

1. Report framework (labels, headers, tables) output in Chinese
2. Every Opportunity shows source attribution: which GitHub accounts and repos support it
3. Every Insight shows source attribution: which accounts and repos feed into it
4. Report includes a pipeline execution summary section

## Non-Goals

- LLM-generated content (summaries, titles, pain points) stays in English
- LLM prompts are NOT changed
- No new external dependencies

## Design

Data is aggregated at its point of production, displayed at the point of consumption. LLM prompts never carry actor/repo metadata.

```
Phase 1: Collect  →  Signal.actor, Signal.target (already present)
Phase 2: aggregator → SignalCluster.actor_breakdown, SignalCluster.top_repos (NEW)
         classifier → Insight.source_cluster_id (NEW)
Phase 3: detector  → Opportunity.source_insights (already present)

Output:  insight.source_cluster_id → cluster → actor_breakdown + top_repos
         (pure ID lookup, no store round-trip)
```

## Changes

### 1. Model Layer (`models/signal.py`)

**SignalCluster** — add 2 fields:
- `actor_breakdown: dict[str, int]` — `{"example_user": 300, "iFurySt": 994}`
- `top_repos: list[str]` — top 5 repo full names by occurrence frequency

**Insight** — add 1 field:
- `source_cluster_id: str` — the SignalCluster.id that generated this insight

### 2. Aggregator (`insight/aggregator.py`)

After clustering signals, compute `actor_breakdown` (count signals per actor) and `top_repos` (extract repo names from `meta.repo` or `target`, rank by frequency, take top 5). Pass both into `SignalCluster()` constructor.

### 3. Classifier (`insight/classifier.py`)

In `classify()`, assign `source_cluster_id = clusters[i].id` for the i-th returned insight. If LLM return count differs from input cluster count, align what matches; leave unmatched as empty string. Prompt is unchanged.

### 4. Pipeline (`pipeline.py`)

`run()` return dict gains a `"clusters"` key so the output layer can do ID-based lookup without hitting the store.

### 5. Output — Markdown (`output/markdown.py`)

Full report restructured with Chinese labels:

```markdown
# BuilderDNA 分析报告
**快照:** `...`
**生成时间:** ...

## 执行摘要
| 阶段 | 输入 | 输出 | 说明 |

## 信号汇总
| 类型 | 数量 | 总权重 |
+ ### 按账号分布 (new sub-table per actor)

## 洞察
Each insight: tags, summary, strength, trend +
**来源账号:** ...  **关键仓库:** ...

## 机会 (SSOT)
Table with 中文 headers: # | 标题 | 需求 | 竞争 | 缺口 | 建议

## 机会详情
Each: pain point, gap score, action +
**关联账号:** ...  **关键仓库:** ...
```

Data linkage: `Opportunity.source_insights[i]` → `Insight.source_cluster_id` → `SignalCluster.actor_breakdown` + `top_repos`. Pure ID lookup, no store query.

### 6. Output — CLI (`output/cli.py`)

Same structural changes with Chinese labels, adapted for Rich terminal formatting. Adds actor/repo attribution display and pipeline execution summary section.

### 7. CLI Entry (`cli.py`)

Ensure `pipeline.run()` result (now containing `clusters`) is passed to render functions. No architectural changes.

## Data Flow (After Changes)

```
GitHub API
    │
    ▼
mapper.py  →  4,675 Signals { actor, target, meta.repo, ... }
    │
    ▼
aggregator.py  →  SignalClusters { actor_breakdown, top_repos, signal_ids }
    │
    ▼
classifier.py (LLM)  →  Insights { source_cluster_id }
    │
    ▼
detector.py (LLM)  →  Opportunities { source_insights }
    │
    ▼
evaluator.py  →  Sorted Opportunities
    │
    ▼
Output Layer:
  insight.source_cluster_id  →  cluster.actor_breakdown  →  来源账号
  insight.source_cluster_id  →  cluster.top_repos        →  关键仓库
```

## Files Modified

| File | Change |
|------|--------|
| `models/signal.py` | SignalCluster +2 fields, Insight +1 field |
| `insight/aggregator.py` | Compute actor_breakdown and top_repos |
| `insight/classifier.py` | Assign source_cluster_id |
| `pipeline.py` | Return `clusters` in result dict |
| `output/markdown.py` | Chinese labels, new sections, source attribution |
| `output/cli.py` | Chinese labels, source attribution, pipeline summary |
| `cli.py` | Pass clusters to render, possible minor wiring |
