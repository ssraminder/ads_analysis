"""Extract structured ad data from Google SERP pages."""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

from playwright.async_api import ElementHandle, Page

from src.utils.domain_parser import DomainParser

logger = logging.getLogger(__name__)


@dataclass
class SiteLink:
    """Individual sitelink in ad extensions."""
    title: str
    url: Optional[str] = None
    description: Optional[str] = None


@dataclass
class AdExtensions:
    """Ad extensions data."""
    sitelinks: List[SiteLink] = field(default_factory=list)
    callouts: List[str] = field(default_factory=list)
    structured_snippets: Dict[str, List[str]] = field(default_factory=dict)
    phone: Optional[str] = None
    location: Optional[str] = None
    price: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None


@dataclass
class AdData:
    """Extracted ad data."""
    position: int
    headline: str
    description: Optional[str]
    display_url: str
    final_url: str
    domain: str
    root_domain: str
    extensions: AdExtensions
    raw_html: Optional[str] = None
    is_top_ad: bool = True  # True for top ads, False for bottom ads

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "position": self.position,
            "headline": self.headline,
            "description": self.description,
            "display_url": self.display_url,
            "final_url": self.final_url,
            "domain": self.domain,
            "root_domain": self.root_domain,
            "is_top_ad": self.is_top_ad,
            "extensions": {
                "sitelinks": [
                    {"title": sl.title, "url": sl.url, "description": sl.description}
                    for sl in self.extensions.sitelinks
                ],
                "callouts": self.extensions.callouts,
                "structured_snippets": self.extensions.structured_snippets,
                "phone": self.extensions.phone,
                "location": self.extensions.location,
                "price": self.extensions.price,
                "rating": self.extensions.rating,
                "review_count": self.extensions.review_count,
            },
        }


