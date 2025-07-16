"""
Security Audit Logging

Provides comprehensive audit logging for security events, API access,
authentication attempts, and other security-relevant activities.
"""

import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import logging
import hashlib

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from .encryption import anonymize_log_data, get_encryption_instance

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events"""
    AUTHENTICATION_SUCCESS = "auth_success"
    AUTHENTICATION_FAILURE = "auth_failure"
    API_ACCESS = "api_access"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SECURITY_VIOLATION = "security_violation"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    ADMIN_ACTION = "admin_action"
    ERROR = "error"
    SYSTEM_EVENT = "system_event"


class AuditSeverity(Enum):
    """Audit event severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event data structure"""
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: datetime
    user_id: Optional[str]
    session_id: Optional[str]
    ip_address: str
    user_agent: str
    endpoint: str
    method: str
    status_code: Optional[int]
    message: str
    details: Dict[str, Any]
    request_id: Optional[str]
    api_key_id: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        data = asdict(self)
        data['event_type'] = self.event_type.value
        data['severity'] = self.severity.value
        data['timestamp'] = self.timestamp.isoformat()
        return data


class AuditLogger:
    """Centralized audit logging system"""
    
    def __init__(self):
        self.encryption = get_encryption_instance()
        self.audit_logger = logging.getLogger("audit")
        self._setup_audit_logger()
    
    def _setup_audit_logger(self):
        """Setup dedicated audit logger"""
        # Create audit-specific handler if not exists
        if not self.audit_logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - AUDIT - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.audit_logger.addHandler(handler)
            self.audit_logger.setLevel(logging.INFO)
    
    def log_event(self, event: AuditEvent):
        """Log an audit event"""
        if not settings.audit_logging_enabled:
            return
        
        try:
            # Anonymize sensitive data
            event_data = anonymize_log_data(event.to_dict())
            
            # Add integrity hash
            event_data['integrity_hash'] = self._calculate_integrity_hash(event_data)
            
            # Log the event
            log_message = f"AUDIT: {event.event_type.value} - {event.message}"
            
            if event.severity in [AuditSeverity.HIGH, AuditSeverity.CRITICAL]:
                self.audit_logger.error(log_message, extra={"audit_data": event_data})
            elif event.severity == AuditSeverity.MEDIUM:
                self.audit_logger.warning(log_message, extra={"audit_data": event_data})
            else:
                self.audit_logger.info(log_message, extra={"audit_data": event_data})
        
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
    
    def _calculate_integrity_hash(self, event_data: Dict[str, Any]) -> str:
        """Calculate integrity hash for audit event"""
        # Create a deterministic string representation
        sorted_data = json.dumps(event_data, sort_keys=True, default=str)
        return hashlib.sha256(sorted_data.encode()).hexdigest()
    
    def log_authentication_success(
        self,
        user_id: str,
        ip_address: str,
        user_agent: str,
        api_key_id: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        """Log successful authentication"""
        event = AuditEvent(
            event_type=AuditEventType.AUTHENTICATION_SUCCESS,
            severity=AuditSeverity.LOW,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            session_id=None,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint="/auth",
            method="POST",
            status_code=200,
            message=f"User {user_id} authenticated successfully",
            details={"api_key_id": api_key_id},
            request_id=request_id,
            api_key_id=api_key_id
        )
        self.log_event(event)
    
    def log_authentication_failure(
        self,
        ip_address: str,
        user_agent: str,
        reason: str,
        request_id: Optional[str] = None
    ):
        """Log failed authentication"""
        event = AuditEvent(
            event_type=AuditEventType.AUTHENTICATION_FAILURE,
            severity=AuditSeverity.MEDIUM,
            timestamp=datetime.now(timezone.utc),
            user_id=None,
            session_id=None,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint="/auth",
            method="POST",
            status_code=401,
            message=f"Authentication failed: {reason}",
            details={"failure_reason": reason},
            request_id=request_id,
            api_key_id=None
        )
        self.log_event(event)
    
    def log_api_access(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        ip_address: str,
        user_agent: str,
        user_id: Optional[str] = None,
        api_key_id: Optional[str] = None,
        request_id: Optional[str] = None,
        response_time: Optional[float] = None
    ):
        """Log API access"""
        severity = AuditSeverity.LOW
        if status_code >= 400:
            severity = AuditSeverity.MEDIUM
        if status_code >= 500:
            severity = AuditSeverity.HIGH
        
        event = AuditEvent(
            event_type=AuditEventType.API_ACCESS,
            severity=severity,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            session_id=None,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            message=f"API access: {method} {endpoint} - {status_code}",
            details={
                "response_time": response_time,
                "api_key_id": api_key_id
            },
            request_id=request_id,
            api_key_id=api_key_id
        )
        self.log_event(event)
    
    def log_security_violation(
        self,
        violation_type: str,
        ip_address: str,
        user_agent: str,
        endpoint: str,
        details: Dict[str, Any],
        request_id: Optional[str] = None
    ):
        """Log security violation"""
        event = AuditEvent(
            event_type=AuditEventType.SECURITY_VIOLATION,
            severity=AuditSeverity.HIGH,
            timestamp=datetime.now(timezone.utc),
            user_id=None,
            session_id=None,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            method="",
            status_code=None,
            message=f"Security violation detected: {violation_type}",
            details=details,
            request_id=request_id,
            api_key_id=None
        )
        self.log_event(event)
    
    def log_rate_limit_exceeded(
        self,
        ip_address: str,
        user_agent: str,
        endpoint: str,
        limit_type: str,
        request_id: Optional[str] = None
    ):
        """Log rate limit exceeded"""
        event = AuditEvent(
            event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
            severity=AuditSeverity.MEDIUM,
            timestamp=datetime.now(timezone.utc),
            user_id=None,
            session_id=None,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            method="",
            status_code=429,
            message=f"Rate limit exceeded: {limit_type}",
            details={"limit_type": limit_type},
            request_id=request_id,
            api_key_id=None
        )
        self.log_event(event)


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware for automatic audit logging of requests"""
    
    def __init__(self, app):
        super().__init__(app)
        self.audit_logger = AuditLogger()
    
    async def dispatch(self, request: Request, call_next):
        """Log request and response"""
        start_time = time.time()
        request_id = request.headers.get("X-Request-ID", "unknown")
        
        # Extract request info
        ip_address = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        endpoint = str(request.url.path)
        method = request.method
        
        # Process request
        response = await call_next(request)
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Extract user info if available
        user_id = getattr(request.state, 'user_id', None)
        api_key_id = getattr(request.state, 'api_key_id', None)
        
        # Log API access
        self.audit_logger.log_api_access(
            endpoint=endpoint,
            method=method,
            status_code=response.status_code,
            ip_address=ip_address,
            user_agent=user_agent,
            user_id=user_id,
            api_key_id=api_key_id,
            request_id=request_id,
            response_time=response_time
        )
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address"""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        if request.client:
            return request.client.host
        
        return "unknown"


# Global audit logger instance
_audit_logger = None


def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


# Convenience functions
def log_authentication_success(user_id: str, ip_address: str, user_agent: str, **kwargs):
    """Log successful authentication"""
    get_audit_logger().log_authentication_success(user_id, ip_address, user_agent, **kwargs)


def log_authentication_failure(ip_address: str, user_agent: str, reason: str, **kwargs):
    """Log failed authentication"""
    get_audit_logger().log_authentication_failure(ip_address, user_agent, reason, **kwargs)


def log_security_violation(violation_type: str, ip_address: str, user_agent: str, endpoint: str, details: Dict[str, Any], **kwargs):
    """Log security violation"""
    get_audit_logger().log_security_violation(violation_type, ip_address, user_agent, endpoint, details, **kwargs)


def log_rate_limit_exceeded(ip_address: str, user_agent: str, endpoint: str, limit_type: str, **kwargs):
    """Log rate limit exceeded"""
    get_audit_logger().log_rate_limit_exceeded(ip_address, user_agent, endpoint, limit_type, **kwargs)
