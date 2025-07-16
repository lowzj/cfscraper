import logging
from typing import Callable, Optional
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
from datetime import datetime

from app.utils.rate_limiter import (
    get_rate_limiter, get_rate_limit_monitor,
    UserTier, RateLimitType
)
from app.security.audit import log_rate_limit_exceeded

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting"""
    
    def __init__(
        self,
        app,
        enabled: bool = True,
        default_rule_id: str = "default_0",
        include_headers: bool = True
    ):
        super().__init__(app)
        self.enabled = enabled
        self.default_rule_id = default_rule_id
        self.include_headers = include_headers
        self.rate_limiter = get_rate_limiter()
        self.monitor = get_rate_limit_monitor()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting"""
        if not self.enabled:
            return await call_next(request)
        
        # Skip rate limiting for certain paths
        if self._should_skip_rate_limiting(request):
            return await call_next(request)
        
        # Extract client information
        client_ip = self._get_client_ip(request)
        user_tier = self._get_user_tier(request)
        bypass_token = self._get_bypass_token(request)
        endpoint = str(request.url.path)
        
        # Determine rate limit rule
        rule_id = self._get_rule_id(request)
        
        # Check rate limit
        try:
            result = await self.rate_limiter.check_rate_limit(
                identifier=client_ip,
                rule_id=rule_id,
                ip_address=client_ip,
                user_tier=user_tier,
                bypass_token=bypass_token
            )
            
            if not result.allowed:
                # Record violation
                await self.monitor.record_violation(
                    identifier=client_ip,
                    rule_id=rule_id,
                    ip_address=client_ip,
                    endpoint=endpoint,
                    user_agent=request.headers.get("user-agent")
                )

                # Log security event
                log_rate_limit_exceeded(
                    ip_address=client_ip,
                    user_agent=request.headers.get("user-agent", "unknown"),
                    endpoint=endpoint,
                    limit_type=rule_id,
                    request_id=request.headers.get("X-Request-ID")
                )

                # Return rate limit exceeded response
                return self._create_rate_limit_response(result)
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers
            if self.include_headers:
                self._add_rate_limit_headers(response, result)
            
            return response
            
        except Exception as e:
            logger.error(f"Rate limiting error: {str(e)}")
            # Fail open - allow request if rate limiter fails
            return await call_next(request)
    
    def _should_skip_rate_limiting(self, request: Request) -> bool:
        """Check if rate limiting should be skipped for this request"""
        # Skip paths
        skip_paths = [
            "/health",
            "/docs",
            "/openapi.json",
            "/favicon.ico"
        ]

        path = str(request.url.path)
        if any(path.startswith(skip_path) for skip_path in skip_paths):
            return True

        # Check IP whitelist
        client_ip = self._get_client_ip(request)
        from app.core.config import settings
        if client_ip in settings.admin_ips:
            return True

        # Check bypass tokens
        bypass_token = self._get_bypass_token(request)
        if bypass_token and bypass_token in settings.rate_limit_bypass_tokens:
            return True

        return False
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address"""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fallback to client host
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _get_user_tier(self, request: Request) -> UserTier:
        """Determine user tier from request"""
        # Check for tier in headers (for API keys, etc.)
        tier_header = request.headers.get("x-user-tier")
        if tier_header:
            try:
                return UserTier(tier_header.lower())
            except ValueError:
                pass
        
        # Check for admin token
        auth_header = request.headers.get("authorization")
        if auth_header and "admin" in auth_header.lower():
            return UserTier.ADMIN
        
        # Default to free tier
        return UserTier.FREE
    
    def _get_bypass_token(self, request: Request) -> Optional[str]:
        """Extract bypass token from request"""
        return request.headers.get("x-rate-limit-bypass")
    
    def _get_rule_id(self, request: Request) -> str:
        """Determine which rate limit rule to apply"""
        path = str(request.url.path)
        
        # Map endpoints to specific rules
        endpoint_rules = {
            "/api/v1/scrape": "scrape_endpoint",
            "/api/v1/export": "export_endpoint",
            "/api/v1/jobs": "jobs_endpoint"
        }
        
        for endpoint, rule_id in endpoint_rules.items():
            if path.startswith(endpoint):
                return rule_id
        
        return self.default_rule_id
    
    def _create_rate_limit_response(self, result) -> JSONResponse:
        """Create rate limit exceeded response"""
        headers = {}
        
        if self.include_headers:
            headers.update({
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(int(result.reset_time.timestamp())),
            })
            
            if result.retry_after:
                headers["Retry-After"] = str(result.retry_after)
        
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": (
                    f"Too many requests. Try again in {result.retry_after} seconds."
                    if result.retry_after is not None
                    else "Too many requests. Rate limit exceeded."
                ),
                "details": {
                    "limit": result.limit,
                    "remaining": result.remaining,
                    "reset_time": result.reset_time.isoformat(),
                    "retry_after": result.retry_after
                }
            },
            headers=headers
        )
    
    def _add_rate_limit_headers(self, response: Response, result) -> None:
        """Add rate limit headers to response"""
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(int(result.reset_time.timestamp()))
        
        if result.burst_remaining > 0:
            response.headers["X-RateLimit-Burst-Remaining"] = str(result.burst_remaining)


class RateLimitConfig:
    """Configuration for rate limiting middleware"""
    
    def __init__(
        self,
        enabled: bool = True,
        redis_url: str = "redis://localhost:6379",
        default_requests_per_minute: int = 60,
        default_requests_per_hour: int = 1000,
        include_headers: bool = True,
        default_rule_id: str = "default_0",
        admin_ips: list = None,
        bypass_tokens: list = None
    ):
        self.enabled = enabled
        self.redis_url = redis_url
        self.default_requests_per_minute = default_requests_per_minute
        self.default_requests_per_hour = default_requests_per_hour
        self.include_headers = include_headers
        self.default_rule_id = default_rule_id
        self.admin_ips = admin_ips or []
        self.bypass_tokens = bypass_tokens or []


def setup_rate_limiting(app, config: Optional[RateLimitConfig] = None):
    """Setup rate limiting middleware for FastAPI app"""
    if config is None:
        config = RateLimitConfig()
    
    if not config.enabled:
        logger.info("Rate limiting disabled")
        return
    
    # Add middleware
    app.add_middleware(
        RateLimitMiddleware,
        enabled=config.enabled,
        default_rule_id=config.default_rule_id,
        include_headers=config.include_headers
    )
    
    logger.info("Rate limiting middleware added to FastAPI app")


# Rate limit decorator for specific endpoints
def rate_limit(
    requests_per_minute: int = 60,
    requests_per_hour: int = 1000,
    rule_id: str = None
):
    """Decorator for applying rate limits to specific endpoints"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # This would need to be implemented to work with the specific endpoint
            # For now, it's a placeholder
            return await func(*args, **kwargs)
        return wrapper
    return decorator
