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


class CloudScraperScraper(BaseScraper):
    """CloudScraper-based scraper for bypassing Cloudflare protection"""
    
    def __init__(self, timeout: int = None):
        super().__init__(timeout or settings.cloudscraper_timeout)
        if not HAS_CLOUDSCRAPER:
            raise ImportError("cloudscraper is not installed. Install it with: pip install cloudscraper")
        self.session = cloudscraper.create_scraper()
        self.session.timeout = self.timeout
        self.executor = ThreadPoolExecutor(max_workers=1)
    
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
        
        try:
            # Run cloudscraper in thread pool since it's blocking
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._make_request,
                url,
                method,
                headers,
                data,
                params
            )
            
            response_time = self._measure_time(start_time)
            
            return ScraperResult(
                status_code=response.status_code,
                content=response.text,
                headers=dict(response.headers),
                response_time=response_time
            )
            
        except Exception as e:
            return self._handle_error(e, url)
    
    def _make_request(
        self,
        url: str,
        method: str,
        headers: Optional[Dict[str, str]],
        data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, str]]
    ):
        """Make the actual HTTP request (blocking)"""
        if not HAS_CLOUDSCRAPER:
            raise ImportError("cloudscraper is not installed")
            
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