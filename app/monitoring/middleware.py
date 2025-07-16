"""
Monitoring middleware for request tracking and metrics collection
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .logging import set_request_context, get_logger, StructuredLogger
from .metrics import record_request_metrics, update_app_uptime


class MonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware for monitoring requests and collecting metrics"""
    
    def __init__(self, app, start_time: float = None):
        super().__init__(app)
        self.start_time = start_time or time.time()
        self.logger = StructuredLogger(__name__)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with monitoring and logging"""
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        # Set request context for logging
        set_request_context(
            request_id=request_id,
            user_id=request.headers.get("x-user-id")
        )
        
        # Extract request information
        method = request.method
        url_path = request.url.path
        user_agent = request.headers.get("user-agent", "unknown")
        ip_address = request.client.host if request.client else "unknown"
        
        # Log request start
        self.logger.log_request_start(
            method=method,
            url=str(request.url),
            user_agent=user_agent,
            ip_address=ip_address
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate response time
            response_time = time.time() - start_time
            
            # Record metrics
            record_request_metrics(
                method=method,
                endpoint=url_path,
                status_code=response.status_code,
                duration=response_time
            )
            
            # Update app uptime
            update_app_uptime(self.start_time)
            
            # Log request completion
            self.logger.log_request_end(
                method=method,
                url=str(request.url),
                status_code=response.status_code,
                response_time=response_time
            )
            
            # Add monitoring headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{response_time:.3f}s"
            
            return response
            
        except Exception as e:
            # Calculate response time for failed requests
            response_time = time.time() - start_time
            
            # Record error metrics
            record_request_metrics(
                method=method,
                endpoint=url_path,
                status_code=500,
                duration=response_time
            )
            
            # Log error
            self.logger.log_error(
                error=e,
                context={
                    "method": method,
                    "url": str(request.url),
                    "response_time": response_time,
                    "user_agent": user_agent,
                    "ip_address": ip_address
                }
            )
            
            # Re-raise the exception
            raise


class MetricsCollectionMiddleware(BaseHTTPMiddleware):
    """Lightweight middleware focused only on metrics collection"""
    
    def __init__(self, app):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Collect metrics for requests"""
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Record successful request metrics
            response_time = time.time() - start_time
            record_request_metrics(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code,
                duration=response_time
            )
            
            return response
            
        except Exception as e:
            # Record failed request metrics
            response_time = time.time() - start_time
            record_request_metrics(
                method=request.method,
                endpoint=request.url.path,
                status_code=500,
                duration=response_time
            )
            
            raise
