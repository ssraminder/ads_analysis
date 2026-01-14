"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    DATABASE_URL: str = Field(
        default="postgresql://user:pass@localhost:5432/adscraper",
        description="PostgreSQL connection URL (sync)"
    )
    DATABASE_ASYNC_URL: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection URL (async) - auto-generated if not set"
    )

    @property
    def async_database_url(self) -> str:
        """Get async database URL, auto-converting from DATABASE_URL if needed."""
        if self.DATABASE_ASYNC_URL:
            return self.DATABASE_ASYNC_URL
        # Convert postgresql:// to postgresql+asyncpg://
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )

    # Proxy Providers
    BRIGHTDATA_API_KEY: Optional[str] = Field(
        default=None,
        description="Bright Data customer ID (e.g., hl_xxxxxxxx)"
    )
    BRIGHTDATA_ZONE: Optional[str] = Field(
        default=None,
        description="Bright Data zone name"
    )
    BRIGHTDATA_PASSWORD: Optional[str] = Field(
        default=None,
        description="Bright Data zone password"
    )
    OXYLABS_USERNAME: Optional[str] = Field(
        default=None,
        description="Oxylabs username"
    )
    OXYLABS_PASSWORD: Optional[str] = Field(
        default=None,
        description="Oxylabs password"
    )

    # AI / LLM
    ANTHROPIC_API_KEY: Optional[str] = Field(
        default=None,
        description="Anthropic API key for AI ad copy generation"
    )
    AI_MODEL: str = Field(
        default="claude-sonnet-4-20250514",
        description="AI model to use for ad copy generation"
    )

    # Scraping Settings
    SCRAPE_DELAY_MIN_SECONDS: int = Field(
        default=30,
        description="Minimum delay between scrapes in seconds"
    )
    SCRAPE_DELAY_MAX_SECONDS: int = Field(
        default=120,
        description="Maximum delay between scrapes in seconds"
    )
    MAX_RETRIES: int = Field(
        default=3,
        description="Maximum number of retry attempts"
    )
    REQUEST_TIMEOUT_SECONDS: int = Field(
        default=30,
        description="Request timeout in seconds"
    )

    # Rate Limits
    MAX_REQUESTS_PER_PROXY_PER_HOUR: int = Field(
        default=30,
        description="Maximum requests per proxy per hour"
    )
    MAX_CONCURRENT_SCRAPERS: int = Field(
        default=5,
        description="Maximum concurrent scraper instances"
    )

    # Geo Targeting
    DEFAULT_GEO: str = Field(
        default="US",
        description="Default geographic location for searches"
    )
    SUPPORTED_GEOS: List[str] = Field(
        default=["US", "UK", "CA", "AU", "DE", "FR", "ES", "IT", "NL", "BR"],
        description="Supported geographic locations"
    )

    # API Settings
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    API_DEBUG: bool = Field(default=False)

    # Celery Settings
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
