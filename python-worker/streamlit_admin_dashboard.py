#!/usr/bin/env python3
"""
Streamlit Admin Dashboard for Trading System
Load and visualize historical, daily, current, intraday data; compute indicators and signals.
"""

import streamlit as st
import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.providers.yahoo_finance.client import YahooFinanceClient
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.indicators.moving_averages import calculate_sma, calculate_ema
from app.indicators.momentum import calculate_rsi, calculate_macd
from app.indicators.signals_with_reasons import generate_signals_with_reasons
from app.analysis.stock_analysis import generate_stock_analysis
from app.analysis.investment_recommendation import generate_comprehensive_report
from app.observability.logging import get_logger

logger = get_logger("streamlit_admin_dashboard")

st.set_page_config(page_title="Trading System Admin", layout="wide")

@st.cache_data(ttl=600)
def fetch_all_data(symbol):
    """Fetch all available data for a symbol with caching."""
    client = YahooFinanceClient.from_settings()
    source = YahooFinanceSource()
    results = {}
    try:
        results["current_price"] = client.fetch_current_price(symbol)
        results["details"] = client.fetch_symbol_details(symbol)
        results["fundamentals"] = client.fetch_fundamentals(symbol)
        results["earnings_history"] = client.fetch_quarterly_earnings_history(symbol)
        results["analyst_recs"] = client.fetch_analyst_recommendations(symbol)
        results["news"] = client.fetch_news(symbol, limit=10)
        results["peers"] = client.fetch_industry_peers(symbol)
        results["price_1y"] = client.fetch_price_data(symbol, period="1y")
        results["price_1mo"] = client.fetch_price_data(symbol, period="1mo")
        results["price_5d"] = client.fetch_price_data(symbol, period="5d")
        results["price_1d"] = client.fetch_price_data(symbol, period="1d", interval="15m")
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        logger.error(f"Dashboard fetch error for {symbol}: {e}")
    return results

def compute_indicators(df):
    """Compute technical indicators for a DataFrame."""
    if df is None or df.empty:
        return df
    df = df.copy()
    df["sma20"] = calculate_sma(df["close"], 20)
    df["sma50"] = calculate_sma(df["close"], 50)
    df["sma200"] = calculate_sma(df["close"], 200)
    df["ema20"] = calculate_ema(df["close"], 20)
    df["ema50"] = calculate_ema(df["close"], 50)
    df["rsi"] = calculate_rsi(df["close"], 14)
    macd_line, macd_signal, macd_hist = calculate_macd(df["close"])
    df["macd"] = macd_line
    df["macd_signal"] = macd_signal
    df["macd_histogram"] = macd_hist
    df["volume_ma"] = df["volume"].rolling(20).mean()
    return df

def generate_signals_df(df):
    """Generate signals with reasons for a DataFrame with indicators."""
    if df is None or df.empty or "signal" in df.columns:
        return df
    # Add required inputs for signal generation
    df["volume_ma"] = df["volume"].rolling(20).mean()
    df["trend_long"] = df.apply(lambda row: 'bullish' if row['close'] > row.get('sma200', row['close']) else 'bearish', axis=1)
    df["trend_medium"] = df.apply(lambda row: 'bullish' if row.get('ema20', row['close']) > row.get('sma50', row['close']) else 'bearish', axis=1)
    signals_df = generate_signals_with_reasons(
        price=df["close"],
        ema20=df["ema20"],
        ema50=df["ema50"],
        sma200=df["sma200"],
        macd_line=df["macd"],
        macd_signal=df["macd_signal"],
        macd_histogram=df["macd_histogram"],
        rsi=df["rsi"],
        volume=df["volume"],
        volume_ma=df["volume_ma"],
        long_term_trend=df["trend_long"],
        medium_term_trend=df["trend_medium"]
    )
    df["signal"] = signals_df["signal"]
    df["reason"] = signals_df["reason"]
    df["confidence"] = df["signal"].map({"buy": 0.8, "sell": 0.8, "hold": 0.5})
    return df

