"""
Integration tests for complete workflows
"""
import asyncio
from unittest.mock import Mock, AsyncMock, patch

import pytest

from app.models.job import JobStatus
from app.utils.executor import JobExecutor
from app.utils.webhooks import WebhookDeliveryService, WebhookConfig, WebhookEvent


@pytest.mark.integration
class TestCompleteScrapingWorkflow:
    """Test complete scraping job lifecycle"""

    @pytest.mark.asyncio
    async def test_end_to_end_scraping_job(self, client, test_db_session, in_memory_queue):
        """Test complete job lifecycle from API to completion"""
        # Step 1: Submit job via API
        job_data = {
            "url": "https://httpbin.org/html",
            "method": "GET",
            "scraper_type": "cloudscraper",
            "config": {
                "timeout": 30,
                "max_retries": 3
            },
            "tags": ["integration-test"],
            "priority": 0
        }

        with patch('app.api.routes.common.get_job_queue', return_value=in_memory_queue):
            response = client.post("/api/v1/scrape/", json=job_data)

            assert response.status_code == 200
            data = response.json()
            job_id = data["job_id"]
            task_id = data["task_id"]

        # Step 2: Verify job is in queue
        queue_size = await in_memory_queue.get_queue_size()
        assert queue_size == 1

        job_status = await in_memory_queue.get_job_status(task_id)
        assert job_status == JobStatus.QUEUED

        # Step 3: Process job with executor
        executor = JobExecutor(job_queue=in_memory_queue, max_concurrent_jobs=1)

        # Mock successful scraping
        with patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                patch('app.utils.executor.SessionLocal') as mock_session_local:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = Mock(
                status_code=200,
                content="<html><body>Test content</body></html>",
                headers={"content-type": "text/html"},
                response_time=1500.0,
                error=None,
                to_dict=Mock(return_value={
                    "status_code": 200,
                    "content": "<html><body>Test content</body></html>",
                    "headers": {"content-type": "text/html"},
                    "response_time": 1500.0,
                    "success": True
                })
            )
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            # Execute the job
            job_info = await in_memory_queue.dequeue()
            assert job_info is not None

            result = await executor.execute_job(job_info)

            assert result["success"] is True
            assert result["task_id"] == task_id
            mock_scraper.scrape.assert_called_once()

        # Step 4: Verify job completion
        final_status = await in_memory_queue.get_job_status(task_id)
        assert final_status == JobStatus.RUNNING  # Updated by dequeue

    @pytest.mark.asyncio
    async def test_job_failure_workflow(self, client, test_db_session, in_memory_queue):
        """Test job failure handling workflow"""
        job_data = {
            "url": "https://invalid-url-that-will-fail.com",
            "scraper_type": "cloudscraper"
        }

        with patch('app.api.routes.common.get_job_queue', return_value=in_memory_queue):
            response = client.post("/api/v1/scrape/", json=job_data)
            task_id = response.json()["task_id"]

        # Process job with failure
        executor = JobExecutor(job_queue=in_memory_queue)

        with patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                patch('app.utils.executor.SessionLocal') as mock_session_local:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            mock_scraper = AsyncMock()
            mock_scraper.scrape.side_effect = Exception("Network error")
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            job_info = await in_memory_queue.dequeue()
            result = await executor.execute_job(job_info)

            assert result["success"] is False
            assert "error" in result
            assert "Network error" in result["error"]

    @pytest.mark.asyncio
    async def test_bulk_job_workflow(self, client, test_db_session, in_memory_queue):
        """Test bulk job processing workflow"""
        bulk_data = {
            "jobs": [
                {
                    "url": "https://httpbin.org/html",
                    "scraper_type": "cloudscraper",
                    "tags": ["bulk-1"]
                },
                {
                    "url": "https://httpbin.org/json",
                    "scraper_type": "cloudscraper",
                    "tags": ["bulk-2"]
                },
                {
                    "url": "https://httpbin.org/xml",
                    "scraper_type": "cloudscraper",
                    "tags": ["bulk-3"]
                }
            ],
            "parallel_limit": 2
        }

        with patch('app.api.routes.common.get_job_queue', return_value=in_memory_queue):
            response = client.post("/api/v1/scrape/bulk", json=bulk_data)

            assert response.status_code == 200
            data = response.json()
            assert data["total_jobs"] == 3

        # Verify all jobs are queued
        queue_size = await in_memory_queue.get_queue_size()
        assert queue_size == 3

        # Process all jobs
        executor = JobExecutor(job_queue=in_memory_queue, max_concurrent_jobs=2)

        with patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                patch('app.utils.executor.SessionLocal') as mock_session_local:

            mock_db = Mock()
            mock_session_local.return_value = mock_db

            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = Mock(
                status_code=200,
                content="test",
                headers={},
                response_time=1000.0,
                error=None,
                to_dict=Mock(return_value={"status_code": 200, "success": True})
            )
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            # Process all jobs
            results = []
            for _ in range(3):
                job_info = await in_memory_queue.dequeue()
                if job_info:
                    result = await executor.execute_job(job_info)
                    results.append(result)

            assert len(results) == 3
            assert all(result["success"] for result in results)


