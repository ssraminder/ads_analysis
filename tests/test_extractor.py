"""Tests for ad extraction."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.scraper.ad_extractor import AdExtractor, AdData


class TestAdExtractor:
    """Tests for AdExtractor class."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return AdExtractor()

    @pytest.mark.asyncio
    async def test_extract_headline(self, extractor, sample_ad_html):
        """Test headline extraction from ad element."""
        # Create mock element
        mock_element = AsyncMock()

        # Setup query selector to return headline
        mock_headline = AsyncMock()
        mock_headline.inner_text = AsyncMock(return_value="Buy Premium Shoes - Free Shipping Today")

        async def mock_query_selector(selector):
            if "h3" in selector or "heading" in selector.lower():
                return mock_headline
            return None

        mock_element.query_selector = mock_query_selector

        # Test extraction
        headline = await extractor._extract_headline(mock_element)
        assert headline == "Buy Premium Shoes - Free Shipping Today"

    @pytest.mark.asyncio
    async def test_extract_description(self, extractor):
        """Test description extraction."""
        mock_element = AsyncMock()
        mock_desc = AsyncMock()
        mock_desc.inner_text = AsyncMock(
            return_value="Shop our collection of premium shoes. Free shipping on orders over $50."
        )

        async def mock_query_selector(selector):
            if "VwiC3b" in selector or "description" in selector.lower():
                return mock_desc
            return None

        mock_element.query_selector = mock_query_selector

        description = await extractor._extract_description(mock_element)
        assert "premium shoes" in description.lower()

    def test_clean_google_url(self, extractor):
        """Test Google URL cleaning."""
        # Test with adurl parameter
        url = "https://www.googleadservices.com/pagead/aclk?adurl=https://example.com/landing"
        cleaned = extractor._clean_google_url(url)
        assert cleaned == "https://example.com/landing"

        # Test with url parameter
        url = "https://www.google.com/aclk?url=https%3A%2F%2Fexample.com%2Fpage"
        cleaned = extractor._clean_google_url(url)
        assert "example.com" in cleaned

        # Test clean URL
        url = "https://example.com/page"
        cleaned = extractor._clean_google_url(url)
        assert cleaned == url

    @pytest.mark.asyncio
    async def test_extract_sitelinks(self, extractor):
        """Test sitelink extraction."""
        mock_element = AsyncMock()

        # Create mock sitelinks
        mock_link1 = AsyncMock()
        mock_link1.inner_text = AsyncMock(return_value="Men's Shoes")
        mock_link1.get_attribute = AsyncMock(return_value="https://example.com/mens")

        mock_link2 = AsyncMock()
        mock_link2.inner_text = AsyncMock(return_value="Women's Shoes")
        mock_link2.get_attribute = AsyncMock(return_value="https://example.com/womens")

        async def mock_query_selector_all(selector):
            if "MhgNwc" in selector or "sitelink" in selector.lower():
                return [mock_link1, mock_link2]
            return []

        mock_element.query_selector_all = mock_query_selector_all

        sitelinks = await extractor._extract_sitelinks(mock_element)
        assert len(sitelinks) == 2
        assert sitelinks[0].title == "Men's Shoes"
        assert sitelinks[1].title == "Women's Shoes"


class TestAdData:
    """Tests for AdData dataclass."""

    def test_ad_data_to_dict(self):
        """Test AdData conversion to dictionary."""
        from src.scraper.ad_extractor import AdExtensions

        ad = AdData(
            position=1,
            headline="Test Headline",
            description="Test description",
            display_url="example.com",
            final_url="https://example.com/landing",
            domain="example.com",
            root_domain="example.com",
            extensions=AdExtensions(
                callouts=["Free Shipping", "Best Prices"],
            ),
            is_top_ad=True,
        )

        ad_dict = ad.to_dict()

        assert ad_dict["position"] == 1
        assert ad_dict["headline"] == "Test Headline"
        assert ad_dict["domain"] == "example.com"
        assert ad_dict["is_top_ad"] is True
        assert "Free Shipping" in ad_dict["extensions"]["callouts"]
