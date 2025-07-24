"""
Tests for request and response models
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models.job import JobStatus, ScraperType
from app.models.requests import ScrapeRequest, ScrapeConfig, BulkScrapeRequest, JobSearchRequest
from app.models.responses import (
    ScrapeResponse, JobStatusResponse, JobResult, JobListResponse,
    HealthCheckResponse, DetailedHealthCheckResponse, MetricsResponse
)


class TestScrapeConfig:
    """Test ScrapeConfig model"""

    def test_default_config(self):
        """Test default configuration"""
        config = ScrapeConfig()
        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.headless is True
        assert config.bypass_cloudflare is True

    def test_custom_config(self):
        """Test custom configuration"""
        config = ScrapeConfig(
            timeout=60,
            max_retries=5,
            headless=False,
            user_agent="Custom Agent",
            proxy="http://proxy:8080"
        )
        assert config.timeout == 60
        assert config.max_retries == 5
        assert config.headless is False
        assert config.user_agent == "Custom Agent"
        assert config.proxy == "http://proxy:8080"

    def test_invalid_timeout(self):
        """Test invalid timeout validation"""
        with pytest.raises(ValidationError):
            ScrapeConfig(timeout=0)  # Too low

        with pytest.raises(ValidationError):
            ScrapeConfig(timeout=400)  # Too high

    def test_invalid_retries(self):
        """Test invalid retries validation"""
        with pytest.raises(ValidationError):
            ScrapeConfig(max_retries=-1)  # Too low

        with pytest.raises(ValidationError):
            ScrapeConfig(max_retries=11)  # Too high

    def test_window_size_validation(self):
        """Test window size validation"""
        # Valid window size
        config = ScrapeConfig(window_size="1920,1080")
        assert config.window_size == "1920,1080"

        # Invalid format - should not raise error with None
        config = ScrapeConfig(window_size=None)
        assert config.window_size is None

        # Invalid dimensions should raise error
        with pytest.raises(ValidationError):
            ScrapeConfig(window_size="50,50")  # Too small


class TestScrapeRequest:
    """Test ScrapeRequest model"""

    def test_minimal_request(self):
        """Test minimal valid request"""
        request = ScrapeRequest(url="https://example.com")
        assert str(request.url) == "https://example.com/"  # HttpUrl adds trailing slash
        assert request.method == "GET"
        assert request.scraper_type == ScraperType.CLOUDSCRAPER
        assert request.priority == 0
        assert request.tags == []

    def test_full_request(self):
        """Test full request with all parameters"""
        request = ScrapeRequest(
            url="https://example.com/page",
            method="POST",
            headers={"Accept": "application/json"},
            data={"key": "value"},
            params={"q": "test"},
            scraper_type=ScraperType.SELENIUM,
            config=ScrapeConfig(timeout=60, headless=False),
            tags=["important", "test"],
            priority=5,
            callback_url="https://callback.example.com"
        )

        assert str(request.url) == "https://example.com/page"
        assert request.method == "POST"
        assert request.headers == {"Accept": "application/json"}
        assert request.data == {"key": "value"}
        assert request.params == {"q": "test"}
        assert request.scraper_type == ScraperType.SELENIUM
        assert request.config.timeout == 60
        assert request.config.headless is False
        assert request.tags == ["important", "test"]
        assert request.priority == 5
        assert str(request.callback_url) == "https://callback.example.com/"  # HttpUrl adds trailing slash

    def test_invalid_url(self):
        """Test invalid URL validation"""
        with pytest.raises(ValidationError):
            ScrapeRequest(url="invalid-url")

        with pytest.raises(ValidationError):
            ScrapeRequest(url="ftp://example.com")  # Invalid protocol

    def test_invalid_method(self):
        """Test invalid method validation"""
        with pytest.raises(ValidationError):
            ScrapeRequest(url="https://example.com", method="INVALID")

    def test_method_normalization(self):
        """Test method normalization to uppercase"""
        request = ScrapeRequest(url="https://example.com", method="post")
        assert request.method == "POST"

    def test_invalid_priority(self):
        """Test invalid priority validation"""
        with pytest.raises(ValidationError):
            ScrapeRequest(url="https://example.com", priority=-11)

        with pytest.raises(ValidationError):
            ScrapeRequest(url="https://example.com", priority=11)

    def test_too_many_tags(self):
        """Test too many tags validation"""
        tags = [f"tag{i}" for i in range(11)]  # 11 tags
        with pytest.raises(ValidationError):
            ScrapeRequest(url="https://example.com", tags=tags)


class TestBulkScrapeRequest:
    """Test BulkScrapeRequest model"""

    def test_valid_bulk_request(self):
        """Test valid bulk request"""
        jobs = [
            ScrapeRequest(url="https://example.com/page1"),
            ScrapeRequest(url="https://example.com/page2"),
        ]

        bulk_request = BulkScrapeRequest(
            jobs=jobs,
            parallel_limit=3,
            stop_on_error=True
        )

        assert len(bulk_request.jobs) == 2
        assert bulk_request.parallel_limit == 3
        assert bulk_request.stop_on_error is True

    def test_empty_jobs(self):
        """Test empty jobs validation"""
        with pytest.raises(ValidationError):
            BulkScrapeRequest(jobs=[])

    def test_too_many_jobs(self):
        """Test too many jobs validation"""
        jobs = [ScrapeRequest(url="https://example.com") for _ in range(101)]
        with pytest.raises(ValidationError):
            BulkScrapeRequest(jobs=jobs)

    def test_invalid_parallel_limit(self):
        """Test invalid parallel limit validation"""
        jobs = [ScrapeRequest(url="https://example.com")]

        with pytest.raises(ValidationError):
            BulkScrapeRequest(jobs=jobs, parallel_limit=0)

        with pytest.raises(ValidationError):
            BulkScrapeRequest(jobs=jobs, parallel_limit=21)


class TestJobSearchRequest:
    """Test JobSearchRequest model"""

    def test_default_search(self):
        """Test default search request"""
        request = JobSearchRequest()
        assert request.page == 1
        assert request.page_size == 20
        assert request.sort_by == "created_at"
        assert request.sort_order == "desc"

    def test_custom_search(self):
        """Test custom search request"""
        request = JobSearchRequest(
            query="example.com",
            status=["completed", "failed"],
            scraper_type=[ScraperType.SELENIUM],
            tags=["important"],
            date_from="2023-01-01T00:00:00Z",
            date_to="2023-12-31T23:59:59Z",
            page=2,
            page_size=50,
            sort_by="updated_at",
            sort_order="asc"
        )

        assert request.query == "example.com"
        assert request.status == ["completed", "failed"]
        assert request.scraper_type == [ScraperType.SELENIUM]
        assert request.tags == ["important"]
        assert request.date_from == "2023-01-01T00:00:00Z"
        assert request.date_to == "2023-12-31T23:59:59Z"
        assert request.page == 2
        assert request.page_size == 50
        assert request.sort_by == "updated_at"
        assert request.sort_order == "asc"

    def test_invalid_sort_by(self):
        """Test invalid sort_by validation"""
        with pytest.raises(ValidationError):
            JobSearchRequest(sort_by="invalid_field")

    def test_invalid_sort_order(self):
        """Test invalid sort_order validation"""
        with pytest.raises(ValidationError):
            JobSearchRequest(sort_order="invalid")

    def test_sort_order_normalization(self):
        """Test sort order normalization"""
        request = JobSearchRequest(sort_order="ASC")
        assert request.sort_order == "asc"


class TestJobResult:
    """Test JobResult model"""

    def test_minimal_result(self):
        """Test minimal job result"""
        result = JobResult()
        assert result.status_code is None
        assert result.content is None
        assert result.headers == {}
        assert result.links == []
        assert result.images == []

    def test_full_result(self):
        """Test full job result"""
        result = JobResult(
            status_code=200,
            response_time=2.5,
            content_length=1024,
            content_type="text/html",
            headers={"content-type": "text/html"},
            content="<html></html>",
            text="Sample text",
            links=["https://example.com/link1"],
            images=["https://example.com/image1.jpg"],
            final_url="https://example.com/final",
            screenshot_url="https://example.com/screenshot.png"
        )

        assert result.status_code == 200
        assert result.response_time == 2.5
        assert result.content_length == 1024
        assert result.content_type == "text/html"
        assert result.headers == {"content-type": "text/html"}
        assert result.content == "<html></html>"
        assert result.text == "Sample text"
        assert result.links == ["https://example.com/link1"]
        assert result.images == ["https://example.com/image1.jpg"]
        assert result.final_url == "https://example.com/final"
        assert result.screenshot_url == "https://example.com/screenshot.png"


class TestScrapeResponse:
    """Test ScrapeResponse model"""

    def test_scrape_response(self):
        """Test scrape response"""
        response = ScrapeResponse(
            job_id="job_123",
            task_id="job_123",
            status=JobStatus.QUEUED,
            message="Job queued successfully",
            created_at=datetime.utcnow()
        )

        assert response.job_id == "job_123"
        assert response.task_id == "job_123"
        assert response.status == JobStatus.QUEUED
        assert response.message == "Job queued successfully"
        assert isinstance(response.created_at, datetime)


class TestJobStatusResponse:
    """Test JobStatusResponse model"""

    def test_job_status_response(self):
        """Test job status response"""
        response = JobStatusResponse(
            job_id="job_123",
            task_id="job_123",
            status=JobStatus.COMPLETED,
            progress=100,
            progress_message="Completed successfully",
            url="https://example.com",
            method="GET",
            scraper_type=ScraperType.CLOUDSCRAPER,
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            retry_count=0,
            tags=["test"],
            priority=0
        )

        assert response.job_id == "job_123"
        assert response.task_id == "job_123"
        assert response.status == JobStatus.COMPLETED
        assert response.progress == 100
        assert response.progress_message == "Completed successfully"
        assert response.url == "https://example.com"
        assert response.method == "GET"
        assert response.scraper_type == ScraperType.CLOUDSCRAPER
        assert response.retry_count == 0
        assert response.tags == ["test"]
        assert response.priority == 0


class TestJobListResponse:
    """Test JobListResponse model"""

    def test_job_list_response(self):
        """Test job list response"""
        job_status = JobStatusResponse(
            job_id="job_123",
            task_id="job_123",
            status=JobStatus.COMPLETED
        )

        response = JobListResponse(
            jobs=[job_status],
            total=1,
            page=1,
            page_size=20,
            total_pages=1,
            has_next=False,
            has_previous=False
        )

        assert len(response.jobs) == 1
        assert response.total == 1
        assert response.page == 1
        assert response.page_size == 20
        assert response.total_pages == 1
        assert response.has_next is False
        assert response.has_previous is False


class TestHealthCheckResponse:
    """Test HealthCheckResponse model"""

    def test_health_check_response(self):
        """Test health check response"""
        response = HealthCheckResponse(
            status="healthy",
            version="1.0.0",
            timestamp=datetime.utcnow(),
            uptime=3600.0
        )

        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert isinstance(response.timestamp, datetime)
        assert response.uptime == 3600.0


class TestDetailedHealthCheckResponse:
    """Test DetailedHealthCheckResponse model"""

    def test_detailed_health_check_response(self):
        """Test detailed health check response"""
        components = {
            "database": {
                "status": "healthy",
                "response_time": 0.015
            }
        }

        metrics = {
            "total_jobs": 1000,
            "active_jobs": 5
        }

        response = DetailedHealthCheckResponse(
            status="healthy",
            version="1.0.0",
            timestamp=datetime.utcnow(),
            uptime=3600.0,
            components=components,
            metrics=metrics
        )

        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert isinstance(response.timestamp, datetime)
        assert response.uptime == 3600.0
        assert response.components == components
        assert response.metrics == metrics


class TestMetricsResponse:
    """Test MetricsResponse model"""

    def test_metrics_response(self):
        """Test metrics response"""
        jobs = {"total": 1000, "completed": 950}
        performance = {"average_response_time": 2.5}
        system = {"cpu_usage": 0.25}
        hourly_stats = {"2023-01-01T12:00:00Z": 50}
        daily_stats = {"2023-01-01": 1200}

        response = MetricsResponse(
            jobs=jobs,
            performance=performance,
            system=system,
            hourly_stats=hourly_stats,
            daily_stats=daily_stats,
            timestamp=datetime.utcnow()
        )

        assert response.jobs == jobs
        assert response.performance == performance
        assert response.system == system
        assert response.hourly_stats == hourly_stats
        assert response.daily_stats == daily_stats
        assert isinstance(response.timestamp, datetime)
