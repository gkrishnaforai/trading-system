"""
Global Ticker Search component (magnifying glass UX)
Renders in sidebar on every page.
Calls Go API /api/v1/tickers/search and /api/v1/tickers/:symbol.
Shows a modern Yahoo-like summary card with quick actions.
"""
import streamlit as st
import logging
from typing import Optional, Dict, Any, List

from api_client import get_go_api_client, APIError, APIConnectionError, APIResponseError

logger = logging.getLogger(__name__)

def format_market_cap(market_cap: Optional[int]) -> str:
    if market_cap is None:
        return "N/A"
    if market_cap >= 1e12:
        return f"${market_cap/1e12:.2f}T"
    if market_cap >= 1e9:
        return f"${market_cap/1e9:.2f}B"
    if market_cap >= 1e6:
        return f"${market_cap/1e6:.2f}M"
    return f"${market_cap:,.0f}"

def render_ticker_search():
    """Render the global ticker search in the sidebar."""
    st.markdown("### 🔎 Search Tickers")
    query = st.text_input("Search tickers or company name", placeholder="e.g., AAPL, Microsoft, Tesla", key="global_ticker_search")
    if not query:
        return None

    # Minimal length to avoid spamming API
    if len(query.strip()) < 1:
        return None

    try:
        client = get_go_api_client()
        search_resp = client.get("api/v1/tickers/search", params={"q": query, "limit": 10})
        tickers = search_resp.get("tickers", [])
        if not tickers:
            st.info("No tickers found.")
            return None
        # Create selectbox options: Symbol — Company Name
        options = [f"{t['symbol']} — {t['company_name'] or 'No name'}" for t in tickers]
        # Default to no selection
        selected_option = st.selectbox("Select a ticker", options=options, index=None, key="global_ticker_select")
        if not selected_option:
            return None
        # Extract symbol
        selected_symbol = selected_option.split(" — ")[0].strip()
        # Fetch full ticker details
        ticker_detail_resp = client.get(f"api/v1/tickers/{selected_symbol}")
        ticker = ticker_detail_resp
        # Render Yahoo-like card
        render_ticker_card(ticker)
        return ticker
    except (APIError, APIConnectionError, APIResponseError) as e:
        st.error(f"Search failed: {e}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return None

def render_ticker_card(ticker: Dict[str, Any]):
    """Render a modern Yahoo-like summary card for a ticker."""
    symbol = ticker.get("symbol", "")
    name = ticker.get("company_name") or "N/A"
    exchange = ticker.get("exchange") or "N/A"
    sector = ticker.get("sector") or "N/A"
    industry = ticker.get("industry") or "N/A"
    country = ticker.get("country") or "N/A"
    currency = ticker.get("currency") or "USD"
    market_cap = ticker.get("market_cap")
    current_price = ticker.get("current_price")
    day_change = ticker.get("day_change")
    day_change_pct = ticker.get("day_change_pct")
    # Render card
    st.markdown("---")
    st.markdown(f"### {symbol}")
    st.markdown(f"**{name}**")
    # Price row if available
    if current_price is not None:
        price_str = f"${current_price:.2f}"
        change_str = ""
        if day_change is not None:
            change_sign = "+" if day_change >= 0 else ""
            change_str = f" {change_sign}{day_change:.2f}"
        if day_change_pct is not None:
            pct_sign = "+" if day_change_pct >= 0 else ""
            change_str += f" ({pct_sign}{day_change_pct:.2f}%)"
        st.markdown(f"#### {price_str}{change_str}")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Exchange", exchange)
    with col2:
        st.metric("Sector", sector)
    with col3:
        st.metric("Industry", industry)
    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric("Country", country)
    with col5:
        st.metric("Currency", currency)
    with col6:
        st.metric("Market Cap", format_market_cap(market_cap))
    # Quick actions
    st.markdown("**Quick Actions**")
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        if st.button("📊 Stock Overview", key=f"stock_overview_{symbol}", use_container_width=True):
            st.session_state.overview_symbol = symbol
            st.switch_page("pages/8_Stock_Overview.py")
    with col_b:
        if st.button("📈 Stock Analysis", key=f"open_analysis_{symbol}", use_container_width=True):
            st.session_state.stock_search_symbol = symbol
            st.info(f"📈 Opening Stock Analysis for {symbol} (navigate to Stock Analysis page)")
    with col_c:
        if st.button("➕ Add to Watchlist", key=f"add_watchlist_{symbol}", use_container_width=True):
            st.session_state.add_to_watchlist_symbol = symbol
            st.info(f"➕ Ready to add {symbol} to a watchlist (use Watchlist Management page)")
    with col_d:
        if st.button("💼 Add to Portfolio", key=f"add_portfolio_{symbol}", use_container_width=True):
            st.session_state.add_to_portfolio_symbol = symbol
            st.info(f"💼 Ready to add {symbol} to a portfolio (use Portfolio Management page)")
    st.markdown("---")
