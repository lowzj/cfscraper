"""
Unit tests for database models
"""
import pytest
from datetime import datetime, timezone
import uuid
import json
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.job import Job, JobResult, JobStatus, ScraperType
from app.core.database import Base


@pytest.mark.unit
class TestJobModel:
    """Test Job SQLAlchemy model"""
    
    def test_job_creation(self, test_db_session):
        """Test creating a job"""
        job = Job(
            id=str(uuid.uuid4()),
            task_id="test-task-123",
            url="https://example.com",
            method="GET",
            scraper_type=ScraperType.CLOUDSCRAPER,
            status=JobStatus.QUEUED,
            headers={"User-Agent": "test"},
            data={"key": "value"},
            params={"param1": "value1"},
            tags=["test", "unit"],
            priority=5,
            max_retries=3,
            retry_count=0,
            progress=0
        )
        
        test_db_session.add(job)
        test_db_session.commit()
        test_db_session.refresh(job)
        
        assert job.id is not None
        assert job.task_id == "test-task-123"
        assert job.url == "https://example.com"
        assert job.method == "GET"
        assert job.scraper_type == ScraperType.CLOUDSCRAPER
        assert job.status == JobStatus.QUEUED
        assert job.headers == {"User-Agent": "test"}
        assert job.data == {"key": "value"}
        assert job.params == {"param1": "value1"}
        assert job.tags == ["test", "unit"]
        assert job.priority == 5
        assert job.max_retries == 3
        assert job.retry_count == 0
        assert job.progress == 0
        assert job.created_at is not None
    
    def test_job_defaults(self, test_db_session):
        """Test job default values"""
        job = Job(
            id=str(uuid.uuid4()),
            url="https://example.com"
        )
        
        test_db_session.add(job)
        test_db_session.commit()
        test_db_session.refresh(job)
        
        assert job.method == "GET"
        assert job.scraper_type == ScraperType.CLOUDSCRAPER
        assert job.status == JobStatus.QUEUED
        assert job.headers == {}
        assert job.data == {}
        assert job.params == {}
        assert job.tags == []
        assert job.priority == 0
        assert job.max_retries == 3
        assert job.retry_count == 0
        assert job.progress == 0
        assert job.created_at is not None
    
    def test_job_unique_task_id(self, test_db_session):
        """Test that task_id must be unique"""
        task_id = "duplicate-task-id"
        
        job1 = Job(
            id=str(uuid.uuid4()),
            task_id=task_id,
            url="https://example.com/1"
        )
        job2 = Job(
            id=str(uuid.uuid4()),
            task_id=task_id,
            url="https://example.com/2"
        )
        
        test_db_session.add(job1)
        test_db_session.commit()
        
        test_db_session.add(job2)
        with pytest.raises(IntegrityError):
            test_db_session.commit()
    
    def test_job_nullable_fields(self, test_db_session):
        """Test nullable fields"""
        job = Job(
            id=str(uuid.uuid4()),
            url="https://example.com",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            result={"status_code": 200, "content": "test"},
            error_message="Test error",
            progress_message="Processing..."
        )
        
        test_db_session.add(job)
        test_db_session.commit()
        test_db_session.refresh(job)
        
        assert job.started_at is not None
        assert job.completed_at is not None
        assert job.result == {"status_code": 200, "content": "test"}
        assert job.error_message == "Test error"
        assert job.progress_message == "Processing..."
    
    def test_job_repr(self, test_db_session):
        """Test job string representation"""
        job = Job(
            id=str(uuid.uuid4()),
            task_id="test-task-123",
            url="https://example.com",
            status=JobStatus.RUNNING
        )
        
        test_db_session.add(job)
        test_db_session.commit()
        test_db_session.refresh(job)
        
        repr_str = repr(job)
        assert "Job(" in repr_str
        assert f"id={job.id}" in repr_str
        assert "task_id='test-task-123'" in repr_str
        assert "status='running'" in repr_str
    
    def test_job_status_enum_values(self, test_db_session):
        """Test all job status enum values"""
        statuses = [
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED
        ]
        
        for i, status in enumerate(statuses):
            job = Job(
                id=str(uuid.uuid4()),
                task_id=f"test-task-{i}",
                url=f"https://example.com/{i}",
                status=status
            )
            test_db_session.add(job)
        
        test_db_session.commit()
        
        # Verify all jobs were created with correct statuses
        jobs = test_db_session.query(Job).all()
        assert len(jobs) == len(statuses)
        
        for job in jobs:
            assert job.status in [s.value for s in statuses]
    
    def test_job_scraper_type_enum_values(self, test_db_session):
        """Test all scraper type enum values"""
        scraper_types = [
            ScraperType.CLOUDSCRAPER,
            ScraperType.SELENIUM
        ]
        
        for i, scraper_type in enumerate(scraper_types):
            job = Job(
                id=str(uuid.uuid4()),
                task_id=f"test-task-{i}",
                url=f"https://example.com/{i}",
                scraper_type=scraper_type
            )
            test_db_session.add(job)
        
        test_db_session.commit()
        
        # Verify all jobs were created with correct scraper types
        jobs = test_db_session.query(Job).all()
        assert len(jobs) == len(scraper_types)
        
        for job in jobs:
            assert job.scraper_type in [s.value for s in scraper_types]
    
    def test_job_json_fields(self, test_db_session):
        """Test JSON field serialization/deserialization"""
        complex_data = {
            "nested": {
                "array": [1, 2, 3],
                "string": "test",
                "boolean": True,
                "null": None
            },
            "list": ["a", "b", "c"]
        }
        
        job = Job(
            id=str(uuid.uuid4()),
            url="https://example.com",
            headers=complex_data,
            data=complex_data,
            params={"simple": "param"},
            tags=["tag1", "tag2", "tag3"],
            result=complex_data
        )
        
        test_db_session.add(job)
        test_db_session.commit()
        test_db_session.refresh(job)
        
        assert job.headers == complex_data
        assert job.data == complex_data
        assert job.params == {"simple": "param"}
        assert job.tags == ["tag1", "tag2", "tag3"]
        assert job.result == complex_data
    
    def test_job_required_fields(self, test_db_session):
        """Test that required fields are enforced"""
        # URL is required
        job = Job(id=str(uuid.uuid4()))
        
        test_db_session.add(job)
        with pytest.raises(IntegrityError):
            test_db_session.commit()


