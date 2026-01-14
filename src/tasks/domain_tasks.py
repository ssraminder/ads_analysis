"""Celery tasks for domain expansion (Phase 2)."""

import asyncio
import random
from datetime import datetime, timezone
from typing import List, Optional
import logging

from src.config import settings
from src.database.connection import get_async_db_context
from src.database.models import JobStatus, JobType, KeywordSource
from src.database.repositories import (
    AdvertiserRepository,
    CrawlJobRepository,
    KeywordAdvertiserStatsRepository,
    KeywordRepository,
)
from src.expansion.keyword_generator import KeywordExpander
from src.expansion.spend_estimator import SpendEstimator
from src.tasks.celery_app import celery_app
from src.tasks.keyword_tasks import run_async, scrape_keyword_task

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def expand_advertiser_keywords(self, advertiser_id_or_domain):
    """
    Discover more keywords an advertiser is bidding on.

    Args:
        advertiser_id_or_domain: Either advertiser ID (int) or domain (str)
    """
    return run_async(_expand_advertiser_keywords_async(self, advertiser_id_or_domain))


async def _expand_advertiser_keywords_async(task, advertiser_id_or_domain):
    """Async implementation of advertiser keyword expansion."""
    async with get_async_db_context() as session:
        advertiser_repo = AdvertiserRepository(session)
        keyword_repo = KeywordRepository(session)
        job_repo = CrawlJobRepository(session)

        # Get advertiser
        if isinstance(advertiser_id_or_domain, int):
            advertiser = await advertiser_repo.get_by_id(advertiser_id_or_domain)
        else:
            advertiser = await advertiser_repo.get_by_domain(advertiser_id_or_domain)

        if not advertiser:
            logger.error(f"Advertiser not found: {advertiser_id_or_domain}")
            return {"error": "Advertiser not found"}

        # Create job record
        job = await job_repo.create(
            job_type=JobType.DOMAIN_EXPANSION,
            target=advertiser.domain,
            priority=5,
        )
        await job_repo.update_status(job.id, JobStatus.RUNNING)
        await session.commit()

        try:
            # Get existing keywords for this advertiser
            existing_keywords = await advertiser_repo.get_keywords(
                advertiser.id,
                limit=500,
            )

            # Initialize expander
            expander = KeywordExpander(
                domain=advertiser.domain,
                company_name=advertiser.company_name,
                existing_keywords=[kw.keyword for kw in existing_keywords],
            )

            # Generate expansion keywords
            expansion_keywords = expander.generate_expansion_keywords()

            # Add new keywords to database
            new_keywords_added = 0
            keywords_to_scrape = []

            for kw in expansion_keywords[:100]:  # Limit to 100 per expansion
                keyword_obj, was_created = await keyword_repo.get_or_create(
                    kw,
                    source=KeywordSource.EXPANDED,
                    crawl_priority=4,  # Medium priority for expanded keywords
                )

                if was_created:
                    new_keywords_added += 1
                    keywords_to_scrape.append(keyword_obj.id)
                else:
                    # Check if keyword hasn't been crawled recently
                    if keyword_obj.last_crawled_at is None:
                        keywords_to_scrape.append(keyword_obj.id)

            await session.commit()

            # Queue keywords for scraping
            for i, kw_id in enumerate(keywords_to_scrape[:20]):  # Limit scrapes
                delay = i * random.randint(60, 180)  # 1-3 min between each
                scrape_keyword_task.apply_async(
                    args=[kw_id],
                    countdown=delay,
                )

            summary = {
                "advertiser_domain": advertiser.domain,
                "keywords_generated": len(expansion_keywords),
                "new_keywords_added": new_keywords_added,
                "keywords_queued_for_scrape": len(keywords_to_scrape[:20]),
            }

            await job_repo.update_status(
                job.id,
                JobStatus.COMPLETED,
                result_summary=summary,
            )
            await session.commit()

            logger.info(
                f"Expanded keywords for {advertiser.domain}: "
                f"{new_keywords_added} new, {len(keywords_to_scrape)} queued"
            )

            return summary

        except Exception as e:
            logger.exception(f"Error expanding keywords for {advertiser.domain}")
            await job_repo.update_status(
                job.id,
                JobStatus.FAILED,
                error=str(e),
            )
            await session.commit()
            raise


