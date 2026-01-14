"""Web scraping package."""

from src.scraper.ad_extractor import AdData, AdExtractor
from src.scraper.captcha_handler import CaptchaDetector, CaptchaError
from src.scraper.google_serp import GoogleSerpScraper, SerpResult
from src.scraper.stealth import StealthConfig

__all__ = [
    "GoogleSerpScraper",
    "SerpResult",
    "AdExtractor",
    "AdData",
    "StealthConfig",
    "CaptchaDetector",
    "CaptchaError",
]
