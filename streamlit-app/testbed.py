"""
Comprehensive Testbed Dashboard for Trading System
QA Engineer's Testing Interface - Test all features end-to-end
"""
import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import os
import logging
from typing import Dict, Any, Optional, List

from api_client import (
    get_go_api_client,
    get_python_api_client,
    APIError,
    APIConnectionError,
    APIResponseError
)
from shared_functions import display_fetch_results, display_validation_report

logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://go-api:8000")
PYTHON_API_URL = os.getenv("PYTHON_API_URL", "http://python-worker:8001")

# Page configuration
st.set_page_config(
    page_title="Trading System Testbed",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for testbed
st.markdown("""
    <style>
    .testbed-header {
        font-size: 2rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .status-success {
        color: #28a745;
        font-weight: bold;
    }
    .status-error {
        color: #dc3545;
        font-weight: bold;
    }
    .status-warning {
        color: #ffc107;
        font-weight: bold;
    }
    .test-section {
        border: 1px solid #dee2e6;
        border-radius: 0.25rem;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .dependency-tree {
        background-color: #f8f9fa;
        padding: 0.5rem;
        border-radius: 0.25rem;
        font-family: monospace;
        font-size: 0.875rem;
    }
    </style>
""", unsafe_allow_html=True)


def check_api_health() -> Dict[str, Any]:
    """Check health of all APIs"""
    health_status = {
        "GO_API": {"status": "unknown", "message": "", "details": {}},
        "PYTHON_API": {"status": "unknown", "message": "", "details": {}}
    }
    
    # Check Go API
    try:
        client = get_go_api_client()
        response = client.get("health", timeout=5)
        
        if response:
            status = response.get("status", "unknown")
            service = response.get("service", "")
            message = response.get("message", "")
            
            # Determine health status
            if status in ["ok", "healthy"]:
                health_status_val = "healthy"
                default_msg = f"Service: {service}" if service else "API is healthy"
            else:
                health_status_val = "unhealthy"
                default_msg = f"Status: {status}" if status != "unknown" else "Health check returned unexpected status"
            
            health_status["GO_API"] = {
                "status": health_status_val,
                "message": message if message else default_msg,
                "timestamp": datetime.now().isoformat(),
                "details": response
            }
        else:
            health_status["GO_API"] = {
                "status": "unhealthy",
                "message": "No response from health endpoint (empty response)",
                "timestamp": datetime.now().isoformat()
            }
    except APIConnectionError as e:
        health_status["GO_API"] = {
            "status": "error",
            "message": f"Connection failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    except APIResponseError as e:
        health_status["GO_API"] = {
            "status": "error",
            "message": f"HTTP {e.status_code}: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        health_status["GO_API"] = {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    
    # Check Python API
    try:
        client = get_python_api_client()
        response = client.get("health", timeout=5)
        
        if response:
            status = response.get("status", "unknown")
            service = response.get("service", "")
            message = response.get("message", "")
            
            # Determine health status
            if status in ["ok", "healthy"]:
                health_status_val = "healthy"
                default_msg = f"Service: {service}" if service else "API is healthy"
            else:
                health_status_val = "unhealthy"
                default_msg = f"Status: {status}" if status != "unknown" else "Health check returned unexpected status"
            
            health_status["PYTHON_API"] = {
                "status": health_status_val,
                "message": message if message else default_msg,
                "timestamp": datetime.now().isoformat(),
                "details": response
            }
        else:
            health_status["PYTHON_API"] = {
                "status": "unhealthy",
                "message": "No response from health endpoint (empty response)",
                "timestamp": datetime.now().isoformat()
            }
    except APIConnectionError as e:
        health_status["PYTHON_API"] = {
            "status": "error",
            "message": f"Connection failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    except APIResponseError as e:
        health_status["PYTHON_API"] = {
            "status": "error",
            "message": f"HTTP {e.status_code}: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        health_status["PYTHON_API"] = {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    
    return health_status


def check_data_availability(symbol: str) -> Dict[str, Any]:
    """Check what data is available for a symbol"""
    availability = {
        "price_historical": False,
        "price_current": False,
        "fundamentals": False,
        "news": False,
        "earnings": False,
        "industry_peers": False,
        "indicators": False,
        "signals": False,
        "reports": False
    }
    
    try:
        # Check historical price data
        client = get_python_api_client()
        response = client.get(f"api/v1/data/check/{symbol}")
        if response:
            availability.update(response)
    except Exception as e:
        logger.error(f"Error checking data availability: {e}")
    
    return availability


def test_data_source(symbol: str, data_type: str) -> Dict[str, Any]:
    """Test fetching data from a specific source"""
    result = {
        "success": False,
        "data_type": data_type,
        "symbol": symbol,
        "message": "",
        "data_count": 0,
        "error": None
    }
    
    try:
        # Map data types to their respective APIs
        # Most data types use Go API (reads from database)
        # Some use Python API (for live/current data fetching)
        
        if data_type == "price_current":
            # Use Python API for live/current price
            python_client = get_python_api_client()
            response = python_client.get(f"api/v1/live-price/{symbol}")
            if response:
                result["success"] = True
                result["message"] = f"Successfully fetched {data_type} from Python API"
                # Check if price is available
                if response.get("price"):
                    result["data_count"] = 1
                    result["message"] = f"Current price: ${response.get('price'):.2f}"
                else:
                    result["message"] = f"No current price available for {symbol}. Use 'Refresh Live Price' to fetch it."
                    result["success"] = False
        else:
            # Use Go API for reading data (reads from database)
            go_client = get_go_api_client()
            
            # Map data types to Go API endpoints
            endpoint_map = {
                "price_historical": f"api/v1/stock/{symbol}",  # Go API - reads from DB
                "fundamentals": f"api/v1/stock/{symbol}/fundamentals",  # Go API
                "news": f"api/v1/stock/{symbol}/news",  # Go API
                "earnings": f"api/v1/stock/{symbol}/earnings",  # Go API
                "industry_peers": f"api/v1/stock/{symbol}/industry-peers",  # Go API
                "indicators": f"api/v1/stock/{symbol}/advanced-analysis",  # Go API
                "signals": f"api/v1/signal/{symbol}"  # Go API
            }
            
            if data_type in endpoint_map:
                response = go_client.get(endpoint_map[data_type])
                # Debug: Log response structure for troubleshooting
                if response is None:
                    result["message"] = f"API returned None for {data_type}. Check API logs."
                    result["success"] = False
                    return result
                
                if response:
                    result["success"] = True
                    result["message"] = f"Successfully fetched {data_type} from Go API"
                    # Count data items
                    try:
                        if isinstance(response, list):
                            result["data_count"] = len(response) if response is not None else 0
                        elif isinstance(response, dict):
                            # Check for data_available flag
                            if response.get("data_available") == False:
                                result["message"] = f"No {data_type} data available in database. Use 'Fetch Data' to load it."
                                result["success"] = False
                                result["data_count"] = 0
                            else:
                                # Count items in response - handle None values safely
                                data_count = 0
                                
                                # Special handling for fundamentals (single object, not list)
                                if data_type == "fundamentals":
                                    # Fundamentals is returned as a single object with fields like market_cap, pe_ratio, etc.
                                    # Go API returns FundamentalData struct with JSON tags (snake_case)
                                    # Check if it has meaningful data (at least one non-nil field)
                                    has_data = False
                                    fundamental_fields = [
                                        "market_cap", "pe_ratio", "forward_pe", "dividend_yield", "eps",
                                        "revenue", "profit_margin", "debt_to_equity", "current_ratio",
                                        "sector", "industry", "enterprise_value", "book_value",
                                        "price_to_book", "peg_ratio", "revenue_growth", "earnings_growth",
                                        # Also check for camelCase variants (Go JSON might use these)
                                        "marketCap", "peRatio", "forwardPE", "dividendYield", "eps",
                                        "revenue", "profitMargin", "debtToEquity", "currentRatio",
                                        "sector", "industry", "enterpriseValue", "bookValue",
                                        "priceToBook", "pegRatio", "revenueGrowth", "earningsGrowth"
                                    ]
                                    for field in fundamental_fields:
                                        value = response.get(field)
                                        # Check if value is not None and not empty string
                                        if value is not None and value != "":
                                            has_data = True
                                            break
                                    
                                    # Also check if response has symbol (indicates valid response)
                                    if response.get("symbol") == symbol:
                                        has_data = True
                                    
                                    if has_data:
                                        data_count = 1
                                        result["message"] = f"Fundamentals data available for {symbol}"
                                        # Show sample fields in message
                                        sample_fields = []
                                        for field in ["market_cap", "pe_ratio", "sector", "industry"]:
                                            if response.get(field) is not None:
                                                sample_fields.append(f"{field}={response.get(field)}")
                                        if sample_fields:
                                            result["message"] += f" ({', '.join(sample_fields[:2])})"
                                    else:
                                        data_count = 0
                                        result["message"] = f"No {data_type} data available. Use 'Fetch Data' to load it."
                                        result["success"] = False
                                elif "data" in response:
                                    data = response.get("data")
                                    data_count = len(data) if data is not None and isinstance(data, (list, dict)) else 0
                                elif "price_data" in response:
                                    price_data = response.get("price_data")
                                    data_count = len(price_data) if price_data is not None and isinstance(price_data, (list, dict)) else 0
                                elif "news" in response:
                                    news = response.get("news")
                                    data_count = len(news) if news is not None and isinstance(news, list) else 0
                                elif "earnings" in response:
                                    earnings = response.get("earnings")
                                    if earnings is not None and isinstance(earnings, list):
                                        data_count = len(earnings)
                                    else:
                                        data_count = 0
                                        if earnings is None:
                                            result["message"] = f"No {data_type} data available. Use 'Fetch Data' to load it."
                                            result["success"] = False
                                elif data_type == "industry_peers":
                                    # Industry peers response structure: {sector, industry, peers}
                                    # Check if we have meaningful data (sector, industry, or peers list)
                                    peers = response.get("peers")
                                    sector = response.get("sector")
                                    industry = response.get("industry")
                                    
                                    has_data = False
                                    if peers is not None and isinstance(peers, list) and len(peers) > 0:
                                        data_count = len(peers)
                                        has_data = True
                                        result["message"] = f"Industry peers data available for {symbol}: {len(peers)} peers"
                                    elif sector is not None and sector != "":
                                        data_count = 1
                                        has_data = True
                                        result["message"] = f"Industry data available for {symbol}: sector={sector}"
                                        if industry is not None and industry != "":
                                            result["message"] += f", industry={industry}"
                                    elif industry is not None and industry != "":
                                        data_count = 1
                                        has_data = True
                                        result["message"] = f"Industry data available for {symbol}: industry={industry}"
                                    else:
                                        data_count = 0
                                        has_data = False
                                    
                                    if not has_data:
                                        result["message"] = f"No {data_type} data available. Use 'Fetch Data' to load it."
                                        result["success"] = False
                                else:
                                    data_count = 1  # At least got a response
                                
                                result["data_count"] = data_count
                        else:
                            result["data_count"] = 0
                    except (TypeError, AttributeError) as e:
                        # Handle case where len() is called on None
                        result["data_count"] = 0
                        result["message"] = f"Error counting data: {str(e)}. Response structure may be unexpected."
                        result["success"] = False
                        result["error"] = str(e)
                else:
                    result["message"] = f"No response from API for {data_type}"
                    result["success"] = False
            else:
                result["message"] = f"Unknown data type: {data_type}"
            
    except APIError as e:
        result["error"] = str(e)
        result["message"] = f"API Error: {str(e)}"
        result["data_count"] = 0
    except (TypeError, AttributeError) as e:
        # Handle len() on None errors specifically
        result["error"] = str(e)
        result["message"] = f"Data structure error: {str(e)}. The API response may have unexpected structure."
        result["data_count"] = 0
        result["success"] = False
    except Exception as e:
        result["error"] = str(e)
        result["message"] = f"Error: {str(e)}"
        result["data_count"] = 0
    
    return result


def test_calculation(symbol: str, calculation_type: str) -> Dict[str, Any]:
    """Test indicator calculations"""
    result = {
        "success": False,
        "calculation_type": calculation_type,
        "symbol": symbol,
        "message": "",
        "result": None,
        "error": None
    }
    
    try:
        python_client = get_python_api_client()
        
        if calculation_type == "indicators":
            # Trigger indicator calculation via refresh-data endpoint
            response = python_client.post(
                "api/v1/refresh-data",
                json_data={
                    "symbol": symbol.upper(),
                    "data_types": ["indicators"],
                    "force": True
                }
            )
            
            if response:
                summary = response.get("summary", {})
                if summary.get("total_successful", 0) > 0:
                    result["success"] = True
                    result["message"] = f"Successfully calculated {calculation_type}"
                    result["result"] = {"indicators_calculated": True}
                else:
                    result["message"] = "Indicator calculation failed - check logs"
        elif calculation_type == "composite_score":
            # Composite score is returned as momentum_score by Go API (Pro/Elite feature)
            go_client = get_go_api_client()
            response = go_client.get(f"api/v1/stock/{symbol}?subscription_level=pro")
            
            if response:
                indicators = response.get("indicators", {})
                momentum_score = indicators.get("momentum_score")
                
                if momentum_score is not None:
                    result["success"] = True
                    result["message"] = f"Composite score (momentum_score): {momentum_score:.1f}/100"
                    result["result"] = {
                        "momentum_score": momentum_score,
                        "note": "Composite score is returned as momentum_score in Go API"
                    }
                else:
                    # Check if indicators exist but momentum_score is null (filtered for Basic tier)
                    if indicators:
                        result["message"] = "Composite score requires Pro/Elite subscription. Use subscription_level=pro in the request."
                    else:
                        result["message"] = "Indicators not calculated yet. Run 'indicators' calculation first, then use Pro/Elite subscription level."
            else:
                result["message"] = "No stock data available. Fetch data and calculate indicators first."
                
        elif calculation_type == "actionable_levels":
            # Actionable levels are returned as pullback_zone and stop_loss by Go API (Pro/Elite feature)
            go_client = get_go_api_client()
            response = go_client.get(f"api/v1/stock/{symbol}?subscription_level=pro")
            
            if response:
                signal = response.get("signal", {})
                pullback_zone = signal.get("pullback_zone")
                stop_loss = signal.get("stop_loss")
                
                if pullback_zone or stop_loss:
                    result["success"] = True
                    result["message"] = "Actionable levels available"
                    result["result"] = {
                        "pullback_zone": pullback_zone,
                        "stop_loss": stop_loss
                    }
                else:
                    # Check if signal exists but actionable levels are null
                    if signal.get("type"):
                        result["message"] = "Actionable levels require Pro/Elite subscription and calculated indicators. Ensure indicators are calculated and use subscription_level=pro."
                    else:
                        result["message"] = "No signal data available. Calculate indicators first, then signals will include actionable levels for Pro/Elite users."
            else:
                result["message"] = "No stock data available. Fetch data and calculate indicators first."
        else:
            result["message"] = f"Unknown calculation type: {calculation_type}. Available types: indicators, composite_score, actionable_levels"
            
    except APIError as e:
        result["error"] = str(e)
        result["message"] = f"API Error: {str(e)}"
    except Exception as e:
        result["error"] = str(e)
        result["message"] = f"Error: {str(e)}"
    
    return result


def test_strategy(symbol: str, strategy_name: str) -> Dict[str, Any]:
    """Test strategy signal generation"""
    result = {
        "success": False,
        "strategy": strategy_name,
        "symbol": symbol,
        "signal": None,
        "confidence": None,
        "message": "",
        "error": None
    }
    
    try:
        # The Go API signal endpoint returns the signal that was already calculated
        # Strategy selection happens during signal generation (in Python worker)
        # For now, we'll get the signal from Go API and note which strategy was used
        client = get_go_api_client()
        response = client.get(f"api/v1/signal/{symbol}?subscription_level=pro")
        
        if response:
            signal_type = response.get("type")
            signal_reason = response.get("reason", "")
            
            # Check if signal data is available
            if signal_type:
                result["success"] = True
                result["signal"] = signal_type.upper()
                result["confidence"] = response.get("confidence", 0.0)
                result["message"] = f"Signal: {signal_type.upper()} - {signal_reason}"
                
                # Note: Strategy selection happens during data processing
                # The signal endpoint returns the calculated signal, not strategy-specific signals
                if strategy_name in ["technical", "hybrid_llm"]:
                    result["message"] += f" (Note: Strategy '{strategy_name}' is used during signal generation in Python worker)"
            else:
                result["message"] = "No signal available - indicators may not be calculated yet"
        else:
            result["message"] = "No signal data returned from API"
            
    except APIError as e:
        result["error"] = str(e)
        result["message"] = f"API Error: {str(e)}"
    except Exception as e:
        result["error"] = str(e)
        result["message"] = f"Error: {str(e)}"
    
    return result


def main():
    """Main testbed interface"""
    st.title("🧪 Trading System Testbed")
    st.markdown("**QA Engineer's Comprehensive Testing Interface**")
    
    # Display Data Source Configuration in Sidebar
    try:
        python_client = get_python_api_client()
        ds_config = python_client.get("api/v1/data-source/config", timeout=5)
        
        if ds_config:
            with st.sidebar.expander("📊 Data Source Configuration", expanded=False):
                current_source = ds_config.get('current_source', 'unknown')
                primary_source = ds_config.get('primary_source', 'N/A')
                fallback_source = ds_config.get('fallback_source', 'N/A')
                default_provider = ds_config.get('default_provider', 'unknown')
                
                st.markdown(f"**Current Source:** `{current_source}`")
                st.markdown(f"**Default Provider:** `{default_provider}`")
                st.markdown(f"**Primary Source:** `{primary_source}`")
                if fallback_source and fallback_source != 'N/A':
                    st.markdown(f"**Fallback Source:** `{fallback_source}`")
                else:
                    st.markdown("**Fallback Source:** Not configured")
                
                # Show availability
                massive_enabled = ds_config.get('massive_enabled', False)
                massive_configured = ds_config.get('massive_configured', False)
                yahoo_enabled = ds_config.get('yahoo_finance_enabled', True)
                
                st.markdown("---")
                st.markdown("**Source Availability:**")
                st.markdown(f"- Yahoo Finance: {'✅ Enabled' if yahoo_enabled else '❌ Disabled'}")
                st.markdown(f"- Massive.com: {'✅ Enabled & Configured' if (massive_enabled and massive_configured) else '⚠️ Not Configured' if massive_enabled else '❌ Disabled'}")
                
                # Show available sources
                available_sources = ds_config.get('available_sources', [])
                if available_sources:
                    st.markdown(f"**Available Sources:** {', '.join(available_sources)}")
                
                # Show debug information in expander
                debug_info = ds_config.get('debug', {})
                if debug_info:
                    with st.expander("🔍 Debug Information"):
                        st.json(debug_info)
                        
                        # Explain why massive might not be available
                        if "massive" not in available_sources:
                            st.warning("**Why Massive.com is not available:**")
                            if not debug_info.get('massive_enabled_from_config'):
                                st.write("❌ `MASSIVE_ENABLED` is not set to `true` in .env file")
                            if not debug_info.get('massive_api_key_set'):
                                st.write("❌ `MASSIVE_API_KEY` is not set in .env file")
                            if not debug_info.get('massive_available'):
                                st.write("❌ Massive.com library (polygon) is not installed")
                            st.info("💡 **To enable Massive.com:** Set `MASSIVE_ENABLED=true` and `MASSIVE_API_KEY=your_key` in `.env` file")
    except Exception as e:
        # Non-critical - just log, don't fail
        logger.debug(f"Could not fetch data source config: {e}")
    
    # Sidebar navigation
    st.sidebar.title("Testbed Navigation")
    test_section = st.sidebar.selectbox(
        "Select Test Section",
        [
            "🏥 System Health",
            "📥 Fetch Data",
            "📋 Audit History & Validation",
            "📊 Data Sources",
            "🧮 Calculations",
            "🎯 Strategies",
            "📋 Watchlist CRUD",
            "💼 Portfolio CRUD",
            "📈 Swing Trading",
            "📝 Blog Generation",
            "🌐 Market Features",
            "🔄 Workflow Engine Lifecycle",
            "🔄 End-to-End Workflows"
        ]
    )
    
    # System Health Section
    if test_section == "🏥 System Health":
        st.header("System Health Dashboard")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("API Health")
            if st.button("Check API Health", key="check_health"):
                with st.spinner("Checking APIs..."):
                    health = check_api_health()
                    
                    for api_name, status_info in health.items():
                        status = status_info.get("status", "unknown")
                        message = status_info.get("message", "")
                        timestamp = status_info.get("timestamp", "N/A")
                        details = status_info.get("details", {})
                        
                        # Always provide a message - never show empty
                        if not message or message.strip() == "":
                            if status == "healthy":
                                service_name = details.get("service", "API")
                                message = f"{service_name} is healthy and responding"
                            elif status == "unhealthy":
                                response_status = details.get("status", "unknown")
                                message = f"Health check returned status: {response_status}"
                            elif status == "error":
                                message = "Failed to connect to API - check if service is running"
                            else:
                                message = f"Unknown status: {status}"
                        
                        status_color = {
                            "healthy": "status-success",
                            "unhealthy": "status-warning",
                            "error": "status-error"
                        }.get(status, "")
                        
                        st.markdown(f"""
                            <div class="test-section">
                                <h4>{api_name}</h4>
                                <p class="{status_color}">Status: {status.upper()}</p>
                                <p><strong>Message:</strong> {message}</p>
                                <p><strong>Timestamp:</strong> {timestamp}</p>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Show additional details if available (always show for debugging)
                        if details:
                            with st.expander(f"View {api_name} Response Details"):
                                st.json(details)
        
        with col2:
            st.subheader("Data Source Status")
            symbol = st.text_input("Symbol to Check", value="AAPL", key="health_symbol")
            
            if st.button("Check Data Availability", key="check_data_avail"):
                with st.spinner("Checking data availability..."):
                    availability = check_data_availability(symbol)
                    
                    st.markdown("**Data Availability:**")
                    for data_type, available in availability.items():
                        status_icon = "✅" if available else "❌"
                        st.write(f"{status_icon} {data_type}: {'Available' if available else 'Not Available'}")
    
    # Fetch Data Section
    elif test_section == "📥 Fetch Data":
        st.header("📥 Fetch All Required Data")
        st.markdown("**Fetch all data types for a symbol: price, fundamentals, earnings, industry peers, and indicators**")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            symbol = st.text_input("Symbol", value="AAPL", key="fetch_symbol")
            period = st.selectbox(
                "Historical Period",
                ["1y", "6mo", "3mo", "1mo", "2y", "5y"],
                index=0,
                key="fetch_period"
            )
            calculate_indicators = st.checkbox("Calculate Indicators", value=True, key="fetch_indicators")
            
            st.markdown("---")
            st.markdown("**Data Types to Fetch:**")
            st.markdown("""
            - ✅ Price Historical (OHLCV)
            - ✅ Fundamentals (P/E, Revenue, etc.)
            - ✅ Earnings (Calendar & History)
            - ✅ Industry Peers
            - ✅ Indicators (if enabled)
            """)
            
            if st.button("🚀 Fetch All Data", key="fetch_all_data", type="primary", use_container_width=True):
                with st.spinner(f"Fetching all data for {symbol.upper()}... This may take 1-2 minutes."):
                    try:
                        client = get_python_api_client()
                        response = client.post(
                            "api/v1/fetch-historical-data",
                            json_data={
                                "symbol": symbol.upper(),
                                "period": period,
                                "calculate_indicators": calculate_indicators
                            },
                            timeout=180  # 3 minutes timeout for comprehensive fetch
                        )
                        
                        st.session_state["fetch_data_result"] = response
                        st.session_state["fetch_data_symbol"] = symbol.upper()
                        
                    except APIError as e:
                        st.error(f"❌ Failed to fetch data: {e}")
                        st.session_state["fetch_data_result"] = None
                    except Exception as e:
                        st.error(f"❌ Unexpected error: {e}")
                        st.session_state["fetch_data_result"] = None
        
        with col2:
            if "fetch_data_result" in st.session_state and st.session_state["fetch_data_result"]:
                result = st.session_state["fetch_data_result"]
                symbol = st.session_state.get("fetch_data_symbol", "N/A")
                
                st.subheader(f"📊 Fetch Results for {symbol}")
                
                # Overall status
                success = result.get("success", False)
                status_color = "status-success" if success else "status-error"
                status_icon = "✅" if success else "❌"
                
                st.markdown(f"""
                    <div class="test-section">
                        <h3>{status_icon} Overall Status: {'SUCCESS' if success else 'FAILED'}</h3>
                        <p><strong>Message:</strong> {result.get('message', 'No message')}</p>
                    </div>
                """, unsafe_allow_html=True)
                
                # Summary
                summary = result.get("summary", {})
                st.markdown("**📈 Summary:**")
                col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
                with col_sum1:
                    st.metric("Requested", summary.get("total_requested", 0))
                with col_sum2:
                    st.metric("✅ Successful", summary.get("total_successful", 0))
                with col_sum3:
                    st.metric("❌ Failed", summary.get("total_failed", 0))
                with col_sum4:
                    st.metric("⏭️ Skipped", summary.get("total_skipped", 0))
                
                # Use shared display function for detailed results with validation
                display_fetch_results(result)
                
                # Show full JSON response in expander
                with st.expander("📄 View Full JSON Response"):
                    st.json(result)
                
                # Success message
                if success:
                    st.success(f"✅ All data fetched successfully for {symbol}!")
                    st.balloons()
            else:
                st.info("👈 Enter a symbol and click 'Fetch All Data' to load all required data types.")
    
    # Audit History & Validation Section
    elif test_section == "📋 Audit History & Validation":
        st.header("📋 Data Fetch Audit History & Validation Reports")
        st.markdown("**Industry Standard: Comprehensive audit trail for all data loads and validation results**")
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            symbol = st.text_input("Symbol", value="AAPL", key="audit_symbol")
            limit = st.number_input("History Limit", min_value=10, max_value=100, value=20, step=10, key="audit_limit")
            
            st.markdown("---")
            st.markdown("**Actions:**")
            
            if st.button("📊 View Audit History", key="view_audit", use_container_width=True):
                st.session_state["audit_symbol_selected"] = symbol.upper()
                st.session_state["audit_limit_selected"] = limit
                st.session_state["load_audit"] = True
            
            if st.button("🔍 View Validation Reports", key="view_validation", use_container_width=True):
                st.session_state["validation_symbol_selected"] = symbol.upper()
                st.session_state["load_validation"] = True
            
            if st.button("✅ Check Signal Readiness", key="check_readiness", use_container_width=True):
                st.session_state["readiness_symbol_selected"] = symbol.upper()
                st.session_state["load_readiness"] = True
            
            if st.button("🔄 Auto-Retry Failed Fetches", key="auto_retry", use_container_width=True):
                st.session_state["retry_symbol_selected"] = symbol.upper()
                st.session_state["do_retry"] = True
        
        with col2:
            # Audit History Tab
            tab1, tab2, tab3 = st.tabs(["📊 Audit History", "🔍 Validation Reports", "✅ Signal Readiness"])
            
            with tab1:
                if st.session_state.get("load_audit") or st.session_state.get("audit_symbol_selected"):
                    audit_symbol = st.session_state.get("audit_symbol_selected", symbol.upper())
                    audit_limit = st.session_state.get("audit_limit_selected", limit)
                    
                    try:
                        python_client = get_python_api_client()
                        audit_response = python_client.get(
                            f"api/v1/data-fetch-audit/{audit_symbol}",
                            params={"limit": audit_limit}
                        )
                        
                        if audit_response and audit_response.get("audit_records"):
                            audit_records = audit_response.get("audit_records", [])
                            
                            st.subheader(f"📊 Audit History for {audit_symbol}")
                            st.markdown(f"**Total Records:** {len(audit_records)}")
                            
                            # Summary metrics
                            if audit_records:
                                success_count = sum(1 for r in audit_records if r.get("success"))
                                failed_count = len(audit_records) - success_count
                                
                                col_met1, col_met2, col_met3 = st.columns(3)
                                with col_met1:
                                    st.metric("Total Fetches", len(audit_records))
                                with col_met2:
                                    st.metric("✅ Successful", success_count)
                                with col_met3:
                                    st.metric("❌ Failed", failed_count)
                            
                            # Display audit records in a table
                            if audit_records:
                                df_audit = pd.DataFrame(audit_records)
                                
                                # Format columns for display
                                if "timestamp" in df_audit.columns:
                                    df_audit["timestamp"] = pd.to_datetime(df_audit["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
                                
                                # Add status icon
                                df_audit["status_icon"] = df_audit["success"].apply(lambda x: "✅" if x else "❌")
                                
                                # Reorder columns - ensure data_source and error_message are prominently displayed
                                display_cols = ["status_icon", "fetch_type", "data_source", "fetch_mode", "timestamp", 
                                               "rows_fetched", "rows_saved", "fetch_duration_ms", "success", "error_message"]
                                display_cols = [c for c in display_cols if c in df_audit.columns]
                                
                                # Truncate long error messages for table display
                                if "error_message" in df_audit.columns:
                                    df_audit["error_message"] = df_audit["error_message"].apply(
                                        lambda x: (x[:100] + "...") if x and len(str(x)) > 100 else x
                                    )
                                
                                # Highlight data source column
                                if "data_source" in df_audit.columns:
                                    st.markdown("**📊 Data Source Used:** Shows which data provider was used (yahoo_finance, massive, fallback)")
                                
                                st.dataframe(
                                    df_audit[display_cols],
                                    use_container_width=True,
                                    hide_index=True
                                )
                                
                                # Detailed view for each record
                                st.markdown("---")
                                st.subheader("📋 Detailed Audit Records")
                                
                                for idx, record in enumerate(audit_records):
                                    status_icon = "✅" if record.get("success") else "❌"
                                    with st.expander(
                                        f"{status_icon} {record.get('fetch_type', 'N/A')} - {record.get('timestamp', 'N/A')}",
                                        expanded=(not record.get("success"))
                                    ):
                                        col_det1, col_det2 = st.columns(2)
                                        
                                        with col_det1:
                                            st.write(f"**Fetch Type:** {record.get('fetch_type', 'N/A')}")
                                            st.write(f"**Fetch Mode:** {record.get('fetch_mode', 'N/A')}")
                                            st.write(f"**Data Source:** {record.get('data_source', 'N/A')}")
                                            st.write(f"**Timestamp:** {record.get('timestamp', 'N/A')}")
                                        
                                        with col_det2:
                                            rows_fetched = record.get('rows_fetched', 0)
                                            rows_saved = record.get('rows_saved', 0)
                                            st.write(f"**Rows Fetched:** {rows_fetched}")
                                            st.write(f"**Rows Saved:** {rows_saved}")
                                            
                                            # Highlight discrepancy between fetched and saved
                                            if rows_fetched > 0 and rows_saved == 0:
                                                st.warning(f"⚠️ **Warning:** Fetched {rows_fetched} rows but saved 0. Check error message below.")
                                            elif rows_fetched > rows_saved:
                                                st.warning(f"⚠️ **Partial:** Fetched {rows_fetched} rows but only saved {rows_saved}.")
                                            
                                            st.write(f"**Duration:** {record.get('fetch_duration_ms', 0)} ms")
                                            success = record.get('success', False)
                                            st.write(f"**Success:** {'✅ Yes' if success else '❌ No'}")
                                        
                                        # Always show error message prominently if present
                                        error_message = record.get("error_message")
                                        if error_message:
                                            st.error(f"**❌ Error Message:** {error_message}")
                                        elif not record.get('success', False):
                                            # If failed but no error message, show a generic message
                                            st.warning("**⚠️ Warning:** Operation failed but no error message was recorded.")
                                        
                                        if record.get("validation_report_id"):
                                            st.info(f"**Validation Report ID:** {record.get('validation_report_id')}")
                                        
                                        # Auto-retry button for failed fetches
                                        if not record.get("success"):
                                            if st.button(f"🔄 Retry {record.get('fetch_type', 'N/A')}", key=f"retry_{idx}"):
                                                try:
                                                    python_client.post(
                                                        "api/v1/refresh-data",
                                                        json_data={
                                                            "symbol": audit_symbol,
                                                            "data_types": [record.get("fetch_type")],
                                                            "force": True
                                                        },
                                                        timeout=120
                                                    )
                                                    st.success(f"✅ Retry initiated for {record.get('fetch_type')}")
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"❌ Retry failed: {e}")
                        else:
                            st.info(f"📭 No audit history found for {audit_symbol}. Fetch data first to see audit records.")
                    except APIError as e:
                        st.error(f"❌ Failed to fetch audit history: {e}")
                    except Exception as e:
                        st.error(f"❌ Unexpected error: {e}")
                else:
                    st.info("👈 Enter a symbol and click 'View Audit History' to see data fetch audit trail.")
            
            with tab2:
                if st.session_state.get("load_validation") or st.session_state.get("validation_symbol_selected"):
                    validation_symbol = st.session_state.get("validation_symbol_selected", symbol.upper())
                    
                    try:
                        python_client = get_python_api_client()
                        
                        # Get latest validation report from the fetch result if available
                        if "fetch_data_result" in st.session_state:
                            fetch_result = st.session_state["fetch_data_result"]
                            validation_reports = fetch_result.get("results", {}).get("price_historical", {}).get("validation")
                            
                            if validation_reports:
                                st.subheader(f"🔍 Latest Validation Report for {validation_symbol}")
                                display_validation_report(validation_reports, validation_symbol)
                            else:
                                st.info("📭 No validation report in last fetch. Fetch data first to see validation results.")
                        else:
                            # Try to get from database via API (would need new endpoint)
                            st.info("📭 No validation report available. Fetch data first to generate validation report.")
                    except Exception as e:
                        st.error(f"❌ Error loading validation report: {e}")
                else:
                    st.info("👈 Enter a symbol and click 'View Validation Reports' to see validation results.")
            
            with tab3:
                if st.session_state.get("load_readiness") or st.session_state.get("readiness_symbol_selected"):
                    readiness_symbol = st.session_state.get("readiness_symbol_selected", symbol.upper())
                    
                    try:
                        python_client = get_python_api_client()
                        readiness_response = python_client.get(
                            f"api/v1/signal-readiness/{readiness_symbol}",
                            params={"signal_type": "swing_trend"}
                        )
                        
                        if readiness_response:
                            st.subheader(f"✅ Signal Readiness for {readiness_symbol}")
                            
                            readiness_status = readiness_response.get("readiness_status", "unknown")
                            status_color = {
                                "ready": "🟢",
                                "not_ready": "🔴",
                                "partial": "🟡"
                            }.get(readiness_status, "⚪")
                            
                            st.markdown(f"""
                                <div class="test-section">
                                    <h3>{status_color} Status: {readiness_status.upper()}</h3>
                                    <p><strong>Reason:</strong> {readiness_response.get('readiness_reason', 'N/A')}</p>
                                    <p><strong>Data Quality Score:</strong> {readiness_response.get('data_quality_score', 0):.2f}/1.0</p>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            col_read1, col_read2 = st.columns(2)
                            
                            with col_read1:
                                st.markdown("**Required Indicators:**")
                                required = readiness_response.get("required_indicators", [])
                                for ind in required:
                                    st.write(f"  - {ind}")
                            
                            with col_read2:
                                st.markdown("**Available Indicators:**")
                                available = readiness_response.get("available_indicators", [])
                                missing = readiness_response.get("missing_indicators", [])
                                
                                for ind in available:
                                    st.write(f"  ✅ {ind}")
                                
                                if missing:
                                    st.markdown("**Missing Indicators:**")
                                    for ind in missing:
                                        st.write(f"  ❌ {ind}")
                                    
                                    # Explain why indicators are missing
                                    st.markdown("---")
                                    st.warning("""
                                    **🔍 Why are indicators missing?**
                                    
                                    Data fetch shows "successful" because **price data was fetched and saved**. However, 
                                    **indicators are calculated separately** from price data. This is by design:
                                    
                                    1. **Step 1:** Fetch price data (OHLCV) ✅ - This succeeded
                                    2. **Step 2:** Calculate indicators from price data ❌ - This hasn't been done yet
                                    
                                    **Solution:** Calculate indicators using the button below or re-fetch with "Calculate Indicators" enabled.
                                    """)
                            
                            recommendations = readiness_response.get("recommendations", [])
                            if recommendations:
                                st.markdown("---")
                                st.markdown("**💡 Actionable Recommendations:**")
                                for rec in recommendations:
                                    # Check if recommendation contains actionable items
                                    if "**Action Required:**" in rec or "**Solution:**" in rec or "**Quick Fix:**" in rec or "**Problem:**" in rec:
                                        st.warning(rec)
                                    elif "**Why:**" in rec:
                                        st.info(rec)
                                    else:
                                        st.info(rec)
                                
                                # Add action buttons for common issues
                                if readiness_status == "not_ready":
                                    missing = readiness_response.get("missing_indicators", [])
                                    if missing:
                                        st.markdown("---")
                                        st.markdown("**🔧 Quick Actions:**")
                                        
                                        col_action1, col_action2 = st.columns(2)
                                        
                                        with col_action1:
                                            if st.button("📊 Calculate Indicators", key=f"calc_indicators_{readiness_symbol}", use_container_width=True):
                                                with st.spinner(f"Calculating indicators for {readiness_symbol}..."):
                                                    try:
                                                        python_client.post(
                                                            "api/v1/refresh-data",
                                                            json_data={
                                                                "symbol": readiness_symbol,
                                                                "data_types": ["indicators"],
                                                                "force": True
                                                            },
                                                            timeout=120
                                                        )
                                                        st.success(f"✅ Indicators calculation initiated for {readiness_symbol}!")
                                                        st.info("🔄 Refresh this page in a few seconds to see updated status.")
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"❌ Failed to calculate indicators: {e}")
                                        
                                        with col_action2:
                                            if st.button("📥 Fetch All Data + Indicators", key=f"fetch_all_{readiness_symbol}", use_container_width=True):
                                                with st.spinner(f"Fetching all data and calculating indicators for {readiness_symbol}..."):
                                                    try:
                                                        python_client.post(
                                                            "api/v1/fetch-historical-data",
                                                            json_data={
                                                                "symbol": readiness_symbol,
                                                                "period": "1y",
                                                                "calculate_indicators": True
                                                            },
                                                            timeout=180
                                                        )
                                                        st.success(f"✅ Data fetch and indicator calculation initiated for {readiness_symbol}!")
                                                        st.info("🔄 Refresh this page in a few seconds to see updated status.")
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"❌ Failed to fetch data: {e}")
                            
                            # Show full response
                            with st.expander("📄 View Full Readiness Response"):
                                st.json(readiness_response)
                        else:
                            st.info(f"📭 No readiness data found for {readiness_symbol}")
                    except APIError as e:
                        st.error(f"❌ Failed to check signal readiness: {e}")
                    except Exception as e:
                        st.error(f"❌ Unexpected error: {e}")
                else:
                    st.info("👈 Enter a symbol and click 'Check Signal Readiness' to see readiness status.")
            
            # Auto-retry functionality
            if st.session_state.get("do_retry"):
                retry_symbol = st.session_state.get("retry_symbol_selected", symbol.upper())
                st.markdown("---")
                st.subheader("🔄 Auto-Retry Failed Fetches")
                
                try:
                    python_client = get_python_api_client()
                    audit_response = python_client.get(
                        f"api/v1/data-fetch-audit/{retry_symbol}",
                        params={"limit": 50}
                    )
                    
                    if audit_response and audit_response.get("audit_records"):
                        failed_records = [r for r in audit_response.get("audit_records", []) if not r.get("success")]
                        
                        if failed_records:
                            st.warning(f"Found {len(failed_records)} failed fetch(es). Retrying...")
                            
                            retry_results = []
                            for record in failed_records:
                                fetch_type = record.get("fetch_type")
                                with st.spinner(f"Retrying {fetch_type}..."):
                                    try:
                                        retry_response = python_client.post(
                                            "api/v1/refresh-data",
                                            json_data={
                                                "symbol": retry_symbol,
                                                "data_types": [fetch_type],
                                                "force": True
                                            },
                                            timeout=120
                                        )
                                        retry_results.append({
                                            "fetch_type": fetch_type,
                                            "success": True,
                                            "message": "Retry successful"
                                        })
                                    except Exception as e:
                                        retry_results.append({
                                            "fetch_type": fetch_type,
                                            "success": False,
                                            "message": str(e)
                                        })
                            
                            # Display retry results
                            for result in retry_results:
                                if result["success"]:
                                    st.success(f"✅ {result['fetch_type']}: {result['message']}")
                                else:
                                    st.error(f"❌ {result['fetch_type']}: {result['message']}")
                            
                            st.info("🔄 Refresh the audit history to see updated results.")
                        else:
                            st.success(f"✅ No failed fetches found for {retry_symbol}. All fetches are successful!")
                except Exception as e:
                    st.error(f"❌ Auto-retry failed: {e}")
                
                st.session_state["do_retry"] = False
    
    # Data Sources Section
    elif test_section == "📊 Data Sources":
        st.header("Data Source Testing")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            symbol = st.text_input("Symbol", value="AAPL", key="data_symbol")
            data_types = st.multiselect(
                "Data Types to Test",
                [
                    "price_historical",
                    "price_current",
                    "fundamentals",
                    "news",
                    "earnings",
                    "industry_peers"
                ],
                default=["price_historical"]
            )
            
            if st.button("Test Data Sources", key="test_data_sources"):
                results = []
                for data_type in data_types:
                    with st.spinner(f"Testing {data_type}..."):
                        result = test_data_source(symbol, data_type)
                        results.append(result)
                
                st.session_state["data_source_results"] = results
        
        with col2:
            if "data_source_results" in st.session_state:
                st.subheader("Test Results")
                for result in st.session_state["data_source_results"]:
                    status_icon = "✅" if result["success"] else "❌"
                    st.markdown(f"""
                        <div class="test-section">
                            <h4>{status_icon} {result['data_type']}</h4>
                            <p><strong>Symbol:</strong> {result['symbol']}</p>
                            <p><strong>Status:</strong> {result['message']}</p>
                            <p><strong>Data Count:</strong> {result['data_count']}</p>
                            {f"<p><strong>Error:</strong> {result['error']}</p>" if result.get('error') else ""}
                        </div>
                    """, unsafe_allow_html=True)
    
    # Calculations Section
    elif test_section == "🧮 Calculations":
        st.header("🧮 Calculation Testing")
        st.markdown("**Test individual calculation functions and verify results**")
        
        tab1, tab2, tab3 = st.tabs(["📊 Indicator Calculations", "📈 Composite Metrics", "🎯 Actionable Levels"])
        
        with tab1:
            st.subheader("📊 Indicator Calculation Testing")
            st.markdown("**Test calculation of technical indicators (EMA, SMA, RSI, MACD, ATR, etc.)**")
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                symbol = st.text_input("Symbol", value="AAPL", key="calc_indicator_symbol")
                
                st.markdown("---")
                st.markdown("**Calculation Options:**")
                force_recalc = st.checkbox("Force Recalculation", value=False, key="force_recalc", 
                                          help="Force recalculation even if indicators already exist")
                
                show_details = st.checkbox("Show Detailed Results", value=True, key="show_calc_details",
                                         help="Display detailed breakdown of calculated indicators")
                
                st.markdown("---")
                
                if st.button("🔄 Calculate Indicators", key="calc_indicators_btn", use_container_width=True):
                    with st.spinner(f"Calculating indicators for {symbol}..."):
                        try:
                            python_client = get_python_api_client()
                            response = python_client.post(
                                "api/v1/refresh-data",
                                json_data={
                                    "symbol": symbol.upper(),
                                    "data_types": ["indicators"],
                                    "force": force_recalc
                                },
                                timeout=120
                            )
                            
                            if response:
                                st.session_state["indicator_calc_result"] = response
                                st.session_state["indicator_calc_symbol"] = symbol.upper()
                                st.success(f"✅ Indicator calculation initiated for {symbol.upper()}")
                            else:
                                st.error("❌ No response from API")
                        except APIError as e:
                            st.error(f"❌ API Error: {e}")
                        except Exception as e:
                            st.error(f"❌ Error: {e}")
            
            with col2:
                if st.session_state.get("indicator_calc_result"):
                    result = st.session_state["indicator_calc_result"]
                    symbol = st.session_state.get("indicator_calc_symbol", "N/A")
                    
                    st.subheader(f"📊 Calculation Results for {symbol}")
                    
                    # Summary
                    summary = result.get("summary", {})
                    col_sum1, col_sum2, col_sum3 = st.columns(3)
                    with col_sum1:
                        st.metric("Total Requested", summary.get("total_requested", 0))
                    with col_sum2:
                        st.metric("✅ Successful", summary.get("total_successful", 0))
                    with col_sum3:
                        st.metric("❌ Failed", summary.get("total_failed", 0))
                    
                    # Detailed results
                    results = result.get("results", {})
                    indicators_result = results.get("indicators")
                    
                    if indicators_result:
                        status = indicators_result.get("status", "unknown")
                        message = indicators_result.get("message", "")
                        error = indicators_result.get("error")
                        
                        if status == "success":
                            st.success(f"✅ {message}")
                            
                            if show_details:
                                st.markdown("---")
                                st.markdown("**📋 Calculated Indicators:**")
                                
                                # Fetch calculated indicators from Go API to show what was calculated
                                try:
                                    go_client = get_go_api_client()
                                    stock_data = go_client.get(f"api/v1/stock/{symbol}?subscription_level=pro")
                                    
                                    if stock_data and stock_data.get("indicators"):
                                        indicators = stock_data["indicators"]
                                        
                                        # Group indicators by category
                                        st.markdown("**Moving Averages:**")
                                        ma_cols = ["ema9", "ema20", "ema21", "ema50", "sma50", "sma200", "ma7", "ma21"]
                                        ma_data = {k: v for k, v in indicators.items() if k in ma_cols and v is not None}
                                        if ma_data:
                                            st.json(ma_data)
                                        else:
                                            st.info("No moving averages calculated")
                                        
                                        st.markdown("**Momentum Indicators:**")
                                        momentum_cols = ["rsi", "macd", "macd_signal", "macd_histogram"]
                                        momentum_data = {k: v for k, v in indicators.items() if k in momentum_cols and v is not None}
                                        if momentum_data:
                                            st.json(momentum_data)
                                        else:
                                            st.info("No momentum indicators calculated")
                                        
                                        st.markdown("**Volatility Indicators:**")
                                        vol_cols = ["atr", "bb_upper", "bb_middle", "bb_lower"]
                                        vol_data = {k: v for k, v in indicators.items() if k in vol_cols and v is not None}
                                        if vol_data:
                                            st.json(vol_data)
                                        else:
                                            st.info("No volatility indicators calculated")
                                        
                                        st.markdown("**Volume Indicators:**")
                                        volume_cols = ["volume", "volume_ma"]
                                        volume_data = {k: v for k, v in indicators.items() if k in volume_cols and v is not None}
                                        if volume_data:
                                            st.json(volume_data)
                                        else:
                                            st.info("No volume indicators calculated")
                                        
                                        st.markdown("**Trend Indicators:**")
                                        trend_cols = ["long_term_trend", "medium_term_trend", "momentum_score"]
                                        trend_data = {k: v for k, v in indicators.items() if k in trend_cols and v is not None}
                                        if trend_data:
                                            st.json(trend_data)
                                        else:
                                            st.info("No trend indicators calculated")
                                        
                                        # Show all indicators in expander
                                        with st.expander("📄 View All Calculated Indicators"):
                                            st.json(indicators)
                                    else:
                                        st.warning("⚠️ Indicators calculated but not yet available via API. Try refreshing in a few seconds.")
                                        
                                except Exception as e:
                                    st.warning(f"⚠️ Could not fetch indicator details: {e}")
                                    st.info("💡 Indicators were calculated successfully. Use 'Data Sources' section to view them.")
                        else:
                            st.error(f"❌ {message}")
                            if error:
                                st.error(f"Error: {error}")
                    else:
                        st.info("📭 No indicator calculation result available. Click 'Calculate Indicators' to test.")
                else:
                    st.info("👈 Enter a symbol and click 'Calculate Indicators' to test indicator calculation.")
        
        with tab2:
            st.subheader("📈 Composite Metrics Testing")
            st.markdown("**Test calculation of composite scores and momentum metrics**")
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                symbol = st.text_input("Symbol", value="AAPL", key="calc_composite_symbol")
                subscription_level = st.selectbox("Subscription Level", ["basic", "pro", "elite"], 
                                                  index=1, key="calc_composite_sub")
                
                if st.button("📊 Get Composite Metrics", key="get_composite_btn", use_container_width=True):
                    try:
                        go_client = get_go_api_client()
                        response = go_client.get(f"api/v1/stock/{symbol.upper()}?subscription_level={subscription_level}")
                        
                        if response:
                            st.session_state["composite_result"] = response
                            st.session_state["composite_symbol"] = symbol.upper()
                            st.success(f"✅ Fetched composite metrics for {symbol.upper()}")
                        else:
                            st.error("❌ No response from API")
                    except APIError as e:
                        st.error(f"❌ API Error: {e}")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
            
            with col2:
                if st.session_state.get("composite_result"):
                    result = st.session_state["composite_result"]
                    symbol = st.session_state.get("composite_symbol", "N/A")
                    
                    st.subheader(f"📈 Composite Metrics for {symbol}")
                    
                    indicators = result.get("indicators", {})
                    signal = result.get("signal", {})
                    
                    # Composite Score (Momentum Score)
                    momentum_score = indicators.get("momentum_score")
                    if momentum_score is not None:
                        st.metric("Composite Score (Momentum)", f"{momentum_score:.2f}/100")
                        st.progress(momentum_score / 100)
                        
                        # Score interpretation
                        if momentum_score >= 70:
                            st.success("🟢 Strong Momentum - Bullish")
                        elif momentum_score >= 50:
                            st.info("🟡 Moderate Momentum - Neutral")
                        else:
                            st.warning("🔴 Weak Momentum - Bearish")
                    else:
                        st.warning("⚠️ Composite score not available. Calculate indicators first.")
                    
                    # Additional metrics
                    st.markdown("---")
                    st.markdown("**📊 Additional Metrics:**")
                    
                    metrics_data = {
                        "RSI": indicators.get("rsi"),
                        "MACD": indicators.get("macd"),
                        "MACD Signal": indicators.get("macd_signal"),
                        "Long Term Trend": indicators.get("long_term_trend"),
                        "Medium Term Trend": indicators.get("medium_term_trend")
                    }
                    
                    # Filter out None values
                    metrics_data = {k: v for k, v in metrics_data.items() if v is not None}
                    
                    if metrics_data:
                        st.json(metrics_data)
                    else:
                        st.info("No additional metrics available")
        
        with tab3:
            st.subheader("🎯 Actionable Levels Testing")
            st.markdown("**Test calculation of actionable entry/exit levels (Pro/Elite feature)**")
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                symbol = st.text_input("Symbol", value="AAPL", key="calc_actionable_symbol")
                subscription_level = st.selectbox("Subscription Level", ["pro", "elite"], 
                                                  index=0, key="calc_actionable_sub")
                
                if st.button("🎯 Get Actionable Levels", key="get_actionable_btn", use_container_width=True):
                    try:
                        go_client = get_go_api_client()
                        response = go_client.get(f"api/v1/stock/{symbol.upper()}?subscription_level={subscription_level}")
                        
                        if response:
                            st.session_state["actionable_result"] = response
                            st.session_state["actionable_symbol"] = symbol.upper()
                            st.success(f"✅ Fetched actionable levels for {symbol.upper()}")
                        else:
                            st.error("❌ No response from API")
                    except APIError as e:
                        st.error(f"❌ API Error: {e}")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
            
            with col2:
                if st.session_state.get("actionable_result"):
                    result = st.session_state["actionable_result"]
                    symbol = st.session_state.get("actionable_symbol", "N/A")
                    
                    st.subheader(f"🎯 Actionable Levels for {symbol}")
                    
                    signal = result.get("signal", {})
                    indicators = result.get("indicators", {})
                    current_price = result.get("current_price")
                    
                    # Pullback Zone
                    pullback_zone = signal.get("pullback_zone")
                    if pullback_zone:
                        st.markdown("**📉 Pullback Zone:**")
                        if isinstance(pullback_zone, dict):
                            lower = pullback_zone.get("lower")
                            upper = pullback_zone.get("upper")
                            if lower and upper:
                                st.metric("Lower Bound", f"${lower:.2f}")
                                st.metric("Upper Bound", f"${upper:.2f}")
                                if current_price:
                                    if lower <= current_price <= upper:
                                        st.success(f"✅ Current price (${current_price:.2f}) is within pullback zone")
                                    elif current_price < lower:
                                        st.info(f"📊 Current price (${current_price:.2f}) is below pullback zone")
                                    else:
                                        st.warning(f"⚠️ Current price (${current_price:.2f}) is above pullback zone")
                        else:
                            st.json(pullback_zone)
                    else:
                        st.warning("⚠️ Pullback zone not available. Calculate indicators first.")
                    
                    # Stop Loss
                    stop_loss = signal.get("stop_loss")
                    if stop_loss:
                        st.markdown("---")
                        st.markdown("**🛑 Stop Loss Level:**")
                        st.metric("Stop Loss", f"${stop_loss:.2f}")
                        if current_price:
                            risk_pct = ((current_price - stop_loss) / current_price) * 100
                            st.info(f"Risk: {risk_pct:.2f}% below current price")
                    else:
                        st.warning("⚠️ Stop loss not available. Calculate indicators first.")
                    
                    # Signal Info
                    signal_type = signal.get("type")
                    if signal_type:
                        st.markdown("---")
                        st.markdown("**📊 Signal Information:**")
                        st.write(f"**Type:** {signal_type.upper()}")
                        st.write(f"**Confidence:** {signal.get('confidence', 0):.1%}")
                        st.write(f"**Reason:** {signal.get('reason', 'N/A')}")
        
        # Legacy calculations section (for backward compatibility)
        st.markdown("---")
        with st.expander("🔧 Legacy Calculation Testing"):
            col1, col2 = st.columns([1, 2])
            
            with col1:
                symbol_legacy = st.text_input("Symbol", value="AAPL", key="calc_symbol_legacy")
                calculation_types = st.multiselect(
                    "Calculations to Test",
                    [
                        "indicators",
                        "composite_score",
                        "actionable_levels"
                    ],
                    default=["indicators"],
                    key="calc_types_legacy"
                )
                
                st.caption("💡 Note: 'signals' is a data type, not a calculation. Test it in the 'Data Sources' section.")
                
                if st.button("Test Calculations", key="test_calculations_legacy"):
                    results = []
                    for calc_type in calculation_types:
                        with st.spinner(f"Testing {calc_type}..."):
                            result = test_calculation(symbol_legacy, calc_type)
                            results.append(result)
                    
                    st.session_state["calculation_results"] = results
            
            with col2:
                if "calculation_results" in st.session_state:
                    st.subheader("Calculation Results")
                    for result in st.session_state["calculation_results"]:
                        status_icon = "✅" if result["success"] else "❌"
                        st.markdown(f"""
                            <div class="test-section">
                                <h4>{status_icon} {result['calculation_type']}</h4>
                                <p><strong>Symbol:</strong> {result['symbol']}</p>
                                <p><strong>Status:</strong> {result['message']}</p>
                                {f"<pre>{json.dumps(result['result'], indent=2)}</pre>" if result.get('result') else ""}
                                {f"<p><strong>Error:</strong> {result['error']}</p>" if result.get('error') else ""}
                            </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("👈 Enter a symbol and click 'Test Calculations' to see results.")
    
    # Strategies Section
    elif test_section == "🎯 Strategies":
        st.header("Strategy Testing")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            symbol = st.text_input("Symbol", value="AAPL", key="strategy_symbol")
            strategies = st.multiselect(
                "Strategies to Test",
                [
                    "technical",
                    "hybrid_llm",
                    "swing_trend"
                ],
                default=["technical"]
            )
            
            if st.button("Test Strategies", key="test_strategies"):
                results = []
                for strategy in strategies:
                    with st.spinner(f"Testing {strategy}..."):
                        result = test_strategy(symbol, strategy)
                        results.append(result)
                
                st.session_state["strategy_results"] = results
        
        with col2:
            if "strategy_results" in st.session_state:
                st.subheader("Strategy Results")
                for result in st.session_state["strategy_results"]:
                    status_icon = "✅" if result["success"] else "❌"
                    st.markdown(f"""
                        <div class="test-section">
                            <h4>{status_icon} {result['strategy']}</h4>
                            <p><strong>Symbol:</strong> {result['symbol']}</p>
                            <p><strong>Signal:</strong> {result.get('signal', 'N/A')}</p>
                            <p><strong>Confidence:</strong> {result.get('confidence', 'N/A')}</p>
                            <p><strong>Status:</strong> {result['message']}</p>
                            {f"<p><strong>Error:</strong> {result['error']}</p>" if result.get('error') else ""}
                        </div>
                    """, unsafe_allow_html=True)
    
    # Watchlist CRUD Section
    elif test_section == "📋 Watchlist CRUD":
        st.header("Watchlist CRUD Testing")
        
        tab1, tab2, tab3, tab4 = st.tabs(["Create", "Read", "Update", "Delete"])
        
        with tab1:
            st.subheader("Create Watchlist")
            user_id = st.text_input("User ID", value="user1", key="watchlist_create_user")
            watchlist_name = st.text_input("Watchlist Name", key="watchlist_create_name")
            watchlist_type = st.selectbox("Type", ["simple", "advanced", "smart"], key="watchlist_create_type")
            
            if st.button("Create Watchlist", key="create_watchlist"):
                try:
                    client = get_go_api_client()
                    response = client.post(
                        "api/v1/watchlists",
                        json_data={
                            "user_id": user_id,
                            "watchlist_name": watchlist_name,
                            "watchlist_type": watchlist_type
                        }
                    )
                    st.success(f"Watchlist created: {response.get('watchlist_id')}")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        with tab2:
            st.subheader("Read Watchlists")
            user_id = st.text_input("User ID", value="user1", key="watchlist_read_user")
            
            if st.button("Get Watchlists", key="get_watchlists"):
                try:
                    client = get_go_api_client()
                    response = client.get(f"api/v1/watchlists/user/{user_id}")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        with tab3:
            st.subheader("Update Watchlist")
            watchlist_id = st.text_input("Watchlist ID", key="watchlist_update_id")
            new_name = st.text_input("New Name", key="watchlist_update_name")
            
            if st.button("Update Watchlist", key="update_watchlist"):
                try:
                    client = get_go_api_client()
                    response = client.put(
                        f"api/v1/watchlists/{watchlist_id}",
                        json_data={"watchlist_name": new_name}
                    )
                    st.success("Watchlist updated")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        with tab4:
            st.subheader("Delete Watchlist")
            watchlist_id = st.text_input("Watchlist ID", key="watchlist_delete_id")
            
            if st.button("Delete Watchlist", key="delete_watchlist"):
                try:
                    client = get_go_api_client()
                    response = client.delete(f"api/v1/watchlists/{watchlist_id}")
                    st.success("Watchlist deleted")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    # Portfolio CRUD Section
    elif test_section == "💼 Portfolio CRUD":
        st.header("Portfolio CRUD Testing")
        
        tab1, tab2, tab3, tab4 = st.tabs(["Create", "Read", "Update", "Delete"])
        
        with tab1:
            st.subheader("Create Portfolio")
            user_id = st.text_input("User ID", value="user1", key="portfolio_create_user")
            portfolio_name = st.text_input("Portfolio Name", key="portfolio_create_name")
            portfolio_type = st.selectbox("Type", ["long_term", "swing", "options"], key="portfolio_create_type")
            
            if st.button("Create Portfolio", key="create_portfolio"):
                try:
                    client = get_go_api_client()
                    response = client.post(
                        "api/v1/portfolios",
                        json_data={
                            "user_id": user_id,
                            "portfolio_name": portfolio_name,
                            "portfolio_type": portfolio_type
                        }
                    )
                    st.success(f"Portfolio created: {response.get('portfolio_id')}")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        with tab2:
            st.subheader("Read Portfolios")
            user_id = st.text_input("User ID", value="user1", key="portfolio_read_user")
            
            if st.button("Get Portfolios", key="get_portfolios"):
                try:
                    client = get_go_api_client()
                    response = client.get(f"api/v1/portfolios/user/{user_id}")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        with tab3:
            st.subheader("Update Portfolio")
            portfolio_id = st.text_input("Portfolio ID", key="portfolio_update_id")
            new_name = st.text_input("New Name", key="portfolio_update_name")
            
            if st.button("Update Portfolio", key="update_portfolio"):
                try:
                    client = get_go_api_client()
                    response = client.put(
                        f"api/v1/portfolios/{portfolio_id}",
                        json_data={"portfolio_name": new_name}
                    )
                    st.success("Portfolio updated")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        with tab4:
            st.subheader("Delete Portfolio")
            portfolio_id = st.text_input("Portfolio ID", key="portfolio_delete_id")
            
            if st.button("Delete Portfolio", key="delete_portfolio"):
                try:
                    client = get_go_api_client()
                    response = client.delete(f"api/v1/portfolios/{portfolio_id}")
                    st.success("Portfolio deleted")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    # Swing Trading Section
    elif test_section == "📈 Swing Trading":
        st.header("Swing Trading Testing")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            symbol = st.text_input("Symbol", value="TQQQ", key="swing_symbol")
            user_id = st.text_input("User ID", value="user1", key="swing_user")
            
            if st.button("Generate Swing Signal", key="generate_swing"):
                try:
                    client = get_python_api_client()
                    response = client.post(
                        "api/v1/swing/signal",
                        json_data={
                            "symbol": symbol,
                            "user_id": user_id
                        }
                    )
                    st.session_state["swing_result"] = response
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        with col2:
            if "swing_result" in st.session_state:
                st.subheader("Swing Trading Result")
                result = st.session_state["swing_result"]
                st.json(result)
    
    # Blog Generation Section
    elif test_section == "📝 Blog Generation":
        st.header("Blog Generation Testing")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            user_id = st.text_input("User ID", value="user1", key="blog_user")
            symbol = st.text_input("Symbol (optional)", key="blog_symbol")
            topic_type = st.selectbox("Topic Type", ["signal_change", "trend_breakout", "earnings_alert"], key="blog_topic")
            
            if st.button("Generate Blog", key="generate_blog"):
                try:
                    client = get_python_api_client()
                    payload = {
                        "user_id": user_id,
                        "topic_type": topic_type
                    }
                    if symbol:
                        payload["symbol"] = symbol
                    
                    response = client.post("api/v1/blog/generate", json_data=payload)
                    st.session_state["blog_result"] = response
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        with col2:
            if "blog_result" in st.session_state:
                st.subheader("Blog Generation Result")
                result = st.session_state["blog_result"]
                st.json(result)
    
    # Market Features Section
    elif test_section == "🌐 Market Features":
        st.header("Market Features Testing")
        
        feature = st.selectbox(
            "Select Feature",
            [
                "Market Movers",
                "Sector Performance",
                "Stock Comparison",
                "Analyst Ratings",
                "Market Overview",
                "Market Trends"
            ]
        )
        
        if feature == "Market Movers":
            if st.button("Get Market Movers", key="get_movers"):
                try:
                    client = get_go_api_client()
                    response = client.get("api/v1/market/movers")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        elif feature == "Sector Performance":
            if st.button("Get Sector Performance", key="get_sectors"):
                try:
                    client = get_go_api_client()
                    response = client.get("api/v1/market/sectors")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        elif feature == "Stock Comparison":
            symbols = st.text_input("Symbols (comma-separated)", value="AAPL,GOOGL,NVDA", key="compare_symbols")
            if st.button("Compare Stocks", key="compare_stocks"):
                try:
                    client = get_go_api_client()
                    response = client.post(
                        "api/v1/stocks/compare",
                        json_data={"symbols": [s.strip() for s in symbols.split(",")]}
                    )
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        elif feature == "Analyst Ratings":
            symbol = st.text_input("Symbol", value="AAPL", key="ratings_symbol")
            if st.button("Get Analyst Ratings", key="get_ratings"):
                try:
                    client = get_go_api_client()
                    response = client.get(f"api/v1/stock/{symbol}/analyst-ratings")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        elif feature == "Market Overview":
            if st.button("Get Market Overview", key="get_overview"):
                try:
                    client = get_go_api_client()
                    response = client.get("api/v1/market/overview")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        
        elif feature == "Market Trends":
            if st.button("Get Market Trends", key="get_trends"):
                try:
                    client = get_go_api_client()
                    response = client.get("api/v1/market/trends")
                    st.json(response)
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    # Workflow Engine Lifecycle Section
    elif test_section == "🔄 Workflow Engine Lifecycle":
        # Import and use the workflow testbed
        # Root cause fix: testbed_workflow.py is in the same directory as testbed.py
        # In Docker: /app/testbed_workflow.py
        # Locally: streamlit-app/testbed_workflow.py (same dir as testbed.py)
        try:
            from pathlib import Path
            import importlib.util
            
            # Get the directory where testbed.py is located
            # __file__ is always available when this module is loaded
            testbed_dir = Path(__file__).parent
            workflow_testbed_path = testbed_dir / "testbed_workflow.py"
            
            if workflow_testbed_path.exists():
                spec = importlib.util.spec_from_file_location(
                    "testbed_workflow", str(workflow_testbed_path)
                )
                if spec and spec.loader:
                    workflow_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(workflow_module)
                    if hasattr(workflow_module, 'main'):
                        workflow_module.main()
                    else:
                        st.error("❌ Workflow testbed module loaded but 'main' function not found")
                else:
                    st.error("❌ Failed to create module spec for workflow testbed")
            else:
                st.error("❌ Workflow testbed file not found")
                st.info(f"Expected path: {workflow_testbed_path}")
                st.info(f"Testbed directory: {testbed_dir}")
                st.info(f"Files in directory: {list(testbed_dir.glob('*.py'))}")
        except Exception as e:
            st.error(f"❌ Failed to load workflow testbed: {e}")
            st.exception(e)
    
    # End-to-End Workflows Section
    elif test_section == "🔄 End-to-End Workflows":
        st.header("End-to-End Workflow Testing")
        
        workflow = st.selectbox(
            "Select Workflow",
            [
                "Complete Stock Analysis",
                "Portfolio Setup & Analysis",
                "Watchlist to Portfolio",
                "Swing Trade Execution",
                "Blog Generation Workflow"
            ]
        )
        
        if workflow == "Complete Stock Analysis":
            st.subheader("Complete Stock Analysis Workflow")
            symbol = st.text_input("Symbol", value="AAPL", key="e2e_symbol")
            
            if st.button("Run Complete Analysis", key="run_complete_analysis"):
                steps = [
                    ("1. Fetch Historical Data", lambda: test_data_source(symbol, "price_historical")),
                    ("2. Calculate Indicators", lambda: test_calculation(symbol, "indicators")),
                    ("3. Generate Signal", lambda: test_strategy(symbol, "technical")),
                    ("4. Get Fundamentals", lambda: test_data_source(symbol, "fundamentals")),
                    ("5. Get News", lambda: test_data_source(symbol, "news"))
                ]
                
                results = []
                for step_name, step_func in steps:
                    with st.spinner(step_name):
                        result = step_func()
                        results.append((step_name, result))
                
                st.subheader("Workflow Results")
                for step_name, result in results:
                    status_icon = "✅" if result["success"] else "❌"
                    st.markdown(f"{status_icon} **{step_name}**: {result['message']}")
        
        elif workflow == "Portfolio Setup & Analysis":
            st.subheader("Portfolio Setup & Analysis Workflow")
            user_id = st.text_input("User ID", value="user1", key="e2e_portfolio_user")
            portfolio_name = st.text_input("Portfolio Name", value="Test Portfolio", key="e2e_portfolio_name")
            symbols = st.text_input("Symbols (comma-separated)", value="AAPL,GOOGL,NVDA", key="e2e_portfolio_symbols")
            
            if st.button("Run Portfolio Workflow", key="run_portfolio_workflow"):
                st.info("This workflow would: 1) Create portfolio, 2) Add holdings, 3) Calculate metrics, 4) Generate analysis")
                # Implementation would go here
        
        elif workflow == "Watchlist to Portfolio":
            st.subheader("Watchlist to Portfolio Workflow")
            st.info("This workflow would: 1) Create watchlist, 2) Add stocks, 3) Move stock to portfolio")
            # Implementation would go here
        
        elif workflow == "Swing Trade Execution":
            st.subheader("Swing Trade Execution Workflow")
            st.info("This workflow would: 1) Generate swing signal, 2) Check risk limits, 3) Execute trade, 4) Track performance")
            # Implementation would go here
        
        elif workflow == "Blog Generation Workflow":
            st.subheader("Blog Generation Workflow")
            st.info("This workflow would: 1) Rank topics, 2) Build context, 3) Generate blog, 4) Save draft")
            # Implementation would go here


if __name__ == "__main__":
    main()

