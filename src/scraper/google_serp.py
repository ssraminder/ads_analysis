"""Main Google SERP scraper implementation."""

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote_plus, urlencode
import logging

from playwright.async_api import Browser, Page, async_playwright

from src.config import settings
from src.proxy.manager import Proxy, ProxyManager
from src.scraper.ad_extractor import AdData, AdExtractor
from src.scraper.captcha_handler import BlockedError, CaptchaDetector, CaptchaError
from src.scraper.stealth import StealthBrowserLauncher, StealthConfig
from src.utils.rate_limiter import AdaptiveRateLimiter

logger = logging.getLogger(__name__)


@dataclass
class SerpResult:
    """Result of a SERP scrape."""
    keyword: str
    geo: str
    device: str
    language: str
    ads: List[AdData] = field(default_factory=list)
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    success: bool = False
    error: Optional[str] = None
    blocked: bool = False
    captcha: bool = False
    response_time_ms: int = 0
    proxy_used: Optional[str] = None
    raw_html: Optional[str] = None

    @property
    def ad_count(self) -> int:
        return len(self.ads)

    @property
    def top_ad_count(self) -> int:
        return sum(1 for ad in self.ads if ad.is_top_ad)

    @property
    def bottom_ad_count(self) -> int:
        return sum(1 for ad in self.ads if not ad.is_top_ad)

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "geo": self.geo,
            "device": self.device,
            "language": self.language,
            "ads": [ad.to_dict() for ad in self.ads],
            "scraped_at": self.scraped_at.isoformat(),
            "success": self.success,
            "error": self.error,
            "blocked": self.blocked,
            "captcha": self.captcha,
            "response_time_ms": self.response_time_ms,
            "ad_count": self.ad_count,
        }


