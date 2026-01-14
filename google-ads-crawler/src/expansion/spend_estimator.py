"""Estimate advertiser spend based on observable data."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class SpendEstimate:
    """Spend estimation results."""
    estimated_impressions: int
    estimated_clicks: int
    estimated_ctr: float
    estimated_cpc: Decimal
    estimated_spend: Decimal
    confidence: str  # "low", "medium", "high"


class SpendEstimator:
    """
    Estimate advertiser spend based on observable data.

    This uses industry benchmarks and heuristics to estimate spend
    from position data and appearance frequency.
    """

    # CTR by position (industry averages)
    POSITION_CTR = {
        1: 0.065,  # ~6.5% CTR for position 1
        2: 0.040,  # ~4% CTR for position 2
        3: 0.025,  # ~2.5% CTR for position 3
        4: 0.015,  # ~1.5% CTR for position 4
        5: 0.010,  # ~1% CTR for bottom ads
        6: 0.008,
        7: 0.005,
    }

    # Default CPC by industry (USD)
    INDUSTRY_CPC = {
        "legal": 5.00,
        "insurance": 4.50,
        "finance": 4.00,
        "medical": 3.50,
        "software": 3.00,
        "ecommerce": 1.50,
        "education": 2.00,
        "travel": 1.75,
        "real_estate": 2.50,
        "default": 2.00,
    }

    # Default search volume estimate per keyword per day
    # This is very approximate - real data should be used if available
    DEFAULT_DAILY_SEARCHES = 100

    def __init__(
        self,
        default_cpc: Optional[float] = None,
        daily_search_multiplier: float = 1.0,
    ):
        self.default_cpc = default_cpc or self.INDUSTRY_CPC["default"]
        self.daily_search_multiplier = daily_search_multiplier

    def estimate_keyword_spend(
        self,
        appearance_count: int,
        avg_position: float,
        days_active: int = 30,
        search_volume: Optional[int] = None,
        cpc_estimate: Optional[float] = None,
        total_scrapes: Optional[int] = None,
    ) -> SpendEstimate:
        """
        Estimate spend for one advertiser on one keyword.

        Args:
            appearance_count: Number of times ad appeared in scrapes
            avg_position: Average ad position
            days_active: Number of days the ad has been active
            search_volume: Monthly search volume (optional)
            cpc_estimate: Estimated CPC (optional)
            total_scrapes: Total number of scrapes for this keyword (for impression share)

        Returns:
            SpendEstimate with calculated metrics
        """
        # Estimate impression share
        if total_scrapes and total_scrapes > 0:
            impression_share = appearance_count / total_scrapes
        else:
            # Assume 50% impression share if we don't have data
            impression_share = 0.5

        # Estimate monthly searches
        if search_volume:
            monthly_searches = search_volume
        else:
            monthly_searches = self.DEFAULT_DAILY_SEARCHES * 30 * self.daily_search_multiplier

        # Estimate impressions
        estimated_impressions = int(monthly_searches * impression_share)

        # Get CTR based on position
        position_bucket = min(7, max(1, int(avg_position)))
        ctr = self.POSITION_CTR.get(position_bucket, 0.01)

        # Estimate clicks
        estimated_clicks = int(estimated_impressions * ctr)

        # Get CPC
        cpc = Decimal(str(cpc_estimate or self.default_cpc))

        # Calculate spend
        estimated_spend = Decimal(str(estimated_clicks)) * cpc

        # Determine confidence level
        if search_volume and cpc_estimate and total_scrapes:
            confidence = "high"
        elif search_volume or cpc_estimate:
            confidence = "medium"
        else:
            confidence = "low"

        return SpendEstimate(
            estimated_impressions=estimated_impressions,
            estimated_clicks=estimated_clicks,
            estimated_ctr=round(ctr * 100, 2),
            estimated_cpc=cpc,
            estimated_spend=round(estimated_spend, 2),
            confidence=confidence,
        )

    def estimate_total_monthly_spend(
        self,
        keyword_estimates: list[SpendEstimate],
    ) -> Decimal:
        """
        Sum estimated spend across all keywords.

        Args:
            keyword_estimates: List of SpendEstimate objects

        Returns:
            Total estimated monthly spend
        """
        return sum(
            (e.estimated_spend for e in keyword_estimates),
            Decimal("0.00")
        )

    def estimate_by_position_distribution(
        self,
        position_distribution: dict,
        days_active: int = 30,
        search_volume: Optional[int] = None,
        cpc_estimate: Optional[float] = None,
    ) -> SpendEstimate:
        """
        Estimate spend using position distribution data.

        Args:
            position_distribution: Dict of {position: count}
            days_active: Days the advertiser has been active
            search_volume: Optional monthly search volume
            cpc_estimate: Optional CPC estimate

        Returns:
            SpendEstimate
        """
        if not position_distribution:
            return SpendEstimate(
                estimated_impressions=0,
                estimated_clicks=0,
                estimated_ctr=0.0,
                estimated_cpc=Decimal("0.00"),
                estimated_spend=Decimal("0.00"),
                confidence="low",
            )

        total_appearances = sum(position_distribution.values())

        # Calculate weighted average CTR
        weighted_ctr = 0.0
        for pos_str, count in position_distribution.items():
            pos = int(pos_str)
            pos_bucket = min(7, max(1, pos))
            ctr = self.POSITION_CTR.get(pos_bucket, 0.01)
            weighted_ctr += ctr * (count / total_appearances)

        # Estimate monthly searches
        if search_volume:
            monthly_searches = search_volume
        else:
            monthly_searches = self.DEFAULT_DAILY_SEARCHES * 30 * self.daily_search_multiplier

        # Assume some impression share based on appearances
        estimated_impression_share = min(0.8, total_appearances / (days_active or 1) / 3)

        estimated_impressions = int(monthly_searches * estimated_impression_share)
        estimated_clicks = int(estimated_impressions * weighted_ctr)

        cpc = Decimal(str(cpc_estimate or self.default_cpc))
        estimated_spend = Decimal(str(estimated_clicks)) * cpc

        confidence = "medium" if search_volume or cpc_estimate else "low"

        return SpendEstimate(
            estimated_impressions=estimated_impressions,
            estimated_clicks=estimated_clicks,
            estimated_ctr=round(weighted_ctr * 100, 2),
            estimated_cpc=cpc,
            estimated_spend=round(estimated_spend, 2),
            confidence=confidence,
        )


class IndustrySpendBenchmarks:
    """Industry spend benchmarks for comparison."""

    # Average monthly ad spend by company size (USD)
    SPEND_BY_SIZE = {
        "small": (1000, 10000),      # Small business
        "medium": (10000, 50000),    # Medium business
        "large": (50000, 500000),    # Large business
        "enterprise": (500000, 5000000),  # Enterprise
    }

    # Keywords count by advertiser activity level
    KEYWORD_TIERS = {
        "light": (1, 10),
        "moderate": (10, 50),
        "heavy": (50, 200),
        "aggressive": (200, 1000),
    }

    @classmethod
    def categorize_advertiser(
        cls,
        estimated_spend: Decimal,
        keyword_count: int,
    ) -> dict:
        """Categorize an advertiser based on spend and keyword count."""
        # Determine spend tier
        spend_tier = "unknown"
        spend_value = float(estimated_spend)
        for tier, (low, high) in cls.SPEND_BY_SIZE.items():
            if low <= spend_value < high:
                spend_tier = tier
                break

        # Determine activity tier
        activity_tier = "unknown"
        for tier, (low, high) in cls.KEYWORD_TIERS.items():
            if low <= keyword_count < high:
                activity_tier = tier
                break

        return {
            "spend_tier": spend_tier,
            "activity_tier": activity_tier,
            "estimated_monthly_spend": float(estimated_spend),
            "keyword_count": keyword_count,
        }
