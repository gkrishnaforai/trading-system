"""Conviction List — the meta-engine's best ideas.

Pools candidates from every engine (gems, swing calls, movers,
rule-breakers, flywheel, theme money-flow), scores them on adviser
criteria, and journals The List nightly. Two lanes:
  deploy — fundamentals + valuation + tape all aligned → act now
  watch  — right fundamentals, expensive or unconfirmed → future
           compounders (the early-NVDA/PLTR shelf)
Daily best-2 flagged; Friday → weekly pick; month-end → monthly
top-2. Every pick is graded at +5d/+20d/+60d vs SPY.
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar, sym_md
from api_client import APIClient
from api_config import api_config

setup_page_config("Conviction List", "🏆")
render_sidebar()

st.title("🏆 Conviction List — best ideas across every engine")
st.caption("pooled from gems · swing calls · movers · rule-breakers · "
           "flywheel · theme money-flow — score 0–100, journaled and "
           "graded nightly · research flag, not a buy signal")

client = APIClient(api_config.python_worker_url, timeout=120)


@st.cache_data(ttl=600, show_spinner=False)
def _load():
    try:
        return client.get("api/v1/board/conviction") or {}
    except Exception:
        return {}


@st.cache_data(ttl=1800, show_spinner=False)
def _lb():
    try:
        return client.get("api/v1/board/conviction/leaderboard") or {}
    except Exception:
        return {}


S = _load()
if st.button("🔄 rescan"):
    _load.clear()
    st.rerun()

if not S:
    st.warning("conviction engine unavailable — is the worker up?")
    st.stop()

# ---------------------------------------------------------------- banner
c1, c2, c3, c4 = st.columns(4)
c1.metric("Pool", S.get("pool", 0))
c2.metric("Today's picks", " · ".join(S.get("daily_picks") or ["—"]))
wp = S.get("weekly_pick")
c3.metric("Week's best", wp or ("Friday" if not wp else "—"))
mp = S.get("monthly_picks")
c4.metric("Month picks", " · ".join(mp) if mp else "month-end")

# -------------------------------------------------------------- The List
rows = S.get("the_list") or []
_L = {"deploy": "🟢 DEPLOY", "watch": "👁 WATCH", "off": "⚪"}
_V = {"reasonable": "🟢", "elevated": "🟡", "extreme": "🔴",
      "unknown": "⚪"}
st.subheader("The List")
st.caption("`deploy` = fundamentals + value + tape aligned → current "
           "money · `watch` = fundamentals right, valuation/tape not "
           "yet → the future shelf")
for r in rows:
    pick = " ⭐" if r.get("daily_pick") else ""
    head = (f"**#{r['rank']} {sym_md(r['symbol'])}** — "
            f"**{r['score']:.0f}**/100 "
            f"{_L.get(r['lane'],'')}{pick} · "
            f"{_V.get(r.get('valuation'),'⚪')} pe "
            f"{r.get('fwd_pe') if r.get('fwd_pe') is not None else '—'} · "
            f"`{r.get('momentum') or '—'}` · "
            f"{r.get('theme') or '—'}")
    with st.expander(head, expanded=(r["rank"] <= 3)):
        p = r.get("parts") or {}
        cc = st.columns(5)
        cc[0].caption(f"growth **{p.get('growth','—')}**/30")
        cc[1].caption(f"quality **{p.get('quality','—')}**/20")
        cc[2].caption(f"tape **{p.get('tape','—')}**/20")
        cc[3].caption(f"consensus **{p.get('consensus','—')}**/15")
        cc[4].caption(f"theme $ **{p.get('theme_money','—')}**/15")
        st.caption("surfaced by: " + " · ".join(r.get("sources") or []))
        if r.get("future_themes"):
            st.caption(f"future score **{r.get('future_score') or 0:.0f}**/95 · "
                       + " · ".join(r["future_themes"]))
        if r.get("dd52w") is not None:
            st.caption(f"{r['dd52w']*100:+.0f}% off 52w high")

watch = S.get("watch") or []
if watch:
    st.subheader("👁 Future shelf — ranked by future score")
    st.caption("thesis exposure + evidence in the numbers + headroom "
               "(small mcap vs a decade-long thesis) — the early-"
               "NVDA/PLTR bucket, BEFORE the tape confirms")
    for w in watch:
        th = " · ".join(w.get("themes") or []) or "—"
        st.caption(f"**{sym_md(w['symbol'])}** · future "
                   f"**{w.get('future_score',0):.0f}**/95 — {th}")

# ---------------------------------------------------------- performance
st.divider()
st.subheader("📋 Track record — are the picks working?")
lb = _lb()
if lb.get("by_lane"):
    st.markdown("**By lane (graded 20d)**")
    for b in lb["by_lane"]:
        hit = (b.get("hit_20d") or 0)
        n = b.get("n") or 0
        exc = b.get("avg_vs_spy")
        st.caption(
            f"{_L.get(b['lane'], b['lane'])} · n={n} · "
            f"win rate {hit/n:.0%} · avg vs SPY "
            f"{exc:+.1%}" if exc is not None and n else
            f"{b['lane']} · n={n} · grading pending")
if lb.get("symbols"):
    st.markdown("**Persistence — who's earning the list**")
    for s in lb["symbols"][:15]:
        flags = []
        if s.get("weekly_wins"):
            flags.append(f"weekly ×{s['weekly_wins']}")
        if s.get("monthly_wins"):
            flags.append(f"monthly ×{s['monthly_wins']}")
        r20 = s.get("avg_ret_20d")
        st.caption(
            f"**{sym_md(s['symbol'])}** · "
            f"{s['days_on_list']}d on list · "
            f"{s['pick_days']} daily picks"
            + (f" · {' · '.join(flags)}" if flags else "")
            + (f" · avg +20d {r20:+.1%}" if r20 is not None else ""))

st.caption(f"journaled `conviction_snapshots` · {S.get('as_of','')} · "
           f"{S.get('engine_version','')}")
