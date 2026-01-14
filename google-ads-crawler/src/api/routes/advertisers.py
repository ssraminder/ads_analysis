"""Advertiser API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    AdAppearanceResponse,
    AdvertiserDetailResponse,
    AdvertiserResponse,
    CompetitorResponse,
    ExpandRequest,
    ExpandResponse,
    KeywordResponse,
)
from src.database.connection import get_async_db
from src.database.repositories import (
    AdAppearanceRepository,
    AdvertiserRepository,
    KeywordAdvertiserStatsRepository,
    KeywordRepository,
)
from src.tasks.domain_tasks import expand_advertiser_keywords

router = APIRouter(prefix="/api/advertisers", tags=["advertisers"])


@router.get("", response_model=list[AdvertiserResponse])
async def list_advertisers(
    is_active: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_db),
):
    """List all discovered advertisers."""
    repo = AdvertiserRepository(session)

    advertisers = await repo.list_all(
        is_active=is_active,
        limit=limit,
        offset=offset,
    )

    return advertisers


@router.get("/search", response_model=list[AdvertiserResponse])
async def search_advertisers(
    domain: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_db),
):
    """Search advertisers by domain."""
    repo = AdvertiserRepository(session)

    advertisers = await repo.search_by_domain(domain, limit=limit)

    return advertisers


@router.get("/{advertiser_id}", response_model=AdvertiserDetailResponse)
async def get_advertiser(
    advertiser_id: int,
    session: AsyncSession = Depends(get_async_db),
):
    """Get advertiser details."""
    repo = AdvertiserRepository(session)
    stats_repo = KeywordAdvertiserStatsRepository(session)
    keyword_repo = KeywordRepository(session)

    advertiser = await repo.get_by_id(advertiser_id)
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    # Get top keywords
    stats = await stats_repo.get_by_advertiser(advertiser_id, limit=10)

    top_keywords = []
    for stat in stats:
        keyword = await keyword_repo.get_by_id(stat.keyword_id)
        if keyword:
            top_keywords.append({
                "keyword": keyword.keyword,
                "appearances": stat.appearance_count,
                "avg_position": float(stat.avg_position) if stat.avg_position else None,
            })

    # Get discovery keyword
    discovery_keyword = None
    if advertiser.discovery_keyword_id:
        kw = await keyword_repo.get_by_id(advertiser.discovery_keyword_id)
        if kw:
            discovery_keyword = kw.keyword

    return AdvertiserDetailResponse(
        id=advertiser.id,
        domain=advertiser.domain,
        company_name=advertiser.company_name,
        root_domain=advertiser.root_domain,
        estimated_monthly_spend=advertiser.estimated_monthly_spend,
        total_keywords_count=advertiser.total_keywords_count,
        first_seen_at=advertiser.first_seen_at,
        last_seen_at=advertiser.last_seen_at,
        is_active=advertiser.is_active,
        discovery_keyword=discovery_keyword,
        top_keywords=top_keywords,
        metadata=advertiser.metadata_,
    )


@router.get("/{advertiser_id}/keywords", response_model=list[dict])
async def get_advertiser_keywords(
    advertiser_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_db),
):
    """Get all keywords this advertiser bids on."""
    repo = AdvertiserRepository(session)
    stats_repo = KeywordAdvertiserStatsRepository(session)
    keyword_repo = KeywordRepository(session)

    advertiser = await repo.get_by_id(advertiser_id)
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    stats = await stats_repo.get_by_advertiser(advertiser_id, limit=limit)

    results = []
    for stat in stats:
        keyword = await keyword_repo.get_by_id(stat.keyword_id)
        if keyword:
            results.append({
                "keyword": {
                    "id": keyword.id,
                    "keyword": keyword.keyword,
                    "category": keyword.category,
                },
                "stats": {
                    "appearance_count": stat.appearance_count,
                    "avg_position": float(stat.avg_position) if stat.avg_position else None,
                    "first_seen": stat.first_seen_at.isoformat(),
                    "last_seen": stat.last_seen_at.isoformat(),
                    "estimated_spend": float(stat.estimated_spend) if stat.estimated_spend else None,
                },
            })

    return results


@router.get("/{advertiser_id}/ads", response_model=list[AdAppearanceResponse])
async def get_advertiser_ads(
    advertiser_id: int,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_db),
):
    """Get all ad variations seen for this advertiser."""
    repo = AdvertiserRepository(session)
    appearance_repo = AdAppearanceRepository(session)

    advertiser = await repo.get_by_id(advertiser_id)
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    appearances = await appearance_repo.get_unique_ads(advertiser_id, limit=limit)

    return appearances


@router.get("/{advertiser_id}/history", response_model=list[dict])
async def get_advertiser_history(
    advertiser_id: int,
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_async_db),
):
    """Get position/spend history over time."""
    from src.expansion.domain_tracker import DomainTracker

    repo = AdvertiserRepository(session)

    advertiser = await repo.get_by_id(advertiser_id)
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    tracker = DomainTracker(session)
    trends = await tracker.analyze_position_trends(advertiser_id, days_current=days)

    return [
        {
            "keyword": t.keyword,
            "current_avg_position": t.current_avg_position,
            "previous_avg_position": t.previous_avg_position,
            "position_change": t.position_change,
            "appearance_trend": t.appearance_trend,
        }
        for t in trends
    ]


@router.post("/{advertiser_id}/expand", response_model=ExpandResponse)
async def expand_advertiser(
    advertiser_id: int,
    request: ExpandRequest,
    session: AsyncSession = Depends(get_async_db),
):
    """Trigger keyword expansion for this advertiser."""
    repo = AdvertiserRepository(session)

    advertiser = await repo.get_by_id(advertiser_id)
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    # Queue expansion task
    task = expand_advertiser_keywords.delay(advertiser_id)

    return ExpandResponse(
        advertiser_domain=advertiser.domain,
        keywords_generated=0,
        new_keywords_added=0,
        keywords_queued=0,
    )


@router.get("/{advertiser_id}/competitors", response_model=list[CompetitorResponse])
async def get_competitors(
    advertiser_id: int,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_db),
):
    """Get other advertisers on same keywords."""
    repo = AdvertiserRepository(session)

    advertiser = await repo.get_by_id(advertiser_id)
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    competitors = await repo.get_competitors(advertiser_id, limit=limit)

    return [
        CompetitorResponse(
            advertiser=AdvertiserResponse(
                id=comp.id,
                domain=comp.domain,
                company_name=comp.company_name,
                root_domain=comp.root_domain,
                estimated_monthly_spend=comp.estimated_monthly_spend,
                total_keywords_count=comp.total_keywords_count,
                first_seen_at=comp.first_seen_at,
                last_seen_at=comp.last_seen_at,
                is_active=comp.is_active,
            ),
            shared_keywords=shared_count,
        )
        for comp, shared_count in competitors
    ]
