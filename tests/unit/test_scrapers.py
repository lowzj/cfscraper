"""
Unit tests for scraper classes
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import time

from app.scrapers.base import BaseScraper, ScraperResult
from app.scrapers.factory import ScraperFactory, create_scraper
from app.models.job import ScraperType


class TestScraperResult:
    """Test ScraperResult class"""
    
    def test_scraper_result_creation(self):
        """Test creating a ScraperResult"""
        result = ScraperResult(
            status_code=200,
            content="<html>test</html>",
            headers={"content-type": "text/html"},
            response_time=1500.0,
            error=None,
            metadata={"proxy": "127.0.0.1:8080"}
        )
        
        assert result.status_code == 200
        assert result.content == "<html>test</html>"
        assert result.headers == {"content-type": "text/html"}
        assert result.response_time == 1500.0
        assert result.error is None
        assert result.metadata == {"proxy": "127.0.0.1:8080"}
        assert isinstance(result.timestamp, datetime)
    
    def test_scraper_result_is_success(self):
        """Test is_success method"""
        # Successful result
        success_result = ScraperResult(200, "content", {}, 1000.0)
        assert success_result.is_success() is True
        
        # Failed result - wrong status code
        fail_result1 = ScraperResult(404, "content", {}, 1000.0)
        assert fail_result1.is_success() is False
        
        # Failed result - has error
        fail_result2 = ScraperResult(200, "content", {}, 1000.0, error="Some error")
        assert fail_result2.is_success() is False
    
    def test_scraper_result_to_dict(self):
        """Test to_dict method"""
        result = ScraperResult(
            status_code=200,
            content="test",
            headers={"type": "html"},
            response_time=1000.0,
            metadata={"test": "value"}
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["status_code"] == 200
        assert result_dict["content"] == "test"
        assert result_dict["headers"] == {"type": "html"}
        assert result_dict["response_time"] == 1000.0
        assert result_dict["error"] is None
        assert result_dict["success"] is True
        assert result_dict["metadata"] == {"test": "value"}
        assert "timestamp" in result_dict


class TestBaseScraper:
    """Test BaseScraper abstract class"""
    
    def test_base_scraper_initialization(self):
        """Test BaseScraper initialization"""
        # Create a concrete implementation for testing
        class TestScraper(BaseScraper):
            async def scrape(self, url, method="GET", headers=None, data=None, params=None):
                return ScraperResult(200, "test", {}, 1000.0)
            
            async def close(self):
                pass
        
        scraper = TestScraper(timeout=60)
        assert scraper.timeout == 60
        assert scraper.logger.name == "TestScraper"
    
    def test_measure_time(self):
        """Test _measure_time method"""
        class TestScraper(BaseScraper):
            async def scrape(self, url, method="GET", headers=None, data=None, params=None):
                return ScraperResult(200, "test", {}, 1000.0)
            
            async def close(self):
                pass
        
        scraper = TestScraper()
        start_time = time.time() - 1.5  # 1.5 seconds ago
        response_time = scraper._measure_time(start_time)
        
        # Should be approximately 1500ms
        assert 1400 <= response_time <= 1600
    
    def test_handle_error(self):
        """Test _handle_error method"""
        class TestScraper(BaseScraper):
            async def scrape(self, url, method="GET", headers=None, data=None, params=None):
                return ScraperResult(200, "test", {}, 1000.0)
            
            async def close(self):
                pass
        
        scraper = TestScraper()
        error = Exception("Test error")
        result = scraper._handle_error(error, "https://example.com")
        
        assert result.status_code == 0
        assert result.content == ""
        assert result.headers == {}
        assert result.response_time == 0
        assert "Test error" in result.error
        assert "https://example.com" in result.error


@pytest.mark.unit
class TestCloudScraperScraper:
    """Test CloudScraperScraper class"""
    
    @patch('app.scrapers.cloudscraper_scraper.HAS_CLOUDSCRAPER', True)
    @patch('app.scrapers.cloudscraper_scraper.cloudscraper')
    def test_cloudscraper_initialization(self, mock_cloudscraper):
        """Test CloudScraperScraper initialization"""
        from app.scrapers.cloudscraper_scraper import CloudScraperScraper
        
        mock_session = Mock()
        mock_cloudscraper.create_scraper.return_value = mock_session
        
        scraper = CloudScraperScraper(timeout=45)
        
        assert scraper.timeout == 45
        assert scraper.session == mock_session
        assert scraper.session.timeout == 45
        mock_cloudscraper.create_scraper.assert_called_once()
    
    @patch('app.scrapers.cloudscraper_scraper.HAS_CLOUDSCRAPER', False)
    def test_cloudscraper_missing_dependency(self):
        """Test CloudScraperScraper with missing dependency"""
        from app.scrapers.cloudscraper_scraper import CloudScraperScraper
        
        with pytest.raises(ImportError, match="cloudscraper is not installed"):
            CloudScraperScraper()
    
    @patch('app.scrapers.cloudscraper_scraper.HAS_CLOUDSCRAPER', True)
    @patch('app.scrapers.cloudscraper_scraper.cloudscraper')
    @patch('app.utils.proxy_manager.get_proxy_pool')
    @patch('app.utils.proxy_manager.get_user_agent_rotator')
    @patch('app.utils.stealth_manager.get_captcha_detector')
    async def test_cloudscraper_successful_scrape(
        self, mock_captcha_detector, mock_user_agent_rotator, 
        mock_proxy_pool, mock_cloudscraper
    ):
        """Test successful scraping with CloudScraper"""
        from app.scrapers.cloudscraper_scraper import CloudScraperScraper
        
        # Setup mocks
        mock_session = Mock()
        mock_cloudscraper.create_scraper.return_value = mock_session
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html>test content</html>"
        mock_response.headers = {"content-type": "text/html"}
        
        # Mock proxy and user agent
        mock_proxy_pool.return_value.get_proxy = AsyncMock(return_value=None)
        mock_user_agent_rotator.return_value.get_user_agent = AsyncMock(return_value=None)
        
        # Mock captcha detector
        mock_captcha_detector.return_value.detect_captcha = AsyncMock(
            return_value={"has_captcha": False}
        )
        
        scraper = CloudScraperScraper()
        
        # Mock the _make_request method to return our mock response
        with patch.object(scraper, '_make_request', return_value=mock_response):
            result = await scraper.scrape("https://example.com")
        
        assert result.status_code == 200
        assert result.content == "<html>test content</html>"
        assert result.headers == {"content-type": "text/html"}
        assert result.response_time > 0
        assert result.error is None
        assert result.is_success() is True
    
    @patch('app.scrapers.cloudscraper_scraper.HAS_CLOUDSCRAPER', True)
    @patch('app.scrapers.cloudscraper_scraper.cloudscraper')
    async def test_cloudscraper_error_handling(self, mock_cloudscraper):
        """Test error handling in CloudScraper"""
        from app.scrapers.cloudscraper_scraper import CloudScraperScraper
        
        mock_session = Mock()
        mock_cloudscraper.create_scraper.return_value = mock_session
        
        scraper = CloudScraperScraper()
        
        # Mock the _make_request method to raise an exception
        with patch.object(scraper, '_make_request', side_effect=Exception("Network error")):
            result = await scraper.scrape("https://example.com")
        
        assert result.status_code == 0
        assert result.content == ""
        assert result.headers == {}
        assert result.response_time == 0
        assert "Network error" in result.error
        assert result.is_success() is False
    
    @patch('app.scrapers.cloudscraper_scraper.HAS_CLOUDSCRAPER', True)
    @patch('app.scrapers.cloudscraper_scraper.cloudscraper')
    async def test_cloudscraper_close(self, mock_cloudscraper):
        """Test CloudScraper close method"""
        from app.scrapers.cloudscraper_scraper import CloudScraperScraper
        
        mock_session = Mock()
        mock_cloudscraper.create_scraper.return_value = mock_session
        
        scraper = CloudScraperScraper()
        await scraper.close()
        
        mock_session.close.assert_called_once()


@pytest.mark.unit
class TestSeleniumScraper:
    """Test SeleniumScraper class"""
    
    @patch('app.scrapers.selenium_scraper.HAS_SELENIUM', True)
    def test_selenium_initialization(self):
        """Test SeleniumScraper initialization"""
        from app.scrapers.selenium_scraper import SeleniumScraper
        
        scraper = SeleniumScraper(timeout=60, headless=False)
        
        assert scraper.timeout == 60
        assert scraper.headless is False
        assert scraper.driver is None
        assert scraper.use_proxy_rotation is True
        assert scraper.use_user_agent_rotation is True
        assert scraper.use_stealth_mode is True
    
    @patch('app.scrapers.selenium_scraper.HAS_SELENIUM', False)
    def test_selenium_missing_dependency(self):
        """Test SeleniumScraper with missing dependency"""
        from app.scrapers.selenium_scraper import SeleniumScraper
        
        with pytest.raises(ImportError, match="seleniumbase is not installed"):
            SeleniumScraper()
    
    @patch('app.scrapers.selenium_scraper.HAS_SELENIUM', True)
    async def test_selenium_unsupported_method(self):
        """Test SeleniumScraper with unsupported HTTP method"""
        from app.scrapers.selenium_scraper import SeleniumScraper
        
        scraper = SeleniumScraper()
        
        with pytest.raises(ValueError, match="only supports GET requests"):
            await scraper.scrape("https://example.com", method="POST")
    
    @patch('app.scrapers.selenium_scraper.HAS_SELENIUM', True)
    @patch('app.utils.proxy_manager.get_proxy_pool')
    @patch('app.utils.proxy_manager.get_user_agent_rotator')
    @patch('app.utils.stealth_manager.get_captcha_detector')
    async def test_selenium_successful_scrape(
        self, mock_captcha_detector, mock_user_agent_rotator, mock_proxy_pool
    ):
        """Test successful scraping with Selenium"""
        from app.scrapers.selenium_scraper import SeleniumScraper
        
        # Mock proxy and user agent
        mock_proxy_pool.return_value.get_proxy = AsyncMock(return_value=None)
        mock_user_agent_rotator.return_value.get_user_agent = AsyncMock(return_value=None)
        
        # Mock captcha detector
        mock_captcha_detector.return_value.detect_captcha = AsyncMock(
            return_value={"has_captcha": False}
        )
        
        scraper = SeleniumScraper()
        
        # Mock the _scrape_with_selenium method
        with patch.object(scraper, '_scrape_with_selenium', return_value="<html>test content</html>"):
            result = await scraper.scrape("https://example.com")
        
        assert result.status_code == 200
        assert result.content == "<html>test content</html>"
        assert result.headers == {}
        assert result.response_time > 0
        assert result.error is None
        assert result.is_success() is True
    
    @patch('app.scrapers.selenium_scraper.HAS_SELENIUM', True)
    async def test_selenium_error_handling(self):
        """Test error handling in Selenium scraper"""
        from app.scrapers.selenium_scraper import SeleniumScraper
        
        scraper = SeleniumScraper()
        
        # Mock the _scrape_with_selenium method to raise an exception
        with patch.object(scraper, '_scrape_with_selenium', side_effect=Exception("Selenium error")):
            result = await scraper.scrape("https://example.com")
        
        assert result.status_code == 0
        assert result.content == ""
        assert result.headers == {}
        assert result.response_time == 0
        assert "Selenium error" in result.error
        assert result.is_success() is False
    
    @patch('app.scrapers.selenium_scraper.HAS_SELENIUM', True)
    async def test_selenium_close(self):
        """Test Selenium scraper close method"""
        from app.scrapers.selenium_scraper import SeleniumScraper
        
        scraper = SeleniumScraper()
        mock_driver = Mock()
        scraper.driver = mock_driver
        
        await scraper.close()
        
        mock_driver.quit.assert_called_once()


@pytest.mark.unit
class TestScraperFactory:
    """Test ScraperFactory class"""
    
    @patch('app.scrapers.factory.HAS_CLOUDSCRAPER', True)
    @patch('app.scrapers.factory.HAS_SELENIUM', True)
    def test_get_available_scrapers(self):
        """Test getting available scrapers"""
        available = ScraperFactory.get_available_scrapers()
        
        assert ScraperType.CLOUDSCRAPER in available
        assert ScraperType.SELENIUM in available
    
    @patch('app.scrapers.factory.HAS_CLOUDSCRAPER', True)
    @patch('app.scrapers.cloudscraper_scraper.HAS_CLOUDSCRAPER', True)
    @patch('app.scrapers.cloudscraper_scraper.cloudscraper')
    def test_create_cloudscraper(self, mock_cloudscraper):
        """Test creating CloudScraper through factory"""
        mock_session = Mock()
        mock_cloudscraper.create_scraper.return_value = mock_session
        
        scraper = ScraperFactory.create_scraper(ScraperType.CLOUDSCRAPER, timeout=30)
        
        assert scraper.timeout == 30
        assert hasattr(scraper, 'session')
    
    @patch('app.scrapers.factory.HAS_SELENIUM', True)
    def test_create_selenium_scraper(self):
        """Test creating Selenium scraper through factory"""
        scraper = ScraperFactory.create_scraper(
            ScraperType.SELENIUM, 
            timeout=45, 
            headless=False
        )
        
        assert scraper.timeout == 45
        assert scraper.headless is False
    
    def test_create_unsupported_scraper(self):
        """Test creating unsupported scraper type"""
        with pytest.raises(ValueError, match="Unsupported scraper type"):
            ScraperFactory.create_scraper("unsupported_type")
    
    @patch('app.scrapers.factory.HAS_CLOUDSCRAPER', False)
    def test_create_unavailable_cloudscraper(self):
        """Test creating CloudScraper when not available"""
        with pytest.raises(ValueError, match="CloudScraper is not available"):
            ScraperFactory.create_scraper(ScraperType.CLOUDSCRAPER)
    
    @patch('app.scrapers.factory.HAS_SELENIUM', False)
    def test_create_unavailable_selenium(self):
        """Test creating Selenium scraper when not available"""
        with pytest.raises(ValueError, match="Selenium is not available"):
            ScraperFactory.create_scraper(ScraperType.SELENIUM)
    
    def test_register_custom_scraper(self):
        """Test registering a custom scraper"""
        class CustomScraper(BaseScraper):
            async def scrape(self, url, method="GET", headers=None, data=None, params=None):
                return ScraperResult(200, "custom", {}, 1000.0)
            
            async def close(self):
                pass
        
        custom_type = "custom"
        ScraperFactory.register_scraper(custom_type, CustomScraper)
        
        scraper = ScraperFactory.create_scraper(custom_type)
        assert isinstance(scraper, CustomScraper)
    
    def test_register_invalid_scraper(self):
        """Test registering invalid scraper class"""
        class InvalidScraper:
            pass
        
        with pytest.raises(ValueError, match="must inherit from BaseScraper"):
            ScraperFactory.register_scraper("invalid", InvalidScraper)