@celery_app.task
def discover_competitor_keywords(advertiser_id: int):
    """
    Find keywords where competitors of this advertiser appear.

    Logic: If competitors advertise on certain keywords,
    our target advertiser might also be relevant there.
    """
    return run_async(_discover_competitor_keywords_async(advertiser_id))


async def _discover_competitor_keywords_async(advertiser_id: int):
    """Async implementation of competitor keyword discovery."""
    async with get_async_db_context() as session:
        advertiser_repo = AdvertiserRepository(session)
        keyword_repo = KeywordRepository(session)
        stats_repo = KeywordAdvertiserStatsRepository(session)
        job_repo = CrawlJobRepository(session)

        advertiser = await advertiser_repo.get_by_id(advertiser_id)
        if not advertiser:
            return {"error": "Advertiser not found"}

        # Create job
        job = await job_repo.create(
            job_type=JobType.KEYWORD_DISCOVERY,
            target=advertiser.domain,
            priority=3,
        )
        await job_repo.update_status(job.id, JobStatus.RUNNING)
        await session.commit()

        try:
            # Get competitors
            competitors = await advertiser_repo.get_competitors(advertiser_id, limit=10)

            # Get our advertiser's keywords
            our_keywords = await advertiser_repo.get_keywords(advertiser_id, limit=500)
            our_keyword_ids = {kw.id for kw in our_keywords}

            # Find competitor keywords we don't have
            new_keyword_ids = set()

            for competitor, shared_count in competitors:
                competitor_keywords = await advertiser_repo.get_keywords(
                    competitor.id,
                    limit=100,
                )
                for kw in competitor_keywords:
                    if kw.id not in our_keyword_ids:
                        new_keyword_ids.add(kw.id)

            # Queue discovered keywords for scraping
            keywords_queued = 0
            for i, kw_id in enumerate(list(new_keyword_ids)[:30]):
                delay = i * random.randint(120, 300)
                scrape_keyword_task.apply_async(
                    args=[kw_id],
                    countdown=delay,
                )
                keywords_queued += 1

            summary = {
                "advertiser_domain": advertiser.domain,
                "competitors_analyzed": len(competitors),
                "potential_keywords_found": len(new_keyword_ids),
                "keywords_queued": keywords_queued,
            }

            await job_repo.update_status(
                job.id,
                JobStatus.COMPLETED,
                result_summary=summary,
            )
            await session.commit()

            logger.info(
                f"Competitor analysis for {advertiser.domain}: "
                f"{len(new_keyword_ids)} potential keywords found"
            )

            return summary

        except Exception as e:
            logger.exception(f"Error in competitor analysis for {advertiser_id}")
            await job_repo.update_status(
                job.id,
                JobStatus.FAILED,
                error=str(e),
            )
            await session.commit()
            raise


@celery_app.task
def update_advertiser_spend_estimates(advertiser_id: int):
    """
    Update spend estimates for an advertiser.

    Args:
        advertiser_id: Advertiser to update
    """
    return run_async(_update_advertiser_spend_async(advertiser_id))


