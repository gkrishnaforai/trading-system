import streamlit as st
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from api_client import get_go_api_client


go_client = get_go_api_client()


def _safe_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    return []


def _safe_dict(v: Any) -> Dict[str, Any]:
    if isinstance(v, dict):
        return v
    return {}


def _parse_run_response(resp: Dict[str, Any]) -> str:
    # /api/v1/portfolios/:id/data-load returns { success, run_id, status, ... }
    run_id = resp.get("run_id")
    return str(run_id) if run_id else ""


def _format_ts(v: Any) -> str:
    if not v:
        return ""
    try:
        # RFC3339-ish
        s = str(v)
        return s.replace("T", " ").replace("Z", "")
    except Exception:
        return str(v)


def fetch_users() -> List[Dict[str, Any]]:
    resp = _safe_dict(go_client.get("api/v1/users"))
    return _safe_list(resp.get("users"))


def fetch_user_portfolios(user_id: str) -> List[Dict[str, Any]]:
    resp = _safe_dict(go_client.get(f"api/v1/portfolios/user/{user_id}"))
    return _safe_list(resp.get("portfolios"))


def resolve_portfolio_symbols(user_id: str, portfolio_id: str, refresh: bool = False) -> List[str]:
    resp = _safe_dict(
        go_client.get(
            "api/v1/symbol-scope/resolve",
            params={"user_id": user_id, "portfolio_id": portfolio_id, "refresh": "1" if refresh else "0"},
        )
    )
    symbols = _safe_list(resp.get("symbols"))
    out: List[str] = []
    for s in symbols:
        ss = str(s).strip().upper()
        if ss:
            out.append(ss)
    # de-dupe preserve order
    seen = set()
    deduped: List[str] = []
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        deduped.append(s)
    return deduped


def start_data_load(portfolio_id: str, symbols: List[str], data_types: List[str], force: bool) -> Dict[str, Any]:
    payload = {"symbols": symbols, "data_types": data_types, "force": force}
    # Endpoint returns 202 accepted but APIClient treats it as ok; Go returns JSON.
    return _safe_dict(go_client.post(f"api/v1/portfolios/{portfolio_id}/data-load", json_data=payload))


def fetch_job_profiles() -> Dict[str, Any]:
    return _safe_dict(go_client.get("api/v1/admin/job-profiles"))


def start_data_load_with_profile(
    portfolio_id: str,
    symbols: List[str],
    profile: str,
    include_data_types: List[str],
    exclude_data_types: List[str],
    force: bool,
) -> Dict[str, Any]:
    payload = {
        "symbols": symbols,
        "profile": profile,
        "include_data_types": include_data_types,
        "exclude_data_types": exclude_data_types,
        "force": force,
    }
    return _safe_dict(go_client.post(f"api/v1/portfolios/{portfolio_id}/data-load", json_data=payload))


def _normalize_types(raw: List[Any]) -> List[str]:
    out: List[str] = []
    for v in raw or []:
        s = str(v).strip().lower()
        if s:
            out.append(s)
    # de-dupe preserve order
    seen = set()
    deduped: List[str] = []
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        deduped.append(s)
    return deduped


def _apply_overrides(base: List[str], include: List[str], exclude: List[str]) -> List[str]:
    base = _normalize_types(base)
    include = _normalize_types(include)
    exclude = set(_normalize_types(exclude))
    out: List[str] = []
    seen = set()
    for dt in base:
        if dt in exclude:
            continue
        if dt in seen:
            continue
        seen.add(dt)
        out.append(dt)
    for dt in include:
        if dt in exclude:
            continue
        if dt in seen:
            continue
        seen.add(dt)
        out.append(dt)
    return out


def fetch_run(run_id: str) -> Dict[str, Any]:
    return _safe_dict(go_client.get(f"api/v1/data-load/runs/{run_id}"))


def fetch_run_alert_events(run_id: str, limit: int = 200) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": int(limit) if limit else 200}
    return _safe_dict(go_client.get(f"api/v1/data-load/runs/{run_id}/alert-events", params=params))


def fetch_symbol_alert_events(symbol: str, window_hours: int = 168, limit: int = 200) -> Dict[str, Any]:
    sym = str(symbol).strip().upper()
    if not sym:
        return {}
    params: Dict[str, Any] = {
        "symbol": sym,
        "window_hours": int(window_hours) if window_hours else 168,
        "limit": int(limit) if limit else 200,
    }
    return _safe_dict(go_client.get("api/v1/alerts/events", params=params))


def fetch_portfolio_alerts_summary(portfolio_id: str, window_hours: int = 24) -> Dict[str, Any]:
    pid = str(portfolio_id).strip()
    if not pid:
        return {}
    params: Dict[str, Any] = {"window_hours": int(window_hours) if window_hours else 24}
    return _safe_dict(go_client.get(f"api/v1/portfolios/{pid}/alerts/summary", params=params))


def fetch_admin_health() -> Dict[str, Any]:
    return _safe_dict(go_client.get("api/v1/admin/health"))


