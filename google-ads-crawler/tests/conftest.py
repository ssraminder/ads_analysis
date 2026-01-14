"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.connection import Base
from src.database.models import (
    AdAppearance,
    Advertiser,
    CrawlJob,
    Keyword,
    KeywordAdvertiserStats,
    ProxyHealth,
)


# Test database URLs (SQLite for simplicity)
TEST_DATABASE_URL = "sqlite:///./test.db"
TEST_ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./test_async.db"


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def sync_engine():
    """Create a sync test database engine."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def sync_session(sync_engine) -> Generator[Session, None, None]:
    """Create a sync database session for tests."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create an async test database engine."""
    engine = create_async_engine(
        TEST_ASYNC_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create an async database session for tests."""
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with AsyncSessionLocal() as session:
        yield session


# Sample data fixtures

@pytest.fixture
def sample_keyword_data():
    """Sample keyword data for testing."""
    return {
        "keyword": "buy shoes online",
        "category": "ecommerce",
        "crawl_priority": 7,
        "search_volume": 10000,
    }


@pytest.fixture
def sample_advertiser_data():
    """Sample advertiser data for testing."""
    return {
        "domain": "example.com",
        "root_domain": "example.com",
        "company_name": "Example Inc",
    }


@pytest.fixture
def sample_ad_html():
    """Sample Google SERP ad HTML for testing extraction."""
    return """
    <div class="uEierd" data-text-ad="1">
        <div class="v5yQqb">
            <a href="https://www.example.com/landing?utm_source=google" data-rw="https://www.example.com">
                <h3 class="sVXRqc">
                    Buy Premium Shoes - Free Shipping Today
                </h3>
            </a>
        </div>
        <div class="qzEoUe">
            <cite>www.example.com</cite>
            <span> › shoes › premium</span>
        </div>
        <div class="VwiC3b">
            Shop our collection of premium shoes. Free shipping on orders over $50.
            Wide selection of styles and sizes. Order now!
        </div>
        <div class="MhgNwc">
            <a href="https://www.example.com/mens">Men's Shoes</a>
            <a href="https://www.example.com/womens">Women's Shoes</a>
        </div>
    </div>
    """


@pytest.fixture
def sample_serp_page_html():
    """Sample full Google SERP page HTML for testing."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>buy shoes online - Google Search</title></head>
    <body>
        <div id="tads">
            <div class="uEierd" data-text-ad="1">
                <div class="v5yQqb">
                    <a href="https://www.shoestore.com/sale" data-rw="https://www.shoestore.com">
                        <h3 class="sVXRqc">ShoeStore - 50% Off All Shoes</h3>
                    </a>
                </div>
                <div class="qzEoUe"><cite>www.shoestore.com</cite></div>
                <div class="VwiC3b">Huge sale on all shoes. Free returns.</div>
            </div>
            <div class="uEierd" data-text-ad="1">
                <div class="v5yQqb">
                    <a href="https://www.footwear.com/shop">
                        <h3 class="sVXRqc">Footwear.com - Premium Shoes Online</h3>
                    </a>
                </div>
                <div class="qzEoUe"><cite>www.footwear.com</cite></div>
                <div class="VwiC3b">Quality footwear for every occasion.</div>
            </div>
        </div>
        <div id="search">
            <!-- Organic results would go here -->
        </div>
        <div id="tadsb">
            <div class="uEierd" data-text-ad="1">
                <div class="v5yQqb">
                    <a href="https://www.cheapshoes.com">
                        <h3 class="sVXRqc">Cheap Shoes - Best Prices Guaranteed</h3>
                    </a>
                </div>
                <div class="qzEoUe"><cite>www.cheapshoes.com</cite></div>
                <div class="VwiC3b">Lowest prices on shoes online.</div>
            </div>
        </div>
    </body>
    </html>
    """
