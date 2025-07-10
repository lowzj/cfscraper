from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.job import Job, JobStatus, ScraperType
from app.utils.queue import JobQueue, create_job_queue
from app.utils.executor import JobExecutor

router = APIRouter()

# Global job queue and executor
job_queue = create_job_queue()
job_executor = JobExecutor(job_queue)


class ScrapeRequest(BaseModel):
    """Request model for scraping jobs"""
    url: str = Field(..., description="URL to scrape")
    method: str = Field(default="GET", description="HTTP method")
    headers: Optional[Dict[str, str]] = Field(default=None, description="HTTP headers")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Request data")
    params: Optional[Dict[str, str]] = Field(default=None, description="Query parameters")
    scraper_type: ScraperType = Field(default=ScraperType.CLOUDSCRAPER, description="Scraper type")
    timeout: Optional[int] = Field(default=None, description="Request timeout")
    headless: bool = Field(default=True, description="Run browser in headless mode (for Selenium)")
    max_retries: int = Field(default=3, description="Maximum retry attempts")


class ScrapeResponse(BaseModel):
    """Response model for scraping jobs"""
    task_id: str = Field(..., description="Task ID for tracking")
    status: JobStatus = Field(..., description="Current job status")
    message: str = Field(..., description="Status message")


class JobStatusResponse(BaseModel):
    """Response model for job status"""
    task_id: str
    status: JobStatus
    progress: int = Field(default=0, description="Progress percentage")
    progress_message: Optional[str] = Field(default=None, description="Progress message")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Job result")
    error_message: Optional[str] = Field(default=None, description="Error message")
    created_at: Optional[str] = Field(default=None, description="Job creation time")
    started_at: Optional[str] = Field(default=None, description="Job start time")
    completed_at: Optional[str] = Field(default=None, description="Job completion time")


@router.post("/scrape", response_model=ScrapeResponse)
async def create_scrape_job(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create a new scraping job
    
    Args:
        request: Scraping request parameters
        background_tasks: FastAPI background tasks
        db: Database session
        
    Returns:
        ScrapeResponse with task ID and status
    """
    try:
        # Validate URL
        if not request.url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
        
        # Prepare job data
        job_data = {
            'url': request.url,
            'method': request.method,
            'headers': request.headers or {},
            'data': request.data or {},
            'params': request.params or {},
            'scraper_type': request.scraper_type,
            'timeout': request.timeout,
            'headless': request.headless,
            'max_retries': request.max_retries
        }
        
        # Enqueue job
        task_id = await job_queue.enqueue(job_data)
        
        return ScrapeResponse(
            task_id=task_id,
            status=JobStatus.QUEUED,
            message=f"Job {task_id} queued successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create scraping job: {str(e)}")


@router.get("/jobs/{task_id}", response_model=JobStatusResponse)
async def get_job_status(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    Get the status of a specific job
    
    Args:
        task_id: The task ID to check
        db: Database session
        
    Returns:
        JobStatusResponse with job details
    """
    try:
        # First check the queue
        queue_status = await job_queue.get_job_status(task_id)
        
        # Then check the database
        job = db.query(Job).filter(Job.task_id == task_id).first()
        
        if not job and not queue_status:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Build response
        response_data = {
            'task_id': task_id,
            'status': queue_status or (job.status if job else JobStatus.QUEUED),
        }
        
        if job:
            response_data.update({
                'progress': job.progress,
                'progress_message': job.progress_message,
                'result': job.result,
                'error_message': job.error_message,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            })
        
        return JobStatusResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")


@router.get("/jobs")
async def list_jobs(
    status: Optional[JobStatus] = None,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    List jobs with optional filtering
    
    Args:
        status: Filter by job status
        limit: Maximum number of jobs to return
        offset: Number of jobs to skip
        db: Database session
        
    Returns:
        List of jobs
    """
    try:
        query = db.query(Job)
        
        if status:
            query = query.filter(Job.status == status)
        
        jobs = query.offset(offset).limit(limit).all()
        
        return {
            'jobs': [
                {
                    'task_id': job.task_id,
                    'status': job.status,
                    'url': job.url,
                    'scraper_type': job.scraper_type,
                    'created_at': job.created_at.isoformat() if job.created_at else None,
                    'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                }
                for job in jobs
            ],
            'total': query.count(),
            'limit': limit,
            'offset': offset
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {str(e)}")


@router.delete("/jobs/{task_id}")
async def cancel_job(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    Cancel a specific job
    
    Args:
        task_id: The task ID to cancel
        db: Database session
        
    Returns:
        Success message
    """
    try:
        # Update job status in queue
        await job_queue.update_job_status(task_id, JobStatus.CANCELLED)
        
        # Update job in database
        job = db.query(Job).filter(Job.task_id == task_id).first()
        if job and job.status in [JobStatus.QUEUED, JobStatus.RUNNING]:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now()
            db.commit()
        
        return {'message': f'Job {task_id} cancelled successfully'}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


@router.get("/queue/status")
async def get_queue_status():
    """
    Get queue status information
    
    Returns:
        Queue status information
    """
    try:
        queue_size = await job_queue.get_queue_size()
        running_jobs = job_executor.get_running_jobs()
        
        return {
            'queue_size': queue_size,
            'running_jobs': len(running_jobs),
            'max_concurrent_jobs': job_executor.max_concurrent_jobs,
            'running_job_ids': running_jobs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")


@router.post("/queue/clear")
async def clear_queue():
    """
    Clear all jobs from the queue
    
    Returns:
        Success message
    """
    try:
        await job_queue.clear_queue()
        return {'message': 'Queue cleared successfully'}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear queue: {str(e)}")


# Import datetime for job cancellation
from datetime import datetime