# 交流日报模板

Step 5 输出。写入 `state/reports/YYYY-MM-DD.md`（目录不存在则创建），同时打印到终端。

## 固定结构

```markdown
# {主题领域} Twitter Discussion — YYYY-MM-DD

## 今日摘要

今日抓取：XX 条
有效候选：XX 条
Top 15 Discussion：XX 条
已发送：X 条 / 待确认：X 条

---

# 💬 Top 15 Discussion

## 1. xxx
（作者 / 链接 / 为什么值得交流 / 作者的核心观点 / 我可以贡献什么 / 建议回复 —— 用 reply-patterns 里的条目格式）

## 2. xxx
...

---

# ✍️ 待确认回复清单

下面每条都等用户逐条确认后再发（用 `opencli twitter reply <url> <text>`）：

1. 【#1】回复草稿：...
2. 【#3】回复草稿：...
```

## 填写要点

- 若 Top 15 不足 15 条，如实写「今日只有 N 条达到质量阈值」，不要编。
- 每条草稿都写进「待确认回复清单」，等用户点头后再发；发过的记入 `state/replied.json`。
- 同一推文跨天用 `state/seen_tweets.json` 去重，避免反复建议回复同一条。