@pytest.mark.unit
class TestJobResultModel:
    """Test JobResult SQLAlchemy model"""
    
    def test_job_result_creation(self, test_db_session):
        """Test creating a job result"""
        job_result = JobResult(
            job_id=123,
            task_id="test-task-123",
            status_code=200,
            response_headers={"content-type": "text/html"},
            response_content="<html>test</html>",
            response_time=1500,
            content_length=18,
            content_type="text/html"
        )
        
        test_db_session.add(job_result)
        test_db_session.commit()
        test_db_session.refresh(job_result)
        
        assert job_result.id is not None
        assert job_result.job_id == 123
        assert job_result.task_id == "test-task-123"
        assert job_result.status_code == 200
        assert job_result.response_headers == {"content-type": "text/html"}
        assert job_result.response_content == "<html>test</html>"
        assert job_result.response_time == 1500
        assert job_result.content_length == 18
        assert job_result.content_type == "text/html"
        assert job_result.created_at is not None
    
    def test_job_result_nullable_fields(self, test_db_session):
        """Test nullable fields in job result"""
        job_result = JobResult(
            job_id=123,
            task_id="test-task-123"
        )
        
        test_db_session.add(job_result)
        test_db_session.commit()
        test_db_session.refresh(job_result)
        
        assert job_result.status_code is None
        assert job_result.response_headers is None
        assert job_result.response_content is None
        assert job_result.response_time is None
        assert job_result.content_length is None
        assert job_result.content_type is None
        assert job_result.created_at is not None
    
    def test_job_result_repr(self, test_db_session):
        """Test job result string representation"""
        job_result = JobResult(
            job_id=123,
            task_id="test-task-123",
            status_code=200
        )
        
        test_db_session.add(job_result)
        test_db_session.commit()
        test_db_session.refresh(job_result)
        
        repr_str = repr(job_result)
        assert "JobResult(" in repr_str
        assert f"id={job_result.id}" in repr_str
        assert "job_id=123" in repr_str
        assert "status_code=200" in repr_str
    
    def test_job_result_large_content(self, test_db_session):
        """Test storing large content"""
        large_content = "x" * 10000  # 10KB content
        
        job_result = JobResult(
            job_id=123,
            task_id="test-task-123",
            response_content=large_content,
            content_length=len(large_content)
        )
        
        test_db_session.add(job_result)
        test_db_session.commit()
        test_db_session.refresh(job_result)
        
        assert job_result.response_content == large_content
        assert job_result.content_length == 10000
    
    def test_job_result_json_headers(self, test_db_session):
        """Test JSON headers serialization"""
        complex_headers = {
            "content-type": "application/json",
            "set-cookie": ["session=abc123", "csrf=xyz789"],
            "custom-header": "value with spaces",
            "x-rate-limit": "100"
        }
        
        job_result = JobResult(
            job_id=123,
            task_id="test-task-123",
            response_headers=complex_headers
        )
        
        test_db_session.add(job_result)
        test_db_session.commit()
        test_db_session.refresh(job_result)
        
        assert job_result.response_headers == complex_headers


