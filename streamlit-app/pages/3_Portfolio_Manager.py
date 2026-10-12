"""
Portfolio Manager — consolidated entity management.

Tabs: Holdings (view + add/update/delete) | Watchlist (CRUD + items — feeds the
alert scan universe) | Portfolios (CRUD + notification email) | Weekly Changes.
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (setup_page_config, render_sidebar, health_col,
                   health_cfg)
from shared_functions import get_portfolio_data
from api_client import get_go_api_client, get_python_api_client, APIError

setup_page_config("Portfolio Manager", "💼")
subscription_level = render_sidebar()

st.title("💼 Portfolio Manager")
st.caption("Holdings and watchlist symbols feed the alert scan universe automatically.")

client = get_go_api_client()
DEFAULT_USER_ID = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"


def _load_users():
    resp = client.get("api/v1/users")
    return (resp or {}).get("users") or []


def _load_portfolios_for_user(user_id: str):
    if not user_id:
        return []
    resp = client.get(f"api/v1/portfolios/user/{user_id}")
    return (resp or {}).get("portfolios") or []


# --- shared selectors ---------------------------------------------------------
users = []
try:
    users = _load_users()
except APIError as e:
    st.error(f"Failed to load users: {e}")

user_options = {
    f"{u.get('username', 'unknown')} ({u.get('subscription_level', 'basic')})": u.get("user_id")
    for u in users if u.get("user_id")
}
_labels = list(user_options.keys())
_default_idx = next(
    (i for i, l in enumerate(_labels) if user_options[l] == DEFAULT_USER_ID), 0
)
selected_user_label = st.selectbox("User", options=_labels, index=_default_idx if _labels else 0, key="pm_user")
user_id = user_options.get(selected_user_label)

portfolios = []
try:
    portfolios = _load_portfolios_for_user(user_id) if user_id else []
except APIError as e:
    st.error(f"Failed to load portfolios: {e}")

portfolio_options = {p.get("name", p.get("id", "?")): p.get("id") for p in portfolios if p.get("id")}
portfolio_label = st.selectbox("Portfolio", options=list(portfolio_options.keys()), key="pm_portfolio")
portfolio_id = portfolio_options.get(portfolio_label)

tab_holdings, tab_watchlist, tab_portfolios, tab_weekly = st.tabs(
    ["📊 Holdings", "👁 Watchlist", "💼 Portfolios", "📅 Weekly Changes"]
)


# --- Holdings ------------------------------------------------------------------
with tab_holdings:
    if not portfolio_id:
        st.info("Select a portfolio to manage holdings.")
    else:
        holdings = []
        try:
            portfolio_data = get_portfolio_data(user_id, portfolio_id, subscription_level)
            holdings = (portfolio_data or {}).get("holdings") or []
            portfolio = (portfolio_data or {}).get("portfolio") or {}
        except APIError as e:
            st.error(f"Failed to load holdings: {e}")
            portfolio = {}

        c1, c2 = st.columns(2)
        c1.metric("Total Holdings", len(holdings))
        c2.metric("Total Value", f"${portfolio.get('total_value', 0):,.2f}" if portfolio.get("total_value") else "N/A")

        if holdings:
            df = pd.DataFrame(holdings)
            # fundamental health flag — the 'how is the company' axis,
            # joined from the python worker's canonical flag
            try:
                _fmap = {r["symbol"]: r for r in
                         get_python_api_client().get(
                             "api/v1/board/fund-flags") or []}
                _FI = {"accelerating": "🟢⚡", "growing": "🟢",
                       "watch": "🟡", "cyclical": "🔵", "slowing": "🟠",
                       "declining": "🔻", "deteriorating": "🔴",
                       "unknown": "⚪"}
                df["fund"] = df["symbol"].map(
                    lambda s: (lambda f: f"{_FI.get(f.get('state'), '⚪')} {f.get('state') or '—'}")
                    (_fmap.get(str(s).upper()) or {}))
                df["risk"] = df["symbol"].map(
                    lambda s: (_fmap.get(str(s).upper()) or {}).get("risk"))
                df["f_alert"] = df["symbol"].map(
                    lambda s: (_fmap.get(str(s).upper()) or {}).get("alert"))
            except Exception:
                pass
            fv_cols = [c for c in ("fair_value", "fair_value_regime", "fair_value_as_of") if c in df.columns]
            preferred = [c for c in ("symbol", "fund", "risk", "f_alert",
                                     "quantity", "avg_price", "current_price",
                                     "unrealized_gain_loss_percent") if c in df.columns]
            st.dataframe(
                health_col(df[preferred + fv_cols +
                              [c for c in df.columns
                               if c not in preferred + fv_cols]]),
                column_config={"🩺": health_cfg()},
                use_container_width=True, hide_index=True)
        else:
            st.info("No holdings in this portfolio")

        st.markdown("---")
        col_add, col_update, col_delete = st.columns(3)

        with col_add:
            st.markdown("**Add Holding**")
            add_symbol = st.text_input("Symbol", key="pm_add_symbol")
            add_qty = st.number_input("Quantity", min_value=0.0, value=0.0, step=1.0, key="pm_add_qty")
            add_avg = st.number_input("Avg Entry Price", min_value=0.0, value=0.0, step=0.01, key="pm_add_avg")
            add_purchase_date = st.date_input("Purchase Date", key="pm_add_date")
            if st.button("➕ Add", key="pm_add_btn", type="primary"):
                symbol = (add_symbol or "").strip().upper()
                if not symbol or add_qty <= 0:
                    st.error("Symbol and quantity > 0 required")
                else:
                    try:
                        created = client.post(
                            f"api/v1/portfolio/{user_id}/{portfolio_id}/holdings",
                            json_data={
                                "stock_symbol": symbol,
                                "quantity": float(add_qty),
                                "avg_entry_price": float(add_avg),
                                "position_type": "long",
                                "purchase_date": add_purchase_date.strftime("%Y-%m-%d"),
                            },
                        )
                        fv = created.get("fair_value")
                        st.success(f"Added {symbol}" + (f" · fair value {fv}" if fv else " · FV warming up"))
                        st.rerun()
                    except APIError as e:
                        st.error(f"Failed to add holding: {e}")

        holding_options = {
            f"{h.get('symbol', '?')} ({str(h.get('id', ''))[:8]})": h.get("id")
            for h in holdings if h.get("id")
        }

        with col_update:
            st.markdown("**Update Holding**")
            upd_label = st.selectbox("Holding", options=list(holding_options.keys()), key="pm_upd_holding")
            upd_id = holding_options.get(upd_label)
            upd_qty = st.number_input("New Quantity", min_value=0.0, value=0.0, step=1.0, key="pm_upd_qty")
            upd_avg = st.number_input("New Avg Price", min_value=0.0, value=0.0, step=0.01, key="pm_upd_avg")
            if st.button("✏️ Update", key="pm_upd_btn"):
                payload = {}
                if upd_qty > 0:
                    payload["quantity"] = float(upd_qty)
                if upd_avg > 0:
                    payload["avg_price"] = float(upd_avg)
                if not upd_id:
                    st.error("Select a holding")
                elif not payload:
                    st.error("Provide quantity and/or avg price")
                else:
                    try:
                        client.put(f"api/v1/holdings/{upd_id}", json_data=payload)
                        st.success("Holding updated")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Failed to update holding: {e}")

        with col_delete:
            st.markdown("**Delete Holding**")
            del_label = st.selectbox("Holding ", options=list(holding_options.keys()), key="pm_del_holding")
            del_id = holding_options.get(del_label)
            if st.button("🗑️ Delete", key="pm_del_btn"):
                if not del_id:
                    st.error("Select a holding")
                else:
                    try:
                        client.delete(f"api/v1/holdings/{del_id}")
                        st.success("Holding deleted")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Failed to delete holding: {e}")


# --- Watchlist ------------------------------------------------------------------
with tab_watchlist:
    if not user_id:
        st.info("Select a user to manage watchlists.")
    else:
        watchlists = []
        try:
            resp = client.get(f"api/v1/watchlists/user/{user_id}")
            watchlists = (resp or {}).get("watchlists") or []
        except APIError as e:
            st.error(f"Failed to load watchlists: {e}")

        col_w1, col_w2 = st.columns([2, 1])
        with col_w1:
            wl_options = {w.get("watchlist_name", w.get("watchlist_id", "?")): w.get("watchlist_id")
                          for w in watchlists if w.get("watchlist_id")}
            wl_label = st.selectbox("Watchlist", options=list(wl_options.keys()), key="pm_wl")
            watchlist_id = wl_options.get(wl_label)
        with col_w2:
            new_wl_name = st.text_input("New watchlist name", key="pm_new_wl")
            if st.button("Create Watchlist", key="pm_create_wl"):
                if not new_wl_name.strip():
                    st.error("Name required")
                else:
                    try:
                        client.post("api/v1/watchlists", params={"user_id": user_id},
                                    json_data={"watchlist_name": new_wl_name.strip(),
                                               "subscription_level_required": "basic"})
                        st.success("Watchlist created")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Failed: {e}")

        if watchlist_id:
            try:
                wl_detail = client.get(f"api/v1/watchlists/{watchlist_id}") or {}
            except APIError as e:
                wl_detail = {}
                st.error(f"Failed to load watchlist: {e}")
            items = wl_detail.get("items") or wl_detail.get("stocks") or []

            if items:
                st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
            else:
                st.info("Watchlist is empty — add symbols below to include them in the alert scan.")

            st.markdown("**Add symbol to watchlist**")
            wi_cols = st.columns([2, 1, 1])
            wi_symbol = wi_cols[0].text_input("Symbol ", key="pm_wi_symbol")
            wi_notes = wi_cols[1].text_input("Notes (optional)", key="pm_wi_notes")
            if wi_cols[2].button("➕ Add to watchlist", key="pm_wi_add"):
                sym = (wi_symbol or "").strip().upper()
                if not sym:
                    st.error("Symbol required")
                else:
                    try:
                        client.post(f"api/v1/watchlists/{watchlist_id}/items",
                                    json_data={"stock_symbol": sym, "notes": wi_notes or None, "priority": 0})
                        st.success(f"Added {sym} — included in next alert scan")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Failed: {e}")

            if items:
                st.markdown("**Remove symbol**")
                item_options = {
                    f"{(i.get('symbol') or i.get('stock_symbol') or '?')} ({str(i.get('id', ''))[:8]})": i.get("id")
                    for i in items if i.get("id")
                }
                rm_cols = st.columns([3, 1])
                rm_label = rm_cols[0].selectbox("Item", options=list(item_options.keys()), key="pm_wi_rm")
                if rm_cols[1].button("🗑️ Remove", key="pm_wi_rm_btn"):
                    try:
                        client.delete(f"api/v1/watchlist-items/{item_options[rm_label]}")
                        st.success("Removed")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Failed: {e}")

            st.markdown("---")
            del_wl = st.checkbox("Delete this watchlist", key="pm_wl_del_confirm")
            if st.button("🗑️ Delete Watchlist", key="pm_wl_del_btn", disabled=not del_wl):
                try:
                    client.delete(f"api/v1/watchlists/{watchlist_id}")
                    st.success("Watchlist deleted")
                    st.rerun()
                except APIError as e:
                    st.error(f"Failed: {e}")
        elif not watchlists:
            st.info("No watchlists yet — create one above.")


# --- Portfolios -----------------------------------------------------------------
with tab_portfolios:
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**Create Portfolio**")
        new_name = st.text_input("Portfolio Name", key="pm_p_create_name")
        if st.button("➕ Create", key="pm_p_create_btn"):
            if not user_id or not new_name.strip():
                st.error("User and name required")
            else:
                try:
                    resp = client.post(f"api/v1/portfolio/{user_id}",
                                       json_data={"portfolio_name": new_name.strip()})
                    st.success(f"Created: {resp.get('portfolio_id')}")
                    st.rerun()
                except APIError as e:
                    st.error(f"Failed: {e}")

    with c2:
        st.markdown("**Rename Portfolio**")
        upd_name = st.text_input("New Name", key="pm_p_upd_name")
        upd_notes = st.text_area("Notes", key="pm_p_upd_notes")
        if st.button("✏️ Update", key="pm_p_upd_btn"):
            if not portfolio_id:
                st.error("Select a portfolio")
            else:
                try:
                    client.put(f"api/v1/portfolio/{user_id}/{portfolio_id}",
                               json_data={"portfolio_name": upd_name, "notes": upd_notes})
                    st.success("Updated")
                    st.rerun()
                except APIError as e:
                    st.error(f"Failed: {e}")

    with c3:
        st.markdown("**Delete Portfolio**")
        st.warning("Deletes the portfolio and its holdings.")
        del_confirm = st.checkbox("Confirm delete", key="pm_p_del_confirm")
        if st.button("🗑️ Delete", key="pm_p_del_btn", disabled=not del_confirm):
            try:
                client.delete(f"api/v1/portfolio/{user_id}/{portfolio_id}")
                st.success("Deleted")
                st.rerun()
            except APIError as e:
                st.error(f"Failed: {e}")

    st.markdown("---")
    with st.expander("📧 Notification Email"):
        if not user_id:
            st.info("Select a user first")
        else:
            email_key = f"pm_email::{user_id}"
            loaded_key = f"pm_email_loaded::{user_id}"
            if not st.session_state.get(loaded_key):
                try:
                    me = client.get("api/v1/me", headers={"X-User-Id": user_id})
                    st.session_state[email_key] = (me or {}).get("email") or ""
                except Exception as e:
                    st.error(f"Failed to load email: {e}")
                st.session_state[loaded_key] = True
            st.text_input("Email", key=email_key, placeholder="trader@example.com",
                          help="Used for alert notifications")
            if st.button("Save email", key="pm_email_save"):
                try:
                    client.patch("api/v1/me",
                                 json_data={"email": st.session_state.get(email_key, "").strip()},
                                 headers={"X-User-Id": user_id})
                    st.success("Saved")
                except Exception as e:
                    st.error(f"Failed: {e}")


# --- Weekly Changes ---------------------------------------------------------------
with tab_weekly:
    st.caption("Weekly health run + change detection for the selected portfolio.")
    wc_pid = st.text_input("Portfolio ID", value=portfolio_id or st.session_state.get("portfolio_id", ""),
                           key="pm_wc_pid")
    wc_cols = st.columns(3)
    wc_as_of = wc_cols[0].text_input("As of date (YYYY-MM-DD)",
                                     value=datetime.utcnow().strftime("%Y-%m-%d"), key="pm_wc_asof")
    wc_lookback = wc_cols[1].number_input("Lookback days", min_value=7, max_value=60, value=14, key="pm_wc_lb")
    wc_email = wc_cols[2].text_input("Email to (optional)", key="pm_wc_email")

    wc_c1, wc_c2, wc_c3 = st.columns(3)
    if wc_c1.button("Run Weekly Health Now", key="pm_wc_run"):
        if not wc_pid:
            st.error("Portfolio ID required")
        else:
            resp = client.post(f"/api/v1/portfolios/{wc_pid}/analysis-run",
                               json_data={"symbols": [], "profile": "weekly_health",
                                          "target_date": wc_as_of, "asset_type": "stock"})
            st.success(f"Enqueued run_id={resp.get('run_id')}")

    if wc_c2.button("Refresh Changes", key="pm_wc_refresh"):
        if not wc_pid:
            st.error("Portfolio ID required")
        else:
            resp = client.get(f"/api/v1/portfolios/{wc_pid}/weekly-health/changes",
                              params={"as_of_date": wc_as_of, "lookback_days": int(wc_lookback)})
            st.session_state["pm_wc_changes"] = (resp.get("data") or {}).get("changes") or []

    if wc_c3.button("Send Email Summary", key="pm_wc_email_btn"):
        if not wc_pid or not wc_email:
            st.error("Portfolio ID and recipient email required")
        else:
            resp = client.post(f"/api/v1/portfolios/{wc_pid}/weekly-health/email",
                               json_data={"portfolio_id": wc_pid, "as_of_date": wc_as_of,
                                          "recipient_email": wc_email, "lookback_days": int(wc_lookback)})
            st.success("Email queued") if resp.get("success") else st.error(resp.get("error") or "failed")

    changes = st.session_state.get("pm_wc_changes") or []
    if changes:
        rows = [{
            "symbol": c.get("symbol"), "action": c.get("action"),
            "prev_action": c.get("prev_action"), "overall_score": c.get("overall_score"),
            "delta": c.get("delta"), "valuation_score": c.get("valuation_score"),
            "reasons_top": "; ".join(str(r) for r in (c.get("reasons") or [])[:5]),
        } for c in changes]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No changes loaded — click 'Refresh Changes'.")
