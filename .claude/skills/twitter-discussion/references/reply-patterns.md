# 交流对象与回复生成

Step 4 的核心。

> **「值得交流」≠「值得学习」** —— 高价值内容未必值得互动，反之亦然。
> 本 skill 的 Top 15 按「值得交流度」（见 scoring-rubric.md）从全部有效候选里独立选出，依据是「能不能产生有价值的双向对话」，与「值不值得学」正交。

## 优先选择 5 类交流对象

| 类型 | 特征 | 交流方向 |
|------|------|----------|
| A 有争议 | 「Multi-Agent is usually a mistake」 | 追问反例：什么失败让你认定复杂度不值？ |
| B 有观点缺证据 | 结论强、没给数据 | 提验证问题 |
| C 有真实经验 | 一手生产经验 | 分享自己的类似经验 |
| D 有开放问题 | 作者明确在找答案 | 直接给答案 / 资源 |
| E 与自身实践高度相关 | 当前主题的核心子领域（`agent` 预设为 Agent Loop / Evaluation / Harness / FDE） | 带入自己的上下文 |

## Top 15 交流条目格式

```markdown
## 💬 #1 值得交流

作者：
链接：

### 为什么值得交流
...

### 作者的核心观点
...

### 我可以贡献什么
...

### 推荐交流方向
...

### 建议回复
> ...
```

## 回复生成规则

目标不是「获得点赞」，而是**让对方有理由回复你**。

不要：

> "Great insight!" / "Interesting!" / "Totally agree."

应该：观点 + 具体问题 / 自己的经验 / 不同判断 / 延伸问题。

## 四种回复模式

### A 经验交换

```text
We've seen something similar in production.

The interesting part for us was actually X rather than Y.

Curious if you saw the same pattern?
```

### B 追问

```text
Interesting.

How did you distinguish X from Y in your evals?

I've found that these two failure modes often look identical from the final output.
```

### C 补充观点

```text
I agree with the conclusion, but I'd add one layer:

X seems to be a symptom of Y.

This becomes especially visible when Z happens.
```

### D 提出反例

```text
I wonder if this changes when the agent has access to...

We've seen the opposite behavior in that setting.
```

## 语言与发送

- 回复用 **英文**（Twitter/X 语境，作者多为英文圈）。
- 只生成草稿，**逐条等用户确认**后再 `opencli twitter reply <url> <text>` 发出。
