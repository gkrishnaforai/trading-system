"""GARP Screen — good companies at fair prices.

Intersects three deterministic axes:
  fundamental health flag  (accelerating / growing / cyclical-recovery)
  valuation                (fwd P/E cap + PEG = P/E ÷ rev growth)
  tape                     (pullback/basing = dip discount; knives penalized)

Doctrine: a great company at the peak is a bad trade. Every row carries
its evidence chain — expand a symbol to see exactly why it scored.
"""
import sys
import os

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient
from api_config import api_config
from utils import render_top_nav

client = APIClient(api_config.python_worker_url, timeout=60)

st.set_page_config(page_title="GARP Screen", page_icon="📈", layout="wide")
render_top_nav()
st.title("📈 GARP — Good company at a fair price")
st.caption("fundamental flag × valuation × tape — a great company at the "
           "peak is still a bad trade.")

_FUND_I = {"accelerating": "🟢⚡", "growing": "🟢", "watch": "🟡",
           "cyclical": "🔵", "slowing": "🟠", "declining": "🔻",
           "deteriorating": "🔴", "unknown": "⚪"}
_MOM_I = {"breakout": "🚀", "uptrend": "📈", "pullback": "🟢",
          "recovery": "↩️", "basing": "😴", "climax": "🔥",
          "rolling_over": "🟠", "knife": "🔪", "capitulation": "💥",
          "breakdown": "⬇️", "downtrend": "📉", "unknown": "⚪"}
_SW_I = {"confirmed": "✅ HL", "higher_low": "⏳ HL",
         "unconfirmed": "…", "broken": "⛔ brk"}


def _sw_col(x):
    return _SW_I.get(((x.get("swing") or {}).get("phase")), "")


def _sw_caption(x):
    """swing-structure + context captions for expanders"""
    sw = x.get("swing") or {}
    ph = sw.get("phase")
    if ph:
        t = {"confirmed": "✅ higher low confirmed",
             "higher_low": "⏳ higher low forming",
             "unconfirmed": "… swing structure forming",
             "broken": "⛔ swing structure broken"}.get(ph, ph)
        ln = (f"low ${(sw.get('swing_low') or 0):,.2f} vs prior "
              f"${(sw.get('prior_low') or 0):,.2f}")
        if ph == "higher_low" and sw.get("confirm_level"):
            ln += f" — confirm on close >${sw['confirm_level']:,.2f}"
        if sw.get("vol_pullback_vs_rally"):
            ln += f" · dip vol {sw['vol_pullback_vs_rally']}× rally"
        if sw.get("avwap"):
            ln += (f" · AVWAP ${sw['avwap']:,.2f}"
                   + (" ✓" if sw.get("avwap_reclaimed") else ""))
        st.caption(f"📐 swing: {t} — {ln}")
    _cx = ""
    if x.get("rs_pct") is not None:
        _cx = f"RS {x['rs_pct']} pct"
    if x.get("days_to_earnings") is not None \
            and x["days_to_earnings"] <= 15:
        _cx += (" · " if _cx else "") \
            + f"⚠️ earnings in {x['days_to_earnings']}d"
    if _cx:
        st.caption(f"context: {_cx}")

# --- filters ------------------------------------------------------------------
c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
states = c1.multiselect(
    "fundamental status",
    ["accelerating", "growing", "cyclical", "watch", "slowing"],
    default=["accelerating", "growing", "cyclical"],
    help="cyclical rows only pass when the lean is 'recovery'")
max_pe = c2.selectbox("max fwd P/E", [15, 25, 40, 60], index=2)
min_score = c3.slider("min score", 0, 100, 50)
mom_sel = c4.multiselect(
    "tape", ["pullback", "basing", "recovery", "breakout", "uptrend",
             "rolling_over", "knife", "capitulation", "downtrend"],
    default=[], help="empty = all tape states")
st.caption(
    "**tape legend** — buyable: 🟢 pullback (dip in an uptrend — the "
    "discount) · 😴 basing (volatility contracting, coiling) · ↩️ "
    "recovery (washed out, turning back up) | extended: 🚀 breakout · "
    "📈 uptrend (fine but not a discount) | fading: 🟠 rolling_over "
    "(fresh crack — put territory) | broken: 🔪 knife (freefall) · 💥 "
    "capitulation (panic low — bounce candidates only if fundamentals "
    "hold) · 📉 downtrend (stay away)")

