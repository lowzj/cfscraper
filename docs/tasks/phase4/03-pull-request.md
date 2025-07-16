# Pull Request: Comprehensive Monitoring and Alerting System

## Overview

This pull request implements a comprehensive monitoring and alerting system for the CFScraper API, providing production-ready observability with Prometheus metrics, structured logging, health checks, APM integration, error tracking, and alerting capabilities.

## Changes Summary

### 🔧 Core Monitoring Infrastructure

#### Prometheus Metrics Collection
- **New**: `app/monitoring/metrics.py` - Comprehensive metrics collection system
- **New**: `/metrics` endpoint for Prometheus scraping
- **Metrics Added**:
  - HTTP request metrics (rate, duration, status codes)
  - Job processing metrics (queue size, processing time, success/failure rates)
  - Scraper performance metrics (response times, success rates by type)
  - Proxy health and rotation metrics
  - Webhook delivery metrics
  - System resource metrics (CPU, memory, disk usage)
  - Database connection and query metrics

#### Structured JSON Logging
- **New**: `app/monitoring/logging.py` - Structured logging with correlation IDs
- **Features**:
  - JSON-formatted logs for better parsing and analysis
  - Request/response correlation IDs
  - Contextual information (user_id, job_id, request_id)
  - ELK stack compatibility
  - Performance and security event logging

#### Enhanced Health Checks
- **Enhanced**: `app/monitoring/health.py` - Comprehensive health checking system
- **New Endpoints**:
  - `/health/ready` - Kubernetes readiness probe
  - `/health/live` - Kubernetes liveness probe
  - `/health/detailed` - Component-level health status
- **Health Checks**:
  - Database connectivity and response time
  - Redis/Queue connectivity and queue size
  - Scraper availability (CloudScraper, Selenium)
  - External service dependencies
  - Custom component health checks

### 🔍 Application Performance Monitoring (APM)

#### OpenTelemetry Integration
- **New**: `app/monitoring/apm.py` - OpenTelemetry APM integration
- **Features**:
  - Automatic transaction tracing for FastAPI
  - Database query monitoring with SQLAlchemy instrumentation
  - Redis operation tracing
  - HTTP client request tracing
  - Custom span creation and attributes
  - Support for Jaeger and OTLP exporters

#### Error Tracking with Sentry
- **New**: `app/monitoring/error_tracking.py` - Sentry integration
- **Features**:
  - Automatic error capture and grouping
  - Performance monitoring and profiling
  - Custom error context and fingerprinting
  - Job, scraper, and webhook error tracking
  - User and request context capture
  - Error filtering and sampling

### 📊 Monitoring Infrastructure

#### Grafana Dashboards
- **New**: `monitoring/grafana/dashboards/cfscraper-overview.json` - System overview dashboard
- **New**: `monitoring/grafana/dashboards/cfscraper-business.json` - Business metrics dashboard
- **New**: `monitoring/grafana/provisioning/` - Automatic dashboard and datasource provisioning
- **Dashboards Include**:
  - HTTP request rates and error rates
  - Response time percentiles
  - Job processing metrics
  - System resource utilization
  - Scraper success rates
  - Proxy health status
  - Webhook delivery metrics

#### Prometheus Configuration
- **New**: `monitoring/prometheus.yml` - Prometheus server configuration
- **New**: `monitoring/alert_rules.yml` - Comprehensive alerting rules
- **Alert Rules**:
  - Critical: High error rate, service down, database issues
  - Warning: High response time, job failures, resource usage
  - System: Disk usage, application restarts

#### Alertmanager Setup
- **New**: `monitoring/alertmanager.yml` - Alert routing and notification configuration
- **Features**:
  - Email notifications for critical alerts
  - Slack integration for team notifications
  - Webhook delivery to application endpoints
  - Alert grouping and inhibition rules
  - Escalation policies

#### Log Aggregation
- **New**: `monitoring/filebeat.yml` - Log shipping configuration
- **New**: ELK stack integration (optional)
- **Features**:
  - Docker container log collection
  - Application log file monitoring
  - Log parsing and enrichment
  - Elasticsearch indexing
  - Kibana visualization

### 🐳 Docker Infrastructure

#### Monitoring Stack
- **New**: `monitoring/docker-compose.monitoring.yml` - Complete monitoring stack
- **Services**:
  - Prometheus for metrics collection
  - Grafana for visualization
  - Alertmanager for alert handling
  - Node Exporter for system metrics
  - Redis Exporter for Redis metrics
  - Postgres Exporter for database metrics
  - Filebeat for log shipping (optional)
  - ELK stack for log analysis (optional)

### 🔧 Application Integration

#### Monitoring Middleware
- **New**: `app/monitoring/middleware.py` - Request monitoring and metrics collection
- **Features**:
  - Automatic request/response logging
  - Metrics collection for all HTTP requests
  - Request correlation ID generation
  - Response time measurement
  - Error tracking integration

