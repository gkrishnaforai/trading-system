"""Speculative Pulse — the spec sleeve's action board.

Same shape as Portfolio Pulse, different playbook: the thesis IS the
position. Buckets are spec-semantic — runner / buy a lot / buy a
little / thesis check / harvest / cut. No averaging down, harvest
into strength, exits are fast.

A name lands here two ways: promoted engine tier (rule-breakers,
5x-scout, hidden-gems) or unpriceable (held, but no FV + thin analyst
coverage) — a position the valuation engine can't anchor is
speculative whether or not it was bought that way.
"""
import sys
import os

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient
from api_config import api_config
from utils import render_top_nav

client = APIClient(api_config.python_worker_url, timeout=180)

st.set_page_config(page_title="Spec Pulse", page_icon="🧬",
                   layout="wide")
render_top_nav()
st.title("🧬 Speculative Pulse")
st.caption(
    "the spec sleeve — thesis progress × tape → a spec-semantic action "
    "hint. Starter size while unproven, harvest into strength, cut on "
    "thesis OR tape break — never average down. Advisory only.")

_TAPE_DOT = {
    "breakout": "🟢", "uptrend": "🟢",
    "pullback": "🟡", "recovery": "🟡", "basing": "🟡",
    "rolling_over": "🟠", "climax": "🟠",
    "downtrend": "🔴", "breakdown": "🔴", "knife": "🔴",
    "capitulation": "🔴",
}
_FUND_DOT = {
    "accelerating": "🟢", "growing": "🟢",
    "slowing": "🟠", "cyclical": "🟠", "watch": "🟠",
    "declining": "🔴", "deteriorating": "🔴",
}
_ACT = {
    "runner": ("🟢 RUNNER",
               "promoted tier + tape intact — let it work. The only "
               "job is the trailing stop; don't micromanage a "
               "compounding thesis."),
    "buy_a_lot": ("🟢 BUY A LOT",
                  "confirmed/inflecting tier + constructive tape + "
                  "clear event window — the spec sleeve's full-size "
                  "add (still bounded by the sleeve cap)."),
    "buy_a_little": ("🟢 BUY A LITTLE",
                     "early thesis + improving tape — starter size "
                     "while the story proves itself. Scaling in, not "
                     "chasing."),
    "thesis_check": ("🟡 THESIS CHECK",
                     "a leg is degrading, the engine wants to demote "
                     "the tier, or a binary event is inside the "
                     "window — decide within days. This is not a "
                     "lazy weak-hold."),
    "harvest": ("🟠 HARVEST",
                "climax / parabolic extension — sell a tranche into "
                "strength, keep the runner. Spec names mean-revert "
                "violently; the tape is giving you the gift."),
    "cut": ("🔴 CUT",
            "·thesis = the business broke (fundamentals failing, "
            "tier demotion, growth under the 15% floor, or a −50% "
            "position with a weak score). ·tape = structure killed "
            "it — deep (−45% from high) AND persistent (10+ "
            "sessions), not one bad week. Never average down on a "
            "spec name."),
    "hold": ("⚪ HOLD",
             "nothing failing, nothing set up."),
}


@st.cache_data(ttl=120, show_spinner="reading the spec board…")
def _spec():
    return client.get("api/v1/board/spec-pulse") or {}


if st.button("🔄 refresh"):
    st.cache_data.clear()
    st.rerun()

D = _spec()
rows = D.get("rows") or []
if not rows:
    st.warning("no speculative names — nothing promoted in the "
               "engines and no unpriceable holdings")
    st.stop()

# ------------------------------------------- sleeve guardrails
sv = D.get("sleeve") or {}
c = st.columns(6)
c[0].metric("spec book value", f"${sv.get('spec_value', 0):,.0f}")
_sp = sv.get("spec_pct")
c[1].metric("spec sleeve", f"{_sp:.1f}%" if _sp is not None else "—",
            f"cap {sv.get('cap_pct')}%")
c[2].metric("total book", f"${sv.get('total_value', 0):,.0f}")
_cnt = sv.get("counts") or {}
c[3].metric("need decision",
            (_cnt.get("cut", 0) or 0) + (_cnt.get("thesis_check", 0)
                                         or 0),
            f"{_cnt.get('cut', 0)} cut · "
            f"{_cnt.get('thesis_check', 0)} check")
c[4].metric("harvest-ready", _cnt.get("harvest", 0))
c[5].metric("runners", _cnt.get("runner", 0))
if _sp is not None and _sp > (sv.get("cap_pct") or 15):
    st.warning(f"⚠️ spec sleeve {_sp:.1f}% is above the "
               f"{sv['cap_pct']}% cap — the whole board tilts toward "
               "trimming until the sleeve is back inside rails")
if sv.get("rotation"):
    st.caption("🔁 rotation — over cap: weakest theses fund the "
               "strongest. Lowest-STS trim list: "
               + " · ".join(sv["rotation"]))


