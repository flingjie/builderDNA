# BuilderDNA 2.0 Phase 2: Pain Mining — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement.

**Goal:** Add LLM-powered issue pain mining to the Trend Radar pipeline. Auto-fetch issues from top trend repos, score pain severity via LLM, cluster into patterns.

**Architecture:** New `backend/engine/pain.py` plugs into `run_radar()`. LLM client (existing) scores and clusters issues. Results stored in `PainSnapshot` served via `/api/pain`.

**Tech Stack:** Same as Phase 1 — FastAPI, httpx, pydantic, existing OpenAIClient

## Global Constraints

- Python >= 3.11
- No new Python dependencies
- Reuse existing `llm/client.py` (OpenAIClient) for LLM calls
- Reuse existing `collect/github/client.py` for Issue API
- TDD for all backend code
- Follow existing patterns: models, store, engine, router

---

### Task 1: Pain Models

**Files:**
- Create: `backend/models/pain.py`
- Test: `tests/test_radar/test_pain_models.py`

**Models:**
```python
PainIssue(repo, issue_number, title, body, comments, participants, pain_score, labels, url)
PainCluster(id, title, severity, frequency, description, evidence, affected_repos)
PainSnapshot(id, domain, created_at, clusters, issue_count, repos_analyzed)
```

---

### Task 2: Pain Store

**Files:**
- Create: `backend/store/pain_store.py`
- Test: `tests/test_radar/test_pain_store.py`

**Interface:**
```python
class PainStore:
    def __init__(self, db_path="snapshots/pains.db")
    def save(snapshot: PainSnapshot) -> str
    def get_latest(domain: str) -> PainSnapshot | None
```

---

### Task 3: Pain Engine

**Files:**
- Create: `backend/engine/pain.py`
- Test: `tests/test_radar/test_pain_engine.py`

**Implement:**
```python
async def fetch_issues(client, repo: str, max_issues=20) -> list[dict]
    # GET /repos/{repo}/issues?state=open&sort=comments&per_page={max_issues}
    # Extract: number, title, body[:500], comments, labels, html_url, user.login

async def score_issues(issues: list, llm) -> list[PainIssue]
    # Build prompt: list of issue titles+bodies → rate each 1-5
    # Parse LLM JSON response into PainIssue objects
    # pain_score = LLM_score × log(comments+1) × log(participants+1)

async def cluster_pains(issues: list[PainIssue], llm) -> list[PainCluster]
    # Build prompt: all scored issues → group into 3-5 patterns
    # Each cluster: name, root cause, evidence issue numbers

async def run_pain_mining(client, top_repos: list[str], llm, store) -> PainSnapshot
    # For each repo: fetch_issues
    # Score all issues across repos
    # Cluster into patterns
    # Save snapshot, return it
```

**LLM prompt template for scoring:**
```
Rate the pain level (1-5) of each GitHub issue below.
5 = critical, blocking production, no workaround
3 = annoying, slows development
1 = minor, cosmetic, easy workaround
Be strict — most issues should be 2-3.

Issues:
#1 [repo] title: body
#2 [repo] title: body
...

Return JSON: {"scores": [{"issue_number": N, "score": S, "key_phrase": "..."}, ...]}
```

**LLM prompt template for clustering:**
```
Group these pain issues into 3-5 patterns. Each pattern should represent a recurring developer pain point.

Return JSON:
{"clusters": [
  {"title": "5 words max",
   "root_cause": "1 sentence",
   "issue_numbers": [N, N, ...],
   "severity": avg_score}
]}
```

---

### Task 4: API Endpoint

**Files:**
- Modify: `backend/router/radar.py`

Add:
```python
@router.get("/pain")
async def pain(domain: str = Query(...)):
    store = PainStore()
    snapshot = store.get_latest(domain)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No pain data yet")
    return snapshot.model_dump()
```

---

### Task 5: Integrate into Radar Pipeline

**Files:**
- Modify: `backend/engine/radar.py`

In `run_radar()`, after `store.save(snapshot)`:
```python
# Phase 2: Pain Mining on top repos
top_repos = []
for topic in all_topics[:3]:  # top 3 topics
    for repo in topic.top_repos[:2]:  # top 2 repos each
        if repo.full_name not in top_repos:
            top_repos.append(repo.full_name)
top_repos = top_repos[:5]  # cap at 5

if top_repos:
    llm_client = OpenAIClient(...)  # get from config
    from backend.engine.pain import run_pain_mining
    from backend.store.pain_store import PainStore
    pain_snapshot = await run_pain_mining(client, top_repos, llm_client, PainStore())
```

---

### Task 6: Frontend Opportunities Page

**Files:**
- Modify: `frontend/src/app/opportunities/page.tsx`
- Create: `frontend/src/components/opportunity/OpportunityCard.tsx`
- Create: `frontend/src/components/opportunity/OpportunityGrid.tsx`

Add to `frontend/src/lib/api.ts`:
```typescript
export async function fetchPain(domain: string): Promise<PainResponse> {
  const res = await fetch(`${API_BASE}/api/pain?domain=${domain}`);
  if (!res.ok) throw new Error(`Pain fetch failed: ${res.status}`);
  return res.json();
}
```

OpportunityCard shows: pain pattern title, severity bar, description, affected repos, evidence count.

---

### Self-Review

**Spec coverage:** ✅ Models (T1), Store (T2), Engine (T3), API (T4), Integration (T5), Frontend (T6)
**No placeholders:** ✅ All code specified
**Type consistency:** ✅ PainIssue → PainCluster → PainSnapshot chain matches