class GoogleSerpScraper:
    """
    Async Google SERP scraper with stealth and proxy support.

    Usage:
        scraper = GoogleSerpScraper(proxy_manager)
        result = await scraper.scrape_keyword("buy shoes online", geo="US")
        for ad in result.ads:
            print(f"{ad.position}: {ad.domain} - {ad.headline}")
    """

    # Google search base URLs
    GOOGLE_SEARCH_URL = "https://www.google.com/search"

    # Geo-specific Google domains
    GEO_DOMAINS = {
        "US": "google.com",
        "UK": "google.co.uk",
        "CA": "google.ca",
        "AU": "google.com.au",
        "DE": "google.de",
        "FR": "google.fr",
        "ES": "google.es",
        "IT": "google.it",
        "NL": "google.nl",
        "BR": "google.com.br",
    }

    def __init__(
        self,
        proxy_manager: Optional[ProxyManager] = None,
        rate_limiter: Optional[AdaptiveRateLimiter] = None,
    ):
        self.proxy_manager = proxy_manager or ProxyManager()
        self.rate_limiter = rate_limiter or AdaptiveRateLimiter()
        self.stealth_launcher = StealthBrowserLauncher()
        self.ad_extractor = AdExtractor()
        self.captcha_detector = CaptchaDetector()

        self._browser: Optional[Browser] = None
        self._playwright = None

    async def _ensure_browser(self) -> Browser:
        """Ensure browser is initialized."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                **self.stealth_launcher.get_launch_options()
            )
        return self._browser

    async def close(self) -> None:
        """Close browser and cleanup resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def _build_search_url(
        self,
        keyword: str,
        geo: str = "US",
        language: str = "en",
    ) -> str:
        """
        Build Google search URL with appropriate parameters.

        Args:
            keyword: Search query
            geo: Geographic location code
            language: Language code

        Returns:
            Full search URL
        """
        # Get geo-specific domain
        domain = self.GEO_DOMAINS.get(geo.upper(), "google.com")
        base_url = f"https://www.{domain}/search"

        # Build query parameters
        params = {
            "q": keyword,
            "gl": geo.lower(),  # Geo location
            "hl": language,      # Language
            "pws": "0",          # Disable personalized results
            "nfpr": "1",         # No auto-correction
        }

        # Add some randomization to reduce fingerprinting
        random_params = [
            ("source", "hp"),
            ("ei", self._generate_random_ei()),
            ("iflsig", self._generate_random_sig()),
        ]

        # Randomly include some extra params
        for key, value in random_params:
            if random.random() < 0.5:
                params[key] = value

        return f"{base_url}?{urlencode(params)}"

    def _generate_random_ei(self) -> str:
        """Generate random ei parameter (looks like base64)."""
        import base64
        random_bytes = bytes([random.randint(0, 255) for _ in range(12)])
        return base64.b64encode(random_bytes).decode().rstrip("=")

    def _generate_random_sig(self) -> str:
        """Generate random signature parameter."""
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        return "".join(random.choice(chars) for _ in range(43))

    async def scrape_keyword(
        self,
        keyword: str,
        geo: str = "US",
        device: str = "desktop",
        language: str = "en",
        save_html: bool = False,
    ) -> SerpResult:
        """
        Scrape Google search results for a keyword.

        Args:
            keyword: Search term to scrape
            geo: Geographic location (US, UK, CA, etc.)
            device: Device type (desktop, mobile, tablet)
            language: Language code (en, es, de, etc.)
            save_html: Whether to save raw HTML in result

        Returns:
            SerpResult containing extracted ads and metadata
        """
        result = SerpResult(
            keyword=keyword,
            geo=geo,
            device=device,
            language=language,
        )

        proxy: Optional[Proxy] = None
        page: Optional[Page] = None
        start_time = time.time()

        try:
            # Rate limiting
            rate_key = f"{geo}_{device}"
            await self.rate_limiter.acquire(rate_key)

            # Get proxy
            proxy = await self.proxy_manager.get_proxy(geo=geo)
            result.proxy_used = proxy.provider

            logger.info(
                f"Scraping keyword '{keyword}' geo={geo} device={device} "
                f"proxy={proxy.provider}"
            )

            # Create browser context with stealth settings
            browser = await self._ensure_browser()
            stealth_config = StealthConfig(device_type=device, language=language)
            context_options = stealth_config.get_browser_context_options(device)

            # Add proxy if not direct connection
            if proxy.playwright_config:
                context_options["proxy"] = proxy.playwright_config
                # Trust proxy's SSL certificate (needed for Bright Data)
                context_options["ignore_https_errors"] = True

            context = await browser.new_context(**context_options)

            try:
                page = await context.new_page()

                # Apply additional stealth measures
                await stealth_config.apply_stealth(page)

                # Build and navigate to search URL
                search_url = self._build_search_url(keyword, geo, language)
                logger.debug(f"Navigating to: {search_url}")

                await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=settings.REQUEST_TIMEOUT_SECONDS * 1000,
                )

                # Human-like delay after page load
                await asyncio.sleep(random.uniform(1, 3))

                # Simulate human behavior
                await stealth_config.simulate_human_behavior(page)

                # Check for CAPTCHA/block
                detection = await self.captcha_detector.detect(page)

                if detection.is_captcha:
                    result.captcha = True
                    result.error = detection.message
                    if proxy:
                        await self.proxy_manager.mark_blocked(proxy)
                    await self.rate_limiter.record_failure(rate_key, is_block=True)
                    raise CaptchaError(detection.message or "CAPTCHA detected")

                if detection.is_blocked:
                    result.blocked = True
                    result.error = detection.message
                    if proxy:
                        await self.proxy_manager.mark_blocked(proxy)
                    await self.rate_limiter.record_failure(rate_key, is_block=True)
                    raise BlockedError(detection.message or "Request blocked")

                # Wait for ads to potentially load
                await self._wait_for_ads(page)

                # Extract ads
                result.ads = await self.ad_extractor.extract_all_ads(page)

                # Save raw HTML if requested
                if save_html:
                    result.raw_html = await page.content()

                # Calculate response time
                result.response_time_ms = int((time.time() - start_time) * 1000)
                result.success = True

                # Record success
                if proxy:
                    await self.proxy_manager.mark_success(proxy, result.response_time_ms)
                await self.rate_limiter.record_success(rate_key)

                logger.info(
                    f"Successfully scraped '{keyword}': found {result.ad_count} ads "
                    f"in {result.response_time_ms}ms"
                )

            finally:
                await context.close()

        except CaptchaError:
            logger.warning(f"CAPTCHA encountered for '{keyword}'")
            raise

        except BlockedError:
            logger.warning(f"Blocked while scraping '{keyword}'")
            raise

        except Exception as e:
            result.error = str(e)
            result.response_time_ms = int((time.time() - start_time) * 1000)

            if proxy:
                await self.proxy_manager.mark_failure(proxy, str(e))
            await self.rate_limiter.record_failure(rate_key)

            logger.error(f"Error scraping '{keyword}': {e}")

        return result

    async def _wait_for_ads(self, page: Page, timeout_ms: int = 5000) -> None:
        """Wait for ad elements to load."""
        ad_selectors = [
            "#tads",
            "#tadsb",
            "[data-text-ad='1']",
            ".uEierd",
        ]

        for selector in ad_selectors:
            try:
                await page.wait_for_selector(
                    selector,
                    timeout=timeout_ms,
                    state="attached"
                )
                logger.debug(f"Found ad container: {selector}")
                return
            except Exception:
                pass

        logger.debug("No ad containers found within timeout")

    async def scrape_keywords_batch(
        self,
        keywords: List[str],
        geo: str = "US",
        device: str = "desktop",
        language: str = "en",
        max_concurrent: int = 1,
        delay_between: Optional[float] = None,
    ) -> List[SerpResult]:
        """
        Scrape multiple keywords with rate limiting.

        Args:
            keywords: List of keywords to scrape
            geo: Geographic location
            device: Device type
            language: Language code
            max_concurrent: Max concurrent scrapes (default 1 for safety)
            delay_between: Delay between scrapes (uses random if None)

        Returns:
            List of SerpResult objects
        """
        results = []

        # Process keywords with rate limiting
        for i, keyword in enumerate(keywords):
            try:
                result = await self.scrape_keyword(
                    keyword=keyword,
                    geo=geo,
                    device=device,
                    language=language,
                )
                results.append(result)

                # Add delay between requests
                if i < len(keywords) - 1:
                    if delay_between:
                        await asyncio.sleep(delay_between)
                    else:
                        await self.rate_limiter.wait_with_jitter()

            except (CaptchaError, BlockedError) as e:
                logger.error(f"Blocked on keyword '{keyword}': {e}")
                results.append(SerpResult(
                    keyword=keyword,
                    geo=geo,
                    device=device,
                    language=language,
                    blocked=isinstance(e, BlockedError),
                    captcha=isinstance(e, CaptchaError),
                    error=str(e),
                ))

                # Longer delay after block
                await asyncio.sleep(random.uniform(60, 120))

            except Exception as e:
                logger.error(f"Error on keyword '{keyword}': {e}")
                results.append(SerpResult(
                    keyword=keyword,
                    geo=geo,
                    device=device,
                    language=language,
                    error=str(e),
                ))

        return results


async def quick_scrape(
    keyword: str,
    geo: str = "US",
    device: str = "desktop",
) -> SerpResult:
    """
    Quick single-keyword scrape for testing.

    Usage:
        result = await quick_scrape("buy shoes online")
        print(f"Found {len(result.ads)} ads")
    """
    async with GoogleSerpScraper() as scraper:
        return await scraper.scrape_keyword(keyword, geo=geo, device=device)
