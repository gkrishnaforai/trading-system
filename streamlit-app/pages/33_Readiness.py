"""Readiness Screener — the Stock Health readiness checklists run
board-wide. Pick a use case, see who's ready / close / blocked and why.
"""
import sys
import os

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient
from api_config import api_config
from utils import render_top_nav, sym_md

client = APIClient(api_config.python_worker_url, timeout=180)

st.set_page_config(page_title="Readiness", page_icon="✅", layout="wide")
render_top_nav()
st.title("✅ Readiness Screener")
st.caption("the same deterministic checklist as Stock Health — "
           "computed board-wide on stored engine data. Click a name "
           "for the full card; buttons there run the live engine eval.")


@st.cache_data(ttl=120, show_spinner="scoring the board…")
def _board():
    return client.get("api/v1/board/readiness") or {}


if st.button("🔄 recompute"):
    st.cache_data.clear()
    st.rerun()

B = _board()
secs = B.get("sections") or {}
counts = B.get("counts") or {}
if not secs:
    st.warning("no readiness data — run the momentum job to populate "
               "technicals")
    st.stop()

if B.get("as_of"):
    st.caption(f"technicals as of {str(B['as_of'])[:16]}Z — the hourly "
               "momentum job refreshes the inputs")

# --------------------------------------------- 🆕 movements
# journal diffs — readiness_evals (universe) + pulse_rule_evals
# (portfolio actions). Promotions first: no→ready is the money move.
try:
    tr = client.get("api/v1/board/transitions") or {}
except Exception:
    tr = {}
rd_tr = tr.get("readiness") or []
pu_tr = tr.get("pulse") or []
if rd_tr or pu_tr:
    with st.expander(f"🆕 moved since last eval — "
                     f"{len(rd_tr)} readiness · {len(pu_tr)} pulse",
                     expanded=True):
        prom = [r for r in rd_tr if r["state"] == "ready"]
        dem = [r for r in rd_tr if r["state"] == "no"]
        other = [r for r in rd_tr
                 if r["state"] not in ("ready", "no")]
        if prom:
            st.markdown("**🟢 promoted to ready**")
            for r in prom:
                st.markdown(f"- {sym_md(r['symbol'])} "
                            f"`{r['use_case']}` {r['prev_state']} → "
                            f"**ready** ({r['score']}/{r['of']})")
        if pu_tr:
            st.markdown("**pulse action changes**")
            _AI = {"add": "🟢", "reduce": "🔴", "trim": "🟡",
                   "avoid": "🔴", "watch": "🟡", "hold": "⚪"}
            for r in pu_tr:
                st.markdown(f"- {sym_md(r['symbol'])} "
                            f"{r['prev_action']} → "
                            f"{_AI.get(r['action'],'')}"
                            f"**{r['action']}** "
                            f"(`{r.get('matched_rule') or '—'}`)")
        if other:
            st.caption("improved/degraded (no state flip to ready): "
                       + " · ".join(
                           f"{r['symbol']} {r['use_case']} "
                           f"{r['prev_state']}→{r['state']}"
                           for r in other[:20]))
        if dem:
            st.caption("dropped to blocked: "
                       + " · ".join(
                           f"{r['symbol']} ({r['use_case']})"
                           for r in dem[:20]))

_UC = {"swing": "🎯 Swing — dip-buy entries",
       "invest": "🏦 Investing — long-hold entries",
       "leap_call": "📞 LEAP calls — 12-18mo bullish",
       "leap_put": "📕 LEAP puts — hedge/short"}
_RI = {"ready": "🟢 ready", "close": "🟡 close", "no": "🔴 blocked"}

uc = st.radio("use case", list(_UC), format_func=lambda k: _UC[k],
              horizontal=True, label_visibility="collapsed")
c = counts.get(uc) or {}
st.caption(f"**{c.get('ready',0)}** ready · **{c.get('close',0)}** "
           f"close · **{c.get('no',0)}** blocked of "
           f"{len(secs.get(uc) or [])} tracked")

only = st.segmented_control("show", ["ready", "ready + close", "all"],
                            default="ready + close")
rows = secs.get(uc) or []
if only == "ready":
    rows = [r for r in rows if r["state"] == "ready"]
elif only == "ready + close":
    rows = [r for r in rows if r["state"] in ("ready", "close")]

funds = st.text_input("filter", placeholder="symbol or name…").lower()
if funds:
    rows = [r for r in rows if funds in r["symbol"].lower()
            or funds in (r.get("name") or "").lower()]

st.divider()
cur = None
for r in rows:
    if r["state"] != cur:
        cur = r["state"]
        st.markdown(f"### {_RI.get(cur, cur)}")
    head, why = st.columns([2, 3])
    fv = r.get("fv_upside")
    head.markdown(
        f"{sym_md(r['symbol'])} — {r.get('name') or ''} · "
        f"`{r.get('mom') or '—'}` tape · `{r.get('fund') or '—'}` fund · "
        f"{r.get('score')}/{r.get('of')} rules"
        + (f" · rank **{r['rank']}**"
           if r.get("rank") is not None else "")
        + (f" · fv {fv:+.0f}%" if fv is not None else "")
        + (f" · PUT_ENTRY **{r['score']}** `{r['pe_band']}` "
           f"({'A' if r.get('pe_cat') == 'valuation_put' else 'B'})"
           if r.get("pe_band") else "")
        + (f" · **{r['catalyst']}**" if r.get("catalyst") else ""))
    note = ("blocking: " + " · ".join(r["fails"][:2])) \
        if r.get("fails") else ""
    if r.get("catalyst"):
        note += (" · " if note else "") + \
            "channel signal — pre-revenue evidence, unconfirmed"
    if note:
        why.caption(note)
