# Value-Discovery Sleight of Mouth Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade value-discovery skill's Phase 2 from 5 to 7 core signals, add 3 auxiliary tools to Phase 3, and integrate 7 grilling resolutions into the protocol.

**Architecture:** Single-file edit to `.claude/skills/value-discovery/skill.md`. No schema changes, no test changes. Eight edit sites across the file, executed in dependency order (top-to-bottom).

**Tech Stack:** Markdown file edit. No code.

## Global Constraints

- Only file changed: `.claude/skills/value-discovery/skill.md`
- No changes to `models/user_dna_schema.py`, `state/user_dna.json`, or any Python code
- No test changes needed (skill is Claude-orchestrated, not Python)
- Skill must remain valid YAML frontmatter + valid Markdown
- All Chinese text in the skill must stay in Chinese (protocol language)

---

### Task 1: Fix Goal quantifier + add Judgment Claim / Belief Articulation signals + refine Vague Word + add priority & fallback rules

**Files:**
- Modify: `.claude/skills/value-discovery/skill.md` (Goal line, Phase 2 signal table, Critical rules)

**What this does:** Replaces the Phase 2 section with the upgraded 7-signal version, including:
1. Correct "7 core + 3 auxiliary" in the Goal statement (was "7 core + 2 auxiliary" in spec — never written to file yet, but the spec doc says it). Actually: checking the spec... the spec Goal line says "7 core + 2 auxiliary" which was the grilling catch. The skill.md doesn't have this line yet — it still says 5 signals. So this task writes the correct version directly.
2. 7-signal table with refined trigger conditions (Judgment Claim → external objects; Vague Word → self-description)
3. Signal priority rule block
4. Fallback rule ("没把握时问'你能说得更具体吗？'")

- [ ] **Step 1: Read the current Phase 2 section to confirm edit boundaries**

Read `.claude/skills/value-discovery/skill.md` lines 47-60 (Phase 2 header, signal table, and Critical rules). Note exact `old_string` boundaries for the Edit.

- [ ] **Step 2: Replace Phase 2 signal table and critical rules**

Use Edit to replace the block from `### Phase 2: Meta Model Questioning (3-5 follow-ups)` through the Critical rules list (ending before `### Phase 3: Dimension Coverage Check`) with:

```markdown
### Phase 2: Meta Model Questioning (3-5 follow-ups)

Listen for these signal types in the user's response. When you detect one, ask the corresponding follow-up:

| Signal | Trigger Condition | Follow-up |
|--------|-------------------|-----------|
| **Causal Belief** | "因为"、"所以"、"只有...才"、"必须"、"应该"、"不能" | "你说'[quote belief]'——能展开一下吗？你觉得有没有反例？" |
| **Identity Statement** | "我是/不是...的人"、"我一直..."、"我从来不..." | "这代表你更看重什么？如果用一两个词概括？" |
| **Comparison** | "比...更"、"不如"、"宁可" | "如果这两个只能选一个，你选哪个？为什么？" |
| **Vague Word** | 用户用模糊词描述**自己/自己的价值/偏好**："有价值"、"好的"、"有意义"、"重要的" | "你怎么定义'[fuzzy word]'？什么才算'[fuzzy word]'？" |
| **Emotion Marker** | "爽"、"烦"、"受不了"、"特别喜欢" | "这个情绪背后——是什么被满足（或被侵犯）了？" |
| **Judgment Claim** | 用户对**外部对象**做评价（项目、工具、决策、他人选择）："这个没/不行/不靠谱"、"X才是/不算..."、"说到底X就是Y" | "你怎么判断的？你的判断标准是什么？" |
| **Belief Articulation** | 用户清晰陈述了一条信念（**前置条件**：已有≥2条信念经agent判断在对话中浮现） | "你说'[quote belief]'——这个信念本身，帮你看到了什么？又可能让你忽略了什么？" |

**Judgment Claim vs Vague Word 区分规则：**
- Judgment Claim：用户评价**外部对象**（项目、工具、决策、他人选择）→ 追问判断标准（criteria）
- Vague Word：用户用模糊词描述**自己/自己的价值/偏好** → 追问概念定义（belief）
- 触发条件本身即排他——不需要靠优先级区分

**Belief Articulation 前置条件说明：**
- "信念已浮现" = Phase 2 中任意信号被 agent 判定背后有信念，即计入 ≥2 的计数
- 不限于 Causal Belief 和 Identity Statement——任何信号如果 agent 判断隐藏了一个信念，都算
- 用好奇而非质疑的语气——这个模式是帮助反思，不是挑战

**信号优先级（同一回复触发多个信号时）：**
```
Belief Articulation（前置条件满足时）
  > Judgment Claim
    > Emotion Marker
      > Causal Belief / Identity / Comparison / Vague Word（选离价值观最近的）
