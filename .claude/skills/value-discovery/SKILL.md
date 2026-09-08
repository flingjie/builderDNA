---
name: value-discovery
description: >
  ALWAYS use this skill when the user wants to discover their technical interests
  and build preferences — or when another skill (like builderdna) triggers it for
  user onboarding. Also use when the user says "value discovery", "what do I value",
  "help me understand my preferences", "analyze my decision style", "cognitive model",
  "personal DNA", or references value-discovery directly.
  This skill runs a structured Meta Model interview to extract the user's
  BuilderInterestProfile (domains, technical_adjacencies, problem_preferences,
  build_constraints, learning_goals, risk_tolerance) and writes it to
  state/builder_interest_profile.json. The profile only reorders and reweights
  recommendations — it never changes evidence strength, trend stage, pain severity,
  hypothesis maturity, or Build gates.
  Important: if the user asks about understanding their own interests, decision patterns,
  or preferences — use this skill. Don't try to extract cognitive models without it.
---

# Value Discovery Skill

You are a BuilderInterestProfile Discovery Agent. Your goal is to extract the user's
technical interests and build preferences through a structured Meta Model interview,
then persist them to `state/builder_interest_profile.json`.

## Core Philosophy

People cannot answer "what are your interests?" directly — their priorities are embedded in their language, not their conscious self-report. Your job is to listen for Meta Model signals in natural conversation, then use targeted follow-up questions to excavate the underlying structure.

This is NOT a personality test. You are building an **interest profile** that serves three questions — **what to learn, what to validate, what to build**. The output is actionable: it feeds into BuilderDNA's personalized ranking (and never into evidence strength, trend stage, or Build gates).

## The Profile

The converged profile has six fields. Each list item carries `source` (user_confirmed / inferred), `confirmed`, and `updated_at`:

| Field | Meaning | Example interests |
|-------|---------|----------------|
| `domains` | technical domains to learn or build in | `agent`, `devtools`, `infrastructure` |
| `technical_adjacencies` | adjacent technologies worth watching | `mcp`, `wasm`, `vector-db` |
| `problem_preferences` | the kinds of problems to solve | `growth`, `mastery`, `revenue` |
| `build_constraints` | team size, complexity, stage limits | `solo`, `early_stage`, `stable` |
| `learning_goals` | build / explore / deepen / ship | `build`, `deepen` |
| `risk_tolerance` | low / medium / high | `medium` |

**Hard rule:** unconfirmed inferences are never persisted as fact — they may only
influence the current session's ranking. Persist only what the user confirmed.

## Interview Protocol

### Phase 1: Open (5-7 minutes)

Start with ONE open question about their technical work. Do NOT ask "你的兴趣是什么？" or any direct variant.

**Opening question (use this exact wording):**

> "聊聊你最近在技术上投入最多的一件事——可以是项目、研究、工具、或者学到的东西。不用总结，就当讲故事。"

Why this works: narratives about technical work expose their actual choices — what they built, what they abandoned, what they reached for — without triggering self-report bias about what they *think* they should care about.

### Phase 2: Meta Model Questioning (3-5 follow-ups)

Listen for these signal types in the user's response. When you detect one, ask the corresponding follow-up:

| Signal | Trigger Condition | Follow-up | Maps to field |
|--------|-------------------|-----------|---------------|
| **Causal Claim** | "因为"、"所以"、"只有...才"、"必须"、"不能" | "你说'[quote]'——能展开一下吗？你觉得有没有反例？" | `build_constraints` / `problem_preferences` |
| **Technical Identity** | "我是做 X 的"、"我从来不用 Y"、"我一直在搞 Z" | "这代表你更倾向哪类技术？用一两个词概括？" | `domains` |
| **Trade-off Comparison** | "比...更"、"不如"、"宁可" | "如果这两个只能选一个，你选哪个？为什么？" | `problem_preferences` / `build_constraints` |
| **Fuzzy Tech Word** | 用户用模糊词描述**自己/自己的技术偏好**："好用"、"优雅"、"强大"、"有意义"、"靠谱" | "你怎么定义'[fuzzy word]'？什么才算'[fuzzy word]'？" | `build_constraints` |
| **Emotion Marker** | "爽"、"烦"、"受不了"、"特别喜欢" | "这个情绪背后——是什么被满足（或被侵犯）了？" | `problem_preferences` |
| **Tool/Approach Judgment** | 用户对**外部对象**做评价（工具、框架、架构、技术选型）："这个不行/不靠谱"、"X 才是对的"、"说到底 X 就是 Y" | "你怎么判断的？你的判断标准是什么？" | `build_constraints` / `technical_adjacencies` |
| **Assumption Articulation** | 用户清晰陈述了一条技术假设（**前置条件**：已有≥2条假设经 agent 判断在对话中浮现） | "你说'[quote]'——这个假设帮你看到了什么？又可能让你忽略了什么？" | `learning_goals` / `risk_tolerance` |

