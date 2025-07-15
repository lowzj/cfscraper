"""
Unit tests for webhook delivery system
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
import json
import hmac
import hashlib

from app.utils.webhooks import (
    WebhookEvent, WebhookStatus, WebhookConfig, WebhookDelivery,
    WebhookSigner, WebhookDeliveryService, WebhookTester, WebhookEventFilter,
    get_webhook_service, send_job_completed_webhook
)


@pytest.mark.unit
class TestWebhookConfig:
    """Test WebhookConfig dataclass"""
    
    def test_webhook_config_creation(self):
        """Test creating webhook configuration"""
        config = WebhookConfig(
            url="https://example.com/webhook",
            secret="secret123",
            events=[WebhookEvent.JOB_COMPLETED],
            headers={"Authorization": "Bearer token"},
            timeout=60,
            max_retries=5
        )
        
        assert config.url == "https://example.com/webhook"
        assert config.secret == "secret123"
        assert config.events == [WebhookEvent.JOB_COMPLETED]
        assert config.headers == {"Authorization": "Bearer token"}
        assert config.timeout == 60
        assert config.max_retries == 5
        assert config.enabled is True
        assert config.verify_ssl is True
    
    def test_webhook_config_defaults(self):
        """Test webhook configuration defaults"""
        config = WebhookConfig(url="https://example.com/webhook")
        
        assert config.secret is None
        assert config.events == []
        assert config.headers == {}
        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.retry_delay == 60
        assert config.enabled is True
        assert config.verify_ssl is True
    
    def test_webhook_config_invalid_url(self):
        """Test webhook configuration with invalid URL"""
        with pytest.raises(ValueError, match="Invalid webhook URL"):
            WebhookConfig(url="not-a-url")
        
        with pytest.raises(ValueError, match="Invalid webhook URL"):
            WebhookConfig(url="")


@pytest.mark.unit
class TestWebhookDelivery:
    """Test WebhookDelivery dataclass"""
    
    def test_webhook_delivery_creation(self):
        """Test creating webhook delivery"""
        payload = {"job_id": "123", "status": "completed"}
        
        delivery = WebhookDelivery(
            id="delivery-123",
            webhook_id="webhook-1",
            event=WebhookEvent.JOB_COMPLETED,
            payload=payload,
            url="https://example.com/webhook"
        )
        
        assert delivery.id == "delivery-123"
        assert delivery.webhook_id == "webhook-1"
        assert delivery.event == WebhookEvent.JOB_COMPLETED
        assert delivery.payload == payload
        assert delivery.url == "https://example.com/webhook"
        assert delivery.status == WebhookStatus.PENDING
        assert delivery.attempts == 0
        assert delivery.max_retries == 3
        assert isinstance(delivery.created_at, datetime)
    
    def test_webhook_delivery_defaults(self):
        """Test webhook delivery defaults"""
        delivery = WebhookDelivery(
            id="test",
            webhook_id="test",
            event=WebhookEvent.JOB_COMPLETED,
            payload={},
            url="https://example.com"
        )
        
        assert delivery.status == WebhookStatus.PENDING
        assert delivery.attempts == 0
        assert delivery.max_retries == 3
        assert delivery.last_attempt_at is None
        assert delivery.next_retry_at is None
        assert delivery.response_status is None
        assert delivery.response_body is None
        assert delivery.error_message is None


@pytest.mark.unit
class TestWebhookSigner:
    """Test WebhookSigner class"""
    
    def test_generate_signature(self):
        """Test signature generation"""
        payload = '{"test": "data"}'
        secret = "secret123"
        
        signature = WebhookSigner.generate_signature(payload, secret)
        
        assert signature.startswith("sha256=")
        assert len(signature) > 10
    
    def test_generate_signature_no_secret(self):
        """Test signature generation with no secret"""
        payload = '{"test": "data"}'
        
        signature = WebhookSigner.generate_signature(payload, "")
        
        assert signature == ""
    
    def test_verify_signature_valid(self):
        """Test signature verification with valid signature"""
        payload = '{"test": "data"}'
        secret = "secret123"
        
        signature = WebhookSigner.generate_signature(payload, secret)
        is_valid = WebhookSigner.verify_signature(payload, signature, secret)
        
        assert is_valid is True
    
    def test_verify_signature_invalid(self):
        """Test signature verification with invalid signature"""
        payload = '{"test": "data"}'
        secret = "secret123"
        invalid_signature = "sha256=invalid"
        
        is_valid = WebhookSigner.verify_signature(payload, invalid_signature, secret)
        
        assert is_valid is False
    
    def test_verify_signature_no_secret(self):
        """Test signature verification with no secret configured"""
        payload = '{"test": "data"}'
        
        # No secret configured, should return True regardless of signature
        is_valid = WebhookSigner.verify_signature(payload, "", "")
        assert is_valid is True
        
        # With signature but no secret, should return False
        is_valid = WebhookSigner.verify_signature(payload, "sha256=something", "")
        assert is_valid is False
    
    def test_verify_signature_malformed(self):
        """Test signature verification with malformed signature"""
        payload = '{"test": "data"}'
        secret = "secret123"
        malformed_signature = "invalid-format"
        
        is_valid = WebhookSigner.verify_signature(payload, malformed_signature, secret)
        
        assert is_valid is False


@pytest.mark.unit
class TestWebhookDeliveryService:
    """Test WebhookDeliveryService class"""
    
    @pytest.mark.asyncio
    async def test_register_webhook(self):
        """Test registering a webhook"""
        service = WebhookDeliveryService()
        config = WebhookConfig(url="https://example.com/webhook")
        
        webhook_id = await service.register_webhook("webhook-1", config)
        
        assert webhook_id == "webhook-1"
        
        # Verify webhook is registered
        registered_config = await service.get_webhook("webhook-1")
        assert registered_config == config
    
    @pytest.mark.asyncio
    async def test_unregister_webhook(self):
        """Test unregistering a webhook"""
        service = WebhookDeliveryService()
        config = WebhookConfig(url="https://example.com/webhook")
        
        await service.register_webhook("webhook-1", config)
        removed = await service.unregister_webhook("webhook-1")
        
        assert removed is True
        
        # Verify webhook is removed
        registered_config = await service.get_webhook("webhook-1")
        assert registered_config is None
        
        # Try to remove non-existent webhook
        removed = await service.unregister_webhook("nonexistent")
        assert removed is False
    
    @pytest.mark.asyncio
    async def test_send_webhook_to_specific_endpoint(self):
        """Test sending webhook to specific endpoint"""
        service = WebhookDeliveryService()
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=[WebhookEvent.JOB_COMPLETED]
        )
        
        await service.register_webhook("webhook-1", config)
        
        payload = {"job_id": "123", "status": "completed"}
        delivery_ids = await service.send_webhook(
            WebhookEvent.JOB_COMPLETED,
            payload,
            webhook_id="webhook-1"
        )
        
        assert len(delivery_ids) == 1
        assert delivery_ids[0].startswith("webhook-1_job.completed_")
    
    @pytest.mark.asyncio
    async def test_send_webhook_to_all_matching_endpoints(self):
        """Test sending webhook to all matching endpoints"""
        service = WebhookDeliveryService()
        
        # Register multiple webhooks
        config1 = WebhookConfig(
            url="https://example.com/webhook1",
            events=[WebhookEvent.JOB_COMPLETED]
        )
        config2 = WebhookConfig(
            url="https://example.com/webhook2",
            events=[WebhookEvent.JOB_COMPLETED, WebhookEvent.JOB_FAILED]
        )
        config3 = WebhookConfig(
            url="https://example.com/webhook3",
            events=[WebhookEvent.JOB_FAILED]  # Should not receive JOB_COMPLETED
        )
        
        await service.register_webhook("webhook-1", config1)
        await service.register_webhook("webhook-2", config2)
        await service.register_webhook("webhook-3", config3)
        
        payload = {"job_id": "123", "status": "completed"}
        delivery_ids = await service.send_webhook(WebhookEvent.JOB_COMPLETED, payload)
        
        # Should send to webhook-1 and webhook-2, but not webhook-3
        assert len(delivery_ids) == 2
    
    @pytest.mark.asyncio
    async def test_send_webhook_disabled_endpoint(self):
        """Test that disabled webhooks don't receive events"""
        service = WebhookDeliveryService()
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=[WebhookEvent.JOB_COMPLETED],
            enabled=False
        )
        
        await service.register_webhook("webhook-1", config)
        
        payload = {"job_id": "123", "status": "completed"}
        delivery_ids = await service.send_webhook(WebhookEvent.JOB_COMPLETED, payload)
        
        # Should not send to disabled webhook
        assert len(delivery_ids) == 0
    
    @pytest.mark.asyncio
    async def test_start_stop_delivery_worker(self):
        """Test starting and stopping delivery worker"""
        service = WebhookDeliveryService()
        
        assert service._running is False
        assert service._worker_task is None
        
        await service.start_delivery_worker()
        
        assert service._running is True
        assert service._worker_task is not None
        
        await service.stop_delivery_worker()
        
        assert service._running is False
    
    @pytest.mark.asyncio
    async def test_delivery_attempt_success(self):
        """Test successful webhook delivery"""
        service = WebhookDeliveryService()
        config = WebhookConfig(url="https://example.com/webhook")
        
        delivery = WebhookDelivery(
            id="test-delivery",
            webhook_id="webhook-1",
            event=WebhookEvent.JOB_COMPLETED,
            payload={"job_id": "123"},
            url=config.url
        )
        
        # Mock successful HTTP response
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            success = await service._attempt_delivery(delivery, config)
            
            assert success is True
            assert delivery.response_status == 200
            assert delivery.response_body == "OK"
    
    @pytest.mark.asyncio
    async def test_delivery_attempt_failure(self):
        """Test failed webhook delivery"""
        service = WebhookDeliveryService()
        config = WebhookConfig(url="https://example.com/webhook")
        
        delivery = WebhookDelivery(
            id="test-delivery",
            webhook_id="webhook-1",
            event=WebhookEvent.JOB_COMPLETED,
            payload={"job_id": "123"},
            url=config.url
        )
        
        # Mock failed HTTP response
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            success = await service._attempt_delivery(delivery, config)
            
            assert success is False
            assert delivery.response_status == 500
            assert delivery.response_body == "Internal Server Error"
    
    @pytest.mark.asyncio
    async def test_delivery_attempt_with_signature(self):
        """Test webhook delivery with signature"""
        service = WebhookDeliveryService()
        config = WebhookConfig(
            url="https://example.com/webhook",
            secret="secret123"
        )
        
        delivery = WebhookDelivery(
            id="test-delivery",
            webhook_id="webhook-1",
            event=WebhookEvent.JOB_COMPLETED,
            payload={"job_id": "123"},
            url=config.url
        )
        
        # Mock successful HTTP response
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            success = await service._attempt_delivery(delivery, config)
            
            assert success is True
            
            # Verify signature was included in headers
            call_args = mock_post.call_args
            headers = call_args[1]["headers"]
            assert "X-Webhook-Signature" in headers
            assert headers["X-Webhook-Signature"].startswith("sha256=")


