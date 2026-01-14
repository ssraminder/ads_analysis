"""Track domain appearances and analyze trends."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import logging

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AdAppearance, Advertiser, Keyword, KeywordAdvertiserStats

logger = logging.getLogger(__name__)


@dataclass
class PositionTrend:
    """Position trend data for an advertiser on a keyword."""
    keyword: str
    current_avg_position: float
    previous_avg_position: Optional[float]
    position_change: Optional[float]
    appearance_trend: str  # "increasing", "decreasing", "stable"


@dataclass
class DomainStats:
    """Comprehensive stats for a domain."""
    domain: str
    total_keywords: int
    total_appearances: int
    avg_position: float
    top_keywords: List[Tuple[str, int]]  # (keyword, appearances)
    estimated_monthly_spend: Decimal
    first_seen: datetime
    last_seen: datetime
    days_active: int


class DomainTracker:
    """Track and analyze domain advertising behavior."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_domain_stats(self, advertiser_id: int) -> Optional[DomainStats]:
        """Get comprehensive statistics for a domain."""
        # Get advertiser
        result = await self.session.execute(
            select(Advertiser).where(Advertiser.id == advertiser_id)
        )
        advertiser = result.scalar_one_or_none()

        if not advertiser:
            return None

        # Get keyword count
        keyword_count_result = await self.session.execute(
            select(func.count(func.distinct(KeywordAdvertiserStats.keyword_id)))
            .where(KeywordAdvertiserStats.advertiser_id == advertiser_id)
        )
        total_keywords = keyword_count_result.scalar() or 0

        # Get total appearances
        appearances_result = await self.session.execute(
            select(func.sum(KeywordAdvertiserStats.appearance_count))
            .where(KeywordAdvertiserStats.advertiser_id == advertiser_id)
        )
        total_appearances = appearances_result.scalar() or 0

        # Get average position
        avg_pos_result = await self.session.execute(
            select(func.avg(KeywordAdvertiserStats.avg_position))
            .where(KeywordAdvertiserStats.advertiser_id == advertiser_id)
        )
        avg_position = float(avg_pos_result.scalar() or 0)

        # Get top keywords
        top_kw_result = await self.session.execute(
            select(Keyword.keyword, KeywordAdvertiserStats.appearance_count)
            .join(Keyword, Keyword.id == KeywordAdvertiserStats.keyword_id)
            .where(KeywordAdvertiserStats.advertiser_id == advertiser_id)
            .order_by(KeywordAdvertiserStats.appearance_count.desc())
            .limit(10)
        )
        top_keywords = [(row[0], row[1]) for row in top_kw_result.all()]

        # Get date range
        date_result = await self.session.execute(
            select(
                func.min(KeywordAdvertiserStats.first_seen_at),
                func.max(KeywordAdvertiserStats.last_seen_at)
            )
            .where(KeywordAdvertiserStats.advertiser_id == advertiser_id)
        )
        dates = date_result.one()
        first_seen = dates[0] or advertiser.first_seen_at
        last_seen = dates[1] or advertiser.last_seen_at

        days_active = (last_seen - first_seen).days + 1

        return DomainStats(
            domain=advertiser.domain,
            total_keywords=total_keywords,
            total_appearances=total_appearances,
            avg_position=round(avg_position, 2),
            top_keywords=top_keywords,
            estimated_monthly_spend=advertiser.estimated_monthly_spend or Decimal("0"),
            first_seen=first_seen,
            last_seen=last_seen,
            days_active=days_active,
        )

    async def get_position_history(
        self,
        advertiser_id: int,
        keyword_id: int,
        days: int = 30,
    ) -> List[Tuple[datetime, float]]:
        """Get position history for an advertiser on a keyword."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.session.execute(
            select(
                func.date_trunc('day', AdAppearance.scraped_at).label('day'),
                func.avg(AdAppearance.position).label('avg_pos')
            )
            .where(
                and_(
                    AdAppearance.advertiser_id == advertiser_id,
                    AdAppearance.keyword_id == keyword_id,
                    AdAppearance.scraped_at >= cutoff,
                )
            )
            .group_by(func.date_trunc('day', AdAppearance.scraped_at))
            .order_by(func.date_trunc('day', AdAppearance.scraped_at))
        )

        return [(row.day, float(row.avg_pos)) for row in result.all()]

    async def analyze_position_trends(
        self,
        advertiser_id: int,
        days_current: int = 7,
        days_previous: int = 7,
    ) -> List[PositionTrend]:
        """Analyze position trends comparing recent vs previous period."""
        now = datetime.now(timezone.utc)
        current_start = now - timedelta(days=days_current)
        previous_start = current_start - timedelta(days=days_previous)

        # Get current period stats
        current_result = await self.session.execute(
            select(
                Keyword.keyword,
                KeywordAdvertiserStats.keyword_id,
                func.avg(AdAppearance.position).label('avg_pos'),
                func.count(AdAppearance.id).label('appearances')
            )
            .join(Keyword, Keyword.id == KeywordAdvertiserStats.keyword_id)
            .join(AdAppearance, and_(
                AdAppearance.keyword_id == KeywordAdvertiserStats.keyword_id,
                AdAppearance.advertiser_id == KeywordAdvertiserStats.advertiser_id,
            ))
            .where(
                and_(
                    KeywordAdvertiserStats.advertiser_id == advertiser_id,
                    AdAppearance.scraped_at >= current_start,
                )
            )
            .group_by(Keyword.keyword, KeywordAdvertiserStats.keyword_id)
        )
        current_stats = {row[1]: (row[0], float(row[2]), row[3]) for row in current_result.all()}

        # Get previous period stats
        previous_result = await self.session.execute(
            select(
                KeywordAdvertiserStats.keyword_id,
                func.avg(AdAppearance.position).label('avg_pos'),
                func.count(AdAppearance.id).label('appearances')
            )
            .join(AdAppearance, and_(
                AdAppearance.keyword_id == KeywordAdvertiserStats.keyword_id,
                AdAppearance.advertiser_id == KeywordAdvertiserStats.advertiser_id,
            ))
            .where(
                and_(
                    KeywordAdvertiserStats.advertiser_id == advertiser_id,
                    AdAppearance.scraped_at >= previous_start,
                    AdAppearance.scraped_at < current_start,
                )
            )
            .group_by(KeywordAdvertiserStats.keyword_id)
        )
        previous_stats = {row[0]: (float(row[1]), row[2]) for row in previous_result.all()}

        # Calculate trends
        trends = []
        for keyword_id, (keyword, current_pos, current_apps) in current_stats.items():
            prev = previous_stats.get(keyword_id)

            if prev:
                prev_pos, prev_apps = prev
                position_change = current_pos - prev_pos

                if current_apps > prev_apps * 1.2:
                    trend = "increasing"
                elif current_apps < prev_apps * 0.8:
                    trend = "decreasing"
                else:
                    trend = "stable"
            else:
                prev_pos = None
                position_change = None
                trend = "new"

            trends.append(PositionTrend(
                keyword=keyword,
                current_avg_position=round(current_pos, 2),
                previous_avg_position=round(prev_pos, 2) if prev_pos else None,
                position_change=round(position_change, 2) if position_change else None,
                appearance_trend=trend,
            ))

        return sorted(trends, key=lambda t: t.current_avg_position)

    async def get_new_keywords(
        self,
        advertiser_id: int,
        days: int = 7,
    ) -> List[Tuple[str, datetime]]:
        """Find keywords an advertiser newly appeared on."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.session.execute(
            select(Keyword.keyword, KeywordAdvertiserStats.first_seen_at)
            .join(Keyword, Keyword.id == KeywordAdvertiserStats.keyword_id)
            .where(
                and_(
                    KeywordAdvertiserStats.advertiser_id == advertiser_id,
                    KeywordAdvertiserStats.first_seen_at >= cutoff,
                )
            )
            .order_by(KeywordAdvertiserStats.first_seen_at.desc())
        )

        return [(row[0], row[1]) for row in result.all()]

    async def get_dropped_keywords(
        self,
        advertiser_id: int,
        days_inactive: int = 14,
    ) -> List[Tuple[str, datetime]]:
        """Find keywords an advertiser stopped appearing on."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_inactive)

        result = await self.session.execute(
            select(Keyword.keyword, KeywordAdvertiserStats.last_seen_at)
            .join(Keyword, Keyword.id == KeywordAdvertiserStats.keyword_id)
            .where(
                and_(
                    KeywordAdvertiserStats.advertiser_id == advertiser_id,
                    KeywordAdvertiserStats.last_seen_at < cutoff,
                    KeywordAdvertiserStats.appearance_count > 1,  # Had some activity
                )
            )
            .order_by(KeywordAdvertiserStats.last_seen_at.desc())
        )

        return [(row[0], row[1]) for row in result.all()]

    async def compare_competitors(
        self,
        advertiser_id: int,
        competitor_ids: List[int],
    ) -> Dict[str, dict]:
        """Compare domain metrics against competitors."""
        all_ids = [advertiser_id] + competitor_ids

        results = {}

        for adv_id in all_ids:
            stats = await self.get_domain_stats(adv_id)
            if stats:
                results[stats.domain] = {
                    "total_keywords": stats.total_keywords,
                    "total_appearances": stats.total_appearances,
                    "avg_position": stats.avg_position,
                    "estimated_spend": float(stats.estimated_monthly_spend),
                }

        return results