def fetch_notification_queue_summary(window_hours: int = 24, since: Optional[str] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"window_hours": int(window_hours) if window_hours else 24}
    if since:
        params["since"] = since
    return _safe_dict(go_client.get("api/v1/notifications/queue/summary", params=params))


def fetch_notification_queue_recent(limit: int = 200, status: Optional[str] = None, since: Optional[str] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": int(limit) if limit else 200}
    if status:
        params["status"] = status
    if since:
        params["since"] = since
    return _safe_dict(go_client.get("api/v1/notifications/queue/recent", params=params))


def _render_universal_scheduler_health():
    try:
        admin_health = fetch_admin_health()
        sched = _safe_dict(admin_health.get("universal_alert_scheduler"))
        sched_running = bool(sched.get("running"))
        sched_started_at = sched.get("started_at")
        sched_last_tick = sched.get("last_event_processing_at")
        sched_last_error = sched.get("last_error")

        header_col, status_col = st.columns([1, 4])
        with header_col:
            st.write("Universal Alert Scheduler")
        with status_col:
            if sched_running:
                msg = "Running"
                if sched_last_tick:
                    msg = f"Running (last event-processing: {sched_last_tick})"
                elif sched_started_at:
                    msg = f"Running (started: {sched_started_at})"
                st.success(msg)
            else:
                st.error("Not running")
            if sched_last_error:
                st.caption(f"Last scheduler error: {sched_last_error}")
    except Exception:
        st.warning("Failed to fetch python-worker health via Go API (/api/v1/admin/health)")


def rerun_failed(run_id: str) -> Dict[str, Any]:
    return _safe_dict(go_client.post(f"api/v1/data-load/runs/{run_id}/rerun-failed"))


def cancel_run(run_id: str) -> Dict[str, Any]:
    return _safe_dict(go_client.post(f"api/v1/data-load/runs/{run_id}/cancel"))


def fetch_symbol_preview(symbol: str, data_type: str) -> Dict[str, Any]:
    sym = str(symbol).strip().upper()
    if not sym:
        return {}
    if data_type == "stock":
        return _safe_dict(go_client.get(f"api/v1/stock/{sym}"))
    if data_type == "fundamentals":
        return _safe_dict(go_client.get(f"api/v1/stock/{sym}/fundamentals"))
    if data_type == "news":
        return _safe_dict(go_client.get(f"api/v1/stock/{sym}/news"))
    if data_type == "earnings":
        return _safe_dict(go_client.get(f"api/v1/stock/{sym}/earnings"))

    return _safe_dict(
        go_client.get(
            "api/v1/data-preview",
            params={
                "symbol": sym,
                "data_type": data_type,
                "limit": 50,
                "offset": 0,
            },
        )
    )


def _render_preview_result(data_type: str, resp: Dict[str, Any]):
    resp = _safe_dict(resp)
    count = resp.get("count")
    rows = resp.get("rows")
    if isinstance(rows, list):
        row_count = len(rows)
    else:
        row_count = 0

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Data type", str(data_type))
    with col2:
        st.metric("Rows", int(row_count) if row_count is not None else 0)

    if isinstance(rows, list) and rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        if count is not None and int(count) == 0:
            st.info("No rows returned")
        else:
            st.info("No tabular rows to display")

    with st.expander("Raw response", expanded=False):
        st.json(resp)


def _render_events(events: List[Dict[str, Any]]):
    if not events:
        st.info("No events yet")
        return

    rows = []
    for e in events:
        e = _safe_dict(e)
        ctx = e.get("context")
        if isinstance(ctx, dict):
            ctx_str = json.dumps(ctx)
        else:
            ctx_str = str(ctx) if ctx is not None else None
        rows.append(
            {
                "ts": _format_ts(e.get("event_ts")),
                "level": e.get("level"),
                "symbol": e.get("symbol"),
                "operation": e.get("operation"),
                "provider": e.get("provider"),
                "duration_ms": e.get("duration_ms"),
                "message": e.get("message"),
                "error": e.get("error_message") or e.get("root_cause_message"),
                "context": ctx_str,
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_notification_queue_items(items: List[Dict[str, Any]]):
    if not items:
        st.info("No notification queue items")
        return

    rows = []
    for it in items:
        it = _safe_dict(it)
        rows.append(
            {
                "created_at": _format_ts(it.get("created_at")),
                "channel": it.get("channel_type"),
                "status": it.get("status"),
                "attempts": it.get("attempts"),
                "recipient": it.get("user_email") or it.get("recipient"),
                "subject": it.get("subject"),
                "error": it.get("error_message"),
                "correlation_id": it.get("correlation_id"),
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_portfolio_alerts_panel(user_id: str, portfolio_id: str):
    st.markdown("## 6) Portfolio Alerts (stocks + alerts yes/no)")
    st.caption("Uses Go API endpoints: /api/v1/portfolio/:user_id/:portfolio_id, /api/v1/portfolios/:portfolio_id/alerts/summary, /api/v1/alerts/events")

    if not user_id or not portfolio_id:
        st.info("Select user + portfolio above to view portfolio alerts")
        return

    window_hours = st.number_input(
        "Portfolio alerts lookback (hours)",
        min_value=1,
        max_value=24 * 30,
        value=24,
        step=1,
        key="dlt_portfolio_alert_window_hours",
    )

    refresh_col1, refresh_col2 = st.columns([1, 3])
    with refresh_col1:
        refresh_clicked = st.button("Refresh portfolio alerts", key="dlt_refresh_portfolio_alerts")
    with refresh_col2:
        st.caption("Tip: click a symbol row button to view alert details")

    if refresh_clicked or not st.session_state.get("dlt_portfolio_alerts_summary"):
        try:
            st.session_state["dlt_portfolio_alerts_summary"] = fetch_portfolio_alerts_summary(portfolio_id, window_hours=int(window_hours))
        except Exception:
            st.session_state["dlt_portfolio_alerts_summary"] = {}

    summary = _safe_dict(st.session_state.get("dlt_portfolio_alerts_summary") or {})
    alerts_by_symbol = _safe_dict(summary.get("by_symbol"))

    try:
        port = _safe_dict(go_client.get(f"api/v1/portfolio/{user_id}/{portfolio_id}"))
        holdings = _safe_list(port.get("holdings"))
    except Exception:
        holdings = []

    if not holdings:
        st.info("No holdings")
        return

    selected_symbol = st.session_state.get("dlt_portfolio_selected_symbol")
    for h in holdings:
        h = _safe_dict(h)
        sym = str(h.get("symbol") or "").strip().upper()
        if not sym:
            continue
        row = _safe_dict(alerts_by_symbol.get(sym) or {})
        count = int(row.get("alert_count") or 0)

        col1, col2, col3, col4 = st.columns([1, 2, 2, 3])
        with col1:
            if count > 0:
                if st.button(f"Yes ({count})", key=f"dlt_pf_alert_yes_{portfolio_id}_{sym}"):
                    st.session_state["dlt_portfolio_selected_symbol"] = sym
                    st.rerun()
            else:
                if st.button("No", key=f"dlt_pf_alert_no_{portfolio_id}_{sym}"):
                    st.session_state["dlt_portfolio_selected_symbol"] = sym
                    st.rerun()
        with col2:
            st.write(f"**{sym}**")
        with col3:
            st.write(f"Qty: {h.get('quantity', '')}")
        with col4:
            st.write(f"Latest: {row.get('latest_alert_at') or ''}")

    if selected_symbol:
        st.markdown("### Alert details")
        colx, coly = st.columns([1, 4])
        with colx:
            if st.button("Clear selection", key="dlt_pf_alert_clear"):
                st.session_state.pop("dlt_portfolio_selected_symbol", None)
                st.rerun()
        with coly:
            st.write(f"Selected: **{selected_symbol}**")

        try:
            detail = fetch_symbol_alert_events(selected_symbol, window_hours=int(window_hours), limit=200)
            events = _safe_list(detail.get("alert_events"))
            st.write(f"**Events:** {len(events)}")
            if events:
                _render_alert_events(events)
            else:
                st.info("No alerts for this symbol in the selected window")
        except Exception as e:
            st.error(f"Failed to load alert events: {e}")


def _render_run_summary(run: Dict[str, Any], events: Optional[List[Dict[str, Any]]] = None):
    run_id = run.get("run_id")
    status = run.get("status")
    started_at = _format_ts(run.get("started_at"))
    finished_at = _format_ts(run.get("finished_at"))

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Run ID", str(run_id)[:8] + "..." if run_id else "")
    with col2:
        st.metric("Status", str(status))
    with col3:
        st.metric("Started", started_at)
    with col4:
        st.metric("Finished", finished_at)

    if events and isinstance(events, list):
        try:
            for ev in events:
                e = _safe_dict(ev)
                if e.get("operation") == "admin_refresh_failed" and e.get("error_message"):
                    st.error(f"Admin refresh failed: {e.get('error_message')}")
                    st.caption("This failure happens before per-symbol grades refresh, so there will be no 'Failed symbols' table for this run.")
                    break
        except Exception:
            pass

    meta = run.get("metadata")
    if meta is not None:
        try:
            meta_dict = meta if isinstance(meta, dict) else {}
            grades_failed = meta_dict.get("grades_failed")
            grades_failed_symbols = meta_dict.get("grades_failed_symbols")
            if grades_failed_symbols and isinstance(grades_failed_symbols, list):
                st.markdown("#### Failed symbols")
                st.caption("These symbols failed during grades refresh; fix the underlying issue and use 'Re-run failed'.")
                st.dataframe(pd.DataFrame(grades_failed_symbols), use_container_width=True, hide_index=True)
            elif grades_failed:
                st.warning(f"Grades refresh failures recorded: {grades_failed}")
        except Exception:
            pass
        with st.expander("Run metadata", expanded=False):
            try:
                st.json(meta)
            except Exception:
                st.write(str(meta))


def _render_alert_events(alert_events: List[Dict[str, Any]]):
    if not alert_events:
        st.info("No alert events found for this run window")
        return

    rows = []
    for e in alert_events:
        e = _safe_dict(e)

        trigger_details = e.get("trigger_details")
        if isinstance(trigger_details, str):
            try:
                trigger_details = json.loads(trigger_details)
            except Exception:
                trigger_details = {}
        trigger_details = trigger_details if isinstance(trigger_details, dict) else {}

        event_data = e.get("event_data")
        if isinstance(event_data, str):
            try:
                event_data = json.loads(event_data)
            except Exception:
                event_data = {}
        event_data = event_data if isinstance(event_data, dict) else {}

        event_type = e.get("event_type")
        if event_type == "grade_change":
            grading_company = (
                trigger_details.get("grading_company")
                or trigger_details.get("analyst")
                or trigger_details.get("analyst_company")
                or event_data.get("grading_company")
                or event_data.get("analyst_company")
            )
            action = trigger_details.get("action") or event_data.get("action") or trigger_details.get("change_type")
            prev_grade = (
                trigger_details.get("previous_grade")
                or event_data.get("previous_grade")
                or trigger_details.get("previous_rating")
                or event_data.get("previous_rating")
            )
            new_grade = (
                trigger_details.get("new_grade")
                or event_data.get("new_grade")
                or trigger_details.get("new_rating")
                or event_data.get("rating")
            )
            grade_change = ""
            if prev_grade and new_grade and str(prev_grade) != str(new_grade):
                grade_change = f"{prev_grade} → {new_grade}"
            elif new_grade:
                grade_change = str(new_grade)
        else:
            grading_company = None
            action = None
            grade_change = None

        rows.append(
            {
                "created_at": _format_ts(e.get("created_at")),
                "symbol": e.get("symbol"),
                "event_type": event_type,
                "alert_type": e.get("alert_type"),
                "alert_name": e.get("alert_name"),
                "urgency": e.get("urgency_level"),
                "status": e.get("status"),
                "grading_company": grading_company,
                "action": action,
                "grade": grade_change,
                "trigger_reason": e.get("trigger_reason"),
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


st.set_page_config(page_title="Data Load Run Tester", page_icon="🧪", layout="wide")

st.markdown("# 🧪 Data Load Run Tester (Go API only)")
st.caption("Lean operator page: resolve portfolio symbols → start data-load → inspect run status + events")

_render_universal_scheduler_health()

# State
if "dlt_last_run_id" not in st.session_state:
    st.session_state["dlt_last_run_id"] = ""
if "dlt_last_run_details" not in st.session_state:
    st.session_state["dlt_last_run_details"] = None

with st.sidebar:
    st.markdown("## Settings")
    event_limit = st.number_input("Event limit (display)", min_value=10, max_value=500, value=200, step=10)

st.markdown("## 1) Select User + Portfolio")

users = []
try:
    users = fetch_users()
except Exception as e:
    st.error(f"Failed to load users from Go API: {e}")

if not users:
    st.warning("No users returned from Go API. Is go-api connected to the correct DB?")

user_id: Optional[str] = None
if users:
    user_options = {
        f"{u.get('email') or u.get('username') or u.get('user_id')}": u.get("user_id")
        for u in users
        if u.get("user_id")
    }
    user_label = st.selectbox("User", options=list(user_options.keys()), key="dlt_user_select")
    user_id = user_options.get(user_label)
else:
    user_id = st.text_input("User ID (UUID)")

portfolio_id: Optional[str] = None
portfolios: List[Dict[str, Any]] = []
if user_id:
    try:
        portfolios = fetch_user_portfolios(user_id)
    except Exception as e:
        st.error(f"Failed to load portfolios for user {user_id}: {e}")

if user_id and not portfolios:
    st.warning("No portfolios returned for this user.")

if portfolios:
    port_options = {}
    for p in portfolios:
        pid = p.get("id") or p.get("portfolio_id")
        if not pid:
            continue
        name = p.get("name") or "(unnamed)"
        port_options[f"{name} ({pid})"] = pid
    port_label = st.selectbox("Portfolio", options=list(port_options.keys()), key="dlt_portfolio_select")
    portfolio_id = port_options.get(port_label)
else:
    portfolio_id = st.text_input("Portfolio ID (UUID)")

st.markdown("## 2) Resolve Symbols (Go /symbol-scope/resolve)")

force_symbol_refresh = st.checkbox("Force refresh symbols (bypass cache)", value=True, key="dlt_force_symbol_refresh")

symbols: List[str] = []
if portfolio_id and user_id:
    try:
        symbols = resolve_portfolio_symbols(user_id, portfolio_id, refresh=bool(force_symbol_refresh))
        st.session_state["dlt_symbols"] = symbols
    except Exception as e:
        st.error(f"Failed to resolve symbols: {e}")

symbols = st.session_state.get("dlt_symbols", []) or []

if symbols:
    st.success(f"Resolved {len(symbols)} symbols")
    with st.expander("Symbols", expanded=False):
        st.write(", ".join(symbols[:200]) + (" ..." if len(symbols) > 200 else ""))
else:
    st.info("No symbols resolved yet")

st.markdown("## 3) Start Data Load Run (Go /portfolios/:id/data-load)")

coming_soon_types = [
    "short_interest",
    "short_volume",
    "share_float",
    "risk_factors",
    "institutional_buying",
]

grades_types = [
    "stock_grades",
    "analyst_ratings",
    "consensus_data",
    "price_targets",
    "ratings_snapshot",
    "historical_grades",
]

st.info("Analyst/grades data types are loaded via Go API orchestration, which calls python-worker `/api/v1/grades/refresh/{symbol}` (not the main refresh pipeline).")

with st.expander("Analyst / grades data types", expanded=False):
    st.write(", ".join(grades_types))

allowed_types = [
    "price_historical",
    "price_current",
    "price_intraday_5m",
    "fundamentals",
    "indicators",
    "news",
    "earnings",
    "industry_peers",
    "corporate_actions",
    "signals",
    "reports",
    "income_statements",
    "balance_sheets",
    "cash_flow_statements",
    "financial_ratios",
    "weekly_aggregation",
    "growth_calculations",
    "income_statement_growth",
    "balance_sheet_growth",
    "cash_flow_growth",
    "financial_growth",
    "earnings_transcripts",
    "financial_scores",
    "key_metrics_ttm",
    "owner_earnings",
]

allowed_types = [t for t in allowed_types if t not in grades_types] + grades_types

with st.expander("Coming soon (not available yet)", expanded=False):
    st.write(", ".join(coming_soon_types))

profiles_resp: Dict[str, Any] = {}
profiles_map: Dict[str, List[str]] = {}
try:
    profiles_resp = fetch_job_profiles()
    profiles_map = _safe_dict(profiles_resp.get("profiles"))
except Exception:
    profiles_map = {}

profile_names = sorted([str(k) for k in profiles_map.keys()])
if not profile_names:
    profile_names = [
        "intraday_alerts",
        "intraday_alerts_with_intraday_prices",
        "daily_analysis",
        "bootstrap",
    ]

mode = st.radio(
    "Run mode",
    options=["Profile (recommended)", "Manual data types"],
    horizontal=True,
    key="dlt_run_mode",
)

selected_profile = st.selectbox("Profile", options=profile_names, index=0, key="dlt_profile_select")

include_types = st.multiselect(
    "Include data types (optional)",
    options=allowed_types,
    default=[],
    key="dlt_include_types",
)
exclude_types = st.multiselect(
    "Exclude data types (optional)",
    options=allowed_types,
    default=[],
    key="dlt_exclude_types",
)

base_profile_types = _safe_list(profiles_map.get(selected_profile)) if isinstance(profiles_map, dict) else []
base_profile_types = [str(x) for x in base_profile_types]
resolved_types = _apply_overrides(base_profile_types, include_types, exclude_types)

with st.expander("Resolved data types (what will load)", expanded=True):
    st.write(
        ", ".join(resolved_types)
        if resolved_types
        else "(No data types resolved — check profile/overrides)"
    )

if "dlt_selected_types" not in st.session_state:
    st.session_state["dlt_selected_types"] = ["price_historical", "indicators"]

selected_types: List[str] = []
if mode == "Manual data types":
    selected_types = st.multiselect("Data types", options=allowed_types, key="dlt_selected_types")
else:
    # in profile mode, the resolved types are the ones used
    selected_types = resolved_types

col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
with col1:
    start_clicked = st.button("Start data load", disabled=not (portfolio_id and symbols and selected_types))
with col2:
    force_refresh = st.checkbox("Force refresh", value=False, key="dlt_force_refresh")
with col3:
    load_all_clicked = st.button("Load all", disabled=not (portfolio_id and symbols))
with col4:
    st.caption("This creates a durable run_id and triggers python-worker via Go orchestrator. Use Run Inspector below.")

def _dlt_select_all_types(types: list[str]):
    st.session_state["dlt_selected_types"] = list(types)


def _dlt_clear_types():
    st.session_state["dlt_selected_types"] = []


col_a, col_b, col_c = st.columns([1, 1, 3])
with col_a:
    st.button("Select all", key="dlt_select_all", on_click=_dlt_select_all_types, args=(allowed_types,))
with col_b:
    st.button("Clear", key="dlt_clear_types", on_click=_dlt_clear_types)
with col_c:
    st.caption("Tip: use 'Select all' to populate the multiselect, or 'Load all' for a one-click full run.")

if load_all_clicked:
    try:
        if mode == "Manual data types":
            resp = start_data_load(portfolio_id, symbols, allowed_types, force_refresh)
        else:
            resp = start_data_load_with_profile(
                portfolio_id,
                symbols,
                selected_profile,
                include_data_types=include_types,
                exclude_data_types=exclude_types,
                force=force_refresh,
            )
        run_id = _parse_run_response(resp)
        if run_id:
            st.session_state["dlt_last_run_id"] = run_id
            st.success(f"Run started: {run_id}")
            try:
                st.session_state["dlt_last_run_details"] = fetch_run(run_id)
            except Exception as e:
                st.warning(f"Started run, but failed to fetch initial run status: {e}")
        else:
            st.error("Go API response missing run_id")
            st.json(resp)
    except Exception as e:
        st.error(f"Failed to start data load: {e}")

if start_clicked:
    try:
        if mode == "Manual data types":
            resp = start_data_load(portfolio_id, symbols, selected_types, force_refresh)
        else:
            resp = start_data_load_with_profile(
                portfolio_id,
                symbols,
                selected_profile,
                include_data_types=include_types,
                exclude_data_types=exclude_types,
                force=force_refresh,
            )
        run_id = _parse_run_response(resp)
        if run_id:
            st.session_state["dlt_last_run_id"] = run_id
            st.success(f"Run started: {run_id}")
            try:
                st.session_state["dlt_last_run_details"] = fetch_run(run_id)
            except Exception as e:
                st.warning(f"Started run, but failed to fetch initial run status: {e}")
        else:
            st.error("Go API response missing run_id")
            st.json(resp)
    except Exception as e:
        st.error(f"Failed to start data load: {e}")

st.markdown("## 4) Run Inspector (Go /data-load/runs/:run_id)")

run_id_input = st.text_input("Run ID", value=st.session_state.get("dlt_last_run_id", ""), key="dlt_run_id")

auto_col1, auto_col2, auto_col3 = st.columns([1, 1, 2])
with auto_col1:
    auto_refresh = st.checkbox("Auto refresh", value=True, key="dlt_auto_refresh")
with auto_col2:
    auto_refresh_seconds = st.number_input("Every (sec)", min_value=1, max_value=30, value=3, step=1, key="dlt_auto_refresh_seconds")
with auto_col3:
    st.caption("Uses the same endpoint as curl: GET /api/v1/data-load/runs/:run_id")

if auto_refresh and run_id_input:
    try:
        if hasattr(st, "autorefresh"):
            st.autorefresh(interval=int(auto_refresh_seconds) * 1000, key="dlt_autorefresh")
        else:
            st.caption("Auto refresh unavailable in this Streamlit version; use 'Fetch latest'.")
    except Exception:
        pass

col_a, col_b, col_c = st.columns([1, 1, 2])
with col_a:
    fetch_latest_clicked = st.button("Fetch latest", key="dlt_fetch_latest")
with col_b:
    rerun_failed_clicked = st.button("Re-run failed", key="dlt_rerun_failed")
with col_c:
    event_view = st.selectbox("Events view", options=["All", "Errors only"], index=0, key="dlt_event_view")

if rerun_failed_clicked and run_id_input:
    try:
        rr = rerun_failed(run_id_input)
        if rr.get("success") and rr.get("new_run_id"):
            st.success(f"Rerun started: {rr.get('new_run_id')}")
            st.session_state["dlt_last_run_id"] = rr.get("new_run_id")
            st.session_state["dlt_run_id"] = rr.get("new_run_id")
            st.session_state["dlt_last_run_details"] = fetch_run(rr.get("new_run_id"))
        else:
            st.error("Failed to start rerun")
            st.json(rr)
    except Exception as e:
        st.error(f"Failed to rerun failed symbols: {e}")

if fetch_latest_clicked and run_id_input:
    try:
        st.session_state["dlt_last_run_details"] = fetch_run(run_id_input)
    except Exception as e:
        st.error(f"Failed to fetch run: {e}")

if auto_refresh and run_id_input:
    try:
        details_now = fetch_run(run_id_input)
        if isinstance(details_now, dict) and details_now.get("success"):
            st.session_state["dlt_last_run_details"] = details_now
    except Exception:
        pass

details = st.session_state.get("dlt_last_run_details")
if details and isinstance(details, dict) and details.get("success"):
    run = _safe_dict(details.get("run"))
    events = _safe_list(details.get("events"))
    _render_run_summary(run, events)

    if run.get("status") == "running" and run.get("run_id"):
        if st.button("Cancel run", key="dlt_cancel_run"):
            try:
                cr = cancel_run(str(run.get("run_id")))
                st.info(str(cr))
                st.session_state["dlt_last_run_details"] = fetch_run(str(run.get("run_id")))
            except Exception as e:
                st.error(f"Failed to request cancel: {e}")

    st.markdown("### Events")
    if event_view == "Errors only":
        events = [e for e in events if _safe_dict(e).get("error_message")]
    if event_limit and isinstance(event_limit, int):
        events = events[:event_limit]
    _render_events(events)

    alerts_header_col, alerts_btn_col = st.columns([3, 1])
    with alerts_header_col:
        st.markdown("### New Alerts (this run)")
    with alerts_btn_col:
        refresh_alerts_clicked = st.button("Refresh alerts", key="dlt_refresh_alert_events")

    try:
        run_id_str = str(run.get("run_id"))
        should_fetch_alerts = bool(refresh_alerts_clicked or auto_refresh or not st.session_state.get("dlt_last_alert_events_resp"))
        if should_fetch_alerts and run_id_str:
            st.session_state["dlt_last_alert_events_resp"] = fetch_run_alert_events(run_id_str, limit=200)

        ae = _safe_dict(st.session_state.get("dlt_last_alert_events_resp") or {})
        alert_events = _safe_list(ae.get("alert_events"))
        _render_alert_events(alert_events)
        with st.expander("Alert events (raw)", expanded=False):
            st.json(ae)
    except Exception as e:
        st.warning(f"Failed to fetch alert events: {e}")

    notif_header_col, notif_btn_col = st.columns([3, 1])
    with notif_header_col:
        st.markdown("### Notifications (this run)")
    with notif_btn_col:
        refresh_notif_clicked = st.button("Refresh notifications", key="dlt_refresh_notifications")

    try:
        run_started_at = run.get("started_at")
        since = None
        if run_started_at:
            since = str(run_started_at).replace(" ", "T")
            if "T" not in since:
                since = run_started_at
            if not str(since).endswith("Z") and "+" not in str(since):
                since = f"{since}Z"

        should_fetch_notif = bool(refresh_notif_clicked or auto_refresh or not st.session_state.get("dlt_last_notif_resp"))
        if should_fetch_notif:
            st.session_state["dlt_last_notif_summary_resp"] = fetch_notification_queue_summary(window_hours=168, since=since)
            st.session_state["dlt_last_notif_resp"] = fetch_notification_queue_recent(limit=200, since=since)

        summary = _safe_dict(st.session_state.get("dlt_last_notif_summary_resp") or {})
        items_resp = _safe_dict(st.session_state.get("dlt_last_notif_resp") or {})
        items = _safe_list(items_resp.get("items"))

        if summary.get("success"):
            st.caption("Notification queue summary is real data from universal_notification_queue")
            st.dataframe(pd.DataFrame(_safe_list(summary.get("rows"))), use_container_width=True, hide_index=True)
        _render_notification_queue_items(items)

        with st.expander("Notification queue (raw)", expanded=False):
            st.json({"summary": summary, "recent": items_resp})
    except Exception as e:
        st.warning(f"Failed to fetch notification queue items: {e}")

    global_header_col, global_btn_col = st.columns([3, 1])
    with global_header_col:
        st.markdown("### New Alerts (global)")
    with global_btn_col:
        refresh_global_clicked = st.button("Refresh global", key="dlt_refresh_global_alerts")

    global_hours = st.number_input(
        "Global alerts lookback (hours)",
        min_value=1,
        max_value=24 * 30,
        value=24,
        step=1,
        key="dlt_global_alert_window_hours",
    )

    try:
        should_fetch_global = bool(refresh_global_clicked or not st.session_state.get("dlt_last_global_alerts_resp"))
        if should_fetch_global:
            global_symbol = symbols[0] if symbols else ""
            if global_symbol:
                st.session_state["dlt_last_global_alerts_resp"] = fetch_symbol_alert_events(global_symbol, window_hours=int(global_hours), limit=200)
            else:
                st.session_state["dlt_last_global_alerts_resp"] = {}

        ge = _safe_dict(st.session_state.get("dlt_last_global_alerts_resp") or {})
        global_events = _safe_list(ge.get("alert_events"))
        if symbols:
            st.caption(f"Global alerts are currently displayed for the first resolved symbol: {symbols[0]}")
        _render_alert_events(global_events)
        with st.expander("Global alert events (raw)", expanded=False):
            st.json(ge)
    except Exception as e:
        st.warning(f"Failed to fetch global alerts: {e}")

    errors = [e for e in _safe_list(details.get("events")) if _safe_dict(e).get("error_message")]
    with st.expander(f"Errors ({len(errors)})", expanded=False):
        if errors:
            st.json(errors)
        else:
            st.info("No errors recorded")
elif run_id_input:
    st.info("Click 'Fetch latest' to load run status/events.")

_render_portfolio_alerts_panel(user_id=user_id or "", portfolio_id=portfolio_id or "")


st.markdown("## 5) Data Preview (spot-check loaded data)")
st.caption("Use this to quickly verify the system is ready for analysis after a run.")

if symbols:
    preview_symbol = st.selectbox("Symbol", options=symbols, key="dlt_preview_symbol")
else:
    preview_symbol = st.text_input("Symbol", key="dlt_preview_symbol_text")

preview_allowed_types = list(allowed_types)
if "dlt_preview_types" not in st.session_state:
    st.session_state["dlt_preview_types"] = ["fundamentals", "indicators"]

preview_col1, preview_col2 = st.columns([2, 1])
with preview_col1:
    preview_types = st.multiselect("Preview data types", options=preview_allowed_types, key="dlt_preview_types")
with preview_col2:
    show_all_rows = st.checkbox("Show all rows", value=False, key="dlt_preview_show_all_rows")

if show_all_rows:
    preview_limit = st.number_input("Limit", min_value=1, max_value=500, value=50, step=10, key="dlt_preview_limit")
else:
    preview_limit = 2

preview_btn1, preview_btn2, preview_btn3, preview_btn4 = st.columns([1, 1, 1, 2])
with preview_btn1:
    def _dlt_preview_select_all(types: list[str]):
        st.session_state["dlt_preview_types"] = list(types)

    st.button("Select all", key="dlt_preview_select_all", on_click=_dlt_preview_select_all, args=(preview_allowed_types,))
with preview_btn2:
    def _dlt_preview_clear():
        st.session_state["dlt_preview_types"] = []

    st.button("Clear", key="dlt_preview_clear", on_click=_dlt_preview_clear)
with preview_btn3:
    preview_fetch_all = st.button("Fetch all", key="dlt_preview_fetch_all", disabled=not (preview_symbol and preview_types))
with preview_btn4:
    st.caption("Fetch uses Go API /api/v1/data-preview for each selected data type.")

if preview_fetch_all:
    st.session_state["dlt_preview_last_symbol"] = str(preview_symbol).strip().upper()
    st.session_state["dlt_preview_last_types"] = list(preview_types)
    st.session_state["dlt_preview_has_results"] = True

if st.session_state.get("dlt_preview_has_results") and st.session_state.get("dlt_preview_last_symbol") and st.session_state.get("dlt_preview_last_types"):
    sym = str(st.session_state.get("dlt_preview_last_symbol")).strip().upper()
    types_to_show = list(st.session_state.get("dlt_preview_last_types") or [])
    results: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, str] = {}

    for dt in types_to_show:
        all_cols_key = f"dlt_preview_allcols_{dt}"
        if all_cols_key not in st.session_state:
            st.session_state[all_cols_key] = False

        all_cols = bool(st.session_state.get(all_cols_key))
        try:
            results[dt] = _safe_dict(
                go_client.get(
                    "api/v1/data-preview",
                    params={
                        "symbol": sym,
                        "data_type": dt,
                        "limit": int(preview_limit),
                        "offset": 0,
                        "all_columns": "true" if all_cols else "false",
                    },
                )
            )
        except Exception as e:
            errors[dt] = str(e)

    if errors:
        st.warning("Some previews failed. See details in each tab.")

    if results or errors:
        summary_rows = []
        for dt in types_to_show:
            if dt in errors:
                summary_rows.append({"data_type": dt, "count": None, "status": "error"})
                continue
            resp = _safe_dict(results.get(dt) or {})
            rows = resp.get("rows")
            summary_rows.append(
                {
                    "data_type": dt,
                    "count": len(rows) if isinstance(rows, list) else 0,
                    "status": "ok",
                }
            )

        st.markdown("### Preview summary")
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        st.markdown("### Preview details")
        tabs = st.tabs(types_to_show)
        for i, dt in enumerate(types_to_show):
            with tabs[i]:
                all_cols = st.checkbox(
                    "Show all columns (SELECT *) — may be slow",
                    value=bool(st.session_state.get(f"dlt_preview_allcols_{dt}") or False),
                    key=f"dlt_preview_allcols_{dt}",
                )
                if dt in errors:
                    st.error(errors[dt])
                    continue

                resp = _safe_dict(
                    go_client.get(
                        "api/v1/data-preview",
                        params={
                            "symbol": sym,
                            "data_type": dt,
                            "limit": int(preview_limit),
                            "offset": 0,
                            "all_columns": "true" if all_cols else "false",
                        },
                    )
                )
                _render_preview_result(dt, resp)

with st.expander("Debug: curl equivalents", expanded=False):
    if portfolio_id:
        st.code(
            "\n".join(
                [
                    f"curl -s 'http://localhost:8000/api/v1/symbol-scope/resolve?user_id={user_id}&portfolio_id={portfolio_id}' | jq",
                    "",
                    (
                        f"curl -s -X POST 'http://localhost:8000/api/v1/portfolios/{portfolio_id}/data-load' \n    -H 'Content-Type: application/json' \n    -d '{json.dumps({'symbols': symbols[:3], 'profile': selected_profile, 'include_data_types': include_types, 'exclude_data_types': exclude_types, 'force': force_refresh})}' | jq"
                        if mode == "Profile (recommended)"
                        else f"curl -s -X POST 'http://localhost:8000/api/v1/portfolios/{portfolio_id}/data-load' \n    -H 'Content-Type: application/json' \n    -d '{json.dumps({'symbols': symbols[:3], 'data_types': selected_types, 'force': force_refresh})}' | jq"
                    ),
                    "",
                    "curl -s 'http://localhost:8000/api/v1/data-preview?symbol=MU&data_type=analyst_ratings&limit=5' | jq",
                    "curl -s 'http://localhost:8000/api/v1/data-preview?symbol=MU&data_type=price_targets&limit=5' | jq",
                ]
            )
        )
    if run_id_input:
        st.code(
            f"curl -s 'http://localhost:8000/api/v1/data-load/runs/{run_id_input}' | jq"
        )
