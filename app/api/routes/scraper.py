"""
Core scraping endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone
import uuid
import io
import json

from app.core.database import get_db
from app.models.job import Job, JobStatus, ScraperType
from app.models.requests import ScrapeRequest, BulkScrapeRequest
from app.security.validation import SecureScrapeRequest
from app.security.authentication import verify_api_key, require_api_key, APIKeyPermission, APIKeyInfo, security
from app.models.responses import (
    ScrapeResponse,
    JobStatusResponse,
    JobResult,
    BulkScrapeResponse,
    DownloadResponse
)


# Wrapper function for write permission requirement
async def require_write_permission(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> APIKeyInfo:
    """Require API key with WRITE permission"""
    return await require_api_key(request, credentials, APIKeyPermission.WRITE)
from .common import (
    get_job_queue, 
    get_job_executor,
    build_job_result,
    build_job_status_response,
    get_job_by_id,
    validate_job_completed,
    validate_job_has_result,
    handle_route_exception
)

router = APIRouter()


class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime and other non-serializable objects"""
    
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        elif hasattr(obj, 'to_dict'):
            return obj.to_dict()
        else:
            return str(obj)


@router.post("/", response_model=ScrapeResponse)
async def create_scrape_job(
    request: SecureScrapeRequest,  # Use secure validation
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key_info: APIKeyInfo = Depends(require_write_permission)
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
            'config': request.config.model_dump(),
            'tags': request.tags or [],
            'priority': request.priority,
            'callback_url': str(request.callback_url) if request.callback_url else None
        }
        
        # Create job record in database (but don't commit yet)
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
            tags=request.tags or [],
            priority=request.priority,
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(job)
        
        # Try to enqueue job first
        try:
            await get_job_queue().enqueue(job_data)
            # Only commit if enqueue succeeds
            db.commit()
            db.refresh(job)
        except Exception as enqueue_error:
            # Rollback database transaction if enqueue fails
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to enqueue job: {str(enqueue_error)}"
            )
        
        return ScrapeResponse(
            job_id=job_id,
            task_id=job_id,
            status=JobStatus.QUEUED,
            message=f"Job {job_id} queued successfully",
            created_at=datetime.now(timezone.utc)
        )
        
    except HTTPException:
        # Re-raise HTTPExceptions to preserve status code and detail
        raise
    except Exception as e:
        db.rollback()
        raise handle_route_exception(e, "create scraping job")


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
        job = get_job_by_id(job_id, db)
        
        # Check queue status
        queue_status = await get_job_queue().get_job_status(job_id)
        
        return build_job_status_response(job, queue_status)
        
    except Exception as e:
        raise handle_route_exception(e, "get job status")


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
        job = get_job_by_id(job_id, db)
        
        # Validate job status and result
        validate_job_completed(job)
        validate_job_has_result(job)
        
        return build_job_result(job.result)
        
    except Exception as e:
        raise handle_route_exception(e, "get job result")


@router.get("/{job_id}/download")
async def get_job_download(
    job_id: str,
    format: str = "html",
    db: Session = Depends(get_db)
):
    """
    Download job result as a file
    
    Provides a direct download of the job result in various formats.
    
    Args:
        job_id: The job ID to download results for
        format: Download format (html, json, txt)
        db: Database session
        
    Returns:
        StreamingResponse with the file content
    """
    try:
        # Get job from database
        job = get_job_by_id(job_id, db)
        
        # Validate job status and result
        validate_job_completed(job)
        validate_job_has_result(job)
        
        # Determine content and filename based on format
        if format.lower() == "html":
            content = job.result.get('content', '')
            filename = f"{job_id}.html"
            content_type = "text/html"
        elif format.lower() == "json":
            # Use custom JSON encoder to handle datetime and other non-serializable objects
            content = json.dumps(job.result, indent=2, cls=CustomJSONEncoder)
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
        
    except Exception as e:
        raise handle_route_exception(e, "download job result")


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
        job = get_job_by_id(job_id, db)
        
        if job.status in [JobStatus.COMPLETED, JobStatus.CANCELLED]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot cancel job with status: {job.status}"
            )
        
        # Update job status in queue
        await get_job_queue().update_job_status(job_id, JobStatus.CANCELLED)
        
        # Update job in database
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        
        return {'message': f'Job {job_id} cancelled successfully'}
        
    except Exception as e:
        db.rollback()
        raise handle_route_exception(e, "cancel job")


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
        jobs_data = []
        
        # Create job records in database (but don't commit yet)
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
                'config': job_request.config.model_dump(),
                'tags': job_request.tags or [],
                'priority': job_request.priority,
                'callback_url': str(job_request.callback_url) if job_request.callback_url else None
            }
            jobs_data.append(job_data)
            
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
                tags=job_request.tags or [],
                priority=job_request.priority,
                created_at=datetime.now(timezone.utc)
            )
            
            db.add(job)
        
        # Try to enqueue all jobs with proper cleanup on failure
        enqueued_job_ids = []
        try:
            for job_data in jobs_data:
                await get_job_queue().enqueue(job_data)
                enqueued_job_ids.append(job_data['job_id'])
            # Only commit if all enqueues succeed
            db.commit()
        except Exception as enqueue_error:
            # Clean up successfully enqueued jobs from queue
            for enqueued_job_id in enqueued_job_ids:
                try:
                    await get_job_queue().remove_job(enqueued_job_id)
                except Exception:
                    # Log cleanup failure but don't fail the operation
                    pass
            
            # Rollback database transaction
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to enqueue batch jobs: {str(enqueue_error)}"
            )
        
        return BulkScrapeResponse(
            batch_id=batch_id,
            job_ids=job_ids,
            total_jobs=len(job_ids),
            status="queued",
            created_at=datetime.now(timezone.utc)
        )
        
    except HTTPException:
        # Re-raise HTTPExceptions to preserve status code and detail
        raise
    except Exception as e:
        db.rollback()
        raise handle_route_exception(e, "create bulk scraping jobs")