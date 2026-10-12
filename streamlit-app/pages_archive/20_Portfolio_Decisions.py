import json
from datetime import datetime
from typing import Any, Dict, List, Optional

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


def fetch_portfolios(user_id: str) -> List[Dict[str, Any]]:
    resp = go_client.get(f"api/v1/portfolios/user/{user_id}")
    portfolios = (resp or {}).get("portfolios") or []
    return portfolios if isinstance(portfolios, list) else []


def fetch_portfolio(user_id: str, portfolio_id: str) -> Dict[str, Any]:
    resp = go_client.get(f"api/v1/portfolio/{user_id}/{portfolio_id}")
    return resp if isinstance(resp, dict) else {}


def list_portfolio_runs(portfolio_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    resp = go_client.get(f"api/v1/portfolios/{portfolio_id}/data-load/runs", params={"limit": int(limit)})
    runs = (resp or {}).get("runs") or []
    return runs if isinstance(runs, list) else []


def fetch_run(run_id: str) -> Dict[str, Any]:
    resp = go_client.get(f"api/v1/data-load/runs/{run_id}")
    return resp if isinstance(resp, dict) else {}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock(symbol: str) -> Dict[str, Any]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {}
    resp = go_client.get(f"api/v1/stock/{sym}")
    return resp if isinstance(resp, dict) else {}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fundamentals(symbol: str) -> Dict[str, Any]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {}
    resp = go_client.get(f"api/v1/stock/{sym}/fundamentals")
    return resp if isinstance(resp, dict) else {}


def _extract_operation(run_obj: Dict[str, Any]) -> str:
    meta = _safe_json(run_obj.get("metadata"))
    if isinstance(meta, dict):
        op = meta.get("operation")
        return str(op or "").strip()
    return ""


def _find_latest_trading_decision_v3_run_id(runs: List[Dict[str, Any]]) -> str:
    for r in runs or []:
        if not isinstance(r, dict):
            continue
        op = _extract_operation(r).lower()
        if op == "trading_decision_v3":
            run_id = str(r.get("run_id") or r.get("id") or "").strip()
            if run_id:
                return run_id
    return ""


def _collect_latest_decisions_by_symbol(
    *,
    portfolio_symbols: List[str],
    runs: List[Dict[str, Any]],
    max_runs_to_scan: int,
) -> Dict[str, Dict[str, Any]]:
    """Return latest decision row per symbol by scanning runs in descending recency."""
    wanted = [s.strip().upper() for s in (portfolio_symbols or []) if str(s).strip()]
    wanted_set = set(wanted)

    latest_by_symbol: Dict[str, Dict[str, Any]] = {}

    scanned = 0
    for r in runs or []:
        if scanned >= int(max_runs_to_scan):
            break
        if not isinstance(r, dict):
            continue

        op = _extract_operation(r).lower()
        if op != "trading_decision_v3":
            continue

        run_id = str(r.get("run_id") or r.get("id") or "").strip()
        if not run_id:
            continue

        scanned += 1
        try:
            run_resp = fetch_run(run_id)
        except Exception:
            continue

        events = (run_resp or {}).get("events") or []
        decision_rows = _build_decision_rows_from_run(events)

        # Keep lightweight debug stats in session state
        try:
            debug = st.session_state.get("portfolio_decisions_debug")
            debug = debug if isinstance(debug, dict) else {}
            debug.setdefault("runs_scanned", 0)
            debug.setdefault("events_scanned", 0)
            debug.setdefault("decision_rows_seen", 0)
            debug["runs_scanned"] += 1
            debug["events_scanned"] += len(events) if isinstance(events, list) else 0
            debug["decision_rows_seen"] += len(decision_rows)
            st.session_state["portfolio_decisions_debug"] = debug
        except Exception:
            pass

        for row in decision_rows:
            sym = str(row.get("symbol") or "").strip().upper()
            if not sym:
                continue
            if sym not in wanted_set:
                continue
            if sym in latest_by_symbol:
                continue

            row["_run_id"] = run_id
            latest_by_symbol[sym] = row

        if wanted_set and len(latest_by_symbol) >= len(wanted_set):
            break

    return latest_by_symbol


def _build_decision_rows_from_run(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(events, list):
        return []

    finished = [e for e in events if isinstance(e, dict) and e.get("operation") == "job_finished"]
    rows: List[Dict[str, Any]] = []

    for e in finished:
        ctx = _safe_json(e.get("context"))
        if not isinstance(ctx, dict):
            ctx = {}

        result = _safe_json((ctx or {}).get("result"))
        if not isinstance(result, dict):
            result = {}

        action = result.get("action")
        symbol = (e.get("symbol") or "").strip().upper()
        rows.append(
            {
                "symbol": symbol,
                "action": action,
                "state": result.get("state"),
                "phase": result.get("phase"),
                "confidence": result.get("confidence"),
                "opportunity_score": result.get("opportunity_score"),
                "extension": result.get("extension"),
                "volume_context": result.get("volume_context"),
                "event_ts": _format_ts(e.get("event_ts")),
                "duration_ms": e.get("duration_ms"),
                "_raw_result": result,
                "_raw_event": e,
            }
        )

    return rows


st.set_page_config(page_title="Portfolio Decisions", layout="wide")

st.title("Portfolio Decisions")
st.caption("Latest Trading Decision V3 per symbol for a portfolio (TipRanks-style view)")

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

portfolio_data: Dict[str, Any] = {}
holdings: List[Dict[str, Any]] = []
holdings_by_symbol: Dict[str, Dict[str, Any]] = {}

if user_id.strip() and portfolio_id.strip():
    try:
        portfolio_data = fetch_portfolio(user_id.strip(), portfolio_id.strip())
        holdings = (portfolio_data or {}).get("holdings") or []
        if isinstance(holdings, list):
            for h in holdings:
                if not isinstance(h, dict):
                    continue
                sym = str(h.get("symbol") or "").strip().upper()
                if sym:
                    holdings_by_symbol[sym] = h
    except Exception as e:
        st.error(f"Failed to load portfolio holdings: {e}")

st.markdown("---")

col_a, col_b, col_c = st.columns([2, 2, 2])
with col_a:
    limit = st.number_input("Runs to scan", min_value=5, max_value=200, value=50, step=5)
with col_b:
    action_filter = st.multiselect(
        "Filter actions",
        options=["add", "add_light", "hold", "trim", "reduce", "sell", "no_trade"],
        default=[],
    )
with col_c:
    refresh_clicked = st.button("Load latest decisions", type="primary", width="stretch")

auto_load = st.checkbox("Auto-load when portfolio changes", value=True)

debug_mode = st.checkbox("Debug mode", value=False)

def _load_latest_decisions() -> None:
    runs = list_portfolio_runs(portfolio_id.strip(), limit=int(limit))
    st.session_state["portfolio_decisions_last_runs"] = runs
    st.session_state["portfolio_decisions_debug"] = {}
    portfolio_symbols = sorted(list(holdings_by_symbol.keys()))
    latest_by_symbol = _collect_latest_decisions_by_symbol(
        portfolio_symbols=portfolio_symbols,
        runs=runs,
        max_runs_to_scan=int(limit),
    )
    st.session_state["portfolio_decisions_latest_by_symbol"] = latest_by_symbol
    st.session_state["portfolio_decisions_runs_scanned"] = int(limit)
    st.session_state["portfolio_decisions_last_loaded_portfolio_id"] = portfolio_id.strip()
    st.session_state["portfolio_decisions_last_loaded_at"] = datetime.utcnow().isoformat()


should_auto_load = bool(auto_load) and bool(portfolio_id.strip())
if should_auto_load:
    last_pid = str(st.session_state.get("portfolio_decisions_last_loaded_portfolio_id") or "").strip()
    if last_pid != portfolio_id.strip():
        with st.spinner("Loading latest Trading Decision V3 decisions for this portfolio..."):
            try:
                _load_latest_decisions()
            except Exception as e:
                st.error(f"Failed to load latest decisions: {e}")

if refresh_clicked:
    if not portfolio_id.strip():
        st.error("Portfolio ID is required")
    else:
        with st.spinner("Loading latest Trading Decision V3 decisions for this portfolio..."):
            try:
                _load_latest_decisions()
            except Exception as e:
                st.error(f"Failed to load latest decisions: {e}")

        if debug_mode:
            try:
                preview_rows: List[Dict[str, Any]] = []
                runs_preview = st.session_state.get("portfolio_decisions_last_runs")
                runs_preview = runs_preview if isinstance(runs_preview, list) else []
                for r in runs_preview[: min(len(runs_preview), 30)]:
                    if not isinstance(r, dict):
                        continue
                    preview_rows.append(
                        {
                            "run_id": r.get("run_id") or r.get("id"),
                            "started_at": _format_ts(r.get("started_at")),
                            "status": r.get("status"),
                            "operation": _extract_operation(r),
                        }
                    )
                if preview_rows:
                    st.markdown("### Debug: recent runs (first 30)")
                    st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)
            except Exception as e:
                st.warning(f"Debug preview failed: {e}")

latest_by_symbol = st.session_state.get("portfolio_decisions_latest_by_symbol")
latest_by_symbol = latest_by_symbol if isinstance(latest_by_symbol, dict) else {}

if debug_mode:
    dbg = st.session_state.get("portfolio_decisions_debug")
    dbg = dbg if isinstance(dbg, dict) else {}
    st.markdown("### Debug: scan stats")
    st.json(dbg)

    st.markdown("### Debug: manual run inspection")
    manual_run_id = st.text_input("Run ID (optional)", value="")
    if manual_run_id.strip() and st.button("Load run (debug)", width="stretch"):
        try:
            rr = fetch_run(manual_run_id.strip())
            st.json({"run": (rr or {}).get("run"), "events_count": (rr or {}).get("events_count")})
            events = (rr or {}).get("events") or []
            decision_rows = _build_decision_rows_from_run(events)
            st.json({"decision_rows": len(decision_rows)})
            if decision_rows:
                st.dataframe(pd.DataFrame(decision_rows)[["symbol", "action", "event_ts"]], width="stretch", hide_index=True)
        except Exception as e:
            st.error(f"Failed to load run: {e}")

if latest_by_symbol:
    decision_rows = list(latest_by_symbol.values())

    for r in decision_rows:
        sym = r.get("symbol")
        h = holdings_by_symbol.get(sym) or {}
        r["qty"] = h.get("quantity") or h.get("qty")
        r["avg_price"] = h.get("avg_price") or h.get("average_price")
        r["current_price"] = h.get("current_price")
        r["pnl"] = h.get("pnl")

    df = pd.DataFrame(decision_rows)
    if action_filter:
        df = df[df["action"].isin(action_filter)]

    st.markdown("## Data availability (per symbol)")
    show_avail = st.checkbox("Show data availability summary", value=False)
    if show_avail:
        avail_rows: List[Dict[str, Any]] = []
        symbols = sorted([s for s in df["symbol"].tolist() if isinstance(s, str) and s.strip()])
        for sym in symbols:
            sym_u = sym.strip().upper()
            stock = {}
            f_resp = {}
            try:
                stock = fetch_stock(sym_u)
            except Exception as e:
                stock = {"error": str(e)}
            try:
                f_resp = fetch_fundamentals(sym_u)
            except Exception as e:
                f_resp = {"error": str(e)}

            price_time = (stock or {}).get("price_time")
            indicators = (stock or {}).get("indicators") if isinstance(stock, dict) else None
            indicators = indicators if isinstance(indicators, dict) else {}
            ind_date = indicators.get("date")

            fundamentals = (f_resp or {}).get("fundamentals") if isinstance(f_resp, dict) else None
            fundamentals = fundamentals if isinstance(fundamentals, dict) else {}
            fundamentals_as_of = fundamentals.get("as_of_date")

            avail_rows.append(
                {
                    "symbol": sym_u,
                    "latest_price_time": _format_ts(price_time),
                    "latest_indicators_date": _format_ts(ind_date),
                    "fundamentals_as_of": _format_ts(fundamentals_as_of),
                    "fundamentals_available": bool(isinstance(f_resp, dict) and f_resp.get("data_available") is True),
                }
            )

        if avail_rows:
            st.dataframe(pd.DataFrame(avail_rows), width="stretch", hide_index=True)
        else:
            st.caption("No symbols found.")

    display_cols = [
        "symbol",
        "action",
        "state",
        "phase",
        "confidence",
        "opportunity_score",
        "extension",
        "volume_context",
        "qty",
        "avg_price",
        "current_price",
        "pnl",
        "event_ts",
        "_run_id",
    ]

    st.markdown("## Latest decisions (per symbol)")
    st.dataframe(
        df[display_cols].sort_values(["action", "symbol"], na_position="last").reset_index(drop=True),
        width="stretch",
        hide_index=True,
    )

    st.markdown("---")
    st.markdown("## Inspect decision")
    sym_options = sorted([s for s in df["symbol"].tolist() if isinstance(s, str) and s])
    sym_selected = st.selectbox("Symbol", options=sym_options)
    if sym_selected:
        selected_row = latest_by_symbol.get(sym_selected)
        if selected_row:
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown("### Decision")
                st.json(selected_row.get("_raw_result") or {})
            with c2:
                st.markdown("### Event")
                st.json(selected_row.get("_raw_event") or {})

            st.markdown("---")
            st.markdown("## Fundamentals (context)")
            try:
                f_resp = fetch_fundamentals(sym_selected)
            except Exception as e:
                f_resp = {"error": str(e)}

            if isinstance(f_resp, dict) and f_resp.get("data_available") is False:
                st.caption(f_resp.get("message") or "No fundamental data available for this symbol.")
            else:
                fundamentals = (f_resp or {}).get("fundamentals") if isinstance(f_resp, dict) else None
                fundamentals = fundamentals if isinstance(fundamentals, dict) else {}

                key_order = [
                    "as_of_date",
                    "market_cap",
                    "sector",
                    "industry",
                    "pe_ratio",
                    "forward_pe",
                    "peg_ratio",
                    "ev_to_sales",
                    "ev_to_ebitda",
                    "price_to_sales",
                    "price_to_book",
                    "gross_margin",
                    "operating_margin",
                    "profit_margin",
                    "revenue_ttm",
                    "revenue_growth_yoy",
                    "eps_ttm",
                    "fcf_ttm",
                    "debt_to_equity",
                ]
                rows: List[Dict[str, Any]] = []
                seen = set()
                for k in key_order:
                    if k in fundamentals:
                        rows.append({"field": k, "value": fundamentals.get(k)})
                        seen.add(k)
                for k, v in fundamentals.items():
                    if k in seen:
                        continue
                    rows.append({"field": k, "value": v})

                if rows:
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                else:
                    st.caption("No fundamentals payload found for this symbol.")
else:
    st.caption("Click 'Load latest decisions' to load the latest available Trading Decision V3 decision per symbol for the selected portfolio.")