# per-state buy/veto reasoning — shown under every evidence row and in
# the playbook expander below
_TAPE_PLAY = {
    "pullback": (
        "the dip inside an intact uptrend — best risk/reward on the "
        "board; entry while strong fundamentals meet temporary weakness",
        "don't buy if the dip is accelerating into a knife, or the "
        "fundamental flag shows slowing/declining — a pullback only "
        "pays if the trend AND the business hold"),
    "basing": (
        "coiling after a wash — volatility compressed, early low-risk "
        "entry before the move",
        "can sit for weeks — dead money without a catalyst; skip if "
        "fundamentals deteriorate mid-base"),
    "recovery": (
        "washed out and turning back up — cheap re-entry after a "
        "selloff when the fundamentals leg is intact",
        "a recovery that stalls slides into downtrend — only valid "
        "while the momentum holds its turn"),
    "breakout": (
        "new highs on a valid base — momentum entry, works when the "
        "base was tight and volume confirms",
        "chasing pays full price and fails back into the range — "
        "prefer buying the retest, not the break"),
    "uptrend": (
        "trend is working — hold or add small on strength",
        "not a discount — entry here pays peak prices; wait for the "
        "pullback unless very early in the trend"),
    "rolling_over": (
        "NOT a buy — momentum just cracked at the highs; this is the "
        "PUT lane, not the long lane",
        "buying a fresh crack is catching the first leg down"),
    "knife": (
        "no buy — price is in freefall",
        "cheap ≠ safe — without a fundamentals-holds case it's just "
        "cheaper tomorrow; wait for stabilization"),
    "capitulation": (
        "the only buy case is BOUNCE — panic-low + strong fundamentals "
        "= wounded winner, starter size only",
        "without the fundamentals leg it's a value trap, not a "
        "discount — do not buy"),
    "downtrend": (
        "no buy — every rally so far has failed",
        "stays broken until structure repairs; don't bottom-fish"),
}
with st.expander("📖 Tape playbook — when to buy, when not", expanded=False):
    for _s, (_buy, _no) in _TAPE_PLAY.items():
        st.markdown(f"**{_MOM_I.get(_s, '')} {_s}**\n"
                    f"- ✅ {_buy}\n- ⛔ {_no}")
    st.caption(
        "**dip phase** — inside any pullback/recovery row the engine "
        "reads direction-of-travel on 5 legs (MACD hist rising · higher "
        "lows forming · gap to the 50dma shrinking · RSI hooking up · "
        "down-day volume shrinking): `turning_up` ≥3 legs = resolving, "
        "`stabilizing` 2, `still_falling` ≤1 = knife risk — size "
        "accordingly")
    st.caption(
        "**sw** — swing structure: ✅ HL = higher low carved *and* the "
        "pullback's counter-swing high reclaimed (the proven entry); "
        "⏳ HL = low printed above the prior pivot low, waiting for the "
        "confirm-level break; ⛔ brk = a lower low broke the pivot chain "
        "— the pullback thesis is dead until a new base forms")

try:
    d = client.get("api/v1/board/garp", params={
        "max_pe": max_pe, "limit": 100,
        "states": ",".join(states)}) or {}
except Exception as e:
    st.error(f"GARP fetch failed: {e}")
    st.stop()

items = [r for r in (d.get("items") or [])
         if r["score"] >= min_score
         and (not mom_sel or r.get("momentum") in mom_sel)]

m1, m2, m3 = st.columns(3)
m1.metric("matches", len(items))
m2.metric("flagged & priced ≤ cap", d.get("scanned", 0))
m3.metric("P/E cap", max_pe)

if not items:
    st.info("Nothing clears the bar — loosen the P/E cap or score floor, "
            "or run flywheel + fundamental-flag refreshes.")
    st.stop()

df = pd.DataFrame([{
    "symbol": r["symbol"], "score": r["score"],
    "fund": f"{_FUND_I.get(r.get('fund_state'), '')} {r['fund_state']}",
    "risk": r.get("risk") or "—",
    "fwd_pe": r.get("fwd_pe"), "peg": r.get("peg"),
    "rev": (f"{r['rev_growth'] * 100:+.0f}%" if r.get("rev_growth")
            is not None else None),
    "accel": (f"{r['rev_accel'] * 100:+.0f}pts" if r.get("rev_accel")
              is not None else None),
    "beats": r.get("beat_streak"),
    "tape": f"{_MOM_I.get(r.get('momentum'), '')} "
            f"{r.get('momentum') or '—'}",
    "sw": _sw_col(r),
    "rs": (f"{r['rs_pct']}" if r.get("rs_pct") is not None else ""),
    "earn": (f"⚠️{r['days_to_earnings']}d"
             if (r.get("days_to_earnings") is not None
                 and r["days_to_earnings"] <= 15) else ""),
    } for r in items])
