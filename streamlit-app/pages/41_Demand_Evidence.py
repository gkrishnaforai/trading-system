# -*- coding: utf-8 -*-
"""Demand Evidence — review queue for the demand/capital-cycle layer.

Claims are facts extracted from filings, calls and manual notes.
They move canonical demand axes ONLY after human approval — drafts
have zero power. This page is the human-in-the-loop surface:
review → approve/reject → watch the profile + regime respond.
"""
from __future__ import annotations

import streamlit as st

from api_client import APIClient
from api_config import api_config

st.set_page_config(page_title="Demand Evidence", page_icon="🧾",
                   layout="wide")
client = APIClient(api_config.python_worker_url, timeout=120)

AXES = ["demand_model", "capex_sensitivity", "demand_durability",
        "utilization_health", "capital_funding_risk", "ai_monetization"]
SIGNALS = sorted([
    "utilization_rising", "utilization_falling", "capacity_sold_out",
    "capacity_idle", "rental_pricing_up", "rental_pricing_down",
    "contract_signed", "backlog_growth", "backlog_conversion",
    "backlog_declining", "renewal", "lease_commenced", "lease_delayed",
    "contract_cancelled", "churn", "delivery_missed",
    "prepayment_received", "debt_repaid", "fcf_positive",
    "debt_raised", "refinancing_risk", "dilution_announced",
    "covenant_issue", "credit_downgrade",
    "ai_revenue_disclosed", "ai_revenue_growing", "ai_product_launch",
    "ai_revenue_absent", "ai_pricing_pressure",
    "customer_capex_guidance_up", "customer_capex_guidance_down",
    "order_growth", "order_cancellation", "design_win",
    "inventory_build",
    "segment_disclosure", "business_model_shift",
    "revenue_mix_disclosed",
])

st.title("🧾 Demand evidence — review queue")
st.caption("Facts → validated claims → human approval → canonical "
           "demand axes. Drafts never move a classification.")

# ------------------------------------------------ market regime banner
try:
    reg = client.get("admin/ai-capex-regime?fresh=true")
    rg, warn = reg.get("regime") or {}, reg.get("warning") or {}
    c1, c2, c3 = st.columns([2, 2, 4])
    c1.metric("ai-capex regime", rg.get("regime", "—"))
    c2.metric("cycle warning", warn.get("score", "—"))
    groups = rg.get("groups") or {}
    c3.caption("groups: " + " · ".join(
        f"{k} `{v}`" for k, v in groups.items()) +
        f"  · {reg.get('n_claims', 0)} approved claims market-wide")
    if st.button("↻ recompute + persist today"):
        client.post("admin/ai-capex-regime/recompute", json_data={})
        st.toast("regime recomputed")
        st.rerun()
except Exception as e:
    st.info(f"market regime unavailable: {e}")

st.divider()

sym = st.text_input("symbol", value="NBIS").strip().upper()

# ------------------------------------------------ current profile
try:
    prof = client.get(f"admin/demand-profile/{sym}?fresh=true")
    p = prof.get("profile") or {}
    if p:
        cols = st.columns(6)
        for col, k in zip(cols, AXES):
            col.metric(k.replace("_", "\n"), p.get(k) or "—")
        dur = p.get("durability") or {}
        gate = p.get("gate") or {}
        st.caption(
            f"durability **{dur.get('score', '—')}**/100 "
            f"({dur.get('confidence', '—')}) · gate "
            f"`{gate.get('gate', '—')}` · LT-eligible "
            f"**{gate.get('long_term_eligible')}** · src "
            f"`{p.get('source')}` · impact ×{p.get('impact_mult')}")
        if p.get("conflicts"):
            st.warning("conflicts: " + ", ".join(p["conflicts"]))
except Exception as e:
    st.caption(f"profile unavailable: {e}")

# ------------------------------------------------ claims queue
try:
    ev = client.get(f"admin/demand-evidence/{sym}?include_drafts=true")
    claims = ev.get("claims") or []
