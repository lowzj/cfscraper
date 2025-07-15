import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import httpx
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class WebhookEvent(str, Enum):
    """Types of webhook events"""
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_RETRY = "job.retry"
    EXPORT_COMPLETED = "export.completed"
    RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"


class WebhookStatus(str, Enum):
    """Webhook delivery status"""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class WebhookConfig:
    """Configuration for webhook endpoints"""
    url: str
    secret: Optional[str] = None
    events: List[WebhookEvent] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 60  # seconds
    enabled: bool = True
    verify_ssl: bool = True
    
    def __post_init__(self):
        """Validate webhook configuration"""
        parsed_url = urlparse(self.url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError(f"Invalid webhook URL: {self.url}")


@dataclass
class WebhookDelivery:
    """Represents a webhook delivery attempt"""
    id: str
    webhook_id: str
    event: WebhookEvent
    payload: Dict[str, Any]
    url: str
    status: WebhookStatus = WebhookStatus.PENDING
    attempts: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.now)
    last_attempt_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None


class WebhookSigner:
    """Handles webhook signature generation and verification"""
    
    @staticmethod
    def generate_signature(payload: str, secret: str, algorithm: str = "sha256") -> str:
        """Generate HMAC signature for webhook payload"""
        if not secret:
            return ""
        
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            getattr(hashlib, algorithm)
        ).hexdigest()
        
        return f"{algorithm}={signature}"
    
    @staticmethod
    def verify_signature(payload: str, signature: str, secret: str) -> bool:
        """Verify webhook signature"""
        if not secret or not signature:
            return not secret  # If no secret is configured, don't require signature
        
        # Extract algorithm and signature
        try:
            algorithm, expected_signature = signature.split('=', 1)
        except ValueError:
            return False
        
        # Generate expected signature
        expected = WebhookSigner.generate_signature(payload, secret, algorithm)
        
        # Compare signatures (constant time comparison)
        return hmac.compare_digest(signature, expected)


