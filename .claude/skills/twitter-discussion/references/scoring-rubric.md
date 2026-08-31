# 筛选与交流评分

Step 2 过滤 + Step 3 评分。目标是只留下「值得交流」的内容。

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
- 有争议观点 / 有反方空间 / 可被追问
- 作者在找答案 / 开放问题
- 一手经验，值得交换

## 值得交流度（Discussion Worthiness）

只用于选 Top 15 值得交流的推文：

```text
Discussion Worthiness =
  Controversy × 25%      （有没有可争辩 / 反方空间）
+ Openness × 25%         （作者是否在找答案 / 开放问题 / 可被追问）
+ Contribution × 25%     （我能贡献什么：经验 / 数据 / 不同判断）
+ First-hand × 15%       （作者是否一手经验，值得交换）
+ Reply-likelihood × 10% （作者回复意愿 / 活跃度）
```

每项 0～10 分，取加权和，降序取 Top 15。维度对应 reply-patterns.md 的 5 类交流对象（A-E）。

## 防质量下降的四条 Rule

### Rule 1 — 宁缺毋滥

不够 15 条达标就如实说「今日只有 N 条达到质量阈值」，不要为了凑数降低标准。

### Rule 2 — 热度 ≠ 值得交流

`Likes ≠ Quality · Views ≠ Insight · Followers ≠ Expertise`。高互动不等于值得交流，判断依据是「能不能产生有价值的双向对话」。

### Rule 3 — 一手经验优先

排序：真实生产经验 > 实验 / Benchmark > 开源项目经验 > 技术分析 > 观点 > 新闻 > 营销。

### Rule 4 — 避免重复打扰

同一推文跨天用 `state/seen_tweets.json` 去重；已经起草 / 发过回复的用 `state/replied.json` 记录，不要反复建议回复同一条。
