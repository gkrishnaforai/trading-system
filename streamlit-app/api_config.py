"""
Centralized API Configuration
Provides consistent API URLs across all Streamlit apps
"""

import os
from typing import Optional

class APIConfig:
    """Centralized API configuration for all Streamlit apps"""
    
    def __init__(self):
        # Get Python Worker URL from environment with fallbacks
        self.python_worker_url = os.getenv(
            'PYTHON_WORKER_URL', 
            os.getenv('PYTHON_API_URL', 
            'http://python-worker:8001')  # Docker default
        )
        
        # Get Go API URL from environment with fallbacks
        self.go_api_url = os.getenv(
            'GO_API_URL',
            os.getenv('NEXT_PUBLIC_API_URL',
            'http://go-api:8000')  # Docker default
        )
    
    @property
    def universal_api_base(self) -> str:
        """Base URL for Universal API endpoints"""
        return f"{self.python_worker_url}/api/v1/universal"
    
    @property
    def admin_api_base(self) -> str:
        """Base URL for Admin API endpoints"""
        return f"{self.python_worker_url}/admin"
    
    @property
    def data_api_base(self) -> str:
        """Base URL for Data API endpoints"""
        return f"{self.python_worker_url}/api/v1/data"
    
    @property
    def refresh_api_base(self) -> str:
        """Base URL for Refresh API endpoints"""
        return f"{self.python_worker_url}/api/v1/refresh"
    
    def get_universal_signal_url(self) -> str:
        """Get Universal Signal endpoint URL"""
        return f"{self.universal_api_base}/signal/universal"
    
    def get_historical_data_url(self, symbol: str) -> str:
        """Get Historical Data endpoint URL"""
        return f"{self.universal_api_base}/historical-data/{symbol}"
    
    def get_data_summary_url(self, symbol: str) -> str:
        """Get Data Summary endpoint URL (same as TQQQ backtest)"""
        return f"{self.admin_api_base}/data-summary/{symbol.lower()}"
    
    def get_data_url(self, symbol: str) -> str:
        """Get Data endpoint URL (same as TQQQ backtest)"""
        return f"{self.data_api_base}/{symbol}"
    
    def get_refresh_url(self) -> str:
        """Get Refresh endpoint URL"""
        return self.refresh_api_base
    
    def __str__(self) -> str:
        """String representation for debugging"""
        return f"APIConfig(python_worker={self.python_worker_url}, go_api={self.go_api_url})"

# Global instance
api_config = APIConfig()

# Convenience functions for backward compatibility
def get_python_worker_url() -> str:
    """Get Python Worker URL"""
    return api_config.python_worker_url

def get_universal_api_base() -> str:
    """Get Universal API base URL"""
    return api_config.universal_api_base

def get_admin_api_base() -> str:
    """Get Admin API base URL"""
    return api_config.admin_api_base
