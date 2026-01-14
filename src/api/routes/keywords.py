"""Keyword API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    KeywordBulkCreate,
    KeywordCreate,
    KeywordDetailResponse,
    KeywordResponse,
    ScrapeRequest,
    ScrapeResponse,
    SuggestionsResponse,
)
from src.database.connection import get_async_db
from src.database.models import JobStatus, JobType, KeywordSource
from src.database.repositories import (
    AdvertiserRepository,
    CrawlJobRepository,
    KeywordAdvertiserStatsRepository,
    KeywordRepository,
)
from src.tasks.keyword_tasks import scrape_keyword_task

router = APIRouter(prefix="/api/keywords", tags=["keywords"])


@router.post("", response_model=KeywordResponse)
async def create_keyword(
    keyword_data: KeywordCreate,
    session: AsyncSession = Depends(get_async_db),
):
    """Create a new seed keyword."""
    repo = KeywordRepository(session)

    existing = await repo.get_by_keyword(keyword_data.keyword)
    if existing:
        raise HTTPException(status_code=400, detail="Keyword already exists")

    keyword = await repo.create(
        keyword=keyword_data.keyword,
        source=KeywordSource.SEED,
        category=keyword_data.category,
        crawl_priority=keyword_data.crawl_priority,
        search_volume=keyword_data.search_volume,
        cpc_estimate=keyword_data.cpc_estimate,
    )

    await session.commit()
    return keyword


@router.post("/bulk", response_model=dict)
async def create_keywords_bulk(
    data: KeywordBulkCreate,
    session: AsyncSession = Depends(get_async_db),
):
    """Add multiple seed keywords at once."""
    repo = KeywordRepository(session)

    added = 0
    skipped = 0

    for kw in data.keywords:
        _, was_created = await repo.get_or_create(
            kw,
            source=KeywordSource.SEED,
            category=data.category,
        )
        if was_created:
            added += 1
        else:
            skipped += 1

    await session.commit()

    return {
        "added": added,
        "skipped": skipped,
        "total": len(data.keywords),
    }


@router.get("", response_model=list[KeywordResponse])
async def list_keywords(
    is_active: Optional[bool] = Query(None),
    source: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_db),
):
    """List all keywords with optional filters."""
    repo = KeywordRepository(session)

    source_enum = None
    if source:
        try:
            source_enum = KeywordSource(source)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid source: {source}")

    keywords = await repo.list_all(
        is_active=is_active,
        source=source_enum,
        category=category,
        limit=limit,
        offset=offset,
    )

    return keywords


@router.get("/{keyword_id}", response_model=KeywordDetailResponse)
async def get_keyword(
    keyword_id: int,
    session: AsyncSession = Depends(get_async_db),
):
    """Get keyword details with statistics."""
    repo = KeywordRepository(session)
    stats_repo = KeywordAdvertiserStatsRepository(session)

    keyword = await repo.get_by_id(keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    # Get advertiser stats
    stats = await stats_repo.get_by_keyword(keyword_id, limit=10)

    response = KeywordDetailResponse(
        id=keyword.id,
        keyword=keyword.keyword,
        category=keyword.category,
        crawl_priority=keyword.crawl_priority,
        crawl_frequency_hours=keyword.crawl_frequency_hours,
        source=keyword.source.value,
        search_volume=keyword.search_volume,
        cpc_estimate=keyword.cpc_estimate,
        last_crawled_at=keyword.last_crawled_at,
        is_active=keyword.is_active,
        created_at=keyword.created_at,
        total_advertisers=len(stats),
        top_advertisers=[
            {
                "advertiser_id": s.advertiser_id,
                "appearances": s.appearance_count,
                "avg_position": float(s.avg_position) if s.avg_position else None,
            }
            for s in stats
        ],
    )

    return response


@router.get("/{keyword_id}/advertisers", response_model=list[dict])
async def get_keyword_advertisers(
    keyword_id: int,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_db),
):
    """List all advertisers on this keyword."""
    repo = KeywordRepository(session)
    stats_repo = KeywordAdvertiserStatsRepository(session)
    adv_repo = AdvertiserRepository(session)

    keyword = await repo.get_by_id(keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    stats = await stats_repo.get_by_keyword(keyword_id, limit=limit)

    results = []
    for stat in stats:
        advertiser = await adv_repo.get_by_id(stat.advertiser_id)
        if advertiser:
            results.append({
                "advertiser": {
                    "id": advertiser.id,
                    "domain": advertiser.domain,
                    "company_name": advertiser.company_name,
                },
                "stats": {
                    "appearance_count": stat.appearance_count,
                    "avg_position": float(stat.avg_position) if stat.avg_position else None,
                    "first_seen": stat.first_seen_at.isoformat(),
                    "last_seen": stat.last_seen_at.isoformat(),
                },
            })

    return results


@router.post("/{keyword_id}/scrape", response_model=ScrapeResponse)
async def scrape_keyword(
    keyword_id: int,
    request: ScrapeRequest,
    session: AsyncSession = Depends(get_async_db),
):
    """Trigger immediate scrape for a keyword."""
    repo = KeywordRepository(session)
    job_repo = CrawlJobRepository(session)

    keyword = await repo.get_by_id(keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    # Create job record immediately so it shows in the UI
    job = await job_repo.create(
        job_type=JobType.KEYWORD_SCRAPE,
        target=keyword.keyword,
        priority=keyword.crawl_priority,
    )
    await session.commit()

    # Try to queue the Celery task
    task_id = None
    task_error = None
    try:
        task = scrape_keyword_task.delay(
            keyword_id=keyword_id,
            geo=request.geo,
            device=request.device,
        )
        task_id = task.id
        # Update job with celery task ID
        job.celery_task_id = task_id
        await session.commit()
    except Exception as e:
        task_error = f"Celery not available: {str(e)}"
        # Update job status to indicate worker needed
        await job_repo.update_status(
            job.id,
            JobStatus.PENDING,
            error="Waiting for Celery worker to pick up task"
        )
        await session.commit()

    return ScrapeResponse(
        keyword=keyword.keyword,
        ads_found=0,
        new_advertisers=0,
        response_time_ms=0,
        error=f"Job #{job.id} created" + (f", Task: {task_id}" if task_id else f" ({task_error})"),
    )


@router.get("/suggestions", response_model=SuggestionsResponse)
async def get_keyword_suggestions(
    base_keyword: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_db),
):
    """Get related keyword suggestions."""
    from src.expansion.keyword_generator import KeywordExpander

    expander = KeywordExpander(
        domain="suggestions",
        existing_keywords=[base_keyword],
    )

    # Generate suggestions
    suggestions = expander.generate_expansion_keywords(max_keywords=limit)

    return SuggestionsResponse(
        suggestions=[
            {
                "keyword": kw,
                "source": "expansion",
                "relevance_score": 1.0 - (i / len(suggestions)) if suggestions else 0,
            }
            for i, kw in enumerate(suggestions)
        ]
    )
