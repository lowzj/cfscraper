import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus, JobResult, ScraperType
from app.scrapers.factory import create_scraper
from app.utils.queue import JobQueue
from app.core.database import SessionLocal
from app.core.config import settings
from app.utils.webhooks import send_job_completed_webhook, send_job_failed_webhook

logger = logging.getLogger(__name__)


class JobExecutor:
    """Handles job execution with scrapers"""
    
    def __init__(self, job_queue: JobQueue):
        self.job_queue = job_queue
        self.running_jobs: Dict[str, asyncio.Task] = {}
        self.max_concurrent_jobs = settings.max_concurrent_jobs
        self.job_timeout = settings.job_timeout
    
    async def execute_job(self, job_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single scraping job
        
        Args:
            job_info: Job information from the queue
            
        Returns:
            Dictionary with execution results
        """
        task_id = job_info['task_id']
        job_data = job_info['data']
        
        # Create database session
        db = SessionLocal()
        
        try:
            # Create job record in database
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
            db.commit()
            
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
                    job.status = JobStatus.COMPLETED
                    job.result = result.to_dict()
                    job.completed_at = datetime.now()

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
                            "url": job.url,
                            "method": job.method,
                            "scraper_type": job.scraper_type.value,
                            "started_at": job.started_at.isoformat() if job.started_at else None,
                            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
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
                    job.status = JobStatus.FAILED
                    job.error_message = result.error
                    job.completed_at = datetime.now()

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
                            "url": job.url,
                            "method": job.method,
                            "scraper_type": job.scraper_type.value,
                            "started_at": job.started_at.isoformat() if job.started_at else None,
                            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                            "error": result.error
                        }
                        await send_job_failed_webhook(webhook_payload)
                    except Exception as e:
                        logger.warning(f"Failed to send failure webhook for job {task_id}: {str(e)}")
                
                db.commit()
                
                logger.info(f"Job {task_id} completed with status: {job.status}")
                
                return {
                    'task_id': task_id,
                    'status': job.status,
                    'result': job.result,
                    'error': job.error_message
                }
                
            except asyncio.TimeoutError:
                # Handle timeout
                job.status = JobStatus.FAILED
                job.error_message = f"Job timed out after {self.job_timeout} seconds"
                job.completed_at = datetime.now()
                
                await self.job_queue.update_job_status(
                    task_id,
                    JobStatus.FAILED,
                    error=job.error_message
                )
                
                db.commit()
                logger.warning(f"Job {task_id} timed out")
                
                return {
                    'task_id': task_id,
                    'status': JobStatus.FAILED,
                    'error': job.error_message
                }
                
            finally:
                # Clean up scraper
                await scraper.close()
                
        except Exception as e:
            # Handle unexpected errors
            error_msg = f"Unexpected error executing job {task_id}: {str(e)}"
            logger.error(error_msg)
            
            try:
                job.status = JobStatus.FAILED
                job.error_message = error_msg
                job.completed_at = datetime.now()
                db.commit()
                
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
            
        finally:
            db.close()
    
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