st.dataframe(df, use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("#### Evidence — why each name scored")
cols = st.columns(2)
for i, r in enumerate(items[:20]):
    with cols[i % 2]:
        _h = (f"{_FUND_I.get(r.get('fund_state'), '')} **{r['symbol']}** "
              f"· score {r['score']:.0f} · PEG {r.get('peg') or '—'}")
        with st.expander(_h):
            for w in r.get("why") or []:
                st.caption(f"· {w}")
            _tp = _TAPE_PLAY.get(r.get("momentum") or "")
            if _tp:
                st.caption(f"🧭 tape — ✅ {_tp[0]}")
                st.caption(f"🧭 tape — ⛔ {_tp[1]}")
            _sw_caption(r)
            if (r.get("momentum") or "") in {"pullback", "basing",
                                            "recovery"}:
                if st.button(f"📜 Options screen for {r['symbol']}",
                             key=f"gopt_{r['symbol']}"):
                    st.session_state["leaps_sym"] = r["symbol"]
                    st.switch_page("pages/9_Options.py")

st.caption("Reads stored flags — refresh 'Expectation-gap scores' + "
           "'Fundamental flags' on the Daily Board if data looks stale.")

# --- style buckets — value / growth / multi-bagger / recovery ------------------
st.markdown("---")
st.subheader("🧭 Style lanes — same flags, different bets")
st.caption("🏛 compounder = sure-shot growth at sane price · 💰 value = "
           "cheap & not broken · 🚀 growth = hypergrowth accelerating · "
           "💎 multibagger = small-cap + acceleration · 🔄 recovery = "
           "cyclical with leading legs turning up")
try:
    _sd = client.get("api/v1/board/styles", params={"limit": 15}) or {}
except Exception:
    _sd = {}
_bk = _sd.get("buckets") or {}
_LANE_I = {"compounder": "🏛 Compounder", "value": "💰 Value",
           "growth": "🚀 Growth", "multibagger": "💎 Multibagger",
           "recovery": "🔄 Recovery"}
if _bk:
    _tabs = st.tabs([f"{_LANE_I[k]} ({len(_bk[k])})"
                     for k in _LANE_I])
    for _tab, _lane in zip(_tabs, _LANE_I):
        with _tab:
            _rows = _bk.get(_lane) or []
            if not _rows:
                st.info("nothing in this lane right now")
                continue
            _df = pd.DataFrame([{
                "symbol": x["symbol"], "score": x["score"],
                "fund": f"{_FUND_I.get(x.get('fund_state'), '')} "
                        f"{x.get('fund_state')}",
                "risk": x.get("risk") or "—",
                "fwd_pe": x.get("fwd_pe"), "peg": x.get("peg"),
                "rev": (f"{x['rev_growth'] * 100:+.0f}%"
                        if x.get("rev_growth") is not None else None),
                "mcap": (f"${x['mcap'] / 1e9:.1f}B"
                         if x.get("mcap") else "—"),
                "tier": x.get("sc_tier") or x.get("rb_tier") or "—",
                "tape": f"{_MOM_I.get(x.get('momentum'), '')} "
                        f"{x.get('momentum') or '—'}",
                "sw": _sw_col(x),
                "rs": (f"{x['rs_pct']}"
                       if x.get("rs_pct") is not None else ""),
                "earn": (f"⚠️{x['days_to_earnings']}d"
                         if (x.get("days_to_earnings") is not None
                             and x["days_to_earnings"] <= 15) else ""),
                } for x in _rows])
            st.dataframe(_df, use_container_width=True, hide_index=True)
            for x in _rows[:10]:
                with st.expander(f"· {x['symbol']} — why"):
                    for w in x.get("why") or []:
                        st.caption(f"· {w}")
                    _tp = _TAPE_PLAY.get(x.get("momentum") or "")
                    if _tp:
                        st.caption(f"🧭 tape — ✅ {_tp[0]}")
                        st.caption(f"🧭 tape — ⛔ {_tp[1]}")
                    _sw_caption(x)
                    if (x.get("momentum") or "") in {"pullback", "basing",
                                                    "recovery"}:
                        if st.button(f"📜 Options screen for "
                                     f"{x['symbol']}",
                                     key=f"sopt_{_lane}_{x['symbol']}"):
                            st.session_state["leaps_sym"] = x["symbol"]
                            st.switch_page("pages/9_Options.py")
