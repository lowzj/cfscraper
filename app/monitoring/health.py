"""
Enhanced health check system for CFScraper API
"""

import asyncio
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict

import httpx
from sqlalchemy import text

from app.database.connection import connection_manager
from app.core.config import settings
from app.utils.queue import create_job_queue


class ComponentStatus(Enum):
    """Component health status"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Health check result"""
    status: ComponentStatus
    response_time: Optional[float] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    last_check: Optional[datetime] = None


class HealthChecker:
    """Enhanced health checker with component monitoring"""
    
    def __init__(self):
        self.start_time = time.time()
        self.checks: Dict[str, Callable] = {}
        self.last_results: Dict[str, HealthCheckResult] = {}
    
    def register_check(self, name: str, check_func: Callable):
        """
        Register a health check function
        
        Args:
            name: Check name
            check_func: Async function that returns HealthCheckResult
        """
        self.checks[name] = check_func
    
    async def check_database(self) -> HealthCheckResult:
        """Check database connectivity"""
        start_time = time.time()
        
        try:
            async with connection_manager.get_async_session() as db:
                try:
                    result = await db.execute(text("SELECT 1"))
                    row = result.fetchone()
                    response_time = time.time() - start_time
                    
                    if row:
                        return HealthCheckResult(
                            status=ComponentStatus.HEALTHY,
                            response_time=response_time,
                            details={"connection": "active"},
                            last_check=datetime.now(timezone.utc)
                        )
                    else:
                        return HealthCheckResult(
                            status=ComponentStatus.UNHEALTHY,
                            response_time=response_time,
                            error="Database query returned no result",
                            last_check=datetime.now(timezone.utc)
                        )
                except Exception as e:
                    response_time = time.time() - start_time
                    return HealthCheckResult(
                        status=ComponentStatus.UNHEALTHY,
                        response_time=response_time,
                        error=str(e),
                        last_check=datetime.now(timezone.utc)
                    )
                
        except Exception as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                status=ComponentStatus.UNHEALTHY,
                response_time=response_time,
                error=str(e),
                last_check=datetime.now(timezone.utc)
            )
    
    async def check_redis(self) -> HealthCheckResult:
        """Check Redis/Queue connectivity"""
        start_time = time.time()
        
        try:
            if settings.use_in_memory_queue:
                # For in-memory queue, just check if we can create it
                queue = create_job_queue()
                queue_size = await queue.get_queue_size()
                response_time = time.time() - start_time
                
                return HealthCheckResult(
                    status=ComponentStatus.HEALTHY,
                    response_time=response_time,
                    details={
                        "type": "in_memory",
                        "queue_size": queue_size
                    },
                    last_check=datetime.now(timezone.utc)
                )
            else:
                # For Redis queue, check Redis connectivity
                queue = create_job_queue()
                queue_size = await queue.get_queue_size()
                response_time = time.time() - start_time
                
                return HealthCheckResult(
                    status=ComponentStatus.HEALTHY,
                    response_time=response_time,
                    details={
                        "type": "redis",
                        "queue_size": queue_size
                    },
                    last_check=datetime.now(timezone.utc)
                )
                
        except Exception as e:
            response_time = time.time() - start_time
            status = ComponentStatus.DEGRADED if "redis" in str(e).lower() else ComponentStatus.UNHEALTHY
            
            return HealthCheckResult(
                status=status,
                response_time=response_time,
                error=str(e),
                last_check=datetime.now(timezone.utc)
            )
    
    async def check_scrapers(self) -> HealthCheckResult:
        """Check scraper availability"""
        start_time = time.time()
        scrapers_status = {}
        
        try:
            # Check CloudScraper
            try:
                import cloudscraper
                scrapers_status["cloudscraper"] = "available"
            except ImportError:
                scrapers_status["cloudscraper"] = "unavailable"
            
            # Check Selenium
            try:
                import seleniumbase
                scrapers_status["selenium"] = "available"
            except ImportError:
                scrapers_status["selenium"] = "unavailable"
            
            response_time = time.time() - start_time
            available_count = sum(1 for status in scrapers_status.values() if status == "available")
            
            if available_count > 0:
                status = ComponentStatus.HEALTHY if available_count == len(scrapers_status) else ComponentStatus.DEGRADED
            else:
                status = ComponentStatus.UNHEALTHY
            
            return HealthCheckResult(
                status=status,
                response_time=response_time,
                details=scrapers_status,
                last_check=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                status=ComponentStatus.UNHEALTHY,
                response_time=response_time,
                error=str(e),
                last_check=datetime.now(timezone.utc)
            )
    
    async def check_external_dependencies(self) -> HealthCheckResult:
        """Check external service dependencies"""
        start_time = time.time()
        dependencies = {}
        
        try:
            # Check internet connectivity with a simple HTTP request
            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    response = await client.get("https://httpbin.org/status/200")
                    dependencies["internet"] = "available" if response.status_code == 200 else "degraded"
                except Exception:
                    dependencies["internet"] = "unavailable"
            
            response_time = time.time() - start_time
            available_count = sum(1 for status in dependencies.values() if status == "available")
            
            if available_count == len(dependencies):
                status = ComponentStatus.HEALTHY
            elif available_count > 0:
                status = ComponentStatus.DEGRADED
            else:
                status = ComponentStatus.UNHEALTHY
            
            return HealthCheckResult(
                status=status,
                response_time=response_time,
                details=dependencies,
                last_check=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                status=ComponentStatus.UNHEALTHY,
                response_time=response_time,
                error=str(e),
                last_check=datetime.now(timezone.utc)
            )
    
    async def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        """Run all registered health checks"""
        results = {}
        
        # Run built-in checks
        built_in_checks = {
            "database": self.check_database,
            "queue": self.check_redis,
            "scrapers": self.check_scrapers,
            "external_dependencies": self.check_external_dependencies
        }
        
        # Combine with registered checks
        all_checks = {**built_in_checks, **self.checks}
        
        # Run checks concurrently
        tasks = []
        for name, check_func in all_checks.items():
            tasks.append(self._run_single_check(name, check_func))
        
        check_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, (name, _) in enumerate(all_checks.items()):
            result = check_results[i]
            if isinstance(result, Exception):
                results[name] = HealthCheckResult(
                    status=ComponentStatus.UNHEALTHY,
                    error=str(result),
                    last_check=datetime.now(timezone.utc)
                )
            else:
                results[name] = result
        
        # Cache results
        self.last_results = results
        return results
    
    async def _run_single_check(self, name: str, check_func: Callable) -> HealthCheckResult:
        """Run a single health check with timeout"""
        try:
            return await asyncio.wait_for(check_func(), timeout=10.0)
        except asyncio.TimeoutError:
            return HealthCheckResult(
                status=ComponentStatus.UNHEALTHY,
                error="Health check timed out",
                last_check=datetime.now(timezone.utc)
            )
        except Exception as e:
            return HealthCheckResult(
                status=ComponentStatus.UNHEALTHY,
                error=str(e),
                last_check=datetime.now(timezone.utc)
            )
    
    def get_overall_status(self, results: Dict[str, HealthCheckResult]) -> ComponentStatus:
        """Determine overall system status from component results"""
        if not results:
            return ComponentStatus.UNKNOWN
        
        statuses = [result.status for result in results.values()]
        
        if all(status == ComponentStatus.HEALTHY for status in statuses):
            return ComponentStatus.HEALTHY
        elif any(status == ComponentStatus.UNHEALTHY for status in statuses):
            return ComponentStatus.UNHEALTHY
        elif any(status == ComponentStatus.DEGRADED for status in statuses):
            return ComponentStatus.DEGRADED
        else:
            return ComponentStatus.UNKNOWN
    
    def get_uptime(self) -> float:
        """Get application uptime in seconds"""
        return time.time() - self.start_time
    
    async def get_basic_health(self) -> Dict[str, Any]:
        """Get basic health information"""
        return {
            "status": "healthy",
            "version": "1.0.0",
            "uptime": self.get_uptime(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def get_detailed_health(self) -> Dict[str, Any]:
        """Get detailed health information"""
        results = await self.run_all_checks()
        overall_status = self.get_overall_status(results)
        
        # Convert results to dict format
        components = {}
        for name, result in results.items():
            components[name] = {
                "status": result.status.value,
                "response_time": result.response_time,
                "error": result.error,
                "details": result.details,
                "last_check": result.last_check.isoformat() if result.last_check else None
            }
        
        return {
            "status": overall_status.value,
            "version": "1.0.0",
            "uptime": self.get_uptime(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": components
        }
    
    async def get_readiness(self) -> Dict[str, Any]:
        """Get readiness status for Kubernetes readiness probe"""
        results = await self.run_all_checks()
        overall_status = self.get_overall_status(results)
        
        # For readiness, we're more strict - degraded is not ready
        is_ready = overall_status == ComponentStatus.HEALTHY
        
        return {
            "ready": is_ready,
            "status": overall_status.value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# Global health checker instance
health_checker = HealthChecker()


def setup_health_checks():
    """Setup health check system"""
    # Health checker is already initialized
    # Additional setup can be added here if needed
    pass
