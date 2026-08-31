# 个人知识资产

Twitter Research 不该停在日报。把每天的信息沉淀成可复用的个人 {主题领域} 知识库（默认 agent），存于 `state/knowledge.json`（已 gitignore，首次运行时若不存在则创建空结构 `{ "entries": [] }`）。

## 分类 taxonomy

下面是 `agent` 预设的 taxonomy。研究非 agent 主题时二选一：**派生主题专属 taxonomy**（按同样的三层结构拆分当前主题），或直接用**扁平的 `topic` 字段 + 自由 tags**（`topic` 本就是自由字符串，无 schema 限制）。

```text
Agent Engineering
├── Harness / Loop / Graph / Memory / Context
├── Tool / Evaluation / Reliability / Runtime

Agent Solution
├── Discovery / Architecture / Deployment
├── Customer / Workflow / ROI

FDE
├── Problem Discovery / Solution Design / Prototype
├── Deployment / Feedback
```

每条沉淀给一个 `topic`（映射到上述叶子，或当前主题的对应叶子）＋ 1-3 个 `tags`（自由关键词）。

## 演化管线

同一个观点反复出现时，沿管线往上推：

```text
Twitter Observation   （看到一条）
      ↓ 重复出现
Repeated Pattern      （多条指向同一主题）
      ↓ 形成判断
Hypothesis            （我猜 X 是 Y 的原因）
      ↓ 沉淀
Personal Note         （我的理解）
      ↓ 验证
Experiment            （设计实验）
      ↓ 证实
Validated Principle   （可复用的原则）
      ↓ 输出
Long-form Content     （短推文 / 长文 / 分享）
```

每次跑完日报，至少做两件沉淀：

1. 把今日高价值观点按 taxonomy 归类，append 到 `state/knowledge.json`。
2. 检查是否有观点在最近多次出现（`stage` 仍是 observation/pattern 的），决定是否晋升到 hypothesis/note。

## state/knowledge.json 结构

```json
{
  "entries": [
    {
      "id": "slug-or-date-n",
      "date": "YYYY-MM-DD",
      "topic": "Agent Engineering > Evaluation",
      "tags": ["evals", "latency"],
      "stage": "observation | pattern | hypothesis | note | experiment | principle | content",
      "content": "一句话核心认知",
      "source": "tweet 链接或作者",
      "note": "可选，我的判断或待验证的实验"
    }
  ]
}
```

`stage` 是可变的——下次看到同一主题的新证据时，把旧条目往上晋升并更新 `content`。

## 跨天去重

`state/seen_tweets.json` 记录已处理过的推文 id（`{"<tweet-id>": "YYYY-MM-DD"}`），Step 2 去重时读它，Step 5 末尾写回。避免同一推文反复入选。

## 内容输出

每天结束时从知识资产里挑：

- 1 个可写成短推文的观点（已到 note/principle 级）
- 1 个可写成长文的主题（已到 pattern/hypothesis 级且证据足）
- 1 个值得做实验的工程问题（已到 experiment 级）
