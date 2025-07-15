import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)


class RateLimitType(str, Enum):
    """Types of rate limiting"""
    PER_IP = "per_ip"
    PER_ENDPOINT = "per_endpoint"
    PER_USER = "per_user"
    GLOBAL = "global"


class UserTier(str, Enum):
    """User tiers for priority queuing"""
    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"
    ADMIN = "admin"


@dataclass
class RateLimitRule:
    """Configuration for a rate limit rule"""
    limit_type: RateLimitType
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    burst_limit: int = 0  # Additional requests allowed in burst
    burst_window_seconds: int = 60  # Time window for burst
    user_tier: Optional[UserTier] = None
    endpoint_pattern: Optional[str] = None
    enabled: bool = True


@dataclass
class RateLimitResult:
    """Result of rate limit check"""
    allowed: bool
    remaining: int
    reset_time: datetime
    retry_after: Optional[int] = None
    limit: int = 0
    current_usage: int = 0
    burst_remaining: int = 0


class RedisRateLimiter:
    """Redis-based rate limiter with sliding window algorithm"""
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url
        self.redis_client = None
        self._rules: Dict[str, RateLimitRule] = {}
        self._admin_ips: set = set()
        self._bypass_tokens: set = set()
    
    async def _get_redis_client(self):
        """Get Redis client (lazy initialization)"""
        if self.redis_client is None:
            try:
                import redis.asyncio as redis
                self.redis_client = redis.from_url(self.redis_url or "redis://localhost:6379")
                await self.redis_client.ping()
                logger.info("Redis rate limiter connected")
            except ImportError:
                logger.error("Redis not available for rate limiting")
                raise
            except Exception as e:
                logger.error(f"Failed to connect to Redis for rate limiting: {str(e)}")
                raise
        return self.redis_client
    
    def add_rule(self, rule_id: str, rule: RateLimitRule):
        """Add a rate limiting rule"""
        self._rules[rule_id] = rule
        logger.info(f"Added rate limit rule: {rule_id}")
    
    def remove_rule(self, rule_id: str):
        """Remove a rate limiting rule"""
        if rule_id in self._rules:
            del self._rules[rule_id]
            logger.info(f"Removed rate limit rule: {rule_id}")
    
    def add_admin_ip(self, ip: str):
        """Add IP to admin bypass list"""
        self._admin_ips.add(ip)
        logger.info(f"Added admin IP: {ip}")
    
    def add_bypass_token(self, token: str):
        """Add bypass token"""
        self._bypass_tokens.add(token)
        logger.info("Added bypass token")
    
    async def check_rate_limit(
        self,
        identifier: str,
        rule_id: str,
        ip_address: str = None,
        user_tier: UserTier = UserTier.FREE,
        bypass_token: str = None
    ) -> RateLimitResult:
        """
        Check if request is within rate limits
        
        Args:
            identifier: Unique identifier for the request (IP, user ID, etc.)
            rule_id: ID of the rate limiting rule to apply
            ip_address: IP address for admin bypass check
            user_tier: User tier for priority handling
            bypass_token: Token for bypassing rate limits
            
        Returns:
            RateLimitResult with limit check results
        """
        # Check for admin bypass
        if ip_address and ip_address in self._admin_ips:
            return RateLimitResult(
                allowed=True,
                remaining=999999,
                reset_time=datetime.now() + timedelta(hours=1),
                limit=999999,
                current_usage=0,
                burst_remaining=999999
            )
        
        # Check for bypass token
        if bypass_token and bypass_token in self._bypass_tokens:
            return RateLimitResult(
                allowed=True,
                remaining=999999,
                reset_time=datetime.now() + timedelta(hours=1),
                limit=999999,
                current_usage=0,
                burst_remaining=999999
            )
        
        # Get rule
        if rule_id not in self._rules:
            logger.warning(f"Rate limit rule not found: {rule_id}")
            return RateLimitResult(
                allowed=True,
                remaining=1000,
                reset_time=datetime.now() + timedelta(hours=1),
                limit=1000,
                current_usage=0
            )
        
        rule = self._rules[rule_id]
        
        if not rule.enabled:
            return RateLimitResult(
                allowed=True,
                remaining=1000,
                reset_time=datetime.now() + timedelta(hours=1),
                limit=1000,
                current_usage=0
            )
        
        # Apply user tier multipliers
        tier_multipliers = {
            UserTier.FREE: 1.0,
            UserTier.PREMIUM: 2.0,
            UserTier.ENTERPRISE: 5.0,
            UserTier.ADMIN: 10.0
        }
        
        multiplier = tier_multipliers.get(user_tier, 1.0)
        effective_limit_per_minute = int(rule.requests_per_minute * multiplier)
        effective_limit_per_hour = int(rule.requests_per_hour * multiplier)
        effective_burst_limit = int(rule.burst_limit * multiplier)
        
        try:
            redis_client = await self._get_redis_client()
            
            # Check minute window
            minute_result = await self._check_sliding_window(
                redis_client,
                f"{rule_id}:{identifier}:minute",
                effective_limit_per_minute,
                60
            )
            
            # Check hour window
            hour_result = await self._check_sliding_window(
                redis_client,
                f"{rule_id}:{identifier}:hour",
                effective_limit_per_hour,
                3600
            )
            
            # Check burst limit if configured
            burst_result = None
            if effective_burst_limit > 0:
                burst_result = await self._check_sliding_window(
                    redis_client,
                    f"{rule_id}:{identifier}:burst",
                    effective_burst_limit,
                    rule.burst_window_seconds
                )
            
            # Determine if request is allowed
            allowed = minute_result["allowed"] and hour_result["allowed"]
            if burst_result:
                allowed = allowed or burst_result["allowed"]
            
            # Calculate remaining and reset time
            remaining = min(minute_result["remaining"], hour_result["remaining"])
            reset_time = max(minute_result["reset_time"], hour_result["reset_time"])
            
            # Calculate retry after if blocked
            retry_after = None
            if not allowed:
                retry_after = int((reset_time - datetime.now()).total_seconds())
            
            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_time=reset_time,
                retry_after=retry_after,
                limit=min(effective_limit_per_minute, effective_limit_per_hour),
                current_usage=max(minute_result["current"], hour_result["current"]),
                burst_remaining=burst_result["remaining"] if burst_result else 0
            )
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {str(e)}")
            # Fail open - allow request if rate limiter is down
            return RateLimitResult(
                allowed=True,
                remaining=1000,
                reset_time=datetime.now() + timedelta(hours=1),
                limit=1000,
                current_usage=0
            )
    
    async def _check_sliding_window(
        self,
        redis_client,
        key: str,
        limit: int,
        window_seconds: int
    ) -> Dict[str, Any]:
        """Check sliding window rate limit"""
        now = time.time()
        window_start = now - window_seconds
        
        # Use Redis pipeline for atomic operations
        pipe = redis_client.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count current entries
        pipe.zcard(key)
        
        # Add current request
        pipe.zadd(key, {str(now): now})
        
        # Set expiration
        pipe.expire(key, window_seconds + 1)
        
        results = await pipe.execute()
        current_count = results[1]
        
        allowed = current_count < limit
        remaining = max(0, limit - current_count - 1)
        reset_time = datetime.fromtimestamp(now + window_seconds)
        
        return {
            "allowed": allowed,
            "remaining": remaining,
            "reset_time": reset_time,
            "current": current_count
        }
    
    async def get_rate_limit_stats(self, identifier: str, rule_id: str) -> Dict[str, Any]:
        """Get current rate limit statistics for an identifier"""
        try:
            redis_client = await self._get_redis_client()
            
            stats = {}
            for window, seconds in [("minute", 60), ("hour", 3600)]:
                key = f"{rule_id}:{identifier}:{window}"
                count = await redis_client.zcard(key)
                stats[window] = {
                    "current_usage": count,
                    "window_seconds": seconds
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get rate limit stats: {str(e)}")
            return {}
    
    async def reset_rate_limit(self, identifier: str, rule_id: str):
        """Reset rate limits for an identifier"""
        try:
            redis_client = await self._get_redis_client()
            
            keys_to_delete = [
                f"{rule_id}:{identifier}:minute",
                f"{rule_id}:{identifier}:hour",
                f"{rule_id}:{identifier}:burst"
            ]
            
            await redis_client.delete(*keys_to_delete)
            logger.info(f"Reset rate limits for {identifier} on rule {rule_id}")
            
        except Exception as e:
            logger.error(f"Failed to reset rate limits: {str(e)}")


# Global rate limiter instance
_rate_limiter: Optional[RedisRateLimiter] = None


def get_rate_limiter() -> RedisRateLimiter:
    """Get the global rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        from app.core.config import settings
        _rate_limiter = RedisRateLimiter(settings.redis_url)
    return _rate_limiter


class RateLimitMonitor:
    """Monitors rate limit violations and provides alerting"""

    def __init__(self):
        self._violations: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._alert_thresholds = {
            "violations_per_minute": 10,
            "violations_per_hour": 100
        }

    async def record_violation(
        self,
        identifier: str,
        rule_id: str,
        ip_address: str,
        endpoint: str,
        user_agent: str = None
    ):
        """Record a rate limit violation"""
        violation = {
            "identifier": identifier,
            "rule_id": rule_id,
            "ip_address": ip_address,
            "endpoint": endpoint,
            "user_agent": user_agent,
            "timestamp": datetime.now(),
            "severity": self._calculate_severity(identifier, rule_id)
        }

        async with self._lock:
            self._violations.append(violation)
            # Keep only last 1000 violations
            if len(self._violations) > 1000:
                self._violations = self._violations[-1000:]

        logger.warning(f"Rate limit violation: {identifier} on {endpoint}")

        # Check if alerting is needed
        await self._check_alert_conditions()

    def _calculate_severity(self, identifier: str, rule_id: str) -> str:
        """Calculate severity of violation"""
        # Count recent violations from same identifier
        now = datetime.now()
        recent_violations = [
            v for v in self._violations
            if v["identifier"] == identifier and
               (now - v["timestamp"]).total_seconds() < 3600  # Last hour
        ]

        if len(recent_violations) > 50:
            return "high"
        elif len(recent_violations) > 10:
            return "medium"
        else:
            return "low"

    async def _check_alert_conditions(self):
        """Check if alert conditions are met"""
        now = datetime.now()

        # Count violations in last minute
        minute_violations = [
            v for v in self._violations
            if (now - v["timestamp"]).total_seconds() < 60
        ]

        # Count violations in last hour
        hour_violations = [
            v for v in self._violations
            if (now - v["timestamp"]).total_seconds() < 3600
        ]

        if len(minute_violations) >= self._alert_thresholds["violations_per_minute"]:
            await self._send_alert("high_violation_rate_minute", len(minute_violations))

        if len(hour_violations) >= self._alert_thresholds["violations_per_hour"]:
            await self._send_alert("high_violation_rate_hour", len(hour_violations))

    async def _send_alert(self, alert_type: str, count: int):
        """Send alert (placeholder for actual alerting system)"""
        logger.critical(f"RATE LIMIT ALERT: {alert_type} - {count} violations")
        # Here you would integrate with your alerting system
        # (email, Slack, PagerDuty, etc.)

    async def get_violation_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get violation statistics"""
        now = datetime.now()
        cutoff = now - timedelta(hours=hours)

        recent_violations = [
            v for v in self._violations
            if v["timestamp"] >= cutoff
        ]

        # Group by IP
        ip_stats = {}
        for violation in recent_violations:
            ip = violation["ip_address"]
            if ip not in ip_stats:
                ip_stats[ip] = 0
            ip_stats[ip] += 1

        # Group by endpoint
        endpoint_stats = {}
        for violation in recent_violations:
            endpoint = violation["endpoint"]
            if endpoint not in endpoint_stats:
                endpoint_stats[endpoint] = 0
            endpoint_stats[endpoint] += 1

        return {
            "total_violations": len(recent_violations),
            "unique_ips": len(ip_stats),
            "top_violating_ips": sorted(ip_stats.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_violated_endpoints": sorted(endpoint_stats.items(), key=lambda x: x[1], reverse=True)[:10],
            "time_period_hours": hours
        }


# Global monitor instance
_rate_limit_monitor: Optional[RateLimitMonitor] = None


def get_rate_limit_monitor() -> RateLimitMonitor:
    """Get the global rate limit monitor instance"""
    global _rate_limit_monitor
    if _rate_limit_monitor is None:
        _rate_limit_monitor = RateLimitMonitor()
    return _rate_limit_monitor


async def initialize_rate_limiting():
    """Initialize rate limiting system with default rules"""
    from app.core.config import settings

    rate_limiter = get_rate_limiter()

    # Add default rules
    default_rules = [
        RateLimitRule(
            limit_type=RateLimitType.PER_IP,
            requests_per_minute=60,
            requests_per_hour=1000,
            requests_per_day=10000,
            burst_limit=10,
            burst_window_seconds=60
        ),
        RateLimitRule(
            limit_type=RateLimitType.PER_ENDPOINT,
            requests_per_minute=100,
            requests_per_hour=2000,
            requests_per_day=20000,
            burst_limit=20,
            endpoint_pattern="/api/v1/scrape/*"
        )
    ]

    for i, rule in enumerate(default_rules):
        rate_limiter.add_rule(f"default_{i}", rule)

    # Add admin IPs if configured
    admin_ips = getattr(settings, 'admin_ips', [])
    for ip in admin_ips:
        rate_limiter.add_admin_ip(ip)

    logger.info("Rate limiting system initialized")
