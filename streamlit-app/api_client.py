"""
Centralized API client with robust error handling and logging
No fallbacks, no workarounds - fail fast with clear errors
"""
import logging
import streamlit as st
import requests
from typing import Optional, Dict, Any, List
from requests.exceptions import RequestException, Timeout, ConnectionError

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base exception for API errors"""
    pass


class APIConnectionError(APIError):
    """Raised when API connection fails"""
    pass


class APIResponseError(APIError):
    """Raised when API returns error response"""
    def __init__(self, status_code: int, message: str, response_text: str = ""):
        self.status_code = status_code
        self.message = message
        self.response_text = response_text
        super().__init__(f"API Error {status_code}: {message}")


class APIClient:
    """
    Centralized API client with fail-fast error handling
    No fallbacks, no silent failures - all errors are logged and raised
    """
    
    def __init__(self, base_url: str, timeout: int = 30, default_headers: Optional[Dict[str, str]] = None):
        """
        Initialize API client
        
        Args:
            base_url: Base URL for API (must be valid, no fallback)
            timeout: Request timeout in seconds
        
        Raises:
            ValueError: If base_url is empty or invalid
        """
        if not base_url or not isinstance(base_url, str):
            raise ValueError(f"Invalid base_url: {base_url}")
        
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.default_headers = default_headers or {}
        logger.info(f"Initialized API client for {self.base_url}")
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request with robust error handling
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON body for POST requests
            timeout: Request timeout (uses default if None)
        
        Returns:
            Response JSON as dictionary
        
        Raises:
            APIConnectionError: If connection fails
            APIResponseError: If API returns error status
            ValueError: If endpoint is invalid
        """
        if not endpoint:
            raise ValueError("Endpoint cannot be empty")
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        timeout = timeout or self.timeout
        
        merged_headers: Dict[str, str] = {**self.default_headers, **(headers or {})}

        logger.debug(f"{method} {url} - params={params}, json={json_data is not None}")
        
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=merged_headers if merged_headers else None,
                timeout=timeout
            )
            
            # Log response
            logger.debug(f"Response {response.status_code} from {url}")
            
            # Fail fast on non-2xx status codes
            if not response.ok:
                error_msg = f"{method} {url} returned {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_data.get('message', error_data.get('detail', error_msg)))
                except:
                    error_msg = response.text[:200] if response.text else error_msg
                
                logger.error(f"{error_msg} - Status: {response.status_code}")
                raise APIResponseError(
                    status_code=response.status_code,
                    message=error_msg,
                    response_text=response.text
                )
            
            # Parse JSON response
            try:
                return response.json()
            except ValueError as e:
                logger.error(f"Invalid JSON response from {url}: {e}")
                raise APIResponseError(
                    status_code=response.status_code,
                    message=f"Invalid JSON response: {str(e)}",
                    response_text=response.text[:200]
                )
        
        except Timeout as e:
            error_msg = f"Request timeout for {url} after {timeout}s"
            logger.error(error_msg)
            raise APIConnectionError(error_msg) from e
        
        except ConnectionError as e:
            error_msg = f"Connection failed to {url}: {str(e)}"
            logger.error(error_msg)
            raise APIConnectionError(error_msg) from e
        
        except RequestException as e:
            error_msg = f"Request failed for {url}: {str(e)}"
            logger.error(error_msg)
            raise APIConnectionError(error_msg) from e
    
    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """GET request"""
        return self._make_request("GET", endpoint, params=params, timeout=timeout, headers=headers)
    
    def list_agents(self) -> Dict[str, Any]:
        """List Go-owned canonical agent workflows."""
        return self.get("api/v1/agents")

    def list_portfolio_agent_snapshots(self, portfolio_id: str, limit: int = 30) -> Dict[str, Any]:
        """Load persisted portfolio review snapshots through Go API."""
        return self.get(
            f"api/v1/portfolios/{portfolio_id}/agent-snapshots",
            params={"limit": limit},
        )

    def get_portfolio_agent_snapshot(self, portfolio_id: str, snapshot_id: str) -> Dict[str, Any]:
        """Load one persisted portfolio review snapshot with positions/decisions."""
        return self.get(f"api/v1/portfolios/{portfolio_id}/agent-snapshots/{snapshot_id}")

    def get_agent_run(self, run_id: str) -> Dict[str, Any]:
        """Load a durable run record and persisted agent result."""
        return self.get(f"api/v1/runs/{run_id}")

    def list_agent_runs(self, limit: int = 25) -> Dict[str, Any]:
        """List recent durable agent/data runs."""
        return self.get("api/v1/runs", params={"limit": limit})

    def run_agent(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Dict[str, Any]:
        """Run a canonical analysis workflow through the Go API BFF."""
        return self.post("api/v1/agent-runs", json_data=payload, timeout=timeout or 900)

    def get_live_quote(self, symbol: str) -> Dict[str, Any]:
        """Get canonical freshness-aware live quote through Go API."""
        return self.get(f"api/v1/market-data/quote/{symbol.upper()}")

    def get_stock(self, symbol: str) -> Dict[str, Any]:
        """Get legacy stock data; price fields are historical/cached unless separately refreshed."""
        return self.get(f"stock/{symbol}")
    
    def get_news(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """Get recent news for a symbol"""
        return self.get(f"stock/{symbol}/news", params={"limit": limit})
    
    @staticmethod
    def link_button(label: str, url: str):
        """Render a clickable link button using markdown."""
        st.markdown(
            f'<a href="{url}" target="_blank"><button style="background-color:#0f7938;color:white;border:none;padding:0.5rem 1rem;border-radius:0.25rem;cursor:pointer;">{label}</button></a>',
            unsafe_allow_html=True,
        )
    
    def post(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """POST request"""
        return self._make_request("POST", endpoint, params=params, json_data=json_data, timeout=timeout, headers=headers)
    
    def put(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """PUT request"""
        return self._make_request("PUT", endpoint, params=params, json_data=json_data, timeout=timeout, headers=headers)

    def patch(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """PATCH request"""
        return self._make_request("PATCH", endpoint, params=params, json_data=json_data, timeout=timeout, headers=headers)
    
    def delete(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """DELETE request"""
        return self._make_request("DELETE", endpoint, params=params, timeout=timeout, headers=headers)


# Global API clients - initialized once, fail fast if invalid
_go_api_client: Optional[APIClient] = None
_python_api_client: Optional[APIClient] = None


def get_go_api_client() -> APIClient:
    """
    Get Go API client instance
    
    Returns:
        APIClient instance
    
    Raises:
        ValueError: If API_BASE_URL is not configured
    """
    global _go_api_client
    
    if _go_api_client is None:
        import os
        go_api_url = (
            os.getenv("GO_API_URL")
            or os.getenv("API_BASE_URL")
            or "http://localhost:8000"
        )
        if not go_api_url:
            raise ValueError("GO_API_URL/API_BASE_URL not configured")
        _go_api_client = APIClient(go_api_url, timeout=120)
        # Override for local development only (not when running in Docker)
        if _go_api_client.base_url.startswith("http://go-api:") and not os.path.exists('/.dockerenv'):
            _go_api_client.base_url = "http://localhost:8000"
    
    return _go_api_client


def get_python_api_client() -> APIClient:
    raise ValueError("Python API client disabled: Streamlit must call only Go API")

