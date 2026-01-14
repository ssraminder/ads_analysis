"""SQLAlchemy database models."""

import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database.connection import Base


class KeywordSource(str, enum.Enum):
    """Source of keyword discovery."""
    SEED = "seed"
    EXPANDED = "expanded"
    RELATED = "related"


class DeviceType(str, enum.Enum):
    """Device type for ad appearance."""
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"


class JobType(str, enum.Enum):
    """Type of crawl job."""
    KEYWORD_SCRAPE = "keyword_scrape"
    DOMAIN_EXPANSION = "domain_expansion"
    KEYWORD_DISCOVERY = "keyword_discovery"


class JobStatus(str, enum.Enum):
    """Status of a crawl job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class Keyword(Base):
    """Keywords to track for ad scraping."""

    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    search_volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cpc_estimate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    source: Mapped[KeywordSource] = mapped_column(
        Enum(KeywordSource),
        default=KeywordSource.SEED,
        nullable=False
    )
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    crawl_priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    crawl_frequency_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    ad_appearances: Mapped[list["AdAppearance"]] = relationship(
        "AdAppearance",
        back_populates="keyword",
        cascade="all, delete-orphan"
    )
    keyword_stats: Mapped[list["KeywordAdvertiserStats"]] = relationship(
        "KeywordAdvertiserStats",
        back_populates="keyword",
        cascade="all, delete-orphan"
    )
    discovered_advertisers: Mapped[list["Advertiser"]] = relationship(
        "Advertiser",
        back_populates="discovery_keyword",
        foreign_keys="Advertiser.discovery_keyword_id"
    )

    __table_args__ = (
        Index("ix_keywords_crawl_priority", "crawl_priority", "last_crawled_at"),
        Index("ix_keywords_active_priority", "is_active", "crawl_priority"),
    )

    def __repr__(self) -> str:
        return f"<Keyword(id={self.id}, keyword='{self.keyword}')>"


class Advertiser(Base):
    """Discovered advertisers/businesses."""

    __tablename__ = "advertisers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    root_domain: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    estimated_monthly_spend: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True
    )
    total_keywords_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    discovery_keyword_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("keywords.id", ondelete="SET NULL"),
        nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    discovery_keyword: Mapped[Optional["Keyword"]] = relationship(
        "Keyword",
        back_populates="discovered_advertisers",
        foreign_keys=[discovery_keyword_id]
    )
    ad_appearances: Mapped[list["AdAppearance"]] = relationship(
        "AdAppearance",
        back_populates="advertiser",
        cascade="all, delete-orphan"
    )
    advertiser_stats: Mapped[list["KeywordAdvertiserStats"]] = relationship(
        "KeywordAdvertiserStats",
        back_populates="advertiser",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_advertisers_root_domain_active", "root_domain", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Advertiser(id={self.id}, domain='{self.domain}')>"


class AdAppearance(Base):
    """Individual ad appearances in search results."""

    __tablename__ = "ad_appearances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    advertiser_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("advertisers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    final_url: Mapped[str] = mapped_column(Text, nullable=False)
    extensions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    geo_location: Mapped[str] = mapped_column(String(10), default="US", nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(
        Enum(DeviceType),
        default=DeviceType.DESKTOP,
        nullable=False
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    keyword: Mapped["Keyword"] = relationship("Keyword", back_populates="ad_appearances")
    advertiser: Mapped["Advertiser"] = relationship("Advertiser", back_populates="ad_appearances")

    __table_args__ = (
        Index("ix_ad_appearances_keyword_scraped", "keyword_id", "scraped_at"),
        Index("ix_ad_appearances_advertiser_scraped", "advertiser_id", "scraped_at"),
        Index("ix_ad_appearances_geo_device", "geo_location", "device_type"),
    )

    def __repr__(self) -> str:
        return f"<AdAppearance(id={self.id}, keyword_id={self.keyword_id}, position={self.position})>"


class KeywordAdvertiserStats(Base):
    """Aggregated statistics for keyword-advertiser combinations."""

    __tablename__ = "keyword_advertiser_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    advertiser_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("advertisers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    appearance_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_position: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2), nullable=True)
    position_distribution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    days_active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    estimated_impressions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_clicks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_spend: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    keyword: Mapped["Keyword"] = relationship("Keyword", back_populates="keyword_stats")
    advertiser: Mapped["Advertiser"] = relationship("Advertiser", back_populates="advertiser_stats")

    __table_args__ = (
        UniqueConstraint("keyword_id", "advertiser_id", name="uq_keyword_advertiser"),
        Index("ix_kas_advertiser_keyword", "advertiser_id", "keyword_id"),
    )

    def __repr__(self) -> str:
        return f"<KeywordAdvertiserStats(keyword_id={self.keyword_id}, advertiser_id={self.advertiser_id})>"


class CrawlJob(Base):
    """Tracking for crawl jobs."""

    __tablename__ = "crawl_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[JobType] = mapped_column(Enum(JobType), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus),
        default=JobStatus.PENDING,
        nullable=False,
        index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    __table_args__ = (
        Index("ix_crawl_jobs_status_priority", "status", "priority"),
        Index("ix_crawl_jobs_scheduled", "scheduled_for", "status"),
    )

    def __repr__(self) -> str:
        return f"<CrawlJob(id={self.id}, type={self.job_type}, target='{self.target}')>"


class ProxyHealth(Base):
    """Health tracking for proxy servers."""

    __tablename__ = "proxy_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proxy_url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    block_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_blocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    __table_args__ = (
        Index("ix_proxy_health_active_provider", "is_active", "provider"),
    )

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage."""
        total = self.success_count + self.failure_count + self.block_count
        if total == 0:
            return 0.0
        return (self.success_count / total) * 100

    def __repr__(self) -> str:
        return f"<ProxyHealth(id={self.id}, provider='{self.provider}')>"
