import os
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


# Global settings instance
settings = Settings()