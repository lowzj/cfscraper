from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import time

logger = logging.getLogger(__name__)


class ScraperResult:
    """Container for scraper results"""
    
    def __init__(
        self,
        status_code: int,
        content: str,
        headers: Dict[str, str],
        response_time: float,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.status_code = status_code
        self.content = content
        self.headers = headers
        self.response_time = response_time
        self.error = error
        self.metadata = metadata or {}
        self.timestamp = datetime.now()
    
    def is_success(self) -> bool:
        """Check if the scraping was successful"""
        return self.status_code == 200 and self.error is None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary"""
        result = {
            "status_code": self.status_code,
            "content": self.content,
            "headers": self.headers,
            "response_time": self.response_time,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "success": self.is_success()
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class BaseScraper(ABC):
    """Abstract base class for all scrapers"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def scrape(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None
    ) -> ScraperResult:
        """
        Scrape a URL and return the result
        
        Args:
            url: The URL to scrape
            method: HTTP method (GET, POST, etc.)
            headers: Optional headers to include
            data: Optional data for POST requests
            params: Optional query parameters
            
        Returns:
            ScraperResult object containing the response
        """
        pass
    
    @abstractmethod
    async def close(self):
        """Clean up resources"""
        pass
    
    def _measure_time(self, start_time: float) -> float:
        """Calculate response time in milliseconds"""
        return round((time.time() - start_time) * 1000, 2)
    
    def _handle_error(self, error: Exception, url: str) -> ScraperResult:
        """Handle scraping errors"""
        error_msg = f"Error scraping {url}: {str(error)}"
        self.logger.error(error_msg)
        return ScraperResult(
            status_code=0,
            content="",
            headers={},
            response_time=0,
            error=error_msg
        )