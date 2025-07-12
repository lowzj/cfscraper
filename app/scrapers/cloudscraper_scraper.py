from typing import Dict, Any, Optional
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

try:
    import cloudscraper
    from requests import Response
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False

from app.scrapers.base import BaseScraper, ScraperResult
from app.core.config import settings
from app.utils.proxy_manager import get_proxy_pool, get_user_agent_rotator
from app.utils.stealth_manager import get_stealth_manager, get_captcha_detector


class CloudScraperScraper(BaseScraper):
    """CloudScraper-based scraper for bypassing Cloudflare protection"""
    
    def __init__(self, timeout: int = None, use_proxy_rotation: bool = True, use_user_agent_rotation: bool = True, use_stealth_mode: bool = True):
        super().__init__(timeout or settings.cloudscraper_timeout)
        if not HAS_CLOUDSCRAPER:
            raise ImportError("cloudscraper is not installed. Install it with: pip install cloudscraper")
        self.session = cloudscraper.create_scraper()
        self.session.timeout = self.timeout
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.use_proxy_rotation = use_proxy_rotation
        self.use_user_agent_rotation = use_user_agent_rotation
        self.use_stealth_mode = use_stealth_mode
    
    async def scrape(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None
    ) -> ScraperResult:
        """
        Scrape a URL using CloudScraper

        Args:
            url: The URL to scrape
            method: HTTP method (GET, POST, etc.)
            headers: Optional headers to include
            data: Optional data for POST requests
            params: Optional query parameters

        Returns:
            ScraperResult object containing the response
        """
        start_time = time.time()
        proxy_info = None

        try:
            # Apply stealth features if enabled
            if self.use_stealth_mode:
                stealth_manager = get_stealth_manager()
                headers = await stealth_manager.prepare_request(headers)

            # Get proxy if rotation is enabled
            if self.use_proxy_rotation and settings.proxy_list:
                proxy_pool = get_proxy_pool()
                proxy_info = await proxy_pool.get_proxy()

            # Get user agent if rotation is enabled (and not already set by stealth mode)
            if self.use_user_agent_rotation and settings.user_agent_rotation_enabled and not self.use_stealth_mode:
                user_agent_rotator = get_user_agent_rotator()
                fingerprint = await user_agent_rotator.get_browser_fingerprint()
                if headers is None:
                    headers = {}
                headers['User-Agent'] = fingerprint['user_agent']

            # Run cloudscraper in thread pool since it's blocking
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._make_request,
                url,
                method,
                headers,
                data,
                params,
                proxy_info
            )

            response_time = self._measure_time(start_time)

            # Check for captcha if stealth mode is enabled
            captcha_detected = False
            if self.use_stealth_mode:
                captcha_detector = get_captcha_detector()
                detection_result = await captcha_detector.detect_captcha(response.text, url)
                captcha_detected = detection_result["has_captcha"]

                if captcha_detected:
                    self.logger.warning(f"Captcha detected: {detection_result}")
                    # Store cookies for session management
                    if hasattr(response, 'cookies'):
                        stealth_manager = get_stealth_manager()
                        from urllib.parse import urlparse
                        domain = urlparse(url).netloc
                        stealth_manager.store_cookies(domain, dict(response.cookies))

            # Report proxy success if used
            if proxy_info:
                proxy_pool = get_proxy_pool()
                await proxy_pool.report_proxy_result(proxy_info, True, response_time)

            result = ScraperResult(
                status_code=response.status_code,
                content=response.text,
                headers=dict(response.headers),
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
    
    def _make_request(
        self,
        url: str,
        method: str,
        headers: Optional[Dict[str, str]],
        data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, str]],
        proxy_info=None
    ):
        """Make the actual HTTP request (blocking)"""
        if not HAS_CLOUDSCRAPER:
            raise ImportError("cloudscraper is not installed")

        # Configure proxy if provided
        if proxy_info:
            self.session.proxies = {
                'http': proxy_info.url,
                'https': proxy_info.url
            }
        else:
            self.session.proxies = {}

        request_kwargs = {
            'url': url,
            'headers': headers or {},
            'timeout': self.timeout
        }
        
        if method.upper() == 'GET':
            request_kwargs['params'] = params
            return self.session.get(**request_kwargs)
        elif method.upper() == 'POST':
            request_kwargs['data'] = data
            request_kwargs['params'] = params
            return self.session.post(**request_kwargs)
        else:
            # For other methods, use the generic request method
            request_kwargs['method'] = method
            request_kwargs['data'] = data
            request_kwargs['params'] = params
            return self.session.request(**request_kwargs)
    
    async def close(self):
        """Clean up resources"""
        if hasattr(self, 'session'):
            self.session.close()
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)
        self.logger.info("CloudScraper session closed")