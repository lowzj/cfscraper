"""
Custom exception classes for the CFScraper API
"""
from typing import Optional, Dict, Any


class CFScraperException(Exception):
    """Base exception for CFScraper API"""

    def __init__(
            self,
            message: str,
            status_code: int = 500,
            error_code: Optional[str] = None,
            details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(CFScraperException):
    """Raised when input validation fails"""

    def __init__(self, message: str, field: Optional[str] = None, value: Optional[Any] = None):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = value
        super().__init__(
            message=message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=details
        )


class JobNotFoundError(CFScraperException):
    """Raised when a job is not found"""

    def __init__(self, job_id: str):
        super().__init__(
            message=f"Job with ID '{job_id}' not found",
            status_code=404,
            error_code="JOB_NOT_FOUND",
            details={"job_id": job_id}
        )


class JobStateError(CFScraperException):
    """Raised when a job operation is invalid for the current state"""

    def __init__(self, job_id: str, current_state: str, operation: str):
        super().__init__(
            message=f"Cannot {operation} job '{job_id}' in state '{current_state}'",
            status_code=400,
            error_code="INVALID_JOB_STATE",
            details={
                "job_id": job_id,
                "current_state": current_state,
                "operation": operation
            }
        )


class ScraperError(CFScraperException):
    """Raised when scraper encounters an error"""

    def __init__(self, message: str, scraper_type: str, url: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="SCRAPER_ERROR",
            details={
                "scraper_type": scraper_type,
                "url": url
            }
        )


class ConfigurationError(CFScraperException):
    """Raised when there's a configuration error"""

    def __init__(self, message: str, component: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="CONFIGURATION_ERROR",
            details={"component": component} if component else {}
        )


class DatabaseError(CFScraperException):
    """Raised when database operations fail"""

    def __init__(self, message: str, operation: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="DATABASE_ERROR",
            details={"operation": operation} if operation else {}
        )


class QueueError(CFScraperException):
    """Raised when queue operations fail"""

    def __init__(self, message: str, operation: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="QUEUE_ERROR",
            details={"operation": operation} if operation else {}
        )


class RateLimitError(CFScraperException):
    """Raised when rate limits are exceeded"""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(
            message=message,
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
            details={"retry_after": retry_after} if retry_after else {}
        )


class AuthenticationError(CFScraperException):
    """Raised when authentication fails"""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_ERROR"
        )


class AuthorizationError(CFScraperException):
    """Raised when authorization fails"""

    def __init__(self, message: str = "Access denied"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="AUTHORIZATION_ERROR"
        )


class ResourceNotFoundError(CFScraperException):
    """Raised when a resource is not found"""

    def __init__(self, resource_type: str, identifier: str):
        super().__init__(
            message=f"{resource_type} '{identifier}' not found",
            status_code=404,
            error_code="RESOURCE_NOT_FOUND",
            details={
                "resource_type": resource_type,
                "identifier": identifier
            }
        )


class ServiceUnavailableError(CFScraperException):
    """Raised when a service is unavailable"""

    def __init__(self, service: str, message: Optional[str] = None):
        super().__init__(
            message=message or f"Service '{service}' is currently unavailable",
            status_code=503,
            error_code="SERVICE_UNAVAILABLE",
            details={"service": service}
        )


class TimeoutError(CFScraperException):
    """Raised when operations timeout"""

    def __init__(self, operation: str, timeout: int):
        super().__init__(
            message=f"Operation '{operation}' timed out after {timeout} seconds",
            status_code=408,
            error_code="TIMEOUT_ERROR",
            details={
                "operation": operation,
                "timeout": timeout
            }
        )


class NetworkError(CFScraperException):
    """Raised when network operations fail"""

    def __init__(self, message: str, url: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(
            message=message,
            status_code=502,
            error_code="NETWORK_ERROR",
            details={
                "url": url,
                "http_status": status_code
            }
        )


class CloudflareError(CFScraperException):
    """Raised when Cloudflare bypass fails"""

    def __init__(self, message: str, url: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=403,
            error_code="CLOUDFLARE_ERROR",
            details={"url": url} if url else {}
        )


class BrowserError(CFScraperException):
    """Raised when browser operations fail"""

    def __init__(self, message: str, browser_type: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="BROWSER_ERROR",
            details={"browser_type": browser_type} if browser_type else {}
        )


class ContentExtractionError(CFScraperException):
    """Raised when content extraction fails"""

    def __init__(self, message: str, content_type: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="CONTENT_EXTRACTION_ERROR",
            details={"content_type": content_type} if content_type else {}
        )
