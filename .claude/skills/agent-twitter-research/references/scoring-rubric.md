# 筛选与评分

Step 2 过滤 + Step 3 评分。目标是只留下「值得学习 / 值得交流 / 值得沉淀」的内容。

## 直接丢弃

- 单纯营销 / 产品广告
- 没有实质信息的 Launch
- 「AI will change everything」式空话
- 没有具体内容的观点
- 纯转发（retweet）
- Engagement bait / Rage bait
- 重复内容
- 明显 AI 生成的低信息密度内容
- 只有一句观点但没有任何解释
- 纯新闻，没有额外洞察

## 优先保留

- 有真实项目经验 / 有数据 / 有代码 / 有架构
- 有失败案例 / 有具体方法 / 有实验 / 有 Benchmark
- 有生产经验 / 有反直觉观点
- 能迁移到其他 Agent 项目 / 能帮助理解 Agent Engineering

## 100 分质量评分

```text
Quality Score =
  Insight × 25%
+ Practicality × 20%
+ Originality × 20%
+ Transferability × 15%
+ Evidence × 10%
+ Discussion Value × 10%
```

每项 0～10 分：

| 维度 | 权重 | 问题 |
|------|------|------|
| Insight | 25% | 是否有新的认知？ |
| Practicality | 20% | 是否可以实际应用？ |
| Originality | 20% | 是否不是已被反复讨论的内容？ |
| Transferability | 15% | 能否迁移到其他 Agent / AI 项目？ |
| Evidence | 10% | 是否有真实案例、数据、代码或实验？ |
| Discussion Value | 10% | 是否容易产生有价值的讨论？ |

取加权和，降序取 Top 10。给每条留一个分数与一句话理由，便于报告里可追溯。

## 防质量下降的四条 Rule

### Rule 1 — 宁缺毋滥

不够 10 条达标就如实说「今日只有 N 条达到质量阈值」，不要为了凑数降低标准。

### Rule 2 — 热度 ≠ 质量

`Likes ≠ Quality · Views ≠ Insight · Followers ≠ Expertise`。不要把「热门」当「高质量」。

### Rule 3 — 一手经验优先

排序：真实生产经验 > 实验 / Benchmark > 开源项目经验 > 技术分析 > 观点 > 新闻 > 营销。

### Rule 4 — 避免信息重复

如果多条都在讲同一件事（如「Agent 很重要」），只保留最有洞察的一条。跨天用 `state/seen_tweets.json` 去重，避免同一推文反复入选。
