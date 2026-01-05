"""
Shared functions for Streamlit pages
Extracted from main app.py for reuse across pages
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

from api_client import (
    get_go_api_client,
    APIError,
    APIConnectionError,
    APIResponseError
)

logger = logging.getLogger(__name__)


def get_stock_data(symbol: str, subscription_level: str = "basic"):
    """Fetch stock data from API"""
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching stock data for {symbol} (subscription: {subscription_level})")
    
    try:
        client = get_go_api_client()
        return client.get(
            f"api/v1/stock/{symbol}",
            params={"subscription_level": subscription_level}
        )
    except APIError as e:
        logger.error(f"Failed to fetch stock data for {symbol}: {e}")
        raise


def generate_stock_report(symbol: str, user_id: str = "streamlit"):
    """Trigger report generation via Go API (which queues python-worker work).

    Streamlit must only talk to Go API.
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")

    logger.info(f"Triggering stock report generation for {symbol}")
    client = get_go_api_client()
    return client.post(f"api/v1/report/{symbol}/generate", json_data={"user_id": user_id})


def get_portfolio_data(user_id: str, portfolio_id: str, subscription_level: str = "basic"):
    """Fetch portfolio data from API"""
    if not user_id or not portfolio_id:
        raise ValueError("user_id and portfolio_id cannot be empty")
    
    logger.info(f"Fetching portfolio {portfolio_id} for user {user_id}")
    
    try:
        client = get_go_api_client()
        data = client.get(
            f"api/v1/portfolio/{user_id}/{portfolio_id}",
            params={"subscription_level": subscription_level}
        )
        
        # Ensure holdings and signals are always lists
        if data:
            data['holdings'] = data.get('holdings') or []
            data['signals'] = data.get('signals') or []
        
        return data
    except APIError as e:
        logger.error(f"Failed to fetch portfolio {portfolio_id} for user {user_id}: {e}")
        raise


def get_signal(symbol: str, subscription_level: str = "basic"):
    """Fetch trading signal"""
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching signal for {symbol}")
    
    try:
        client = get_go_api_client()
        return client.get(
            f"api/v1/signal/{symbol}",
            params={"subscription_level": subscription_level}
        )
    except APIError as e:
        logger.error(f"Failed to fetch signal for {symbol}: {e}")
        raise


def get_llm_blog(symbol: str):
    """Fetch LLM-generated blog/report"""
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching LLM blog for {symbol}")
    
    try:
        client = get_go_api_client()
        return client.get(f"api/v1/llm_blog/{symbol}", timeout=60)
    except APIResponseError as e:
        if e.status_code == 404:
            logger.info(f"LLM blog not found for {symbol} (404)")
            return None
        logger.error(f"Failed to fetch LLM blog for {symbol}: {e}")
        raise
    except APIError as e:
        logger.error(f"Failed to fetch LLM blog for {symbol}: {e}")
        raise


def get_stock_report(symbol: str):
    """Fetch TipRanks-style stock report"""
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching stock report for {symbol}")
    
    try:
        client = get_go_api_client()
        return client.get(f"api/v1/report/{symbol}", timeout=60)
    except APIResponseError as e:
        if e.status_code == 404:
            logger.info(f"Stock report not found for {symbol} (404)")
            return None
        logger.error(f"Failed to fetch stock report for {symbol}: {e}")
        raise
    except APIError as e:
        logger.error(f"Failed to fetch stock report for {symbol}: {e}")
        raise


def fetch_historical_data(symbol: str, period: str = "1y", calculate_indicators: bool = True):
    """Fetch historical data on-demand via Go API"""
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching historical data for {symbol} via Go API (period: {period}, indicators: {calculate_indicators})")

    data_types = ["price_historical", "fundamentals"]
    if calculate_indicators:
        data_types.append("indicators")

    resp = refresh_data(symbol=symbol, data_types=data_types, force=True)

    # Shape expected by existing pages
    success = bool(resp.get("success"))
    message = resp.get("message") or ("Data fetched successfully" if success else "Data fetch failed")
    return {
        "success": success,
        "symbol": symbol,
        "message": message,
        "period": period,
        "results": resp.get("results"),
        "raw": resp,
    }


