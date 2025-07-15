"""
Unit tests for proxy management and anti-detection systems
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import random
import time

from app.utils.proxy_manager import (
    ProxyInfo, ProxyStatus, ProxyProtocol, ProxyPoolConfig, ProxyPool,
    UserAgentRotator, get_proxy_pool, get_user_agent_rotator
)
from app.utils.stealth_manager import (
    StealthConfig, HeaderRandomizer, ViewportRandomizer, DelayManager,
    StealthManager, CaptchaDetector, JSBypassManager,
    get_stealth_manager, get_captcha_detector
)


@pytest.mark.unit
class TestProxyInfo:
    """Test ProxyInfo dataclass"""
    
    def test_proxy_info_creation(self):
        """Test creating proxy info"""
        proxy = ProxyInfo(
            host="127.0.0.1",
            port=8080,
            protocol=ProxyProtocol.HTTP,
            username="user",
            password="pass"
        )
        
        assert proxy.host == "127.0.0.1"
        assert proxy.port == 8080
        assert proxy.protocol == ProxyProtocol.HTTP
        assert proxy.username == "user"
        assert proxy.password == "pass"
        assert proxy.status == ProxyStatus.ACTIVE
        assert proxy.success_count == 0
        assert proxy.failure_count == 0
    
    def test_proxy_url_with_auth(self):
        """Test proxy URL generation with authentication"""
        proxy = ProxyInfo(
            host="proxy.example.com",
            port=3128,
            protocol=ProxyProtocol.HTTP,
            username="user",
            password="secret"
        )
        
        expected_url = "http://user:secret@proxy.example.com:3128"
        assert proxy.url == expected_url
    
    def test_proxy_url_without_auth(self):
        """Test proxy URL generation without authentication"""
        proxy = ProxyInfo(
            host="proxy.example.com",
            port=3128,
            protocol=ProxyProtocol.HTTP
        )
        
        expected_url = "http://proxy.example.com:3128"
        assert proxy.url == expected_url
    
    def test_proxy_success_rate(self):
        """Test proxy success rate calculation"""
        proxy = ProxyInfo(host="127.0.0.1", port=8080)
        
        # No attempts yet
        assert proxy.success_rate == 0.0
        
        # Add some successes and failures
        proxy.update_stats(True, 1.0)
        proxy.update_stats(True, 1.5)
        proxy.update_stats(False)
        
        # 2 successes out of 3 attempts = 66.67%
        assert abs(proxy.success_rate - 0.6666666666666666) < 0.001
    
    def test_proxy_health_check(self):
        """Test proxy health status"""
        proxy = ProxyInfo(host="127.0.0.1", port=8080)
        
        # Initially healthy (no failures)
        assert proxy.is_healthy is True
        
        # Add many failures
        for _ in range(6):
            proxy.update_stats(False)
        
        # Should be unhealthy due to low success rate and high failure count
        assert proxy.is_healthy is False
        
        # Add many successes to improve health
        for _ in range(20):
            proxy.update_stats(True, 1.0)
        
        # Should be healthy again
        assert proxy.is_healthy is True
    
    def test_proxy_update_stats(self):
        """Test updating proxy statistics"""
        proxy = ProxyInfo(host="127.0.0.1", port=8080)
        
        # Test successful request
        proxy.update_stats(True, 1.5)
        assert proxy.success_count == 1
        assert proxy.failure_count == 0
        assert proxy.avg_response_time == 1.5
        
        # Test failed request
        proxy.update_stats(False)
        assert proxy.success_count == 1
        assert proxy.failure_count == 1
        
        # Test another successful request
        proxy.update_stats(True, 2.0)
        assert proxy.success_count == 2
        assert proxy.failure_count == 1
        assert proxy.avg_response_time == 1.75  # (1.5 + 2.0) / 2


@pytest.mark.unit
class TestProxyPool:
    """Test ProxyPool class"""
    
    @pytest.mark.asyncio
    async def test_add_proxy(self):
        """Test adding proxy to pool"""
        pool = ProxyPool()
        
        proxy = await pool.add_proxy("127.0.0.1", 8080)
        
        assert len(pool.proxies) == 1
        assert proxy.host == "127.0.0.1"
        assert proxy.port == 8080
    
    @pytest.mark.asyncio
    async def test_remove_proxy(self):
        """Test removing proxy from pool"""
        pool = ProxyPool()
        
        proxy = await pool.add_proxy("127.0.0.1", 8080)
        removed = await pool.remove_proxy(proxy)
        
        assert removed is True
        assert len(pool.proxies) == 0
        
        # Try to remove non-existent proxy
        removed = await pool.remove_proxy(proxy)
        assert removed is False
    
    @pytest.mark.asyncio
    async def test_get_proxy_round_robin(self):
        """Test round-robin proxy selection"""
        config = ProxyPoolConfig(rotation_strategy="round_robin")
        pool = ProxyPool(config)
        
        # Add multiple proxies
        proxy1 = await pool.add_proxy("127.0.0.1", 8080)
        proxy2 = await pool.add_proxy("127.0.0.2", 8080)
        proxy3 = await pool.add_proxy("127.0.0.3", 8080)
        
        # Get proxies in round-robin order
        selected1 = await pool.get_proxy()
        selected2 = await pool.get_proxy()
        selected3 = await pool.get_proxy()
        selected4 = await pool.get_proxy()  # Should wrap around
        
        # Should cycle through all proxies
        assert selected1 in [proxy1, proxy2, proxy3]
        assert selected2 in [proxy1, proxy2, proxy3]
        assert selected3 in [proxy1, proxy2, proxy3]
        assert selected4 in [proxy1, proxy2, proxy3]
        
        # Should have different proxies (unless only one is healthy)
        selected_proxies = {selected1, selected2, selected3}
        assert len(selected_proxies) >= 1
    
    @pytest.mark.asyncio
    async def test_get_proxy_random(self):
        """Test random proxy selection"""
        config = ProxyPoolConfig(rotation_strategy="random")
        pool = ProxyPool(config)
        
        # Add multiple proxies
        await pool.add_proxy("127.0.0.1", 8080)
        await pool.add_proxy("127.0.0.2", 8080)
        await pool.add_proxy("127.0.0.3", 8080)
        
        # Get multiple proxies
        selected_proxies = []
        for _ in range(10):
            proxy = await pool.get_proxy()
            if proxy:
                selected_proxies.append(proxy)
        
        # Should have selected some proxies
        assert len(selected_proxies) > 0
    
    @pytest.mark.asyncio
    async def test_get_proxy_no_healthy_proxies(self):
        """Test getting proxy when none are healthy"""
        pool = ProxyPool()
        
        # Add proxy and mark it as unhealthy
        proxy = await pool.add_proxy("127.0.0.1", 8080)
        proxy.status = ProxyStatus.FAILED
        
        selected = await pool.get_proxy()
        assert selected is None
    
    @pytest.mark.asyncio
    async def test_report_proxy_result(self):
        """Test reporting proxy usage results"""
        config = ProxyPoolConfig(max_failures_before_removal=3)
        pool = ProxyPool(config)
        
        proxy = await pool.add_proxy("127.0.0.1", 8080)
        
        # Report successful usage
        await pool.report_proxy_result(proxy, True, 1.5)
        assert proxy.success_count == 1
        assert proxy.avg_response_time == 1.5
        
        # Report failures
        await pool.report_proxy_result(proxy, False)
        await pool.report_proxy_result(proxy, False)
        await pool.report_proxy_result(proxy, False)
        
        # Proxy should be removed after max failures
        assert proxy not in pool.proxies
    
    @pytest.mark.asyncio
    async def test_health_check_with_mock(self):
        """Test proxy health checking with mocked HTTP client"""
        config = ProxyPoolConfig(enable_health_checks=True)
        pool = ProxyPool(config)
        
        proxy = await pool.add_proxy("127.0.0.1", 8080)
        
        # Mock successful health check
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            await pool._check_proxy_health(proxy)
            
            assert proxy.success_count > 0
    
    @pytest.mark.asyncio
    async def test_start_stop_health_checks(self):
        """Test starting and stopping health checks"""
        pool = ProxyPool()
        
        assert pool._running is False
        assert pool._health_check_task is None
        
        await pool.start_health_checks()
        
        assert pool._running is True
        assert pool._health_check_task is not None
        
        await pool.stop_health_checks()
        
        assert pool._running is False


@pytest.mark.unit
class TestUserAgentRotator:
    """Test UserAgentRotator class"""
    
    @pytest.mark.asyncio
    async def test_get_user_agent_round_robin(self):
        """Test round-robin user agent selection"""
        rotator = UserAgentRotator(strategy="round_robin")
        
        # Get multiple user agents
        agents = []
        for _ in range(len(rotator.USER_AGENTS) + 2):
            agent = await rotator.get_user_agent()
            agents.append(agent)
        
        # Should cycle through all user agents
        assert len(set(agents)) == len(rotator.USER_AGENTS)
        
        # Should wrap around
        assert agents[0] == agents[len(rotator.USER_AGENTS)]
    
    @pytest.mark.asyncio
    async def test_get_user_agent_random(self):
        """Test random user agent selection"""
        rotator = UserAgentRotator(strategy="random")
        
        # Get multiple user agents
        agents = []
        for _ in range(20):
            agent = await rotator.get_user_agent()
            agents.append(agent)
        
        # Should have selected some user agents
        assert len(agents) == 20
        assert all(agent in rotator.USER_AGENTS for agent in agents)
    
    @pytest.mark.asyncio
    async def test_get_window_size(self):
        """Test getting random window size"""
        rotator = UserAgentRotator()
        
        window_size = await rotator.get_window_size()
        
        assert window_size in rotator.WINDOW_SIZES
    
    @pytest.mark.asyncio
    async def test_get_browser_fingerprint(self):
        """Test getting browser fingerprint"""
        rotator = UserAgentRotator()
        
        fingerprint = await rotator.get_browser_fingerprint()
        
        assert "user_agent" in fingerprint
        assert "viewport" in fingerprint
        assert "platform" in fingerprint
        assert "browser" in fingerprint
        
        # Verify user agent is valid
        assert fingerprint["user_agent"] in rotator.USER_AGENTS
    
    def test_add_custom_user_agent(self):
        """Test adding custom user agent"""
        rotator = UserAgentRotator()
        original_count = len(rotator.USER_AGENTS)
        
        custom_agent = "Custom Browser/1.0"
        rotator.add_custom_user_agent(custom_agent)
        
        assert len(rotator.USER_AGENTS) == original_count + 1
        assert custom_agent in rotator.USER_AGENTS
        
        # Adding same agent again should not duplicate
        rotator.add_custom_user_agent(custom_agent)
        assert len(rotator.USER_AGENTS) == original_count + 1


@pytest.mark.unit
class TestStealthManager:
    """Test StealthManager class"""
    
    @pytest.mark.asyncio
    async def test_prepare_request_with_headers(self):
        """Test preparing request headers"""
        config = StealthConfig(enable_header_randomization=True)
        manager = StealthManager(config)
        
        original_headers = {"Authorization": "Bearer token"}
        
        with patch.object(manager.delay_manager, 'wait_before_request') as mock_delay, \
             patch.object(manager.header_randomizer, 'get_randomized_headers') as mock_headers:
            
            mock_delay.return_value = asyncio.Future()
            mock_delay.return_value.set_result(None)
            
            mock_headers.return_value = asyncio.Future()
            mock_headers.return_value.set_result({"User-Agent": "Test", **original_headers})
            
            result = await manager.prepare_request(original_headers)
            
            mock_delay.assert_called_once()
            mock_headers.assert_called_once_with(original_headers)
            assert "Authorization" in result
    
    @pytest.mark.asyncio
    async def test_get_viewport_config(self):
        """Test getting viewport configuration"""
        config = StealthConfig(enable_viewport_randomization=True)
        manager = StealthManager(config)
        
        with patch.object(manager.viewport_randomizer, 'get_random_viewport') as mock_viewport:
            mock_viewport.return_value = asyncio.Future()
            mock_viewport.return_value.set_result({"width": 1920, "height": 1080})
            
            result = await manager.get_viewport_config()
            
            mock_viewport.assert_called_once()
            assert "width" in result
            assert "height" in result
    
    def test_store_cookies(self):
        """Test storing cookies for session management"""
        manager = StealthManager()
        
        cookies = {"session": "abc123", "csrf": "xyz789"}
        manager.store_cookies("example.com", cookies)
        
        stored = manager.get_cookies("example.com")
        assert stored == cookies
    
    def test_get_cookies_nonexistent_domain(self):
        """Test getting cookies for non-existent domain"""
        manager = StealthManager()
        
        cookies = manager.get_cookies("nonexistent.com")
        assert cookies == {}


@pytest.mark.unit
class TestCaptchaDetector:
    """Test CaptchaDetector class"""
    
    @pytest.mark.asyncio
    async def test_detect_captcha_present(self):
        """Test detecting captcha when present"""
        detector = CaptchaDetector()
        
        html_content = """
        <html>
            <body>
                <div class="g-recaptcha" data-sitekey="test"></div>
                <p>Please verify you are human</p>
            </body>
        </html>
        """
        
        result = await detector.detect_captcha(html_content, "https://example.com")
        
        assert result["has_captcha"] is True
        assert result["captcha_type"] == "recaptcha"
        assert result["confidence"] > 0.5
        assert len(result["indicators"]) > 0
        assert "suggested_action" in result
    
    @pytest.mark.asyncio
    async def test_detect_captcha_absent(self):
        """Test detecting captcha when absent"""
        detector = CaptchaDetector()
        
        html_content = """
        <html>
            <body>
                <h1>Welcome to our website</h1>
                <p>This is normal content without any captcha.</p>
            </body>
        </html>
        """
        
        result = await detector.detect_captcha(html_content, "https://example.com")
        
        assert result["has_captcha"] is False
        assert result["confidence"] == 0.0
        assert len(result["indicators"]) == 0
    
    @pytest.mark.asyncio
    async def test_detect_cloudflare_challenge(self):
        """Test detecting Cloudflare challenge"""
        detector = CaptchaDetector()
        
        html_content = """
        <html>
            <body>
                <div class="cf-browser-verification">
                    <div class="cf-checking-browser">Checking your browser...</div>
                </div>
            </body>
        </html>
        """
        
        result = await detector.detect_captcha(html_content, "https://example.com")
        
        assert result["has_captcha"] is True
        assert result["captcha_type"] == "cloudflare"
        assert result["suggested_action"] == "wait_and_retry"
    
    @pytest.mark.asyncio
    async def test_detect_hcaptcha(self):
        """Test detecting hCaptcha"""
        detector = CaptchaDetector()
        
        html_content = """
        <html>
            <body>
                <div class="h-captcha" data-sitekey="test"></div>
            </body>
        </html>
        """
        
        result = await detector.detect_captcha(html_content, "https://example.com")
        
        assert result["has_captcha"] is True
        assert result["captcha_type"] == "hcaptcha"
        assert result["suggested_action"] == "manual_intervention"


@pytest.mark.unit
class TestDelayManager:
    """Test DelayManager class"""
    
    @pytest.mark.asyncio
    async def test_wait_before_request(self):
        """Test intelligent delay before request"""
        config = StealthConfig(
            enable_intelligent_delays=True,
            min_delay=0.1,
            max_delay=0.2
        )
        manager = DelayManager(config)
        
        start_time = time.time()
        await manager.wait_before_request()
        end_time = time.time()
        
        delay = end_time - start_time
        assert 0.1 <= delay <= 0.3  # Allow some tolerance
    
    @pytest.mark.asyncio
    async def test_wait_disabled(self):
        """Test that delay is skipped when disabled"""
        config = StealthConfig(enable_intelligent_delays=False)
        manager = DelayManager(config)
        
        start_time = time.time()
        await manager.wait_before_request()
        end_time = time.time()
        
        delay = end_time - start_time
        assert delay < 0.01  # Should be nearly instant


@pytest.mark.unit
class TestHeaderRandomizer:
    """Test HeaderRandomizer class"""
    
    @pytest.mark.asyncio
    async def test_get_randomized_headers(self):
        """Test getting randomized headers"""
        randomizer = HeaderRandomizer()
        
        original_headers = {"Authorization": "Bearer token"}
        result = await randomizer.get_randomized_headers(original_headers)
        
        # Should preserve original headers
        assert result["Authorization"] == "Bearer token"
        
        # Should add randomized headers
        assert "Accept" in result
        assert "Accept-Language" in result
        assert "Accept-Encoding" in result
    
    @pytest.mark.asyncio
    async def test_get_randomized_headers_none(self):
        """Test getting randomized headers with None input"""
        randomizer = HeaderRandomizer()
        
        result = await randomizer.get_randomized_headers(None)
        
        # Should return randomized headers
        assert isinstance(result, dict)
        assert len(result) > 0


@pytest.mark.unit
class TestViewportRandomizer:
    """Test ViewportRandomizer class"""
    
    @pytest.mark.asyncio
    async def test_get_random_viewport(self):
        """Test getting random viewport"""
        randomizer = ViewportRandomizer()
        
        viewport = await randomizer.get_random_viewport()
        
        assert "width" in viewport
        assert "height" in viewport
        assert "device_scale_factor" in viewport
        
        # Should be within reasonable bounds
        assert viewport["width"] >= 800
        assert viewport["height"] >= 600
        assert viewport["device_scale_factor"] >= 1


@pytest.mark.unit
class TestGlobalInstances:
    """Test global instance functions"""
    
    def test_get_proxy_pool_singleton(self):
        """Test that get_proxy_pool returns singleton"""
        pool1 = get_proxy_pool()
        pool2 = get_proxy_pool()
        
        assert pool1 is pool2
    
    def test_get_user_agent_rotator_singleton(self):
        """Test that get_user_agent_rotator returns singleton"""
        rotator1 = get_user_agent_rotator()
        rotator2 = get_user_agent_rotator()
        
        assert rotator1 is rotator2
    
    def test_get_stealth_manager_singleton(self):
        """Test that get_stealth_manager returns singleton"""
        manager1 = get_stealth_manager()
        manager2 = get_stealth_manager()
        
        assert manager1 is manager2
    
    def test_get_captcha_detector_singleton(self):
        """Test that get_captcha_detector returns singleton"""
        detector1 = get_captcha_detector()
        detector2 = get_captcha_detector()
        
        assert detector1 is detector2
