"""
Health check and monitoring endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
import time
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.database import get_async_db_dependency
from app.core.config import settings
from app.models.job import Job, JobStatus
from app.models.responses import HealthCheckResponse, DetailedHealthCheckResponse, MetricsResponse
from .common import get_job_queue
from app.monitoring.health import health_checker

# Try to import psutil for system metrics
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

router = APIRouter()

# Store application start time
_start_time = time.time()


@router.get("/", response_model=HealthCheckResponse)
async def health_check():
    """
    Basic health check endpoint
    
    Returns basic health status information including service status,
    version, and uptime.
    
    Returns:
        HealthCheckResponse with basic health information
    """
    try:
        uptime = time.time() - _start_time
        
        return HealthCheckResponse(
            status="healthy",
            version="1.0.0",
            timestamp=datetime.now(timezone.utc),
            uptime=uptime
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}"
        )


@router.get("/detailed", response_model=DetailedHealthCheckResponse)
async def detailed_health_check(db: AsyncSession = Depends(get_async_db_dependency)):
    """
    Detailed health check endpoint
    
    Returns comprehensive health status including component status,
    performance metrics, and system information.
    
    Returns:
        DetailedHealthCheckResponse with detailed health information
    """
    try:
        uptime = time.time() - _start_time
        components = {}
        metrics = {}
        overall_status = "healthy"
        
        # Check database connection
        try:
            start_time = time.time()
            result = await db.execute(text("SELECT 1"))
            row = result.fetchone()
            db_response_time = time.time() - start_time
            
            components["database"] = {
                "status": "healthy" if row else "unhealthy",
                "response_time": db_response_time,
                "last_check": datetime.now(timezone.utc).isoformat()
            }
            
            if not row:
                overall_status = "unhealthy"
                
        except Exception as e:
            components["database"] = {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.now(timezone.utc).isoformat()
            }
            overall_status = "unhealthy"
        
        # Check Redis/Queue connection
        try:
            job_queue = get_job_queue()
            start_time = time.time()
            queue_size = await get_job_queue().get_queue_size()
            queue_response_time = time.time() - start_time
            
            components["queue"] = {
                "status": "healthy",
                "response_time": queue_response_time,
                "queue_size": queue_size,
                "last_check": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            components["queue"] = {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.now(timezone.utc).isoformat()
            }
            # Don't mark as unhealthy if using in-memory queue
            if "redis" in str(e).lower():
                overall_status = "degraded"
        
        # Check scrapers availability
        try:
            scrapers_status = {}
            
            # Check CloudScraper
            try:
                import cloudscraper
                scrapers_status["cloudscraper"] = "available"
            except ImportError:
                scrapers_status["cloudscraper"] = "unavailable"
            
            # Check Selenium
            try:
                import seleniumbase
                scrapers_status["selenium"] = "available"
            except ImportError:
                scrapers_status["selenium"] = "unavailable"
            
            components["scrapers"] = {
                "status": "healthy" if any(s == "available" for s in scrapers_status.values()) else "unhealthy",
                **scrapers_status
            }
            
            if not any(s == "available" for s in scrapers_status.values()):
                overall_status = "unhealthy"
                
        except Exception as e:
            components["scrapers"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            overall_status = "unhealthy"
        
        # Get job metrics
        try:
            from sqlalchemy import select, func
            
            # Get job counts
            total_jobs_result = await db.execute(select(func.count()).select_from(Job))
            total_jobs = total_jobs_result.scalar()
            
            active_jobs_result = await db.execute(select(func.count()).select_from(Job).where(Job.status == JobStatus.RUNNING))
            active_jobs = active_jobs_result.scalar()
            
            completed_jobs_result = await db.execute(select(func.count()).select_from(Job).where(Job.status == JobStatus.COMPLETED))
            completed_jobs = completed_jobs_result.scalar()
            
            failed_jobs_result = await db.execute(select(func.count()).select_from(Job).where(Job.status == JobStatus.FAILED))
            failed_jobs = failed_jobs_result.scalar()
            
            # Get recent jobs for response time calculation
            recent_jobs_result = await db.execute(
                select(Job).where(
                    Job.completed_at >= datetime.now(timezone.utc) - timedelta(hours=1),
                    Job.status == JobStatus.COMPLETED,
                    Job.result.isnot(None)
                )
            )
            recent_jobs = recent_jobs_result.scalars().all()
            
            avg_response_time = 0
            if recent_jobs:
                response_times = [
                    job.result.get('response_time', 0) 
                    for job in recent_jobs 
                    if job.result and job.result.get('response_time')
                ]
                if response_times:
                    avg_response_time = sum(response_times) / len(response_times)
            
            metrics = {
                "total_jobs": total_jobs,
                "active_jobs": active_jobs,
                "completed_jobs": completed_jobs,
                "failed_jobs": failed_jobs,
                "queue_size": await get_job_queue().get_queue_size(),
                "average_response_time": avg_response_time
            }
            
        except Exception as e:
            metrics = {
                "error": f"Failed to get metrics: {str(e)}"
            }
        
        return DetailedHealthCheckResponse(
            status=overall_status,
            version="1.0.0",
            timestamp=datetime.now(timezone.utc),
            uptime=uptime,
            components=components,
            metrics=metrics
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Detailed health check failed: {str(e)}"
        )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(db: AsyncSession = Depends(get_async_db_dependency)):
    """
    Get system and application metrics
    
    Returns comprehensive metrics including job statistics, performance data,
    and system resource usage.
    
    Returns:
        MetricsResponse with detailed metrics
    """
    try:
        from sqlalchemy import select, func
        
        job_queue = get_job_queue()
        
        # Job statistics
        jobs_stats = {}
        for status in JobStatus:
            result = await db.execute(select(func.count()).select_from(Job).where(Job.status == status))
            jobs_stats[status.value] = result.scalar()
        
        # Performance metrics
        completed_jobs_result = await db.execute(
            select(Job).where(
                Job.status == JobStatus.COMPLETED,
                Job.completed_at >= datetime.now(timezone.utc) - timedelta(hours=24)
            )
        )
        completed_jobs = completed_jobs_result.scalars().all()
        
        performance_metrics = {
            "average_response_time": 0,
            "median_response_time": 0,
            "success_rate": 0,
            "throughput_per_hour": 0
        }
        
        if completed_jobs:
            response_times = [
                job.result.get('response_time', 0) 
                for job in completed_jobs 
                if job.result and job.result.get('response_time')
            ]
            
            if response_times:
                performance_metrics["average_response_time"] = sum(response_times) / len(response_times)
                response_times.sort()
                n = len(response_times)
                performance_metrics["median_response_time"] = (
                    response_times[n // 2] if n % 2 == 1 
                    else (response_times[n // 2 - 1] + response_times[n // 2]) / 2
                )
            
            total_jobs_24h_result = await db.execute(
                select(func.count()).select_from(Job).where(
                    Job.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
                )
            )
            total_jobs_24h = total_jobs_24h_result.scalar()
            
            if total_jobs_24h > 0:
                performance_metrics["success_rate"] = len(completed_jobs) / total_jobs_24h
            
            performance_metrics["throughput_per_hour"] = len(completed_jobs) / 24
        
        # System metrics
        system_metrics = {}
        if HAS_PSUTIL:
            try:
                system_metrics = {
                    "cpu_usage": psutil.cpu_percent(interval=1),
                    "memory_usage": psutil.virtual_memory().percent / 100,
                    "disk_usage": psutil.disk_usage('/').percent / 100,
                    "network_io": {
                        "bytes_sent": psutil.net_io_counters().bytes_sent,
                        "bytes_recv": psutil.net_io_counters().bytes_recv
                    }
                }
            except Exception as e:
                system_metrics = {
                    "error": f"Failed to get system metrics: {str(e)}"
                }
        else:
            system_metrics = {
                "cpu_usage": 0,
                "memory_usage": 0,
                "disk_usage": 0,
                "note": "System metrics unavailable (psutil not installed)"
            }
        
        # Hourly statistics (last 24 hours)
        hourly_stats = {}
        for i in range(24):
            hour_start = datetime.now(timezone.utc) - timedelta(hours=i+1)
            hour_end = datetime.now(timezone.utc) - timedelta(hours=i)
            
            result = await db.execute(
                select(func.count()).select_from(Job).where(
                    Job.created_at >= hour_start,
                    Job.created_at < hour_end
                )
            )
            count = result.scalar()
            
            hourly_stats[hour_start.strftime('%Y-%m-%dT%H:00:00Z')] = count
        
        # Daily statistics (last 7 days)
        daily_stats = {}
        for i in range(7):
            day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            
            result = await db.execute(
                select(func.count()).select_from(Job).where(
                    Job.created_at >= day_start,
                    Job.created_at < day_end
                )
            )
            count = result.scalar()
            
            daily_stats[day_start.strftime('%Y-%m-%d')] = count
        
        return MetricsResponse(
            jobs=jobs_stats,
            performance=performance_metrics,
            system=system_metrics,
            hourly_stats=hourly_stats,
            daily_stats=daily_stats,
            timestamp=datetime.now(timezone.utc)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get metrics: {str(e)}"
        )


@router.get("/status")
async def get_service_status(db: AsyncSession = Depends(get_async_db_dependency)):
    """
    Get service status summary
    
    Returns a summary of the service status including version, uptime,
    and key operational metrics.
    
    Returns:
        Service status summary
    """
    try:
        from sqlalchemy import select, func
        
        job_queue = get_job_queue()
        
        # Basic service info
        uptime = time.time() - _start_time
        
        # Get queue status
        queue_size = await job_queue.get_queue_size()
        
        # Get job counts
        total_jobs_result = await db.execute(select(func.count()).select_from(Job))
        total_jobs = total_jobs_result.scalar()
        
        running_jobs_result = await db.execute(select(func.count()).select_from(Job).where(Job.status == JobStatus.RUNNING))
        running_jobs = running_jobs_result.scalar()
        
        # Get recent activity
        recent_jobs_result = await db.execute(
            select(func.count()).select_from(Job).where(
                Job.created_at >= datetime.now(timezone.utc) - timedelta(hours=1)
            )
        )
        recent_jobs = recent_jobs_result.scalar()
        
        return {
            "service": "CFScraper API",
            "version": "1.0.0",
            "status": "running",
            "uptime": uptime,
            "uptime_human": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
            "queue_size": queue_size,
            "total_jobs": total_jobs,
            "running_jobs": running_jobs,
            "recent_activity": recent_jobs,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get service status: {str(e)}"
        )


@router.get("/ping")
async def ping():
    """
    Simple ping endpoint

    Returns a simple pong response to verify the service is responding.

    Returns:
        Pong response
    """
    return {
        "message": "pong",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/ready")
async def readiness_check():
    """
    Kubernetes readiness probe endpoint

    Returns readiness status for the application. This endpoint should
    return 200 when the application is ready to serve traffic.

    Returns:
        Readiness status
    """
    try:
        result = await health_checker.get_readiness()

        if result["ready"]:
            return result
        else:
            raise HTTPException(
                status_code=503,
                detail=result
            )

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


@router.get("/live")
async def liveness_check():
    """
    Kubernetes liveness probe endpoint

    Returns liveness status for the application. This endpoint should
    return 200 when the application is alive and running.

    Returns:
        Liveness status
    """
    try:
        result = await health_checker.get_basic_health()
        return result

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )