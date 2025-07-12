import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)


class DelayPattern(str, Enum):
    """Delay pattern types for mimicking human behavior"""
    HUMAN_LIKE = "human_like"
    RANDOM = "random"
    FIXED = "fixed"
    EXPONENTIAL_BACKOFF = "exponential_backoff"


@dataclass
class StealthConfig:
    """Configuration for stealth features"""
    enable_header_randomization: bool = True
    enable_viewport_randomization: bool = True
    enable_intelligent_delays: bool = True
    delay_pattern: DelayPattern = DelayPattern.HUMAN_LIKE
    min_delay: float = 1.0
    max_delay: float = 5.0
    enable_cookie_management: bool = True
    enable_js_detection_bypass: bool = True
    enable_webdriver_detection_bypass: bool = True


class HeaderRandomizer:
    """Manages randomization of HTTP headers to avoid detection"""
    
    # Common browser headers that vary between requests
    ACCEPT_HEADERS = [
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    ]
    
    ACCEPT_LANGUAGE_HEADERS = [
        "en-US,en;q=0.9",
        "en-US,en;q=0.8",
        "en-GB,en;q=0.9",
        "en-US,en;q=0.9,es;q=0.8",
        "en-US,en;q=0.5",
    ]
    
    ACCEPT_ENCODING_HEADERS = [
        "gzip, deflate, br",
        "gzip, deflate",
        "gzip, deflate, br, zstd",
    ]
    
    DNT_VALUES = ["1", "0"]
    
    UPGRADE_INSECURE_REQUESTS = ["1"]
    
    SEC_FETCH_SITE = ["none", "same-origin", "same-site", "cross-site"]
    SEC_FETCH_MODE = ["navigate", "cors", "no-cors", "websocket"]
    SEC_FETCH_USER = ["?1"]
    SEC_FETCH_DEST = ["document", "empty", "image", "script", "style"]
    
    def __init__(self):
        self._lock = asyncio.Lock()
    
    async def get_randomized_headers(self, base_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Generate randomized headers"""
        async with self._lock:
            headers = base_headers.copy() if base_headers else {}
            
            # Add common headers with randomization
            headers.update({
                "Accept": random.choice(self.ACCEPT_HEADERS),
                "Accept-Language": random.choice(self.ACCEPT_LANGUAGE_HEADERS),
                "Accept-Encoding": random.choice(self.ACCEPT_ENCODING_HEADERS),
                "DNT": random.choice(self.DNT_VALUES),
                "Upgrade-Insecure-Requests": random.choice(self.UPGRADE_INSECURE_REQUESTS),
                "Sec-Fetch-Site": random.choice(self.SEC_FETCH_SITE),
                "Sec-Fetch-Mode": random.choice(self.SEC_FETCH_MODE),
                "Sec-Fetch-User": random.choice(self.SEC_FETCH_USER),
                "Sec-Fetch-Dest": random.choice(self.SEC_FETCH_DEST),
            })
            
            # Randomly add or remove some optional headers
            if random.random() > 0.5:
                headers["Cache-Control"] = random.choice(["no-cache", "max-age=0"])
            
            if random.random() > 0.7:
                headers["Pragma"] = "no-cache"
            
            # Add connection header variation
            headers["Connection"] = random.choice(["keep-alive", "close"])
            
            return headers


class ViewportRandomizer:
    """Manages browser viewport and window size randomization"""
    
    # Common screen resolutions and viewport sizes
    VIEWPORTS = [
        {"width": 1920, "height": 1080, "device_scale_factor": 1},
        {"width": 1366, "height": 768, "device_scale_factor": 1},
        {"width": 1440, "height": 900, "device_scale_factor": 1},
        {"width": 1536, "height": 864, "device_scale_factor": 1},
        {"width": 1280, "height": 720, "device_scale_factor": 1},
        {"width": 1600, "height": 900, "device_scale_factor": 1},
        {"width": 1680, "height": 1050, "device_scale_factor": 1},
        {"width": 2560, "height": 1440, "device_scale_factor": 1},
        # High DPI displays
        {"width": 1920, "height": 1080, "device_scale_factor": 1.25},
        {"width": 1366, "height": 768, "device_scale_factor": 1.5},
    ]
    
    def __init__(self):
        self._lock = asyncio.Lock()
    
    async def get_random_viewport(self) -> Dict[str, Any]:
        """Get a random viewport configuration"""
        async with self._lock:
            viewport = random.choice(self.VIEWPORTS).copy()
            
            # Add small random variations to make it more realistic
            viewport["width"] += random.randint(-50, 50)
            viewport["height"] += random.randint(-30, 30)
            
            # Ensure minimum sizes
            viewport["width"] = max(800, viewport["width"])
            viewport["height"] = max(600, viewport["height"])
            
            return viewport


class DelayManager:
    """Manages intelligent delays between requests"""
    
    def __init__(self, config: StealthConfig):
        self.config = config
        self.last_request_time = None
        self.request_count = 0
        self._lock = asyncio.Lock()
    
    async def wait_before_request(self):
        """Wait appropriate time before making a request"""
        if not self.config.enable_intelligent_delays:
            return
        
        async with self._lock:
            now = time.time()
            
            if self.last_request_time is not None:
                elapsed = now - self.last_request_time
                delay = self._calculate_delay()
                
                if elapsed < delay:
                    wait_time = delay - elapsed
                    logger.debug(f"Waiting {wait_time:.2f}s before next request")
                    await asyncio.sleep(wait_time)
            
            self.last_request_time = time.time()
            self.request_count += 1
    
    def _calculate_delay(self) -> float:
        """Calculate delay based on configured pattern"""
        if self.config.delay_pattern == DelayPattern.FIXED:
            return self.config.min_delay
        
        elif self.config.delay_pattern == DelayPattern.RANDOM:
            return random.uniform(self.config.min_delay, self.config.max_delay)
        
        elif self.config.delay_pattern == DelayPattern.EXPONENTIAL_BACKOFF:
            # Exponential backoff with jitter
            base_delay = min(self.config.min_delay * (2 ** min(self.request_count, 10)), self.config.max_delay)
            jitter = random.uniform(0.8, 1.2)
            return base_delay * jitter
        
        else:  # HUMAN_LIKE
            return self._human_like_delay()
    
    def _human_like_delay(self) -> float:
        """Generate human-like delay patterns"""
        # Most humans have delays between 1-3 seconds with occasional longer pauses
        if random.random() < 0.1:  # 10% chance of longer pause
            return random.uniform(5.0, 15.0)
        elif random.random() < 0.3:  # 30% chance of medium pause
            return random.uniform(3.0, 7.0)
        else:  # 60% chance of short pause
            return random.uniform(1.0, 3.0)


class StealthManager:
    """Main stealth manager that coordinates all anti-detection features"""
    
    def __init__(self, config: Optional[StealthConfig] = None):
        self.config = config or StealthConfig()
        self.header_randomizer = HeaderRandomizer()
        self.viewport_randomizer = ViewportRandomizer()
        self.delay_manager = DelayManager(self.config)
        self._session_cookies: Dict[str, Any] = {}
    
    async def prepare_request(self, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Prepare headers for a request with anti-detection features"""
        # Apply intelligent delays
        await self.delay_manager.wait_before_request()
        
        # Randomize headers if enabled
        if self.config.enable_header_randomization:
            return await self.header_randomizer.get_randomized_headers(headers)
        
        return headers or {}
    
    async def get_viewport_config(self) -> Dict[str, Any]:
        """Get viewport configuration for browser setup"""
        if self.config.enable_viewport_randomization:
            return await self.viewport_randomizer.get_random_viewport()
        
        # Default viewport
        return {"width": 1920, "height": 1080, "device_scale_factor": 1}
    
    def store_cookies(self, domain: str, cookies: Dict[str, Any]):
        """Store cookies for session management"""
        if self.config.enable_cookie_management:
            self._session_cookies[domain] = cookies
            logger.debug(f"Stored cookies for domain: {domain}")
    
    def get_cookies(self, domain: str) -> Dict[str, Any]:
        """Get stored cookies for a domain"""
        if self.config.enable_cookie_management:
            return self._session_cookies.get(domain, {})
        return {}
    
    def clear_cookies(self, domain: Optional[str] = None):
        """Clear stored cookies"""
        if domain:
            self._session_cookies.pop(domain, None)
            logger.debug(f"Cleared cookies for domain: {domain}")
        else:
            self._session_cookies.clear()
            logger.debug("Cleared all cookies")


# Global stealth manager instance
_stealth_manager: Optional[StealthManager] = None


def get_stealth_manager() -> StealthManager:
    """Get the global stealth manager instance"""
    global _stealth_manager
    if _stealth_manager is None:
        _stealth_manager = StealthManager()
    return _stealth_manager


def configure_stealth_manager(config: StealthConfig):
    """Configure the global stealth manager"""
    global _stealth_manager
    _stealth_manager = StealthManager(config)


class CaptchaDetector:
    """Detects various types of captchas and bot detection mechanisms"""

    # Common captcha indicators
    CAPTCHA_INDICATORS = [
        # Text-based indicators
        "captcha", "recaptcha", "hcaptcha", "cloudflare",
        "verify you are human", "prove you're not a robot",
        "security check", "bot detection", "access denied",

        # CSS selectors for common captcha services
        ".g-recaptcha", ".h-captcha", ".cf-challenge",
        "#captcha", ".captcha", "[data-captcha]",

        # Cloudflare specific
        ".cf-browser-verification", ".cf-checking-browser",
        ".cf-under-attack", ".cf-error-details",
    ]

    # JavaScript detection patterns
    JS_DETECTION_PATTERNS = [
        "webdriver", "selenium", "phantomjs", "chromedriver",
        "__webdriver_script_fn", "__selenium_unwrapped",
        "__webdriver_evaluate", "__selenium_evaluate",
        "__fxdriver_evaluate", "__driver_unwrapped",
    ]

    def __init__(self):
        self._lock = asyncio.Lock()

    async def detect_captcha(self, content: str, url: str = "") -> Dict[str, Any]:
        """
        Detect if the page contains a captcha or bot detection

        Args:
            content: HTML content of the page
            url: URL of the page (optional)

        Returns:
            Dictionary with detection results
        """
        async with self._lock:
            detection_result = {
                "has_captcha": False,
                "captcha_type": None,
                "confidence": 0.0,
                "indicators": [],
                "suggested_action": "continue"
            }

            content_lower = content.lower()
            indicators_found = []

            # Check for text-based indicators
            for indicator in self.CAPTCHA_INDICATORS:
                if indicator.lower() in content_lower:
                    indicators_found.append(indicator)

            # Check for specific captcha services
            captcha_type = None
            if any("recaptcha" in ind for ind in indicators_found):
                captcha_type = "recaptcha"
            elif any("hcaptcha" in ind for ind in indicators_found):
                captcha_type = "hcaptcha"
            elif any("cloudflare" in ind for ind in indicators_found):
                captcha_type = "cloudflare"
            elif any("captcha" in ind for ind in indicators_found):
                captcha_type = "generic"

            # Calculate confidence based on number of indicators
            confidence = min(len(indicators_found) * 0.3, 1.0)

            # Determine if captcha is present
            has_captcha = len(indicators_found) > 0 or confidence > 0.5

            # Suggest action based on detection
            suggested_action = "continue"
            if has_captcha:
                if captcha_type == "cloudflare":
                    suggested_action = "wait_and_retry"
                elif captcha_type in ["recaptcha", "hcaptcha"]:
                    suggested_action = "manual_intervention"
                else:
                    suggested_action = "retry_with_delay"

            detection_result.update({
                "has_captcha": has_captcha,
                "captcha_type": captcha_type,
                "confidence": confidence,
                "indicators": indicators_found,
                "suggested_action": suggested_action
            })

            if has_captcha:
                logger.warning(f"Captcha detected on {url}: {captcha_type} (confidence: {confidence:.2f})")

            return detection_result

    async def detect_js_detection(self, content: str) -> bool:
        """Detect JavaScript-based bot detection"""
        content_lower = content.lower()

        for pattern in self.JS_DETECTION_PATTERNS:
            if pattern.lower() in content_lower:
                logger.warning(f"JavaScript bot detection pattern found: {pattern}")
                return True

        return False


class JSBypassManager:
    """Manages JavaScript execution and bot detection bypass"""

    # JavaScript code to inject for bypassing detection
    STEALTH_SCRIPTS = [
        # Remove webdriver property
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
        """,

        # Override plugins
        """
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        """,

        # Override languages
        """
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        """,

        # Override permissions
        """
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        """,
    ]

    def __init__(self):
        self._lock = asyncio.Lock()

    async def get_stealth_scripts(self) -> List[str]:
        """Get JavaScript scripts for stealth mode"""
        async with self._lock:
            return self.STEALTH_SCRIPTS.copy()

    async def inject_stealth_scripts(self, driver):
        """Inject stealth scripts into a Selenium driver"""
        try:
            for script in self.STEALTH_SCRIPTS:
                driver.execute_script(script)
            logger.debug("Injected stealth scripts successfully")
        except Exception as e:
            logger.warning(f"Failed to inject stealth scripts: {str(e)}")


# Add captcha detector and JS bypass manager to stealth manager
def get_captcha_detector() -> CaptchaDetector:
    """Get captcha detector instance"""
    return CaptchaDetector()


def get_js_bypass_manager() -> JSBypassManager:
    """Get JS bypass manager instance"""
    return JSBypassManager()


async def initialize_stealth_system():
    """Initialize the stealth system with configuration from settings"""
    from app.core.config import settings

    if not settings.stealth_mode_enabled:
        logger.info("Stealth mode disabled in configuration")
        return

    # Configure stealth manager
    stealth_config = StealthConfig(
        enable_header_randomization=settings.stealth_header_randomization,
        enable_viewport_randomization=settings.stealth_viewport_randomization,
        enable_intelligent_delays=settings.stealth_intelligent_delays,
        min_delay=settings.stealth_delay_min,
        max_delay=settings.stealth_delay_max,
        enable_cookie_management=settings.stealth_cookie_management,
        enable_js_detection_bypass=settings.stealth_js_detection_bypass,
    )

    configure_stealth_manager(stealth_config)
    logger.info("Stealth system initialized successfully")
