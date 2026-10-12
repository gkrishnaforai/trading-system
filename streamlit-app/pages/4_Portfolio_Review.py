"""Portfolio Review cockpit — Run Review + Decision History in one page.

Human-in-the-loop only: no orders, allocation, or broker calls are created.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from api_client import APIError, get_go_api_client
from utils import (render_sidebar, setup_page_config, health_col,
                   health_cfg)

setup_page_config("Portfolio Review", "💼")
render_sidebar()

st.title("💼 Portfolio Review")
st.caption("Human-in-the-loop review. No orders, allocation, or broker calls are created.")

client = get_go_api_client()
DEFAULT_USER_ID = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"

POSITION_ACTION_LABELS = {
    "ADD": "May add to position (human decision required)",
    "HOLD": "Hold — no change",
    "TRIM": "Reduce position",
    "TAKE_PROFIT": "Take profit",
    "EXIT": "Exit position",
    "REVIEW": "Manual review required — reconciliation unsafe",
}
ENTRY_STATE_LABELS = {
    "READY": "Setup confirmed — entry permitted by setup, still subject to risk",
    "WAIT": "Wait — do not add now",
    "AVOID": "Avoid — do not enter",
    "BLOCKED": "Blocked — entry not permitted",
}

# --- shared selection -----------------------------------------------------------
with st.sidebar:
    st.header("Review Configuration")
    user_id = st.text_input("User ID", value=DEFAULT_USER_ID).strip()
    horizon = st.selectbox("Horizon", ["swing", "investing"], index=0)
    mode = st.selectbox("Mode", ["analysis", "paper"], index=0)
    persist = st.checkbox(
        "Persist snapshot and decision history",
        value=True,
        help="Writes the review to portfolio-agent history; it still creates no orders.",
    )

if not user_id:
    st.warning("Enter a user ID in the sidebar to load portfolios.")
    st.stop()

try:
    portfolio_response = client.get(f"api/v1/portfolios/user/{user_id}")
    portfolios = portfolio_response.get("portfolios", [])
except APIError as exc:
    st.error(f"Unable to load portfolios from Go API: {exc}")
    st.stop()

if not portfolios:
    st.warning("No portfolios were returned for this user.")
    st.stop()

portfolio_labels = {f"{p.get('name', p.get('id'))} · {p.get('id')}": p for p in portfolios}
selected_label = st.selectbox("Select portfolio", list(portfolio_labels.keys()))
selected_portfolio = portfolio_labels[selected_label]
portfolio_id = str(selected_portfolio.get("id"))

selection_key = f"{portfolio_id}:{horizon}:{mode}"
if st.session_state.get("portfolio_review_selection") != selection_key:
    st.session_state.pop("portfolio_review_result", None)
    st.session_state["portfolio_review_selection"] = selection_key

tab_run, tab_history = st.tabs(["🧠 Run Review", "📜 Decision History"])


# --- Run Review -----------------------------------------------------------------
with tab_run:
    st.subheader("Selected Portfolio")
    summary_cols = st.columns(4)
    summary_cols[0].metric("Name", selected_portfolio.get("name", "n/a"))
    summary_cols[1].metric("Portfolio ID", portfolio_id[:12] + "…")
    summary_cols[2].metric("Holdings", selected_portfolio.get("holdings_count", "n/a"))
    summary_cols[3].metric("Mode", "MANUAL")

    try:
        portfolio_detail = client.get(f"api/v1/portfolio/{user_id}/{portfolio_id}")
    except APIError as exc:
        portfolio_detail = {}
        st.warning(f"Portfolio detail preview unavailable: {exc}")

    holdings = portfolio_detail.get("holdings", []) if isinstance(portfolio_detail, dict) else []
    if holdings:
        st.subheader("Current Holdings")
        st.dataframe(health_col(pd.DataFrame(holdings)),
                     column_config={"🩺": health_cfg()},
                     use_container_width=True, hide_index=True)
    else:
        st.caption("Holdings preview is unavailable or empty; the review agent will validate the portfolio snapshot.")

    st.subheader("Account State")
    try:
        account_state = client.get(f"api/v1/portfolios/{portfolio_id}/account-state") or {}
    except APIError:
        account_state = {}

    def _acct_value(field: str, default: float = 0.0) -> float:
        value = account_state.get(field)
        return float(value) if value is not None else default

    if account_state:
        info_cols = st.columns(3)
        info_cols[0].metric("Reconciliation", account_state.get("reconciliation_status", "UNKNOWN"))
        info_cols[1].metric("State as of", str(account_state.get("as_of", "n/a"))[:19])
        info_cols[2].metric("Source", account_state.get("source", "n/a"))
        missing = account_state.get("missing_fields") or []
        if missing:
            st.warning(f"Missing account fields: {', '.join(missing)} — review will fail closed (REVIEW).")
    else:
        st.warning(
            "No persisted account state. Enter and save the values below — "
            "without them the review cannot reconcile and will return REVIEW for every position."
        )

    with st.form(f"account_state_form_{portfolio_id}"):
        acct_cols = st.columns(3)
        account_equity = acct_cols[0].number_input(
            "Account equity ($)", min_value=0.0, value=_acct_value("account_equity"), step=1000.0)
        settled_cash = acct_cols[1].number_input(
            "Settled cash ($)", min_value=0.0, value=_acct_value("settled_cash"), step=1000.0)
        buying_power = acct_cols[2].number_input(
            "Buying power ($)", min_value=0.0, value=_acct_value("buying_power"), step=1000.0)
        acct_cols2 = st.columns(3)
        unsettled_cash = acct_cols2[0].number_input(
            "Unsettled cash ($)", min_value=0.0, value=_acct_value("unsettled_cash"), step=100.0)
        portfolio_heat = acct_cols2[1].number_input(
            "Portfolio heat (open risk, 0–1)", min_value=0.0, max_value=1.0,
            value=_acct_value("portfolio_heat"), step=0.01, format="%.2f",
            help="Fraction of account equity currently at risk across open positions.")
        save_account_state = st.form_submit_button("Save account state")

    if save_account_state:
        try:
            saved = client.post(f"api/v1/portfolios/{portfolio_id}/account-state", json_data={
                "account_equity": account_equity,
                "settled_cash": settled_cash,
                "unsettled_cash": unsettled_cash,
                "buying_power": buying_power,
                "portfolio_heat": portfolio_heat,
                "source": "manual_ui",
            })
            st.session_state["portfolio_review_account_state"] = saved
            st.success(f"Account state saved (reconciliation: {saved.get('reconciliation_status', 'n/a')}).")
            st.rerun()
        except APIError as exc:
            st.error(f"Failed to save account state: {exc}")

    run_review = st.button("Run Portfolio Review", type="primary", use_container_width=True)

    if run_review:
        payload = {
            "agent": "portfolio_review",
            "scope": "portfolio",
            "portfolio_id": portfolio_id,
            "horizon": horizon,
            "mode": mode,
            "persist": persist,
            "account_equity": account_equity,
            "settled_cash": settled_cash,
            "unsettled_cash": unsettled_cash,
            "buying_power": buying_power,
            "portfolio_heat": portfolio_heat,
        }
        with st.spinner("Reviewing every portfolio position through the Go API..."):
            try:
                response = client.run_agent(payload, timeout=1800)
            except APIError as exc:
                st.error(f"Portfolio review failed: {exc}")
                st.stop()
        st.session_state["portfolio_review_result"] = response

    response = st.session_state.get("portfolio_review_result")
    if not response:
        st.subheader("Ready for review")
        st.markdown(
            """
