"""
Request models for the CFScraper API
"""
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field, HttpUrl, field_validator

from .job import ScraperType


class ScrapeConfig(BaseModel):
    """Configuration for scraping operations"""

    # Request configuration
    timeout: Optional[int] = Field(
        default=30,
        ge=1,
        le=300,
        description="Request timeout in seconds (1-300)"
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts (0-10)"
    )
    delay_between_retries: Optional[int] = Field(
        default=1,
        ge=0,
        le=60,
        description="Delay between retries in seconds (0-60)"
    )

    # Browser configuration (for Selenium)
    headless: bool = Field(
        default=True,
        description="Run browser in headless mode"
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="Custom user agent string"
    )
    window_size: Optional[str] = Field(
        default="1920,1080",
        description="Browser window size (width,height)"
    )

    # Proxy configuration
    proxy: Optional[str] = Field(
        default=None,
        description="Proxy URL (http://user:pass@host:port)"
    )

    # CloudFlare bypass configuration
    bypass_cloudflare: bool = Field(
        default=True,
        description="Enable CloudFlare bypass"
    )

    # Content filtering
    extract_text: bool = Field(
        default=False,
        description="Extract text content from HTML"
    )
    extract_links: bool = Field(
        default=False,
        description="Extract all links from the page"
    )
    extract_images: bool = Field(
        default=False,
        description="Extract image URLs from the page"
    )

    # JavaScript execution
    wait_for_selector: Optional[str] = Field(
        default=None,
        description="CSS selector to wait for before scraping"
    )
    execute_script: Optional[str] = Field(
        default=None,
        description="JavaScript code to execute on the page"
    )

    @field_validator('window_size')
    def validate_window_size(cls, v):
        if v and ',' in v:
            try:
                width, height = v.split(',')
                width, height = int(width), int(height)
                if width < 100 or height < 100 or width > 4000 or height > 4000:
                    raise ValueError("Window dimensions must be between 100x100 and 4000x4000")
            except ValueError:
                raise ValueError("Window size must be in format 'width,height' (e.g., '1920,1080')")
        return v

    class Config:
        schema_extra = {
            "example": {
                "timeout": 30,
                "max_retries": 3,
                "delay_between_retries": 1,
                "headless": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "window_size": "1920,1080",
                "proxy": None,
                "bypass_cloudflare": True,
                "extract_text": False,
                "extract_links": False,
                "extract_images": False,
                "wait_for_selector": None,
                "execute_script": None
            }
        }


class ScrapeRequest(BaseModel):
    """Request model for scraping jobs"""

    # Required fields
    url: HttpUrl = Field(
        ...,
        description="URL to scrape (must be valid HTTP/HTTPS URL)"
    )

    # Optional request configuration
    method: str = Field(
        default="GET",
        description="HTTP method (GET, POST, PUT, DELETE, etc.)"
    )
    headers: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="HTTP headers to send with request"
    )
    data: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Request body data (for POST/PUT requests)"
    )
    params: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="URL query parameters"
    )

    # Scraper configuration
    scraper_type: ScraperType = Field(
        default=ScraperType.CLOUDSCRAPER,
        description="Type of scraper to use"
    )
    config: ScrapeConfig = Field(
        default_factory=ScrapeConfig,
        description="Scraping configuration options"
    )

    # Job metadata
    tags: Optional[List[str]] = Field(
        default_factory=list,
        max_length=10,
        description="Tags for job categorization"
    )
    priority: int = Field(
        default=0,
        ge=-10,
        le=10,
        description="Job priority (-10 to 10, higher is more priority)"
    )
    callback_url: Optional[HttpUrl] = Field(
        default=None,
        description="URL to POST job completion notification"
    )

    @field_validator('method')
    def validate_method(cls, v):
        allowed_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
        if v.upper() not in allowed_methods:
            raise ValueError(f"Method must be one of: {', '.join(allowed_methods)}")
        return v.upper()

    @field_validator('tags')
    def validate_tags(cls, v):
        if v and len(v) > 10:
            raise ValueError("Maximum 10 tags allowed")
        return v

    class Config:
        schema_extra = {
            "example": {
                "url": "https://example.com/page",
                "method": "GET",
                "headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                },
                "data": {},
                "params": {
                    "page": "1",
                    "limit": "20"
                },
                "scraper_type": "cloudscraper",
                "config": {
                    "timeout": 30,
                    "max_retries": 3,
                    "headless": True,
                    "bypass_cloudflare": True
                },
                "tags": ["web-scraping", "data-collection"],
                "priority": 0,
                "callback_url": None
            }
        }


class BulkScrapeRequest(BaseModel):
    """Request model for bulk scraping operations"""

    jobs: List[ScrapeRequest] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of scraping jobs (max 100)"
    )

    # Bulk operation settings
    parallel_limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum parallel jobs to run (1-20)"
    )
    stop_on_error: bool = Field(
        default=False,
        description="Stop all jobs if one fails"
    )

    class Config:
        schema_extra = {
            "example": {
                "jobs": [
                    {
                        "url": "https://example.com/page1",
                        "scraper_type": "cloudscraper",
                        "tags": ["bulk-job-1"]
                    },
                    {
                        "url": "https://example.com/page2",
                        "scraper_type": "selenium",
                        "tags": ["bulk-job-2"]
                    }
                ],
                "parallel_limit": 5,
                "stop_on_error": False
            }
        }


class JobSearchRequest(BaseModel):
    """Request model for job search"""

    query: Optional[str] = Field(
        default=None,
        description="Search query (URL, job ID, or text)"
    )
    status: Optional[List[str]] = Field(
        default=None,
        description="Filter by job status"
    )
    scraper_type: Optional[List[ScraperType]] = Field(
        default=None,
        description="Filter by scraper type"
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Filter by tags"
    )
    date_from: Optional[str] = Field(
        default=None,
        description="Filter jobs created after this date (ISO format)"
    )
    date_to: Optional[str] = Field(
        default=None,
        description="Filter jobs created before this date (ISO format)"
    )

    # Pagination
    page: int = Field(
        default=1,
        ge=1,
        description="Page number (starts from 1)"
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Items per page (1-100)"
    )

    # Sorting
    sort_by: str = Field(
        default="created_at",
        description="Sort field (created_at, updated_at, priority)"
    )
    sort_order: str = Field(
        default="desc",
        description="Sort order (asc, desc)"
    )

    @field_validator('sort_by')
    def validate_sort_by(cls, v):
        allowed_fields = ['created_at', 'updated_at', 'priority', 'status']
        if v not in allowed_fields:
            raise ValueError(f"Sort field must be one of: {', '.join(allowed_fields)}")
        return v

    @field_validator('sort_order')
    def validate_sort_order(cls, v):
        if v.lower() not in ['asc', 'desc']:
            raise ValueError("Sort order must be 'asc' or 'desc'")
        return v.lower()

    class Config:
        schema_extra = {
            "example": {
                "query": "example.com",
                "status": ["completed", "running"],
                "scraper_type": ["cloudscraper"],
                "tags": ["important"],
                "date_from": "2023-01-01T00:00:00Z",
                "date_to": "2023-12-31T23:59:59Z",
                "page": 1,
                "page_size": 20,
                "sort_by": "created_at",
                "sort_order": "desc"
            }
        }
