"""
Basic tests for the CFScraper API
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Test the health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cfscraper-api"


def test_root_endpoint():
    """Test the root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_queue_status():
    """Test the queue status endpoint"""
    response = client.get("/api/v1/queue/status")
    assert response.status_code == 200
    data = response.json()
    assert "queue_size" in data
    assert "running_jobs" in data
    assert "max_concurrent_jobs" in data


def test_scrape_job_creation():
    """Test creating a scrape job"""
    job_data = {
        "url": "https://httpbin.org/html",
        "method": "GET",
        "scraper_type": "cloudscraper"
    }
    response = client.post("/api/v1/scrape", json=job_data)
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "queued"


def test_invalid_url():
    """Test creating a job with invalid URL"""
    job_data = {
        "url": "invalid-url",
        "method": "GET"
    }
    response = client.post("/api/v1/scrape", json=job_data)
    assert response.status_code == 400


def test_job_status_not_found():
    """Test getting status of non-existent job"""
    response = client.get("/api/v1/jobs/nonexistent-task-id")
    assert response.status_code == 404


def test_list_jobs():
    """Test listing jobs"""
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert "total" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])