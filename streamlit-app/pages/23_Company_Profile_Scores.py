import streamlit as st
import pandas as pd
from datetime import date

from api_client import APIClient, APIError
from api_config import api_config
import os


st.set_page_config(page_title="Company Profile Scores", layout="wide")

python_api_url = api_config.python_worker_url
if python_api_url.startswith("http://python-worker:") and not os.path.exists("/.dockerenv"):
    python_api_url = "http://localhost:8001"
client = APIClient(python_api_url, timeout=30)

st.title("Company Profile Scores")
st.caption("Manual, versioned, historical qualitative scores (moat/leadership/recurring/AI optionality).")

colA, colB, colC = st.columns([2, 1, 1])
with colA:
    symbol = st.text_input("Symbol", value="NVDA").strip().upper()
with colB:
    as_of_date = st.date_input("As-of date", value=date.today())
with colC:
    scoring_version = st.text_input("Scoring version", value="v1").strip() or "v1"

st.divider()

top_left, top_right = st.columns([1, 1])
with top_left:
    st.subheader("Auto profile (from FMP-backed data)")
    st.caption("Computes proxy scores using stored key-metrics, financial-scores, and transcript signals.")
    if st.button("Update Profile (from FMP)", use_container_width=True):
        try:
            res = client.post(
                "/api/v1/company-profile-scores/auto/compute",
                json_data={
                    "symbol": symbol,
                    "as_of_date": as_of_date.isoformat(),
                    "scoring_version": scoring_version,
                    "persist": True,
                },
            )
            st.success("Auto profile updated")
            st.session_state["auto_profile_latest"] = (res or {}).get("row")
        except APIError as e:
            st.error(str(e))

with top_right:
    st.subheader("Latest profile overlay")
    try:
        auto_latest = st.session_state.get("auto_profile_latest")
        if auto_latest is None:
            auto_latest = client.get(
                "/api/v1/company-profile-scores/auto/latest",
                params={
                    "symbol": symbol,
                    "as_of_date": as_of_date.isoformat(),
                    "scoring_version": scoring_version,
                },
            ).get("row")
        manual_latest = client.get(
            "/api/v1/company-profile-scores/latest",
            params={"symbol": symbol, "scoring_version": scoring_version},
        ).get("row")
        effective = manual_latest or auto_latest

        st.caption("Effective = manual if present, else auto")
        st.write("Manual")
        st.json(manual_latest or {})
        st.write("Auto")
        st.json(auto_latest or {})
        st.write("Effective")
        st.json(effective or {})
    except APIError as e:
        st.error(str(e))

left, right = st.columns([1, 1])

with left:
    st.subheader("Upsert manual scores")
    moat = st.slider("Moat score", 0, 100, 70)
    leadership = st.slider("Leadership score", 0, 100, 70)
    recurring = st.slider("Recurring revenue score", 0, 100, 60)
    ai_opt = st.slider("AI optionality score", 0, 100, 75)

    reason = st.text_area(
        "Reason JSON (optional)",
        value='{"notes": ""}',
        height=120,
    )

    if st.button("Save / Upsert", use_container_width=True):
        try:
            payload = {
                "symbol": symbol,
                "as_of_date": as_of_date.isoformat(),
                "scoring_version": scoring_version,
                "moat_score": float(moat),
                "leadership_score": float(leadership),
                "recurring_revenue_score": float(recurring),
                "ai_optionality_score": float(ai_opt),
            }
            # Keep reason_json optional + safe
            try:
                import json

                payload["reason_json"] = json.loads(reason) if reason.strip() else {}
            except Exception:
                payload["reason_json"] = {"raw": reason}

            res = client.post("/api/v1/company-profile-scores/upsert", json_data=payload)
            st.success("Saved")
            st.json(res)
        except APIError as e:
            st.error(str(e))

with right:
    st.subheader("History")
    lim = st.number_input("History limit", min_value=10, max_value=500, value=60, step=10)

    if st.button("Load history", use_container_width=True):
        try:
            res = client.get(
                "/api/v1/company-profile-scores/history",
                params={"symbol": symbol, "limit": int(lim)},
            )
            rows = (res or {}).get("rows") or []
            if not rows:
                st.info("No rows")
            else:
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True)
        except APIError as e:
            st.error(str(e))

st.divider()

st.subheader("Investment score (roll-up)")
st.caption("Computes + persists investment_scores row, blending quant business quality with manual profile scores.")

if st.button("Compute investment score now", use_container_width=True):
    try:
        res = client.post(
            "/api/v1/investment-scores/compute",
            json_data={
                "symbol": symbol,
                "as_of_date": as_of_date.isoformat(),
                "scoring_version": scoring_version,
                "persist": True,
            },
        )
        st.success("Computed")
        st.json(res)
    except APIError as e:
        st.error(str(e))
