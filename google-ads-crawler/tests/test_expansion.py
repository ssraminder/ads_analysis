"""Tests for keyword expansion."""

import pytest
from decimal import Decimal

from src.expansion.keyword_generator import KeywordExpander
from src.expansion.spend_estimator import SpendEstimator, SpendEstimate


class TestKeywordExpander:
    """Tests for KeywordExpander class."""

    @pytest.fixture
    def expander(self):
        """Create expander with sample data."""
        return KeywordExpander(
            domain="shoestore.com",
            company_name="ShoeStore",
            existing_keywords=[
                "buy shoes online",
                "running shoes",
                "best athletic shoes",
                "shoe sale",
            ],
            competitors=["footlocker.com", "zappos.com"],
        )

    def test_extract_brand_from_domain(self):
        """Test brand extraction from domain."""
        expander = KeywordExpander(domain="my-shoe-store.com")
        assert expander.company_name == "my shoe store"

    def test_extract_keyword_themes(self, expander):
        """Test theme extraction from keywords."""
        themes = expander._themes
        assert "shoes" in themes
        # "buy", "online", etc. are common but might be filtered

    def test_generate_brand_keywords(self, expander):
        """Test brand keyword generation."""
        brand_keywords = expander._generate_brand_keywords()
        assert "ShoeStore" in brand_keywords
        assert "ShoeStore reviews" in brand_keywords
        assert "ShoeStore pricing" in brand_keywords

    def test_generate_longtail_variations(self, expander):
        """Test long-tail keyword generation."""
        longtail = expander._generate_longtail_variations()
        # Should have variations with modifiers
        found_prefix = any("best" in kw or "cheap" in kw for kw in longtail)
        found_suffix = any("near me" in kw or "online" in kw for kw in longtail)
        assert found_prefix or found_suffix

    def test_generate_comparison_keywords(self, expander):
        """Test competitor comparison keyword generation."""
        comparison = expander._generate_comparison_keywords()
        # Should include competitor comparisons
        assert any("footlocker" in kw.lower() for kw in comparison)
        assert any("vs" in kw.lower() or "alternative" in kw.lower() for kw in comparison)

    def test_generate_expansion_keywords(self, expander):
        """Test full expansion keyword generation."""
        keywords = expander.generate_expansion_keywords(max_keywords=50)
        assert len(keywords) > 0
        assert len(keywords) <= 50

        # Should not include existing keywords
        for existing in expander.existing_keywords:
            assert existing.lower() not in [k.lower() for k in keywords]

    def test_clean_keywords(self, expander):
        """Test keyword cleaning."""
        dirty_keywords = {
            "  test keyword  ",
            "UPPERCASE KEYWORD",
            "ab",  # Too short
            "this is a very very very long keyword that should probably be filtered out",
            "keyword with special!chars",
            "valid keyword",
        }

        cleaned = expander._clean_keywords(dirty_keywords)

        assert "test keyword" in cleaned
        assert "uppercase keyword" in cleaned
        assert "valid keyword" in cleaned
        assert "ab" not in cleaned
        assert not any(len(k.split()) > 8 for k in cleaned)

    def test_prioritize_keywords(self, expander):
        """Test keyword prioritization."""
        keywords = [
            "random keyword",
            "ShoeStore reviews",  # Brand mention
            "buy running shoes",  # Theme + buying intent
            "cheap shoes online",  # Buying intent
        ]

        prioritized = expander._prioritize_keywords(keywords)

        # Brand mention should be highest priority
        assert prioritized[0] == "ShoeStore reviews"


class TestSpendEstimator:
    """Tests for SpendEstimator class."""

    @pytest.fixture
    def estimator(self):
        """Create estimator instance."""
        return SpendEstimator()

    def test_estimate_keyword_spend(self, estimator):
        """Test basic spend estimation."""
        estimate = estimator.estimate_keyword_spend(
            appearance_count=10,
            avg_position=2.5,
            days_active=30,
        )

        assert isinstance(estimate, SpendEstimate)
        assert estimate.estimated_impressions > 0
        assert estimate.estimated_clicks > 0
        assert estimate.estimated_spend > 0
        assert estimate.confidence == "low"  # No search volume/CPC data

    def test_estimate_with_search_volume(self, estimator):
        """Test estimation with search volume."""
        estimate = estimator.estimate_keyword_spend(
            appearance_count=10,
            avg_position=1.0,
            days_active=30,
            search_volume=50000,
        )

        assert estimate.estimated_impressions > 0
        assert estimate.confidence == "medium"

    def test_estimate_with_full_data(self, estimator):
        """Test estimation with all data."""
        estimate = estimator.estimate_keyword_spend(
            appearance_count=20,
            avg_position=1.5,
            days_active=30,
            search_volume=100000,
            cpc_estimate=3.50,
            total_scrapes=30,
        )

        assert estimate.confidence == "high"
        assert estimate.estimated_cpc == Decimal("3.50")

    def test_position_ctr(self, estimator):
        """Test CTR varies by position."""
        pos1_estimate = estimator.estimate_keyword_spend(
            appearance_count=10,
            avg_position=1.0,
            days_active=30,
            search_volume=10000,
        )

        pos4_estimate = estimator.estimate_keyword_spend(
            appearance_count=10,
            avg_position=4.0,
            days_active=30,
            search_volume=10000,
        )

        # Position 1 should have higher CTR and thus more clicks
        assert pos1_estimate.estimated_clicks > pos4_estimate.estimated_clicks
        assert pos1_estimate.estimated_ctr > pos4_estimate.estimated_ctr

    def test_estimate_total_monthly_spend(self, estimator):
        """Test total spend calculation."""
        estimates = [
            SpendEstimate(
                estimated_impressions=1000,
                estimated_clicks=50,
                estimated_ctr=5.0,
                estimated_cpc=Decimal("2.00"),
                estimated_spend=Decimal("100.00"),
                confidence="medium",
            ),
            SpendEstimate(
                estimated_impressions=2000,
                estimated_clicks=80,
                estimated_ctr=4.0,
                estimated_cpc=Decimal("2.50"),
                estimated_spend=Decimal("200.00"),
                confidence="medium",
            ),
        ]

        total = estimator.estimate_total_monthly_spend(estimates)
        assert total == Decimal("300.00")

    def test_estimate_by_position_distribution(self, estimator):
        """Test estimation with position distribution."""
        distribution = {"1": 5, "2": 10, "3": 8, "4": 2}

        estimate = estimator.estimate_by_position_distribution(
            position_distribution=distribution,
            days_active=30,
        )

        assert estimate.estimated_impressions > 0
        assert estimate.estimated_clicks > 0