def display_fetch_results(fetch_response):
    """Display detailed fetch results with validation info (reusable function)"""
    if not fetch_response:
        return
    
    st.markdown("---")
    st.subheader("📊 Data Fetch Details")
    
    results = fetch_response.get('results', {}) or {}
    summary = fetch_response.get('summary')

    # Go-admin refresh proxy returns {success, message, results} without summary.
    if not isinstance(summary, dict):
        total_requested = len(results)
        total_successful = 0
        total_failed = 0
        total_skipped = 0

        for _, r in results.items():
            if not isinstance(r, dict):
                continue
            status = (r.get('status') or '').lower()
            if status in {"success", "completed"}:
                total_successful += 1
            elif status in {"failed", "error"}:
                total_failed += 1
            elif status in {"skipped"}:
                total_skipped += 1

        summary = {
            "total_requested": total_requested,
            "total_successful": total_successful,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
        }
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Requested", summary.get('total_requested', 0))
    with col2:
        st.metric("✅ Successful", summary.get('total_successful', 0))
    with col3:
        st.metric("❌ Failed", summary.get('total_failed', 0))
    with col4:
        st.metric("⏭️ Skipped", summary.get('total_skipped', 0))
    
    # Show overall message if available
    if fetch_response.get("message"):
        st.info(fetch_response.get("message"))

    overall_data_source = fetch_response.get('data_source')
    if overall_data_source:
        st.info(f"📊 **Data Source Used:** {overall_data_source}")
    
    # Detailed results for each data type
    for data_type, result in results.items():
        if result is None:
            continue
        
        status = result.get('status', 'unknown')
        status_icon = "✅" if status == "success" else "❌" if status == "failed" else "⚠️"
        
        # Get data source for this specific data type
        data_source = result.get('data_source', overall_data_source or 'N/A')
        
        with st.expander(f"{status_icon} {data_type.replace('_', ' ').title()}: {status.upper()}", expanded=(status != "success")):
            col_info1, col_info2 = st.columns(2)
            
            with col_info1:
                st.write(f"**Status:** {status}")
                st.write(f"**Message:** {result.get('message', 'N/A')}")
                st.write(f"**Data Source:** {data_source}")
            
            with col_info2:
                if result.get('rows_affected'):
                    st.write(f"**Rows Affected:** {result.get('rows_affected')}")
                if result.get('error'):
                    st.error(f"**Error:** {result.get('error')}")
            
            # Show validation report if available
            validation = result.get('validation')
            if validation:
                st.markdown("**🔍 Data Validation Report:**")
                val_status = validation.get('overall_status', 'unknown')
                val_color = "🟢" if val_status == "pass" else "🟡" if val_status == "warning" else "🔴"
                st.write(f"{val_color} **Overall Status:** {val_status.upper()}")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Rows", validation.get('total_rows', 0))
                with col2:
                    st.metric("Rows Dropped", validation.get('rows_dropped', 0))
                with col3:
                    st.metric("After Cleaning", validation.get('rows_after_cleaning', 0))
                
                if validation.get('critical_issues', 0) > 0:
                    st.error(f"🔴 **Critical Issues:** {validation.get('critical_issues', 0)}")
                if validation.get('warnings', 0) > 0:
                    st.warning(f"⚠️ **Warnings:** {validation.get('warnings', 0)}")
                
                # Show validation results
                val_results = validation.get('validation_results', [])
                if val_results:
                    with st.expander("📋 Detailed Validation Checks"):
                        for val_result in val_results:
                            check_name = val_result.get('check_name', 'Unknown')
                            passed = val_result.get('passed', False)
                            severity = val_result.get('severity', 'info')
                            
                            check_icon = "✅" if passed else "❌" if severity == "critical" else "⚠️"
                            st.write(f"{check_icon} **{check_name}:** {'PASSED' if passed else 'FAILED'}")
                            
                            if not passed:
                                issues = val_result.get('issues', [])
                                for issue in issues:
                                    st.write(f"   - {issue.get('message', 'N/A')}")
                                    if issue.get('recommendation'):
                                        st.info(f"   💡 {issue.get('recommendation')}")
                
                # Show recommendations
                recommendations = validation.get('recommendations', [])
                if recommendations:
                    st.info("**💡 Recommendations:**")
                    for rec in recommendations:
                        st.write(f"   - {rec}")


