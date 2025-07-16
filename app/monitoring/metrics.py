"""
Prometheus metrics collection for CFScraper API
"""

import time
from typing import Dict, Any, Optional
from prometheus_client import (
    CollectorRegistry, 
    Counter, 
    Histogram, 
    Gauge, 
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST
)
from fastapi import Response
from fastapi.responses import PlainTextResponse

# Create a custom registry for our metrics
metrics_registry = CollectorRegistry()

# HTTP Request Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status_code'],
    registry=metrics_registry
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    registry=metrics_registry
)

# Job Processing Metrics
jobs_total = Counter(
    'jobs_total',
    'Total number of jobs processed',
    ['job_type', 'status'],
    registry=metrics_registry
)

job_duration_seconds = Histogram(
    'job_duration_seconds',
    'Job processing duration in seconds',
    ['job_type'],
    registry=metrics_registry
)

job_queue_size = Gauge(
    'job_queue_size',
    'Current number of jobs in queue',
    registry=metrics_registry
)

active_jobs = Gauge(
    'active_jobs',
    'Current number of active jobs',
    registry=metrics_registry
)

# Scraper Metrics
scraper_requests_total = Counter(
    'scraper_requests_total',
    'Total number of scraper requests',
    ['scraper_type', 'status'],
    registry=metrics_registry
)

scraper_response_time_seconds = Histogram(
    'scraper_response_time_seconds',
    'Scraper response time in seconds',
    ['scraper_type'],
    registry=metrics_registry
)

scraper_success_rate = Gauge(
    'scraper_success_rate',
    'Scraper success rate (0-1)',
    ['scraper_type'],
    registry=metrics_registry
)

# Proxy Metrics
proxy_requests_total = Counter(
    'proxy_requests_total',
    'Total number of proxy requests',
    ['proxy_id', 'status'],
    registry=metrics_registry
)

proxy_response_time_seconds = Histogram(
    'proxy_response_time_seconds',
    'Proxy response time in seconds',
    ['proxy_id'],
    registry=metrics_registry
)

proxy_health_status = Gauge(
    'proxy_health_status',
    'Proxy health status (1=healthy, 0=unhealthy)',
    ['proxy_id'],
    registry=metrics_registry
)

active_proxies = Gauge(
    'active_proxies',
    'Number of active proxies',
    registry=metrics_registry
)

# Webhook Metrics
webhook_deliveries_total = Counter(
    'webhook_deliveries_total',
    'Total number of webhook deliveries',
    ['webhook_url', 'status'],
    registry=metrics_registry
)

webhook_delivery_duration_seconds = Histogram(
    'webhook_delivery_duration_seconds',
    'Webhook delivery duration in seconds',
    ['webhook_url'],
    registry=metrics_registry
)

# System Metrics
system_cpu_usage = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage',
    registry=metrics_registry
)

system_memory_usage = Gauge(
    'system_memory_usage_percent',
    'System memory usage percentage',
    registry=metrics_registry
)

system_disk_usage = Gauge(
    'system_disk_usage_percent',
    'System disk usage percentage',
    registry=metrics_registry
)

# Application Info
app_info = Info(
    'app_info',
    'Application information',
    registry=metrics_registry
)

app_uptime_seconds = Gauge(
    'app_uptime_seconds',
    'Application uptime in seconds',
    registry=metrics_registry
)

# Database Metrics
database_connections_active = Gauge(
    'database_connections_active',
    'Number of active database connections',
    registry=metrics_registry
)

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query duration in seconds',
    ['query_type'],
    registry=metrics_registry
)

# Rate Limiting Metrics
rate_limit_violations_total = Counter(
    'rate_limit_violations_total',
    'Total number of rate limit violations',
    ['endpoint', 'client_ip'],
    registry=metrics_registry
)

rate_limit_requests_allowed = Counter(
    'rate_limit_requests_allowed',
    'Total number of requests allowed by rate limiter',
    ['endpoint'],
    registry=metrics_registry
)


