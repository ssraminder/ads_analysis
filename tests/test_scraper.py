"""Tests for the Google SERP scraper."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.scraper.google_serp import GoogleSerpScraper, SerpResult
from src.scraper.captcha_handler import CaptchaDetector, DetectionResult


class TestGoogleSerpScraper:
    """Tests for GoogleSerpScraper class."""

    @pytest.fixture
    def scraper(self):
        """Create scraper instance."""
        return GoogleSerpScraper()

    def test_build_search_url(self, scraper):
        """Test search URL building."""
        url = scraper._build_search_url("buy shoes", geo="US", language="en")

        assert "google.com/search" in url
        assert "q=buy+shoes" in url or "q=buy%20shoes" in url
        assert "gl=us" in url
        assert "hl=en" in url

    def test_build_search_url_uk(self, scraper):
        """Test search URL for UK geo."""
        url = scraper._build_search_url("buy shoes", geo="UK", language="en")
        assert "google.co.uk/search" in url

    def test_build_search_url_germany(self, scraper):
        """Test search URL for German geo."""
        url = scraper._build_search_url("schuhe kaufen", geo="DE", language="de")
        assert "google.de/search" in url
        assert "hl=de" in url

    def test_generate_random_ei(self, scraper):
        """Test random ei parameter generation."""
        ei1 = scraper._generate_random_ei()
        ei2 = scraper._generate_random_ei()

        # Should be non-empty strings
        assert len(ei1) > 0
        assert len(ei2) > 0
        # Should be different (random)
        assert ei1 != ei2

    def test_generate_random_sig(self, scraper):
        """Test random signature generation."""
        sig = scraper._generate_random_sig()
        assert len(sig) == 43  # Expected length


class TestSerpResult:
    """Tests for SerpResult dataclass."""

    def test_serp_result_defaults(self):
        """Test SerpResult default values."""
        result = SerpResult(
            keyword="test keyword",
            geo="US",
            device="desktop",
            language="en",
        )

        assert result.keyword == "test keyword"
        assert result.ads == []
        assert result.success is False
        assert result.blocked is False
        assert result.ad_count == 0

    def test_serp_result_ad_counts(self):
        """Test SerpResult ad count properties."""
        from src.scraper.ad_extractor import AdData, AdExtensions

        result = SerpResult(
            keyword="test",
            geo="US",
            device="desktop",
            language="en",
            ads=[
                AdData(
                    position=1, headline="Ad 1", description="", display_url="a.com",
                    final_url="https://a.com", domain="a.com", root_domain="a.com",
                    extensions=AdExtensions(), is_top_ad=True
                ),
                AdData(
                    position=2, headline="Ad 2", description="", display_url="b.com",
                    final_url="https://b.com", domain="b.com", root_domain="b.com",
                    extensions=AdExtensions(), is_top_ad=True
                ),
                AdData(
                    position=3, headline="Ad 3", description="", display_url="c.com",
                    final_url="https://c.com", domain="c.com", root_domain="c.com",
                    extensions=AdExtensions(), is_top_ad=False
                ),
            ],
        )

        assert result.ad_count == 3
        assert result.top_ad_count == 2
        assert result.bottom_ad_count == 1

    def test_serp_result_to_dict(self):
        """Test SerpResult conversion to dict."""
        result = SerpResult(
            keyword="test keyword",
            geo="US",
            device="desktop",
            language="en",
            success=True,
            response_time_ms=1500,
        )

        result_dict = result.to_dict()

        assert result_dict["keyword"] == "test keyword"
        assert result_dict["geo"] == "US"
        assert result_dict["success"] is True
        assert result_dict["response_time_ms"] == 1500


class TestCaptchaDetector:
    """Tests for CaptchaDetector class."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return CaptchaDetector()

    @pytest.mark.asyncio
    async def test_detect_clean_page(self, detector):
        """Test detection on clean page."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.google.com/search?q=test"
        mock_page.content = AsyncMock(return_value="<html><body>Normal search results</body></html>")
        mock_page.title = AsyncMock(return_value="test - Google Search")
        mock_page.query_selector = AsyncMock(return_value=None)

        result = await detector.detect(mock_page)

        assert result.is_blocked is False
        assert result.is_captcha is False

    @pytest.mark.asyncio
    async def test_detect_sorry_url(self, detector):
        """Test detection of sorry page URL."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.google.com/sorry/index"

        result = await detector.detect(mock_page)

        assert result.is_blocked is True
        assert result.block_type == "url_redirect"

    @pytest.mark.asyncio
    async def test_detect_captcha_element(self, detector):
        """Test detection of CAPTCHA element."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.google.com/search?q=test"
        mock_page.content = AsyncMock(return_value="<html><body>Search results</body></html>")
        mock_page.title = AsyncMock(return_value="test - Google Search")

        # Return CAPTCHA element for recaptcha selector
        mock_captcha = MagicMock()

        async def mock_query_selector(selector):
            if "recaptcha" in selector:
                return mock_captcha
            return None

        mock_page.query_selector = mock_query_selector

        result = await detector.detect(mock_page)

        assert result.is_captcha is True
        assert result.captcha_type == "recaptcha"

    @pytest.mark.asyncio
    async def test_detect_blocked_text(self, detector):
        """Test detection of block text in page content."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.google.com/search?q=test"
        mock_page.content = AsyncMock(
            return_value="<html><body>Our systems have detected unusual traffic from your computer</body></html>"
        )
        mock_page.title = AsyncMock(return_value="test - Google Search")
        mock_page.query_selector = AsyncMock(return_value=None)

        result = await detector.detect(mock_page)

        assert result.is_blocked is True
        assert result.block_type == "text_detection"
