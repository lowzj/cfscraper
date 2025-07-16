"""
Structured JSON logging for CFScraper API
"""

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from contextvars import ContextVar

import structlog
from structlog.stdlib import LoggerFactory
from structlog.processors import JSONRenderer, TimeStamper, add_log_level, StackInfoRenderer

# Context variables for request correlation
request_id_context: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
user_id_context: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
job_id_context: ContextVar[Optional[str]] = ContextVar('job_id', default=None)


def add_correlation_id(logger, method_name, event_dict):
    """Add correlation IDs to log entries"""
    request_id = request_id_context.get()
    if request_id:
        event_dict['request_id'] = request_id
    
    user_id = user_id_context.get()
    if user_id:
        event_dict['user_id'] = user_id
    
    job_id = job_id_context.get()
    if job_id:
        event_dict['job_id'] = job_id
    
    return event_dict


def add_service_info(logger, method_name, event_dict):
    """Add service information to log entries"""
    event_dict['service'] = 'cfscraper-api'
    event_dict['version'] = '1.0.0'
    return event_dict


def add_timestamp_iso(logger, method_name, event_dict):
    """Add ISO timestamp to log entries"""
    event_dict['timestamp'] = datetime.now(timezone.utc).isoformat()
    return event_dict


def setup_structured_logging(log_level: str = "INFO", enable_json: bool = True):
    """
    Setup structured logging with JSON format
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_json: Whether to use JSON format
    """
    # Configure structlog
    processors = [
        add_correlation_id,
        add_service_info,
        add_timestamp_iso,
        add_log_level,
        StackInfoRenderer(),
    ]
    
    if enable_json:
        processors.append(JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper())
    )
    
    # Set log levels for noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance
    
    Args:
        name: Logger name (defaults to calling module)
    
    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


def log_with_context(
    logger: structlog.stdlib.BoundLogger,
    level: str,
    message: str,
    **kwargs
) -> None:
    """
    Log a message with additional context
    
    Args:
        logger: Logger instance
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        **kwargs: Additional context fields
    """
    log_method = getattr(logger, level.lower())
    log_method(message, **kwargs)


class RequestContextMiddleware:
    """Middleware to set request context for logging"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Generate request ID
            request_id = str(uuid.uuid4())
            request_id_context.set(request_id)
            
            # Extract user ID from headers if available
            headers = dict(scope.get("headers", []))
            user_id = headers.get(b"x-user-id")
            if user_id:
                user_id_context.set(user_id.decode())
        
        await self.app(scope, receive, send)


def set_request_context(request_id: str, user_id: Optional[str] = None):
    """
    Set request context for logging
    
    Args:
        request_id: Request identifier
        user_id: User identifier (optional)
    """
    request_id_context.set(request_id)
    if user_id:
        user_id_context.set(user_id)


def set_job_context(job_id: str):
    """
    Set job context for logging
    
    Args:
        job_id: Job identifier
    """
    job_id_context.set(job_id)


def clear_context():
    """Clear all logging context"""
    request_id_context.set(None)
    user_id_context.set(None)
    job_id_context.set(None)


class StructuredLogger:
    """Enhanced structured logger with common patterns"""
    
    def __init__(self, name: str = None):
        self.logger = get_logger(name)
    
    def log_request_start(
        self,
        method: str,
        url: str,
        user_agent: str = None,
        ip_address: str = None,
        **kwargs
    ):
        """Log request start"""
        self.logger.info(
            "Request started",
            method=method,
            url=url,
            user_agent=user_agent,
            ip_address=ip_address,
            **kwargs
        )
    
    def log_request_end(
        self,
        method: str,
        url: str,
        status_code: int,
        response_time: float,
        **kwargs
    ):
        """Log request completion"""
        self.logger.info(
            "Request completed",
            method=method,
            url=url,
            status_code=status_code,
            response_time=response_time,
            **kwargs
        )
    
    def log_job_start(self, job_id: str, job_type: str, **kwargs):
        """Log job start"""
        set_job_context(job_id)
        self.logger.info(
            "Job started",
            job_id=job_id,
            job_type=job_type,
            **kwargs
        )
    
    def log_job_end(
        self,
        job_id: str,
        job_type: str,
        status: str,
        duration: float,
        **kwargs
    ):
        """Log job completion"""
        self.logger.info(
            "Job completed",
            job_id=job_id,
            job_type=job_type,
            status=status,
            duration=duration,
            **kwargs
        )
    
    def log_scraper_request(
        self,
        scraper_type: str,
        url: str,
        status: str,
        response_time: float = None,
        **kwargs
    ):
        """Log scraper request"""
        self.logger.info(
            "Scraper request",
            scraper_type=scraper_type,
            url=url,
            status=status,
            response_time=response_time,
            **kwargs
        )
    
    def log_proxy_usage(
        self,
        proxy_id: str,
        url: str,
        status: str,
        response_time: float = None,
        **kwargs
    ):
        """Log proxy usage"""
        self.logger.info(
            "Proxy request",
            proxy_id=proxy_id,
            url=url,
            status=status,
            response_time=response_time,
            **kwargs
        )
    
    def log_webhook_delivery(
        self,
        webhook_url: str,
        status: str,
        duration: float = None,
        **kwargs
    ):
        """Log webhook delivery"""
        self.logger.info(
            "Webhook delivery",
            webhook_url=webhook_url,
            status=status,
            duration=duration,
            **kwargs
        )
    
    def log_error(self, error: Exception, context: Dict[str, Any] = None, **kwargs):
        """Log error with context"""
        error_context = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            **(context or {}),
            **kwargs
        }
        
        self.logger.error(
            "Error occurred",
            **error_context,
            exc_info=True
        )
    
    def log_security_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        **kwargs
    ):
        """Log security-related events"""
        self.logger.warning(
            "Security event",
            event_type=event_type,
            severity=severity,
            description=description,
            **kwargs
        )
    
    def log_performance_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "seconds",
        **kwargs
    ):
        """Log performance metrics"""
        self.logger.info(
            "Performance metric",
            metric_name=metric_name,
            value=value,
            unit=unit,
            **kwargs
        )


# Global logger instance
logger = StructuredLogger(__name__)
