"""Data access layer for database operations."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload

from src.database.models import (
    AdAppearance,
    Advertiser,
    CrawlJob,
    DeviceType,
    JobStatus,
    JobType,
    Keyword,
    KeywordAdvertiserStats,
    KeywordSource,
    ProxyHealth,
)


class KeywordRepository:
    """Repository for keyword operations."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    async def create(
        self,
        keyword: str,
        source: KeywordSource = KeywordSource.SEED,
        category: Optional[str] = None,
        crawl_priority: int = 5,
        search_volume: Optional[int] = None,
        cpc_estimate: Optional[Decimal] = None,
    ) -> Keyword:
        """Create a new keyword."""
        kw = Keyword(
            keyword=keyword.lower().strip(),
            source=source,
            category=category,
            crawl_priority=crawl_priority,
            search_volume=search_volume,
            cpc_estimate=cpc_estimate,
        )
        self.session.add(kw)
        await self.session.flush()
        return kw

    async def get_by_id(self, keyword_id: int) -> Optional[Keyword]:
        """Get keyword by ID."""
        result = await self.session.execute(
            select(Keyword).where(Keyword.id == keyword_id)
        )
        return result.scalar_one_or_none()

    async def get_by_keyword(self, keyword: str) -> Optional[Keyword]:
        """Get keyword by text."""
        result = await self.session.execute(
            select(Keyword).where(Keyword.keyword == keyword.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        keyword: str,
        source: KeywordSource = KeywordSource.SEED,
        **kwargs
    ) -> Tuple[Keyword, bool]:
        """Get existing keyword or create new one. Returns (keyword, created)."""
        existing = await self.get_by_keyword(keyword)
        if existing:
            return existing, False
        new_kw = await self.create(keyword, source=source, **kwargs)
        return new_kw, True

    async def list_all(
        self,
        is_active: Optional[bool] = None,
        source: Optional[KeywordSource] = None,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Keyword]:
        """List keywords with optional filters."""
        query = select(Keyword)

        if is_active is not None:
            query = query.where(Keyword.is_active == is_active)
        if source is not None:
            query = query.where(Keyword.source == source)
        if category is not None:
            query = query.where(Keyword.category == category)

        query = query.order_by(Keyword.crawl_priority.desc(), Keyword.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_due_for_crawl(self, limit: int = 50) -> Sequence[Keyword]:
        """Get keywords that are due for re-crawling."""
        now = datetime.now(timezone.utc)
        query = select(Keyword).where(
            and_(
                Keyword.is_active == True,
                or_(
                    Keyword.last_crawled_at.is_(None),
                    Keyword.last_crawled_at + func.make_interval(0, 0, 0, 0, Keyword.crawl_frequency_hours, 0, 0) < now
                )
            )
        ).order_by(
            Keyword.crawl_priority.desc(),
            Keyword.last_crawled_at.asc().nulls_first()
        ).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def update_crawled(self, keyword_id: int) -> None:
        """Update last crawled timestamp."""
        await self.session.execute(
            update(Keyword)
            .where(Keyword.id == keyword_id)
            .values(last_crawled_at=datetime.now(timezone.utc))
        )

    async def bulk_create(self, keywords: List[str], source: KeywordSource = KeywordSource.SEED) -> List[Keyword]:
        """Bulk create keywords, skipping existing ones."""
        created = []
        for kw in keywords:
            _, was_created = await self.get_or_create(kw, source=source)
            if was_created:
                created.append(kw)
        return created


class AdvertiserRepository:
    """Repository for advertiser operations."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    async def create(
        self,
        domain: str,
        root_domain: str,
        company_name: Optional[str] = None,
        discovery_keyword_id: Optional[int] = None,
    ) -> Advertiser:
        """Create a new advertiser."""
        advertiser = Advertiser(
            domain=domain.lower().strip(),
            root_domain=root_domain.lower().strip(),
            company_name=company_name,
            discovery_keyword_id=discovery_keyword_id,
        )
        self.session.add(advertiser)
        await self.session.flush()
        return advertiser

    async def get_by_id(self, advertiser_id: int) -> Optional[Advertiser]:
        """Get advertiser by ID."""
        result = await self.session.execute(
            select(Advertiser).where(Advertiser.id == advertiser_id)
        )
        return result.scalar_one_or_none()

    async def get_by_domain(self, domain: str) -> Optional[Advertiser]:
        """Get advertiser by domain."""
        result = await self.session.execute(
            select(Advertiser).where(Advertiser.domain == domain.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        domain: str,
        root_domain: str,
        **kwargs
    ) -> Tuple[Advertiser, bool]:
        """Get existing advertiser or create new one."""
        existing = await self.get_by_domain(domain)
        if existing:
            return existing, False
        new_adv = await self.create(domain=domain, root_domain=root_domain, **kwargs)
        return new_adv, True

    async def list_all(
        self,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Advertiser]:
        """List advertisers with optional filters."""
        query = select(Advertiser)

        if is_active is not None:
            query = query.where(Advertiser.is_active == is_active)

        query = query.order_by(
            Advertiser.total_keywords_count.desc(),
            Advertiser.last_seen_at.desc()
        )
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def search_by_domain(self, domain_pattern: str, limit: int = 20) -> Sequence[Advertiser]:
        """Search advertisers by domain pattern."""
        result = await self.session.execute(
            select(Advertiser)
            .where(Advertiser.domain.ilike(f"%{domain_pattern}%"))
            .limit(limit)
        )
        return result.scalars().all()

    async def update_last_seen(self, advertiser_id: int) -> None:
        """Update last seen timestamp."""
        await self.session.execute(
            update(Advertiser)
            .where(Advertiser.id == advertiser_id)
            .values(last_seen_at=datetime.now(timezone.utc))
        )

    async def update_keyword_count(self, advertiser_id: int) -> None:
        """Update total keywords count for an advertiser."""
        subquery = select(func.count(func.distinct(KeywordAdvertiserStats.keyword_id))).where(
            KeywordAdvertiserStats.advertiser_id == advertiser_id
        ).scalar_subquery()

        await self.session.execute(
            update(Advertiser)
            .where(Advertiser.id == advertiser_id)
            .values(total_keywords_count=subquery)
        )

    async def get_keywords(
        self,
        advertiser_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> Sequence[Keyword]:
        """Get all keywords an advertiser appears on."""
        query = select(Keyword).join(
            KeywordAdvertiserStats,
            Keyword.id == KeywordAdvertiserStats.keyword_id
        ).where(
            KeywordAdvertiserStats.advertiser_id == advertiser_id
        ).order_by(
            KeywordAdvertiserStats.appearance_count.desc()
        ).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_competitors(
        self,
        advertiser_id: int,
        limit: int = 20
    ) -> Sequence[Tuple[Advertiser, int]]:
        """Get competitors (advertisers appearing on same keywords)."""
        # Get keywords this advertiser appears on
        keyword_subquery = select(KeywordAdvertiserStats.keyword_id).where(
            KeywordAdvertiserStats.advertiser_id == advertiser_id
        ).subquery()

        # Find other advertisers on those keywords
        query = select(
            Advertiser,
            func.count(KeywordAdvertiserStats.keyword_id).label("shared_keywords")
        ).join(
            KeywordAdvertiserStats,
            Advertiser.id == KeywordAdvertiserStats.advertiser_id
        ).where(
            and_(
                KeywordAdvertiserStats.keyword_id.in_(select(keyword_subquery)),
                KeywordAdvertiserStats.advertiser_id != advertiser_id
            )
        ).group_by(Advertiser.id).order_by(
            func.count(KeywordAdvertiserStats.keyword_id).desc()
        ).limit(limit)

        result = await self.session.execute(query)
        return [(row[0], row[1]) for row in result.all()]


class AdAppearanceRepository:
    """Repository for ad appearance operations."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    async def create(
        self,
        keyword_id: int,
        advertiser_id: int,
        position: int,
        headline: str,
        display_url: str,
        final_url: str,
        description: Optional[str] = None,
        extensions: Optional[dict] = None,
        geo_location: str = "US",
        device_type: DeviceType = DeviceType.DESKTOP,
        raw_html: Optional[str] = None,
    ) -> AdAppearance:
        """Create a new ad appearance record."""
        appearance = AdAppearance(
            keyword_id=keyword_id,
            advertiser_id=advertiser_id,
            position=position,
            headline=headline,
            description=description,
            display_url=display_url,
            final_url=final_url,
            extensions=extensions,
            geo_location=geo_location,
            device_type=device_type,
            raw_html=raw_html,
        )
        self.session.add(appearance)
        await self.session.flush()
        return appearance

    async def get_by_keyword(
        self,
        keyword_id: int,
        limit: int = 100,
        offset: int = 0,
        since: Optional[datetime] = None,
    ) -> Sequence[AdAppearance]:
        """Get ad appearances for a keyword."""
        query = select(AdAppearance).where(AdAppearance.keyword_id == keyword_id)

        if since:
            query = query.where(AdAppearance.scraped_at >= since)

        query = query.order_by(AdAppearance.scraped_at.desc()).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_advertiser(
        self,
        advertiser_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[AdAppearance]:
        """Get ad appearances for an advertiser."""
        query = select(AdAppearance).where(
            AdAppearance.advertiser_id == advertiser_id
        ).order_by(
            AdAppearance.scraped_at.desc()
        ).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_unique_ads(
        self,
        advertiser_id: int,
        limit: int = 50,
    ) -> Sequence[AdAppearance]:
        """Get unique ad variations for an advertiser."""
        # Use distinct on headline to get unique ads
        query = select(AdAppearance).where(
            AdAppearance.advertiser_id == advertiser_id
        ).distinct(
            AdAppearance.headline
        ).order_by(
            AdAppearance.headline,
            AdAppearance.scraped_at.desc()
        ).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()


class KeywordAdvertiserStatsRepository:
    """Repository for keyword-advertiser statistics."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    async def get_or_create(
        self,
        keyword_id: int,
        advertiser_id: int,
    ) -> KeywordAdvertiserStats:
        """Get or create stats record."""
        result = await self.session.execute(
            select(KeywordAdvertiserStats).where(
                and_(
                    KeywordAdvertiserStats.keyword_id == keyword_id,
                    KeywordAdvertiserStats.advertiser_id == advertiser_id,
                )
            )
        )
        stats = result.scalar_one_or_none()

        if stats:
            return stats

        stats = KeywordAdvertiserStats(
            keyword_id=keyword_id,
            advertiser_id=advertiser_id,
        )
        self.session.add(stats)
        await self.session.flush()
        return stats

    async def update_stats(
        self,
        keyword_id: int,
        advertiser_id: int,
        position: int,
    ) -> KeywordAdvertiserStats:
        """Update statistics with a new appearance."""
        stats = await self.get_or_create(keyword_id, advertiser_id)

        # Update appearance count
        stats.appearance_count += 1

        # Update position distribution
        if stats.position_distribution is None:
            stats.position_distribution = {}
        pos_key = str(position)
        stats.position_distribution[pos_key] = stats.position_distribution.get(pos_key, 0) + 1

        # Calculate new average position
        total_positions = sum(
            int(k) * v for k, v in stats.position_distribution.items()
        )
        stats.avg_position = Decimal(str(total_positions / stats.appearance_count))

        # Update last seen
        stats.last_seen_at = datetime.now(timezone.utc)

        # Update days active
        days_diff = (stats.last_seen_at - stats.first_seen_at).days
        stats.days_active = max(1, days_diff)

        await self.session.flush()
        return stats

    async def get_by_keyword(
        self,
        keyword_id: int,
        limit: int = 100,
    ) -> Sequence[KeywordAdvertiserStats]:
        """Get stats for all advertisers on a keyword."""
        query = select(KeywordAdvertiserStats).where(
            KeywordAdvertiserStats.keyword_id == keyword_id
        ).order_by(
            KeywordAdvertiserStats.appearance_count.desc()
        ).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_advertiser(
        self,
        advertiser_id: int,
        limit: int = 100,
    ) -> Sequence[KeywordAdvertiserStats]:
        """Get stats for all keywords an advertiser appears on."""
        query = select(KeywordAdvertiserStats).where(
            KeywordAdvertiserStats.advertiser_id == advertiser_id
        ).order_by(
            KeywordAdvertiserStats.appearance_count.desc()
        ).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()


class CrawlJobRepository:
    """Repository for crawl job operations."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    async def create(
        self,
        job_type: JobType,
        target: str,
        priority: int = 5,
        scheduled_for: Optional[datetime] = None,
    ) -> CrawlJob:
        """Create a new crawl job."""
        job = CrawlJob(
            job_type=job_type,
            target=target,
            priority=priority,
            scheduled_for=scheduled_for,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_by_id(self, job_id: int) -> Optional[CrawlJob]:
        """Get job by ID."""
        result = await self.session.execute(
            select(CrawlJob).where(CrawlJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        status: Optional[JobStatus] = None,
        job_type: Optional[JobType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[CrawlJob]:
        """List jobs with optional filters."""
        query = select(CrawlJob)

        if status:
            query = query.where(CrawlJob.status == status)
        if job_type:
            query = query.where(CrawlJob.job_type == job_type)

        query = query.order_by(
            CrawlJob.priority.desc(),
            CrawlJob.created_at.desc()
        ).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def update_status(
        self,
        job_id: int,
        status: JobStatus,
        error: Optional[str] = None,
        result_summary: Optional[dict] = None,
    ) -> None:
        """Update job status."""
        values = {"status": status}

        if status == JobStatus.RUNNING:
            values["started_at"] = datetime.now(timezone.utc)
            values["attempts"] = CrawlJob.attempts + 1
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.BLOCKED):
            values["completed_at"] = datetime.now(timezone.utc)

        if error:
            values["last_error"] = error
        if result_summary:
            values["result_summary"] = result_summary

        await self.session.execute(
            update(CrawlJob).where(CrawlJob.id == job_id).values(**values)
        )

    async def get_stats(self) -> dict:
        """Get job statistics."""
        result = await self.session.execute(
            select(
                CrawlJob.status,
                func.count(CrawlJob.id)
            ).group_by(CrawlJob.status)
        )

        stats = {status.value: 0 for status in JobStatus}
        for row in result.all():
            stats[row[0].value] = row[1]

        return stats


class ProxyHealthRepository:
    """Repository for proxy health operations."""

    def __init__(self, session: Session | AsyncSession):
        self.session = session

    async def get_or_create(
        self,
        proxy_url: str,
        provider: str,
    ) -> ProxyHealth:
        """Get or create proxy health record."""
        result = await self.session.execute(
            select(ProxyHealth).where(ProxyHealth.proxy_url == proxy_url)
        )
        proxy = result.scalar_one_or_none()

        if proxy:
            return proxy

        proxy = ProxyHealth(proxy_url=proxy_url, provider=provider)
        self.session.add(proxy)
        await self.session.flush()
        return proxy

    async def get_healthy_proxies(
        self,
        provider: Optional[str] = None,
        min_success_rate: float = 50.0,
        limit: int = 10,
    ) -> Sequence[ProxyHealth]:
        """Get healthy proxies for use."""
        query = select(ProxyHealth).where(
            and_(
                ProxyHealth.is_active == True,
                or_(
                    ProxyHealth.last_blocked_at.is_(None),
                    ProxyHealth.last_blocked_at < datetime.now(timezone.utc) - timedelta(hours=1)
                )
            )
        )

        if provider:
            query = query.where(ProxyHealth.provider == provider)

        # Order by success rate and recency
        query = query.order_by(
            ProxyHealth.last_used_at.asc().nulls_first(),
            ProxyHealth.success_count.desc()
        ).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def mark_success(
        self,
        proxy_url: str,
        response_time_ms: int,
    ) -> None:
        """Record successful proxy use."""
        await self.session.execute(
            update(ProxyHealth)
            .where(ProxyHealth.proxy_url == proxy_url)
            .values(
                success_count=ProxyHealth.success_count + 1,
                last_used_at=datetime.now(timezone.utc),
                avg_response_time_ms=response_time_ms,  # Simplified: just use latest
            )
        )

    async def mark_failure(self, proxy_url: str) -> None:
        """Record proxy failure."""
        await self.session.execute(
            update(ProxyHealth)
            .where(ProxyHealth.proxy_url == proxy_url)
            .values(
                failure_count=ProxyHealth.failure_count + 1,
                last_used_at=datetime.now(timezone.utc),
            )
        )

    async def mark_blocked(self, proxy_url: str) -> None:
        """Record proxy being blocked."""
        await self.session.execute(
            update(ProxyHealth)
            .where(ProxyHealth.proxy_url == proxy_url)
            .values(
                block_count=ProxyHealth.block_count + 1,
                last_blocked_at=datetime.now(timezone.utc),
                last_used_at=datetime.now(timezone.utc),
            )
        )

    async def get_health_report(self) -> dict:
        """Get overall proxy health statistics."""
        result = await self.session.execute(
            select(
                ProxyHealth.provider,
                func.count(ProxyHealth.id).label("total"),
                func.sum(ProxyHealth.success_count).label("successes"),
                func.sum(ProxyHealth.failure_count).label("failures"),
                func.sum(ProxyHealth.block_count).label("blocks"),
                func.avg(ProxyHealth.avg_response_time_ms).label("avg_response_time"),
            ).where(ProxyHealth.is_active == True).group_by(ProxyHealth.provider)
        )

        report = {}
        for row in result.all():
            total_requests = (row.successes or 0) + (row.failures or 0) + (row.blocks or 0)
            success_rate = (row.successes or 0) / total_requests * 100 if total_requests > 0 else 0

            report[row.provider] = {
                "total_proxies": row.total,
                "success_count": row.successes or 0,
                "failure_count": row.failures or 0,
                "block_count": row.blocks or 0,
                "success_rate": round(success_rate, 2),
                "avg_response_time_ms": int(row.avg_response_time or 0),
            }

        return report
