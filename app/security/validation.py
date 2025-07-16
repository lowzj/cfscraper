"""
Input Validation and Sanitization

Provides comprehensive input validation, sanitization, and security checks
to prevent common attack vectors like XSS, SQL injection, and path traversal.
"""

import re
import html
import urllib.parse
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse
import logging

from pydantic import BaseModel, validator, Field
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class SecurityValidator:
    """Security validation utilities"""
    
    # Dangerous patterns to detect
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
        r"(--|#|/\*|\*/)",
        r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
        r"(\b(OR|AND)\s+['\"]?\w+['\"]?\s*=\s*['\"]?\w+['\"]?)",
        r"(;|\|\||&&)",
    ]
    
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"vbscript:",
        r"onload\s*=",
        r"onerror\s*=",
        r"onclick\s*=",
        r"onmouseover\s*=",
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
    ]
    
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",
        r"\.\.\\",
        r"/etc/passwd",
        r"/etc/shadow",
        r"C:\\Windows\\System32",
        r"\.\.%2F",
        r"\.\.%5C",
    ]
    
    COMMAND_INJECTION_PATTERNS = [
        r"[;&|`$(){}[\]<>]",
        r"\$\(",
        r"`.*`",
        r"\|\s*\w+",
        r"&&\s*\w+",
        r";\s*\w+",
    ]
    
    @classmethod
    def detect_sql_injection(cls, text: str) -> bool:
        """Detect potential SQL injection attempts"""
        if not text:
            return False
        
        text_lower = text.lower()
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.warning(f"Potential SQL injection detected: {pattern}")
                return True
        return False
    
    @classmethod
    def detect_xss(cls, text: str) -> bool:
        """Detect potential XSS attempts"""
        if not text:
            return False
        
        text_lower = text.lower()
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.warning(f"Potential XSS detected: {pattern}")
                return True
        return False
    
    @classmethod
    def detect_path_traversal(cls, text: str) -> bool:
        """Detect potential path traversal attempts"""
        if not text:
            return False
        
        for pattern in cls.PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Potential path traversal detected: {pattern}")
                return True
        return False
    
    @classmethod
    def detect_command_injection(cls, text: str) -> bool:
        """Detect potential command injection attempts"""
        if not text:
            return False
        
        for pattern in cls.COMMAND_INJECTION_PATTERNS:
            if re.search(pattern, text):
                logger.warning(f"Potential command injection detected: {pattern}")
                return True
        return False
    
    @classmethod
    def is_safe_string(cls, text: str) -> bool:
        """Check if string is safe from common attacks"""
        if not text:
            return True
        
        return not any([
            cls.detect_sql_injection(text),
            cls.detect_xss(text),
            cls.detect_path_traversal(text),
            cls.detect_command_injection(text)
        ])


def sanitize_input(value: Any) -> Any:
    """Sanitize input value to prevent attacks"""
    if isinstance(value, str):
        # HTML escape
        value = html.escape(value)
        
        # Remove null bytes and control characters
        value = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
        
        # Limit length
        if len(value) > 10000:
            value = value[:10000]
        
        return value
    
    elif isinstance(value, dict):
        return {k: sanitize_input(v) for k, v in value.items()}
    
    elif isinstance(value, list):
        return [sanitize_input(item) for item in value]
    
    return value


def validate_url(url: str) -> str:
    """Validate and sanitize URL"""
    if not url:
        raise ValueError("URL cannot be empty")
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL format")
    
    # Check scheme
    if parsed.scheme not in ['http', 'https']:
        raise ValueError("URL must use HTTP or HTTPS protocol")
    
    # Check for dangerous patterns
    if SecurityValidator.detect_xss(url):
        raise ValueError("URL contains potentially dangerous content")
    
    if SecurityValidator.detect_path_traversal(url):
        raise ValueError("URL contains path traversal attempts")
    
    # Check hostname
    if not parsed.netloc:
        raise ValueError("URL must have a valid hostname")
    
    # Prevent localhost/internal network access in production
    if not getattr(validate_url, '_allow_localhost', False):
        hostname = parsed.hostname
        if hostname and (
            hostname in ['localhost', '127.0.0.1', '0.0.0.0'] or
            hostname.startswith('192.168.') or
            hostname.startswith('10.') or
            hostname.startswith('172.')
        ):
            raise ValueError("Access to internal networks is not allowed")
    
    return url


