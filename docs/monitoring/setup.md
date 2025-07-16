# CFScraper API Monitoring Setup

This document describes how to set up and configure the comprehensive monitoring system for CFScraper API.

## Overview

The monitoring stack includes:
- **Prometheus** - Metrics collection and alerting
- **Grafana** - Visualization and dashboards
- **Alertmanager** - Alert routing and notifications
- **Sentry** - Error tracking and performance monitoring
- **OpenTelemetry** - Application performance monitoring (APM)
- **Structured Logging** - JSON-formatted logs with correlation IDs
- **ELK Stack** (optional) - Log aggregation and analysis

## Quick Start

### 1. Start the Monitoring Stack

```bash
# Start the main application
docker-compose up -d

# Start the monitoring stack
cd monitoring
docker-compose -f docker-compose.monitoring.yml up -d

# Optional: Start logging stack
docker-compose -f docker-compose.monitoring.yml --profile logging up -d
```

### 2. Access the Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Alertmanager**: http://localhost:9093
- **Kibana** (optional): http://localhost:5601

### 3. Configure Environment Variables

Create a `.env` file with monitoring configuration:

```bash
# Sentry Configuration
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=1.0.0

# OpenTelemetry Configuration
OTEL_SERVICE_NAME=cfscraper-api
OTEL_SERVICE_VERSION=1.0.0
OTEL_ENVIRONMENT=production
JAEGER_ENDPOINT=http://jaeger:14268
OTLP_ENDPOINT=http://otel-collector:4317

# Enable/Disable Features
ENABLE_APM=true
ENABLE_STRUCTURED_LOGGING=true
```

## Components

### Prometheus Metrics

The application exposes metrics at `/metrics` endpoint including:

#### HTTP Metrics
- `http_requests_total` - Total HTTP requests by method, endpoint, status
- `http_request_duration_seconds` - Request duration histogram

#### Job Metrics
- `jobs_total` - Total jobs by type and status
- `job_duration_seconds` - Job processing duration
- `job_queue_size` - Current queue size
- `active_jobs` - Number of active jobs

#### Scraper Metrics
- `scraper_requests_total` - Scraper requests by type and status
- `scraper_response_time_seconds` - Scraper response times
- `scraper_success_rate` - Success rate by scraper type

#### Proxy Metrics
- `proxy_requests_total` - Proxy requests by ID and status
- `proxy_response_time_seconds` - Proxy response times
- `proxy_health_status` - Proxy health (1=healthy, 0=unhealthy)
- `active_proxies` - Number of active proxies

#### System Metrics
- `system_cpu_usage_percent` - CPU usage
- `system_memory_usage_percent` - Memory usage
- `system_disk_usage_percent` - Disk usage
- `app_uptime_seconds` - Application uptime

### Grafana Dashboards

#### CFScraper Overview Dashboard
- HTTP request rate and error rate
- Response time percentiles
- Job queue size
- System resource usage

#### Business Metrics Dashboard
- Job processing rates by type
- Scraper success rates
- Proxy status and health
- Webhook delivery rates

### Alerting Rules

Critical alerts:
- **HighErrorRate**: Error rate > 10% for 2 minutes
- **ServiceDown**: Service unavailable for 1 minute
- **HighQueueSize**: Queue size > 100 for 5 minutes
- **DatabaseConnectionIssues**: No DB connections for 2 minutes

Warning alerts:
- **HighResponseTime**: 95th percentile > 2s for 5 minutes
- **HighJobFailureRate**: Job failure rate > 20% for 5 minutes
- **HighCPUUsage**: CPU > 80% for 10 minutes
- **HighMemoryUsage**: Memory > 85% for 5 minutes

### Health Checks

The application provides multiple health check endpoints:

- `/health` - Basic liveness check
- `/health/ready` - Readiness check for Kubernetes
- `/health/detailed` - Comprehensive component status
- `/health/live` - Liveness probe endpoint
- `/ping` - Simple ping/pong

## Configuration

### Prometheus Configuration

Edit `monitoring/prometheus.yml` to configure:
- Scrape intervals
- Target endpoints
- Retention policies
- Alert rule files

### Alertmanager Configuration

Edit `monitoring/alertmanager.yml` to configure:
- Email notifications
- Slack webhooks
- PagerDuty integration
- Alert routing rules

### Grafana Provisioning

Dashboards and datasources are automatically provisioned from:
- `monitoring/grafana/provisioning/datasources/`
- `monitoring/grafana/provisioning/dashboards/`
- `monitoring/grafana/dashboards/`

## Structured Logging

The application uses structured JSON logging with:

### Log Format
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "info",
  "message": "Request completed",
  "service": "cfscraper-api",
  "version": "1.0.0",
  "request_id": "uuid-here",
  "method": "GET",
  "url": "/api/v1/jobs",
  "status_code": 200,
  "response_time": 0.123
}
```

### Context Variables
- `request_id` - Unique request identifier
- `user_id` - User identifier (if available)
- `job_id` - Job identifier for job-related logs

## Error Tracking with Sentry

Sentry integration provides:
- Automatic error capture
- Performance monitoring
- Release tracking
- User context
- Custom fingerprinting

### Error Context
Errors are captured with context including:
- Request information
- User details
- Job information
- Custom tags and fingerprints

## Troubleshooting

### Common Issues

1. **Metrics not appearing in Prometheus**
   - Check if `/metrics` endpoint is accessible
   - Verify Prometheus configuration
   - Check network connectivity

2. **Grafana dashboards not loading**
   - Verify Prometheus datasource configuration
   - Check dashboard JSON syntax
   - Ensure proper permissions

3. **Alerts not firing**
   - Check alert rule syntax
   - Verify Alertmanager configuration
   - Test notification channels

4. **Logs not appearing in Elasticsearch**
   - Check Filebeat configuration
   - Verify Elasticsearch connectivity
   - Check log format and parsing

### Debugging Commands

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check Alertmanager status
curl http://localhost:9093/api/v1/status

# Test metrics endpoint
curl http://localhost:8000/metrics

# Check application health
curl http://localhost:8000/health/detailed
```

## Security Considerations

1. **Network Security**
   - Use internal networks for monitoring components
   - Restrict external access to monitoring dashboards
   - Use authentication for Grafana and other UIs

2. **Data Privacy**
   - Configure Sentry to not send PII
   - Sanitize logs of sensitive information
   - Use secure communication channels

3. **Access Control**
   - Implement role-based access for dashboards
   - Use API keys for external integrations
   - Regular security updates for monitoring components

## Performance Impact

The monitoring system is designed to have minimal performance impact:
- Metrics collection: < 5% CPU overhead
- Log processing: < 1 second latency
- Health checks: < 100ms response time
- APM tracing: Configurable sampling rates

## Maintenance

### Regular Tasks
1. Monitor disk usage for time-series data
2. Update dashboard configurations
3. Review and tune alert thresholds
4. Clean up old logs and metrics
5. Update monitoring component versions

### Backup and Recovery
- Backup Grafana dashboards and configuration
- Export Prometheus data for long-term storage
- Document alert runbooks and procedures
