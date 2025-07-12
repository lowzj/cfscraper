from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Boolean
from sqlalchemy.sql import func

from app.core.database import Base


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScraperType(str, Enum):
    CLOUDSCRAPER = "cloudscraper"
    SELENIUM = "selenium"


class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, index=True)
    status = Column(String, default=JobStatus.QUEUED)
    scraper_type = Column(String, default=ScraperType.CLOUDSCRAPER)
    
    # Job configuration
    url = Column(String, nullable=False)
    method = Column(String, default="GET")
    headers = Column(JSON, default=dict)
    data = Column(JSON, default=dict)
    params = Column(JSON, default=dict)
    
    # Job metadata
    tags = Column(JSON, default=list)
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Results
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Retry configuration
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Progress tracking
    progress = Column(Integer, default=0)  # 0-100
    progress_message = Column(String, nullable=True)
    
    def __repr__(self):
        return f"<Job(id={self.id}, task_id='{self.task_id}', status='{self.status}')>"


class JobResult(Base):
    __tablename__ = "job_results"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, index=True)
    task_id = Column(String, index=True)
    
    # Response data
    status_code = Column(Integer, nullable=True)
    response_headers = Column(JSON, nullable=True)
    response_content = Column(Text, nullable=True)
    
    # Metadata
    response_time = Column(Integer, nullable=True)  # milliseconds
    content_length = Column(Integer, nullable=True)
    content_type = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    
    def __repr__(self):
        return f"<JobResult(id={self.id}, job_id={self.job_id}, status_code={self.status_code})>"