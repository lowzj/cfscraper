#!/usr/bin/env python3
"""
Manual test script to demonstrate the Phase 2 API implementation
"""
import json
import time
from fastapi.testclient import TestClient
from app.main import app

def test_api_endpoints():
    """Test all the implemented API endpoints"""
    client = TestClient(app)
    
    print("🚀 Testing CFScraper Phase 2 API Implementation")
    print("=" * 60)
    
    # Test Health Endpoints
    print("\n📊 Health & Monitoring Endpoints:")
    
    # Basic health check
    resp = client.get("/api/v1/health/")
    print(f"  GET /api/v1/health/ → {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"    Status: {data.get('status')}, Uptime: {data.get('uptime'):.2f}s")
    
    # Detailed health check
    resp = client.get("/api/v1/health/detailed")
    print(f"  GET /api/v1/health/detailed → {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"    Components: {len(data.get('components', {}))}")
    
    # Metrics
    resp = client.get("/api/v1/health/metrics")
    print(f"  GET /api/v1/health/metrics → {resp.status_code}")
    
    # Ping
    resp = client.get("/api/v1/health/ping")
    print(f"  GET /api/v1/health/ping → {resp.status_code}")
    if resp.status_code == 200:
        print(f"    Response: {resp.json().get('message')}")
    
    # Test Scraper Endpoints
    print("\n🕷️  Scraper Endpoints:")
    
    # Create a scrape job
    job_data = {
        "url": "https://httpbin.org/html",
        "method": "GET",
        "scraper_type": "cloudscraper",
        "config": {
            "timeout": 30,
            "max_retries": 3,
            "headless": True
        },
        "tags": ["test", "demo"],
        "priority": 0
    }
    
    resp = client.post("/api/v1/scrape/", json=job_data)
    print(f"  POST /api/v1/scrape/ → {resp.status_code}")
    
    job_id = None
    if resp.status_code == 200:
        data = resp.json()
        job_id = data.get('job_id')
        print(f"    Created job: {job_id}")
        print(f"    Status: {data.get('status')}")
    
    # Test job status endpoint
    if job_id:
        resp = client.get(f"/api/v1/scrape/{job_id}")
        print(f"  GET /api/v1/scrape/{job_id} → {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"    Job status: {data.get('status')}")
    
    # Test bulk job creation
    bulk_data = {
        "jobs": [
            {"url": "https://example.com/page1", "scraper_type": "cloudscraper"},
            {"url": "https://example.com/page2", "scraper_type": "cloudscraper"}
        ],
        "parallel_limit": 2
    }
    
    resp = client.post("/api/v1/scrape/bulk", json=bulk_data)
    print(f"  POST /api/v1/scrape/bulk → {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"    Batch created: {data.get('batch_id')}")
        print(f"    Jobs created: {data.get('total_jobs')}")
    
    # Test Job Management Endpoints
    print("\n📋 Job Management Endpoints:")
    
    # List jobs
    resp = client.get("/api/v1/jobs/")
    print(f"  GET /api/v1/jobs/ → {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"    Total jobs: {data.get('total', 0)}")
        print(f"    Jobs in response: {len(data.get('jobs', []))}")
    
    # Search jobs
    search_data = {
        "query": "example.com",
        "page": 1,
        "page_size": 10,
        "sort_by": "created_at",
        "sort_order": "desc"
    }
    
    resp = client.post("/api/v1/jobs/search", json=search_data)
    print(f"  POST /api/v1/jobs/search → {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"    Search results: {data.get('total', 0)} jobs")
    
    # Get job statistics
    resp = client.get("/api/v1/jobs/stats")
    print(f"  GET /api/v1/jobs/stats → {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"    Total jobs: {data.get('total_jobs', 0)}")
        print(f"    Success rate: {data.get('success_rate', 0):.2%}")
    
    # Queue status
    resp = client.get("/api/v1/jobs/queue/status")
    print(f"  GET /api/v1/jobs/queue/status → {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"    Queue size: {data.get('queue_size', 0)}")
        print(f"    Running jobs: {data.get('running_jobs', 0)}")
    
    # Test Validation
    print("\n✅ Input Validation Tests:")
    
    # Invalid URL
    resp = client.post("/api/v1/scrape/", json={"url": "invalid-url"})
    print(f"  Invalid URL → {resp.status_code} (expected 422)")
    
    # Invalid method
    resp = client.post("/api/v1/scrape/", json={
        "url": "https://example.com",
        "method": "INVALID"
    })
    print(f"  Invalid method → {resp.status_code} (expected 422)")
    
    # Invalid search sort field
    resp = client.post("/api/v1/jobs/search", json={"sort_by": "invalid_field"})
    print(f"  Invalid sort field → {resp.status_code} (expected 422)")
    
    # Test Error Handling
    print("\n❌ Error Handling Tests:")
    
    # Non-existent job
    resp = client.get("/api/v1/scrape/nonexistent-job-id")
    print(f"  Non-existent job → {resp.status_code} (expected 404)")
    
    # Non-existent endpoint
    resp = client.get("/api/v1/nonexistent")
    print(f"  Non-existent endpoint → {resp.status_code} (expected 404)")
    
    # Test Legacy Compatibility
    print("\n🔄 Legacy Compatibility Tests:")
    
    # Legacy health check
    resp = client.get("/health")
    print(f"  GET /health → {resp.status_code}")
    
    # Legacy root
    resp = client.get("/")
    print(f"  GET / → {resp.status_code}")
    
    print("\n" + "=" * 60)
    print("✅ Phase 2 API Implementation Test Complete!")
    print("\nKey Features Demonstrated:")
    print("  • Comprehensive request/response models with validation")
    print("  • Organized route structure (scraper, jobs, health)")
    print("  • Advanced job management with search and filtering")
    print("  • Health monitoring with detailed component status")
    print("  • Error handling with structured responses")
    print("  • Input validation with helpful error messages")
    print("  • Backward compatibility with legacy endpoints")
    print("  • Graceful handling of missing dependencies")

if __name__ == "__main__":
    test_api_endpoints()