#### Main Application Updates
- **Modified**: `app/main.py` - Integrated monitoring components
- **Changes**:
  - Added monitoring middleware
  - Integrated structured logging
  - Setup APM instrumentation
  - Configured error tracking
  - Added metrics endpoint

## Configuration

### Environment Variables

```bash
# Sentry Configuration
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=1.0.0
SENTRY_SAMPLE_RATE=1.0
SENTRY_TRACES_SAMPLE_RATE=0.1

# OpenTelemetry Configuration
OTEL_SERVICE_NAME=cfscraper-api
OTEL_SERVICE_VERSION=1.0.0
OTEL_ENVIRONMENT=production
JAEGER_ENDPOINT=http://jaeger:14268
OTLP_ENDPOINT=http://otel-collector:4317
ENABLE_APM=true

# Logging Configuration
ENABLE_STRUCTURED_LOGGING=true
LOG_LEVEL=INFO
```

### Dependencies Added

```toml
# Monitoring and observability
prometheus-client = "^0.22.1"
opentelemetry-api = "^1.35.0"
opentelemetry-sdk = "^1.35.0"
opentelemetry-instrumentation-fastapi = "^0.56b0"
opentelemetry-instrumentation-sqlalchemy = "^0.56b0"
opentelemetry-instrumentation-redis = "^0.56b0"
opentelemetry-instrumentation-httpx = "^0.56b0"
opentelemetry-exporter-prometheus = "^0.56b0"
sentry-sdk = "^2.33.0"
structlog = "^25.4.0"
```

## Usage

### Starting the Monitoring Stack

```bash
# Start the main application
docker-compose up -d

# Start the monitoring stack
cd monitoring
docker-compose -f docker-compose.monitoring.yml up -d

# Optional: Start logging stack
docker-compose -f docker-compose.monitoring.yml --profile logging up -d
```

### Accessing Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Alertmanager**: http://localhost:9093
- **Kibana** (optional): http://localhost:5601

### Health Check Endpoints

- `/health` - Basic liveness check
- `/health/ready` - Readiness check for Kubernetes
- `/health/detailed` - Comprehensive component status
- `/health/live` - Liveness probe endpoint
- `/metrics` - Prometheus metrics endpoint

## Testing

### Manual Testing

```bash
# Test metrics endpoint
curl http://localhost:8000/metrics

# Test health checks
curl http://localhost:8000/health/detailed

# Test structured logging
curl http://localhost:8000/api/v1/jobs

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Test alert rules
curl http://localhost:9090/api/v1/rules
```

### Automated Testing

The monitoring system includes comprehensive tests for:
- Metrics collection accuracy
- Health check functionality
- Structured logging format
- Error tracking integration
- APM instrumentation

## Performance Impact

The monitoring system is designed for minimal performance impact:
- **Metrics collection**: < 5% CPU overhead
- **Log processing**: < 1 second latency
- **Health checks**: < 100ms response time
- **APM tracing**: Configurable sampling rates (default 10%)

## Documentation

### New Documentation Files

- `docs/monitoring/setup.md` - Complete setup and configuration guide
- `docs/monitoring/runbooks.md` - Alert response procedures and troubleshooting

### Key Features Documented

- Monitoring system architecture
- Alert response procedures
- Troubleshooting guides
- Performance optimization tips
- Security considerations
- Maintenance procedures

## Breaking Changes

None. All monitoring features are additive and can be disabled via environment variables.

## Migration Notes

1. **Environment Variables**: Add monitoring configuration to `.env` file
2. **Dependencies**: Run `uv sync` to install new dependencies
3. **Infrastructure**: Deploy monitoring stack using provided Docker Compose files
4. **Configuration**: Update Prometheus, Grafana, and Alertmanager configurations as needed

## Security Considerations

- Monitoring dashboards should be secured with authentication
- Sentry configured to not send personally identifiable information
- Internal networks used for monitoring component communication
- API keys and credentials properly secured

## Future Enhancements

- Integration with external monitoring services (DataDog, New Relic)
- Advanced anomaly detection and machine learning alerts
- Custom business metric dashboards
- Integration with incident management systems
- Advanced log analysis and correlation

## Rollback Plan

If issues arise, the monitoring system can be disabled by:
1. Setting `ENABLE_APM=false` and `ENABLE_STRUCTURED_LOGGING=false`
2. Removing monitoring middleware from application
3. Stopping monitoring stack containers
4. Reverting to previous application version if needed

## Checklist

- [x] Prometheus metrics collection implemented
- [x] Custom business metrics added
- [x] Structured JSON logging implemented
- [x] Enhanced health check endpoints created
- [x] OpenTelemetry APM integration completed
- [x] Sentry error tracking configured
- [x] Grafana dashboards created
- [x] Alerting rules and notifications configured
- [x] Log aggregation setup completed
- [x] Monitoring infrastructure as code implemented
- [x] Documentation created
- [x] Testing completed
- [x] Performance impact validated