@pytest.mark.unit
class TestWebhookTester:
    """Test WebhookTester class"""
    
    @pytest.mark.asyncio
    async def test_test_webhook_endpoint_success(self):
        """Test successful webhook endpoint test"""
        service = WebhookDeliveryService()
        tester = WebhookTester(service)
        
        # Mock successful HTTP response
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_response.headers = {"content-type": "text/plain"}
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            result = await tester.test_webhook_endpoint("https://example.com/webhook")
            
            assert result["success"] is True
            assert result["status_code"] == 200
            assert "response_time" in result
            assert "test_payload" in result
    
    @pytest.mark.asyncio
    async def test_test_webhook_endpoint_failure(self):
        """Test failed webhook endpoint test"""
        service = WebhookDeliveryService()
        tester = WebhookTester(service)
        
        # Mock HTTP exception
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection failed")
            )
            
            result = await tester.test_webhook_endpoint("https://example.com/webhook")
            
            assert result["success"] is False
            assert "error" in result
            assert "Connection failed" in result["error"]
    
    @pytest.mark.asyncio
    async def test_validate_webhook_signature(self):
        """Test webhook signature validation"""
        service = WebhookDeliveryService()
        tester = WebhookTester(service)
        
        payload = '{"test": "data"}'
        secret = "secret123"
        signature = WebhookSigner.generate_signature(payload, secret)
        
        result = await tester.validate_webhook_signature(payload, signature, secret)
        
        assert result["valid"] is True
        assert result["signature"] == signature
        assert "expected_signature" in result


