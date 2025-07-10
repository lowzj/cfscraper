"""
API routes initialization
"""
from fastapi import APIRouter

from .scraper import router as scraper_router
from .jobs import router as jobs_router
from .health import router as health_router

# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(scraper_router, prefix="/scrape", tags=["scraping"])
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(health_router, prefix="/health", tags=["health"])

# Re-export for backward compatibility
router = api_router