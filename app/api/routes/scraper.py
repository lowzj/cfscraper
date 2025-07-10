"""
Core scraping endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import uuid
import io
import json

from app.core.database import get_db
from app.models.job import Job, JobStatus, ScraperType
from app.models.requests import ScrapeRequest, BulkScrapeRequest
from app.models.responses import (
    ScrapeResponse, 
    JobStatusResponse, 
    JobResult, 
    BulkScrapeResponse,
    DownloadResponse
)
from app.utils.queue import JobQueue, create_job_queue
from app.utils.executor import JobExecutor

router = APIRouter()

# Global job queue and executor
job_queue = create_job_queue()
job_executor = JobExecutor(job_queue)


@router.post("/", response_model=ScrapeResponse)
async def create_scrape_job(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create a new scraping job
    
    Creates a new scraping job with the provided configuration and adds it to the queue
    for processing. Returns immediately with a job ID that can be used to track progress.
    
    Args:
        request: Scraping request parameters
        background_tasks: FastAPI background tasks
        db: Database session
        
    Returns:
        ScrapeResponse with job ID and status
    """
    try:
        # Generate unique job ID
        job_id = f"job_{str(uuid.uuid4())}"
        
        # Prepare job data
        job_data = {
            'job_id': job_id,
            'url': str(request.url),
            'method': request.method,
            'headers': request.headers or {},
            'data': request.data or {},
            'params': request.params or {},
            'scraper_type': request.scraper_type,
            'config': request.config.dict(),
            'tags': request.tags or [],
            'priority': request.priority,
            'callback_url': str(request.callback_url) if request.callback_url else None
        }
        
        # Create job record in database
        job = Job(
            task_id=job_id,
            url=str(request.url),
            method=request.method,
            headers=request.headers or {},
            data=request.data or {},
            params=request.params or {},
            scraper_type=request.scraper_type,
            max_retries=request.config.max_retries,
            status=JobStatus.QUEUED,
            created_at=datetime.utcnow()
        )
        
        db.add(job)
        db.commit()
        db.refresh(job)
        
        # Enqueue job
        await job_queue.enqueue(job_data)
        
        return ScrapeResponse(
            job_id=job_id,
            task_id=job_id,
            status=JobStatus.QUEUED,
            message=f"Job {job_id} queued successfully",
            created_at=datetime.utcnow()
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create scraping job: {str(e)}"
        )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Get the status of a specific job
    
    Retrieves the current status and details of a scraping job, including progress,
    results, and error information if applicable.
    
    Args:
        job_id: The job ID to check
        db: Database session
        
    Returns:
        JobStatusResponse with job details
    """
    try:
        # Get job from database
        job = db.query(Job).filter(Job.task_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Check queue status
        queue_status = await job_queue.get_job_status(job_id)
        
        # Build result
        result = None
        if job.result:
            result = JobResult(
                status_code=job.result.get('status_code'),
                response_time=job.result.get('response_time'),
                content_length=job.result.get('content_length'),
                content_type=job.result.get('content_type'),
                headers=job.result.get('headers', {}),
                content=job.result.get('content'),
                text=job.result.get('text'),
                links=job.result.get('links', []),
                images=job.result.get('images', []),
                final_url=job.result.get('final_url'),
                screenshot_url=job.result.get('screenshot_url'),
                error_message=job.result.get('error_message'),
                error_type=job.result.get('error_type')
            )
        
        return JobStatusResponse(
            job_id=job_id,
            task_id=job_id,
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
            tags=job.result.get('tags', []) if job.result else [],
            priority=job.result.get('priority', 0) if job.result else 0
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get job status: {str(e)}"
        )


@router.get("/{job_id}/result", response_model=JobResult)
async def get_job_result(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Get the result of a completed job
    
    Retrieves the full result data of a completed scraping job, including the 
    scraped content, metadata, and any extracted data.
    
    Args:
        job_id: The job ID to get results for
        db: Database session
        
    Returns:
        JobResult with complete job results
    """
    try:
        # Get job from database
        job = db.query(Job).filter(Job.task_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=400, 
                detail=f"Job is not completed. Current status: {job.status}"
            )
        
        if not job.result:
            raise HTTPException(
                status_code=404, 
                detail="Job result not found"
            )
        
        return JobResult(
            status_code=job.result.get('status_code'),
            response_time=job.result.get('response_time'),
            content_length=job.result.get('content_length'),
            content_type=job.result.get('content_type'),
            headers=job.result.get('headers', {}),
            content=job.result.get('content'),
            text=job.result.get('text'),
            links=job.result.get('links', []),
            images=job.result.get('images', []),
            final_url=job.result.get('final_url'),
            screenshot_url=job.result.get('screenshot_url'),
            error_message=job.result.get('error_message'),
            error_type=job.result.get('error_type')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get job result: {str(e)}"
        )