def _table(rws, label):
    if not rws:
        return
    st.subheader(label)
    df = pd.DataFrame([{
        "stock": f"/Stock?sym={r['symbol']}",
        "ticker": r["symbol"],
        "engine·tier": (f"{r.get('engine') or 'unpriced'}·"
                        f"{r.get('tier') or '—'}"),
        "price": r.get("price"),
        "P&L %": r.get("pnl_pct"),
        "value $": r.get("value"),
        "tape": f"{_TAPE_DOT.get(r.get('mom_state'), '⚪')} "
                f"{r.get('mom_state') or '—'}",
        "dip": r.get("dip_phase") or "—",
        "vs 50dma %": round(r["vs_sma50"] * 100, 1)
                      if r.get("vs_sma50") is not None else None,
        "fund": f"{_FUND_DOT.get(r.get('fund_state'), '⚪')} "
                f"{r.get('fund_state') or '—'}",
        "thesis": ((f"g{r['gates_met']}" if r.get("gates_met") is not None
                    else "")
                  + (f" ·{r['rev_streak']}q" if r.get("rev_streak")
                     else "")
                  + (f" ·{r['rev_growth'] * 100:+.0f}%"
                     if r.get("rev_growth") is not None else "")
                  + (" 🌱" if r.get("hidden_engine") else "")),
        "sts": (r.get("sts") or {}).get("sts"),
        "earn": (f"{r['earn_days']}d"
                 if r.get("earn_days") is not None else "—"),
        "action": (_ACT.get(r["bucket"], ("⚪",))[0]
                   + (f"·{r['driver']}" if r.get("driver") else "")
                   + (f"→{r['demoting']}" if r.get("demoting") else "")),
        "why": r.get("why"),
    } for r in rws])
    st.dataframe(
        df.drop(columns=["ticker"]),
        use_container_width=True, hide_index=True,
        column_config={
            "stock": st.column_config.LinkColumn(
                "stock", display_text=r"/Stock\?sym=(\w+)",
                help="open the full Stock page"),
            "price": st.column_config.NumberColumn(format="$%.2f"),
            "P&L %": st.column_config.NumberColumn(format="%+.1f%%"),
            "value $": st.column_config.NumberColumn(format="$%.0f"),
            "vs 50dma %": st.column_config.NumberColumn(
                format="%+.1f%%"),
            "engine·tier": st.column_config.TextColumn(
                help="which engine owns the thesis + its tier — "
                     "watch/emerging/confirmed (rb) or "
                     "watch/inflecting/runner (5x)"),
            "thesis": st.column_config.TextColumn(
                help="gates passed · rev-growth streak quarters · "
                     "latest rev growth. 🌱 = hidden engine "
                     "(segment compounding >40% masked inside)"),
            "sts": st.column_config.NumberColumn(
                "STS", help="Spec Thesis Score — thesis legs "
                "(fundamentals, tier, gates, streak, coverage, "
                "balance sheet /60) + tape legs (momentum, dip, "
                "extension, structure /40). Drops ≥15 pts trigger "
                "a review"),
            "why": st.column_config.TextColumn(width="large"),
        })


pos = [r for r in rows if r["kind"] == "position"]
watch = [r for r in rows if r["kind"] == "watch"]

n = {a: sum(1 for r in pos if r["bucket"] == a) for a in _ACT}
opts = [f"All ({len(pos)})"] + [
    f"{_ACT[a][0]} ({n.get(a, 0)})"
    for a in ("runner", "buy_a_lot", "buy_a_little", "thesis_check",
              "harvest", "cut", "hold")]
pick = st.radio(
    "filter spec positions", opts, horizontal=True,
    help="filters the positions table — the watchlist below "
         "always stays visible")
lbl = pick.split("(", 1)[0].strip()
sel = next((a for a in _ACT if _ACT[a][0] == lbl), None)
if sel:
    st.caption(f"**{_ACT[sel][0]}** — {_ACT[sel][1]}")
with st.expander("what do the buckets mean?"):
    for a in ("runner", "buy_a_lot", "buy_a_little", "thesis_check",
              "harvest", "cut", "hold"):
        st.markdown(f"**{_ACT[a][0]}** — {_ACT[a][1]}")

_table([r for r in pos if sel is None or r["bucket"] == sel],
       "🎰 Spec positions — the risky sleeve"
       + (f" · filtered: {_ACT[sel][0]}" if sel else ""))
_table(watch,
       "👀 Engine watchlist — candidates working on a thesis")

# ------------------------------------------- 🔬 incubator funnel
_cands = D.get("candidates") or []
if _cands:
    _CS = {"incubating": "🥚", "promoted": "🎓", "expired": "💀"}
    with st.expander(
            f"🔬 Incubator — {_cands[0].get('state') and ''}"
            f"{sum(1 for c in _cands if c['state'] == 'incubating')} "
            "incubating · quality movers proving they hold",
            expanded=True):
        cdf = pd.DataFrame([{
            "symbol": c["symbol"],
            "state": f"{_CS.get(c['state'], '⚪')} {c['state']}",
            "days in": c.get("days_in"),
            "appearances": c.get("appearances"),
            "best day %": c.get("best_chg_pct"),
            "peak vs admit %": c.get("retained_pct"),
            "tape": c.get("mom_state") or "—",
            "verdict": c.get("verdict") or "—",
            "→ engine / why": (f"{c['engine']}:{c['promoted_tier']}"
                               if c["state"] == "promoted"
                               else c.get("expired_reason") or "—"),
        } for c in _cands])
        st.dataframe(cdf, use_container_width=True, hide_index=True)
        st.caption(
            "admitted: quality-gate-passed mover appearing ≥3× in "
            "20 sessions · promoted: held the move 5+ days on healthy "
            "tape → joins the engine watchlist · expired: round-"
            "tripped >50% of the move, tape broke, or went quiet. "
            "A spike is noise; sustained strength is the signal.")

st.caption(
    "**reading the board:** CUT needs only *one* leg broken — a spec "
    "name doesn't earn the benefit of the doubt a core holding does. "
    "HARVEST is a gift, not a warning — the tape is giving you an "
    "exit into strength. THESIS CHECK has a clock: binary event "
    "inside 5d or a tier regression. The sleeve cap is 15% of book — "
    "above it, every action tilts toward trim.")
