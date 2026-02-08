"""
Portfolio Management Page
Full CRUD operations for portfolios and holdings
"""
import streamlit as st
import sys
import os
import pandas as pd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from shared_functions import get_portfolio_data
from api_client import get_go_api_client, APIError

setup_page_config("Portfolio Management", "💼")

st.title("💼 Portfolio Management")

# Sidebar
subscription_level = render_sidebar()


def _load_me_email_for_user(user_id: str) -> str:
    if not user_id:
        return ""
    client = get_go_api_client()
    me = client.get("api/v1/me", headers={"X-User-Id": user_id})
    return (me or {}).get("email") or ""


def _save_me_email_for_user(user_id: str, email: str) -> str:
    if not user_id:
        raise ValueError("user_id is required")
    client = get_go_api_client()
    updated = client.patch(
        "api/v1/me",
        json_data={"email": (email or "").strip()},
        headers={"X-User-Id": user_id},
    )
    return (updated or {}).get("email") or (email or "").strip()

# Tabs for different operations
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 View", "➕ Create", "✏️ Update", "🗑️ Delete", "📊 Analytics"])


def _load_users():
    client = get_go_api_client()
    resp = client.get("api/v1/users")
    users = (resp or {}).get("users") or []
    return users


def _load_portfolios_for_user(user_id: str):
    if not user_id:
        return []
    client = get_go_api_client()
    resp = client.get(f"api/v1/portfolios/user/{user_id}")
    portfolios = (resp or {}).get("portfolios") or []
    return portfolios


users = []
try:
    users = _load_users()
except APIError as e:
    st.error(f"❌ Failed to load users: {e}")

user_options = {f"{u.get('username', 'unknown')} ({u.get('subscription_level', 'basic')})": u.get('user_id') for u in users if u.get('user_id')}

_base_portfolio_owner_user_id = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
_default_user_index = 0
_user_labels = list(user_options.keys()) if user_options else []
for i, label in enumerate(_user_labels):
    if user_options.get(label) == _base_portfolio_owner_user_id:
        _default_user_index = i
        break

selected_user_label = st.selectbox(
    "User",
    options=_user_labels,
    index=_default_user_index if _user_labels else 0,
    key="portfolio_selected_user",
)
selected_user_id = user_options.get(selected_user_label)


with st.expander("📧 Notification Email", expanded=True):
    if not selected_user_id:
        st.info("Select a user to view/update the notification email")
    else:
        email_state_key = f"portfolio_me_email::{selected_user_id}"
        loaded_state_key = f"portfolio_me_email_loaded::{selected_user_id}"

        if not st.session_state.get(loaded_state_key):
            try:
                st.session_state[email_state_key] = _load_me_email_for_user(selected_user_id)
            except Exception as e:
                st.error(f"❌ Failed to load current email: {e}")
            st.session_state[loaded_state_key] = True

        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("Reload", key=f"reload_email::{selected_user_id}"):
                try:
                    st.session_state[email_state_key] = _load_me_email_for_user(selected_user_id)
                    st.success("Loaded")
                except Exception as e:
                    st.error(f"❌ Failed to load current email: {e}")

        with col_b:
            if st.button("Save", key=f"save_email::{selected_user_id}", type="primary"):
                try:
                    updated_email = _save_me_email_for_user(selected_user_id, st.session_state.get(email_state_key, ""))
                    st.session_state[email_state_key] = updated_email
                    st.success("Saved")
                except Exception as e:
                    st.error(f"❌ Failed to update email: {e}")

        st.text_input(
            "Email",
            key=email_state_key,
            placeholder="trader@example.com",
            help="This email is used for alert notifications for the selected user",
        )

portfolios = []
portfolio_options = {}
if selected_user_id:
    try:
        portfolios = _load_portfolios_for_user(selected_user_id)
        portfolio_options = {p.get('name', p.get('id', 'unknown')): p.get('id') for p in portfolios if p.get('id')}
    except APIError as e:
        st.error(f"❌ Failed to load portfolios: {e}")

