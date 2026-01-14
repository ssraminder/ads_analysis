"""Pydantic schemas for API request/response models."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============== Keyword Schemas ==============

class KeywordBase(BaseModel):
    """Base keyword schema."""
    keyword: str = Field(..., min_length=1, max_length=500)
    category: Optional[str] = Field(None, max_length=200)
    crawl_priority: int = Field(default=5, ge=1, le=10)
    crawl_frequency_hours: int = Field(default=24, ge=1, le=168)


class KeywordCreate(KeywordBase):
    """Schema for creating a keyword."""
    search_volume: Optional[int] = None
    cpc_estimate: Optional[Decimal] = None


class KeywordBulkCreate(BaseModel):
    """Schema for bulk keyword creation."""
    keywords: List[str] = Field(..., min_length=1, max_length=1000)
    category: Optional[str] = None


class KeywordResponse(KeywordBase):
    """Schema for keyword response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    search_volume: Optional[int]
    cpc_estimate: Optional[Decimal]
    last_crawled_at: Optional[datetime]
    is_active: bool
    created_at: datetime


class KeywordDetailResponse(KeywordResponse):
    """Detailed keyword response with stats."""
    total_advertisers: int = 0
    top_advertisers: List[Dict[str, Any]] = []


# ============== Advertiser Schemas ==============

class AdvertiserBase(BaseModel):
    """Base advertiser schema."""
    domain: str
    company_name: Optional[str] = None


class AdvertiserResponse(AdvertiserBase):
    """Schema for advertiser response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    root_domain: str
    estimated_monthly_spend: Optional[Decimal]
    total_keywords_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool


class AdvertiserDetailResponse(AdvertiserResponse):
    """Detailed advertiser response."""
    discovery_keyword: Optional[str] = None
    top_keywords: List[Dict[str, Any]] = []
    metadata: Optional[Dict[str, Any]] = None


class AdvertiserSearchRequest(BaseModel):
    """Schema for advertiser search."""
    domain: str = Field(..., min_length=1)


class CompetitorResponse(BaseModel):
    """Schema for competitor data."""
    advertiser: AdvertiserResponse
    shared_keywords: int


# ============== Ad Appearance Schemas ==============

class AdExtensionsSchema(BaseModel):
    """Schema for ad extensions."""
    sitelinks: List[Dict[str, Any]] = []
    callouts: List[str] = []
    structured_snippets: Dict[str, List[str]] = {}
    phone: Optional[str] = None
    location: Optional[str] = None
    price: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None


class AdAppearanceResponse(BaseModel):
    """Schema for ad appearance response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword_id: int
    advertiser_id: int
    position: int
    headline: str
    description: Optional[str]
    display_url: str
    final_url: str
    extensions: Optional[Dict[str, Any]]
    geo_location: str
    device_type: str
    scraped_at: datetime


class AdVariationResponse(BaseModel):
    """Schema for unique ad variations."""
    headline: str
    description: Optional[str]
    display_url: str
    first_seen: datetime
    last_seen: datetime
    appearance_count: int


# ============== Stats Schemas ==============

class KeywordStatsResponse(BaseModel):
    """Schema for keyword-advertiser stats."""
    model_config = ConfigDict(from_attributes=True)

    keyword_id: int
    advertiser_id: int
    appearance_count: int
    avg_position: Optional[Decimal]
    position_distribution: Optional[Dict[str, int]]
    first_seen_at: datetime
    last_seen_at: datetime
    days_active: int
    estimated_impressions: Optional[int]
    estimated_clicks: Optional[int]
    estimated_spend: Optional[Decimal]


class AdvertiserHistoryResponse(BaseModel):
    """Schema for advertiser history."""
    date: datetime
    keyword_count: int
    avg_position: float
    total_appearances: int
    estimated_spend: Decimal


# ============== Job Schemas ==============

