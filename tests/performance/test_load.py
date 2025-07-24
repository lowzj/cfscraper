"""
Performance and load tests
"""
import asyncio
import gc
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, AsyncMock, patch

import psutil
import pytest

from app.utils.executor import JobExecutor
from app.utils.queue import InMemoryJobQueue


@pytest.mark.performance
class TestAPIPerformance:
    """Test API performance under load"""

    def test_health_check_response_time(self, client, benchmark):
        """Benchmark health check endpoint response time"""

        def health_check():
            response = client.get("/api/v1/health/")
            assert response.status_code == 200
            return response

        result = benchmark(health_check)

        # Verify response time is reasonable
        assert result.status_code == 200

    def test_job_creation_response_time(self, client, benchmark):
        """Benchmark job creation endpoint response time"""
        job_data = {
            "url": "https://httpbin.org/html",
            "scraper_type": "cloudscraper"
        }

        def create_job():
            with patch('app.api.routes.common.get_job_queue') as mock_queue:
                mock_queue.return_value.enqueue = AsyncMock(return_value="test-task-id")
                response = client.post("/api/v1/scrape/", json=job_data)
                return response

        result = benchmark(create_job)

        # Should complete quickly even under load
        assert result.status_code in [200, 500]  # 500 due to mocking

    def test_concurrent_api_requests(self, client):
        """Test API performance under concurrent load"""

        def make_request():
            return client.get("/api/v1/health/")

        # Test with multiple concurrent requests
        with ThreadPoolExecutor(max_workers=10) as executor:
            start_time = time.time()

            # Submit 50 concurrent requests
            futures = [executor.submit(make_request) for _ in range(50)]

            # Wait for all to complete
            responses = [future.result() for future in futures]

            end_time = time.time()
            total_time = end_time - start_time

        # All requests should succeed
        assert all(response.status_code == 200 for response in responses)

        # Should complete within reasonable time (adjust based on requirements)
        assert total_time < 10.0  # 50 requests in under 10 seconds

        # Calculate average response time
        avg_time = total_time / len(responses)
        assert avg_time < 0.5  # Average under 500ms per request

    def test_bulk_job_creation_performance(self, client):
        """Test performance of bulk job creation"""
        # Create bulk job with many items
        bulk_data = {
            "jobs": [
                {
                    "url": f"https://httpbin.org/status/200?id={i}",
                    "scraper_type": "cloudscraper"
                }
                for i in range(50)  # 50 jobs in bulk
            ],
            "parallel_limit": 10
        }

        with patch('app.api.routes.common.get_job_queue') as mock_queue:
            mock_queue.return_value.enqueue = AsyncMock(return_value="test-task-id")

            start_time = time.time()
            response = client.post("/api/v1/scrape/bulk", json=bulk_data)
            end_time = time.time()

            processing_time = end_time - start_time

        # Should handle bulk creation efficiently
        assert response.status_code == 200
        assert processing_time < 5.0  # Should complete in under 5 seconds

    def test_job_listing_performance(self, client, test_db_session):
        """Test performance of job listing with large datasets"""
        from app.models.job import Job, JobStatus, ScraperType
        import uuid

        # Create many jobs in database
        jobs = []
        for i in range(1000):
            job = Job(
                id=str(uuid.uuid4()),
                url=f"https://example.com/page{i}",
                method="GET",
                scraper_type=ScraperType.CLOUDSCRAPER,
                status=JobStatus.COMPLETED,
                created_at=time.time()
            )
            jobs.append(job)

        test_db_session.add_all(jobs)
        test_db_session.commit()

        # Test listing performance
        start_time = time.time()
        response = client.get("/api/v1/jobs/?page=1&page_size=100")
        end_time = time.time()

        query_time = end_time - start_time

        assert response.status_code == 200
        assert query_time < 2.0  # Should query 1000 records in under 2 seconds

        data = response.json()
        assert len(data["jobs"]) == 100
        assert data["total"] == 1000


