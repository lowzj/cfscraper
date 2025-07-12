from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import asyncio
import uuid
import json
import logging
from datetime import datetime

from app.models.job import Job, JobStatus
from app.core.config import settings

logger = logging.getLogger(__name__)


class JobQueue(ABC):
    """Abstract base class for job queue implementations"""
    
    @abstractmethod
    async def enqueue(self, job_data: Dict[str, Any]) -> str:
        """
        Add a job to the queue
        
        Args:
            job_data: Dictionary containing job parameters
            
        Returns:
            Task ID for the queued job
        """
        pass
    
    @abstractmethod
    async def dequeue(self) -> Optional[Dict[str, Any]]:
        """
        Get the next job from the queue
        
        Returns:
            Job data dictionary or None if queue is empty
        """
        pass
    
    @abstractmethod
    async def get_job_status(self, task_id: str) -> Optional[JobStatus]:
        """
        Get the status of a specific job
        
        Args:
            task_id: The task ID to check
            
        Returns:
            JobStatus or None if job not found
        """
        pass
    
    @abstractmethod
    async def update_job_status(self, task_id: str, status: JobStatus, **kwargs):
        """
        Update the status of a job
        
        Args:
            task_id: The task ID to update
            status: New status
            **kwargs: Additional fields to update
        """
        pass
    
    @abstractmethod
    async def get_queue_size(self) -> int:
        """Get the current queue size"""
        pass
    
    @abstractmethod
    async def clear_queue(self):
        """Clear all jobs from the queue"""
        pass
    
    @abstractmethod
    async def remove_job(self, task_id: str) -> bool:
        """
        Remove a specific job from the queue
        
        Args:
            task_id: The task ID to remove
            
        Returns:
            True if job was removed, False if not found
        """
        pass


class InMemoryJobQueue(JobQueue):
    """In-memory job queue implementation for development"""
    
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def enqueue(self, job_data: Dict[str, Any]) -> str:
        """Add a job to the in-memory queue"""
        task_id = str(uuid.uuid4())
        
        job_info = {
            'task_id': task_id,
            'status': JobStatus.QUEUED,
            'created_at': datetime.now().isoformat(),
            'data': job_data
        }
        
        async with self._lock:
            self._jobs[task_id] = job_info
            await self._queue.put(job_info)
        
        logger.info(f"Job {task_id} enqueued")
        return task_id
    
    async def dequeue(self) -> Optional[Dict[str, Any]]:
        """Get the next job from the in-memory queue"""
        try:
            job_info = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            
            # Check if job was removed (cleanup scenario)
            async with self._lock:
                if job_info['task_id'] not in self._jobs:
                    # Job was removed, skip it and try again
                    return await self.dequeue()
                
                # Update status to running
                self._jobs[job_info['task_id']]['status'] = JobStatus.RUNNING
                self._jobs[job_info['task_id']]['started_at'] = datetime.now().isoformat()
            
            return job_info
            
        except asyncio.TimeoutError:
            return None
    
    async def get_job_status(self, task_id: str) -> Optional[JobStatus]:
        """Get job status from in-memory storage"""
        async with self._lock:
            job = self._jobs.get(task_id)
            return job['status'] if job else None
    
    async def update_job_status(self, task_id: str, status: JobStatus, **kwargs):
        """Update job status in in-memory storage"""
        async with self._lock:
            if task_id in self._jobs:
                self._jobs[task_id]['status'] = status
                self._jobs[task_id].update(kwargs)
                
                if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                    self._jobs[task_id]['completed_at'] = datetime.now().isoformat()
    
    async def get_queue_size(self) -> int:
        """Get current queue size"""
        return self._queue.qsize()
    
    async def clear_queue(self):
        """Clear all jobs from the queue"""
        async with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._jobs.clear()
    
    async def remove_job(self, task_id: str) -> bool:
        """Remove a specific job from the in-memory queue"""
        async with self._lock:
            if task_id in self._jobs:
                # Remove from jobs tracking
                del self._jobs[task_id]
                
                # Note: For in-memory queue, we can't easily remove from the asyncio.Queue
                # The job will be skipped when dequeued since it's no longer in _jobs
                return True
            return False
    
    def get_all_jobs(self) -> Dict[str, Dict[str, Any]]:
        """Get all jobs (for debugging)"""
        return self._jobs.copy()


