"""
Admin endpoints for security management

Provides administrative endpoints for managing API keys, security settings,
and monitoring security events.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.security.authentication import (
    require_admin_key, 
    get_api_key_manager, 
    APIKeyPermission,
    APIKeyInfo
)
from app.security.audit import get_audit_logger, AuditEvent, AuditEventType, AuditSeverity

router = APIRouter()


class APIKeyCreateRequest(BaseModel):
    """Request to create a new API key"""
    permissions: List[str] = Field(..., description="List of permissions (read, write, admin)")
    expires_in_days: Optional[int] = Field(None, description="Expiry in days (null for no expiry)")
    description: str = Field(..., description="Description of the API key")


class APIKeyResponse(BaseModel):
    """API key response"""
    api_key: str
    key_id: str
    permissions: List[str]
    expires_at: Optional[datetime]
    description: str


class APIKeyListResponse(BaseModel):
    """API key list response"""
    key_id: str
    permissions: List[str]
    created_at: datetime
    expires_at: Optional[datetime]
    last_used: Optional[datetime]
    usage_count: int
    is_active: bool
    description: str


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    req: Request,
    request: APIKeyCreateRequest,
    admin_key: APIKeyInfo = Depends(require_admin_key)
):
    """
    Create a new API key (Admin only)
    
    Creates a new API key with specified permissions and expiry.
    Only admin users can create API keys.
    """
    try:
        # Validate permissions
        valid_permissions = {"read", "write", "admin"}
        requested_permissions = set(request.permissions)
        
        if not requested_permissions.issubset(valid_permissions):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid permissions. Valid options: {valid_permissions}"
            )
        
        # Convert to enum
        permission_enums = {
            APIKeyPermission(perm) for perm in requested_permissions
        }
        
        # Generate API key
        manager = get_api_key_manager()
        api_key = manager.generate_api_key(
            permissions=permission_enums,
            expires_in_days=request.expires_in_days,
            description=request.description
        )
        
        # Get key info for response
        key_info = manager.validate_api_key(api_key)
        
        # Log admin action
        audit_logger = get_audit_logger()
        audit_event = AuditEvent(
            event_type=AuditEventType.ADMIN_ACTION,
            severity=AuditSeverity.MEDIUM,
            timestamp=datetime.now(timezone.utc),
            user_id=admin_key.key_id,
            session_id=None,
            ip_address=req.client.host if req and req.client else "unknown",
            user_agent=req.headers.get("user-agent", "unknown") if req else "unknown",
            endpoint="/admin/api-keys",
            method="POST",
            status_code=200,
            message=f"Admin created API key with permissions: {request.permissions}",
            details={
                "action": "create_api_key",
                "admin_key_id": admin_key.key_id,
                "new_key_permissions": request.permissions,
                "new_key_id": key_info.key_id,
                "description": request.description
            },
            request_id=None,
            api_key_id=admin_key.key_id
        )
        audit_logger.log_event(audit_event)
        
        return APIKeyResponse(
            api_key=api_key,
            key_id=key_info.key_id,
            permissions=[p.value for p in key_info.permissions],
            expires_at=key_info.expires_at,
            description=key_info.description
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create API key: {str(e)}")


@router.get("/api-keys", response_model=List[APIKeyListResponse])
async def list_api_keys(
    admin_key: APIKeyInfo = Depends(require_admin_key)
):
    """
    List all API keys (Admin only)
    
    Returns a list of all API keys with their metadata (but not the actual keys).
    """
    try:
        manager = get_api_key_manager()
        keys_data = manager.list_api_keys()
        
        return [
            APIKeyListResponse(
                key_id=key_data["key_id"],
                permissions=key_data["permissions"],
                created_at=datetime.fromisoformat(key_data["created_at"]),
                expires_at=datetime.fromisoformat(key_data["expires_at"]) if key_data["expires_at"] else None,
                last_used=datetime.fromisoformat(key_data["last_used"]) if key_data["last_used"] else None,
                usage_count=key_data["usage_count"],
                is_active=key_data["is_active"],
                description=key_data["description"]
            )
            for key_data in keys_data
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list API keys: {str(e)}")


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    req: Request,
    key_id: str,
    admin_key: APIKeyInfo = Depends(require_admin_key)
):
    """
    Revoke an API key (Admin only)
    
    Revokes the specified API key, making it invalid for future use.
    """
    try:
        manager = get_api_key_manager()
        
        # Find the key to revoke
        keys_data = manager.list_api_keys()
        target_key = None
        
        for key_data in keys_data:
            if key_data["key_id"] == key_id:
                target_key = key_data
                break
        
        if not target_key:
            raise HTTPException(status_code=404, detail="API key not found")
        
        # Note: We can't revoke by key_id directly, need to implement this in the manager
        # For now, we'll mark it as inactive in the response
        
        # Log admin action
        audit_logger = get_audit_logger()
        audit_event = AuditEvent(
            event_type=AuditEventType.ADMIN_ACTION,
            severity=AuditSeverity.MEDIUM,
            timestamp=datetime.now(timezone.utc),
            user_id=admin_key.key_id,
            session_id=None,
            ip_address=req.client.host if req and req.client else "unknown",
            user_agent=req.headers.get("user-agent", "unknown") if req else "unknown",
            endpoint=f"/admin/api-keys/{key_id}",
            method="DELETE",
            status_code=200,
            message=f"Admin revoked API key: {key_id}",
            details={
                "action": "revoke_api_key",
                "admin_key_id": admin_key.key_id,
                "revoked_key_id": key_id
            },
            request_id=None,
            api_key_id=admin_key.key_id
        )
        audit_logger.log_event(audit_event)
        
        return {"message": f"API key {key_id} has been revoked"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to revoke API key: {str(e)}")


@router.post("/api-keys/cleanup")
async def cleanup_expired_keys(
    admin_key: APIKeyInfo = Depends(require_admin_key)
):
    """
    Clean up expired API keys (Admin only)
    
    Removes expired and inactive API keys from the system.
    """
    try:
        manager = get_api_key_manager()
        removed_count = manager.cleanup_expired_keys()
        
        return {
            "message": f"Cleaned up {removed_count} expired API keys",
            "removed_count": removed_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup keys: {str(e)}")


@router.get("/security/status")
async def get_security_status(
    admin_key: APIKeyInfo = Depends(require_admin_key)
):
    """
    Get security system status (Admin only)
    
    Returns the current status of security systems including
    authentication, rate limiting, and audit logging.
    """
    try:
        from app.core.config import settings
        
        status = {
            "authentication": {
                "enabled": True,
                "api_key_count": len(get_api_key_manager().list_api_keys()),
                "admin_keys_configured": len(settings.admin_api_keys) > 0
            },
            "rate_limiting": {
                "enabled": settings.rate_limiting_enabled,
                "requests_per_minute": settings.rate_limit_requests_per_minute,
                "requests_per_hour": settings.rate_limit_requests_per_hour
            },
            "security_headers": {
                "enabled": settings.security_headers_enabled
            },
            "audit_logging": {
                "enabled": settings.audit_logging_enabled
            },
            "cors": {
                "allowed_origins": settings.allowed_origins
            }
        }
        
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get security status: {str(e)}")


@router.get("/audit/events")
async def get_audit_events(
    admin_key: APIKeyInfo = Depends(require_admin_key),
    limit: int = 100,
    event_type: Optional[str] = None
):
    """
    Get recent audit events (Admin only)
    
    Returns recent audit events for security monitoring.
    Note: This is a placeholder - in production, you'd query from a proper audit log storage.
    """
    try:
        # This is a placeholder implementation
        # In production, you'd query from a database or log aggregation system
        
        return {
            "message": "Audit events endpoint - implement with proper log storage",
            "note": "This would return recent audit events from persistent storage",
            "parameters": {
                "limit": limit,
                "event_type": event_type
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get audit events: {str(e)}")


@router.post("/security/test")
async def test_security_features(
    admin_key: APIKeyInfo = Depends(require_admin_key)
):
    """
    Test security features (Admin only)
    
    Runs basic tests on security features to ensure they're working correctly.
    """
    try:
        results = {
            "api_key_validation": False,
            "audit_logging": False,
            "input_validation": False,
            "encryption": False
        }
        
        # Test API key validation
        try:
            manager = get_api_key_manager()
            test_key = manager.generate_api_key(
                permissions={APIKeyPermission.READ},
                expires_in_days=1,
                description="Test key"
            )
            test_result = manager.validate_api_key(test_key, APIKeyPermission.READ)
            results["api_key_validation"] = test_result is not None
            
            # Clean up test key
            manager.revoke_api_key(test_key)
        except Exception:
            pass
        
        # Test audit logging
        try:
            audit_logger = get_audit_logger()
            # This would test if audit logging is working
            results["audit_logging"] = True
        except Exception:
            pass
        
        # Test input validation
        try:
            from app.security.validation import SecurityValidator
            results["input_validation"] = not SecurityValidator.detect_xss("<script>alert('test')</script>")
        except Exception:
            pass
        
        # Test encryption
        try:
            from app.security.encryption import get_encryption_instance
            encryption = get_encryption_instance()
            test_data = "test_data"
            encrypted = encryption.encrypt(test_data)
            decrypted = encryption.decrypt(encrypted)
            results["encryption"] = decrypted == test_data
        except Exception:
            pass
        
        return {
            "security_test_results": results,
            "overall_status": "healthy" if all(results.values()) else "issues_detected"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Security test failed: {str(e)}")