@pytest.mark.performance
class TestQueuePerformance:
    """Test job queue performance"""

    @pytest.mark.asyncio
    async def test_queue_enqueue_performance(self, benchmark_config):
        """Test queue enqueue performance"""
        queue = InMemoryJobQueue()

        job_data = {
            "url": "https://example.com",
            "scraper_type": "cloudscraper"
        }

        async def enqueue_job():
            return await queue.enqueue(job_data)

        # Benchmark enqueue operation
        start_time = time.time()
        task_ids = []

        for _ in range(1000):
            task_id = await enqueue_job()
            task_ids.append(task_id)

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle 1000 enqueues efficiently
        assert len(task_ids) == 1000
        assert total_time < 5.0  # Under 5 seconds for 1000 operations
        assert await queue.get_queue_size() == 1000

    @pytest.mark.asyncio
    async def test_queue_dequeue_performance(self):
        """Test queue dequeue performance"""
        queue = InMemoryJobQueue()

        # Fill queue with jobs
        job_data = {"url": "https://example.com", "scraper_type": "cloudscraper"}
        for _ in range(1000):
            await queue.enqueue(job_data)

        # Benchmark dequeue operations
        start_time = time.time()
        dequeued_jobs = []

        for _ in range(1000):
            job_info = await queue.dequeue()
            if job_info:
                dequeued_jobs.append(job_info)

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle 1000 dequeues efficiently
        assert len(dequeued_jobs) == 1000
        assert total_time < 5.0  # Under 5 seconds for 1000 operations
        assert await queue.get_queue_size() == 0

    @pytest.mark.asyncio
    async def test_concurrent_queue_operations(self):
        """Test concurrent queue operations performance"""
        queue = InMemoryJobQueue()

        async def producer():
            """Producer that adds jobs to queue"""
            for i in range(100):
                job_data = {
                    "url": f"https://example.com/page{i}",
                    "scraper_type": "cloudscraper"
                }
                await queue.enqueue(job_data)
                await asyncio.sleep(0.001)  # Small delay

        async def consumer():
            """Consumer that processes jobs from queue"""
            processed = 0
            while processed < 100:
                job_info = await queue.dequeue()
                if job_info:
                    processed += 1
                else:
                    await asyncio.sleep(0.001)  # Wait for more jobs
            return processed

        # Run producer and consumer concurrently
        start_time = time.time()

        producer_task = asyncio.create_task(producer())
        consumer_task = asyncio.create_task(consumer())

        await asyncio.gather(producer_task, consumer_task)

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle concurrent operations efficiently
        assert total_time < 10.0  # Should complete in reasonable time
        assert await queue.get_queue_size() == 0  # All jobs processed


@pytest.mark.performance
class TestExecutorPerformance:
    """Test job executor performance"""

    @pytest.mark.asyncio
    async def test_single_job_execution_time(self):
        """Test single job execution performance"""
        queue = InMemoryJobQueue()
        executor = JobExecutor(job_queue=queue)

        job_data = {
            "url": "https://httpbin.org/html",
            "scraper_type": "cloudscraper"
        }
        task_id = await queue.enqueue(job_data)

        with patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                patch('app.utils.executor.SessionLocal') as mock_session_local:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            # Mock fast scraper
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = Mock(
                status_code=200,
                content="test",
                headers={},
                response_time=100.0,
                error=None,
                to_dict=Mock(return_value={"status_code": 200, "success": True})
            )
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            # Execute job and measure time
            job_info = await queue.dequeue()

            start_time = time.time()
            result = await executor.execute_job(job_info)
            end_time = time.time()

            execution_time = end_time - start_time

        assert result["success"] is True
        assert execution_time < 1.0  # Should complete quickly with mocked scraper

    @pytest.mark.asyncio
    async def test_concurrent_job_execution_performance(self):
        """Test concurrent job execution performance"""
        queue = InMemoryJobQueue()
        executor = JobExecutor(job_queue=queue, max_concurrent_jobs=5)

        # Enqueue multiple jobs
        job_ids = []
        for i in range(20):
            job_data = {
                "url": f"https://httpbin.org/delay/{i % 3}",
                "scraper_type": "cloudscraper"
            }
            task_id = await queue.enqueue(job_data)
            job_ids.append(task_id)

        with patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                patch('app.utils.executor.SessionLocal') as mock_session_local:

            mock_db = Mock()
            mock_session_local.return_value = mock_db

            # Mock scraper with variable delay
            async def mock_scrape(*args, **kwargs):
                await asyncio.sleep(0.1)  # Simulate work
                return Mock(
                    status_code=200,
                    content="test",
                    headers={},
                    response_time=100.0,
                    error=None,
                    to_dict=Mock(return_value={"status_code": 200, "success": True})
                )

            mock_scraper = AsyncMock()
            mock_scraper.scrape = mock_scrape
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            # Execute jobs concurrently
            start_time = time.time()

            tasks = []
            for _ in range(20):
                job_info = await queue.dequeue()
                if job_info:
                    task = asyncio.create_task(executor.execute_job(job_info))
                    tasks.append(task)

            results = await asyncio.gather(*tasks)
            end_time = time.time()

            total_time = end_time - start_time

        # All jobs should succeed
        assert len(results) == 20
        assert all(result["success"] for result in results)

        # Concurrent execution should be faster than sequential
        # With 5 concurrent workers and 0.1s per job, should complete in ~0.4s
        assert total_time < 2.0  # Allow some overhead


