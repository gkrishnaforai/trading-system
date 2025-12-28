#!/usr/bin/env python3
"""
Streamlit Stock Insights Dashboard
Displays comprehensive stock analysis with strategy comparison
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
import sys
import os
import requests

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_database
from app.services.stock_insights_service import StockInsightsService
from app.observability.logging import get_logger

logger = get_logger("stock_insights")

# Initialize database
init_database()

def clean_dataframe_for_streamlit(df):
    """Clean DataFrame to prevent Arrow serialization errors"""
    if df.empty:
        return df
    
    df_clean = df.copy()
    string_replacements = ['N/A', 'NA', 'null', 'None', 'n/a', 'na', 'NULL', 'undefined', '']
    df_clean = df_clean.replace(string_replacements, None)
    
    for col in df_clean.columns:
        if df_clean[col].dtype == 'object':
            try:
                non_null_series = df_clean[col].dropna()
                if len(non_null_series) > 0:
                    sample_values = non_null_series.head(10).astype(str)
                    if sample_values.str.match(r'^-?\d+\.?\d*$').all():
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

def main():
    st.set_page_config(
        page_title="Stock Insights Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("📊 Stock Insights Dashboard")
    st.markdown("Comprehensive stock analysis with strategy comparison and recommendations")
    
    # Initialize service
    insights_service = StockInsightsService()
    
    # Sidebar
    st.sidebar.title("🎛️ Analysis Controls")
    
    # Symbol input
    symbol = st.sidebar.text_input(
        "Stock Symbol",
        value="AAPL",
        help="Enter stock symbol (e.g., AAPL, MSFT, GOOGL)"
    ).upper()
    
    # Analysis options
    run_all_strategies = st.sidebar.checkbox(
        "Run All Strategies",
        value=True,
        help="Execute all available trading strategies for comparison"
    )
    
    # Get available strategies
    try:
        available_strategies = insights_service.get_available_strategies()
        strategy_names = list(available_strategies.keys())
        
        # Single strategy selector
        selected_strategy = st.sidebar.selectbox(
            "Run Single Strategy",
            options=["None"] + strategy_names,
            help="Select a single strategy to run"
        )
    except Exception as e:
        st.sidebar.error(f"Error loading strategies: {e}")
        available_strategies = {}
        strategy_names = []
        selected_strategy = "None"
    
    # Action buttons
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        generate_insights = st.button(
            "🚀 Generate Insights",
            type="primary",
            help="Generate comprehensive stock insights"
        )
    
    with col2:
        run_strategy = st.button(
            "🎯 Run Strategy",
            help="Run selected single strategy"
        )
    
    # Main content area
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
                    
                    # Display results
                    st.success(f"✅ Analysis completed for {symbol}")
                    
                    # Overall recommendation
                    st.header("🎯 Overall Recommendation")
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
                    st.header("📈 Analysis Sections")
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
                        st.header("⚖️ Strategy Comparison")
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
        # Welcome screen
        st.info("👆 Enter a stock symbol and click 'Generate Insights' to begin analysis")
        
        # Display available strategies
        if available_strategies:
            st.subheader("🎯 Available Strategies")
            
            strategy_info = []
            for name, description in available_strategies.items():
                strategy_info.append({"Strategy": name, "Description": description})
            
            df_strategies = pd.DataFrame(strategy_info)
            st.dataframe(df_strategies, width='stretch')

if __name__ == "__main__":
    main()
