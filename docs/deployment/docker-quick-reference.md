# CFScraper Docker Quick Reference

## Quick Commands

### Development Environment

```bash
# Start development environment
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop environment
docker-compose down

# Rebuild and restart
docker-compose up -d --build

# Access application shell
docker-compose exec app bash

# Run migrations
docker-compose exec app alembic upgrade head

# Run tests
docker-compose exec app pytest
```

### Production Environment

```bash
# Deploy production
docker-compose -f docker-compose.prod.yml --env-file .env.prod.local up -d

# Scale application
docker-compose -f docker-compose.prod.yml up -d --scale app=3

# View production logs
docker-compose -f docker-compose.prod.yml logs -f app

# Stop production
docker-compose -f docker-compose.prod.yml down
```

### Monitoring

```bash
# Check service status
docker-compose ps

# Monitor resource usage
docker stats

# Check health
curl http://localhost:8000/health

# View detailed health
curl http://localhost:8000/api/v1/health/detailed
```

### Database Operations

```bash
# Backup database
docker-compose exec postgres pg_dump -U cfscraper cfscraper_dev > backup.sql

# Restore database
docker-compose exec -T postgres psql -U cfscraper cfscraper_dev < backup.sql

# Access database shell
docker-compose exec postgres psql -U cfscraper cfscraper_dev

# View database logs
docker-compose logs postgres
```

### Redis Operations

```bash
# Access Redis CLI
docker-compose exec redis redis-cli

# Check Redis info
docker-compose exec redis redis-cli info

# Monitor Redis
docker-compose exec redis redis-cli monitor

# Flush Redis (WARNING: Deletes all data)
docker-compose exec redis redis-cli flushall
```

### Troubleshooting

```bash
# View all logs
docker-compose logs

# Restart specific service
docker-compose restart app

# Check container processes
docker-compose top

# Clean up stopped containers
docker container prune

# Clean up unused images
docker image prune

# Full system cleanup
docker system prune -a
```

## Environment Files

### Development (.env.dev)
- `DEBUG=true`
- `DATABASE_URL=postgresql://cfscraper:cfscraper_password@postgres:5432/cfscraper_dev`
- `REDIS_URL=redis://redis:6379`

### Production (.env.prod.local)
- `DEBUG=false`
- `DATABASE_URL=postgresql://user:password@postgres:5432/cfscraper_prod`
- `REDIS_URL=redis://redis:6379`

## Service Ports

| Service | Development Port | Production Port | Purpose |
|---------|------------------|-----------------|---------|
| Application | 8000 | 80/443 | Main API |
| PostgreSQL | 5432 | - | Database |
| Redis | 6379 | - | Job Queue |
| pgAdmin | 8080 | - | DB Management |
| Redis Commander | 8081 | - | Redis Management |
| Prometheus | - | 9090 | Monitoring |

## Health Check Endpoints

- **Basic Health**: `GET /health`
- **Detailed Health**: `GET /api/v1/health/detailed`
- **Metrics**: `GET /api/v1/metrics`
- **Service Status**: `GET /api/v1/status`

## Common Issues

### Container Won't Start
1. Check logs: `docker-compose logs service_name`
2. Verify environment variables
3. Check port conflicts
4. Restart Docker daemon

### Database Connection Failed
1. Check PostgreSQL logs: `docker-compose logs postgres`
2. Verify DATABASE_URL
3. Ensure PostgreSQL is healthy: `docker-compose ps`
4. Test connection: `docker-compose exec postgres pg_isready`

### Redis Connection Failed
1. Check Redis logs: `docker-compose logs redis`
2. Verify REDIS_URL
3. Test Redis: `docker-compose exec redis redis-cli ping`

### Performance Issues
1. Check resource usage: `docker stats`
2. Scale services: `docker-compose up -d --scale app=2`
3. Check application metrics: `curl localhost:8000/api/v1/metrics`

## Security Checklist

- [ ] Change default passwords
- [ ] Configure SSL/TLS certificates
- [ ] Set up firewall rules
- [ ] Enable container security scanning
- [ ] Configure log monitoring
- [ ] Set up backup procedures
- [ ] Review environment variables
- [ ] Enable rate limiting
- [ ] Configure CORS properly
- [ ] Set up monitoring alerts
