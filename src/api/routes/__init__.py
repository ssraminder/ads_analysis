"""API routes package."""

from src.api.routes.adcopy import router as adcopy_router
from src.api.routes.advertisers import router as advertisers_router
from src.api.routes.jobs import router as jobs_router
from src.api.routes.keywords import router as keywords_router

__all__ = ["keywords_router", "advertisers_router", "jobs_router", "adcopy_router"]
