"""
Workflow Engine Lifecycle Testbed
Follows the complete data load workflow: Ingestion → Validation → Indicators → Signals → Screeners
Each step is a test case that can be run independently or as part of end-to-end flow
"""
import streamlit as st
import pandas as pd
import json
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

# Configure logging to ensure errors show up in logs
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),  # Log to stderr (visible in Docker logs)
        logging.FileHandler('testbed_workflow.log') if hasattr(sys, '_getframe') else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)

from api_client import (
    get_go_api_client,
    APIError,
    APIConnectionError,
    APIResponseError
)
from shared_functions import display_fetch_results, display_validation_report

# Page configuration
st.set_page_config(
    page_title="Workflow Engine Testbed",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Test symbols (using valid stock tickers)
TEST_SYMBOLS = ['NVDA', 'AAPL', 'ASTL', 'LCID', 'TSLA']

# Workflow stages
WORKFLOW_STAGES = [
    "📥 Stage 1: Data Ingestion",
    "✅ Stage 2: Validation & Audit",
    "📊 Stage 3: Indicator Calculation",
    "🎯 Stage 4: Signal Generation",
    "🔍 Stage 5: Stock Screening",
    "🔄 End-to-End Workflow",
    "📋 Workflow Audit History"
]


def run_data_ingestion(symbol: str) -> Dict[str, Any]:
    """Stage 1: Data Ingestion - Load raw price data"""
    try:
        go_client = get_go_api_client()
        response = go_client.post(
            "api/v1/admin/fetch-historical-data",
            json_data={
                "symbol": symbol.upper(),
                "period": "1y",
                "include_fundamentals": True,
                "calculate_indicators": False  # Calculate separately in Stage 3
            },
            timeout=180
        )
        return {"success": True, "data": response}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_validation_audit(symbol: str) -> Dict[str, Any]:
    """Stage 2: Validation & Audit - Check data quality and audit trail"""
    try:
        go_client = get_go_api_client()
        
        # Get audit history
        audit_response = go_client.get(
            f"api/v1/admin/data-fetch-audit/{symbol}",
            params={"limit": 10}
        )
        
        # Get validation reports
        validation_response = go_client.get(
            f"api/v1/admin/data-validation-reports/{symbol}",
            params={"data_type": "price_historical", "limit": 1}
        )
        
        # Get signal readiness
        readiness_response = go_client.get(
            f"api/v1/admin/signal-readiness/{symbol}",
            params={"signal_type": "swing_trend"}
        )
        
        return {
            "success": True,
            "audit": audit_response,
            "validation": validation_response,
            "readiness": readiness_response
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_indicator_calculation(symbol: str) -> Dict[str, Any]:
    """Stage 3: Indicator Calculation - Compute all technical indicators"""
    try:
        go_client = get_go_api_client()
        
        # Calculate indicators
        response = go_client.post(
            "api/v1/admin/refresh-data",
            json_data={
                "symbol": symbol.upper(),
                "data_types": ["indicators"],
                "force": True
            },
            timeout=120
        )
        
        # Get latest indicators via Go API (advanced-analysis endpoint is in Go API, not Python API)
        from api_client import get_go_api_client
        go_client = get_go_api_client()
        indicators_response = go_client.get(
            f"api/v1/stock/{symbol}/advanced-analysis",
            timeout=60
        )
        indicators = indicators_response.get('indicators', {}) if indicators_response else {}
        
        return {"success": True, "calculation": response, "indicators": indicators}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_signal_generation(symbol: str) -> Dict[str, Any]:
    """Stage 4: Signal Generation - Generate buy/sell/hold signals"""
    try:
        go_client = get_go_api_client()
        
        # Execute strategy
        response = go_client.post(
            "api/v1/admin/strategy/execute",
            json_data={
                "symbol": symbol.upper(),
                "strategy_name": "technical"
            },
            timeout=60
        )
        
        return {"success": True, "signal": response}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_stock_screening(criteria: Dict[str, Any]) -> Dict[str, Any]:
    """Stage 5: Stock Screening - Screen stocks based on criteria"""
    try:
        go_client = get_go_api_client()
        
        response = go_client.get(
            "api/v1/admin/screener/stocks",
            params=criteria,
            timeout=60
        )
        
        return {"success": True, "results": response}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_end_to_end_workflow(symbols: List[str]) -> Dict[str, Any]:
    """End-to-End Workflow - Run all stages for multiple symbols"""
    results = {}
    
    for symbol in symbols:
        st.info(f"🔄 Processing {symbol}...")
        symbol_results = {}
        
        # Stage 1: Data Ingestion
        with st.spinner(f"Stage 1: Ingesting data for {symbol}..."):
            ingestion_result = run_data_ingestion(symbol)
            symbol_results['ingestion'] = ingestion_result
        
        if not ingestion_result.get('success'):
            symbol_results['error'] = f"Failed at ingestion: {ingestion_result.get('error')}"
            results[symbol] = symbol_results
            continue
        
        # Stage 2: Validation & Audit
        with st.spinner(f"Stage 2: Validating data for {symbol}..."):
            validation_result = run_validation_audit(symbol)
            symbol_results['validation'] = validation_result
        
        # Stage 3: Indicator Calculation
        with st.spinner(f"Stage 3: Calculating indicators for {symbol}..."):
            indicator_result = run_indicator_calculation(symbol)
            symbol_results['indicators'] = indicator_result
        
        if not indicator_result.get('success'):
            symbol_results['error'] = f"Failed at indicators: {indicator_result.get('error')}"
            results[symbol] = symbol_results
            continue
        
        # Stage 4: Signal Generation
        with st.spinner(f"Stage 4: Generating signals for {symbol}..."):
            signal_result = run_signal_generation(symbol)
            symbol_results['signals'] = signal_result
        
        results[symbol] = symbol_results
    
    return results


def main():
    """Main testbed interface"""
    st.title("🔄 Workflow Engine Lifecycle Testbed")
    st.markdown("**Industry Standard: Complete Data Load Workflow Testing**")
    
    # Sidebar
    st.sidebar.title("Workflow Stages")
    selected_stage = st.sidebar.selectbox(
        "Select Workflow Stage",
        WORKFLOW_STAGES
    )
    
    # Stage selection
    if selected_stage == "📥 Stage 1: Data Ingestion":
        st.header("📥 Stage 1: Data Ingestion")
        st.markdown("**Load raw price data (OHLCV) for symbols**")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            symbol = st.selectbox("Symbol", TEST_SYMBOLS, key="ingestion_symbol")
            if st.button("🚀 Run Data Ingestion", type="primary", use_container_width=True):
                with st.spinner(f"Ingesting data for {symbol}..."):
                    result = run_data_ingestion(symbol)
                    st.session_state[f"ingestion_result_{symbol}"] = result
        
        with col2:
            if f"ingestion_result_{symbol}" in st.session_state:
                result = st.session_state[f"ingestion_result_{symbol}"]
                if result.get('success'):
                    st.success(f"✅ Data ingestion successful for {symbol}")
                    display_fetch_results(result['data'])
                else:
                    st.error(f"❌ Ingestion failed: {result.get('error')}")
    
    elif selected_stage == "✅ Stage 2: Validation & Audit":
        st.header("✅ Stage 2: Validation & Audit")
        st.markdown("**Check data quality, validation reports, and audit trail**")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            symbol = st.selectbox("Symbol", TEST_SYMBOLS, key="validation_symbol")
            if st.button("🔍 Run Validation & Audit", type="primary", use_container_width=True):
                with st.spinner(f"Validating data for {symbol}..."):
                    result = run_validation_audit(symbol)
                    st.session_state[f"validation_result_{symbol}"] = result
        
        with col2:
            if f"validation_result_{symbol}" in st.session_state:
                result = st.session_state[f"validation_result_{symbol}"]
                if result.get('success'):
                    # Audit History
                    st.subheader("📊 Audit History")
                    audit = result.get('audit', {})
                    if audit.get('audit_records'):
                        df_audit = pd.DataFrame(audit['audit_records'])
                        st.dataframe(df_audit, use_container_width=True)
                    
                    # Validation Report
                    st.subheader("🔍 Validation Report")
                    validation = result.get('validation', {})
                    if validation.get('reports'):
                        display_validation_report(validation['reports'][0], symbol)
                    
                    # Signal Readiness
                    st.subheader("✅ Signal Readiness")
                    readiness = result.get('readiness', {})
                    if readiness:
                        status = readiness.get('readiness_status', 'unknown')
                        status_color = {
                            "ready": "🟢",
                            "not_ready": "🔴",
                            "partial": "🟡"
                        }.get(status, "⚪")
                        st.markdown(f"**Status:** {status_color} {status.upper()}")
                        st.json(readiness)
                else:
                    st.error(f"❌ Validation failed: {result.get('error')}")
    
    elif selected_stage == "📊 Stage 3: Indicator Calculation":
        st.header("📊 Stage 3: Indicator Calculation")
        st.markdown("**Compute all technical indicators from price data**")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            symbol = st.selectbox("Symbol", TEST_SYMBOLS, key="indicator_symbol")
            if st.button("📊 Calculate Indicators", type="primary", use_container_width=True):
                with st.spinner(f"Calculating indicators for {symbol}..."):
                    result = run_indicator_calculation(symbol)
                    st.session_state[f"indicator_result_{symbol}"] = result
        
        with col2:
            if f"indicator_result_{symbol}" in st.session_state:
                result = st.session_state[f"indicator_result_{symbol}"]
                if result.get('success'):
                    st.success(f"✅ Indicators calculated for {symbol}")
                    
                    indicators = result.get('indicators', {})
                    if indicators:
                        st.subheader("📊 Calculated Indicators")
                        
                        # Moving Averages
                        st.markdown("**Moving Averages:**")
                        col_ma1, col_ma2, col_ma3 = st.columns(3)
                        with col_ma1:
                            st.metric("EMA9", f"${indicators.get('ema9', 0):.2f}" if indicators.get('ema9') else "N/A")
                            st.metric("EMA21", f"${indicators.get('ema21', 0):.2f}" if indicators.get('ema21') else "N/A")
                        with col_ma2:
                            st.metric("SMA50", f"${indicators.get('sma50', 0):.2f}" if indicators.get('sma50') else "N/A")
                            st.metric("SMA200", f"${indicators.get('sma200', 0):.2f}" if indicators.get('sma200') else "N/A")
                        with col_ma3:
                            st.metric("EMA20", f"${indicators.get('ema20', 0):.2f}" if indicators.get('ema20') else "N/A")
                            st.metric("EMA50", f"${indicators.get('ema50', 0):.2f}" if indicators.get('ema50') else "N/A")
                        
                        # Momentum Indicators
                        st.markdown("**Momentum Indicators:**")
                        col_mom1, col_mom2 = st.columns(2)
                        with col_mom1:
                            st.metric("RSI", f"{indicators.get('rsi', 0):.2f}" if indicators.get('rsi') else "N/A")
                            st.metric("MACD", f"{indicators.get('macd', 0):.4f}" if indicators.get('macd') else "N/A")
                        with col_mom2:
                            st.metric("MACD Signal", f"{indicators.get('macd_signal', 0):.4f}" if indicators.get('macd_signal') else "N/A")
                            st.metric("MACD Histogram", f"{indicators.get('macd_histogram', 0):.4f}" if indicators.get('macd_histogram') else "N/A")
                        
                        # Volatility
                        st.markdown("**Volatility:**")
                        st.metric("ATR", f"${indicators.get('atr', 0):.2f}" if indicators.get('atr') else "N/A")
                        
                        # Flags
                        st.markdown("**Industry Standard Flags:**")
                        flags = {
                            "Price > SMA200": indicators.get('price_above_sma200', False),
                            "EMA9 > EMA21": indicators.get('ema9_above_ema21', False),
                            "EMA20 > EMA50": indicators.get('ema20_above_ema50', False),
                            "SMA50 > SMA200": indicators.get('sma50_above_sma200', False),
                            "Volume > Average": indicators.get('volume_above_average', False),
                            "MACD > Signal": indicators.get('macd_above_signal', False)
                        }
                        for flag_name, flag_value in flags.items():
                            icon = "✅" if flag_value else "❌"
                            st.write(f"{icon} {flag_name}")
                        
                        # Full indicators JSON
                        with st.expander("📄 View Full Indicators"):
                            st.json(indicators)
                else:
                    st.error(f"❌ Indicator calculation failed: {result.get('error')}")
    
    elif selected_stage == "🎯 Stage 4: Signal Generation":
        st.header("🎯 Stage 4: Signal Generation")
        st.markdown("**Generate buy/sell/hold signals from indicators**")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            symbol = st.selectbox("Symbol", TEST_SYMBOLS, key="signal_symbol")
            if st.button("🎯 Generate Signal", type="primary", use_container_width=True):
                with st.spinner(f"Generating signal for {symbol}..."):
                    result = run_signal_generation(symbol)
                    st.session_state[f"signal_result_{symbol}"] = result
        
        with col2:
            if f"signal_result_{symbol}" in st.session_state:
                result = st.session_state[f"signal_result_{symbol}"]
                if result.get('success'):
                    signal_data = result.get('signal', {})
                    
                    signal = signal_data.get('signal', 'hold').upper()
                    confidence = signal_data.get('confidence', 0.0)
                    reason = signal_data.get('reason', 'No reason provided')
                    
                    # Signal display
                    signal_color = {
                        'BUY': '🟢',
                        'SELL': '🔴',
                        'HOLD': '🟡'
                    }.get(signal, '⚪')
                    
                    st.markdown(f"""
                        <div style="border: 2px solid #dee2e6; border-radius: 0.5rem; padding: 1rem;">
                            <h2>{signal_color} Signal: {signal}</h2>
                            <p><strong>Confidence:</strong> {confidence:.2%}</p>
                            <p><strong>Reason:</strong> {reason}</p>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Full signal JSON
                    with st.expander("📄 View Full Signal Data"):
                        st.json(signal_data)
                else:
                    st.error(f"❌ Signal generation failed: {result.get('error')}")
    
    elif selected_stage == "🔍 Stage 5: Stock Screening":
        st.header("🔍 Stage 5: Stock Screening")
        st.markdown("**Screen stocks based on technical and fundamental criteria**")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Screening Criteria")
            
            # Price vs MAs
            st.markdown("**Price vs Moving Averages:**")
            price_below_sma50 = st.checkbox("Price Below SMA50", key="screen_price_sma50")
            price_below_sma200 = st.checkbox("Price Below SMA200", key="screen_price_sma200")
            
            # Fundamentals
            st.markdown("**Fundamentals:**")
            has_good_fundamentals = st.checkbox("Good Fundamentals", key="screen_fundamentals")
            is_growth_stock = st.checkbox("Growth Stock", key="screen_growth")
            is_exponential_growth = st.checkbox("Exponential Growth", key="screen_exp_growth")
            
            # RSI
            st.markdown("**RSI Range:**")
            min_rsi = st.slider("Min RSI", 0, 100, 30, key="screen_min_rsi")
            max_rsi = st.slider("Max RSI", 0, 100, 70, key="screen_max_rsi")
            
            limit = st.number_input("Result Limit", min_value=10, max_value=200, value=50, key="screen_limit")
            
            if st.button("🔍 Run Screener", type="primary", use_container_width=True):
                criteria = {
                    "price_below_sma50": price_below_sma50 if price_below_sma50 else None,
                    "price_below_sma200": price_below_sma200 if price_below_sma200 else None,
                    "has_good_fundamentals": has_good_fundamentals if has_good_fundamentals else None,
                    "is_growth_stock": is_growth_stock if is_growth_stock else None,
                    "is_exponential_growth": is_exponential_growth if is_exponential_growth else None,
                    "min_rsi": min_rsi,
                    "max_rsi": max_rsi,
                    "limit": limit
                }
                # Remove None values
                criteria = {k: v for k, v in criteria.items() if v is not None}
                
                with st.spinner("Screening stocks..."):
                    result = run_stock_screening(criteria)
                    st.session_state["screener_result"] = result
        
        with col2:
            if "screener_result" in st.session_state:
                result = st.session_state["screener_result"]
                if result.get('success'):
                    results_data = result.get('results', {})
                    stocks = results_data.get('stocks', [])
                    
                    st.subheader(f"📊 Screening Results ({len(stocks)} stocks)")
                    
                    if stocks:
                        try:
                            # Normalize data: convert any pandas Series/DataFrame to native Python types
                            # This prevents "Mixing dicts with non-Series" error
                            normalized_stocks = []
                            for stock in stocks:
                                if not isinstance(stock, dict):
                                    continue
                                
                                normalized_stock = {}
                                for key, value in stock.items():
                                    # Convert pandas Series to list
                                    if isinstance(value, pd.Series):
                                        normalized_stock[key] = value.tolist()
                                    # Convert pandas DataFrame to dict
                                    elif isinstance(value, pd.DataFrame):
                                        normalized_stock[key] = value.to_dict('records')
                                    # Convert nested dicts that might contain Series
                                    elif isinstance(value, dict):
                                        normalized_stock[key] = {
                                            k: v.tolist() if isinstance(v, pd.Series) else v
                                            for k, v in value.items()
                                        }
                                    # Keep other types as-is (int, float, str, bool, None, list)
                                    else:
                                        normalized_stock[key] = value
                                normalized_stocks.append(normalized_stock)
                            
                            if not normalized_stocks:
                                st.warning("⚠️ No valid stock data to display")
                                return
                            
                            # Create DataFrame from normalized data
                            df = pd.DataFrame(normalized_stocks)
                            
                            # Flatten nested 'fundamentals' dict if present
                            if 'fundamentals' in df.columns and not df['fundamentals'].isna().all():
                                try:
                                    # Expand fundamentals into separate columns
                                    fundamentals_df = pd.json_normalize(df['fundamentals'])
                                    if not fundamentals_df.empty:
                                        # Drop the original fundamentals column and add expanded columns
                                        df = df.drop(columns=['fundamentals'])
                                        df = pd.concat([df, fundamentals_df], axis=1)
                                except Exception:
                                    # If normalization fails, keep fundamentals as-is
                                    pass
                            
                            st.dataframe(df, use_container_width=True)
                        except ValueError as e:
                            # Log the error properly - this will show in Streamlit logs
                            import traceback
                            error_msg = f"Error creating DataFrame from stocks data: {str(e)}"
                            logger.error(error_msg, exc_info=True)
                            # Also print to stderr for Docker logs
                            print(f"ERROR: {error_msg}", file=sys.stderr)
                            traceback.print_exc(file=sys.stderr)
                            
                            st.error(f"❌ {error_msg}")
                            st.exception(e)
                            
                            # Show raw data for debugging
                            with st.expander("🔍 Debug: Raw Stocks Data (First 3)"):
                                st.json(stocks[:3] if len(stocks) > 3 else stocks)
                        except Exception as e:
                            # Log any other errors
                            import traceback
                            error_msg = f"Unexpected error displaying screening results: {str(e)}"
                            logger.error(error_msg, exc_info=True)
                            # Also print to stderr for Docker logs
                            print(f"ERROR: {error_msg}", file=sys.stderr)
                            traceback.print_exc(file=sys.stderr)
                            
                            st.error(f"❌ {error_msg}")
                            st.exception(e)
                    else:
                        st.info("No stocks match the criteria")
                else:
                    st.error(f"❌ Screening failed: {result.get('error')}")
    
    elif selected_stage == "🔄 End-to-End Workflow":
        st.header("🔄 End-to-End Workflow Test")
        st.markdown("**Run complete workflow for all test symbols**")
        
        selected_symbols = st.multiselect(
            "Select Symbols",
            TEST_SYMBOLS,
            default=TEST_SYMBOLS,
            key="e2e_symbols"
        )
        
        if st.button("🚀 Run End-to-End Workflow", type="primary", use_container_width=True):
            with st.spinner("Running end-to-end workflow..."):
                results = run_end_to_end_workflow(selected_symbols)
                st.session_state["e2e_results"] = results
        
        if "e2e_results" in st.session_state:
            results = st.session_state["e2e_results"]
            
            st.subheader("📊 End-to-End Results")
            
            for symbol, symbol_results in results.items():
                with st.expander(f"📈 {symbol} - Complete Workflow", expanded=True):
                    # Stage 1: Ingestion
                    ingestion = symbol_results.get('ingestion', {})
                    if ingestion.get('success'):
                        st.success("✅ Stage 1: Data Ingestion - PASSED")
                    else:
                        st.error(f"❌ Stage 1: Data Ingestion - FAILED: {ingestion.get('error')}")
                    
                    # Stage 2: Validation
                    validation = symbol_results.get('validation', {})
                    if validation.get('success'):
                        st.success("✅ Stage 2: Validation & Audit - PASSED")
                    else:
                        st.warning(f"⚠️ Stage 2: Validation & Audit - FAILED: {validation.get('error')}")
                    
                    # Stage 3: Indicators
                    indicators = symbol_results.get('indicators', {})
                    if indicators.get('success'):
                        st.success("✅ Stage 3: Indicator Calculation - PASSED")
                    else:
                        st.error(f"❌ Stage 3: Indicator Calculation - FAILED: {indicators.get('error')}")
                    
                    # Stage 4: Signals
                    signals = symbol_results.get('signals', {})
                    if signals.get('success'):
                        signal_data = signals.get('signal', {})
                        signal = signal_data.get('signal', 'hold').upper()
                        confidence = signal_data.get('confidence', 0.0)
                        st.success(f"✅ Stage 4: Signal Generation - PASSED (Signal: {signal}, Confidence: {confidence:.2%})")
                    else:
                        st.error(f"❌ Stage 4: Signal Generation - FAILED: {signals.get('error')}")
                    
                    # Summary
                    if all([
                        ingestion.get('success'),
                        indicators.get('success'),
                        signals.get('success')
                    ]):
                        st.balloons()
                        st.success(f"🎉 {symbol}: Complete workflow PASSED!")
                    else:
                        st.error(f"❌ {symbol}: Workflow FAILED at one or more stages")
    
    elif selected_stage == "📋 Workflow Audit History":
        st.header("📋 Workflow Audit History")
        st.markdown("**View complete workflow execution audit trail**")
        
        go_client = get_go_api_client()
        
        # Get workflow executions
        try:
            executions_response = go_client.get(
                "api/v1/admin/workflow/executions",
                params={"limit": 20},
                timeout=30
            )
            executions = executions_response.get('executions', [])
            
            if executions:
                st.subheader("🔄 Recent Workflow Executions")
                
                # Display executions in a table
                df_executions = pd.DataFrame(executions)
                
                # Format timestamps
                if 'started_at' in df_executions.columns:
                    df_executions['started_at'] = pd.to_datetime(df_executions['started_at']).dt.strftime("%Y-%m-%d %H:%M:%S")
                if 'completed_at' in df_executions.columns:
                    df_executions['completed_at'] = pd.to_datetime(df_executions['completed_at']).dt.strftime("%Y-%m-%d %H:%M:%S")
                
                # Add status icon
                df_executions['status_icon'] = df_executions['status'].apply(
                    lambda x: "✅" if x == "completed" else "❌" if x == "failed" else "🔄"
                )
                
                # Select workflow to view details
                selected_workflow = st.selectbox(
                    "Select Workflow to View Details",
                    df_executions['workflow_id'].tolist(),
                    format_func=lambda x: f"{x[:8]}... ({df_executions[df_executions['workflow_id'] == x]['workflow_type'].iloc[0]})"
                )
                
                # Display execution summary
                st.dataframe(
                    df_executions[['status_icon', 'workflow_type', 'status', 'current_stage', 'started_at', 'completed_at']],
                    use_container_width=True,
                    hide_index=True
                )
                
                # Get workflow details
                if selected_workflow:
                    st.markdown("---")
                    st.subheader(f"📊 Workflow Details: {selected_workflow[:8]}...")
                    
                    try:
                        summary_response = python_client.get(
                            f"api/v1/workflow/executions/{selected_workflow}/summary",
                            timeout=30
                        )
                        
                        workflow = summary_response.get('workflow', {})
                        stages = summary_response.get('stages', [])
                        symbol_states = summary_response.get('symbol_states', [])
                        summary = summary_response.get('summary', {})
                        
                        # Parse workflow metadata for error details
                        workflow_metadata = workflow.get('metadata', {})
                        if isinstance(workflow_metadata, str):
                            import json
                            try:
                                workflow_metadata = json.loads(workflow_metadata)
                            except:
                                workflow_metadata = {}
                        
                        failed_stages = workflow_metadata.get('failed_stages', [])
                        stage_errors = workflow_metadata.get('stage_errors', {})
                        failed_data_types = workflow_metadata.get('failed_data_types', [])
                        
                        # Workflow Summary
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Total Stages", summary.get('total_stages', 0))
                        with col2:
                            st.metric("Stages Completed", summary.get('stages_completed', 0))
                        with col3:
                            st.metric("Symbols Succeeded", summary.get('symbols_succeeded', 0))
                        with col4:
                            st.metric("Symbols Failed", summary.get('symbols_failed', 0))
                        
                        # Show failure details prominently if workflow failed
                        if workflow.get('status') == 'failed':
                            st.markdown("---")
                            st.error("❌ **Workflow Failed**")
                            
                            # Show failed stages
                            if failed_stages:
                                st.markdown("**Failed Stages:**")
                                for stage in failed_stages:
                                    error_msg = stage_errors.get(stage, 'Unknown error')
                                    st.error(f"  - **{stage}**: {error_msg}")
                            
                            # Show failed data types
                            if failed_data_types:
                                st.markdown("**Failed Data Types:**")
                                for data_type in failed_data_types:
                                    st.warning(f"  - {data_type}")
                            
                            # Show general error if available
                            if workflow_metadata.get('error'):
                                st.error(f"**Error:** {workflow_metadata.get('error')}")
                            
                            # Re-run button
                            st.markdown("---")
                            st.markdown("**🔄 Re-run Options:**")
                            
                            col_rerun1, col_rerun2 = st.columns(2)
                            
                            with col_rerun1:
                                if st.button("🔄 Re-run Failed Stages", key=f"rerun_workflow_{selected_workflow}", use_container_width=True):
                                    # Extract symbol from workflow metadata
                                    symbols = workflow_metadata.get('symbols', [])
                                    if symbols:
                                        symbol = symbols[0] if symbols else None
                                        if symbol:
                                            with st.spinner(f"Re-running workflow for {symbol}..."):
                                                try:
                                                    # Re-run the fetch
                                                    rerun_response = python_client.post(
                                                        "api/v1/fetch-historical-data",
                                                        json_data={
                                                            "symbol": symbol,
                                                            "period": "1y",
                                                            "include_fundamentals": True,
                                                            "calculate_indicators": True
                                                        },
                                                        timeout=180
                                                    )
                                                    st.success(f"✅ Re-run initiated for {symbol}")
                                                    st.info("🔄 Refresh this page in a few seconds to see updated results.")
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"❌ Re-run failed: {e}")
                            
                            with col_rerun2:
                                # Re-run specific failed data types
                                if failed_data_types:
                                    selected_data_types = st.multiselect(
                                        "Select Data Types to Re-run",
                                        failed_data_types,
                                        default=failed_data_types,
                                        key=f"rerun_types_{selected_workflow}"
                                    )
                                    if st.button("🔄 Re-run Selected Data Types", key=f"rerun_types_btn_{selected_workflow}", use_container_width=True):
                                        symbols = workflow_metadata.get('symbols', [])
                                        if symbols:
                                            symbol = symbols[0] if symbols else None
                                            if symbol and selected_data_types:
                                                with st.spinner(f"Re-running {', '.join(selected_data_types)} for {symbol}..."):
                                                    try:
                                                        rerun_response = python_client.post(
                                                            "api/v1/refresh-data",
                                                            json_data={
                                                                "symbol": symbol,
                                                                "data_types": selected_data_types,
                                                                "force": True
                                                            },
                                                            timeout=120
                                                        )
                                                        st.success(f"✅ Re-run initiated for {', '.join(selected_data_types)}")
                                                        st.info("🔄 Refresh this page in a few seconds to see updated results.")
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"❌ Re-run failed: {e}")
                        
                        # Workflow Info (collapsible)
                        with st.expander("📄 View Full Workflow Information"):
                            st.json(workflow)
                        
                        # Stages
                        if stages:
                            st.subheader("📋 Stage Execution History")
                            df_stages = pd.DataFrame(stages)
                            
                            # Format timestamps
                            if 'started_at' in df_stages.columns:
                                df_stages['started_at'] = pd.to_datetime(df_stages['started_at']).dt.strftime("%Y-%m-%d %H:%M:%S")
                            if 'completed_at' in df_stages.columns:
                                df_stages['completed_at'] = pd.to_datetime(df_stages['completed_at']).dt.strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Add status icon
                            df_stages['status_icon'] = df_stages['status'].apply(
                                lambda x: "✅" if x == "completed" else "❌" if x == "failed" else "🔄"
                            )
                            
                            st.dataframe(
                                df_stages[['status_icon', 'stage_name', 'status', 'symbols_succeeded', 'symbols_failed', 'started_at', 'completed_at']],
                                use_container_width=True,
                                hide_index=True
                            )
                            
                            # Show detailed stage information with errors
                            for idx, stage in enumerate(stages):
                                if stage.get('status') == 'failed':
                                    with st.expander(f"❌ {stage.get('stage_name', 'Unknown')} - Failed", expanded=True):
                                        st.error(f"**Status:** {stage.get('status', 'unknown')}")
                                        st.write(f"**Started:** {stage.get('started_at', 'N/A')}")
                                        st.write(f"**Completed:** {stage.get('completed_at', 'N/A')}")
                                        st.write(f"**Symbols Succeeded:** {stage.get('symbols_succeeded', 0)}")
                                        st.write(f"**Symbols Failed:** {stage.get('symbols_failed', 0)}")
                                        
                                        # Show error from metadata if available
                                        stage_name = stage.get('stage_name')
                                        if stage_name and stage_errors.get(stage_name):
                                            st.error(f"**Error:** {stage_errors[stage_name]}")
                                        
                                        # Re-run button for this specific stage
                                        symbols = workflow_metadata.get('symbols', [])
                                        if symbols:
                                            symbol = symbols[0] if symbols else None
                                            if symbol:
                                                # Map stage name to data type
                                                stage_to_data_type = {
                                                    'ingestion': 'price_historical',
                                                    'indicators': 'indicators',
                                                    'fundamentals': 'fundamentals',
                                                    'earnings': 'earnings',
                                                    'industry_peers': 'industry_peers'
                                                }
                                                data_type = stage_to_data_type.get(stage_name)
                                                
                                                if data_type and st.button(f"🔄 Re-run {stage_name}", key=f"rerun_stage_{selected_workflow}_{idx}"):
                                                    with st.spinner(f"Re-running {stage_name} for {symbol}..."):
                                                        try:
                                                            rerun_response = python_client.post(
                                                                "api/v1/refresh-data",
                                                                json_data={
                                                                    "symbol": symbol,
                                                                    "data_types": [data_type],
                                                                    "force": True
                                                                },
                                                                timeout=120
                                                            )
                                                            st.success(f"✅ Re-run initiated for {stage_name}")
                                                            st.info("🔄 Refresh this page in a few seconds to see updated results.")
                                                            st.rerun()
                                                        except Exception as e:
                                                            st.error(f"❌ Re-run failed: {e}")
                        else:
                            st.info("📭 No stage execution records found. This workflow may have been created before stage tracking was implemented.")
                        
                        # Symbol States
                        if symbol_states:
                            st.subheader("📈 Symbol State History")
                            df_symbols = pd.DataFrame(symbol_states)
                            
                            # Format timestamps
                            if 'started_at' in df_symbols.columns:
                                df_symbols['started_at'] = pd.to_datetime(df_symbols['started_at']).dt.strftime("%Y-%m-%d %H:%M:%S")
                            if 'completed_at' in df_symbols.columns:
                                df_symbols['completed_at'] = pd.to_datetime(df_symbols['completed_at']).dt.strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Add status icon
                            df_symbols['status_icon'] = df_symbols['status'].apply(
                                lambda x: "✅" if x == "completed" else "❌" if x == "failed" else "🔄" if x == "running" else "⏸️"
                            )
                            
                            # Group by symbol
                            symbols_list = df_symbols['symbol'].unique()
                            for symbol in symbols_list:
                                symbol_data = df_symbols[df_symbols['symbol'] == symbol]
                                
                                # Count failed stages for this symbol
                                failed_stages_count = len(symbol_data[symbol_data['status'] == 'failed'])
                                
                                with st.expander(
                                    f"📊 {symbol} - {len(symbol_data)} stages" + (f" ({failed_stages_count} failed)" if failed_stages_count > 0 else ""),
                                    expanded=(failed_stages_count > 0)
                                ):
                                    st.dataframe(
                                        symbol_data[['status_icon', 'stage', 'status', 'error_message', 'retry_count', 'started_at', 'completed_at']],
                                        use_container_width=True,
                                        hide_index=True
                                    )
                                    
                                    # Show failed stages with error details
                                    failed_stages_data = symbol_data[symbol_data['status'] == 'failed']
                                    if not failed_stages_data.empty:
                                        st.markdown("---")
                                        st.error("**Failed Stages:**")
                                        for _, failed_stage in failed_stages_data.iterrows():
                                            stage_name = failed_stage.get('stage', 'Unknown')
                                            error_msg = failed_stage.get('error_message', 'No error message')
                                            st.error(f"  - **{stage_name}**: {error_msg}")
                                            
                                            # Re-run button for this specific stage
                                            stage_to_data_type = {
                                                'ingestion': 'price_historical',
                                                'indicators': 'indicators',
                                                'fundamentals': 'fundamentals',
                                                'earnings': 'earnings',
                                                'industry_peers': 'industry_peers'
                                            }
                                            data_type = stage_to_data_type.get(stage_name)
                                            
                                            if data_type and st.button(f"🔄 Re-run {stage_name}", key=f"rerun_symbol_stage_{selected_workflow}_{symbol}_{stage_name}"):
                                                with st.spinner(f"Re-running {stage_name} for {symbol}..."):
                                                    try:
                                                        rerun_response = python_client.post(
                                                            "api/v1/refresh-data",
                                                            json_data={
                                                                "symbol": symbol,
                                                                "data_types": [data_type],
                                                                "force": True
                                                            },
                                                            timeout=120
                                                        )
                                                        st.success(f"✅ Re-run initiated for {stage_name}")
                                                        st.info("🔄 Refresh this page in a few seconds to see updated results.")
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"❌ Re-run failed: {e}")
                        else:
                            st.info("📭 No symbol state records found. This workflow may have been created before symbol state tracking was implemented.")
                        
                    except Exception as e:
                        st.error(f"❌ Error fetching workflow details: {str(e)}")
            else:
                st.info("No workflow executions found. Run a workflow first to see audit history.")
                
        except Exception as e:
            st.error(f"❌ Error fetching workflow executions: {str(e)}")


if __name__ == "__main__":
    main()