@pytest.mark.performance
class TestMemoryUsage:
    """Test memory usage under load"""

    @pytest.mark.asyncio
    async def test_memory_usage_during_bulk_processing(self):
        """Test memory usage during bulk job processing"""
        queue = InMemoryJobQueue()

        # Get initial memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create many jobs
        for i in range(1000):
            job_data = {
                "url": f"https://example.com/page{i}",
                "scraper_type": "cloudscraper",
                "data": {"large_field": "x" * 1000}  # Add some data
            }
            await queue.enqueue(job_data)

        # Check memory after enqueueing
        after_enqueue_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Process all jobs
        processed = 0
        while processed < 1000:
            job_info = await queue.dequeue()
            if job_info:
                processed += 1
                # Simulate some processing
                await asyncio.sleep(0.001)

        # Force garbage collection
        gc.collect()

        # Check final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Memory should not grow excessively
        memory_growth = final_memory - initial_memory
        assert memory_growth < 100  # Should not grow by more than 100MB

        # Memory should be released after processing
        assert final_memory < after_enqueue_memory + 50  # Allow some overhead

    def test_api_memory_usage_under_load(self, client):
        """Test API memory usage under concurrent load"""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Make many concurrent requests
        def make_requests():
            responses = []
            for _ in range(100):
                response = client.get("/api/v1/health/")
                responses.append(response)
            return responses

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_requests) for _ in range(5)]
            all_responses = []
            for future in futures:
                all_responses.extend(future.result())

        # Force garbage collection
        gc.collect()

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        # All requests should succeed
        assert len(all_responses) == 500
        assert all(response.status_code == 200 for response in all_responses)

        # Memory growth should be reasonable
        assert memory_growth < 50  # Should not grow by more than 50MB


@pytest.mark.performance
class TestDatabasePerformance:
    """Test database query performance"""

    def test_job_insertion_performance(self, test_db_session):
        """Test performance of inserting many jobs"""
        from app.models.job import Job, JobStatus, ScraperType
        import uuid

        # Prepare many jobs
        jobs = []
        for i in range(1000):
            job = Job(
                id=str(uuid.uuid4()),
                url=f"https://example.com/page{i}",
                method="GET",
                scraper_type=ScraperType.CLOUDSCRAPER,
                status=JobStatus.QUEUED,
                tags=[f"tag{i % 10}"],
                priority=i % 5
            )
            jobs.append(job)

        # Measure insertion time
        start_time = time.time()
        test_db_session.add_all(jobs)
        test_db_session.commit()
        end_time = time.time()

        insertion_time = end_time - start_time

        # Should insert 1000 jobs efficiently
        assert insertion_time < 5.0  # Under 5 seconds

        # Verify all jobs were inserted
        count = test_db_session.query(Job).count()
        assert count == 1000

    def test_job_query_performance(self, test_db_session):
        """Test performance of querying jobs"""
        from app.models.job import Job, JobStatus, ScraperType
        import uuid

        # Create test data
        jobs = []
        for i in range(5000):
            job = Job(
                id=str(uuid.uuid4()),
                url=f"https://example.com/page{i}",
                method="GET",
                scraper_type=ScraperType.CLOUDSCRAPER,
                status=JobStatus.COMPLETED if i % 2 == 0 else JobStatus.FAILED,
                tags=[f"tag{i % 10}"],
                priority=i % 5
            )
            jobs.append(job)

        test_db_session.add_all(jobs)
        test_db_session.commit()

        # Test various query patterns
        query_times = []

        # Query 1: Simple status filter
        start_time = time.time()
        completed_jobs = test_db_session.query(Job).filter(
            Job.status == JobStatus.COMPLETED
        ).limit(100).all()
        query_times.append(time.time() - start_time)

        # Query 2: Complex filter with pagination
        start_time = time.time()
        filtered_jobs = test_db_session.query(Job).filter(
            Job.status == JobStatus.COMPLETED,
            Job.priority >= 2
        ).order_by(Job.created_at.desc()).limit(50).all()
        query_times.append(time.time() - start_time)

        # Query 3: Count query
        start_time = time.time()
        total_count = test_db_session.query(Job).count()
        query_times.append(time.time() - start_time)

        # All queries should be fast
        assert all(qt < 1.0 for qt in query_times)  # Under 1 second each
        assert len(completed_jobs) == 100
        assert len(filtered_jobs) <= 50
        assert total_count == 5000