```
一次只问一个问题。

**兜底规则：**
如果没有十足把握分到哪个信号，宁可只问一个元问题："你能说得更具体吗？"

**Critical rules for Phase 2:**
1. Ask ONE question at a time. Wait for the answer before following up.
2. Never ask "你的价值观是什么？" or any direct variant.
3. Each follow-up must reference the user's own words — quote them back.
4. If a follow-up reveals a deeper signal, follow THAT thread first (depth before breadth).
5. **Belief Articulation: only after ≥2 beliefs surfaced.** Using it too early feels like a challenge, not curiosity.
```

- [ ] **Step 3: Verify the edit**

Read the file to confirm the block was replaced. Check that Phase 3 header (`### Phase 3: Dimension Coverage Check`) follows immediately after.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/value-discovery/skill.md
git commit -m "feat(value-discovery): upgrade Phase 2 to 7 core signals with SoM patterns"
```

---

### Task 2: Append auxiliary tools block to Phase 3

**Files:**
- Modify: `.claude/skills/value-discovery/skill.md` (Phase 3 section, after the bridging question)

**What this does:** Adds 3 optional auxiliary tools (Chunk Up, Chunk Down, Analogy Bridge) to Phase 3, each with explicit trigger conditions and exit rules.

- [ ] **Step 1: Read Phase 3 to confirm insertion point**

Read `.claude/skills/value-discovery/skill.md` to find the end of Phase 3 (the bridging question paragraph), before Phase 4 header.

- [ ] **Step 2: Append auxiliary tools block after the bridging question**

Use Edit to insert after the bridging question line (`> "你刚才主要聊的是[已覆盖维度]...` paragraph) and before `### Phase 4: Conflict Detection`:

```markdown

#### Auxiliary Tools (use only when stuck)

These are optional tools — use them ONLY when the user is clearly having trouble articulating. Do NOT scan for them in every response.

**Tool A: Chunk Up** (SoM: Chunking Up)

When to use: the user gives narrow, concrete answers that don't reveal values. They talk about *what* they did but not *why* it mattered.

> "我们换一个角度——不说具体项目，往上看一层：你做这件事，最终在追求什么？那个东西比'[他们提到的具体事物]'更大的是什么？"

Why it works: raising abstraction forces values to surface. Values are always at a higher chunk level than actions.

**退出条件：** 如果用户说 "我也不知道"，不继续 Chunk Up。退回到 Phase 3 维度桥接。用一次无效就换路。

**Tool B: Chunk Down** (SoM: Chunking Down)

When to use: the user gives abstract value words but you can't pin them to anything concrete. They say "我在乎成长" but you can't tell what "成长" means to them.

> "你说的'[abstract value]'——最近有没有一个具体时刻，让你觉得'对，就是这种感觉'？是什么样的场景？"

Why it works: values anchored in specific memories are richer and more reliable than stated labels.

**退出条件：** 如果用户给的场景和之前的抽象值对不上（比如 "我在乎自由" → 描述了一个遵守规则帮团队的场景），这本身就是信号——说明抽象词的定义不准。不要进 Phase 4 Conflict Detection，而是退回做概念澄清：用 Vague Word 模式追问 "'[抽象值]'对你来说更准确是什么意思？" 如果场景和值本身就匹配，正常继续。

**Tool C: Analogy Bridge** (SoM: Analogy/Metaphor)

When to use: the user struggles to articulate a preference even after Chunk Up/Down attempts.

> "我换个问法——如果你的[选择 A]是一把瑞士军刀，[选择 B]是一把厨师刀，你觉得你更像哪种使用场景？"

The analogy must map to their actual choice tension, not a generic metaphor. Pick images from domains they've already mentioned.

**安全阀：** 如果 3 秒内想不到一个映射恰当的类比，直接跳过 Analogy，改用 Chunk Down。不要硬造一个平庸类比——连续两次类比会让用户觉得你在玩文字游戏。

**退出条件：** 如果用户拒绝类比（"都不像"），放弃 Analogy。说 "没关系，让我们换个角度"，退回 Phase 3 维度桥接。不要换一个类比再试。
```

- [ ] **Step 3: Verify the edit**

Read the Phase 3-4 boundary to confirm auxiliary tools block sits between the bridging question and Phase 4 header.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/value-discovery/skill.md
git commit -m "feat(value-discovery): add 3 auxiliary tools to Phase 3 (Chunk Up/Down, Analogy)"
```

---

### Task 3: Append Belief Articulation calibration line to Phase 5

**Files:**
- Modify: `.claude/skills/value-discovery/skill.md` (Phase 5 section, after belief presentation block)

**What this does:** Adds one optional calibration checkpoint when Belief Articulation was used in Phase 2.

- [ ] **Step 1: Read Phase 5 to find the belief presentation block**

Read `.claude/skills/value-discovery/skill.md` Phase 5 section, locate where beliefs are presented to the user (after the ranking confirmation block).

- [ ] **Step 2: Insert calibration checkpoint after the belief presentation**

Use Edit to insert after the belief presentation paragraph (after `> - "[belief statement]" (confidence: X%)` block) and before `Let the user correct or adjust...`:

```markdown

