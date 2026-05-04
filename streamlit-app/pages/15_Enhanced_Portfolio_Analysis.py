"""
Enhanced Portfolio Analysis Page with Database Persistence and Audit Trails
Industry-standard portfolio management with user authentication, multiple portfolios, and scheduling
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, date, time
import time as time_module
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
import sys
from typing import List, Dict, Any, Optional

# Add the current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import portfolio utilities and shared components
try:
    from utils.portfolio_utils import PortfolioManager, PortfolioAnalyzer, PortfolioVisualizer
except ImportError:
    # Fallback for Docker environment
    PortfolioManager = None
    PortfolioAnalyzer = None
    PortfolioVisualizer = None

from utils import setup_page_config, render_sidebar
from api_client import APIClient, APIError
from api_config import api_config
from api_client import get_go_api_client
from shared_functions import get_portfolio_data

# Import shared analysis display component
from components.analysis_display import display_signal_analysis, display_no_data_message

# Initialize API clients
go_client = get_go_api_client()
# Always set correct URL based on environment
import os
if os.path.exists('/.dockerenv'):
    go_client.base_url = "http://go-api:8000"
else:
    go_client.base_url = "http://localhost:8000"
print(f"DEBUG PORTFOLIO: final go_client.base_url = {go_client.base_url}")

if os.path.exists('/.dockerenv'):
    python_worker_base_url = "http://python-worker:8001"
else:
    python_worker_base_url = "http://127.0.0.1:8001"

# ========================================
# Helper Functions for DRY Code
# ========================================

def create_portfolio_selector(portfolios: List[Dict[str, Any]], key: str = "portfolio") -> Dict[str, Any]:
    """Create standardized portfolio selector dropdown"""
    portfolio_options = {f"{p['name']} ({p['portfolio_type'].title()})": p for p in portfolios}
    selected_name = st.selectbox(
        "Select Portfolio",
        options=list(portfolio_options.keys()),
        key=f"{key}_selector",
        help="Choose a portfolio to manage"
    )
    return portfolio_options[selected_name]

def format_currency(value: Any, default: str = "$0.00") -> str:
    """Safely format currency values"""
    try:
        if value is None or value == "":
            return default
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return str(value) if value else default

def format_percentage(value: Any, default: str = "0.00%") -> str:
    """Safely format percentage values"""
    try:
        if value is None or value == "":
            return default
        return f"{float(value):+.2f}%"
    except (ValueError, TypeError):
        return str(value) if value else default

def format_shares(value: Any, default: str = "0") -> str:
    """Safely format share values"""
    try:
        if value is None or value == "":
            return default
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return str(value) if value else default

def create_portfolio_metrics(portfolio: Dict[str, Any]) -> None:
    """Create standardized portfolio metrics display"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Portfolio Type", portfolio['portfolio_type'].title())
    
    with col2:
        initial_capital = portfolio.get('initial_capital', 0)
        try:
            initial_capital = float(initial_capital)
            st.metric("Initial Capital", f"${initial_capital:,.2f}")
        except (ValueError, TypeError):
            st.metric("Initial Capital", str(initial_capital))
    
    with col3:
        st.metric("Holdings", portfolio.get('holdings_count', 0))
    
    with col4:
        status = "🟢 Active" if portfolio.get('is_active', True) else "🔴 Inactive"
        st.metric("Status", status)


def run_v3_portfolio_decisions_python_worker(
    portfolio_id: str,
    *,
    refresh: bool,
    data_types: Optional[List[str]],
    force: bool,
    as_of_date: Optional[str],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "portfolio_id": portfolio_id,
        "refresh": bool(refresh),
        "data_types": data_types,
        "force": bool(force),
        "as_of_date": as_of_date,
    }

    url = f"{python_worker_base_url}/api/v1/trading-v3/decisions/run-portfolio"
    timeout_seconds = int(os.getenv("PYTHON_WORKER_TIMEOUT_SECONDS", "1800"))
    resp = requests.post(url, json=payload, timeout=timeout_seconds)
    if resp.status_code >= 400:
        raise Exception(f"python-worker error {resp.status_code}: {resp.text[:300]}")
    out = resp.json()
    if not isinstance(out, dict):
        raise Exception("python-worker returned invalid response")
    return out


def list_v3_decision_dates_python_worker(limit: int = 60) -> List[str]:
    url = f"{python_worker_base_url}/api/v1/trading-v3/decisions/dates"
    resp = requests.get(url, params={"limit": int(limit)}, timeout=30)
    if resp.status_code >= 400:
        raise Exception(f"python-worker error {resp.status_code}: {resp.text[:300]}")
    out = resp.json()
    dates = (out or {}).get("dates") or []
    return [str(d) for d in dates if d]


def list_v3_decisions_by_date_python_worker(
    *,
    as_of_date: str,
    portfolio_id: Optional[str],
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    url = f"{python_worker_base_url}/api/v1/trading-v3/decisions/by-date"
    params: Dict[str, Any] = {"as_of_date": as_of_date, "limit": int(limit)}
    if portfolio_id:
        params["portfolio_id"] = portfolio_id
    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code >= 400:
        raise Exception(f"python-worker error {resp.status_code}: {resp.text[:300]}")
    out = resp.json()
    decisions = (out or {}).get("decisions") or []
    return [d for d in decisions if isinstance(d, dict)]

def create_holdings_table(holdings: List[Dict[str, Any]], show_actions: bool = True) -> pd.DataFrame:
    """Create standardized holdings table with formatting"""
    holdings_data = []
    
    for holding in holdings:
        if not isinstance(holding, dict):
            continue

        symbol = (
            holding.get('symbol')
            or holding.get('stock_symbol')
            or holding.get('ticker')
            or holding.get('code')
        )
        symbol = str(symbol).strip().upper() if symbol else ""

        shares_val = (
            holding.get('shares_held')
            if holding.get('shares_held') is not None
            else holding.get('quantity')
        )

        # Get signal with color formatting
        signal = get_stock_signal(symbol)
        signal_colors = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}
        color = signal_colors.get(signal, '⚪')
        formatted_signal = f"{color} {signal}"
        
        # Safe numeric formatting
        avg_cost = holding.get('average_cost', 0)
        current_price = holding.get('current_price')
        market_value = holding.get('market_value')
        pnl_pct = holding.get('unrealized_pnl_pct')
        
        holdings_data.append({
            'Symbol': symbol or 'N/A',
            'Shares': format_shares(shares_val),
            'Avg Cost': format_currency(avg_cost),
            'Current Price': format_currency(current_price),
            'Market Value': format_currency(market_value),
            'P&L': format_percentage(pnl_pct),
            'Signal': formatted_signal
        })
    
    return pd.DataFrame(holdings_data)

def create_portfolio_action_buttons(portfolio: Dict[str, Any]) -> None:
    """Create standardized portfolio action buttons"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("✏️ Edit Portfolio", key=f"edit_{portfolio['id']}"):
            st.session_state.edit_portfolio = portfolio['id']
    
    with col2:
        if st.button("🗑️ Delete Portfolio", key=f"delete_{portfolio['id']}"):
            if portfolio.get('holdings_count', 0) == 0:
                delete_portfolio(portfolio['id'])
                st.success("Portfolio deleted successfully!")
                st.rerun()
            else:
                st.error("Cannot delete portfolio with holdings. Remove all holdings first.")
    
    with col3:
        if st.button("📊 View Analysis", key=f"analyze_{portfolio['id']}"):
            st.session_state.selected_portfolio = portfolio['id']
            st.session_state.show_analysis = True

    with col4:
        if st.button("🔁 Run Rebalance", key=f"rebalance_{portfolio['id']}"):
            payload: Dict[str, Any] = {"profile": "weekly_rebalance"}
            try:
                with st.spinner("Starting rebalance run..."):
                    resp = go_client.post(
                        f"api/v1/portfolios/{portfolio['id']}/rebalance-run",
                        json_data=payload,
                        timeout=30,
                    )
                if isinstance(resp, dict) and resp.get("run_id"):
                    st.session_state["epa_last_rebalance_run_id"] = str(resp.get("run_id"))
                    st.success(f"✅ Rebalance run started (run_id={resp.get('run_id')})")
                else:
                    st.error("❌ Failed to start rebalance run")
                    st.json(resp)
            except Exception as e:
                st.error(f"❌ Failed to start rebalance run: {e}")


def _load_users() -> List[Dict[str, Any]]:
    resp = go_client.get("api/v1/users")
    return (resp or {}).get("users") or []


def _resolve_default_user() -> Dict[str, Any]:
    # Align with streamlit Portfolio page default
    base_user_id = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
    try:
        users = _load_users()
        for u in users or []:
            if not isinstance(u, dict):
                continue
            if (u.get("user_id") or u.get("id")) == base_user_id:
                return u
    except Exception:
        pass

    return {
        "user_id": base_user_id,
        "id": base_user_id,
        "username": "default_user",
        "role": "user",
    }


def _load_portfolios_for_user(user_id: str) -> List[Dict[str, Any]]:
    if not user_id:
        return []
    resp = go_client.get(f"api/v1/portfolios/user/{user_id}")
    return (resp or {}).get("portfolios") or []


def _normalize_portfolio_for_ui(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": p.get("id"),
        "name": p.get("name") or p.get("portfolio_name") or p.get("id"),
        "description": p.get("notes") or "",
        "portfolio_type": (p.get("portfolio_type") or "custom"),
        "initial_capital": p.get("initial_capital"),
        "holdings_count": p.get("holdings_count") or 0,
    }

# ========================================
# Portfolio Management Functions
# ========================================

def get_user_portfolios() -> List[Dict[str, Any]]:
    """Get all portfolios for current user"""
    try:
        user = st.session_state.get("current_user") or {}
        user_id = user.get("user_id") or user.get("id")
        portfolios = _load_portfolios_for_user(user_id)
        return [_normalize_portfolio_for_ui(p) for p in portfolios if p]
    except Exception as e:
        st.error(f"Error loading portfolios: {str(e)}")
        return []

def create_portfolio(name: str, description: str = "", portfolio_type: str = "custom", 
                    initial_capital: float = 10000.0) -> Optional[Dict[str, Any]]:
    """Create a new portfolio"""
    try:
        user = st.session_state.get("current_user") or {}
        user_id = user.get("user_id") or user.get("id")
        if not user_id:
            st.error("Select a user first")
            return None

        created = go_client.post(
            f"api/v1/portfolio/{user_id}",
            json_data={"portfolio_name": name, "notes": (description or "").strip() or None},
        )
        return _normalize_portfolio_for_ui(created or {})
    except Exception as e:
        st.error(f"Error creating portfolio: {str(e)}")
        return None

def get_portfolio_holdings(portfolio_id: str) -> List[Dict[str, Any]]:
    """Get holdings for a portfolio with timeout handling"""
    try:
        user = st.session_state.get("current_user") or {}
        user_id = user.get("user_id") or user.get("id")
        if not user_id:
            return []

        data = get_portfolio_data(user_id, portfolio_id, subscription_level=st.session_state.get("subscription_level") or "basic")
        holdings = (data or {}).get("holdings") or []
        return holdings
    except Exception as e:
        st.error(f"Error loading holdings: {str(e)}")
        return []

def add_portfolio_holding(portfolio_id: str, symbol: str, asset_type: str = "stock", 
                         shares_held: float = 0, average_cost: float = 0) -> Optional[Dict[str, Any]]:
    """Add a holding to portfolio with timeout handling"""
    try:
        user = st.session_state.get("current_user") or {}
        user_id = user.get("user_id") or user.get("id")
        if not user_id:
            st.error("Select a user first")
            return None

        created = go_client.post(
            f"api/v1/portfolio/{user_id}/{portfolio_id}/holdings",
            json_data={
                "stock_symbol": symbol.upper(),
                "quantity": float(shares_held),
                "avg_entry_price": float(average_cost),
                "position_type": "long",
                "purchase_date": date.today().strftime("%Y-%m-%d"),
            },
        )
        return created
    except Exception as e:
        st.error(f"Error adding holding: {str(e)}")
        return None

def analyze_portfolio(portfolio_id: str, target_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Run analysis on portfolio with timeout handling"""
    try:
        payload: Dict[str, Any] = {}
        if target_date:
            payload["target_date"] = target_date.strftime("%Y-%m-%d")
        else:
            payload["target_date"] = date.today().strftime("%Y-%m-%d")

        resp = go_client.post(
            f"api/v1/portfolios/{portfolio_id}/analysis-run",
            json_data=payload,
            timeout=30,
        )
        if isinstance(resp, dict) and resp.get("run_id"):
            st.session_state["epa_last_analysis_run_id"] = str(resp.get("run_id"))
        return resp if isinstance(resp, dict) else {"success": False, "error": "invalid response"}
    except Exception as e:
        st.error(f"❌ Failed to start portfolio analysis run: {e}")
        return {"success": False, "error": str(e)}


def fetch_analysis_profiles() -> Dict[str, Any]:
    try:
        resp = go_client.get("api/v1/admin/analysis-profiles")
        return resp if isinstance(resp, dict) else {}
    except Exception:
        return {}


