import os
import logging
from typing import Optional, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings"""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    # App settings
    app_name: str = Field(default="CFScraper API")
    debug: bool = Field(default=False)
    
    # Database settings
    database_url: str = Field(
        default="sqlite:///./cfscraper.db",
        description="Database URL"
    )
    
    # Redis settings
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis URL"
    )
    
    # Job queue settings
    max_concurrent_jobs: int = Field(default=10, description="Max concurrent jobs")
    job_timeout: int = Field(default=300, description="Job timeout in seconds")
    
    # Scraper settings
    selenium_timeout: int = Field(default=30, description="Selenium timeout")
    cloudscraper_timeout: int = Field(default=30, description="CloudScraper timeout")
    
    # Development settings
    use_in_memory_queue: bool = Field(default=True, description="Use in-memory queue")

    # Proxy settings
    proxy_list: List[str] = Field(
        default_factory=list,
        description="List of proxy URLs (http://user:pass@host:port)"
    )
    proxy_rotation_strategy: str = Field(
        default="round_robin",
        description="Proxy rotation strategy: round_robin, random, weighted"
    )
    proxy_health_check_enabled: bool = Field(
        default=True,
        description="Enable proxy health checking"
    )
    proxy_health_check_interval: int = Field(
        default=300,
        description="Proxy health check interval in seconds"
    )
    proxy_health_check_timeout: int = Field(
        default=10,
        description="Proxy health check timeout in seconds"
    )
    proxy_health_check_url: str = Field(
        default="http://httpbin.org/ip",
        description="URL for proxy health checks"
    )
    proxy_max_failures: int = Field(
        default=10,
        description="Max failures before removing proxy"
    )

    # User-Agent rotation settings
    user_agent_rotation_enabled: bool = Field(
        default=True,
        description="Enable user-agent rotation"
    )
    user_agent_rotation_strategy: str = Field(
        default="random",
        description="User-agent rotation strategy: random, round_robin"
    )
    custom_user_agents: List[str] = Field(
        default_factory=list,
        description="Custom user agents to add to rotation"
    )

    # Stealth mode settings
    stealth_mode_enabled: bool = Field(
        default=True,
        description="Enable stealth mode for anti-detection"
    )
    stealth_header_randomization: bool = Field(
        default=True,
        description="Enable header randomization in stealth mode"
    )
    stealth_viewport_randomization: bool = Field(
        default=True,
        description="Enable viewport randomization in stealth mode"
    )
    stealth_intelligent_delays: bool = Field(
        default=True,
        description="Enable intelligent delays in stealth mode"
    )
    stealth_delay_min: float = Field(
        default=1.0,
        description="Minimum delay between requests in seconds"
    )
    stealth_delay_max: float = Field(
        default=5.0,
        description="Maximum delay between requests in seconds"
    )
    stealth_cookie_management: bool = Field(
        default=True,
        description="Enable cookie management in stealth mode"
    )
    stealth_js_detection_bypass: bool = Field(
        default=True,
        description="Enable JavaScript detection bypass"
    )

    # Rate limiting settings
    rate_limiting_enabled: bool = Field(
        default=True,
        description="Enable rate limiting"
    )
    rate_limit_requests_per_minute: int = Field(
        default=60,
        description="Default requests per minute limit"
    )
    rate_limit_requests_per_hour: int = Field(
        default=1000,
        description="Default requests per hour limit"
    )
    rate_limit_burst_limit: int = Field(
        default=10,
        description="Burst limit for sudden traffic spikes"
    )
    rate_limit_include_headers: bool = Field(
        default=True,
        description="Include rate limit headers in responses"
    )
    admin_ips: List[str] = Field(
        default_factory=list,
        description="IP addresses that bypass rate limiting"
    )
    rate_limit_bypass_tokens: List[str] = Field(
        default_factory=list,
        description="Tokens that bypass rate limiting"
    )

    # Security settings
    api_key_secret: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for API key generation and validation"
    )
    api_key_expiry_days: int = Field(
        default=30,
        description="Default API key expiry in days"
    )
    admin_api_keys: List[str] = Field(
        default_factory=list,
        description="List of admin API keys"
    )
    allowed_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins"
    )
    security_headers_enabled: bool = Field(
        default=True,
        description="Enable security headers middleware"
    )
    audit_logging_enabled: bool = Field(
        default=True,
        description="Enable audit logging"
    )
    encryption_key: str = Field(
        default="your-encryption-key-change-in-production",
        description="Key for data encryption"
    )

    # Encryption salt (should be unique per installation)
    encryption_salt: str = Field(
        default="",
        description="Salt for encryption key derivation (auto-generated if empty)"
    )

    @field_validator('api_key_secret')
    @classmethod
    def validate_api_key_secret(cls, v):
        """Validate API key secret strength"""
        if v == "your-secret-key-change-in-production":
            logger.warning("Using default API key secret - change in production!")
        if len(v) < 32:
            logger.warning("API key secret should be at least 32 characters long")
        return v

    @field_validator('encryption_key')
    @classmethod
    def validate_encryption_key(cls, v):
        """Validate encryption key strength"""
        if v == "your-encryption-key-change-in-production":
            logger.warning("Using default encryption key - change in production!")
        if len(v) < 32:
            logger.warning("Encryption key should be at least 32 characters long")
        return v

    @field_validator('encryption_salt')
    @classmethod
    def validate_encryption_salt(cls, v):
        """Validate and generate encryption salt if needed"""
        if not v:
            # Generate a random salt if not provided
            import secrets
            v = secrets.token_hex(32)
            logger.info("Generated new encryption salt - save this value to maintain data compatibility")
        elif len(v) < 32:
            logger.warning("Encryption salt should be at least 32 characters long")
        return v

    @field_validator('allowed_origins')
    @classmethod
    def validate_cors_origins(cls, v):
        """Validate CORS origins"""
        if "*" in v:
            logger.warning("Wildcard CORS origin detected - not recommended for production")
        return v

    @field_validator('admin_api_keys')
    @classmethod
    def validate_admin_keys(cls, v):
        """Validate admin API keys"""
        if not v:
            logger.warning("No admin API keys configured")
        for key in v:
            if len(key) < 32:
                logger.warning("Admin API key should be at least 32 characters long")
        return v


def validate_security_configuration():
    """Validate security configuration on startup"""
    issues = []

    # Check for default secrets
    if settings.api_key_secret == "your-secret-key-change-in-production":
        issues.append("Default API key secret is being used")

    if settings.encryption_key == "your-encryption-key-change-in-production":
        issues.append("Default encryption key is being used")

    # Check CORS configuration
    if "*" in settings.allowed_origins:
        issues.append("Wildcard CORS origin is configured")

    # Check admin configuration
    if not settings.admin_api_keys:
        issues.append("No admin API keys are configured")

    # Check rate limiting
    if not settings.rate_limiting_enabled:
        issues.append("Rate limiting is disabled")

    # Check security headers
    if not settings.security_headers_enabled:
        issues.append("Security headers are disabled")

    # Check audit logging
    if not settings.audit_logging_enabled:
        issues.append("Audit logging is disabled")

    if issues:
        logger.warning(f"Security configuration issues detected: {', '.join(issues)}")
        if not settings.debug:
            logger.error("Security issues detected in production mode!")

    return issues


# Global settings instance
settings = Settings()

# Validate configuration on import
validate_security_configuration()