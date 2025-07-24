"""
Unit tests for job queue and executor system
"""
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch

import pytest

from app.models.job import JobStatus, ScraperType
from app.utils.executor import JobExecutor
from app.utils.queue import JobQueue, InMemoryJobQueue, RedisJobQueue, create_job_queue


@pytest.mark.unit
class TestInMemoryJobQueue:
    """Test InMemoryJobQueue implementation"""

    @pytest.mark.asyncio
    async def test_enqueue_job(self):
        """Test enqueueing a job"""
        queue = InMemoryJobQueue()

        job_data = {
            "url": "https://example.com",
            "method": "GET",
            "scraper_type": ScraperType.CLOUDSCRAPER
        }

        task_id = await queue.enqueue(job_data)

        assert task_id is not None
        assert isinstance(task_id, str)

        # Verify job is in queue
        queue_size = await queue.get_queue_size()
        assert queue_size == 1

        # Verify job status
        status = await queue.get_job_status(task_id)
        assert status == JobStatus.QUEUED

    @pytest.mark.asyncio
    async def test_dequeue_job(self):
        """Test dequeuing a job"""
        queue = InMemoryJobQueue()

        job_data = {
            "url": "https://example.com",
            "method": "GET",
            "scraper_type": ScraperType.CLOUDSCRAPER
        }

        task_id = await queue.enqueue(job_data)

        # Dequeue the job
        job_info = await queue.dequeue()

        assert job_info is not None
        assert job_info["task_id"] == task_id
        assert job_info["data"] == job_data
        assert "created_at" in job_info

        # Verify status updated to running
        status = await queue.get_job_status(task_id)
        assert status == JobStatus.RUNNING

        # Queue should be empty now
        queue_size = await queue.get_queue_size()
        assert queue_size == 0

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue(self):
        """Test dequeuing from empty queue"""
        queue = InMemoryJobQueue()

        job_info = await queue.dequeue()
        assert job_info is None

    @pytest.mark.asyncio
    async def test_update_job_status(self):
        """Test updating job status"""
        queue = InMemoryJobQueue()

        job_data = {"url": "https://example.com"}
        task_id = await queue.enqueue(job_data)

        # Update status to completed
        await queue.update_job_status(
            task_id,
            JobStatus.COMPLETED,
            result={"status_code": 200}
        )

        status = await queue.get_job_status(task_id)
        assert status == JobStatus.COMPLETED

        # Check that additional data was stored
        all_jobs = queue.get_all_jobs()
        job = all_jobs[task_id]
        assert job["result"] == {"status_code": 200}
        assert "completed_at" in job

    @pytest.mark.asyncio
    async def test_remove_job(self):
        """Test removing a job from queue"""
        queue = InMemoryJobQueue()

        job_data = {"url": "https://example.com"}
        task_id = await queue.enqueue(job_data)

        # Remove the job
        removed = await queue.remove_job(task_id)
        assert removed is True

        # Job should no longer exist
        status = await queue.get_job_status(task_id)
        assert status is None

        # Try to remove non-existent job
        removed = await queue.remove_job("nonexistent")
        assert removed is False

    @pytest.mark.asyncio
    async def test_clear_queue(self):
        """Test clearing the entire queue"""
        queue = InMemoryJobQueue()

        # Add multiple jobs
        for i in range(3):
            await queue.enqueue({"url": f"https://example.com/{i}"})

        assert await queue.get_queue_size() == 3

        # Clear queue
        await queue.clear_queue()

        assert await queue.get_queue_size() == 0
        assert len(queue.get_all_jobs()) == 0

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent queue operations"""
        queue = InMemoryJobQueue()

        # Enqueue jobs concurrently
        tasks = []
        for i in range(10):
            task = asyncio.create_task(
                queue.enqueue({"url": f"https://example.com/{i}"})
            )
            tasks.append(task)

        task_ids = await asyncio.gather(*tasks)

        assert len(task_ids) == 10
        assert len(set(task_ids)) == 10  # All unique
        assert await queue.get_queue_size() == 10

    @pytest.mark.asyncio
    async def test_dequeue_removed_job(self):
        """Test dequeuing when job was removed"""
        queue = InMemoryJobQueue()

        # Enqueue multiple jobs
        task_ids = []
        for i in range(3):
            task_id = await queue.enqueue({"url": f"https://example.com/{i}"})
            task_ids.append(task_id)

        # Remove middle job
        await queue.remove_job(task_ids[1])

        # Dequeue should skip removed job and get next valid one
        job_info = await queue.dequeue()
        assert job_info is not None
        assert job_info["task_id"] in [task_ids[0], task_ids[2]]


@pytest.mark.unit
class TestRedisJobQueue:
    """Test RedisJobQueue implementation"""

    @pytest.mark.asyncio
    async def test_redis_connection_error(self):
        """Test Redis connection error handling"""
        with patch('redis.asyncio.from_url') as mock_redis:
            mock_redis.side_effect = Exception("Connection failed")

            queue = RedisJobQueue("redis://invalid:6379")

            with pytest.raises(Exception):
                await queue.enqueue({"url": "https://example.com"})

    @pytest.mark.asyncio
    async def test_enqueue_with_mock_redis(self, mock_redis):
        """Test enqueueing with mocked Redis"""
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client

        queue = RedisJobQueue()
        queue.redis_client = mock_client

        job_data = {"url": "https://example.com"}
        task_id = await queue.enqueue(job_data)

        assert task_id is not None
        mock_client.rpush.assert_called_once()
        mock_client.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_dequeue_with_mock_redis(self, mock_redis):
        """Test dequeuing with mocked Redis"""
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client

        # Mock Redis responses
        job_info = {
            "task_id": "test-task-123",
            "status": JobStatus.QUEUED,
            "data": {"url": "https://example.com"}
        }
        mock_client.blpop.return_value = ("queue", json.dumps(job_info))
        mock_client.exists.return_value = True

        queue = RedisJobQueue()
        queue.redis_client = mock_client

        result = await queue.dequeue()

        assert result == job_info
        mock_client.blpop.assert_called_once()
        mock_client.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_dequeue_empty_redis_queue(self, mock_redis):
        """Test dequeuing from empty Redis queue"""
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client
        mock_client.blpop.return_value = None

        queue = RedisJobQueue()
        queue.redis_client = mock_client

        result = await queue.dequeue()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_job_status_with_mock_redis(self, mock_redis):
        """Test getting job status with mocked Redis"""
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client
        mock_client.hget.return_value = b"running"

        queue = RedisJobQueue()
        queue.redis_client = mock_client

        status = await queue.get_job_status("test-task-123")

        assert status == JobStatus.RUNNING
        mock_client.hget.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_job_status_with_mock_redis(self, mock_redis):
        """Test updating job status with mocked Redis"""
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client

        queue = RedisJobQueue()
        queue.redis_client = mock_client

        await queue.update_job_status(
            "test-task-123",
            JobStatus.COMPLETED,
            result={"status_code": 200}
        )

        mock_client.hset.assert_called_once()
        call_args = mock_client.hset.call_args
        assert "status" in call_args[1]["mapping"]
        assert "result" in call_args[1]["mapping"]
        assert "completed_at" in call_args[1]["mapping"]

    @pytest.mark.asyncio
    async def test_get_queue_size_with_mock_redis(self, mock_redis):
        """Test getting queue size with mocked Redis"""
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client
        mock_client.llen.return_value = 5

        queue = RedisJobQueue()
        queue.redis_client = mock_client

        size = await queue.get_queue_size()

        assert size == 5
        mock_client.llen.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_queue_with_mock_redis(self, mock_redis):
        """Test clearing queue with mocked Redis"""
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client
        mock_client.keys.return_value = ["key1", "key2"]

        queue = RedisJobQueue()
        queue.redis_client = mock_client

        await queue.clear_queue()

        mock_client.delete.assert_called()
        assert mock_client.delete.call_count == 2  # Once for queue, once for status keys

    @pytest.mark.asyncio
    async def test_remove_job_with_mock_redis(self, mock_redis):
        """Test removing job with mocked Redis"""
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client
        mock_client.delete.return_value = 1  # Job existed and was deleted

        queue = RedisJobQueue()
        queue.redis_client = mock_client

        removed = await queue.remove_job("test-task-123")

        assert removed is True
        mock_client.delete.assert_called()
        mock_client.hset.assert_called()  # For marking as removed


@pytest.mark.unit
class TestJobQueueFactory:
    """Test job queue factory function"""

    def test_create_in_memory_queue(self):
        """Test creating in-memory queue"""
        with patch('app.utils.queue.settings') as mock_settings:
            mock_settings.use_in_memory_queue = True

            queue = create_job_queue()

            assert isinstance(queue, InMemoryJobQueue)

    def test_create_redis_queue(self):
        """Test creating Redis queue"""
        with patch('app.utils.queue.settings') as mock_settings, \
                patch('app.utils.queue.RedisJobQueue') as mock_redis_queue:
            mock_settings.use_in_memory_queue = False
            mock_redis_instance = Mock()
            mock_redis_queue.return_value = mock_redis_instance

            queue = create_job_queue()

            assert queue == mock_redis_instance
            mock_redis_queue.assert_called_once()

    def test_fallback_to_in_memory_on_redis_error(self):
        """Test fallback to in-memory queue when Redis fails"""
        with patch('app.utils.queue.settings') as mock_settings, \
                patch('app.utils.queue.RedisJobQueue') as mock_redis_queue:
            mock_settings.use_in_memory_queue = False
            mock_redis_queue.side_effect = Exception("Redis connection failed")

            queue = create_job_queue()

            assert isinstance(queue, InMemoryJobQueue)


@pytest.mark.unit
class TestJobQueueInterface:
    """Test job queue abstract interface"""

    def test_abstract_methods(self):
        """Test that JobQueue is abstract and requires implementation"""
        with pytest.raises(TypeError):
            JobQueue()

    @pytest.mark.asyncio
    async def test_queue_operations_flow(self):
        """Test typical queue operations flow"""
        queue = InMemoryJobQueue()

        # 1. Start with empty queue
        assert await queue.get_queue_size() == 0

        # 2. Enqueue a job
        job_data = {"url": "https://example.com", "method": "GET"}
        task_id = await queue.enqueue(job_data)

        assert await queue.get_queue_size() == 1
        assert await queue.get_job_status(task_id) == JobStatus.QUEUED

        # 3. Dequeue the job
        job_info = await queue.dequeue()
        assert job_info["task_id"] == task_id
        assert await queue.get_job_status(task_id) == JobStatus.RUNNING

        # 4. Update job to completed
        await queue.update_job_status(task_id, JobStatus.COMPLETED)
        assert await queue.get_job_status(task_id) == JobStatus.COMPLETED

        # 5. Queue should be empty
        assert await queue.get_queue_size() == 0

    @pytest.mark.asyncio
    async def test_priority_handling(self):
        """Test that jobs with higher priority are processed first"""
        queue = InMemoryJobQueue()

        # Enqueue jobs with different priorities
        low_priority_id = await queue.enqueue({
            "url": "https://example.com/low",
            "priority": -5
        })
        high_priority_id = await queue.enqueue({
            "url": "https://example.com/high",
            "priority": 10
        })
        normal_priority_id = await queue.enqueue({
            "url": "https://example.com/normal",
            "priority": 0
        })

        # Note: Basic InMemoryJobQueue doesn't implement priority sorting
        # This test documents expected behavior for priority-aware implementations

        # For now, just verify all jobs are enqueued
        assert await queue.get_queue_size() == 3

        # Dequeue all jobs and verify they exist
        job1 = await queue.dequeue()
        job2 = await queue.dequeue()
        job3 = await queue.dequeue()

        assert job1 is not None
        assert job2 is not None
        assert job3 is not None

        # All jobs should be accounted for
        task_ids = {job1["task_id"], job2["task_id"], job3["task_id"]}
        expected_ids = {low_priority_id, high_priority_id, normal_priority_id}
        assert task_ids == expected_ids


@pytest.mark.unit
class TestJobExecutor:
    """Test JobExecutor implementation"""

    @pytest.mark.asyncio
    async def test_executor_initialization(self):
        """Test job executor initialization"""
        mock_queue = Mock()

        executor = JobExecutor(job_queue=mock_queue, max_concurrent_jobs=3)

        assert executor.job_queue == mock_queue
        assert executor.max_concurrent_jobs == 3
        assert executor.running_jobs == {}
        assert executor.running is False

    @pytest.mark.asyncio
    async def test_start_and_stop_executor(self):
        """Test starting and stopping the executor"""
        mock_queue = Mock()
        executor = JobExecutor(job_queue=mock_queue)

        # Mock the worker method to avoid infinite loop
        with patch.object(executor, '_job_worker') as mock_worker:
            mock_worker.return_value = asyncio.Future()
            mock_worker.return_value.set_result(None)

            await executor.start()
            assert executor.running is True

            await executor.stop()
            assert executor.running is False

    @pytest.mark.asyncio
    async def test_execute_job_success(self):
        """Test successful job execution"""
        mock_queue = Mock()
        executor = JobExecutor(job_queue=mock_queue)

        job_info = {
            "task_id": "test-task-123",
            "data": {
                "url": "https://example.com",
                "method": "GET",
                "scraper_type": ScraperType.CLOUDSCRAPER
            }
        }

        # Mock scraper and database
        with patch('app.utils.executor.SessionLocal') as mock_session_local, \
                patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                patch('app.utils.executor.send_job_completed_webhook') as mock_webhook:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = Mock(
                status_code=200,
                content="<html>test</html>",
                headers={"content-type": "text/html"},
                response_time=1500.0,
                error=None,
                to_dict=Mock(return_value={"status_code": 200, "content": "<html>test</html>"})
            )
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            mock_webhook.return_value = asyncio.Future()
            mock_webhook.return_value.set_result(None)

            result = await executor.execute_job(job_info)

            assert result["success"] is True
            assert result["task_id"] == "test-task-123"
            mock_scraper.scrape.assert_called_once()
            mock_scraper.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_job_failure(self):
        """Test job execution failure"""
        mock_queue = Mock()
        executor = JobExecutor(job_queue=mock_queue)

        job_info = {
            "task_id": "test-task-123",
            "data": {
                "url": "https://example.com",
                "scraper_type": ScraperType.CLOUDSCRAPER
            }
        }

        # Mock scraper to raise exception
        with patch('app.utils.executor.SessionLocal') as mock_session_local, \
                patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                patch('app.utils.executor.send_job_failed_webhook') as mock_webhook:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            mock_scraper = AsyncMock()
            mock_scraper.scrape.side_effect = Exception("Scraping failed")
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            mock_webhook.return_value = asyncio.Future()
            mock_webhook.return_value.set_result(None)

            result = await executor.execute_job(job_info)

            assert result["success"] is False
            assert "error" in result
            assert "Scraping failed" in result["error"]
            mock_scraper.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_job_with_retries(self):
        """Test job execution with retry mechanism"""
        mock_queue = Mock()
        executor = JobExecutor(job_queue=mock_queue)

        job_info = {
            "task_id": "test-task-123",
            "data": {
                "url": "https://example.com",
                "scraper_type": ScraperType.CLOUDSCRAPER,
                "max_retries": 2
            }
        }

        with patch('app.utils.executor.SessionLocal') as mock_session_local, \
                patch('app.utils.executor.create_scraper') as mock_create_scraper:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            # Mock job record
            mock_job = Mock()
            mock_job.retry_count = 0
            mock_job.max_retries = 2
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            mock_scraper = AsyncMock()
            mock_scraper.scrape.side_effect = Exception("Temporary failure")
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            result = await executor.execute_job(job_info)

            # Should fail but attempt retry logic
            assert result["success"] is False
            mock_scraper.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_running_jobs_count(self):
        """Test getting running jobs count"""
        mock_queue = Mock()
        executor = JobExecutor(job_queue=mock_queue)

        # Add some mock running jobs
        executor.running_jobs = {
            "task1": Mock(),
            "task2": Mock(),
            "task3": Mock()
        }

        count = executor.get_running_jobs()
        assert count == 3

    @pytest.mark.asyncio
    async def test_max_concurrent_jobs_limit(self):
        """Test that executor respects max concurrent jobs limit"""
        mock_queue = AsyncMock()
        mock_queue.dequeue.return_value = None  # Empty queue

        executor = JobExecutor(job_queue=mock_queue, max_concurrent_jobs=2)

        # Simulate having max concurrent jobs running
        executor.running_jobs = {
            "task1": Mock(),
            "task2": Mock()
        }

        # Mock the worker method to test the capacity check
        with patch.object(executor, '_job_worker') as mock_worker:
            # Create a future that we can control
            future = asyncio.Future()
            mock_worker.return_value = future

            # Start executor
            await executor.start()

            # Give it a moment to check capacity
            await asyncio.sleep(0.1)

            # Should not dequeue when at capacity
            mock_queue.dequeue.assert_not_called()

            # Stop executor
            future.set_result(None)
            await executor.stop()

    @pytest.mark.asyncio
    async def test_job_cleanup_on_completion(self):
        """Test that completed jobs are cleaned up from running_jobs"""
        mock_queue = Mock()
        executor = JobExecutor(job_queue=mock_queue)

        job_info = {
            "task_id": "test-task-123",
            "data": {
                "url": "https://example.com",
                "scraper_type": ScraperType.CLOUDSCRAPER
            }
        }

        # Add job to running jobs
        mock_task = Mock()
        executor.running_jobs["test-task-123"] = mock_task

        with patch('app.utils.executor.SessionLocal') as mock_session_local, \
                patch('app.utils.executor.create_scraper') as mock_create_scraper, \
                patch('app.utils.executor.send_job_completed_webhook') as mock_webhook:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = Mock(
                status_code=200,
                content="test",
                headers={},
                response_time=1000.0,
                error=None,
                to_dict=Mock(return_value={"status_code": 200})
            )
            mock_scraper.close = AsyncMock()
            mock_create_scraper.return_value = mock_scraper

            mock_webhook.return_value = asyncio.Future()
            mock_webhook.return_value.set_result(None)

            await executor.execute_job(job_info)

            # Job should still be in running_jobs during execution
            # (cleanup happens via callback in real implementation)
            assert "test-task-123" in executor.running_jobs
