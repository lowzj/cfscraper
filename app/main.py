import time
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db
from app.core.middleware import setup_exception_handlers, log_requests
from app.core.rate_limit_middleware import RateLimitMiddleware, setup_rate_limiting, RateLimitConfig
from app.utils.proxy_manager import initialize_proxy_system, shutdown_proxy_system
from app.utils.stealth_manager import initialize_stealth_system
from app.utils.rate_limiter import initialize_rate_limiting
from app.utils.webhooks import initialize_webhook_system, shutdown_webhook_system

# Import monitoring components
from app.monitoring import (
    setup_metrics,
    setup_structured_logging,
    setup_health_checks,
    get_metrics_handler
)
from app.monitoring.middleware import MonitoringMiddleware
from app.monitoring.apm import setup_apm_instrumentation
from app.monitoring.error_tracking import ErrorTracker

# Import security components
from app.security.headers import SecurityHeadersMiddleware
from app.security.audit import AuditMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up cfscraper API...")

    # Setup error tracking first
    ErrorTracker.setup_from_env()

    # Setup monitoring and logging
    setup_structured_logging(log_level="INFO", enable_json=True)
    setup_metrics(app_version="1.0.0", app_name="CFScraper API")
    setup_health_checks()

    init_db()  # Initialize database tables

    # Setup APM instrumentation
    from app.core.database import engine
    setup_apm_instrumentation(app, engine)

    await initialize_proxy_system()  # Initialize proxy rotation system
    await initialize_stealth_system()  # Initialize stealth features
    await initialize_rate_limiting()  # Initialize rate limiting
    await initialize_webhook_system()  # Initialize webhook system

    print("CFScraper API startup complete")
    yield
    # Shutdown
    print("Shutting down cfscraper API...")
    await shutdown_proxy_system()  # Cleanup proxy system
    await shutdown_webhook_system()  # Cleanup webhook system


app = FastAPI(
    title="CFScraper API",
    description="A comprehensive scraper API service with FastAPI, SeleniumBase, and Cloudscraper",
    version="1.0.0",
    lifespan=lifespan
)

# Setup CORS middleware with secure configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,  # Use configured origins instead of wildcard
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add security headers middleware (first)
if settings.security_headers_enabled:
    app.add_middleware(SecurityHeadersMiddleware)

# Add audit logging middleware
if settings.audit_logging_enabled:
    app.add_middleware(AuditMiddleware)

# Add monitoring middleware (before rate limiting)
app.add_middleware(MonitoringMiddleware, start_time=time.time())

# Add rate limiting middleware
if settings.rate_limiting_enabled:
    rate_limit_config = RateLimitConfig(
        enabled=settings.rate_limiting_enabled,
        include_headers=settings.rate_limit_include_headers
    )
    setup_rate_limiting(app, rate_limit_config)

# Setup exception handlers
setup_exception_handlers(app)

# Add Prometheus metrics endpoint
app.get("/metrics")(get_metrics_handler())

# Import and include API routes
from app.api.routes import api_router
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "CFScraper API is running"}


@app.get("/health")
async def health_check():
    """
    Docker health check endpoint

    This endpoint is used by Docker HEALTHCHECK instruction.
    Returns 200 for healthy, 503 for unhealthy.
    """
    from sqlalchemy import text
    from app.database.connection import connection_manager
    from app.utils.queue import create_job_queue
    import time

    try:
        # Check database connectivity
        async with connection_manager.get_async_session() as db:
            try:
                result = await db.execute(text("SELECT 1"))
                row = result.fetchone()
                if not row:
                    return JSONResponse(
                        status_code=503,
                        content={
                            "status": "unhealthy",
                            "error": "Database connection failed",
                            "service": "cfscraper-api"
                        }
                    )
            except Exception as e:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "unhealthy",
                        "error": f"Database error: {str(e)}",
                        "service": "cfscraper-api"
                    }
                )

        # Check Redis/Queue connectivity (if not using in-memory queue)
        if not settings.use_in_memory_queue:
            try:
                job_queue = create_job_queue()
                # Test Redis connection by getting queue size
                await job_queue.get_queue_size()
            except Exception as e:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "unhealthy",
                        "error": f"Redis connection failed: {str(e)}",
                        "service": "cfscraper-api"
                    }
                )

        return JSONResponse(
            content={
                "status": "healthy",
                "version": "1.0.0",
                "service": "cfscraper-api",
                "timestamp": time.time()
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": f"Health check failed: {str(e)}",
                "service": "cfscraper-api"
            }
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)