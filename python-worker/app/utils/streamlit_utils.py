"""
Streamlit Utilities
Common utilities for Streamlit applications
"""
import os
from typing import Optional


def get_go_api_base_url() -> str:
    """
    Get the Go API base URL from environment variables with intelligent fallbacks
    
    Priority order:
    1. GO_API_URL (explicit Go API URL)
    2. GO_API_BASE_URL (alternative Go API URL)
    3. NEXT_PUBLIC_API_URL (frontend API URL)
    4. Docker environment (go-api:8000) if DOCKER_ENV is set
    5. Local development (localhost:8000)
    
    Returns:
        str: The Go API base URL
    """
    go_api_url = (
        os.environ.get("GO_API_URL") or 
        os.environ.get("GO_API_BASE_URL") or
        os.environ.get("NEXT_PUBLIC_API_URL") or
        # Docker environment
        "http://go-api:8000" if os.environ.get("DOCKER_ENV") else 
        # Local development
        "http://localhost:8000"
    )
    return go_api_url


def get_go_api_url(path: str) -> str:
    """
    Get the full Go API URL for a specific path
    
    Args:
        path: The API path (e.g., "/api/v1/watchlists")
        
    Returns:
        str: The full URL
    """
    return get_go_api_base_url().rstrip("/") + path


def is_docker_environment() -> bool:
    """
    Check if running in Docker environment
    
    Returns:
        bool: True if running in Docker
    """
    return os.environ.get("DOCKER_ENV") is not None or os.path.exists("/.dockerenv")


def get_environment_name() -> str:
    """
    Get the current environment name
    
    Returns:
        str: Environment name (development, staging, production)
    """
    return os.environ.get("ENVIRONMENT", "development")


def is_development() -> bool:
    """
    Check if running in development environment
    
    Returns:
        bool: True if development environment
    """
    return get_environment_name() in ["development", "dev", "local"]


def get_log_level() -> str:
    """
    Get the log level from environment
    
    Returns:
        str: Log level (DEBUG, INFO, WARNING, ERROR)
    """
    return os.environ.get("LOG_LEVEL", "INFO").upper()
