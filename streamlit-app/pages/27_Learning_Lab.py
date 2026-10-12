"""🧠 Learning Lab — is the system actually getting better?

Four sections:
  1. ENGINE STATUS   — every self-training engine: what it learns,
     last write, current state, and the milestone it's waiting on
  2. DATA ACCRUAL    — the memory tables: rows + freshness (learning
     stalls surface here instead of going silent)
  3. LEARNED CORRECTIONS — what the system changed about itself:
     dip:/gate: weight writes, meta report findings
  4. CALIBRATION     — does a higher score actually pay? score-decile
     vs realized returns, plus the capex snapshot trend

All reads of stored state — this page fetches nothing live.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import streamlit as st
from api_client import APIClient
from api_config import api_config
from utils import render_top_nav

st.set_page_config(page_title="Learning Lab", page_icon="🧠",
                   layout="wide")
render_top_nav()
client = APIClient(api_config.python_worker_url, timeout=180)

st.title("🧠 Learning Lab")
st.caption("every self-training engine, what it's learned, and what "
           "it's still waiting for — the accountability surface for "
           "the learning loop")

if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()


@st.cache_data(ttl=120)
def _lab():
    try:
        return client.get("api/v1/board/learning") or {}
    except Exception as e:
        return {"error": str(e)}


lab = _lab()
if lab.get("error"):
    st.error(f"worker unreachable: {lab['error']}")
    st.stop()

# ------------------------------------------------------------------
# 1. ENGINE STATUS
# ------------------------------------------------------------------
st.subheader("⚙️ Engines")
st.caption("each engine reads stored evidence and writes bounded "
           "corrections — nothing here executes trades")
for e in lab.get("engines") or []:
    ic = "🟢" if e.get("last") else ("🟡" if e.get("waiting") else "⚪")
    with st.expander(
            f"{ic} **{e['engine']}** — {e.get('state') or 'no state'} "
            f"· {e.get('cadence')}", expanded=False):
        st.caption(f"**learns:** {e['what']}")
        st.caption(f"**last write:** {e.get('last') or '—'} · cadence: "
                   f"{e.get('cadence')}")
        if e.get("waiting"):
            st.caption(f"⏳ **waiting on:** {e['waiting']}")
        else:
            st.caption("✅ no blocking milestone — fully armed")

# ------------------------------------------------------------------
# 2. DATA ACCRUAL — the memory tables
# ------------------------------------------------------------------
st.subheader("📦 Data accrual")
st.caption("learning only happens if evidence keeps landing — a table "
           "that stops growing is a stalled engine")

rows = []
for t, v in sorted((lab.get("tables") or {}).items()):
    n = v.get("rows") or 0
    rows.append({
        "table": t,
        "rows": n,
        "latest": v.get("latest") or "—",
        "status": ("🟢 accruing" if n and v.get("latest") else
                   "🟡 empty" if not n else "⚪"),
    })
st.dataframe(rows, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------
# 3. LEARNED CORRECTIONS — what the system changed about itself
# ------------------------------------------------------------------
st.subheader("🔧 Learned corrections")
learned = lab.get("learned") or []
writes = [l for l in learned if l["key"].startswith(("dip:", "gate:"))]
meta = next((l for l in learned if l["key"] == "meta:report"), None)

if not writes:
    st.caption("no learned weight writes yet — meta is still in its "
               "minimum-sample window; that's the system being "
               "honest, not broken")
for l in writes:
    v = l["value"] or {}
    if l["key"].startswith("dip:"):
        st.caption(f"`{l['key']}` → adj **{v.get('adj')}** "
                   f"(n={v.get('n')}, lift {v.get('lift')}) · "
                   f"{l['updated']}")
    elif l["key"].startswith("gate:"):
        st.caption(f"`{l['key']}` → enabled **{v.get('enabled')}** "
                   f"(n={v.get('n')}, med {v.get('med')}) · "
                   f"{l['updated']}")

if meta:
    mv = meta["value"] or {}
    st.markdown(f"**meta report** · ran {meta['updated']}")
    for n in mv.get("notes") or []:
        st.caption(f"· {n}")
    for w in mv.get("writes") or []:
        st.caption(f"✍️ {w}")
    lifts = mv.get("signal_lifts") or {}
    if lifts:
        with st.expander("signal lift detail", expanded=False):
            for sig, lf in lifts.items():
                w, wo = lf.get("with") or {}, lf.get("without") or {}
                st.caption(
                    f"`{sig}` with: n={w.get('n')} hit "
                    f"{w.get('hit')} med {w.get('med')} · "
                    f"without: n={wo.get('n')} hit {wo.get('hit')} "
                    f"med {wo.get('med')}")

# ------------------------------------------------------------------
# 4. CALIBRATION — does a higher score actually pay?
# ------------------------------------------------------------------
st.subheader("🎯 Calibration")
cal = lab.get("calibration")
if cal:
    st.caption("board score decile → realized 10d return · "
               "a monotone staircase = the weights are right; "
               "inversions mean the scoring is lying somewhere")
    def _f(x, spec):
        try:
            return format(float(x), spec)
        except (TypeError, ValueError):
            return str(x)
    rows = [{"score band": k, "n": v["n"],
             "hit rate": _f(v.get("hit"), ".0%"),
             "median ret": _f(v.get("med"), "+.1%")}
            for k, v in cal.items()]
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.caption("no calibration data yet — needs ≥5 graded outcomes per "
               "score band; accrues as board_outcomes fills")

# capex engine trend — the newest learner, plotted as it accrues
cx_hist = (lab.get("capex_history") or [])
if len(cx_hist) >= 2:
    import pandas as pd
    st.markdown("**🏗 AI capex slowdown score over time**")
    latest = cx_hist[-1].get("score")
    band = ("expansion" if latest < 25 else "normalization"
            if latest < 50 else "slowing" if latest < 70 else
            "serious slowdown" if latest < 85 else "contraction")
    up = len(cx_hist) >= 2 and latest > cx_hist[-2].get("score", latest)
    arrow = "📈 rising" if up else "📉 falling"
    st.caption(
        "**lower = healthier.** The score is *slowdown evidence*, not "
        "capex level — a line going **up** means the buildout is "
        "decelerating (bad for new-build names like VRT/CRDO/ALAB; "
        "rotate toward operators like IREN/NBIS). Going **down** = "
        "capex accelerating, full risk-on for the theme.")
    z1, z2, z3, z4, z5 = st.columns(5)
    z1.caption("🟢 **0–25** expansion\ncapex-beta full weight")
    z2.caption("🟡 **25–50** normalization\nwatch zone, no action")
    z3.caption("🟠 **50–70** slowing\nnew money → operators")
    z4.caption("🔴 **70–85** serious\nhalve new-build entries")
    z5.caption("⛔ **85–100** contraction\ncapex-beta avoid")
    df = pd.DataFrame(cx_hist).set_index("as_of")[["score"]]
    st.line_chart(df)
    st.caption(f"now: **{latest:.0f} — {band}** · {arrow} · "
               "a +10–15pt climb over 3 months is the early warning, "
               "the level itself is not a sell signal")
else:
    st.caption("🏗 capex engine: snapshot history accrues daily — "
               "the trend chart unlocks after a few days of runs")

st.caption("_everything here is derived state — the engines keep "
           "their own honesty; this page just makes it visible_")
