import json
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from api_client import get_go_api_client


go_client = get_go_api_client()


def _format_ts(v: Any) -> str:
    if v is None:
        return ""
    try:
        return str(v).replace("T", " ").replace("Z", "")
    except Exception:
        return str(v)


def fetch_portfolios(user_id: str) -> List[Dict[str, Any]]:
    resp = go_client.get(f"api/v1/portfolios/user/{user_id}")
    portfolios = (resp or {}).get("portfolios") or []
    return portfolios if isinstance(portfolios, list) else []


def fetch_portfolio(user_id: str, portfolio_id: str) -> Dict[str, Any]:
    resp = go_client.get(f"api/v1/portfolio/{user_id}/{portfolio_id}")
    return resp if isinstance(resp, dict) else {}


def enqueue_data_load(portfolio_id: str, symbols: List[str], data_types: List[str], force: bool) -> Dict[str, Any]:
    payload = {"symbols": symbols, "data_types": data_types, "force": bool(force)}
    resp = go_client.post(f"api/v1/portfolios/{portfolio_id}/data-load", json_data=payload)
    return resp if isinstance(resp, dict) else {}


def enqueue_trading_decision_v3(portfolio_id: str, symbols: List[str], as_of_date: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if symbols:
        payload["symbols"] = symbols
    if (as_of_date or "").strip():
        payload["as_of_date"] = as_of_date.strip()
    resp = go_client.post(f"api/v1/portfolios/{portfolio_id}/trading-decisions/v3/run", json_data=payload)
    return resp if isinstance(resp, dict) else {}


def fetch_run(run_id: str) -> Dict[str, Any]:
    resp = go_client.get(f"api/v1/data-load/runs/{run_id}")
    return resp if isinstance(resp, dict) else {}


def fetch_schedules() -> Dict[str, Any]:
    resp = go_client.get("api/v1/schedules")
    return resp if isinstance(resp, dict) else {}


def create_schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = go_client.post("api/v1/schedules", json_data=payload)
    return resp if isinstance(resp, dict) else {}


def run_now_schedule(schedule_id: str) -> Dict[str, Any]:
    resp = go_client.post(f"api/v1/schedules/{schedule_id}/run-now", json_data={})
    return resp if isinstance(resp, dict) else {}


def tick_scheduler() -> Dict[str, Any]:
    resp = go_client.post("api/v1/scheduler/tick", json_data={})
    return resp if isinstance(resp, dict) else {}


st.set_page_config(page_title="Trading Decision V3 (Portfolio)", layout="wide")

st.title("Trading Decision V3 (Portfolio)")
st.caption("On-demand and scheduled V3 decision generation via Go API job queue")

user_id = st.text_input("User ID", value="4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4")

portfolios: List[Dict[str, Any]] = []
if user_id.strip():
    try:
        portfolios = fetch_portfolios(user_id.strip())
    except Exception as e:
        st.error(f"Failed to load portfolios: {e}")

portfolio_id = ""
if portfolios:
    options = {f"{p.get('name')} ({p.get('portfolio_type', '')})": p for p in portfolios}
    selected = st.selectbox("Portfolio", options=list(options.keys()))
    portfolio_id = str((options.get(selected) or {}).get("id") or "").strip()
else:
    portfolio_id = st.text_input("Portfolio ID (UUID)")

symbols: List[str] = []
portfolio_data: Dict[str, Any] = {}
if user_id.strip() and portfolio_id.strip():
    try:
        portfolio_data = fetch_portfolio(user_id.strip(), portfolio_id.strip())
        holdings = (portfolio_data or {}).get("holdings") or []
        if isinstance(holdings, list):
            symbols = [str(h.get("symbol") or "").strip().upper() for h in holdings if isinstance(h, dict) and h.get("symbol")]
            symbols = [s for s in symbols if s]
    except Exception as e:
        st.error(f"Failed to load portfolio holdings: {e}")

st.markdown("---")

st.markdown("## Run now")

col_a, col_b = st.columns([1, 1])

with col_a:
    st.markdown("### 1) Refresh data (optional)")
    data_types = st.multiselect(
        "Data types",
        options=["price_historical", "indicators"],
        default=["price_historical", "indicators"],
    )
    force_refresh = st.checkbox("Force", value=True)
    refresh_clicked = st.button("Enqueue data-load", type="primary", width='stretch')

with col_b:
    st.markdown("### 2) Generate decisions")
    as_of_date = st.text_input("as_of_date (optional, YYYY-MM-DD)", value="")
    decisions_clicked = st.button("Enqueue Trading Decision V3", type="primary", width='stretch')

if refresh_clicked:
    if not portfolio_id.strip():
        st.error("Portfolio ID is required")
    elif not symbols:
        st.error("No symbols found for portfolio")
    elif not data_types:
        st.error("Select at least one data type")
    else:
        with st.spinner("Enqueuing data-load..."):
            resp = enqueue_data_load(portfolio_id.strip(), symbols, data_types, force_refresh)
            st.session_state["tdv3_last_run_id"] = (resp or {}).get("run_id")
            st.json(resp)

if decisions_clicked:
    if not portfolio_id.strip():
        st.error("Portfolio ID is required")
    elif not symbols:
        st.error("No symbols found for portfolio")
    else:
        with st.spinner("Enqueuing Trading Decision V3..."):
            resp = enqueue_trading_decision_v3(portfolio_id.strip(), [], as_of_date)
            st.session_state["tdv3_last_run_id"] = (resp or {}).get("run_id")
            st.json(resp)

st.markdown("---")

st.markdown("## Inspect a run")

run_id = st.text_input("Run ID", value=str(st.session_state.get("tdv3_last_run_id") or "").strip())
inspect_clicked = st.button("Load run", width='stretch')

if inspect_clicked and run_id.strip():
    with st.spinner("Fetching run..."):
        resp = fetch_run(run_id.strip())
    st.session_state["tdv3_last_run"] = resp

run_resp = st.session_state.get("tdv3_last_run") if isinstance(st.session_state.get("tdv3_last_run"), dict) else {}
if run_resp:
    run_obj = (run_resp or {}).get("run") or {}
    events = (run_resp or {}).get("events") or []

    st.markdown("### Run summary")
    st.json({"run": run_obj, "events_count": (run_resp or {}).get("events_count")})

    if isinstance(events, list) and events:
        finished = [e for e in events if isinstance(e, dict) and e.get("operation") == "job_finished"]
        rows: List[Dict[str, Any]] = []
        for e in finished:
            ctx = e.get("context")
            if isinstance(ctx, str):
                try:
                    ctx = json.loads(ctx)
                except Exception:
                    ctx = {}
            result = (ctx or {}).get("result") or {}
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:
                    result = {}

            rows.append(
                {
                    "symbol": e.get("symbol"),
                    "event_ts": _format_ts(e.get("event_ts")),
                    "duration_ms": e.get("duration_ms"),
                    "job_type": (ctx or {}).get("job_type"),
                    "action": (result or {}).get("action"),
                    "state": (result or {}).get("state"),
                    "phase": (result or {}).get("phase"),
                    "extension": (result or {}).get("extension"),
                    "confidence": (result or {}).get("confidence"),
                    "opportunity_score": (result or {}).get("opportunity_score"),
                    "volume_context": (result or {}).get("volume_context"),
                }
            )

        if rows:
            st.markdown("### Results (job_finished)")
            df = pd.DataFrame(rows)
            st.dataframe(df.sort_values(["symbol"]).reset_index(drop=True), width='stretch', hide_index=True)

            sym_options = [str(x.get("symbol")) for x in rows if x.get("symbol")]
            sym_selected = st.selectbox("Inspect symbol", options=sorted(list(set(sym_options))))
            if sym_selected:
                ev = next((e for e in finished if str(e.get("symbol")) == sym_selected), None)
                if ev:
                    st.json(ev)

st.markdown("---")

st.markdown("## Scheduling")
st.caption("Backed by Go API schedules: /api/v1/schedules and /api/v1/scheduler/tick")

sched_col1, sched_col2 = st.columns([2, 1])
with sched_col1:
    cron_expression = st.text_input("Cron (5-field)", value="0 18 * * 1-5")
    timezone = st.text_input("Timezone", value="America/New_York")
with sched_col2:
    enabled = st.checkbox("Enabled", value=True)

sched_as_of_date = st.text_input("Scheduled as_of_date (optional, YYYY-MM-DD)", value="")

create_sched_clicked = st.button("Create Trading Decision V3 schedule", type="primary", width='stretch')

if create_sched_clicked:
    if not portfolio_id.strip():
        st.error("Portfolio ID is required")
    else:
        cfg: Dict[str, Any] = {}
        if sched_as_of_date.strip():
            cfg["target_date"] = sched_as_of_date.strip()
        payload = {
            "kind": "trading_decision_v3",
            "portfolio_id": portfolio_id.strip(),
            "profile": "",
            "cron_expression": cron_expression.strip(),
            "timezone": timezone.strip() or "UTC",
            "enabled": bool(enabled),
            "config": cfg,
        }
        with st.spinner("Creating schedule..."):
            resp = create_schedule(payload)
        st.json(resp)

st.markdown("### Existing schedules")

scheds_resp: Dict[str, Any] = {}
try:
    scheds_resp = fetch_schedules()
except Exception as e:
    st.error(f"Failed to fetch schedules: {e}")

scheds = (scheds_resp or {}).get("schedules") or []
if isinstance(scheds, list) and scheds:
    td_scheds = [s for s in scheds if isinstance(s, dict) and str(s.get("kind") or "").lower() == "trading_decision_v3"]
    if td_scheds:
        df = pd.DataFrame(
            [
                {
                    "schedule_id": s.get("schedule_id"),
                    "portfolio_id": s.get("portfolio_id"),
                    "cron_expression": s.get("cron_expression"),
                    "timezone": s.get("timezone"),
                    "enabled": s.get("enabled"),
                    "next_run_at": _format_ts(s.get("next_run_at")),
                    "last_run_at": _format_ts(s.get("last_run_at")),
                    "last_run_id": s.get("last_run_id"),
                }
                for s in td_scheds
            ]
        )
        st.dataframe(df, width='stretch', hide_index=True)

        ids = [str(s.get("schedule_id")) for s in td_scheds if s.get("schedule_id")]
        selected_id = st.selectbox("Schedule", options=ids)
        c1, c2 = st.columns([1, 1])
        if c1.button("Run now", width='stretch'):
            with st.spinner("Triggering schedule run..."):
                resp = run_now_schedule(selected_id)
            st.json(resp)
            if (resp or {}).get("run_id"):
                st.session_state["tdv3_last_run_id"] = (resp or {}).get("run_id")
        if c2.button("Tick scheduler", width='stretch'):
            with st.spinner("Calling scheduler tick..."):
                resp = tick_scheduler()
            st.json(resp)
    else:
        st.caption("No Trading Decision V3 schedules found.")
else:
    st.caption("No schedules found.")