**If Belief Articulation was used in Phase 2**, add to the belief presentation:

> "另外，我们聊到 '[belief]' 的时候，你说这个信念可能让你忽略了 [X]。你觉得这个盲区对你做决策影响大吗？"

This turns the articulation result into a calibration checkpoint, not just a passing question.
```

- [ ] **Step 3: Verify the edit**

Read the Phase 5 section to confirm the calibration line sits correctly.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/value-discovery/skill.md
git commit -m "feat(value-discovery): add Belief Articulation calibration to Phase 5"
```

---

### Task 4: Append 6 new edge cases

**Files:**
- Modify: `.claude/skills/value-discovery/skill.md` (Edge Cases table)

**What this does:** Appends 6 entries to the existing Edge Cases table.

- [ ] **Step 1: Read the Edge Cases table to find the last row**

Read `.claude/skills/value-discovery/skill.md` Edge Cases section, note the last row of the table.

- [ ] **Step 2: Append 6 rows to the table**

Use Edit to append after the last row (`| Existing user_dna.json already has data | ... |`) and before `## Key Files`:

```markdown
| Judgment Claim 被触发但用户给的不是标准而是新的因果句（"它就是不行因为..."） | 不追 Judgment Claim，切换到 Causal Belief 模式追因果。判断标准必须用户自己说出来才算 |
| Belief Articulation 被触发，用户回答 "没忽略什么" 或 "我觉得没问题" | 不追问。说 "明白" 然后自然过渡到下一个维度。这个模式不适用于每个信念——只有用户对信念的边界有反思空间时才有效 |
| Chunk Up 后用户说 "我也不知道" | 不继续 Chunk Up。退回到 Phase 3 维度桥接。Chunk Up 是工具不是通道——用一次无效就换路 |
| Chunk Down 后用户给的场景和之前的抽象值对不上 | 这就是信号——矛盾本身就是提取点。退回做概念澄清：用 Vague Word 模式追问 "'[抽象值]'对你来说更准确是什么意思？"（不是 Phase 4，因为这不是两个价值冲突，而是概念边界不清晰） |
| Analogy 的类比被用户拒绝（"都不像"） | 放弃 Analogy。说 "没关系，让我们换个角度" 然后退回 Phase 3 维度桥接。不要换一个类比再试——连续两次类比会让用户觉得你在玩文字游戏 |
| 同一个回复触发多个信号（比如既是 Judgment Claim 又是 Emotion Marker） | 按信号优先级表选择。如果底层的 4 个信号并列触发，选离价值观最近的那个。没把握时用兜底规则："你能说得更具体吗？" |
| Agent 无法确定该选哪个信号 | 宁可问兜底元问题："你能说得更具体吗？" 这比选错信号、问偏方向要好 |
```

- [ ] **Step 3: Verify the edit**

Read the Edge Cases table to confirm all 7 new rows (6 from design + 1 grilling catch) are present and the old rows are intact.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/value-discovery/skill.md
git commit -m "feat(value-discovery): add 7 edge cases for new signals and auxiliary tools"
```

---

### Task 5: Final review — verify all grilling resolutions are covered

**Files:**
- Read: `.claude/skills/value-discovery/skill.md`

**What this does:** Checks the final file against all 7 grilling resolutions to ensure nothing was missed.

- [ ] **Step 1: Read the entire skill.md**

```bash
cat .claude/skills/value-discovery/skill.md
```

- [ ] **Step 2: Verify each grilling resolution is present**

| # | Resolution | Where it should appear | Verify |
|---|-----------|----------------------|--------|
| 1 | 3 auxiliary tools count correct | Phase 3 header | "3 auxiliary tools" or "3 辅助工具" appears |
| 2 | Belief surfaced = any signal agent judges | Phase 2 belief articulation precondition | "任意信号" or equivalent |
| 3 | Bottom 4 signals → pick closest to values | Signal priority block | "离价值观最近的" appears |
| 4 | Chunk Down contradiction → concept clarification, not Phase 4 | Auxiliary Tool B exit + Edge Case | "不进入 Phase 4" or equivalent in both places |
| 5 | Analogy 3-second safety valve | Auxiliary Tool C | "3 秒" appears |
| 6 | Judgment Claim vs Vague Word trigger distinction | Phase 2 signal table + 区分规则 block | "外部对象" vs "自己" distinction |
| 7 | Fallback rule | Phase 2 bottom + Edge Case bottom | "你能说得更具体吗" appears in both places |

- [ ] **Step 3: Fix any gaps found in the checklist**

If any resolution is missing or incomplete, edit the skill.md with the correction and re-verify.

- [ ] **Step 4: Final commit**

```bash
git add .claude/skills/value-discovery/skill.md
git commit -m "chore(value-discovery): final review — verify all grilling resolutions"
```