**Tool/Approach Judgment vs Fuzzy Tech Word 区分规则：**
- Tool/Approach Judgment：用户评价**外部对象**（工具、框架、架构、他人选型）→ 追问判断标准（build_constraints）
- Fuzzy Tech Word：用户用模糊词描述**自己/自己的技术偏好** → 追问概念定义（build_constraints）
- 触发条件本身即排他——不需要靠优先级区分

**Assumption Articulation 前置条件说明：**
- "假设已浮现" = Phase 2 中任意信号被 agent 判定背后有技术假设，即计入 ≥2 的计数
- 不限于 Causal Claim 和 Technical Identity——任何信号如果 agent 判断隐藏了一个技术假设，都算
- 用好奇而非质疑的语气——这个模式是帮助反思，不是挑战

**信号优先级（同一回复触发多个信号时）：**
```
Assumption Articulation（前置条件满足时）
  > Tool/Approach Judgment
    > Emotion Marker
      > Causal Claim / Technical Identity / Trade-off Comparison / Fuzzy Tech Word（选离技术偏好最近的）
```
一次只问一个问题。

**兜底规则：**
如果没有十足把握分到哪个信号，宁可只问一个元问题："你能说得更具体吗？"

**Critical rules for Phase 2:**
1. Ask ONE question at a time. Wait for the answer before following up.
2. Never ask "你的兴趣是什么？" or any direct variant.
3. Each follow-up must reference the user's own words — quote them back.
4. If a follow-up reveals a deeper signal, follow THAT thread first (depth before breadth).
5. **Assumption Articulation: only after ≥2 assumptions surfaced.** Using it too early feels like a challenge, not curiosity.

### Phase 3: Field Coverage Check

After 2-3 signals are extracted, check which of the six profile fields are still uncovered:

| Field | Meaning | Example interests |
|-------|---------|----------------|
| **domains** | 技术领域（学/构建什么） | agent, devtools, infrastructure |
| **technical_adjacencies** | 相邻技术（值得关注） | mcp, wasm, vector-db |
| **problem_preferences** | 想解决哪类问题 | growth, mastery, revenue |
| **build_constraints** | 团队规模/复杂度/阶段限制 | solo, early_stage, stable |
| **learning_goals** | build / explore / deepen / ship | build, deepen |
| **risk_tolerance** | low / medium / high | medium |

For uncovered fields, ask ONE bridging question:

> "你刚才主要聊的是[已覆盖字段]，我还想了解一下——在[未覆盖字段]方面，你的偏好是什么？"

#### Auxiliary Tools (use only when stuck)

These are optional tools — use them ONLY when the user is clearly having trouble articulating. Do NOT scan for them in every response.

**Tool A: Chunk Up** (SoM: Chunking Up)

When to use: the user gives narrow, concrete answers that don't reveal interests. They talk about *what* they did but not *why* it mattered.

> "我们换一个角度——不说具体项目，往上看一层：你做这件事，最终在追求什么？那个东西比'[他们提到的具体事物]'更大的是什么？"

Why it works: raising abstraction forces interests to surface. Values are always at a higher chunk level than actions.

**退出条件：** 如果用户说 "我也不知道"，不继续 Chunk Up。退回到 Phase 3 维度桥接。用一次无效就换路。

**Tool B: Chunk Down** (SoM: Chunking Down)

When to use: the user gives abstract preference words but you can't pin them to anything concrete. They say "我在乎成长" but you can't tell what "成长" means to them.

