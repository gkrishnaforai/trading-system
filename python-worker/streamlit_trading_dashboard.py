#!/usr/bin/env python3
"""
Streamlit Trading System Dashboard
Data validation and comprehensive stock analysis with strategy insights
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
import sys
import os
import json
import uuid
import requests

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_database, db
from app.services.data_aggregation_service import DataAggregationService
from app.services.market_overview_service import MarketOverviewService
from app.services.signal_history_tracker import create_signal_tracker, RecoverySignal, SignalType, SignalQuality, RiskLevel
from app.services.stock_screener_service import StockScreenerService
from streamlit_enhanced_watchlist_portfolio import display_enhanced_watchlist, display_enhanced_portfolio
from app.data_management.refresh_manager import DataRefreshManager, RefreshMode, DataType
from app.data_sources import get_data_source
from app.repositories.market_data_daily_repository import MarketDataDailyRepository
from app.repositories.indicators_repository import IndicatorsRepository
from app.repositories.fundamentals_repository import FundamentalsRepository
from app.repositories.stock_insights_repository import StockInsightsRepository
from app.utils.indicator_keys import (
    normalize_indicator_keys, normalize_fundamental_keys,
    IndicatorKeys, FundamentalKeys, get_missing_indicators, get_missing_fundamentals,
    get_required_indicator_keys, get_required_fundamental_keys
)
from app.observability.logging import get_logger
from app.clients.go_api_client import GoApiClient, GoApiClientConfig, GoApiError
from app.utils.trading_calendar import expected_trading_days, expected_intraday_15m_timestamps
from app.streamlit.signal_engine_interface import render_signal_engine_interface

logger = get_logger("data_validation")


def display_screeners(available_symbols: List[str]):
    st.header("🔎 Screeners")

    if 'custom_universe_symbols' not in st.session_state:
        st.session_state.custom_universe_symbols = []

    c1, c2 = st.columns([3, 1])
    with c1:
        new_symbol = st.text_input("Add symbol to universe", key="screener_add_symbol_input").strip().upper()
    with c2:
        if st.button("Add", key="screener_add_symbol_button"):
            if new_symbol and new_symbol not in st.session_state.custom_universe_symbols:
                st.session_state.custom_universe_symbols.append(new_symbol)
                st.rerun()

    universe = list(dict.fromkeys((available_symbols or []) + st.session_state.custom_universe_symbols))

    selected_universe = st.multiselect(
        "Universe",
        options=universe,
        default=universe[:200] if universe else [],
        key="screener_universe_multiselect",
    )

    max_symbols = st.slider("Max symbols to scan", min_value=25, max_value=500, value=200, step=25, key="screener_max_symbols")
    symbols_to_scan = (selected_universe or universe)[:max_symbols]

    screener_service = StockScreenerService()

# Helper to call Python worker screener API
def call_screener_api(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        base_url = os.environ.get("PYTHON_WORKER_API_URL", "http://python-worker:8000")
        response = requests.get(f"{base_url}/api/v1/screener/stocks", params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Failed to call screener API: {e}")
        return {"stocks": [], "count": 0}

    tabs = st.tabs(["📈 Technical", "💰 Fundamentals", "🎯 Signals"])
    symbols_param = symbols_to_scan if symbols_to_scan else None

    with tabs[0]:
        st.subheader("Technical Screener")
        rsi_max = st.slider("RSI max (oversold)", min_value=0, max_value=100, value=35, step=1, key="screener_rsi_max")
        rsi_min = st.slider("RSI min (overbought)", min_value=0, max_value=100, value=65, step=1, key="screener_rsi_min")

        params = {"max_rsi": float(rsi_max), "limit": max_symbols}
        if symbols_param:
            params["symbols"] = symbols_param
        oversold_resp = call_screener_api(params)

        params = {"min_rsi": float(rsi_min), "limit": max_symbols}
        if symbols_param:
            params["symbols"] = symbols_param
        overbought_resp = call_screener_api(params)

        oversold_df = pd.DataFrame(oversold_resp.get("stocks", []))
        overbought_df = pd.DataFrame(overbought_resp.get("stocks", []))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Oversold")
            if not oversold_df.empty:
                st.dataframe(oversold_df.sort_values(by=["rsi"], ascending=True), width='stretch')
            else:
                st.info("No matches")
        with c2:
            st.markdown("#### Overbought")
            if not overbought_df.empty:
                st.dataframe(overbought_df.sort_values(by=["rsi"], ascending=False), width='stretch')
            else:
                st.info("No matches")

    with tabs[1]:
        st.subheader("Fundamentals Screener")
        min_market_cap = st.number_input("Min market cap", min_value=0.0, value=0.0, step=1e9, format="%.0f", key="screener_min_market_cap")
        max_pe = st.number_input("Max P/E", min_value=0.0, value=30.0, step=1.0, key="screener_max_pe")

        fund_resp = screener_service.screen_stocks(
            symbols=symbols_param,
            min_market_cap=float(min_market_cap) if min_market_cap > 0 else None,
            max_pe_ratio=float(max_pe) if max_pe > 0 else None,
            limit=max_symbols,
        )
        fund_rows = fund_resp.get("stocks", [])
        fund_df = pd.DataFrame(fund_rows)
        if not fund_df.empty and "fundamentals" in fund_df.columns:
            fund_df["market_cap"] = fund_df["fundamentals"].apply(lambda x: (x or {}).get("market_cap"))
            fund_df["pe_ratio"] = fund_df["fundamentals"].apply(lambda x: (x or {}).get("pe_ratio"))

        if not fund_df.empty:
            sort_cols = [c for c in ["market_cap", "pe_ratio"] if c in fund_df.columns]
            st.dataframe(fund_df.sort_values(by=(sort_cols[0] if sort_cols else "symbol"), ascending=False), width='stretch')
        else:
            st.info("No matches")

    with tabs[2]:
        st.subheader("Signals Screener")
        signal_filter = st.selectbox("Signal", options=["Any", "BUY", "HOLD", "SELL"], index=0, key="screener_signal_filter")
        min_conf = st.number_input("Min confidence", value=0.0, step=0.05, key="screener_min_conf")

        sig_resp = screener_service.screen_stocks(
            symbols=symbols_param,
            signal=None if signal_filter == "Any" else signal_filter,
            min_confidence_score=float(min_conf) if min_conf > 0 else None,
            limit=max_symbols,
        )
        sig_df = pd.DataFrame(sig_resp.get("stocks", []))
        if not sig_df.empty:
            st.dataframe(sig_df.sort_values(by=["confidence_score"], ascending=False), width='stretch')
        else:
            st.info("No matches")

    st.subheader("Load data for a symbol")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        load_symbol = st.selectbox("Symbol", options=(universe or ["AAPL"]), key="screener_load_symbol_select")
    with c2:
        if st.button("Load price+indicators", key="screener_load_price_indicators"):
            refresh_manager = DataRefreshManager()
            refresh_manager.refresh_data(
                symbol=load_symbol,
                data_types=[DataType.PRICE_HISTORICAL, DataType.INDICATORS],
                mode=RefreshMode.ON_DEMAND,
                force=True,
            )
            st.cache_data.clear()
            st.success(f"Triggered refresh for {load_symbol}")
    with c3:
        if st.button("Load fundamentals", key="screener_load_fundamentals"):
            st.cache_data.clear()
            get_data_availability.clear()
            refresh_manager = DataRefreshManager()
            refresh_manager.refresh_data(
                symbol=load_symbol,
                data_types=[DataType.FUNDAMENTALS],
                mode=RefreshMode.ON_DEMAND,
                force=True,
            )
            st.success(f"Triggered fundamentals refresh for {load_symbol}")


def _get_provider_status() -> Dict[str, Any]:
    try:
        ds = get_data_source()
        primary = getattr(ds, "primary_source", None)
        fallback = getattr(ds, "fallback_source", None)
        return {
            "data_source": ds,
            "composite": primary is not None or fallback is not None,
            "primary": getattr(primary, "name", None) if primary is not None else getattr(ds, "name", None),
            "fallback": getattr(fallback, "name", None) if fallback is not None else None,
        }
    except Exception as e:
        return {"error": str(e)}


def display_audit(symbol: str):
    st.header("🧾 Audit")
    st.markdown("Recent fetch/save activity and latest stored snapshots")

    limit = st.slider("Rows", min_value=10, max_value=200, value=50, step=10, key="audit_limit")
    completeness_days = st.selectbox("Completeness Lookback (days)", [5, 10, 20, 30, 60, 90], index=3, key="audit_completeness_days")

    try:
        audit_rows = db.execute_query(
            """
            SELECT fetch_timestamp, fetch_type, data_source, rows_fetched, rows_saved, success, error_message
            FROM data_fetch_audit
            WHERE symbol = :symbol
            ORDER BY fetch_timestamp DESC
            LIMIT :limit
            """,
            {"symbol": symbol, "limit": limit},
        )

        if audit_rows:
            st.subheader("Recent Data Fetch Audit")
            st.dataframe(pd.DataFrame(audit_rows))
        else:
            st.info("No audit rows found for this symbol.")
    except Exception as e:
        st.warning(f"Could not query data_fetch_audit: {e}")

    st.subheader("Ingestion State")
    try:
        state_rows = db.execute_query(
            """
            SELECT dataset, interval, source, status, last_attempt_at, last_success_at, error_message, retry_count,
                   historical_start_date, historical_end_date, cursor_date, cursor_ts, updated_at
            FROM data_ingestion_state
            WHERE symbol = :symbol
            ORDER BY updated_at DESC
            """,
            {"symbol": symbol},
        )
        if state_rows:
            st.dataframe(pd.DataFrame(state_rows))
        else:
            st.info("No ingestion state rows found for this symbol.")
    except Exception as e:
        st.warning(f"Could not query data_ingestion_state: {e}")

    st.subheader("Completeness")
    try:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=int(completeness_days))
        daily_dates = db.execute_query(
            """
            SELECT date
            FROM raw_market_data_daily
            WHERE symbol = :symbol
              AND date >= :start_date
              AND date <= :end_date
            ORDER BY date ASC
            """,
            {"symbol": symbol, "start_date": start_date, "end_date": end_date},
        )
        present = {r["date"] for r in daily_dates if r.get("date") is not None}
        expected = set(expected_trading_days(start_date, end_date))
        missing = sorted(expected - present)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Expected (BDays)", len(expected))
        with c2:
            st.metric("Present", len(present))
        with c3:
            st.metric("Missing", len(missing))
        if missing:
            st.warning("Missing trading-day bars detected")
            st.dataframe(pd.DataFrame({"missing_trade_date": missing}))
        else:
            st.success("No missing business-day bars in lookback window")
    except Exception as e:
        st.warning(f"Completeness check failed: {e}")

    st.subheader("15m Completeness")
    try:
        table_exists = db.execute_query("SELECT to_regclass('public.raw_market_data_intraday') AS t")
        if table_exists and table_exists[0].get("t"):
            start_date = end_date - timedelta(days=int(completeness_days))
            expected_ts = expected_intraday_15m_timestamps(start_date, end_date)
            # Pull existing timestamps for 15m
            actual_ts_rows = db.execute_query(
                """
                SELECT ts
                FROM raw_market_data_intraday
                WHERE symbol = :symbol
                  AND interval = '15m'
                  AND ts >= :start_ts
                  AND ts <= :end_ts
                """,
                {
                    "symbol": symbol,
                    "start_ts": pd.Timestamp(start_date).tz_localize("UTC"),
                    "end_ts": pd.Timestamp(end_date + timedelta(days=1)).tz_localize("UTC"),
                },
            )
            actual = {pd.to_datetime(r["ts"]).tz_convert("UTC").floor("15min") for r in actual_ts_rows if r.get("ts")}
            expected = {pd.to_datetime(t).tz_convert("UTC").floor("15min") for t in expected_ts}
            missing = sorted(expected - actual)
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Expected 15m bars", len(expected))
            with c2:
                st.metric("Present 15m bars", len(actual))
            with c3:
                st.metric("Missing 15m bars", len(missing))
            if missing:
                st.warning("Missing 15m bars detected")
                st.dataframe(pd.DataFrame({"missing_ts_utc": [m.isoformat() for m in missing[:200]]}))
            else:
                st.success("No missing 15m bars in lookback window")
        else:
            st.info("Intraday table not present (raw_market_data_intraday)")
    except Exception as e:
        st.warning(f"15m completeness check failed: {e}")

    st.subheader("Intraday Freshness")
    try:
        table_exists = db.execute_query("SELECT to_regclass('public.raw_market_data_intraday') AS t")
        if table_exists and table_exists[0].get("t"):
            last_ts = db.execute_query(
                """
                SELECT MAX(ts) AS last_ts
                FROM raw_market_data_intraday
                WHERE symbol = :symbol
                  AND interval = 'last'
                """,
                {"symbol": symbol},
            )
            ts_val = last_ts[0].get("last_ts") if last_ts else None
            st.write({"last_ts": ts_val})
            if ts_val:
                age_min = (datetime.utcnow() - ts_val).total_seconds() / 60.0
                st.metric("Last Price Age (min)", f"{age_min:.1f}")
        else:
            st.info("Intraday table not present (raw_market_data_intraday)")
    except Exception as e:
        st.warning(f"Intraday freshness check failed: {e}")

    st.subheader("Ingestion Runs / Events")
    try:
        events = db.execute_query(
            """
            SELECT event_ts, level, provider, operation, duration_ms, records_in, records_saved,
                   message, error_type, error_message
            FROM data_ingestion_events
            WHERE symbol = :symbol
            ORDER BY event_ts DESC
            LIMIT :limit
            """,
            {"symbol": symbol, "limit": limit},
        )
        if events:
            st.dataframe(pd.DataFrame(events))
        else:
            st.info("No ingestion events for this symbol.")

        runs = db.execute_query(
            """
            SELECT r.run_id, r.started_at, r.finished_at, r.status, r.environment, r.git_sha
            FROM data_ingestion_runs r
            WHERE r.started_at >= NOW() - INTERVAL '7 days'
            ORDER BY r.started_at DESC
            LIMIT 25
            """,
        )
        if runs:
            st.write("Recent Runs (last 7 days)")
            st.dataframe(pd.DataFrame(runs))
    except Exception as e:
        st.warning(f"Could not query ingestion runs/events: {e}")

    st.subheader("Latest Stored Snapshots")
    col1, col2, col3 = st.columns(3)

    with col1:
        try:
            rows = db.execute_query(
                """
                SELECT COUNT(*) AS cnt, MIN(date) AS min_date, MAX(date) AS max_date
                FROM raw_market_data_daily
                WHERE symbol = :symbol
                """,
                {"symbol": symbol},
            )
            if rows:
                st.metric("Market Data Rows", int(rows[0]["cnt"] or 0))
                st.write({"min_date": rows[0]["min_date"], "max_date": rows[0]["max_date"]})

            src = db.execute_query(
                """
                SELECT source, COUNT(*) AS cnt
                FROM raw_market_data_daily
                WHERE symbol = :symbol
                GROUP BY source
                ORDER BY cnt DESC
                LIMIT 10
                """,
                {"symbol": symbol},
            )
            if src:
                st.write("Sources")
                st.dataframe(pd.DataFrame(src))
        except Exception as e:
            st.warning(f"Market data snapshot query failed: {e}")

    with col2:
        try:
            rows = db.execute_query(
                """
                SELECT COUNT(*) AS cnt, MIN(date) AS min_date, MAX(date) AS max_date
                FROM indicators_daily
                WHERE symbol = :symbol
                """,
                {"symbol": symbol},
            )
            if rows:
                st.metric("Indicators Rows", int(rows[0]["cnt"] or 0))
                st.write({"min_date": rows[0]["min_date"], "max_date": rows[0]["max_date"]})
        except Exception as e:
            st.warning(f"Indicators snapshot query failed: {e}")

    with col3:
        try:
            rows = db.execute_query(
                """
                SELECT as_of_date, source, updated_at
                FROM fundamentals_snapshots
                WHERE symbol = :symbol
                ORDER BY as_of_date DESC
                LIMIT 10
                """,
                {"symbol": symbol},
            )
            if rows:
                st.metric("Fundamentals Snapshots", len(rows))
                st.dataframe(pd.DataFrame(rows))
            else:
                st.write("No fundamentals snapshots")
        except Exception as e:
            st.warning(f"Fundamentals snapshot query failed: {e}")


def display_earnings_and_news(symbol: str):
    st.header("📅 Earnings Calendar")

    @st.cache_resource
    def _go_api_base_url() -> str:
        return os.environ.get("GO_API_URL") or os.environ.get("GO_API_BASE_URL") or "http://localhost:8000"

    @st.cache_resource
    def _go_api_client() -> GoApiClient:
        return GoApiClient(
            _go_api_base_url(),
            config=GoApiClientConfig(connect_timeout_s=5.0, read_timeout_s=30.0, total_retries=2, backoff_factor=0.3),
        )

    def _go_api_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return _go_api_client().get(path, params=params)
        except GoApiError as e:
            raise RuntimeError(f"Go API request failed ({_go_api_base_url()}): {e}")

    def _go_api_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return _go_api_client().post(path, payload=payload)
        except GoApiError as e:
            raise RuntimeError(f"Go API request failed ({_go_api_base_url()}): {e}")

    col1, col2, col3 = st.columns(3)
    with col1:
        start = st.date_input("Start", value=date.today(), key="earnings_start")
    with col2:
        end = st.date_input("End", value=date.today() + timedelta(days=14), key="earnings_end")
    with col3:
        refresh_days = st.selectbox("Refresh window", [7, 14, 30, 60, 90], index=2, key="earnings_refresh_days")

    cta1, cta2 = st.columns(2)
    with cta1:
        if st.button("🔄 Refresh earnings calendar (window)", key="earnings_refresh_window"):
            with st.spinner("Refreshing earnings calendar..."):
                payload = {
                    "symbols": None,
                    "start_date": start.strftime("%Y-%m-%d"),
                    "end_date": (date.today() + timedelta(days=int(refresh_days))).strftime("%Y-%m-%d"),
                }
                res = _go_api_post("/api/v1/admin/earnings-calendar/refresh", payload)
                if res.get("status") == "success":
                    st.success(f"✅ Refreshed {res.get('count', 0)} earnings rows")
                elif res.get("status") == "no_data":
                    st.info("No earnings returned")
                else:
                    st.error(res.get("error") or "Refresh failed")

    with cta2:
        selected_day = st.date_input("Earnings for date", value=date.today(), key="earnings_selected_day")
        if st.button("🔄 Refresh earnings for selected date", key="earnings_refresh_day"):
            with st.spinner("Refreshing earnings for date..."):
                payload = {"earnings_date": selected_day.strftime("%Y-%m-%d"), "symbols": None}
                res = _go_api_post("/api/v1/admin/earnings-calendar/refresh-for-date", payload)
                if res.get("status") == "success":
                    st.success(f"✅ Refreshed {res.get('count', 0)} earnings rows for {res.get('date')}")
                elif res.get("status") == "no_data":
                    st.info("No earnings returned")
                else:
                    st.error(res.get("error") or "Refresh failed")

    try:
        resp = _go_api_get(
            "/api/v1/admin/earnings-calendar",
            params={
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": end.strftime("%Y-%m-%d"),
            },
        )
        rows = resp.get("rows", [])
        if rows:
            df = pd.DataFrame(rows)
            display_cols = [c for c in ["earnings_date", "symbol", "company_name", "time", "eps_estimate", "eps_actual", "sector", "industry", "market_cap"] if c in df.columns]
            df_disp = df[display_cols].copy() if display_cols else df
            
            # Add selection column for data_editor
            df_disp.insert(0, "Select", False)
            
            st.subheader("Earnings Calendar (click a row to select)")
            edited_df = st.data_editor(
                df_disp,
                width='stretch',
                height=400,
                hide_index=True,
                column_config={"Select": st.column_config.CheckboxColumn(required=False)},
                key="earnings_calendar_selector"
            )
            
            # Find selected row(s)
            selected_rows = edited_df[edited_df["Select"] == True]
            if not selected_rows.empty:
                # Get the first selected row
                selected_idx = selected_rows.index[0]
                selected_data = df.iloc[selected_idx].to_dict()
                
                st.subheader(f"📊 Earnings Details: {selected_data.get('symbol', 'Unknown')}")
                
                # Display all available details for the selected row
                details_cols = st.columns(2)
                with details_cols[0]:
                    for key, value in selected_data.items():
                        if key not in ["Select"] and value is not None:
                            if isinstance(value, (int, float)):
                                st.metric(key.replace("_", " ").title(), f"{value:,.2f}" if isinstance(value, float) else f"{value:,}")
                            else:
                                st.write(f"**{key.replace('_', ' ').title()}:** {value}")
                
                with details_cols[1]:
                    # Show additional context if available
                    if selected_data.get("eps_estimate") and selected_data.get("eps_actual"):
                        eps_surprise = float(selected_data["eps_actual"]) - float(selected_data["eps_estimate"])
                        surprise_pct = (eps_surprise / float(selected_data["eps_estimate"])) * 100 if float(selected_data["eps_estimate"]) != 0 else 0
                        st.metric("EPS Surprise", f"{eps_surprise:+.2f}", f"{surprise_pct:+.1f}%")
                    
                    if selected_data.get("earnings_date"):
                        earnings_date = pd.to_datetime(selected_data["earnings_date"])
                        days_until = (earnings_date.date() - date.today()).days
                        if days_until >= 0:
                            st.metric("Days Until Earnings", f"{days_until} days")
                        else:
                            st.metric("Days Since Earnings", f"{abs(days_until)} days ago")
            
            # Clear selection button
            if selected_rows.empty is False and st.button("Clear Selection", key="clear_earnings_selection"):
                st.rerun()
                
        else:
            st.info("No earnings calendar rows stored for selected date range. Use refresh above.")
    except Exception as e:
        st.warning(f"Could not load earnings calendar: {e}")

    st.header("📰 Stock News")
    
    # News viewer state
    if 'selected_article' not in st.session_state:
        st.session_state.selected_article = None
    if 'show_article_modal' not in st.session_state:
        st.session_state.show_article_modal = False
    
    try:
        ds = get_data_source()
        news_limit = st.slider("Articles", min_value=5, max_value=50, value=10, step=5, key="news_limit")
        with st.spinner(f"Fetching news for {symbol}..."):
            articles = ds.fetch_news(symbol, int(news_limit))
        if not articles:
            st.info("No news returned for this symbol.")
            return

        st.subheader(f"Latest News for {symbol}")
        st.caption("*Headlines and summaries provided for informational purposes. Full content available at source.*")
        
        for i, a in enumerate(articles):
            title = a.get("title") or "(no title)"
            link = a.get("link") or ""
            publisher = a.get("publisher") or ""
            published = a.get("published")
            summary = a.get("summary")
            
            # Create expandable news card
            with st.expander(f"📰 {title}", expanded=False):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # Article metadata
                    meta_parts = []
                    if publisher:
                        meta_parts.append(f"**Source:** {publisher}")
                    if published:
                        # Format published date
                        try:
                            if isinstance(published, (int, float)):
                                pub_date = datetime.fromtimestamp(published).strftime("%Y-%m-%d %H:%M")
                            else:
                                pub_date = str(published)
                            meta_parts.append(f"**Published:** {pub_date}")
                        except:
                            meta_parts.append(f"**Published:** {published}")
                    
                    if meta_parts:
                        st.write(" | ".join(meta_parts))
                    
                    # Summary (truncated for compliance)
                    if summary:
                        # Show first 150 characters as preview
                        preview = summary[:150] + "..." if len(summary) > 150 else summary
                        st.write(preview)
                
                with col2:
                    # Action buttons
                    if link:
                        st.markdown(f"[🔗 Read Full Article]({link})", unsafe_allow_html=True)
                    
                    # Preview button (shows expanded view without full content)
                    if st.button("📋 Preview", key=f"preview_{i}"):
                        st.session_state.selected_article = a
                        st.session_state.show_article_modal = True
                        st.rerun()
        
        # Article preview modal
        if st.session_state.show_article_modal and st.session_state.selected_article:
            article = st.session_state.selected_article
            
            st.markdown("---")
            st.subheader("📋 Article Preview")
            
            col_close, col_title = st.columns([1, 10])
            with col_close:
                if st.button("✖️ Close", key="close_preview"):
                    st.session_state.show_article_modal = False
                    st.session_state.selected_article = None
                    st.rerun()
            
            with col_title:
                st.markdown(f"### {article.get('title', 'No title')}")
            
            # Article details
            details_col1, details_col2 = st.columns(2)
            with details_col1:
                if article.get('publisher'):
                    st.write(f"**Publisher:** {article['publisher']}")
                if article.get('published'):
                    try:
                        if isinstance(article['published'], (int, float)):
                            pub_date = datetime.fromtimestamp(article['published']).strftime("%Y-%m-%d %H:%M")
                        else:
                            pub_date = str(article['published'])
                        st.write(f"**Published:** {pub_date}")
                    except:
                        st.write(f"**Published:** {article['published']}")
            
            with details_col2:
                if article.get('link'):
                    st.markdown(f"[🔗 Read Full Article]({article['link']})", unsafe_allow_html=True)
            
            # Summary (full summary, still compliant)
            if article.get('summary'):
                st.write("**Summary:**")
                st.write(article['summary'])
            
            # Legal compliance notice
            st.info("ℹ️ *This is a preview. Full article content is available at the source link above. We respect copyright and drive traffic to original publishers.*")
            
    except Exception as e:
        st.warning(f"Could not fetch news: {e}")

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

def display_advanced_technical_analysis(symbol: str):
    """Display advanced technical analysis with MACD, Volume, and VIX data"""
    try:
        from app.utils.market_data_utils import get_symbol_indicators_data, calculate_market_regime_context
        from app.config import settings
        from datetime import date
        
        # Get today's date for analysis
        target_date = date.today().strftime("%Y-%m-%d")
        
        # Get symbol data with enhanced logging
        symbol_data = get_symbol_indicators_data(symbol, target_date, settings.database_url)
        
        if symbol_data:
            # Get market context for VIX
            market_context = calculate_market_regime_context(symbol, target_date, settings.database_url, 'stock')
            
            # Create columns for better layout
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown("### 📊 Volume & Price Action")
                current_volume = symbol_data.get('volume', 0)
                avg_volume_20d = symbol_data.get('avg_volume_20d', 0)
                volume_ratio = symbol_data.get('volume_ratio', 0)
                price_range = symbol_data.get('price_range', 0)
                high_price = symbol_data.get('high', 0)
                low_price = symbol_data.get('low', 0)
                open_price = symbol_data.get('open', 0)
                close_price = symbol_data.get('close', 0)
                
                st.metric("Current Volume", f"{current_volume:,.0f}")
                st.metric("20d Avg Volume", f"{avg_volume_20d:,.0f}")
                
                # Volume ratio with color coding
                volume_color = "🟢" if volume_ratio >= 1.2 else "🟡" if volume_ratio >= 0.8 else "🔴"
                st.metric(f"Volume Ratio {volume_color}", f"{volume_ratio:.2f}x")
                
                st.markdown(f"**Price Range:** ${low_price:.2f} - ${high_price:.2f}")
                st.markdown(f"**Today's Move:** ${open_price:.2f} → ${close_price:.2f}")
                
                # Critical Analysis #2: Volume-Price Relationship
                st.markdown("### 🎯 Volume-Price Confirmation")
                volume_price_confirmation = symbol_data.get('volume_price_confirmation', False)
                volume_price_reason = symbol_data.get('volume_price_reason', '')
                
                if volume_price_confirmation:
                    st.success("✅ **CONFIRMED** - Genuine buying pressure")
                    st.info(volume_price_reason)
                else:
                    st.warning("⚠️ **NOT CONFIRMED** - Potential fake pump")
                    st.info(volume_price_reason)
                
                # Volume interpretation
                if volume_ratio >= 1.5:
                    st.success("🔥 **High Volume** - Strong institutional interest")
                elif volume_ratio >= 1.2:
                    st.info("📈 **Above Average** - Healthy trading activity")
                elif volume_ratio >= 0.8:
                    st.warning("⚠️ **Normal Volume** - Typical trading levels")
                else:
                    st.error("📉 **Low Volume** - Weak trading interest")
            
            with col2:
                st.markdown("### 📈 MACD & Trend Analysis")
                macd_line = symbol_data.get('macd', 0)
                macd_signal = symbol_data.get('macd_signal', 0)
                macd_histogram = symbol_data.get('macd_histogram', macd_line - macd_signal)
                
                st.metric("MACD Line", f"{macd_line:.4f}")
                st.metric("Signal Line", f"{macd_signal:.4f}")
                
                # Industry-standard MACD analysis
                # 1. Trend direction (MACD Line vs 0)
                macd_trend = "bullish" if macd_line > 0 else "bearish"
                trend_color = "🟢" if macd_trend == "bullish" else "🔴"
                
                # 2. Momentum direction (MACD Line vs Signal Line)
                macd_momentum = "bullish" if macd_line > macd_signal else "bearish"
                momentum_color = "🟢" if macd_momentum == "bullish" else "🔴"
                
                # 3. Momentum strength (Histogram)
                histogram_strength = "strengthening" if (macd_histogram > 0 and macd_momentum == "bullish") or (macd_histogram < 0 and macd_momentum == "bearish") else "weakening"
                strength_color = "🟢" if histogram_strength == "strengthening" else "🔴"
                
                st.metric(f"Histogram {strength_color}", f"{macd_histogram:.4f}")
                
                # Display trend and momentum separately
                col2a, col2b = st.columns(2)
                with col2a:
                    st.metric(f"Trend {trend_color}", macd_trend.title())
                with col2b:
                    st.metric(f"Momentum {momentum_color}", macd_momentum.title())
                
                # Critical Analysis #1: Trend Confirmation Trigger
                st.markdown("### 🎯 Trend Confirmation")
                trend_confirmation = symbol_data.get('trend_confirmation', False)
                trend_confirmation_reason = symbol_data.get('trend_confirmation_reason', '')
                
                if trend_confirmation:
                    st.success("✅ **CONFIRMED** - Trend supports bullish move")
                    st.info(trend_confirmation_reason)
                else:
                    st.error("❌ **NOT CONFIRMED** - Trend against bullish move")
                    st.info(trend_confirmation_reason)
                
                # Advanced interpretation based on combination
                if macd_trend == "bullish" and macd_momentum == "bullish":
                    st.success("🚀 **Strong Bullish** - Trend and momentum aligned")
                elif macd_trend == "bearish" and macd_momentum == "bearish":
                    st.error("📉 **Strong Bearish** - Trend and momentum aligned")
                elif macd_trend == "bearish" and macd_momentum == "bullish":
                    st.warning("🔄 **Early Recovery** - Bullish momentum in bearish trend")
                elif macd_trend == "bullish" and macd_momentum == "bearish":
                    st.warning("⚠️ **Momentum Weakening** - Bearish momentum in bullish trend")
                
                with st.expander("📚 Industry-Standard MACD Analysis"):
                    st.markdown("""
                    **MACD Components:**
                    - **MACD Line** = 12-EMA - 26-EMA (Trend direction)
                    - **Signal Line** = 9-EMA of MACD Line (Momentum trigger)
                    - **Histogram** = MACD Line - Signal Line (Momentum strength)
                    
                    **Professional Interpretation:**
                    
                    **1. Trend Analysis (MACD Line vs 0):**
                    - MACD > 0: Bullish trend (price above long-term average)
                    - MACD < 0: Bearish trend (price below long-term average)
                    
                    **2. Momentum Analysis (MACD vs Signal):**
                    - MACD > Signal: Bullish momentum
                    - MACD < Signal: Bearish momentum
                    
                    **3. Momentum Strength (Histogram):**
                    - Positive histogram: Momentum strengthening in direction of trend
                    - Negative histogram: Momentum weakening against trend
                    
                    **Key Combinations:**
                    - **Bullish Trend + Bullish Momentum**: Strong buy signal
                    - **Bearish Trend + Bearish Momentum**: Strong sell signal
                    - **Bearish Trend + Bullish Momentum**: Early recovery/potential reversal
                    - **Bullish Trend + Bearish Momentum**: Trend weakening/potential reversal
                    
                    **Your Example Analysis:**
                    - MACD Line: -0.099 (Bearish trend)
                    - Signal Line: -0.247 (MACD above signal = Bullish momentum)
                    - Histogram: +0.147 (Momentum strengthening)
                    - **Interpretation**: Early recovery - bullish momentum emerging in bearish trend
                    """)
            
            with col3:
                st.markdown("### 🎯 Market Context")
                vix_level = market_context.get('vix_level', 20)
                volatility = market_context.get('volatility', 0)
                recent_change = market_context.get('recent_change', 0)
                
                st.metric("VIX Level", f"{vix_level:.2f}")
                st.metric("Volatility", f"{volatility:.2f}%")
                st.metric("Recent Change", f"{recent_change:.2f}%")
                
                # VIX interpretation
                if vix_level < 15:
                    st.success("😌 **Low Fear** - Market complacency")
                elif vix_level < 25:
                    st.info("😐 **Moderate** - Normal market conditions")
                elif vix_level < 35:
                    st.warning("😰 **Elevated** - Market uncertainty")
                else:
                    st.error("😱 **High Fear** - Market panic")
                
                with st.expander("📖 VIX & Market Context"):
                    st.markdown(f"""
                    **VIX (CBOE Volatility Index):**
                    - Measures market fear/greed through S&P 500 options
                    - **< 15**: Low volatility, potential complacency
                    - **15-25**: Normal market conditions
                    - **25-35**: Elevated uncertainty
                    - **> 35**: High fear, potential buying opportunity
                    
                    **Current Market:**
                    - Volatility: {volatility:.2f}% (stock-specific)
                    - Recent Change: {recent_change:.2f}% (price momentum)
                    """)
            
            with col4:
                st.markdown("### 🔄 Recovery Detection")
                
                # Get recovery data
                relative_strength = symbol_data.get('relative_strength', 0)
                stability_score = symbol_data.get('stability_score', 0)
                no_new_lows = symbol_data.get('no_new_lows', False)
                range_stable = symbol_data.get('range_stable', False)
                close_upper_half = symbol_data.get('close_upper_half', False)
                
                # Layer 1: Market Context
                vix_level = market_context.get('vix_level', 20)
                volatility = market_context.get('volatility', 0)
                context_ok = vix_level < 25 and volatility < 8.0
                
                st.metric("VIX Level", f"{vix_level:.1f}")
                st.metric("Volatility", f"{volatility:.1f}%")
                
                if context_ok:
                    st.success("✅ Context Favorable")
                else:
                    st.error("❌ Context Unfavorable")
                
                # Layer 2: Downtrend Weakening
                st.markdown("#### 📉 Downtrend Status")
                downtrend_weakening = no_new_lows and range_stable
                
                if downtrend_weakening:
                    st.success("✅ Weakening")
                else:
                    st.error("❌ Still Strong")
                
                # Show stability details
                st.markdown(f"No new lows: {'✅' if no_new_lows else '❌'}")
                st.markdown(f"Range stable: {'✅' if range_stable else '❌'}")
                st.markdown(f"Close upper half: {'✅' if close_upper_half else '❌'}")
                
                # Layer 3: Momentum Shift
                st.markdown("#### 📈 Momentum Shift")
                macd_histogram = symbol_data.get('macd_histogram', 0)
                rsi = symbol_data.get('rsi_14', 50)
                
                macd_positive = macd_histogram > 0
                rsi_range = 40 <= rsi <= 55
                momentum_ok = macd_positive and rsi_range
                
                if momentum_ok:
                    st.success("✅ Shifting Positive")
                else:
                    st.error("❌ Not Shifting")
                
                st.markdown(f"MACD: {macd_histogram:+.4f} ({'✅' if macd_positive else '❌'})")
                st.markdown(f"RSI: {rsi:.0f} ({'✅' if rsi_range else '❌'})")
                
                # Layer 4: Accumulation
                st.markdown("#### 💰 Accumulation")
                volume_price_confirmation = symbol_data.get('volume_price_confirmation', False)
                high_volume = symbol_data.get('high_volume', False)
                
                accumulation_ok = volume_price_confirmation and high_volume
                
                if accumulation_ok:
                    st.success("✅ Smart Money")
                else:
                    st.error("❌ No Accumulation")
                
                # Layer 5: Relative Strength (CRITICAL)
                st.markdown("#### 🏎️ Relative Strength")
                relative_strength_positive = relative_strength > 0
                
                if relative_strength_positive:
                    st.success(f"✅ +{relative_strength:.3f}")
                else:
                    st.error(f"❌ {relative_strength:.3f}")
                
                st.markdown(f"vs SPY: {relative_strength:+.3f}")
                
                # Overall Recovery Signal with comprehensive output
                st.markdown("### 🎯 Recovery Signal")
                
                recovery_confidence = 0.0
                recovery_factors = []
                
                # Layer 1: Context Gate (must pass)
                if context_ok:
                    recovery_confidence += 0.0  # Base requirement
                else:
                    recovery_confidence = 0.0
                    st.error("🔴 CONTEXT BLOCKED")
                    st.stop()
                
                # Layer 2: Downtrend Weakening
                if downtrend_weakening:
                    recovery_confidence += 0.10
                    recovery_factors.append("Downtrend weakening")
                
                # Layer 3: Momentum Shift
                if momentum_ok:
                    recovery_confidence += 0.35  # MACD + RSI
                    recovery_factors.append("Momentum shift")
                
                # Layer 4: Accumulation
                if accumulation_ok:
                    recovery_confidence += 0.25
                    recovery_factors.append("Smart money accumulation")
                
                # Layer 5: Relative Strength
                if relative_strength_positive:
                    recovery_confidence += 0.25
                    recovery_factors.append("Outperforming SPY")
                
                # Calculate position sizing and risk level
                position_size = 30 + int(recovery_confidence * 20)  # 30-50%
                risk_level = "LOW" if recovery_confidence >= 0.65 else "MODERATE" if recovery_confidence >= 0.55 else "HIGH"
                
                # Generate signal type
                if recovery_confidence >= 0.55:
                    signal_type = "BUY"
                    signal_name = "RECOVERY_ENTRY"
                    signal_color = "🟢"
                elif recovery_confidence >= 0.30:
                    signal_type = "HOLD" 
                    signal_name = "MONITORING"
                    signal_color = "🟡"
                else:
                    signal_type = "SELL"
                    signal_name = "AVOID"
                    signal_color = "🔴"
                
                # Display comprehensive signal output
                st.markdown(f"### {signal_color} Signal: {signal_type}")
                
                col_signal1, col_signal2, col_signal3 = st.columns(3)
                
                with col_signal1:
                    st.metric("Type", signal_name)
                    st.metric("Confidence", f"{recovery_confidence:.2f}")
                
                with col_signal2:
                    st.metric("Risk Level", risk_level)
                    st.metric("Position Size", f"{position_size}%")
                
                with col_signal3:
                    st.metric("Signal Quality", "HIGH" if recovery_confidence >= 0.55 else "MEDIUM" if recovery_confidence >= 0.30 else "LOW")
                    st.metric("Execution Size", "REDUCED" if position_size < 50 else "NORMAL")
                
                # Hard stop calculation
                swing_low = symbol_data.get('low', 0)
                stop_loss = swing_low * 0.95  # 5% buffer below swing low
                
                st.markdown(f"**🛡️ Hard Stop:** ${stop_loss:.2f} (5% below swing low ${swing_low:.2f})")
                
                # Soft fail conditions
                soft_fail_conditions = []
                if macd_histogram <= 0:
                    soft_fail_conditions.append("MACD histogram turns negative")
                if relative_strength <= 0:
                    soft_fail_conditions.append("Relative strength turns negative")
                if not no_new_lows:
                    soft_fail_conditions.append("Price makes new lower low")
                
                if soft_fail_conditions:
                    st.markdown(f"**⚠️ Soft Fail Triggers:** {', '.join(soft_fail_conditions)}")
                
                # Winner scaling rules
                sma_20 = symbol_data.get('ema_20', 0)  # Using EMA20 as proxy
                sma_50 = symbol_data.get('sma_50', 0)
                
                scaling_rules = []
                if close_price > sma_20:
                    scaling_rules.append("Add size when price > SMA20")
                if sma_20 > sma_50:
                    scaling_rules.append("Add again when SMA20 > SMA50")
                
                if scaling_rules:
                    st.markdown(f"**📈 Winner Scaling:** {', '.join(scaling_rules)}")
                
                # Signal tracking and comparison
                signal_tracker = create_signal_tracker()
                
                # Create current signal object
                current_signal = RecoverySignal(
                    symbol=symbol,
                    signal_type=SignalType(signal_type),
                    signal_name=signal_name,
                    confidence=recovery_confidence,
                    risk_level=RiskLevel(risk_level),
                    position_size=position_size,
                    signal_quality=SignalQuality("HIGH" if recovery_confidence >= 0.55 else "MEDIUM" if recovery_confidence >= 0.30 else "LOW"),
                    execution_size="REDUCED" if position_size < 50 else "NORMAL",
                    
                    # Recovery-specific metrics
                    recovery_confidence=recovery_confidence,
                    context_ok=context_ok,
                    downtrend_weakening=downtrend_weakening,
                    momentum_shift=momentum_ok,
                    accumulation_ok=accumulation_ok,
                    relative_strength_positive=relative_strength_positive,
                    
                    # Risk management
                    hard_stop=stop_loss,
                    swing_low=swing_low,
                    
                    # Market context
                    vix_level=vix_level,
                    volatility=volatility,
                    relative_strength=relative_strength,
                    
                    # Technical indicators
                    macd_histogram=macd_histogram,
                    rsi=symbol_data.get('rsi_14', 50),
                    volume_ratio=volume_ratio,
                    
                    # Metadata
                    timestamp=datetime.now(),
                    analysis_date=date.today()
                )
                
                # Save current signal
                signal_tracker.save_signal(current_signal)
                
                # Get previous signal for comparison
                previous_signal = signal_tracker.get_signal_history(symbol, days=7)
                if previous_signal and len(previous_signal) > 1:
                    prev_signal = previous_signal[1]  # Get most recent previous signal
                    
                    # Show signal comparison
                    st.markdown("### 📊 Signal Comparison")
                    
                    col_comp1, col_comp2, col_comp3 = st.columns(3)
                    
                    with col_comp1:
                        st.markdown("**Previous Signal:**")
                        st.metric("Type", prev_signal.signal_type.value)
                        st.metric("Confidence", f"{prev_signal.confidence:.2f}")
                        st.metric("Date", prev_signal.analysis_date.strftime("%m/%d"))
                    
                    with col_comp2:
                        st.markdown("**Current Signal:**")
                        st.metric("Type", current_signal.signal_type.value)
                        st.metric("Confidence", f"{current_signal.confidence:.2f}")
                        st.metric("Date", current_signal.analysis_date.strftime("%m/%d"))
                    
                    with col_comp3:
                        st.markdown("**Change Analysis:**")
                        
                        # Signal type change
                        if prev_signal.signal_type != current_signal.signal_type:
                            change_emoji = "🔄" if prev_signal.signal_type != SignalType.BUY and current_signal.signal_type == SignalType.BUY else "⚠️"
                            st.success(f"{change_emoji} {prev_signal.signal_type.value} → {current_signal.signal_type.value}")
                        else:
                            st.info("➡️ No signal type change")
                        
                        # Confidence change
                        conf_change = current_signal.confidence - prev_signal.confidence
                        if abs(conf_change) > 0.05:  # Significant change
                            conf_emoji = "📈" if conf_change > 0 else "📉"
                            st.metric(f"Confidence {conf_emoji}", f"{conf_change:+.2f}")
                        else:
                            st.metric("Confidence", "~ Stable")
                    
                    # Show recent changes for alerts
                    recent_changes = signal_tracker.get_signal_changes(symbol, hours=24)
                    if recent_changes:
                        st.markdown("### 🔔 Recent Signal Changes")
                        
                        for change in recent_changes[:3]:  # Show last 3 changes
                            change_time = change['timestamp'].strftime("%H:%M")
                            change_type = change['change_type']
                            
                            if change_type == 'SIGNAL_TYPE_CHANGE':
                                st.warning(f"🔄 {change_time}: Signal changed {change['old_value']} → {change['new_value']}")
                            elif change_type == 'CONFIDENCE_THRESHOLD_CHANGE':
                                st.info(f"📊 {change_time}: Confidence {change['old_value']} → {change['new_value']}")
                            elif change_type == 'RISK_LEVEL_CHANGE':
                                st.error(f"⚠️ {change_time}: Risk {change['old_value']} → {change['new_value']}")
                if recovery_confidence >= 0.55:
                    st.success(f"🟢 RECOVERY BUY")
                    st.metric("Confidence", f"{recovery_confidence:.2f}")
                    st.metric("Position Size", f"{30 + int(recovery_confidence * 20)}%")
                    
                    with st.expander("🧮 Recovery Logic"):
                        st.markdown("**Why RECOVERY BUY:**")
                        for factor in recovery_factors:
                            st.markdown(f"✅ {factor}")
                        
                        st.markdown(f"\n**Confidence Score:** {recovery_confidence:.2f}")
                        st.markdown(f"**Position Size:** {30 + int(recovery_confidence * 20)}% (reduced sizing)")
                        st.markdown(f"**Risk Level:** {'LOW' if recovery_confidence >= 0.65 else 'MODERATE'}")
                        
                        st.markdown("\n**Recovery Philosophy:**")
                        st.markdown("• Buy in fear → Early relief rally")
                        st.markdown("• Before breakout confirmation")
                        st.markdown("• Asymmetric risk/reward setup")
                        st.markdown("• Smart money accumulation detected")
                        
                else:
                    st.warning(f"⚪ NO RECOVERY")
                    st.metric("Confidence", f"{recovery_confidence:.2f}")
                    
                    with st.expander("🧮 Why No Recovery Signal Failed"):
                        missing_factors = []
                        
                        if not downtrend_weakening:
                            missing_factors.append("Downtrend not weakening")
                        if not momentum_ok:
                            missing_factors.append("Momentum not shifting")
                        if not accumulation_ok:
                            missing_factors.append("No smart money accumulation")
                        if not relative_strength_positive:
                            missing_factors.append("Underperforming SPY")
                        
                        st.markdown("**Missing Requirements:**")
                        for factor in missing_factors:
                            st.markdown(f"❌ {factor}")
                        
                        st.markdown(f"\n**Current Confidence:** {recovery_confidence:.2f} (Need ≥0.55)")
                        st.markdown("**Recommendation:** Wait for clearer recovery signals")
            
            # Summary section at bottom
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 📋 Technical Summary")
                
                # Overall technical signal using corrected MACD + critical analysis
                macd_momentum_bullish = macd_line > macd_signal
                macd_trend_bullish = macd_line > 0
                volume_strong = volume_ratio >= 1.2
                vix_low = vix_level < 25
                
                # Get critical analysis results
                trend_confirmation = symbol_data.get('trend_confirmation', False)
                volume_price_confirmation = symbol_data.get('volume_price_confirmation', False)
                
                # Get recovery signal
                recovery_confidence = 0.0
                if context_ok and symbol_data.get('stability_score', 0) > 0.67:
                    recovery_confidence += 0.10
                if macd_histogram > 0 and 40 <= symbol_data.get('rsi_14', 50) <= 55:
                    recovery_confidence += 0.35
                if volume_price_confirmation and symbol_data.get('high_volume', False):
                    recovery_confidence += 0.25
                if relative_strength > 0:
                    recovery_confidence += 0.25
                
                recovery_signal = recovery_confidence >= 0.55
                
                # Enhanced signal combination with critical rules + recovery
                if recovery_signal:
                    st.success("🟢 **RECOVERY BUY SETUP** - Early recovery detected")
                elif trend_confirmation and volume_price_confirmation and macd_momentum_bullish:
                    st.success("🟢 **STRONG BUY SETUP** - All critical confirmations met")
                elif trend_confirmation and macd_momentum_bullish and not volume_price_confirmation:
                    st.warning("🟡 **BUY WITH CAUTION** - Trend & momentum good, but volume weak")
                elif not trend_confirmation and volume_price_confirmation and macd_momentum_bullish:
                    st.warning("🔄 **EARLY RECOVERY** - Volume & momentum bullish, trend turning")
                elif trend_confirmation and not macd_momentum_bullish:
                    st.warning("⚠️ **HOLD** - Trend confirmed but momentum bearish")
                elif not trend_confirmation and not volume_price_confirmation:
                    st.error("🔴 **STRONG SELL SETUP** - All critical signals negative")
                else:
                    st.info("📊 **MIXED SIGNALS** - Wait for clearer confirmation")
                
                # Show critical rules status
                st.markdown("### 🎯 Critical Rules Status:")
                col_summary1, col_summary2, col_summary3 = st.columns(3)
                
                with col_summary1:
                    st.markdown(f"**Trend Confirmation:** {'✅' if trend_confirmation else '❌'}")
                    st.markdown(f"**Volume-Price:** {'✅' if volume_price_confirmation else '❌'}")
                
                with col_summary2:
                    st.markdown(f"**MACD Momentum:** {'✅' if macd_momentum_bullish else '❌'}")
                    st.markdown(f"**Volume Strength:** {'✅' if volume_strong else '❌'}")
                
                with col_summary3:
                    st.markdown(f"**Recovery Signal:** {'✅' if recovery_signal else '❌'}")
                    st.markdown(f"**Recovery Confidence:** {recovery_confidence:.2f}")
            
            with col2:
                st.markdown("### 🎯 Trading Insights")
                
                insights = []
                if volume_ratio >= 1.5:
                    insights.append(f"🔥 **Exceptional Volume**: {volume_ratio:.1f}x normal - Institutional activity detected")
                if abs(macd_histogram) > 0.5:
                    insights.append(f"📈 **Strong MACD**: {macd_histogram:.3f} - Momentum accelerating")
                if vix_level > 30:
                    insights.append(f"😱 **High VIX**: {vix_level:.1f} - Fear creates opportunity")
                if volatility > 3:
                    insights.append(f"📊 **High Volatility**: {volatility:.1f}% - Higher risk/reward")
                
                if insights:
                    for insight in insights[:3]:  # Show top 3 insights
                        st.markdown(f"• {insight}")
                else:
                    st.info("📊 Normal market conditions - No unusual signals detected")
        
        else:
            st.warning(f"⚠️ No technical data available for {symbol}")
            st.info("💡 Load market data and indicators using the sidebar buttons")
            
    except Exception as e:
        st.error(f"❌ Error loading advanced analysis: {e}")
        logger.error(f"Error in advanced technical analysis: {e}")

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

def display_overall_recommendation(overall_recommendation: Dict[str, Any]):
    """Display enhanced overall recommendation with entry/exit plans"""
    if not overall_recommendation:
        st.warning("No overall recommendation available")
        return
    
    # Main recommendation header
    signal = overall_recommendation.get("signal", "HOLD")
    confidence = overall_recommendation.get("confidence", 0.0)
    risk_level = overall_recommendation.get("risk_level", "Unknown")
    
    # Display main signal with color coding
    signal_color = {
        "BUY": "🟢",
        "SELL": "🔴", 
        "HOLD": "🟡"
    }.get(signal, "⚪")
    
    st.markdown(f"### {signal_color} Overall Recommendation: {signal}")
    st.markdown(f"**Confidence:** {confidence:.1%} | **Risk Level:** {risk_level}")
    
    # Reason summary
    reason_summary = overall_recommendation.get("reason_summary", "")
    if reason_summary:
        with st.expander("📝 Why this recommendation?", expanded=True):
            st.write(reason_summary)
    
    # Key drivers
    key_drivers = overall_recommendation.get("key_drivers", [])
    if key_drivers:
        st.subheader("🎯 Key Drivers")
        driver_cols = st.columns(len(key_drivers[:3]))  # Show max 3 in columns
        
        for i, driver in enumerate(key_drivers[:3]):
            with driver_cols[i]:
                impact_emoji = {
                    "Positive": "✅",
                    "Negative": "❌", 
                    "Neutral": "⚪"
                }.get(driver.get("impact", "Neutral"), "⚪")
                
                st.markdown(f"**{impact_emoji} {driver.get('factor', 'Unknown')}**")
                st.caption(f"{driver.get('value', 'N/A')}")
                st.write(f"*{driver.get('category', 'Unknown')}*")
    
    # Entry/Exit Plans
    position_plan = overall_recommendation.get("position_plan")
    swing_plan = overall_recommendation.get("swing_plan")
    
    if position_plan or swing_plan:
        st.subheader("📈 Entry & Exit Plans")
        
        plan_col1, plan_col2 = st.columns(2)
        
        with plan_col1:
            if position_plan:
                st.markdown("#### 💼 Position Trading (Weeks to Months)")
                display_trading_plan(position_plan, "Position")
        
        with plan_col2:
            if swing_plan:
                st.markdown("#### ⚡ Swing Trading (Days to Weeks)")
                display_trading_plan(swing_plan, "Swing")
    
    # Invalidation triggers
    invalidation_triggers = overall_recommendation.get("invalidation_triggers", [])
    if invalidation_triggers:
        st.subheader("⚠️ What Would Change This Call")
        for trigger in invalidation_triggers:
            st.write(f"• {trigger}")
    
    # Data readiness
    data_readiness = overall_recommendation.get("data_readiness", {})
    if data_readiness:
        st.subheader("📊 Data Readiness")
        
        readiness_cols = st.columns(4)
        with readiness_cols[0]:
            st.metric("Market Data", "✅" if data_readiness.get("market_data") else "❌")
        with readiness_cols[1]:
            st.metric("Indicators", "✅" if data_readiness.get("indicators") else "❌")
        with readiness_cols[2]:
            st.metric("Fundamentals", "✅" if data_readiness.get("fundamentals") else "❌")
        with readiness_cols[3]:
            st.metric("Overall", "✅" if data_readiness.get("overall") else "❌")
        
        missing_items = data_readiness.get("missing_items", [])
        if missing_items:
            st.warning("Missing data items: " + ", ".join(missing_items))

def display_trading_plan(plan: Dict[str, Any], plan_type: str):
    """Display a trading plan (position or swing)"""
    if not plan:
        return
    
    # Bias
    bias = plan.get("bias", "Neutral")
    bias_color = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}.get(bias, "⚪")
    st.write(f"**Bias:** {bias_color} {bias}")
    
    # Entry
    entry = plan.get("entry", {})
    if entry:
        st.write("**Entry:**")
        if plan_type == "Position" and entry.get("price_range"):
            price_range = entry["price_range"]
            st.write(f"• Zone: ${price_range[0]:.2f} - ${price_range[1]:.2f}")
        elif plan_type == "Swing" and entry.get("price"):
            st.write(f"• Price: ${entry['price']:.2f}")
        
        if entry.get("conditions"):
            for condition in entry["conditions"]:
                st.write(f"• {condition}")
        
        if entry.get("relative_guidance"):
            st.caption(f"💡 {entry['relative_guidance']}")
    
    # Stops by risk level
    stops = plan.get("stops", {})
    if stops and stops.get("levels"):
        st.write("**Stop Loss Levels:**")
        for stop in stops["levels"]:
            risk_emoji = {"Low": "🛡️", "Medium": "⚖️", "High": "⚡"}.get(stop.get("risk_level"), "❓")
            st.write(f"• {risk_emoji} **{stop.get('risk_level')}**: ${stop.get('price', 0):.2f} ({stop.get('type', 'Unknown')})")
    
    # Targets
    targets = plan.get("targets", {})
    if targets and targets.get("levels"):
        st.write("**Targets:**")
        for target in targets["levels"]:
            st.write(f"• ${target.get('price', 0):.2f} ({target.get('type', 'Unknown')})")
    
    # Risk/Reward
    risk_reward = plan.get("risk_reward")
    if risk_reward:
        st.write(f"**Risk/Reward:** {risk_reward}")
    
    # Invalidation
    invalidation = plan.get("invalidation", {})
    if invalidation and invalidation.get("price_levels"):
        st.write("**Invalidation:**")
        st.caption(invalidation.get("reasoning", ""))
        for level in invalidation["price_levels"]:
            st.write(f"• ${level.get('price', 0):.2f} - {level.get('condition', 'Unknown')}")

def display_stock_insights(symbol: str):
    """Display comprehensive stock insights"""
    st.header(f"📊 Stock Insights for {symbol}")
    
    insights_service = StockInsightsService()
    
    # Check data availability first
    fundamentals_repo = insights_service.fundamentals_repo
    has_fundamentals = bool(fundamentals_repo.fetch_by_symbol(symbol))
    
    if not has_fundamentals:
        st.warning("⚠️ **Fundamental data not available**")
        st.info("💡 **Load fundamental data using the 'Load Fundamentals' button in the sidebar** for complete analysis including:")
        st.markdown("""
        - Financial strength analysis (debt ratios, profitability)
        - Valuation metrics (P/E, EV/EBITDA with industry benchmarks)
        - Comprehensive investment recommendations
        """)
    
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
                    recommendation = insights.get("overall_recommendation", {})
                    
                    if recommendation:
                        display_overall_recommendation(recommendation)
                    else:
                        st.warning("No overall recommendation available")
                    
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
                    
                    # Advanced Technical Analysis Section
                    st.subheader("🔬 Advanced Technical Analysis")
                    display_advanced_technical_analysis(symbol)
                
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

    """Display data validation section"""
    st.header("🔍 Data Validation")
    st.markdown("Validate candlestick data quality and swing trading features")
    
    # Data Management and Caching
    @st.cache_data(ttl=3600)  # 1 hour cache
    def get_data_availability(symbol: str) -> Dict[str, Any]:
        """Check what data is available for a symbol"""
        try:
            # Check market data
            market_data = market_data_repo.fetch_by_symbol(symbol, limit=1)
            has_market_data = len(market_data) > 0
            
            # Check indicators
            indicators = indicators_repo.fetch_latest_by_symbol(symbol)
            has_indicators = indicators is not None

            normalized_indicators = normalize_indicator_keys(indicators) if indicators else {}
            
            # Check fundamentals
            fundamentals = fundamentals_repo.fetch_by_symbol(symbol)
            has_fundamentals = fundamentals is not None

            normalized_fundamentals = normalize_fundamental_keys(fundamentals) if fundamentals else {}
            
            # Check insights snapshot
            insights = stock_insights_repo.fetch_latest_insights(symbol)
            has_insights = insights is not None
            
            # Calculate data age
            market_data_age = None
            indicators_age = None
            fundamentals_age = None
            
            if has_market_data:
                market_data_age = market_data[0].get('date') if market_data else None
            if has_indicators:
                indicators_age = indicators.get('trade_date')
            if has_fundamentals:
                fundamentals_age = fundamentals.get('as_of_date')
                
            return {
                "symbol": symbol,
                "market_data": {
                    "available": has_market_data,
                    "age": market_data_age,
                    "records": len(market_data) if has_market_data else 0
                },
                "indicators": {
                    "available": has_indicators,
                    "age": indicators_age,
                    "missing_fields": get_missing_indicators(normalized_indicators) if has_indicators else _get_all_required_indicators()
                },
                "fundamentals": {
                    "available": has_fundamentals,
                    "age": fundamentals_age,
                    "missing_fields": get_missing_fundamentals(normalized_fundamentals) if has_fundamentals else _get_all_required_fundamentals()
                },
                "insights": {
                    "available": has_insights,
                    "age": insights.get('generated_at') if has_insights else None,
                    "source": insights.get('source') if has_insights else None
                },
                "overall_ready": has_market_data and has_indicators and has_fundamentals
            }
        except Exception as e:
            logger.error(f"Error checking data availability for {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "overall_ready": False
            }

    def _get_all_required_indicators() -> List[str]:
        """Get list of all required indicators"""
        return get_required_indicator_keys()

    def _get_all_required_fundamentals() -> List[str]:
        """Get list of all required fundamentals"""
        return get_required_fundamental_keys()

    def _get_missing_indicators(indicators: Dict[str, Any]) -> List[str]:
        """Get missing indicators"""
        normalized = normalize_indicator_keys(indicators) if indicators else {}
        return get_missing_indicators(normalized)

    def _get_missing_fundamentals(fundamentals: Dict[str, Any]) -> List[str]:
        """Get missing fundamentals"""
        normalized = normalize_fundamental_keys(fundamentals) if fundamentals else {}
        return get_missing_fundamentals(normalized)

    def load_data_for_symbol(symbol: str, data_types: List[str], force_refresh: bool = False) -> Dict[str, bool]:
        """Load specified data types for a symbol"""
        from app.data_management.refresh_manager import DataRefreshManager
        
        results = {}
        refresh_manager = DataRefreshManager()
        
        try:
            if 'market_data' in data_types:
                st.info(f"🔄 Loading market data for {symbol}...")
                success = refresh_manager.refresh_symbol(symbol, [DataType.PRICE_HISTORICAL])
                results['market_data'] = success
                if success:
                    st.success("✅ Market data loaded")
                else:
                    st.error("❌ Failed to load market data")
            
            if 'indicators' in data_types:
                st.info(f"🔄 Calculating indicators for {symbol}...")
                success = refresh_manager.refresh_symbol(symbol, [DataType.INDICATORS])
                results['indicators'] = success
                if success:
                    st.success("✅ Indicators calculated")
                else:
                    st.error("❌ Failed to calculate indicators")
            
            if 'fundamentals' in data_types:
                st.info(f"🔄 Loading fundamentals for {symbol}...")
                success = refresh_manager.refresh_symbol(symbol, [DataType.FUNDAMENTALS])
                results['fundamentals'] = success
                if success:
                    st.success("✅ Fundamentals loaded")
                else:
                    st.error("❌ Failed to load fundamentals")
                    
            # Clear cache to refresh data availability
            if any(results.values()):
                get_data_availability.clear()
                
        except Exception as e:
            st.error(f"❌ Error loading data: {e}")
            logger.error(f"Error loading data for {symbol}: {e}")
            
        return results

    # Initialize services
    market_data_repo = MarketDataDailyRepository()
    indicators_repo = IndicatorsRepository()
    fundamentals_repo = FundamentalsRepository()
    stock_insights_repo = StockInsightsRepository()

    # Load data with caching
    @st.cache_data(ttl=300)  # 5 minutes cache
    def load_market_data(sym, days):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            data = market_data_repo.fetch_by_symbol(sym, order_by="trade_date DESC", limit=days)
            if data is not None and len(data) > 0:
                df = pd.DataFrame(data)
                # Convert date column to datetime if it's a date object
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                df = df[df['date'] >= start_date]
                df = df.sort_values('date')
                return clean_dataframe_for_streamlit(df)
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error loading market data: {e}")
            return pd.DataFrame()
    
    @st.cache_data(ttl=300)  # 5 minutes cache
    def load_indicators_data(sym, days):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            data = indicators_repo.fetch_by_symbol(sym, order_by="trade_date DESC", limit=days)
            if data is not None and len(data) > 0:
                df = pd.DataFrame(data)
                # Convert date column to datetime if it's a date object
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                df = df[df['date'] >= start_date]
                df = df.sort_values('date')
                return clean_dataframe_for_streamlit(df)
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error loading indicators data: {e}")
            return pd.DataFrame()
    
    # Load data
    df_market = load_market_data(symbol, days_back)
    df_indicators = load_indicators_data(symbol, days_back)

    # Validation summary
    st.subheader("📊 Data Summary")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Market Data Records", len(df_market) if df_market is not None else 0)
    with col2:
        st.metric("Indicators Records", len(df_indicators) if df_indicators is not None else 0)

    # Market data validation
    if df_market is None or len(df_market) == 0:
        st.error("❌ No market data found")
        st.info("💡 Load market data using the Data Refresh Manager")
        return

    # Indicators validation
    if df_indicators is None or len(df_indicators) == 0:
        st.warning("⚠️ No indicators data found")
        st.info("💡 Load indicators using the Data Refresh Manager")

    # Show data samples
    if len(df_market) > 0:
        st.subheader("📈 Market Data Sample")
        st.dataframe(df_market.head(), width='stretch')

    if len(df_indicators) > 0:
        st.subheader("📊 Indicators Data Sample")
        st.dataframe(df_indicators.head(), width='stretch')

    # Data quality checks
    st.subheader("🔍 Data Quality Checks")

    quality_issues = []
    indicator_issues = []

    if df_market is None or len(df_market) == 0:
        quality_issues.append("No market data available")
    else:
        # Check for required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df_market.columns]
        if missing_cols:
            quality_issues.append(f"Missing columns: {missing_cols}")

        # Check for null values
        null_counts = df_market[required_cols].isnull().sum()
        if null_counts.any():
            quality_issues.append(f"Null values found: {null_counts[null_counts > 0].to_dict()}")
        
        # Check data consistency
        if not (df_market['high'] >= df_market['low']).all():
            quality_issues.append("High < Low values detected")
        
        if not (df_market['high'] >= df_market['open']).all():
            quality_issues.append("High < Open values detected")
        
        if not (df_market['high'] >= df_market['close']).all():
            quality_issues.append("High < Close values detected")
    
    if df_indicators is None or len(df_indicators) == 0:
        indicator_issues.append("No indicators data available")
    else:
        # Check for key indicators
        key_indicators = ['sma50', 'sma200', 'ema20', 'rsi', 'macd_line']
        missing_indicators = [ind for ind in key_indicators if ind not in df_indicators.columns]
        if missing_indicators:
            indicator_issues.append(f"Missing indicators: {missing_indicators}")
    
    # Display issues
    if quality_issues:
        st.error("🚨 Data Quality Issues:")
        for issue in quality_issues:
            st.error(f"• {issue}")
    
    if indicator_issues:
        st.warning("⚠️ Indicator Issues:")
        for issue in indicator_issues:
            st.warning(f"• {issue}")
    
    if not quality_issues and not indicator_issues:
        st.success("✅ All data quality checks passed!")
    
    # Data preview
    if df_market is not None and len(df_market) > 0:
        st.subheader("📈 Market Data Preview")
        st.dataframe(df_market.tail(10))
        
        # Basic statistics
        st.subheader("📊 Market Statistics")
        st.dataframe(df_market[['open', 'high', 'low', 'close', 'volume']].describe())
    
    if df_indicators is not None and len(df_indicators) > 0:
        st.subheader("📊 Indicators Preview")
        st.dataframe(df_indicators.tail(10))

def display_data_validation(symbol: str, days_back: int):
    """Display data validation section"""
    st.header("🔍 Data Validation")
    st.markdown("Validate candlestick data quality and swing trading features")
    
    # Initialize repositories
    market_data_repo = MarketDataDailyRepository()
    indicators_repo = IndicatorsRepository()
    fundamentals_repo = FundamentalsRepository()
    
    # Load data with caching
    @st.cache_data(ttl=300)  # 5 minutes cache
    def load_market_data(sym, days):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            data = market_data_repo.fetch_by_symbol(sym, order_by="trade_date DESC", limit=days)
            if data is not None and len(data) > 0:
                df = pd.DataFrame(data)
                # Convert date column to datetime if it's a date object
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                df = df[df['date'] >= start_date]
                df = df.sort_values('date')
                return clean_dataframe_for_streamlit(df)
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error loading market data: {e}")
            return pd.DataFrame()
    
    @st.cache_data(ttl=300)  # 5 minutes cache
    def load_indicators_data(sym, days):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            data = indicators_repo.fetch_by_symbol(sym, order_by="trade_date DESC", limit=days)
            if data is not None and len(data) > 0:
                df = pd.DataFrame(data)
                # Convert date column to datetime if it's a date object
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                df = df[df['date'] >= start_date]
                df = df.sort_values('date')
                return clean_dataframe_for_streamlit(df)
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error loading indicators data: {e}")
            return pd.DataFrame()
    
    # Load data
    df_market = load_market_data(symbol, days_back)
    df_indicators = load_indicators_data(symbol, days_back)
    
    # Validation summary
    st.subheader("📊 Data Summary")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Market Data Records", len(df_market) if df_market is not None else 0)
    with col2:
        st.metric("Indicators Records", len(df_indicators) if df_indicators is not None else 0)
    
    # Market data validation
    if df_market is None or len(df_market) == 0:
        st.error("❌ No market data found")
        st.info("💡 Load market data using the Data Refresh Manager")
        return
    
    # Indicators validation
    if df_indicators is None or len(df_indicators) == 0:
        st.warning("⚠️ No indicators data found")
        st.info("💡 Load indicators using the Data Refresh Manager")
    
    # Show data samples
    if len(df_market) > 0:
        st.subheader("📈 Market Data Sample")
        st.dataframe(df_market.head(), width='stretch')
    
    if len(df_indicators) > 0:
        st.subheader("📊 Indicators Data Sample")
        st.dataframe(df_indicators.head(), width='stretch')

    # Data quality checks
    st.subheader("🔍 Data Quality Checks")

    quality_issues = []
    indicator_issues = []

    if df_market is None or len(df_market) == 0:
        quality_issues.append("No market data available")
    else:
        # Check for required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df_market.columns]
        if missing_cols:
            quality_issues.append(f"Missing columns: {missing_cols}")

        # Check for null values
        null_counts = df_market[required_cols].isnull().sum()
        if null_counts.any():
            quality_issues.append(f"Null values found: {null_counts[null_counts > 0].to_dict()}")
        
        # Check data consistency
        if not (df_market['high'] >= df_market['low']).all():
            quality_issues.append("High < Low values detected")
        
        if not (df_market['high'] >= df_market['open']).all():
            quality_issues.append("High < Open values detected")
        
        if not (df_market['high'] >= df_market['close']).all():
            quality_issues.append("High < Close values detected")
    
    if df_indicators is None or len(df_indicators) == 0:
        indicator_issues.append("No indicators data available")
    else:
        # Check for key indicators
        key_indicators = ['sma50', 'sma200', 'ema20', 'rsi', 'macd_line']
        missing_indicators = [ind for ind in key_indicators if ind not in df_indicators.columns]
        if missing_indicators:
            indicator_issues.append(f"Missing indicators: {missing_indicators}")
    
    # Display issues
    if quality_issues:
        st.warning("⚠️ Data Quality Issues:")
        for issue in quality_issues:
            st.warning(f"• {issue}")
    
    if indicator_issues:
        st.warning("⚠️ Indicator Issues:")
        for issue in indicator_issues:
            st.warning(f"• {issue}")
    
    if not quality_issues and not indicator_issues:
        st.success("✅ All data quality checks passed!")
    
    # Data preview
    if df_market is not None and len(df_market) > 0:
        st.subheader("📈 Market Data Preview")
        st.dataframe(df_market.tail(10))
        
        # Basic statistics
        st.subheader("📊 Market Statistics")
        st.dataframe(df_market[['open', 'high', 'low', 'close', 'volume']].describe())
    
    if df_indicators is not None and len(df_indicators) > 0:
        st.subheader("📊 Indicators Preview")
        st.dataframe(df_indicators.tail(10))

# Data Availability Functions (moved here to be defined before use)
@st.cache_data(ttl=3600)  # 1 hour cache
def get_data_availability(symbol: str, filter_days: int = 365) -> Dict[str, Any]:
    """Check what data is available for a symbol"""
    try:
        # Initialize repositories
        market_data_repo = MarketDataDailyRepository()
        indicators_repo = IndicatorsRepository()
        fundamentals_repo = FundamentalsRepository()
        stock_insights_repo = StockInsightsRepository()
        
        # Check market data with date filter
        market_data = market_data_repo.fetch_by_symbol(symbol, limit=filter_days)
        has_market_data = len(market_data) > 0
        
        # Check indicators
        indicators = indicators_repo.fetch_latest_by_symbol(symbol)
        has_indicators = indicators is not None
        
        # Check fundamentals
        fundamentals = fundamentals_repo.fetch_by_symbol(symbol)
        has_fundamentals = fundamentals is not None
        
        # Check insights snapshot
        insights = stock_insights_repo.fetch_latest_insights(symbol)
        has_insights = insights is not None
        
        # Calculate data age
        market_data_age = None
        indicators_age = None
        fundamentals_age = None
        
        if has_market_data:
            market_data_age = market_data[0].get('date') if market_data else None
        if has_indicators:
            indicators_age = indicators.get('trade_date')
        if has_fundamentals:
            fundamentals_age = fundamentals.get('as_of_date')
            
        return {
            "symbol": symbol,
            "filter_days": filter_days,
            "market_data": {
                "available": has_market_data,
                "age": market_data_age,
                "records": len(market_data) if has_market_data else 0
            },
            "indicators": {
                "available": has_indicators,
                "age": indicators_age,
                "missing_fields": _get_missing_indicators(indicators) if has_indicators else _get_all_required_indicators()
            },
            "fundamentals": {
                "available": has_fundamentals,
                "age": fundamentals_age,
                "missing_fields": _get_missing_fundamentals(fundamentals) if has_fundamentals else _get_all_required_fundamentals()
            },
            "insights": {
                "available": has_insights,
                "age": insights.get('generated_at') if has_insights else None,
                "source": insights.get('source') if has_insights else None
            },
            "overall_ready": has_market_data and has_indicators and has_fundamentals
        }
    except Exception as e:
        logger.error(f"Error checking data availability for {symbol}: {e}")
        return {
            "symbol": symbol,
            "filter_days": filter_days,
            "error": str(e),
            "overall_ready": False
        }

def _get_all_required_indicators() -> List[str]:
    """Get list of all required indicators"""
    return ['sma_50', 'sma_200', 'ema_20', 'rsi_14', 'macd', 'macd_signal', 'macd_hist']

def _get_all_required_fundamentals() -> List[str]:
    """Get list of all required fundamentals"""
    return ['pe_ratio', 'pb_ratio', 'price_to_sales', 'debt_to_equity', 'roe', 'revenue_growth']

def _get_missing_indicators(indicators: Dict[str, Any]) -> List[str]:
    """Get missing indicators"""
    if not indicators:
        return _get_all_required_indicators()
    
    missing = []
    required = _get_all_required_indicators()
    
    # Map expected names to actual database column names (after aliases)
    # The indicators dict now contains aliased names like 'sma50', 'sma200', etc.
    db_columns = {
        'sma_50': 'sma50',
        'sma_200': 'sma200', 
        'ema_20': 'ema20',
        'rsi_14': 'rsi',
        'macd': 'macd_line',
        'macd_signal': 'macd_signal',
        'macd_hist': 'macd_hist'
    }
    
    for req in required:
        db_field = db_columns.get(req, req)
        if db_field not in indicators or indicators[db_field] is None:
            missing.append(req)
    
    return missing

def _get_missing_fundamentals(fundamentals: Dict[str, Any]) -> List[str]:
    """Get missing fundamentals"""
    if not fundamentals:
        return _get_all_required_fundamentals()
    
    missing = []
    required = _get_all_required_fundamentals()
    
    for req in required:
        if req not in fundamentals or fundamentals[req] is None:
            missing.append(req)
    
    return missing

def load_data_for_symbol(symbol: str, data_types: List[str]) -> Dict[str, bool]:
    """Load specified data types for a symbol"""
    results = {}
    refresh_manager = DataRefreshManager()
    
    try:
        if 'market_data' in data_types:
            success = refresh_manager.refresh_symbol(symbol, [DataType.PRICE_HISTORICAL])
            results['market_data'] = success
        
        if 'indicators' in data_types:
            success = refresh_manager.refresh_symbol(symbol, [DataType.INDICATORS])
            results['indicators'] = success
        
        if 'fundamentals' in data_types:
            success = refresh_manager.refresh_symbol(symbol, [DataType.FUNDAMENTALS])
            results['fundamentals'] = success
                
        # Clear cache to refresh data availability
        if any(results.values()):
            get_data_availability.clear()
            
    except Exception as e:
        st.error(f"❌ Error loading data: {e}")
        logger.error(f"Error loading data for {symbol}: {e}")
        
    return results

def display_data_availability(symbol: str):
    """Display comprehensive data availability and loading interface"""
    st.header("📊 Data Availability & Management")
    st.markdown("Check data availability, load missing data, and manage caching for symbols")

    sidebar_symbol = symbol

    # If the selected symbol changes, clear any pending force-refresh confirmation
    last_symbol_key = "_data_availability_last_symbol"
    if st.session_state.get(last_symbol_key) != sidebar_symbol:
        st.session_state["force_refresh_confirm"] = False
        st.session_state["force_refresh_symbol"] = sidebar_symbol
        st.session_state[last_symbol_key] = sidebar_symbol
    
    # Symbol input - use the same symbol from sidebar
    symbol = st.text_input(
        "Enter Symbol",
        value=sidebar_symbol,
        key=f"data_av_symbol_{sidebar_symbol}",
    ).upper()
    
    # Date range for filtering
    filter_days = st.selectbox("Filter Data Range", [30, 90, 180, 365], index=1, key="filter_days")
    
    check_btn = st.button("🔍 Check Data", type="primary")
    
    if check_btn or symbol:
        # Get data availability
        with st.spinner(f"Checking data availability for {symbol}..."):
            data_status = get_data_availability(symbol, filter_days)
        
        # Display overall status
        st.subheader("📋 Overall Status")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if data_status.get("overall_ready", False):
                st.success("✅ All Data Ready")
            else:
                st.warning("⚠️ Missing Data")
        
        with col2:
            st.metric("Market Data", "✅" if data_status.get("market_data", {}).get("available") else "❌")
        
        with col3:
            st.metric("Indicators", "✅" if data_status.get("indicators", {}).get("available") else "❌")
        
        # Detailed breakdown
        st.subheader("📈 Detailed Data Status")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Market Data**")
            market_data = data_status.get("market_data", {})
            if market_data.get("available"):
                st.success(f"✅ Available ({market_data.get('records', 0)} records in last {filter_days} days)")
                if market_data.get("age"):
                    st.info(f"📅 Latest: {market_data['age']}")
            else:
                st.error(f"❌ Not Available (last {filter_days} days)")
        
        with col2:
            st.write("**Fundamentals**")
            fundamentals = data_status.get("fundamentals", {})
            if fundamentals.get("available"):
                st.success("✅ Available")
                if fundamentals.get("age"):
                    st.info(f"📅 As of: {fundamentals['age']}")
            else:
                st.error("❌ Not Available")
        
        # Indicators details
        st.write("**Technical Indicators**")
        indicators = data_status.get("indicators", {})
        if indicators.get("available"):
            st.success("✅ Available")
            missing = indicators.get("missing_fields", [])
            if missing:
                st.warning(f"⚠️ Missing: {', '.join(missing)}")
            else:
                st.success("✅ All required indicators present")
        else:
            st.error("❌ Not Available")
            st.info(f"Required: {', '.join(indicators.get('missing_fields', []))}")
        
        # Loading section
        st.subheader("🔄 Data Loading")
        
        # Check what needs to be loaded
        missing_data = []
        if not data_status.get("market_data", {}).get("available"):
            missing_data.append("market_data")
        if not data_status.get("indicators", {}).get("available"):
            missing_data.append("indicators")
        if not data_status.get("fundamentals", {}).get("available"):
            missing_data.append("fundamentals")
        
        if missing_data:
            st.info(f"📋 Missing data: {', '.join(missing_data).replace('_', ' ').title()}")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("📈 Load Market Data", disabled="market_data" not in missing_data):
                    load_data_for_symbol(symbol, ["market_data"])
            
            with col2:
                if st.button("📊 Calculate Indicators", disabled="indicators" not in missing_data):
                    load_data_for_symbol(symbol, ["indicators"])
            
            with col3:
                if st.button("💰 Load Fundamentals", disabled="fundamentals" not in missing_data):
                    load_data_for_symbol(symbol, ["fundamentals"])
            
            # Load all button
            if st.button("🚀 Load All Missing Data", type="primary"):
                with st.spinner(f"Loading all missing data for {symbol}..."):
                    results = load_data_for_symbol(symbol, missing_data)
                    if all(results.values()):
                        st.success("✅ All data loaded successfully!")
                        st.rerun()
        else:
            st.success("✅ All data is available!")
            
            # Force refresh option
            if st.button("🔄 Force Refresh All Data", key=f"force_refresh_btn_{symbol}"):
                st.session_state["force_refresh_confirm"] = True
                st.session_state["force_refresh_symbol"] = symbol

            if st.session_state.get("force_refresh_confirm") and st.session_state.get("force_refresh_symbol") == symbol:
                st.warning(f"This will reload all data for {symbol}.")
                confirm_col, cancel_col = st.columns(2)

                with confirm_col:
                    if st.button("✅ Yes, reload", type="primary", key=f"force_refresh_yes_{symbol}"):
                        with st.spinner(f"Force refreshing all data for {symbol}..."):
                            load_data_for_symbol(symbol, ["market_data", "indicators", "fundamentals"])
                        st.session_state["force_refresh_confirm"] = False
                        st.rerun()

                with cancel_col:
                    if st.button("❌ Cancel", key=f"force_refresh_cancel_{symbol}"):
                        st.session_state["force_refresh_confirm"] = False
                        st.rerun()
        
        # Data insights
        st.subheader("📊 Data Insights")
        insights = data_status.get("insights", {})
        if insights.get("available"):
            st.success(f"✅ Insights available (Generated: {insights.get('age')})")
            st.info(f"Source: {insights.get('source')}")
        else:
            st.info("💡 Generate insights using the Stock Insights tab")

def display_growth_quality_analysis(symbol: str):
    """Display institutional-grade growth quality analysis"""
    st.header("💰 Growth Quality Analysis")
    st.markdown("Institutional-grade growth health classification with clear investment guidance")
    
    try:
        # Fetch growth health classification
        with st.spinner(f"Analyzing growth health for {symbol}..."):
            response = requests.get(f"http://localhost:8001/api/v1/growth-quality/growth-health/{symbol}")
            
            if response.status_code == 200:
                data = response.json()
                _render_institutional_analysis(data)
            else:
                st.error(f"❌ Failed to analyze {symbol}")
                st.info("💡 Make sure fundamentals data is loaded using the 'Load All Data' button")
                
    except Exception as e:
        st.error(f"❌ Error in growth quality analysis: {e}")
        logger.error(f"Error in growth quality analysis for {symbol}: {e}")


def _render_institutional_analysis(data: Dict[str, Any]):
    """Render institutional-grade analysis with clear messaging"""
    symbol = data.get('symbol', 'Unknown')
    
    # Structural Risk Assessment
    structural_risk = data.get('structural_risk', 'LOW')
    structural_colors = {
        'LOW': '#38ef7d',
        'MEDIUM': '#f5576c', 
        'HIGH': '#eb3349'
    }
    structural_icons = {
        'LOW': '🟢',
        'MEDIUM': '🟡',
        'HIGH': '🔴'
    }
    
    # Growth Phase Assessment
    growth_phase = data.get('growth_phase', 'MATURE_COMPOUNDER')
    growth_display = {
        'HEALTHY_COMPOUNDER': '🟢 Healthy Compounder',
        'MATURE_COMPOUNDER': '🟡 Mature Compounder',
        'GROWTH_DEGRADATION': '🟠 Growth Degradation',
        'GROWTH_BREAKDOWN': '🔴 Growth Breakdown'
    }
    
    # Investment Posture
    investment_posture = data.get('investment_posture', 'HOLD_SELECTIVE_ADD')
    posture_display = {
        'BUY': '🟢 BUY',
        'HOLD_SELECTIVE_ADD': '🟡 HOLD / SELECTIVE ADD',
        'TRIM_REDUCE': '🟠 TRIM / REDUCE',
        'EXIT_AVOID': '🔴 EXIT / AVOID'
    }
    
    # Main Assessment Card
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 30px; border-radius: 15px; color: white; margin: 20px 0;">
        <h2>📊 Overall Assessment — {symbol}</h2>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;">
            <div>
                <h3>Structural Risk: {structural_icons.get(structural_risk, '')} {structural_risk}</h3>
                <p style="font-size: 14px; opacity: 0.9;">Balance sheet and revenue quality assessment</p>
            </div>
            <div>
                <h3>Growth Phase: {growth_display.get(growth_phase, growth_phase)}</h3>
                <p style="font-size: 14px; opacity: 0.9;">Business lifecycle stage and trajectory</p>
            </div>
        </div>
        
        <div style="margin-top: 20px; padding: 15px; background: rgba(255,255,255,0.1); border-radius: 10px;">
            <h3>Investment Posture: {posture_display.get(investment_posture, investment_posture)}</h3>
            <p style="font-size: 14px; opacity: 0.9;">Clear action guidance based on risk and growth profile</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Detailed Analysis Sections
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🎯 Investment Reasoning")
        for reason in data.get('reasoning', []):
            st.markdown(f"• {reason}")
        
        st.markdown("### 💰 Forward Return Expectations")
        st.info(data.get('forward_return_expectation', 'Not available'))
    
    with col2:
        st.markdown("### ⚠️ Risk Factors to Monitor")
        for risk in data.get('risk_factors', []):
            st.markdown(f"• {risk}")
        
        st.markdown("### 🚀 Potential Opportunities")
        for opportunity in data.get('opportunities', []):
            st.markdown(f"• {opportunity}")
    
    # Confidence and Analysis Date
    confidence = data.get('confidence', 0) * 100
    st.markdown(f"**Confidence in Assessment:** {confidence:.0f}%")
    st.caption(f"Analysis as of: {data.get('analysis_date', 'Unknown')}")
    
    # Investment Guidance Summary
    st.markdown("---")
    st.markdown("### 📋 Investment Guidance Summary")
    
    if investment_posture == 'BUY':
        st.success("""
        **🟢 BUY - Aggressive Accumulation**
        
        **Why:** Strong structural health + accelerating growth trajectory
        **Action:** Build core position, consider adding on weakness
        **Sizing:** Above-average position size (2-3% of portfolio)
        """)
    elif investment_posture == 'HOLD_SELECTIVE_ADD':
        st.warning("""
        **🟡 HOLD / SELECTIVE ADD - Long-term Compounder**
        
        **Why:** Strong structural health + mature growth phase
        **Action:** Hold core position, add only on meaningful corrections (15%+ pullbacks)
        **Sizing:** Standard position size (1-2% of portfolio)
        **Note:** Do NOT chase breakouts - growth is priced in
        """)
    elif investment_posture == 'TRIM_REDUCE':
        st.error("""
        **🟠 TRIM / REDUCE - Growth Slowing**
        
        **Why:** Growth trajectory showing material slowdown
        **Action:** Reduce position size by 25-50%
        **Sizing:** Below-average position size (0.5-1% of portfolio)
        **Note:** Consider redeploying capital to higher-growth opportunities
        """)
    else:
        st.error("""
        **🔴 EXIT / AVOID - Structural Issues**
        
        **Why:** Structural risk or growth breakdown detected
        **Action:** Sell existing position or avoid entirely
        **Sizing:** Zero exposure
        **Note:** Capital preservation priority over growth potential
        """)

def display_fundamentals_and_indicators(symbol: str):
    """Display latest fundamentals and indicators side by side using canonical keys"""
    st.header("📚 Fundamentals & Indicators")
    st.markdown("Latest snapshot of key metrics and technical indicators")
    
    # Initialize repositories
    indicators_repo = IndicatorsRepository()
    fundamentals_repo = FundamentalsRepository()
    market_data_repo = MarketDataDailyRepository()
    
    try:
        # Fetch data
        with st.spinner(f"Loading data for {symbol}..."):
            indicators_data = indicators_repo.fetch_latest_by_symbol(symbol)
            fundamentals_data = fundamentals_repo.fetch_by_symbol(symbol)
            market_data = market_data_repo.fetch_by_symbol(symbol, limit=1)
            
            # Normalize to canonical keys
            indicators = normalize_indicator_keys(indicators_data) if indicators_data else {}
            fundamentals = normalize_fundamental_keys(fundamentals_data) if fundamentals_data else {}
            
            # Inject price if available
            if market_data and len(market_data) > 0:
                indicators[IndicatorKeys.PRICE] = float(market_data[0]['close'])
        
        # Overview metrics
        st.subheader("📊 Overview")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            current_price = indicators.get(IndicatorKeys.PRICE)
            if current_price:
                st.metric("Current Price", f"${current_price:.2f}")
            else:
                st.metric("Current Price", "N/A")
        
        with col2:
            pe_ratio = fundamentals.get(FundamentalKeys.PE_RATIO)
            if pe_ratio:
                st.metric("P/E Ratio", f"{pe_ratio:.2f}")
            else:
                st.metric("P/E Ratio", "N/A")
        
        with col3:
            rsi = indicators.get(IndicatorKeys.RSI_14)
            if rsi:
                rsi_color = "🟢" if rsi < 70 else "🔴" if rsi > 80 else "🟡"
                st.metric("RSI", f"{rsi:.1f} {rsi_color}")
            else:
                st.metric("RSI", "N/A")
        
        with col4:
            sma50 = indicators.get(IndicatorKeys.SMA_50)
            sma200 = indicators.get(IndicatorKeys.SMA_200)
            if sma50 and sma200:
                trend = "📈" if sma50 > sma200 else "📉"
                st.metric("Trend", f"{trend}")
            else:
                st.metric("Trend", "N/A")
        
        # Technical Indicators
        st.subheader("📈 Technical Indicators")
        
        if indicators:
            # Group indicators by category
            ma_indicators = {
                "SMA 50": indicators.get(IndicatorKeys.SMA_50),
                "SMA 200": indicators.get(IndicatorKeys.SMA_200),
                "EMA 20": indicators.get(IndicatorKeys.EMA_20),
                "EMA 50": indicators.get(IndicatorKeys.EMA_50),
            }
            
            momentum_indicators = {
                "RSI (14)": indicators.get(IndicatorKeys.RSI_14),
                "MACD Line": indicators.get(IndicatorKeys.MACD_LINE),
                "MACD Signal": indicators.get(IndicatorKeys.MACD_SIGNAL),
                "MACD Histogram": indicators.get(IndicatorKeys.MACD_HIST),
            }
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Moving Averages**")
                for name, value in ma_indicators.items():
                    if value is not None:
                        st.metric(name, f"{value:.2f}")
                    else:
                        st.metric(name, "N/A")
            
            with col2:
                st.write("**Momentum Indicators**")
                for name, value in momentum_indicators.items():
                    if value is not None:
                        if "RSI" in name:
                            st.metric(name, f"{value:.1f}")
                        else:
                            st.metric(name, f"{value:.4f}")
                    else:
                        st.metric(name, "N/A")
        else:
            st.warning("⚠️ No indicators data available")
        
        # Fundamentals
        st.subheader("💰 Fundamentals")
        
        if fundamentals:
            # Group fundamentals by category
            valuation_metrics = {
                "P/E Ratio": fundamentals.get(FundamentalKeys.PE_RATIO),
                "P/B Ratio": fundamentals.get(FundamentalKeys.PB_RATIO),
                "Price to Sales": fundamentals.get(FundamentalKeys.PRICE_TO_SALES),
                "Market Cap": fundamentals.get(FundamentalKeys.MARKET_CAP),
            }
            
            financial_health = {
                "Debt to Equity": fundamentals.get(FundamentalKeys.DEBT_TO_EQUITY),
                "Return on Equity": fundamentals.get(FundamentalKeys.ROE),
                "Revenue Growth": fundamentals.get(FundamentalKeys.REVENUE_GROWTH),
                "EPS": fundamentals.get(FundamentalKeys.EPS),
            }
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Valuation Metrics**")
                for name, value in valuation_metrics.items():
                    if value is not None:
                        if "Market Cap" in name and value > 1e9:
                            st.metric(name, f"${value/1e9:.1f}B")
                        elif "Market Cap" in name and value > 1e6:
                            st.metric(name, f"${value/1e6:.1f}M")
                        elif name in ["P/E Ratio", "P/B Ratio", "Price to Sales"]:
                            st.metric(name, f"{value:.2f}")
                        else:
                            st.metric(name, f"{value:.2f}")
                    else:
                        st.metric(name, "N/A")
            
            with col2:
                st.write("**Financial Health**")
                for name, value in financial_health.items():
                    if value is not None:
                        if "Revenue Growth" in name or "Return on Equity" in name:
                            st.metric(name, f"{value:.1%}")
                        else:
                            st.metric(name, f"{value:.2f}")
                    else:
                        st.metric(name, "N/A")
        else:
            st.warning("⚠️ No fundamentals data available")
        
        # Data Quality Status
        st.subheader("🔍 Data Quality")
        
        missing_indicators = get_missing_indicators(indicators)
        missing_fundamentals = get_missing_fundamentals(fundamentals)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if not missing_indicators:
                st.success("✅ All required indicators present")
            else:
                st.warning(f"⚠️ Missing indicators: {', '.join(missing_indicators)}")
        
        with col2:
            if not missing_fundamentals:
                st.success("✅ All required fundamentals present")
            else:
                st.info(f"ℹ️ Missing fundamentals: {', '.join(missing_fundamentals)}")
        
        # Raw data for developers
        with st.expander("🔧 Raw Data (Canonical Keys)"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Indicators (Canonical Keys)**")
                if indicators:
                    st.json(indicators)
                else:
                    st.write("No indicators data")
            
            with col2:
                st.write("**Fundamentals (Canonical Keys)**")
                if fundamentals:
                    st.json(fundamentals)
                else:
                    st.write("No fundamentals data")
    
    except Exception as e:
        st.error(f"❌ Error loading data: {e}")
        logger.error(f"Error in fundamentals and indicators display: {e}")

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

provider_status = _get_provider_status()
if provider_status.get("error"):
    st.warning(f"Provider status unavailable: {provider_status['error']}")
else:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Primary Provider", provider_status.get("primary") or "unknown")
    with c2:
        st.metric("Fallback Provider", provider_status.get("fallback") or "none")
    with c3:
        st.metric("Data Source", getattr(provider_status.get("data_source"), "name", "unknown"))

# Sidebar
st.sidebar.header("Dashboard Controls")

# Symbol selection
if 'custom_symbols' not in st.session_state:
    st.session_state.custom_symbols = []

try:
    _symbols_from_db = DataAggregationService().get_available_symbols()
except Exception:
    _symbols_from_db = []

_default_symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMZN", "META", "SPY", "QQQ", "IWM"]
available_symbols = list(dict.fromkeys((_symbols_from_db or _default_symbols) + st.session_state.custom_symbols))

new_symbol_sidebar = st.sidebar.text_input("Add custom symbol", key="sidebar_add_symbol").strip().upper()
if st.sidebar.button("Add symbol", key="sidebar_add_symbol_btn"):
    if new_symbol_sidebar and new_symbol_sidebar not in st.session_state.custom_symbols:
        st.session_state.custom_symbols.append(new_symbol_sidebar)
        st.rerun()

symbol = st.sidebar.selectbox(
    "Select Symbol",
    available_symbols,
    index=0,
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

# Data Loading Section
st.sidebar.subheader("📥 Data Loading")
load_data = st.sidebar.button("Load Market Data", help="Load historical market data for selected symbol")
load_indicators = st.sidebar.button("Load Indicators", help="Calculate technical indicators for selected symbol")
load_fundamentals = st.sidebar.button("Load Fundamentals", help="Load fundamental data for selected symbol")
clear_cache = st.sidebar.button("🗑️ Clear Cache", help="Clear all cached data to force refresh")

# Custom Symbol Data Loading Section
st.sidebar.subheader("🔧 Custom Symbol Loading")
custom_symbol = st.sidebar.text_input(
    "Enter Symbol (e.g., TQQQ, QQQ, VIX)",
    placeholder="TQQQ",
    help="Load historical data for any ticker symbol"
)

if custom_symbol:
    custom_symbol = custom_symbol.upper().strip()
    
    col1, col2, col3 = st.sidebar.columns(3)
    
    with col1:
        load_custom_price = st.button(
            "📈 Price",
            key=f"load_price_{custom_symbol}",
            help=f"Load price data for {custom_symbol}"
        )
    
    with col2:
        load_custom_indicators = st.button(
            "📊 Indicators", 
            key=f"load_indicators_{custom_symbol}",
            help=f"Load indicators for {custom_symbol}"
        )
    
    with col3:
        load_custom_all = st.button(
            "🚀 All",
            key=f"load_all_{custom_symbol}",
            help=f"Load all data for {custom_symbol}"
        )
    
    # Handle custom symbol loading
    if load_custom_price or load_custom_indicators or load_custom_all:
        with st.spinner(f"Loading data for {custom_symbol}..."):
            try:
                refresh_manager = DataRefreshManager()
                
                # Determine what to load
                data_types = []
                if load_custom_price or load_custom_all:
                    data_types.append(DataType.PRICE_HISTORICAL)
                if load_custom_indicators or load_custom_all:
                    data_types.append(DataType.INDICATORS)
                if load_custom_all:
                    data_types.append(DataType.FUNDAMENTALS)
                
                result = refresh_manager.refresh_data(
                    symbol=custom_symbol,
                    data_types=data_types,
                    mode=RefreshMode.ON_DEMAND,
                    force=True,
                )

                if result.total_failed == 0:
                    st.success(
                        f"✅ Loaded data for {custom_symbol} (success={result.total_successful}, skipped={result.total_skipped})"
                    )
                    # Clear cache to force reload
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"❌ Failed to load data for {custom_symbol}. See details below.")
                    st.json(result.to_dict())
                    
            except Exception as e:
                st.error(f"❌ Error loading data for {custom_symbol}: {str(e)}")

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

if load_fundamentals:
    with st.spinner(f"Loading fundamentals for {symbol}..."):
        try:
            # Clear cache BEFORE refreshing to ensure fresh data
            st.cache_data.clear()
            # Also clear the specific data availability cache
            get_data_availability.clear()
            refresh_manager = DataRefreshManager()
            result = refresh_manager.refresh_data(
                symbol=symbol,
                data_types=[DataType.FUNDAMENTALS],
                mode=RefreshMode.ON_DEMAND,
                force=True,
            )

            if result.total_failed == 0:
                st.success(
                    f"✅ Loaded fundamentals for {symbol} (success={result.total_successful}, skipped={result.total_skipped})"
                )
                # Clear cache to force reload
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"❌ Failed to load fundamentals for {symbol}. See details below.")
                st.json(result.to_dict())
        except Exception as e:
            st.error(f"❌ Error loading fundamentals: {e}")
            logger.error(f"Error loading fundamentals for {symbol}: {e}")

if clear_cache:
    st.cache_data.clear()
    get_data_availability.clear()
    st.success("✅ Cache cleared! Data will be refreshed on next load.")
    st.rerun()

# Create main tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
    "🔍 Data Validation",
    "📊 Stock Insights", 
    "📈 Data Availability",
    "📚 Fundamentals & Indicators",
    "💰 Growth Quality Analysis",
    "🧠 Signal Engines",
    "🧾 Audit",
    "📅 Earnings & News",
    "📋 Enhanced Watchlist",
    "💼 Enhanced Portfolio",
    "🔎 Screeners",
])

with tab1:
    display_data_validation(symbol, days_back)

with tab2:
    display_stock_insights(symbol)

with tab3:
    display_data_availability(symbol)

with tab4:
    display_fundamentals_and_indicators(symbol)

with tab5:
    display_growth_quality_analysis(symbol)

with tab6:
    render_signal_engine_interface(symbol)

with tab7:
    display_audit(symbol)

with tab8:
    display_earnings_and_news(symbol)

with tab9:
    display_enhanced_watchlist()

with tab10:
    display_enhanced_portfolio()

with tab11:
    display_screeners(available_symbols)

# Footer
st.markdown("---")
st.markdown("📊 Trading System Dashboard | Data Validation & Stock Insights")
