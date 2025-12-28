"""
Configuration-Driven Alpha Vantage Data Source
Uses endpoint configuration file for flexible API calls
Follows exact Alpha Vantage URL patterns
"""
import requests
import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from app.observability.logging import get_logger
from app.config import settings

logger = get_logger("alphavantage_configured")

class ConfiguredAlphaVantageSource:
    """Configuration-driven Alpha Vantage API source"""
    
    def __init__(self, api_key: str, config_file: str = None):
        self.api_key = api_key
        self.config_file = config_file or "config/alphavantage_endpoints.json"
        self.endpoints = self._load_config()
        self.base_url = self.endpoints.get("base_url", "https://www.alphavantage.co/query")
        self.last_call_time = 0
        self.min_call_interval = 60 / self.endpoints.get("rate_limit", {}).get("calls_per_minute", 5)
        
        logger.info(f"✅ Configured Alpha Vantage initialized")
        logger.info(f"   API Key: ***{api_key[-4:]}")
        logger.info(f"   Endpoints loaded: {len(self.endpoints.get('endpoints', {}))}")
        logger.info(f"   Rate limit: {self.min_call_interval:.1f}s between calls")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load endpoint configuration from JSON file"""
        try:
            config_path = Path(self.config_file)
            if not config_path.exists():
                # Try relative to project root
                config_path = Path(__file__).parent.parent.parent / self.config_file
            
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                logger.info(f"✅ Loaded Alpha Vantage config from {config_path}")
                return config
            else:
                logger.error(f"❌ Config file not found: {config_path}")
                return {}
                
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
            return {}
    
    def _respect_rate_limit(self):
        """Ensure we respect Alpha Vantage rate limits"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_call_time
        
        if time_since_last_call < self.min_call_interval:
            sleep_time = self.min_call_interval - time_since_last_call
            logger.info(f"⏳ Rate limiting: waiting {sleep_time:.1f}s...")
            time.sleep(sleep_time)
        
        self.last_call_time = time.time()
    
    def _validate_response(self, endpoint_config: Dict[str, Any], response_data: Dict[str, Any]) -> bool:
        """Validate response based on endpoint configuration"""
        try:
            validator = endpoint_config.get("response_validator", {})
            validator_type = validator.get("type", "key_exists")
            
            if validator_type == "key_exists":
                key = validator.get("key")
                return key in response_data and response_data[key] is not None
            
            elif validator_type == "array_exists":
                key = validator.get("key")
                min_length = validator.get("min_length", 1)
                return (key in response_data and 
                       isinstance(response_data[key], list) and 
                       len(response_data[key]) >= min_length)
            
            elif validator_type == "not_error_response":
                # Check if response doesn't contain error messages
                error_keys = ["Error Message", "Note", "Information"]
                return not any(key in response_data for key in error_keys)
            
            return True  # Default to valid if no validator
            
        except Exception as e:
            logger.error(f"Error validating response: {e}")
            return False
    
    def _build_url(self, endpoint_id: str, **params) -> str:
        """Build API URL based on endpoint configuration"""
        try:
            endpoint_config = self.endpoints.get("endpoints", {}).get(endpoint_id)
            if not endpoint_config:
                raise ValueError(f"Unknown endpoint: {endpoint_id}")
            
            # Start with base URL and function
            url_params = {
                "function": endpoint_config["function"],
                "apikey": self.api_key
            }
            
            # Add default parameters
            default_params = self.endpoints.get("default_params", {})
            for key, value in default_params.items():
                if value == "${ALPHAVANTAGE_API_KEY}":
                    url_params[key] = self.api_key
                else:
                    url_params[key] = value
            
            # Add required parameters
            for param in endpoint_config.get("required_params", []):
                if param not in params:
                    raise ValueError(f"Required parameter missing: {param}")
                url_params[param] = params[param]
            
            # Add optional parameters
            for param in endpoint_config.get("optional_params", []):
                if param in params:
                    url_params[param] = params[param]
            
            # Build query string
            query_string = "&".join([f"{k}={v}" for k, v in url_params.items()])
            return f"{self.base_url}?{query_string}"
            
        except Exception as e:
            logger.error(f"Error building URL for {endpoint_id}: {e}")
            raise
    
    def fetch_data(self, endpoint_id: str, **params) -> Optional[Dict[str, Any]]:
        """
        Generic fetch method using endpoint configuration
        
        Args:
            endpoint_id: Configuration key (e.g., "company_overview", "income_statement")
            **params: Parameters for the specific endpoint
        
        Returns:
            Response data or None if failed
        """
        try:
            # Respect rate limits
            self._respect_rate_limit()
            
            # Build URL
            url = self._build_url(endpoint_id, **params)
            endpoint_config = self.endpoints.get("endpoints", {}).get(endpoint_id)
            
            logger.info(f"📡 Fetching {endpoint_id} from Alpha Vantage")
            logger.debug(f"URL: {url.replace(self.api_key, '***')}")
            
            # Make request
            response = requests.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            # Validate response
            if self._validate_response(endpoint_config, data):
                logger.info(f"✅ Successfully fetched {endpoint_id}")
                return data
            else:
                logger.warning(f"❌ Invalid response for {endpoint_id}")
                logger.debug(f"Response keys: {list(data.keys())}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching {endpoint_id}: {e}")
            return None
    
    # Convenience methods that use the generic fetch_data
    def fetch_company_overview(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch company overview"""
        return self.fetch_data("company_overview", symbol=symbol.upper())
    
    def fetch_income_statement(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch income statement"""
        return self.fetch_data("income_statement", symbol=symbol.upper())
    
    def fetch_balance_sheet(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch balance sheet"""
        return self.fetch_data("balance_sheet", symbol=symbol.upper())
    
    def fetch_cash_flow(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch cash flow statement"""
        return self.fetch_data("cash_flow", symbol=symbol.upper())
    
    def fetch_earnings(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch earnings data"""
        return self.fetch_data("earnings", symbol=symbol.upper())
    
    def fetch_time_series_daily(self, symbol: str, outputsize: str = "compact") -> Optional[Dict[str, Any]]:
        """Fetch daily time series"""
        return self.fetch_data("time_series_daily", symbol=symbol.upper(), outputsize=outputsize)
    
    def fetch_technical_indicator(self, symbol: str, indicator: str, **params) -> Optional[Dict[str, Any]]:
        """Fetch technical indicators"""
        endpoint_id = f"technical_{indicator.lower()}"
        return self.fetch_data(endpoint_id, symbol=symbol.upper(), **params)
    
    def fetch_news_sentiment(self, tickers: str = None, limit: int = 10) -> Optional[Dict[str, Any]]:
        """Fetch news and sentiment"""
        params = {}
        if tickers:
            params["tickers"] = tickers
        if limit:
            params["limit"] = limit
        return self.fetch_data("news_sentiment", **params)
    
    def list_available_endpoints(self) -> List[str]:
        """List all available endpoint IDs"""
        return list(self.endpoints.get("endpoints", {}).keys())
    
    def get_endpoint_info(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific endpoint"""
        return self.endpoints.get("endpoints", {}).get(endpoint_id)
