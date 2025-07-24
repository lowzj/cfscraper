"""
Response models for the CFScraper API
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field

from .job import JobStatus, ScraperType


class JobResult(BaseModel):
    """Model for job execution results"""

    # Response metadata
    status_code: Optional[int] = Field(
        default=None,
        description="HTTP response status code"
    )
    response_time: Optional[float] = Field(
        default=None,
        description="Response time in seconds"
    )
    content_length: Optional[int] = Field(
        default=None,
        description="Content length in bytes"
    )
    content_type: Optional[str] = Field(
        default=None,
        description="Content type of the response"
    )

    # Response data
    headers: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Response headers"
    )
    content: Optional[str] = Field(
        default=None,
        description="Response content (HTML, JSON, etc.)"
    )

    # Extracted data
    text: Optional[str] = Field(
        default=None,
        description="Extracted text content"
    )
    links: Optional[List[str]] = Field(
        default_factory=list,
        description="Extracted links"
    )
    images: Optional[List[str]] = Field(
        default_factory=list,
        description="Extracted image URLs"
    )

    # Metadata
    final_url: Optional[str] = Field(
        default=None,
        description="Final URL after redirects"
    )
    screenshot_url: Optional[str] = Field(
        default=None,
        description="URL to screenshot (if taken)"
    )

    # Error information
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if job failed"
    )
    error_type: Optional[str] = Field(
        default=None,
        description="Type of error that occurred"
    )

    class Config:
        schema_extra = {
            "example": {
                "status_code": 200,
                "response_time": 2.45,
                "content_length": 15420,
                "content_type": "text/html; charset=utf-8",
                "headers": {
                    "content-type": "text/html; charset=utf-8",
                    "server": "nginx/1.18.0"
                },
                "content": "<html><head><title>Example</title></head><body>...</body></html>",
                "text": "Example page content...",
                "links": ["https://example.com/page1", "https://example.com/page2"],
                "images": ["https://example.com/image1.jpg", "https://example.com/image2.png"],
                "final_url": "https://example.com/final-page",
                "screenshot_url": None,
                "error_message": None,
                "error_type": None
            }
        }


class ScrapeResponse(BaseModel):
    """Response model for scraping job creation"""

    job_id: str = Field(
        ...,
        description="Unique job identifier"
    )
    task_id: str = Field(
        ...,
        description="Task ID for tracking (same as job_id)"
    )
    status: JobStatus = Field(
        ...,
        description="Current job status"
    )
    message: str = Field(
        ...,
        description="Status message"
    )
    created_at: datetime = Field(
        ...,
        description="Job creation timestamp"
    )
    estimated_completion: Optional[datetime] = Field(
        default=None,
        description="Estimated completion time"
    )

    class Config:
        schema_extra = {
            "example": {
                "job_id": "job_123e4567-e89b-12d3-a456-426614174000",
                "task_id": "job_123e4567-e89b-12d3-a456-426614174000",
                "status": "queued",
                "message": "Job queued successfully",
                "created_at": "2023-01-01T12:00:00Z",
                "estimated_completion": "2023-01-01T12:01:00Z"
            }
        }


class JobStatusResponse(BaseModel):
    """Response model for job status requests"""

    job_id: str = Field(
        ...,
        description="Unique job identifier"
    )
    task_id: str = Field(
        ...,
        description="Task ID for tracking"
    )
    status: JobStatus = Field(
        ...,
        description="Current job status"
    )

    # Progress tracking
    progress: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Progress percentage (0-100)"
    )
    progress_message: Optional[str] = Field(
        default=None,
        description="Human-readable progress message"
    )

    # Job configuration
    url: Optional[str] = Field(
        default=None,
        description="Target URL being scraped"
    )
    method: Optional[str] = Field(
        default=None,
        description="HTTP method"
    )
    scraper_type: Optional[ScraperType] = Field(
        default=None,
        description="Scraper type used"
    )

    # Timestamps
    created_at: Optional[datetime] = Field(
        default=None,
        description="Job creation timestamp"
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="Job start timestamp"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Job completion timestamp"
    )

    # Results
    result: Optional[JobResult] = Field(
        default=None,
        description="Job result (if completed)"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message (if failed)"
    )

    # Metadata
    retry_count: int = Field(
        default=0,
        description="Number of retry attempts"
    )
    tags: Optional[List[str]] = Field(
        default_factory=list,
        description="Job tags"
    )
    priority: int = Field(
        default=0,
        description="Job priority"
    )

    class Config:
        schema_extra = {
            "example": {
                "job_id": "job_123e4567-e89b-12d3-a456-426614174000",
                "task_id": "job_123e4567-e89b-12d3-a456-426614174000",
                "status": "completed",
                "progress": 100,
                "progress_message": "Scraping completed successfully",
                "url": "https://example.com/page",
                "method": "GET",
                "scraper_type": "cloudscraper",
                "created_at": "2023-01-01T12:00:00Z",
                "started_at": "2023-01-01T12:00:05Z",
                "completed_at": "2023-01-01T12:00:15Z",
                "result": {
                    "status_code": 200,
                    "response_time": 2.45,
                    "content_length": 15420,
                    "content_type": "text/html; charset=utf-8"
                },
                "error_message": None,
                "retry_count": 0,
                "tags": ["web-scraping"],
                "priority": 0
            }
        }


class JobListResponse(BaseModel):
    """Response model for job listing"""

    jobs: List[JobStatusResponse] = Field(
        ...,
        description="List of jobs"
    )
    total: int = Field(
        ...,
        description="Total number of jobs matching criteria"
    )
    page: int = Field(
        ...,
        description="Current page number"
    )
    page_size: int = Field(
        ...,
        description="Items per page"
    )
    total_pages: int = Field(
        ...,
        description="Total number of pages"
    )
    has_next: bool = Field(
        ...,
        description="Whether there are more pages"
    )
    has_previous: bool = Field(
        ...,
        description="Whether there are previous pages"
    )

    class Config:
        schema_extra = {
            "example": {
                "jobs": [
                    {
                        "job_id": "job_123e4567-e89b-12d3-a456-426614174000",
                        "task_id": "job_123e4567-e89b-12d3-a456-426614174000",
                        "status": "completed",
                        "progress": 100,
                        "url": "https://example.com/page",
                        "scraper_type": "cloudscraper",
                        "created_at": "2023-01-01T12:00:00Z",
                        "completed_at": "2023-01-01T12:00:15Z"
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "total_pages": 1,
                "has_next": False,
                "has_previous": False
            }
        }


class BulkScrapeResponse(BaseModel):
    """Response model for bulk scraping operations"""

    batch_id: str = Field(
        ...,
        description="Unique batch identifier"
    )
    job_ids: List[str] = Field(
        ...,
        description="List of created job IDs"
    )
    total_jobs: int = Field(
        ...,
        description="Total number of jobs created"
    )
    status: str = Field(
        default="queued",
        description="Batch status"
    )
    created_at: datetime = Field(
        ...,
        description="Batch creation timestamp"
    )

    class Config:
        schema_extra = {
            "example": {
                "batch_id": "batch_123e4567-e89b-12d3-a456-426614174000",
                "job_ids": [
                    "job_123e4567-e89b-12d3-a456-426614174001",
                    "job_123e4567-e89b-12d3-a456-426614174002"
                ],
                "total_jobs": 2,
                "status": "queued",
                "created_at": "2023-01-01T12:00:00Z"
            }
        }


class HealthCheckResponse(BaseModel):
    """Response model for health check"""

    status: str = Field(
        ...,
        description="Overall health status"
    )
    version: str = Field(
        ...,
        description="API version"
    )
    timestamp: datetime = Field(
        ...,
        description="Health check timestamp"
    )
    uptime: float = Field(
        ...,
        description="Service uptime in seconds"
    )

    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "timestamp": "2023-01-01T12:00:00Z",
                "uptime": 3600.0
            }
        }


class DetailedHealthCheckResponse(BaseModel):
    """Response model for detailed health check"""

    status: str = Field(
        ...,
        description="Overall health status"
    )
    version: str = Field(
        ...,
        description="API version"
    )
    timestamp: datetime = Field(
        ...,
        description="Health check timestamp"
    )
    uptime: float = Field(
        ...,
        description="Service uptime in seconds"
    )

    # Component status
    components: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="Status of individual components"
    )

    # System metrics
    metrics: Dict[str, Any] = Field(
        ...,
        description="System performance metrics"
    )

    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "timestamp": "2023-01-01T12:00:00Z",
                "uptime": 3600.0,
                "components": {
                    "database": {
                        "status": "healthy",
                        "response_time": 0.015,
                        "last_check": "2023-01-01T12:00:00Z"
                    },
                    "redis": {
                        "status": "healthy",
                        "response_time": 0.002,
                        "last_check": "2023-01-01T12:00:00Z"
                    },
                    "scrapers": {
                        "status": "healthy",
                        "cloudscraper": "available",
                        "selenium": "available"
                    }
                },
                "metrics": {
                    "total_jobs": 1024,
                    "active_jobs": 5,
                    "completed_jobs": 1000,
                    "failed_jobs": 19,
                    "queue_size": 2,
                    "average_response_time": 2.5
                }
            }
        }


class MetricsResponse(BaseModel):
    """Response model for metrics endpoint"""

    # Job statistics
    jobs: Dict[str, int] = Field(
        ...,
        description="Job count statistics"
    )

    # Performance metrics
    performance: Dict[str, float] = Field(
        ...,
        description="Performance metrics"
    )

    # System metrics
    system: Dict[str, Any] = Field(
        ...,
        description="System resource metrics"
    )

    # Time-based metrics
    hourly_stats: Dict[str, int] = Field(
        ...,
        description="Hourly job statistics"
    )
    daily_stats: Dict[str, int] = Field(
        ...,
        description="Daily job statistics"
    )

    timestamp: datetime = Field(
        ...,
        description="Metrics collection timestamp"
    )

    class Config:
        schema_extra = {
            "example": {
                "jobs": {
                    "total": 1024,
                    "queued": 2,
                    "running": 5,
                    "completed": 1000,
                    "failed": 19,
                    "cancelled": 3
                },
                "performance": {
                    "average_response_time": 2.5,
                    "median_response_time": 2.1,
                    "success_rate": 0.98,
                    "throughput_per_hour": 120
                },
                "system": {
                    "cpu_usage": 0.25,
                    "memory_usage": 0.45,
                    "disk_usage": 0.15
                },
                "hourly_stats": {
                    "2023-01-01T11:00:00Z": 45,
                    "2023-01-01T12:00:00Z": 52
                },
                "daily_stats": {
                    "2023-01-01": 1200,
                    "2023-01-02": 1150
                },
                "timestamp": "2023-01-01T12:00:00Z"
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response model"""

    error: str = Field(
        ...,
        description="Error type"
    )
    message: str = Field(
        ...,
        description="Error message"
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional error details"
    )
    timestamp: datetime = Field(
        ...,
        description="Error timestamp"
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Request ID for tracking"
    )

    class Config:
        schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Invalid URL format",
                "details": {
                    "field": "url",
                    "value": "invalid-url",
                    "expected": "Valid HTTP/HTTPS URL"
                },
                "timestamp": "2023-01-01T12:00:00Z",
                "request_id": "req_123e4567-e89b-12d3-a456-426614174000"
            }
        }


class DownloadResponse(BaseModel):
    """Response model for file downloads"""

    download_url: str = Field(
        ...,
        description="URL to download the file"
    )
    filename: str = Field(
        ...,
        description="Suggested filename"
    )
    content_type: str = Field(
        ...,
        description="File content type"
    )
    file_size: Optional[int] = Field(
        default=None,
        description="File size in bytes"
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Download link expiration time"
    )

    class Config:
        schema_extra = {
            "example": {
                "download_url": "https://api.example.com/download/abc123",
                "filename": "scraped_content.html",
                "content_type": "text/html",
                "file_size": 15420,
                "expires_at": "2023-01-01T13:00:00Z"
            }
        }
