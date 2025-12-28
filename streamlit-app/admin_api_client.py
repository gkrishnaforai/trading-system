"""
Admin API Client for Trading System
Handles all backend API communication for the admin dashboard.
"""
import requests
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date
import pandas as pd

logger = logging.getLogger(__name__)

class AdminAPIError(Exception):
    """Admin API specific errors"""
    pass

class AdminAPIClient:
    """Enhanced API client for admin operations"""
    
    def __init__(self, python_api_url: str = "http://localhost:8002", 
                 go_api_url: str = "http://localhost:8000"):
        self.python_api_url = python_api_url
        self.go_api_url = go_api_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def _make_request(self, url: str, method: str = "GET", data: Dict = None, 
                     params: Dict = None) -> Dict[str, Any]:
        """Make HTTP request with comprehensive error handling"""
        try:
            if method == "GET":
                response = self.session.get(url, params=params)
            elif method == "POST":
                response = self.session.post(url, json=data, params=params)
            elif method == "PUT":
                response = self.session.put(url, json=data, params=params)
            elif method == "DELETE":
                response = self.session.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            
            # Handle empty responses
            if response.status_code == 204:
                return {"success": True}
            
            return response.json()
            
        except requests.exceptions.Timeout:
            raise AdminAPIError(f"Request timeout: {url}")
        except requests.exceptions.ConnectionError:
            raise AdminAPIError(f"Connection failed: {url}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise AdminAPIError(f"Endpoint not found: {url}")
            elif e.response.status_code == 500:
                raise AdminAPIError(f"Server error: {e.response.text}")
            else:
                raise AdminAPIError(f"HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            raise AdminAPIError(f"Request failed: {str(e)}")
    
    # Data Sources Management
    def get_data_sources(self) -> List[Dict[str, Any]]:
        """Get all configured data sources"""
        result = self._make_request(f"{self.python_api_url}/admin/data-sources")
        return result.get("data_sources", [])
    
    def add_data_source(self, source_config: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new data source"""
        return self._make_request(f"{self.python_api_url}/admin/data-sources", "POST", source_config)
    
    def update_data_source(self, source_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update data source configuration"""
        return self._make_request(f"{self.python_api_url}/admin/data-sources/{source_name}", "PUT", config)
    
    def test_data_source(self, source_name: str) -> Dict[str, Any]:
        """Test data source connection"""
        return self._make_request(f"{self.python_api_url}/admin/data-sources/{source_name}/test")
    
    # Data Management
    def refresh_data(self, symbols: List[str], data_types: List[str], force: bool = False) -> Dict[str, Any]:
        """Trigger data refresh for specific symbols and data types"""
        data = {
            "symbols": symbols,
            "data_types": data_types,
            "force": force
        }
        return self._make_request(f"{self.python_api_url}/refresh", "POST", data)
    
    def get_refresh_status(self) -> Dict[str, Any]:
        """Get current refresh status and queue"""
        return self._make_request(f"{self.python_api_url}/admin/refresh/status")
    
    def get_data_summary(self, table: str, date_filter: Optional[str] = None) -> Dict[str, Any]:
        """Get data summary for a specific table"""
        params = {}
        if date_filter:
            params["date_filter"] = date_filter
        
        return self._make_request(f"{self.python_api_url}/admin/data-summary/{table}", params=params)
    
    # Signals and Screeners
    def generate_signals(self, symbols: List[str], strategy: str = "technical") -> Dict[str, Any]:
        """Generate trading signals for symbols"""
        data = {
            "symbols": symbols,
            "strategy": strategy
        }
        return self._make_request(f"{self.python_api_url}/signals/generate", "POST", data)
    
    def get_recent_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent trading signals"""
        result = self._make_request(f"{self.python_api_url}/signals/recent", params={"limit": limit})
        return result.get("signals", [])
    
    def run_screener(self, criteria: Dict[str, Any]) -> Dict[str, Any]:
        """Run stock screener with criteria"""
        return self._make_request(f"{self.python_api_url}/screener/run", "POST", criteria)
    
    def get_screener_results(self, screener_id: str) -> Dict[str, Any]:
        """Get screener results by ID"""
        return self._make_request(f"{self.python_api_url}/screener/results/{screener_id}")
    
    # Audit and Logs
    def get_audit_logs(self, start_date: str, end_date: str, level: str = "ALL", 
                      limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit logs with filters"""
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "level": level,
            "limit": limit
        }
        result = self._make_request(f"{self.python_api_url}/admin/audit-logs", params=params)
        return result.get("logs", [])
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health status"""
        return self._make_request(f"{self.python_api_url}/admin/health")
    
    # System Configuration
    def get_settings(self) -> Dict[str, Any]:
        """Get system configuration settings"""
        try:
            return self._make_request(f"{self.python_api_url}/admin/settings")
        except AdminAPIError:
            # Mock data for development
            return {
                "general": {
                    "auto_refresh": True,
                    "refresh_interval": 15,
                    "max_concurrent_jobs": 5,
                    "raw_data_retention": 90,
                    "log_retention": 30
                },
                "security": {
                    "enable_auth": True,
                    "session_timeout": 60,
                    "max_login_attempts": 5,
                    "api_key_required": True
                },
                "monitoring": {
                    "enable_health_checks": True,
                    "health_check_interval": 5,
                    "enable_alerts": True,
                    "cpu_threshold": 80,
                    "memory_threshold": 85
                }
            }
    
    def update_settings(self, category: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Update system configuration settings"""
        return self._make_request(f"{self.python_api_url}/admin/settings/{category}", "PUT", settings)
    
    # Data Export
    def export_data(self, table: str, format: str = "csv", filters: Dict = None) -> str:
        """Export data from table"""
        params = {"format": format}
        if filters:
            params.update(filters)
        
        response = self._make_request(f"{self.python_api_url}/admin/export/{table}", params=params)
        return response.get("download_url", "")
    
    # Performance Metrics
    def get_performance_metrics(self, period: str = "24h") -> Dict[str, Any]:
        """Get system performance metrics"""
        try:
            return self._make_request(f"{self.python_api_url}/admin/metrics", params={"period": period})
        except AdminAPIError:
            # Mock data for development
            return {
                "period": period,
                "api_requests": {
                    "total": 15420,
                    "success_rate": 99.2,
                    "avg_response_time": 145
                },
                "data_processing": {
                    "signals_generated": 1247,
                    "screener_runs": 89,
                    "data_refreshes": 47
                },
                "resource_usage": {
                    "cpu_avg": 45.2,
                    "memory_avg": 67.8,
                    "disk_io": 1024
                }
            }

# Singleton instance for easy import
admin_client = AdminAPIClient()
