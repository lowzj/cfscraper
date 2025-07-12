from typing import Dict, Any, Optional
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

try:
    from seleniumbase import BaseCase
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

from app.scrapers.base import BaseScraper, ScraperResult
from app.core.config import settings
from app.utils.proxy_manager import get_proxy_pool, get_user_agent_rotator
from app.utils.stealth_manager import get_stealth_manager, get_captcha_detector, get_js_bypass_manager


class SeleniumScraper(BaseScraper):
    """SeleniumBase-based scraper for JavaScript-heavy websites"""
    
    def __init__(self, timeout: int = None, headless: bool = True, use_proxy_rotation: bool = True, use_user_agent_rotation: bool = True, use_stealth_mode: bool = True):
        super().__init__(timeout or settings.selenium_timeout)
        if not HAS_SELENIUM:
            raise ImportError("seleniumbase is not installed. Install it with: pip install seleniumbase")
        self.headless = headless
        self.driver = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.use_proxy_rotation = use_proxy_rotation
        self.use_user_agent_rotation = use_user_agent_rotation
        self.use_stealth_mode = use_stealth_mode
        self.current_proxy = None
        self.current_user_agent = None
        self.current_viewport = None
    
    async def scrape(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None
    ) -> ScraperResult:
        """
        Scrape a URL using SeleniumBase
        
        Args:
            url: The URL to scrape
            method: HTTP method (currently only GET is supported)
            headers: Optional headers (not fully supported in Selenium)
            data: Optional data (not applicable for GET requests)
            params: Optional query parameters (will be added to URL)
            
        Returns:
            ScraperResult object containing the response
        """
        if not HAS_SELENIUM:
            raise ImportError("seleniumbase is not installed")
            
        if method.upper() != "GET":
            raise ValueError("SeleniumScraper currently only supports GET requests")
        start_time = time.time()
        proxy_info = None

        try:
            # Apply stealth features if enabled
            if self.use_stealth_mode:
                stealth_manager = get_stealth_manager()
                # Apply intelligent delays
                await stealth_manager.delay_manager.wait_before_request()
                # Get viewport configuration
                self.current_viewport = await stealth_manager.get_viewport_config()

            # Get proxy if rotation is enabled
            if self.use_proxy_rotation and settings.proxy_list:
                proxy_pool = get_proxy_pool()
                proxy_info = await proxy_pool.get_proxy()
                self.current_proxy = proxy_info

            # Get user agent if rotation is enabled (and not using stealth mode)
            if self.use_user_agent_rotation and settings.user_agent_rotation_enabled and not self.use_stealth_mode:
                user_agent_rotator = get_user_agent_rotator()
                fingerprint = await user_agent_rotator.get_browser_fingerprint()
                self.current_user_agent = fingerprint['user_agent']
            elif self.use_stealth_mode:
                # Stealth mode handles user agent internally
                user_agent_rotator = get_user_agent_rotator()
                fingerprint = await user_agent_rotator.get_browser_fingerprint()
                self.current_user_agent = fingerprint['user_agent']

            # Build URL with parameters
            if params:
                url_params = '&'.join([f"{k}={v}" for k, v in params.items()])
                url = f"{url}?{url_params}" if '?' not in url else f"{url}&{url_params}"

            # Run selenium in thread pool since it's blocking
            content = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._scrape_with_selenium,
                url
            )

            response_time = self._measure_time(start_time)

            # Check for captcha if stealth mode is enabled
            captcha_detected = False
            detection_result = {}
            if self.use_stealth_mode:
                captcha_detector = get_captcha_detector()
                detection_result = await captcha_detector.detect_captcha(content, url)
                captcha_detected = detection_result["has_captcha"]

                if captcha_detected:
                    self.logger.warning(f"Captcha detected: {detection_result}")

            # Report proxy success if used
            if proxy_info:
                proxy_pool = get_proxy_pool()
                await proxy_pool.report_proxy_result(proxy_info, True, response_time)

            result = ScraperResult(
                status_code=200,  # Selenium doesn't easily provide status codes
                content=content,
                headers={},  # Selenium doesn't easily provide response headers
                response_time=response_time
            )

            # Add captcha detection metadata
            if captcha_detected:
                result.metadata = {"captcha_detected": True, "captcha_info": detection_result}

            return result

        except Exception as e:
            # Report proxy failure if used
            if proxy_info:
                proxy_pool = get_proxy_pool()
                await proxy_pool.report_proxy_result(proxy_info, False)

            return self._handle_error(e, url)
    
    def _scrape_with_selenium(self, url: str) -> str:
        """Perform the actual scraping with Selenium (blocking)"""
        try:
            # Initialize the driver if not already done
            if not self.driver:
                self._init_driver()
            
            # Navigate to the URL
            self.driver.get(url)
            
            # Wait for the page to load
            WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Get the page source
            return self.driver.page_source
            
        except Exception as e:
            self.logger.error(f"Selenium scraping failed: {str(e)}")
            raise
    
    def _init_driver(self):
        """Initialize the Selenium driver"""
        try:
            from seleniumbase import Driver

            # Prepare driver options
            driver_options = {
                "browser": "chrome",
                "headless": self.headless,
                "page_load_timeout": self.timeout,
                "implicit_wait": 10
            }

            # Add proxy if available
            if self.current_proxy:
                driver_options["proxy"] = self.current_proxy.url
                self.logger.info(f"Using proxy: {self.current_proxy.host}:{self.current_proxy.port}")

            # Add user agent if available
            if self.current_user_agent:
                driver_options["user_agent"] = self.current_user_agent
                self.logger.info(f"Using user agent: {self.current_user_agent[:50]}...")

            # Create driver with options
            self.driver = Driver(**driver_options)

            # Apply stealth features if enabled
            if self.use_stealth_mode:
                self._apply_stealth_features()

            # Set viewport if available
            if self.current_viewport:
                try:
                    self.driver.set_window_size(
                        self.current_viewport["width"],
                        self.current_viewport["height"]
                    )
                    self.logger.info(f"Set viewport: {self.current_viewport['width']}x{self.current_viewport['height']}")
                except Exception as e:
                    self.logger.warning(f"Failed to set viewport: {str(e)}")

            self.logger.info("Selenium driver initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize Selenium driver: {str(e)}")
            raise

    def _apply_stealth_features(self):
        """Apply stealth features to the Selenium driver"""
        try:
            # Inject stealth scripts
            js_bypass_manager = get_js_bypass_manager()
            stealth_scripts = asyncio.run(js_bypass_manager.get_stealth_scripts())

            for script in stealth_scripts:
                try:
                    self.driver.execute_script(script)
                except Exception as e:
                    self.logger.warning(f"Failed to execute stealth script: {str(e)}")

            # Additional stealth configurations
            try:
                # Disable automation indicators
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                # Override permissions API
                self.driver.execute_script("""
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                """)

                self.logger.debug("Applied stealth features successfully")

            except Exception as e:
                self.logger.warning(f"Failed to apply some stealth features: {str(e)}")

        except Exception as e:
            self.logger.warning(f"Failed to apply stealth features: {str(e)}")
    
    async def close(self):
        """Clean up resources"""
        if self.driver:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self.driver.quit
                )
                self.driver = None
                self.logger.info("Selenium driver closed")
            except Exception as e:
                self.logger.error(f"Error closing Selenium driver: {str(e)}")
        
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)
    
    def __del__(self):
        """Cleanup on deletion"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass