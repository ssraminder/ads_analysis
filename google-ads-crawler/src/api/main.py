"""FastAPI main application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src import __version__
from src.api.routes import advertisers_router, jobs_router, keywords_router
from src.api.schemas import HealthResponse
from src.config import settings
from src.database.connection import async_engine, init_async_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Google Ads Crawler API...")

    # Initialize database
    try:
        await init_async_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Google Ads Crawler API...")
    await async_engine.dispose()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Google Ads Competitive Intelligence Crawler",
        description="""
        A web scraping system to discover businesses advertising on Google
        and analyze their advertising strategies.

        ## Features

        - **Keyword Scraping**: Scrape Google SERP for ads on specific keywords
        - **Advertiser Discovery**: Track which domains are advertising
        - **Keyword Expansion**: Discover more keywords advertisers bid on
        - **Spend Estimation**: Estimate advertising spend based on position data
        - **Competitor Analysis**: Find and compare competing advertisers

        ## API Sections

        - **/api/keywords**: Manage seed keywords and view results
        - **/api/advertisers**: View discovered advertisers and their data
        - **/api/jobs**: Monitor and manage crawl jobs
        """,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(keywords_router)
    app.include_router(advertisers_router)
    app.include_router(jobs_router)

    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # Health check endpoint
    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check():
        """Check API health status."""
        db_status = "healthy"
        redis_status = "healthy"

        # Check database
        try:
            from sqlalchemy import text
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            db_status = "unhealthy"

        # Check Redis
        try:
            import redis
            r = redis.from_url(settings.REDIS_URL)
            r.ping()
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            redis_status = "unhealthy"

        overall_status = "healthy" if db_status == "healthy" and redis_status == "healthy" else "degraded"

        return HealthResponse(
            status=overall_status,
            database=db_status,
            redis=redis_status,
            version=__version__,
        )

    # Root endpoint
    @app.get("/", tags=["root"])
    async def root():
        """API root endpoint."""
        return {
            "name": "Google Ads Competitive Intelligence Crawler",
            "version": __version__,
            "docs": "/docs",
            "health": "/health",
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_DEBUG,
    )
