"""Crawl job API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    BulkScrapeRequest,
    JobResponse,
    JobStatsResponse,
)
from src.database.connection import get_async_db
from src.database.models import JobStatus, JobType
from src.database.repositories import CrawlJobRepository
from src.tasks.keyword_tasks import bulk_scrape_keywords

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_db),
):
    """List crawl jobs with optional filters."""
    repo = CrawlJobRepository(session)

    status_enum = None
    if status:
        try:
            status_enum = JobStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    type_enum = None
    if job_type:
        try:
            type_enum = JobType(job_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid job type: {job_type}")

    jobs = await repo.list_all(
        status=status_enum,
        job_type=type_enum,
        limit=limit,
        offset=offset,
    )

    return [
        JobResponse(
            id=job.id,
            job_type=job.job_type.value,
            target=job.target,
            status=job.status.value,
            priority=job.priority,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            last_error=job.last_error,
            result_summary=job.result_summary,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
        for job in jobs
    ]


@router.get("/stats", response_model=JobStatsResponse)
async def get_job_stats(
    session: AsyncSession = Depends(get_async_db),
):
    """Get crawling statistics dashboard."""
    repo = CrawlJobRepository(session)

    stats = await repo.get_stats()

    return JobStatsResponse(
        pending=stats.get("pending", 0),
        running=stats.get("running", 0),
        completed=stats.get("completed", 0),
        failed=stats.get("failed", 0),
        blocked=stats.get("blocked", 0),
        total=sum(stats.values()),
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    session: AsyncSession = Depends(get_async_db),
):
    """Get job details."""
    repo = CrawlJobRepository(session)

    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(
        id=job.id,
        job_type=job.job_type.value,
        target=job.target,
        status=job.status.value,
        priority=job.priority,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        last_error=job.last_error,
        result_summary=job.result_summary,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.post("/bulk-scrape", response_model=dict)
async def create_bulk_scrape(
    request: BulkScrapeRequest,
    session: AsyncSession = Depends(get_async_db),
):
    """Queue bulk keyword scraping."""
    # Queue the bulk scrape task
    task = bulk_scrape_keywords.delay(
        keyword_ids=request.keyword_ids,
        geo=request.geo,
        device=request.device,
    )

    return {
        "task_id": task.id,
        "keywords_queued": len(request.keyword_ids),
        "geo": request.geo,
        "device": request.device,
    }


@router.delete("/{job_id}", response_model=dict)
async def cancel_job(
    job_id: int,
    session: AsyncSession = Depends(get_async_db),
):
    """Cancel a pending job."""
    repo = CrawlJobRepository(session)

    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job.status.value}"
        )

    await repo.update_status(job_id, JobStatus.FAILED, error="Cancelled by user")
    await session.commit()

    return {"status": "cancelled", "job_id": job_id}
