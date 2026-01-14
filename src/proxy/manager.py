"""Proxy rotation and management."""

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import logging

from src.config import settings
from src.proxy.providers import (
    DirectConnectionProvider,
    ProxyCredentials,
    ProxyProvider,
    get_configured_providers,
)

logger = logging.getLogger(__name__)


@dataclass
class Proxy:
    """Proxy instance with metadata."""
    credentials: ProxyCredentials
    provider: str
    geo: str
    session_id: Optional[str] = None
    last_used: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    block_count: int = 0
    _response_times: List[int] = field(default_factory=list)

    @property
    def url(self) -> str:
        return self.credentials.url

    @property
    def is_direct(self) -> bool:
        return self.credentials.protocol == "direct"

    @property
    def playwright_config(self) -> Optional[dict]:
        """Get Playwright proxy config, or None for direct connection."""
        if self.is_direct:
            return None
        return self.credentials.playwright_config

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        total = self.success_count + self.failure_count + self.block_count
        if total == 0:
            return 100.0  # Assume good until proven otherwise
        return (self.success_count / total) * 100

    @property
    def avg_response_time_ms(self) -> int:
        """Get average response time in milliseconds."""
        if not self._response_times:
            return 0
        return int(sum(self._response_times) / len(self._response_times))

    def record_success(self, response_time_ms: int) -> None:
        """Record a successful request."""
        self.success_count += 1
        self.last_used = datetime.now(timezone.utc)
        self._response_times.append(response_time_ms)
        # Keep only last 100 response times
        if len(self._response_times) > 100:
            self._response_times = self._response_times[-100:]

    def record_failure(self) -> None:
        """Record a failed request."""
        self.failure_count += 1
        self.last_used = datetime.now(timezone.utc)

    def record_block(self) -> None:
        """Record being blocked."""
        self.block_count += 1
        self.last_used = datetime.now(timezone.utc)