@pytest.mark.unit
class TestDatabaseCRUDOperations:
    """Test CRUD operations on database models"""
    
    def test_create_and_read_job(self, test_db_session):
        """Test creating and reading a job"""
        # Create
        job = Job(
            id=str(uuid.uuid4()),
            task_id="crud-test-123",
            url="https://example.com",
            status=JobStatus.QUEUED
        )
        test_db_session.add(job)
        test_db_session.commit()
        
        # Read
        retrieved_job = test_db_session.query(Job).filter(Job.task_id == "crud-test-123").first()
        
        assert retrieved_job is not None
        assert retrieved_job.task_id == "crud-test-123"
        assert retrieved_job.url == "https://example.com"
        assert retrieved_job.status == JobStatus.QUEUED
    
    def test_update_job(self, test_db_session):
        """Test updating a job"""
        # Create
        job = Job(
            id=str(uuid.uuid4()),
            task_id="update-test-123",
            url="https://example.com",
            status=JobStatus.QUEUED,
            progress=0
        )
        test_db_session.add(job)
        test_db_session.commit()
        
        # Update
        job.status = JobStatus.RUNNING
        job.progress = 50
        job.started_at = datetime.now(timezone.utc)
        test_db_session.commit()
        
        # Verify update
        test_db_session.refresh(job)
        assert job.status == JobStatus.RUNNING
        assert job.progress == 50
        assert job.started_at is not None
    
    def test_delete_job(self, test_db_session):
        """Test deleting a job"""
        # Create
        job = Job(
            id=str(uuid.uuid4()),
            task_id="delete-test-123",
            url="https://example.com"
        )
        test_db_session.add(job)
        test_db_session.commit()
        job_id = job.id
        
        # Delete
        test_db_session.delete(job)
        test_db_session.commit()
        
        # Verify deletion
        deleted_job = test_db_session.query(Job).filter(Job.id == job_id).first()
        assert deleted_job is None
    
    def test_query_jobs_by_status(self, test_db_session):
        """Test querying jobs by status"""
        # Create jobs with different statuses
        statuses = [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETED]
        for i, status in enumerate(statuses):
            job = Job(
                id=str(uuid.uuid4()),
                task_id=f"status-test-{i}",
                url=f"https://example.com/{i}",
                status=status
            )
            test_db_session.add(job)
        test_db_session.commit()
        
        # Query by status
        queued_jobs = test_db_session.query(Job).filter(Job.status == JobStatus.QUEUED).all()
        running_jobs = test_db_session.query(Job).filter(Job.status == JobStatus.RUNNING).all()
        completed_jobs = test_db_session.query(Job).filter(Job.status == JobStatus.COMPLETED).all()
        
        assert len(queued_jobs) == 1
        assert len(running_jobs) == 1
        assert len(completed_jobs) == 1
    
    def test_query_jobs_by_date_range(self, test_db_session):
        """Test querying jobs by date range"""
        from datetime import timedelta
        
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)
        
        # Create jobs with different creation times
        old_job = Job(
            id=str(uuid.uuid4()),
            task_id="old-job",
            url="https://example.com/old",
            created_at=yesterday
        )
        new_job = Job(
            id=str(uuid.uuid4()),
            task_id="new-job",
            url="https://example.com/new",
            created_at=now
        )
        
        test_db_session.add_all([old_job, new_job])
        test_db_session.commit()
        
        # Query by date range
        recent_jobs = test_db_session.query(Job).filter(
            Job.created_at >= yesterday,
            Job.created_at <= tomorrow
        ).all()
        
        assert len(recent_jobs) == 2
        
        # Query only today's jobs
        today_jobs = test_db_session.query(Job).filter(
            Job.created_at >= now - timedelta(hours=1)
        ).all()
        
        assert len(today_jobs) == 1
        assert today_jobs[0].task_id == "new-job"
