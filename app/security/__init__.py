"""
Security module for CFScraper API

This module provides security functionality including:
- API key authentication
- Input validation and sanitization
- Rate limiting enhancements
- Security headers
- Data encryption
- Audit logging
"""

from .authentication import (
    APIKeyManager,
    get_api_key_manager,
    verify_api_key,
    require_api_key,
    require_admin_key,
    APIKeyPermission
)

from .validation import (
    SecurityValidator,
    sanitize_input,
    validate_url,
    validate_headers,
    prevent_xss,
    prevent_sql_injection
)

from .headers import (
    SecurityHeadersMiddleware,
    add_security_headers
)

from .encryption import (
    DataEncryption,
    encrypt_sensitive_data,
    decrypt_sensitive_data
)

__all__ = [
    "APIKeyManager",
    "get_api_key_manager", 
    "verify_api_key",
    "require_api_key",
    "require_admin_key",
    "APIKeyPermission",
    "SecurityValidator",
    "sanitize_input",
    "validate_url",
    "validate_headers",
    "prevent_xss",
    "prevent_sql_injection",
    "SecurityHeadersMiddleware",
    "add_security_headers",
    "DataEncryption",
    "encrypt_sensitive_data",
    "decrypt_sensitive_data"
]