class WebhookDeliveryService:
    """Handles webhook delivery with retry logic"""
    
    def __init__(self):
        self._deliveries: Dict[str, WebhookDelivery] = {}
        self._webhooks: Dict[str, WebhookConfig] = {}
        self._lock = asyncio.Lock()
        self._delivery_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def register_webhook(self, webhook_id: str, config: WebhookConfig) -> str:
        """Register a webhook endpoint"""
        async with self._lock:
            self._webhooks[webhook_id] = config
            logger.info(f"Registered webhook: {webhook_id} -> {config.url}")
        return webhook_id
    
    async def unregister_webhook(self, webhook_id: str) -> bool:
        """Unregister a webhook endpoint"""
        async with self._lock:
            if webhook_id in self._webhooks:
                del self._webhooks[webhook_id]
                logger.info(f"Unregistered webhook: {webhook_id}")
                return True
        return False
    
    async def send_webhook(
        self,
        event: WebhookEvent,
        payload: Dict[str, Any],
        webhook_id: Optional[str] = None
    ) -> List[str]:
        """
        Send webhook to registered endpoints
        
        Args:
            event: Type of event
            payload: Event payload
            webhook_id: Specific webhook to send to (if None, sends to all matching)
            
        Returns:
            List of delivery IDs
        """
        delivery_ids = []
        
        async with self._lock:
            webhooks_to_notify = {}
            
            if webhook_id:
                # Send to specific webhook
                if webhook_id in self._webhooks:
                    webhooks_to_notify[webhook_id] = self._webhooks[webhook_id]
            else:
                # Send to all webhooks that subscribe to this event
                for wh_id, config in self._webhooks.items():
                    if config.enabled and (not config.events or event in config.events):
                        webhooks_to_notify[wh_id] = config
        
        # Create deliveries
        for wh_id, config in webhooks_to_notify.items():
            delivery_id = f"{wh_id}_{event}_{int(time.time())}"
            
            delivery = WebhookDelivery(
                id=delivery_id,
                webhook_id=wh_id,
                event=event,
                payload=payload,
                url=config.url,
                max_retries=config.max_retries
            )
            
            async with self._lock:
                self._deliveries[delivery_id] = delivery
            
            # Queue for delivery
            await self._delivery_queue.put(delivery_id)
            delivery_ids.append(delivery_id)
            
            logger.info(f"Queued webhook delivery: {delivery_id}")
        
        return delivery_ids
    
    async def start_delivery_worker(self):
        """Start the webhook delivery worker"""
        if self._running:
            return
        
        self._running = True
        self._worker_task = asyncio.create_task(self._delivery_worker())
        logger.info("Webhook delivery worker started")
    
    async def stop_delivery_worker(self):
        """Stop the webhook delivery worker"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("Webhook delivery worker stopped")
    
    async def _delivery_worker(self):
        """Background worker for processing webhook deliveries"""
        while self._running:
            try:
                # Get delivery from queue (with timeout)
                try:
                    delivery_id = await asyncio.wait_for(
                        self._delivery_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process delivery
                await self._process_delivery(delivery_id)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in webhook delivery worker: {str(e)}")
                await asyncio.sleep(1)
    
    async def _process_delivery(self, delivery_id: str):
        """Process a single webhook delivery"""
        async with self._lock:
            delivery = self._deliveries.get(delivery_id)
            if not delivery:
                return
            
            webhook_config = self._webhooks.get(delivery.webhook_id)
            if not webhook_config:
                delivery.status = WebhookStatus.FAILED
                delivery.error_message = "Webhook configuration not found"
                return
        
        # Attempt delivery
        try:
            success = await self._attempt_delivery(delivery, webhook_config)
            
            async with self._lock:
                if success:
                    delivery.status = WebhookStatus.DELIVERED
                    logger.info(f"Webhook delivered successfully: {delivery_id}")
                else:
                    delivery.attempts += 1
                    delivery.last_attempt_at = datetime.now()
                    
                    if delivery.attempts >= delivery.max_retries:
                        delivery.status = WebhookStatus.FAILED
                        logger.error(f"Webhook delivery failed after {delivery.attempts} attempts: {delivery_id}")
                    else:
                        delivery.status = WebhookStatus.RETRYING
                        delivery.next_retry_at = datetime.now() + timedelta(
                            seconds=webhook_config.retry_delay * delivery.attempts
                        )
                        
                        # Schedule retry
                        asyncio.create_task(self._schedule_retry(delivery_id, delivery.next_retry_at))
                        logger.warning(f"Webhook delivery failed, scheduling retry: {delivery_id}")
        
        except Exception as e:
            async with self._lock:
                delivery.status = WebhookStatus.FAILED
                delivery.error_message = str(e)
            logger.error(f"Webhook delivery error: {delivery_id} - {str(e)}")
    
    async def _attempt_delivery(self, delivery: WebhookDelivery, config: WebhookConfig) -> bool:
        """Attempt to deliver a webhook"""
        try:
            # Prepare payload
            payload_data = {
                "event": delivery.event,
                "timestamp": delivery.created_at.isoformat(),
                "delivery_id": delivery.id,
                "data": delivery.payload
            }
            
            payload_json = json.dumps(payload_data, default=str)
            
            # Generate signature
            signature = ""
            if config.secret:
                signature = WebhookSigner.generate_signature(payload_json, config.secret)
            
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "CFScraper-Webhook/1.0",
                **config.headers
            }
            
            if signature:
                headers["X-Webhook-Signature"] = signature
            
            # Make HTTP request
            async with httpx.AsyncClient(
                timeout=config.timeout,
                verify=config.verify_ssl
            ) as client:
                response = await client.post(
                    config.url,
                    content=payload_json,
                    headers=headers
                )
                
                delivery.response_status = response.status_code
                delivery.response_body = response.text[:1000]  # Limit response body size
                
                # Consider 2xx status codes as success
                return 200 <= response.status_code < 300
                
        except Exception as e:
            delivery.error_message = str(e)
            return False
    
    async def _schedule_retry(self, delivery_id: str, retry_time: datetime):
        """Schedule a retry for a failed delivery"""
        delay = (retry_time - datetime.now()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        
        # Re-queue for delivery
        await self._delivery_queue.put(delivery_id)
    
    async def get_delivery_status(self, delivery_id: str) -> Optional[WebhookDelivery]:
        """Get status of a webhook delivery"""
        async with self._lock:
            return self._deliveries.get(delivery_id)
    
    async def get_webhook_stats(self, webhook_id: str) -> Dict[str, Any]:
        """Get statistics for a webhook"""
        async with self._lock:
            webhook_deliveries = [
                d for d in self._deliveries.values()
                if d.webhook_id == webhook_id
            ]
            
            total = len(webhook_deliveries)
            delivered = len([d for d in webhook_deliveries if d.status == WebhookStatus.DELIVERED])
            failed = len([d for d in webhook_deliveries if d.status == WebhookStatus.FAILED])
            pending = len([d for d in webhook_deliveries if d.status == WebhookStatus.PENDING])
            retrying = len([d for d in webhook_deliveries if d.status == WebhookStatus.RETRYING])
            
            return {
                "webhook_id": webhook_id,
                "total_deliveries": total,
                "delivered": delivered,
                "failed": failed,
                "pending": pending,
                "retrying": retrying,
                "success_rate": delivered / total if total > 0 else 0
            }


# Global webhook service instance
_webhook_service: Optional[WebhookDeliveryService] = None


def get_webhook_service() -> WebhookDeliveryService:
    """Get the global webhook service instance"""
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = WebhookDeliveryService()
    return _webhook_service


class WebhookTester:
    """Tools for testing webhook endpoints"""

    def __init__(self, webhook_service: WebhookDeliveryService):
        self.webhook_service = webhook_service

    async def test_webhook_endpoint(
        self,
        url: str,
        secret: Optional[str] = None,
        timeout: int = 10
    ) -> Dict[str, Any]:
        """Test a webhook endpoint with a sample payload"""
        test_payload = {
            "event": WebhookEvent.JOB_COMPLETED,
            "timestamp": datetime.now().isoformat(),
            "delivery_id": "test_delivery",
            "data": {
                "job_id": "test_job_123",
                "status": "completed",
                "url": "https://example.com",
                "result": {
                    "status_code": 200,
                    "content": "Sample content",
                    "response_time": 1.5
                }
            }
        }

        try:
            payload_json = json.dumps(test_payload, default=str)

            # Generate signature if secret provided
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "CFScraper-Webhook-Test/1.0"
            }

            if secret:
                signature = WebhookSigner.generate_signature(payload_json, secret)
                headers["X-Webhook-Signature"] = signature

            # Make test request
            start_time = time.time()
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    content=payload_json,
                    headers=headers
                )

            response_time = time.time() - start_time

            return {
                "success": True,
                "status_code": response.status_code,
                "response_time": response_time,
                "response_headers": dict(response.headers),
                "response_body": response.text[:500],  # Limit response body
                "test_payload": test_payload
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "test_payload": test_payload
            }

    async def validate_webhook_signature(
        self,
        payload: str,
        signature: str,
        secret: str
    ) -> Dict[str, Any]:
        """Validate a webhook signature"""
        try:
            is_valid = WebhookSigner.verify_signature(payload, signature, secret)

            return {
                "valid": is_valid,
                "signature": signature,
                "expected_signature": WebhookSigner.generate_signature(payload, secret) if secret else None
            }

        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }


class WebhookEventFilter:
    """Filters webhook events based on conditions"""

    def __init__(self):
        self._filters: Dict[str, Callable[[Dict[str, Any]], bool]] = {}

    def add_filter(self, filter_id: str, filter_func: Callable[[Dict[str, Any]], bool]):
        """Add a custom filter function"""
        self._filters[filter_id] = filter_func
        logger.info(f"Added webhook filter: {filter_id}")

    def remove_filter(self, filter_id: str):
        """Remove a filter"""
        if filter_id in self._filters:
            del self._filters[filter_id]
            logger.info(f"Removed webhook filter: {filter_id}")

    def should_send_webhook(self, event: WebhookEvent, payload: Dict[str, Any]) -> bool:
        """Check if webhook should be sent based on filters"""
        for filter_id, filter_func in self._filters.items():
            try:
                if not filter_func(payload):
                    logger.debug(f"Webhook filtered out by {filter_id}")
                    return False
            except Exception as e:
                logger.error(f"Error in webhook filter {filter_id}: {str(e)}")
                # Continue with other filters

        return True

    def add_status_filter(self, allowed_statuses: List[str]):
        """Add filter for job status"""
        def status_filter(payload: Dict[str, Any]) -> bool:
            job_status = payload.get("status")
            return job_status in allowed_statuses

        self.add_filter("status_filter", status_filter)

    def add_url_pattern_filter(self, patterns: List[str]):
        """Add filter for URL patterns"""
        def url_pattern_filter(payload: Dict[str, Any]) -> bool:
            url = payload.get("url", "")
            return any(pattern in url for pattern in patterns)

        self.add_filter("url_pattern_filter", url_pattern_filter)

    def add_response_time_filter(self, max_response_time: float):
        """Add filter for response time"""
        def response_time_filter(payload: Dict[str, Any]) -> bool:
            result = payload.get("result", {})
            response_time = result.get("response_time", 0)
            return response_time <= max_response_time

        self.add_filter("response_time_filter", response_time_filter)


async def initialize_webhook_system():
    """Initialize the webhook system"""
    webhook_service = get_webhook_service()
    await webhook_service.start_delivery_worker()
    logger.info("Webhook system initialized")


async def shutdown_webhook_system():
    """Shutdown the webhook system"""
    global _webhook_service
    if _webhook_service:
        await _webhook_service.stop_delivery_worker()
        logger.info("Webhook system shutdown complete")


# Convenience functions for common webhook operations
async def send_job_completed_webhook(job_data: Dict[str, Any], webhook_id: Optional[str] = None):
    """Send job completed webhook"""
    webhook_service = get_webhook_service()
    return await webhook_service.send_webhook(
        event=WebhookEvent.JOB_COMPLETED,
        payload=job_data,
        webhook_id=webhook_id
    )


async def send_job_failed_webhook(job_data: Dict[str, Any], webhook_id: Optional[str] = None):
    """Send job failed webhook"""
    webhook_service = get_webhook_service()
    return await webhook_service.send_webhook(
        event=WebhookEvent.JOB_FAILED,
        payload=job_data,
        webhook_id=webhook_id
    )


async def send_export_completed_webhook(export_data: Dict[str, Any], webhook_id: Optional[str] = None):
    """Send export completed webhook"""
    webhook_service = get_webhook_service()
    return await webhook_service.send_webhook(
        event=WebhookEvent.EXPORT_COMPLETED,
        payload=export_data,
        webhook_id=webhook_id
    )
