
import streamlit as st
from datetime import datetime

from utils import setup_page_config, render_sidebar
from api_client import get_go_api_client


setup_page_config("Weekly Changes", "📅")
st.title("📅 Weekly Changes")
render_sidebar()

client = get_go_api_client()

portfolio_id = st.text_input("Portfolio ID", value=st.session_state.get("portfolio_id", ""))

as_of_date = st.text_input("As of date (YYYY-MM-DD)", value=datetime.utcnow().strftime("%Y-%m-%d"))

lookback_days = st.number_input("Lookback days", min_value=7, max_value=60, value=14, step=1)

recipient_email = st.text_input("Email to (optional)", value="")

run_now = st.button("Run Weekly Health Now", use_container_width=True)
if run_now:
    if not portfolio_id:
        st.error("Portfolio ID is required")
    else:
        with st.spinner("Enqueueing weekly health jobs..."):
            resp = client.post(
                f"/api/v1/portfolios/{portfolio_id}/analysis-run",
                json_data={"symbols": [], "profile": "weekly_health", "target_date": as_of_date, "asset_type": "stock"},
            )
        st.success(f"Enqueued run_id={resp.get('run_id')}")

refresh = st.button("Refresh Changes", use_container_width=True)
if refresh:
    if not portfolio_id:
        st.error("Portfolio ID is required")
    else:
        with st.spinner("Loading changes..."):
            resp = client.get(
                f"/api/v1/portfolios/{portfolio_id}/weekly-health/changes",
                params={"as_of_date": as_of_date, "lookback_days": int(lookback_days)},
            )
        st.session_state.weekly_health_changes = (resp.get("data") or {}).get("changes") or []

changes = st.session_state.get("weekly_health_changes") or []
if changes:
    st.subheader("Changes")
    # Flatten a few useful fields for readability
    rows = []
    for c in changes:
        score = c.get("overall_score")
        reasons = c.get("reasons") or []
        reasons_s = "; ".join([str(r) for r in reasons[:5]])
        rows.append(
            {
                "symbol": c.get("symbol"),
                "action": c.get("action"),
                "prev_action": c.get("prev_action"),
                "overall_score": score,
                "delta": c.get("delta"),
                "valuation_score": c.get("valuation_score"),
                "reasons_top": reasons_s,
            }
        )
    st.dataframe(rows, use_container_width=True)
else:
    st.info("No changes loaded yet. Click 'Refresh Changes'.")

send_email = st.button("Send Email Summary", use_container_width=True)
if send_email:
    if not portfolio_id:
        st.error("Portfolio ID is required")
    elif not recipient_email:
        st.error("Recipient email is required")
    else:
        with st.spinner("Sending email..."):
            resp = client.post(
                f"/api/v1/portfolios/{portfolio_id}/weekly-health/email",
                json_data={
                    "portfolio_id": portfolio_id,
                    "as_of_date": as_of_date,
                    "recipient_email": recipient_email,
                    "lookback_days": int(lookback_days),
                },
            )
        if resp.get("success"):
            st.success("Email queued/sent")
        else:
            st.error(resp.get("error") or "failed to send email")
