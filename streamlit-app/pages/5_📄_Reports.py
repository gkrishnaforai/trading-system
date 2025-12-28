"""
Reports Page
TipRanks-style stock reports generation and viewing
"""
import streamlit as st
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from shared_functions import get_stock_report, generate_stock_report, refresh_data
from api_client import APIError

setup_page_config("Stock Reports", "📄")

st.title("📄 TipRanks-Style Stock Reports")

# Sidebar
subscription_level = render_sidebar()

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    symbol = st.text_input("Enter Stock Symbol", value="AAPL", placeholder="e.g., AAPL, MSFT, GOOGL", key="report_symbol")

with col2:
    st.write("")  # Spacing
    fetch_data_button = st.button("📥 Fetch Data", help="Fetch historical data first", use_container_width=True, key="report_fetch_data")

with col3:
    st.write("")  # Spacing
    generate_button = st.button("🔄 Generate Report", type="primary", use_container_width=True, key="report_generate")

# Fetch historical data if button clicked
if fetch_data_button and symbol:
    with st.spinner(f"📥 Fetching historical data for {symbol.upper()}... This may take 1-2 minutes."):
        try:
            refresh_result = refresh_data(
                symbol.upper(),
                data_types=["price_historical", "fundamentals", "indicators"],
                force=True
            )
            if refresh_result:
                summary = refresh_result.get('summary', {})
                if summary.get('total_successful', 0) > 0:
                    st.success(f"✅ Data refresh completed for {symbol.upper()}!")
                else:
                    st.error(f"❌ All data refreshes failed for {symbol.upper()}")
        except APIError as e:
            st.error(f"❌ Failed to refresh data: {e}")

# Generate report if button clicked
if generate_button and symbol:
    with st.spinner("🔄 Generating report... This may take 30-60 seconds."):
        try:
            gen_result = generate_stock_report(symbol.upper())
            if gen_result and gen_result.get('success'):
                st.success(f"✅ Report generated successfully for {symbol.upper()}!")
                st.balloons()
                st.rerun()
        except APIError as e:
            st.error(f"❌ Failed to generate report: {e}")

# Display report
if symbol:
    with st.spinner("Loading report..."):
        try:
            report_data = get_stock_report(symbol.upper())
            if report_data and report_data.get('report'):
                report = report_data['report']
                
                # Simple Summary
                st.subheader("📋 Simple Summary")
                st.info(report.get('summary', 'No summary available'))
                
                # Trend Status
                st.subheader("📈 Trend Status")
                trend_status = report.get('trend_status', {})
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write("**Short-term**")
                    st.write(trend_status.get('short_term', 'N/A'))
                with col2:
                    st.write("**Medium-term**")
                    st.write(trend_status.get('medium_term', 'N/A'))
                with col3:
                    st.write("**Long-term**")
                    st.write(trend_status.get('long_term', 'N/A'))
                
                # Signal Clarity
                st.subheader("🎯 Signal Clarity")
                signal_clarity = report.get('signal_clarity', {})
                st.write(f"**Signal:** {signal_clarity.get('signal', 'N/A')}")
                st.write(f"**Confidence:** {signal_clarity.get('confidence', 'N/A')}")
                st.write(f"**Why:** {signal_clarity.get('why', 'N/A')}")
                st.write(f"**Action:** {signal_clarity.get('action', 'N/A')}")
                
                # Recommendation
                st.subheader("💡 Final Recommendation")
                recommendation = report.get('recommendation', {})
                action = recommendation.get('action', 'N/A')
                if action == 'BUY':
                    st.success(f"✅ **{action}** - Confidence: {recommendation.get('confidence', 'N/A')}")
                elif action == 'SELL':
                    st.error(f"❌ **{action}** - Confidence: {recommendation.get('confidence', 'N/A')}")
                else:
                    st.info(f"⚪ **{action}** - Confidence: {recommendation.get('confidence', 'N/A')}")
            else:
                st.info("📊 No report available yet. Click '🔄 Generate Report' to create one.")
        except APIError as e:
            st.error(f"❌ Failed to fetch report: {e}")