def setup_metrics(app_version: str = "1.0.0", app_name: str = "CFScraper API"):
    """
    Initialize metrics with application information
    
    Args:
        app_version: Application version
        app_name: Application name
    """
    app_info.info({
        'version': app_version,
        'name': app_name
    })


def record_request_metrics(method: str, endpoint: str, status_code: int, duration: float):
    """
    Record HTTP request metrics
    
    Args:
        method: HTTP method
        endpoint: Request endpoint
        status_code: HTTP status code
        duration: Request duration in seconds
    """
    http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status_code=str(status_code)
    ).inc()
    
    http_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint
    ).observe(duration)


def record_job_metrics(job_type: str, status: str, duration: Optional[float] = None):
    """
    Record job processing metrics
    
    Args:
        job_type: Type of job
        status: Job status (completed, failed, etc.)
        duration: Job duration in seconds
    """
    jobs_total.labels(
        job_type=job_type,
        status=status
    ).inc()
    
    if duration is not None:
        job_duration_seconds.labels(job_type=job_type).observe(duration)


def record_scraper_metrics(scraper_type: str, status: str, response_time: Optional[float] = None):
    """
    Record scraper metrics
    
    Args:
        scraper_type: Type of scraper (selenium, cloudscraper)
        status: Request status (success, failure)
        response_time: Response time in seconds
    """
    scraper_requests_total.labels(
        scraper_type=scraper_type,
        status=status
    ).inc()
    
    if response_time is not None:
        scraper_response_time_seconds.labels(scraper_type=scraper_type).observe(response_time)


def record_proxy_metrics(proxy_id: str, status: str, response_time: Optional[float] = None):
    """
    Record proxy metrics
    
    Args:
        proxy_id: Proxy identifier
        status: Request status (success, failure)
        response_time: Response time in seconds
    """
    proxy_requests_total.labels(
        proxy_id=proxy_id,
        status=status
    ).inc()
    
    if response_time is not None:
        proxy_response_time_seconds.labels(proxy_id=proxy_id).observe(response_time)


def record_webhook_metrics(webhook_url: str, status: str, duration: Optional[float] = None):
    """
    Record webhook delivery metrics
    
    Args:
        webhook_url: Webhook URL
        status: Delivery status (success, failure)
        duration: Delivery duration in seconds
    """
    webhook_deliveries_total.labels(
        webhook_url=webhook_url,
        status=status
    ).inc()
    
    if duration is not None:
        webhook_delivery_duration_seconds.labels(webhook_url=webhook_url).observe(duration)


def update_system_metrics(cpu_percent: float, memory_percent: float, disk_percent: float):
    """
    Update system resource metrics
    
    Args:
        cpu_percent: CPU usage percentage
        memory_percent: Memory usage percentage
        disk_percent: Disk usage percentage
    """
    system_cpu_usage.set(cpu_percent)
    system_memory_usage.set(memory_percent)
    system_disk_usage.set(disk_percent)


def update_queue_metrics(queue_size: int, active_job_count: int):
    """
    Update job queue metrics
    
    Args:
        queue_size: Current queue size
        active_job_count: Number of active jobs
    """
    job_queue_size.set(queue_size)
    active_jobs.set(active_job_count)


def update_proxy_health(proxy_id: str, is_healthy: bool):
    """
    Update proxy health status
    
    Args:
        proxy_id: Proxy identifier
        is_healthy: Whether proxy is healthy
    """
    proxy_health_status.labels(proxy_id=proxy_id).set(1 if is_healthy else 0)


def update_app_uptime(start_time: float):
    """
    Update application uptime
    
    Args:
        start_time: Application start time (timestamp)
    """
    uptime = time.time() - start_time
    app_uptime_seconds.set(uptime)


def get_metrics_handler():
    """
    Get FastAPI handler for /metrics endpoint
    
    Returns:
        FastAPI response with Prometheus metrics
    """
    def metrics_endpoint():
        metrics_data = generate_latest(metrics_registry)
        return PlainTextResponse(
            content=metrics_data,
            media_type=CONTENT_TYPE_LATEST
        )
    
    return metrics_endpoint