st.title("📈 Trading System Admin Dashboard")
st.sidebar.header("Controls")

symbol = st.sidebar.text_input("Symbol", value="CIEN", max_chars=10).upper()

if st.sidebar.button("Load Data"):
    with st.spinner(f"Loading data for {symbol}..."):
        data = fetch_all_data(symbol)
    st.success("Data loaded!")

    # Current price and details
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Current Price", f"{data.get('current_price', 'N/A')}")
    with col2:
        details = data.get("details", {})
        st.metric("Market Cap", f"{details.get('market_cap', 'N/A')}")
    with col3:
        st.metric("PE Ratio", f"{details.get('pe_ratio', 'N/A')}")

    # Fundamentals
    st.subheader("Fundamentals")
    fundamentals = data.get("fundamentals", {})
    if fundamentals:
        fund_df = pd.DataFrame(list(fundamentals.items()), columns=["Metric", "Value"])
        st.dataframe(fund_df, use_container_width=True)
    else:
        st.info("No fundamentals data available")

    # Stock Analysis (TipRanks style)
    st.subheader("Stock Analysis")
    price_df = data.get("price_1y")
    details = data.get("details", {})
    industry_key = details.get("industryKey")
    analysis = generate_stock_analysis(symbol, price_df, fundamentals, industry_key)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Technical Momentum")
        tm = analysis["technical_momentum"]
        st.metric("Score", f"{tm['score']}/10")
        st.write(tm["summary"])
        with st.expander("Details"):
            st.json(tm["details"])
    
    with col2:
        st.markdown("### Financial Strength")
        fs = analysis["financial_strength"]
        st.metric("Score", f"{fs['score']}/10")
        st.write(fs["summary"])
        with st.expander("Details"):
            st.json(fs["details"])
    
    col3, col4 = st.columns(2)
    with col3:
        st.markdown("### Valuation")
        val = analysis["valuation"]
        st.metric("Score", f"{val['score']}/10")
        st.write(val["summary"])
        with st.expander("Details"):
            st.json(val["details"])
    
    with col4:
        st.markdown("### Trend Strength")
        ts = analysis["trend_strength"]
        st.metric("Score", f"{ts['score']}/10")
        st.write(ts["summary"])
        with st.expander("Details"):
            st.json(ts["details"])

    # Comprehensive Investment Recommendation
    st.subheader("Investment Recommendation")
    use_llm = st.checkbox("Enable LLM Sentiment Analysis", help="Toggle to analyze news sentiment with AI")
    
    # Generate comprehensive report
    news = data.get("news", [])
    report = generate_comprehensive_report(symbol, analysis, news, use_llm=use_llm)
    
    # Main recommendation
    rec = report["recommendation"]
    col_main, col_conf = st.columns([2, 1])
    with col_main:
        st.markdown(f"### Overall Signal: {rec['signal']}")
        st.write(rec["rationale"])
    with col_conf:
        st.metric("Confidence", rec["confidence"])
        st.metric("Score", f"{rec['weighted_score']}/10")
    
    # Component scores visualization
    st.markdown("#### Component Analysis")
    comp_scores = rec["component_scores"]
    comp_df = pd.DataFrame([
        {"Component": "Technical Momentum", "Score": comp_scores["technical"]},
        {"Component": "Financial Strength", "Score": comp_scores["financial"]},
        {"Component": "Valuation (Inverted)", "Score": comp_scores["valuation"]},
        {"Component": "Trend Strength", "Score": comp_scores["trend"]}
    ])
    st.bar_chart(comp_df.set_index("Component"))
    
    # Portfolio advice
    st.markdown("#### Portfolio Management")
    advice = report["portfolio_advice"]
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Action Plan**")
        st.write(advice["action"])
        st.write("**Position Sizing**")
        st.write(advice["position_sizing"])
    with col2:
        st.markdown("**Profit Strategy**")
        st.write(advice["profit_strategy"])
        st.markdown("**Risk Management**")
        st.write(advice["risk_management"])
    
    # Investor summary
    st.markdown("#### Investor Summary")
    st.info(report["investor_summary"])
    
    # Sentiment analysis (if enabled)
    if use_llm and "sentiment_analysis" in report:
        sentiment = report["sentiment_analysis"]
        st.markdown("#### Market Sentiment Analysis")
        col_sent, col_conf = st.columns([2, 1])
        with col_sent:
            st.write(sentiment.get("summary", "Sentiment analysis unavailable"))
        with col_conf:
            st.metric("Sentiment", sentiment.get("sentiment", "N/A"))
            if "confidence" in sentiment:
                st.metric("Confidence", f"{sentiment['confidence']:.0%}")
        if "disclaimer" in sentiment:
            st.caption(sentiment["disclaimer"])

    # Quarterly earnings history
    st.subheader("Quarterly Earnings History")
    earnings = data.get("earnings_history", [])
    if earnings:
        earnings_df = pd.DataFrame(earnings)
        st.dataframe(earnings_df, use_container_width=True)
    else:
        st.info("No earnings data available")

    # Analyst recommendations
    st.subheader("Analyst Recommendations")
    recs = data.get("analyst_recs", [])
    if recs:
        recs_df = pd.DataFrame(recs)
        st.dataframe(recs_df, use_container_width=True)
    else:
        st.info("No analyst recommendations available (FINNHUB_API_KEY not set)")

    # Price charts and indicators
    st.subheader("Price Data & Technical Indicators")
    period = st.selectbox("Select period", ["1y", "1mo", "5d", "1d"], index=0)
    price_key = {"1y": "price_1y", "1mo": "price_1mo", "5d": "price_5d", "1d": "price_1d"}[period]
    price_df = data.get(price_key)
    if price_df is not None and not price_df.empty:
        # Compute indicators and signals
        price_df = compute_indicators(price_df)
        price_df = generate_signals_df(price_df)

        st.write("**Price and Moving Averages**")
        st.line_chart(price_df.set_index("date")[["close", "sma20", "sma50", "sma200"]])

        st.write("**RSI**")
        st.line_chart(price_df.set_index("date")[["rsi"]])

        st.write("**MACD**")
        st.line_chart(price_df.set_index("date")[["macd", "macd_signal"]])

        st.write("**Signals**")
        signals_df = price_df[["date", "signal", "confidence", "reason"]].copy()
        st.dataframe(signals_df.tail(20), use_container_width=True)

        # Download links
        csv = price_df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, f"{symbol}_{period}_indicators_signals.csv", "text/csv")

    else:
        st.warning("No price data available for selected period")

    # News
    st.subheader("Latest News")
    news = data.get("news", [])
    if news:
        # Check if news has meaningful content
        meaningful = any(n.get("title") != "No title" and n.get("link") for n in news)
        if meaningful:
            for article in news[:5]:
                title = article.get("title", "No title")
                pub_time = article.get("published")
                pub_str = datetime.fromtimestamp(pub_time).strftime("%Y-%m-%d %H:%M") if pub_time else "Unknown"
                summary = article.get("summary", "No summary")
                link = article.get("link")
                st.markdown(f"**{title}** ({pub_str})")
                st.write(summary)
                if link:
                    st.write(f"[Read more]({link})")
                st.divider()
        else:
            st.info("Limited news content (market may be closed). Try again during market hours.")
    else:
        st.info("No news available (market may be closed)")

    # Peers
    st.subheader("Industry Peers")
    peers = data.get("peers", {})
    if peers:
        st.json(peers)
    else:
        st.info("No peers data available")

else:
    st.info("Enter a symbol and click 'Load Data' to begin.")

st.sidebar.markdown("---")
st.sidebar.markdown("Built with Streamlit + Yahoo Finance + Finnhub fallback")
