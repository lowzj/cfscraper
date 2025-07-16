# CFScraper API Monitoring Runbooks

This document provides step-by-step procedures for responding to monitoring alerts and troubleshooting common issues.

## Alert Response Procedures

### Critical Alerts

#### HighErrorRate
**Alert**: Error rate > 10% for 2 minutes
**Severity**: Critical

**Immediate Actions**:
1. Check application logs for error patterns
2. Verify database connectivity
3. Check external service dependencies
4. Review recent deployments

**Investigation Steps**:
```bash
# Check error rate by endpoint
curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total{status_code=~\"5..\"}[5m])" | jq

# Check application logs
docker logs cfscraper-app-dev --tail 100

# Check health status
curl http://localhost:8000/health/detailed
```

**Resolution**:
- If database issue: Restart database or check connections
- If code issue: Rollback deployment or apply hotfix
- If external dependency: Implement circuit breaker or fallback

#### ServiceDown
**Alert**: Service unavailable for 1 minute
**Severity**: Critical

**Immediate Actions**:
1. Check if application container is running
2. Verify network connectivity
3. Check resource availability (CPU, memory, disk)
4. Review application startup logs

**Investigation Steps**:
```bash
# Check container status
docker ps | grep cfscraper

# Check resource usage
docker stats cfscraper-app-dev

# Check startup logs
docker logs cfscraper-app-dev --since 10m

# Test connectivity
curl -f http://localhost:8000/health || echo "Service unreachable"
```

**Resolution**:
- Restart application container
- Scale resources if needed
- Check and fix configuration issues
- Investigate and resolve startup failures

#### DatabaseConnectionIssues
**Alert**: No active database connections for 2 minutes
**Severity**: Critical

**Immediate Actions**:
1. Check database service status
2. Verify connection pool configuration
3. Check network connectivity to database
4. Review database logs

**Investigation Steps**:
```bash
# Check database container
docker ps | grep postgres

# Test database connectivity
docker exec cfscraper-postgres-dev pg_isready -U cfscraper

# Check connection pool metrics
curl -s "http://localhost:9090/api/v1/query?query=database_connections_active" | jq

# Check database logs
docker logs cfscraper-postgres-dev --tail 50
```

**Resolution**:
- Restart database service if needed
- Adjust connection pool settings
- Fix network connectivity issues
- Resolve database performance problems

### Warning Alerts

#### HighResponseTime
**Alert**: 95th percentile response time > 2s for 5 minutes
**Severity**: Warning

**Investigation Steps**:
1. Identify slow endpoints
2. Check database query performance
3. Review external API response times
4. Analyze resource utilization

**Diagnostic Commands**:
```bash
# Check response time by endpoint
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))" | jq

# Check database query times
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, rate(database_query_duration_seconds_bucket[5m]))" | jq

# Check system resources
curl -s "http://localhost:9090/api/v1/query?query=system_cpu_usage_percent" | jq
```

#### HighJobFailureRate
**Alert**: Job failure rate > 20% for 5 minutes
**Severity**: Warning

**Investigation Steps**:
1. Check job error logs
2. Verify scraper configurations
3. Check proxy health
4. Review external website changes

**Diagnostic Commands**:
```bash
# Check job failure rate by type
curl -s "http://localhost:9090/api/v1/query?query=rate(jobs_total{status=\"failed\"}[10m])" | jq

# Check recent failed jobs
curl http://localhost:8000/api/v1/jobs?status=failed&limit=10

# Check proxy status
curl -s "http://localhost:9090/api/v1/query?query=proxy_health_status" | jq
```

## Troubleshooting Procedures

### Application Issues

#### High Memory Usage
**Symptoms**: Memory usage > 85%

**Investigation**:
```bash
# Check memory usage
docker stats cfscraper-app-dev

# Check for memory leaks
curl http://localhost:8000/health/detailed

# Review application metrics
curl -s "http://localhost:9090/api/v1/query?query=system_memory_usage_percent" | jq
```

