"""
Market Features Page
Market movers, sectors, comparisons, analyst ratings, overview, trends
"""
import streamlit as st
import sys
import os
import pandas as pd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from api_client import get_go_api_client, APIError

setup_page_config("Market Features", "🌐")

st.title("🌐 Market Features")

# Sidebar
subscription_level = render_sidebar()

feature = st.selectbox(
    "Select Feature",
    [
        "📈 Market Movers",
        "🏭 Sector Performance",
        "⚖️ Stock Comparison",
        "⭐ Analyst Ratings",
        "📊 Market Overview",
        "📉 Market Trends"
    ]
)

if feature == "📈 Market Movers":
    st.subheader("Market Movers")
    if st.button("Get Market Movers", key="get_movers"):
        try:
            client = get_go_api_client()
            response = client.get("api/v1/market/movers")
            if response:
                movers = response.get('movers', {})
                if movers.get('gainers'):
                    st.write("**Top Gainers:**")
                    st.dataframe(pd.DataFrame(movers['gainers']), use_container_width=True)
                if movers.get('losers'):
                    st.write("**Top Losers:**")
                    st.dataframe(pd.DataFrame(movers['losers']), use_container_width=True)
                if movers.get('most_active'):
                    st.write("**Most Active:**")
                    st.dataframe(pd.DataFrame(movers['most_active']), use_container_width=True)
        except Exception as e:
            st.error(f"❌ Error: {e}")

elif feature == "🏭 Sector Performance":
    st.subheader("Sector Performance")
    if st.button("Get Sector Performance", key="get_sectors"):
        try:
            client = get_go_api_client()
            response = client.get("api/v1/market/sectors")
            if response:
                st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

elif feature == "⚖️ Stock Comparison":
    st.subheader("Stock Comparison")
    symbols = st.text_input("Symbols (comma-separated)", value="AAPL,GOOGL,NVDA", key="compare_symbols")
    if st.button("Compare Stocks", key="compare_stocks"):
        try:
            client = get_go_api_client()
            response = client.post(
                "api/v1/stocks/compare",
                json={"symbols": [s.strip() for s in symbols.split(",")]}
            )
            if response:
                st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

elif feature == "⭐ Analyst Ratings":
    st.subheader("Analyst Ratings")
    symbol = st.text_input("Symbol", value="AAPL", key="ratings_symbol")
    if st.button("Get Analyst Ratings", key="get_ratings"):
        try:
            client = get_go_api_client()
            response = client.get(f"api/v1/stock/{symbol}/analyst-ratings")
            if response:
                st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

elif feature == "📊 Market Overview":
    st.subheader("Market Overview")
    if st.button("Get Market Overview", key="get_overview"):
        try:
            client = get_go_api_client()
            response = client.get("api/v1/market/overview")
            if response:
                st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

elif feature == "📉 Market Trends":
    st.subheader("Market Trends")
    if st.button("Get Market Trends", key="get_trends"):
        try:
            client = get_go_api_client()
            response = client.get("api/v1/market/trends")
            if response:
                st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

