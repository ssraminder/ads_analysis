"""CAPTCHA and block detection for Google scraping."""

import re
from dataclasses import dataclass
from typing import Optional
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class CaptchaError(Exception):
    """Raised when a CAPTCHA is detected."""

    def __init__(self, message: str, captcha_type: str = "unknown"):
        super().__init__(message)
        self.captcha_type = captcha_type


class BlockedError(Exception):
    """Raised when the request is blocked."""

    def __init__(self, message: str, block_type: str = "unknown"):
        super().__init__(message)
        self.block_type = block_type


@dataclass
class DetectionResult:
    """Result of CAPTCHA/block detection."""
    is_blocked: bool = False
    is_captcha: bool = False
    block_type: Optional[str] = None
    captcha_type: Optional[str] = None
    message: Optional[str] = None


class CaptchaDetector:
    """Detect CAPTCHAs and blocks on Google pages."""

    # URL patterns indicating blocks
    BLOCKED_URL_PATTERNS = [
        r"/sorry/",
        r"google\.com/sorry",
        r"ipv4\.google\.com/sorry",
        r"captcha",
        r"/recaptcha/",
    ]

    # Text patterns indicating blocks or CAPTCHAs
    BLOCKED_TEXT_PATTERNS = [
        r"unusual traffic",
        r"automated queries",
        r"your computer or network may be sending automated queries",
        r"please show you're not a robot",
        r"our systems have detected unusual traffic",
        r"this page checks to see if it's really you",
        r"are you a robot",
        r"verify you are a human",
        r"access denied",
        r"blocked",
        r"too many requests",
    ]

    # Element selectors for CAPTCHA iframes
    CAPTCHA_SELECTORS = [
        "iframe[src*='recaptcha']",
        "iframe[src*='captcha']",
        "#recaptcha",
        ".g-recaptcha",
        "[data-sitekey]",
        "#captcha-form",
        "form[action*='sorry']",
    ]

    # Element selectors for block pages
    BLOCK_SELECTORS = [
        "#infoDiv",  # Google sorry page
        ".error-code",
        "#error-information-popup",
        "#challenge-running",
        "#challenge-form",
    ]

    async def detect(self, page: Page) -> DetectionResult:
        """
        Check if the page shows a CAPTCHA or block.

        Args:
            page: Playwright page to check

        Returns:
            DetectionResult with detection details
        """
        result = DetectionResult()

        try:
            current_url = page.url

            # Check URL patterns
            for pattern in self.BLOCKED_URL_PATTERNS:
                if re.search(pattern, current_url, re.IGNORECASE):
                    result.is_blocked = True
                    result.block_type = "url_redirect"
                    result.message = f"Redirected to blocked URL: {current_url}"
                    logger.warning(result.message)
                    return result

            # Check for CAPTCHA elements
            for selector in self.CAPTCHA_SELECTORS:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        result.is_captcha = True
                        result.captcha_type = "recaptcha" if "recaptcha" in selector else "other"
                        result.message = f"CAPTCHA detected: {selector}"
                        logger.warning(result.message)
                        return result
                except Exception:
                    pass

            # Check for block page elements
            for selector in self.BLOCK_SELECTORS:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        result.is_blocked = True
                        result.block_type = "block_page"
                        result.message = f"Block page element detected: {selector}"
                        logger.warning(result.message)
                        return result
                except Exception:
                    pass

            # Check page content for blocked text
            try:
                page_content = await page.content()
                page_text = page_content.lower()

                for pattern in self.BLOCKED_TEXT_PATTERNS:
                    if re.search(pattern, page_text, re.IGNORECASE):
                        result.is_blocked = True
                        result.block_type = "text_detection"
                        result.message = f"Block text detected: {pattern}"
                        logger.warning(result.message)
                        return result
            except Exception as e:
                logger.debug(f"Error checking page content: {e}")

            # Check page title
            try:
                title = await page.title()
                title_lower = title.lower() if title else ""

                block_titles = ["sorry", "blocked", "captcha", "unusual traffic", "error"]
                for block_title in block_titles:
                    if block_title in title_lower:
                        result.is_blocked = True
                        result.block_type = "title"
                        result.message = f"Block page title detected: {title}"
                        logger.warning(result.message)
                        return result
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error during CAPTCHA detection: {e}")
            # Don't raise - return non-blocked result and let scraper continue

        return result

    async def wait_for_resolution(
        self,
        page: Page,
        timeout_ms: int = 30000
    ) -> bool:
        """
        Wait for CAPTCHA/block to be resolved (manual intervention).

        This is mainly useful for debugging or manual solving.

        Args:
            page: Playwright page with CAPTCHA
            timeout_ms: Maximum time to wait

        Returns:
            True if resolved, False if still blocked
        """
        try:
            # Wait for navigation away from sorry page
            await page.wait_for_url(
                lambda url: "/sorry" not in url and "captcha" not in url.lower(),
                timeout=timeout_ms
            )

            # Re-check after navigation
            result = await self.detect(page)
            return not result.is_blocked and not result.is_captcha

        except Exception as e:
            logger.warning(f"CAPTCHA resolution timeout: {e}")
            return False


class GoogleErrorDetector:
    """Detect various Google error states."""

    async def check_for_errors(self, page: Page) -> Optional[str]:
        """
        Check for Google-specific error messages.

        Returns error message if detected, None otherwise.
        """
        error_selectors = {
            "#topstuff .card-section": "search_error",
            ".error-content": "page_error",
            "#error": "general_error",
        }

        for selector, error_type in error_selectors.items():
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text and len(text.strip()) > 0:
                        return f"{error_type}: {text.strip()[:200]}"
            except Exception:
                pass

        # Check for empty results
        try:
            no_results_element = await page.query_selector("#topstuff")
            if no_results_element:
                text = await no_results_element.inner_text()
                if "did not match any documents" in text.lower():
                    return "no_results"
        except Exception:
            pass

        return None
