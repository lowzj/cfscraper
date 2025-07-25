"""
API routes initialization
"""
from fastapi import APIRouter

from .admin import router as admin_router
from .export import router as export_router
from .health import router as health_router
from .jobs import router as jobs_router
from .scraper import router as scraper_router

# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(scraper_router, prefix="/scrape", tags=["scraping"])
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(export_router, prefix="/export", tags=["export"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])

# Re-export for backward compatibility
router = api_router

# Re-export common utilities
from . import common

__all__ = ["api_router", "router", "common"]