with tab1:
    st.subheader("View Portfolio")
    user_id = st.text_input("User ID", value=selected_user_id or "", key="view_user", disabled=True)
    portfolio_label = st.selectbox(
        "Portfolio",
        options=list(portfolio_options.keys()) if portfolio_options else [],
        key="view_portfolio_label",
    )
    portfolio_id = portfolio_options.get(portfolio_label)
    
    if st.button("Load Portfolio", key="load_portfolio"):
        if user_id and portfolio_id:
            with st.spinner("Loading portfolio..."):
                try:
                    portfolio_data = get_portfolio_data(user_id, portfolio_id, subscription_level)
                    if portfolio_data:
                        portfolio = portfolio_data.get("portfolio") or {}
                        holdings = portfolio_data.get("holdings") or []
                        signals = portfolio_data.get("signals") or []
                        
                        st.success(f"✅ Portfolio loaded: {portfolio.get('portfolio_name', 'N/A')}")
                        
                        # Portfolio info
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Holdings", len(holdings))
                        with col2:
                            st.metric("Total Value", f"${portfolio.get('total_value', 0):,.2f}" if portfolio.get('total_value') else "N/A")
                        with col3:
                            st.metric("Signals", len(signals))
                        
                        # Holdings table
                        if holdings:
                            st.subheader("Holdings")
                            df_holdings = pd.DataFrame(holdings)
                            st.dataframe(df_holdings, use_container_width=True)
                        
                        # Signals
                        if signals and subscription_level in ["pro", "elite"]:
                            st.subheader("Trading Signals")
                            df_signals = pd.DataFrame(signals)
                            st.dataframe(df_signals, use_container_width=True)
                except APIError as e:
                    st.error(f"❌ Error: {e}")

with tab2:
    st.subheader("Create Portfolio")
    user_id = st.text_input("User ID", value=selected_user_id or "", key="create_user", disabled=True)
    portfolio_name = st.text_input("Portfolio Name", key="create_name")
    portfolio_type = st.selectbox("Type", ["long_term", "swing", "options"], key="create_type")
    
    if st.button("Create Portfolio", key="create_portfolio"):
        # Validate inputs
        user_id = user_id.strip() if user_id else ""
        portfolio_name = portfolio_name.strip() if portfolio_name else ""
        
        if not user_id:
            st.error("❌ User ID is required")
        elif not portfolio_name:
            st.error("❌ Portfolio Name is required")
        else:
            try:
                client = get_go_api_client()
                # user_id must be in URL path, not in JSON body
                # Route: POST /api/v1/portfolio/:user_id
                endpoint = f"api/v1/portfolio/{user_id}"
                response = client.post(
                    endpoint,
                    json_data={
                        "portfolio_name": portfolio_name
                    }
                )
                st.success(f"✅ Portfolio created: {response.get('portfolio_id')}")
                st.json(response)
            except APIError as e:
                st.error(f"❌ API Error: {e}")
                st.info(f"💡 Endpoint called: POST {endpoint}")
                st.info(f"💡 User ID: '{user_id}', Portfolio Name: '{portfolio_name}'")
            except Exception as e:
                st.error(f"❌ Error: {e}")

