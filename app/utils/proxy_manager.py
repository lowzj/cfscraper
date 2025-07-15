import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import httpx
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ProxyProtocol(str, Enum):
    """Supported proxy protocols"""
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


class ProxyStatus(str, Enum):
    """Proxy status states"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    TESTING = "testing"


@dataclass
class ProxyInfo:
    """Information about a proxy server"""
    host: str
    port: int
    protocol: ProxyProtocol
    username: Optional[str] = None
    password: Optional[str] = None
    status: ProxyStatus = ProxyStatus.INACTIVE
    last_used: Optional[datetime] = None
    last_checked: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    average_response_time: float = 0.0
    total_response_time: float = 0.0
    total_requests: int = 0
    
    def __post_init__(self):
        """Initialize computed fields"""
        if self.last_checked is None:
            self.last_checked = datetime.now()
    
    @property
    def url(self) -> str:
        """Get the proxy URL"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total
    
    @property
    def is_healthy(self) -> bool:
        """Check if proxy is considered healthy"""
        return (
            self.status == ProxyStatus.ACTIVE and
            self.success_rate >= 0.7 and  # At least 70% success rate
            self.failure_count < 5  # Less than 5 consecutive failures
        )
    
    def update_stats(self, success: bool, response_time: float = 0.0):
        """Update proxy statistics"""
        if success:
            self.success_count += 1
            self.status = ProxyStatus.ACTIVE
            self.last_used = datetime.now()
            if response_time > 0:
                self.total_response_time += response_time
                self.total_requests += 1
                self.average_response_time = self.total_response_time / self.total_requests
        else:
            self.failure_count += 1
            if self.failure_count >= 3:
                self.status = ProxyStatus.FAILED
        
        self.last_checked = datetime.now()


@dataclass
class ProxyPoolConfig:
    """Configuration for proxy pool"""
    health_check_interval: int = 300  # 5 minutes
    health_check_timeout: int = 10
    health_check_url: str = "http://httpbin.org/ip"
    max_failures_before_removal: int = 10
    rotation_strategy: str = "round_robin"  # round_robin, random, weighted
    enable_health_checks: bool = True
    concurrent_health_checks: int = 5


