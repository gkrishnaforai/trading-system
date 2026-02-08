"""
Comprehensive Admin Dashboard
Complete system monitoring and audit functionality for trading system administrators
Provides visibility into alerts, data loading, notifications, and system health
"""

import streamlit as st
import requests
import json
import time
from datetime import datetime, timedelta, date, timezone
from typing import Dict, List, Any, Optional
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os

# Add path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the same API client and config as other pages
from api_client import APIClient, APIError, APIConnectionError
from api_config import api_config

# Initialize API client
python_api_url = api_config.python_worker_url
python_client = APIClient(python_api_url, timeout=30)

go_api_url = api_config.go_api_url
go_client = APIClient(go_api_url, timeout=30)


def create_portfolio_data_load_run(portfolio_id: str, symbols: List[str], data_types: List[str], force: bool = False):
    return go_client.post(
        f"api/v1/portfolios/{portfolio_id}/data-load",
        json_data={
            "symbols": symbols,
            "data_types": data_types,
            "force": force,
        },
    )


def resolve_portfolio_symbols(portfolio_id: str) -> List[str]:
    try:
        resp = go_client.get(
            "api/v1/symbol-scope/resolve",
            params={
                "portfolio_id": portfolio_id,
                "user_id": get_user_id(),
                "subscription_level": "basic",
            },
        )
        symbols = (resp or {}).get("symbols") or []
        if not isinstance(symbols, list):
            return []
        return [str(s).strip().upper() for s in symbols if str(s).strip()]
    except Exception as e:
        st.error(f"❌ Failed to resolve portfolio symbols: {e}")
        return []