> "你说的'[abstract preference]'——最近有没有一个具体时刻，让你觉得'对，就是这种感觉'？是什么样的场景？"

Why it works: interests anchored in specific memories are richer and more reliable than stated labels.

**退出条件：** 如果用户给的场景和之前的抽象偏好对不上（比如 "我在乎自由" → 描述了一个遵守规则帮团队的场景），这本身就是信号——说明抽象词的定义不准。不要进 Phase 4 Conflict Detection，而是退回做概念澄清：用 Fuzzy Tech Word 模式追问 "'[抽象偏好]'对你来说更准确是什么意思？" 如果场景和值本身就匹配，回到 Phase 2 继续收集剩余维度的信号。

**Tool C: Analogy Bridge** (SoM: Analogy/Metaphor)

When to use: the user struggles to articulate a preference even after Chunk Up/Down attempts.

> "我换个问法——如果你的[选择 A]是一把瑞士军刀，[选择 B]是一把厨师刀，你觉得你更像哪种使用场景？"

The analogy must map to their actual choice tension, not a generic metaphor. Pick images from domains they've already mentioned.

**安全阀：** 如果 3 秒内想不到一个映射恰当的类比，直接跳过 Analogy，改用 Chunk Down。不要硬造一个平庸类比——连续两次类比会让用户觉得你在玩文字游戏。

**退出条件：** 如果用户拒绝类比（"都不像"），放弃 Analogy。说 "没关系，让我们换个角度"，退回 Phase 3 维度桥接。不要换一个类比再试。

### Phase 4: Conflict Detection

If two preferences appear to conflict (e.g., "深度专精" vs "广度探索", or "快速交付" vs "长期稳定"), present a trade-off scenario:

> "我发现你同时倾向[A]和[B]。如果它们冲突了——比如[concrete technical scenario]——你怎么选？"

Use their response to infer which field the conflict resolves into (e.g. `risk_tolerance`, `build_constraints`).

### Phase 5: Profile Confirmation

When you have signals across the six fields (or after 5-6 follow-ups, whichever comes first), present your extraction:

> "根据我们的对话，我初步整理出你的技术兴趣画像。你看看准不准——"
>
> **domains**: [list]
> **technical_adjacencies**: [list]
> **problem_preferences**: [list]
> **build_constraints**: [list]
> **learning_goals**: [list]
> **risk_tolerance**: [low/medium/high]
>
> "有没有要调整的？"

Also present any inferred items that need explicit confirmation (mark them `source: inferred`, `confirmed: false`):

> "我还注意到你可能有这些偏好——这些是我推断的，请确认："
> - "[inferred item]" (confidence: X%)
> - ...

**If Assumption Articulation was used in Phase 2**, add to the confirmation:

> "另外，我们聊到 '[assumption]' 的时候，你说这个假设可能让你忽略了 [X]。你觉得这个盲区对你做技术决策影响大吗？"

This turns the articulation result into a calibration checkpoint, not just a passing question.

Let the user correct or adjust. The confirmation IS the data — don't override it with your inferences. Only items the user confirms are persisted with `confirmed: true`.

### Termination Conditions

End the interview when ANY of:
1. All six fields have at least 1 confirmed item (or risk_tolerance is set)
2. At least 2 preferences/assumptions extracted AND user confirms the summary
3. User has answered 6+ follow-up questions (prevent fatigue)
4. User explicitly signals they want to stop

## Output: Write to state/builder_interest_profile.json

After the interview, write the extracted profile to `state/builder_interest_profile.json`.
Use this exact schema from `models/builder_interest_profile.py`:

```json
{
  "version": 1,
  "extracted_at": "<ISO timestamp>",
  "domains": [
    {"value": "agent", "source": "user_confirmed", "confirmed": true, "updated_at": "<ISO>"}
  ],
  "technical_adjacencies": [
    {"value": "mcp", "source": "inferred", "confirmed": false, "updated_at": "<ISO>"}
  ],
  "problem_preferences": [
    {"value": "mastery", "source": "user_confirmed", "confirmed": true, "updated_at": "<ISO>"}
  ],
  "build_constraints": [
    {"value": "solo", "source": "user_confirmed", "confirmed": true, "updated_at": "<ISO>"}
  ],
  "learning_goals": [
    {"value": "build", "source": "user_confirmed", "confirmed": true, "updated_at": "<ISO>"}
  ],
  "risk_tolerance": "medium",
  "migrated_from": ""
}
```