def analyze_portfolio_with_profile(
    portfolio_id: str,
    profile: str,
    target_date: Optional[date] = None,
    symbols: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    try:
        payload: Dict[str, Any] = {"profile": (profile or "").strip()}
        if target_date:
            payload["target_date"] = target_date.strftime("%Y-%m-%d")
        else:
            payload["target_date"] = date.today().strftime("%Y-%m-%d")
        if symbols:
            payload["symbols"] = symbols

        resp = go_client.post(
            f"api/v1/portfolios/{portfolio_id}/analysis-run",
            json_data=payload,
            timeout=30,
        )
        if isinstance(resp, dict) and resp.get("run_id"):
            st.session_state["epa_last_analysis_run_id"] = str(resp.get("run_id"))
        return resp if isinstance(resp, dict) else {"success": False, "error": "invalid response"}
    except Exception as e:
        st.error(f"❌ Failed to start portfolio analysis run: {e}")
        return {"success": False, "error": str(e)}


def _format_ts(v: Any) -> str:
    if not v:
        return ""
    try:
        s = str(v)
        return s.replace("T", " ").replace("Z", "")
    except Exception:
        return str(v)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        if isinstance(v, bool):
            return float(default)
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if not s:
            return float(default)
        return float(s)
    except Exception:
        return float(default)


def fetch_run(run_id: str) -> Dict[str, Any]:
    if not run_id:
        return {}
    # Note: analysis runs and data-load runs both persist into the same audit tables
    # and can be fetched via this unified endpoint.
    resp = go_client.get(f"api/v1/data-load/runs/{run_id}")
    return resp if isinstance(resp, dict) else {}


def fetch_run_notifications(run_id: str) -> Dict[str, Any]:
    if not run_id:
        return {}
    resp = go_client.get(f"api/v1/notifications/queue/by-correlation/{run_id}")
    return resp if isinstance(resp, dict) else {}


def cancel_run(run_id: str) -> Dict[str, Any]:
    if not run_id:
        return {}
    resp = go_client.post(f"api/v1/data-load/runs/{run_id}/cancel", json_data={})
    return resp if isinstance(resp, dict) else {}


def fetch_schedules() -> Dict[str, Any]:
    resp = go_client.get("api/v1/schedules")
    return resp if isinstance(resp, dict) else {}


def create_schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = go_client.post("api/v1/schedules", json_data=payload)
    return resp if isinstance(resp, dict) else {}


def update_schedule(schedule_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = go_client.patch(f"api/v1/schedules/{schedule_id}", json_data=payload)
    return resp if isinstance(resp, dict) else {}


def delete_schedule(schedule_id: str) -> Dict[str, Any]:
    resp = go_client.delete(f"api/v1/schedules/{schedule_id}")
    return resp if isinstance(resp, dict) else {}


def run_now_schedule(schedule_id: str) -> Dict[str, Any]:
    resp = go_client.post(f"api/v1/schedules/{schedule_id}/run-now")
    return resp if isinstance(resp, dict) else {}


def fetch_schedule_runs(schedule_id: str, limit: int = 10) -> Dict[str, Any]:
    resp = go_client.get(f"api/v1/schedules/{schedule_id}/runs?limit={int(limit)}")
    return resp if isinstance(resp, dict) else {}


def show_schedules_tab(portfolios: List[Dict[str, Any]]):
    st.markdown("## ⏰ Schedules (Admin)")
    st.caption("Backed by Go API: /api/v1/schedules and /api/v1/scheduler/tick")

    profiles_job_resp: Dict[str, Any] = {}
    profiles_job_map: Dict[str, Any] = {}
    try:
        profiles_job_resp = go_client.get("api/v1/admin/job-profiles")
        profiles_job_map = (profiles_job_resp or {}).get("profiles") or {}
    except Exception:
        profiles_job_map = {}
    job_profile_names = sorted([str(k) for k in profiles_job_map.keys()])
    if not job_profile_names:
        job_profile_names = ["intraday_alerts", "intraday_alerts_with_intraday_prices", "daily_analysis", "bootstrap"]

    profiles_analysis_resp: Dict[str, Any] = fetch_analysis_profiles()
    profiles_analysis_map = (profiles_analysis_resp or {}).get("profiles") or {}
    analysis_profile_names = sorted([str(k) for k in profiles_analysis_map.keys()])
    if not analysis_profile_names:
        analysis_profile_names = ["daily_signals", "intraday_signals", "weekly_rebalance"]

    st.markdown("### ✅ Recommended schedules")
    st.caption("Creates 5 low-bandwidth schedules (data_load) using the new profiles and recommended cadences")

    auto_col1, auto_col2 = st.columns([2, 1])
    with auto_col1:
        if portfolios:
            auto_portfolio_options = {f"{p.get('name')} ({p.get('portfolio_type', '').title()})": p for p in portfolios}
            auto_selected_portfolio_label = st.selectbox(
                "Portfolio for auto-create",
                options=list(auto_portfolio_options.keys()),
                key="epa_sched_auto_portfolio",
            )
            auto_portfolio_id = str((auto_portfolio_options.get(auto_selected_portfolio_label) or {}).get("id") or "")
        else:
            auto_portfolio_id = st.text_input("Portfolio ID (UUID)", key="epa_sched_auto_portfolio_id")

    with auto_col2:
        auto_create_clicked = st.button(
            "Create 5 schedules",
            type="primary",
            width='stretch',
            key="epa_sched_auto_create",
        )

    if auto_create_clicked:
        if not auto_portfolio_id.strip():
            st.error("Portfolio ID is required")
        else:
            recommended = [
                {
                    "profile": "intraday_prices_only",
                    "cron_expression": "*/15 9-16 * * 1-5",
                    "timezone": "America/New_York",
                },
                {
                    "profile": "intraday_news_hourly",
                    "cron_expression": "0 * * * 1-5",
                    "timezone": "America/New_York",
                },
                {
                    "profile": "daily_market_intel",
                    "cron_expression": "0 18 * * 1-5",
                    "timezone": "America/New_York",
                },
                {
                    "profile": "weekly_fundamentals",
                    "cron_expression": "0 9 * * 6",
                    "timezone": "America/New_York",
                },
                {
                    "profile": "monthly_reference_backfill",
                    "cron_expression": "0 9 1 * *",
                    "timezone": "America/New_York",
                },
            ]

            existing_resp = {}
            try:
                existing_resp = fetch_schedules()
            except Exception:
                existing_resp = {}
            existing = (existing_resp or {}).get("schedules") or []
            existing = existing if isinstance(existing, list) else []

            def _already_exists(item: Dict[str, Any]) -> bool:
                for s in existing:
                    if not isinstance(s, dict):
                        continue
                    if str(s.get("portfolio_id") or "") != str(auto_portfolio_id):
                        continue
                    if str(s.get("kind") or "") != "data_load":
                        continue
                    if str(s.get("profile") or "") != str(item.get("profile") or ""):
                        continue
                    if str(s.get("cron_expression") or "") != str(item.get("cron_expression") or ""):
                        continue
                    if str(s.get("timezone") or "") != str(item.get("timezone") or ""):
                        continue
                    return True
                return False

            created = 0
            skipped = 0
            failures: List[Dict[str, Any]] = []
            with st.spinner("Creating schedules..."):
                for item in recommended:
                    if _already_exists(item):
                        skipped += 1
                        continue
                    payload = {
                        "kind": "data_load",
                        "portfolio_id": auto_portfolio_id,
                        "profile": item["profile"],
                        "cron_expression": item["cron_expression"],
                        "timezone": item["timezone"],
                        "enabled": True,
                        "config": {},
                    }
                    try:
                        resp = create_schedule(payload)
                        if resp and resp.get("schedule"):
                            created += 1
                        else:
                            failures.append({"profile": item["profile"], "response": resp})
                    except Exception as e:
                        failures.append({"profile": item["profile"], "error": str(e)})

            if failures:
                st.error(f"Created {created}, skipped {skipped}, failed {len(failures)}")
                st.json(failures)
            else:
                st.success(f"✅ Created {created}, skipped {skipped}")
                st.rerun()

    with st.expander("➕ Create Schedule", expanded=False):
        preset_options = {
            "Custom": {"cron": "0 9 * * 1-5", "tz": "America/New_York"},
            "Intraday prices (every 15m, market hours)": {"cron": "*/15 9-16 * * 1-5", "tz": "America/New_York"},
            "Intraday news (every 60m, weekdays)": {"cron": "0 * * * 1-5", "tz": "America/New_York"},
            "Daily (6pm ET, weekdays)": {"cron": "0 18 * * 1-5", "tz": "America/New_York"},
            "Weekly (Sat 9am ET)": {"cron": "0 9 * * 6", "tz": "America/New_York"},
            "Monthly (1st 9am ET)": {"cron": "0 9 1 * *", "tz": "America/New_York"},
        }
        selected_preset = st.selectbox(
            "Preset",
            options=list(preset_options.keys()),
            index=0,
            key="epa_sched_preset",
        )

        kind = st.selectbox(
            "Kind",
            options=["data_load", "analysis_run", "rebalance_run"],
            index=0,
            key="epa_sched_kind",
        )

        if portfolios:
            portfolio_options = {f"{p.get('name')} ({p.get('portfolio_type', '').title()})": p for p in portfolios}
            selected_portfolio_label = st.selectbox(
                "Portfolio",
                options=list(portfolio_options.keys()),
                key="epa_sched_portfolio",
            )
            portfolio_id = str((portfolio_options.get(selected_portfolio_label) or {}).get("id") or "")
        else:
            portfolio_id = st.text_input("Portfolio ID (UUID)", key="epa_sched_portfolio_id")

        if kind == "data_load":
            profile = st.selectbox("Profile", options=job_profile_names, index=0, key="epa_sched_profile_job")
        elif kind == "analysis_run":
            profile = st.selectbox("Profile", options=analysis_profile_names, index=0, key="epa_sched_profile_analysis")
        else:
            profile = st.selectbox("Profile", options=["weekly_rebalance"], index=0, key="epa_sched_profile_rebalance")

        preset_default = preset_options.get(selected_preset) or preset_options["Custom"]
        cron_expression = st.text_input(
            "Cron (5-field)",
            value=str(preset_default.get("cron") or "0 9 * * 1-5"),
            help="minute hour day-of-month month day-of-week",
            key="epa_sched_cron",
        )
        timezone = st.text_input(
            "Timezone",
            value=str(preset_default.get("tz") or "America/New_York"),
            key="epa_sched_tz",
        )
        enabled = st.checkbox("Enabled", value=True, key="epa_sched_enabled")

        symbols_csv = st.text_input(
            "Symbols (optional, CSV)",
            value="",
            help="Leave empty to use all symbols in portfolio",
            key="epa_sched_symbols",
        )

        config: Dict[str, Any] = {}
        symbols = [s.strip().upper() for s in (symbols_csv or "").split(",") if s.strip()]
        if symbols:
            config["symbols"] = symbols

        if kind == "data_load":
            force = st.checkbox("Force", value=False, key="epa_sched_force")
            config["force"] = force
        if kind in {"analysis_run", "rebalance_run"}:
            target_date = st.text_input("Target date (YYYY-MM-DD, optional)", value="", key="epa_sched_target_date")
            if target_date.strip():
                config["target_date"] = target_date.strip()
        if kind == "analysis_run":
            asset_type = st.selectbox("Asset type", options=["stock", "etf"], index=0, key="epa_sched_asset_type")
            config["asset_type"] = asset_type

        create_clicked = st.button("Create", type="primary", width='stretch', key="epa_sched_create")
        if create_clicked:
            payload = {
                "kind": kind,
                "portfolio_id": portfolio_id,
                "profile": profile,
                "cron_expression": cron_expression,
                "timezone": timezone,
                "enabled": enabled,
                "config": config,
            }
            with st.spinner("Creating schedule..."):
                try:
                    resp = create_schedule(payload)
                    if resp and resp.get("schedule"):
                        st.success("✅ Schedule created")
                        st.rerun()
                    else:
                        st.error("❌ Failed to create schedule")
                        st.json(resp)
                except Exception as e:
                    st.error(f"Create failed: {e}")

    st.markdown("### 📋 Existing Schedules")
    schedules_resp: Dict[str, Any] = {}
    try:
        schedules_resp = fetch_schedules()
    except Exception as e:
        st.error(f"Failed to fetch schedules: {e}")
        schedules_resp = {}

    schedules = (schedules_resp or {}).get("schedules") or []
    if not isinstance(schedules, list):
        schedules = []

    if schedules:
        rows = []
        for s in schedules:
            if not isinstance(s, dict):
                continue
            rows.append({
                "schedule_id": s.get("schedule_id"),
                "kind": s.get("kind"),
                "portfolio_id": s.get("portfolio_id"),
                "profile": s.get("profile"),
                "cron_expression": s.get("cron_expression"),
                "timezone": s.get("timezone"),
                "enabled": s.get("enabled"),
                "next_run_at": _format_ts(s.get("next_run_at")),
                "last_run_at": _format_ts(s.get("last_run_at")),
                "last_run_id": s.get("last_run_id"),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, width='stretch', hide_index=True)

        st.markdown("### ⚙️ Manage")
        sched_ids = [str(s.get("schedule_id")) for s in schedules if isinstance(s, dict) and s.get("schedule_id")]
        selected_id = st.selectbox("Schedule", options=sched_ids, key="epa_sched_manage_select")
        selected_obj = next((x for x in schedules if isinstance(x, dict) and str(x.get("schedule_id")) == str(selected_id)), {})
        manage_col1, manage_col2, manage_col3, manage_col4 = st.columns([1, 1, 1, 1])

        with st.expander("✏️ Edit selected schedule", expanded=False):
            kind_val = str((selected_obj or {}).get("kind") or "")
            current_profile = str((selected_obj or {}).get("profile") or "")
            if kind_val == "data_load":
                profile_options = job_profile_names
            elif kind_val == "analysis_run":
                profile_options = analysis_profile_names
            elif kind_val == "rebalance_run":
                profile_options = ["weekly_rebalance"]
            else:
                profile_options = sorted(list(set(job_profile_names + analysis_profile_names)))
            if current_profile and current_profile not in profile_options:
                profile_options = [current_profile] + profile_options

            current_config_obj = (selected_obj or {}).get("config")
            try:
                config_default = json.dumps(current_config_obj or {}, indent=2)
            except Exception:
                config_default = "{}"

            with st.form(key="epa_sched_edit_form"):
                edit_cron = st.text_input(
                    "Cron (5-field)",
                    value=str((selected_obj or {}).get("cron_expression") or ""),
                    key="epa_sched_edit_cron",
                )
                edit_tz = st.text_input(
                    "Timezone",
                    value=str((selected_obj or {}).get("timezone") or "UTC"),
                    key="epa_sched_edit_tz",
                )
                edit_profile = st.selectbox(
                    "Profile",
                    options=profile_options,
                    index=max(0, profile_options.index(current_profile)) if current_profile in profile_options else 0,
                    key="epa_sched_edit_profile",
                )
                edit_enabled = st.checkbox(
                    "Enabled",
                    value=bool((selected_obj or {}).get("enabled", True)),
                    key="epa_sched_edit_enabled",
                )
                edit_config_text = st.text_area(
                    "Config (JSON)",
                    value=config_default,
                    height=180,
                    key="epa_sched_edit_config",
                )
                submitted = st.form_submit_button("💾 Save changes", width='stretch')

            if submitted:
                try:
                    cfg = json.loads(edit_config_text or "{}")
                    if not isinstance(cfg, dict):
                        raise ValueError("config must be a JSON object")
                except Exception as e:
                    st.error(f"Invalid config JSON: {e}")
                else:
                    payload = {
                        "cron_expression": edit_cron,
                        "timezone": edit_tz,
                        "profile": edit_profile,
                        "enabled": edit_enabled,
                        "config": cfg,
                    }
                    with st.spinner("Updating schedule..."):
                        resp = update_schedule(selected_id, payload)
                        if resp and resp.get("schedule"):
                            st.success("✅ Updated")
                            st.rerun()
                        else:
                            st.error("❌ Update failed")
                            st.json(resp)

        with manage_col1:
            if st.button("▶️ Run now", width='stretch', key="epa_sched_run_now"):
                with st.spinner("Triggering run..."):
                    resp = run_now_schedule(selected_id)
                    run_id = (resp or {}).get("run_id")
                    if run_id:
                        st.session_state["epa_last_analysis_run_id"] = str(run_id)
                        st.success(f"✅ Run started: {run_id}")
                    else:
                        st.error("❌ Failed to trigger run")
                        st.json(resp)

        with manage_col2:
            new_enabled = st.checkbox(
                "Enabled",
                value=bool(selected_obj.get("enabled", True)),
                key="epa_sched_manage_enabled",
            )
            if st.button("💾 Save", width='stretch', key="epa_sched_save"):
                with st.spinner("Updating..."):
                    resp = update_schedule(selected_id, {"enabled": new_enabled})
                    if resp and resp.get("schedule"):
                        st.success("✅ Updated")
                        st.rerun()
                    else:
                        st.error("❌ Update failed")
                        st.json(resp)

        with manage_col3:
            if st.button("🗑️ Delete", width='stretch', key="epa_sched_delete"):
                with st.spinner("Deleting..."):
                    resp = delete_schedule(selected_id)
                    if resp and resp.get("success"):
                        st.success("✅ Deleted")
                        st.rerun()
                    else:
                        st.error("❌ Delete failed")
                        st.json(resp)

        with manage_col4:
            if st.button("🔄 Tick now", width='stretch', key="epa_sched_tick"):
                with st.spinner("Calling scheduler tick..."):
                    resp = go_client.post("api/v1/scheduler/tick", json_data={})
                    st.json(resp)

        st.markdown("### 🧾 Last 10 runs")
        with st.expander("Debug: schedule runs", expanded=False):
            st.write(f"Go API base_url: {getattr(go_client, 'base_url', 'unknown')}")
            st.write(f"Selected schedule_id: {selected_id}")

        runs_resp: Dict[str, Any] = {}
        try:
            runs_resp = fetch_schedule_runs(selected_id, limit=10)
        except Exception as e:
            st.error(f"Failed to fetch schedule runs: {e}")
            runs_resp = {}

        with st.expander("Debug: raw /runs response", expanded=False):
            st.json(runs_resp)

        runs = (runs_resp or {}).get("runs") or []
        if isinstance(runs, list) and runs:
            header_c1, header_c2, header_c3, header_c4, header_c5, header_c6 = st.columns([3, 1, 2, 2, 1, 1])
            header_c1.caption("run_id")
            header_c2.caption("status")
            header_c3.caption("started_at")
            header_c4.caption("finished_at")
            header_c5.caption("inspect")
            header_c6.caption("cancel")

            for idx, r in enumerate(runs):
                if not isinstance(r, dict):
                    continue
                rid = str(r.get("run_id") or "").strip()
                status = str(r.get("status") or "")
                started_at = _format_ts(r.get("started_at"))
                finished_at = _format_ts(r.get("finished_at"))

                c1, c2, c3, c4, c5, c6 = st.columns([3, 1, 2, 2, 1, 1])
                c1.code(rid or "")
                c2.write(status)
                c3.write(started_at)
                c4.write(finished_at)

                inspect_clicked = c5.button("Select", width='stretch', key=f"epa_sched_run_select_{idx}_{rid}")
                if inspect_clicked and rid:
                    st.session_state["epa_last_analysis_run_id"] = rid
                    st.session_state["epa_run_id"] = rid
                    try:
                        st.session_state["epa_last_run_details"] = fetch_run(rid)
                    except Exception:
                        pass
                    st.rerun()

                cancel_clicked = c6.button(
                    "Cancel",
                    width='stretch',
                    disabled=not (rid and status.lower() == "running"),
                    key=f"epa_sched_run_cancel_{idx}_{rid}",
                )
                if cancel_clicked and rid:
                    try:
                        resp = cancel_run(rid)
                        if isinstance(resp, dict) and resp.get("success"):
                            st.success(f"✅ Cancel requested for {rid}")
                            st.rerun()
                        else:
                            st.error("❌ Cancel request failed")
                            st.json(resp)
                    except Exception as e:
                        st.error(f"Cancel request failed: {e}")
        else:
            st.caption("No runs found for this schedule yet.")
    else:
        st.caption("No schedules found.")

def get_symbol_signal_history(symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get signal history for a symbol with timeout handling"""
    _ = symbol
    _ = limit
    return []

def get_schedule_runs(schedule_id: str, limit: int = 2) -> List[Dict[str, Any]]:
    """Get last N runs for a schedule"""
    try:
        response = go_client.get(f"api/v1/schedules/{schedule_id}/runs")
        if response and response.get("runs"):
            return response["runs"][:limit]  # Return last N runs
        return []
    except Exception as e:
        st.error(f"❌ Error loading schedule runs: {e}")
        return []

def cancel_run(run_id: str) -> bool:
    """Cancel a running run"""
    try:
        response = go_client.post(f"api/v1/data-load/runs/{run_id}/cancel")
        return response is not None
    except Exception as e:
        st.error(f"❌ Error canceling run: {e}")
        return False

def get_portfolio_schedule_runs(schedule_id: str, limit: int = 2) -> List[Dict[str, Any]]:
    """Get last N runs for a portfolio schedule"""
    try:
        response = go_client.get(f"api/v1/portfolio-schedules/{schedule_id}/runs")
        if response and response.get("runs"):
            return response["runs"][:limit]  # Return last N runs
        return []
    except Exception as e:
        st.error(f"❌ Error loading portfolio schedule runs: {e}")
        return []

def cancel_portfolio_run(run_id: str) -> bool:
    """Cancel a running portfolio analysis run"""
    try:
        response = go_client.post(f"api/v1/portfolio-analysis/runs/{run_id}/cancel")
        return response is not None
    except Exception as e:
        st.error(f"❌ Error canceling portfolio run: {e}")
        return False

def update_system_schedule(schedule_id: str, updates: Dict[str, Any]) -> bool:
    """Update a system schedule configuration"""
    try:
        response = go_client.patch(f"api/v1/schedules/{schedule_id}", updates)
        return response is not None
    except Exception as e:
        st.error(f"❌ Error updating schedule: {e}")
        return False

def get_portfolio_schedules(portfolio_id: str) -> List[Dict[str, Any]]:
    """Get scheduled analyses for portfolio using new API"""
    try:
        response = go_client.get(f"api/v1/portfolio-schedules/list?portfolio_id={portfolio_id}")
        if response and response.get("schedules"):
            return response["schedules"]
        return []
    except Exception as e:
        st.error(f"❌ Error loading schedules: {e}")
        return []

def create_portfolio_schedule(portfolio_id: str, schedule_type: str, schedule_time: str, schedule_day: Optional[int]) -> Optional[Dict[str, Any]]:
    """Create a scheduled analysis using new API"""
    try:
        payload = {
            "portfolio_id": portfolio_id,
            "schedule_type": schedule_type,
            "schedule_time": schedule_time.strftime("%H:%M"),
            "notification_preferences": {
                "push": False,
                "email": True
            }
        }
        
        if schedule_day:
            payload["schedule_day"] = schedule_day
        
        response = go_client.post("api/v1/portfolio-schedules/", json_data=payload)
        if response and response.get("success"):
            return response
        else:
            st.error(f"❌ Failed to create schedule: {response.get('error', 'Unknown error')}")
            return None
    except Exception as e:
        st.error(f"❌ Error creating schedule: {e}")
        return None

def delete_portfolio_schedule(schedule_id: str) -> bool:
    """Delete a scheduled analysis using new API"""
    try:
        response = go_client.delete(f"api/v1/portfolio-schedules/{schedule_id}")
        return response and response.get("success", False)
    except Exception as e:
        st.error(f"❌ Error deleting schedule: {e}")
        return False

def toggle_portfolio_schedule(schedule_id: str) -> bool:
    """Toggle schedule active/paused status using new API"""
    try:
        response = go_client.post(f"api/v1/portfolio-schedules/{schedule_id}/toggle")
        return response and response.get("success", False)
    except Exception as e:
        st.error(f"❌ Error toggling schedule: {e}")
        return False

def update_portfolio_schedule(schedule_id: str, updates: Dict[str, Any]) -> bool:
    """Update a scheduled analysis using new API"""
    try:
        response = go_client.put(f"api/v1/portfolio-schedules/{schedule_id}", json_data=updates)
        return response and response.get("success", False)
    except Exception as e:
        st.error(f"❌ Error updating schedule: {e}")
        return False

def show_enhanced_portfolio_schedules_tab(portfolios: List[Dict[str, Any]]):
    """Enhanced Portfolio Schedules Tab - Professional schedule management"""
    st.markdown("## ⏰ Portfolio Analysis Schedules")
    st.markdown("Manage automated portfolio analysis schedules with professional controls")
    
    # Debug: Show that function is being called
    st.info("🐛 DEBUG: Enhanced Portfolio Schedules Tab is loading!")
    
    # Get schedule overview
    try:
        overview = go_client.get("api/v1/portfolio-schedules/status/overview")
        if overview:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📊 Total Schedules", overview.get("total_schedules", 0))
            with col2:
                st.metric("🟢 Active", overview.get("active_schedules", 0))
            with col3:
                st.metric("🔴 Paused", overview.get("paused_schedules", 0))
            with col4:
                scheduler_status = "🟢 Running" if overview.get("scheduler_running", False) else "🔴 Stopped"
                st.metric("🔄 Scheduler", scheduler_status)
    except Exception as e:
        st.warning(f"⚠️ Could not load schedule overview: {e}")
    
    # Portfolio selector for schedule management
    if portfolios:
        selected_portfolio = create_portfolio_selector(portfolios, "schedule_management")
        
        if selected_portfolio:
            portfolio_id = selected_portfolio['id']
            portfolio_name = selected_portfolio['name']
            
            st.markdown(f"### 📅 All Schedules for {portfolio_name}")
            st.caption("Data loading schedules and portfolio analysis schedules")
            
            # Get system schedules for this portfolio
            system_schedules_for_portfolio = []
            try:
                all_system_schedules = go_client.get("api/v1/schedules")
                if all_system_schedules and all_system_schedules.get("schedules"):
                    system_schedules_for_portfolio = [
                        sched for sched in all_system_schedules["schedules"] 
                        if sched.get('portfolio_id') == portfolio_id
                    ]
            except Exception as e:
                st.warning(f"⚠️ Could not load system schedules: {e}")
            
            # Get portfolio analysis schedules for this portfolio
            portfolio_schedules = get_portfolio_schedules(portfolio_id)
            
            # Display System Schedules (Data Loading)
            if system_schedules_for_portfolio:
                st.markdown("#### 🔄 Data Loading Schedules")
                st.caption("System schedules that load market data for this portfolio")
                
                for schedule in system_schedules_for_portfolio:
                    with st.container():
                        # Enhanced schedule card with better styling
                        schedule_card = st.container()
                        with schedule_card:
                            # Header with status badge
                            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
                            
                            with col1:
                                # Profile info with enhanced icons
                                profile_icon = {
                                    "monthly_reference_backfill": "🗓️", 
                                    "weekly_fundamentals": "📊",
                                    "daily_market_intel": "📈", 
                                    "intraday_news_hourly": "📰",
                                    "intraday_prices_only": "💹"
                                }.get(schedule['profile'], "⏰")
                                
                                # Status badge
                                status_badge = "🟢 ACTIVE" if schedule['enabled'] else "🔴 DISABLED"
                                st.markdown(f"**{profile_icon} {schedule['profile'].replace('_', ' ').title()}**")
                                st.markdown(f"<span style='font-size: 12px; color: {'#10b981' if schedule['enabled'] else '#ef4444'};'>{status_badge}</span>", unsafe_allow_html=True)
                                st.caption(f"Data Loading • Cron: `{schedule['cron_expression']}`")
                            
                            with col2:
                                st.markdown("**⏰ Next Run:**")
                                if schedule.get('next_run_at'):
                                    next_run = schedule['next_run_at']
                                    if isinstance(next_run, str):
                                        next_run = datetime.fromisoformat(next_run.replace('Z', '+00:00'))
                                    st.caption(next_run.strftime('%Y-%m-%d %H:%M'))
                                else:
                                    st.caption("Not scheduled")
                                
                                st.markdown("**📅 Last Run:**")
                                if schedule.get('last_run_at'):
                                    last_run = schedule['last_run_at']
                                    if isinstance(last_run, str):
                                        last_run = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                                    st.caption(last_run.strftime('%m-%d %H:%M'))
                                else:
                                    st.caption("Never run")
                            
                            with col3:
                                st.markdown("**📊 Schedule Info:**")
                                st.caption(f"ID: `{schedule['schedule_id'][:8]}...`")
                                st.caption(f"Kind: `{schedule['kind']}`")
                                if schedule.get('timezone'):
                                    st.caption(f"Timezone: `{schedule['timezone']}`")
                                
                                # Show last 2 runs for active schedules
                                if schedule['enabled']:
                                    st.markdown("**🕐 Recent Runs:**")
                                    recent_runs = get_schedule_runs(schedule['schedule_id'], 2)
                                    if recent_runs:
                                        for i, run in enumerate(recent_runs):
                                            run_status = run.get('status', 'unknown')
                                            status_icon = {
                                                'success': '✅', 
                                                'running': '🔄', 
                                                'failed': '❌', 
                                                'cancelled': '⏹️'
                                            }.get(run_status, '❓')
                                            
                                            # Format time
                                            run_time = "Unknown"
                                            if run.get('started_at'):
                                                try:
                                                    started_at = datetime.fromisoformat(run['started_at'].replace('Z', '+00:00'))
                                                    run_time = started_at.strftime('%m-%d %H:%M')
                                                except:
                                                    run_time = "Invalid date"
                                            
                                            # Show run info with cancel option for running runs
                                            col_run, col_cancel = st.columns([4, 1])
                                            with col_run:
                                                st.caption(f"{status_icon} {run_status.title()} • {run_time}")
                                            with col_cancel:
                                                if run_status == 'running':
                                                    if st.button("⏹️", key=f"cancel_run_{run['run_id']}", help="Cancel this run"):
                                                        if cancel_run(run['run_id']):
                                                            st.success(f"⏹️ Run cancelled!")
                                                            st.rerun()
                                                        else:
                                                            st.error("❌ Failed to cancel run")
                                    else:
                                        st.caption("No recent runs")
                                else:
                                    st.markdown("**📊 Schedule Info:**")
                                    st.caption(f"ID: `{schedule['schedule_id'][:8]}...`")
                                    st.caption(f"Kind: `{schedule['kind']}`")
                                    if schedule.get('timezone'):
                                        st.caption(f"Timezone: `{schedule['timezone']}`")
                                    st.caption("ℹ️ Enable schedule to see recent runs")
                            
                            with col4:
                                st.markdown("**🎛️ Quick Actions:**")
                                # Primary toggle button
                                if schedule['enabled']:
                                    if st.button("⏸️ Disable", key=f"disable_{schedule['schedule_id']}", help="Disable this schedule"):
                                        response = go_client.patch(f"api/v1/schedules/{schedule['schedule_id']}", 
                                                                  {"enabled": False})
                                        if response:
                                            st.success(f"✅ Disabled {schedule['profile']}")
                                            st.rerun()
                                        else:
                                            st.error(f"❌ Failed to disable {schedule['profile']}")
                                else:
                                    if st.button("▶️ Enable", key=f"enable_{schedule['schedule_id']}", help="Enable this schedule"):
                                        response = go_client.patch(f"api/v1/schedules/{schedule['schedule_id']}", 
                                                                  {"enabled": True})
                                        if response:
                                            st.success(f"✅ Enabled {schedule['profile']}")
                                            st.rerun()
                                        else:
                                            st.error(f"❌ Failed to enable {schedule['profile']}")
                                
                                # Run now button
                                if st.button("🚀 Run Now", key=f"run_{schedule['schedule_id']}", help="Execute this schedule immediately"):
                                    response = go_client.post(f"api/v1/schedules/{schedule['schedule_id']}/run-now")
                                    if response:
                                        st.success(f"🚀 Triggered {schedule['profile']} to run now!")
                                    else:
                                        st.error(f"❌ Failed to trigger {schedule['profile']}")
                            
                            with col5:
                                st.markdown("**⚙️ More Actions:**")
                                # Edit button
                                if st.button("✏️ Edit", key=f"edit_{schedule['schedule_id']}", help="Edit schedule configuration"):
                                    st.session_state[f'edit_system_schedule_{schedule["schedule_id"]}'] = True
                                
                                # Delete button with confirmation
                                if st.button("🗑️ Delete", key=f"delete_{schedule['schedule_id']}", help="Delete this schedule"):
                                    if st.session_state.get(f'confirm_delete_{schedule["schedule_id"]}', False):
                                        response = go_client.delete(f"api/v1/schedules/{schedule['schedule_id']}")
                                        if response:
                                            st.success(f"🗑️ Deleted {schedule['profile']}")
                                            st.rerun()
                                        else:
                                            st.error(f"❌ Failed to delete {schedule['profile']}")
                                    else:
                                        st.session_state[f'confirm_delete_{schedule["schedule_id"]}'] = True
                                        st.warning("⚠️ Click Delete again to confirm")
                        
                        # Edit form (shown when edit button is clicked)
                        if st.session_state.get(f'edit_system_schedule_{schedule["schedule_id"]}', False):
                            with st.expander(f"✏️ Edit {schedule['profile'].replace('_', ' ').title()} Schedule", expanded=True):
                                with st.form(f"edit_system_schedule_form_{schedule['schedule_id']}"):
                                    st.markdown(f"**🔧 Edit System Schedule Configuration**")
                                    st.caption(f"Profile: `{schedule['profile']}` | ID: `{schedule['schedule_id'][:8]}...`")
                                    
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        # Basic settings
                                        st.markdown("**⚙️ Basic Settings:**")
                                        
                                        # Enable/Disable toggle
                                        current_enabled = schedule.get('enabled', False)
                                        new_enabled = st.checkbox("🟢 Enable Schedule", value=current_enabled, 
                                                                 help="Enable or disable this schedule")
                                        
                                        # Cron expression editing
                                        current_cron = schedule.get('cron_expression', '')
                                        st.markdown("**⏰ Cron Expression:**")
                                        st.caption("Define when this schedule should run using cron syntax")
                                        new_cron = st.text_input("Cron Expression", value=current_cron, 
                                                              help="Cron format: * * * * * (minute hour day month weekday)")
                                        
                                        # Cron helper
                                        with st.expander("📖 Cron Expression Helper", expanded=False):
                                            st.markdown("""
                                            **Cron Format:** `minute hour day month weekday`
                                            
                                            **Examples:**
                                            - `0 9 * * 1-5` - Weekdays at 9:00 AM
                                            - `0 */6 * * *` - Every 6 hours
                                            - `0 9 1 * *` - 1st of every month at 9:00 AM
                                            - `*/15 9-17 * * 1-5` - Every 15 min, 9 AM-5 PM, weekdays
                                            
                                            **Fields:**
                                            - **Minute:** 0-59
                                            - **Hour:** 0-23 (24-hour format)
                                            - **Day:** 1-31
                                            - **Month:** 1-12
                                            - **Weekday:** 0-7 (0 and 7 = Sunday)
                                            """)
                                        
                                        # Timezone selection
                                        current_timezone = schedule.get('timezone', 'UTC')
                                        timezones = ['UTC', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'Europe/London', 'Europe/Paris', 'Asia/Tokyo']
                                        new_timezone = st.selectbox("🌍 Timezone", timezones, 
                                                                 index=timezones.index(current_timezone) if current_timezone in timezones else 0,
                                                                 help="Schedule timezone")
                                    
                                    with col2:
                                        # Advanced settings
                                        st.markdown("**🔧 Advanced Settings:**")
                                        
                                        # Force execution option
                                        current_config = schedule.get('config', {})
                                        current_force = current_config.get('force', False)
                                        new_force = st.checkbox("💪 Force Execution", value=current_force,
                                                              help="Force execution even if recently run")
                                        
                                        # Portfolio assignment (read-only for now)
                                        st.markdown("**📊 Portfolio Assignment:**")
                                        st.info(f"Portfolio: `{portfolio_name}`")
                                        st.caption("Portfolio assignment cannot be changed here")
                                    
                                    # Data types configuration (preserve existing profile)
                                    st.markdown("**📊 Data Types Configuration:**")
                                    st.caption("Override default data types for this schedule (optional)")
                                    
                                    # Show current profile info
                                    profile_name = schedule.get('profile', 'unknown')
                                    st.info(f"📋 **Current Profile:** `{profile_name}`")
                                    st.caption("This profile defines the default data types. Use overrides below to customize.")
                                    
                                    # Parse current data types
                                    current_config = schedule.get('config', {})
                                    current_include = current_config.get('include_data_types', [])
                                    current_exclude = current_config.get('exclude_data_types', [])
                                    
                                    # Available data types (based on profile)
                                    available_data_types = [
                                        'market_data_daily', 'market_data_intraday', 'fundamentals_snapshot',
                                        'earnings_transcripts', 'ratings_snapshot', 'corporate_actions',
                                        'industry_peers', 'historical_grades', 'market_news', 'earnings_calendar'
                                    ]
                                    
                                    # Profile-specific data types info
                                    profile_data_info = {
                                        'monthly_reference_backfill': ['fundamentals_snapshot', 'earnings_transcripts', 'ratings_snapshot', 'corporate_actions', 'industry_peers', 'historical_grades'],
                                        'weekly_fundamentals': ['fundamentals_snapshot', 'earnings_transcripts', 'ratings_snapshot'],
                                        'daily_market_intel': ['market_data_daily', 'market_news', 'earnings_calendar'],
                                        'intraday_news_hourly': ['market_news'],
                                        'intraday_prices_only': ['market_data_intraday']
                                    }
                                    
                                    # Show profile defaults
                                    if profile_name in profile_data_info:
                                        with st.expander(f"📋 Default Data Types for {profile_name.replace('_', ' ').title()}", expanded=False):
                                            st.markdown("**This profile normally loads:**")
                                            for data_type in profile_data_info[profile_name]:
                                                st.caption(f"• `{data_type}`")
                                    
                                    # Override options
                                    col_include, col_exclude = st.columns(2)
                                    with col_include:
                                        st.markdown("**📥 Include Overrides:**")
                                        st.caption("Add these data types (empty = use profile defaults)")
                                        include_types = st.multiselect("Additional Data Types", 
                                                                      available_data_types,
                                                                      default=current_include,
                                                                      help="Select additional data types to include")
                                    with col_exclude:
                                        st.markdown("**📤 Exclude Overrides:**")
                                        st.caption("Remove these data types from profile defaults")
                                        exclude_types = st.multiselect("Data Types to Exclude", 
                                                                      available_data_types,
                                                                      default=current_exclude,
                                                                      help="Select data types to exclude from profile")
                                    
                                    # Action buttons
                                    col_submit, col_cancel = st.columns(2)
                                    with col_submit:
                                        if st.form_submit_button("💾 Save Changes", type="primary"):
                                            # Validate cron expression
                                            if new_cron.strip():
                                                # Prepare updates
                                                updates = {
                                                    "enabled": new_enabled,
                                                    "cron_expression": new_cron.strip(),
                                                    "timezone": new_timezone,
                                                    "config": {
                                                        "force": new_force,
                                                        "include_data_types": include_types,
                                                        "exclude_data_types": exclude_types
                                                    }
                                                }
                                                
                                                if update_system_schedule(schedule['schedule_id'], updates):
                                                    st.success("✅ Schedule updated successfully!")
                                                    st.session_state[f'edit_system_schedule_{schedule["schedule_id"]}'] = False
                                                    st.rerun()
                                                else:
                                                    st.error("❌ Failed to update schedule")
                                            else:
                                                st.error("❌ Cron expression cannot be empty")
                                    
                                    with col_cancel:
                                        if st.form_submit_button("❌ Cancel"):
                                            st.session_state[f'edit_system_schedule_{schedule["schedule_id"]}'] = False
                                            st.rerun()
                        
                        st.divider()
                
                st.markdown("---")
            else:
                st.info(f"🔄 No data loading schedules configured for {portfolio_name}")
                st.caption("System schedules for market data, fundamentals, and news will appear here")
            
            # Display Portfolio Analysis Schedules
            if portfolio_schedules:
                st.markdown("#### 📊 Portfolio Analysis Schedules")
                st.caption("Analysis and rebalancing schedules for this portfolio")
                
                for i, schedule in enumerate(portfolio_schedules):
                    with st.container():
                        # Enhanced schedule card with better styling
                        schedule_card = st.container()
                        with schedule_card:
                            # Header with status badge
                            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
                            
                            with col1:
                                # Schedule type with enhanced icons
                                type_icon = {"daily": "📅", "weekly": "📆", "monthly": "🗓️"}.get(schedule['schedule_type'], "⏰")
                                
                                # Status badge
                                status_badge = "🟢 ACTIVE" if schedule['is_active'] else "🔴 PAUSED"
                                st.markdown(f"**{type_icon} {schedule['schedule_type'].title()} Analysis**")
                                st.markdown(f"<span style='font-size: 12px; color: {'#10b981' if schedule['is_active'] else '#ef4444'};'>{status_badge}</span>", unsafe_allow_html=True)
                                st.caption(f"at {schedule['schedule_time']}")
                                if schedule['schedule_day']:
                                    if schedule['schedule_type'] == 'weekly':
                                        days = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                                        st.caption(f"on {days[schedule['schedule_day']]}")
                                    else:
                                        st.caption(f"on day {schedule['schedule_day']}")
                            
                            with col2:
                                st.markdown("**⏰ Next Run:**")
                                if schedule.get('next_run'):
                                    next_run = schedule['next_run']
                                    if isinstance(next_run, str):
                                        next_run = datetime.fromisoformat(next_run.replace('Z', '+00:00'))
                                    st.caption(next_run.strftime('%Y-%m-%d %H:%M'))
                                else:
                                    st.caption("Not scheduled")
                                
                                st.markdown("**📅 Last Run:**")
                                if schedule.get('last_run'):
                                    last_run = schedule['last_run']
                                    if isinstance(last_run, str):
                                        last_run = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                                    st.caption(last_run.strftime('%m-%d %H:%M'))
                                else:
                                    st.caption("Never run")
                            
                            with col3:
                                st.markdown("**📊 Schedule Info:**")
                                st.caption(f"ID: `{schedule['id'][:8]}...`")
                                
                                # Job status with enhanced icons
                                job_status = schedule.get('job_status', 'unknown')
                                job_icon = {"scheduled": "⏰", "running": "🔄", "paused": "⏸️", "error": "❌", "completed": "✅"}.get(job_status, "❓")
                                job_color = {"scheduled": "#6b7280", "running": "#3b82f6", "paused": "#f59e0b", "error": "#ef4444", "completed": "#10b981"}.get(job_status, "#6b7280")
                                st.markdown(f"<span style='font-size: 12px; color: {job_color};'>{job_icon} {job_status.title()}</span>", unsafe_allow_html=True)
                                
                                # Notification preferences
                                notif_prefs = schedule.get('notification_preferences', {})
                                notif_text = []
                                if notif_prefs.get('email'):
                                    notif_text.append("📧")
                                if notif_prefs.get('push'):
                                    notif_text.append("📱")
                                if notif_text:
                                    st.caption(f"Notifications: {' '.join(notif_text)}")
                                else:
                                    st.caption("Notifications: None")
                                
                                # Show last 2 runs for active schedules
                                if schedule['is_active']:
                                    st.markdown("**🕐 Recent Runs:**")
                                    recent_runs = get_portfolio_schedule_runs(schedule['id'], 2)
                                    if recent_runs:
                                        for i, run in enumerate(recent_runs):
                                            run_status = run.get('status', 'unknown')
                                            status_icon = {
                                                'success': '✅', 
                                                'running': '🔄', 
                                                'failed': '❌', 
                                                'cancelled': '⏹️'
                                            }.get(run_status, '❓')
                                            
                                            # Format time
                                            run_time = "Unknown"
                                            if run.get('started_at'):
                                                try:
                                                    started_at = datetime.fromisoformat(run['started_at'].replace('Z', '+00:00'))
                                                    run_time = started_at.strftime('%m-%d %H:%M')
                                                except:
                                                    run_time = "Invalid date"
                                            
                                            # Show run info with cancel option for running runs
                                            col_run, col_cancel = st.columns([4, 1])
                                            with col_run:
                                                st.caption(f"{status_icon} {run_status.title()} • {run_time}")
                                            with col_cancel:
                                                if run_status == 'running':
                                                    if st.button("⏹️", key=f"cancel_portfolio_run_{run['run_id']}", help="Cancel this run"):
                                                        if cancel_portfolio_run(run['run_id']):
                                                            st.success(f"⏹️ Run cancelled!")
                                                            st.rerun()
                                                        else:
                                                            st.error("❌ Failed to cancel run")
                                    else:
                                        st.caption("No recent runs")
                                else:
                                    st.caption("ℹ️ Resume schedule to see recent runs")
                            
                            with col4:
                                st.markdown("**🎛️ Quick Actions:**")
                                # Primary toggle button
                                toggle_text = "⏸️ Pause" if schedule['is_active'] else "▶️ Resume"
                                toggle_help = "Pause this schedule" if schedule['is_active'] else "Resume this schedule"
                                if st.button(toggle_text, key=f"tab_toggle_{schedule['id']}", help=toggle_help):
                                    if toggle_portfolio_schedule(schedule['id']):
                                        st.success(f"✅ Schedule {'paused' if schedule['is_active'] else 'resumed'}!")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Failed to {'pause' if schedule['is_active'] else 'resume'} schedule")
                                
                                # Run now button
                                if st.button("🚀 Run Now", key=f"run_now_{schedule['id']}", help="Execute analysis immediately"):
                                    # Trigger portfolio analysis run
                                    response = go_client.post(f"api/v1/portfolio-schedules/{schedule['id']}/run-now")
                                    if response:
                                        st.success(f"🚀 Triggered {schedule['schedule_type']} analysis to run now!")
                                    else:
                                        st.error(f"❌ Failed to trigger {schedule['schedule_type']} analysis")
                            
                            with col5:
                                st.markdown("**⚙️ More Actions:**")
                                # Edit button
                                if st.button("✏️ Edit", key=f"tab_edit_{schedule['id']}", help="Edit schedule configuration"):
                                    st.session_state[f'tab_edit_schedule_{schedule["id"]}'] = True
                                
                                # Delete button with confirmation
                                if st.button("🗑️ Delete", key=f"tab_delete_{schedule['id']}", help="Delete this schedule"):
                                    if st.session_state.get(f'confirm_delete_portfolio_{schedule["id"]}', False):
                                        if delete_portfolio_schedule(schedule['id']):
                                            st.success("🗑️ Schedule deleted!")
                                            st.rerun()
                                        else:
                                            st.error("❌ Failed to delete schedule")
                                    else:
                                        st.session_state[f'confirm_delete_portfolio_{schedule["id"]}'] = True
                                        st.warning("⚠️ Click Delete again to confirm")
                        
                        # Edit form (shown when edit button is clicked)
                        if st.session_state.get(f'tab_edit_schedule_{schedule["id"]}', False):
                            with st.expander(f"✏️ Edit {schedule['schedule_type'].title()} Schedule", expanded=True):
                                with st.form(f"tab_edit_schedule_form_{schedule['id']}"):
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        new_type = st.selectbox("Schedule Type", ["daily", "weekly", "monthly"], 
                                                              index=["daily", "weekly", "monthly"].index(schedule['schedule_type']))
                                        new_time = st.time_input("Time", value=datetime.strptime(schedule['schedule_time'], '%H:%M').time())
                                    
                                    with col2:
                                        new_day = None
                                        if new_type == "weekly":
                                            new_day = st.selectbox("Day of Week", list(range(1, 8)), 
                                                                  index=schedule.get('schedule_day', 1) - 1,
                                                                  format_func=lambda x: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][x-1])
                                        elif new_type == "monthly":
                                            new_day = st.selectbox("Day of Month", list(range(1, 32)), 
                                                                  index=schedule.get('schedule_day', 1) - 1)
                                    
                                    # Notification preferences
                                    st.markdown("**🔔 Notification Preferences:**")
                                    email_notif = st.checkbox("📧 Email Notifications", 
                                                            value=schedule.get('notification_preferences', {}).get('email', True))
                                    push_notif = st.checkbox("📱 Push Notifications", 
                                                           value=schedule.get('notification_preferences', {}).get('push', False))
                                    
                                    col_submit, col_cancel = st.columns(2)
                                    with col_submit:
                                        if st.form_submit_button("💾 Save Changes", type="primary"):
                                            updates = {
                                                "schedule_type": new_type,
                                                "schedule_time": new_time.strftime("%H:%M"),
                                                "notification_preferences": {
                                                    "email": email_notif,
                                                    "push": push_notif
                                                }
                                            }
                                            if new_day:
                                                updates["schedule_day"] = new_day
                                            
                                            if update_portfolio_schedule(schedule['id'], updates):
                                                st.success("✅ Schedule updated!")
                                                st.session_state[f'tab_edit_schedule_{schedule["id"]}'] = False
                                                st.rerun()
                                    
                                    with col_cancel:
                                        if st.form_submit_button("❌ Cancel"):
                                            st.session_state[f'tab_edit_schedule_{schedule["id"]}'] = False
                                            st.rerun()
                        
                        st.divider()
            else:
                st.info(f"⏰ No scheduled analyses set up for {selected_portfolio['name']}")
            
            # Add new schedule section
            with st.expander("➕ Create New Schedule", expanded=False):
                st.markdown(f"**Schedule Analysis for {selected_portfolio['name']}**")
                
                with st.form("tab_create_schedule_form"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        schedule_type = st.selectbox("📅 Schedule Type", ["daily", "weekly", "monthly"], 
                                                   help="Choose how often to run the analysis")
                        schedule_time = st.time_input("⏰ Execution Time", value=time(9, 0), 
                                                     help="Time of day to run the analysis (9:00 AM default)")
                    
                    with col2:
                        schedule_day = None
                        if schedule_type == "weekly":
                            schedule_day = st.selectbox("📆 Day of Week", list(range(1, 8)), 
                                                      format_func=lambda x: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][x-1],
                                                      help="Day of the week to run the analysis")
                        elif schedule_type == "monthly":
                            schedule_day = st.selectbox("🗓️ Day of Month", list(range(1, 32)), 
                                                      help="Day of the month to run the analysis")
                    
                    # Notification preferences
                    st.markdown("**🔔 Notification Preferences:**")
                    col_email, col_push = st.columns(2)
                    with col_email:
                        email_notif = st.checkbox("📧 Email Notifications", value=True, 
                                                 help="Receive email notifications when analysis completes")
                    with col_push:
                        push_notif = st.checkbox("📱 Push Notifications", value=False, 
                                                 help="Receive push notifications (if enabled)")
                    
                    # Schedule description
                    st.markdown("**📝 Schedule Description:**")
                    if schedule_type == "daily":
                        desc = f"Analysis will run every day at {schedule_time.strftime('%I:%M %p')}"
                    elif schedule_type == "weekly":
                        day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][schedule_day-1] if schedule_day else "Monday"
                        desc = f"Analysis will run every {day_name} at {schedule_time.strftime('%I:%M %p')}"
                    else:
                        day_num = schedule_day or 1
                        desc = f"Analysis will run on the {day_num}{('st' if day_num == 1 else 'nd' if day_num == 2 else 'rd' if day_num == 3 else 'th')} of each month at {schedule_time.strftime('%I:%M %p')}"
                    
                    st.info(desc)
                    
                    if st.form_submit_button("⏰ Create Schedule", type="primary"):
                        schedule = create_portfolio_schedule(selected_portfolio['id'], schedule_type, schedule_time, schedule_day)
                        if schedule:
                            st.success("✅ Schedule created successfully!")
                            st.rerun()
    else:
        st.warning("⚠️ No portfolios available. Create a portfolio first to manage schedules.")

def show_scheduling_section(portfolio_id: str):
    """Show enhanced scheduling section for portfolio"""
    st.markdown("### ⏰ Portfolio Analysis Scheduling")
    
    # Get schedule overview
    try:
        overview = go_client.get("api/v1/portfolio-schedules/status/overview")
        if overview:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📊 Total Schedules", overview.get("total_schedules", 0))
            with col2:
                st.metric("🟢 Active", overview.get("active_schedules", 0))
            with col3:
                st.metric("🔴 Paused", overview.get("paused_schedules", 0))
            with col4:
                scheduler_status = "🟢 Running" if overview.get("scheduler_running", False) else "🔴 Stopped"
                st.metric("🔄 Scheduler", scheduler_status)
    except Exception as e:
        st.warning(f"⚠️ Could not load schedule overview: {e}")
    
    # Get portfolio-specific schedules
    schedules = get_portfolio_schedules(portfolio_id)
    
    if schedules:
        st.markdown("#### 📅 Portfolio Schedules")
        
        for i, schedule in enumerate(schedules):
            with st.container():
                # Schedule card with professional styling
                col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
                
                with col1:
                    # Schedule type and time with icon
                    type_icon = {"daily": "📅", "weekly": "📆", "monthly": "🗓️"}.get(schedule['schedule_type'], "⏰")
                    st.markdown(f"**{type_icon} {schedule['schedule_type'].title()}**")
                    st.caption(f"at {schedule['schedule_time']}")
                    if schedule['schedule_day']:
                        if schedule['schedule_type'] == 'weekly':
                            days = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                            st.caption(f"on {days[schedule['schedule_day']]}")
                        else:
                            st.caption(f"on day {schedule['schedule_day']}")
                
                with col2:
                    # Next run information
                    if schedule.get('next_run'):
                        next_run = schedule['next_run']
                        if isinstance(next_run, str):
                            next_run = datetime.fromisoformat(next_run.replace('Z', '+00:00'))
                        st.markdown("**Next Run:**")
                        st.caption(next_run.strftime('%Y-%m-%d %H:%M'))
                    else:
                        st.markdown("**Next Run:**")
                        st.caption("Not scheduled")
                
                with col3:
                    # Status with toggle button
                    status_color = "🟢" if schedule['is_active'] else "🔴"
                    status_text = "Active" if schedule['is_active'] else "Paused"
                    st.markdown(f"**{status_color} {status_text}**")
                    
                    # Job status
                    job_status = schedule.get('job_status', 'unknown')
                    job_icon = {"scheduled": "⏰", "running": "🔄", "paused": "⏸️", "error": "❌"}.get(job_status, "❓")
                    st.caption(f"{job_icon} {job_status.title()}")
                
                with col4:
                    # Last run information
                    if schedule.get('last_run'):
                        last_run = schedule['last_run']
                        if isinstance(last_run, str):
                            last_run = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                        st.markdown("**Last Run:**")
                        st.caption(last_run.strftime('%m-%d %H:%M'))
                    else:
                        st.markdown("**Last Run:**")
                        st.caption("Never run")
                
                with col5:
                    # Action buttons
                    st.markdown("**Actions:**")
                    
                    # Toggle button
                    toggle_text = "⏸️" if schedule['is_active'] else "▶️"
                    toggle_help = "Pause" if schedule['is_active'] else "Resume"
                    if st.button(toggle_text, key=f"toggle_{schedule['id']}", help=toggle_help):
                        if toggle_portfolio_schedule(schedule['id']):
                            st.success(f"✅ Schedule {'paused' if schedule['is_active'] else 'resumed'}!")
                            st.rerun()
                    
                    # Edit button
                    if st.button("✏️", key=f"edit_{schedule['id']}", help="Edit Schedule"):
                        st.session_state[f'edit_schedule_{schedule["id"]}'] = True
                    
                    # Delete button
                    if st.button("🗑️", key=f"delete_{schedule['id']}", help="Delete Schedule"):
                        if delete_portfolio_schedule(schedule['id']):
                            st.success("✅ Schedule deleted!")
                            st.rerun()
                
                # Edit form (shown when edit button is clicked)
                if st.session_state.get(f'edit_schedule_{schedule["id"]}', False):
                    with st.expander(f"✏️ Edit Schedule - {schedule['schedule_type'].title()}", expanded=True):
                        with st.form(f"edit_form_{schedule['id']}"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                new_type = st.selectbox("Schedule Type", ["daily", "weekly", "monthly"], 
                                                      index=["daily", "weekly", "monthly"].index(schedule['schedule_type']))
                                new_time = st.time_input("Time", value=datetime.strptime(schedule['schedule_time'], '%H:%M').time())
                            
                            with col2:
                                new_day = None
                                if new_type == "weekly":
                                    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                                    current_day = schedule.get('schedule_day', 1) - 1 if schedule.get('schedule_day') else 0
                                    new_day = st.selectbox("Day of Week", list(range(1, 8)), 
                                                          index=current_day, format_func=lambda x: days[x-1])
                                elif new_type == "monthly":
                                    new_day = st.selectbox("Day of Month", list(range(1, 32)), 
                                                          index=schedule.get('schedule_day', 1) - 1)
                            
                            # Notification preferences
                            st.markdown("**Notification Preferences:**")
                            email_notif = st.checkbox("📧 Email Notifications", 
                                                    value=schedule.get('notification_preferences', {}).get('email', True))
                            push_notif = st.checkbox("📱 Push Notifications", 
                                                   value=schedule.get('notification_preferences', {}).get('push', False))
                            
                            col_submit, col_cancel = st.columns(2)
                            with col_submit:
                                if st.form_submit_button("💾 Save Changes", type="primary"):
                                    updates = {
                                        "schedule_type": new_type,
                                        "schedule_time": new_time.strftime("%H:%M"),
                                        "notification_preferences": {
                                            "email": email_notif,
                                            "push": push_notif
                                        }
                                    }
                                    if new_day:
                                        updates["schedule_day"] = new_day
                                    
                                    if update_portfolio_schedule(schedule['id'], updates):
                                        st.success("✅ Schedule updated!")
                                        st.session_state[f'edit_schedule_{schedule["id"]}'] = False
                                        st.rerun()
                            
                            with col_cancel:
                                if st.form_submit_button("❌ Cancel"):
                                    st.session_state[f'edit_schedule_{schedule["id"]}'] = False
                                    st.rerun()
                
                st.divider()
    else:
        st.info("⏰ No scheduled analyses set up for this portfolio")
    
    # Add new schedule section
    with st.expander("➕ Create New Schedule", expanded=False):
        st.markdown("**Schedule Portfolio Analysis**")
        
        with st.form("create_schedule_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                schedule_type = st.selectbox("📅 Schedule Type", ["daily", "weekly", "monthly"], 
                                           help="Choose how often to run the analysis")
                schedule_time = st.time_input("⏰ Execution Time", value=time(9, 0), 
                                             help="Time of day to run the analysis (9:00 AM default)")
            
            with col2:
                schedule_day = None
                if schedule_type == "weekly":
                    schedule_day = st.selectbox("📆 Day of Week", list(range(1, 8)), 
                                              format_func=lambda x: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][x-1],
                                              help="Day of the week to run the analysis")
                elif schedule_type == "monthly":
                    schedule_day = st.selectbox("🗓️ Day of Month", list(range(1, 32)), 
                                              help="Day of the month to run the analysis")
            
            # Notification preferences
            st.markdown("**🔔 Notification Preferences:**")
            col_email, col_push = st.columns(2)
            with col_email:
                email_notif = st.checkbox("📧 Email Notifications", value=True, 
                                         help="Receive email notifications when analysis completes")
            with col_push:
                push_notif = st.checkbox("📱 Push Notifications", value=False, 
                                         help="Receive push notifications (if enabled)")
            
            # Schedule description
            st.markdown("**📝 Schedule Description:**")
            if schedule_type == "daily":
                desc = f"Analysis will run every day at {schedule_time.strftime('%I:%M %p')}"
            elif schedule_type == "weekly":
                day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][schedule_day-1] if schedule_day else "Monday"
                desc = f"Analysis will run every {day_name} at {schedule_time.strftime('%I:%M %p')}"
            else:
                day_num = schedule_day or 1
                desc = f"Analysis will run on the {day_num}{('st' if day_num == 1 else 'nd' if day_num == 2 else 'rd' if day_num == 3 else 'th')} of each month at {schedule_time.strftime('%I:%M %p')}"
            
            st.info(desc)
            
            if st.form_submit_button("⏰ Create Schedule", type="primary"):
                schedule = create_portfolio_schedule(portfolio_id, schedule_type, schedule_time, schedule_day)
                if schedule:
                    st.success("✅ Schedule created successfully!")
                    st.rerun()

def refresh_symbol_analysis(symbol: str, asset_type: str = "stock") -> bool:
    """Refresh analysis for a symbol with timeout handling"""
    _ = asset_type
    try:
        go_client.post(
            "api/v1/admin/refresh",
            json_data={
                "symbols": [symbol],
                "data_types": ["price_historical", "indicators"],
                "force": True,
            },
            timeout=180,
        )
        return True
    except Exception as e:
        st.error(f"Error refreshing analysis: {str(e)}")
        return False

# ========================================
# UI Components
# ========================================

def show_login_page():
    """Show login page with session persistence info"""
    st.markdown(f"""
    <div style="text-align: center; padding: 4rem; color: #666;">
        <h1>🔐 Portfolio Management System</h1>
        <p>Select a user to access portfolios</p>
    </div>
    """, unsafe_allow_html=True)

    users = []
    try:
        users = _load_users()
    except Exception as e:
        st.error(f"❌ Failed to load users from Go API: {e}")
        return

    user_options = {
        f"{u.get('username', 'unknown')} ({u.get('subscription_level', 'basic')})": u
        for u in users
        if u and (u.get('user_id') or u.get('id'))
    }

    if not user_options:
        st.error("No users returned from Go API")
        return

    selected_label = st.selectbox("User", options=list(user_options.keys()), key="enh_portfolio_user_select")
    if st.button("Continue", type="primary", width='stretch', key="enh_portfolio_user_continue"):
        st.session_state.current_user = user_options[selected_label]
        st.rerun()

def show_portfolio_management_tab(portfolios):
    """Portfolio Management tab with CRUD operations"""
    st.markdown("### 📋 Portfolio Management")
    
    # Portfolio selection and actions
    col1, col2 = st.columns([3, 1])
    
    with col1:
        selected_portfolio = create_portfolio_selector(portfolios, "management")
    
    with col2:
        if st.button("➕ Create New", type="primary", width='stretch', key="create_portfolio_mgmt"):
            st.session_state.show_create_portfolio = True
    
    # Show create portfolio form if requested
    if st.session_state.get('show_create_portfolio', False):
        st.markdown("#### ➕ Create New Portfolio")
        show_create_portfolio_form("management")
        if st.button("❌ Cancel", key="cancel_create_mgmt"):
            st.session_state.show_create_portfolio = False
            st.rerun()
        return
    
    # Portfolio details and actions
    if selected_portfolio:
        st.markdown("---")
        
        # Use helper function for portfolio metrics
        create_portfolio_metrics(selected_portfolio)
        
        # Use helper function for action buttons
        create_portfolio_action_buttons(selected_portfolio)
        
        # Portfolio holdings
        st.markdown("#### 📈 Portfolio Holdings")
        holdings = get_portfolio_holdings(selected_portfolio['id'])
        
        if holdings:
            # Use helper function for holdings table
            df_holdings = create_holdings_table(holdings)
            
            # Display the dataframe without styling the Signal column
            st.dataframe(df_holdings, width='stretch', hide_index=True)
            
            # Action buttons for each holding
            st.markdown("#### 🎯 Stock Actions")
            for holding in holdings:
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                
                with col1:
                    st.write(f"**{holding['symbol']}**")
                
                with col2:
                    if st.button("✏️ Edit", key=f"mgmt_edit_{holding['symbol']}"):
                        st.session_state.show_edit_stock = True
                        st.session_state.edit_symbol = holding['symbol']
                        st.session_state.edit_holding = holding
                        st.rerun()
                
                with col3:
                    if st.button("🗑️ Delete", key=f"mgmt_delete_{holding['symbol']}"):
                        if st.session_state.get(f'confirm_delete_{holding["symbol"]}', False):
                            success = delete_portfolio_holding(holding.get('id'))
                            if success:
                                st.success(f"✅ {holding['symbol']} deleted successfully!")
                                st.rerun()
                            else:
                                st.error(f"❌ Failed to delete {holding['symbol']}")
                        else:
                            st.session_state[f'confirm_delete_{holding["symbol"]}'] = True
                            st.warning(f"⚠️ Click again to confirm deleting {holding['symbol']}")
                            st.rerun()
                
                with col4:
                    signal = get_stock_signal(holding['symbol'])
                    signal_colors = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}
                    color = signal_colors.get(signal, '⚪')
                    if st.button(f"{color} {signal}", key=f"mgmt_signal_{holding['symbol']}"):
                        # Clear any previous analysis state
                        if 'show_symbol_analysis' in st.session_state:
                            st.session_state.show_symbol_analysis = False
                        if 'selected_symbol_for_analysis' in st.session_state:
                            del st.session_state.selected_symbol_for_analysis
                        
                        # Set new symbol for analysis
                        st.session_state.selected_symbol_for_analysis = holding['symbol']
                        st.session_state.show_symbol_analysis = True
                        st.success(f"🔄 Loading analysis for {holding['symbol']}...")
                        st.rerun()
            
            # Show edit stock form if requested
            if st.session_state.get('show_edit_stock', False) and st.session_state.get('edit_holding'):
                show_edit_stock_form(selected_portfolio['id'], st.session_state.edit_holding)
            
            # Add stock button
            st.markdown("---")
            if st.button("➕ Add Stock to Portfolio", type="primary", key="add_stock_mgmt"):
                st.session_state.show_add_stock = True
            
            # Add stock form
            if st.session_state.get('show_add_stock', False):
                show_add_stock_form(selected_portfolio['id'])
        else:
            st.info("📋 No holdings in this portfolio. Add stocks to get started!")
            if st.button("➕ Add Your First Stock", type="primary", key="add_first_stock"):
                st.session_state.show_add_stock = True
            
            # Add stock form
            if st.session_state.get('show_add_stock', False):
                show_add_stock_form(selected_portfolio['id'])

def update_portfolio_holding(holding_id: str, shares_held: float, average_cost: float, asset_type: str = "stock") -> Optional[Dict[str, Any]]:
    """Update a holding in portfolio"""
    _ = asset_type
    try:
        payload: Dict[str, Any] = {}
        if shares_held is not None and shares_held > 0:
            payload["quantity"] = float(shares_held)
        if average_cost is not None and average_cost > 0:
            payload["avg_price"] = float(average_cost)
        if not payload:
            return None
        return go_client.put(f"api/v1/holdings/{holding_id}", json_data=payload)
    except Exception as e:
        st.error(f"Error updating holding: {str(e)}")
        return None

def delete_portfolio_holding(holding_id: str) -> bool:
    """Delete a holding from portfolio"""
    try:
        if not holding_id:
            return False
        go_client.delete(f"api/v1/holdings/{holding_id}")
        return True
    except Exception as e:
        st.error(f"Error deleting holding: {e}")
        return False

def show_edit_stock_form(portfolio_id: str, holding: Dict[str, Any]):
    """Show edit stock form"""
    with st.form(f"edit_stock_form_{holding['symbol']}"):
        st.markdown(f"#### ✏️ Edit {holding['symbol']}")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.text_input("Symbol", value=holding['symbol'], disabled=True)
        
        with col2:
            asset_type = st.selectbox("Type*", ["stock", "regular_etf", "3x_etf"], 
                                     index=["stock", "regular_etf", "3x_etf"].index(holding.get('asset_type', 'stock')))
        
        with col3:
            shares_value = holding.get("shares_held")
            if shares_value is None:
                shares_value = holding.get("quantity")
            if shares_value is None:
                shares_value = holding.get("shares")
            shares = st.number_input("Shares*", min_value=0.0, value=float(shares_value or 0.0), step=10.0)
        
        with col4:
            avg_cost = st.number_input("Avg Cost ($)*", min_value=0.0, value=float(holding['average_cost']), step=0.01)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("💾 Update Stock", type="primary"):
                holding_id = holding.get("id")
                if not holding_id:
                    st.error("Holding id missing; cannot update")
                    return
                updated_holding = update_portfolio_holding(holding_id, shares, avg_cost, asset_type)
                if updated_holding:
                    st.success(f"✅ {holding['symbol']} updated successfully!")
                    st.session_state.show_edit_stock = False
                    st.session_state.edit_symbol = None
                    st.rerun()
        
        with col2:
            if st.form_submit_button("❌ Cancel"):
                st.session_state.show_edit_stock = False
                st.session_state.edit_symbol = None
                st.rerun()

def get_stock_signal(symbol: str) -> str:
    """Get stock signal from Go API"""
    try:
        resp = go_client.get(f"api/v1/signal/{symbol}")
        if not resp:
            return "HOLD"
        if isinstance(resp, dict) and resp.get("signal"):
            return str(resp.get("signal") or "HOLD").upper()
        if isinstance(resp, str):
            return resp.upper()
        return "HOLD"
    except Exception:
        return "HOLD"

def delete_portfolio(portfolio_id: str) -> bool:
    """Delete a portfolio"""
    try:
        user = st.session_state.get("current_user") or {}
        user_id = user.get("user_id") or user.get("id")
        if not user_id:
            return False
        go_client.delete(f"api/v1/portfolio/{user_id}/{portfolio_id}")
        return True
    except Exception:
        return False

def show_add_stock_form(portfolio_id: str):
    """Show add stock form"""
    with st.form("add_stock_form"):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            symbol = st.text_input("Symbol*", placeholder="e.g., AAPL").upper()
        
        with col2:
            asset_type = st.selectbox("Type*", ["stock", "regular_etf", "3x_etf"])
        
        with col3:
            shares = st.number_input("Shares", min_value=0.0, value=100.0, step=10.0)
        
        with col4:
            avg_cost = st.number_input("Avg Cost ($)", min_value=0.0, value=0.0, step=0.01)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("➕ Add Stock", type="primary"):
                if symbol:
                    holding = add_portfolio_holding(portfolio_id, symbol, asset_type, shares, avg_cost)
                    if holding:
                        st.success(f"✅ {symbol} added to portfolio!")
                        st.session_state.show_add_stock = False
                        st.rerun()
                else:
                    st.error("Symbol is required")
        
        with col2:
            if st.form_submit_button("❌ Cancel"):
                st.session_state.show_add_stock = False
                st.rerun()

def show_portfolio_overview_tab(portfolios):
    """Portfolio Overview tab"""
    show_portfolio_overview()

def show_stock_analysis_tab(portfolios):
    """Stock Analysis tab with clickable signals"""
    st.markdown("### 📈 Stock Analysis")
    
    # Use helper function for portfolio selection
    selected_portfolio = create_portfolio_selector(portfolios, "analysis")
    
    # Get holdings
    holdings = get_portfolio_holdings(selected_portfolio['id'])
    
    if holdings:
        st.markdown("#### 📊 Portfolio Stocks with Signals")
        
        for holding in holdings:
            signal = get_stock_signal(holding['symbol'])
            
            # Signal color
            signal_colors = {
                'BUY': '🟢',
                'SELL': '🔴', 
                'HOLD': '🟡'
            }
            color = signal_colors.get(signal, '⚪')
            
            # Create clickable signal
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
            
            with col1:
                st.write(f"**{holding['symbol']}**")
            
            with col2:
                shares_value = holding.get('shares_held', holding.get('shares', holding.get('quantity', 0)))
                st.write(f"Shares: {format_shares(shares_value)}")
            
            with col3:
                st.write(f"Cost: {format_currency(holding.get('average_cost', 0))}")
            
            with col4:
                if st.button(f"{color} {signal}", key=f"analysis_signal_{holding['symbol']}"):
                    # Clear any previous analysis state
                    if 'show_symbol_analysis' in st.session_state:
                        st.session_state.show_symbol_analysis = False
                    if 'selected_symbol_for_analysis' in st.session_state:
                        del st.session_state.selected_symbol_for_analysis
                    
                    # Set new symbol for analysis
                    st.session_state.selected_symbol_for_analysis = holding['symbol']
                    st.session_state.show_symbol_analysis = True
                    st.success(f"🔄 Loading analysis for {holding['symbol']}...")
                    st.rerun()
            
            with col5:
                current_price = holding.get('current_price')
                st.write(f"Price: {format_currency(current_price)}")
    else:
        st.info("📋 No holdings in this portfolio. Add stocks to see analysis.")

def show_settings_tab():
    """Comprehensive Settings Tab - Industry Standard Trading System Configuration"""
    st.markdown("## ⚙️ System Settings")
    st.markdown("Configure your trading system with institutional-grade settings")
    
    # Initialize session state for settings
    if 'settings' not in st.session_state:
        st.session_state.settings = {
            'portfolio': {
                'risk_tolerance': 'Moderate',
                'max_position_size': 10.0,
                'max_portfolio_exposure': 100.0,
                'rebalancing_frequency': 'Monthly',
                'sector_concentration_limit': 25.0
            },
            'risk_management': {
                'stop_loss_percentage': 5.0,
                'take_profit_percentage': 15.0,
                'max_drawdown_limit': 20.0,
                'daily_loss_limit': 10.0,
                'volatility_threshold': 2.0
            },
            'trading': {
                'default_order_type': 'Market',
                'execution_preference': 'Immediate',
                'slippage_tolerance': 0.5,
                'time_in_force': 'Day',
                'minimum_trade_size': 1000.0
            },
            'alerts': {
                'price_alerts': True,
                'volume_alerts': True,
                'portfolio_alerts': True,
                'risk_alerts': True,
                'notification_method': 'Email'
            },
            'data': {
                'primary_data_source': 'Yahoo Finance',
                'backup_data_source': 'Alpha Vantage',
                'update_frequency': 'Daily',
                'cache_duration': 3600,
                'api_rate_limit': 100
            }
        }
    
    # Settings categories
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Portfolio", 
        "⚠️ Risk Management", 
        "📈 Trading", 
        "🔔 Alerts", 
        "🌐 Data & API"
    ])
    
    with tab1:
        show_portfolio_settings()
    
    with tab2:
        show_risk_management_settings()
    
    with tab3:
        show_trading_settings()
    
    with tab4:
        show_alerts_settings()
    
    with tab5:
        show_data_api_settings()

def show_portfolio_settings():
    """Portfolio Management Settings"""
    st.markdown("### 📊 Portfolio Management Settings")
    st.markdown("Configure portfolio-level parameters and constraints")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🎯 Risk Profile")
        
        risk_tolerance = st.selectbox(
            "Risk Tolerance",
            ["Conservative", "Moderate", "Aggressive", "Very Aggressive"],
            index=["Conservative", "Moderate", "Aggressive", "Very Aggressive"].index(
                st.session_state.settings['portfolio']['risk_tolerance']
            ),
            help="Overall risk appetite for portfolio management"
        )
        
        max_position_size = st.slider(
            "Maximum Position Size (%)",
            min_value=1.0,
            max_value=50.0,
            value=st.session_state.settings['portfolio']['max_position_size'],
            step=0.5,
            help="Maximum percentage of portfolio for single position"
        )
        
        max_portfolio_exposure = st.slider(
            "Maximum Portfolio Exposure (%)",
            min_value=50.0,
            max_value=150.0,
            value=st.session_state.settings['portfolio']['max_portfolio_exposure'],
            step=5.0,
            help="Maximum total exposure (includes leverage)"
        )
    
    with col2:
        st.markdown("#### 🔄 Rebalancing")
        
        rebalancing_frequency = st.selectbox(
            "Rebalancing Frequency",
            ["Daily", "Weekly", "Monthly", "Quarterly", "Annually"],
            index=["Daily", "Weekly", "Monthly", "Quarterly", "Annually"].index(
                st.session_state.settings['portfolio']['rebalancing_frequency']
            ),
            help="How often to rebalance portfolio"
        )
        
        sector_concentration_limit = st.slider(
            "Sector Concentration Limit (%)",
            min_value=10.0,
            max_value=60.0,
            value=st.session_state.settings['portfolio']['sector_concentration_limit'],
            step=5.0,
            help="Maximum exposure to any single sector"
        )
        
        st.markdown("#### 📊 Portfolio Summary")
        st.info(f"""
        **Current Configuration:**
        - Risk Profile: {risk_tolerance}
        - Max Position: {max_position_size}%
        - Max Exposure: {max_portfolio_exposure}%
        - Rebalancing: {rebalancing_frequency}
        - Sector Limit: {sector_concentration_limit}%
        """)
    
    # Update settings
    if st.button("💾 Save Portfolio Settings", type="primary"):
        st.session_state.settings['portfolio'].update({
            'risk_tolerance': risk_tolerance,
            'max_position_size': max_position_size,
            'max_portfolio_exposure': max_portfolio_exposure,
            'rebalancing_frequency': rebalancing_frequency,
            'sector_concentration_limit': sector_concentration_limit
        })
        st.success("✅ Portfolio settings saved!")

def show_risk_management_settings():
    """Risk Management Settings"""
    st.markdown("### ⚠️ Risk Management Settings")
    st.markdown("Configure risk parameters and loss limits")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🛡️ Loss Protection")
        
        stop_loss_percentage = st.slider(
            "Stop Loss Percentage (%)",
            min_value=1.0,
            max_value=20.0,
            value=st.session_state.settings['risk_management']['stop_loss_percentage'],
            step=0.5,
            help="Automatic stop loss trigger percentage"
        )
        
        take_profit_percentage = st.slider(
            "Take Profit Percentage (%)",
            min_value=5.0,
            max_value=50.0,
            value=st.session_state.settings['risk_management']['take_profit_percentage'],
            step=1.0,
            help="Automatic take profit trigger percentage"
        )
        
        max_drawdown_limit = st.slider(
            "Maximum Drawdown Limit (%)",
            min_value=5.0,
            max_value=50.0,
            value=st.session_state.settings['risk_management']['max_drawdown_limit'],
            step=2.5,
            help="Maximum portfolio drawdown before action"
        )
    
    with col2:
        st.markdown("#### 📊 Risk Metrics")
        
        daily_loss_limit = st.slider(
            "Daily Loss Limit (%)",
            min_value=1.0,
            max_value=25.0,
            value=st.session_state.settings['risk_management']['daily_loss_limit'],
            step=1.0,
            help="Maximum daily loss before trading halt"
        )
        
        volatility_threshold = st.slider(
            "Volatility Threshold (σ)",
            min_value=0.5,
            max_value=5.0,
            value=st.session_state.settings['risk_management']['volatility_threshold'],
            step=0.1,
            help="Volatility threshold for risk alerts"
        )
        
        st.markdown("#### 🚨 Risk Summary")
        risk_score = calculate_risk_score(
            stop_loss_percentage, 
            take_profit_percentage, 
            max_drawdown_limit
        )
        
        risk_color = "🟢 Low" if risk_score < 3 else "🟡 Medium" if risk_score < 7 else "🔴 High"
        st.info(f"""
        **Risk Assessment: {risk_color}**
        **Risk Score: {risk_score}/10**
        
        - Stop Loss: {stop_loss_percentage}%
        - Take Profit: {take_profit_percentage}%
        - Max Drawdown: {max_drawdown_limit}%
        - Daily Limit: {daily_loss_limit}%
        - Volatility: {volatility_threshold}σ
        """)
    
    if st.button("💾 Save Risk Settings", type="primary"):
        st.session_state.settings['risk_management'].update({
            'stop_loss_percentage': stop_loss_percentage,
            'take_profit_percentage': take_profit_percentage,
            'max_drawdown_limit': max_drawdown_limit,
            'daily_loss_limit': daily_loss_limit,
            'volatility_threshold': volatility_threshold
        })
        st.success("✅ Risk management settings saved!")

def show_trading_settings():
    """Trading Preferences Settings"""
    st.markdown("### 📈 Trading Preferences")
    st.markdown("Configure execution and order preferences")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📋 Order Configuration")
        
        default_order_type = st.selectbox(
            "Default Order Type",
            ["Market", "Limit", "Stop Loss", "Stop Limit"],
            index=["Market", "Limit", "Stop Loss", "Stop Limit"].index(
                st.session_state.settings['trading']['default_order_type']
            ),
            help="Default order type for trades"
        )
        
        execution_preference = st.selectbox(
            "Execution Preference",
            ["Immediate", "Best Price", "Lowest Cost", "Fastest"],
            index=["Immediate", "Best Price", "Lowest Cost", "Fastest"].index(
                st.session_state.settings['trading']['execution_preference']
            ),
            help="Order execution priority"
        )
        
        time_in_force = st.selectbox(
            "Time in Force",
            ["Day", "GTC", "IOC", "FOK"],
            index=["Day", "GTC", "IOC", "FOK"].index(
                st.session_state.settings['trading']['time_in_force']
            ),
            help="Order duration and execution rules"
        )
    
    with col2:
        st.markdown("#### ⚙️ Execution Parameters")
        
        slippage_tolerance = st.slider(
            "Slippage Tolerance (%)",
            min_value=0.1,
            max_value=5.0,
            value=st.session_state.settings['trading']['slippage_tolerance'],
            step=0.1,
            help="Acceptable price slippage"
        )
        
        minimum_trade_size = st.number_input(
            "Minimum Trade Size ($)",
            min_value=100.0,
            max_value=100000.0,
            value=st.session_state.settings['trading']['minimum_trade_size'],
            step=100.0,
            help="Minimum trade size in dollars"
        )
        
        st.markdown("#### 📊 Trading Summary")
        st.info(f"""
        **Trading Configuration:**
        - Order Type: {default_order_type}
        - Execution: {execution_preference}
        - Time in Force: {time_in_force}
        - Slippage: {slippage_tolerance}%
        - Min Trade: ${minimum_trade_size:,.0f}
        """)
    
    if st.button("💾 Save Trading Settings", type="primary"):
        st.session_state.settings['trading'].update({
            'default_order_type': default_order_type,
            'execution_preference': execution_preference,
            'time_in_force': time_in_force,
            'slippage_tolerance': slippage_tolerance,
            'minimum_trade_size': minimum_trade_size
        })
        st.success("✅ Trading settings saved!")

def show_alerts_settings():
    """Alerts and Notifications Settings"""
    st.markdown("### 🔔 Alerts & Notifications")
    st.markdown("Configure alert preferences and notification methods")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🚨 Alert Types")
        
        price_alerts = st.checkbox(
            "Price Alerts",
            value=st.session_state.settings['alerts']['price_alerts'],
            help="Alert on significant price movements"
        )
        
        volume_alerts = st.checkbox(
            "Volume Alerts",
            value=st.session_state.settings['alerts']['volume_alerts'],
            help="Alert on unusual volume activity"
        )
        
        portfolio_alerts = st.checkbox(
            "Portfolio Alerts",
            value=st.session_state.settings['alerts']['portfolio_alerts'],
            help="Alert on portfolio rebalancing needs"
        )
        
        risk_alerts = st.checkbox(
            "Risk Alerts",
            value=st.session_state.settings['alerts']['risk_alerts'],
            help="Alert on risk threshold breaches"
        )
    
    with col2:
        st.markdown("#### 📧 Notification Methods")
        
        notification_method = st.selectbox(
            "Primary Notification Method",
            ["Email", "SMS", "Push", "Webhook"],
            index=["Email", "SMS", "Push", "Webhook"].index(
                st.session_state.settings['alerts']['notification_method']
            ),
            help="How to receive notifications"
        )
        
        if notification_method == "Email":
            email_address = st.text_input(
                "Email Address",
                placeholder="trader@example.com",
                help="Email for notifications"
            )
        
        st.markdown("#### 📊 Alert Summary")
        active_alerts = sum([price_alerts, volume_alerts, portfolio_alerts, risk_alerts])
        st.info(f"""
        **Alert Configuration:**
        - Active Alerts: {active_alerts}/4
        - Notification: {notification_method}
        - Price Alerts: {'✅' if price_alerts else '❌'}
        - Volume Alerts: {'✅' if volume_alerts else '❌'}
        - Portfolio Alerts: {'✅' if portfolio_alerts else '❌'}
        - Risk Alerts: {'✅' if risk_alerts else '❌'}
        """)
    
    if st.button("💾 Save Alert Settings", type="primary"):
        st.session_state.settings['alerts'].update({
            'price_alerts': price_alerts,
            'volume_alerts': volume_alerts,
            'portfolio_alerts': portfolio_alerts,
            'risk_alerts': risk_alerts,
            'notification_method': notification_method
        })
        st.success("✅ Alert settings saved!")

def show_data_api_settings():
    """Data and API Settings"""
    st.markdown("### 🌐 Data & API Settings")
    st.markdown("Configure data sources and API parameters")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📊 Data Sources")
        
        primary_data_source = st.selectbox(
            "Primary Data Source",
            ["Yahoo Finance", "Alpha Vantage", "Bloomberg", "Reuters"],
            index=["Yahoo Finance", "Alpha Vantage", "Bloomberg", "Reuters"].index(
                st.session_state.settings['data']['primary_data_source']
            ),
            help="Primary source for market data"
        )
        
        backup_data_source = st.selectbox(
            "Backup Data Source",
            ["Alpha Vantage", "Yahoo Finance", "IEX Cloud", "Polygon"],
            index=["Alpha Vantage", "Yahoo Finance", "IEX Cloud", "Polygon"].index(
                st.session_state.settings['data']['backup_data_source']
            ),
            help="Fallback data source"
        )
        
        update_frequency = st.selectbox(
            "Update Frequency",
            ["Real-time", "5 minutes", "15 minutes", "Hourly", "Daily"],
            index=["Real-time", "5 minutes", "15 minutes", "Hourly", "Daily"].index(
                st.session_state.settings['data']['update_frequency']
            ),
            help="How often to update data"
        )
    
    with col2:
        st.markdown("#### ⚙️ API Configuration")
        
        cache_duration = st.slider(
            "Cache Duration (seconds)",
            min_value=60,
            max_value=86400,
            value=st.session_state.settings['data']['cache_duration'],
            step=60,
            help="How long to cache API responses"
        )
        
        api_rate_limit = st.slider(
            "API Rate Limit (requests/minute)",
            min_value=10,
            max_value=1000,
            value=st.session_state.settings['data']['api_rate_limit'],
            step=10,
            help="Maximum API requests per minute"
        )
        
        st.markdown("#### 📊 Data Summary")
        st.info(f"""
        **Data Configuration:**
        - Primary: {primary_data_source}
        - Backup: {backup_data_source}
        - Updates: {update_frequency}
        - Cache: {cache_duration}s
        - Rate Limit: {api_rate_limit}/min
        """)
    
    if st.button("💾 Save Data Settings", type="primary"):
        st.session_state.settings['data'].update({
            'primary_data_source': primary_data_source,
            'backup_data_source': backup_data_source,
            'update_frequency': update_frequency,
            'cache_duration': cache_duration,
            'api_rate_limit': api_rate_limit
        })
        st.success("✅ Data settings saved!")

def calculate_risk_score(stop_loss, take_profit, max_drawdown):
    """Calculate risk score based on parameters"""
    # Simple risk scoring algorithm
    score = 0
    
    # Higher stop loss = lower risk
    if stop_loss >= 10:
        score += 1
    elif stop_loss >= 5:
        score += 2
    else:
        score += 3
    
    # Higher take profit = lower risk
    if take_profit >= 25:
        score += 1
    elif take_profit >= 15:
        score += 2
    else:
        score += 3
    
    # Higher max drawdown = higher risk
    if max_drawdown <= 10:
        score += 1
    elif max_drawdown <= 20:
        score += 2
    else:
        score += 4
    
    return min(score, 10)

def show_portfolio_overview():
    """Show institutional-grade portfolio overview page"""
    user = st.session_state.current_user or {}
    
    # Institutional header with professional styling
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); 
                padding: 2.5rem; border-radius: 15px; color: white; margin-bottom: 2rem; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h1 style="margin: 0; font-size: 2.5rem; font-weight: 700;">🏛️ Portfolio Management</h1>
                <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">Institutional-grade portfolio analysis and management</p>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 1.2rem; font-weight: 600;">{(user.get('full_name') or user.get('username') or user.get('email') or user.get('user_id') or 'User')}</div>
                <div style="opacity: 0.8;">{str(user.get('role') or 'user').title()} Account</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Get user portfolios
    portfolios = get_user_portfolios()
    
    if not portfolios:
        # Show create portfolio form for first-time users
        st.markdown("""
        <div style="background: #f8fafc; padding: 3rem; border-radius: 15px; text-align: center; border: 2px dashed #cbd5e1;">
            <div style="font-size: 4rem; margin-bottom: 1rem;">📋</div>
            <h2 style="color: #475569; margin-bottom: 1rem;">No Portfolios Yet</h2>
            <p style="color: #64748b; margin-bottom: 2rem;">Create your first portfolio to start institutional-grade analysis</p>
        </div>
        """, unsafe_allow_html=True)
        
        show_create_portfolio_form("first_portfolio")
    else:
        # Use helper function for portfolio selection
        selected_portfolio = create_portfolio_selector(portfolios, "overview")
        st.session_state.selected_portfolio = selected_portfolio['id']
        
        # Institutional action buttons
        st.markdown("### 🎯 Portfolio Actions")
        col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1, 1, 1])
        
        with col1:
            if st.button("📊 Institutional Analysis", type="primary", width='stretch', key="overview_analysis"):
                with st.spinner("Starting portfolio analysis run..."):
                    result = analyze_portfolio(selected_portfolio['id'])
                    if result and result.get('run_id'):
                        st.success(f"✅ Analysis run started: {result.get('run_id')}")
                    else:
                        st.error("❌ Failed to start analysis run")

        profiles_resp: Dict[str, Any] = fetch_analysis_profiles()
        profiles_map = (profiles_resp or {}).get("profiles") or {}
        profile_names = sorted([str(k) for k in profiles_map.keys()])
        if not profile_names:
            profile_names = ["daily_signals", "intraday_signals", "weekly_rebalance"]

        st.markdown("#### 📌 Analysis Profiles")
        prof_col1, prof_col2, prof_col3 = st.columns([2, 1, 2])
        with prof_col1:
            selected_profile = st.selectbox("Profile", options=profile_names, index=0, key="epa_analysis_profile_select")
        with prof_col2:
            run_profile_clicked = st.button("▶️ Run", width='stretch', key="epa_run_analysis_profile")
        with prof_col3:
            st.caption("Starts: POST /api/v1/portfolios/:portfolio_id/analysis-run")

        if run_profile_clicked:
            with st.spinner(f"Starting analysis run ({selected_profile})..."):
                result = analyze_portfolio_with_profile(selected_portfolio['id'], selected_profile)
                if result and result.get("run_id"):
                    st.success(f"✅ Analysis run started: {result.get('run_id')}")
                else:
                    st.error("❌ Failed to start analysis run")

        st.markdown("#### 🧠 Trading Decision V3 (Portfolio)")
        tdv3_col1, tdv3_col2, tdv3_col3, tdv3_col4 = st.columns([1, 1, 1, 2])
        with tdv3_col1:
            tdv3_refresh = st.checkbox("Refresh first", value=False, key="epa_tdv3_refresh")
        with tdv3_col2:
            tdv3_force = st.checkbox("Force", value=False, key="epa_tdv3_force")
        with tdv3_col3:
            tdv3_as_of_date = st.text_input("As-of date", value="", key="epa_tdv3_as_of_date")
        with tdv3_col4:
            tdv3_data_types = st.multiselect(
                "Refresh data types",
                options=["price_historical", "indicators", "price_current", "signals"],
                default=["price_historical", "indicators"],
                key="epa_tdv3_data_types",
            )

        run_tdv3_clicked = st.button("▶️ Run V3 Decisions", width='stretch', key="epa_tdv3_run")
        if run_tdv3_clicked:
            try:
                with st.spinner("Running V3 decisions for portfolio..."):
                    resp = run_v3_portfolio_decisions_python_worker(
                        selected_portfolio['id'],
                        refresh=tdv3_refresh,
                        data_types=tdv3_data_types if tdv3_refresh else None,
                        force=tdv3_force,
                        as_of_date=(tdv3_as_of_date.strip() or None),
                    )
                st.session_state.epa_last_tdv3_portfolio_resp = resp
                st.success("✅ V3 decisions complete")
            except Exception as e:
                st.error(f"❌ Failed to run V3 decisions: {e}")

        tdv3_resp = st.session_state.get("epa_last_tdv3_portfolio_resp")
        if isinstance(tdv3_resp, dict) and tdv3_resp.get("decisions"):
            decisions = tdv3_resp.get("decisions") or []
            df = pd.DataFrame(decisions)
            if "opportunity_score" in df.columns:
                df = df.sort_values(by=["opportunity_score"], ascending=False, na_position="last")
            st.dataframe(
                df[[c for c in ["symbol", "action", "state", "phase", "extension", "confidence", "opportunity_score", "volume_context", "price"] if c in df.columns]],
                width='stretch',
                hide_index=True,
            )
            with st.expander("Reasons"):
                reasons_df = df[[c for c in ["symbol", "reasons"] if c in df.columns]]
                st.dataframe(reasons_df, width='stretch', hide_index=True)

        st.markdown("#### 🗓️ Trading Decision V3 History")
        hist_col1, hist_col2, hist_col3 = st.columns([2, 1, 2])
        with hist_col1:
            hist_limit = st.number_input("Dates to load", min_value=5, max_value=365, value=60, step=5, key="epa_tdv3_hist_limit")
        with hist_col2:
            hist_refresh_dates = st.button("🔄 Load dates", key="epa_tdv3_hist_refresh_dates")
        with hist_col3:
            hist_filter_to_portfolio = st.checkbox("Filter to this portfolio", value=True, key="epa_tdv3_hist_filter_portfolio")

        if hist_refresh_dates or ("epa_tdv3_hist_dates" not in st.session_state):
            try:
                with st.spinner("Loading available decision dates..."):
                    st.session_state.epa_tdv3_hist_dates = list_v3_decision_dates_python_worker(limit=int(hist_limit))
            except Exception as e:
                st.error(f"❌ Failed to load V3 decision dates: {e}")
                st.session_state.epa_tdv3_hist_dates = []

        hist_dates = st.session_state.get("epa_tdv3_hist_dates") or []
        selected_hist_date = st.selectbox(
            "As-of date",
            options=hist_dates,
            index=0 if hist_dates else None,
            key="epa_tdv3_hist_date_select",
        )

        hist_load_clicked = st.button("📥 Load decisions", width='stretch', key="epa_tdv3_hist_load")
        if hist_load_clicked and selected_hist_date:
            try:
                with st.spinner(f"Loading V3 decisions for {selected_hist_date}..."):
                    decisions = list_v3_decisions_by_date_python_worker(
                        as_of_date=str(selected_hist_date),
                        portfolio_id=(selected_portfolio['id'] if hist_filter_to_portfolio else None),
                        limit=5000,
                    )
                st.session_state.epa_tdv3_hist_decisions = decisions
            except Exception as e:
                st.error(f"❌ Failed to load V3 decisions: {e}")
                st.session_state.epa_tdv3_hist_decisions = []

        hist_decisions = st.session_state.get("epa_tdv3_hist_decisions") or []
        if hist_decisions:
            hist_df = pd.DataFrame(hist_decisions)
            if "opportunity_score" in hist_df.columns:
                hist_df = hist_df.sort_values(by=["opportunity_score"], ascending=False, na_position="last")
            st.dataframe(
                hist_df[[c for c in ["symbol", "action", "state", "phase", "extension", "confidence", "opportunity_score", "volume_context", "price", "timestamp"] if c in hist_df.columns]],
                width='stretch',
                hide_index=True,
            )

            symbols = [str(s) for s in hist_df.get("symbol", []).tolist() if s]
            selected_symbol = st.selectbox("Inspect symbol", options=symbols, index=0 if symbols else None, key="epa_tdv3_hist_symbol")
            if selected_symbol:
                selected_rows = [d for d in hist_decisions if d.get("symbol") == selected_symbol]
                selected_decision = selected_rows[0] if selected_rows else None
                if isinstance(selected_decision, dict):
                    with st.expander("Decision details", expanded=True):
                        st.json(selected_decision.get("metadata") or selected_decision)

        with col2:
            if st.button("🔄 Refresh Data", width='stretch', key="overview_refresh"):
                load_portfolio_data(selected_portfolio['id'])
        
        with col3:
            if st.button("📈 Risk Metrics", width='stretch', key="overview_risk"):
                st.session_state.show_risk_metrics = True
        
        with col4:
            if st.button("➕ Add Symbol", width='stretch', key="overview_add"):
                st.session_state.show_add_symbol = True
        
        with col5:
            if st.button("🔄 Load All Data", width='stretch', key="overview_load_all"):
                load_all_portfolio_data(selected_portfolio['id'])
        
        with col6:
            if st.button("⏰ Scheduling", width='stretch', key="overview_scheduling"):
                st.session_state.show_scheduling = True
        
        # Show portfolio details with institutional formatting
        show_portfolio_details(selected_portfolio)
        
        # Show institutional risk metrics if requested
        if st.session_state.get('show_risk_metrics', False):
            show_institutional_risk_metrics(selected_portfolio)
        
        # Show portfolio scheduling section if requested
        if st.session_state.get('show_scheduling', False):
            show_scheduling_section(selected_portfolio['id'])
        
        # Show last analysis results with institutional formatting
        if 'last_analysis_result' in st.session_state:
            show_institutional_analysis_results(st.session_state.last_analysis_result)

        st.markdown("### 🧵 Run Inspector (Data Load + Analysis)")

        run_id_input = st.text_input(
            "Run ID",
            value=st.session_state.get("epa_last_analysis_run_id", ""),
            key="epa_run_id",
        )

        auto_col1, auto_col2, auto_col3 = st.columns([1, 1, 2])
        with auto_col1:
            auto_refresh = st.checkbox("Auto refresh", value=True, key="epa_auto_refresh")
        with auto_col2:
            auto_refresh_seconds = st.number_input("Every (sec)", min_value=1, max_value=30, value=3, step=1, key="epa_auto_refresh_seconds")
        with auto_col3:
            st.caption("Polls Go API: GET /api/v1/data-load/runs/:run_id")

        if auto_refresh and run_id_input:
            try:
                if hasattr(st, "autorefresh"):
                    st.autorefresh(interval=int(auto_refresh_seconds) * 1000, key="epa_autorefresh")
            except Exception:
                pass

        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            fetch_latest_clicked = st.button("Fetch latest", key="epa_fetch_latest")
        with col_b:
            show_notifications = st.checkbox("Show notifications", value=False, key="epa_show_notifications")
        with col_c:
            event_view = st.selectbox("Events view", options=["All", "Errors only"], index=0, key="epa_event_view")

        if fetch_latest_clicked and run_id_input:
            try:
                st.session_state["epa_last_run_details"] = fetch_run(run_id_input)
            except Exception as e:
                st.error(f"Failed to fetch run: {e}")

        if auto_refresh and run_id_input:
            try:
                details_now = fetch_run(run_id_input)
                if isinstance(details_now, dict) and details_now.get("success"):
                    st.session_state["epa_last_run_details"] = details_now
            except Exception:
                pass

        details = st.session_state.get("epa_last_run_details")
        if isinstance(details, dict) and details:
            run_obj = details.get("run") or {}
            status = str((run_obj or {}).get("status") or "")
            started_at = _format_ts((run_obj or {}).get("started_at"))
            finished_at = _format_ts((run_obj or {}).get("finished_at"))

            st.markdown("#### Run")
            st.write({
                "run_id": (run_obj or {}).get("run_id"),
                "status": status,
                "started_at": started_at,
                "finished_at": finished_at,
            })


            cancel_col1, cancel_col2 = st.columns([1, 3])
            with cancel_col1:
                cancel_clicked = st.button(
                    "Cancel run",
                    type="secondary",
                    disabled=not (run_id_input and status.lower() == "running"),
                    key="epa_cancel_run",
                )
            with cancel_col2:
                if status.lower() != "running":
                    st.caption("Cancel is only available while status=running")

            if cancel_clicked and run_id_input:
                try:
                    resp = cancel_run(run_id_input)
                    if isinstance(resp, dict) and resp.get("success"):
                        st.success("✅ Cancel requested")
                        try:
                            st.session_state["epa_last_run_details"] = fetch_run(run_id_input)
                        except Exception:
                            pass
                    else:
                        st.error("❌ Cancel request failed")
                        st.json(resp)
                except Exception as e:
                    st.error(f"Cancel request failed: {e}")

            events = details.get("events") or []
            if not isinstance(events, list):
                events = []
            if event_view == "Errors only":
                events = [e for e in events if str((e or {}).get("level") or "").lower() == "error"]

            st.markdown(f"#### Events ({len(events)})")
            if events:
                rows = []
                for e in events:
                    if not isinstance(e, dict):
                        continue
                    rows.append({
                        "ts": _format_ts(e.get("event_ts")),
                        "level": e.get("level"),
                        "operation": e.get("operation"),
                        "symbol": e.get("symbol"),
                        "message": e.get("message"),
                        "error": e.get("error_message"),
                    })
                df = pd.DataFrame(rows)
                st.dataframe(df, width='stretch', hide_index=True)
            else:
                st.caption("No events yet.")

            if show_notifications and run_id_input:
                st.markdown("#### Notifications (by correlation_id=run_id)")
                try:
                    n = fetch_run_notifications(run_id_input)
                    st.json(n)
                except Exception as e:
                    st.error(f"Failed to fetch notifications: {e}")

def show_create_portfolio_form(location: str = "main"):
    """Show create portfolio form"""
    form_key = f"create_portfolio_form_{location}"
    with st.form(form_key):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Portfolio Name*", placeholder="e.g., Growth Portfolio")
            portfolio_type = st.selectbox("Portfolio Type", [
                "custom", "growth", "income", "balanced", "retirement"
            ])
        
        with col2:
            initial_capital = st.number_input("Initial Capital ($)", min_value=0.0, value=10000.0, step=1000.0)
            currency = st.selectbox("Currency", ["USD", "EUR", "GBP"])
        
        description = st.text_area("Description (Optional)", placeholder="Describe your portfolio strategy...")
        
        if st.form_submit_button("➕ Create Portfolio", type="primary", width='stretch'):
            if name:
                portfolio = create_portfolio(name, description, portfolio_type, initial_capital)
                if portfolio:
                    st.success(f"✅ Portfolio '{name}' created successfully!")
                    st.rerun()
            else:
                st.error("Portfolio name is required")

def show_institutional_risk_metrics(portfolio: Dict[str, Any]):
    """Show institutional-grade risk metrics"""
    st.markdown("### 📊 Institutional Risk Metrics")
    
    # Get portfolio holdings for risk analysis
    holdings = get_portfolio_holdings(portfolio['id'])
    
    if not holdings:
        st.warning("No holdings data available for risk analysis")
        return
    
    # Calculate risk metrics
    total_value = sum(float(h.get('market_value', 0)) for h in holdings if h.get('market_value'))
    
    # Risk metrics calculation
    risk_metrics = calculate_institutional_risk_metrics(holdings)
    
    # Display risk dashboard
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div style="background: #f0f9ff; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #0ea5e9;">
            <h4 style="margin: 0; color: #0c4a6e;">📊 Portfolio Beta</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #0284c7;">{risk_metrics['portfolio_beta']:.2f}</div>
            <div style="font-size: 0.875rem; color: #64748b;">Market sensitivity</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: #fef3c7; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #f59e0b;">
            <h4 style="margin: 0; color: #92400e;">⚠️ Value at Risk</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #d97706;">{risk_metrics['var_95']:.2f}%</div>
            <div style="font-size: 0.875rem; color: #64748b;">95% Confidence</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div style="background: #f0fdf4; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #22c55e;">
            <h4 style="margin: 0; color: #166534;">🎯 Sharpe Ratio</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #16a34a;">{risk_metrics['sharpe_ratio']:.2f}</div>
            <div style="font-size: 0.875rem; color: #64748b;">Risk-adjusted return</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div style="background: #fef2f2; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #ef4444;">
            <h4 style="margin: 0; color: #991b1b;">📉 Max Drawdown</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #dc2626;">{risk_metrics['max_drawdown']:.2f}%</div>
            <div style="font-size: 0.875rem; color: #64748b;">Peak to trough</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Risk assessment
    st.markdown("### 🎯 Risk Assessment")
    
    risk_level = assess_portfolio_risk(risk_metrics)
    
    st.markdown(f"""
    <div style="background: {risk_level['bg_color']}; padding: 1.5rem; border-radius: 10px; border-left: 4px solid {risk_level['border_color']};">
        <h4 style="margin: 0; color: {risk_level['text_color']};">{risk_level['emoji']} Risk Level: {risk_level['level']}</h4>
        <p style="margin: 0.5rem 0 0 0; color: {risk_level['text_color']};">{risk_level['description']}</p>
        <div style="margin-top: 1rem;">
            <strong>Key Risk Factors:</strong>
            <ul style="margin: 0.5rem 0; padding-left: 1.5rem; color: {risk_level['text_color']};">
                {"".join([f"<li>{factor}</li>" for factor in risk_level['factors']])}
            </ul>
        </div>
    </div>
    """, unsafe_allow_html=True)

def calculate_institutional_risk_metrics(holdings: List[Dict]) -> Dict[str, float]:
    """Calculate institutional-grade risk metrics"""
    # Simplified calculations - in production, these would use historical data
    total_value = sum(float(h.get('market_value', 0)) for h in holdings if h.get('market_value'))
    
    # Portfolio beta (simplified)
    portfolio_beta = 1.0  # Would calculate from individual stock betas
    
    # VaR (simplified - would use historical returns)
    var_95 = 2.5  # 95% VaR percentage
    
    # Sharpe ratio (simplified)
    sharpe_ratio = 1.2  # Risk-adjusted return metric
    
    # Max drawdown (simplified)
    max_drawdown = 8.5  # Maximum peak-to-trough decline
    
    return {
        'portfolio_beta': portfolio_beta,
        'var_95': var_95,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown
    }

def assess_portfolio_risk(risk_metrics: Dict[str, float]) -> Dict[str, Any]:
    """Assess overall portfolio risk level"""
    risk_score = 0
    
    # Calculate risk score based on metrics
    if risk_metrics['portfolio_beta'] > 1.2:
        risk_score += 2
    elif risk_metrics['portfolio_beta'] < 0.8:
        risk_score += 1
    
    if risk_metrics['var_95'] > 3.0:
        risk_score += 2
    elif risk_metrics['var_95'] > 2.0:
        risk_score += 1
    
    if risk_metrics['max_drawdown'] > 10.0:
        risk_score += 2
    elif risk_metrics['max_drawdown'] > 5.0:
        risk_score += 1
    
    if risk_metrics['sharpe_ratio'] < 0.5:
        risk_score += 2
    elif risk_metrics['sharpe_ratio'] < 1.0:
        risk_score += 1
    
    # Determine risk level
    if risk_score >= 6:
        return {
            'level': 'HIGH',
            'emoji': '🔴',
            'bg_color': '#fef2f2',
            'border_color': '#ef4444',
            'text_color': '#991b1b',
            'description': 'Portfolio exhibits high risk characteristics. Consider reducing exposure or implementing hedging strategies.',
            'factors': ['High market sensitivity', 'Elevated volatility risk', 'Significant drawdown potential', 'Low risk-adjusted returns']
        }
    elif risk_score >= 3:
        return {
            'level': 'MODERATE',
            'emoji': '🟡',
            'bg_color': '#fef3c7',
            'border_color': '#f59e0b',
            'text_color': '#92400e',
            'description': 'Portfolio has moderate risk levels. Monitor market conditions and maintain balanced diversification.',
            'factors': ['Moderate market sensitivity', 'Acceptable volatility levels', 'Reasonable drawdown risk', 'Adequate risk-adjusted returns']
        }
    else:
        return {
            'level': 'LOW',
            'emoji': '🟢',
            'bg_color': '#f0fdf4',
            'border_color': '#22c55e',
            'text_color': '#166534',
            'description': 'Portfolio demonstrates low risk characteristics with good diversification and risk management.',
            'factors': ['Low market sensitivity', 'Controlled volatility', 'Limited drawdown risk', 'Strong risk-adjusted returns']
        }

def show_institutional_analysis_results(analysis_result: Dict[str, Any]):
    """Show institutional-grade analysis results"""
    st.markdown("### 📊 Institutional Analysis Results")
    
    # Analysis summary
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); 
                padding: 2rem; border-radius: 15px; color: white; margin-bottom: 2rem;">
        <h2 style="margin: 0; font-size: 2rem;">🎯 Analysis Summary</h2>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1.5rem;">
            <div style="background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 10px;">
                <div style="font-size: 0.875rem; opacity: 0.8;">Signals Generated</div>
                <div style="font-size: 1.5rem; font-weight: 700;">{analysis_result.get('signals_generated', 0)}</div>
            </div>
            <div style="background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 10px;">
                <div style="font-size: 0.875rem; opacity: 0.8;">Analysis Time</div>
                <div style="font-size: 1.5rem; font-weight: 700;">{analysis_result.get('analysis_time', 'N/A')}</div>
            </div>
            <div style="background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 10px;">
                <div style="font-size: 0.875rem; opacity: 0.8;">Confidence</div>
                <div style="font-size: 1.5rem; font-weight: 700;">{analysis_result.get('confidence', 'N/A')}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Signal breakdown
    if 'signals' in analysis_result:
        st.markdown("### 🚦 Signal Breakdown")
        
        signals = analysis_result['signals']
        signal_counts = {}
        
        for signal in signals:
            signal_type = signal.get('signal', 'UNKNOWN')
            signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1
        
        # Create signal distribution chart
        if signal_counts:
            fig = go.Figure(data=[
                go.Bar(
                    x=list(signal_counts.keys()),
                    y=list(signal_counts.values()),
                    marker_color=['#00C851' if k == 'BUY' else '#FF4444' if k == 'SELL' else '#FF8800' for k in signal_counts.keys()]
                )
            ])
            
            fig.update_layout(
                title="Signal Distribution",
                xaxis_title="Signal Type",
                yaxis_title="Count",
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
            
            st.plotly_chart(fig, width='stretch')
        
        # Detailed signals table
        st.markdown("#### 📋 Detailed Signals")
        
        signal_data = []
        for signal in signals:
            signal_data.append({
                'Symbol': signal.get('symbol', 'N/A'),
                'Signal': signal.get('signal', 'N/A'),
                'Confidence': f"{signal.get('confidence', 0):.1%}",
                'Reasoning': signal.get('reasoning', ['No reasoning'])[0] if signal.get('reasoning') else 'No reasoning',
                'Timestamp': signal.get('timestamp', 'N/A')
            })
        
        if signal_data:
            df_signals = pd.DataFrame(signal_data)
            st.dataframe(df_signals, width='stretch', hide_index=True)

def show_portfolio_details(portfolio: Dict[str, Any]):
    """Show institutional-grade portfolio information"""
    st.markdown(f"### 📊 {portfolio['name']}")
    
    # Portfolio metrics with institutional styling
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div style="background: #f8fafc; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #0ea5e9;">
            <h4 style="margin: 0; color: #0c4a6e;">💰 Initial Capital</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #0284c7;">${:.2f}</div>
        </div>
        """.format(_safe_float(portfolio.get('initial_capital'), 0.0)), unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: #f8fafc; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #22c55e;">
            <h4 style="margin: 0; color: #166534;">📈 Portfolio Type</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #16a34a;">{}</div>
        </div>
        """.format(portfolio.get('portfolio_type', 'custom').replace('_', ' ').title()), unsafe_allow_html=True)
    
    with col3:
        created_at = portfolio.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        st.markdown("""
        <div style="background: #f8fafc; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #f59e0b;">
            <h4 style="margin: 0; color: #92400e;">📅 Created</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #d97706;">{}</div>
        </div>
        """.format(created_at.strftime('%Y-%m-%d') if hasattr(created_at, 'strftime') else str(created_at)), unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div style="background: #f8fafc; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #8b5cf6;">
            <h4 style="margin: 0; color: #6d28d9;">👤 Portfolio ID</h4>
            <div style="font-size: 1.2rem; font-weight: 600; color: #7c3aed;">{}</div>
        </div>
        """.format(portfolio.get('id', 'N/A')), unsafe_allow_html=True)
    
    # Portfolio description
    if portfolio.get('description'):
        st.markdown("### 📝 Portfolio Strategy")
        st.info(portfolio.get('description', 'No strategy description available'))
    
    # Holdings section with institutional formatting
    with st.spinner("Loading portfolio holdings..."):
        holdings = get_portfolio_holdings(portfolio['id'])
    
    # Initialize holdings_data to avoid UnboundLocalError
    holdings_data = []
    
    if holdings:
        st.markdown("### 📋 Portfolio Holdings")
        
        # Holdings summary
        total_value = sum(_safe_float(h.get('market_value'), 0.0) for h in holdings)
        total_cost = sum(_safe_float(h.get('average_cost'), 0.0) * _safe_float(h.get('shares_held'), 0.0) for h in holdings)
        total_return = total_value - total_cost
        total_return_pct = (total_return / total_cost * 100) if total_cost > 0 else 0
        
        # Portfolio performance metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("""
            <div style="background: #f0fdf4; padding: 1rem; border-radius: 10px; text-align: center;">
                <div style="font-size: 0.875rem; color: #166534;">Total Value</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: #16a34a;">${:,.2f}</div>
            </div>
            """.format(_safe_float(total_value, 0.0)), unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div style="background: #fef2f2; padding: 1rem; border-radius: 10px; text-align: center;">
                <div style="font-size: 0.875rem; color: #991b1b;">Total Cost</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: #dc2626;">${:,.2f}</div>
            </div>
            """.format(_safe_float(total_cost, 0.0)), unsafe_allow_html=True)
        
        with col3:
            color = "#16a34a" if total_return >= 0 else "#dc2626"
            total_return_float = float(total_return) if total_return else 0
            st.markdown(f"""
            <div style="background: {'#f0fdf4' if total_return >= 0 else '#fef2f2'}; padding: 1rem; border-radius: 10px; text-align: center;">
                <div style="font-size: 0.875rem; color: {color};">Total Return</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: {color};">${total_return_float:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            color = "#16a34a" if total_return_pct >= 0 else "#dc2626"
            st.markdown(f"""
            <div style="background: {'#f0fdf4' if total_return_pct >= 0 else '#fef2f2'}; padding: 1rem; border-radius: 10px; text-align: center;">
                <div style="font-size: 0.875rem; color: {color};">Return %</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: {color};">{total_return_pct:+.2f}%</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Holdings table with institutional formatting
        st.markdown("#### 📊 Detailed Holdings")
        
        # Process holdings in batches to avoid timeout
        batch_size = 10
        
        for i in range(0, len(holdings), batch_size):
            batch = holdings[i:i+batch_size]
            
            # Show progress for large portfolios
            if len(holdings) > 20:
                progress = (i + len(batch)) / len(holdings)
                st.progress(progress, text=f"Processing holdings {i+len(batch)}/{len(holdings)}...")
            
            for holding in batch:
                market_value = _safe_float(holding.get('market_value'), 0.0)
                average_cost = _safe_float(
                    holding.get('average_cost')
                    if holding.get('average_cost') is not None
                    else holding.get('avg_price')
                    if holding.get('avg_price') is not None
                    else holding.get('avg_entry_price')
                    if holding.get('avg_entry_price') is not None
                    else holding.get('avg_cost'),
                    0.0,
                )
                shares_held = _safe_float(
                    holding.get('shares_held')
                    if holding.get('shares_held') is not None
                    else holding.get('quantity'),
                    0.0,
                )
                cost_basis = average_cost * shares_held
                unrealized_pnl = market_value - cost_basis
                unrealized_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0
                
                holdings_data.append({
                    'Symbol': holding.get('symbol', 'N/A'),
                    'Shares': format_shares(shares_held),
                    'Avg Cost': format_currency(average_cost),
                    'Current Price': format_currency(_safe_float(holding.get('current_price'), 0.0)),
                    'Market Value': format_currency(market_value),
                    'Cost Basis': format_currency(cost_basis),
                    'P&L %': format_percentage(unrealized_pct),
                    'Weight': f"{((_safe_float(market_value, 0.0) / _safe_float(total_value, 0.0)) * 100):.2f}%" if _safe_float(total_value, 0.0) > 0 and _safe_float(market_value, 0.0) > 0 else "0.00%"
                })
        
        if holdings_data:
            df_holdings = pd.DataFrame(holdings_data)
            
            # Style the dataframe with institutional formatting
            def highlight_pnl(val):
                color = 'inherit'
                if isinstance(val, str) and val.startswith('+'):
                    color = '#16a34a'
                elif isinstance(val, str) and val.startswith('-'):
                    color = '#dc2626'
                return f'color: {color}'
            
            # Display the dataframe without styling the Signal column
            display_columns = ['Symbol', 'Shares', 'Avg Cost', 'Current Price', 'Market Value', 'Cost Basis', 'P&L %', 'Weight']
            df_display = df_holdings[display_columns]
            
            # Apply styling to P&L % column
            styled_df = df_display.style.applymap(highlight_pnl, subset=['P&L %'])
            st.dataframe(styled_df, hide_index=True, width='stretch')
            
            # Add View Analysis buttons in a clean grid layout
            st.markdown("#### 📊 Stock Analysis")
            
            # Calculate optimal grid layout (4 columns max for desktop)
            num_holdings = len(holdings_data)
            cols_per_row = min(4, max(2, num_holdings))
            cols = st.columns(cols_per_row)
            
            for i, holding_data in enumerate(holdings_data):
                col_idx = i % cols_per_row
                symbol = holding_data['Symbol']
                
                with cols[col_idx]:
                    # Link to professional overview page with symbol (same page)
                    st.markdown(
                        f'<a href="http://localhost:8501/Stock_Overview_Pro?symbol={symbol}"><button style="background-color:#0f7938;color:white;border:none;padding:0.5rem 1rem;border-radius:0.25rem;cursor:pointer;width:100%;">📊 {symbol}</button></a>',
                        unsafe_allow_html=True,
                    )
            
            # Portfolio allocation chart
            st.markdown("#### 📊 Portfolio Allocation")
            
            # Create allocation pie chart
            fig = go.Figure(data=[go.Pie(
                labels=[h['symbol'] for h in holdings],
                values=[_safe_float(h.get('market_value'), 0.0) for h in holdings],
                hole=0.3,
                textinfo='label+percent',
                textposition='outside'
            )])
            
            fig.update_layout(
                title="Portfolio Allocation by Market Value",
                plot_bgcolor='white',
                paper_bgcolor='white',
                showlegend=True,
                legend=dict(
                    orientation="v",
                    yanchor="middle",
                    y=0.5,
                    xanchor="left",
                    font=dict(size=10)
                )
            )
            
            st.plotly_chart(fig, width='stretch')
    else:
        st.warning("No holdings data available for this portfolio")
        
        # Clear progress bar
        if len(holdings) > 20:
            st.empty()
        
        if holdings_data:
            
            for i, holding_data in enumerate(holdings_data):
                col_idx = i % len(cols)
                with cols[col_idx]:
                    # Link to professional overview page with symbol (same page)
                    st.markdown(
                        f'<a href="http://localhost:8501/Stock_Overview_Pro?symbol={holding_data["Symbol"]}"><button style="background-color:#0f7938;color:white;border:none;padding:0.5rem 1rem;border-radius:0.25rem;cursor:pointer;width:100%;">📊 {holding_data["Symbol"]}</button></a>',
                        unsafe_allow_html=True,
                    )
            
            st.markdown("---")
            
            # Portfolio summary
            total_pnl = total_value - total_cost
            total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
            
            st.markdown("#### 💰 Portfolio Summary")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Value", format_currency(total_value, "$0.00"))
            
            with col2:
                st.metric("Total Cost", format_currency(total_cost, "$0.00"))
            
            with col3:
                st.metric("Total P&L", format_currency(total_pnl, "$0.00"))
            
            with col4:
                st.metric("Return %", f"{float(total_pnl_pct):.2f}%" if total_pnl_pct is not None else "0.00%")
        
        # Add symbol form
        if st.session_state.get('show_add_symbol', False):
            st.markdown("#### ➕ Add Symbol to Portfolio")
            
            with st.form("add_symbol_form"):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    symbol = st.text_input("Symbol*", placeholder="e.g., AAPL").upper()
                
                with col2:
                    asset_type = st.selectbox("Type*", ["stock", "regular_etf", "3x_etf"])
                
                with col3:
                    shares = st.number_input("Shares", min_value=0.0, value=100.0, step=10.0)
                
                with col4:
                    avg_cost = st.number_input("Avg Cost ($)", min_value=0.0, value=0.0, step=0.01)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("➕ Add Symbol", type="primary"):
                        if symbol:
                            holding = add_portfolio_holding(portfolio['id'], symbol, asset_type, shares, avg_cost)
                            if holding:
                                st.success(f"✅ {symbol} added to portfolio!")
                                st.session_state.show_add_symbol = False
                                st.rerun()
                        else:
                            st.error("Symbol is required")
                
                with col2:
                    if st.form_submit_button("❌ Cancel"):
                        st.session_state.show_add_symbol = False
                        st.rerun()
    
    # Show message if no holdings
    if not holdings:
        st.info("📋 No holdings in this portfolio. Add symbols to get started!")

def show_analysis_results(result: Dict[str, Any]):
    """Show portfolio analysis results"""
    st.markdown("### 📊 Analysis Results")
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📈 Symbols Analyzed", result['symbols_analyzed'])
    
    with col2:
        st.metric("🎯 Signals Generated", result['signals_generated'])
    
    with col3:
        st.metric("✅ Success Rate", f"{result['success_rate']:.1f}%")
    
    with col4:
        st.metric("📅 Analysis Date", result['analysis_date'])
    
    # Signal results
    if result.get('results'):
        st.markdown("#### 🎯 Generated Signals")
        
        signals_data = []
        for signal_result in result['results']:
            signals_data.append({
                'Symbol': signal_result['symbol'],
                'Signal': signal_result['signal'],
                'Confidence': f"{signal_result['confidence']:.1f}%",
                'Price': f"${signal_result['price']:.2f}"
            })
        
        df_signals = pd.DataFrame(signals_data)
        
        # Color code signals
        def color_signal(val):
            if val == 'BUY':
                return 'background-color: #E8F5E8; color: #00C851'
            elif val == 'SELL':
                return 'background-color: #FFEBEE; color: #FF4444'
            else:
                return 'background-color: #FFF3E0; color: #FF8800'
        
        styled_df = df_signals.style.applymap(color_signal, subset=['Signal'])
        st.dataframe(styled_df, width='stretch')
        
        # Signal distribution chart
        signal_counts = {'BUY': 0, 'SELL': 0, 'HOLD': 0}
        for signal_result in result['results']:
            signal_type = signal_result['signal']
            if signal_type in signal_counts:
                signal_counts[signal_type] += 1
        
        if sum(signal_counts.values()) > 0:
            fig = PortfolioVisualizer.create_signal_distribution_chart(signal_counts)
            st.plotly_chart(fig, width='stretch')

def load_all_symbol_data(symbol: str):
    """Load all data types for a single symbol (similar to Trading Dashboard)"""
    # All data types to load (same as Trading Dashboard)
    all_data_types = [
        "price_historical",
        "price_current", 
        "price_intraday_5m",
        "fundamentals",
        "indicators",
        "news",
        "earnings",
        "industry_peers",
    ]
    
    with st.spinner(f"Loading all data for {symbol} ({', '.join(all_data_types)})..."):
        try:
            response = go_client.post("api/v1/admin/refresh", json_data={
                "symbols": [symbol],
                "data_types": all_data_types,
                "force": True,  # Always force refresh for Load All Data
            }, timeout=180)  # 3 minute timeout for single symbol data load
            
            if response and response.get("success"):
                st.success(f"✅ Load All triggered successfully for {symbol}!")
                st.info(f"Loaded data types: {', '.join(all_data_types)}")
                
                # Clear cached analysis to force refresh with new data
                cache_key = f"analysis_{symbol}"
                if cache_key in st.session_state:
                    del st.session_state[cache_key]
                
                # Auto-refresh analysis after loading data
                st.rerun()
                
                # Show response details in expander
                with st.expander("📊 Load Details", expanded=False):
                    st.json(response)
            else:
                st.error(f"❌ Failed to load data: {response.get('error', 'Unknown error')}")
                
        except Exception as e:
            st.error(f"❌ Error loading data for {symbol}: {str(e)}")

def load_all_portfolio_data(portfolio_id: str):
    """Load all data types for all symbols in portfolio (similar to Trading Dashboard)"""
    holdings = get_portfolio_holdings(portfolio_id)
    
    if not holdings:
        st.warning("⚠️ No symbols found in portfolio to load data for")
        return
    
    symbols = [holding['symbol'] for holding in holdings]
    
    # All data types to load (same as Trading Dashboard)
    all_data_types = [
        "price_historical",
        "price_current", 
        "price_intraday_5m",
        "fundamentals",
        "indicators",
        "news",
        "earnings",
        "industry_peers",
    ]
    
    with st.spinner(f"Loading all data for {len(symbols)} symbols ({', '.join(all_data_types)})..."):
        try:
            response = go_client.post("api/v1/admin/refresh", json_data={
                "symbols": symbols,
                "data_types": all_data_types,
                "force": True,  # Always force refresh for Load All Data
            }, timeout=300)  # 5 minute timeout for portfolio-wide data load
            
            if response and response.get("success"):
                st.success(f"✅ Load All triggered successfully for {len(symbols)} symbols!")
                st.info(f"Loaded data types: {', '.join(all_data_types)}")
                
                # Show response details in expander
                with st.expander("📊 Load Details", expanded=False):
                    st.json(response)
            else:
                st.error(f"❌ Failed to load data: {response.get('error', 'Unknown error')}")
                
        except Exception as e:
            st.error(f"❌ Error loading portfolio data: {str(e)}")

def load_portfolio_data(portfolio_id: str):
    """Load data for all symbols in portfolio"""
    holdings = get_portfolio_holdings(portfolio_id)
    
    if holdings:
        symbols = [holding['symbol'] for holding in holdings]
        
        with st.spinner(f"Loading data for {len(symbols)} symbols..."):
            try:
                response = go_client.post("api/v1/admin/refresh", json_data={
                    "symbols": symbols,
                    "data_types": ["price_historical", "indicators"],
                    "force": True
                })
                
                if response and response.get("success"):
                    st.success(f"✅ Data loaded successfully for {len(symbols)} symbols!")
                else:
                    st.error(f"❌ Failed to load data: {response.get('error', 'Unknown error')}")
            except Exception as e:
                st.error(f"❌ Error loading data: {str(e)}")
    else:
        st.warning("⚠️ No symbols found in portfolio")

# ========================================
# ========================================
# Symbol Analysis Functions
# ========================================

def get_symbol_analysis(symbol: str, asset_type: str = "stock"):
    """Get detailed analysis for a specific symbol"""
    try:
        payload = {
            "symbol": symbol,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "asset_type": asset_type
        }
        
        response = go_client.post(
            "api/v1/admin/universal/signal/universal",
            json_data=payload,
            timeout=180,
        )
        
        if response and response.get("success"):
            return response["data"]
        else:
            return {"error": response.get("error", "Unknown error")}
            
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}

def refresh_symbol_analysis(symbol: str, asset_type: str = "stock"):
    """Refresh analysis for a specific symbol"""
    _ = asset_type
    try:
        go_client.post(
            "api/v1/admin/refresh",
            json_data={
                "symbols": [symbol],
                "data_types": ["price_historical", "indicators"],
                "force": True,
            },
            timeout=180,
        )
        return True
    except Exception as e:
        st.error(f"Error refreshing analysis: {str(e)}")
        return False

def show_symbol_analysis(symbol: str):
    """Show detailed analysis for a symbol using shared component"""
    st.markdown(f"### 📊 Detailed Analysis - {symbol}")
    
    # Action buttons for symbol analysis
    st.markdown("#### 🎯 Analysis Actions")
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if st.button("🔄 Load All Data", type="primary", width='stretch', help=f"Load fresh data for {symbol}"):
            load_all_symbol_data(symbol)
    
    with col2:
        if st.button("📊 Refresh Analysis", width='stretch', help=f"Refresh analysis for {symbol}"):
            refresh_symbol_analysis(symbol)
    
    with col3:
        if st.button("← Back to Portfolio", width='stretch'):
            st.session_state.show_symbol_analysis = False
            st.session_state.selected_symbol_for_analysis = None
            st.rerun()
    
    st.markdown("---")
    
    # ALWAYS get fresh analysis for the selected symbol (no caching)
    with st.spinner(f"Loading fresh analysis for {symbol}..."):
        asset_type = "stock"  # Default, could be enhanced to get from holdings
        analysis_data = get_symbol_analysis(symbol, asset_type)

    # Enrich displayed technical reasoning with fundamentals overlay (best-effort).
    try:
        if isinstance(analysis_data, dict):
            overlay = analysis_data.get("fundamentals_overlay")
            sig = analysis_data.get("signal")
            if isinstance(overlay, dict) and isinstance(sig, dict):
                risk_state = str(overlay.get("risk_state") or "UNKNOWN")
                pos_mult = overlay.get("position_size_multiplier")
                conf_cap = overlay.get("confidence_cap")
                alerts = overlay.get("active_fundamental_alerts") or []

                # Cap displayed confidence if present.
                try:
                    if conf_cap is not None and sig.get("confidence") is not None:
                        sig["confidence"] = float(min(float(sig.get("confidence")), float(conf_cap)))
                except Exception:
                    pass

                # Append overlay to reasoning.
                try:
                    rs: List[str] = []
                    if isinstance(sig.get("reasoning"), list):
                        rs = [str(x) for x in sig.get("reasoning") if x is not None]
                    overlay_reason = f"Fundamentals overlay: risk_state={risk_state}, position_size_multiplier={pos_mult}, confidence_cap={conf_cap}"
                    if isinstance(alerts, list) and alerts:
                        top = "; ".join([str(a) for a in alerts[:3] if a is not None])
                        overlay_reason = overlay_reason + f" | alerts: {top}"
                    rs.append(overlay_reason)
                    sig["reasoning"] = rs
                except Exception:
                    pass
                analysis_data["signal"] = sig
    except Exception:
        pass
    
    # Cache the analysis for potential reuse within this session
    cache_key = f"analysis_{symbol}"
    status = None
    if isinstance(analysis_data, dict):
        sig = analysis_data.get("signal")
        if isinstance(sig, dict):
            status = sig.get("status")

    if analysis_data and not analysis_data.get('error') and status != "data_missing":
        st.session_state[cache_key] = analysis_data
    elif cache_key in st.session_state:
        del st.session_state[cache_key]
    
    # Display analysis using shared component
    if analysis_data and not analysis_data.get('error'):
        display_signal_analysis(symbol, analysis_data, show_header=True, show_debug=True)
    else:
        display_no_data_message(symbol, analysis_data.get('error') if analysis_data else None, context="main")
    
    # Add Fundamentals Analysis section
    st.markdown("---")
    st.markdown("### 💰 Fundamentals Analysis")
    
    # Add tabs for different analysis types
    tab1, tab2 = st.tabs(["📊 Technical Analysis", "💰 Fundamentals Analysis"])
    
    with tab1:
        # Current technical analysis (already displayed above)
        if analysis_data and not analysis_data.get('error'):
            st.info("Technical analysis shown above")
        else:
            display_no_data_message(symbol, analysis_data.get('error') if analysis_data else None, context="tab1")
    
    with tab2:
        # Fundamentals analysis
        try:
            cached = get_cached_fundamentals_analysis(symbol)
            if cached:
                _render_fundamentals_analysis(cached)
            else:
                with st.spinner(f"Loading fundamentals analysis for {symbol}..."):
                    response = go_client.get(f"api/v1/admin/growth-quality/growth-health/{symbol}")

                if response and isinstance(response, dict):
                    data = response
                    cache_fundamentals_analysis(symbol, data)
                    _render_fundamentals_analysis(data)
                else:
                    err = response.get('error', 'Unknown error') if isinstance(response, dict) else 'Unknown error'
                    st.error(f"❌ Error: {err}")
                    
                    # Show retry button
                    if st.button("🔄 Retry Analysis", key=f"retry_error_fundamentals_{symbol}"):
                        st.rerun()

            st.markdown("---")
            try:
                ew = go_client.get(f"api/v1/admin/growth-quality/early-warning/{symbol}")
                if isinstance(ew, dict):
                    items = _build_fundamentals_change_feed_items_from_early_warning(ew)
                    _render_fundamentals_change_feed(items)
                else:
                    _render_fundamentals_change_feed([])
            except Exception:
                _render_fundamentals_change_feed([])

        except requests.exceptions.RequestException as e:
            st.error(f"❌ Connection error: Unable to reach analysis service")
            st.error(f"🔍 Details: {str(e)}")
            st.info("💡 Please check if the Python Worker service is running")
            
            # Show retry button
            if st.button("🔄 Retry Connection", key=f"retry_connection_{symbol}"):
                st.rerun()
                
        except Exception as e:
            st.error(f"❌ Unexpected error in fundamentals analysis")
            st.error(f"🔍 Details: {str(e)}")
            st.info("💡 Please try refreshing the page or contact support")
            
            # Show retry button
            if st.button("🔄 Refresh Page", key=f"refresh_page_{symbol}"):
                st.rerun()


def _render_comprehensive_fundamentals_analysis(symbol: str):
    """Render comprehensive fundamentals analysis with professional visualizations"""
    try:
        # Fetch early warning analysis
        analysis_data = go_client.get(f"api/v1/admin/growth-quality/early-warning/{symbol}")
        
        if analysis_data and isinstance(analysis_data, dict):
            _render_fundamentals_risk_overview(analysis_data, symbol)
            _render_fundamentals_detailed_flags(analysis_data)
            _render_fundamentals_metrics_dashboard(analysis_data)
        else:
            st.warning(f"⚠️ No fundamentals data available for {symbol}")
            
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Network error loading analysis for {symbol}: {str(e)}")
    except Exception as e:
        st.error(f"❌ Error loading comprehensive analysis for {symbol}: {str(e)}")


def _build_fundamentals_change_feed_items_from_early_warning(analysis_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    overall_risk = (analysis_data or {}).get("overall_risk")
    warnings = (analysis_data or {}).get("warnings") or []
    metrics = (analysis_data or {}).get("metrics") or {}

    if overall_risk:
        severity = "LOW"
        direction = "neutral"
        action = "No action required"
        if overall_risk == "YELLOW":
            severity = "MEDIUM"
            direction = "negative"
            action = "Reduce size and tighten risk controls"
        elif overall_risk == "RED":
            severity = "HIGH"
            direction = "negative"
            action = "Avoid adding; consider trimming/exiting depending on your plan"

        evidence: List[str] = []
        for k in ["receivables_vs_revenue_growth", "margin_trend", "roe_trend"]:
            if k in metrics:
                evidence.append(f"{k}: {metrics.get(k)}")

        items.append(
            {
                "headline": f"Overall fundamentals risk: {overall_risk}",
                "severity": severity,
                "direction": direction,
                "evidence": evidence,
                "recommended_action": action,
            }
        )

    if isinstance(warnings, list):
        for w in warnings[:5]:
            if not isinstance(w, str) or not w.strip():
                continue
            items.append(
                {
                    "headline": w.strip(),
                    "severity": "MEDIUM" if overall_risk in {"YELLOW", "RED"} else "LOW",
                    "direction": "negative",
                    "evidence": [],
                    "recommended_action": "Monitor next quarter update; reduce position size if this persists",
                }
            )

    return items


def _render_fundamentals_change_feed(items: List[Dict[str, Any]]):
    st.markdown("### 📰 Fundamentals Change Feed")
    if not items:
        st.info("No fundamentals change items available yet")
        return

    severity_icon = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}
    direction_icon = {"positive": "⬆️", "negative": "⬇️", "neutral": "➡️"}
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        headline = str(it.get("headline") or "")
        severity = str(it.get("severity") or "LOW").upper()
        direction = str(it.get("direction") or "neutral").lower()
        evidence = it.get("evidence") or []
        recommended_action = str(it.get("recommended_action") or "")

        title = f"{severity_icon.get(severity, '🟢')} {direction_icon.get(direction, '➡️')} {headline}"
        with st.expander(title, expanded=(i == 0)):
            st.caption(f"Severity: {severity} | Direction: {direction}")
            if isinstance(evidence, list) and evidence:
                st.markdown("**Evidence**")
                for ev in evidence[:3]:
                    st.write(str(ev))
            if recommended_action:
                st.markdown("**Recommended action**")
                st.write(recommended_action)

def _render_fundamentals_risk_overview(analysis_data: Dict[str, Any], symbol: str):
    """Render risk overview with professional styling"""
    overall_risk = analysis_data.get('overall_risk', 'GREEN')
    
    risk_colors = {
        'GREEN': '#38ef7d',
        'YELLOW': '#f5576c', 
        'RED': '#eb3349'
    }
    
    risk_icons = {
        'GREEN': '✅',
        'YELLOW': '⚠️',
        'RED': '🚨'
    }
    
    risk_descriptions = {
        'GREEN': 'Low Structural Risk - Balance sheet strong, revenue quality clean',
        'YELLOW': 'Medium Structural Risk - Some concerns but no critical issues',
        'RED': 'High Structural Risk - Structural issues or red flags detected'
    }
    
    # Main risk card
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {risk_colors.get(overall_risk, '#38ef7d')} 0%, #667eea 100%); 
                padding: 20px; border-radius: 15px; color: white; margin: 20px 0;">
        <h3>{risk_icons.get(overall_risk, '')} {symbol} Overall Risk: {overall_risk}</h3>
        <p>{risk_descriptions.get(overall_risk, '')}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Domain risks
    domain_risks = analysis_data.get('domain_risks', {})
    if domain_risks:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📊 Revenue Quality")
            revenue_risk = domain_risks.get('revenue_risk', 'NO_RISK')
            _render_domain_risk_gauge(revenue_risk, "Revenue Quality")
            
            st.markdown("### 💰 Capital Efficiency")
            capital_risk = domain_risks.get('capital_risk', 'NO_RISK')
            _render_domain_risk_gauge(capital_risk, "Capital Efficiency")
        
        with col2:
            st.markdown("### 📈 Margin Stress")
            margin_risk = domain_risks.get('margin_risk', 'NO_RISK')
            _render_domain_risk_gauge(margin_risk, "Margin Stress")
            
            st.markdown("### 🎯 Management Signals")
            mgmt_risk = domain_risks.get('management_risk', 'NO_RISK')
            _render_domain_risk_gauge(mgmt_risk, "Management Signals")

def _render_domain_risk_gauge(risk_level: str, title: str):
    """Render individual domain risk gauge"""
    risk_values = {'NO_RISK': 0, 'EARLY_STRESS': 50, 'STRUCTURAL_BREAKDOWN': 100}
    risk_colors = {'NO_RISK': '#38ef7d', 'EARLY_STRESS': '#f5576c', 'STRUCTURAL_BREAKDOWN': '#eb3349'}
    
    fig = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        value = risk_values.get(risk_level, 0),
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': title},
        delta = {'reference': 0},
        gauge = {
            'axis': {'range': [None, 100]},
            'bar': {'color': risk_colors.get(risk_level, '#38ef7d')},
            'steps': [
                {'range': [0, 33], 'color': "lightgray"},
                {'range': [33, 66], 'color': "gray"},
                {'range': [66, 100], 'color': "darkgray"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 80
            }
        }
    ))
    
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, width='stretch')