def _normalize_data_load_types(data_types: List[str]) -> List[str]:
    allowed = {
        "price_historical",
        "indicators",
        "fundamentals",
        "earnings",
        "market_news",
    }
    out: List[str] = []
    for dt in data_types or []:
        s = str(dt).strip()
        if not s:
            continue
        if s in allowed:
            out.append(s)
    # preserve order but de-dupe
    seen = set()
    deduped: List[str] = []
    for dt in out:
        if dt in seen:
            continue
        seen.add(dt)
        deduped.append(dt)
    return deduped


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Page configuration
st.set_page_config(
    page_title="Comprehensive Admin Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def get_user_id():
    """Get current user ID"""
    portfolio_user = st.session_state.get("portfolio_user")
    if isinstance(portfolio_user, dict) and portfolio_user.get("id"):
        return portfolio_user.get("id")
    return st.session_state.get('user_id', '4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4')

def get_portfolio_auth_headers() -> Dict[str, str]:
    token = st.session_state.get("portfolio_auth_token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}

def ensure_portfolio_login_ui():
    if st.session_state.get("_sidebar_portfolio_login_rendered"):
        return
    st.session_state["_sidebar_portfolio_login_rendered"] = True
    with st.sidebar.expander("Portfolio Login", expanded=False):
        if st.session_state.get("portfolio_auth_token"):
            st.success("Authenticated")
            if st.button("Logout", key="portfolio_logout"):
                st.session_state.pop("portfolio_auth_token", None)
                st.session_state.pop("portfolio_user", None)
                st.rerun()
            return

        username = st.text_input("Username", key="portfolio_username")
        password = st.text_input("Password", type="password", key="portfolio_password")
        if st.button("Login", key="portfolio_login"):
            try:
                login_resp = python_client.post(
                    "api/v1/portfolio/users/login",
                    json_data={"username": username, "password": password}
                )
                token = login_resp.get("access_token")
                if token:
                    st.session_state["portfolio_auth_token"] = token
                    st.session_state["portfolio_user"] = login_resp.get("user")
                    st.rerun()
                else:
                    st.error(login_resp.get("detail") or login_resp.get("error") or "Login failed")
            except Exception as e:
                st.error(str(e))


def ensure_notification_email_ui():
    if st.session_state.get("_sidebar_notification_email_rendered"):
        return
    st.session_state["_sidebar_notification_email_rendered"] = True
    with st.sidebar.expander("Notification Email", expanded=False):
        user_id = get_user_id()
        if not user_id:
            st.info("Login to manage notification email")
            return

        headers = {"X-User-Id": user_id}

        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("Load", key="load_me_email"):
                try:
                    me = go_client.get("api/v1/me", headers=headers)
                    st.session_state["_me_email"] = (me or {}).get("email") or ""
                except Exception as e:
                    st.error(f"❌ Failed to load profile: {e}")
        with col_b:
            if st.button("Save", key="save_me_email"):
                try:
                    email = st.session_state.get("_me_email", "").strip()
                    updated = go_client.patch("api/v1/me", json_data={"email": email}, headers=headers)
                    st.session_state["_me_email"] = (updated or {}).get("email") or email
                    st.success("Saved")
                except Exception as e:
                    st.error(f"❌ Failed to update email: {e}")

        st.text_input(
            "Email",
            key="_me_email",
            placeholder="trader@example.com",
            help="Used for alert notifications",
        )


def api_call(method: str, endpoint: str, data: Dict[str, Any] = None, params: Dict[str, Any] = None, verbose: bool = False) -> Dict[str, Any]:
    """Make API call using the same pattern as other pages"""
    try:
        # Determine the correct API prefix based on the endpoint
        if endpoint.startswith('/portfolio/'):
            # Portfolio endpoints go to /api/v1/portfolio/
            clean_endpoint = endpoint.lstrip('/')
            full_endpoint = f"api/v1/{clean_endpoint}"
            headers = get_portfolio_auth_headers()
        elif endpoint.startswith('/admin/'):
            # Admin endpoints go to /admin/
            clean_endpoint = endpoint.lstrip('/')
            full_endpoint = f"{clean_endpoint}"
            headers = None
        else:
            # Universal Alerts endpoints go to /api/v1/universal-alerts/
            clean_endpoint = endpoint.replace('/api/v1/universal-alerts', '').lstrip('/')
            full_endpoint = f"api/v1/universal-alerts/{clean_endpoint}"
            headers = None
        
        if method == "GET":
            response = python_client.get(full_endpoint, params=params, headers=headers)
        elif method == "POST":
            response = python_client.post(full_endpoint, json_data=data, params=params, headers=headers)
        elif method == "PUT":
            response = python_client.put(full_endpoint, json_data=data, params=params, headers=headers)
        elif method == "DELETE":
            response = python_client.delete(full_endpoint, params=params, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        return response
        
    except APIConnectionError as e:
        if verbose:
            st.error(f"🔌 Connection Error: {e}")
        return {"success": False, "error": str(e)}
    except APIError as e:
        if verbose:
            st.error(f"❌ API Error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        if verbose:
            st.error(f"💥 Unexpected Error: {e}")
        return {"success": False, "error": str(e)}


def grades_get(endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    try:
        return python_client.get(f"api/v1/grades/{endpoint.lstrip('/')}", params=params)
    except Exception as e:
        return {"success": False, "error": str(e)}


def grades_post(endpoint: str, params: Dict[str, Any] = None, data: Dict[str, Any] = None) -> Dict[str, Any]:
    try:
        return python_client.post(f"api/v1/grades/{endpoint.lstrip('/')}", params=params, json_data=data)
    except Exception as e:
        return {"success": False, "error": str(e)}


def ua_admin_call(method: str, path: str, data: Dict[str, Any] = None, params: Dict[str, Any] = None) -> Dict[str, Any]:
    try:
        full_endpoint = f"api/v1/universal-alerts/admin/{path.lstrip('/')}"
        if method == "GET":
            return python_client.get(full_endpoint, params=params)
        if method == "POST":
            return python_client.post(full_endpoint, json_data=data, params=params)
        raise ValueError(f"Unsupported method: {method}")
    except Exception as e:
        return {"success": False, "error": str(e)}


def show_market_day_analyst_moves():
    st.markdown("### 📈 Market Day Analyst Moves")
    st.markdown("*Upgrades/downgrades and analyst activity summary for decision making*\n")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        symbol_filter = st.text_input("Filter by symbol (optional)", value="", key="md_symbol_filter").strip().upper()
    with col2:
        days = st.number_input("Lookback (days)", min_value=1, max_value=30, value=7, step=1, key="md_days")
    with col3:
        action_filter = st.selectbox("Action", options=["All", "upgrade", "downgrade"], key="md_action")

    today = grades_get("today-changes")
    if isinstance(today, dict) and (today.get("changes") is not None):
        changes = today.get("changes", [])
    else:
        changes = []

    if symbol_filter:
        changes = [c for c in changes if (c.get("symbol") or "").upper() == symbol_filter]
    if action_filter != "All":
        changes = [c for c in changes if (c.get("action") == action_filter)]

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("⬆️ Upgrades Today", len([c for c in changes if c.get("action") == "upgrade"]))
    with col_b:
        st.metric("⬇️ Downgrades Today", len([c for c in changes if c.get("action") == "downgrade"]))
    with col_c:
        st.metric("📊 Total Today", len(changes))

    if changes:
        df = pd.DataFrame(changes)
        preferred = [
            c for c in [
                "grade_date",
                "symbol",
                "grading_company",
                "action",
                "previous_grade",
                "new_grade",
                "price_at_grade",
                "created_at",
            ]
            if c in df.columns
        ]
        st.dataframe(df[preferred] if preferred else df, width='stretch')
    else:
        st.info("No market-day upgrades/downgrades found")

    st.markdown("#### 🔄 Quick Refresh")
    col_r1, col_r2, col_r3 = st.columns([2, 1, 1])
    with col_r1:
        refresh_symbol = st.text_input("Symbol to refresh grades", value=symbol_filter or "MU", key="md_refresh_symbol").strip().upper()
    with col_r2:
        include_consensus = st.checkbox("Include consensus", value=True, key="md_refresh_consensus")
    with col_r3:
        force_refresh = st.checkbox("Force refresh", value=False, key="md_refresh_force")

    if st.button("🔄 Refresh grades now", key="md_refresh_button"):
        if not refresh_symbol:
            st.error("Symbol is required")
        else:
            resp = grades_post(f"refresh/{refresh_symbol}", params={"include_consensus": include_consensus, "force_refresh": force_refresh})
            st.json(resp)

    st.markdown("#### 🧭 What should I do as an admin?")
    st.write("- If **today changes** are empty but you expect activity: run **Refresh grades** for symbols you care about.")
    st.write("- If refresh works but **events/notifications** are not updating: run **Collect/Process** in the Notifications tab or Universal Alert System page.")
    st.write("- If the scheduler shows **no executions** recently: restart the scheduler in Operations → Scheduler Controls.")


def show_price_target_changes_dashboard():
    st.markdown("### 🎯 Price Target Changes (DB-backed)")
    st.markdown("*True price target deltas from the audit log (`rating_change_log`). Best signal for forward expectation shifts.*\n")

    scope_col, days_col, max_col = st.columns([2, 1, 1])
    with scope_col:
        scope = st.selectbox("Scope", ["Portfolio", "Manual Symbols"], key="pt_scope")
    with days_col:
        days = st.number_input("Lookback (days)", min_value=1, max_value=365, value=30, step=1, key="pt_days")
    with max_col:
        max_symbols = st.number_input("Max symbols", min_value=1, max_value=200, value=25, step=1, key="pt_max_symbols")

    symbols: List[str] = []
    if scope == "Portfolio":
        ensure_portfolio_login_ui()
        portfolios = get_available_portfolios() or []
        if portfolios:
            portfolio_options = {f"{p['name']} ({p['symbol_count']} symbols)": p['portfolio_id'] for p in portfolios}
            selected_key = st.selectbox("Select Portfolio", options=list(portfolio_options.keys()), key="pt_portfolio_select")
            portfolio_id = portfolio_options[selected_key]
            symbols = resolve_portfolio_symbols(portfolio_id)
        else:
            st.warning("No portfolios available. Login in sidebar or switch scope to Manual Symbols.")
    else:
        raw = st.text_area("Symbols (comma/newline separated)", value="MU", key="pt_manual_symbols")
        symbols = [s.strip().upper() for s in raw.replace('\n', ',').split(',') if s.strip()]

    symbols = list(dict.fromkeys(symbols))[: int(max_symbols)]

    if not symbols:
        st.info("No symbols selected")
        return

    refresh_symbol = st.text_input("Quick refresh symbol", value=symbols[0] if symbols else "MU", key="pt_refresh_symbol").strip().upper()
    refresh_force = st.checkbox("Force refresh", value=False, key="pt_refresh_force")
    if st.button("🔄 Refresh grades for symbol", key="pt_refresh_button"):
        if not refresh_symbol:
            st.error("Symbol is required")
        else:
            st.json(grades_post(f"refresh/{refresh_symbol}", params={"include_consensus": True, "force_refresh": refresh_force}))

    rows: List[Dict[str, Any]] = []
    for sym in symbols:
        resp = grades_get(f"{sym}/recent-price-target-changes", params={"days": int(days)})
        if isinstance(resp, dict) and (resp.get('changes') is not None):
            for ch in resp.get('changes', []) or []:
                item = ch.copy()
                item['symbol'] = item.get('symbol') or sym
                rows.append(item)

    if not rows:
        st.info("No price target changes found in selected window")
        st.caption("If you expect changes: refresh grades for symbols, then re-check. Price targets are logged only when the system detects a delta and writes `rating_change_log`.")
        return

    df = pd.DataFrame(rows)
    if 'created_at' in df.columns:
        try:
            df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
        except Exception:
            pass

    preferred_cols = [
        c for c in [
            'created_at',
            'symbol',
            'old_price_target',
            'new_price_target',
            'delta',
            'delta_percent',
            'old_rating',
            'new_rating',
            'rating_score',
            'data_source',
            'change_type'
        ]
        if c in df.columns
    ]

    if 'delta_percent' in df.columns:
        try:
            df = df.sort_values(by='delta_percent', ascending=False)
        except Exception:
            pass

    st.dataframe(df[preferred_cols] if preferred_cols else df, width='stretch')

    st.markdown("#### 🧭 How to use this as a trader")
    st.write("- **Large positive PT delta** + improving consensus/ratings can signal upward re-rating potential.")
    st.write("- **PT cuts** combined with downgrades and weakening fundamentals can be a sell/avoid flag.")
    st.write("- Use this alongside Fundamentals/Technical dashboards to confirm trend + valuation.")

    st.markdown("#### 🛡️ Admin audit: what to do when this is empty")
    st.write("- If **no changes**: it may be real (nothing changed) or data isn’t refreshed.")
    st.write("- Run **Refresh grades** for key symbols (above).")
    st.write("- If refresh succeeds but still no updates over time, check Operations → Scheduler Controls and restart scheduler if needed.")

def get_system_health():
    """Get comprehensive system health status"""
    health_data = {
        "api_health": {"status": "unknown", "response_time": None},
        "database_health": {"status": "unknown", "response_time": None},
        "scheduler_health": {"status": "unknown", "last_run": None},
        "memory_usage": {"status": "unknown", "usage_percent": None},
        "error_rate": {"status": "unknown", "rate": None}
    }
    
    # API Health Check - Direct call to /health endpoint
    start_time = datetime.now()
    try:
        api_health = python_client.get("health")
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        
        if api_health and api_health.get("status") == "healthy":
            health_data["api_health"] = {"status": "healthy", "response_time": response_time}
        else:
            health_data["api_health"] = {"status": "unhealthy", "response_time": response_time}
    except Exception as e:
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        health_data["api_health"] = {"status": "unhealthy", "response_time": response_time}
    
    # Database Health (via alerts endpoint)
    start_time = datetime.now()
    db_test = api_call("GET", "/alerts", params={"user_id": get_user_id(), "limit": 1}, verbose=False)
    response_time = (datetime.now() - start_time).total_seconds() * 1000
    
    if db_test.get("success"):
        health_data["database_health"] = {"status": "healthy", "response_time": response_time}
    else:
        health_data["database_health"] = {"status": "unhealthy", "response_time": response_time}
    
    # Get Universal Alerts system health and metrics
    try:
        start_time = datetime.now()
        alerts_health = api_call("GET", "/health", verbose=False)
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        
        if alerts_health and alerts_health.get("success"):
            health_data["error_rate"] = {"status": "healthy", "rate": 0}
        else:
            health_data["error_rate"] = {"status": "warning", "rate": 0.1}
    except:
        health_data["error_rate"] = {"status": "error", "rate": 0.2}
    
    # Get Universal Alerts metrics
    try:
        alerts_metrics = api_call("GET", "/metrics", verbose=False)
        if alerts_metrics and alerts_metrics.get("success"):
            metrics_data = alerts_metrics.get("metrics", {})
            # Use actual metrics if available
            error_count = metrics_data.get("error_count", 0)
            total_requests = metrics_data.get("total_requests", 1)
            error_rate = error_count / total_requests if total_requests > 0 else 0
            health_data["error_rate"] = {"status": "healthy" if error_rate < 0.05 else "warning", "rate": error_rate}
    except:
        # Keep default values if metrics call fails
        pass
    
    # Get scheduler status (Universal Alerts admin endpoint)
    try:
        scheduler_status = ua_admin_call("GET", "scheduler/status")
        if scheduler_status and scheduler_status.get("success"):
            status = scheduler_status.get("status", {})
            last_exec = status.get("last_execution")
            is_running = status.get("is_running")
            health_data["scheduler_health"] = {
                "status": "healthy" if is_running else "unhealthy",
                "last_run": last_exec,
                "details": status,
            }
        else:
            health_data["scheduler_health"] = {"status": "unknown", "last_run": None}
    except Exception:
        health_data["scheduler_health"] = {"status": "unknown", "last_run": None}
    
    return health_data

def get_alert_audit_data():
    """Get comprehensive alert audit data"""
    audit_data = {
        "total_alerts": 0,
        "active_alerts": 0,
        "alerts_by_type": {},
        "alerts_by_priority": {},
        "recent_creations": [],
        "recent_modifications": [],
        "alert_symbols_coverage": {},
        "alerts_with_no_symbols": 0,
        "oldest_alert": None,
        "newest_alert": None
    }
    
    # Get all alerts
    alerts_response = api_call("GET", "/alerts", params={"user_id": get_user_id()}, verbose=False)
    
    if alerts_response.get("success"):
        alerts = alerts_response.get("alerts", [])
        audit_data["total_alerts"] = len(alerts)
        
        # Analyze alerts
        for alert in alerts:
            # Active alerts
            if alert.get("is_active", True):
                audit_data["active_alerts"] += 1
            
            # By type
            alert_type = alert.get("alert_type", "unknown")
            audit_data["alerts_by_type"][alert_type] = audit_data["alerts_by_type"].get(alert_type, 0) + 1
            
            # By priority
            priority = alert.get("priority_level", 3)
            priority_label = f"Priority {priority}"
            audit_data["alerts_by_priority"][priority_label] = audit_data["alerts_by_priority"].get(priority_label, 0) + 1
            
            # Symbol coverage
            symbols = alert.get("entity_filters", {}).get("symbols", [])
            if symbols:
                for symbol in symbols:
                    audit_data["alert_symbols_coverage"][symbol] = audit_data["alert_symbols_coverage"].get(symbol, 0) + 1
            else:
                audit_data["alerts_with_no_symbols"] += 1
            
            # Creation dates
            created_at = alert.get("created_at")
            if created_at:
                try:
                    created_dt = _parse_iso_datetime(created_at)
                    
                    # Track oldest/newest
                    if not audit_data["oldest_alert"] or created_dt < audit_data["oldest_alert"]:
                        audit_data["oldest_alert"] = created_dt
                    if not audit_data["newest_alert"] or created_dt > audit_data["newest_alert"]:
                        audit_data["newest_alert"] = created_dt
                    
                    # Recent creations (last 7 days)
                    if created_dt >= _utc_now() - timedelta(days=7):
                        audit_data["recent_creations"].append({
                            "alert_name": alert.get("alert_name", ""),
                            "alert_type": alert_type,
                            "created_at": created_at,
                            "priority": priority,
                            "symbols": len(symbols)
                        })
                    
                    # Recent modifications (check updated_at)
                    updated_at = alert.get("updated_at")
                    if updated_at and updated_at != created_at:
                        updated_dt = _parse_iso_datetime(updated_at)
                        if updated_dt and updated_dt >= _utc_now() - timedelta(days=7):
                            audit_data["recent_modifications"].append({
                                "alert_name": alert.get("alert_name", ""),
                                "alert_type": alert_type,
                                "updated_at": updated_at,
                                "priority": priority,
                                "symbols": len(symbols)
                            })
                except:
                    pass
    
    return audit_data

def get_notification_audit_data():
    """Get notification and email delivery audit data"""
    notification_data = {
        "window_hours": 24,
        "summary_rows": [],
        "counts_by_channel": {},
        "counts_by_status": {},
        "pending_backlog": 0,
        "failed_backlog": 0,
        "sent_count": 0,
        "delivery_rates": {},
        "recent_notifications": [],
        "failed_notifications": [],
    }

    try:
        window_hours = int(st.session_state.get("notification_window_hours") or 24)
    except Exception:
        window_hours = 24
    notification_data["window_hours"] = window_hours

    summary = go_client.get(
        "api/v1/notifications/queue/summary",
        params={"window_hours": window_hours},
    )
    if summary and summary.get("success"):
        rows = summary.get("rows", []) or []
        notification_data["summary_rows"] = rows

        counts_by_channel = {}
        counts_by_status = {}
        for r in rows:
            channel = r.get("channel_type")
            status = r.get("status")
            count = int(r.get("count") or 0)
            if channel:
                counts_by_channel[channel] = counts_by_channel.get(channel, 0) + count
            if status:
                counts_by_status[status] = counts_by_status.get(status, 0) + count

        notification_data["counts_by_channel"] = counts_by_channel
        notification_data["counts_by_status"] = counts_by_status
        notification_data["pending_backlog"] = counts_by_status.get("pending", 0) + counts_by_status.get("processing", 0)
        notification_data["failed_backlog"] = counts_by_status.get("failed", 0)
        notification_data["sent_count"] = counts_by_status.get("sent", 0)

        delivery_rates = {}
        for channel, total in counts_by_channel.items():
            sent_for_channel = 0
            failed_for_channel = 0
            for r in rows:
                if r.get("channel_type") != channel:
                    continue
                stt = r.get("status")
                cnt = int(r.get("count") or 0)
                if stt == "sent":
                    sent_for_channel += cnt
                if stt == "failed":
                    failed_for_channel += cnt
            denom = sent_for_channel + failed_for_channel
            delivery_rates[channel] = (sent_for_channel / denom) if denom > 0 else 0.0
        notification_data["delivery_rates"] = delivery_rates

    recent = go_client.get(
        "api/v1/notifications/queue/recent",
        params={"limit": 200},
    )
    if recent and recent.get("success"):
        items = recent.get("items", []) or []
        notification_data["recent_notifications"] = [
            {
                "channel": it.get("channel_type"),
                "status": it.get("status"),
                "recipient": it.get("user_email") or it.get("recipient"),
                "subject": it.get("subject"),
                "created_at": it.get("created_at"),
                "attempts": it.get("attempts"),
                "error": it.get("error_message"),
                "correlation_id": it.get("correlation_id"),
            }
            for it in items
            if (it.get("status") or "").lower() in {"sent", "delivered", "pending", "processing"}
        ]
        notification_data["failed_notifications"] = [
            {
                "channel": it.get("channel_type"),
                "status": it.get("status"),
                "recipient": it.get("user_email") or it.get("recipient"),
                "subject": it.get("subject"),
                "failed_at": it.get("created_at"),
                "attempts": it.get("attempts"),
                "error": it.get("error_message"),
                "correlation_id": it.get("correlation_id"),
            }
            for it in items
            if (it.get("status") or "").lower() in {"failed", "error"}
        ]

    return notification_data


def show_job_queue_dashboard():
    st.markdown("## Job Queue Console")
    st.caption("Redis Streams observability for `ts:jobs` + DLQ. Use this as a one-stop shop for health, lag, pending, consumers, and failure triage.")

    with st.container(border=True):
        col_a, col_b, col_c, col_d, col_e = st.columns([1, 1, 1, 1, 2])
        with col_a:
            stream_key = st.text_input("Main stream", value="ts:jobs", key="jq_stream_key")
        with col_b:
            dlq_key = st.text_input("DLQ stream", value="ts:jobs:dlq", key="jq_dlq_key")
        with col_c:
            group = st.text_input("Consumer group", value="python-workers", key="jq_group")
        with col_d:
            limit = st.number_input("Recent entries", min_value=1, max_value=500, value=50, step=10, key="jq_limit")
        with col_e:
            r1, r2, r3 = st.columns([1, 1, 2])
            with r1:
                refresh = st.button("Refresh", key="jq_refresh", use_container_width=True)
            with r2:
                auto_refresh = st.checkbox("Auto-refresh", value=False, key="jq_auto_refresh")
            with r3:
                refresh_seconds = st.select_slider(
                    "Interval (s)",
                    options=[5, 10, 15, 30, 60],
                    value=15,
                    key="jq_refresh_seconds",
                    disabled=not auto_refresh,
                )

        if auto_refresh:
            if hasattr(st, "autorefresh"):
                st.autorefresh(interval=int(refresh_seconds) * 1000, key="jq_autorefresh")
            else:
                st.info("Auto-refresh requires a newer Streamlit version; use manual refresh for now.")

        if refresh:
            st.rerun()

    try:
        status = go_client.get(
            "api/v1/admin/job-queue/status",
            params={
                "stream_key": stream_key,
                "dlq_key": dlq_key,
                "group": group,
                "limit": int(limit),
            },
        )
    except Exception as e:
        st.error(f"❌ Failed to load job queue status: {e}")
        return

    if not isinstance(status, dict) or not status.get("success"):
        st.warning("Could not load job queue status")
        st.json(status)
        return

    if not status.get("enabled"):
        st.info(status.get("message") or "Job queue is not enabled")
        return

    stream = status.get("stream") or {}
    dlq = status.get("dlq") or {}

    group_infos = stream.get("groups_info") or []
    group_info = None
    for g in group_infos:
        if (g.get("name") or "") == group:
            group_info = g
            break
    if group_info is None and group_infos:
        group_info = group_infos[0]

    stream_len = int(stream.get("length") or 0)
    stream_groups = int(stream.get("groups") or 0)
    dlq_len = int(dlq.get("length") or 0)
    group_pending = int((group_info or {}).get("pending") or 0)
    group_lag = (group_info or {}).get("lag")
    try:
        group_lag = int(group_lag) if group_lag is not None else None
    except Exception:
        group_lag = None
    group_consumers = int((group_info or {}).get("consumers") or 0)

    with st.container(border=True):
        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            st.metric("Main length", stream_len)
        with k2:
            st.metric("Group lag", group_lag if group_lag is not None else "-")
        with k3:
            st.metric("Pending", group_pending)
        with k4:
            st.metric("Consumers", group_consumers)
        with k5:
            st.metric("DLQ length", dlq_len)

    with st.container(border=True):
        st.markdown("### Health interpretation")
        hcol1, hcol2, hcol3, hcol4 = st.columns([1, 1, 1, 2])
        with hcol1:
            stale_idle_s = st.number_input(
                "Stale consumer threshold (seconds)",
                min_value=5,
                max_value=3600,
                value=120,
                step=10,
                key="jq_stale_idle_s",
            )
        with hcol2:
            lag_warn = st.number_input(
                "Lag warning threshold",
                min_value=0,
                max_value=1_000_000,
                value=500,
                step=50,
                key="jq_lag_warn",
            )
        with hcol3:
            pending_warn = st.number_input(
                "Pending warning threshold",
                min_value=0,
                max_value=1_000_000,
                value=50,
                step=10,
                key="jq_pending_warn",
            )
        with hcol4:
            st.caption(
                "These heuristics help interpret queue health. Tune thresholds based on your expected workload and job duration."
            )

        consumers_for_group = (stream.get("consumers_by_group") or {}).get(group) or []
        stale_consumers = []
        for cinfo in consumers_for_group:
            try:
                idle_ms = int((cinfo or {}).get("idle_ms") or 0)
            except Exception:
                idle_ms = 0
            if idle_ms >= int(stale_idle_s) * 1000:
                stale_consumers.append((cinfo or {}).get("name") or "")

        def _safe_int(v: Any, default: int = 0) -> int:
            try:
                return int(v)
            except Exception:
                return default

        def _first_dlq_error(info: Dict[str, Any]) -> str | None:
            try:
                entries = info.get("recent_entries") or []
                if not entries:
                    return None
                values = (entries[0] or {}).get("values") or {}
                err = values.get("error")
                return str(err) if err else None
            except Exception:
                return None

        signals: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []

        def add_signal(
            title: str,
            reason: str,
            severity: str,
            suggested_actions: list[dict[str, Any]] | None = None,
        ):
            signals.append({"title": title, "reason": reason, "severity": severity})
            if suggested_actions:
                actions.extend(suggested_actions)

        if not stream.get("exists"):
            add_signal(
                title="Main stream does not exist",
                reason="No jobs have been enqueued yet, so there is nothing to consume.",
                severity="info",
                suggested_actions=[
                    {"title": "Enqueue a test run", "detail": "Use Data Load Run Tester or enqueue via the API to validate end-to-end flow."},
                ],
            )

        if stream.get("exists") and group_consumers <= 0:
            add_signal(
                title="No consumers registered",
                reason="If jobs are being enqueued, the group will fall behind and backlog will grow because no workers are consuming.",
                severity="error",
                suggested_actions=[
                    {"title": "Start/scale workers", "detail": "Ensure job-worker containers are running and attached to the correct Redis + group."},
                    {"title": "Verify consumer group", "detail": f"Run: XINFO CONSUMERS {stream_key} {group}"},
                ],
            )

        if group_lag is not None and group_lag >= _safe_int(lag_warn):
            add_signal(
                title=f"High lag (lag={group_lag})",
                reason="Lag is the number of stream entries the group is behind. High lag typically means insufficient worker throughput, workers stuck, or upstream producing too fast.",
                severity="warning" if group_lag < _safe_int(lag_warn) * 5 else "error",
                suggested_actions=[
                    {"title": "Scale workers up", "detail": "Increase job-worker replicas or reduce job production rate."},
                    {"title": "Check consumers", "detail": "Go to the Consumers tab and look for high idle or pending on a single consumer."},
                ],
            )

        if group_pending >= _safe_int(pending_warn):
            add_signal(
                title=f"High pending (pending={group_pending})",
                reason="Pending means messages were delivered to consumers but not ACKed. A spike usually indicates long-running jobs or crashed/stuck consumers.",
                severity="warning" if group_pending < _safe_int(pending_warn) * 5 else "error",
                suggested_actions=[
                    {"title": "Inspect pending ownership", "detail": f"Run: XPENDING {stream_key} {group}"},
                    {"title": "Check stale consumers", "detail": "Go to the Consumers tab; stale consumers with pending work often indicate crashed workers."},
                ],
            )

        if stale_consumers and group_pending > 0:
            add_signal(
                title="Stale consumers detected",
                reason=f"One or more consumers are idle for ≥ {int(stale_idle_s)}s while pending work exists. This often means a worker died, lost connectivity, or is wedged.",
                severity="warning",
                suggested_actions=[
                    {"title": "Restart stale worker(s)", "detail": "Restart the corresponding container(s). Pending entries will be reclaimed via XAUTOCLAIM by healthy workers."},
                ],
            )

        if dlq_len > 0:
            dlq_err = _first_dlq_error(dlq)
            reason = "A DLQ entry means a job failed repeatedly and was quarantined. This is elevated risk because data may be missing/incomplete for that symbol/run until you fix and re-run."
            if dlq_err:
                reason = f"{reason} Latest error: {dlq_err}"
            add_signal(
                title=f"DLQ has entries (count={dlq_len})",
                reason=reason,
                severity="error",
                suggested_actions=[
                    {"title": "Inspect DLQ details", "detail": "Go to the DLQ tab and open the error/payload fields to identify the root cause."},
                    {"title": "Run Redis inspection", "detail": f"Run: XRANGE {dlq_key} - + COUNT 10"},
                    {"title": "Fix + re-run", "detail": "After fixing the root cause (API, symbol, data type, DB), re-run that symbol/run via Data Load Run Tester."},
                ],
            )

        if not signals:
            st.success("Healthy: consumers active, lag/pending within thresholds, and no DLQ backlog.")
        else:
            severities = {s.get("severity") for s in signals}
            if "error" in severities:
                st.error("Elevated risk: at least one signal indicates jobs may be failing or data may be incomplete.")
            elif "warning" in severities:
                st.warning("Monitor closely: signals indicate the queue may be falling behind or consumers may be unhealthy.")
            else:
                st.info("Informational: signals detected, but no immediate risk.")

            st.markdown("**Why this is flagged**")
            for s in signals:
                title = s.get("title")
                reason = s.get("reason")
                sev = s.get("severity")
                prefix = "ERROR" if sev == "error" else ("WARN" if sev == "warning" else "INFO")
                st.write(f"- **[{prefix}] {title}**\n  - {reason}")

        def _dedupe_actions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            out = []
            seen = set()
            for it in items:
                k = (it.get("title") or "", it.get("detail") or "")
                if k in seen:
                    continue
                seen.add(k)
                out.append(it)
            return out

        actions = _dedupe_actions(actions)
        if actions:
            st.markdown("**What to do next (in order)**")
            for idx, a in enumerate(actions[:8], start=1):
                st.write(f"{idx}. **{a.get('title')}**\n   - {a.get('detail')}")
        else:
            st.markdown("**What to do next**")
            st.write("- No action recommended.")

    with st.expander("Redis CLI quick commands", expanded=False):
        cmds = [
            f"XINFO STREAM {stream_key}",
            f"XINFO GROUPS {stream_key}",
            f"XINFO CONSUMERS {stream_key} {group}",
            f"XPENDING {stream_key} {group}",
            f"XRANGE {stream_key} - + COUNT 5",
            f"XINFO STREAM {dlq_key}",
            f"XRANGE {dlq_key} - + COUNT 10",
        ]
        st.code("\n".join(cmds))

    tab_overview, tab_consumers, tab_pending, tab_recent, tab_dlq = st.tabs(
        ["Overview", "Consumers", "Pending", "Recent", "DLQ"],
    )

    with tab_overview:
        left, right = st.columns(2)
        with left:
            st.markdown("### Main stream")
            if not stream.get("exists"):
                st.info("Stream key does not exist yet")
            else:
                s1, s2, s3, s4 = st.columns(4)
                with s1:
                    st.metric("Length", int(stream.get("length") or 0))
                with s2:
                    st.metric("Entries added", int(stream.get("entries_added") or 0))
                with s3:
                    st.metric("Groups", int(stream.get("groups") or 0))
                with s4:
                    st.metric("Key", stream.get("key") or "")

                if group_infos:
                    rows = []
                    for g in group_infos:
                        rows.append(
                            {
                                "group": g.get("name"),
                                "consumers": g.get("consumers"),
                                "pending": g.get("pending"),
                                "lag": g.get("lag"),
                                "last_delivered_id": g.get("last-delivered-id") or g.get("last_delivered_id"),
                            }
                        )
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        with right:
            st.markdown("### DLQ")
            if not dlq.get("exists"):
                st.info("DLQ key does not exist yet")
            else:
                d1, d2, d3, d4 = st.columns(4)
                with d1:
                    st.metric("Length", int(dlq.get("length") or 0))
                with d2:
                    st.metric("Entries added", int(dlq.get("entries_added") or 0))
                with d3:
                    st.metric("Groups", int(dlq.get("groups") or 0))
                with d4:
                    st.metric("Key", dlq.get("key") or "")

    with tab_consumers:
        st.markdown("### Consumers")
        consumers_by_group = stream.get("consumers_by_group") or {}
        if not consumers_by_group:
            st.info("No consumer info available")
        else:
            filter_text = st.text_input("Filter (consumer name)", value="", key="jq_consumer_filter")
            for gname, consumers in consumers_by_group.items():
                st.markdown(f"#### Group: `{gname}`")
                if not consumers:
                    st.info("No consumers")
                    continue
                df = pd.DataFrame(consumers)
                if "idle_ms" in df.columns:
                    try:
                        df["idle_s"] = (df["idle_ms"].astype(float) / 1000.0).round(1)
                    except Exception:
                        pass
                if "idle_s" in df.columns:
                    try:
                        df["status"] = df["idle_s"].apply(lambda x: "stale" if pd.notna(x) and float(x) >= float(stale_idle_s) else "ok")
                    except Exception:
                        df["status"] = "ok"
                if filter_text:
                    ft = filter_text.strip().lower()
                    if "name" in df.columns:
                        df = df[df["name"].astype(str).str.lower().str.contains(ft, na=False)]
                cols = list(df.columns)
                if "idle_s" in cols and "idle_ms" in cols:
                    cols = [c for c in cols if c != "idle_ms"]
                st.dataframe(df[cols], use_container_width=True, hide_index=True)

    with tab_pending:
        st.markdown("### Pending")
        pending_by_group = stream.get("pending_by_group") or {}
        if not pending_by_group:
            st.info("No pending summary available")
        else:
            rows = [{"group": k, **(v or {})} for k, v in pending_by_group.items()]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab_recent:
        st.markdown("### Recent jobs")
        entries = stream.get("recent_entries") or []
        if not entries:
            st.info("No recent entries")
        else:
            symbol_filter = st.text_input("Filter (symbol)", value="", key="jq_recent_symbol_filter")
            rows = []
            for m in entries:
                values = m.get("values") or {}
                payload = values.get("payload")
                run_id = None
                symbol = None
                attempt = None
                max_attempts = None
                try:
                    if payload:
                        pj = json.loads(payload)
                        run_id = pj.get("run_id")
                        symbol = pj.get("symbol")
                        attempt = pj.get("attempt")
                        max_attempts = pj.get("max_attempts")
                except Exception:
                    pass
                if symbol_filter and symbol and symbol_filter.strip().upper() not in str(symbol).upper():
                    continue
                rows.append(
                    {
                        "id": m.get("id"),
                        "job_id": values.get("job_id"),
                        "job_type": values.get("job_type"),
                        "run_id": run_id,
                        "symbol": symbol,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "enqueued_at": values.get("enqueued_at"),
                        "deferred_reason": values.get("deferred_reason"),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab_dlq:
        st.markdown("### Dead Letter Queue")
        dlq_entries = dlq.get("recent_entries") or []
        if not dlq_entries:
            st.info("No DLQ entries")
        else:
            rows = []
            for m in dlq_entries:
                values = m.get("values") or {}
                payload = values.get("payload")
                run_id = None
                symbol = None
                attempt = None
                max_attempts = None
                try:
                    if payload:
                        pj = json.loads(payload)
                        run_id = pj.get("run_id")
                        symbol = pj.get("symbol")
                        attempt = pj.get("attempt")
                        max_attempts = pj.get("max_attempts")
                except Exception:
                    pass
                rows.append(
                    {
                        "id": m.get("id"),
                        "job_id": values.get("job_id"),
                        "source_msg_id": values.get("source_msg_id"),
                        "run_id": run_id,
                        "symbol": symbol,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "failed_at": values.get("failed_at") or values.get("enqueued_at"),
                        "error": values.get("error"),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            st.markdown("#### DLQ actions")
            st.caption("Requeue pushes DLQ entries back onto the main stream for retry. Delete removes entries (useful for tombstones or after requeue with delete-after).")

            available_ids = [str(m.get("id") or "").strip() for m in dlq_entries if str(m.get("id") or "").strip()]
            selected_ids = st.multiselect(
                "Select DLQ message IDs",
                options=available_ids,
                default=available_ids[:1] if available_ids else [],
                key="jq_dlq_action_ids",
            )
            delete_after = st.checkbox("Delete after requeue", value=True, key="jq_dlq_delete_after")

            a1, a2, a3 = st.columns([1, 1, 2])
            with a1:
                do_requeue = st.button("Requeue", disabled=not selected_ids, key="jq_dlq_requeue", use_container_width=True)
            with a2:
                do_delete = st.button("Delete", disabled=not selected_ids, key="jq_dlq_delete", use_container_width=True)
            with a3:
                st.caption("Requeue target: main stream key from top panel")

            if do_requeue:
                try:
                    resp = go_client.post(
                        "api/v1/admin/job-queue/dlq/requeue",
                        json_data={
                            "dlq_key": dlq_key,
                            "stream_key": stream_key,
                            "ids": selected_ids,
                            "delete_after": bool(delete_after),
                        },
                    )
                    st.json(resp)
                except Exception as e:
                    st.error(f"Failed to requeue DLQ entries: {e}")

            if do_delete:
                try:
                    resp = go_client.post(
                        "api/v1/admin/job-queue/stream/delete",
                        json_data={
                            "key": dlq_key,
                            "ids": selected_ids,
                        },
                    )
                    st.json(resp)
                except Exception as e:
                    st.error(f"Failed to delete DLQ entries: {e}")

            st.markdown("#### Inspect DLQ message")
            ids = [str(m.get("id") or "").strip() for m in dlq_entries if str(m.get("id") or "").strip()]
            selected_id = st.selectbox("DLQ message id", options=ids, index=0, key="jq_dlq_selected_id")
            selected = None
            for m in dlq_entries:
                if str(m.get("id") or "").strip() == selected_id:
                    selected = m
                    break

            selected_values = (selected or {}).get("values") or {}

            if not selected_values:
                st.warning(
                    "This DLQ message looks like a Redis Stream tombstone (the ID exists but the field map is empty). "
                    "This typically happens if the entry was deleted (XDEL) or trimmed. There is no payload/error to display."
                )
                st.caption("Next steps: refresh, verify you are looking at the correct DLQ key, and inspect Redis directly via XRANGE.")
                st.code(f"XRANGE {dlq_key} {selected_id} {selected_id}")

            raw_payload = selected_values.get("payload")
            decoded_payload = None
            if raw_payload:
                try:
                    decoded_payload = json.loads(raw_payload)
                except Exception:
                    decoded_payload = None

            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown("**Error**")
                err = selected_values.get("error")
                if err:
                    st.code(str(err))
                else:
                    st.info("No `error` field found on this DLQ entry")
            with c2:
                st.markdown("**Metadata**")
                st.json(
                    {
                        "id": selected_id,
                        "job_id": selected_values.get("job_id"),
                        "source_msg_id": selected_values.get("source_msg_id"),
                        "failed_at": selected_values.get("failed_at") or selected_values.get("enqueued_at"),
                        "job_type": selected_values.get("job_type"),
                    }
                )

            with st.expander("Payload (decoded)", expanded=True):
                if decoded_payload is not None:
                    st.json(decoded_payload)
                elif raw_payload:
                    st.code(str(raw_payload))
                else:
                    st.info("No `payload` field found on this DLQ entry")

            with st.expander("Raw Redis fields", expanded=False):
                st.json(selected_values)


def show_on_demand_alert_pipeline():
    st.markdown("### 🧪 On-Demand Alert Pipeline")
    st.markdown("*Refresh grades → collect grade events → process → verify notifications*\n")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        symbol = st.text_input("Symbol", value="MU", key="pipeline_symbol").strip().upper()
        days = st.number_input("Days (DB lookback for collection)", min_value=1, max_value=365, value=30, step=1, key="pipeline_days")
    with col2:
        st.write("\n")
        st.write("\n")
        run_refresh = st.button("🔄 Refresh Grades", key="pipeline_refresh")
        run_collect = st.button("📥 Collect Events", key="pipeline_collect")
    with col3:
        st.write("\n")
        st.write("\n")
        run_process_one = st.button("⚡ Process 1 Pending", key="pipeline_process_one")
        run_process_all = st.button("⚡ Process All Pending", key="pipeline_process_all")

    if run_refresh:
        if not symbol:
            st.error("Symbol is required")
        else:
            try:
                resp = python_client.post(f"api/v1/grades/refresh/{symbol}")
                st.json(resp)
            except Exception as e:
                st.error(str(e))

    if run_collect:
        if not symbol:
            st.error("Symbol is required")
        else:
            payload = {
                "analyst_grades": {
                    "sources": ["fmp"],
                    "symbols": [symbol],
                    "days": int(days)
                }
            }
            resp = api_call("POST", "/data-collection/collect", data=payload, verbose=True)
            st.json(resp)

    pending = api_call("GET", "/events/pending", params={"event_type": "grade_change", "limit": 50}, verbose=False)
    pending_events = pending.get("events", []) if pending.get("success") else []
    st.write(f"**Pending grade_change events:** {len(pending_events)}")

    def _post_event(ev: Dict[str, Any]):
        body = {
            "event_type": ev.get("event_type", "grade_change"),
            "entity_type": ev.get("entity_type", "stock"),
            "entity_id": ev.get("entity_id"),
            "event_data": ev.get("event_data", {}),
            "previous_data": ev.get("previous_data"),
            "change_metadata": ev.get("change_metadata"),
            "event_timestamp": ev.get("event_timestamp"),
            "data_source": ev.get("data_source", "local_db"),
            "source_id": ev.get("source_id"),
            "confidence_score": ev.get("confidence_score", 0.85),
            "priority": ev.get("priority", 3),
            "correlation_id": ev.get("correlation_id"),
            "tags": ev.get("tags", [])
        }
        return api_call("POST", "/events", data=body, verbose=True)

    if run_process_one:
        if not pending_events:
            st.info("No pending events")
        else:
            st.json(_post_event(pending_events[0]))

    if run_process_all:
        if not pending_events:
            st.info("No pending events")
        else:
            results = []
            for ev in pending_events:
                results.append(_post_event(ev))
            st.json({"processed": len(results), "results": results[:5]})

    st.markdown("#### 🔔 Recent Notification Queue Activity")
    try:
        recent = go_client.get("api/v1/notifications/queue/recent", params={"limit": 100})
        if recent and recent.get("success"):
            items = recent.get("items", []) or []
            # Focus this panel on items with correlation_id so operators can trace run/processing flows.
            items = [it for it in items if it.get("correlation_id")]
            st.write(f"**Queue items (with correlation_id):** {len(items)}")
            if items:
                df = pd.DataFrame(
                    [
                        {
                            "created_at": it.get("created_at"),
                            "channel": it.get("channel_type"),
                            "status": it.get("status"),
                            "recipient": it.get("user_email") or it.get("recipient"),
                            "subject": it.get("subject"),
                            "attempts": it.get("attempts"),
                            "error": it.get("error_message"),
                            "correlation_id": it.get("correlation_id"),
                        }
                        for it in items
                    ]
                )
                if "created_at" in df.columns:
                    df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
                st.dataframe(df, width='stretch')
            else:
                st.info("No recent queue items found with correlation_id")
        else:
            st.warning("Could not load notification queue items")
            st.json(recent)
    except Exception as e:
        st.warning(f"Could not load notification queue items: {e}")

def get_alert_data_monitoring():
    """Get alert-specific data monitoring and interval tracking"""
    alert_data = {
        "alert_specific_sources": {},
        "data_loading_intervals": {},
        "missing_symbols": [],
        "alert_data_health": {},
        "scheduled_jobs": [],
        "data_collection_status": {}
    }
    
    # Alert-specific data sources and their expected loading intervals
    # Include all FMP data sources that are actively used
    alert_data_sources = {
        # === ANALYST & GRADING DATA (FMP Primary) ===
        "stock_grades": {
            "name": "Stock Grades (Analyst Ratings)",
            "table": "stock_grades",
            "expected_interval": "hourly", 
            "alert_types": ["grade_change", "rating_change"],
            "priority": "high",
            "api_endpoint": "/api/v1/grades/refresh/{symbol}",
            "data_source": "fmp",
            "category": "analyst_data"
        },
        "consensus_data": {
            "name": "Analyst Consensus Data",
            "table": "stock_consensus_history",
            "expected_interval": "daily",
            "alert_types": ["consensus_change", "rating_change"],
            "priority": "high",
            "api_endpoint": "/api/v1/grades/update-consensus/{symbol}",
            "data_source": "fmp",
            "category": "analyst_data"
        },
        "price_targets": {
            "name": "Price Targets",
            "table": "stock_grades",
            "expected_interval": "daily",
            "alert_types": ["price_target_change", "analyst_upgrade"],
            "priority": "medium",
            "api_endpoint": "/api/v1/grades/refresh/{symbol}",
            "data_source": "fmp",
            "category": "analyst_data"
        },
        "analyst_ratings": {
            "name": "Analyst Ratings",
            "table": "stock_grades",
            "expected_interval": "daily",
            "alert_types": ["analyst_upgrade", "analyst_downgrade"],
            "priority": "medium",
            "api_endpoint": "/api/v1/grades/refresh/{symbol}",
            "data_source": "fmp",
            "category": "analyst_data"
        },
        
        # === MARKET DATA ===
        "raw_market_data_daily": {
            "name": "Market Data (Daily)",
            "table": "raw_market_data_daily",
            "expected_interval": "daily",
            "alert_types": ["price_movement", "volume_spike", "technical_indicator"],
            "priority": "high", 
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "market_data"
        },
        "raw_market_data_intraday": {
            "name": "Market Data (Intraday)",
            "table": "raw_market_data_intraday",
            "expected_interval": "hourly",
            "alert_types": ["price_movement", "volume_spike"],
            "priority": "medium",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "market_data"
        },
        
        # === FINANCIAL STATEMENTS ===
        "fundamentals_snapshots": {
            "name": "Fundamentals Data",
            "table": "fundamentals_snapshots",
            "expected_interval": "daily", 
            "alert_types": ["fundamentals_change", "valuation_change"],
            "priority": "high",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "financial_statements"
        },
        "income_statements": {
            "name": "Income Statements",
            "table": "income_statements",
            "expected_interval": "daily",
            "alert_types": ["earnings_change", "revenue_change"],
            "priority": "medium",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "financial_statements"
        },
        "balance_sheets": {
            "name": "Balance Sheets",
            "table": "balance_sheets",
            "expected_interval": "daily",
            "alert_types": ["balance_sheet_change", "debt_change"],
            "priority": "medium",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "financial_statements"
        },
        "cash_flow_statements": {
            "name": "Cash Flow Statements",
            "table": "cash_flow_statements",
            "expected_interval": "daily",
            "alert_types": ["cash_flow_change", "free_cash_flow_change"],
            "priority": "medium",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "financial_statements"
        },
        
        # === FINANCIAL METRICS ===
        "indicators_daily": {
            "name": "Technical Indicators",
            "table": "indicators_daily",
            "expected_interval": "daily",
            "alert_types": ["technical_indicator"],
            "priority": "high",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "financial_metrics"
        },
        "financial_ratios": {
            "name": "Financial Ratios",
            "table": "financial_ratios",
            "expected_interval": "daily",
            "alert_types": ["ratio_change", "valuation_ratio_change"],
            "priority": "medium",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "financial_metrics"
        },
        "key_metrics_ttm": {
            "name": "Key Metrics (TTM)",
            "table": "key_metrics_ttm",
            "expected_interval": "daily",
            "alert_types": ["metric_change", "growth_change"],
            "priority": "medium",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "financial_metrics"
        },
        "financial_scores": {
            "name": "Financial Scores",
            "table": "financial_scores",
            "expected_interval": "daily",
            "alert_types": ["score_change", "health_change"],
            "priority": "low",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "financial_metrics"
        },
        
        # === EARNINGS DATA ===
        "earnings_data": {
            "name": "Earnings Data",
            "table": "earnings_data", 
            "expected_interval": "daily",
            "alert_types": ["earnings_announcement", "earnings_surprise"],
            "priority": "high",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "earnings_data"
        },
        "earnings_transcripts": {
            "name": "Earnings Transcripts",
            "table": "earnings_transcripts",
            "expected_interval": "daily",
            "alert_types": ["transcript_available", "call_sentiment"],
            "priority": "low",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "earnings_data"
        },
        
        # === NEWS & EVENTS ===
        "market_news": {
            "name": "Market News",
            "table": "market_news",
            "expected_interval": "hourly",
            "alert_types": ["news_sentiment", "news_volume"],
            "priority": "medium",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "news_events"
        },
        "corporate_actions": {
            "name": "Corporate Actions",
            "table": "corporate_actions",
            "expected_interval": "daily",
            "alert_types": ["stock_split", "dividend_change", "buyback"],
            "priority": "medium",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "news_events"
        },
        
        # === REFERENCE DATA ===
        "industry_peers": {
            "name": "Industry Peers",
            "table": "industry_peers",
            "expected_interval": "weekly",
            "alert_types": ["industry_performance", "peer_comparison"],
            "priority": "medium",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "reference_data"
        },
        "macro_market_data": {
            "name": "Macro Market Data",
            "table": "macro_market_data",
            "expected_interval": "daily",
            "alert_types": ["market_sentiment", "macro_indicator"],
            "priority": "low",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "reference_data"
        },
        
        # === SPECIALIZED DATA ===
        "short_interest": {
            "name": "Short Interest",
            "table": "short_interest",
            "expected_interval": "daily",
            "alert_types": ["short_interest_change", "short_squeeze"],
            "priority": "low",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "specialized_data"
        },
        "short_volume": {
            "name": "Short Volume",
            "table": "short_volume",
            "expected_interval": "daily",
            "alert_types": ["short_volume_spike", "short_ratio_change"],
            "priority": "low",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "specialized_data"
        },
        "share_float": {
            "name": "Share Float",
            "table": "share_float",
            "expected_interval": "weekly",
            "alert_types": ["float_change", "insider_activity"],
            "priority": "low",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "specialized_data"
        },
        "risk_factors": {
            "name": "Risk Factors",
            "table": "risk_factors",
            "expected_interval": "monthly",
            "alert_types": ["risk_factor_change", "compliance_alert"],
            "priority": "low",
            "api_endpoint": "/api/v1/refresh",
            "data_source": "fmp",
            "category": "specialized_data"
        }
    }
    
    # Check each alert-specific data source
    for source_key, source_info in alert_data_sources.items():
        try:
            # Get table summary
            summary_response = python_client.get(f"admin/data-summary/{source_info['table']}")

            if isinstance(summary_response, dict) and summary_response.get("total_records") is not None:
                total_records = summary_response.get("total_records", 0)
                latest_date = summary_response.get("last_updated")
                
                # Check if data is loading at expected intervals
                interval_status = "on_track"
                interval_icon = "🟢"
                last_loaded = "Unknown"
                next_expected = "Unknown"
                
                if latest_date:
                    try:
                        if isinstance(latest_date, str):
                            latest_dt = datetime.fromisoformat(latest_date.replace('Z', '+00:00'))
                        else:
                            latest_dt = latest_date
                        
                        last_loaded = latest_dt.strftime('%Y-%m-%d %H:%M:%S')
                        
                        # Calculate if data is loading at expected intervals
                        now = _utc_now()
                        if latest_dt.tzinfo is None:
                            latest_dt = latest_dt.replace(tzinfo=timezone.utc)
                        else:
                            latest_dt = latest_dt.astimezone(timezone.utc)
                        age_hours = (now - latest_dt).total_seconds() / 3600
                        
                        if source_info["expected_interval"] == "hourly":
                            if age_hours > 2:
                                interval_status = "delayed"
                                interval_icon = "🟡"
                            if age_hours > 6:
                                interval_status = "overdue"
                                interval_icon = "🔴"
                            next_expected = (latest_dt + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M')
                        elif source_info["expected_interval"] == "daily":
                            if age_hours > 30:
                                interval_status = "delayed" 
                                interval_icon = "🟡"
                            if age_hours > 48:
                                interval_status = "overdue"
                                interval_icon = "🔴"
                            next_expected = (latest_dt + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
                        
                    except:
                        interval_status = "error"
                        interval_icon = "🔴"
                        last_loaded = "Invalid date"
                
                # Check if there are alerts that depend on this data
                alerts_response = api_call("GET", "/alerts", params={"user_id": get_user_id()}, verbose=False)
                dependent_alerts = 0
                if alerts_response.get("success"):
                    alerts = alerts_response.get("alerts", [])
                    for alert in alerts:
                        alert_type = alert.get("alert_type", "")
                        if alert_type in source_info["alert_types"]:
                            dependent_alerts += 1
                
                alert_data["alert_specific_sources"][source_key] = {
                    "name": source_info["name"],
                    "table": source_info["table"],
                    "expected_interval": source_info["expected_interval"],
                    "interval_status": interval_status,
                    "interval_icon": interval_icon,
                    "total_records": total_records,
                    "last_loaded": last_loaded,
                    "next_expected": next_expected,
                    "dependent_alerts": dependent_alerts,
                    "alert_types": source_info["alert_types"],
                    "priority": source_info["priority"],
                    "api_endpoint": source_info["api_endpoint"]
                }
                
            else:
                # API call failed
                alert_data["alert_specific_sources"][source_key] = {
                    "name": source_info["name"],
                    "table": source_info["table"],
                    "expected_interval": source_info["expected_interval"],
                    "interval_status": "error",
                    "interval_icon": "🔴",
                    "total_records": 0,
                    "last_loaded": "API Error",
                    "next_expected": "Unknown",
                    "dependent_alerts": 0,
                    "alert_types": source_info["alert_types"],
                    "priority": source_info["priority"],
                    "api_endpoint": source_info["api_endpoint"],
                    "error": summary_response.get("error") if isinstance(summary_response, dict) else "Failed to fetch data summary",
                }
        except Exception as e:
            # Handle API errors
            alert_data["alert_specific_sources"][source_key] = {
                "name": source_info["name"],
                "table": source_info["table"],
                "expected_interval": source_info["expected_interval"],
                "interval_status": "error",
                "interval_icon": "🔴",
                "total_records": 0,
                "last_loaded": "API Error",
                "next_expected": "Unknown",
                "dependent_alerts": 0,
                "alert_types": source_info["alert_types"],
                "priority": source_info["priority"],
                "api_endpoint": source_info["api_endpoint"],
                "error": str(e),
            }
    try:
        stocks_response = python_client.get("admin/data-summary/stocks")
        if isinstance(stocks_response, dict) and stocks_response.get("total_records") is not None:
            total_symbols = stocks_response.get("total_records", 0)
            
            # Check each alert data source for missing symbols
            for source_key, source_info in alert_data["alert_specific_sources"].items():
                if source_info["total_records"] < total_symbols * 0.8:  # Less than 80% coverage
                    alert_data["missing_symbols"].append({
                        "data_source": source_info["name"],
                        "expected_symbols": total_symbols,
                        "actual_records": source_info["total_records"],
                        "coverage_percentage": (source_info["total_records"] / total_symbols * 100) if total_symbols > 0 else 0,
                        "missing_count": total_symbols - source_info["total_records"]
                    })
        else:
            # If stocks table fails, use a reasonable estimate
            total_symbols = 1000  # Estimate
            for source_key, source_info in alert_data["alert_specific_sources"].items():
                if source_info["total_records"] < total_symbols * 0.8:
                    alert_data["missing_symbols"].append({
                        "data_source": source_info["name"],
                        "expected_symbols": total_symbols,
                        "actual_records": source_info["total_records"],
                        "coverage_percentage": (source_info["total_records"] / total_symbols * 100),
                        "missing_count": total_symbols - source_info["total_records"]
                    })
    except Exception:
        pass
    
    return alert_data

def get_available_portfolios():
    """Get available portfolios from the API"""
    try:
        # Use the portfolio API to get user portfolios
        response = api_call("GET", "/portfolio/portfolios")

        if isinstance(response, list):
            portfolios = response
        elif isinstance(response, dict) and response.get("success"):
            portfolios = response.get("portfolios", [])
        else:
            portfolios = []

        if portfolios:
            
            # Transform to expected format
            portfolio_list = []
            for portfolio in portfolios:
                portfolio_list.append({
                    'portfolio_id': portfolio.get('id', portfolio.get('portfolio_id')),
                    'name': portfolio.get('name', 'Unknown Portfolio'),
                    'symbol_count': len(portfolio.get('holdings', [])),
                    'portfolio_type': portfolio.get('portfolio_type', 'unknown'),
                    'total_value': portfolio.get('total_value', 0)
                })
            
            return portfolio_list
        else:
            st.warning("No portfolios returned")
        return None
    except Exception as e:
        st.error(f"❌ **Portfolio Loading Failed**: {str(e)}")
        st.error("🔧 **Technical Issue**: Unable to connect to portfolio service")
        return None  # Return None to indicate failure

def get_portfolio_details(portfolio_id: str):
    """Get detailed portfolio information from the API"""
    try:
        def _to_float(v) -> float:
            if v is None:
                return 0.0
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                s = v.strip()
                if not s:
                    return 0.0
                try:
                    return float(s)
                except Exception:
                    return 0.0
            try:
                return float(v)
            except Exception:
                return 0.0

        # Use the portfolio API to get portfolio holdings
        response = api_call("GET", f"/portfolio/portfolios/{portfolio_id}/holdings", 
                          params={"user_id": get_user_id()})

        if isinstance(response, dict) and response.get("success") is False:
            st.error(f"❌ **Portfolio Holdings API Error**: {response.get('error')}")
            return None

        if isinstance(response, list):
            holdings = response
        elif isinstance(response, dict) and response.get("success"):
            holdings = response.get("holdings", [])
        else:
            holdings = []

        if holdings is not None:
            
            # Extract symbols from holdings
            symbols = []
            total_value = 0.0
            
            for holding in holdings:
                symbol = holding.get('symbol')
                if symbol:
                    symbols.append(symbol)
                    holding_value = holding.get('value')
                    if holding_value is not None:
                        total_value += _to_float(holding_value)
                        continue

                    qty = holding.get('quantity')
                    if qty is None:
                        qty = holding.get('shares_held')
                    qty = _to_float(qty)

                    px = holding.get('current_price')
                    px = _to_float(px)

                    total_value += qty * px
            
            # Get portfolio basic info
            portfolio_response = api_call("GET", "/portfolio/portfolios", 
                                         params={"user_id": get_user_id()})

            if isinstance(portfolio_response, list):
                portfolios = portfolio_response
            elif isinstance(portfolio_response, dict) and portfolio_response.get("success"):
                portfolios = portfolio_response.get("portfolios", [])
            else:
                portfolios = []
            
            portfolio_name = f"Portfolio {portfolio_id}"
            portfolio_type = "unknown"
            
            if portfolios:
                for portfolio in portfolios:
                    if portfolio.get('id') == portfolio_id or portfolio.get('portfolio_id') == portfolio_id:
                        portfolio_name = portfolio.get('name', portfolio_name)
                        portfolio_type = portfolio.get('portfolio_type', portfolio_type)
                        break
            
            return {
                'portfolio_id': portfolio_id,
                'name': portfolio_name,
                'symbols': symbols,
                'symbol_count': len(symbols),
                'portfolio_type': portfolio_type,
                'total_value': total_value,
                'holdings': holdings
            }
        if isinstance(response, dict) and response.get("error"):
            st.error(f"❌ **Portfolio Details API Error**: {response.get('error')}")
        else:
            st.error(f"❌ **Portfolio Details API Error**: No data returned")
        return None
    except Exception as e:
        st.error(f"❌ **Portfolio Details Loading Failed**: {str(e)}")
        st.error(f"🔧 **Technical Issue**: Failed to build portfolio details for portfolio ID: {portfolio_id}")
        return None  # Return None to indicate failure


def show_stocks_management_dashboard():
    st.markdown("## 📊 Stocks Management")
    st.markdown("*Stock inventory and portfolio integration*\n")

    try:
        tab1, tab2 = st.tabs(["📋 Stock Inventory", "📂 Portfolio Integration"])

        with tab1:
            show_stock_inventory()

        with tab2:
            available_portfolios = get_available_portfolios()
            if not available_portfolios:
                st.warning("No portfolios available")
                return

            portfolio_options = {
                f"{p['name']} ({p['symbol_count']} symbols)": p['portfolio_id']
                for p in available_portfolios
            }
            selected_key = st.selectbox(
                "Select Portfolio",
                options=list(portfolio_options.keys()),
                key="stocks_mgmt_portfolio"
            )
            portfolio_id = portfolio_options[selected_key]
            portfolio_details = get_portfolio_details(portfolio_id)
            if not portfolio_details:
                st.warning("Could not load portfolio details")
                return

            st.write(f"**Portfolio:** {portfolio_details.get('name', portfolio_id)}")
            st.write(f"**Symbol Count:** {portfolio_details.get('symbol_count', 0)}")
            symbols = [h.get('symbol') for h in portfolio_details.get('holdings', []) if h.get('symbol')]
            if symbols:
                st.write(", ".join(symbols[:50]))
            else:
                st.info("No holdings found")
    except Exception as e:
        st.error(f"Stocks Management tab error: {e}")
        st.code(str(e))


def show_stock_inventory():
    st.markdown("### 📋 Stock Inventory")

    try:
        st.write("🔍 Debug: Fetching stocks from API...")
        response = python_client.get("api/v1/stocks/available")

        if not response or not response.get("success", False):
            st.error("Failed to load stocks inventory")
            if response:
                st.json(response)
            return

        stocks = response.get("data", [])
        st.write(f"🔍 Debug: Found {len(stocks)} stocks")

        if not stocks:
            st.info("No stocks returned")
            return

        search_term = st.text_input(
            "Search",
            placeholder="Search by symbol or company name...",
            key="stocks_inventory_search"
        )

        filtered = stocks
        if search_term:
            s = search_term.lower()
            filtered = [
                x for x in filtered
                if s in (x.get("symbol") or "").lower() or s in (x.get("company_name") or "").lower()
            ]

        df = pd.DataFrame(filtered)
        preferred_cols = [
            c for c in ["symbol", "company_name", "sector", "industry", "exchange", "is_active"]
            if c in df.columns
        ]
        st.dataframe(df[preferred_cols] if preferred_cols else df, width='stretch')
    except Exception as e:
        st.error(f"Error loading stock inventory: {e}")
        st.code(str(e))

def get_portfolio_data_coverage(portfolio_id: str):
    """Get data coverage analysis for portfolio"""
    try:
        portfolio_details = get_portfolio_details(portfolio_id)
        if not portfolio_details:
            return None
        
        symbols = portfolio_details['symbols']
        
        # Check for different types of alerts based on data loaded
        new_alerts = []
        alert_categories = []
        
        if any(dt in data_types_loaded for dt in ["grades", "stock_grades"]):
            alert_status.write("**📊 Checking for analyst grade changes...**")
            # Get recent grade change alerts
            grade_alerts = api_call("GET", "/alerts", 
                                 params={"user_id": get_user_id(), 
                                       "alert_type": "grade_change", 
                                       "limit": 20}, 
                                 verbose=False)
            
            if grade_alerts and grade_alerts.get("success"):
                alerts = grade_alerts.get("alerts", [])
                # Filter alerts for portfolio symbols
                portfolio_grade_alerts = [
                    alert for alert in alerts 
                    if alert.get("entity_filters", {}).get("symbols") and 
                       any(symbol in alert["entity_filters"]["symbols"] for symbol in portfolio_symbols)
                ]
                new_alerts.extend(portfolio_grade_alerts)
                alert_categories.extend(["Grade Changes"] * len(portfolio_grade_alerts))
        
        if any(dt in data_types_loaded for dt in ["price_historical", "fundamentals"]):
            alert_status.write("**💰 Checking for price target changes...**")
            # Get recent price target alerts
            price_alerts = api_call("GET", "/alerts", 
                                   params={"user_id": get_user_id(), 
                                         "alert_type": "price_target_change", 
                                         "limit": 20}, 
                                   verbose=False)
            
            if price_alerts and price_alerts.get("success"):
                alerts = price_alerts.get("alerts", [])
                # Filter alerts for portfolio symbols
                portfolio_price_alerts = [
                    alert for alert in alerts 
                    if alert.get("entity_filters", {}).get("symbols") and 
                       any(symbol in alert["entity_filters"]["symbols"] for symbol in portfolio_symbols)
                ]
                new_alerts.extend(portfolio_price_alerts)
                alert_categories.extend(["Price Targets"] * len(portfolio_price_alerts))
        
        if any(dt in data_types_loaded for dt in ["earnings", "earnings_data"]):
            alert_status.write("**📈 Checking for earnings alerts...**")
            # Get recent earnings alerts
            earnings_alerts = api_call("GET", "/alerts", 
                                      params={"user_id": get_user_id(), 
                                            "alert_type": "earnings_announcement", 
                                            "limit": 20}, 
                                      verbose=False)
            
            if earnings_alerts and earnings_alerts.get("success"):
                alerts = earnings_alerts.get("alerts", [])
                # Filter alerts for portfolio symbols
                portfolio_earnings_alerts = [
                    alert for alert in alerts 
                    if alert.get("entity_filters", {}).get("symbols") and 
                       any(symbol in alert["entity_filters"]["symbols"] for symbol in portfolio_symbols)
                ]
                new_alerts.extend(portfolio_earnings_alerts)
                alert_categories.extend(["Earnings"] * len(portfolio_earnings_alerts))
        
        alert_progress.progress(1.0, text="Alert detection completed!")
        
        # Clear placeholders
        alert_progress.empty()
        alert_status.empty()
        
        # Display results
        if new_alerts:
            st.success(f"🎉 Found {len(new_alerts)} new alerts for your portfolio!")
            
            # Alert summary metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                grade_count = alert_categories.count("Grade Changes")
                st.metric("📊 Grade Changes", grade_count)
            with col2:
                price_count = alert_categories.count("Price Targets")
                st.metric("💰 Price Targets", price_count)
            with col3:
                earnings_count = alert_categories.count("Earnings")
                st.metric("📈 Earnings", earnings_count)
            with col4:
                st.metric("🔔 Total Alerts", len(new_alerts))
            
            # Detailed alerts display
            st.markdown("#### 📋 Recent Alerts Details")
            
            for i, alert in enumerate(new_alerts[:10]):  # Show top 10 alerts
                with st.expander(f"🔔 {alert.get('alert_name', 'Unknown Alert')} - {alert.get('created_at', 'Unknown Date')}"):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.write(f"**Type:** {alert.get('alert_type', 'Unknown')}")
                        st.write(f"**Priority:** {alert.get('priority_level', 3)}")
                        st.write(f"**Created:** {alert.get('created_at', 'Unknown')}")
                        
                        # Show affected symbols
                        symbols = alert.get("entity_filters", {}).get("symbols", [])
                        if symbols:
                            st.write(f"**Symbols:** {', '.join(symbols)}")
                        
                        # Show alert details if available
                        if alert.get("event_data"):
                            st.write("**Details:**")
                            st.json(alert["event_data"])
                    
                    with col2:
                        # Alert action buttons
                        if st.button(f"👁️ View Details", key=f"view_alert_{i}"):
                            st.info(f"Alert ID: {alert.get('id', 'Unknown')}")
                        
                        if st.button(f"🔕 Dismiss", key=f"dismiss_alert_{i}"):
                            st.success("Alert dismissed")
            
            if len(new_alerts) > 10:
                st.info(f"📝 Showing 10 of {len(new_alerts)} alerts. Check the Universal Alerts dashboard for complete list.")
            
        else:
            st.info("🔍 No new alerts found for your portfolio symbols.")
            st.write("This could mean:")
            st.write("- No recent analyst actions on your portfolio symbols")
            st.write("- Alerts may be older than the detection window")
            st.write("- Consider checking the Universal Alerts dashboard directly")
        
        return {
            "success": True,
            "new_alerts_count": len(new_alerts),
            "alert_categories": alert_categories,
            "alerts": new_alerts
        }
        
    except Exception as e:
        st.error(f"❌ Error detecting alerts: {e}")
        return {
            "success": False,
            "error": str(e),
            "new_alerts_count": 0
        }

def get_portfolio_data_coverage(portfolio_id: str):
    try:
        symbols = resolve_portfolio_symbols(portfolio_id)
        if not symbols:
            return None
        
        # Check data availability for each symbol
        data_types = ['price_historical', 'indicators', 'fundamentals', 'grades', 'earnings']
        
        symbol_details = []
        data_type_coverage = {}
        
        # Initialize data type coverage
        for data_type in data_types:
            data_type_coverage[data_type] = {
                'symbols_with_data': 0,
                'symbols_missing_data': 0,
                'missing_symbols': [],
                'coverage_percentage': 0
            }
        
        for symbol in symbols:
            # Get symbol data coverage
            try:
                # Go API proxy endpoint so Streamlit only talks to Go
                response = go_client.get(f"api/v1/stocks/{symbol}/coverage")
                if response.get("success", False):
                    coverage = response["data"]
                    
                    symbol_data_types = {}
                    missing_data_types = []
                    
                    for data_type in data_types:
                        has_data = coverage.get(f'has_{data_type}_data', False)
                        symbol_data_types[data_type] = has_data
                        
                        if has_data:
                            data_type_coverage[data_type]['symbols_with_data'] += 1
                        else:
                            data_type_coverage[data_type]['symbols_missing_data'] += 1
                            data_type_coverage[data_type]['missing_symbols'].append(symbol)
                            missing_data_types.append(data_type)
                    
                    # Calculate data completeness
                    data_completeness = (sum(symbol_data_types.values()) / len(data_types)) * 100
                    
                    symbol_details.append({
                        'symbol': symbol,
                        'data_types': symbol_data_types,
                        'missing_data_types': missing_data_types,
                        'data_completeness': data_completeness
                    })
                else:
                    # Symbol not found or error
                    symbol_data_types = {dt: False for dt in data_types}
                    missing_data_types = data_types.copy()
                    
                    for data_type in data_types:
                        data_type_coverage[data_type]['symbols_missing_data'] += 1
                        data_type_coverage[data_type]['missing_symbols'].append(symbol)
                    
                    symbol_details.append({
                        'symbol': symbol,
                        'data_types': symbol_data_types,
                        'missing_data_types': missing_data_types,
                        'data_completeness': 0
                    })
            except Exception:
                # Error checking coverage
                symbol_data_types = {dt: False for dt in data_types}
                missing_data_types = data_types.copy()
                
                for data_type in data_types:
                    data_type_coverage[data_type]['symbols_missing_data'] += 1
                    data_type_coverage[data_type]['missing_symbols'].append(symbol)
                
                symbol_details.append({
                    'symbol': symbol,
                    'data_types': symbol_data_types,
                    'missing_data_types': missing_data_types,
                    'data_completeness': 0
                })
        
        # Calculate coverage percentages
        for data_type in data_types:
            total_symbols = len(symbols)
            symbols_with_data = data_type_coverage[data_type]['symbols_with_data']
            data_type_coverage[data_type]['coverage_percentage'] = (symbols_with_data / total_symbols) * 100 if total_symbols > 0 else 0
        
        # Calculate portfolio-level metrics
        symbols_with_complete_data = sum(1 for s in symbol_details if s['data_completeness'] >= 90)
        symbols_with_missing_data = len(symbol_details) - symbols_with_complete_data
        
        # Get portfolio missing data types
        portfolio_missing_data_types = []
        for data_type in data_types:
            if data_type_coverage[data_type]['symbols_missing_data'] > 0:
                portfolio_missing_data_types.append(data_type)
        
        return {
            'total_symbols': len(symbols),
            'symbols_with_complete_data': symbols_with_complete_data,
            'symbols_with_missing_data': symbols_with_missing_data,
            'data_type_coverage': data_type_coverage,
            'symbol_details': symbol_details,
            'portfolio_missing_data_types': portfolio_missing_data_types
        }
        
    except Exception as e:
        st.error(f"Error analyzing portfolio coverage: {e}")
        return None

def load_portfolio_data_type(portfolio_id: str, data_type: str, force_refresh: bool = False):
    """Load specific data type for portfolio symbols"""
    try:
        symbols = resolve_portfolio_symbols(portfolio_id)
        if not symbols:
            st.error("No symbols found for this portfolio")
            return

        data_types = _normalize_data_load_types([data_type])
        if not data_types:
            st.error(f"Unsupported data type for data-load: {data_type}")
            return

        with st.spinner(f"Starting data load run for {data_type} ({len(symbols)} symbols)..."):
            resp = create_portfolio_data_load_run(portfolio_id, symbols, data_types, force=force_refresh)
            if resp and resp.get("success"):
                st.success(f"✅ Run started: {resp.get('run_id')}")
                st.info("See 'Data Loading Audit Trail' below for status and events.")
            else:
                st.error(resp.get("error") if isinstance(resp, dict) else "Failed to start data-load run")

    except Exception as e:
        st.error(f"Error loading portfolio data: {e}")

def load_portfolio_data_types(portfolio_id: str, data_types: List[str], force_refresh: bool = False):
    """Load multiple data types for portfolio symbols"""
    try:
        symbols = resolve_portfolio_symbols(portfolio_id)
        if not symbols:
            st.error("No symbols found for this portfolio")
            return

        normalized = _normalize_data_load_types(data_types)
        if not normalized:
            st.error("No supported data types selected for data-load")
            return

        with st.spinner(f"Starting data load run ({len(symbols)} symbols, {len(normalized)} data types)..."):
            resp = create_portfolio_data_load_run(portfolio_id, symbols, normalized, force=force_refresh)
            if resp and resp.get("success"):
                st.success(f"✅ Run started: {resp.get('run_id')}")
                st.info("See 'Data Loading Audit Trail' below for status and events.")
            else:
                st.error(resp.get("error") if isinstance(resp, dict) else "Failed to start data-load run")

    except Exception as e:
        st.error(f"Error loading portfolio data: {e}")

def load_symbol_missing_data(symbol: str, missing_data_types: List[str], force_refresh: bool = False):
    """Load missing data types for a specific symbol"""
    try:
        portfolio_id = st.session_state.get("portfolio_selection")
        if not portfolio_id:
            st.error("Select a portfolio above to run a data load")
            return

        normalized = _normalize_data_load_types(missing_data_types)
        if not normalized:
            st.error("No supported missing data types to load")
            return

        with st.spinner(f"Starting data load run for {symbol}..."):
            resp = create_portfolio_data_load_run(portfolio_id, [symbol], normalized, force=force_refresh)
            if resp and resp.get("success"):
                st.success(f"✅ Run started: {resp.get('run_id')}")
                st.info("See 'Data Loading Audit Trail' below for status and events.")
                st.rerun()
            else:
                st.error(resp.get("error") if isinstance(resp, dict) else "Failed to start data-load run")
    
    except Exception as e:
        st.error(f"Error loading symbol data: {e}")

def refresh_symbol_all_data(symbol: str, force_refresh: bool = False):
    """Refresh all data for a specific symbol"""
    try:
        all_data_types = ["price_historical", "indicators", "fundamentals", "earnings"]

        portfolio_id = st.session_state.get("portfolio_selection")
        if not portfolio_id:
            st.error("Select a portfolio above to run a data load")
            return

        normalized = _normalize_data_load_types(all_data_types)
        if not normalized:
            st.error("No supported data types to refresh")
            return

        with st.spinner(f"Starting data load run for {symbol}..."):
            resp = create_portfolio_data_load_run(portfolio_id, [symbol], normalized, force=force_refresh)
            if resp and resp.get("success"):
                st.success(f"✅ Run started: {resp.get('run_id')}")
                st.info("See 'Data Loading Audit Trail' below for status and events.")
                st.rerun()
            else:
                st.error(resp.get("error") if isinstance(resp, dict) else "Failed to start data-load run")
    
    except Exception as e:
        st.error(f"Error refreshing symbol data: {e}")

def load_data_for_portfolio_stocks(symbols: List[str], data_types: List[str], force_refresh: bool = False, 
                                  progress_placeholder=None, status_placeholder=None):
    """Load data for portfolio symbols using the correct API endpoints with rate limiting"""
    try:
        # Use the same logic as load_data_for_all_stocks but for portfolio symbols
        results = {
            "success": True,
            "data": {},
            "symbols_loaded": 0,
            "data_types": data_types,
            "errors": [],
            "api_calls_made": [],
            "rate_limit_info": {
                "calls_per_minute_limit": 200,
                "total_calls_planned": 0,
                "estimated_time_minutes": 0
            }
        }
        
        # Calculate rate limiting info
        total_calls = len(symbols) * len(data_types)
        results["rate_limit_info"]["total_calls_planned"] = total_calls
        results["rate_limit_info"]["estimated_time_minutes"] = max(1, (total_calls / 180))
        
        # Rate limiting: 200 calls per minute = ~3.33 calls per second
        call_delay = 0.34  # seconds between calls
        calls_in_current_minute = 0
        minute_start_time = time.time()
        
        total_operations = len(symbols) * len(data_types)
        completed_operations = 0
        
        for symbol_idx, symbol in enumerate(symbols):
            symbol_results = {}
            
            for data_type_idx, data_type in enumerate(data_types):
                try:
                    # Update progress
                    completed_operations += 1
                    progress_percentage = completed_operations / total_operations
                    current_symbol = f"{symbol} - {data_type}"
                    
                    if progress_placeholder:
                        progress_placeholder.progress(progress_percentage, text=f"Loading {current_symbol}...")
                    
                    if status_placeholder:
                        status_placeholder.write(f"**Current:** {current_symbol} ({completed_operations}/{total_operations})")
                    
                    # Check rate limiting
                    current_time = time.time()
                    if current_time - minute_start_time >= 60:
                        # Reset minute counter
                        calls_in_current_minute = 0
                        minute_start_time = current_time
                    
                    if calls_in_current_minute >= 180:  # Leave buffer for other calls
                        # Wait until next minute
                        wait_time = 60 - (current_time - minute_start_time)
                        if wait_time > 0:
                            if status_placeholder:
                                status_placeholder.write(f"**Rate limit reached - waiting {wait_time:.0f}s...**")
                            time.sleep(wait_time)
                            calls_in_current_minute = 0
                            minute_start_time = current_time
                    
                    # Check if data already exists (unless force refresh)
                    if not force_refresh:
                        try:
                            coverage_response = python_client.get(f"api/v1/stocks/{symbol}/coverage")
                            if coverage_response.get("success", False):
                                coverage = coverage_response["data"]
                                if coverage.get(f'has_{data_type}_data', False):
                                    if status_placeholder:
                                        status_placeholder.write(f"**Skipping {current_symbol} - data already exists**")
                                    calls_in_current_minute += 1
                                    symbol_results[data_type] = "skipped_existing"
                                    continue
                        except:
                            pass  # Proceed with loading if coverage check fails
                    
                    # Load data based on type
                    if status_placeholder:
                        status_placeholder.write(f"**Loading {current_symbol}...**")
                    
                    if data_type == "price_historical":
                        # Use price data loading endpoint
                        load_response = python_client.post(f"refresh/price-data/{symbol}")
                    elif data_type == "indicators":
                        # Use indicators loading endpoint
                        load_response = python_client.post(f"refresh/indicators/{symbol}")
                    elif data_type == "fundamentals":
                        # Use fundamentals loading endpoint
                        load_response = python_client.post(f"refresh/fundamentals/{symbol}")
                    elif data_type == "grades":
                        # Use stock grades loading endpoint
                        load_response = python_client.post(f"refresh/stock-grades/{symbol}")
                    elif data_type == "earnings":
                        # Use earnings loading endpoint
                        load_response = python_client.post(f"refresh/earnings/{symbol}")
                    else:
                        # Unknown data type
                        st.warning(f"Unknown data type: {data_type}")
                        continue
                    
                    calls_in_current_minute += 1
                    results["api_calls_made"].append(f"{symbol}_{data_type}")
                    
                    # Add delay between calls
                    if data_type_idx < len(data_types) - 1 or symbol_idx < len(symbols) - 1:
                        time.sleep(call_delay)
                    
                    symbol_results[data_type] = "loading_initiated"
                    
                except Exception as e:
                    error_msg = f"Failed to load {data_type} for {symbol}: {str(e)}"
                    results["errors"].append(error_msg)
                    symbol_results[data_type] = f"error: {str(e)}"
            
            results["data"][symbol] = symbol_results
            results["symbols_loaded"] += 1
        
        # Final progress update
        if progress_placeholder:
            progress_placeholder.progress(1.0, text="Data loading completed!")
        
        if status_placeholder:
            status_placeholder.write(f"**✅ Completed {results['symbols_loaded']} symbols with {len(results['data_types'])} data types**")
        
        return results
    
    except Exception as e:
        if progress_placeholder:
            progress_placeholder.empty()
        if status_placeholder:
            status_placeholder.empty()
        
        return {
            "success": False,
            "error": str(e),
            "symbols_loaded": 0,
            "data_types": data_types
        }

def analyze_portfolio_data_coverage(portfolio_id: str):
    """Analyze and display portfolio data coverage"""
    try:
        portfolio_coverage = get_portfolio_data_coverage(portfolio_id)
        
        if portfolio_coverage:
            st.success("✅ Portfolio analysis complete!")
            
            # Display comprehensive analysis
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📋 Total Symbols", portfolio_coverage['total_symbols'])
            with col2:
                st.metric("✅ Complete Data", portfolio_coverage['symbols_with_complete_data'])
            with col3:
                coverage_pct = (portfolio_coverage['symbols_with_complete_data'] / portfolio_coverage['total_symbols'] * 100) if portfolio_coverage['total_symbols'] > 0 else 0
                st.metric("📈 Coverage", f"{coverage_pct:.1f}%")
            with col4:
                st.metric("⚠️ Need Data", portfolio_coverage['symbols_with_missing_data'])
            
            # Data type breakdown
            st.markdown("#### 📊 Data Type Analysis")
            for data_type, coverage in portfolio_coverage['data_type_coverage'].items():
                st.write(f"**{data_type.title()}**: {coverage['coverage_percentage']:.1f}% ({coverage['symbols_with_data']}/{portfolio_coverage['total_symbols']} symbols)")
            
            # Missing symbols by data type
            for data_type, coverage in portfolio_coverage['data_type_coverage'].items():
                if coverage['missing_symbols']:
                    with st.expander(f"❌ {data_type.title()} - Missing {len(coverage['missing_symbols'])} symbols"):
                        st.write(", ".join(coverage['missing_symbols'][:20]))
                        if len(coverage['missing_symbols']) > 20:
                            st.write(f"... and {len(coverage['missing_symbols']) - 20} more")
        else:
            st.error("Could not analyze portfolio coverage")
    
    except Exception as e:
        st.error(f"Error analyzing portfolio: {e}")

def get_portfolio_symbol_data_availability(portfolio_id: str, selected_date):
    """Get symbol data availability for portfolio on specific date"""
    try:
        portfolio_details = get_portfolio_details(portfolio_id)
        if not portfolio_details:
            return []
        
        symbols = portfolio_details['symbols']
        symbol_status = []
        
        for symbol in symbols:
            try:
                # Get symbol availability for the date
                # This would use the existing get_symbol_data_availability function
                # TODO: Implement actual data availability check
                st.warning(f"🔧 **Feature Not Implemented**: Symbol availability check for {symbol} on {date}")
                continue
            except:
                continue
        
        return []
    
    except Exception as e:
        st.error(f"Error getting portfolio symbol availability: {e}")
        return []

def load_data_for_all_stocks(data_types: List[str], force_refresh: bool = False):
    """Load data for all symbols using the correct API endpoints with rate limiting"""
    try:
        # Use the same stock grades API as the Analyst Ratings
        results = {
            "success": True,
            "data": {},
            "symbols_loaded": 0,
            "data_types": data_types,
            "errors": [],
            "api_calls_made": [],
            "rate_limit_info": {
                "calls_per_minute_limit": 200,
                "total_calls_planned": 0,
                "estimated_time_minutes": 0
            }
        }
        
        # Get a list of major symbols to load (same as Analyst Ratings)
        symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "META", "NVDA", "JPM", "JNJ", "V"]
        
        # Calculate rate limiting info
        total_calls = len(symbols) * len(data_types)
        results["rate_limit_info"]["total_calls_planned"] = total_calls
        results["rate_limit_info"]["estimated_time_minutes"] = max(1, (total_calls / 180))  # Use 180 to be safe
        
        # Rate limiting: 200 calls per minute = ~3.33 calls per second
        # We'll use 3 calls per second to be safe (1 call every 0.33 seconds)
        call_delay = 0.34  # seconds between calls
        calls_in_current_minute = 0
        minute_start_time = time.time()
        
        for symbol_idx, symbol in enumerate(symbols):
            symbol_results = {}
            
            for data_type_idx, data_type in enumerate(data_types):
                try:
                    # Check rate limiting
                    current_time = time.time()
                    if current_time - minute_start_time >= 60:
                        # Reset minute counter
                        calls_in_current_minute = 0
                        minute_start_time = current_time
                    
                    if calls_in_current_minute >= 180:  # Leave buffer for other calls
                        # Wait until next minute
                        wait_time = 60 - (current_time - minute_start_time)
                        if wait_time > 0:
                            time.sleep(wait_time)
                            calls_in_current_minute = 0
                            minute_start_time = time.time()
                    
                    # Small delay between calls to prevent bursting
                    if symbol_idx > 0 or data_type_idx > 0:
                        time.sleep(call_delay)
                    
                    calls_in_current_minute += 1
                    
                    # === ANALYST & GRADING DATA (use /api/v1/grades/ endpoints) ===
                    if data_type in ["stock_grades", "consensus_data", "price_targets", "analyst_ratings"]:
                        # Use the correct stock grades API endpoints
                        if data_type == "stock_grades":
                            endpoint = f"api/v1/grades/refresh/{symbol}"
                        elif data_type == "consensus_data":
                            endpoint = f"api/v1/grades/update-consensus/{symbol}"
                        elif data_type == "price_targets":
                            # Price targets are part of stock grades, use the same refresh
                            endpoint = f"api/v1/grades/refresh/{symbol}"
                        elif data_type == "analyst_ratings":
                            # Analyst ratings are also part of stock grades
                            endpoint = f"api/v1/grades/refresh/{symbol}"
                        
                        # Log the API call for debugging
                        api_call_log = f"POST {endpoint} for {symbol} (call #{len(results['api_calls_made']) + 1})"
                        results["api_calls_made"].append(api_call_log)
                        
                        refresh_response = python_client.post(endpoint)
                        
                        if refresh_response and refresh_response.get('success'):
                            results_count = refresh_response.get('results', {}).get('grades_loaded', 0)
                            symbol_results[data_type] = {
                                "status": "success",
                                "message": f"Loaded {results_count} items for {symbol}",
                                "timestamp": datetime.now().isoformat()
                            }
                        else:
                            error_msg = refresh_response.get('message', 'Unknown error') if refresh_response else 'Failed to connect'
                            symbol_results[data_type] = {
                                "status": "error",
                                "message": error_msg,
                                "timestamp": datetime.now().isoformat()
                            }
                    
                    # === MARKET & FINANCIAL DATA (use /api/v1/refresh endpoint) ===
                    elif data_type in [
                        "price_historical", "price_current", "price_intraday_5m",
                        "fundamentals", "income_statements", "balance_sheets", "cash_flow_statements",
                        "indicators", "financial_ratios", "key_metrics_ttm", "financial_scores",
                        # === GROWTH METRICS (NEW) ===
                        "income_statement_growth", "balance_sheet_growth", "cash_flow_growth", "financial_growth",
                        "earnings", "earnings_transcripts", "news", "corporate_actions",
                        "industry_peers", "macro_market_data", "short_interest", "short_volume", 
                        "share_float", "risk_factors", "signals"
                    ]:
                        # Use the main refresh API for market and financial data
                        endpoint = "/api/v1/refresh"
                        payload = {
                            "symbols": [symbol],
                            "data_types": [data_type],
                            "force": force_refresh,
                        }
                        
                        # Log the API call for debugging
                        api_call_log = f"POST {endpoint} for {symbol} - {data_type} (call #{len(results['api_calls_made']) + 1})"
                        results["api_calls_made"].append(api_call_log)
                        
                        refresh_response = python_client.post(
                            endpoint,
                            json_data=payload,
                            timeout=300,
                        )
                        
                        if refresh_response and refresh_response.get('success'):
                            symbol_results[data_type] = {
                                "status": "success",
                                "message": f"Refreshed {data_type} for {symbol}",
                                "timestamp": datetime.now().isoformat()
                            }
                        else:
                            error_msg = refresh_response.get('message', 'Unknown error') if refresh_response else 'Failed to connect'
                            symbol_results[data_type] = {
                                "status": "error",
                                "message": error_msg,
                                "timestamp": datetime.now().isoformat()
                            }
                    
                    # === NOT YET IMPLEMENTED ===
                    else:
                        symbol_results[data_type] = {
                            "status": "skipped",
                            "message": f"Data type '{data_type}' not yet implemented",
                            "timestamp": datetime.now().isoformat()
                        }
                        
                except Exception as e:
                    symbol_results[data_type] = {
                        "status": "error",
                        "message": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                    results["errors"].append(f"Error with {data_type} for {symbol}: {str(e)}")
            
            results["data"][symbol] = symbol_results
        
        results["symbols_loaded"] = len(symbols)
        
        return results
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_data_loading_audit_data():
    """Get comprehensive data loading audit data using python-worker admin endpoints"""
    try:
        audit_data = {
            "last_data_collection": None,
            "data_collection_status": "unknown",
            "data_sources": {},
            "recent_collections": [],
            "failed_collections": [],
            "data_freshness": {},
            "collection_stats": {
                "total_collections_today": 0,
                "successful_collections": 0,
                "failed_collections": 0
            },
            "available_tables": [
                # === MARKET DATA ===
                "raw_market_data_daily",
                "raw_market_data_intraday",
                
                # === FINANCIAL STATEMENTS ===
                "fundamentals_snapshots",
                "income_statements", 
                "balance_sheets",
                "cash_flow_statements",
                
                # === FINANCIAL METRICS ===
                "indicators_daily",
                "financial_ratios",
                
                # === ANALYST & GRADING DATA ===
                "stock_grades",
                "stock_consensus_history",
                
                # === EARNINGS DATA ===
                "earnings_data",
                "earnings_transcripts",
                
                # === NEWS & EVENTS ===
                "market_news",
                "corporate_actions",
                
                # === REFERENCE DATA ===
                "industry_peers",
                "macro_market_data",
                
                # === SYSTEM DATA ===
                "data_ingestion_events",
                "share_float",
                "risk_factors",
                "short_interest",
                "short_volume"
            ]
        }

        hours = 24
        summary = python_client.get("admin/data-loading-summary", params={"hours": hours})
        if isinstance(summary, dict) and summary.get("success"):
            runs = summary.get("runs_summary", []) or []
            total_runs = sum(int(r.get("count") or 0) for r in runs)
            success_runs = sum(int(r.get("count") or 0) for r in runs if (r.get("status") or "").lower() in {"success", "completed", "ok"})
            failed_runs = total_runs - success_runs

            audit_data["collection_stats"]["total_collections_today"] = total_runs
            audit_data["collection_stats"]["successful_collections"] = success_runs
            audit_data["collection_stats"]["failed_collections"] = failed_runs

            events = summary.get("events_summary", []) or []
            for ev in events[:15]:
                audit_data["recent_collections"].append({
                    "timestamp": summary.get("generated_at"),
                    "data_type": ev.get("operation"),
                    "symbol": ev.get("symbol"),
                    "status": "failed" if (ev.get("error_count") or 0) else "success",
                    "records_count": ev.get("total_records_saved") or ev.get("total_records_processed"),
                    "provider": ev.get("provider")
                })

            audit_data["data_collection_status"] = "healthy"
            audit_data["last_data_collection"] = summary.get("generated_at")

        core_tables = [
            "raw_market_data_daily",
            "raw_market_data_intraday",
            "indicators_daily",
            "fundamentals_snapshots",
            "market_news",
            "earnings_data",
            "stock_grades",
            "stock_consensus_history",
            "rating_change_log",
        ]

        for t in core_tables:
            try:
                t_summary = python_client.get(f"admin/data-summary/{t}")
                if isinstance(t_summary, dict) and t_summary.get("total_records") is not None:
                    audit_data["data_sources"][t] = {
                        "name": t,
                        "status": "active",
                        "last_update": t_summary.get("last_updated"),
                        "records_today": t_summary.get("today_records"),
                        "total_records": t_summary.get("total_records"),
                    }
            except Exception:
                continue
        
        return audit_data
        
    except Exception as e:
        st.error(f"❌ **Data Loading Audit Failed**: {str(e)}")
        st.error("🔧 **Technical Issue**: Unable to connect to data loading audit service")
        return None  # Return None to indicate failure, not fallback data

def get_provider_distribution_status(selected_date):
    """Get universal provider distribution status for all data sources"""
    try:
        response = python_client.get(f"api/v1/audit/provider-distribution/{selected_date}")

        if isinstance(response, dict) and "total_records" in response:
            return response

        if isinstance(response, dict) and response.get("success", False) and response.get("data"):
            return response["data"]

        error_msg = response.get("error", "Unknown API error") if isinstance(response, dict) else "Unexpected response"
        st.error(f"❌ **Provider Distribution API Error**: {error_msg}")
        st.error(f"🔧 **Technical Issue**: Unable to get provider distribution for {selected_date}")
        return None  # Return None to indicate failure
    except Exception as e:
        st.error(f"❌ **Provider Distribution Loading Failed**: {str(e)}")
        st.error(f"🔧 **Technical Issue**: Unable to connect to audit service for {selected_date}")
        return None  # Return None to indicate failure


def get_detailed_audit_records(selected_date, show_only_errors: bool, show_only_primary: bool, limit: int):
    """Get detailed audit records for a date with filters."""
    try:
        params = {
            "show_only_errors": show_only_errors,
            "show_only_primary": show_only_primary,
            "limit": limit,
        }

        response = python_client.get(f"api/v1/audit/audit-records/{selected_date}", params=params)

        if isinstance(response, list):
            return response

        if isinstance(response, dict):
            if response.get("success") and isinstance(response.get("data"), list):
                return response.get("data")
            if isinstance(response.get("records"), list):
                return response.get("records")

        return []
    except Exception as e:
        st.error(f"❌ **Audit Records Loading Failed**: {str(e)}")
        return []

def get_fmp_api_audit_status(selected_date):
    """Get FMP API integration status for selected date"""
    try:
        response = python_client.get(f"api/v1/audit/fmp-status/{selected_date}")

        if isinstance(response, dict) and "total_records" in response:
            return response

        if isinstance(response, dict) and response.get("success", False) and response.get("data"):
            return response["data"]

        error_msg = response.get("error", "Unknown API error") if isinstance(response, dict) else "Unexpected response"
        st.error(f"❌ **FMP API Status Error**: {error_msg}")
        st.error(f"🔧 **Technical Issue**: Unable to get FMP API status for {selected_date}")
        return None  # Return None to indicate failure
    except Exception as e:
        st.error(f"❌ **FMP API Status Loading Failed**: {str(e)}")
        st.error(f"🔧 **Technical Issue**: Unable to connect to FMP audit service for {selected_date}")
        return None  # Return None to indicate failure

# Enhanced portfolio functions with Universal Alerts API integration

def show_executive_dashboard():
    """Executive overview dashboard"""
    st.markdown("## 📊 Market Overview")
    st.markdown("*Actionable analyst + price target changes and data freshness for your watchlist/portfolio.*")

    health = get_system_health()
    data_audit = get_data_loading_audit_data()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        api_status = (health or {}).get("api_health", {}).get("status", "unknown")
        status_color = "🟢" if api_status == "healthy" else "🔴"
        st.metric(f"{status_color} API", api_status.title())
    with col2:
        db_status = (health or {}).get("database_health", {}).get("status", "unknown")
        status_color = "🟢" if db_status == "healthy" else "🔴"
        st.metric(f"{status_color} DB", db_status.title())
    with col3:
        last_updated = None
        if data_audit and data_audit.get("data_sources"):
            last_updated = (data_audit.get("data_sources", {}).get("raw_market_data_intraday") or {}).get("last_update")
        st.metric("Intraday Last Update", str(last_updated) if last_updated else "-")
    with col4:
        last_pt = None
        if data_audit and data_audit.get("data_sources"):
            last_pt = (data_audit.get("data_sources", {}).get("rating_change_log") or {}).get("last_update")
        st.metric("PT Log Last Update", str(last_pt) if last_pt else "-")

    st.markdown("---")
    show_market_day_analyst_moves()

    st.markdown("---")
    show_price_target_changes_dashboard()

def show_operations_dashboard():
    """Operations monitoring dashboard"""
    st.markdown("## ⚙️ Operations Dashboard")
    st.markdown("*Real-time system monitoring for operations team*")
    
    # System Health Details
    health = get_system_health()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🏥 System Health")
        
        if health:
            health_items = [
                ("API", health.get("api_health", {}).get("status", "unknown"), health.get("api_health", {}).get("response_time")),
                ("Database", health.get("database_health", {}).get("status", "unknown"), health.get("database_health", {}).get("response_time")),
                ("Scheduler", health.get("scheduler_health", {}).get("status", "unknown"), None),
            ]
            
            for name, status, response_time in health_items:
                status_icon = "🟢" if status == "healthy" else "🔴"
                st.write(f"{status_icon} **{name}**: {status.title()}")
                if response_time:
                    st.write(f"   Response time: {response_time:.0f}ms")
        else:
            st.error("🔴 **System Health Unavailable**")
            st.error("🔧 **Technical Issue**: Unable to connect to health monitoring service")
    
    with col2:
        st.markdown("### 📊 Alert Statistics")
        
        alert_audit = get_alert_audit_data()
        
        if alert_audit:
            stats_items = [
                ("Total Alerts", alert_audit.get("total_alerts", 0), "📊"),
                ("Active Alerts", alert_audit.get("active_alerts", 0), "✅"),
                ("Alerts w/ Symbols", alert_audit.get("total_alerts", 0) - alert_audit.get("alerts_with_no_symbols", 0), "🎯"),
                ("Alerts w/o Symbols", alert_audit.get("alerts_with_no_symbols", 0), "⚠️"),
            ]
            
            for label, value, icon in stats_items:
                st.metric(f"{icon} {label}", value)
        else:
            st.error("🔴 **Alert Statistics Unavailable**")
            st.error("🔧 **Technical Issue**: Unable to connect to alert audit service")
    
    with col3:
        st.markdown("### 📧 Notification Status")
        
        notification_data = get_notification_audit_data()
        
        if notification_data:
            pending_backlog = int(notification_data.get("pending_backlog") or 0)
            failed_backlog = int(notification_data.get("failed_backlog") or 0)

            st.metric("Pending backlog", pending_backlog)
            st.metric("Failed (window)", failed_backlog)

            for channel, count in (notification_data.get("counts_by_channel") or {}).items():
                icon = {"email": "📧", "sms": "📱", "push": "🔔", "webhook": "🔗"}.get(channel, "📢")
                delivery_rate = (notification_data.get("delivery_rates") or {}).get(channel, 0)
                st.metric(f"{icon} {channel.title()}", f"{count}", f"{delivery_rate:.0%} sent/(sent+failed)")
        else:
            st.error("🔴 **Notification Status Unavailable**")
            st.error("🔧 **Technical Issue**: Unable to connect to notification audit service")
    
    st.markdown("---")
    
    # Data Loading Monitor
    st.markdown("### 🔄 Data Loading Monitor")
    
    data_data = get_data_loading_audit_data()
    
    if data_data:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Collection Status")
            
            for source_key, source_info in data_data.get("data_sources", {}).items():
                status = source_info.get("status", "unknown")
                status_icon = {"healthy": "🟢", "warning": "🟡", "error": "🔴"}.get(status, "⚪")
                st.write(f"{status_icon} **{source_info.get('name', source_key)}**: {status.title()}")
            
            st.markdown("#### Today's Collections")
            stats = data_data.get("collection_stats", {})
            st.write(f"Total: {stats.get('total_collections_today', 0)}")
            st.write(f"Success: {stats.get('successful_collections', 0)}")
            st.write(f"Failed: {stats.get('failed_collections', 0)}")
        
        with col2:
            st.markdown("#### Recent Collections")
            
            if data_data.get("recent_collections"):
                df_collections = pd.DataFrame(data_data["recent_collections"])
                st.dataframe(df_collections, width='stretch')
            else:
                st.info("No recent data collections found")
    else:
        st.error("🔴 **Data Loading Monitor Unavailable**")
        st.error("🔧 **Technical Issue**: Unable to connect to data loading audit service")

    st.markdown("---")
    st.markdown("### 🗓️ Scheduler Controls (Admin)")

    scheduler = ua_admin_call("GET", "scheduler/status")
    if not scheduler.get("success"):
        st.error(scheduler.get("error") or "Failed to load scheduler status")
    else:
        status = scheduler.get("status", {})
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        with col_s1:
            st.metric("Running", "Yes" if status.get("is_running") else "No")
        with col_s2:
            st.metric("Active Jobs", status.get("active_jobs", 0))
        with col_s3:
            st.metric("Executions (1h)", status.get("executions_last_hour", 0))
        with col_s4:
            st.metric("Success Rate", f"{status.get('success_rate', 0):.0f}%")

        st.write(f"**Last execution:** {status.get('last_execution')}")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("▶️ Start", key="sched_start"):
                st.json(ua_admin_call("POST", "scheduler/start"))
        with b2:
            if st.button("⏹ Stop", key="sched_stop"):
                st.json(ua_admin_call("POST", "scheduler/stop"))
        with b3:
            if st.button("🔄 Restart", key="sched_restart"):
                st.json(ua_admin_call("POST", "scheduler/restart"))

def show_audit_trail_dashboard():
    """Comprehensive audit trail dashboard"""
    st.markdown("## 🔍 Audit Trail Dashboard")
    st.markdown("*Detailed audit logs and system activity tracking*")
    
    # Alert Audit Data
    alert_audit = get_alert_audit_data()
    
    # Filters
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        date_range = st.date_input("Date Range", [datetime.now() - timedelta(days=7), datetime.now()])
    
    with col2:
        entity_filter = st.selectbox("Entity Type", ["All", "alert", "notification", "data_collection"])
    
    with col3:
        status_filter = st.selectbox("Status", ["All", "success", "failed", "warning"])
    
    with col4:
        if st.button("🔄 Refresh Audit Data"):
            st.rerun()
    
    st.markdown("---")
    
    # Alert Creation Audit
    st.markdown("### 📋 Alert Creation Audit")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Recent Alert Creations")
        
        recent_creations = alert_audit["recent_creations"]
        if recent_creations:
            df_creations = pd.DataFrame(recent_creations)
            df_creations['created_at'] = pd.to_datetime(df_creations['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
            st.dataframe(df_creations[['alert_name', 'alert_type', 'created_at', 'symbols']], width='stretch')
        else:
            st.info("No recent alert creations")


    
    with col2:
        st.markdown("#### Recent Alert Modifications")
        
        recent_mods = alert_audit["recent_modifications"]
        if recent_mods:
            df_mods = pd.DataFrame(recent_mods)
            df_mods['updated_at'] = pd.to_datetime(df_mods['updated_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
            st.dataframe(df_mods[['alert_name', 'alert_type', 'updated_at', 'symbols']], width='stretch')
        else:
            st.info("No recent alert modifications")
    
    st.markdown("---")
    
    # Symbol Coverage Audit
    st.markdown("### 🎯 Symbol Coverage Audit")
    
    symbol_coverage = alert_audit["alert_symbols_coverage"]
    alerts_no_symbols = alert_audit["alerts_with_no_symbols"]
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("📊 Total Unique Symbols", len(symbol_coverage))
        st.metric("⚠️ Alerts w/ No Symbols", alerts_no_symbols)
        
        if symbol_coverage:
            # Symbol frequency distribution
            symbol_counts = list(symbol_coverage.values())
            fig = px.histogram(
                x=symbol_counts,
                nbins=20,
                title="Symbol Coverage Distribution"
            )
            fig.update_xaxes(title_text="Number of Alerts per Symbol")
            fig.update_yaxes(title_text="Number of Symbols")
            st.plotly_chart(fig, width='stretch')
    
    with col2:
        st.markdown("#### Symbol Coverage Details")
        
        if symbol_coverage:
            # Create coverage analysis
            coverage_df = pd.DataFrame([
                {"symbol": symbol, "alert_count": count}
                for symbol, count in sorted(symbol_coverage.items(), key=lambda x: x[1], reverse=True)[:20]
            ])
            
            st.dataframe(coverage_df, width='stretch')
        else:
            st.info("No symbol coverage data available")
    
    st.markdown("---")
    
    # Export functionality
    st.markdown("### 📥 Export Audit Data")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Export Alert Audit"):
            # Create comprehensive audit export
            audit_export = {
                "export_timestamp": datetime.now().isoformat(),
                "alert_audit": alert_audit,
                "notification_audit": get_notification_audit_data(),
                "data_audit": get_data_loading_audit_data(),
                "system_health": health
            }
            
            st.download_button(
                label="Download Complete Audit Report",
                data=json.dumps(audit_export, indent=2, default=str),
                file_name=f"comprehensive_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
    
    with col2:
        if st.button("📋 Export Alert List"):
            if alert_audit["recent_creations"]:
                df_export = pd.DataFrame(alert_audit["recent_creations"])
                csv_data = df_export.to_csv(index=False)
                st.download_button(
                    label="Download Alert List CSV",
                    data=csv_data,
                    file_name=f"alert_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
    
    with col3:
        if st.button("📈 Export Symbol Coverage"):
            if symbol_coverage:
                coverage_df = pd.DataFrame([
                    {"symbol": symbol, "alert_count": count}
                    for symbol, count in symbol_coverage.items()
                ])
                csv_data = coverage_df.to_csv(index=False)
                st.download_button(
                    label="Download Symbol Coverage CSV",
                    data=csv_data,
                    file_name=f"symbol_coverage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

def main():
    """Main dashboard application"""
    st.title("🛡️ Comprehensive Admin Dashboard")
    st.markdown("*Complete system monitoring and audit functionality*")
    
    # Sidebar utilities
    ensure_portfolio_login_ui()
    ensure_notification_email_ui()
    
    # Navigation
    dashboard_tabs = st.tabs([
        "🏢 Executive", 
        "⚙️ Operations", 
        "🔍 Audit Trail",
        "📧 Notifications",
        "🧵 Job Queue",
        "🔄 Data Loading Audit",
        "📊 Stocks Management",
        "🚨 Alert Data Monitoring"
    ])
    
    with dashboard_tabs[0]:
        show_executive_dashboard()
    
    with dashboard_tabs[1]:
        show_operations_dashboard()
    
    with dashboard_tabs[2]:
        show_audit_trail_dashboard()
    
    with dashboard_tabs[3]:
        st.markdown("## 📧 Notification Audit")
        st.markdown("*Email and notification delivery monitoring*")

        st.session_state.setdefault("notification_window_hours", 24)
        notification_window_hours = st.number_input(
            "Notification lookback (hours)",
            min_value=1,
            max_value=24 * 30,
            value=int(st.session_state.get("notification_window_hours") or 24),
            step=1,
            key="notification_window_hours",
        )
        # Note: the widget owns st.session_state["notification_window_hours"]. Do not assign to it post-instantiation.
        
        notification_data = get_notification_audit_data()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📊 Notification Statistics")
            
            st.metric("Pending backlog", int(notification_data.get("pending_backlog") or 0))
            st.metric("Failed (window)", int(notification_data.get("failed_backlog") or 0))
            st.metric("Sent (window)", int(notification_data.get("sent_count") or 0))

            for channel, count in (notification_data.get("counts_by_channel") or {}).items():
                delivery_rate = (notification_data.get("delivery_rates") or {}).get(channel, 0)
                st.metric(f"{channel.title()}", f"{count} queued", f"{delivery_rate:.0%} sent/(sent+failed)")
        
        with col2:
            st.markdown("### 📈 Delivery Performance")
            
            channels = list((notification_data.get("delivery_rates") or {}).keys())
            rates = list((notification_data.get("delivery_rates") or {}).values())

            df_rates = pd.DataFrame({"channel": channels, "rate": rates})
            fig = px.bar(
                df_rates,
                x="channel",
                y="rate",
                title="Notification Delivery Rates by Channel",
                labels={"channel": "Channel", "rate": "Delivery Rate"},
                color="rate",
                color_continuous_scale="RdYlGn",
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("### 📋 Recent Notifications")
        
        if notification_data.get("recent_notifications"):
            df_notifications = pd.DataFrame(notification_data.get("recent_notifications"))
            if "created_at" in df_notifications.columns:
                df_notifications['created_at'] = pd.to_datetime(df_notifications['created_at']).dt.strftime('%Y-%m-%d %H:%M')
            st.dataframe(df_notifications, width='stretch')
        else:
            st.info("No recent queue activity")

        st.markdown("### ❌ Recent Failures")

        if notification_data.get("failed_notifications"):
            df_failed = pd.DataFrame(notification_data.get("failed_notifications"))
            if "failed_at" in df_failed.columns:
                df_failed['failed_at'] = pd.to_datetime(df_failed['failed_at']).dt.strftime('%Y-%m-%d %H:%M')
            st.dataframe(df_failed, width='stretch')
        else:
            st.info("No failures found in recent queue items")
        
        st.markdown("---")
        show_on_demand_alert_pipeline()

    with dashboard_tabs[4]:
        show_job_queue_dashboard()
    
    with dashboard_tabs[5]:
        st.markdown("## 🔄 Portfolio-Based Data Loading Audit")
        st.markdown("*Intelligent data loading for portfolio holdings with audit capabilities*")
        
        # Portfolio Selection Section
        st.markdown("### 📂 Portfolio Selection")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            # Get available portfolios
            available_portfolios = get_available_portfolios()
            if available_portfolios:
                portfolio_options = {f"{p['name']} ({p['symbol_count']} symbols)": p['portfolio_id'] for p in available_portfolios}
                selected_portfolio_id = st.selectbox(
                    "Select Portfolio",
                    options=list(portfolio_options.keys()),
                    format_func=lambda x: x,
                    key="portfolio_selection"
                )
                
                # Get the actual portfolio ID
                actual_portfolio_id = portfolio_options[selected_portfolio_id]
                
                # Get portfolio details
                portfolio_details = get_portfolio_details(actual_portfolio_id)
                if portfolio_details:
                    st.info(f"📊 **Portfolio**: {portfolio_details['name']} | **Symbols**: {portfolio_details['symbol_count']} | **Type**: {portfolio_details.get('portfolio_type', 'N/A')}")
            else:
                st.warning("No portfolios found or access denied. Use the Portfolio Login in the sidebar.")
                portfolio_details = None
        
        with col2:
            st.markdown("**Data Loading Options**")
            force_refresh = st.checkbox("🔄 Force Refresh", value=False, 
                                      help="Load data even if already exists")
            load_missing_only = st.checkbox("🎯 Load Missing Only", value=True,
                                          help="Only load data types that are missing")
        
        with col3:
            st.markdown("**Quick Actions**")
            if st.button("🔍 Analyze Portfolio", key="analyze_portfolio"):
                if portfolio_details:
                    portfolio_id_for_calls = portfolio_details.get('portfolio_id') or portfolio_details.get('id')
                    if not portfolio_id_for_calls:
                        st.error("Portfolio ID missing from portfolio details")
                    else:
                        # Resolve symbols via Go API /api/v1/symbol-scope/resolve
                        symbols = resolve_portfolio_symbols(portfolio_id_for_calls)
                        analyze_portfolio_data_coverage(symbols)
            
            if st.button("📊 Refresh Portfolio", key="refresh_portfolio"):
                st.rerun()
        
        st.markdown("---")
        
        # Portfolio Data Coverage Analysis
        if portfolio_details:
            st.markdown("### 📊 Portfolio Data Coverage Analysis")
            
            # Get portfolio holdings with data coverage
            portfolio_id_for_calls = portfolio_details.get('portfolio_id') or portfolio_details.get('id')
            if not portfolio_id_for_calls:
                st.error("Portfolio ID missing from portfolio details")
                portfolio_coverage = None
            else:
                portfolio_coverage = get_portfolio_data_coverage(portfolio_id_for_calls)
            
            if portfolio_coverage:
                # Summary metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📋 Total Symbols", portfolio_coverage['total_symbols'])
                with col2:
                    complete_symbols = portfolio_coverage['symbols_with_complete_data']
                    st.metric("✅ Complete Data", complete_symbols)
                with col3:
                    coverage_pct = (complete_symbols / portfolio_coverage['total_symbols'] * 100) if portfolio_coverage['total_symbols'] > 0 else 0
                    st.metric("📈 Coverage", f"{coverage_pct:.1f}%")
                with col4:
                    missing_data_symbols = portfolio_coverage['symbols_with_missing_data']
                    st.metric("⚠️ Missing Data", missing_data_symbols)
                
                # Data type coverage breakdown
                st.markdown("#### 📈 Data Type Coverage")
                data_type_coverage = portfolio_coverage['data_type_coverage']
                
                for data_type, coverage_info in data_type_coverage.items():
                    with st.expander(f"📊 {data_type.title()} - {coverage_info['coverage_percentage']:.1f}% Coverage"):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            # Coverage progress bar
                            st.progress(coverage_info['coverage_percentage'] / 100)
                            st.write(f"**Symbols with data**: {coverage_info['symbols_with_data']}")
                            st.write(f"**Symbols missing**: {coverage_info['symbols_missing_data']}")
                            
                            # Missing symbols list
                            if coverage_info['missing_symbols']:
                                st.write("**Missing symbols**:")
                                for symbol in coverage_info['missing_symbols'][:10]:  # Show first 10
                                    st.write(f"  • {symbol}")
                                if len(coverage_info['missing_symbols']) > 10:
                                    st.write(f"  ... and {len(coverage_info['missing_symbols']) - 10} more")
                        
                        with col2:
                            # Action buttons
                            if coverage_info['symbols_missing_data'] > 0:
                                if st.button(f"🚀 Load {data_type}", key=f"load_{data_type}"):
                                    load_portfolio_data_type(portfolio_id_for_calls, data_type, force_refresh)
                            else:
                                st.success("✅ Complete")
                
                # Symbol-level detailed view
                st.markdown("#### 🎯 Symbol-Level Data Status")
                
                # Filter options
                col1, col2, col3 = st.columns(3)
                with col1:
                    filter_status = st.selectbox("Filter by Status", 
                                               ["All Symbols", "Missing Data Only", "Complete Data Only"])
                with col2:
                    sort_by = st.selectbox("Sort by", ["Symbol", "Coverage %", "Missing Count"])
                with col3:
                    max_symbols = st.selectbox("Show Symbols", [10, 25, 50, 100], index=1)
                
                # Filter and sort symbols
                symbol_details = portfolio_coverage['symbol_details']
                
                if filter_status == "Missing Data Only":
                    symbol_details = [s for s in symbol_details if s['missing_data_types']]
                elif filter_status == "Complete Data Only":
                    symbol_details = [s for s in symbol_details if not s['missing_data_types']]
                
                if sort_by == "Symbol":
                    symbol_details.sort(key=lambda x: x['symbol'])
                elif sort_by == "Coverage %":
                    symbol_details.sort(key=lambda x: x['data_completeness'], reverse=True)
                elif sort_by == "Missing Count":
                    symbol_details.sort(key=lambda x: len(x['missing_data_types']), reverse=True)
                
                # Display symbols
                for symbol_data in symbol_details[:max_symbols]:
                    with st.expander(f"📊 {symbol_data['symbol']} - {symbol_data['data_completeness']}% Complete"):
                        col1, col2, col3 = st.columns([3, 1, 1])
                        
                        with col1:
                            # Data completeness indicator
                            completeness_color = "🟢" if symbol_data['data_completeness'] >= 90 else "🟡" if symbol_data['data_completeness'] >= 70 else "🔴"
                            st.write(f"{completeness_color} **Data Completeness**: {symbol_data['data_completeness']}%")
                            
                            # Data types status
                            for data_type, has_data in symbol_data['data_types'].items():
                                status_icon = "✅" if has_data else "❌"
                                st.write(f"{status_icon} **{data_type.title()}**: {'Available' if has_data else 'Missing'}")
                            
                            # Missing data types
                            if symbol_data['missing_data_types']:
                                st.write(f"⚠️ **Missing**: {', '.join(symbol_data['missing_data_types'])}")
                            else:
                                st.write("✅ **All data types present**")
                        
                        with col2:
                            # Load missing data button
                            if symbol_data['missing_data_types']:
                                if st.button(f"🚀 Load Missing", key=f"load_missing_{symbol_data['symbol']}"):
                                    load_symbol_missing_data(symbol_data['symbol'], symbol_data['missing_data_types'], force_refresh)
                            else:
                                st.success("✅ Complete")
                        
                        with col3:
                            # Force refresh button
                            if st.button(f"🔄 Refresh All", key=f"refresh_{symbol_data['symbol']}"):
                                refresh_symbol_all_data(symbol_data['symbol'], force_refresh)
                
                # Portfolio-wide actions
                st.markdown("#### 🚀 Portfolio-Wide Data Loading")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    missing_data_types = portfolio_coverage['portfolio_missing_data_types']
                    if missing_data_types:
                        selected_data_types = st.multiselect(
                            "Select Data Types to Load",
                            options=missing_data_types,
                            default=missing_data_types
                        )
                    else:
                        st.success("✅ All data types complete!")
                        selected_data_types = []
                
                with col2:
                    if selected_data_types:
                        if st.button("🚀 Load Selected Data Types", type="primary"):
                            load_portfolio_data_types(portfolio_id_for_calls, selected_data_types, force_refresh)
                    else:
                        st.info("No data types selected")
                
                with col3:
                    if st.button("🔄 Force Refresh All Data", type="secondary"):
                        all_data_types = ["price_historical", "indicators", "fundamentals", "earnings"]
                        load_portfolio_data_types(portfolio_id_for_calls, all_data_types, force_refresh=True)
            
            else:
                st.error("Could not load portfolio coverage data")
        
        st.markdown("---")
        
        # Date filter for audit data
        st.markdown("### 📅 Audit History")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            from datetime import datetime as dt
            selected_date = st.date_input(
                "📅 Select Audit Date",
                value=dt.now().date(),
                max_value=dt.now().date(),
                key="audit_date_filter"
            )
        with col2:
            st.markdown("**Provider Distribution Status**")
            provider_status = get_provider_distribution_status(selected_date)
            provider_status = provider_status or {}
            if provider_status.get("total_records", 0) > 0:
                st.success("🟢 Data Available")
            else:
                st.warning("🟡 Limited Data")
        with col3:
            if st.button("🔄 Refresh Audit", key="refresh_audit"):
                st.rerun()
        
        st.markdown("---")
        
        # Enhanced Data Source Status with Universal Provider Tracking
        st.markdown("### 📊 Universal Provider Distribution & Data Sources")
        
        # Get comprehensive audit data
        data_data = get_data_loading_audit_data()
        provider_status = get_provider_distribution_status(selected_date)
        provider_status = provider_status or {}
        
        # Universal Provider Usage Summary
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📊 Total Records", f"{provider_status.get('total_records', 0):,}")
        with col2:
            st.metric("🔄 Primary Provider", provider_status.get('primary_provider', 'Unknown'))
        with col3:
            provider_count = len(provider_status.get('providers', {}))
            st.metric("📈 Active Providers", provider_count)
        with col4:
            symbols_processed = provider_status.get('symbols_processed', 0)
            st.metric("🎯 Symbols Processed", symbols_processed)
        
        st.markdown("---")
        
        # Provider Distribution Chart
        with st.expander("📈 Provider Distribution (details)", expanded=False):
            if provider_status.get('providers'):
                providers = provider_status['providers']
                provider_names = list(providers.keys())
                provider_counts = [providers[name]['record_count'] for name in provider_names]
                
                fig = px.pie(
                    values=provider_counts,
                    names=provider_names,
                    title=f"Data Source Distribution for {selected_date}"
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
                
                total_records = provider_status.get('total_records', 0) or 0
                provider_df = pd.DataFrame([
                    {
                        "Provider": name,
                        "Records": data['record_count'],
                        "Symbols": data['symbol_count'],
                        "Percentage": f"{(data['record_count'] / total_records * 100):.1f}%" if total_records else "0.0%"
                    }
                    for name, data in providers.items()
                ])
                st.dataframe(provider_df, use_container_width=True, hide_index=True)
            else:
                st.info("No provider data available for selected date")
        
        st.markdown("---")
        
        # Symbol-level Data Availability (Portfolio-focused)
        with st.expander("🎯 Portfolio Symbol Data Availability (details)", expanded=False):
            if portfolio_details:
                portfolio_id_for_calls = portfolio_details.get('portfolio_id') or portfolio_details.get('id')
                if not portfolio_id_for_calls:
                    st.error("Portfolio ID missing from portfolio details")
                    portfolio_symbol_status = None
                else:
                    portfolio_symbol_status = get_portfolio_symbol_data_availability(portfolio_id_for_calls, selected_date)
                
                if portfolio_symbol_status:
                    total_symbols = len(portfolio_symbol_status)
                    complete_symbols = sum(1 for s in portfolio_symbol_status if s['data_completeness'] >= 90)
                    primary_provider_symbols = sum(1 for s in portfolio_symbol_status if s.get('uses_primary_provider', False))
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("📋 Portfolio Symbols", total_symbols)
                    with col2:
                        st.metric("✅ Complete Data", complete_symbols)
                    with col3:
                        st.metric("🔄 Primary Provider Users", primary_provider_symbols)
                    
                    for symbol_data in portfolio_symbol_status[:10]:
                        with st.expander(f"{symbol_data['symbol']} - {symbol_data['data_completeness']}% Complete"):
                            col1, col2, col3 = st.columns([3, 1, 1])
                            
                            with col1:
                                completeness_color = "🟢" if symbol_data['data_completeness'] >= 90 else "🟡" if symbol_data['data_completeness'] >= 70 else "🔴"
                                st.write(f"{completeness_color} **Data Completeness**: {symbol_data['data_completeness']}%")
                                
                                primary_provider = symbol_data.get('primary_provider', 'Unknown')
                                provider_icon = "🔄" if symbol_data.get('uses_primary_provider', False) else "⚡"
                                st.write(f"{provider_icon} **Primary Provider**: {primary_provider}")
                                
                                if symbol_data.get('missing_data_types'):
                                    st.write(f"⚠️ **Missing**: {', '.join(symbol_data['missing_data_types'])}")
                                else:
                                    st.write("✅ **All data types present**")
                            
                            with col2:
                                if st.button(f"🔄 Reload", key=f"reload_{symbol_data['symbol']}"):
                                    with st.spinner(f"Reloading data for {symbol_data['symbol']}..."):
                                        reload_symbol_data(symbol_data['symbol'])
                                        st.success(f"Reload initiated for {symbol_data['symbol']}")
                                        st.rerun()
                            
                            with col3:
                                if st.button(f"🔍 Details", key=f"details_{symbol_data['symbol']}"):
                                    show_symbol_audit_details(symbol_data['symbol'], selected_date)
                else:
                    st.info("No portfolio symbol data found for selected date")
            else:
                st.info("Please select a portfolio to view symbol data availability")
        
        st.markdown("---")
        
        # Detailed Audit Trail
        with st.expander("🔍 Detailed Audit Trail (details)", expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                show_only_errors = st.checkbox("Show Only Errors", key="show_errors_only")
            with col2:
                show_only_primary = st.checkbox("Show Only Primary Provider", key="show_primary_only")
            with col3:
                limit_records = st.selectbox("Max Records", [50, 100, 200, 500], index=1, key="audit_limit")
            
            audit_records = get_detailed_audit_records(selected_date, show_only_errors, show_only_primary, limit_records)
            
            if audit_records:
                audit_df = pd.DataFrame(audit_records)
                if not audit_df.empty:
                    audit_df['timestamp'] = pd.to_datetime(audit_df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
                    audit_df['duration'] = audit_df['duration_ms'].apply(lambda x: f"{x}ms" if x else "N/A")
                    
                    def color_code_level(level):
                        if level == 'error': return 'background-color: #ffebee'
                        elif level == 'warning': return 'background-color: #fff3e0'
                        elif level == 'info': return 'background-color: #e3f2fd'
                        return ''
                    
                    styled_df = audit_df.style.applymap(color_code_level, subset=['level'])
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No audit records match the selected filters")
            else:
                st.info("No audit records found for selected date")
        
        st.markdown("---")
        
        # System Overview (existing functionality)
        st.markdown("### 📋 System Overview")
        
        # Collection Statistics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            stats = data_data["collection_stats"]
            st.metric("Total Collections Today", stats["total_collections_today"])
        
        with col2:
            st.metric("Successful", stats["successful_collections"])
        
        with col3:
            st.metric("Failed", stats["failed_collections"])
        
        with col4:
            success_rate = stats["successful_collections"] / max(stats["total_collections_today"], 1)
            st.metric("Success Rate", f"{success_rate:.0%}")
        
        st.markdown("---")
        
        # Display all data sources with detailed information (existing functionality)
        st.markdown("### 📊 Data Source Details")
        data_sources = data_data["data_sources"]
        
        for table_name, source_info in list(data_sources.items())[:5]:  # Show top 5
            status = (source_info or {}).get("status", "unknown")
            status_icon = {"active": "🟢", "healthy": "🟢", "warning": "🟡", "error": "🔴"}.get(status, "⚪")
            name = (source_info or {}).get("name") or table_name
            with st.expander(f"{status_icon} {name}"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Total Records", f"{source_info.get('total_records', 0):,}")
                
                with col2:
                    last_update = source_info.get('last_update') or 'N/A'
                    st.metric("Last Update", str(last_update) if last_update else 'N/A')
                
                with col3:
                    st.metric("Records Today", f"{source_info.get('records_today', 0):,}")
                
                with col1:
                    st.markdown("**Status Information**")
                    st.write(f"**Status:** {status.title()}")
                    st.write(f"**Table:** `{table_name}`")
                
                with col2:
                    st.markdown("**Data Information**")
                    st.write(f"**Total Records:** {source_info.get('total_records', 0):,}")
                    st.write(f"**Records Today:** {source_info.get('records_today', 0):,}")
                    st.write(f"**Last Update:** {str(source_info.get('last_update')) if source_info.get('last_update') else 'N/A'}")
                
                with col3:
                    st.markdown("**Actions**")
                    st.caption("No actions available here. Use dedicated refresh controls per symbol/data type.")
        
        st.markdown("---")
        
        # Manual Data Loading Section
        st.markdown("### 🎯 Manual Data Loading")
        st.markdown("*Load data for specific symbols or data types using real API calls*")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Load Data for Specific Symbols")

            st.caption("Symbol count lookup disabled here (UI -> Go API only).")
            
            # Symbol selection
            symbol_input = st.text_input("Enter symbols (comma-separated)", placeholder="AAPL, MSFT, GOOGL, TSLA", key="symbol_input")
            
            # All 29 data types from refresh strategy (matching test_all_data_loading.py)
            all_data_types = [
                # === MARKET DATA ===
                "price_historical", "price_current", "price_intraday_5m",
                # === FINANCIAL STATEMENTS ===
                "fundamentals", "income_statements", "balance_sheets", "cash_flow_statements",
                # === FINANCIAL METRICS ===
                "indicators", "financial_ratios", "key_metrics_ttm", "financial_scores",
                # === GROWTH METRICS ===
                "income_statement_growth", "balance_sheet_growth", "cash_flow_growth", "financial_growth",
                # === ANALYST & GRADING DATA ===
                "stock_grades", "consensus_data", "price_targets", "analyst_ratings",
                # === EARNINGS DATA ===
                "earnings", "earnings_transcripts",
                # === NEWS & EVENTS ===
                "news", "corporate_actions",
                # === REFERENCE DATA ===
                "industry_peers", "macro_market_data",
                # === SPECIALIZED DATA ===
                "short_interest", "short_volume", "share_float", "risk_factors", "institutional_buying",
                # === SYSTEM DATA ===
                "signals"
            ]
            
            # Create user-friendly names for data types
            data_type_names = {
                "price_historical": "Price Historical",
                "price_current": "Price Current", 
                "price_intraday_5m": "Price Intraday (5m)",
                "fundamentals": "Fundamentals",
                "income_statements": "Income Statements",
                "balance_sheets": "Balance Sheets",
                "cash_flow_statements": "Cash Flow Statements",
                "indicators": "Technical Indicators",
                "financial_ratios": "Financial Ratios",
                "key_metrics_ttm": "Key Metrics (TTM)",
                "financial_scores": "Financial Scores",
                "income_statement_growth": "Income Statement Growth",
                "balance_sheet_growth": "Balance Sheet Growth",
                "cash_flow_growth": "Cash Flow Growth",
                "financial_growth": "Financial Growth",
                "stock_grades": "Stock Grades",
                "consensus_data": "Consensus Data",
                "price_targets": "Price Targets",
                "analyst_ratings": "Analyst Ratings",
                "earnings": "Earnings",
                "earnings_transcripts": "Earnings Transcripts",
                "news": "Market News",
                "corporate_actions": "Corporate Actions",
                "industry_peers": "Industry Peers",
                "macro_market_data": "Macro Market Data",
                "short_interest": "Short Interest",
                "short_volume": "Short Volume",
                "share_float": "Share Float",
                "risk_factors": "Risk Factors",
                "institutional_buying": "Institutional Buying",
                "signals": "Signals"
            }
            
            selected_data_types = st.multiselect(
                "Select data types to load",
                options=all_data_types,
                format_func=lambda x: data_type_names.get(x, x),
                default=["price_historical", "indicators"]
            )
            
            # Rate limiting option
            enable_rate_limiting = st.checkbox("Enable Rate Limiting (Recommended)", value=True, help="Limits API calls to 200 per minute to avoid hitting API limits")
            
            if st.button("🚀 Load Data for Selected Symbols", key="load_selected_symbols"):
                if not portfolio_details:
                    st.error("Select a portfolio above to run a data load")
                elif symbol_input and selected_data_types:
                    symbols = [s.strip().upper() for s in symbol_input.split(',') if s.strip()]
                    portfolio_id_for_calls = portfolio_details.get('portfolio_id') or portfolio_details.get('id')
                    if not portfolio_id_for_calls:
                        st.error("Portfolio ID missing from portfolio details")
                    else:
                        with st.spinner("Starting data load run..."):
                            resp = create_portfolio_data_load_run(
                                portfolio_id_for_calls,
                                symbols,
                                selected_data_types,
                                force=True,
                            )
                            if resp and resp.get("success"):
                                st.success(f"✅ Run started: {resp.get('run_id')}")
                                st.info("See 'Data Loading Audit Trail' below for status and events.")
                            else:
                                st.error(resp.get("error") if isinstance(resp, dict) else "Failed to start data-load run")
                else:
                    st.error("Please enter symbols and select at least one data type")
        
        with col2:
            st.markdown("#### Load Data by Type")
            
            # Data type selection
            data_type_selection = st.selectbox(
                "Select data type to load",
                ["All Data Types", "Market Data Only", "Financial Statements Only", "Financial Metrics Only", "Analyst Data Only", "Earnings Only", "News & Events Only"]
            )
            
            # Symbol set selection
            symbol_set = st.selectbox(
                "Select symbol set",
                ["Major Tech Stocks", "S&P 500 Components", "All Symbols", "Custom"]
            )
            
            if symbol_set == "Major Tech Stocks":
                symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "META", "NVDA"]
            elif symbol_set == "S&P 500 Components":
                symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "JNJ", "V", "PG", "UNH", "HD", "MA", "PYPL", "DIS", "NFLX", "ADBE", "CRM", "BAC"]
            elif symbol_set == "All Symbols":
                symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "META", "NVDA", "JPM", "JNJ", "V"]  # Sample for demo
            else:  # Custom
                custom_symbols = st.text_input("Enter custom symbols (comma-separated)", placeholder="AAPL, MSFT, GOOGL")
                symbols = [s.strip().upper() for s in custom_symbols.split(',') if s.strip()] if custom_symbols else []
            
            # Map selection to actual data types
            if data_type_selection == "All Data Types":
                selected_types = all_data_types
            elif data_type_selection == "Market Data Only":
                selected_types = ["price_historical", "price_current", "price_intraday_5m"]
            elif data_type_selection == "Financial Statements Only":
                selected_types = ["fundamentals", "income_statements", "balance_sheets", "cash_flow_statements"]
            elif data_type_selection == "Financial Metrics Only":
                selected_types = ["indicators", "financial_ratios", "key_metrics_ttm", "financial_scores"] + ["income_statement_growth", "balance_sheet_growth", "cash_flow_growth", "financial_growth"]
            elif data_type_selection == "Analyst Data Only":
                selected_types = ["stock_grades", "consensus_data", "price_targets", "analyst_ratings"]
            elif data_type_selection == "Earnings Only":
                selected_types = ["earnings", "earnings_transcripts"]
            elif data_type_selection == "News & Events Only":
                selected_types = ["news", "corporate_actions"]
            else:
                selected_types = []
            
            st.info(f"Will load {len(selected_types)} data types for {len(symbols)} symbols ({len(selected_types) * len(symbols)} total API calls)")
            
            if st.button("📥 Load Data by Type", key="load_by_type"):
                if not portfolio_details:
                    st.error("Select a portfolio above to run a data load")
                elif symbols and selected_types:
                    portfolio_id_for_calls = portfolio_details.get('portfolio_id') or portfolio_details.get('id')
                    if not portfolio_id_for_calls:
                        st.error("Portfolio ID missing from portfolio details")
                    else:
                        with st.spinner("Starting data load run..."):
                            resp = create_portfolio_data_load_run(
                                portfolio_id_for_calls,
                                symbols,
                                selected_types,
                                force=force_refresh,
                            )
                            if resp and resp.get("success"):
                                st.success(f"✅ Run started: {resp.get('run_id')}")
                                st.info("See 'Data Loading Audit Trail' below for status and events.")
                            else:
                                st.error(resp.get("error") if isinstance(resp, dict) else "Failed to start data-load run")
                else:
                    st.error("Please select a valid symbol set and data type")
        
        st.markdown("---")
        
        # Comprehensive Audit Trail Section
        st.markdown("### 🔍 Data Loading Audit Trail")
        st.markdown("*Complete audit history of all data loading operations with re-run capabilities*")
        portfolio_id_for_runs = None
        try:
            if portfolio_details:
                portfolio_id_for_runs = portfolio_details.get('portfolio_id') or portfolio_details.get('id')
        except Exception:
            portfolio_id_for_runs = None

        if not portfolio_id_for_runs:
            st.info("Select a portfolio above to view recent data-load runs.")
        else:
            try:
                runs_response = go_client.get(
                    f"api/v1/portfolios/{portfolio_id_for_runs}/data-load/runs",
                    params={"limit": 10},
                )
                if runs_response and runs_response.get("success"):
                    runs = runs_response.get("runs", []) or []
                    st.markdown("#### 📋 Recent Portfolio Data-Load Runs")

                    if not runs:
                        st.info("No recent runs found for this portfolio")
                    else:
                        for run in runs:
                            run_id = run.get("run_id", "")
                            started_at = run.get("started_at", "")
                            status = run.get("status", "unknown")

                            status_color = "🟢" if status == "completed" else "🔴" if status == "failed" else "🟡"
                            status_text = status.title()

                            started_display = "Unknown"
                            if started_at:
                                try:
                                    dt = _parse_iso_datetime(started_at)
                                    if dt:
                                        started_display = dt.strftime('%Y-%m-%d %H:%M:%S')
                                    else:
                                        started_display = str(started_at)
                                except Exception:
                                    started_display = str(started_at)

                            with st.expander(f"{status_color} {status_text} Run - {started_display}"):
                                col1, col2 = st.columns(2)

                                with col1:
                                    st.markdown("**Run Information**")
                                    st.write(f"**Run ID:** `{run_id}`")
                                    st.write(f"**Status:** {status_text}")

                                with col2:
                                    st.markdown("**Actions**")
                                    if run_id and st.button("📊 View Details", key=f"go_view_details_{run_id}"):
                                        st.session_state[f"go_show_run_{run_id}"] = True
                                    if status == "failed" and run_id and st.button("🔄 Re-run Failed Symbols", key=f"go_rerun_failed_{run_id}"):
                                        with st.spinner("Starting rerun..."):
                                            rr = go_client.post(f"api/v1/data-load/runs/{run_id}/rerun-failed")
                                            if rr and rr.get("success"):
                                                st.success(f"✅ Rerun started. New run: {rr.get('new_run_id')}")
                                                st.rerun()
                                            else:
                                                st.error(rr.get("error") if isinstance(rr, dict) else "Failed to start rerun")

                                if run_id and st.session_state.get(f"go_show_run_{run_id}"):
                                    details = go_client.get(f"api/v1/data-load/runs/{run_id}")
                                    if details and details.get("success"):
                                        events = details.get("events", []) or []
                                        if events:
                                            df = pd.DataFrame([
                                                {
                                                    "Time": e.get("event_ts"),
                                                    "Level": e.get("level"),
                                                    "Symbol": e.get("symbol"),
                                                    "Operation": e.get("operation"),
                                                    "Records Saved": e.get("records_saved"),
                                                    "Duration": e.get("duration_ms"),
                                                    "Error": e.get("error_message"),
                                                }
                                                for e in events
                                            ])
                                            st.dataframe(df, use_container_width=True)
                                        else:
                                            st.info("No events logged yet")
                                    else:
                                        st.error("Failed to load run details")

                                    if st.button("❌ Close Details", key=f"go_close_{run_id}"):
                                        st.session_state[f"go_show_run_{run_id}"] = False
                                        st.rerun()
                else:
                    st.error("Failed to load recent runs")
            except Exception as e:
                st.error(f"Failed to load audit information: {str(e)}")
        
        st.markdown("---")
        
        # Error Analysis Section
        st.markdown("#### 🚨 Error Analysis")
        st.info("Error analysis summary is not yet wired to Go-backed aggregation endpoints.")
        
        st.markdown("---")
        
        # Performance Analysis Section
        st.markdown("#### 📈 Performance Analysis")
        st.info("Performance analysis summary is not yet wired to Go-backed aggregation endpoints.")
        
        st.markdown("---")
        
        # Collection History
        st.markdown("### 📋 Collection History")
        
        if data_data["recent_collections"]:
            df_collections = pd.DataFrame(data_data["recent_collections"])

            ts_col = None
            for candidate in ["started_at", "created_at", "event_ts", "timestamp"]:
                if candidate in df_collections.columns:
                    ts_col = candidate
                    break

            if ts_col:
                try:
                    df_collections[ts_col] = pd.to_datetime(df_collections[ts_col]).dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass

            cols = [c for c in ["source", "status", "records_processed", ts_col, "duration_ms"] if c and c in df_collections.columns]
            if cols:
                st.dataframe(df_collections[cols], width='stretch')
            else:
                st.dataframe(df_collections, width='stretch')
        else:
            st.info("No recent data collections found")
        
        # Data Quality Metrics
        st.markdown("### 📈 Data Quality Metrics")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_records = sum((ds or {}).get("total_records", 0) for ds in data_sources.values())
            st.metric("📊 Total Records", f"{total_records:,}")
        
        with col2:
            avg_records_per_source = total_records / len(data_sources) if data_sources else 0
            st.metric("📈 Avg Records/Source", f"{avg_records_per_source:,.0f}")
        
        with col3:
            high_priority_sources = [
                ds
                for ds in data_sources.values()
                if (ds or {}).get("priority", "normal") == "high"
            ]
            healthy_high_priority = sum(
                1 for ds in high_priority_sources if (ds or {}).get("status", "unknown") == "healthy"
            )
            st.metric("🎯 Healthy High Priority", f"{healthy_high_priority}/{len(high_priority_sources)}")
        
        with col4:
            sources_with_data = sum(
                1 for ds in data_sources.values() if (ds or {}).get("total_records", 0) > 0
            )
            st.metric("📋 Sources with Data", f"{sources_with_data}/{len(data_sources)}")

    with dashboard_tabs[5]:
        show_stocks_management_dashboard()
    
    with dashboard_tabs[6]:
        st.markdown("## 🚨 Alert Data Monitoring")
        st.markdown("*Monitor data loading intervals for alert-specific sources like grading data*")
        
        try:
            alert_monitoring = get_alert_data_monitoring()
            st.write(f"🔍 Debug: Alert monitoring data retrieved: {len(alert_monitoring.get('alert_specific_sources', {}))} sources")
            
            if not alert_monitoring.get('alert_specific_sources'):
                st.warning("⚠️ No alert data sources found. Check debug output above for details.")
                alert_sources = {}
            else:
                alert_sources = alert_monitoring["alert_specific_sources"]

            if not alert_sources:
                st.info("No alert monitoring data to display")
                st.write("🔍 Debug: Raw alert_monitoring payload")
                st.json(alert_monitoring)
            else:
                # Alert Data Interval Status
                st.markdown("### 📊 Alert Data Loading Intervals")
                
                # Summary metrics
                col1, col2, col3, col4 = st.columns(4)
                
                on_track_count = sum(1 for ds in alert_sources.values() if ds["interval_status"] == "on_track")
                delayed_count = sum(1 for ds in alert_sources.values() if ds["interval_status"] == "delayed")
                overdue_count = sum(1 for ds in alert_sources.values() if ds["interval_status"] == "overdue")
                error_count = sum(1 for ds in alert_sources.values() if ds["interval_status"] == "error")
                
                with col1:
                    st.metric("🟢 On Track", on_track_count)
                with col2:
                    st.metric("🟡 Delayed", delayed_count)
                with col3:
                    st.metric("🔴 Overdue", overdue_count)
                with col4:
                    st.metric("❌ Error", error_count)
                
                st.markdown("---")
                
                # Detailed alert data source monitoring
                for source_key, source_info in alert_sources.items():
                    with st.expander(f"{source_info['interval_icon']} {source_info['name']} - {source_info['expected_interval'].title()}"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.markdown("**Interval Information**")
                            st.write(f"**Expected Interval:** {source_info['expected_interval'].title()}")
                            st.write(f"**Current Status:** {source_info['interval_status'].title()}")
                            st.write(f"**Last Loaded:** {source_info['last_loaded']}")
                            st.write(f"**Next Expected:** {source_info['next_expected']}")
                            if source_info.get("interval_status") == "error" and source_info.get("error"):
                                st.error(f"Data summary error: {source_info.get('error')}")
                        
                        with col2:
                            st.markdown("**Alert Dependencies**")
                            st.write(f"**Dependent Alerts:** {source_info['dependent_alerts']}")
                            st.write(f"**Alert Types:** {', '.join(source_info['alert_types'])}")
                            st.write(f"**Priority:** {source_info['priority'].title()}")
                            st.write(f"**Table:** `{source_info['table']}`")
                        
                        with col3:
                            st.markdown("**Data Statistics**")
                            st.write(f"**Total Records:** {source_info['total_records']:,}")
                            st.write(f"**API Endpoint:** `{source_info['api_endpoint']}`")
                            st.write(f"**Data Source:** {source_info.get('data_source', 'Unknown')}")
                        
        except Exception as e:
            st.error(f"❌ Error loading alert data monitoring: {str(e)}")
            st.code(str(e))

if __name__ == "__main__":
    main()

