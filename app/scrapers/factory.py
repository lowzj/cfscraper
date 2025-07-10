from typing import Dict, Any, Optional
import logging

from app.scrapers.base import BaseScraper
from app.scrapers.cloudscraper_scraper import CloudScraperScraper
from app.scrapers.selenium_scraper import SeleniumScraper
from app.models.job import ScraperType

logger = logging.getLogger(__name__)


class ScraperFactory:
    """Factory class for creating scrapers"""
    
    _scrapers: Dict[ScraperType, type] = {
        ScraperType.CLOUDSCRAPER: CloudScraperScraper,
        ScraperType.SELENIUM: SeleniumScraper,
    }
    
    @classmethod
    def create_scraper(
        self,
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
        if scraper_type not in self._scrapers:
            raise ValueError(f"Unsupported scraper type: {scraper_type}")
        
        scraper_class = self._scrapers[scraper_type]
        
        # Create scraper with appropriate arguments
        if scraper_type == ScraperType.SELENIUM:
            return scraper_class(timeout=timeout, **kwargs)
        else:
            return scraper_class(timeout=timeout)
    
    @classmethod
    def get_available_scrapers(cls) -> list[str]:
        """Get list of available scraper types"""
        return list(cls._scrapers.keys())
    
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
        
        cls._scrapers[scraper_type] = scraper_class
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