def _render_fundamentals_detailed_flags(analysis_data: Dict[str, Any]):
    """Render detailed flag analysis"""
    st.markdown("### 🔍 Detailed Risk Flags Analysis")
    
    # Warnings and insights
    warnings = analysis_data.get('warnings', [])
    insights = analysis_data.get('insights', [])
    
    if warnings:
        st.markdown("#### ⚠️ Risk Warnings")
        for warning in warnings:
            st.error(f"• {warning}")
    
    if insights:
        st.markdown("#### ✅ Positive Insights")
        for insight in insights:
            st.success(f"• {insight}")
    
    # Metrics analysis
    metrics = analysis_data.get('metrics', {})
    if metrics:
        st.markdown("#### 📊 Key Metrics Analysis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            for metric_name, value in list(metrics.items())[:len(metrics)//2]:
                st.metric(metric_name.replace('_', ' ').title(), str(value))
        
        with col2:
            for metric_name, value in list(metrics.items())[len(metrics)//2:]:
                st.metric(metric_name.replace('_', ' ').title(), str(value))

def _render_fundamentals_metrics_dashboard(analysis_data: Dict[str, Any]):
    """Render comprehensive metrics dashboard"""
    st.markdown("### 📈 Fundamentals Metrics Dashboard")
    
    # Create metrics overview
    metrics = analysis_data.get('metrics', {})
    if not metrics:
        st.info("No detailed metrics available")
        return
    
    # Key financial metrics
    col1, col2, col3, col4 = st.columns(4)
    
    key_metrics = {
        'receivables_vs_revenue_growth': 'Receivables vs Revenue',
        'margin_trend': 'Margin Trend',
        'roe_trend': 'ROE Trend',
        'roic_trend': 'ROIC Trend',
        'growth_vs_capital': 'Growth vs Capital',
        'debt_level': 'Debt Level'
    }
    
    for i, (metric_key, display_name) in enumerate(list(key_metrics.items())[:4]):
        col = [col1, col2, col3, col4][i]
        with col:
            value = metrics.get(metric_key, 'N/A')
            st.metric(display_name, str(value))
    
    # Analysis date
    analysis_date = analysis_data.get('analysis_date', 'Unknown')
    st.caption(f"Analysis as of: {analysis_date}")


def _render_fundamentals_analysis(data: Dict[str, Any]):
    """Render institutional-grade fundamentals analysis with corrected logic"""
    symbol = data.get('symbol', 'Unknown')
    
    # Structural Risk Assessment
    structural_risk = data.get('structural_risk', 'LOW')
    structural_icons = {
        'LOW': '🟢',
        'MEDIUM': '🟡',
        'HIGH': '🔴'
    }
    
    structural_descriptions = {
        'LOW': 'Low Structural Risk - Balance sheet strong, revenue quality clean',
        'MEDIUM': 'Medium Structural Risk - Some concerns but no critical issues',
        'HIGH': 'High Structural Risk - Structural issues or red flags detected'
    }
    
    # Growth Phase Assessment
    growth_phase = data.get('growth_phase', 'MATURE_COMPOUNDER')
    growth_icons = {
        'HEALTHY_COMPOUNDER': '🟢',
        'MATURE_COMPOUNDER': '🟡',
        'GROWTH_DEGRADATION': '🟠',
        'GROWTH_BREAKDOWN': '🔴'
    }
    
    growth_descriptions = {
        'HEALTHY_COMPOUNDER': 'Accelerating Compounder - Revenue + margins + ROIC expanding',
        'MATURE_COMPOUNDER': 'Mature Compounder - Growth persists but efficiency and margins are no longer expanding',
        'GROWTH_DEGRADATION': 'Growth Degrading - Growth trajectory showing material slowdown',
        'GROWTH_BREAKDOWN': 'Growth Breakdown - Structural business issues detected'
    }
    
    # Investment Posture
    investment_posture = data.get('investment_posture', 'HOLD_SELECTIVE_ADD')
    posture_icons = {
        'BUY': '🟢',
        'HOLD_SELECTIVE_ADD': '🟡',
        'TRIM_REDUCE': '🟠',
        'EXIT_AVOID': '🔴'
    }
    
    posture_descriptions = {
        'BUY': 'BUY - Aggressive accumulation recommended',
        'HOLD_SELECTIVE_ADD': 'HOLD / SELECTIVE ADD - Suitable for core holding; add selectively during market pullbacks',
        'TRIM_REDUCE': 'TRIM / REDUCE - Reduce position size',
        'EXIT_AVOID': 'EXIT / AVOID - Capital preservation priority'
    }
    
    # Forward Returns
    forward_returns = data.get('forward_return_expectation', '6-10% annualized (cash flows + buybacks)')
    
    # Main Assessment Card
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 25px; border-radius: 15px; color: white; margin: 20px 0;">
        <h2>{structural_icons.get(structural_risk, '🟢')} {symbol} Fundamentals Assessment</h2>
        <p style="font-size: 18px; margin: 15px 0;"><strong>{structural_descriptions.get(structural_risk, '')}</strong></p>
    </div>
    """, unsafe_allow_html=True)
    
    # Growth Phase and Investment Posture
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        <div style="background: {growth_phase == 'HEALTHY_COMPOUNDER' and '#d4edda' or growth_phase == 'MATURE_COMPOUNDER' and '#fff3cd' or growth_phase == 'GROWTH_DEGRADATION' and '#f8d7da' or '#f5c6cb'}; 
                    padding: 20px; border-radius: 10px; margin: 10px 0;">
            <h3>{growth_icons.get(growth_phase, '🟡')} Growth Phase</h3>
            <p><strong>{growth_descriptions.get(growth_phase, '')}</strong></p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div style="background: {investment_posture == 'BUY' and '#d4edda' or investment_posture == 'HOLD_SELECTIVE_ADD' and '#fff3cd' or investment_posture == 'TRIM_REDUCE' and '#f8d7da' or '#f5c6cb'}; 
                    padding: 20px; border-radius: 10px; margin: 10px 0;">
            <h3>{posture_icons.get(investment_posture, '🟡')} Investment Posture</h3>
            <p><strong>{posture_descriptions.get(investment_posture, '')}</strong></p>
        </div>
        """, unsafe_allow_html=True)
    
    # Forward Return Expectation
    st.markdown(f"""
    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 15px 0; border-left: 5px solid #007bff;">
        <h3>📈 Forward Return Outlook</h3>
        <p style="font-size: 16px;"><strong>{forward_returns}</strong></p>
    </div>
    """, unsafe_allow_html=True)
    
    # Key Insights
    reasoning = data.get('reasoning', [])
    if reasoning:
        st.markdown("### 🎯 Key Assessment Points")
        for point in reasoning:
            st.success(f"• {point}")
    
    # Risk Factors with Critical Impact Analysis
    risk_factors = data.get('risk_factors', [])
    if risk_factors:
        st.markdown("### ⚠️ Critical Risk Factors")
        for factor in risk_factors:
            # Determine risk impact level
            if any(phrase in factor.lower() for phrase in ['margin declining', 'growth vs capital mismatch', 'structural breakdown']):
                st.error(f"🚨 **CRITICAL**: {factor} - Prevents BUY recommendation")
            elif any(phrase in factor.lower() for phrase in ['monitor', 'concerns', 'pressure']):
                st.warning(f"⚠️ **WARNING**: {factor} - May limit returns")
            else:
                st.info(f"ℹ️ **NOTE**: {factor}")
    
    # Risk-to-Decision Summary
    st.markdown("### 📋 Risk-to-Decision Analysis")
    
    # Show why investment posture was chosen
    if investment_posture == 'BUY':
        st.success("✅ **BUY Justification**: All critical risk factors cleared - Growth phase accelerating with strong fundamentals")
    elif investment_posture == 'HOLD_SELECTIVE_ADD':
        if growth_phase == 'MATURE_COMPOUNDER':
            st.info("🟡 **HOLD Justification**: Mature compounder with stable but non-accelerating growth - Suitable for core holding")
        else:
            st.warning("🟡 **HOLD Justification**: Some risk factors present - Monitor closely")
    elif investment_posture == 'TRIM_REDUCE':
        st.warning("🟠 **TRIM Justification**: Growth degradation or medium structural risk detected - Reduce exposure")
    elif investment_posture == 'EXIT_AVOID':
        st.error("🔴 **EXIT Justification**: Structural breakdown or growth breakdown detected - Capital preservation priority")
    
    # Risk Gate Status
    st.markdown("### 🚪 Risk Gate Status")
    
    # Get domain risks from analysis data
    domain_risks = data.get('domain_risks', {})
    
    # Ensure domain_risks is a dictionary
    if not isinstance(domain_risks, dict):
        st.error("❌ Invalid domain risks data format")
        domain_risks = {}
    
    gates = {
        "Revenue Quality": domain_risks.get('revenue_risk', 'NO_RISK') == 'NO_RISK',
        "Margin Stability": domain_risks.get('margin_risk', 'NO_RISK') == 'NO_RISK', 
        "Capital Efficiency": domain_risks.get('capital_risk', 'NO_RISK') == 'NO_RISK',
        "Structural Risk": structural_risk == 'LOW'
    }
    
    for gate_name, passed in gates.items():
        if passed:
            st.success(f"✅ {gate_name}: PASSED")
        else:
            st.error(f"❌ {gate_name}: FAILED - Blocks BUY signal")
    
    # Golden Rule Status
    st.markdown("### 🏛️ Golden Rule Check")
    if investment_posture == 'BUY' and growth_phase == 'HEALTHY_COMPOUNDER':
        st.success("✅ **PASSED**: BUY allowed only when Growth Phase = Accelerating")
    elif investment_posture != 'BUY' and growth_phase != 'HEALTHY_COMPOUNDER':
        st.info("ℹ️ **CORRECTLY APPLIED**: Non-BUY posture for non-accelerating growth")
    else:
        st.warning("⚠️ **REVIEW**: Check if posture matches growth phase")
    
    # Opportunities
    opportunities = data.get('opportunities', [])
    if opportunities:
        st.markdown("### 💡 Opportunities")
        for opportunity in opportunities:
            st.info(f"• {opportunity}")
    
    # Confidence Score
    confidence = data.get('confidence', 0.85)
    st.markdown(f"""
    <div style="background: #e9ecef; padding: 15px; border-radius: 8px; margin: 15px 0;">
        <p><strong>Analysis Confidence:</strong> {confidence:.1%}</p>
        <div style="background: #ddd; height: 10px; border-radius: 5px;">
            <div style="background: #28a745; width: {confidence*100}%; height: 10px; border-radius: 5px;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Critical Rule Display (Golden Rule)
    if investment_posture == 'BUY' and growth_phase != 'HEALTHY_COMPOUNDER':
        st.error("🚨 **CRITICAL WARNING**: This analysis shows a BUY recommendation but growth phase is not accelerating. This violates the golden rule: NEVER allow BUY when Growth Phase ≠ Accelerating. Please review the analysis logic.")
    elif investment_posture == 'BUY' and growth_phase == 'HEALTHY_COMPOUNDER':
        st.success("✅ **Valid BUY Signal**: Growth phase is accelerating, supporting the BUY recommendation.")
    elif investment_posture == 'HOLD_SELECTIVE_ADD' and growth_phase == 'MATURE_COMPOUNDER':
        st.info("✅ **Valid HOLD Signal**: Mature compounder with low structural risk - appropriate for core holding.")
    
    # Analysis Date
    analysis_date = data.get('analysis_date', datetime.now().strftime('%Y-%m-%d'))
    st.caption(f"Analysis as of: {analysis_date}")


# Main Page Logic
# ========================================

def main():
    """Main page logic with session persistence"""
    setup_page_config("Portfolio Analysis", "📊")
    
    # Initialize session state variables if they don't exist
    if 'session_initialized' not in st.session_state:
        st.session_state.session_initialized = True
        if 'current_user' not in st.session_state:
            st.session_state.current_user = None
    
    # Custom CSS for institutional appearance
    st.markdown("""
    <style>
    .portfolio-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
        padding: 2.5rem; 
        border-radius: 15px; 
        color: white; 
        margin-bottom: 2rem; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        text-align: center;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    }
    
    .institutional-metric {
        background: white;
        padding: 1.5rem; 
        border-radius: 10px; 
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        border-left: 4px solid #1e40af;
        margin-bottom: 1rem;
        transition: all 0.3s ease;
    }
    
    .institutional-metric:hover {
        box-shadow: 0 8px 12px rgba(0, 0, 0, 0.15);
        transform: translateY(-2px);
    }
    
    .risk-high {
        background: linear-gradient(135deg, #fef2f2 0%, #f87171 100%);
        border-left: 4px solid #ef4444;
    }
    
    .risk-moderate {
        background: linear-gradient(135deg, #fef3c7 0%, #fbbf24 100%);
        border-left: 4px solid #f59e0b;
    }
    
    .risk-low {
        background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
        border-left: 4px solid #22c55e;
    }
    
    .signal-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.875rem;
        font-weight: 600;
        text-align: center;
        transition: all 0.2s ease;
    }
    
    .buy-signal { 
        background: #E8F5E8; 
        color: #00C851; 
        border: 1px solid #00C851;
    }
    
    .sell-signal { 
        background: #FFEBEE; 
        color: #FF4444; 
        border: 1px solid #FF4444;
    }
    
    .hold-signal { 
        background: #FFF3E0; 
        color: #FF8800; 
        border: 1px solid #FF8800;
    }
    
    .add-signal { 
        background: #E8F5E8; 
        color: #00C851; 
        border: 1px solid #00C851;
    }
    
    .reduce-signal { 
        background: #FFF3E0; 
        color: #FF8800; 
        border: 1px solid #FF8800;
    }
    
    .institutional-table {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        overflow: hidden;
    }
    
    .institutional-table th {
        background: #f8fafc;
        font-weight: 600;
        color: #1e293b8;
        border-bottom: 2px solid #e2e8f0;
        padding: 1rem;
    }
    
    .institutional-table td {
        border-bottom: 1px solid #f1f5f9;
        padding: 0.75rem 1rem;
        color: #475569;
    }
    
    .institutional-table tr:hover {
        background: #f8fafc;
    }
    
    .portfolio-summary {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); 
        padding: 2rem; 
        border-radius: 15px; 
        margin-bottom: 2rem; 
        border: 1px solid #cbd5e1;
    }
    
    .signal-summary {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); 
        color: white; 
        padding: 2rem; 
        border-radius: 15px; 
        margin-bottom: 2rem; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    
    .analysis-summary {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); 
        color: white; 
        padding: 2rem; 
        border-radius: 15px; 
        margin-bottom: 2rem; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    
    .institutional-button {
        background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
        color: white; 
        border: none; 
        border-radius: 8px; 
        padding: 0.75rem 1.5rem; 
        font-weight: 600; 
        transition: all 0.3s ease; 
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .institutional-button:hover {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        transform: translateY(-2px);
    }
    
    .institutional-button:active {
        background: linear-gradient(135deg, #1e40af 0%, #1e40af 100%);
        transform: translateY(0px);
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    </style>
    """, unsafe_allow_html=True)
    
    # Default user (no login selector on this page)
    # Option A: always use the base portfolio owner user_id
    st.session_state.current_user = _resolve_default_user()
    
    # User is authenticated - show full interface
    # Sidebar with user info and session status
    with st.sidebar:
        user = st.session_state.current_user or {}

        st.markdown(
            f"### 👤 {(user.get('full_name') or user.get('username') or user.get('email') or user.get('user_id') or 'User')}"
        )
        st.caption(f"Role: {str(user.get('role') or 'user').title()}")
        
        # Show session status
        if 'login_time' in st.session_state:
            try:
                login_time = datetime.fromisoformat(st.session_state.login_time)
                hours_since_login = (datetime.now() - login_time).total_seconds() / 3600
                remaining_hours = 24 - hours_since_login
                
                if remaining_hours > 0:
                    st.success(f"🔓 Session active")
                    st.caption(f"⏰ Expires in {remaining_hours:.1f} hours")
                else:
                    st.warning("⚠️ Session expired")
                    if st.button("🔄 Refresh Session", width='stretch'):
                        logout_user()
            except:
                st.warning("⚠️ Session status unknown")
        
        st.divider()
        
        if st.button("🔄 Refresh Data", width='stretch'):
            if 'selected_portfolio' in st.session_state:
                load_portfolio_data(st.session_state.selected_portfolio)
        
        # Logout removed from this page (no login state)
    
    # Main content with tabs
    portfolios = get_user_portfolios()
    
    if not portfolios:
        # Show create portfolio form for first-time users
        show_portfolio_overview()
        
        st.markdown("""
        <div style="background: #f8fafc; padding: 3rem; border-radius: 15px; text-align: center; border: 2px dashed #cbd5e1;">
            <div style="font-size: 4rem; margin-bottom: 1rem;">📋</div>
            <h2 style="color: #475569; margin-bottom: 1rem;">No Portfolios Yet</h2>
            <p style="color: #64748b; margin-bottom: 2rem;">Create your first portfolio to start institutional-grade analysis</p>
        </div>
        """, unsafe_allow_html=True)
        
        show_create_portfolio_form("first_portfolio_mgmt")
    else:
        # Tabbed interface for portfolio management
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
            "📊 Portfolio Overview", 
            "📋 Portfolio Management", 
            "📈 Stock Analysis", 
            "🏢 Stock Symbols",
            "📊 Analyst Ratings",
            "🔔 Alert Management",
            "⚙️ Settings",
            "⏰ Schedules"
        ])
        
        # Check if symbol analysis is requested and show it instead of tabs
        if st.session_state.get('show_symbol_analysis', False):
            symbol = st.session_state.get('selected_symbol_for_analysis')
            if symbol:
                # Clear any cached analysis for this symbol to ensure fresh data
                cache_key = f"analysis_{symbol}"
                if cache_key in st.session_state:
                    del st.session_state[cache_key]
                
                # Always show fresh analysis for the selected symbol
                show_symbol_analysis(symbol)
            else:
                st.error("No symbol selected for analysis")
                st.session_state.show_symbol_analysis = False
                st.rerun()
        else:
            with tab1:
                show_portfolio_overview_tab(portfolios)
            
            with tab2:
                show_portfolio_management_tab(portfolios)
            
            with tab3:
                show_stock_analysis_tab(portfolios)
            
            with tab4:
                show_stock_symbols_tab()
            
            with tab5:
                show_analyst_ratings_tab()
            
            with tab6:
                show_alert_management_tab()
            
            with tab7:
                show_settings_tab()

            with tab8:
                show_enhanced_portfolio_schedules_tab(portfolios)

def show_stock_symbols_tab():
    """Stock Symbols Management Tab - Add and view stock symbols"""
    st.markdown("## 🏢 Stock Symbols Management")
    st.markdown("Manage stock symbols in the system - add new symbols and view existing ones")
    
    # Initialize session state for form
    if 'add_symbol_form_visible' not in st.session_state:
        st.session_state.add_symbol_form_visible = False
    
    # Initialize session state for data loading
    if 'data_loading_config' not in st.session_state:
        st.session_state.data_loading_config = {
            'auto_refresh': False,
            'refresh_interval': 15,  # minutes
            'last_refresh': None,
            'loading_status': 'idle'
        }
    
    # Data Loading Controls Section
    st.markdown("### 🔄 Data Loading Configuration")
    st.markdown("Configure automatic data loading for all stock symbols")
    
    # Get scheduler status
    scheduler_status = get_scheduler_status()
    
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    
    with col1:
        auto_refresh = st.checkbox(
            "🔄 Auto-refresh Data",
            value=scheduler_status.get('is_running', False),
            help="Enable automatic data refresh for all symbols (background service)"
        )
    
    with col2:
        refresh_interval = st.selectbox(
            "⏱️ Refresh Interval",
            options=[5, 10, 15, 30, 60],
            index=[5, 10, 15, 30, 60].index(
                st.session_state.data_loading_config['refresh_interval']
            ),
            help="Minutes between automatic refreshes (configurable per data type)"
        )
    
    with col3:
        # Show scheduler stats
        if scheduler_status.get('is_running'):
            st.info(f"🟢 Active: {scheduler_status.get('active_schedules', 0)} schedules")
        else:
            st.info(f"🔴 Inactive: {scheduler_status.get('total_scheduled', 0)} schedules")
    
    with col4:
        # Scheduler control buttons
        if scheduler_status.get('is_running'):
            if st.button("⏹️ Stop", width='stretch'):
                stop_scheduler()
        else:
            if st.button("▶️ Start", width='stretch'):
                start_scheduler()
    
    # Manual Load All Stocks Button
    col_load1, col_load2, col_load3 = st.columns([2, 1, 1])
    
    with col_load1:
        if st.button("🚀 Load All Stocks Data", type="primary", width='stretch'):
            load_all_stocks_data()
    
    with col_load2:
        if st.button("🔄 Quick Refresh", width='stretch'):
            load_all_stocks_data(quick_mode=True)
    
    with col_load3:
        if st.button("📋 Schedule All", width='stretch'):
            schedule_all_symbols()
    
    # Show scheduler details
    if scheduler_status.get('is_running'):
        st.markdown("### 📊 Scheduler Status")
        
        col_sched1, col_sched2, col_sched3 = st.columns(3)
        
        with col_sched1:
            st.metric("🔄 Active Schedules", scheduler_status.get('active_schedules', 0))
        
        with col_sched2:
            st.metric("⏰ Next Refresh", 
                     format_time(scheduler_status.get('next_refresh')) if scheduler_status.get('next_refresh') else "N/A")
        
        with col_sched3:
            st.metric("📈 Total Symbols", scheduler_status.get('total_scheduled', 0))
        
        # Show upcoming refreshes
        upcoming = get_upcoming_refreshes()
        if upcoming.get('upcoming_refreshes'):
            st.markdown("#### 📅 Upcoming Refreshes")
            for refresh in upcoming['upcoming_refreshes'][:5]:
                st.info(f"🕐 {refresh['symbol']} - {refresh['data_type']} at {format_time(refresh['next_refresh'])}")
    
    # Add new symbol section
    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown("### ➕ Add New Symbol")
        st.markdown("Add a new stock symbol to the system for portfolio management")
        st.caption("💡 Company information is automatically fetched from Yahoo Finance")
    
    with col2:
        if st.button("📝 Add Symbol", type="primary", width='stretch'):
            st.session_state.add_symbol_form_visible = not st.session_state.add_symbol_form_visible
            st.rerun()
    
    # Show add symbol form
    if st.session_state.add_symbol_form_visible:
        show_add_symbol_form()
    
    # List all symbols section
    st.markdown("### 📋 All Stock Symbols")
    st.markdown("View and manage all stock symbols available in the system")
    
    # Fetch all symbols
    symbols_data = get_all_stock_symbols()
    
    if symbols_data:
        # Show success message with count
        st.success(f"✅ Found {len(symbols_data)} stock symbols in the system")
        
        # Search and filter
        col_search, col_filter = st.columns([2, 1])
        
        with col_search:
            search_term = st.text_input("🔍 Search symbols", placeholder="Search by symbol or company name...")
        
        with col_filter:
            filter_status = st.selectbox("📊 Status", ["All", "Active", "Inactive"], index=0)
        
        # Filter symbols
        filtered_symbols = filter_symbols(symbols_data, search_term, filter_status)
        
        if filtered_symbols:
            # Display symbols in a nice table
            display_symbols_table(filtered_symbols)
        else:
            st.info("🔍 No symbols found matching your criteria")
    else:
        st.warning("⚠️ No stock symbols found in the system")
        st.info("💡 Add your first stock symbol using the form above")
    
    # Update session state
    st.session_state.data_loading_config.update({
        'auto_refresh': auto_refresh,
        'refresh_interval': refresh_interval
    })

def show_analyst_ratings_tab():
    """Analyst Ratings Tab - Industry standard page with smart caching"""
    st.markdown("## 📊 Analyst Ratings & Grades")
    st.markdown("View analyst ratings, stock grades, and recent changes for any symbol")
    
    # Symbol selection with improved UX
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # Get available stocks from Go API (Redis cached)
        available_stocks = get_all_stock_symbols()
        
        if available_stocks:
            # Create symbol options with company names for better UX
            stock_options = {}
            for stock in available_stocks:
                symbol = stock.get('symbol', '')
                company = stock.get('company_name', '')
                if symbol and company:
                    display_name = f"{symbol} - {company[:50]}{'...' if len(company) > 50 else ''}"
                    stock_options[display_name] = symbol
                elif symbol:
                    stock_options[symbol] = symbol
            
            # Sort options by symbol
            sorted_options = dict(sorted(stock_options.items(), key=lambda x: x[1]))
            
            # Add search functionality
            search_term = st.text_input("🔎 Search Symbols", placeholder="Type to search...", key="symbol_search")
            
            if search_term:
                # Filter options based on search
                filtered_options = {
                    k: v for k, v in sorted_options.items() 
                    if search_term.upper() in v.upper() or search_term.upper() in k.upper()
                }
                
                if filtered_options:
                    selected_display = st.selectbox(
                        "🔍 Select Stock Symbol",
                        options=list(filtered_options.keys()),
                        key="analyst_ratings_symbol_filtered",
                        help="Select a stock symbol to view analyst ratings and grades"
                    )
                    selected_symbol = filtered_options.get(selected_display, "")
                else:
                    st.warning("No symbols found matching your search.")
                    selected_symbol = ""
            else:
                # Show top 100 popular symbols by default for performance
                popular_options = dict(list(sorted_options.items())[:100])
                selected_display = st.selectbox(
                    "🔍 Select Stock Symbol (Top 100)",
                    options=list(popular_options.keys()),
                    key="analyst_ratings_symbol_select",
                    help="Select a stock symbol to view analyst ratings and grades. Use search above to find more symbols."
                )
                selected_symbol = popular_options.get(selected_display, "")
                
                # Show how many more symbols are available
                if len(sorted_options) > 100:
                    st.info(f"📊 Showing 100 of {len(sorted_options)} available symbols. Use search to find more.")
        else:
            # Fallback to text input if API fails
            selected_symbol = st.text_input(
                "🔍 Enter Symbol",
                placeholder="e.g., AAPL, MSFT, GOOGL",
                key="analyst_ratings_symbol_fallback",
                help="Enter a stock symbol to view analyst ratings and grades"
            ).upper()
    
    with col2:
        # Load ratings button
        if selected_symbol and st.button("🔄 Load Ratings", width='stretch', help="Load latest ratings for selected symbol"):
            # Clear cache and load fresh data
            clear_ratings_cache(selected_symbol)
            load_ratings_for_symbol(selected_symbol)
    
    if selected_symbol:
        st.markdown(f"### 📈 Analyst Ratings for **{selected_symbol}**")
        
        # Create tabs for different rating views
        tab1, tab2, tab3 = st.tabs([
            "📊 Latest Grades", 
            "📈 Recent Changes", 
            "🔄 Load New Data"
        ])
        
        with tab1:
            show_latest_grades_cached(selected_symbol)
        
        with tab2:
            show_recent_grade_changes_cached(selected_symbol)
        
        with tab3:
            show_ratings_data_loading(selected_symbol)

def clear_ratings_cache(symbol: str):
    """Clear cached ratings data for a symbol"""
    cache_keys = [
        f"grades_{symbol}",
        f"recent_changes_{symbol}",
        f"last_updated_{symbol}"
    ]
    for key in cache_keys:
        if key in st.session_state:
            del st.session_state[key]

def get_cached_grades(symbol: str, cache_duration_minutes: int = 30):
    """Get cached grades data if available and fresh"""
    cache_key = f"grades_{symbol}"
    last_updated_key = f"last_updated_{symbol}"
    
    if cache_key in st.session_state and last_updated_key in st.session_state:
        last_updated = st.session_state[last_updated_key]
        import datetime
        if datetime.datetime.now() - last_updated < datetime.timedelta(minutes=cache_duration_minutes):
            return st.session_state[cache_key]
    return None

def cache_grades(symbol: str, data):
    """Cache grades data with timestamp"""
    import datetime
    st.session_state[f"grades_{symbol}"] = data
    st.session_state[f"last_updated_{symbol}"] = datetime.datetime.now()

def get_cached_recent_changes(symbol: str, cache_duration_minutes: int = 30):
    """Get cached recent changes data if available and fresh"""
    cache_key = f"recent_changes_{symbol}"
    last_updated_key = f"last_updated_{symbol}"
    
    if cache_key in st.session_state and last_updated_key in st.session_state:
        last_updated = st.session_state[last_updated_key]
        import datetime
        if datetime.datetime.now() - last_updated < datetime.timedelta(minutes=cache_duration_minutes):
            return st.session_state[cache_key]
    return None

def cache_recent_changes(symbol: str, data):
    """Cache recent changes data with timestamp"""
    import datetime
    st.session_state[f"recent_changes_{symbol}"] = data
    st.session_state[f"last_updated_{symbol}"] = datetime.datetime.now()


def get_cached_fundamentals_analysis(symbol: str, cache_duration_minutes: int = 60) -> Optional[Dict[str, Any]]:
    cache_key = f"fundamentals_{symbol}"
    last_updated_key = f"fundamentals_last_updated_{symbol}"

    if cache_key in st.session_state and last_updated_key in st.session_state:
        last_updated = st.session_state[last_updated_key]
        import datetime

        if datetime.datetime.now() - last_updated < datetime.timedelta(minutes=cache_duration_minutes):
            v = st.session_state[cache_key]
            return v if isinstance(v, dict) else None
    return None


def cache_fundamentals_analysis(symbol: str, data: Dict[str, Any]):
    import datetime

    st.session_state[f"fundamentals_{symbol}"] = data
    st.session_state[f"fundamentals_last_updated_{symbol}"] = datetime.datetime.now()

def show_latest_grades_cached(symbol: str):
    """Show latest grades for a symbol using smart caching"""
    # Check cache first
    cached_data = get_cached_grades(symbol)
    if cached_data:
        grades = cached_data
        # Show cache indicator
        st.caption("📋 Showing cached data (refreshed recently)")
    else:
        # Fetch from API
        try:
            with st.spinner(f"Loading grades for {symbol}..."):
                grades_response = go_client.get(f"api/v2/stock-grades/{symbol}/grades")
                
                if grades_response and isinstance(grades_response, list):
                    grades = grades_response
                    # Cache the data
                    cache_grades(symbol, grades)
                else:
                    grades = []
        except Exception as e:
            st.error(f"❌ Error loading grades: {e}")
            return
    
    if grades:
        st.markdown(f"#### 📊 Analyst Ratings for {symbol}")
        
        # Industry Standard Summary (like Yahoo Finance)
        col1, col2, col3, col4 = st.columns(4)
        
        # Count ratings by type
        strong_buy = len([g for g in grades if g.get('new_grade', '').lower() in ['strong buy']])
        buy = len([g for g in grades if g.get('new_grade', '').lower() in ['buy', 'outperform']])
        hold = len([g for g in grades if g.get('new_grade', '').lower() in ['hold', 'maintain', 'neutral']])
        sell = len([g for g in grades if g.get('new_grade', '').lower() in ['sell', 'underperform']])
        strong_sell = len([g for g in grades if g.get('new_grade', '').lower() in ['strong sell']])
        
        with col1:
            st.metric("🟢 Strong Buy", strong_buy, help="Analysts believe stock will perform exceptionally well")
        with col2:
            st.metric("📈 Buy/Outperform", buy, help="Analysts expect stock to outperform market")
        with col3:
            st.metric("⚪ Hold/Neutral", hold, help="Neutral recommendation")
        with col4:
            st.metric("🔴 Sell/Underperform", sell + strong_sell, help="Analysts expect underperformance")
        
        # Consensus Rating (like Yahoo Finance)
        total_analysts = len(grades)
        if total_analysts > 0:
            # Calculate consensus score
            buy_score = (strong_buy * 2) + (buy * 1) + (hold * 0) + (sell * -1) + (strong_sell * -2)
            consensus_avg = buy_score / total_analysts
            
            if consensus_avg >= 1.5:
                consensus_rating = "🟢 Strong Buy"
                consensus_color = "green"
            elif consensus_avg >= 0.5:
                consensus_rating = "📈 Buy"
                consensus_color = "lightgreen"
            elif consensus_avg >= -0.5:
                consensus_rating = "⚪ Hold"
                consensus_color = "orange"
            else:
                consensus_rating = "🔴 Sell"
                consensus_color = "red"
            
            st.markdown(f"#### Consensus: <span style='color:{consensus_color};font-size:24px;font-weight:bold'>{consensus_rating}</span>", unsafe_allow_html=True)
            st.markdown(f"**{total_analysts} analysts** • Consensus Score: `{consensus_avg:.2f}`")
        
        # Detailed grades table
        st.markdown("#### 📋 Detailed Analyst Ratings")
        
        # Convert to DataFrame for display
        df_data = []
        for grade in grades:
            df_data.append({
                'Date': grade.get('grade_date', ''),
                'Firm': grade.get('grading_company', ''),
                'Rating': grade.get('new_grade', ''),
                'Action': grade.get('action', ''),
                'Previous': grade.get('previous_grade', 'N/A')
            })
        
        if df_data:
            df = pd.DataFrame(df_data)
            st.dataframe(df, width='stretch', hide_index=True)
            
            # Refresh button
            if st.button(f"🔄 Refresh {symbol} Ratings", key=f"refresh_{symbol}"):
                with st.spinner(f"Refreshing ratings for {symbol}..."):
                    refresh_response = go_client.post(f"api/v2/stock-grades/refresh/{symbol}")
                    if refresh_response and refresh_response.get('success'):
                        st.success(f"✅ Refreshed {refresh_response.get('results', {}).get('grades_loaded', 0)} grades")
                        clear_ratings_cache(symbol)
                        st.rerun()
                    else:
                        st.error("❌ Failed to refresh ratings")
        else:
            st.info(f"ℹ️ No grades found for {symbol}")
            
            # Offer to load ratings
            if st.button(f"🔄 Load Ratings for {symbol}", key=f"load_{symbol}"):
                load_ratings_for_symbol(symbol)

def show_recent_grade_changes_cached(symbol: str):
    """Show recent grade changes for a symbol using smart caching"""
    # Check cache first
    cached_data = get_cached_recent_changes(symbol)
    if cached_data:
        changes = cached_data
        # Show cache indicator
        st.caption("📋 Showing cached data (refreshed recently)")
    else:
        # Fetch from API
        try:
            with st.spinner(f"Loading recent changes for {symbol}..."):
                changes_response = go_client.get(f"api/v2/stock-grades/{symbol}/recent-changes?days=30")
                
                if changes_response and isinstance(changes_response, dict):
                    changes = changes_response.get('changes', [])
                    # Cache the data
                    cache_recent_changes(symbol, changes)
                else:
                    changes = []
        except Exception as e:
            st.error(f"❌ Error fetching recent changes: {e}")
            return
    
    if changes:
        st.markdown(f"#### 📈 Recent Grade Changes for {symbol} (Last 30 Days)")
        
        # Convert to DataFrame for display
        df_data = []
        for change in changes:
            df_data.append({
                'Date': change.get('grade_date', ''),
                'Firm': change.get('grading_company', ''),
                'Action': change.get('action', ''),
                'Previous': change.get('previous_grade', 'N/A'),
                'New': change.get('new_grade', ''),
                'Price': f"${change.get('price_at_grade', 0):.2f}" if change.get('price_at_grade') else "N/A"
            })
        
        if df_data:
            df = pd.DataFrame(df_data)
            st.dataframe(df, width='stretch', hide_index=True)
            
            # Summary statistics
            upgrades = len([c for c in changes if c.get('action') == 'upgrade'])
            downgrades = len([c for c in changes if c.get('action') == 'downgrade'])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("⬆️ Upgrades", upgrades)
            with col2:
                st.metric("⬇️ Downgrades", downgrades)
            with col3:
                st.metric("📊 Total Changes", len(changes))
        else:
            st.info(f"ℹ️ No recent grade changes found for {symbol} in the last 30 days")
    else:
        st.info(f"ℹ️ No recent grade changes found for {symbol} in the last 30 days")

def show_ratings_data_loading(symbol: str):
    """Show ratings data loading controls and status"""
    st.markdown(f"#### 🔄 Data Loading for {symbol}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Load Fresh Data**")
        st.info("Click to load the latest analyst ratings from external sources")
        
        if st.button(f"📥 Load {symbol} Ratings", key=f"load_fresh_{symbol}", width='stretch'):
            load_ratings_for_symbol(symbol)
    
    with col2:
        st.markdown("**Cache Status**")
        # Check if we have cached data
        cached_data = get_cached_grades(symbol)
        if cached_data:
            st.success("✅ Data cached")
            st.caption(f"📊 {len(cached_data)} ratings cached")
            
            if st.button("🗑️ Clear Cache", key=f"clear_cache_{symbol}"):
                clear_ratings_cache(symbol)
                st.rerun()
        else:
            st.warning("⚠️ No cached data")
            st.caption("Load data to cache for faster access")
    
    # Show data source info
    st.markdown("---")
    st.markdown("**📊 Data Sources**")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("🏢 Primary", "FMP", help="Financial Modeling Prep API")
    
    with col2:
        st.metric("🔄 Refresh", "Manual", help="Data refreshed on demand")
    
    with col3:
        st.metric("💾 Cache", "30 min", help="Data cached for 30 minutes")

def load_ratings_for_symbol(symbol: str):
    """Load latest ratings data for a symbol using the new stock grades API"""
    with st.spinner(f"Loading ratings for {symbol}..."):
        try:
            # Use the new stock grades API to refresh data
            refresh_response = go_client.post(f"api/v2/stock-grades/refresh/{symbol}?data_source=fmp&include_consensus=true")
            
            if refresh_response and refresh_response.get("success"):
                results = refresh_response.get("results", {})
                grades_loaded = results.get("grades_loaded", 0)
                consensus_loaded = results.get("consensus_loaded", False)
                
                st.success(f"✅ Loaded {grades_loaded} grades for {symbol}")
                if consensus_loaded:
                    st.info("📊 Consensus data also loaded")
                
                # Show summary of what was loaded
                if grades_loaded > 0:
                    # Get the loaded grades to show summary
                    grades_response = go_client.get(f"api/v2/stock-grades/{symbol}/grades")
                    if grades_response and isinstance(grades_response, list):
                        upgrades = len([g for g in grades_response if g.get('action') == 'upgrade'])
                        downgrades = len([g for g in grades_response if g.get('action') == 'downgrade'])
                        maintains = len([g for g in grades_response if g.get('action') == 'maintain'])
                        
                        if upgrades > 0 or downgrades > 0 or maintains > 0:
                            st.markdown("**Summary:**")
                            if upgrades > 0:
                                st.success(f"⬆️ {upgrades} upgrades")
                            if downgrades > 0:
                                st.error(f"⬇️ {downgrades} downgrades")
                            if maintains > 0:
                                st.info(f"➡️ {maintains} maintains")
                
                # Refresh the page to show new data
                st.rerun()
            else:
                error_msg = refresh_response.get("message", "Unknown error") if refresh_response else "No response"
                st.error(f"❌ Failed to load ratings: {error_msg}")
                
        except Exception as e:
            st.error(f"❌ Error loading ratings for {symbol}: {e}")
            st.help("Try again in a few minutes or check if the symbol is correct")

def show_latest_grades(symbol: str):
    """Show latest grades for a symbol using the new stock grades API"""
    try:
        with st.spinner(f"Loading grades for {symbol}..."):
            # Use the new stock grades API
            grades_response = go_client.get(f"api/v2/stock-grades/{symbol}/grades")
            
            if grades_response and isinstance(grades_response, list):
                grades = grades_response
                
                if grades:
                    st.markdown(f"#### 📊 Analyst Ratings for {symbol}")
                    
                    # Industry Standard Summary (like Yahoo Finance)
                    col1, col2, col3, col4 = st.columns(4)
                    
                    # Count ratings by type
                    strong_buy = len([g for g in grades if g.get('new_grade', '').lower() in ['strong buy']])
                    buy = len([g for g in grades if g.get('new_grade', '').lower() in ['buy', 'outperform']])
                    hold = len([g for g in grades if g.get('new_grade', '').lower() in ['hold', 'maintain', 'neutral']])
                    sell = len([g for g in grades if g.get('new_grade', '').lower() in ['sell', 'underperform']])
                    strong_sell = len([g for g in grades if g.get('new_grade', '').lower() in ['strong sell']])
                    
                    with col1:
                        st.metric("🟢 Strong Buy", strong_buy, help="Analysts believe stock will perform exceptionally well")
                    with col2:
                        st.metric("📈 Buy/Outperform", buy, help="Analysts expect stock to outperform market")
                    with col3:
                        st.metric("⚪ Hold/Neutral", hold, help="Neutral recommendation")
                    with col4:
                        st.metric("🔴 Sell/Underperform", sell + strong_sell, help="Analysts expect underperformance")
                    
                    # Consensus Rating (like Yahoo Finance)
                    total_analysts = len(grades)
                    if total_analysts > 0:
                        # Calculate consensus score
                        buy_score = (strong_buy * 2) + (buy * 1) + (hold * 0) + (sell * -1) + (strong_sell * -2)
                        consensus_avg = buy_score / total_analysts
                        
                        if consensus_avg >= 1.5:
                            consensus_rating = "🟢 Strong Buy"
                            consensus_color = "green"
                        elif consensus_avg >= 0.5:
                            consensus_rating = "📈 Buy"
                            consensus_color = "lightgreen"
                        elif consensus_avg >= -0.5:
                            consensus_rating = "⚪ Hold"
                            consensus_color = "orange"
                        else:
                            consensus_rating = "🔴 Sell"
                            consensus_color = "red"
                        
                        st.markdown(f"#### Consensus: <span style='color:{consensus_color};font-size:24px;font-weight:bold'>{consensus_rating}</span>", unsafe_allow_html=True)
                        st.markdown(f"**{total_analysts} analysts** • Consensus Score: `{consensus_avg:.2f}`")
                    
                    # Detailed grades table
                    st.markdown("#### 📋 Detailed Analyst Ratings")
                    
                    # Convert to DataFrame for display
                    df_data = []
                    for grade in grades:
                        df_data.append({
                            'Date': grade.get('grade_date', ''),
                            'Firm': grade.get('grading_company', ''),
                            'Rating': grade.get('new_grade', ''),
                            'Action': grade.get('action', ''),
                            'Previous': grade.get('previous_grade', 'N/A')
                        })
                    
                    if df_data:
                        df = pd.DataFrame(df_data)
                        st.dataframe(df, width='stretch', hide_index=True)
                    
                    # Refresh button
                    if st.button(f"🔄 Refresh {symbol} Ratings", key=f"refresh_{symbol}"):
                        with st.spinner(f"Refreshing ratings for {symbol}..."):
                            refresh_response = go_client.post(f"api/v2/stock-grades/refresh/{symbol}?data_source=fmp&include_consensus=true")
                            if refresh_response and refresh_response.get('success'):
                                st.success(f"✅ Refreshed {refresh_response.get('results', {}).get('grades_loaded', 0)} grades")
                                st.rerun()
                            else:
                                st.error("❌ Failed to refresh ratings")
                else:
                    st.info(f"ℹ️ No grades found for {symbol}")
                    
                    # Offer to load ratings
                    if st.button(f"🔄 Load Ratings for {symbol}", key=f"load_{symbol}"):
                        load_ratings_for_symbol(symbol)
            else:
                st.info(f"ℹ️ No grades data available for {symbol}")
                
                # Offer to load ratings
                if st.button(f"🔄 Load Ratings for {symbol}", key=f"load_{symbol}_fallback"):
                    load_ratings_for_symbol(symbol)
                    
    except Exception as e:
        st.error(f"❌ Error loading grades for {symbol}: {e}")
        st.help("Try refreshing the page or selecting a different symbol")

def show_recent_grade_changes(symbol: str):
    """Show recent grade changes for a symbol using the new stock grades API"""
    try:
        with st.spinner(f"Loading recent changes for {symbol}..."):
            # Use the new stock grades API for recent changes
            changes_response = go_client.get(f"api/v2/stock-grades/{symbol}/recent-changes?days=30")
            
            if changes_response and isinstance(changes_response, dict):
                changes = changes_response.get('changes', [])
                
                if changes:
                    st.markdown(f"#### 📈 Recent Grade Changes for {symbol} (Last 30 Days)")
                    
                    # Convert to DataFrame for display
                    df_data = []
                    for change in changes:
                        df_data.append({
                            'Date': change.get('grade_date', ''),
                            'Firm': change.get('grading_company', ''),
                            'Action': change.get('action', ''),
                            'Previous': change.get('previous_grade', 'N/A'),
                            'New': change.get('new_grade', ''),
                            'Price': f"${change.get('price_at_grade', 0):.2f}" if change.get('price_at_grade') else "N/A"
                        })
                    
                    if df_data:
                        df = pd.DataFrame(df_data)
                        st.dataframe(df, width='stretch', hide_index=True)
                        
                        # Summary statistics
                        upgrades = len([c for c in changes if c.get('action') == 'upgrade'])
                        downgrades = len([c for c in changes if c.get('action') == 'downgrade'])
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("⬆️ Upgrades", upgrades)
                        with col2:
                            st.metric("⬇️ Downgrades", downgrades)
                        with col3:
                            st.metric("📊 Total Changes", len(changes))
                    else:
                        st.info(f"ℹ️ No recent grade changes found for {symbol} in the last 30 days")
                else:
                    st.info(f"ℹ️ No recent grade changes found for {symbol} in the last 30 days")
            else:
                st.info(f"ℹ️ Unable to fetch recent changes for {symbol}")
                
    except Exception as e:
        st.error(f"❌ Error fetching recent changes: {e}")
        st.help("Try refreshing the page or selecting a different symbol")

def get_scheduler_status():
    """Get current scheduler status using portfolio schedule overview"""
    try:
        response = go_client.get("api/v1/portfolio-schedules/status/overview")
        
        if response and response.get("scheduler_running") is not None:
            return {
                'is_running': response.get("scheduler_running", False),
                'total_schedules': response.get("total_schedules", 0),
                'active_schedules': response.get("active_schedules", 0),
                'paused_schedules': response.get("paused_schedules", 0)
            }
        else:
            return {'is_running': False, 'error': 'Failed to get status'}
            
    except Exception as e:
        st.error(f"❌ Error getting scheduler status: {str(e)}")
        return {'is_running': False, 'error': str(e)}

def start_scheduler():
    """Start the data refresh scheduler"""
    st.warning("⚠️ Scheduler start/stop functionality is not yet implemented in the Go API.")
    st.info("💡 You can create and manage portfolio schedules using the Scheduling button in Portfolio Actions.")

def stop_scheduler():
    """Stop the data refresh scheduler"""
    st.warning("⚠️ Scheduler start/stop functionality is not yet implemented in the Go API.")
    st.info("💡 You can pause individual portfolio schedules using the Scheduling button in Portfolio Actions.")

def schedule_all_symbols():
    """Schedule all symbols for automatic refresh"""
    try:
        response = go_client.post("api/v1/scheduler/schedule-all")
        
        if response and response.get("success"):
            st.success(f"✅ {response.get('message')}")
            st.rerun()
        else:
            error_msg = response.get("message", "Unknown error") if response else "No response"
            st.error(f"❌ Failed to schedule symbols: {error_msg}")
            
    except Exception as e:
        st.error(f"❌ Error scheduling symbols: {str(e)}")

def get_upcoming_refreshes():
    """Get upcoming scheduled refreshes"""
    try:
        response = go_client.get("api/v1/scheduler/upcoming?limit=10")
        
        if response and isinstance(response, dict):
            return response
        else:
            return {'upcoming_refreshes': []}
            
    except Exception as e:
        return {'upcoming_refreshes': []}

def format_time(dt):
    """Format datetime for display"""
    if dt is None:
        return "N/A"
    
    if isinstance(dt, str):
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    
    return dt.strftime("%H:%M:%S")

def load_all_stocks_data(quick_mode=False, auto_triggered=False):
    """Load data for all stock symbols with proper rate limiting"""
    try:
        st.session_state.data_loading_config['loading_status'] = 'loading'
        
        # Get all symbols
        symbols_data = get_all_stock_symbols()
        
        if not symbols_data:
            st.error("❌ No symbols found to load data for")
            st.session_state.data_loading_config['loading_status'] = 'idle'
            return
        
        # Extract symbols
        symbols = [symbol['symbol'] for symbol in symbols_data if symbol.get('is_active', True)]
        
        if not symbols:
            st.error("❌ No active symbols found")
            st.session_state.data_loading_config['loading_status'] = 'idle'
            return
        
        # Determine data types based on mode
        if quick_mode:
            data_types = ["price_historical", "indicators"]
            mode_text = "Quick Refresh"
        else:
            data_types = ["price_historical", "indicators", "fundamentals", "earnings"]
            mode_text = "Full Data Load"
        
        # Show loading message
        if auto_triggered:
            st.info(f"🔄 Auto-refreshing {mode_text} for {len(symbols)} symbols...")
        else:
            st.info(f"🚀 {mode_text} for {len(symbols)} symbols...")
        
        # Create progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Load data in batches to respect API rate limits
        batch_size = 5  # Process 5 symbols at a time
        delay_between_batches = 15  # 15 seconds between batches (200 calls/min = ~3.3 calls/sec)
        
        successful_loads = []
        failed_loads = []
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            
            # Update progress
            progress = (i / len(symbols))
            progress_bar.progress(progress)
            status_text.text(f"Loading batch {i//batch_size + 1}/{(len(symbols) + batch_size - 1)//batch_size}: {', '.join(batch)}")
            
            # Load data for this batch
            try:
                response = go_client.post("api/v1/admin/refresh", json_data={
                    "symbols": batch,
                    "data_types": data_types,
                    "force": True
                }, timeout=300)
                
                if response and response.get("success"):
                    successful_loads.extend(batch)
                else:
                    failed_loads.extend(batch)
                    error_msg = response.get("error", "Unknown error") if response else "No response"
                    st.warning(f"⚠️ Batch {i//batch_size + 1} failed: {error_msg}")
                
            except Exception as e:
                failed_loads.extend(batch)
                st.error(f"❌ Batch {i//batch_size + 1} error: {str(e)}")
            
            # Add delay between batches (except for last batch)
            if i + batch_size < len(symbols):
                if not auto_triggered:  # Only show delay message for manual loads
                    st.info(f"⏱️ Waiting {delay_between_batches}s to respect API rate limits...")
                time_module.sleep(delay_between_batches)
        
        # Complete progress
        progress_bar.progress(1.0)
        
        # Update last refresh time
        from datetime import datetime
        st.session_state.data_loading_config['last_refresh'] = datetime.now()
        st.session_state.data_loading_config['loading_status'] = 'idle'
        
        # Show results
        if successful_loads:
            st.success(f"✅ Successfully loaded data for {len(successful_loads)} symbols")
        
        if failed_loads:
            st.error(f"❌ Failed to load data for {len(failed_loads)} symbols: {', '.join(failed_loads[:5])}{'...' if len(failed_loads) > 5 else ''}")
        
        # Auto-refresh for next cycle
        if auto_triggered and st.session_state.data_loading_config['auto_refresh']:
            st.rerun()
        
    except Exception as e:
        st.session_state.data_loading_config['loading_status'] = 'error'
        st.error(f"❌ Error loading data: {str(e)}")

def show_add_symbol_form():
    """Show form to add a new stock symbol"""
    with st.expander("📝 Add New Stock Symbol", expanded=True):
        st.markdown("**🚀 Auto-populated from Yahoo Finance** - Enter symbol and optionally company details")
        
        with st.form("add_symbol_form"):
            symbol = st.text_input(
                "📈 Stock Symbol *", 
                placeholder="e.g., AAPL, GOOGL, MSFT",
                help="Enter the stock ticker symbol (e.g., AAPL, GOOGL, MSFT)"
            ).upper()
            
            st.markdown("---")
            st.markdown("**📝 Optional Company Information**")
            st.caption("Yahoo Finance API may be rate-limited. You can manually enter company details below.")
            
            col1, col2 = st.columns(2)
            
            with col1:
                company_name = st.text_input(
                    "🏢 Company Name", 
                    placeholder="e.g., Apple Inc.",
                    help="Company name (optional - will be fetched from Yahoo Finance if not provided)"
                )
                
                sector = st.text_input(
                    "🏭 Sector", 
                    placeholder="e.g., Technology",
                    help="Industry sector (optional)"
                )
            
            with col2:
                industry = st.text_input(
                    "⚙️ Industry", 
                    placeholder="e.g., Consumer Electronics",
                    help="Industry (optional)"
                )
                
                country = st.text_input(
                    "🌍 Country", 
                    placeholder="e.g., United States",
                    help="Country (optional)"
                )
            
            description = st.text_area(
                "📝 Description", 
                placeholder="Brief company description...",
                help="Enter a brief description of the company (optional)",
                height=80
            )
            
            st.info("💡 **Tip**: If Yahoo Finance API is rate-limited, you can manually enter company details above")
            
            # Submit buttons
            col_submit, col_cancel = st.columns([1, 1])
            
            with col_submit:
                submitted = st.form_submit_button("➕ Add Symbol", type="primary", width='stretch')
            
            with col_cancel:
                if st.form_submit_button("❌ Cancel", width='stretch'):
                    st.session_state.add_symbol_form_visible = False
                    st.rerun()
            
            if submitted:
                if symbol:
                    success = add_stock_symbol(
                        symbol=symbol,
                        company_name=company_name,
                        sector=sector,
                        industry=industry,
                        description=description
                    )
                    
                    if success:
                        st.session_state.add_symbol_form_visible = False
                        st.rerun()
                else:
                    st.error("❌ Stock Symbol is required")

def get_all_stock_symbols():
    """Fetch all stock symbols from Go API with Redis caching"""
    # Check cache first
    if 'stock_symbols_cache' in st.session_state:
        cache_time = st.session_state.get('stock_symbols_cache_time', 0)
        if time_module.time() - cache_time < 3600:  # Cache for 1 hour
            return st.session_state.stock_symbols_cache
    
    try:
        # Use Go API for tickers (Redis cached)
        response = go_client.get("api/v1/tickers")
        
        if response and isinstance(response, dict) and 'tickers' in response:
            tickers = response['tickers']
            # Return only symbol and company_name for dropdown
            symbols = [
                {
                    'symbol': ticker.get('symbol', ''),
                    'company_name': ticker.get('company_name', '')
                }
                for ticker in tickers 
                if ticker.get('symbol') and ticker.get('is_active') == True
            ]
            
            # Cache the results
            st.session_state.stock_symbols_cache = symbols
            st.session_state.stock_symbols_cache_time = time_module.time()
            
            return symbols
        return []
        
    except Exception as e:
        st.error(f"❌ Error fetching stock symbols: {e}")
        return []

def show_alert_management_tab():
    """Alert Management Tab - Create and manage rating alerts"""
    st.markdown("## 🔔 Alert Management")
    st.markdown("Create and manage alerts for rating changes, price targets, and earnings")
    
    # Get user ID (for demo, use a default UUID that exists in database)
    user_id = st.session_state.get('user_id', '4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4')
    
    # Create tabs for different alert management functions
    tab_options = [
        "📝 Create Alerts", 
        "📋 My Alerts", 
        "📊 Subscriptions", 
        "⚙️ Quick Setup"
    ]
    
    # Get active tab from session state (default to 0)
    active_tab = st.session_state.get('active_tab', 0)
    
    # Create tab selector
    selected_tab = st.radio(
        "Select Action:",
        options=tab_options,
        index=active_tab,
        horizontal=True,
        label_visibility="collapsed"
    )
    
    # Update session state
    active_tab = tab_options.index(selected_tab)
    st.session_state.active_tab = active_tab
    
    # Show content based on active tab
    if active_tab == 0:
        show_create_alert_section(user_id)
    elif active_tab == 1:
        show_my_alerts_section(user_id)
    elif active_tab == 2:
        show_subscriptions_section(user_id)
    elif active_tab == 3:
        show_quick_setup_section(user_id)

def show_create_alert_section(user_id: str):
    """Show create alert interface"""
    st.markdown("### 📝 Create New Alert")
    
    # Get available stock symbols
    available_stocks = get_all_stock_symbols()
    
    # Alert creation form
    with st.form("create_alert_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            # Stock symbol selection with type-ahead search
            if available_stocks:
                # Create a searchable dropdown with type-ahead
                symbol_options = {
                    f"{stock.get('symbol', '')} - {(stock.get('company_name') or '')[:40]}": stock.get('symbol', '')
                    for stock in available_stocks
                    if isinstance(stock, dict) and stock.get('symbol')
                }
                
                # Search box for filtering symbols
                search_term = st.text_input(
                    "🔍 Search Stock Symbol",
                    placeholder="Type to search symbols...",
                    help="Start typing to search for stocks"
                )
                
                # Filter symbols based on search
                if search_term:
                    filtered_options = {k: v for k, v in symbol_options.items() 
                                      if search_term.upper() in k.upper()}
                else:
                    filtered_options = symbol_options
                
                # Show filtered dropdown
                if filtered_options:
                    selected_display = st.selectbox(
                        "📈 Select Stock Symbol",
                        options=list(filtered_options.keys()),
                        key="analyst_ratings_symbol_filtered",
                        help="Choose a stock symbol to create an alert for"
                    )
                    selected_symbol = filtered_options.get(selected_display, "")
                else:
                    st.warning("No symbols found matching your search")
                    selected_symbol = ""
            else:
                selected_symbol = st.text_input(
                    "📈 Enter Stock Symbol",
                    placeholder="e.g., AAPL, MSFT, GOOGL",
                    key="analyst_ratings_symbol_fallback",
                    help="Enter stock symbol manually"
                ).upper()
            
            # Alert type selection
            alert_types = {
                "rating_change": "Rating Change",
                "price_target_change": "Price Target Change", 
                "consensus_alert": "Consensus Alert",
                "earnings_alert": "Earnings Alert"
            }
            
            selected_alert_type = st.selectbox(
                "🔔 Alert Type",
                options=list(alert_types.keys()),
                format_func=lambda x: alert_types[x],
                help="Choose the type of alert you want to create"
            )
        
        with col2:
            # Alert name
            alert_name = st.text_input(
                "📝 Alert Name",
                placeholder=f"{selected_symbol} {alert_types[selected_alert_type]}",
                help="Give your alert a descriptive name"
            )
            
            # Notification channels
            notification_channels = st.multiselect(
                "📧 Notification Channels",
                options=["email", "sms", "push", "webhook"],
                default=["email"],
                help="Choose how you want to be notified"
            )
        
        # Alert configuration based on type
        st.markdown("#### ⚙️ Alert Configuration")
        
        config = {}
        
        if selected_alert_type == "rating_change":
            col1, col2 = st.columns(2)
            with col1:
                config["min_consensus_change"] = st.slider(
                    "Min Consensus Change",
                    min_value=0.1, max_value=1.0, value=0.3, step=0.1,
                    help="Minimum consensus score change to trigger alert"
                )
                config["tier_1_firms_only"] = st.checkbox(
                    "Tier 1 Firms Only",
                    value=False,
                    help="Only alert for top-tier analyst firms"
                )
            with col2:
                config["include_upgrades"] = st.checkbox(
                    "Include Upgrades",
                    value=True,
                    help="Alert when ratings are upgraded"
                )
                config["include_downgrades"] = st.checkbox(
                    "Include Downgrades", 
                    value=True,
                    help="Alert when ratings are downgraded"
                )
        
        elif selected_alert_type == "price_target_change":
            col1, col2 = st.columns(2)
            with col1:
                config["min_price_change_percent"] = st.slider(
                    "Min Price Change %",
                    min_value=1.0, max_value=20.0, value=5.0, step=1.0,
                    help="Minimum price target change percentage"
                )
                config["min_analyst_count"] = st.slider(
                    "Min Analyst Count",
                    min_value=1, max_value=10, value=3, step=1,
                    help="Minimum number of analysts for consensus"
                )
            with col2:
                config["include_increases"] = st.checkbox(
                    "Include Increases",
                    value=True,
                    help="Alert when price targets increase"
                )
                config["include_decreases"] = st.checkbox(
                    "Include Decreases",
                    value=True,
                    help="Alert when price targets decrease"
                )
        
        elif selected_alert_type == "consensus_alert":
            col1, col2 = st.columns(2)
            with col1:
                config["target_consensus"] = st.selectbox(
                    "Target Consensus",
                    options=["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"],
                    help="Consensus level to alert on"
                )
                config["direction"] = st.selectbox(
                    "Direction",
                    options=["above", "below", "exactly"],
                    help="When to trigger the alert"
                )
            with col2:
                config["min_analyst_count"] = st.slider(
                    "Min Analyst Count",
                    min_value=1, max_value=20, value=5, step=1,
                    help="Minimum number of analysts"
                )
        
        elif selected_alert_type == "earnings_alert":
            col1, col2 = st.columns(2)
            with col1:
                config["include_pre_announcements"] = st.checkbox(
                    "Include Pre-announcements",
                    value=True,
                    help="Alert before earnings announcements"
                )
                config["include_surprises_only"] = st.checkbox(
                    "Surprises Only",
                    value=False,
                    help="Only alert on earnings surprises"
                )
            with col2:
                config["min_surprise_percent"] = st.slider(
                    "Min Surprise %",
                    min_value=1.0, max_value=20.0, value=5.0, step=1.0,
                    help="Minimum earnings surprise percentage"
                )
                config["days_before_earnings"] = st.slider(
                    "Days Before Earnings",
                    min_value=0, max_value=7, value=1, step=1,
                    help="Alert this many days before earnings"
                )
        
        # Notification delay (common for all types)
        config["notification_delay_minutes"] = st.slider(
            "Notification Delay (minutes)",
            min_value=0, max_value=60, value=5, step=5,
            help="Delay before sending notification"
        )
        
        # Submit button
        col_submit, col_cancel = st.columns([1, 1])
        
        with col_submit:
            submitted = st.form_submit_button("🔔 Create Alert", type="primary", width='stretch')
        
        with col_cancel:
            if st.form_submit_button("❌ Cancel", width='stretch'):
                st.rerun()
        
        # Debug: Check if form was submitted
        st.write(f"Form submitted: {submitted}")
        st.write(f"Selected symbol: {selected_symbol}")
        st.write(f"Alert name: {alert_name}")
        
        if submitted:
            st.write("✅ Form submission detected!")
            if selected_symbol and alert_name:
                st.write("✅ Validation passed!")
                with st.spinner("Creating alert..."):
                    try:
                        # Debug: Show what we're sending
                        st.write(f"Creating alert for: {selected_symbol}")
                        st.write(f"Alert type: {selected_alert_type}")
                        st.write(f"User ID: {user_id}")
                        
                        # Prepare the payload
                        payload = {
                            "stock_symbol": selected_symbol,
                            "alert_type": selected_alert_type,
                            "name": alert_name,
                            "config": config,
                            "notification_channels": notification_channels
                        }
                        
                        st.write("Payload:", payload)
                        
                        # Call API to create alert
                        response = go_client.post(
                            "api/v1/admin/rating-alerts/alerts",
                            json_data=payload,
                            params={"user_id": user_id},
                        )
                        
                        # Debug: Show response
                        st.write("API Response:", response)
                        
                        if response and response.get("success"):
                            st.success(f"✅ Alert '{alert_name}' created successfully for {selected_symbol}")
                            st.balloons()
                        else:
                            st.error(f"❌ Failed to create alert: {response.get('message', 'Unknown error')}")
                            if response:
                                st.json(response)  # Show full response for debugging
                    
                    except Exception as e:
                        st.error(f"❌ Error creating alert: {e}")
                        st.exception(e)  # Show full exception for debugging
            else:
                st.error("❌ Please fill in all required fields")
                if not selected_symbol:
                    st.error("- Please select a stock symbol")
                if not alert_name:
                    st.error("- Please enter an alert name")


def show_my_alerts_section(user_id: str):
    """Show user's existing alerts"""
    st.markdown("### 📋 My Alerts")
    
    # Add refresh button
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 Refresh", key="refresh_alerts", width='stretch'):
            st.rerun()
    with col2:
        st.write("")  # Empty space for alignment
    
    # Load user's alerts
    with st.spinner("Loading alerts..."):
        try:
            response = go_client.get("api/v1/admin/rating-alerts/alerts", params={"user_id": user_id})
            
            if response and response.get("success"):
                alerts = response.get("alerts", [])
                
                if alerts:
                    # Alert filters
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        alert_type_filter = st.selectbox(
                            "Filter by Type",
                            options=["All"] + list(set(alert["alert_type"] for alert in alerts)),
                            key="alert_type_filter"
                        )
                    
                    with col2:
                        status_filter = st.selectbox(
                            "Filter by Status",
                            options=["All", "Enabled", "Disabled"],
                            key="status_filter"
                        )
                    
                    with col3:
                        sort_by = st.selectbox(
                            "Sort by",
                            options=["Created Date", "Symbol", "Type"],
                            key="sort_by"
                        )
                    
                    # Apply filters
                    filtered_alerts = alerts
                    if alert_type_filter != "All":
                        filtered_alerts = [a for a in filtered_alerts if a["alert_type"] == alert_type_filter]
                    if status_filter != "All":
                        enabled_status = status_filter == "Enabled"
                        filtered_alerts = [a for a in filtered_alerts if a["enabled"] == enabled_status]
                    
                    # Sort alerts
                    if sort_by == "Created Date":
                        filtered_alerts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                    elif sort_by == "Symbol":
                        filtered_alerts.sort(key=lambda x: x.get("stock_symbol", ""))
                    elif sort_by == "Type":
                        filtered_alerts.sort(key=lambda x: x.get("alert_type", ""))
                    
                    # Display alerts
                    for alert in filtered_alerts:
                        with st.expander(f"🔔 {alert['name']} ({alert['stock_symbol']})"):
                            col1, col2 = st.columns([2, 1])
                            
                            with col1:
                                st.write(f"**Type:** {alert['alert_type']}")
                                st.write(f"**Symbol:** {alert['stock_symbol']}")
                                st.write(f"**Status:** {'✅ Active' if alert['enabled'] else '❌ Disabled'}")
                                st.write(f"**Created:** {alert.get('created_at', 'Unknown')}")
                                
                                # Show notification channels
                                channels = alert.get('notification_channels', [])
                                if channels:
                                    st.write(f"**Notifications:** {', '.join(channels)}")
                            
                            with col2:
                                if st.button(f"✏️ Edit", key=f"edit_{alert['alert_id']}"):
                                    st.session_state[f"edit_alert_{alert['alert_id']}"] = True
                                    st.rerun()
                                
                                st.write("---")
                                st.write("**Quick Actions:**")
                                
                                # Toggle enable/disable
                                status_text = "Disable" if alert.get('enabled', True) else "Enable"
                                if st.button(f"🔘 {status_text}", key=f"toggle_{alert['alert_id']}", width='stretch'):
                                    with st.spinner(f"{status_text} alert..."):
                                        try:
                                            response = go_client.put(
                                                f"api/v1/admin/rating-alerts/alerts/{alert['alert_id']}",
                                                params={"user_id": user_id},
                                                json_data={"enabled": not alert.get('enabled', True)},
                                            )
                                            if response and response.get("success"):
                                                st.rerun()
                                            else:
                                                st.error(f"Failed to {status_text.lower()} alert")
                                        except Exception as e:
                                            st.error(f"Error: {e}")
                                
                                # Delete button
                                if st.button("🗑️ Delete", key=f"delete_quick_{alert['alert_id']}", type="secondary", width='stretch'):
                                    with st.spinner("Deleting alert..."):
                                        try:
                                            response = go_client.delete(
                                                f"api/v1/admin/rating-alerts/alerts/{alert['alert_id']}",
                                                params={"user_id": user_id},
                                            )
                                            if response and response.get("success"):
                                                st.success("Alert deleted!")
                                                st.rerun()
                                            else:
                                                st.error("Failed to delete alert")
                                        except Exception as e:
                                            st.error(f"Error: {e}")
                            
                            # Show edit section if expanded
                            if st.session_state.get(f"edit_alert_{alert['alert_id']}", False):
                                show_edit_alert_section(alert, user_id)
                else:
                    st.info("No alerts created yet. Create your first alert!")
            
            else:
                st.error("Failed to load alerts")
        
        except Exception as e:
            st.error(f"Error loading alerts: {e}")


def show_subscriptions_section(user_id: str):
    """Show rating subscriptions"""
    st.markdown("### 📊 Subscriptions")
    
    # Load user subscriptions
    with st.spinner("Loading subscriptions..."):
        try:
            response = go_client.get(
                "api/v1/admin/rating-alerts/subscriptions",
                params={"user_id": "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"},
            )
            
            if response and response.get("success"):
                subscriptions = response.get("subscriptions", [])
                
                if subscriptions:
                    st.write(f"**Active subscriptions:** {len(subscriptions)}")
                    
                    for sub in subscriptions:
                        with st.expander(f"📊 {sub['symbol']} - {sub['subscription_type']}"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.write(f"**Symbol:** {sub['symbol']}")
                                st.write(f"**Type:** {sub['subscription_type']}")
                                st.write(f"**Status:** {'✅ Active' if sub['enabled'] else '❌ Disabled'}")
                            
                            with col2:
                                st.write(f"**Priority:** {sub.get('priority', 'medium')}")
                                st.write(f"**Created:** {sub.get('created_at', 'N/A')}")
                else:
                    st.info("No subscriptions found")
            else:
                st.error("Failed to load subscriptions")
        
        except Exception as e:
            st.error(f"Error loading subscriptions: {e}")


def show_quick_setup_section(user_id: str):
    """Quick setup for common alert configurations"""
    st.markdown("### ⚙️ Quick Setup")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🏆 Top S&P 500 Stocks")
        st.write("Set up alerts for the top S&P 500 companies")
        
        if st.button("🚀 Setup Top Stocks Alerts", type="primary", width='stretch'):
            with st.spinner("Setting up alerts..."):
                try:
                    response = go_client.post(
                        "api/v1/admin/rating-alerts/setup/top-stocks",
                        params={"user_id": "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"},
                    )
                    if response and response.get("success"):
                        st.success("✅ Top stocks alerts set up successfully!")
                        st.balloons()
                    else:
                        st.error("❌ Failed to set up alerts")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    with col2:
        st.markdown("#### ⭐ Custom Watchlist")
        st.write("Set up alerts for your custom watchlist")
        
        symbols = st.text_area(
            "Enter symbols (one per line)",
            placeholder="AAPL\nMSFT\nGOOGL\nTSLA",
            help="Enter stock symbols for watchlist alerts"
        )
        
        if st.button("🚀 Setup Watchlist Alerts", type="primary", width='stretch'):
            if symbols:
                symbol_list = [s.strip().upper() for s in symbols.split('\n') if s.strip()]
                with st.spinner("Setting up alerts..."):
                    try:
                        response = go_client.post(
                            "api/v1/admin/rating-alerts/setup/watchlist",
                            params={"user_id": "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"},
                            json_data={"symbols": symbol_list},
                        )
                        if response and response.get("success"):
                            st.success(f"✅ Watchlist alerts set up for {len(symbol_list)} symbols!")
                            st.balloons()
                        else:
                            st.error("❌ Failed to set up alerts")
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.warning("Please enter at least one symbol")


def show_edit_alert_section(alert: dict, user_id: str):
    """Show edit alert section with symbol management"""
    st.markdown("---")
    st.markdown(f"### ✏️ Edit Alert: {alert['name']}")
    
    # Since each alert is for a single symbol, show that symbol
    current_symbol = alert.get('stock_symbol', '')
    st.info(f"📊 **Current Symbol:** {current_symbol}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📝 Alert Configuration")
        
        # Alert name
        new_name = st.text_input(
            "Alert Name",
            value=alert.get('name', ''),
            key=f"edit_name_{alert['alert_id']}"
        )
        
        # Alert status
        enabled = st.checkbox(
            "Enable Alert",
            value=alert.get('enabled', True),
            key=f"edit_enabled_{alert['alert_id']}"
        )
        
        # Notification channels
        notification_channels = st.multiselect(
            "Notification Channels",
            options=['email', 'sms', 'webhook'],
            default=alert.get('notification_channels', ['email']),
            key=f"edit_channels_{alert['alert_id']}"
        )
        
        if st.button("💾 Save Changes", key=f"save_{alert['alert_id']}", type="primary"):
            with st.spinner("Updating alert..."):
                try:
                    response = go_client.put(
                        f"api/v1/admin/rating-alerts/alerts/{alert['alert_id']}",
                        params={"user_id": user_id},
                        json_data={
                            "name": new_name,
                            "config": alert.get('config', {}),
                            "notification_channels": notification_channels,
                            "enabled": enabled
                        }
                    )
                    
                    if response and response.get("success"):
                        st.success("✅ Alert updated successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to update alert")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    with col2:
        st.markdown("#### ⚠️ Delete Alert")
        st.warning("⚠️ This will permanently delete this alert.")
        
        if st.button("🗑️ Delete Alert", key=f"delete_{alert['alert_id']}", type="secondary"):
            with st.spinner("Deleting alert..."):
                try:
                    response = go_client.delete(
                        f"api/v1/admin/rating-alerts/alerts/{alert['alert_id']}",
                        params={"user_id": user_id},
                    )
                    
                    if response and response.get("success"):
                        st.success("✅ Alert deleted successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete alert")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Add note about creating new alerts for other symbols
    st.info("💡 **Note:** Each alert is created for a specific symbol. To create alerts for additional symbols, use the 'Create New Alert' tab.")
    
    # Close button
    if st.button("❌ Close Edit", key=f"close_edit_{alert['alert_id']}"):
        st.session_state[f"edit_alert_{alert['alert_id']}"] = False
        st.rerun()


def filter_symbols(symbols_data, search_term, filter_status):
    """Filter symbols based on search term and status"""
    if not symbols_data:
        return []
    
    filtered = symbols_data.copy()
    
    # Filter by search term
    if search_term:
        search_term = search_term.lower()
        filtered = [s for s in filtered if 
                   search_term in s.get('symbol', '').lower() or 
                   search_term in s.get('company_name', '').lower()]
    
    # Filter by status
    if filter_status != "All":
        is_active = filter_status == "Active"
        filtered = [s for s in filtered if s.get('is_active') == is_active]
    
    return filtered


def display_symbols_table(symbols_data):
    """Display symbols in a formatted table"""
    if not symbols_data:
        st.info("No symbols found")
        return
    
    # Create DataFrame for better display
    import pandas as pd
    
    df_data = []
    for symbol in symbols_data:
        df_data.append({
            'Symbol': symbol.get('symbol', 'N/A'),
            'Company': symbol.get('company_name', 'N/A'),
            'Sector': symbol.get('sector', 'N/A'),
            'Status': '✅ Active' if symbol.get('is_active') else '❌ Inactive'
        })
    
    df = pd.DataFrame(df_data)
    
    # Display the table
    st.dataframe(df, width='stretch', hide_index=True)
    
    # Show summary
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Symbols", len(symbols_data))
    with col2:
        active_count = len([s for s in symbols_data if s.get('is_active')])
        st.metric("Active", active_count)
    with col3:
        inactive_count = len([s for s in symbols_data if not s.get('is_active')])
        st.metric("Inactive", inactive_count)


# Main execution
if __name__ == "__main__":
    main()
