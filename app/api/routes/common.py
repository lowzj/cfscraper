"""
Common utilities for API routes
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.models.responses import JobResult, JobStatusResponse
from app.utils.queue import JobQueue, create_job_queue

# Try to import executor, but handle missing dependencies
try:
    from app.utils.executor import AsyncJobExecutor

    job_queue = create_job_queue()
    job_executor = AsyncJobExecutor(job_queue)
except Exception:
    job_executor = None
    job_queue = create_job_queue()


def get_job_queue() -> JobQueue:
    """Get the global job queue instance"""
    return job_queue


def get_job_executor() -> Optional[AsyncJobExecutor]:
    """Get the global job executor instance"""
    return job_executor


def build_job_result(job_result_dict: dict) -> JobResult:
    """
    Build a JobResult object from a job result dictionary
    
    Args:
        job_result_dict: Dictionary containing job result data
        
    Returns:
        JobResult object
    """
    return JobResult(
        status_code=job_result_dict.get('status_code'),
        response_time=job_result_dict.get('response_time'),
        content_length=job_result_dict.get('content_length'),
        content_type=job_result_dict.get('content_type'),
        headers=job_result_dict.get('headers', {}),
        content=job_result_dict.get('content'),
        text=job_result_dict.get('text'),
        links=job_result_dict.get('links', []),
        images=job_result_dict.get('images', []),
        final_url=job_result_dict.get('final_url'),
        screenshot_url=job_result_dict.get('screenshot_url'),
        error_message=job_result_dict.get('error_message'),
        error_type=job_result_dict.get('error_type')
    )


def build_job_status_response(job: Job, queue_status: Optional[JobStatus] = None) -> JobStatusResponse:
    """
    Build a JobStatusResponse object from a Job database object
    
    Args:
        job: Job database object
        queue_status: Optional queue status to override job status
        
    Returns:
        JobStatusResponse object
    """
    # Build result if available
    result = None
    if job.result:
        result = build_job_result(job.result)

    return JobStatusResponse(
        job_id=job.task_id,
        task_id=job.task_id,
        status=queue_status or job.status,
        progress=job.progress,
        progress_message=job.progress_message,
        url=job.url,
        method=job.method,
        scraper_type=job.scraper_type,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        result=result,
        error_message=job.error_message,
        retry_count=job.retry_count,
        tags=job.tags or [],
        priority=job.priority or 0
    )


async def get_job_by_id(job_id: str, db: AsyncSession) -> Job:
    """
    Get a job by ID from the database
    
    Args:
        job_id: The job ID to look up
        db: Async database session
        
    Returns:
        Job object
        
    Raises:
        HTTPException: If job not found
    """
    result = await db.execute(select(Job).where(Job.task_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def validate_job_completed(job: Job) -> None:
    """
    Validate that a job is completed
    
    Args:
        job: Job object to validate
        
    Raises:
        HTTPException: If job is not completed
    """
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed. Current status: {job.status}"
        )


def validate_job_has_result(job: Job) -> None:
    """
    Validate that a job has a result
    
    Args:
        job: Job object to validate
        
    Raises:
        HTTPException: If job has no result
    """
    if not job.result:
        raise HTTPException(
            status_code=404,
            detail="Job result not found"
        )


def handle_route_exception(e: Exception, operation: str) -> HTTPException:
    """
    Handle common route exceptions
    
    Args:
        e: Exception to handle
        operation: Description of the operation that failed
        
    Returns:
        HTTPException to raise
    """
    if isinstance(e, HTTPException):
        return e

    return HTTPException(
        status_code=500,
        detail=f"Failed to {operation}: {str(e)}"
    )