@router.get("/{job_id}/download", response_model=DownloadResponse)
async def get_job_download(
    job_id: str,
    format: str = "html",
    db: Session = Depends(get_db)
):
    """
    Download job result as a file
    
    Provides a download link or direct download of the job result in various formats.
    
    Args:
        job_id: The job ID to download results for
        format: Download format (html, json, txt)
        db: Database session
        
    Returns:
        DownloadResponse with download information
    """
    try:
        # Get job from database
        job = db.query(Job).filter(Job.task_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=400, 
                detail=f"Job is not completed. Current status: {job.status}"
            )
        
        if not job.result:
            raise HTTPException(
                status_code=404, 
                detail="Job result not found"
            )
        
        # Determine content and filename based on format
        if format.lower() == "html":
            content = job.result.get('content', '')
            filename = f"{job_id}.html"
            content_type = "text/html"
        elif format.lower() == "json":
            content = json.dumps(job.result, indent=2)
            filename = f"{job_id}.json"
            content_type = "application/json"
        elif format.lower() == "txt":
            content = job.result.get('text', job.result.get('content', ''))
            filename = f"{job_id}.txt"
            content_type = "text/plain"
        else:
            raise HTTPException(
                status_code=400, 
                detail="Unsupported format. Use 'html', 'json', or 'txt'"
            )
        
        # Create download stream
        content_stream = io.BytesIO(content.encode('utf-8'))
        
        return StreamingResponse(
            io.BytesIO(content.encode('utf-8')),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to download job result: {str(e)}"
        )


@router.delete("/{job_id}")
async def cancel_job(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Cancel a specific job
    
    Cancels a queued or running job. Completed jobs cannot be cancelled.
    
    Args:
        job_id: The job ID to cancel
        db: Database session
        
    Returns:
        Success message
    """
    try:
        # Get job from database
        job = db.query(Job).filter(Job.task_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status in [JobStatus.COMPLETED, JobStatus.CANCELLED]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot cancel job with status: {job.status}"
            )
        
        # Update job status in queue
        await job_queue.update_job_status(job_id, JobStatus.CANCELLED)
        
        # Update job in database
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.utcnow()
        db.commit()
        
        return {'message': f'Job {job_id} cancelled successfully'}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to cancel job: {str(e)}"
        )


@router.post("/bulk", response_model=BulkScrapeResponse)
async def create_bulk_scrape_jobs(
    request: BulkScrapeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create multiple scraping jobs in bulk
    
    Creates multiple scraping jobs from a single request. Jobs are processed 
    according to the specified parallel limit.
    
    Args:
        request: Bulk scraping request with multiple jobs
        background_tasks: FastAPI background tasks
        db: Database session
        
    Returns:
        BulkScrapeResponse with batch information
    """
    try:
        # Generate batch ID
        batch_id = f"batch_{str(uuid.uuid4())}"
        job_ids = []
        
        # Create jobs
        for job_request in request.jobs:
            job_id = f"job_{str(uuid.uuid4())}"
            job_ids.append(job_id)
            
            # Prepare job data
            job_data = {
                'job_id': job_id,
                'batch_id': batch_id,
                'url': str(job_request.url),
                'method': job_request.method,
                'headers': job_request.headers or {},
                'data': job_request.data or {},
                'params': job_request.params or {},
                'scraper_type': job_request.scraper_type,
                'config': job_request.config.dict(),
                'tags': job_request.tags or [],
                'priority': job_request.priority,
                'callback_url': str(job_request.callback_url) if job_request.callback_url else None
            }
            
            # Create job record in database
            job = Job(
                task_id=job_id,
                url=str(job_request.url),
                method=job_request.method,
                headers=job_request.headers or {},
                data=job_request.data or {},
                params=job_request.params or {},
                scraper_type=job_request.scraper_type,
                max_retries=job_request.config.max_retries,
                status=JobStatus.QUEUED,
                created_at=datetime.utcnow()
            )
            
            db.add(job)
            
            # Enqueue job
            await job_queue.enqueue(job_data)
        
        db.commit()
        
        return BulkScrapeResponse(
            batch_id=batch_id,
            job_ids=job_ids,
            total_jobs=len(job_ids),
            status="queued",
            created_at=datetime.utcnow()
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create bulk scraping jobs: {str(e)}"
        )