def validate_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Validate and sanitize HTTP headers"""
    if not headers:
        return {}
    
    validated_headers = {}
    
    for key, value in headers.items():
        # Sanitize key and value
        key = sanitize_input(str(key))
        value = sanitize_input(str(value))
        
        # Check for dangerous patterns
        if SecurityValidator.detect_xss(key) or SecurityValidator.detect_xss(value):
            logger.warning(f"Skipping header with XSS content: {key}")
            continue
        
        if SecurityValidator.detect_command_injection(key) or SecurityValidator.detect_command_injection(value):
            logger.warning(f"Skipping header with command injection: {key}")
            continue
        
        # Limit header length
        if len(key) > 100 or len(value) > 1000:
            logger.warning(f"Skipping oversized header: {key}")
            continue
        
        validated_headers[key] = value
    
    return validated_headers


def prevent_xss(text: str) -> str:
    """Prevent XSS by escaping dangerous content"""
    if not text:
        return text
    
    # HTML escape
    text = html.escape(text)
    
    # Remove dangerous JavaScript patterns
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'vbscript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
    
    return text


def prevent_sql_injection(text: str) -> str:
    """Prevent SQL injection by escaping dangerous content"""
    if not text:
        return text
    
    # Escape single quotes
    text = text.replace("'", "''")
    
    # Remove dangerous SQL keywords and patterns
    dangerous_patterns = [
        r'\b(DROP|DELETE|INSERT|UPDATE|CREATE|ALTER|EXEC)\b',
        r'--',
        r'/\*.*?\*/',
        r';\s*$'
    ]
    
    for pattern in dangerous_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return text


class SecureBaseModel(BaseModel):
    """Base model with security validation"""
    
    @validator('*', pre=True)
    def validate_security(cls, v):
        """Apply security validation to all fields"""
        if isinstance(v, str):
            if not SecurityValidator.is_safe_string(v):
                raise ValueError("Input contains potentially dangerous content")
            return sanitize_input(v)
        return v


from typing import Annotated
from pydantic import AfterValidator

def validate_secure_url(v: str) -> str:
    """Validate URL for security"""
    if not isinstance(v, str):
        raise TypeError('string required')
    return validate_url(v)

def validate_secure_headers(v: dict) -> dict:
    """Validate headers for security"""
    if not isinstance(v, dict):
        raise TypeError('dict required')
    return validate_headers(v)

# Use Annotated types for Pydantic v2
SecureURLField = Annotated[str, AfterValidator(validate_secure_url)]
SecureHeadersField = Annotated[dict, AfterValidator(validate_secure_headers)]


# Enhanced request models with security validation
class SecureScrapeRequest(SecureBaseModel):
    """Secure scrape request with enhanced validation"""
    url: SecureURLField
    method: str = Field(default="GET", pattern=r"^(GET|POST|PUT|DELETE|HEAD|OPTIONS)$")
    headers: Optional[SecureHeadersField] = None
    data: Optional[Dict[str, Any]] = None
    scraper_type: str = Field(pattern=r"^(selenium|cloudscraper)$")
    tags: Optional[List[str]] = Field(default=None, max_items=10)
    priority: int = Field(default=0, ge=-10, le=10)
    
    @validator('tags')
    def validate_tags(cls, v):
        if v:
            for tag in v:
                if not SecurityValidator.is_safe_string(tag):
                    raise ValueError(f"Tag contains dangerous content: {tag}")
        return v
    
    @validator('data')
    def validate_data(cls, v):
        if v:
            return sanitize_input(v)
        return v
