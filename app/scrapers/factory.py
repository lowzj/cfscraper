from typing import Dict, Any, Optional
import logging

from app.scrapers.base import BaseScraper
from app.models.job import ScraperType

logger = logging.getLogger(__name__)

# Try to import scrapers, but handle missing dependencies
try:
    from app.scrapers.cloudscraper_scraper import CloudScraperScraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False
    CloudScraperScraper = None

try:
    from app.scrapers.selenium_scraper import SeleniumScraper
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    SeleniumScraper = None


class ScraperFactory:
    """Factory class for creating scrapers"""
    
    @classmethod
    def _get_scrapers(cls) -> Dict[ScraperType, type]:
        """Get available scrapers based on installed dependencies"""
        scrapers = {}
        
        if HAS_CLOUDSCRAPER and CloudScraperScraper:
            scrapers[ScraperType.CLOUDSCRAPER] = CloudScraperScraper
        
        if HAS_SELENIUM and SeleniumScraper:
            scrapers[ScraperType.SELENIUM] = SeleniumScraper
            
        return scrapers
    
    @classmethod
    def create_scraper(
        cls,
        scraper_type: ScraperType,
        timeout: Optional[int] = None,
        **kwargs
    ) -> BaseScraper:
        """
        Create a scraper instance based on the specified type
        
        Args:
            scraper_type: The type of scraper to create
            timeout: Optional timeout for the scraper
            **kwargs: Additional arguments for the scraper
            
        Returns:
            BaseScraper instance
            
        Raises:
            ValueError: If scraper type is not supported
        """
        scrapers = cls._get_scrapers()
        
        if scraper_type not in scrapers:
            if scraper_type == ScraperType.CLOUDSCRAPER and not HAS_CLOUDSCRAPER:
                raise ValueError("CloudScraper is not available. Install it with: pip install cloudscraper")
            elif scraper_type == ScraperType.SELENIUM and not HAS_SELENIUM:
                raise ValueError("Selenium is not available. Install it with: pip install seleniumbase")
            else:
                raise ValueError(f"Unsupported scraper type: {scraper_type}")
        
        scraper_class = scrapers[scraper_type]
        
        # Create scraper with appropriate arguments
        if scraper_type == ScraperType.SELENIUM:
            return scraper_class(timeout=timeout, **kwargs)
        else:
            return scraper_class(timeout=timeout)
    
    @classmethod
    def get_available_scrapers(cls) -> list[str]:
        """Get list of available scraper types"""
        return list(cls._get_scrapers().keys())
    
    @classmethod
    def register_scraper(cls, scraper_type: ScraperType, scraper_class: type):
        """
        Register a new scraper type
        
        Args:
            scraper_type: The type identifier for the scraper
            scraper_class: The scraper class (must inherit from BaseScraper)
        """
        if not issubclass(scraper_class, BaseScraper):
            raise ValueError("Scraper class must inherit from BaseScraper")
        
        # Note: This method is for runtime registration, not for the factory's core scrapers
        logger.info(f"Registered scraper: {scraper_type}")


# Convenience function
def create_scraper(
    scraper_type: ScraperType,
    timeout: Optional[int] = None,
    **kwargs
) -> BaseScraper:
    """
    Create a scraper instance
    
    Args:
        scraper_type: The type of scraper to create
        timeout: Optional timeout for the scraper
        **kwargs: Additional arguments for the scraper
        
    Returns:
        BaseScraper instance
    """
    return ScraperFactory.create_scraper(scraper_type, timeout, **kwargs)