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


def list_portfolio_runs(portfolio_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    resp = go_client.get(f"api/v1/portfolios/{portfolio_id}/data-load/runs", params={"limit": int(limit)})
    runs = (resp or {}).get("runs") or []
    return runs if isinstance(runs, list) else []


def _safe_json(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return v
        try:
            return json.loads(s)
        except Exception:
            return v
    return v


def _extract_operation(run_obj: Dict[str, Any]) -> str:
    meta = _safe_json(run_obj.get("metadata"))
    if isinstance(meta, dict):
        op = meta.get("operation")
        return str(op or "").strip()
    return ""


def fetch_schedules() -> Dict[str, Any]:
    resp = go_client.get("api/v1/schedules")
    return resp if isinstance(resp, dict) else {}


def _is_data_load_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if "data_types" in result and ("main" in result or "grades" in result):
        return True
    if "results" in result and "summary" in result:
        return True
    return False


def _extract_refresh_main(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    main = result.get("main")
    if isinstance(main, dict):
        return main
    if isinstance(result.get("results"), dict) and isinstance(result.get("summary"), dict):
        return result
    return {}


def _extract_grades_block(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    g = result.get("grades")
    return g if isinstance(g, dict) else {}


def create_schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = go_client.post("api/v1/schedules", json_data=payload)
    return resp if isinstance(resp, dict) else {}


def run_now_schedule(schedule_id: str) -> Dict[str, Any]:
    resp = go_client.post(f"api/v1/schedules/{schedule_id}/run-now", json_data={})
    return resp if isinstance(resp, dict) else {}


def tick_scheduler() -> Dict[str, Any]:
    resp = go_client.post("api/v1/scheduler/tick", json_data={})
    return resp if isinstance(resp, dict) else {}


def fetch_fair_value(symbol: str, *, method_key: str = "") -> Dict[str, Any]:
    params: Dict[str, Any] = {"symbol": symbol}
    if (method_key or "").strip():
        params["method_key"] = method_key.strip()
    resp = go_client.get("api/v1/admin/fundamentals/fair-value", params=params)
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

    all_data_type_options = [
        "price_historical",
        "price_current",
        "price_intraday_5m",
        "indicators",
        "company_profile",
        "fundamentals",
        "financial_ratios",
        "income_statements",
        "balance_sheets",
        "cash_flow_statements",
        "news",
        "earnings",
        "industry_peers",
        "corporate_actions",
        "institutional_buying",
        "analyst_ratings",
        "consensus_data",
        "price_targets",
    ]

    presets = {
        "Default (Screeners + Decisions)": [
            "price_historical",
            "price_current",
            "indicators",
            "fundamentals",
            "financial_ratios",
            "income_statements",
        ],
        "Fair Value V2 (Analyst consensus)": [
            "price_current",
            "company_profile",
            "fundamentals",
            "financial_ratios",
            "analyst_ratings",
            "consensus_data",
            "price_targets",
        ],
        "Default + Alerts (News + Ratings)": [
            "price_historical",
            "price_current",
            "indicators",
            "fundamentals",
            "financial_ratios",
            "income_statements",
            "news",
            "analyst_ratings",
            "consensus_data",
            "price_targets",
        ],
        "Decisions only (EOD)": [
            "price_historical",
            "price_current",
            "indicators",
        ],
        "Decisions only (Intraday)": [
            "price_historical",
            "price_current",
            "price_intraday_5m",
            "indicators",
        ],
        "Screeners only": [
            "fundamentals",
            "financial_ratios",
            "income_statements",
            "balance_sheets",
            "cash_flow_statements",
        ],
    }

    preset_label = st.selectbox(
        "Preset",
        options=list(presets.keys()),
        index=0,
    )
    apply_preset = st.button("Apply preset", width='stretch')
    if apply_preset:
        st.session_state["tdv3_refresh_data_types"] = presets[preset_label]

    data_types = st.multiselect(
        "Data types",
        options=all_data_type_options,
        default=st.session_state.get("tdv3_refresh_data_types") or presets["Default (Screeners + Decisions)"],
        key="tdv3_refresh_data_types",
    )
    force_refresh = st.checkbox("Force", value=True)
    refresh_clicked = st.button("Enqueue data-load", type="primary", width='stretch')

with col_b:
    st.markdown("### 2) Generate decisions")
    as_of_date = st.text_input("as_of_date (optional, YYYY-MM-DD)", value="")
    decisions_clicked = st.button("Enqueue Trading Decision V3", type="primary", width='stretch')

    st.markdown("### 3) Fair value (optional)")
    if symbols:
        fv_symbol = st.selectbox(
            "Symbol",
            options=sorted(list(set(symbols))),
            index=0,
        )
    else:
        st.info("Load/select a portfolio with symbols to fetch fair value")
        fv_symbol = ""
    fv_engine = st.selectbox(
        "Engine",
        options=["Default (V1 + V2 override if enabled)", "V2 (single method)", "V2 (Analyst consensus)"] ,
        index=0,
    )
    fv_compare_consensus = st.checkbox("Compare with V2 (Analyst consensus)", value=True)
    fv_clicked = st.button("Fetch fair value", width='stretch')

    if fv_clicked:
        if not (fv_symbol or "").strip():
            st.error("Select a symbol")
        else:
            method_key = ""
            if fv_engine == "V2 (single method)":
                method_key = st.session_state.get("tdv3_fv_v2_method_key") or "pe_forward"
            if fv_engine == "V2 (Analyst consensus)":
                method_key = "analyst_consensus"

            with st.spinner("Fetching fair value..."):
                try:
                    sym = str(fv_symbol).strip().upper()
                    resp = fetch_fair_value(sym, method_key=str(method_key or ""))
                    st.session_state["tdv3_last_fair_value"] = resp

                    # If user is looking at the default fair value (which may include a v2 override)
                    # also fetch analyst consensus as a validation/comparison signal.
                    if fv_compare_consensus and fv_engine == "Default (V1 + V2 override if enabled)":
                        st.session_state["tdv3_last_fair_value_consensus"] = fetch_fair_value(
                            sym,
                            method_key="analyst_consensus",
                        )
                    elif fv_engine != "Default (V1 + V2 override if enabled)":
                        st.session_state["tdv3_last_fair_value_consensus"] = {}
                except Exception as e:
                    st.error(str(e))

    if fv_engine == "V2 (single method)":
        st.selectbox(
            "V2 method_key",
            options=[
                "pe_basic",
                "pe_forward",
                "pe_growth",
                "pe_value",
                "pe_technology_dynamic",
                "dcf_simple",
                "dcf_mega_cap",
                "peg",
                "peg_40",
                "peg_corrected",
                "ev_sales_growth",
                "ev_sales_fintech",
                "pb_bank",
                "analyst_consensus",
            ],
            index=1,
            key="tdv3_fv_v2_method_key",
        )

    fv_resp = st.session_state.get("tdv3_last_fair_value") if isinstance(st.session_state.get("tdv3_last_fair_value"), dict) else {}
    fv_consensus_resp = (
        st.session_state.get("tdv3_last_fair_value_consensus")
        if isinstance(st.session_state.get("tdv3_last_fair_value_consensus"), dict)
        else {}
    )
    if fv_resp:
        data = (fv_resp or {}).get("data") if isinstance((fv_resp or {}).get("data"), dict) else {}
        st.json(fv_resp)
        try:
            if data:
                c1, c2, c3 = st.columns([1, 1, 1])
                with c1:
                    st.metric("Current price", str(data.get("current_price") or ""))
                with c2:
                    st.metric("Fair value", str(data.get("fair_value") or ""))
                with c3:
                    st.metric("Undervaluation %", str(data.get("undervaluation_pct") or ""))
        except Exception:
            pass

    # Optional comparison: default vs analyst consensus
    try:
        if fv_compare_consensus and fv_engine == "Default (V1 + V2 override if enabled)" and fv_consensus_resp:
            cd = (fv_consensus_resp or {}).get("data") if isinstance((fv_consensus_resp or {}).get("data"), dict) else {}
            v2 = (cd or {}).get("v2") if isinstance((cd or {}).get("v2"), dict) else {}
            consensus_fv = (v2 or {}).get("fair_value")
            default_fv = (fv_resp or {}).get("data", {}).get("fair_value") if isinstance((fv_resp or {}).get("data"), dict) else None

            st.markdown("#### Validate vs analyst consensus")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                st.metric("Default FV", str(default_fv or ""))
            with c2:
                st.metric("Consensus FV", str(consensus_fv or ""))
            with c3:
                diff_pct = None
                try:
                    if default_fv and consensus_fv and float(default_fv) != 0:
                        diff_pct = (float(consensus_fv) - float(default_fv)) / float(default_fv) * 100.0
                except Exception:
                    diff_pct = None
                st.metric("Consensus vs Default %", f"{diff_pct:.2f}%" if diff_pct is not None else "")

            with st.expander("Raw consensus fair value payload", expanded=False):
                st.json(fv_consensus_resp)
    except Exception:
        pass

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

runs: List[Dict[str, Any]] = []
if portfolio_id.strip():
    try:
        runs = list_portfolio_runs(portfolio_id.strip(), limit=50)
    except Exception:
        runs = []

if runs:
    run_options = {}
    for r in runs:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("run_id") or "").strip()
        if not rid:
            continue
        op = _extract_operation(r)
        label = f"{_format_ts(r.get('started_at'))} | {op or '(unknown)'} | {rid} | {str(r.get('status') or '').strip()}"
        run_options[label] = rid

    default_run_id = str(st.session_state.get("tdv3_last_run_id") or "").strip()
    default_label = None
    if default_run_id:
        for k, v in run_options.items():
            if v == default_run_id:
                default_label = k
                break

    selected_label = st.selectbox(
        "Recent runs (portfolio)",
        options=list(run_options.keys()),
        index=list(run_options.keys()).index(default_label) if default_label in run_options else 0,
        key="tdv3_recent_runs_select",
    )
    if selected_label:
        st.session_state["tdv3_last_run_id"] = run_options.get(selected_label)

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
    failure = (run_resp or {}).get("failure") or {}

    st.markdown("### Run summary")
    st.json({"run": run_obj, "events_count": (run_resp or {}).get("events_count")})

    if isinstance(failure, dict) and failure:
        st.markdown("### Failure summary")
        st.json(failure)

    if isinstance(events, list) and events:
        finished = [e for e in events if isinstance(e, dict) and e.get("operation") == "job_finished"]
        rows: List[Dict[str, Any]] = []
        data_avail_rows: List[Dict[str, Any]] = []
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

            if _is_data_load_result(result):
                main = _extract_refresh_main(result)
                grades = _extract_grades_block(result)
                summary = (main or {}).get("summary") if isinstance(main, dict) else {}
                per_dt = (main or {}).get("results") if isinstance(main, dict) else {}
                if isinstance(per_dt, dict) and per_dt:
                    for dt_key, dt_res in per_dt.items():
                        if not isinstance(dt_res, dict):
                            continue
                        data_avail_rows.append(
                            {
                                "symbol": result.get("symbol") or e.get("symbol"),
                                "data_type": dt_res.get("data_type") or dt_key,
                                "status": dt_res.get("status"),
                                "rows_affected": dt_res.get("rows_affected"),
                                "timestamp": _format_ts(dt_res.get("timestamp")),
                                "message": dt_res.get("message"),
                                "error": dt_res.get("error"),
                                "total_requested": (summary or {}).get("total_requested"),
                                "total_successful": (summary or {}).get("total_successful"),
                                "total_failed": (summary or {}).get("total_failed"),
                                "total_skipped": (summary or {}).get("total_skipped"),
                            }
                        )
                elif isinstance(summary, dict) and summary:
                    data_avail_rows.append(
                        {
                            "symbol": result.get("symbol") or e.get("symbol"),
                            "data_type": "(summary)",
                            "status": "(unknown)",
                            "rows_affected": None,
                            "timestamp": "",
                            "message": "No per-data-type results in payload",
                            "error": None,
                            "total_requested": summary.get("total_requested"),
                            "total_successful": summary.get("total_successful"),
                            "total_failed": summary.get("total_failed"),
                            "total_skipped": summary.get("total_skipped"),
                        }
                    )

                if isinstance(grades, dict) and grades:
                    grades_results = grades.get("results") if isinstance(grades.get("results"), dict) else {}
                    grades_errors = grades.get("errors") if isinstance(grades.get("errors"), list) else []
                    grades_ts = grades.get("timestamp")
                    for dt_key, dt_res in (grades_results or {}).items():
                        if not isinstance(dt_res, dict):
                            continue
                        data_avail_rows.append(
                            {
                                "symbol": result.get("symbol") or e.get("symbol"),
                                "data_type": dt_key,
                                "status": dt_res.get("status"),
                                "rows_affected": dt_res.get("rows"),
                                "timestamp": _format_ts(grades_ts) if grades_ts else "",
                                "message": "grades_refresh",
                                "error": dt_res.get("error") or ("; ".join([str(x) for x in grades_errors]) if grades_errors else None),
                                "total_requested": None,
                                "total_successful": None,
                                "total_failed": None,
                                "total_skipped": None,
                            }
                        )
                continue

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

            action_counts = {}
            try:
                action_counts = (
                    df["action"].fillna("(none)").astype(str).value_counts().to_dict()
                    if "action" in df.columns
                    else {}
                )
            except Exception:
                action_counts = {}

            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            with c1:
                st.metric("Symbols", int(df["symbol"].nunique()) if "symbol" in df.columns else len(df))
            with c2:
                st.metric("Actions", len(action_counts))
            with c3:
                st.metric("Top action", next(iter(action_counts.keys()), ""))
            with c4:
                st.metric("Top action count", int(next(iter(action_counts.values()), 0) or 0))

            action_filter = st.selectbox(
                "Filter by action",
                options=["(all)"] + sorted(list(action_counts.keys() or [])),
            )
            df_view = df
            if action_filter != "(all)" and "action" in df_view.columns:
                df_view = df_view[df_view["action"].fillna("(none)").astype(str) == action_filter]

            st.dataframe(df_view.sort_values(["symbol"]).reset_index(drop=True), width='stretch', hide_index=True)

            if action_counts:
                st.markdown("#### Action distribution")
                dist_df = pd.DataFrame(
                    [{"action": k, "count": int(v)} for k, v in action_counts.items()]
                ).sort_values(["count"], ascending=False)
                st.bar_chart(dist_df.set_index("action")["count"], height=240)

            sym_options = [str(x.get("symbol")) for x in rows if x.get("symbol")]
            sym_selected = st.selectbox("Inspect symbol", options=sorted(list(set(sym_options))))
            if sym_selected:
                ev = next((e for e in finished if str(e.get("symbol")) == sym_selected), None)
                if ev:
                    ctx = ev.get("context")
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

                    st.markdown("#### Decision")
                    d1, d2, d3, d4 = st.columns([1, 1, 1, 1])
                    with d1:
                        st.metric("Action", str((result or {}).get("action") or ""))
                    with d2:
                        st.metric("State", str((result or {}).get("state") or ""))
                    with d3:
                        st.metric("Confidence", str((result or {}).get("confidence") or ""))
                    with d4:
                        st.metric("Opportunity", str((result or {}).get("opportunity_score") or ""))

                    with st.expander("Raw decision payload", expanded=False):
                        st.json(result)

                    with st.expander("Raw job_finished event", expanded=False):
                        st.json(ev)

        if data_avail_rows:
            st.markdown("### Data availability check (data-load)")
            dav = pd.DataFrame(data_avail_rows)
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            with c1:
                st.metric("Symbols", int(dav["symbol"].nunique()) if "symbol" in dav.columns else len(dav))
            with c2:
                st.metric("Data types", int(dav["data_type"].nunique()) if "data_type" in dav.columns else 0)
            with c3:
                failed_ct = int((dav["status"].fillna("") == "failed").sum()) if "status" in dav.columns else 0
                st.metric("Failed", failed_ct)
            with c4:
                skipped_ct = int((dav["status"].fillna("") == "skipped").sum()) if "status" in dav.columns else 0
                st.metric("Skipped", skipped_ct)

            sym_filter = st.selectbox(
                "Filter symbol (data availability)",
                options=["(all)"] + sorted([x for x in dav["symbol"].dropna().astype(str).unique().tolist()]),
            )
            dav_view = dav
            if sym_filter != "(all)":
                dav_view = dav_view[dav_view["symbol"].fillna("").astype(str) == sym_filter]

            dt_filter = st.selectbox(
                "Filter data_type (data availability)",
                options=["(all)"] + sorted([x for x in dav_view["data_type"].dropna().astype(str).unique().tolist()]),
            )
            if dt_filter != "(all)":
                dav_view = dav_view[dav_view["data_type"].fillna("").astype(str) == dt_filter]

            st.dataframe(
                dav_view.sort_values(["symbol", "data_type"]).reset_index(drop=True),
                width='stretch',
                hide_index=True,
            )

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