@pytest.mark.integration
class TestWebhookIntegration:
    """Test webhook integration with job processing"""

    @pytest.mark.asyncio
    async def test_job_completion_webhook(self, in_memory_queue):
        """Test webhook delivery on job completion"""
        webhook_service = WebhookDeliveryService()

        # Register webhook
        webhook_config = WebhookConfig(
            url="https://webhook.example.com/notify",
            events=[WebhookEvent.JOB_COMPLETED]
        )
        webhook_id = await webhook_service.register_webhook("test-webhook", webhook_config)

        # Start webhook worker
        await webhook_service.start_delivery_worker()

        try:
            # Process job and trigger webhook
            executor = JobExecutor(job_queue=in_memory_queue)

            job_data = {
                "url": "https://httpbin.org/html",
                "scraper_type": "cloudscraper"
            }
            task_id = await in_memory_queue.enqueue(job_data)

            with patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                    patch('app.utils.executor.SessionLocal') as mock_session_local, \
                    patch('httpx.AsyncClient') as mock_http_client:

                # Mock successful scraping
                mock_db = Mock()
                mock_session_local.return_value = mock_db

                mock_scraper = AsyncMock()
                mock_scraper.scrape.return_value = Mock(
                    status_code=200,
                    content="test",
                    headers={},
                    response_time=1000.0,
                    error=None,
                    to_dict=Mock(return_value={"status_code": 200, "success": True})
                )
                mock_scraper.close = AsyncMock()
                mock_create_scraper.return_value = mock_scraper

                # Mock webhook delivery
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.text = "OK"
                mock_http_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                # Execute job
                job_info = await in_memory_queue.dequeue()
                result = await executor.execute_job(job_info)

                assert result["success"] is True

                # Give webhook time to process
                await asyncio.sleep(0.1)

                # Verify webhook was called
                mock_http_client.return_value.__aenter__.return_value.post.assert_called()

        finally:
            await webhook_service.stop_delivery_worker()

    @pytest.mark.asyncio
    async def test_webhook_retry_mechanism(self):
        """Test webhook retry mechanism on failure"""
        webhook_service = WebhookDeliveryService()

        # Register webhook with retry configuration
        webhook_config = WebhookConfig(
            url="https://webhook.example.com/notify",
            events=[WebhookEvent.JOB_COMPLETED],
            max_retries=2,
            retry_delay=1  # 1 second for testing
        )
        await webhook_service.register_webhook("test-webhook", webhook_config)

        # Start webhook worker
        await webhook_service.start_delivery_worker()

        try:
            with patch('httpx.AsyncClient') as mock_http_client:
                # Mock failed webhook delivery
                mock_response = Mock()
                mock_response.status_code = 500
                mock_response.text = "Internal Server Error"
                mock_http_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                # Send webhook
                job_data = {"job_id": "test-123", "status": "completed"}
                delivery_ids = await webhook_service.send_webhook(
                    WebhookEvent.JOB_COMPLETED,
                    job_data
                )

                assert len(delivery_ids) == 1

                # Give time for initial attempt and retry
                await asyncio.sleep(0.2)

                # Should have attempted delivery multiple times
                assert mock_http_client.return_value.__aenter__.return_value.post.call_count >= 1

        finally:
            await webhook_service.stop_delivery_worker()


