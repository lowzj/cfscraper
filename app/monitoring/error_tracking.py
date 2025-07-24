"""
Error tracking and notification system using Sentry
"""

import logging
import os
from functools import wraps
from typing import Dict, Any, Optional, List

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration


def setup_sentry(
        dsn: Optional[str] = None,
        environment: str = "development",
        release: Optional[str] = None,
        sample_rate: float = 1.0,
        traces_sample_rate: float = 0.1,
        profiles_sample_rate: float = 0.1,
        enable_tracing: bool = True
):
    """
    Setup Sentry error tracking
    
    Args:
        dsn: Sentry DSN
        environment: Environment name
        release: Release version
        sample_rate: Error sampling rate (0.0 to 1.0)
        traces_sample_rate: Performance monitoring sampling rate
        profiles_sample_rate: Profiling sampling rate
        enable_tracing: Enable performance monitoring
    """
    if not dsn:
        dsn = os.getenv("SENTRY_DSN")

    if not dsn:
        logging.warning("Sentry DSN not provided, error tracking disabled")
        return

    # Setup integrations
    integrations = [
        FastApiIntegration(auto_enabling_integrations=False),
        SqlalchemyIntegration(),
        RedisIntegration(),
        HttpxIntegration(),
        LoggingIntegration(
            level=logging.INFO,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR  # Send errors as events
        ),
    ]

    # Initialize Sentry
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or os.getenv("SENTRY_RELEASE", "1.0.0"),
        sample_rate=sample_rate,
        traces_sample_rate=traces_sample_rate if enable_tracing else 0.0,
        profiles_sample_rate=profiles_sample_rate if enable_tracing else 0.0,
        integrations=integrations,
        send_default_pii=False,  # Don't send personally identifiable information
        attach_stacktrace=True,
        before_send=before_send_filter,
        before_send_transaction=before_send_transaction_filter,
    )


def before_send_filter(event, hint):
    """
    Filter events before sending to Sentry
    
    Args:
        event: Sentry event
        hint: Event hint with additional context
        
    Returns:
        Modified event or None to drop
    """
    # Don't send health check errors
    if event.get("request", {}).get("url", "").endswith(("/health", "/ping", "/metrics")):
        return None

    # Don't send rate limit errors
    if "rate limit" in str(event.get("exception", {}).get("values", [{}])[0].get("value", "")).lower():
        return None

    return event


def before_send_transaction_filter(event, hint):
    """
    Filter transactions before sending to Sentry
    
    Args:
        event: Sentry transaction event
        hint: Event hint with additional context
        
    Returns:
        Modified event or None to drop
    """
    # Don't send health check transactions
    transaction_name = event.get("transaction", "")
    if any(path in transaction_name for path in ["/health", "/ping", "/metrics"]):
        return None

    return event


def capture_exception(
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None,
        level: str = "error",
        fingerprint: Optional[List[str]] = None
):
    """
    Capture an exception with additional context
    
    Args:
        error: Exception to capture
        context: Additional context information
        tags: Tags to add to the event
        level: Error level (debug, info, warning, error, fatal)
        fingerprint: Custom fingerprint for grouping
    """
    with sentry_sdk.push_scope() as scope:
        # Set level
        scope.level = level

        # Add context
        if context:
            for key, value in context.items():
                scope.set_context(key, value)

        # Add tags
        if tags:
            for key, value in tags.items():
                scope.set_tag(key, value)

        # Set fingerprint for custom grouping
        if fingerprint:
            scope.fingerprint = fingerprint

        # Capture the exception
        sentry_sdk.capture_exception(error)


def capture_message(
        message: str,
        level: str = "info",
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None
):
    """
    Capture a message with additional context
    
    Args:
        message: Message to capture
        level: Message level (debug, info, warning, error, fatal)
        context: Additional context information
        tags: Tags to add to the event
    """
    with sentry_sdk.push_scope() as scope:
        # Set level
        scope.level = level

        # Add context
        if context:
            for key, value in context.items():
                scope.set_context(key, value)

        # Add tags
        if tags:
            for key, value in tags.items():
                scope.set_tag(key, value)

        # Capture the message
        sentry_sdk.capture_message(message)


def set_user_context(user_id: str, email: Optional[str] = None, username: Optional[str] = None):
    """
    Set user context for error tracking
    
    Args:
        user_id: User identifier
        email: User email
        username: Username
    """
    sentry_sdk.set_user({
        "id": user_id,
        "email": email,
        "username": username
    })


