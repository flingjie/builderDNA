# BuilderDNA 2.0 Phase 3: Opportunity Intelligence — Implementation Plan

> **Goal:** Add LLM-powered opportunity reasoning engine. Feeds Phase 1+2 data to LLM for Chain-of-Thought opportunity discovery.

**Architecture:** New `backend/engine/opportunity.py` reads TrendSnapshot + PainSnapshot, prompts LLM, outputs OpportunityCard[]. Stored in SQLite, served via API, rendered on frontend.

**Tech Stack:** Same — FastAPI, pydantic, existing OpenAIClient, SQLite

## Global Constraints

- Python >= 3.11, no new dependencies
- Reuse existing `llm/client.py` (OpenAIClient)
- TDD for backend
- Follow existing patterns: models → store → engine → router → frontend

---

### Task 1: Opportunity Models

- Create: `backend/models/opportunity.py`
- Create: `tests/test_radar/test_opportunity_models.py`

Models: OpportunityEvidence, OpportunityCard, OpportunitySnapshot

---

### Task 2: Opportunity Store

- Create: `backend/store/opportunity_store.py`
- Create: `tests/test_radar/test_opportunity_store.py`

Interface: save(snapshot) → str, get_latest(domain) → OpportunitySnapshot | None

---

### Task 3: Opportunity Engine

- Create: `backend/engine/opportunity.py`
- Create: `tests/test_radar/test_opportunity_engine.py`

Functions:
- `format_trends_for_llm(snapshot: TrendSnapshot) -> str`
- `format_pains_for_llm(snapshot: PainSnapshot) -> str`
- `async generate_opportunities(trend_snapshot, pain_snapshot, llm) -> list[OpportunityCard]`
- `async run_opportunity_engine(trend_snapshot, pain_snapshot, llm, store) -> OpportunitySnapshot`

LLM prompt template as specified in the spec.

---

### Task 4: API Endpoints

- Modify: `backend/router/radar.py`

Replace placeholder `/api/opportunities` with real data from OpportunityStore.
Add `/api/evidence/:opportunity_id` → returns detailed evidence.

---

### Task 5: Pipeline Integration

- Modify: `backend/engine/radar.py`

After pain mining, load trend + pain snapshots, call opportunity engine.

---

### Task 6: Frontend

- Modify: `frontend/src/lib/types.ts` — add OpportunityCard, OpportunityEvidence
- Modify: `frontend/src/lib/api.ts` — add fetchOpportunities, fetchEvidence
- Create: `frontend/src/components/opportunity/OpportunityCard.tsx`
- Modify: `frontend/src/app/opportunities/page.tsx` — show OpportunityCard[]
- Modify: `frontend/src/app/evidence/[id]/page.tsx` — show real evidence