except Exception as e:
    claims = []
    st.error(f"claims load failed: {e}")

st.subheader(f"claims — {sym} ({len(claims)})")
for c in claims:
    stt = c.get("status")
    icon = {"approved": "🟢", "draft": "🟡",
            "rejected": "🔴", "stale": "⚪"}.get(stt, "·")
    with st.container():
        cols = st.columns([1, 1.2, 1.2, 6, 1.6])
        cols[0].caption(icon)
        cols[1].caption(f"`{c.get('axis','')}`")
        cols[2].caption(f"`{c.get('signal','')}`")
        cols[3].caption(
            f"{c.get('claim','')[:140]} — {c.get('source','')}"
            + (f" · {str(c.get('source_date',''))[:10]}"
               if c.get("source_date") else ""))
        if stt == "draft":
            if cols[4].button("approve", key=f"a{c['id']}"):
                client.post(f"admin/demand-evidence/{c['id']}/status",
                            json_data={"status": "approved",
                                       "reviewed_by": "streamlit"})
                st.rerun()
            if cols[4].button("reject", key=f"r{c['id']}"):
                client.post(f"admin/demand-evidence/{c['id']}/status",
                            json_data={"status": "rejected",
                                       "reviewed_by": "streamlit"})
                st.rerun()
        else:
            cols[4].caption(f"`{stt}`")

# ------------------------------------------------ manual claim
with st.expander("➕ submit a claim manually"):
    with st.form("manual_claim"):
        f1, f2, f3 = st.columns(3)
        ax = f1.selectbox("axis", AXES)
        sig = f2.selectbox("signal", SIGNALS)
        conf = f3.selectbox("confidence", ["high", "medium", "low"])
        claim = st.text_input("claim — one fact as disclosed")
        ref = st.text_input("source ref (url / filing / quote)")
        sdate = st.date_input("source date")
        if st.form_submit_button("submit (manual → approved)"):
            try:
                client.post("admin/demand-evidence", json_data={
                    "symbol": sym, "axis": ax, "signal": sig,
                    "claim": claim, "source": "manual",
                    "source_ref": ref,
                    "source_date": str(sdate),
                    "confidence": conf,
                    "status": "approved"})
                st.success("claim recorded")
                st.rerun()
            except Exception as e:
                st.error(str(e))

# ------------------------------------------------ LLM extraction
with st.expander("🤖 extract claims from a filing / call excerpt"):
    st.caption("LLM produces DRAFTS only — nothing is written until "
               "you submit each claim through the queue above.")
    src = st.selectbox("source", ["filing", "earnings_call",
                                  "guidance", "news"])
    txt = st.text_area("excerpt", height=160,
                       placeholder="paste an 8-K / 10-Q / call "
                                   "transcript excerpt…")
    if st.button("extract drafts") and txt.strip():
        try:
            out = client.post("admin/demand-evidence/extract",
                              json_data={"symbol": sym, "text": txt,
                                         "source": src})
            st.session_state["extract_drafts"] = out.get("drafts") or []
            if not out.get("success"):
                st.warning(out.get("error") or "no drafts")
        except Exception as e:
            st.error(str(e))
    for i, dft in enumerate(st.session_state.get("extract_drafts") or []):
        st.markdown(
            f"- `{dft.get('axis')}` / `{dft.get('signal')}` "
            f"({dft.get('confidence')}) — {dft.get('claim')}")
        if st.button(f"submit draft {i+1} to queue",
                     key=f"draft{i}"):
            try:
                client.post("admin/demand-evidence", json_data={
                    "symbol": sym, "axis": dft.get("axis"),
                    "signal": dft.get("signal"),
                    "claim": dft.get("claim"),
                    "value": dft.get("value"),
                    "source": "llm_extract",
                    "source_ref": dft.get("source_ref"),
                    "source_date": dft.get("source_date"),
                    "confidence": dft.get("confidence")})
                st.success("submitted as draft — approve above")
                st.rerun()
            except Exception as e:
                st.error(str(e))