def refresh_data(symbol: str, data_types: list = None, force: bool = False):
    """Refresh data on-demand with detailed error tracking"""
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    if not data_types:
        data_types = ["price_historical", "fundamentals"]
    
    logger.info(f"Refreshing data for {symbol} via Go API admin proxy: {data_types} (force={force})")

    client = get_go_api_client()
    return client.post(
        "api/v1/admin/refresh",
        json_data={
            "symbols": [symbol],
            "data_types": data_types,
            "force": force,
        },
        timeout=120,
    )


def plot_stock_chart(data: dict):
    """Plot stock chart with indicators"""
    indicators = data.get("indicators", {})
    price_data = data.get("price_data", [])
    
    if not price_data:
        return go.Figure()
    
    # Convert to DataFrame
    df = pd.DataFrame(price_data)
    dates = pd.to_datetime(df['date']) if 'date' in df.columns else df.index
    
    # Create subplots
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=('Price & Moving Averages', 'RSI'),
        row_width=[0.7, 0.3]
    )
    
    # Plot price
    fig.add_trace(
        go.Scatter(x=dates, y=df['close'], name="Close Price", line=dict(color="blue")),
        row=1, col=1
    )
    
    # Plot moving averages
    if indicators.get("ema20"):
        fig.add_trace(
            go.Scatter(x=dates[-100:], y=[indicators["ema20"]] * 100,
                      name="EMA20", line=dict(color="orange", dash="dash")),
            row=1, col=1
        )
    
    if indicators.get("sma50"):
        fig.add_trace(
            go.Scatter(x=dates[-200:], y=[indicators["sma50"]] * 200,
                      name="SMA50", line=dict(color="green", dash="dash")),
            row=1, col=1
        )
    
    if indicators.get("sma200"):
        fig.add_trace(
            go.Scatter(x=dates[-200:], y=[indicators["sma200"]] * 200,
                      name="SMA200", line=dict(color="red", dash="dash")),
            row=1, col=1
        )
    
    # Plot RSI
    rsi_value = indicators.get("rsi", 50)
    fig.add_trace(
        go.Scatter(x=dates, y=[rsi_value] * 100, name="RSI",
                  line=dict(color="purple")),
        row=2, col=1
    )
    
    # Add RSI overbought/oversold lines
    fig.add_hline(y=70, line_dash="dash", line_color="red", 
                  annotation_text="Overbought", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green",
                  annotation_text="Oversold", row=2, col=1)
    
    fig.update_layout(
        height=600,
        title_text="Stock Analysis",
        showlegend=True
    )
    
    return fig


def get_fundamentals(symbol: str):
    """
    Fetch fundamental data from API
    
    Args:
        symbol: Stock symbol
    
    Returns:
        Fundamentals data dictionary
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching fundamentals for {symbol}")
    
    try:
        client = get_go_api_client()
        return client.get(f"api/v1/stock/{symbol}/fundamentals", timeout=30)
    except APIError as e:
        logger.error(f"Failed to fetch fundamentals for {symbol}: {e}")
        raise


def get_news(symbol: str):
    """
    Fetch news data from API
    
    Args:
        symbol: Stock symbol
    
    Returns:
        List of news articles
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching news for {symbol}")
    
    try:
        client = get_go_api_client()
        data = client.get(f"api/v1/stock/{symbol}/news", timeout=30)
        return data.get('news', [])
    except APIError as e:
        logger.error(f"Failed to fetch news for {symbol}: {e}")
        raise