class JobResponse(BaseModel):
    """Schema for crawl job response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    target: str
    status: str
    priority: int
    attempts: int
    max_attempts: int
    last_error: Optional[str]
    result_summary: Optional[Dict[str, Any]]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class BulkScrapeRequest(BaseModel):
    """Schema for bulk scrape request."""
    keyword_ids: List[int] = Field(..., min_length=1, max_length=100)
    geo: str = Field(default="US", max_length=5)
    device: str = Field(default="desktop")


class JobStatsResponse(BaseModel):
    """Schema for job statistics."""
    pending: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    blocked: int = 0
    total: int = 0


# ============== Scrape Schemas ==============

class ScrapeRequest(BaseModel):
    """Schema for immediate scrape request."""
    geo: str = Field(default="US", max_length=5)
    device: str = Field(default="desktop")


class ScrapeResponse(BaseModel):
    """Schema for scrape result."""
    keyword: str
    ads_found: int
    new_advertisers: int
    response_time_ms: int
    blocked: bool = False
    error: Optional[str] = None


# ============== Expansion Schemas ==============

class ExpandRequest(BaseModel):
    """Schema for keyword expansion request."""
    max_keywords: int = Field(default=100, ge=1, le=500)


class ExpandResponse(BaseModel):
    """Schema for expansion result."""
    advertiser_domain: str
    keywords_generated: int
    new_keywords_added: int
    keywords_queued: int


# ============== Suggestion Schemas ==============

class KeywordSuggestion(BaseModel):
    """Schema for keyword suggestion."""
    keyword: str
    source: str
    relevance_score: float


class SuggestionsResponse(BaseModel):
    """Schema for keyword suggestions response."""
    suggestions: List[KeywordSuggestion]


# ============== Pagination ==============

class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int


# ============== Ad Copy Generation Schemas ==============

class AdCopyGenerateRequest(BaseModel):
    """Schema for ad copy generation request."""
    business_name: Optional[str] = Field(None, max_length=100)
    business_description: Optional[str] = Field(None, max_length=500)
    target_audience: Optional[str] = Field(None, max_length=200)
    tone: str = Field(
        default="professional",
        description="Tone of ad copy: professional, friendly, urgent, luxurious, casual, authoritative, playful, trustworthy"
    )
    conversion_focus: str = Field(
        default="clicks",
        description="Optimization goal: clicks, leads, sales, brand_awareness, sign_ups, downloads, calls, store_visits"
    )
    num_variations: int = Field(default=3, ge=1, le=10)
    unique_selling_points: Optional[List[str]] = Field(None, max_length=10)
    use_competitor_insights: bool = Field(default=True)


class GeneratedAdCopyResponse(BaseModel):
    """Schema for generated ad copy response."""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    keyword_id: int
    headline_1: str
    headline_2: str
    headline_3: Optional[str]
    description_1: str
    description_2: Optional[str]
    display_path_1: Optional[str]
    display_path_2: Optional[str]
    call_to_action: Optional[str]
    target_audience: Optional[str]
    unique_selling_points: Optional[List[str]]
    tone: str
    conversion_focus: Optional[str]
    quality_score: Optional[int]
    is_favorite: bool = False
    created_at: Optional[datetime] = None


class AdCopyBulkGenerateRequest(BaseModel):
    """Schema for bulk ad copy generation."""
    keyword_ids: List[int] = Field(..., min_length=1, max_length=20)
    business_name: Optional[str] = None
    business_description: Optional[str] = None
    tone: str = "professional"
    conversion_focus: str = "clicks"
    num_variations: int = Field(default=2, ge=1, le=5)


class AdCopyImproveRequest(BaseModel):
    """Schema for ad copy improvement request."""
    original_headline: str = Field(..., max_length=90)
    original_description: str = Field(..., max_length=180)
    improvement_goal: str = Field(
        default="higher_ctr",
        description="Goal: higher_ctr, more_conversions, better_quality_score"
    )


# ============== Health Check ==============

class HealthResponse(BaseModel):
    """Schema for health check response."""
    status: str
    database: str
    redis: str
    version: str
