"""Manual Portfolio Review cockpit through the Go API BFF only."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from api_client import APIError, get_go_api_client
from utils import render_sidebar, setup_page_config

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

st.info(
    "Canonical workflow: Market Regime → Technical/Setup → Fundamentals → "
    "Events → Risk → Position Review. All calls go through the Go API."
)

if not user_id:
    st.warning("Enter a user ID to load portfolios.")
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

portfolio_labels = {
    f"{p.get('name', p.get('id'))} · {p.get('id')}": p
    for p in portfolios
}
selected_label = st.selectbox("Select portfolio", list(portfolio_labels.keys()))
selected_portfolio = portfolio_labels[selected_label]
portfolio_id = str(selected_portfolio.get("id"))
selection_key = f"{portfolio_id}:{horizon}:{mode}"
if st.session_state.get("portfolio_review_selection") != selection_key:
    st.session_state.pop("portfolio_review_result", None)
    st.session_state["portfolio_review_selection"] = selection_key

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
    st.dataframe(pd.DataFrame(holdings), use_container_width=True, hide_index=True)
else:
    st.caption("Holdings preview is unavailable or empty; the review agent will validate the portfolio snapshot.")

# --- Persisted account state -------------------------------------------------
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
    st.stop()

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
        c2.write(f"SMA200: **{'Below' if price is not None and sma200 is not None and price < sma200 else 'Above/unknown'}**")
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
