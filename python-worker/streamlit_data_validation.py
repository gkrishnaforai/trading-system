#!/usr/bin/env python3
"""
Streamlit Data Validation Dashboard
Validates candlestick data and swing trading features
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
import sys
import os

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_database
from app.services.data_aggregation_service import DataAggregationService
from app.services.market_overview_service import MarketOverviewService
from app.services.stock_insights_service import StockInsightsService
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import DataType, RefreshMode
from app.repositories.market_data_daily_repository import MarketDataDailyRepository
from app.repositories.indicators_repository import IndicatorsRepository
from app.observability.logging import get_logger

logger = get_logger("data_validation")

def clean_dataframe_for_streamlit(df):
    """
    Clean DataFrame to prevent Arrow serialization errors
    """
    if df.empty:
        return df
    
    # Make a copy to avoid modifying original
    df_clean = df.copy()
    
    # Replace all problematic string values
    string_replacements = ['N/A', 'NA', 'null', 'None', 'n/a', 'na', 'NULL', 'undefined', '']
    df_clean = df_clean.replace(string_replacements, None)
    
    # Convert object columns that should be numeric
    for col in df_clean.columns:
        if df_clean[col].dtype == 'object':
            # Try to convert to numeric if it looks like numeric data
            try:
                # Check if most non-null values are numeric-like
                non_null_series = df_clean[col].dropna()
                if len(non_null_series) > 0:
                    sample = non_null_series.head(10).astype(str)
                    if sample.str.match(r'^-?\d*\.?\d+$').all():
                        df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
            except:
                pass
    
    return df_clean

def format_confidence_score(confidence):
    """Format confidence score with color indicator"""
    if confidence >= 0.7:
        return f"🟢 {confidence:.2f}"
    elif confidence >= 0.4:
        return f"🟡 {confidence:.2f}"
    else:
        return f"🔴 {confidence:.2f}"

def format_signal(signal):
    """Format signal with emoji"""
    signal_lower = signal.lower()
    if "buy" in signal_lower:
        if "strong" in signal_lower:
            return "🚀 Strong Buy"
        return "📈 Buy"
    elif "sell" in signal_lower:
        if "strong" in signal_lower:
            return "📉 Strong Sell"
        return "🔻 Sell"
    else:
        return "➡️ Hold"

def display_analysis_section(section_name: str, section_data: Dict[str, Any]):
    """Display a single analysis section"""
    if not section_data:
        st.warning(f"No {section_name.replace('_', ' ').title()} data available")
        return
    
    score = section_data.get("score", 0)
    summary = section_data.get("summary", "No summary available")
    details = section_data.get("details", {})
    
    # Create columns for score and summary
    col1, col2 = st.columns([1, 3])
    
    with col1:
        # Score gauge
        score_color = "🟢" if score >= 7 else "🟡" if score >= 4 else "🔴"
        st.metric(f"{section_name.replace('_', ' ').title()} Score", f"{score:.1f}/10", delta=score_color)
    
    with col2:
        st.write("**Summary:**", summary)
    
    # Details expander
    if details:
        with st.expander(f"📊 {section_name.replace('_', ' ').title()} Details"):
            details_df = pd.DataFrame(list(details.items()), columns=["Metric", "Value"])
            st.dataframe(details_df, width='stretch')

def display_strategy_comparison(strategy_results: List[Dict[str, Any]]):
    """Display strategy comparison table"""
    if not strategy_results:
        st.warning("No strategy results available")
        return
    
    # Create comparison table
    comparison_data = []
    for strategy in strategy_results:
        comparison_data.append({
            "Strategy": strategy["name"],
            "Signal": format_signal(strategy["signal"]),
            "Confidence": format_confidence_score(strategy["confidence"]),
            "Reason": strategy["reason"][:100] + "..." if len(strategy["reason"]) > 100 else strategy["reason"]
        })
    
    df_comparison = pd.DataFrame(comparison_data)
    st.dataframe(df_comparison, width='stretch')
    
    # Detailed strategy results
    st.subheader("📋 Detailed Strategy Results")
    
    for i, strategy in enumerate(strategy_results):
        with st.expander(f"🔍 {strategy['name']} - {format_signal(strategy['signal'])}"):
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.write("**Signal:**", format_signal(strategy["signal"]))
                st.write("**Confidence:**", format_confidence_score(strategy["confidence"]))
                st.write("**Description:**", strategy["description"])
            
            with col2:
                st.write("**Reason:**", strategy["reason"])
                if strategy.get("metadata"):
                    st.write("**Metadata:**")
                    st.json(strategy["metadata"])

def display_stock_insights(symbol: str):
    """Display comprehensive stock insights"""
    st.header(f"📊 Stock Insights for {symbol}")
    
    insights_service = StockInsightsService()
    
    # Analysis options
    col1, col2 = st.columns(2)
    with col1:
        run_all_strategies = st.checkbox("Run All Strategies", value=True)
    with col2:
        generate_insights = st.button("🚀 Generate Insights", type="primary")
    
    # Get available strategies
    try:
        available_strategies = insights_service.get_available_strategies()
        strategy_names = list(available_strategies.keys())
        selected_strategy = st.selectbox(
            "Run Single Strategy",
            options=["None"] + strategy_names,
            help="Select a single strategy to run"
        )
        run_strategy = st.button("🎯 Run Selected Strategy")
    except Exception as e:
        st.error(f"Error loading strategies: {e}")
        available_strategies = {}
        strategy_names = []
        selected_strategy = "None"
        run_strategy = False
    
    if generate_insights or run_strategy:
        if not symbol:
            st.error("Please enter a stock symbol")
            return
        
        with st.spinner(f"Analyzing {symbol}..."):
            try:
                if generate_insights:
                    # Generate comprehensive insights
                    insights = insights_service.get_stock_insights(
                        symbol=symbol,
                        run_all_strategies=run_all_strategies
                    )
                    
                    st.success(f"✅ Analysis completed for {symbol}")
                    
                    # Overall recommendation
                    st.subheader("🎯 Overall Recommendation")
                    recommendation = insights["overall_recommendation"]
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Signal", format_signal(recommendation["signal"]))
                    with col2:
                        st.metric("Confidence", recommendation["confidence"])
                    with col3:
                        st.metric("Score", f"{recommendation['weighted_score']:.1f}/10")
                    
                    st.write("**Rationale:**", recommendation["rationale"])
                    
                    # Analysis sections
                    st.subheader("📈 Analysis Sections")
                    analysis_sections = insights["analysis_sections"]
                    
                    # Create tabs for each section
                    tab_names = ["Technical Momentum", "Financial Strength", "Valuation", "Trend Strength"]
                    tabs = st.tabs(tab_names)
                    
                    sections_order = ["technical_momentum", "financial_strength", "valuation", "trend_strength"]
                    for i, section_key in enumerate(sections_order):
                        with tabs[i]:
                            display_analysis_section(section_key, analysis_sections.get(section_key))
                    
                    # Strategy comparison
                    if run_all_strategies and insights.get("strategy_comparison"):
                        st.subheader("⚖️ Strategy Comparison")
                        display_strategy_comparison(insights["strategy_comparison"])
                
                elif run_strategy and selected_strategy != "None":
                    # Run single strategy
                    result = insights_service.run_single_strategy(symbol, selected_strategy)
                    
                    st.success(f"✅ Strategy {selected_strategy} executed for {symbol}")
                    
                    # Display single strategy result
                    strategy_data = result["strategy"]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Signal", format_signal(strategy_data["signal"]))
                        st.metric("Confidence", format_confidence_score(strategy_data["confidence"]))
                    
                    with col2:
                        st.write("**Strategy:**", strategy_data["name"])
                        st.write("**Description:**", strategy_data["description"])
                    
                    st.write("**Reason:**", strategy_data["reason"])
                    
                    if strategy_data.get("metadata"):
                        with st.expander("📊 Strategy Metadata"):
                            st.json(strategy_data["metadata"])
                
            except Exception as e:
                st.error(f"❌ Error analyzing {symbol}: {str(e)}")
                logger.error(f"Error in stock insights for {symbol}: {e}")
    else:
        # Display available strategies
        if available_strategies:
            st.info("👆 Click 'Generate Insights' to begin comprehensive analysis")
            
            st.subheader("🎯 Available Strategies")
            
            strategy_info = []
            for name, description in available_strategies.items():
                strategy_info.append({"Strategy": name, "Description": description})
            
            df_strategies = pd.DataFrame(strategy_info)
            st.dataframe(df_strategies, width='stretch')

# Initialize database
init_database()

# Page config
st.set_page_config(
    page_title="Trading System Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Trading System Dashboard")
st.markdown("Data validation and comprehensive stock analysis with strategy insights")

# Sidebar
st.sidebar.header("Dashboard Controls")

# Symbol selection
symbol = st.sidebar.selectbox(
    "Select Symbol",
    ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMZN", "META", "SPY", "QQQ", "IWM"],
    help="Choose symbol to analyze"
)

# Date range
days_back = st.sidebar.slider(
    "Days to Analyze",
    min_value=30,
    max_value=365,
    value=90,
    help="Number of days of historical data to analyze"
)

# Create main tabs
tab1, tab2 = st.tabs(["🔍 Data Validation", "📊 Stock Insights"])

with tab1:
    st.header("🔍 Data Validation")
    st.markdown("Validate candlestick data quality and swing trading features")
    
    # Data Loading Section
    st.sidebar.subheader("📥 Data Loading")
    load_data = st.sidebar.button("Load Market Data", help="Load historical market data for selected symbol")
    load_indicators = st.sidebar.button("Load Indicators", help="Calculate technical indicators for selected symbol")

    if load_data:
        with st.spinner(f"Loading {days_back} days of data for {symbol}..."):
            try:
                refresh_manager = DataRefreshManager()
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL],
                    mode=RefreshMode.ON_DEMAND,
                    force=True,
                )

                if result.total_failed == 0:
                    st.success(
                        f"✅ Loaded market data for {symbol} (success={result.total_successful}, skipped={result.total_skipped})"
                    )
                    # Clear cache to force reload
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"❌ Failed to load market data for {symbol}. See details below.")
                    st.json(result.to_dict())
            except Exception as e:
                st.error(f"❌ Error loading market data: {e}")
                logger.error(f"Error loading market data for {symbol}: {e}")

    if load_indicators:
        with st.spinner(f"Calculating indicators for {symbol}..."):
            try:
                refresh_manager = DataRefreshManager()
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.INDICATORS],
                    mode=RefreshMode.ON_DEMAND,
                    force=True,
                )

                if result.total_failed == 0:
                    st.success(
                        f"✅ Calculated indicators for {symbol} (success={result.total_successful}, skipped={result.total_skipped})"
                    )
                    # Clear cache to force reload
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"❌ Failed to calculate indicators for {symbol}. See details below.")
                    st.json(result.to_dict())
            except Exception as e:
                st.error(f"❌ Error calculating indicators: {e}")
                logger.error(f"Error calculating indicators for {symbol}: {e}")

    # Data loading and validation logic (rest of the original data validation code)
    # ... [include all the existing data validation logic here] ...

with tab2:
    display_stock_insights(symbol)

# Footer
st.markdown("---")
st.markdown("📊 Trading System Dashboard | Data Validation & Stock Insights")

if load_data:
    with st.spinner(f"Loading {days_back} days of data for {symbol}..."):
        try:
            refresh_manager = DataRefreshManager()
            result = refresh_manager.refresh_data(
                symbol=symbol,
                data_types=[DataType.PRICE_HISTORICAL],
                mode=RefreshMode.ON_DEMAND,
                force=True,
            )

            if result.total_failed == 0:
                st.success(
                    f"✅ Loaded market data for {symbol} (success={result.total_successful}, skipped={result.total_skipped})"
                )
                # Clear cache to force reload
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"❌ Failed to load market data for {symbol}. See details below.")
                st.json(result.to_dict())
        except Exception as e:
            st.error(f"❌ Error loading data: {e}")

if load_indicators:
    with st.spinner(f"Calculating indicators for {symbol}..."):
        try:
            refresh_manager = DataRefreshManager()
            result = refresh_manager.refresh_data(
                symbol=symbol,
                data_types=[DataType.INDICATORS],
                mode=RefreshMode.ON_DEMAND,
                force=True,
            )

            if result.total_failed == 0:
                st.success(
                    f"✅ Calculated indicators for {symbol} (success={result.total_successful}, skipped={result.total_skipped})"
                )
                # Clear cache to force reload
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"❌ Failed to calculate indicators for {symbol}. See details below.")
                st.json(result.to_dict())
        except Exception as e:
            st.error(f"❌ Error calculating indicators: {e}")

# Validation sections
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Candlestick Data", 
    "📈 Technical Indicators", 
    "🔄 Data Quality",
    "📊 Swing Trading Features",
    "📋 Summary Report"
])

# Initialize services
@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_data(symbol: str, days: int):
    """Load market data and indicators"""
    try:
        service = DataAggregationService()
        market_data = service.get_daily_data(symbol, days=days)
        indicators = service.get_indicators_data(symbol, days=days)
        
        return {
            "market_data": market_data,
            "indicators": indicators,
            "success": True
        }
    except Exception as e:
        logger.error(f"Error loading data for {symbol}: {e}")
        return {
            "market_data": [],
            "indicators": [],
            "success": False,
            "error": str(e)
        }

# Load data
data_result = load_data(symbol, days_back)

if not data_result["success"]:
    st.error(f"❌ Failed to load data: {data_result['error']}")
    st.stop()

market_data = data_result["market_data"]
indicators = data_result["indicators"]

# Convert to DataFrames for easier analysis
if market_data:
    df_market = pd.DataFrame(market_data)
    # Handle both 'date' and 'trade_date' column names
    date_col = 'date' if 'date' in df_market.columns else 'trade_date'
    df_market[date_col] = pd.to_datetime(df_market[date_col])
    if date_col != 'trade_date':
        df_market = df_market.rename(columns={date_col: 'trade_date'})
        date_col = 'trade_date'
    df_market = df_market.sort_values(date_col)

    # Some repository/service paths may not include stock_symbol in each row.
    # Ensure it exists so downstream merges and displays don't crash.
    if 'stock_symbol' not in df_market.columns:
        df_market['stock_symbol'] = symbol
    
    # Replace ALL string placeholders with None for proper data types
    string_replacements = ['N/A', 'NA', 'null', 'None', 'n/a', 'na', 'NULL', 'undefined', '']
    df_market = df_market.replace(string_replacements, None)
    
    # Convert ALL possible numeric columns properly
    for col in df_market.columns:
        if col not in [date_col, 'stock_symbol']:  # Skip date and symbol columns
            try:
                df_market[col] = pd.to_numeric(df_market[col], errors='coerce')
            except:
                # If conversion fails, keep as is but ensure no problematic strings
                df_market[col] = df_market[col].astype(str).replace(string_replacements, None)
else:
    df_market = pd.DataFrame()

if indicators:
    df_indicators = pd.DataFrame(indicators)
    # Handle both 'date' and 'trade_date' column names
    date_col = 'date' if 'date' in df_indicators.columns else 'trade_date'
    df_indicators[date_col] = pd.to_datetime(df_indicators[date_col])
    if date_col != 'trade_date':
        df_indicators = df_indicators.rename(columns={date_col: 'trade_date'})
        date_col = 'trade_date'
    df_indicators = df_indicators.sort_values(date_col)

    # Ensure stock_symbol exists for downstream merges
    if 'stock_symbol' not in df_indicators.columns:
        df_indicators['stock_symbol'] = symbol
    
    # Replace ALL string placeholders with None for proper data types
    string_replacements = ['N/A', 'NA', 'null', 'None', 'n/a', 'na', 'NULL', 'undefined', '']
    df_indicators = df_indicators.replace(string_replacements, None)
    
    # Convert ALL possible numeric columns properly
    for col in df_indicators.columns:
        if col not in [date_col, 'stock_symbol']:  # Skip date and symbol columns
            try:
                df_indicators[col] = pd.to_numeric(df_indicators[col], errors='coerce')
            except:
                # If conversion fails, keep as is but ensure no problematic strings
                df_indicators[col] = df_indicators[col].astype(str).replace(string_replacements, None)
else:
    df_indicators = pd.DataFrame()

# Tab 1: Candlestick Data Validation
with tab1:
    st.header("📊 Candlestick Data Validation")
    
    if df_market.empty:
        st.warning("⚠️ No market data available")
    else:
        # Basic stats
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Records", len(df_market))
        with col2:
            date_col = 'date' if 'date' in df_market.columns else 'trade_date'
            st.metric("Date Range", f"{df_market[date_col].min().date()} to {df_market[date_col].max().date()}")
        with col3:
            st.metric("Missing OHLC", df_market[['open', 'high', 'low', 'close']].isnull().any().any())
        with col4:
            st.metric("Zero Volume", (df_market['volume'] == 0).sum())
        
        # Data quality checks
        st.subheader("Data Quality Checks")
        
        quality_issues = []
        
        # Check for missing data
        missing_data = df_market.isnull().sum()
        if missing_data.any():
            quality_issues.append(f"Missing data: {missing_data[missing_data > 0].to_dict()}")
        
        # Check for negative prices
        negative_prices = (df_market[['open', 'high', 'low', 'close']] < 0).any().any()
        if negative_prices:
            quality_issues.append("Negative prices detected")
        
        # Check for invalid OHLC relationships
        invalid_ohlc = ((df_market['high'] < df_market['low']) | 
                       (df_market['high'] < df_market['open']) | 
                       (df_market['high'] < df_market['close']) |
                       (df_market['low'] > df_market['open']) | 
                       (df_market['low'] > df_market['close'])).sum()
        if invalid_ohlc > 0:
            quality_issues.append(f"Invalid OHLC relationships: {invalid_ohlc} records")
        
        # Check for gaps in data
        expected_days = len(pd.date_range(start=df_market[date_col].min(), 
                                        end=df_market[date_col].max(), 
                                        freq='B'))  # Business days
        actual_days = len(df_market)
        gap_ratio = (expected_days - actual_days) / expected_days if expected_days > 0 else 0
        
        if gap_ratio > 0.1:  # More than 10% missing days
            quality_issues.append(f"Data gaps: {gap_ratio:.1%} missing trading days")
        
        if quality_issues:
            st.error("🚨 Data Quality Issues Found:")
            for issue in quality_issues:
                st.write(f"• {issue}")
        else:
            st.success("✅ All candlestick data quality checks passed!")
        
        # Sample data display
        st.subheader("Sample Data (Last 10 Records)")
        sample_df = clean_dataframe_for_streamlit(df_market.tail(10)[[date_col, 'open', 'high', 'low', 'close', 'volume']])
        st.dataframe(sample_df)
        
        # Price chart
        st.subheader("Price Chart")
        chart_df = clean_dataframe_for_streamlit(df_market[[date_col, 'open', 'high', 'low', 'close']].set_index(date_col))
        st.line_chart(chart_df)

# Tab 2: Technical Indicators Validation
with tab2:
    st.header("📈 Technical Indicators Validation")
    
    if df_indicators.empty:
        st.warning("⚠️ No indicators data available")
    else:
        # Basic stats
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Indicator Records", len(df_indicators))
        with col2:
            available_indicators = [col for col in df_indicators.columns 
                                 if col not in ['stock_symbol', 'trade_date', 'created_at', 'updated_at']]
            st.metric("Available Indicators", len(available_indicators))
        with col3:
            st.metric("Date Match", len(df_market) == len(df_indicators))
        
        # Check indicator calculations
        st.subheader("Indicator Validation")
        
        indicator_issues = []
        
        # Check for null values in key indicators
        key_indicators = ['sma_50', 'sma_200', 'ema_20', 'rsi_14', 'macd']
        for indicator in key_indicators:
            if indicator in df_indicators.columns:
                null_count = df_indicators[indicator].isnull().sum()
                if null_count > 0:
                    indicator_issues.append(f"{indicator}: {null_count} null values")
        
        # Check RSI range
        if 'rsi_14' in df_indicators.columns:
            rsi_invalid = ((df_indicators['rsi_14'] < 0) | (df_indicators['rsi_14'] > 100)).sum()
            if rsi_invalid > 0:
                indicator_issues.append(f"RSI out of range: {rsi_invalid} records")
        
        # Check SMA relationships
        if 'sma_50' in df_indicators.columns and 'sma_200' in df_indicators.columns:
            # SMA 50 should be more volatile than SMA 200
            sma50_vol = df_indicators['sma_50'].std()
            sma200_vol = df_indicators['sma_200'].std()
            if sma50_vol < sma200_vol:
                indicator_issues.append("SMA 50 less volatile than SMA 200 (possible calculation error)")
        
        if indicator_issues:
            st.error("🚨 Indicator Issues Found:")
            for issue in indicator_issues:
                st.write(f"• {issue}")
        else:
            st.success("✅ All indicator validations passed!")
        
        # Sample indicators
        st.subheader("Sample Indicators (Last 10 Records)")
        ind_date_col = 'date' if 'date' in df_indicators.columns else 'trade_date'
        display_cols = [ind_date_col] + [col for col in available_indicators if col in df_indicators.columns][:6]
        sample_indicators = clean_dataframe_for_streamlit(df_indicators.tail(10)[display_cols])
        st.dataframe(sample_indicators)

# Tab 3: Data Quality Metrics
with tab3:
    st.header("🔄 Data Quality Metrics")
    
    if df_market.empty:
        st.warning("⚠️ No data to analyze")
    else:
        # Comprehensive quality metrics
        st.subheader("Data Completeness")
        
        # Missing data analysis
        missing_analysis = df_market.isnull().sum() / len(df_market) * 100
        missing_df = pd.DataFrame({
            'Column': missing_analysis.index,
            'Missing %': missing_analysis.values
        })
        st.bar_chart(missing_df.set_index('Column'))
        
        # Data consistency
        st.subheader("Data Consistency")
        
        consistency_checks = {
            "High >= Low": (df_market['high'] >= df_market['low']).all(),
            "High >= Open": (df_market['high'] >= df_market['open']).all(),
            "High >= Close": (df_market['high'] >= df_market['close']).all(),
            "Low <= Open": (df_market['low'] <= df_market['open']).all(),
            "Low <= Close": (df_market['low'] <= df_market['close']).all(),
            "Volume >= 0": (df_market['volume'] >= 0).all(),
            "Prices > 0": (df_market[['open', 'high', 'low', 'close']] > 0).all().all()
        }
        
        for check, passed in consistency_checks.items():
            if passed:
                st.success(f"✅ {check}")
            else:
                st.error(f"❌ {check}")
        
        # Statistical summary
        st.subheader("Statistical Summary")
        st.dataframe(df_market[['open', 'high', 'low', 'close', 'volume']].describe())

# Tab 4: Swing Trading Features
with tab4:
    st.header("📊 Swing Trading Features Validation")
    
    if df_market.empty or df_indicators.empty:
        st.warning("⚠️ Need both market data and indicators for swing trading validation")
    else:
        # Merge data for analysis
        merge_keys = []
        for k in ['stock_symbol', 'trade_date']:
            if k in df_market.columns and k in df_indicators.columns:
                merge_keys.append(k)

        if len(merge_keys) != 2:
            st.error(
                f"Cannot merge market data and indicators. Missing keys: "
                f"{[k for k in ['stock_symbol', 'trade_date'] if k not in df_market.columns or k not in df_indicators.columns]}"
            )
            st.stop()

        merged_df = pd.merge(df_market, df_indicators, on=merge_keys, how='inner')
        
        st.subheader("Swing Trading Indicators")
        
        # Check for swing trading specific indicators
        swing_indicators = ['ema_20', 'signal', 'confidence_score']
        available_swing = [ind for ind in swing_indicators if ind in merged_df.columns]
        
        st.write(f"Available swing indicators: {available_swing}")
        
        # Signal analysis
        if 'signal' in merged_df.columns:
            st.subheader("Signal Analysis")
            
            signal_counts = merged_df['signal'].value_counts()
            st.bar_chart(signal_counts)
            
            # Recent signals
            st.write("Recent Signals (Last 10):")
            recent_signals = merged_df.tail(10)[['trade_date', 'signal', 'confidence_score']]
            st.dataframe(recent_signals)
        
        # EMA crossover analysis
        if 'ema_20' in merged_df.columns and 'sma_50' in merged_df.columns:
            st.subheader("EMA/SMA Crossover Analysis")
            
            # Calculate crossovers (using EMA 20 vs SMA 50 as an example)
            merged_df['ema_sma_diff'] = merged_df['ema_20'] - merged_df['sma_50']
            merged_df['crossover'] = np.where(merged_df['ema_sma_diff'] > 0, 'Bullish (EMA>SMA)', 'Bearish (EMA<SMA)')
            
            # Count crossovers
            crossovers = merged_df['crossover'].value_counts()
            st.write(f"EMA 20/SMA 50 Crossovers: {crossovers.to_dict()}")
            
            # Plot EMAs and SMA
            st.line_chart(merged_df.tail(50).set_index('trade_date')[['close', 'ema_20', 'sma_50']])
        
        # MACD analysis (momentum)
        if 'macd' in merged_df.columns:
            st.subheader("MACD Analysis")
            
            current_macd = merged_df['macd'].iloc[-1]
            avg_macd = merged_df['macd'].mean()
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Current MACD", f"{current_macd:.4f}")
            with col2:
                st.metric("Average MACD", f"{avg_macd:.4f}")
            
            st.line_chart(merged_df.tail(50).set_index('trade_date')[['macd', 'macd_signal']])

# Tab 5: Summary Report
with tab5:
    st.header("📋 Validation Summary Report")
    
    # Generate summary
    validation_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    st.write(f"**Validation Date:** {validation_date}")
    st.write(f"**Symbol:** {symbol}")
    st.write(f"**Data Period:** {days_back} days")
    
    # Overall status
    if df_market.empty:
        st.error("🚨 CRITICAL: No market data available")
        overall_status = "FAILED"
    elif df_indicators.empty:
        st.warning("⚠️ WARNING: Market data available but no indicators")
        overall_status = "PARTIAL"
    else:
        # Calculate overall score
        data_quality_score = 100
        if quality_issues:
            data_quality_score -= len(quality_issues) * 10
        if indicator_issues:
            data_quality_score -= len(indicator_issues) * 10
        
        if data_quality_score >= 90:
            st.success("✅ EXCELLENT: Data validation passed with high quality")
            overall_status = "EXCELLENT"
        elif data_quality_score >= 70:
            st.info("ℹ️ GOOD: Data validation passed with minor issues")
            overall_status = "GOOD"
        else:
            st.warning("⚠️ NEEDS ATTENTION: Data validation found significant issues")
            overall_status = "NEEDS ATTENTION"
    
    # Detailed summary
    st.subheader("Detailed Summary")
    
    summary_data = {
        "Metric": [
            "Market Data Records",
            "Indicator Records", 
            "Data Quality Issues",
            "Indicator Issues",
            "Date Coverage",
            "Overall Status"
        ],
        "Value": [
            len(df_market),
            len(df_indicators),
            len(quality_issues) if 'quality_issues' in locals() else 0,
            len(indicator_issues) if 'indicator_issues' in locals() else 0,
            f"{df_market['trade_date'].min().date()} to {df_market['trade_date'].max().date()}" if not df_market.empty else "N/A",
            overall_status
        ]
    }
    
    summary_df = pd.DataFrame(summary_data)
    # Make the summary Arrow-safe (this is where mixed 'N/A' + numbers usually breaks pyarrow)
    summary_df = clean_dataframe_for_streamlit(summary_df)
    if "Value" in summary_df.columns:
        summary_df["Value"] = summary_df["Value"].astype(str)
    st.dataframe(summary_df)
    
    # Recommendations
    st.subheader("Recommendations")
    
    if overall_status == "FAILED":
        st.error("🚨 Immediate action required: Load market data using the refresh manager")
    elif overall_status == "PARTIAL":
        st.warning("⚠ Generate indicators using the technical analysis service")
    elif overall_status == "NEEDS ATTENTION":
        st.warning("⚠ Review and fix data quality issues before using for trading")
    else:
        st.success("✅ Data is ready for swing trading analysis")
    
    # Export button
    if st.button("📥 Export Validation Report"):
        report = {
            "validation_date": validation_date,
            "symbol": symbol,
            "period_days": days_back,
            "market_data_records": len(df_market),
            "indicator_records": len(df_indicators),
            "overall_status": overall_status,
            "data_quality_issues": quality_issues if 'quality_issues' in locals() else [],
            "indicator_issues": indicator_issues if 'indicator_issues' in locals() else []
        }
        
        st.download_button(
            label="Download JSON Report",
            data=str(report),
            file_name=f"validation_report_{symbol}_{validation_date}.json",
            mime="application/json"
        )

# Footer
st.markdown("---")
st.markdown("🔍 Data Validation Dashboard | Swing Trading Ready")