with tab3:
    st.subheader("Update Portfolio")
    user_id = st.text_input("User ID", value=selected_user_id or "", key="update_user", disabled=True)
    portfolio_label = st.selectbox(
        "Portfolio",
        options=list(portfolio_options.keys()) if portfolio_options else [],
        key="update_portfolio_label",
    )
    portfolio_id = portfolio_options.get(portfolio_label)
    new_name = st.text_input("New Name", key="update_name")
    notes = st.text_area("Notes", key="update_notes")
    
    if st.button("Update Portfolio", key="update_portfolio"):
        try:
            client = get_go_api_client()
            # user_id must be in URL path
            response = client.put(
                f"api/v1/portfolio/{user_id}/{portfolio_id}",
                json_data={"portfolio_name": new_name, "notes": notes}
            )
            st.success("✅ Portfolio updated")
            st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

    st.markdown("---")
    st.subheader("Holdings (Stocks)")

    if not user_id or not portfolio_id:
        st.info("Select a user and portfolio above to manage holdings.")
    else:
        holdings = []
        try:
            portfolio_data = get_portfolio_data(user_id, portfolio_id, subscription_level)
            holdings = (portfolio_data or {}).get("holdings") or []
        except APIError as e:
            st.error(f"❌ Failed to load holdings: {e}")

        if holdings:
            st.dataframe(pd.DataFrame(holdings), use_container_width=True)
        else:
            st.info("No holdings found for this portfolio")

        col_add, col_update, col_delete = st.columns(3)

        with col_add:
            st.markdown("**Add Holding**")
            add_symbol = st.text_input("Symbol", key="add_holding_symbol")
            add_qty = st.number_input("Quantity", min_value=0.0, value=0.0, step=1.0, key="add_holding_qty")
            add_avg = st.number_input("Avg Entry Price", min_value=0.0, value=0.0, step=0.01, key="add_holding_avg")
            add_position_type = st.selectbox("Position Type", ["long"], key="add_holding_position_type")
            add_purchase_date = st.date_input("Purchase Date", key="add_holding_purchase_date")

            if st.button("➕ Add", key="add_holding_btn"):
                symbol = (add_symbol or "").strip().upper()
                if not symbol:
                    st.error("❌ Symbol is required")
                elif add_qty <= 0:
                    st.error("❌ Quantity must be > 0")
                else:
                    try:
                        client = get_go_api_client()
                        client.post(
                            f"api/v1/portfolio/{user_id}/{portfolio_id}/holdings",
                            json_data={
                                "stock_symbol": symbol,
                                "quantity": float(add_qty),
                                "avg_entry_price": float(add_avg),
                                "position_type": add_position_type,
                                "purchase_date": add_purchase_date.strftime("%Y-%m-%d"),
                            },
                        )
                        st.success(f"✅ Added holding: {symbol}")
                        st.rerun()
                    except APIError as e:
                        st.error(f"❌ Failed to add holding: {e}")

        holding_options = {
            f"{h.get('symbol', 'UNKNOWN')} ({str(h.get('id', ''))[:8]})": h.get("id")
            for h in holdings
            if h.get("id")
        }

        with col_update:
            st.markdown("**Update Holding**")
            update_holding_label = st.selectbox(
                "Holding",
                options=list(holding_options.keys()) if holding_options else [],
                key="update_holding_label",
            )
            update_holding_id = holding_options.get(update_holding_label)
            update_qty = st.number_input(
                "New Quantity",
                min_value=0.0,
                value=0.0,
                step=1.0,
                key="update_holding_qty",
            )
            update_avg = st.number_input(
                "New Avg Price",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key="update_holding_avg",
            )

            if st.button("✏️ Update", key="update_holding_btn"):
                if not update_holding_id:
                    st.error("❌ Select a holding")
                else:
                    payload = {}
                    if update_qty > 0:
                        payload["quantity"] = float(update_qty)
                    if update_avg > 0:
                        payload["avg_price"] = float(update_avg)
                    if not payload:
                        st.error("❌ Provide at least one field (quantity or avg price)")
                    else:
                        try:
                            client = get_go_api_client()
                            client.put(
                                f"api/v1/holdings/{update_holding_id}",
                                json_data=payload,
                            )
                            st.success("✅ Holding updated")
                            st.rerun()
                        except APIError as e:
                            st.error(f"❌ Failed to update holding: {e}")

        with col_delete:
            st.markdown("**Delete Holding**")
            delete_holding_label = st.selectbox(
                "Holding ",
                options=list(holding_options.keys()) if holding_options else [],
                key="delete_holding_label",
            )
            delete_holding_id = holding_options.get(delete_holding_label)
            if st.button("🗑️ Delete", key="delete_holding_btn", type="primary"):
                if not delete_holding_id:
                    st.error("❌ Select a holding")
                else:
                    try:
                        client = get_go_api_client()
                        client.delete(f"api/v1/holdings/{delete_holding_id}")
                        st.success("✅ Holding deleted")
                        st.rerun()
                    except APIError as e:
                        st.error(f"❌ Failed to delete holding: {e}")

with tab4:
    st.subheader("Delete Portfolio")
    user_id = st.text_input("User ID", value=selected_user_id or "", key="delete_user", disabled=True)
    portfolio_label = st.selectbox(
        "Portfolio",
        options=list(portfolio_options.keys()) if portfolio_options else [],
        key="delete_portfolio_label",
    )
    portfolio_id = portfolio_options.get(portfolio_label)
    
    if st.button("Delete Portfolio", key="delete_portfolio", type="primary"):
        try:
            client = get_go_api_client()
            # user_id must be in URL path
            response = client.delete(f"api/v1/portfolio/{user_id}/{portfolio_id}")
            st.success("✅ Portfolio deleted")
            st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

with tab5:
    st.subheader("Portfolio Analytics")
    st.info("📊 Portfolio analytics and performance metrics (Pro/Elite feature)")

