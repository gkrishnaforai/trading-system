import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from api_config import api_config
from api_client import APIClient, APIError


def _bucket_color(score):
    if score is None:
        return "#6b7280"  # gray
    if score >= 70:
        return "#16a34a"  # green
    if score >= 50:
        return "#f59e0b"  # amber
    return "#dc2626"  # red


def _render_score_card(title: str, score, series):
    color = _bucket_color(score)
    st.markdown(
        f"""
        <div style="padding: 0.75rem 0.75rem; border-radius: 0.75rem; border: 1px solid rgba(255,255,255,0.08);">
          <div style="font-size: 0.9rem; color: rgba(255,255,255,0.75);">{title}</div>
          <div style="font-size: 1.6rem; font-weight: 700; color: {color};">{'' if score is None else int(round(score))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if series is not None and len(series) > 1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=series, mode="lines", line=dict(color=color, width=2)))
        fig.update_layout(
            height=70,
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)


st.set_page_config(page_title="Macro Dashboard", layout="wide")
st.title("📊 Macro Dashboard (MVP)")

python_base = api_config.python_worker_url.rstrip("/")
client = APIClient(python_base, timeout=60)

col_a, col_b = st.columns([1, 1])
with col_a:
    if st.button("Run Macro Update Now", use_container_width=True):
        try:
            res = client.post("/api/v1/macro/run", json_data={})
            st.success(res.get("message", "ran"))
            st.write(res)
        except APIError as e:
            st.error(str(e))

with col_b:
    st.caption(f"FastAPI: {python_base}")

try:
    latest = client.get("/api/v1/macro/latest")
    snap = (latest or {}).get("snapshot")
except APIError as e:
    st.error(str(e))
    st.stop()

if not snap:
    st.info("No macro snapshots found yet. Click 'Run Macro Update Now'.")
    st.stop()

as_of = snap.get("as_of_date")
module_scores = snap.get("module_scores") or {}
overall = snap.get("overall_score")
regime = snap.get("regime_probs") or {}
alloc = snap.get("portfolio_alloc") or {}

st.markdown("---")

header1, header2, header3, header4 = st.columns([1, 1, 1, 1])
with header1:
    st.metric("Overall Macro Score", "" if overall is None else f"{int(round(overall))}")
with header2:
    if regime:
        top = sorted(regime.items(), key=lambda x: x[1], reverse=True)[0]
        st.metric("Current Regime", f"{top[0]} ({int(round(top[1]*100))}%)")
    else:
        st.metric("Current Regime", "N/A")
with header3:
    st.metric("Last Updated", as_of or "N/A")
with header4:
    st.metric("Allocation", f"G {int(round(alloc.get('growth',0)*100))}% / V {int(round(alloc.get('value',0)*100))}% / C {int(round(alloc.get('cash',0)*100))}%")

# Fetch history for sparklines + charts
try:
    hist = client.get("/api/v1/macro/snapshots", params={"days": 540})
    snaps = (hist or {}).get("snapshots") or []
except APIError as e:
    st.error(str(e))
    st.stop()

if snaps:
    df = pd.DataFrame(snaps)
else:
    df = pd.DataFrame([])

st.subheader("Module Scores")
row1 = st.columns(8)
modules = ["growth", "labor", "inflation", "rates", "credit", "liquidity", "housing", "manufacturing"]
labels = {
    "growth": "Growth",
    "labor": "Labor",
    "inflation": "Inflation",
    "rates": "Rates",
    "credit": "Credit",
    "liquidity": "Liquidity",
    "housing": "Housing",
    "manufacturing": "Manufacturing",
}

for i, m in enumerate(modules):
    with row1[i]:
        score = (module_scores.get(m) or {}).get("score")
        series = None
        if not df.empty and "module_scores" in df.columns:
            try:
                series = [((x or {}).get(m) or {}).get("score") for x in df["module_scores"].tolist()]
            except Exception:
                series = None
        _render_score_card(labels[m], score, series)

st.markdown("---")

c1, c2 = st.columns([2, 1])

with c1:
    st.subheader("Macro Score Trend")
    if not df.empty:
        y = df["overall_score"].tolist()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["as_of_date"], y=y, mode="lines", line=dict(color="#60a5fa", width=2)))
        fig.update_layout(height=260, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No history yet")

with c2:
    st.subheader("Regime Probabilities")
    if regime:
        reg_df = pd.DataFrame([{k: float(v) for k, v in regime.items()}])
        st.dataframe(reg_df.T.rename(columns={0: "prob"}).sort_values("prob", ascending=False))
    else:
        st.info("N/A")

st.markdown("---")

st.subheader("Portfolio Allocation History")
if not df.empty:
    growth_w = [((x or {}).get("growth") or 0) for x in df["portfolio_alloc"].tolist()]
    value_w = [((x or {}).get("value") or 0) for x in df["portfolio_alloc"].tolist()]
    cash_w = [((x or {}).get("cash") or 0) for x in df["portfolio_alloc"].tolist()]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["as_of_date"], y=growth_w, stackgroup="one", name="Growth"))
    fig.add_trace(go.Scatter(x=df["as_of_date"], y=value_w, stackgroup="one", name="Value"))
    fig.add_trace(go.Scatter(x=df["as_of_date"], y=cash_w, stackgroup="one", name="Cash"))
    fig.update_layout(height=260, margin=dict(l=0, r=0, t=30, b=0), yaxis=dict(tickformat="%"))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No allocation history yet")
