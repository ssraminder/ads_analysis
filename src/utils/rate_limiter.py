"""Rate limiting utilities."""

import asyncio
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import logging

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_minute: int = 2
    requests_per_hour: int = 30
    min_delay_seconds: float = 30.0
    max_delay_seconds: float = 120.0
    burst_limit: int = 3  # Max requests in quick succession
    burst_window_seconds: float = 60.0


class RateLimiter:
    """
    Async-safe rate limiter with multiple strategies.

    Implements:
    - Token bucket for burst control
    - Sliding window for per-minute/hour limits
    - Random delays for anti-detection
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig(
            min_delay_seconds=settings.SCRAPE_DELAY_MIN_SECONDS,
            max_delay_seconds=settings.SCRAPE_DELAY_MAX_SECONDS,
            requests_per_hour=settings.MAX_REQUESTS_PER_PROXY_PER_HOUR,
        )

        # Track requests by key (e.g., proxy, domain)
        self._request_times: Dict[str, List[datetime]] = defaultdict(list)
        self._last_request: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    def _clean_old_requests(self, key: str) -> None:
        """Remove request records older than 1 hour."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        self._request_times[key] = [
            t for t in self._request_times[key] if t > cutoff
        ]

    def _get_requests_in_window(self, key: str, window_seconds: float) -> int:
        """Count requests within a time window."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        return sum(1 for t in self._request_times[key] if t > cutoff)

    async def acquire(self, key: str = "default") -> float:
        """
        Acquire permission to make a request.

        Args:
            key: Rate limit bucket key (e.g., proxy ID, domain)

        Returns:
            Actual delay time in seconds
        """
        async with self._lock:
            self._clean_old_requests(key)
            now = datetime.now(timezone.utc)

            # Check burst limit
            burst_count = self._get_requests_in_window(key, self.config.burst_window_seconds)
            if burst_count >= self.config.burst_limit:
                # Wait until burst window passes
                oldest_in_burst = sorted(self._request_times[key])[-self.config.burst_limit]
                wait_time = (
                    oldest_in_burst + timedelta(seconds=self.config.burst_window_seconds) - now
                ).total_seconds()
                if wait_time > 0:
                    logger.debug(f"Burst limit reached for {key}, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)

            # Check hourly limit
            hourly_count = len(self._request_times[key])
            if hourly_count >= self.config.requests_per_hour:
                # Find when we can make next request
                oldest = min(self._request_times[key])
                wait_time = (oldest + timedelta(hours=1) - now).total_seconds()
                if wait_time > 0:
                    logger.warning(f"Hourly limit reached for {key}, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)

            # Add random delay for anti-detection
            delay = random.uniform(
                self.config.min_delay_seconds,
                self.config.max_delay_seconds
            )

            # Check time since last request
            if key in self._last_request:
                time_since_last = (now - self._last_request[key]).total_seconds()
                if time_since_last < delay:
                    additional_wait = delay - time_since_last
                    logger.debug(f"Adding delay for {key}: {additional_wait:.1f}s")
                    await asyncio.sleep(additional_wait)
                    delay = additional_wait

            # Record this request
            self._request_times[key].append(datetime.now(timezone.utc))
            self._last_request[key] = datetime.now(timezone.utc)

            return delay

    async def wait_with_jitter(self, base_delay: float = None) -> float:
        """
        Simple wait with random jitter.

        Args:
            base_delay: Base delay in seconds (uses config if not specified)

        Returns:
            Actual delay time
        """
        if base_delay is None:
            delay = random.uniform(
                self.config.min_delay_seconds,
                self.config.max_delay_seconds
            )
        else:
            # Add ±20% jitter
            jitter = base_delay * 0.2
            delay = random.uniform(base_delay - jitter, base_delay + jitter)

        await asyncio.sleep(delay)
        return delay

    def get_stats(self, key: str = "default") -> dict:
        """Get rate limiting statistics for a key."""
        self._clean_old_requests(key)

        return {
            "key": key,
            "requests_last_minute": self._get_requests_in_window(key, 60),
            "requests_last_hour": len(self._request_times[key]),
            "hourly_limit": self.config.requests_per_hour,
            "last_request": self._last_request.get(key),
            "can_request_now": len(self._request_times[key]) < self.config.requests_per_hour,
        }


class AdaptiveRateLimiter(RateLimiter):
    """
    Rate limiter that adapts based on response patterns.

    Increases delays when blocks are detected,
    decreases (slightly) when successful.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        super().__init__(config)
        self._success_streak: Dict[str, int] = defaultdict(int)
        self._current_multiplier: Dict[str, float] = defaultdict(lambda: 1.0)

    async def record_success(self, key: str = "default") -> None:
        """Record a successful request."""
        async with self._lock:
            self._success_streak[key] += 1

            # Slowly decrease multiplier after consistent success
            if self._success_streak[key] >= 10:
                self._current_multiplier[key] = max(
                    0.8,  # Don't go below 80% of base delay
                    self._current_multiplier[key] * 0.95
                )
                self._success_streak[key] = 0

    async def record_failure(self, key: str = "default", is_block: bool = False) -> None:
        """Record a failed request."""
        async with self._lock:
            self._success_streak[key] = 0

            if is_block:
                # Significantly increase delay on blocks
                self._current_multiplier[key] = min(
                    3.0,  # Max 3x delay
                    self._current_multiplier[key] * 1.5
                )
            else:
                # Modest increase on other failures
                self._current_multiplier[key] = min(
                    2.0,
                    self._current_multiplier[key] * 1.2
                )

    async def acquire(self, key: str = "default") -> float:
        """Acquire with adaptive delay."""
        base_delay = await super().acquire(key)

        # Apply multiplier
        multiplier = self._current_multiplier[key]
        if multiplier != 1.0:
            additional_delay = base_delay * (multiplier - 1)
            await asyncio.sleep(additional_delay)
            return base_delay * multiplier

        return base_delay