async def _update_advertiser_spend_async(advertiser_id: int):
    """Async implementation of spend estimation update."""
    async with get_async_db_context() as session:
        from sqlalchemy import update as sql_update

        advertiser_repo = AdvertiserRepository(session)
        stats_repo = KeywordAdvertiserStatsRepository(session)

        advertiser = await advertiser_repo.get_by_id(advertiser_id)
        if not advertiser:
            return {"error": "Advertiser not found"}

        # Get all keyword stats for this advertiser
        stats = await stats_repo.get_by_advertiser(advertiser_id, limit=1000)

        if not stats:
            return {"error": "No keyword stats found"}

        estimator = SpendEstimator()
        total_estimated_spend = 0

        for stat in stats:
            # Estimate spend for each keyword
            keyword_spend = estimator.estimate_keyword_spend(
                appearance_count=stat.appearance_count,
                avg_position=float(stat.avg_position or 3),
                days_active=stat.days_active,
            )

            # Update stats with estimates
            stat.estimated_spend = keyword_spend.estimated_spend
            stat.estimated_impressions = keyword_spend.estimated_impressions
            stat.estimated_clicks = keyword_spend.estimated_clicks

            total_estimated_spend += float(keyword_spend.estimated_spend or 0)

        # Update advertiser total
        from src.database.models import Advertiser
        await session.execute(
            sql_update(Advertiser)
            .where(Advertiser.id == advertiser_id)
            .values(estimated_monthly_spend=total_estimated_spend)
        )

        await session.commit()

        logger.info(
            f"Updated spend estimates for {advertiser.domain}: "
            f"${total_estimated_spend:.2f}/month"
        )

        return {
            "advertiser_domain": advertiser.domain,
            "keywords_analyzed": len(stats),
            "estimated_monthly_spend": total_estimated_spend,
        }


@celery_app.task
def update_all_advertiser_stats():
    """
    Periodic task to update stats for all active advertisers.

    Run this via Celery Beat every few hours.
    """
    return run_async(_update_all_advertiser_stats_async())


async def _update_all_advertiser_stats_async():
    """Async implementation of bulk stats update."""
    async with get_async_db_context() as session:
        advertiser_repo = AdvertiserRepository(session)

        advertisers = await advertiser_repo.list_all(is_active=True, limit=500)

        updated = 0
        for advertiser in advertisers:
            # Update keyword count
            await advertiser_repo.update_keyword_count(advertiser.id)
            updated += 1

        await session.commit()

        # Queue spend estimation updates
        for i, advertiser in enumerate(advertisers[:50]):  # Limit to 50
            update_advertiser_spend_estimates.apply_async(
                args=[advertiser.id],
                countdown=i * 10,  # Spread over time
            )

        logger.info(f"Updated stats for {updated} advertisers")
        return {"updated": updated}


@celery_app.task
def continuous_domain_monitor(
    advertiser_id: int,
    interval_hours: int = 24,
):
    """
    Set up continuous monitoring for an advertiser.

    This re-scrapes known keywords and queues itself to run again.
    """
    return run_async(_continuous_domain_monitor_async(advertiser_id, interval_hours))


async def _continuous_domain_monitor_async(advertiser_id: int, interval_hours: int):
    """Async implementation of continuous monitoring."""
    async with get_async_db_context() as session:
        advertiser_repo = AdvertiserRepository(session)
        stats_repo = KeywordAdvertiserStatsRepository(session)

        advertiser = await advertiser_repo.get_by_id(advertiser_id)
        if not advertiser or not advertiser.is_active:
            return {"error": "Advertiser not found or inactive"}

        # Get keywords to monitor
        stats = await stats_repo.get_by_advertiser(advertiser_id, limit=50)

        # Queue scrapes for top keywords
        scraped = 0
        for i, stat in enumerate(stats[:20]):  # Top 20 keywords
            delay = i * random.randint(120, 300)
            scrape_keyword_task.apply_async(
                args=[stat.keyword_id],
                countdown=delay,
            )
            scraped += 1

        # Schedule next monitoring run
        continuous_domain_monitor.apply_async(
            args=[advertiser_id, interval_hours],
            countdown=interval_hours * 3600,
        )

        logger.info(
            f"Monitoring {advertiser.domain}: queued {scraped} keyword scrapes, "
            f"next run in {interval_hours} hours"
        )

        return {
            "advertiser_domain": advertiser.domain,
            "keywords_scraped": scraped,
            "next_run_hours": interval_hours,
        }
