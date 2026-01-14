"""Celery tasks for keyword scraping (Phase 1)."""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import logging

from celery import current_task
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database.connection import get_async_db_context
from src.database.models import DeviceType, JobStatus, JobType, KeywordSource
from src.database.repositories import (
    AdAppearanceRepository,
    AdvertiserRepository,
    CrawlJobRepository,
    KeywordAdvertiserStatsRepository,
    KeywordRepository,
)
from src.proxy.manager import ProxyManager
from src.scraper.captcha_handler import BlockedError, CaptchaError
from src.scraper.google_serp import GoogleSerpScraper
from src.tasks.celery_app import celery_app
from src.utils.domain_parser import DomainParser

logger = logging.getLogger(__name__)


def run_async(coro):
    """Helper to run async functions in sync Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def scrape_keyword_task(
    self,
    keyword_id: int,
    geo: str = "US",
    device: str = "desktop",
):
    """
    Celery task to scrape a single keyword.

    Args:
        keyword_id: Database ID of keyword to scrape
        geo: Geographic location code
        device: Device type (desktop/mobile/tablet)
    """
    return run_async(_scrape_keyword_async(self, keyword_id, geo, device))


async def _scrape_keyword_async(
    task,
    keyword_id: int,
    geo: str,
    device: str,
):
    """Async implementation of keyword scraping."""
    async with get_async_db_context() as session:
        # Get repositories
        keyword_repo = KeywordRepository(session)
        advertiser_repo = AdvertiserRepository(session)
        appearance_repo = AdAppearanceRepository(session)
        stats_repo = KeywordAdvertiserStatsRepository(session)
        job_repo = CrawlJobRepository(session)

        # Fetch keyword
        keyword = await keyword_repo.get_by_id(keyword_id)
        if not keyword:
            logger.error(f"Keyword {keyword_id} not found")
            return {"error": "Keyword not found"}

        # Create or update job record
        job = await job_repo.create(
            job_type=JobType.KEYWORD_SCRAPE,
            target=keyword.keyword,
            priority=keyword.crawl_priority,
        )
        job.celery_task_id = current_task.request.id if current_task else None
        await job_repo.update_status(job.id, JobStatus.RUNNING)

        try:
            # Initialize scraper
            proxy_manager = ProxyManager()

            async with GoogleSerpScraper(proxy_manager=proxy_manager) as scraper:
                result = await scraper.scrape_keyword(
                    keyword=keyword.keyword,
                    geo=geo,
                    device=device,
                    save_html=True,
                )

            if result.blocked or result.captcha:
                # Handle block - retry with different proxy
                await job_repo.update_status(
                    job.id,
                    JobStatus.BLOCKED,
                    error=result.error,
                )

                if task.request.retries < task.max_retries:
                    # Exponential backoff
                    delay = 60 * (2 ** task.request.retries) + random.randint(0, 60)
                    raise task.retry(countdown=delay)
                else:
                    return {"error": result.error, "blocked": True}

            if not result.success:
                await job_repo.update_status(
                    job.id,
                    JobStatus.FAILED,
                    error=result.error,
                )
                return {"error": result.error, "success": False}

            # Process found ads
            new_advertisers = 0
            new_appearances = 0

            device_type = DeviceType(device)

            for ad in result.ads:
                # Get or create advertiser
                advertiser, was_created = await advertiser_repo.get_or_create(
                    domain=ad.domain,
                    root_domain=ad.root_domain,
                    company_name=DomainParser.extract_company_name(
                        ad.domain, ad.headline
                    ),
                    discovery_keyword_id=keyword_id if was_created else None,
                )

                if was_created:
                    new_advertisers += 1
                    logger.info(f"Discovered new advertiser: {ad.domain}")

                # Update advertiser last seen
                await advertiser_repo.update_last_seen(advertiser.id)

                # Create ad appearance record
                await appearance_repo.create(
                    keyword_id=keyword_id,
                    advertiser_id=advertiser.id,
                    position=ad.position,
                    headline=ad.headline,
                    description=ad.description,
                    display_url=ad.display_url,
                    final_url=ad.final_url,
                    extensions=ad.extensions.to_dict() if hasattr(ad.extensions, 'to_dict') else {
                        "sitelinks": [{"title": sl.title, "url": sl.url} for sl in ad.extensions.sitelinks],
                        "callouts": ad.extensions.callouts,
                        "phone": ad.extensions.phone,
                        "rating": ad.extensions.rating,
                    },
                    geo_location=geo,
                    device_type=device_type,
                    raw_html=ad.raw_html,
                )
                new_appearances += 1

                # Update keyword-advertiser stats
                await stats_repo.update_stats(
                    keyword_id=keyword_id,
                    advertiser_id=advertiser.id,
                    position=ad.position,
                )

                # Update advertiser keyword count
                await advertiser_repo.update_keyword_count(advertiser.id)

            # Update keyword last crawled time
            await keyword_repo.update_crawled(keyword_id)

            # Commit all changes
            await session.commit()

            # Update job as completed
            summary = {
                "ads_found": len(result.ads),
                "new_advertisers": new_advertisers,
                "new_appearances": new_appearances,
                "response_time_ms": result.response_time_ms,
                "top_ads": result.top_ad_count,
                "bottom_ads": result.bottom_ad_count,
            }

            await job_repo.update_status(
                job.id,
                JobStatus.COMPLETED,
                result_summary=summary,
            )
            await session.commit()

            logger.info(
                f"Scraped keyword '{keyword.keyword}': "
                f"{len(result.ads)} ads, {new_advertisers} new advertisers"
            )

            # Queue domain expansion for new advertisers
            if new_advertisers > 0:
                # Import here to avoid circular imports
                from src.tasks.domain_tasks import expand_advertiser_keywords
                for ad in result.ads:
                    if ad.domain:
                        # Queue with delay to spread load
                        expand_advertiser_keywords.apply_async(
                            args=[ad.domain],
                            countdown=random.randint(300, 900),  # 5-15 min delay
                        )

            return summary

        except (CaptchaError, BlockedError) as e:
            await job_repo.update_status(
                job.id,
                JobStatus.BLOCKED,
                error=str(e),
            )
            await session.commit()
            raise

        except Exception as e:
            logger.exception(f"Error scraping keyword {keyword_id}")
            await job_repo.update_status(
                job.id,
                JobStatus.FAILED,
                error=str(e),
            )
            await session.commit()
            raise


@celery_app.task
def bulk_scrape_keywords(
    keyword_ids: List[int],
    geo: str = "US",
    device: str = "desktop",
):
    """
    Queue multiple keywords for scraping with rate limiting.

    Args:
        keyword_ids: List of keyword IDs to scrape
        geo: Geographic location
        device: Device type
    """
    scheduled = 0

    for i, keyword_id in enumerate(keyword_ids):
        # Add random delay between jobs (30-120 seconds)
        delay = i * random.randint(30, 120)

        scrape_keyword_task.apply_async(
            args=[keyword_id, geo, device],
            countdown=delay,
        )
        scheduled += 1

    logger.info(f"Scheduled {scheduled} keyword scrape tasks")
    return {"scheduled": scheduled}


@celery_app.task
def schedule_keyword_refresh():
    """
    Periodic task to find and queue keywords due for re-scraping.

    Run this every hour via Celery Beat.
    """
    return run_async(_schedule_keyword_refresh_async())


async def _schedule_keyword_refresh_async():
    """Async implementation of keyword refresh scheduling."""
    async with get_async_db_context() as session:
        keyword_repo = KeywordRepository(session)

        # Get keywords due for crawl
        due_keywords = await keyword_repo.get_due_for_crawl(limit=50)

        if not due_keywords:
            logger.info("No keywords due for refresh")
            return {"scheduled": 0}

        # Queue keywords based on priority
        scheduled = 0
        for i, keyword in enumerate(due_keywords):
            # Higher priority = less delay
            base_delay = (10 - keyword.crawl_priority) * 30  # 0-270 seconds
            delay = base_delay + random.randint(0, 60)

            scrape_keyword_task.apply_async(
                args=[keyword.id],
                countdown=delay,
            )
            scheduled += 1

        logger.info(f"Scheduled {scheduled} keywords for refresh")
        return {"scheduled": scheduled}


@celery_app.task
def cleanup_old_jobs(days_old: int = 7):
    """
    Clean up old completed/failed jobs.

    Args:
        days_old: Delete jobs older than this many days
    """
    return run_async(_cleanup_old_jobs_async(days_old))


async def _cleanup_old_jobs_async(days_old: int):
    """Async implementation of job cleanup."""
    from sqlalchemy import delete

    async with get_async_db_context() as session:
        from src.database.models import CrawlJob

        cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)

        result = await session.execute(
            delete(CrawlJob).where(
                CrawlJob.completed_at < cutoff,
                CrawlJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
            )
        )

        deleted = result.rowcount
        await session.commit()

        logger.info(f"Cleaned up {deleted} old jobs")
        return {"deleted": deleted}


@celery_app.task
def add_seed_keywords(keywords: List[str], category: Optional[str] = None):
    """
    Add seed keywords to the database.

    Args:
        keywords: List of keyword strings
        category: Optional category for grouping
    """
    return run_async(_add_seed_keywords_async(keywords, category))


async def _add_seed_keywords_async(keywords: List[str], category: Optional[str]):
    """Async implementation of adding seed keywords."""
    async with get_async_db_context() as session:
        keyword_repo = KeywordRepository(session)

        added = 0
        for kw in keywords:
            _, was_created = await keyword_repo.get_or_create(
                kw,
                source=KeywordSource.SEED,
                category=category,
            )
            if was_created:
                added += 1

        await session.commit()

        logger.info(f"Added {added} new seed keywords")
        return {"added": added, "total": len(keywords)}
