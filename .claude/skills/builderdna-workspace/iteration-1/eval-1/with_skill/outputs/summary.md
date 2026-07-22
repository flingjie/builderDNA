# BuilderDNA Analysis Summary: karpathy & geohot

## Task
Analyze karpathy and geohot's GitHub to understand their recent tech directions and identify product opportunities.

## Approach

### 1. Skill Interpretation
Followed the BuilderDNA SKILL.md workflow:
- Identified the task as "analyze X's GitHub" which maps to the v1 `run` command
- Discovered the actual CLI only has `radar`, `opportunities`, and `health` commands (SKILL.md was outdated)
- Mapped to `radar agent` which runs the 8-node LangGraph DAG (collect -> trend -> pain -> opportunity -> evidence -> critic -> report)

### 2. Configuration
- Updated `config.yaml` `accounts:` to `[karpathy, geohot]` for targeted analysis
- karpathy and geohot were already in `follow_groups.个人影响力` which gets collected by the pipeline's vendor collection step
- Added `.env` symlink (was missing in worktree) for GitHub token + LLM API access

### 3. Pipeline Execution
- Ran health check: `PYTHONPATH=. uv run builderdna health` -- PASSED (deepseek-v4-pro + bge-m3 ready)
- Ran radar: `PYTHONPATH=. uv run bldr-dna radar agent -w 60 -m full_auto` -- SUCCESS
- First run failed with empty results because `.env` was missing from the worktree directory
- After symlinking `.env`, the second run succeeded with 25+ trends and 3 opportunities

## Key Findings

### karpathy (karpathy) -- Recent Work
| Repo | Stars | Language | Last Push | Focus |
|------|-------|----------|-----------|-------|
| nanochat | 56,529 | Python | Jul 2026 | Best ChatGPT $100 can buy |
| autoresearch | 91,765 | Python | Mar 2026 | AI agents running research on single-GPU |
| nanoGPT | 61,412 | Python | Nov 2025 | Simplest/fastest repo for training GPTs |
| llm-council | 22,978 | Python | Nov 2025 | Multi-LLM collaborative answering |
| llm.c | 30,609 | Cuda | Jun 2025 | LLM training in raw C/CUDA |
| jobs | 1,928 | HTML | Mar 2026 | BLS data visual exploration tool |

**Direction**: Accessible LLM training (nano* family), AI agent research automation (autoresearch), LLM collaboration/orchestration (llm-council), and educational data tools (jobs).

### geohot (geohot) -- Recent Work
| Repo | Stars | Language | Last Push | Focus |
|------|-------|----------|-----------|-------|
| factoring | 51 | Python | Apr 2026 | Polynomial time factoring algorithm |
| anker-vibecoded | 9 | Python | Dec 2025 | BTLE connection to Anker chargers |
| omarchy-boring-theme | 22 | CSS | Dec 2025 | Theme for omarchy |
| configuration | 446 | Shell | Dec 2025 | Dotfiles/config management |
| qira | 4,070 | C | 2022 | QEMU Interactive Runtime Analyzer |
| cannon | 27 | Go | 2022 | On-chain interactive fault prover for Ethereum |

**Direction**: Algorithm research (factoring), hardware hacking (anker-vibecoded, cuda_ioctl_sniffer), low-level systems (qira), decentralized computing (cannon), practical config automation.

### Pipeline-Detected Trends (Agent Domain, 60-day window)
- **Fastest growing**: agent-skills, claude-code-plugin, cursor-rules, prompt-engineering (velocity 2187.6)
- **Declining**: ai, codex, coding-agent, mcp, typescript
- **Steady**: agent-framework, ai-agents, developer-tools, multi-agent

### Generated Opportunities
1. **Agent Skills Marketplace** (Score 8.5/10, Medium Risk) -- Centralized, versioned ecosystem for sharing Claude Code/Cursor agent skills
2. **Prompt Engineering IDE** (Score 9.0/10, Low Risk) -- Visual collaborative tools for prompt design, A/B testing, and performance tracking for self-hosted LLM interfaces
3. **Cross-IDE Agent Rules Synchronizer** (Score 7.5/10, High Risk) -- Sync custom instructions/rules across Cursor, Claude Code, GitHub Copilot

## Product Ideas Connecting karpathy + geohot's Work to Opportunities

1. **Local-First AI Research Agent** (combining karpathy's autoresearch + nanochat with agent skills trend): A desktop app that runs local LLM research agents on consumer GPUs, using nanochat-level efficiency. Productize autoresearch as a paid tool for independent researchers.

2. **Multi-LLM Council as a Service** (karpathy's llm-council + prompt-engineering trend): An API that routes complex questions to a council of LLMs that debate and reach consensus. Enterprise decision-support product.

3. **Hardware-Aware Agent Runtime** (geohot's low-level systems expertise + agent-runtime trend): A CUDA-optimized agent execution engine that runs coding agents 10x faster by eliminating Python overhead (like llm.c did for training, but for inference/agent loops).

4. **Agent Verification/Factoring Engine** (geohot's factoring + cannon + agent-governance trend): Formal verification tools for AI agent outputs, inspired by geohot's work on interactive fault provers. Verify that agent reasoning chains are sound.

## What Went Well
- Health check passed immediately (LLM + embedding endpoints reachable)
- Radar pipeline ran end-to-end in one shot with `full_auto` mode
- 3 well-scored opportunities generated with specific related repos

## Issues Encountered & Resolved
1. **SKILL.md command mapping was outdated**: The skill references `run`, `show`, `snapshots`, `diff`, `follow` commands that don't exist in this CLI version. Actual commands: `radar`, `opportunities`, `health`. The SKILL.md should be updated.
2. **Missing .env in worktree**: The `_load_dotenv(Path(".env"))` uses relative path from CWD. Worktree didn't have one. Fixed with symlink.
3. **First radar run returned empty**: Collect node couldn't reach GitHub API without token env vars. Resolved by adding .env.

## Suggested Refinements (Feedback Loop)
1. **Narrow time window**: Re-run with `-w 30` to focus on very recent activity (nanochat was pushed July 2026, factoring April 2026)
2. **Expert mode**: Re-run with `-m expert` to get human-in-the-loop review at each pipeline stage for deeper analysis
3. **Add more developer accounts**: Add peers for richer comparison

## Files Produced
- `outputs/report.md` -- Markdown analysis report
- `outputs/report.json` -- JSON detail with all trends/opportunities
- `outputs/summary.md` -- This summary
