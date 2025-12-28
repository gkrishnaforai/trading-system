"""
Centralized API client with robust error handling and logging
No fallbacks, no workarounds - fail fast with clear errors
"""
import logging
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
    
    def __init__(self, base_url: str, timeout: int = 30):
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
        logger.info(f"Initialized API client for {self.base_url}")
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
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
        
        logger.debug(f"{method} {url} - params={params}, json={json_data is not None}")
        
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=timeout
            )
            
            # Log response
            logger.debug(f"Response {response.status_code} from {url}")
            
            # Fail fast on non-2xx status codes
            if not response.ok:
                error_msg = f"{method} {url} returned {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_data.get('message', error_msg))
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
    
    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
        """GET request"""
        return self._make_request("GET", endpoint, params=params, timeout=timeout)
    
    def post(self, endpoint: str, json_data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
        """POST request"""
        return self._make_request("POST", endpoint, params=params, json_data=json_data, timeout=timeout)
    
    def put(self, endpoint: str, json_data: Optional[Dict[str, Any]] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
        """PUT request"""
        return self._make_request("PUT", endpoint, json_data=json_data, timeout=timeout)
    
    def delete(self, endpoint: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """DELETE request"""
        return self._make_request("DELETE", endpoint, timeout=timeout)


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
        API_BASE_URL = os.getenv("API_BASE_URL", "http://go-api:8000")
        if not API_BASE_URL:
            raise ValueError("API_BASE_URL not configured")
        _go_api_client = APIClient(API_BASE_URL, timeout=30)
    
    return _go_api_client


def get_python_api_client() -> APIClient:
    """
    Get Python API client instance
    
    Returns:
        APIClient instance
    
    Raises:
        ValueError: If PYTHON_API_URL is not configured
    """
    global _python_api_client
    
    if _python_api_client is None:
        import os
        PYTHON_API_URL = os.getenv("PYTHON_API_URL", "http://python-worker:8001")
        if not PYTHON_API_URL:
            raise ValueError("PYTHON_API_URL not configured")
        _python_api_client = APIClient(PYTHON_API_URL, timeout=120)
    
    return _python_api_client

