"""Radar API router."""
from fastapi import APIRouter, Query, HTTPException

from backend.dependencies import get_github_client, get_domain_config
from backend.store.trend_store import TrendStore
from backend.store.pain_store import PainStore
from backend.store.opportunity_store import OpportunityStore
from backend.store.discovery_store import DiscoveryStore
from backend.engine.discovery import run_discovery
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
    """Get auto-discovered emerging themes from the discovery engine."""
    from backend.dependencies import get_config
    from backend.store.discovery_store import DiscoveryStore
    from backend.engine.discovery import run_discovery
    from llm.client import OpenAIClient

    store = DiscoveryStore()
    cfg = get_config()
    cfg.discovery.lookback_days = window

    client = get_github_client()
    try:
        if refresh:
            llm_client = OpenAIClient(
                api_key=cfg.llm.api_key,
                model=cfg.llm.model,
                base_url=cfg.llm.base_url,
            )
            snapshot = await run_discovery(client, cfg, llm_client, store)
        else:
            snapshot = store.get_latest("global")
            if snapshot is None:
                llm_client = OpenAIClient(
                    api_key=cfg.llm.api_key,
                    model=cfg.llm.model,
                    base_url=cfg.llm.base_url,
                )
                snapshot = await run_discovery(client, cfg, llm_client, store)

        if snapshot is None:
            return {"domain": "global", "snapshot_id": "", "generated_at": "", "window_days": window, "themes": []}

        return {
            "domain": snapshot.domain,
            "snapshot_id": snapshot.id,
            "generated_at": snapshot.created_at.isoformat(),
            "window_days": snapshot.window_days,
            "themes": [t.model_dump() for t in snapshot.themes],
        }
    except Exception:
        return {"domain": "global", "snapshot_id": "", "generated_at": "", "window_days": window, "themes": []}
    finally:
        await client.close()


@router.get("/vendors")
async def vendors(
    tag: str = Query("", description="Filter by comparison_group: domestic, overseas, or empty for all"),
):
    """Get latest vendor profiles, optionally filtered by tag."""
    from backend.store.vendor_store import VendorStore
    store = VendorStore()
    snapshot = store.get_latest("agent")
    if snapshot is None:
        return {"profiles": [], "count": 0}

    profiles = snapshot.profiles
    if tag:
        profiles = [p for p in profiles if p.comparison_group == tag]

    return {"profiles": [p.model_dump() for p in profiles], "count": len(profiles)}


@router.get("/vendors/{name}")
async def vendor_detail(name: str):
    """Get detailed profile for a single vendor."""
    from backend.store.vendor_store import VendorStore
    store = VendorStore()
    snapshot = store.get_latest("agent")
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No vendor data")

    for p in snapshot.profiles:
        if p.name == name:
            return p.model_dump()
    raise HTTPException(status_code=404, detail=f"Vendor '{name}' not found")


@router.get("/compare")
async def compare(
    dimension: str = Query("", description="Optional: filter by dimension name"),
):
    """Get domestic-vs-overseas comparison. Requires a refresh to generate."""
    from backend.store.vendor_store import VendorStore
    from backend.engine.vendor import generate_comparison
    from llm.client import OpenAIClient
    from backend.dependencies import get_config

    store = VendorStore()
    cfg = get_config()
    client = get_github_client()
    try:
        llm_client = OpenAIClient(
            api_key=cfg.llm.api_key,
            model=cfg.llm.model,
            base_url=cfg.llm.base_url,
        )
        diffs = await generate_comparison(client, cfg, llm_client)
    except Exception:
        diffs = []
    finally:
        await client.close()

    if dimension:
        diffs = [d for d in diffs if d.dimension == dimension]

    return {"diffs": [d.model_dump() for d in diffs]}


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
