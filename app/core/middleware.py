"""
Global exception handlers for the CFScraper API
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

from app.core.exceptions import CFScraperException
from app.models.responses import ErrorResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cfscraper_exception_handler(request: Request, exc: CFScraperException) -> JSONResponse:
    """
    Handle custom CFScraper exceptions
    
    Args:
        request: The incoming request
        exc: The CFScraper exception
        
    Returns:
        JSONResponse with error details
    """
    request_id = str(uuid.uuid4())
    
    # Log the error
    logger.error(
        f"CFScraper error occurred: {exc.error_code} - {exc.message}",
        extra={
            "request_id": request_id,
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "details": exc.details,
            "url": str(request.url),
            "method": request.method,
            "user_agent": request.headers.get("user-agent", "unknown")
        }
    )
    
    # Create error response
    error_response = ErrorResponse(
        error=exc.error_code,
        message=exc.message,
        details=exc.details,
        timestamp=datetime.now(timezone.utc),
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(mode='json')
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle FastAPI HTTP exceptions
    
    Args:
        request: The incoming request
        exc: The HTTP exception
        
    Returns:
        JSONResponse with error details
    """
    request_id = str(uuid.uuid4())
    
    # Log the error
    logger.warning(
        f"HTTP error occurred: {exc.status_code} - {exc.detail}",
        extra={
            "request_id": request_id,
            "status_code": exc.status_code,
            "url": str(request.url),
            "method": request.method,
            "user_agent": request.headers.get("user-agent", "unknown")
        }
    )
    
    # Create error response
    error_response = ErrorResponse(
        error="HTTPException",
        message=str(exc.detail),
        details={"status_code": exc.status_code},
        timestamp=datetime.now(timezone.utc),
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(mode='json')
    )


async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """
    Handle Pydantic validation errors
    
    Args:
        request: The incoming request
        exc: The validation error
        
    Returns:
        JSONResponse with validation error details
    """
    request_id = str(uuid.uuid4())
    
    # Extract validation error details
    errors = []
    for error in exc.errors():
        error_dict = {
            "field": " -> ".join(str(x) for x in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        }
        if "input" in error:
            error_dict["input"] = error["input"]
        errors.append(error_dict)
    
    # Log the error
    logger.warning(
        f"Validation error occurred: {len(errors)} validation errors",
        extra={
            "request_id": request_id,
            "errors": errors,
            "url": str(request.url),
            "method": request.method,
            "user_agent": request.headers.get("user-agent", "unknown")
        }
    )
    
    # Create error response
    error_response = ErrorResponse(
        error="ValidationError",
        message=f"Request validation failed with {len(errors)} error(s)",
        details={"validation_errors": errors},
        timestamp=datetime.now(timezone.utc),
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=422,
        content=error_response.model_dump(mode='json')
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions
    
    Args:
        request: The incoming request
        exc: The unexpected exception
        
    Returns:
        JSONResponse with generic error message
    """
    request_id = str(uuid.uuid4())
    
    # Log the error
    logger.error(
        f"Unexpected error occurred: {type(exc).__name__} - {str(exc)}",
        extra={
            "request_id": request_id,
            "exception_type": type(exc).__name__,
            "url": str(request.url),
            "method": request.method,
            "user_agent": request.headers.get("user-agent", "unknown")
        },
        exc_info=True
    )
    
    # Create error response (don't expose internal details)
    error_response = ErrorResponse(
        error="InternalServerError",
        message="An unexpected error occurred",
        details={"error_type": type(exc).__name__},
        timestamp=datetime.now(timezone.utc),
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=500,
        content=error_response.model_dump(mode='json')
    )


def setup_exception_handlers(app):
    """
    Setup exception handlers for the FastAPI app
    
    Args:
        app: The FastAPI application instance
    """
    # Custom exception handlers
    app.add_exception_handler(CFScraperException, cfscraper_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    
    logger.info("Exception handlers registered successfully")


# Request logging middleware
async def log_requests(request: Request, call_next):
    """
    Log incoming requests and responses
    
    Args:
        request: The incoming request
        call_next: The next middleware/handler
        
    Returns:
        Response with added logging
    """
    start_time = datetime.now(timezone.utc)
    request_id = str(uuid.uuid4())
    
    # Log request
    logger.info(
        f"Request started: {request.method} {request.url.path}",
        extra={
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "user_agent": request.headers.get("user-agent", "unknown"),
            "ip": request.client.host if request.client else "unknown"
        }
    )
    
    # Process request
    try:
        response = await call_next(request)
        
        # Calculate response time
        end_time = datetime.now(timezone.utc)
        response_time = (end_time - start_time).total_seconds()
        
        # Log response
        logger.info(
            f"Request completed: {request.method} {request.url.path} - {response.status_code}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
                "status_code": response.status_code,
                "response_time": response_time,
                "user_agent": request.headers.get("user-agent", "unknown"),
                "ip": request.client.host if request.client else "unknown"
            }
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
        
    except Exception as e:
        # Calculate response time
        end_time = datetime.now(timezone.utc)
        response_time = (end_time - start_time).total_seconds()
        
        # Log error
        logger.error(
            f"Request failed: {request.method} {request.url.path} - {type(e).__name__}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
                "error": str(e),
                "response_time": response_time,
                "user_agent": request.headers.get("user-agent", "unknown"),
                "ip": request.client.host if request.client else "unknown"
            },
            exc_info=True
        )
        
        # Re-raise the exception to let other handlers deal with it
        raise