1. Select a portfolio.
2. Confirm the account context shown in the sidebar.
3. Click **Run Portfolio Review**.
4. Inspect every position's ADD/TRIM/HOLD/REVIEW evidence.
5. Make the final human decision manually.

This phase does not create orders or call a broker.
            """
        )
    else:
        result = response.get("result", response)
        actions = result.get("actions", []) if isinstance(result, dict) else []
        st.success(f"Review completed: {response.get('run_id', result.get('run_id', 'unknown'))}")

        counts = Counter(item.get("action", "REVIEW") for item in actions)
        metric_columns = st.columns(4)
        for column, action in zip(metric_columns, ["ADD", "TRIM", "HOLD", "REVIEW"]):
            column.metric(action, counts.get(action, 0))

        context_columns = st.columns(3)
        context_columns[0].metric("Positions analyzed", result.get("position_count", len(actions)))
        context_columns[1].metric("Manual only", str(result.get("manual_only", True)))
        context_columns[2].metric("Orders created", str(not result.get("no_orders_created", True)))

        st.subheader("Position Actions")
        if actions:
            table_rows: List[Dict[str, Any]] = []
            for item in actions:
                action = item.get("action", "REVIEW")
                entry_state = item.get("entry_state", "WAIT")
                table_rows.append({
                    "Symbol": item.get("symbol"),
                    "Position action": POSITION_ACTION_LABELS.get(action, action),
                    "Entry signal": ENTRY_STATE_LABELS.get(entry_state, entry_state),
                    "Quantity": item.get("quantity"),
                    "Current Price": item.get("current_price"),
                    "Setup": item.get("setup_type"),
                    "Opportunity": item.get("opportunity_quality"),
                    "Fundamentals": item.get("fundamental_quality"),
                    "Event Policy": item.get("event_policy"),
                    "Risk": item.get("risk_status"),
                    "Confidence": item.get("confidence"),
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

            st.subheader("Full Stock Review")
            review_symbols = [item.get("symbol") for item in actions if item.get("symbol")]
            selected_symbol = st.selectbox(
                "Select a position for full analysis",
                review_symbols,
                key="portfolio_review_detail_symbol",
            )
            if st.button("Load Full Stock Review", type="secondary"):
                with st.spinner(f"Analyzing {selected_symbol} through the Go API..."):
                    try:
                        detail_response = client.run_agent({
                            "agent": "swing_review",
                            "scope": "stock",
                            "symbol": selected_symbol,
                            "horizon": horizon,
                            "mode": "analysis",
                        }, timeout=1800)
                        st.session_state["portfolio_review_detail"] = detail_response
                        st.session_state["portfolio_review_detail_loaded_symbol"] = selected_symbol
                    except APIError as exc:
                        st.error(f"Stock review failed: {exc}")

            detail_response = st.session_state.get("portfolio_review_detail")
            if detail_response and detail_response.get("result"):
                detail = detail_response["result"]
                opportunity = detail.get("opportunity", {})
                stock = opportunity.get("stock", {})
                technicals = stock.get("technicals", {})
                fundamentals = opportunity.get("fundamentals", {})
                setup = opportunity.get("setup", {})
                risk = detail.get("risk", {})
                decision = detail.get("decision", {})
                price = technicals.get("price")
                sma50 = technicals.get("sma50")
                sma200 = technicals.get("sma200")
                ema20 = technicals.get("ema20")
                rsi = technicals.get("rsi")
                ret1 = technicals.get("ret1")
                ret5 = technicals.get("ret5")
                volume_ratio = technicals.get("volume_ratio")
                trend = (
                    "Bearish" if price is not None and sma50 is not None and sma200 is not None and price < sma50 and price < sma200
                    else "Bullish" if price is not None and sma50 is not None and price > sma50
                    else "Mixed"
                )
                momentum = "Weak" if rsi is not None and rsi < 45 else "Strong" if rsi is not None and rsi > 60 else "Neutral"
                volume_state = "Expansion" if volume_ratio is not None and volume_ratio >= 1.3 else "Normal/weak" if volume_ratio is not None else "Unavailable"
                reversal_attempt = ret1 is not None and ret1 > 0 and (ret5 is None or ret5 < 0)
                reversal_confirmed = bool(
                    technicals.get("higher_low") is True and
                    price is not None and ema20 is not None and price > ema20
                )
                quality_score = fundamentals.get("quality_score")
                fundamental_thesis = (
                    "INTACT" if fundamentals.get("data_quality") == "good" and quality_score is not None and quality_score >= 50
                    else "INCOMPLETE"
                )
                confirmations = []
                if price is not None and ema20 is not None and price <= ema20:
                    confirmations.append("EMA20 reclaim")
                if technicals.get("higher_low") is not True:
                    confirmations.append("higher low")
                if volume_ratio is None or volume_ratio < 1.0:
                    confirmations.append("positive volume")
                if price is not None and sma50 is not None and price <= sma50:
                    confirmations.append("SMA50 reclaim")
                if not confirmations:
                    confirmations.append("maintain trend confirmation")

                st.markdown(f"### {selected_symbol}")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Price", f"${price:.2f}" if price is not None else "n/a")
                c2.metric("Action", decision.get("action", "REVIEW"))
                c3.metric("Confidence", f"{decision.get('confidence', 0):.0%}")
                c4.metric("Setup", setup.get("type", "n/a"))
                st.markdown("**TREND / MOMENTUM / VOLUME**")
                c1, c2, c3, c4 = st.columns(4)
                c1.write(f"Trend: **{trend}**")
                c2.write(f"Momentum: **{momentum}**")
                c3.write(f"RSI: **{rsi if rsi is not None else 'n/a'}**")
                c4.write(f"Volume: **{volume_state}**")
                c1, c2, c3, c4 = st.columns(4)
                c1.write(f"SMA50: **{'Below' if price is not None and sma50 is not None and price < sma50 else 'Above/unknown'}**")
                c2.write(f"SMA200: **{'Below' if price is not None and sma200 is not None and price > sma200 else 'Above/unknown'}**")
                c3.write(f"Today: **{ret1:.2%}**" if ret1 is not None else "Today: **n/a**")
                c4.write(f"5d: **{ret5:.2%}**" if ret5 is not None else "5d: **n/a**")
                st.markdown("**REVERSAL / THESIS / EVENT**")
                c1, c2, c3 = st.columns(3)
                c1.write(f"Reversal attempt: **{'YES' if reversal_attempt else 'NO'}**")
                c2.write(f"Reversal confirmed: **{'YES' if reversal_confirmed else 'NO'}**")
                c3.write(f"Fundamental thesis: **{fundamental_thesis}**")
                st.write(f"Event policy: **{opportunity.get('event_policy', 'NORMAL')}**")
                st.write(f"Next confirmation: **{' + '.join(confirmations)}**")
                with st.expander("Full deterministic evidence"):
                    st.json({
                        "opportunity": opportunity,
                        "risk": risk,
                        "decision": decision,
                        "event": detail.get("market_event"),
                        "event_environment": detail.get("event_aware_swing_environment"),
                    })

            st.subheader("Per-Position Evidence")
            for item in actions:
                symbol = item.get("symbol", "Unknown")
                with st.expander(f"{symbol} — {POSITION_ACTION_LABELS.get(item.get('action', 'REVIEW'), item.get('action', 'REVIEW'))}"):
                    st.json(item)
        else:
            st.warning("No positions were returned for this portfolio.")

        run_notes = result.get("reasons", []) if isinstance(result, dict) else []
        if run_notes:
            st.subheader("Run Notes")
            for note in run_notes:
                st.write(f"- {note}")


# --- Decision History -------------------------------------------------------------
def _format_ts(v: Any) -> str:
    if v is None:
        return ""
    try:
        return str(v).replace("T", " ").replace("Z", "")
    except Exception:
        return str(v)


def _safe_json(v: Any) -> Any:
    if v is None or isinstance(v, (dict, list)):
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


def _fetch_run(run_id: str) -> Dict[str, Any]:
    resp = client.get(f"api/v1/data-load/runs/{run_id}")
    return resp if isinstance(resp, dict) else {}


def _list_portfolio_runs(pid: str, limit: int = 50) -> List[Dict[str, Any]]:
    resp = client.get(f"api/v1/portfolios/{pid}/data-load/runs", params={"limit": int(limit)})
    runs = (resp or {}).get("runs") or []
    return runs if isinstance(runs, list) else []


def _extract_operation(run_obj: Dict[str, Any]) -> str:
    meta = _safe_json(run_obj.get("metadata"))
    if isinstance(meta, dict):
        return str(meta.get("operation") or "").strip()
    return ""


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
        rows.append({
            "symbol": (e.get("symbol") or "").strip().upper(),
            "action": result.get("action"),
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
        })
    return rows


def _collect_latest_decisions_by_symbol(portfolio_symbols, runs, max_runs_to_scan):
    wanted_set = {s.strip().upper() for s in (portfolio_symbols or []) if str(s).strip()}
    latest_by_symbol: Dict[str, Dict[str, Any]] = {}
    scanned = 0
    for r in runs or []:
        if scanned >= int(max_runs_to_scan):
            break
        if not isinstance(r, dict) or _extract_operation(r).lower() != "trading_decision_v3":
            continue
        run_id = str(r.get("run_id") or r.get("id") or "").strip()
        if not run_id:
            continue
        scanned += 1
        try:
            run_resp = _fetch_run(run_id)
        except Exception:
            continue
        for row in _build_decision_rows_from_run((run_resp or {}).get("events") or []):
            sym = row.get("symbol")
            if sym and sym in wanted_set and sym not in latest_by_symbol:
                row["_run_id"] = run_id
                latest_by_symbol[sym] = row
        if wanted_set and len(latest_by_symbol) >= len(wanted_set):
            break
    return latest_by_symbol


with tab_history:
    st.caption("Latest Trading Decision V3 per symbol for the selected portfolio.")

    try:
        portfolio_data = client.get(f"api/v1/portfolio/{user_id}/{portfolio_id}") or {}
    except APIError as e:
        portfolio_data = {}
        st.error(f"Failed to load holdings: {e}")
    holdings = portfolio_data.get("holdings") or []
    holdings_by_symbol = {
        str(h.get("symbol") or "").strip().upper(): h
        for h in holdings if isinstance(h, dict) and h.get("symbol")
    }

    col_a, col_b, col_c = st.columns([2, 2, 2])
    with col_a:
        limit = st.number_input("Runs to scan", min_value=5, max_value=200, value=50, step=5, key="dh_limit")
    with col_b:
        action_filter = st.multiselect(
            "Filter actions",
            options=["add", "add_light", "hold", "trim", "reduce", "sell", "no_trade"],
            default=[], key="dh_filter",
        )
    with col_c:
        st.write("")
        st.write("")
        refresh_clicked = st.button("Load latest decisions", type="primary", use_container_width=True, key="dh_load")

    auto_load = st.checkbox("Auto-load when portfolio changes", value=True, key="dh_auto")

    def _load_latest_decisions() -> None:
        runs = _list_portfolio_runs(portfolio_id.strip(), limit=int(limit))
        st.session_state["portfolio_decisions_latest_by_symbol"] = _collect_latest_decisions_by_symbol(
            portfolio_symbols=sorted(holdings_by_symbol.keys()),
            runs=runs,
            max_runs_to_scan=int(limit),
        )
        st.session_state["portfolio_decisions_last_loaded_portfolio_id"] = portfolio_id.strip()

    if auto_load and portfolio_id.strip():
        if str(st.session_state.get("portfolio_decisions_last_loaded_portfolio_id") or "") != portfolio_id.strip():
            with st.spinner("Loading latest decisions..."):
                try:
                    _load_latest_decisions()
                except Exception as e:
                    st.error(f"Failed to load latest decisions: {e}")

    if refresh_clicked:
        with st.spinner("Loading latest decisions..."):
            try:
                _load_latest_decisions()
            except Exception as e:
                st.error(f"Failed to load latest decisions: {e}")

    latest_by_symbol = st.session_state.get("portfolio_decisions_latest_by_symbol")
    latest_by_symbol = latest_by_symbol if isinstance(latest_by_symbol, dict) else {}

    if latest_by_symbol:
        decision_rows = list(latest_by_symbol.values())
        for r in decision_rows:
            h = holdings_by_symbol.get(r.get("symbol")) or {}
            r["qty"] = h.get("quantity") or h.get("qty")
            r["avg_price"] = h.get("avg_price") or h.get("average_price")
            r["current_price"] = h.get("current_price")
            r["pnl"] = h.get("pnl")

        df = pd.DataFrame(decision_rows)
        if action_filter:
            df = df[df["action"].isin(action_filter)]

        display_cols = [
            "symbol", "action", "state", "phase", "confidence", "opportunity_score",
            "extension", "volume_context", "qty", "avg_price", "current_price",
            "pnl", "event_ts", "_run_id",
        ]
        st.markdown("#### Latest decisions (per symbol)")
        st.dataframe(
            df[display_cols].sort_values(["action", "symbol"], na_position="last").reset_index(drop=True),
            use_container_width=True, hide_index=True,
        )

        st.markdown("#### Inspect decision")
        sym_options = sorted(s for s in df["symbol"].tolist() if isinstance(s, str) and s)
        sym_selected = st.selectbox("Symbol", options=sym_options, key="dh_symbol")
        if sym_selected:
            selected_row = latest_by_symbol.get(sym_selected)
            if selected_row:
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.markdown("##### Decision")
                    st.json(selected_row.get("_raw_result") or {})
                with c2:
                    st.markdown("##### Event")
                    st.json(selected_row.get("_raw_event") or {})
    else:
        st.caption("Click 'Load latest decisions' to scan run history for this portfolio.")
