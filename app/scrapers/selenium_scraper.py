from typing import Dict, Any, Optional
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

from seleniumbase import BaseCase
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from app.scrapers.base import BaseScraper, ScraperResult
from app.core.config import settings


class SeleniumScraper(BaseScraper):
    """SeleniumBase-based scraper for JavaScript-heavy websites"""
    
    def __init__(self, timeout: int = None, headless: bool = True):
        super().__init__(timeout or settings.selenium_timeout)
        self.headless = headless
        self.driver = None
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
        start_time = time.time()
        
        try:
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
            
            return ScraperResult(
                status_code=200,  # Selenium doesn't easily provide status codes
                content=content,
                headers={},  # Selenium doesn't easily provide response headers
                response_time=response_time
            )
            
        except Exception as e:
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
            
            # Create driver with appropriate options
            self.driver = Driver(
                browser="chrome",
                headless=self.headless,
                page_load_timeout=self.timeout,
                implicit_wait=10
            )
            
            self.logger.info("Selenium driver initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Selenium driver: {str(e)}")
            raise
    
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
            except:
                pass