**Resolution**:
- Restart application if memory leak suspected
- Increase memory limits
- Optimize application code
- Review job processing patterns

#### High CPU Usage
**Symptoms**: CPU usage > 80% for extended periods

**Investigation**:
```bash
# Check CPU usage
docker stats cfscraper-app-dev

# Check active jobs
curl -s "http://localhost:9090/api/v1/query?query=active_jobs" | jq

# Review job processing rate
curl -s "http://localhost:9090/api/v1/query?query=rate(jobs_total[5m])" | jq
```

**Resolution**:
- Scale application horizontally
- Optimize job processing
- Implement rate limiting
- Review scraper efficiency

### Database Issues

#### Slow Queries
**Symptoms**: High database response times

**Investigation**:
```bash
# Check slow queries
docker exec cfscraper-postgres-dev psql -U cfscraper -d cfscraper_dev -c "
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;"

# Check database connections
docker exec cfscraper-postgres-dev psql -U cfscraper -d cfscraper_dev -c "
SELECT count(*) as active_connections 
FROM pg_stat_activity 
WHERE state = 'active';"
```

**Resolution**:
- Add database indexes
- Optimize query patterns
- Increase database resources
- Implement query caching

### Monitoring System Issues

#### Prometheus Not Scraping
**Symptoms**: Missing metrics in Prometheus

**Investigation**:
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Test metrics endpoint
curl http://localhost:8000/metrics

# Check Prometheus logs
docker logs cfscraper-prometheus
```

**Resolution**:
- Fix network connectivity
- Update Prometheus configuration
- Restart Prometheus service
- Check application metrics endpoint

#### Grafana Dashboard Issues
**Symptoms**: Dashboards not loading or showing data

**Investigation**:
```bash
# Check Grafana logs
docker logs cfscraper-grafana

# Test Prometheus datasource
curl http://localhost:3000/api/datasources/proxy/1/api/v1/query?query=up

# Check dashboard configuration
curl http://localhost:3000/api/dashboards/uid/cfscraper-overview
```

**Resolution**:
- Fix datasource configuration
- Update dashboard queries
- Restart Grafana service
- Check dashboard permissions

## Performance Optimization

### Metrics Collection
- Adjust scrape intervals based on needs
- Use recording rules for complex queries
- Implement metric retention policies
- Monitor metrics cardinality

### Log Management
- Configure log rotation
- Implement log sampling for high-volume logs
- Use structured logging consistently
- Set appropriate log levels

### Alert Tuning
- Adjust alert thresholds based on baseline
- Implement alert fatigue prevention
- Use alert dependencies and inhibitions
- Regular review of alert effectiveness

## Maintenance Procedures

### Daily Tasks
1. Check alert status and resolve any issues
2. Review dashboard metrics for anomalies
3. Monitor disk usage for time-series data
4. Check application health status

### Weekly Tasks
1. Review and tune alert thresholds
2. Analyze performance trends
3. Update dashboard configurations
4. Clean up old logs and metrics

### Monthly Tasks
1. Review monitoring system performance
2. Update monitoring component versions
3. Backup monitoring configurations
4. Conduct monitoring system health check

## Emergency Contacts

### Escalation Matrix
- **Level 1**: On-call engineer
- **Level 2**: Senior engineer or team lead
- **Level 3**: Engineering manager
- **Level 4**: CTO or VP Engineering

### Communication Channels
- **Slack**: #alerts channel
- **Email**: alerts@company.com
- **PagerDuty**: For critical alerts
- **Phone**: For urgent escalations

## Recovery Procedures

### Application Recovery
1. Identify root cause using monitoring data
2. Implement immediate fix or rollback
3. Verify system stability
4. Document incident and lessons learned

### Data Recovery
1. Stop application to prevent data corruption
2. Restore from latest backup
3. Verify data integrity
4. Resume application operations

### Monitoring System Recovery
1. Identify failed components
2. Restore from configuration backups
3. Verify metric collection and alerting
4. Update runbooks based on experience
