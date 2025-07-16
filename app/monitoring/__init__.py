"""
Monitoring and observability package for CFScraper API
"""

from .metrics import (
    metrics_registry,
    setup_metrics,
    record_request_metrics,
    record_job_metrics,
    record_scraper_metrics,
    record_proxy_metrics,
    record_webhook_metrics,
    get_metrics_handler
)

from .logging import (
    setup_structured_logging,
    get_logger,
    log_with_context,
    StructuredLogger
)

from .health import (
    HealthChecker,
    ComponentStatus,
    setup_health_checks
)

from .apm import (
    setup_apm_instrumentation,
    apm_tracer
)

from .error_tracking import (
    ErrorTracker,
    capture_exception,
    capture_message
)

from .middleware import (
    MonitoringMiddleware,
    MetricsCollectionMiddleware
)

__all__ = [
    "metrics_registry",
    "setup_metrics",
    "record_request_metrics",
    "record_job_metrics",
    "record_scraper_metrics",
    "record_proxy_metrics",
    "record_webhook_metrics",
    "get_metrics_handler",
    "setup_structured_logging",
    "get_logger",
    "log_with_context",
    "StructuredLogger",
    "HealthChecker",
    "ComponentStatus",
    "setup_health_checks",
    "setup_apm_instrumentation",
    "apm_tracer",
    "ErrorTracker",
    "capture_exception",
    "capture_message",
    "MonitoringMiddleware",
    "MetricsCollectionMiddleware"
]