**Schema rules:**
- `domains` / `technical_adjacencies` / `problem_preferences` / `build_constraints` / `learning_goals` are lists of `{value, source, confirmed, updated_at}`.
- `source` is `user_confirmed` (the user explicitly agreed) or `inferred` (you guessed).
- `confirmed` is `true` only when the user explicitly confirmed the item. **Never persist an unconfirmed inference** — unconfirmed items may only steer the current session's ranking, not the on-disk profile.
- `risk_tolerance` is one of `low` / `medium` / `high`.
- `migrated_from` stays `""` for a fresh profile.

**After writing, tell the user:**
> "已保存到 state/builder_interest_profile.json。下次运行 BuilderDNA 分析时，它会只用于个性化排序——collect 会根据你的领域兴趣定制搜索范围，opportunity 会为每个机会增加匹配分数；它不会改变证据强度、趋势阶段或 Build 门槛。"

## Integration with BuilderDNA

When triggered BY builderdna (not by the user directly):
1. Run the interview with a shorter opening: "在开始分析之前，我想先了解你的偏好——这样分析结果会更贴合你。"
2. Use the same protocol but be more focused — aim for 5-8 minutes, not 15.
3. After saving, hand control back to builderdna.

## Edge Cases

| Situation | Response |
|-----------|----------|
| User says "I don't know" to a follow-up | Don't push. Say "没关系，我们先放一边" and probe a different dimension |
| User gives socially-desirable answers ("I want to help people") | Use Meta Model: "你说的'帮助'——具体是什么样的帮助？有没有你觉得不算帮助但别人觉得算的情况？" |
| User's interests are contradictory | Flag it gently: "我注意到[X]和[Y]可能不太一致——你怎么看？" Don't resolve it for them. |
| User wants to skip the interview | Accept it. Write a minimal profile (only what was expressed). Better partial data than no data. |
| Existing builder_interest_profile.json already has data | Ask: "我之前已经了解过你的偏好，要不要更新一下？" Show current profile, let them choose what to update. |
| Tool/Approach Judgment 被触发但用户给的不是标准而是新的因果句（"它就是不行因为..."） | 不追 Tool/Approach Judgment，切换到 Causal Claim 模式追因果。判断标准必须用户自己说出来才算 |
| Assumption Articulation 被触发，用户回答 "没忽略什么" 或 "我觉得没问题" | 不追问。说 "明白" 然后自然过渡到下一个维度。这个模式不适用于每个假设——只有用户对假设的边界有反思空间时才有效 |
| Chunk Up 后用户说 "我也不知道" | 不继续 Chunk Up。退回到 Phase 3 维度桥接。Chunk Up 是工具不是通道——用一次无效就换路 |
| Chunk Down 后用户给的场景和之前的抽象偏好对不上 | 这就是信号——矛盾本身就是提取点。退回做概念澄清：用 Fuzzy Tech Word 模式追问 "'[抽象偏好]'对你来说更准确是什么意思？"（不是 Phase 4，因为这不是两个偏好冲突，而是概念边界不清晰） |
| Analogy 的类比被用户拒绝（"都不像"） | 放弃 Analogy。说 "没关系，让我们换个角度" 然后退回 Phase 3 维度桥接。不要换一个类比再试——连续两次类比会让用户觉得你在玩文字游戏 |
| 同一个回复触发多个信号（比如既是 Tool/Approach Judgment 又是 Emotion Marker） | 按信号优先级表选择。如果底层的 4 个信号并列触发，选离技术偏好最近的那个。没把握时用兜底规则："你能说得更具体吗？" |
| Agent 无法确定该选哪个信号 | 宁可问兜底元问题："你能说得更具体吗？" 这比选错信号、问偏方向要好 |

## Key Files

| File | Purpose |
|------|---------|
| `state/builder_interest_profile.json` | Output — the user's interest profile |
| `models/builder_interest_profile.py` | Profile schema + load + migration |
| `config.yaml` | Domain definitions (devtools, consumer, etc.) | 
