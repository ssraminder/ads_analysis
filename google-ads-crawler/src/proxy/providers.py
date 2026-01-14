"""Proxy provider integrations."""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from src.config import settings


@dataclass
class ProxyCredentials:
    """Proxy connection credentials."""
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"

    @property
    def url(self) -> str:
        """Get full proxy URL."""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"

    @property
    def playwright_config(self) -> dict:
        """Get Playwright proxy configuration."""
        config = {
            "server": f"{self.protocol}://{self.host}:{self.port}",
        }
        if self.username and self.password:
            config["username"] = self.username
            config["password"] = self.password
        return config


class ProxyProvider(ABC):
    """Abstract base class for proxy providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @abstractmethod
    def get_proxy(self, geo: str = "US", session_id: Optional[str] = None) -> ProxyCredentials:
        """Get a proxy from this provider."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        pass


class BrightDataProvider(ProxyProvider):
    """Bright Data (formerly Luminati) proxy provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        zone: Optional[str] = None,
    ):
        self.api_key = api_key or settings.BRIGHTDATA_API_KEY
        self.zone = zone or settings.BRIGHTDATA_ZONE
        self.host = "brd.superproxy.io"
        self.port = 22225

    @property
    def name(self) -> str:
        return "brightdata"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.zone)

    def get_proxy(self, geo: str = "US", session_id: Optional[str] = None) -> ProxyCredentials:
        """
        Get a Bright Data residential proxy.

        Args:
            geo: Country code for geo-targeting
            session_id: Session ID for sticky sessions
        """
        if not self.is_configured():
            raise ValueError("Bright Data provider not configured")

        # Build username with zone and options
        username_parts = [f"brd-customer-{self.api_key}", f"zone-{self.zone}"]

        # Add country targeting
        username_parts.append(f"country-{geo.lower()}")

        # Add session for sticky IP if provided
        if session_id:
            username_parts.append(f"session-{session_id}")

        username = "-".join(username_parts)

        return ProxyCredentials(
            host=self.host,
            port=self.port,
            username=username,
            password=self.zone,
            protocol="http",
        )


class OxylabsProvider(ProxyProvider):
    """Oxylabs proxy provider."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.username = username or settings.OXYLABS_USERNAME
        self.password = password or settings.OXYLABS_PASSWORD
        self.host = "pr.oxylabs.io"
        self.port = 7777

    @property
    def name(self) -> str:
        return "oxylabs"

    def is_configured(self) -> bool:
        return bool(self.username and self.password)

    def get_proxy(self, geo: str = "US", session_id: Optional[str] = None) -> ProxyCredentials:
        """
        Get an Oxylabs residential proxy.

        Args:
            geo: Country code for geo-targeting
            session_id: Session ID for sticky sessions
        """
        if not self.is_configured():
            raise ValueError("Oxylabs provider not configured")

        # Oxylabs uses username suffix for targeting
        username = f"customer-{self.username}-cc-{geo.upper()}"

        # Add session for sticky IP
        if session_id:
            username = f"{username}-sessid-{session_id}"

        return ProxyCredentials(
            host=self.host,
            port=self.port,
            username=username,
            password=self.password,
            protocol="http",
        )


class DirectConnectionProvider(ProxyProvider):
    """
    Direct connection (no proxy) for testing.

    WARNING: Only use for development/testing.
    Google will quickly block direct connections for scraping.
    """

    @property
    def name(self) -> str:
        return "direct"

    def is_configured(self) -> bool:
        return True

    def get_proxy(self, geo: str = "US", session_id: Optional[str] = None) -> ProxyCredentials:
        """Return empty proxy (direct connection)."""
        # Return a special marker that indicates no proxy
        return ProxyCredentials(
            host="",
            port=0,
            protocol="direct",
        )


class FreeProxyProvider(ProxyProvider):
    """
    Free proxy list provider for testing only.

    WARNING: Free proxies are unreliable and often blocked.
    Only use for development/testing.
    """

    # Sample of free proxies (these will likely not work in production)
    FREE_PROXIES = [
        ("104.248.63.15", 30588),
        ("185.199.229.156", 7492),
        ("185.199.228.220", 7300),
        ("51.158.169.52", 29976),
    ]

    @property
    def name(self) -> str:
        return "free"

    def is_configured(self) -> bool:
        return True

    def get_proxy(self, geo: str = "US", session_id: Optional[str] = None) -> ProxyCredentials:
        """Get a random free proxy."""
        host, port = random.choice(self.FREE_PROXIES)
        return ProxyCredentials(
            host=host,
            port=port,
            protocol="http",
        )


def get_configured_providers() -> List[ProxyProvider]:
    """Get all configured proxy providers."""
    providers = []

    brightdata = BrightDataProvider()
    if brightdata.is_configured():
        providers.append(brightdata)

    oxylabs = OxylabsProvider()
    if oxylabs.is_configured():
        providers.append(oxylabs)

    # Always add direct connection as fallback for testing
    providers.append(DirectConnectionProvider())

    return providers
