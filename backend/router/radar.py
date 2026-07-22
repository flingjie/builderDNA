"""Radar API router."""
from fastapi import APIRouter, Query, HTTPException

from backend.dependencies import get_github_client, get_domain_config
from backend.store.trend_store import TrendStore
from backend.store.pain_store import PainStore
from backend.store.opportunity_store import OpportunityStore
from backend.engine.radar import run_radar
from llm.client import OpenAIClient
from backend.dependencies import get_config

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
            "rate_limit": {"summary": client.rate_limiter.usage_summary()},
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


@router.get("/explorer")
async def explorer(
    domain: str = Query("agent", description="Domain to cross-reference for known topics"),
    window: int = Query(30, description="Lookback window in days"),
    refresh: bool = Query(False, description="Force re-run discovery"),
):
    """Get auto-discovered emerging themes.

    WARNING: Discovery engine has been deprecated. This endpoint returns empty
    data until the new intelligence/trend/detector.py pipeline is wired up.
    Frontend should handle empty themes gracefully.
    """
    return {"domain": "global", "snapshot_id": "", "generated_at": "", "window_days": window, "themes": []}


@router.get("/vendors")
async def vendors(
    tag: str = Query("", description="Filter by comparison_group: domestic, overseas, or empty for all"),
):
    """Get latest vendor profiles.

    WARNING: Vendor engine has been deprecated. Returns empty data until
    the new intelligence/trend/detector.py pipeline is wired up.
    """
    return {"profiles": [], "count": 0}


@router.get("/vendors/{name}")
async def vendor_detail(name: str):
    """Get detailed profile for a single vendor.

    WARNING: Vendor engine has been deprecated.
    """
    raise HTTPException(status_code=404, detail="Vendor engine unavailable — awaiting intelligence/trend migration")


@router.get("/compare")
async def compare(
    dimension: str = Query("", description="Optional: filter by dimension name"),
):
    """Get domestic-vs-overseas comparison.

    WARNING: Vendor engine has been deprecated. Returns empty diffs until
    the new intelligence/trend/detector.py pipeline is wired up.
    """
    return {"diffs": []}


@router.get("/pain")
async def pain(domain: str = Query(...)):
    store = PainStore()
    snapshot = store.get_latest(domain)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"No pain data for domain '{domain}'")
    return snapshot.model_dump()


@router.get("/opportunities")
async def opportunities(domain: str = Query("agent")):
    """Get latest opportunity cards for a domain."""
    store = OpportunityStore()
    snapshot = store.get_latest(domain)
    if snapshot is None:
        return {"cards": []}
    return {"cards": [c.model_dump() for c in snapshot.cards]}


@router.get("/evidence/{opportunity_id}")
async def evidence(opportunity_id: str, domain: str = Query("agent")):
    """Get detailed evidence for a specific opportunity."""
    store = OpportunityStore()
    snapshot = store.get_latest(domain)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No opportunity data")

    for card in snapshot.cards:
        if card.id == opportunity_id:
            return {
                "card": card.model_dump(),
                "evidence": card.evidence.model_dump(),
            }
    raise HTTPException(status_code=404, detail=f"Opportunity '{opportunity_id}' not found")