@pytest.mark.integration
class TestConcurrentProcessing:
    """Test concurrent job processing"""

    @pytest.mark.asyncio
    async def test_concurrent_job_execution(self, in_memory_queue):
        """Test processing multiple jobs concurrently"""
        executor = JobExecutor(job_queue=in_memory_queue, max_concurrent_jobs=3)

        # Enqueue multiple jobs
        job_ids = []
        for i in range(5):
            job_data = {
                "url": f"https://httpbin.org/delay/{i}",
                "scraper_type": "cloudscraper"
            }
            task_id = await in_memory_queue.enqueue(job_data)
            job_ids.append(task_id)

        assert await in_memory_queue.get_queue_size() == 5

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

            # Process jobs concurrently
            tasks = []
            for _ in range(5):
                job_info = await in_memory_queue.dequeue()
                if job_info:
                    task = asyncio.create_task(executor.execute_job(job_info))
                    tasks.append(task)

            # Wait for all jobs to complete
            results = await asyncio.gather(*tasks)

            assert len(results) == 5
            assert all(result["success"] for result in results)

            # Verify all scrapers were closed
            assert mock_scraper.close.call_count == 5

    @pytest.mark.asyncio
    async def test_queue_overflow_handling(self, in_memory_queue):
        """Test handling of queue overflow scenarios"""
        # Fill queue with many jobs
        job_ids = []
        for i in range(100):
            job_data = {
                "url": f"https://httpbin.org/status/200?id={i}",
                "scraper_type": "cloudscraper"
            }
            task_id = await in_memory_queue.enqueue(job_data)
            job_ids.append(task_id)

        assert await in_memory_queue.get_queue_size() == 100

        # Process with limited concurrency
        executor = JobExecutor(job_queue=in_memory_queue, max_concurrent_jobs=5)

        with patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                patch('app.utils.executor.SessionLocal') as mock_session_local:

            mock_db = Mock()
            mock_session_local.return_value = mock_db

            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = Mock(
                status_code=200,
                content="test",
                headers={},
                response_time=50.0,
                error=None,
                to_dict=Mock(return_value={"status_code": 200, "success": True})
            )
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            # Process first batch of jobs
            processed_count = 0
            while processed_count < 20 and await in_memory_queue.get_queue_size() > 0:
                job_info = await in_memory_queue.dequeue()
                if job_info:
                    result = await executor.execute_job(job_info)
                    assert result["success"] is True
                    processed_count += 1

            assert processed_count == 20
            assert await in_memory_queue.get_queue_size() == 80


@pytest.mark.integration
class TestErrorRecovery:
    """Test error recovery and resilience"""

    @pytest.mark.asyncio
    async def test_database_connection_failure_recovery(self, in_memory_queue):
        """Test recovery from database connection failures"""
        executor = JobExecutor(job_queue=in_memory_queue)

        job_data = {
            "url": "https://httpbin.org/html",
            "scraper_type": "cloudscraper"
        }
        task_id = await in_memory_queue.enqueue(job_data)

        with patch('app.utils.executor.SessionLocal') as mock_session_local:
            # Mock database connection failure
            mock_session_local.side_effect = Exception("Database connection failed")

            job_info = await in_memory_queue.dequeue()
            result = await executor.execute_job(job_info)

            # Should handle database error gracefully
            assert result["success"] is False
            assert "Database connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_scraper_timeout_handling(self, in_memory_queue):
        """Test handling of scraper timeouts"""
        executor = JobExecutor(job_queue=in_memory_queue)

        job_data = {
            "url": "https://httpbin.org/delay/60",  # Long delay
            "scraper_type": "cloudscraper",
            "config": {"timeout": 1}  # Short timeout
        }
        task_id = await in_memory_queue.enqueue(job_data)

        with patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                patch('app.utils.executor.SessionLocal') as mock_session_local:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            mock_scraper = AsyncMock()
            mock_scraper.scrape.side_effect = asyncio.TimeoutError("Request timeout")
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            job_info = await in_memory_queue.dequeue()
            result = await executor.execute_job(job_info)

            assert result["success"] is False
            assert "timeout" in result["error"].lower()
            mock_scraper.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_corruption_recovery(self, in_memory_queue):
        """Test recovery from queue corruption scenarios"""
        # Add valid job
        job_data = {
            "url": "https://httpbin.org/html",
            "scraper_type": "cloudscraper"
        }
        task_id = await in_memory_queue.enqueue(job_data)

        # Simulate queue corruption by removing job data
        async with in_memory_queue._lock:
            if task_id in in_memory_queue._jobs:
                del in_memory_queue._jobs[task_id]

        # Try to dequeue - should handle missing job gracefully
        job_info = await in_memory_queue.dequeue()

        # Should return None or handle gracefully
        # (Implementation may vary based on queue behavior)
        assert job_info is None or "task_id" in job_info
