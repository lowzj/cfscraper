# CFScraper Docker Setup and Deployment Guide

This guide provides comprehensive instructions for setting up and deploying the CFScraper API using Docker containers.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Development Environment](#development-environment)
- [Production Deployment](#production-deployment)
- [Configuration](#configuration)
- [Monitoring and Maintenance](#monitoring-and-maintenance)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Docker**: Version 20.10 or higher
- **Docker Compose**: Version 2.0 or higher
- **System Memory**: Minimum 4GB RAM (8GB recommended for production)
- **Disk Space**: Minimum 10GB free space
- **Network**: Internet access for downloading images and dependencies

### Installation

#### Docker Installation

**Ubuntu/Debian:**

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

**macOS:**

```bash
# Install Docker Desktop from https://docker.com/products/docker-desktop
# Or using Homebrew:
brew install --cask docker
```

**Windows:**
Download and install Docker Desktop from https://docker.com/products/docker-desktop

#### Verify Installation

```bash
docker --version
docker-compose --version
```

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd cfscraper
```

### 2. Start Development Environment

```bash
# Copy environment configuration
cp .env.dev .env

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f app
```

### 3. Verify Installation

```bash
# Check health
curl http://localhost:8000/health

# Test API
curl http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://httpbin.org/get", "method": "GET"}'
```

## Development Environment

### Starting Services

```bash
# Start all services in background
docker-compose up -d

# Start with logs visible
docker-compose up

# Start specific services
docker-compose up app postgres redis
```

### Development Features

- **Live Code Reloading**: Source code is mounted as volumes
- **Database Management**: pgAdmin available at http://localhost:8080
- **Redis Management**: Redis Commander at http://localhost:8081
- **Hot Reload**: Changes to Python files trigger automatic restart

### Development Tools

```bash
# Access application container
docker-compose exec app bash

# Run database migrations
docker-compose exec app alembic upgrade head

# Run tests
docker-compose exec app pytest

# View application logs
docker-compose logs -f app

# Monitor resource usage
docker stats
```

### Stopping Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: This deletes data)
docker-compose down -v

# Stop specific service
docker-compose stop app
```

## Production Deployment

### 1. Environment Setup

```bash
# Copy production environment template
cp .env.prod .env.prod.local

# Edit configuration (IMPORTANT: Set secure passwords)
nano .env.prod.local
```

### 2. Security Configuration

**Required Changes in `.env.prod.local`:**

- Set secure database passwords
- Configure Redis authentication
- Set JWT secret keys
- Configure allowed hosts/origins
- Set up monitoring credentials

### 3. Deploy Production Stack

```bash
# Build production images
./scripts/build-docker.sh prod

# Deploy with production compose
docker-compose -f docker-compose.prod.yml --env-file .env.prod.local up -d

# Run database migrations
docker-compose -f docker-compose.prod.yml exec migration alembic upgrade head
```

### 4. SSL/TLS Setup

```bash
# Create SSL directory
mkdir -p docker/ssl

# Copy your SSL certificates
cp your-cert.pem docker/ssl/
cp your-key.pem docker/ssl/

# Update nginx configuration for HTTPS
# Edit docker/nginx/conf.d/cfscraper.conf
```

### 5. Production Monitoring

```bash
# Start with monitoring stack
docker-compose -f docker-compose.prod.yml --profile monitoring up -d

# Access monitoring
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (if configured)
```

## Configuration

### Environment Variables

| Variable                         | Description                      | Default                  | Required |
| -------------------------------- | -------------------------------- | ------------------------ | -------- |
| `DATABASE_URL`                   | PostgreSQL connection string     | -                        | Yes      |
| `REDIS_URL`                      | Redis connection string          | `redis://localhost:6379` | Yes      |
| `MAX_CONCURRENT_JOBS`            | Maximum concurrent scraping jobs | `10`                     | No       |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | API rate limit                   | `60`                     | No       |
| `DEBUG`                          | Enable debug mode                | `false`                  | No       |

### Service Configuration

#### Application Service

- **Port**: 8000
- **Health Check**: `/health`
- **Memory Limit**: 1GB (production)
- **CPU Limit**: 1.0 (production)

#### PostgreSQL Service

- **Port**: 5432
- **Memory Limit**: 2GB (production)
- **Persistent Storage**: Yes

#### Redis Service

- **Port**: 6379
- **Memory Limit**: 512MB (production)
- **Persistent Storage**: Yes

### Scaling

```bash
# Scale application instances
docker-compose -f docker-compose.prod.yml up -d --scale app=3

# Scale with resource limits
docker-compose -f docker-compose.prod.yml up -d --scale app=3 --scale redis=1
```

## Monitoring and Maintenance

### Health Checks

```bash
# Check all services
docker-compose ps

# Check specific service health
docker-compose exec app curl -f http://localhost:8000/health

# View detailed health information
curl http://localhost:8000/api/v1/health/detailed
```

### Log Management

```bash
# View logs
docker-compose logs -f app

# View logs with timestamps
docker-compose logs -f -t app

# View last 100 lines
docker-compose logs --tail=100 app

# Export logs
docker-compose logs app > app.log
```

### Database Maintenance

```bash
# Backup database
docker-compose exec postgres pg_dump -U cfscraper cfscraper_prod > backup.sql

# Restore database
docker-compose exec -T postgres psql -U cfscraper cfscraper_prod < backup.sql

# Run migrations
docker-compose exec app alembic upgrade head
```

### Performance Monitoring

```bash
# Monitor resource usage
docker stats

# Monitor specific container
docker stats cfscraper-app-prod

# View container processes
docker-compose top
```

## Troubleshooting

### Common Issues

#### Container Won't Start

```bash
# Check logs
docker-compose logs app

# Check container status
docker-compose ps

# Restart specific service
docker-compose restart app
```

#### Database Connection Issues

```bash
# Check PostgreSQL logs
docker-compose logs postgres

# Test database connection
docker-compose exec app python -c "
from app.core.database import engine
print(engine.execute('SELECT 1').fetchone())
"
```

#### Redis Connection Issues

```bash
# Check Redis logs
docker-compose logs redis

# Test Redis connection
docker-compose exec redis redis-cli ping
```

#### Performance Issues

```bash
# Check resource usage
docker stats

# Check application metrics
curl http://localhost:8000/api/v1/metrics

# Scale services if needed
docker-compose up -d --scale app=2
```

### Debug Mode

```bash
# Enable debug mode
echo "DEBUG=true" >> .env

# Restart with debug
docker-compose restart app

# View debug logs
docker-compose logs -f app
```

### Clean Installation

```bash
# Stop all services
docker-compose down

# Remove all containers and volumes
docker-compose down -v --remove-orphans

# Remove images
docker rmi $(docker images cfscraper* -q)

# Clean Docker system
docker system prune -a
```

## Security Best Practices

1. **Use non-root containers** (already implemented)
2. **Set secure passwords** for all services
3. **Enable SSL/TLS** for production
4. **Configure firewalls** to restrict access
5. **Regular security updates** of base images
6. **Monitor logs** for suspicious activity
7. **Use secrets management** for sensitive data

## Advanced Configuration

### Custom Nginx Configuration

```bash
# Edit nginx configuration
nano docker/nginx/conf.d/cfscraper.conf

# Reload nginx configuration
docker-compose exec nginx nginx -s reload
```

### Custom Redis Configuration

```bash
# Edit redis configuration
nano docker/redis/redis.conf

# Restart Redis
docker-compose restart redis
```

### Custom PostgreSQL Configuration

```bash
# Edit PostgreSQL configuration
nano docker/postgres/postgresql.conf

# Restart PostgreSQL
docker-compose restart postgres
```

## Backup and Recovery

### Automated Backups

```bash
# Create backup script
cat > scripts/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec postgres pg_dump -U cfscraper cfscraper_prod > backups/db_$DATE.sql
docker-compose exec redis redis-cli BGSAVE
cp data/redis/dump.rdb backups/redis_$DATE.rdb
EOF

chmod +x scripts/backup.sh
```

### Disaster Recovery

```bash
# Stop services
docker-compose down

# Restore database
docker-compose up -d postgres
docker-compose exec -T postgres psql -U cfscraper cfscraper_prod < backups/db_latest.sql

# Restore Redis
cp backups/redis_latest.rdb data/redis/dump.rdb

# Start all services
docker-compose up -d
```

## Support

For additional support:

- Check the [main README](../../README.md)
- Review [API documentation](../api/)
- Submit issues on the project repository