class AdExtractor:
    """Extract ads from Google SERP pages."""

    # Multiple selector strategies (Google changes these frequently)
    AD_CONTAINER_SELECTORS = [
        "#tads",                    # Top ads container (traditional)
        "#tadsb",                   # Bottom ads container
        "#taw",                     # Alternative top ads wrapper
        "[data-text-ad='1']",       # Data attribute marker
        ".uEierd",                  # Common ad wrapper class
        ".commercial-unit-desktop-top",  # Desktop top commercial unit
    ]

    AD_ITEM_SELECTORS = [
        ".uEierd",                  # Individual ad wrapper
        "[data-text-ad='1']",       # Individual ad by data attr
        ".Krnil",                   # Ad block class
        "[data-hveid]",             # Elements with hveid (ad tracking)
    ]

    HEADLINE_SELECTORS = [
        "[role='heading'] a",       # Heading link
        "h3 a",                     # H3 with link
        ".CCgQ5 a",                 # Specific class
        "a[data-rw]",               # Link with rw data
        ".sVXRqc",                  # Headline span class
    ]

    DESCRIPTION_SELECTORS = [
        ".VwiC3b",                  # Main description class
        ".MUxGbd",                  # Another description class
        "[data-snf='nke7rc']",      # Description data attr
        ".yDYNvb",                  # Alternative description
    ]

    DISPLAY_URL_SELECTORS = [
        ".qzEoUe",                  # Display URL container
        "cite",                     # Cite element often contains URL
        ".NV6Xye span",             # URL span
        "[data-dtld]",              # Data attribute for domain
    ]

    FINAL_URL_SELECTORS = [
        "[data-rw] a",              # Link with tracking
        "h3 a",                     # Direct headline link
        "a.sVXRqc",                 # Specific link class
    ]

    async def extract_all_ads(self, page: Page) -> List[AdData]:
        """
        Extract all ads from a Google SERP page.

        Args:
            page: Playwright page with Google search results

        Returns:
            List of extracted AdData objects
        """
        ads = []

        # Debug: Log what containers exist on the page
        for selector in self.AD_CONTAINER_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el:
                    logger.info(f"Found ad container: {selector}")
            except Exception:
                pass

        # Try to find top ads container
        top_ads = await self._extract_ads_from_container(page, "#tads", is_top=True)
        ads.extend(top_ads)
        logger.info(f"Top ads (#tads): found {len(top_ads)}")

        # Try to find bottom ads container
        bottom_ads = await self._extract_ads_from_container(page, "#tadsb", is_top=False)
        ads.extend(bottom_ads)
        logger.info(f"Bottom ads (#tadsb): found {len(bottom_ads)}")

        # If no ads found with containers, try direct ad elements
        if not ads:
            logger.info("No ads in containers, trying direct extraction")
            ads = await self._extract_ads_direct(page)

        # Debug: Check for "Sponsored" text on page
        try:
            page_text = await page.inner_text("body")
            has_sponsored = "sponsored" in page_text.lower()
            logger.info(f"Page contains 'Sponsored' text: {has_sponsored}")
        except Exception as e:
            logger.debug(f"Could not check for Sponsored text: {e}")

        # Assign positions
        for i, ad in enumerate(ads, 1):
            ad.position = i

        logger.info(f"Extracted {len(ads)} ads from page")
        return ads

    async def _extract_ads_from_container(
        self,
        page: Page,
        container_selector: str,
        is_top: bool
    ) -> List[AdData]:
        """Extract ads from a specific container."""
        ads = []

        try:
            container = await page.query_selector(container_selector)
            if not container:
                return ads

            # Find individual ads within container
            ad_elements = await container.query_selector_all(".uEierd, [data-text-ad='1']")

            for i, ad_el in enumerate(ad_elements):
                try:
                    ad_data = await self._extract_single_ad(ad_el, position=i + 1, is_top=is_top)
                    if ad_data:
                        ads.append(ad_data)
                except Exception as e:
                    logger.debug(f"Failed to extract ad {i + 1} from container: {e}")

        except Exception as e:
            logger.debug(f"Error extracting from container {container_selector}: {e}")

        return ads

    async def _extract_ads_direct(self, page: Page) -> List[AdData]:
        """Try to extract ads directly without container."""
        ads = []

        # Look for elements with ad indicators
        for selector in self.AD_ITEM_SELECTORS:
            try:
                elements = await page.query_selector_all(selector)
                for i, el in enumerate(elements):
                    # Check if this looks like an ad
                    if await self._is_likely_ad(el):
                        ad_data = await self._extract_single_ad(el, position=i + 1, is_top=True)
                        if ad_data:
                            ads.append(ad_data)
            except Exception as e:
                logger.debug(f"Error with selector {selector}: {e}")

        # Deduplicate by URL
        seen_urls = set()
        unique_ads = []
        for ad in ads:
            if ad.final_url not in seen_urls:
                seen_urls.add(ad.final_url)
                unique_ads.append(ad)

        return unique_ads

    async def _is_likely_ad(self, element: ElementHandle) -> bool:
        """Check if an element is likely to be an ad."""
        try:
            # Check for "Ad" or "Sponsored" label
            text = await element.inner_text()
            text_lower = text.lower() if text else ""

            ad_indicators = ["sponsored", " ad ", "\nad\n", "ad·", "· ad"]
            for indicator in ad_indicators:
                if indicator in text_lower:
                    return True

            # Check for ad-related attributes
            data_text_ad = await element.get_attribute("data-text-ad")
            if data_text_ad:
                return True

            # Check class names
            class_name = await element.get_attribute("class") or ""
            ad_classes = ["commercial", "sponsored", "ad-slot"]
            for ac in ad_classes:
                if ac in class_name.lower():
                    return True

        except Exception:
            pass

        return False

    async def _extract_single_ad(
        self,
        element: ElementHandle,
        position: int,
        is_top: bool
    ) -> Optional[AdData]:
        """Extract data from a single ad element."""
        try:
            # Get raw HTML for debugging
            raw_html = await element.inner_html()

            # Extract headline
            headline = await self._extract_headline(element)
            if not headline:
                logger.debug(f"No headline found for ad at position {position}")
                return None

            # Extract description
            description = await self._extract_description(element)

            # Extract URLs
            display_url = await self._extract_display_url(element)
            final_url = await self._extract_final_url(element)

            if not final_url and not display_url:
                logger.debug(f"No URL found for ad at position {position}")
                return None

            # Parse domain from URL
            url_for_domain = final_url or display_url
            domain, root_domain = DomainParser.extract_from_url(url_for_domain)

            # Extract extensions
            extensions = await self._extract_extensions(element)

            return AdData(
                position=position,
                headline=headline,
                description=description,
                display_url=display_url or domain,
                final_url=final_url or display_url,
                domain=domain,
                root_domain=root_domain,
                extensions=extensions,
                raw_html=raw_html[:5000] if raw_html else None,  # Limit size
                is_top_ad=is_top,
            )

        except Exception as e:
            logger.error(f"Error extracting single ad: {e}")
            return None

    async def _extract_headline(self, element: ElementHandle) -> Optional[str]:
        """Extract ad headline."""
        for selector in self.HEADLINE_SELECTORS:
            try:
                headline_el = await element.query_selector(selector)
                if headline_el:
                    text = await headline_el.inner_text()
                    if text and len(text.strip()) > 0:
                        return text.strip()
            except Exception:
                pass

        # Fallback: look for any h3
        try:
            h3 = await element.query_selector("h3")
            if h3:
                return (await h3.inner_text()).strip()
        except Exception:
            pass

        return None

    async def _extract_description(self, element: ElementHandle) -> Optional[str]:
        """Extract ad description."""
        for selector in self.DESCRIPTION_SELECTORS:
            try:
                desc_el = await element.query_selector(selector)
                if desc_el:
                    text = await desc_el.inner_text()
                    if text and len(text.strip()) > 20:  # Skip very short text
                        return text.strip()
            except Exception:
                pass

        return None

    async def _extract_display_url(self, element: ElementHandle) -> Optional[str]:
        """Extract display URL (visible URL in ad)."""
        for selector in self.DISPLAY_URL_SELECTORS:
            try:
                url_el = await element.query_selector(selector)
                if url_el:
                    text = await url_el.inner_text()
                    # Clean up display URL
                    if text:
                        # Remove breadcrumb separators for clean domain
                        text = text.split("›")[0].strip()
                        text = text.split(" ")[0].strip()
                        if "." in text:  # Looks like a URL
                            return DomainParser.normalize_domain(text)
            except Exception:
                pass

        return None

    async def _extract_final_url(self, element: ElementHandle) -> Optional[str]:
        """Extract final URL (actual destination)."""
        # Try direct link extraction
        for selector in self.FINAL_URL_SELECTORS:
            try:
                link_el = await element.query_selector(selector)
                if link_el:
                    href = await link_el.get_attribute("href")
                    if href and href.startswith("http"):
                        # Google often wraps URLs - try to extract real URL
                        return self._clean_google_url(href)
            except Exception:
                pass

        # Fallback: find any link with href
        try:
            links = await element.query_selector_all("a[href]")
            for link in links:
                href = await link.get_attribute("href")
                if href and href.startswith("http") and "google.com" not in href:
                    return self._clean_google_url(href)
        except Exception:
            pass

        return None

    def _clean_google_url(self, url: str) -> str:
        """Clean Google redirect URLs to get actual destination."""
        # Google often uses /aclk? redirects
        if "/aclk?" in url or "googleadservices.com" in url:
            # Try to find adurl parameter
            match = re.search(r"adurl=([^&]+)", url)
            if match:
                from urllib.parse import unquote
                return unquote(match.group(1))

        # Check for url= parameter
        match = re.search(r"[?&]url=([^&]+)", url)
        if match:
            from urllib.parse import unquote
            return unquote(match.group(1))

        return url

    async def _extract_extensions(self, element: ElementHandle) -> AdExtensions:
        """Extract ad extensions (sitelinks, callouts, etc.)."""
        extensions = AdExtensions()

        try:
            # Extract sitelinks
            extensions.sitelinks = await self._extract_sitelinks(element)

            # Extract callouts
            extensions.callouts = await self._extract_callouts(element)

            # Extract phone number
            extensions.phone = await self._extract_phone(element)

            # Extract rating
            rating_data = await self._extract_rating(element)
            if rating_data:
                extensions.rating = rating_data.get("rating")
                extensions.review_count = rating_data.get("review_count")

        except Exception as e:
            logger.debug(f"Error extracting extensions: {e}")

        return extensions

    async def _extract_sitelinks(self, element: ElementHandle) -> List[SiteLink]:
        """Extract sitelink extensions."""
        sitelinks = []

        # Common sitelink container selectors
        sitelink_selectors = [
            ".MhgNwc a",  # Sitelink class
            ".bOeY0b a",  # Alternative sitelink
            "[data-sld] a",  # Data attribute
        ]

        for selector in sitelink_selectors:
            try:
                links = await element.query_selector_all(selector)
                for link in links:
                    title = await link.inner_text()
                    href = await link.get_attribute("href")
                    if title and len(title.strip()) > 0:
                        sitelinks.append(SiteLink(
                            title=title.strip(),
                            url=self._clean_google_url(href) if href else None,
                        ))
            except Exception:
                pass

            if sitelinks:
                break

        return sitelinks[:8]  # Max 8 sitelinks

    async def _extract_callouts(self, element: ElementHandle) -> List[str]:
        """Extract callout extensions."""
        callouts = []

        # Callout selectors
        callout_selectors = [
            ".YhemCb",  # Callout class
            "[data-callout]",
        ]

        for selector in callout_selectors:
            try:
                elements = await element.query_selector_all(selector)
                for el in elements:
                    text = await el.inner_text()
                    if text and len(text.strip()) > 0:
                        callouts.append(text.strip())
            except Exception:
                pass

        return callouts[:10]

    async def _extract_phone(self, element: ElementHandle) -> Optional[str]:
        """Extract phone number extension."""
        phone_pattern = r"[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,4}[-\s\.]?[0-9]{1,9}"

        try:
            # Look for phone icon or tel: link
            tel_link = await element.query_selector("a[href^='tel:']")
            if tel_link:
                href = await tel_link.get_attribute("href")
                return href.replace("tel:", "")

            # Search text for phone pattern
            text = await element.inner_text()
            match = re.search(phone_pattern, text)
            if match:
                return match.group(0)
        except Exception:
            pass

        return None

    async def _extract_rating(self, element: ElementHandle) -> Optional[Dict]:
        """Extract rating and review count."""
        try:
            # Look for rating stars or text
            rating_el = await element.query_selector("[role='img'][aria-label*='rating']")
            if rating_el:
                label = await rating_el.get_attribute("aria-label")
                # Parse "Rated X.X out of 5" or similar
                rating_match = re.search(r"(\d+\.?\d*)\s*(out of|/)\s*5", label or "")
                if rating_match:
                    return {"rating": float(rating_match.group(1))}

            # Look for review count
            review_el = await element.query_selector("[aria-label*='review']")
            if review_el:
                label = await review_el.get_attribute("aria-label")
                count_match = re.search(r"(\d+[,\d]*)\s*review", label or "")
                if count_match:
                    count = int(count_match.group(1).replace(",", ""))
                    return {"review_count": count}

        except Exception:
            pass

        return None