def set_request_context(
        request_id: str,
        method: str,
        url: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
):
    """
    Set request context for error tracking
    
    Args:
        request_id: Request identifier
        method: HTTP method
        url: Request URL
        user_agent: User agent string
        ip_address: Client IP address
    """
    sentry_sdk.set_context("request", {
        "request_id": request_id,
        "method": method,
        "url": url,
        "user_agent": user_agent,
        "ip_address": ip_address
    })


def set_job_context(job_id: str, job_type: str, status: Optional[str] = None):
    """
    Set job context for error tracking
    
    Args:
        job_id: Job identifier
        job_type: Type of job
        status: Job status
    """
    sentry_sdk.set_context("job", {
        "job_id": job_id,
        "job_type": job_type,
        "status": status
    })


def add_breadcrumb(
        message: str,
        category: str = "custom",
        level: str = "info",
        data: Optional[Dict[str, Any]] = None
):
    """
    Add a breadcrumb for debugging context
    
    Args:
        message: Breadcrumb message
        category: Breadcrumb category
        level: Breadcrumb level
        data: Additional data
    """
    sentry_sdk.add_breadcrumb(
        message=message,
        category=category,
        level=level,
        data=data or {}
    )


def sentry_trace(operation_name: str = None, tags: Optional[Dict[str, str]] = None):
    """
    Decorator to trace function execution with Sentry
    
    Args:
        operation_name: Name of the operation (defaults to function name)
        tags: Tags to add to the transaction
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"

            with sentry_sdk.start_transaction(op=op_name, name=op_name) as transaction:
                # Add tags
                if tags:
                    for key, value in tags.items():
                        transaction.set_tag(key, value)

                try:
                    result = func(*args, **kwargs)
                    transaction.set_tag("success", True)
                    return result
                except Exception as e:
                    transaction.set_tag("success", False)
                    transaction.set_tag("error.type", type(e).__name__)
                    capture_exception(e, context={"function": op_name})
                    raise

        return wrapper

    return decorator


def sentry_trace_async(operation_name: str = None, tags: Optional[Dict[str, str]] = None):
    """
    Decorator to trace async function execution with Sentry
    
    Args:
        operation_name: Name of the operation (defaults to function name)
        tags: Tags to add to the transaction
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"

            with sentry_sdk.start_transaction(op=op_name, name=op_name) as transaction:
                # Add tags
                if tags:
                    for key, value in tags.items():
                        transaction.set_tag(key, value)

                try:
                    result = await func(*args, **kwargs)
                    transaction.set_tag("success", True)
                    return result
                except Exception as e:
                    transaction.set_tag("success", False)
                    transaction.set_tag("error.type", type(e).__name__)
                    capture_exception(e, context={"function": op_name})
                    raise

        return wrapper

    return decorator


class ErrorTracker:
    """High-level error tracking interface"""

    @staticmethod
    def setup_from_env():
        """Setup error tracking from environment variables"""
        dsn = os.getenv("SENTRY_DSN")
        environment = os.getenv("SENTRY_ENVIRONMENT", "development")
        release = os.getenv("SENTRY_RELEASE", "1.0.0")
        sample_rate = float(os.getenv("SENTRY_SAMPLE_RATE", "1.0"))
        traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

        if dsn:
            setup_sentry(
                dsn=dsn,
                environment=environment,
                release=release,
                sample_rate=sample_rate,
                traces_sample_rate=traces_sample_rate
            )

    @staticmethod
    def capture_job_error(job_id: str, job_type: str, error: Exception, context: Dict[str, Any] = None):
        """Capture job-related error"""
        set_job_context(job_id, job_type, "failed")
        capture_exception(
            error,
            context=context,
            tags={"component": "job_processor", "job_type": job_type},
            fingerprint=[f"job-error-{job_type}", str(type(error).__name__)]
        )

    @staticmethod
    def capture_scraper_error(scraper_type: str, url: str, error: Exception, context: Dict[str, Any] = None):
        """Capture scraper-related error"""
        capture_exception(
            error,
            context={**(context or {}), "scraper_type": scraper_type, "url": url},
            tags={"component": "scraper", "scraper_type": scraper_type},
            fingerprint=[f"scraper-error-{scraper_type}", str(type(error).__name__)]
        )

    @staticmethod
    def capture_webhook_error(webhook_url: str, error: Exception, context: Dict[str, Any] = None):
        """Capture webhook-related error"""
        capture_exception(
            error,
            context={**(context or {}), "webhook_url": webhook_url},
            tags={"component": "webhook", "webhook_url": webhook_url},
            fingerprint=["webhook-error", str(type(error).__name__)]
        )


# Global error tracker instance
error_tracker = ErrorTracker()
