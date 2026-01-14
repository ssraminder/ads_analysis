"""Bright Data SERP API client for Google search results."""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import aiohttp

from src.config import settings
from src.scraper.ad_extractor import AdData, AdExtensions, SiteLink
from src.utils.domain_parser import DomainParser

logger = logging.getLogger(__name__)


@dataclass
class SerpApiResult:
    """Result from SERP API."""
    keyword: str
    geo: str
    ads: List[AdData] = field(default_factory=list)
    success: bool = False
    error: Optional[str] = None
    response_time_ms: int = 0
    raw_html: Optional[str] = None


class BrightDataSerpApi:
    """Client for Bright Data SERP API."""

    API_URL = "https://api.brightdata.com/request"

    def __init__(self, api_token: Optional[str] = None, zone: Optional[str] = None):
        self.api_token = api_token or settings.BRIGHTDATA_SERP_API_TOKEN
        self.zone = zone or settings.BRIGHTDATA_SERP_ZONE or "serp_api1"

    def is_configured(self) -> bool:
        """Check if SERP API is configured."""
        return bool(self.api_token)

    async def search(
        self,
        keyword: str,
        geo: str = "US",
        language: str = "en",
        device: str = "desktop",
    ) -> SerpApiResult:
        """
        Search Google using Bright Data SERP API.

        Args:
            keyword: Search query
            geo: Country code (e.g., "US", "UK")
            language: Language code (e.g., "en")
            device: Device type ("desktop" or "mobile")

        Returns:
            SerpApiResult with extracted ads
        """
        result = SerpApiResult(keyword=keyword, geo=geo)
        start_time = asyncio.get_event_loop().time()

        if not self.is_configured():
            result.error = "SERP API not configured"
            return result

        # Build Google search URL
        search_url = f"https://www.google.com/search?q={keyword}&gl={geo.lower()}&hl={language}"

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_token}",
                }

                payload = {
                    "zone": self.zone,
                    "url": search_url,
                    "format": "raw",  # Get raw HTML
                }

                logger.info(f"SERP API request for '{keyword}' geo={geo}")

                async with session.post(
                    self.API_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        result.error = f"SERP API error {response.status}: {error_text}"
                        logger.error(result.error)
                        return result

                    html_content = await response.text()
                    result.raw_html = html_content

                    # Parse ads from HTML
                    result.ads = self._extract_ads_from_html(html_content)
                    result.success = True

                    end_time = asyncio.get_event_loop().time()
                    result.response_time_ms = int((end_time - start_time) * 1000)

                    logger.info(
                        f"SERP API success for '{keyword}': "
                        f"found {len(result.ads)} ads in {result.response_time_ms}ms"
                    )

        except asyncio.TimeoutError:
            result.error = "SERP API request timed out"
            logger.error(result.error)
        except Exception as e:
            result.error = f"SERP API error: {str(e)}"
            logger.error(result.error)

        return result

    def _extract_ads_from_html(self, html: str) -> List[AdData]:
        """Extract ads from Google SERP HTML."""
        ads = []
        soup = BeautifulSoup(html, "html.parser")

        # Debug: Check for Sponsored text
        page_text = soup.get_text().lower()
        has_sponsored = "sponsored" in page_text
        logger.info(f"SERP API page contains 'Sponsored': {has_sponsored}")

        # Try multiple ad container selectors
        ad_containers = []

        # Top ads container
        tads = soup.find(id="tads")
        if tads:
            logger.info("Found #tads container")
            ad_containers.extend(tads.find_all(class_="uEierd") or tads.find_all(attrs={"data-text-ad": "1"}))

        # Bottom ads container
        tadsb = soup.find(id="tadsb")
        if tadsb:
            logger.info("Found #tadsb container")
            ad_containers.extend(tadsb.find_all(class_="uEierd") or tadsb.find_all(attrs={"data-text-ad": "1"}))

        # Alternative: Find all elements with data-text-ad attribute
        if not ad_containers:
            ad_containers = soup.find_all(attrs={"data-text-ad": "1"})
            logger.info(f"Found {len(ad_containers)} elements with data-text-ad")

        # Alternative: Find by Sponsored label
        if not ad_containers:
            # Look for elements containing "Sponsored" text
            for elem in soup.find_all(["div", "span"]):
                text = elem.get_text()
                if text and "sponsored" in text.lower() and len(text) < 20:
                    parent = elem.find_parent("div", class_=True)
                    if parent and parent not in ad_containers:
                        ad_containers.append(parent)

        logger.info(f"Processing {len(ad_containers)} potential ad containers")

        # Extract data from each ad
        for i, container in enumerate(ad_containers):
            try:
                ad_data = self._parse_ad_element(container, position=i + 1)
                if ad_data:
                    ads.append(ad_data)
            except Exception as e:
                logger.debug(f"Failed to parse ad {i + 1}: {e}")

        return ads

    def _parse_ad_element(self, element, position: int) -> Optional[AdData]:
        """Parse a single ad element."""
        # Extract headline
        headline = None
        headline_selectors = ["h3", "[role='heading']", ".CCgQ5", ".sVXRqc"]
        for selector in headline_selectors:
            headline_el = element.select_one(selector)
            if headline_el:
                headline = headline_el.get_text(strip=True)
                if headline:
                    break

        if not headline:
            return None

        # Extract description
        description = None
        desc_selectors = [".VwiC3b", ".MUxGbd", ".yDYNvb"]
        for selector in desc_selectors:
            desc_el = element.select_one(selector)
            if desc_el:
                description = desc_el.get_text(strip=True)
                if description and len(description) > 20:
                    break

        # Extract URL
        final_url = None
        link = element.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "google.com" not in href:
                final_url = self._clean_google_url(href)
            elif "/aclk?" in href or "googleadservices" in href:
                # Extract actual URL from Google redirect
                final_url = self._clean_google_url(href)

        # Extract display URL
        display_url = None
        cite = element.find("cite")
        if cite:
            display_url = cite.get_text(strip=True).split("›")[0].strip()

        if not final_url and not display_url:
            return None

        # Parse domain
        url_for_domain = final_url or display_url
        domain, root_domain = DomainParser.extract_from_url(url_for_domain)

        # Extract extensions
        extensions = self._extract_extensions(element)

        return AdData(
            position=position,
            headline=headline,
            description=description,
            display_url=display_url or domain,
            final_url=final_url or display_url,
            domain=domain,
            root_domain=root_domain,
            extensions=extensions,
            is_top_ad=position <= 4,
        )

    def _clean_google_url(self, url: str) -> str:
        """Clean Google redirect URLs."""
        if "/aclk?" in url or "googleadservices" in url:
            match = re.search(r"adurl=([^&]+)", url)
            if match:
                from urllib.parse import unquote
                return unquote(match.group(1))

        match = re.search(r"[?&]url=([^&]+)", url)
        if match:
            from urllib.parse import unquote
            return unquote(match.group(1))

        return url

    def _extract_extensions(self, element) -> AdExtensions:
        """Extract ad extensions from element."""
        extensions = AdExtensions()

        # Extract sitelinks
        sitelink_containers = element.select(".MhgNwc a, .bOeY0b a")
        for link in sitelink_containers[:8]:
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if title:
                extensions.sitelinks.append(SiteLink(
                    title=title,
                    url=self._clean_google_url(href) if href else None,
                ))

        # Extract phone
        tel_link = element.select_one("a[href^='tel:']")
        if tel_link:
            extensions.phone = tel_link.get("href", "").replace("tel:", "")

        return extensions
