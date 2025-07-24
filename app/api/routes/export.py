import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db_dependency
from app.models.job import Job
from app.utils.data_export import (
    DataExportManager, ExportConfig, ExportFormat, CompressionType
)

router = APIRouter()


class ExportRequest(BaseModel):
    """Request model for data export"""
    job_ids: Optional[List[str]] = Field(
        default=None,
        description="List of job IDs to export. If not provided, exports all jobs"
    )
    format: ExportFormat = Field(
        default=ExportFormat.JSON,
        description="Export format"
    )
    compression: CompressionType = Field(
        default=CompressionType.NONE,
        description="Compression type"
    )
    include_metadata: bool = Field(
        default=True,
        description="Include export metadata"
    )
    pretty_print: bool = Field(
        default=True,
        description="Pretty print output"
    )
    date_from: Optional[datetime] = Field(
        default=None,
        description="Export jobs from this date"
    )
    date_to: Optional[datetime] = Field(
        default=None,
        description="Export jobs until this date"
    )
    include_content: bool = Field(
        default=True,
        description="Include scraped content in export"
    )
    include_headers: bool = Field(
        default=False,
        description="Include response headers in export"
    )


class ExportResponse(BaseModel):
    """Response model for export operations"""
    export_id: str
    status: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    total_records: Optional[int] = None
    created_at: datetime
    download_url: Optional[str] = None


async def prepare_export_data(
        db: AsyncSession,
        job_ids: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        include_content: bool = True,
        include_headers: bool = False
) -> List[Dict[str, Any]]:
    """Prepare data for export from database"""

    # Build query
    query = select(Job)

    # Apply filters
    if job_ids:
        query = query.where(Job.task_id.in_(job_ids))

    if date_from:
        query = query.where(Job.created_at >= date_from)

    if date_to:
        query = query.where(Job.created_at <= date_to)

    # Execute query
    result = await db.execute(query)
    jobs = result.scalars().all()

    # Transform data for export
    export_data = []
    for job in jobs:
        job_data = {
            "job_id": job.task_id,
            "url": job.url,
            "method": job.method,
            "status": job.status.value,
            "scraper_type": job.scraper_type.value,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "max_retries": job.max_retries,
            "retry_count": job.retry_count,
        }

        # Add content if requested
        if include_content and job.result:
            result_data = job.result if isinstance(job.result, dict) else {}
            job_data["result"] = {
                "status_code": result_data.get("status_code"),
                "content": result_data.get("content"),
                "response_time": result_data.get("response_time"),
                "error": result_data.get("error"),
                "timestamp": result_data.get("timestamp")
            }

            # Add headers if requested
            if include_headers and result_data.get("headers"):
                job_data["result"]["headers"] = result_data.get("headers")

        # Add request parameters
        if job.headers:
            job_data["request_headers"] = job.headers
        if job.data:
            job_data["request_data"] = job.data
        if job.params:
            job_data["request_params"] = job.params

        export_data.append(job_data)

    return export_data


@router.post("/", response_model=ExportResponse)
async def export_data(
        request: ExportRequest,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_async_db_dependency)
):
    """
    Export scraping job data in various formats
    """
    try:
        # Prepare export data
        export_data = await prepare_export_data(
            db=db,
            job_ids=request.job_ids,
            date_from=request.date_from,
            date_to=request.date_to,
            include_content=request.include_content,
            include_headers=request.include_headers
        )

        if not export_data:
            raise HTTPException(status_code=404, detail="No data found for export")

        # Configure export manager
        config = ExportConfig(
            format=request.format,
            compression=request.compression,
            include_metadata=request.include_metadata,
            pretty_print=request.pretty_print
        )

        export_manager = DataExportManager(config)

        # Generate export file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_id = f"export_{timestamp}"

        # Create exports directory if it doesn't exist
        exports_dir = "exports"
        os.makedirs(exports_dir, exist_ok=True)

        # Export data
        output_path = await export_manager.export_data(
            data=export_data,
            output_path=os.path.join(exports_dir, f"{export_id}.{request.format.value}")
        )

        # Get file size
        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0

        return ExportResponse(
            export_id=export_id,
            status="completed",
            file_path=output_path,
            file_size=file_size,
            total_records=len(export_data),
            created_at=datetime.now(),
            download_url=f"/api/v1/export/download/{export_id}"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/download/{export_id}")
async def download_export(export_id: str):
    """
    Download exported file
    """
    try:
        # Find the export file
        exports_dir = "exports"
        export_files = []

        if os.path.exists(exports_dir):
            for filename in os.listdir(exports_dir):
                if filename.startswith(export_id):
                    export_files.append(os.path.join(exports_dir, filename))

        if not export_files:
            raise HTTPException(status_code=404, detail="Export file not found")

        # Get the most recent file if multiple exist
        export_file = max(export_files, key=os.path.getctime)

        if not os.path.exists(export_file):
            raise HTTPException(status_code=404, detail="Export file not found")

        # Determine media type based on file extension
        media_type_map = {
            '.json': 'application/json',
            '.csv': 'text/csv',
            '.xml': 'application/xml',
            '.jsonl': 'application/x-jsonlines',
            '.gz': 'application/gzip',
            '.zip': 'application/zip'
        }

        file_ext = None
        for ext in media_type_map.keys():
            if export_file.endswith(ext):
                file_ext = ext
                break

        media_type = media_type_map.get(file_ext, 'application/octet-stream')

        return FileResponse(
            path=export_file,
            media_type=media_type,
            filename=os.path.basename(export_file)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.get("/exports")
async def list_exports():
    """
    List available export files
    """
    try:
        exports_dir = "exports"
        exports = []

        if os.path.exists(exports_dir):
            for filename in os.listdir(exports_dir):
                file_path = os.path.join(exports_dir, filename)
                if os.path.isfile(file_path):
                    stat = os.stat(file_path)
                    exports.append({
                        "filename": filename,
                        "size": stat.st_size,
                        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "download_url": f"/api/v1/export/download/{filename.split('.')[0]}"
                    })

        return {"exports": exports}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list exports: {str(e)}")


@router.delete("/{export_id}")
async def delete_export(export_id: str):
    """
    Delete an export file
    """
    try:
        exports_dir = "exports"
        deleted_files = []

        if os.path.exists(exports_dir):
            for filename in os.listdir(exports_dir):
                if filename.startswith(export_id):
                    file_path = os.path.join(exports_dir, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        deleted_files.append(filename)

        if not deleted_files:
            raise HTTPException(status_code=404, detail="Export file not found")

        return {"message": f"Deleted {len(deleted_files)} file(s)", "files": deleted_files}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/formats")
async def get_export_formats():
    """
    Get available export formats and compression options
    """
    return {
        "formats": [format.value for format in ExportFormat],
        "compression_types": [comp.value for comp in CompressionType],
        "default_config": {
            "format": ExportFormat.JSON.value,
            "compression": CompressionType.NONE.value,
            "include_metadata": True,
            "pretty_print": True
        }
    }
