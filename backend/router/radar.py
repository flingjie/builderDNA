"""Radar API router."""
from fastapi import APIRouter, Query, HTTPException

from backend.dependencies import get_github_client, get_domain_config
from backend.store.trend_store import TrendStore
from backend.store.pain_store import PainStore
from backend.engine.radar import run_radar

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/radar")
async def radar(
    domain: str = Query(..., description="Domain name, e.g. 'agent'"),
    window: int = Query(60, description="Time window in days"),
    refresh: bool = Query(False, description="Force refresh, skip cache"),
):
    client = get_github_client()
    store = TrendStore()
    domain_config = get_domain_config(domain)
    domain_config.window_days = window

    try:
        if refresh:
            snapshot = await run_radar(client, domain_config, store)
        else:
            snapshot = store.get_latest(domain)
            if snapshot is None or snapshot.window_days != window:
                snapshot = await run_radar(client, domain_config, store)

        if snapshot is None:
            raise HTTPException(status_code=500, detail="Radar engine did not return a snapshot")

        return {
            "domain": snapshot.domain,
            "snapshot_id": snapshot.id,
            "generated_at": snapshot.created_at.isoformat(),
            "window_days": snapshot.window_days,
            "rate_limit": {"calls": client.rate_limiter._total_calls},
            "topics": [t.model_dump() for t in snapshot.topics],
        }
    except NotImplementedError:
        raise HTTPException(status_code=500, detail="Radar engine not yet available (Task 4)")
    finally:
        await client.close()


@router.get("/trends")
async def trends(
    domain: str = Query(...),
    topic: str = Query(..., description="Topic name"),
):
    """Get detailed trend data for a specific topic."""
    store = TrendStore()
    snapshot = store.get_latest(domain)
    if snapshot is None:
        raise HTTPException(
            status_code=404, detail=f"No snapshot for domain '{domain}'"
        )

    for t in snapshot.topics:
        if t.topic == topic:
            return t.model_dump()

    raise HTTPException(
        status_code=404, detail=f"Topic '{topic}' not found"
    )


@router.get("/pain")
async def pain(domain: str = Query(...)):
    store = PainStore()
    snapshot = store.get_latest(domain)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"No pain data for domain '{domain}'")
    return snapshot.model_dump()
