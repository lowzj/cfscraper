import os
from typing import Optional
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


# Global settings instance
settings = Settings()