class ProxyPool:
    """Manages a pool of proxy servers with health checking and rotation"""
    
    def __init__(self, config: Optional[ProxyPoolConfig] = None):
        self.config = config or ProxyPoolConfig()
        self.proxies: List[ProxyInfo] = []
        self.current_index = 0
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def add_proxy(
        self,
        host: str,
        port: int,
        protocol: ProxyProtocol = ProxyProtocol.HTTP,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> ProxyInfo:
        """Add a proxy to the pool"""
        proxy = ProxyInfo(
            host=host,
            port=port,
            protocol=protocol,
            username=username,
            password=password
        )
        
        async with self._lock:
            self.proxies.append(proxy)
            logger.info(f"Added proxy: {proxy.url}")
        
        # Test the proxy immediately
        if self.config.enable_health_checks:
            await self._check_proxy_health(proxy)
        
        return proxy
    
    async def add_proxies_from_list(self, proxy_urls: List[str]):
        """Add multiple proxies from a list of URLs"""
        for proxy_url in proxy_urls:
            try:
                parsed = urlparse(proxy_url)
                if not parsed.hostname or not parsed.port:
                    logger.warning(f"Invalid proxy URL: {proxy_url}")
                    continue
                
                protocol = ProxyProtocol(parsed.scheme) if parsed.scheme else ProxyProtocol.HTTP
                await self.add_proxy(
                    host=parsed.hostname,
                    port=parsed.port,
                    protocol=protocol,
                    username=parsed.username,
                    password=parsed.password
                )
            except Exception as e:
                logger.error(f"Failed to add proxy {proxy_url}: {str(e)}")
    
    async def get_proxy(self) -> Optional[ProxyInfo]:
        """Get the next proxy based on rotation strategy"""
        async with self._lock:
            healthy_proxies = [p for p in self.proxies if p.is_healthy]
            
            if not healthy_proxies:
                logger.warning("No healthy proxies available")
                return None
            
            if self.config.rotation_strategy == "random":
                return random.choice(healthy_proxies)
            elif self.config.rotation_strategy == "weighted":
                return self._get_weighted_proxy(healthy_proxies)
            else:  # round_robin
                return self._get_round_robin_proxy(healthy_proxies)

    def _get_round_robin_proxy(self, healthy_proxies: List[ProxyInfo]) -> ProxyInfo:
        """Get proxy using round-robin strategy"""
        if self.current_index >= len(healthy_proxies):
            self.current_index = 0

        proxy = healthy_proxies[self.current_index]
        self.current_index += 1
        return proxy

    def _get_weighted_proxy(self, healthy_proxies: List[ProxyInfo]) -> ProxyInfo:
        """Get proxy using weighted strategy based on performance"""
        # Calculate weights based on success rate and response time
        weights = []
        for proxy in healthy_proxies:
            # Higher success rate and lower response time = higher weight
            success_weight = proxy.success_rate
            time_weight = 1.0 / (proxy.average_response_time + 0.1)  # Avoid division by zero
            weight = success_weight * time_weight
            weights.append(weight)

        # Weighted random selection
        total_weight = sum(weights)
        if total_weight == 0:
            return random.choice(healthy_proxies)

        r = random.uniform(0, total_weight)
        cumulative_weight = 0
        for i, weight in enumerate(weights):
            cumulative_weight += weight
            if r <= cumulative_weight:
                return healthy_proxies[i]

        return healthy_proxies[-1]  # Fallback

    async def report_proxy_result(self, proxy: ProxyInfo, success: bool, response_time: float = 0.0):
        """Report the result of using a proxy"""
        async with self._lock:
            proxy.update_stats(success, response_time)

            # Remove proxy if it has too many failures
            if proxy.failure_count >= self.config.max_failures_before_removal:
                self.proxies.remove(proxy)
                logger.info(f"Removed failed proxy: {proxy.url}")

    async def start_health_checks(self):
        """Start background health checking"""
        if self._running:
            return

        self._running = True
        if self.config.enable_health_checks:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info("Started proxy health checking")

    async def stop_health_checks(self):
        """Stop background health checking"""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("Stopped proxy health checking")

    async def _health_check_loop(self):
        """Background loop for health checking proxies"""
        while self._running:
            try:
                await self._check_all_proxies()
                await asyncio.sleep(self.config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {str(e)}")
                await asyncio.sleep(60)  # Wait before retrying

    async def _check_all_proxies(self):
        """Check health of all proxies"""
        if not self.proxies:
            return

        # Create semaphore to limit concurrent checks
        semaphore = asyncio.Semaphore(self.config.concurrent_health_checks)

        async def check_with_semaphore(proxy):
            async with semaphore:
                await self._check_proxy_health(proxy)

        # Check all proxies concurrently
        tasks = [check_with_semaphore(proxy) for proxy in self.proxies]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_proxy_health(self, proxy: ProxyInfo):
        """Check the health of a single proxy"""
        proxy.status = ProxyStatus.TESTING
        start_time = time.time()

        try:
            async with httpx.AsyncClient(
                proxies=proxy.url,
                timeout=self.config.health_check_timeout
            ) as client:
                response = await client.get(self.config.health_check_url)
                response_time = time.time() - start_time

                if response.status_code == 200:
                    proxy.update_stats(True, response_time)
                    logger.debug(f"Proxy {proxy.url} is healthy (response time: {response_time:.2f}s)")
                else:
                    proxy.update_stats(False)
                    logger.warning(f"Proxy {proxy.url} returned status {response.status_code}")

        except Exception as e:
            response_time = time.time() - start_time
            proxy.update_stats(False, response_time)
            logger.warning(f"Proxy {proxy.url} health check failed: {str(e)}")

    async def get_proxy_stats(self) -> Dict[str, Any]:
        """Get statistics about the proxy pool"""
        async with self._lock:
            total_proxies = len(self.proxies)
            healthy_proxies = len([p for p in self.proxies if p.is_healthy])
            active_proxies = len([p for p in self.proxies if p.status == ProxyStatus.ACTIVE])
            failed_proxies = len([p for p in self.proxies if p.status == ProxyStatus.FAILED])

            avg_response_time = 0.0
            if self.proxies:
                total_time = sum(p.average_response_time for p in self.proxies if p.average_response_time > 0)
                count = len([p for p in self.proxies if p.average_response_time > 0])
                if count > 0:
                    avg_response_time = total_time / count

            return {
                "total_proxies": total_proxies,
                "healthy_proxies": healthy_proxies,
                "active_proxies": active_proxies,
                "failed_proxies": failed_proxies,
                "average_response_time": avg_response_time,
                "rotation_strategy": self.config.rotation_strategy,
                "health_checks_enabled": self.config.enable_health_checks
            }

    async def remove_proxy(self, proxy_url: str) -> bool:
        """Remove a proxy from the pool"""
        async with self._lock:
            for i, proxy in enumerate(self.proxies):
                if proxy.url == proxy_url:
                    del self.proxies[i]
                    logger.info(f"Removed proxy: {proxy_url}")
                    return True
            return False

    async def clear_proxies(self):
        """Remove all proxies from the pool"""
        async with self._lock:
            self.proxies.clear()
            self.current_index = 0
            logger.info("Cleared all proxies from pool")


# User-Agent rotation functionality
class UserAgentRotator:
    """Manages user-agent rotation with realistic browser fingerprints"""

    # Common user agents for different browsers and platforms
    USER_AGENTS = [
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",

        # Chrome on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",

        # Chrome on Linux
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",

        # Firefox on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",

        # Firefox on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",

        # Safari on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",

        # Edge on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    ]

    # Window sizes that match common screen resolutions
    WINDOW_SIZES = [
        "1920,1080",  # Full HD
        "1366,768",   # Common laptop
        "1440,900",   # MacBook Air
        "1536,864",   # Surface Pro
        "1280,720",   # HD
        "1600,900",   # 16:9 widescreen
        "1680,1050",  # 16:10 widescreen
        "2560,1440",  # QHD
    ]

    def __init__(self, strategy: str = "random"):
        """
        Initialize user agent rotator

        Args:
            strategy: Rotation strategy ('random', 'round_robin')
        """
        self.strategy = strategy
        self.current_index = 0
        self._lock = asyncio.Lock()

    async def get_user_agent(self) -> str:
        """Get a user agent based on rotation strategy"""
        async with self._lock:
            if self.strategy == "random":
                return random.choice(self.USER_AGENTS)
            else:  # round_robin
                user_agent = self.USER_AGENTS[self.current_index]
                self.current_index = (self.current_index + 1) % len(self.USER_AGENTS)
                return user_agent

    async def get_window_size(self) -> str:
        """Get a random window size"""
        return random.choice(self.WINDOW_SIZES)

    async def get_browser_fingerprint(self) -> Dict[str, str]:
        """Get a complete browser fingerprint with user agent and window size"""
        user_agent = await self.get_user_agent()
        window_size = await self.get_window_size()

        # Extract browser info from user agent
        browser_info = self._parse_user_agent(user_agent)

        return {
            "user_agent": user_agent,
            "window_size": window_size,
            "browser": browser_info.get("browser", "Chrome"),
            "platform": browser_info.get("platform", "Windows"),
            "version": browser_info.get("version", "120.0.0.0")
        }

    def _parse_user_agent(self, user_agent: str) -> Dict[str, str]:
        """Parse user agent string to extract browser information"""
        info = {}

        if "Chrome" in user_agent:
            info["browser"] = "Chrome"
            # Extract Chrome version
            import re
            match = re.search(r"Chrome/(\d+\.\d+\.\d+\.\d+)", user_agent)
            if match:
                info["version"] = match.group(1)
        elif "Firefox" in user_agent:
            info["browser"] = "Firefox"
            match = re.search(r"Firefox/(\d+\.\d+)", user_agent)
            if match:
                info["version"] = match.group(1)
        elif "Safari" in user_agent and "Chrome" not in user_agent:
            info["browser"] = "Safari"
            match = re.search(r"Version/(\d+\.\d+)", user_agent)
            if match:
                info["version"] = match.group(1)
        elif "Edg" in user_agent:
            info["browser"] = "Edge"
            match = re.search(r"Edg/(\d+\.\d+\.\d+\.\d+)", user_agent)
            if match:
                info["version"] = match.group(1)

        if "Windows" in user_agent:
            info["platform"] = "Windows"
        elif "Macintosh" in user_agent or "Mac OS X" in user_agent:
            info["platform"] = "macOS"
        elif "Linux" in user_agent:
            info["platform"] = "Linux"

        return info

    def add_custom_user_agent(self, user_agent: str):
        """Add a custom user agent to the rotation pool"""
        if user_agent not in self.USER_AGENTS:
            self.USER_AGENTS.append(user_agent)
            logger.info(f"Added custom user agent: {user_agent[:50]}...")


# Global instances for easy access
_proxy_pool: Optional[ProxyPool] = None
_user_agent_rotator: Optional[UserAgentRotator] = None


def get_proxy_pool() -> ProxyPool:
    """Get the global proxy pool instance"""
    global _proxy_pool
    if _proxy_pool is None:
        _proxy_pool = ProxyPool()
    return _proxy_pool


def get_user_agent_rotator() -> UserAgentRotator:
    """Get the global user agent rotator instance"""
    global _user_agent_rotator
    if _user_agent_rotator is None:
        _user_agent_rotator = UserAgentRotator()
    return _user_agent_rotator


async def initialize_proxy_system():
    """Initialize the proxy system with configuration from settings"""
    from app.core.config import settings

    # Initialize proxy pool
    proxy_pool = get_proxy_pool()
    proxy_pool.config.rotation_strategy = settings.proxy_rotation_strategy
    proxy_pool.config.enable_health_checks = settings.proxy_health_check_enabled
    proxy_pool.config.health_check_interval = settings.proxy_health_check_interval
    proxy_pool.config.health_check_timeout = settings.proxy_health_check_timeout
    proxy_pool.config.health_check_url = settings.proxy_health_check_url
    proxy_pool.config.max_failures_before_removal = settings.proxy_max_failures

    # Add proxies from configuration
    if settings.proxy_list:
        await proxy_pool.add_proxies_from_list(settings.proxy_list)
        logger.info(f"Added {len(settings.proxy_list)} proxies from configuration")

    # Start health checks
    await proxy_pool.start_health_checks()

    # Initialize user agent rotator
    user_agent_rotator = get_user_agent_rotator()
    user_agent_rotator.strategy = settings.user_agent_rotation_strategy

    # Add custom user agents
    for user_agent in settings.custom_user_agents:
        user_agent_rotator.add_custom_user_agent(user_agent)

    logger.info("Proxy system initialized successfully")


async def shutdown_proxy_system():
    """Shutdown the proxy system"""
    global _proxy_pool
    if _proxy_pool:
        await _proxy_pool.stop_health_checks()
        logger.info("Proxy system shutdown complete")