@pytest.mark.unit
class TestWebhookEventFilter:
    """Test WebhookEventFilter class"""
    
    def test_add_remove_filter(self):
        """Test adding and removing filters"""
        filter_obj = WebhookEventFilter()
        
        def test_filter(payload):
            return payload.get("status") == "completed"
        
        filter_obj.add_filter("status_filter", test_filter)
        
        # Test filter works
        assert filter_obj.should_send_webhook(
            WebhookEvent.JOB_COMPLETED,
            {"status": "completed"}
        ) is True
        
        assert filter_obj.should_send_webhook(
            WebhookEvent.JOB_COMPLETED,
            {"status": "failed"}
        ) is False
        
        # Remove filter
        filter_obj.remove_filter("status_filter")
        
        # Should now pass all events
        assert filter_obj.should_send_webhook(
            WebhookEvent.JOB_COMPLETED,
            {"status": "failed"}
        ) is True
    
    def test_status_filter(self):
        """Test built-in status filter"""
        filter_obj = WebhookEventFilter()
        filter_obj.add_status_filter(["completed", "failed"])
        
        # Should pass allowed statuses
        assert filter_obj.should_send_webhook(
            WebhookEvent.JOB_COMPLETED,
            {"status": "completed"}
        ) is True
        
        assert filter_obj.should_send_webhook(
            WebhookEvent.JOB_FAILED,
            {"status": "failed"}
        ) is True
        
        # Should block other statuses
        assert filter_obj.should_send_webhook(
            WebhookEvent.JOB_STARTED,
            {"status": "running"}
        ) is False


@pytest.mark.unit
class TestWebhookConvenienceFunctions:
    """Test convenience functions"""
    
    @pytest.mark.asyncio
    async def test_send_job_completed_webhook(self):
        """Test send_job_completed_webhook function"""
        with patch('app.utils.webhooks.get_webhook_service') as mock_get_service:
            mock_service = Mock()
            mock_service.send_webhook = AsyncMock(return_value=["delivery-123"])
            mock_get_service.return_value = mock_service
            
            job_data = {"job_id": "123", "status": "completed"}
            delivery_ids = await send_job_completed_webhook(job_data)
            
            assert delivery_ids == ["delivery-123"]
            mock_service.send_webhook.assert_called_once_with(
                event=WebhookEvent.JOB_COMPLETED,
                payload=job_data,
                webhook_id=None
            )
    
    def test_get_webhook_service_singleton(self):
        """Test that get_webhook_service returns singleton"""
        service1 = get_webhook_service()
        service2 = get_webhook_service()
        
        assert service1 is service2
