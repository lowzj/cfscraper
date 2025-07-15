"""
Unit tests for API endpoints
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone
import uuid
import json

from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.models.job import Job, JobStatus, ScraperType
from app.models.requests import ScrapeRequest, BulkScrapeRequest, JobSearchRequest
from app.models.responses import (
    ScrapeResponse, JobStatusResponse, JobResult, JobListResponse,
    HealthCheckResponse, DetailedHealthCheckResponse
)


@pytest.mark.unit
class TestScraperEndpoints:
    """Test scraper endpoints"""
    
    def test_create_scrape_job_success(self, client, mock_job_queue, sample_job_data):
        """Test successful scrape job creation"""
        with patch('app.api.routes.common.get_job_queue', return_value=mock_job_queue):
            response = client.post("/api/v1/scrape/", json=sample_job_data)
            
            assert response.status_code == 200
            data = response.json()
            
            assert "job_id" in data
            assert "task_id" in data
            assert data["status"] == "queued"
            assert "message" in data
            assert "created_at" in data
            
            # Verify queue was called
            mock_job_queue.enqueue.assert_called_once()
    
    def test_create_scrape_job_invalid_url(self, client):
        """Test scrape job creation with invalid URL"""
        invalid_data = {
            "url": "not-a-valid-url",
            "scraper_type": "cloudscraper"
        }
        
        response = client.post("/api/v1/scrape/", json=invalid_data)
        assert response.status_code == 422  # Validation error
    
    def test_create_scrape_job_missing_url(self, client):
        """Test scrape job creation without URL"""
        invalid_data = {
            "scraper_type": "cloudscraper"
        }
        
        response = client.post("/api/v1/scrape/", json=invalid_data)
        assert response.status_code == 422  # Validation error
    
    def test_create_scrape_job_invalid_scraper_type(self, client):
        """Test scrape job creation with invalid scraper type"""
        invalid_data = {
            "url": "https://example.com",
            "scraper_type": "invalid_scraper"
        }
        
        response = client.post("/api/v1/scrape/", json=invalid_data)
        assert response.status_code == 422  # Validation error
    
    def test_get_job_status_success(self, client, sample_job):
        """Test successful job status retrieval"""
        with patch('app.api.routes.common.get_job_by_id', return_value=sample_job):
            response = client.get(f"/api/v1/scrape/{sample_job.id}/status")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["job_id"] == sample_job.id
            assert data["status"] == sample_job.status.value
            assert "created_at" in data
    
    def test_get_job_status_not_found(self, client):
        """Test job status retrieval for non-existent job"""
        with patch('app.api.routes.common.get_job_by_id', side_effect=HTTPException(404, "Job not found")):
            response = client.get("/api/v1/scrape/nonexistent-id/status")
            assert response.status_code == 404
    
    def test_get_job_result_success(self, client, sample_job, sample_scraper_result):
        """Test successful job result retrieval"""
        # Set job as completed with result
        sample_job.status = JobStatus.COMPLETED
        sample_job.result = sample_scraper_result
        
        with patch('app.api.routes.common.get_job_by_id', return_value=sample_job):
            response = client.get(f"/api/v1/scrape/{sample_job.id}/result")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status_code"] == 200
            assert "content" in data
            assert "headers" in data
            assert "response_time" in data
    
    def test_get_job_result_not_completed(self, client, sample_job):
        """Test job result retrieval for incomplete job"""
        sample_job.status = JobStatus.RUNNING
        
        with patch('app.api.routes.common.get_job_by_id', return_value=sample_job):
            response = client.get(f"/api/v1/scrape/{sample_job.id}/result")
            assert response.status_code == 400  # Job not completed
    
    def test_bulk_scrape_success(self, client, mock_job_queue):
        """Test successful bulk scrape job creation"""
        bulk_data = {
            "jobs": [
                {
                    "url": "https://example.com/page1",
                    "scraper_type": "cloudscraper"
                },
                {
                    "url": "https://example.com/page2",
                    "scraper_type": "selenium"
                }
            ],
            "parallel_limit": 2
        }
        
        with patch('app.api.routes.common.get_job_queue', return_value=mock_job_queue):
            response = client.post("/api/v1/scrape/bulk", json=bulk_data)
            
            assert response.status_code == 200
            data = response.json()
            
            assert "bulk_id" in data
            assert "jobs" in data
            assert len(data["jobs"]) == 2
            assert data["total_jobs"] == 2
            
            # Verify queue was called for each job
            assert mock_job_queue.enqueue.call_count == 2
    
    def test_bulk_scrape_empty_jobs(self, client):
        """Test bulk scrape with empty jobs list"""
        bulk_data = {
            "jobs": [],
            "parallel_limit": 2
        }
        
        response = client.post("/api/v1/scrape/bulk", json=bulk_data)
        assert response.status_code == 422  # Validation error
    
    def test_bulk_scrape_too_many_jobs(self, client):
        """Test bulk scrape with too many jobs"""
        bulk_data = {
            "jobs": [{"url": f"https://example.com/page{i}", "scraper_type": "cloudscraper"} 
                    for i in range(101)],  # More than max allowed
            "parallel_limit": 2
        }
        
        response = client.post("/api/v1/scrape/bulk", json=bulk_data)
        assert response.status_code == 422  # Validation error


@pytest.mark.unit
class TestJobsEndpoints:
    """Test jobs management endpoints"""
    
    def test_list_jobs_success(self, client, test_db_session):
        """Test successful job listing"""
        # Create test jobs
        jobs = []
        for i in range(3):
            job = Job(
                id=str(uuid.uuid4()),
                url=f"https://example.com/page{i}",
                method="GET",
                scraper_type=ScraperType.CLOUDSCRAPER,
                status=JobStatus.QUEUED,
                created_at=datetime.now(timezone.utc)
            )
            test_db_session.add(job)
            jobs.append(job)
        test_db_session.commit()
        
        response = client.get("/api/v1/jobs/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "jobs" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert len(data["jobs"]) == 3
    
    def test_list_jobs_with_filters(self, client, test_db_session):
        """Test job listing with filters"""
        # Create test jobs with different statuses
        job1 = Job(
            id=str(uuid.uuid4()),
            url="https://example.com/page1",
            method="GET",
            scraper_type=ScraperType.CLOUDSCRAPER,
            status=JobStatus.QUEUED,
            created_at=datetime.now(timezone.utc)
        )
        job2 = Job(
            id=str(uuid.uuid4()),
            url="https://example.com/page2",
            method="GET",
            scraper_type=ScraperType.SELENIUM,
            status=JobStatus.COMPLETED,
            created_at=datetime.now(timezone.utc)
        )
        test_db_session.add_all([job1, job2])
        test_db_session.commit()
        
        # Filter by status
        response = client.get("/api/v1/jobs/?status=queued")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["status"] == "queued"
    
    def test_list_jobs_pagination(self, client, test_db_session):
        """Test job listing pagination"""
        # Create multiple test jobs
        for i in range(25):
            job = Job(
                id=str(uuid.uuid4()),
                url=f"https://example.com/page{i}",
                method="GET",
                scraper_type=ScraperType.CLOUDSCRAPER,
                status=JobStatus.QUEUED,
                created_at=datetime.now(timezone.utc)
            )
            test_db_session.add(job)
        test_db_session.commit()
        
        # Test first page
        response = client.get("/api/v1/jobs/?page=1&page_size=10")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 10
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total"] == 25
    
    def test_search_jobs_success(self, client, test_db_session):
        """Test successful job search"""
        # Create test job
        job = Job(
            id=str(uuid.uuid4()),
            url="https://example.com/search-test",
            method="GET",
            scraper_type=ScraperType.CLOUDSCRAPER,
            status=JobStatus.QUEUED,
            tags=["test", "search"],
            created_at=datetime.now(timezone.utc)
        )
        test_db_session.add(job)
        test_db_session.commit()
        
        search_data = {
            "query": "search-test",
            "tags": ["test"]
        }
        
        response = client.post("/api/v1/jobs/search", json=search_data)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 1
        assert "search-test" in data["jobs"][0]["url"]
    
    def test_get_job_by_id_success(self, client, sample_job):
        """Test successful job retrieval by ID"""
        with patch('app.api.routes.common.get_job_by_id', return_value=sample_job):
            response = client.get(f"/api/v1/jobs/{sample_job.id}")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["job_id"] == sample_job.id
            assert data["url"] == str(sample_job.url)
            assert data["status"] == sample_job.status.value
    
    def test_get_job_by_id_not_found(self, client):
        """Test job retrieval for non-existent job"""
        with patch('app.api.routes.common.get_job_by_id', side_effect=HTTPException(404, "Job not found")):
            response = client.get("/api/v1/jobs/nonexistent-id")
            assert response.status_code == 404
    
    def test_cancel_job_success(self, client, sample_job, mock_job_queue):
        """Test successful job cancellation"""
        sample_job.status = JobStatus.QUEUED
        
        with patch('app.api.routes.common.get_job_by_id', return_value=sample_job), \
             patch('app.api.routes.common.get_job_queue', return_value=mock_job_queue):
            
            response = client.post(f"/api/v1/jobs/{sample_job.id}/cancel")
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Job cancelled successfully"
    
    def test_cancel_job_already_completed(self, client, sample_job):
        """Test cancelling already completed job"""
        sample_job.status = JobStatus.COMPLETED
        
        with patch('app.api.routes.common.get_job_by_id', return_value=sample_job):
            response = client.post(f"/api/v1/jobs/{sample_job.id}/cancel")
            assert response.status_code == 400  # Cannot cancel completed job


@pytest.mark.unit
class TestHealthEndpoints:
    """Test health check endpoints"""
    
    def test_basic_health_check(self, client):
        """Test basic health check endpoint"""
        response = client.get("/api/v1/health/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"
        assert "timestamp" in data
        assert "uptime" in data
    
    def test_detailed_health_check(self, client, mock_job_queue, mock_job_executor):
        """Test detailed health check endpoint"""
        with patch('app.api.routes.common.get_job_queue', return_value=mock_job_queue), \
             patch('app.api.routes.common.get_job_executor', return_value=mock_job_executor):
            
            response = client.get("/api/v1/health/detailed")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "healthy"
            assert "components" in data
            assert "database" in data["components"]
            assert "queue" in data["components"]
            assert "executor" in data["components"]
    
    def test_ping_endpoint(self, client):
        """Test ping endpoint"""
        response = client.get("/api/v1/health/ping")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["message"] == "pong"
        assert "timestamp" in data
    
    def test_metrics_endpoint(self, client, test_db_session):
        """Test metrics endpoint"""
        # Create some test jobs for metrics
        for status in [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETED]:
            job = Job(
                id=str(uuid.uuid4()),
                url="https://example.com",
                method="GET",
                scraper_type=ScraperType.CLOUDSCRAPER,
                status=status,
                created_at=datetime.now(timezone.utc)
            )
            test_db_session.add(job)
        test_db_session.commit()
        
        response = client.get("/api/v1/health/metrics")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "total_jobs" in data
        assert "jobs_by_status" in data
        assert "jobs_by_scraper_type" in data
        assert "recent_activity" in data


@pytest.mark.unit
class TestExportEndpoints:
    """Test export endpoints"""
    
    def test_export_data_success(self, client, test_db_session):
        """Test successful data export"""
        # Create test job with result
        job = Job(
            id=str(uuid.uuid4()),
            url="https://example.com",
            method="GET",
            scraper_type=ScraperType.CLOUDSCRAPER,
            status=JobStatus.COMPLETED,
            result={"status_code": 200, "content": "test"},
            created_at=datetime.now(timezone.utc)
        )
        test_db_session.add(job)
        test_db_session.commit()
        
        export_data = {
            "format": "json",
            "compression": "none",
            "include_metadata": True
        }
        
        with patch('app.utils.data_export.DataExportManager') as mock_export_manager:
            mock_export_manager.return_value.export_data = AsyncMock(return_value="test_export.json")
            
            response = client.post("/api/v1/export/", json=export_data)
            
            assert response.status_code == 200
            data = response.json()
            
            assert "export_id" in data
            assert data["status"] == "completed"
            assert "file_path" in data
            assert "download_url" in data
    
    def test_export_data_no_data(self, client, test_db_session):
        """Test export with no data available"""
        export_data = {
            "format": "json",
            "job_ids": ["nonexistent-id"]
        }
        
        response = client.post("/api/v1/export/", json=export_data)
        assert response.status_code == 404  # No data found
    
    def test_download_export_success(self, client):
        """Test successful export download"""
        export_id = "test_export_123"
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', create=True) as mock_open:
            
            mock_open.return_value.__enter__.return_value.read.return_value = b'{"test": "data"}'
            
            response = client.get(f"/api/v1/export/download/{export_id}")
            
            assert response.status_code == 200
    
    def test_download_export_not_found(self, client):
        """Test download of non-existent export"""
        export_id = "nonexistent_export"
        
        with patch('os.path.exists', return_value=False):
            response = client.get(f"/api/v1/export/download/{export_id}")
            assert response.status_code == 404