def get_earnings(symbol: str):
    """
    Fetch earnings data from API
    
    Args:
        symbol: Stock symbol
    
    Returns:
        List of earnings records
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching earnings for {symbol}")
    
    try:
        client = get_go_api_client()
        data = client.get(f"api/v1/stock/{symbol}/earnings", timeout=30)
        return data.get('earnings', [])
    except APIError as e:
        logger.error(f"Failed to fetch earnings for {symbol}: {e}")
        raise


def get_industry_peers(symbol: str):
    """
    Fetch industry and peers data from API
    
    Args:
        symbol: Stock symbol
    
    Returns:
        Industry peers data dictionary
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching industry peers for {symbol}")
    
    try:
        client = get_go_api_client()
        return client.get(f"api/v1/stock/{symbol}/industry-peers", timeout=30)
    except APIError as e:
        logger.error(f"Failed to fetch industry peers for {symbol}: {e}")
        raise


def get_swing_signal(symbol: str, subscription_level: str = "basic"):
    """
    Get swing trading signal for a symbol
    
    Args:
        symbol: Stock symbol
        subscription_level: Subscription level
    
    Returns:
        Swing signal data dictionary
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching swing signal for {symbol}")

    client = get_go_api_client()
    return client.post(
        "api/v1/admin/swing/signal",
        json_data={
            "symbol": symbol,
            "strategy_name": "swing_trend",
            "user_id": "streamlit",
        },
        timeout=120,
    )


def display_validation_report(validation: Dict[str, Any], symbol: str):
    """
    Display detailed validation report in Streamlit (standalone function)
    
    Args:
        validation: Validation report dictionary
        symbol: Stock symbol
    """
    st.markdown(f"### 🔍 Validation Report for {symbol}")
    
    val_status = validation.get('overall_status', 'unknown')
    val_color = "🟢" if val_status == "pass" else "🟡" if val_status == "warning" else "🔴"
    st.write(f"{val_color} **Overall Status:** {val_status.upper()}")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Rows", validation.get('total_rows', 0))
    with col2:
        st.metric("Rows Dropped", validation.get('rows_dropped', 0))
    with col3:
        st.metric("After Cleaning", validation.get('rows_after_cleaning', 0))
    with col4:
        st.metric("Data Quality", f"{validation.get('data_quality_score', 0):.2f}" if validation.get('data_quality_score') else "N/A")
    
    if validation.get('critical_issues', 0) > 0:
        st.error(f"🔴 **Critical Issues:** {validation.get('critical_issues', 0)}")
    if validation.get('warnings', 0) > 0:
        st.warning(f"⚠️ **Warnings:** {validation.get('warnings', 0)}")
    
    # Show validation results
    val_results = validation.get('validation_results', [])
    if val_results:
        st.markdown("---")
        st.subheader("📋 Detailed Validation Checks")
        for val_result in val_results:
            check_name = val_result.get('check_name', 'Unknown')
            passed = val_result.get('passed', False)
            severity = val_result.get('severity', 'info')
            
            check_icon = "✅" if passed else "❌" if severity == "critical" else "⚠️"
            with st.expander(f"{check_icon} {check_name} ({severity.upper()})", expanded=(not passed)):
                st.write(f"**Passed:** {passed}")
                st.write(f"**Rows Checked:** {val_result.get('rows_checked', 0)}")
                st.write(f"**Rows Failed:** {val_result.get('rows_failed', 0)}")
                
                if not passed:
                    issues = val_result.get('issues', [])
                    if issues:
                        st.markdown("**Issues:**")
                        for issue in issues:
                            issue_severity = issue.get('severity', 'info')
                            issue_icon = "🔴" if issue_severity == "critical" else "🟡" if issue_severity == "warning" else "🔵"
                            st.write(f"{issue_icon} {issue.get('message', 'N/A')}")
                            if issue.get('recommendation'):
                                st.info(f"   💡 {issue.get('recommendation')}")
                
                if val_result.get('metrics'):
                    st.write(f"**Metrics:** {val_result.get('metrics')}")
    
    # Show recommendations
    recommendations = validation.get('recommendations', [])
    if recommendations:
        st.markdown("---")
        st.markdown("**💡 Recommendations:**")
        for rec in recommendations:
            st.info(f"  - {rec}")