class ProxyManager:
    """Manages proxy rotation and selection."""

    def __init__(
        self,
        providers: Optional[List[ProxyProvider]] = None,
        max_requests_per_hour: int = None,
    ):
        self.providers = providers or get_configured_providers()
        self.max_requests_per_hour = max_requests_per_hour or settings.MAX_REQUESTS_PER_PROXY_PER_HOUR

        # Track proxy usage
        self._proxies: Dict[str, Proxy] = {}
        self._usage_counts: Dict[str, List[datetime]] = {}
        self._blocked_proxies: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    def _get_provider(self, name: Optional[str] = None) -> ProxyProvider:
        """Get a provider by name or randomly weighted by availability."""
        if name:
            for provider in self.providers:
                if provider.name == name:
                    return provider
            raise ValueError(f"Provider '{name}' not found or not configured")

        # Filter to configured providers, excluding direct for production
        available = [p for p in self.providers if p.is_configured()]
        if not available:
            raise ValueError("No proxy providers configured")

        # Prefer paid providers over direct/free
        paid_providers = [p for p in available if p.name not in ("direct", "free")]
        if paid_providers:
            return random.choice(paid_providers)

        return random.choice(available)

    def _is_rate_limited(self, proxy_key: str) -> bool:
        """Check if a proxy has exceeded its rate limit."""
        if proxy_key not in self._usage_counts:
            return False

        # Remove old usage records
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        self._usage_counts[proxy_key] = [
            t for t in self._usage_counts[proxy_key] if t > cutoff
        ]

        return len(self._usage_counts[proxy_key]) >= self.max_requests_per_hour

    def _is_blocked(self, proxy_key: str) -> bool:
        """Check if a proxy is currently blocked."""
        if proxy_key not in self._blocked_proxies:
            return False

        # Unblock after 1 hour
        blocked_at = self._blocked_proxies[proxy_key]
        if datetime.now(timezone.utc) - blocked_at > timedelta(hours=1):
            del self._blocked_proxies[proxy_key]
            return False

        return True

    def _record_usage(self, proxy_key: str) -> None:
        """Record proxy usage for rate limiting."""
        if proxy_key not in self._usage_counts:
            self._usage_counts[proxy_key] = []
        self._usage_counts[proxy_key].append(datetime.now(timezone.utc))

    async def get_proxy(
        self,
        geo: str = "US",
        provider_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Proxy:
        """
        Get a proxy for use.

        Args:
            geo: Geographic location code
            provider_name: Specific provider to use
            session_id: Session ID for sticky sessions

        Returns:
            Proxy instance ready for use
        """
        async with self._lock:
            # Generate unique session ID if not provided
            if not session_id:
                session_id = f"session_{int(time.time())}_{random.randint(1000, 9999)}"

            provider = self._get_provider(provider_name)
            credentials = provider.get_proxy(geo=geo, session_id=session_id)

            # Create proxy key for tracking
            proxy_key = f"{provider.name}_{geo}_{session_id}"

            # Check rate limits and blocks (skip for direct)
            if credentials.protocol != "direct":
                # Try to find an unblocked, un-rate-limited proxy
                attempts = 0
                max_attempts = 5

                while (self._is_rate_limited(proxy_key) or self._is_blocked(proxy_key)) and attempts < max_attempts:
                    session_id = f"session_{int(time.time())}_{random.randint(1000, 9999)}"
                    credentials = provider.get_proxy(geo=geo, session_id=session_id)
                    proxy_key = f"{provider.name}_{geo}_{session_id}"
                    attempts += 1

                if attempts >= max_attempts:
                    logger.warning(f"All proxies rate limited or blocked, using anyway: {proxy_key}")

            # Get or create proxy object
            if proxy_key in self._proxies:
                proxy = self._proxies[proxy_key]
            else:
                proxy = Proxy(
                    credentials=credentials,
                    provider=provider.name,
                    geo=geo,
                    session_id=session_id,
                )
                self._proxies[proxy_key] = proxy

            self._record_usage(proxy_key)
            return proxy

    async def mark_success(self, proxy: Proxy, response_time_ms: int) -> None:
        """Record a successful request."""
        async with self._lock:
            proxy.record_success(response_time_ms)
            logger.debug(
                f"Proxy success: {proxy.provider} geo={proxy.geo} "
                f"response_time={response_time_ms}ms success_rate={proxy.success_rate:.1f}%"
            )

    async def mark_failure(self, proxy: Proxy, error: str) -> None:
        """Record a failed request."""
        async with self._lock:
            proxy.record_failure()
            logger.warning(
                f"Proxy failure: {proxy.provider} geo={proxy.geo} "
                f"error={error} success_rate={proxy.success_rate:.1f}%"
            )

    async def mark_blocked(self, proxy: Proxy) -> None:
        """Mark a proxy as blocked by Google."""
        async with self._lock:
            proxy.record_block()
            proxy_key = f"{proxy.provider}_{proxy.geo}_{proxy.session_id}"
            self._blocked_proxies[proxy_key] = datetime.now(timezone.utc)
            logger.error(
                f"Proxy blocked: {proxy.provider} geo={proxy.geo} "
                f"session_id={proxy.session_id}"
            )

    async def get_health_report(self) -> dict:
        """Get current health statistics for all proxies."""
        async with self._lock:
            report = {
                "total_proxies": len(self._proxies),
                "blocked_count": len(self._blocked_proxies),
                "providers": {},
            }

            for proxy_key, proxy in self._proxies.items():
                provider = proxy.provider
                if provider not in report["providers"]:
                    report["providers"][provider] = {
                        "total": 0,
                        "success_count": 0,
                        "failure_count": 0,
                        "block_count": 0,
                        "avg_response_time_ms": 0,
                    }

                stats = report["providers"][provider]
                stats["total"] += 1
                stats["success_count"] += proxy.success_count
                stats["failure_count"] += proxy.failure_count
                stats["block_count"] += proxy.block_count
                stats["avg_response_time_ms"] = (
                    stats["avg_response_time_ms"] + proxy.avg_response_time_ms
                ) // 2

            return report

    def has_configured_providers(self) -> bool:
        """Check if any paid providers are configured."""
        return any(
            p.is_configured() and p.name not in ("direct", "free")
            for p in self.providers
        )