class RedisJobQueue(JobQueue):
    """Redis-based job queue implementation for production"""
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.redis_url
        self.redis_client = None
        self.queue_key = "cfscraper:job_queue"
        self.status_key_prefix = "cfscraper:job_status:"
    
    async def _get_redis_client(self):
        """Get Redis client (lazy initialization)"""
        if self.redis_client is None:
            try:
                import redis.asyncio as redis
                self.redis_client = redis.from_url(self.redis_url)
                await self.redis_client.ping()
                logger.info("Redis client connected")
            except ImportError:
                logger.error("Redis not available, falling back to in-memory queue")
                raise
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                raise
        return self.redis_client
    
    async def enqueue(self, job_data: Dict[str, Any]) -> str:
        """Add a job to the Redis queue"""
        redis_client = await self._get_redis_client()
        task_id = str(uuid.uuid4())
        
        job_info = {
            'task_id': task_id,
            'status': JobStatus.QUEUED,
            'created_at': datetime.now().isoformat(),
            'data': job_data
        }
        
        # Store job in Redis
        await redis_client.rpush(self.queue_key, json.dumps(job_info))
        await redis_client.hset(
            f"{self.status_key_prefix}{task_id}",
            mapping=job_info
        )
        
        logger.info(f"Job {task_id} enqueued in Redis")
        return task_id
    
    async def dequeue(self) -> Optional[Dict[str, Any]]:
        """Get the next job from Redis queue"""
        try:
            redis_client = await self._get_redis_client()
            
            # Pop job from queue
            job_data = await redis_client.blpop(self.queue_key, timeout=1)
            if not job_data:
                return None
            
            job_info = json.loads(job_data[1])
            task_id = job_info['task_id']
            
            # Check if job was removed (cleanup scenario)
            job_exists = await redis_client.exists(f"{self.status_key_prefix}{task_id}")
            if not job_exists:
                # Job was removed, skip it and try again
                return await self.dequeue()
            
            # Update status to running
            await redis_client.hset(
                f"{self.status_key_prefix}{task_id}",
                mapping={
                    'status': JobStatus.RUNNING,
                    'started_at': datetime.now().isoformat()
                }
            )
            
            return job_info
            
        except Exception as e:
            logger.error(f"Error dequeuing from Redis: {str(e)}")
            return None
    
    async def get_job_status(self, task_id: str) -> Optional[JobStatus]:
        """Get job status from Redis"""
        try:
            redis_client = await self._get_redis_client()
            status = await redis_client.hget(f"{self.status_key_prefix}{task_id}", 'status')
            return JobStatus(status.decode()) if status else None
        except Exception as e:
            logger.error(f"Error getting job status from Redis: {str(e)}")
            return None
    
    async def update_job_status(self, task_id: str, status: JobStatus, **kwargs):
        """Update job status in Redis"""
        try:
            redis_client = await self._get_redis_client()
            update_data = {'status': status, **kwargs}
            
            if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                update_data['completed_at'] = datetime.now().isoformat()
            
            await redis_client.hset(
                f"{self.status_key_prefix}{task_id}",
                mapping=update_data
            )
        except Exception as e:
            logger.error(f"Error updating job status in Redis: {str(e)}")
    
    async def get_queue_size(self) -> int:
        """Get current queue size from Redis"""
        try:
            redis_client = await self._get_redis_client()
            return await redis_client.llen(self.queue_key)
        except Exception as e:
            logger.error(f"Error getting queue size from Redis: {str(e)}")
            return 0
    
    async def clear_queue(self):
        """Clear all jobs from Redis queue"""
        try:
            redis_client = await self._get_redis_client()
            await redis_client.delete(self.queue_key)
            
            # Clear all job status keys
            keys = await redis_client.keys(f"{self.status_key_prefix}*")
            if keys:
                await redis_client.delete(*keys)
        except Exception as e:
            logger.error(f"Error clearing Redis queue: {str(e)}")
    
    async def remove_job(self, task_id: str) -> bool:
        """Remove a specific job from Redis queue"""
        try:
            redis_client = await self._get_redis_client()
            
            # Remove job status
            status_deleted = await redis_client.delete(f"{self.status_key_prefix}{task_id}")
            
            # Remove from queue (this is complex since Redis lists don't have direct remove by value)
            # We'll mark the job as cancelled in case it's still in the queue
            if status_deleted:
                await redis_client.hset(
                    f"{self.status_key_prefix}{task_id}_removed",
                    mapping={'status': JobStatus.CANCELLED, 'removed_at': datetime.now().isoformat()}
                )
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error removing job from Redis: {str(e)}")
            return False


def create_job_queue() -> JobQueue:
    """Create appropriate job queue based on configuration"""
    if settings.use_in_memory_queue:
        return InMemoryJobQueue()
    else:
        try:
            return RedisJobQueue()
        except Exception as e:
            logger.warning(f"Failed to create Redis queue, falling back to in-memory: {str(e)}")
            return InMemoryJobQueue()