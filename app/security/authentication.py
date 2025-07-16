"""
API Key Authentication System

Provides secure API key generation, validation, and management with different permission levels.
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Dict, List, Set
from dataclasses import dataclass
import logging

from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

logger = logging.getLogger(__name__)

# Global instance
_api_key_manager = None


class APIKeyPermission(Enum):
    """API Key permission levels"""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


@dataclass
class APIKeyInfo:
    """API Key information"""
    key_id: str
    key_hash: str
    permissions: Set[APIKeyPermission]
    created_at: datetime
    expires_at: Optional[datetime]
    last_used: Optional[datetime]
    usage_count: int
    is_active: bool
    description: str


class APIKeyManager:
    """Manages API keys with secure generation, validation, and permissions"""
    
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode('utf-8')
        self.api_keys: Dict[str, APIKeyInfo] = {}
        self._load_admin_keys()
    
    def _load_admin_keys(self):
        """Load admin API keys from configuration"""
        for admin_key in settings.admin_api_keys:
            if admin_key:
                key_hash = self._hash_key(admin_key)
                self.api_keys[key_hash] = APIKeyInfo(
                    key_id=f"admin_{len(self.api_keys)}",
                    key_hash=key_hash,
                    permissions={APIKeyPermission.READ, APIKeyPermission.WRITE, APIKeyPermission.ADMIN},
                    created_at=datetime.now(timezone.utc),
                    expires_at=None,  # Admin keys don't expire
                    last_used=None,
                    usage_count=0,
                    is_active=True,
                    description="Admin API Key"
                )
    
    def _hash_key(self, api_key: str) -> str:
        """Hash an API key using HMAC-SHA256"""
        return hmac.new(
            self.secret_key,
            api_key.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def generate_api_key(
        self,
        permissions: Set[APIKeyPermission],
        expires_in_days: Optional[int] = None,
        description: str = "Generated API Key"
    ) -> str:
        """Generate a new API key with specified permissions"""
        # Generate secure random key
        api_key = f"cfsk_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(api_key)
        
        # Calculate expiry
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        elif settings.api_key_expiry_days > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(days=settings.api_key_expiry_days)
        
        # Store key info
        self.api_keys[key_hash] = APIKeyInfo(
            key_id=f"key_{len(self.api_keys)}",
            key_hash=key_hash,
            permissions=permissions,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            last_used=None,
            usage_count=0,
            is_active=True,
            description=description
        )
        
        logger.info(f"Generated API key with permissions: {[p.value for p in permissions]}")
        return api_key
    
    def validate_api_key(
        self,
        api_key: str,
        required_permission: Optional[APIKeyPermission] = None
    ) -> Optional[APIKeyInfo]:
        """Validate an API key and check permissions"""
        if not api_key:
            return None
        
        key_hash = self._hash_key(api_key)
        key_info = self.api_keys.get(key_hash)
        
        if not key_info:
            return None
        
        # Check if key is active
        if not key_info.is_active:
            return None
        
        # Check expiry
        if key_info.expires_at and datetime.now(timezone.utc) > key_info.expires_at:
            key_info.is_active = False
            logger.warning(f"API key {key_info.key_id} has expired")
            return None
        
        # Check permissions
        if required_permission and required_permission not in key_info.permissions:
            return None
        
        # Update usage
        key_info.last_used = datetime.now(timezone.utc)
        key_info.usage_count += 1
        
        return key_info
    
    def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key"""
        key_hash = self._hash_key(api_key)
        key_info = self.api_keys.get(key_hash)
        
        if key_info:
            key_info.is_active = False
            logger.info(f"Revoked API key {key_info.key_id}")
            return True
        
        return False
    
    def list_api_keys(self) -> List[Dict]:
        """List all API keys (without the actual keys)"""
        return [
            {
                "key_id": info.key_id,
                "permissions": [p.value for p in info.permissions],
                "created_at": info.created_at.isoformat(),
                "expires_at": info.expires_at.isoformat() if info.expires_at else None,
                "last_used": info.last_used.isoformat() if info.last_used else None,
                "usage_count": info.usage_count,
                "is_active": info.is_active,
                "description": info.description
            }
            for info in self.api_keys.values()
        ]
    
    def cleanup_expired_keys(self) -> int:
        """Remove expired keys and return count of removed keys"""
        now = datetime.now(timezone.utc)
        expired_keys = []
        
        for key_hash, key_info in self.api_keys.items():
            if (key_info.expires_at and now > key_info.expires_at) or not key_info.is_active:
                expired_keys.append(key_hash)
        
        for key_hash in expired_keys:
            del self.api_keys[key_hash]
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired API keys")
        
        return len(expired_keys)


def get_api_key_manager() -> APIKeyManager:
    """Get the global API key manager instance"""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager(settings.api_key_secret)
    return _api_key_manager


# FastAPI security scheme
security = HTTPBearer(auto_error=False)


async def verify_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    required_permission: Optional[APIKeyPermission] = None
) -> Optional[APIKeyInfo]:
    """Verify API key from request"""
    api_key = None
    
    # Try to get API key from Authorization header
    if credentials:
        api_key = credentials.credentials
    
    # Try to get API key from X-API-Key header
    if not api_key:
        api_key = request.headers.get("X-API-Key")
    
    # Try to get API key from query parameter (less secure, for testing only)
    if not api_key and settings.debug:
        api_key = request.query_params.get("api_key")
    
    if not api_key:
        return None
    
    manager = get_api_key_manager()
    return manager.validate_api_key(api_key, required_permission)


async def require_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    required_permission: APIKeyPermission = APIKeyPermission.READ
) -> APIKeyInfo:
    """Require valid API key with specified permission"""
    key_info = await verify_api_key(request, credentials, required_permission)
    
    if not key_info:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return key_info


async def require_admin_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> APIKeyInfo:
    """Require admin API key"""
    return await require_api_key(request, credentials, APIKeyPermission.ADMIN)
