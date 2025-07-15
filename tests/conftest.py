"""
Shared pytest fixtures for the CFScraper test suite
"""
import asyncio
import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, Generator, AsyncGenerator
from datetime import datetime, timezone
import tempfile
import os
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import fakeredis.aioredis

from app.main import app
from app.core.database import get_db, Base
from app.core.config import settings
from app.models.job import Job, JobStatus, ScraperType
from app.utils.queue import JobQueue, InMemoryJobQueue
from app.utils.executor import JobExecutor
from app.utils.webhooks import WebhookDeliveryService


# Test Database Setup
@pytest.fixture(scope="session")
def test_db_engine():
    """Create test database engine"""
    # Use in-memory SQLite for tests
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def test_db_session(test_db_engine) -> Generator[Session, None, None]:
    """Create test database session"""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_db_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_db(test_db_session):
    """Override database dependency for tests"""
    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    yield test_db_session
    app.dependency_overrides.clear()


# Test Client Setup
@pytest.fixture
def client(test_db) -> TestClient:
    """Create test client with database override"""
    return TestClient(app)


# Redis Mock Setup
@pytest_asyncio.fixture
async def mock_redis():
    """Create mock Redis client for testing"""
    redis_mock = fakeredis.aioredis.FakeRedis()
    yield redis_mock
    await redis_mock.flushall()
    await redis_mock.aclose()


# Job Queue Fixtures
@pytest.fixture
def mock_job_queue():
    """Create mock job queue"""
    queue = Mock(spec=JobQueue)
    queue.enqueue = AsyncMock(return_value="test-task-id")
    queue.dequeue = AsyncMock(return_value=None)
    queue.get_status = AsyncMock(return_value={"status": "queued"})
    queue.update_status = AsyncMock()
    queue.get_queue_size = AsyncMock(return_value=0)
    queue.get_running_jobs = AsyncMock(return_value=0)
    return queue


@pytest_asyncio.fixture
async def in_memory_queue():
    """Create real in-memory job queue for integration tests"""
    queue = InMemoryJobQueue()
    yield queue
    # Cleanup
    await queue.clear()


# Job Executor Fixtures
@pytest.fixture
def mock_job_executor():
    """Create mock job executor"""
    executor = Mock(spec=JobExecutor)
    executor.start = AsyncMock()
    executor.stop = AsyncMock()
    executor.get_running_jobs = AsyncMock(return_value=0)
    executor.get_max_concurrent_jobs = Mock(return_value=5)
    return executor


# Webhook Service Fixtures
@pytest.fixture
def mock_webhook_service():
    """Create mock webhook service"""
    service = Mock(spec=WebhookDeliveryService)
    service.register_webhook = AsyncMock(return_value="webhook-id")
    service.send_webhook = AsyncMock(return_value=["delivery-id"])
    service.get_webhook = AsyncMock()
    service.list_webhooks = AsyncMock(return_value=[])
    return service


# Sample Data Fixtures
@pytest.fixture
def sample_job_data():
    """Sample job data for testing"""
    return {
        "url": "https://httpbin.org/html",
        "method": "GET",
        "scraper_type": "cloudscraper",
        "config": {
            "timeout": 30,
            "max_retries": 3
        },
        "tags": ["test"],
        "priority": 0
    }


@pytest.fixture
def sample_job(test_db_session, sample_job_data):
    """Create sample job in database"""
    job = Job(
        id=str(uuid.uuid4()),
        url=sample_job_data["url"],
        method=sample_job_data["method"],
        scraper_type=ScraperType.CLOUDSCRAPER,
        config=sample_job_data["config"],
        tags=sample_job_data["tags"],
        priority=sample_job_data["priority"],
        status=JobStatus.QUEUED,
        created_at=datetime.now(timezone.utc)
    )
    test_db_session.add(job)
    test_db_session.commit()
    test_db_session.refresh(job)
    return job


@pytest.fixture
def sample_scraper_result():
    """Sample scraper result for testing"""
    return {
        "status_code": 200,
        "content": "<html><body>Test content</body></html>",
        "headers": {"content-type": "text/html"},
        "response_time": 1500.0,
        "error": None,
        "metadata": {"proxy_used": "127.0.0.1:8080"}
    }


# Mock External Services
@pytest.fixture
def mock_external_website():
    """Mock external website responses"""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Test content</body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.elapsed.total_seconds.return_value = 1.5
        
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        yield mock_client


@pytest.fixture
def mock_selenium_driver():
    """Mock Selenium WebDriver"""
    with patch('seleniumbase.BaseCase') as mock_driver:
        driver_instance = Mock()
        driver_instance.get_page_source.return_value = "<html><body>Test content</body></html>"
        driver_instance.get_current_url.return_value = "https://httpbin.org/html"
        driver_instance.execute_script.return_value = None
        mock_driver.return_value = driver_instance
        yield driver_instance


# Environment Setup
@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment variables"""
    original_env = os.environ.copy()
    
    # Set test environment variables
    os.environ.update({
        "TESTING": "true",
        "DATABASE_URL": "sqlite:///:memory:",
        "REDIS_URL": "redis://localhost:6379/1",
        "USE_IN_MEMORY_QUEUE": "true",
        "LOG_LEVEL": "WARNING"
    })
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


# Async Event Loop
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Performance Testing Fixtures
@pytest.fixture
def benchmark_config():
    """Configuration for benchmark tests"""
    return {
        "min_rounds": 5,
        "max_time": 10.0,
        "warmup": True
    }


# Security Testing Fixtures
@pytest.fixture
def malicious_payloads():
    """Common malicious payloads for security testing"""
    return {
        "sql_injection": [
            "'; DROP TABLE jobs; --",
            "1' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM jobs --"
        ],
        "xss": [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "';alert('xss');//"
        ],
        "path_traversal": [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd"
        ]
    }


# Cleanup Fixtures
@pytest.fixture(autouse=True)
def cleanup_after_test(test_db_session):
    """Cleanup database after each test"""
    yield
    # Clean up all tables
    for table in reversed(Base.metadata.sorted_tables):
        test_db_session.execute(table.delete())
    test_db_session.commit()
