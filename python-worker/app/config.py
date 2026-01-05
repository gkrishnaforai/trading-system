"""
Configuration management for Python worker
"""
import os
from pathlib import Path
from typing import Optional, Any
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings
    
    Note: pydantic-settings automatically loads from .env file and environment variables
    Environment variables take precedence over .env file values
    """
    
    model_config = {
        "env_file": [".env", "../.env"], 
        "env_file_encoding": "utf-8", 
        "case_sensitive": False,
        "extra": "ignore"
    }
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Override DATABASE_URL for local testing if we detect local environment
        import os
        if os.path.exists(".env") and not os.path.exists("/.dockerenv") and "postgres:" in self.database_url:
            # Force localhost for local testing when local .env exists
            self.database_url = self.database_url.replace("postgres:", "localhost:")
    
    # Environment
    environment: str = "development"
    log_level: str = "INFO"
    
    # Database
    database_url: str = "sqlite:///./db/trading.db"  # Fallback if not in .env
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_db_url: Optional[str] = None
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # gRPC
    python_grpc_url: str = "localhost:50051"
    
    # LLM
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    litellm_proxy_url: Optional[str] = None
    litellm_master_key: Optional[str] = None
    
    # Data fetching
    yahoo_finance_enabled: bool = False
    data_fetch_retry_attempts: int = 3
    data_fetch_retry_delay: int = 5
    
    # Data provider selection (Industry Standard: Primary + Fallback pattern)
    # Set PRIMARY_DATA_PROVIDER, FALLBACK_DATA_PROVIDER, DEFAULT_DATA_PROVIDER in .env
    primary_data_provider: Optional[str] = None
    fallback_data_provider: Optional[str] = None
    default_data_provider: str = "fmp"
    
    # Alpha Vantage API
    alphavantage_api_key: str = Field(default="", description="Alpha Vantage API key")
    alphavantage_rate_limit_calls: int = Field(default=1, description="Alpha Vantage rate limit calls per window")
    alphavantage_rate_limit_window: float = Field(default=1.0, description="Alpha Vantage rate limit window in seconds")
    
    # Massive.com (Polygon.io) API
    # Set MASSIVE_API_KEY and MASSIVE_ENABLED=true in .env file
    massive_api_key: Optional[str] = None
    massive_enabled: bool = False
    massive_rate_limit_calls: int = 2  # Conservative: 2 calls per minute for daily operations
    massive_rate_limit_window: float = 60.0  # Seconds
    
    # Batch scheduler
    batch_schedule_hour: int = 1  # 1 AM
    batch_schedule_minute: int = 0
    
    # Periodic/Live updates
    enable_live_updates: bool = False
    periodic_update_interval_minutes: int = 15  # How often to check for periodic updates

    # Financial Modeling Prep (FMP) API
    fmp_api_key: str = Field(default="", description="Financial Modeling Prep API key")
    fmp_enabled: bool = Field(default=False, description="Enable FMP data provider")
    fmp_base_url: str = Field(default="https://financialmodelingprep.com/stable", description="FMP base URL")
    fmp_timeout: int = Field(default=30, description="FMP request timeout in seconds")
    fmp_max_retries: int = Field(default=3, description="FMP max retries on failure")
    fmp_retry_delay: float = Field(default=1.0, description="FMP retry delay in seconds")
    fmp_rate_limit_calls: int = Field(default=60, description="FMP rate limit calls per window")
    fmp_rate_limit_window: float = Field(default=60.0, description="FMP rate limit window in seconds")


settings = Settings()

