import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.job import Job, JobStatus, JobResult, ScraperType
from app.scrapers.factory import create_scraper
from app.utils.queue import JobQueue
from app.database.connection import connection_manager
from app.core.config import settings
from app.utils.webhooks import send_job_completed_webhook, send_job_failed_webhook

logger = logging.getLogger(__name__)


class AsyncJobExecutor:
    """Handles async job execution with scrapers"""
    
    def __init__(self, job_queue: JobQueue):
        self.job_queue = job_queue
        self.running_jobs: Dict[str, asyncio.Task] = {}
        self.max_concurrent_jobs = settings.max_concurrent_jobs
        self.job_timeout = settings.job_timeout
    
    @asynccontextmanager
    async def get_db_session(self) -> AsyncSession:
        """Get async database session with proper error handling"""
        async with connection_manager.get_async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
    
    async def execute_job(self, job_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single scraping job asynchronously
        
        Args:
            job_info: Job information from the queue
            
        Returns:
            Dictionary with execution results
        """
        task_id = job_info['task_id']
        job_data = job_info['data']
        
        async with self.get_db_session() as db:
            try:
                # Create or update job record in database
                job_stmt = select(Job).where(Job.task_id == task_id)
                result = await db.execute(job_stmt)
                job = result.scalar_one_or_none()
                
                if not job:
                    job = Job(
                        task_id=task_id,
                        status=JobStatus.RUNNING,
                        url=job_data['url'],
                        method=job_data.get('method', 'GET'),
                        headers=job_data.get('headers', {}),
                        data=job_data.get('data', {}),
                        params=job_data.get('params', {}),
                        scraper_type=job_data.get('scraper_type', ScraperType.CLOUDSCRAPER),
                        max_retries=job_data.get('max_retries', 3),
                        started_at=datetime.now()
                    )
                    db.add(job)
                else:
                    # Update existing job
                    update_stmt = update(Job).where(Job.task_id == task_id).values(
                        status=JobStatus.RUNNING,
                        started_at=datetime.now()
                    )
                    await db.execute(update_stmt)
                
                await db.commit()
                
                # Update job status in queue
                await self.job_queue.update_job_status(task_id, JobStatus.RUNNING)
                
                # Create scraper
                scraper_type = ScraperType(job_data.get('scraper_type', ScraperType.CLOUDSCRAPER))
                scraper = create_scraper(
                    scraper_type=scraper_type,
                    timeout=job_data.get('timeout', settings.selenium_timeout),
                    headless=job_data.get('headless', True)
                )
                
                try:
                    # Execute scraping with timeout
                    result = await asyncio.wait_for(
                        scraper.scrape(
                            url=job_data['url'],
                            method=job_data.get('method', 'GET'),
                            headers=job_data.get('headers'),
                            data=job_data.get('data'),
                            params=job_data.get('params')
                        ),
                        timeout=self.job_timeout
                    )
                    
                    # Update job status
                    if result.is_success():
                        # Update job with success
                        update_stmt = update(Job).where(Job.task_id == task_id).values(
                            status=JobStatus.COMPLETED,
                            result=result.to_dict(),
                            completed_at=datetime.now()
                        )
                        await db.execute(update_stmt)

                        # Store result in separate table
                        job_result = JobResult(
                            job_id=job.id,
                            task_id=task_id,
                            status_code=result.status_code,
                            response_headers=result.headers,
                            response_content=result.content,
                            response_time=int(result.response_time),
                            content_length=len(result.content),
                            content_type=result.headers.get('content-type', 'text/html')
                        )
                        db.add(job_result)
                        await db.commit()

                        await self.job_queue.update_job_status(
                            task_id,
                            JobStatus.COMPLETED,
                            result=result.to_dict()
                        )

                        # Send webhook for job completion
                        try:
                            webhook_payload = {
                                "job_id": task_id,
                                "status": "completed",
                                "url": job_data['url'],
                                "method": job_data.get('method', 'GET'),
                                "scraper_type": scraper_type.value,
                                "started_at": job.started_at.isoformat() if job.started_at else None,
                                "completed_at": datetime.now().isoformat(),
                                "result": {
                                    "status_code": result.status_code,
                                    "response_time": result.response_time,
                                    "content_length": len(result.content),
                                    "content_type": result.headers.get('content-type', 'text/html')
                                }
                            }
                            await send_job_completed_webhook(webhook_payload)
                        except Exception as e:
                            logger.warning(f"Failed to send completion webhook for job {task_id}: {str(e)}")

                    else:
                        # Update job with failure
                        update_stmt = update(Job).where(Job.task_id == task_id).values(
                            status=JobStatus.FAILED,
                            error_message=result.error,
                            completed_at=datetime.now()
                        )
                        await db.execute(update_stmt)
                        await db.commit()

                        await self.job_queue.update_job_status(
                            task_id,
                            JobStatus.FAILED,
                            error=result.error
                        )

                        # Send webhook for job failure
                        try:
                            webhook_payload = {
                                "job_id": task_id,
                                "status": "failed",
                                "url": job_data['url'],
                                "method": job_data.get('method', 'GET'),
                                "scraper_type": scraper_type.value,
                                "started_at": job.started_at.isoformat() if job.started_at else None,
                                "completed_at": datetime.now().isoformat(),
                                "error": result.error
                            }
                            await send_job_failed_webhook(webhook_payload)
                        except Exception as e:
                            logger.warning(f"Failed to send failure webhook for job {task_id}: {str(e)}")
                    
                    logger.info(f"Job {task_id} completed with status: {JobStatus.COMPLETED if result.is_success() else JobStatus.FAILED}")
                    
                    return {
                        'task_id': task_id,
                        'status': JobStatus.COMPLETED if result.is_success() else JobStatus.FAILED,
                        'result': result.to_dict() if result.is_success() else None,
                        'error': result.error if not result.is_success() else None
                    }
                    
                except asyncio.TimeoutError:
                    # Handle timeout
                    error_msg = f"Job timed out after {self.job_timeout} seconds"
                    
                    update_stmt = update(Job).where(Job.task_id == task_id).values(
                        status=JobStatus.FAILED,
                        error_message=error_msg,
                        completed_at=datetime.now()
                    )
                    await db.execute(update_stmt)
                    await db.commit()
                    
                    await self.job_queue.update_job_status(
                        task_id,
                        JobStatus.FAILED,
                        error=error_msg
                    )
                    
                    logger.warning(f"Job {task_id} timed out")
                    
                    return {
                        'task_id': task_id,
                        'status': JobStatus.FAILED,
                        'error': error_msg
                    }
                    
                finally:
                    # Clean up scraper
                    await scraper.close()
                    
            except Exception as e:
                # Handle unexpected errors
                error_msg = f"Unexpected error executing job {task_id}: {str(e)}"
                logger.error(error_msg)
                
                try:
                    update_stmt = update(Job).where(Job.task_id == task_id).values(
                        status=JobStatus.FAILED,
                        error_message=error_msg,
                        completed_at=datetime.now()
                    )
                    await db.execute(update_stmt)
                    await db.commit()
                    
                    await self.job_queue.update_job_status(
                        task_id,
                        JobStatus.FAILED,
                        error=error_msg
                    )
                except Exception:
                    pass  # Ignore errors during error handling
                
                return {
                    'task_id': task_id,
                    'status': JobStatus.FAILED,
                    'error': error_msg
                }
    
    async def start_worker(self):
        """Start the job worker loop"""
        logger.info("Starting job worker")
        
        while True:
            try:
                # Check if we have capacity for more jobs
                if len(self.running_jobs) >= self.max_concurrent_jobs:
                    await asyncio.sleep(1)
                    continue
                
                # Get next job from queue
                job_info = await self.job_queue.dequeue()
                if not job_info:
                    await asyncio.sleep(1)
                    continue
                
                # Start job execution
                task_id = job_info['task_id']
                task = asyncio.create_task(self.execute_job(job_info))
                self.running_jobs[task_id] = task
                
                # Set up cleanup callback
                def cleanup_job(task):
                    if task_id in self.running_jobs:
                        del self.running_jobs[task_id]
                
                task.add_done_callback(cleanup_job)
                
                logger.info(f"Started job {task_id}")
                
            except Exception as e:
                logger.error(f"Error in job worker: {str(e)}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def stop_worker(self):
        """Stop the job worker and cancel running jobs"""
        logger.info("Stopping job worker")
        
        # Cancel all running jobs
        for task_id, task in self.running_jobs.items():
            task.cancel()
            logger.info(f"Cancelled job {task_id}")
        
        # Wait for jobs to finish
        if self.running_jobs:
            await asyncio.gather(*self.running_jobs.values(), return_exceptions=True)
        
        self.running_jobs.clear()
        logger.info("Job worker stopped")
    
    def get_running_jobs(self) -> list[str]:
        """Get list of currently running job IDs"""
        return list(self.running_jobs.keys())
    
    def get_job_count(self) -> int:
        """Get number of currently running jobs"""
        return len(self.running_jobs)

# Backward compatibility alias
JobExecutor = AsyncJobExecutor