"""Portfolio Pulse — every holding on one board.

Two columns of truth per name:
  tape         — the price action state and which way it's moving
  fundamentals — what the business is actually doing
Then valuation (fair-value gap) and a deterministic action hint:
buy a lot / buy a little / weak hold / hold / trim / reduce / avoid.

Click any column header to sort. Click a ticker for the full Stock page.
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

st.set_page_config(page_title="Portfolio Pulse", page_icon="💓",
                   layout="wide")
render_top_nav()
st.title("💓 Portfolio Pulse")
st.caption(
    "every holding, one board — **tape** (technical state + direction) "
    "× **fundamentals** × **fair-value gap** → a deterministic action "
    "hint. Click a column header to sort, a ticker to open the Stock "
    "page. Advisory only — you decide.")

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
    "reduce": ("🔴 REDUCE",
               "tape broken AND nothing holding the thesis — weak/"
               "unknown fundamentals, street cutting, or a real premium "
               "over fair value. Trim exposure or exit; revisit only "
               "after the tape repairs."),
    "avoid": ("⛔ AVOID",
              "watchlist names whose tape is broken enough that a "
              "position would be a reduce — no capital until repair."),
    "trim": ("🟠 TRIM",
             "extended on constructive tape (climax confirmed, "
             "rolling-over after a run) or strong tape on deteriorating "
             "fundamentals — harvest partial profits into strength, "
             "keep the core."),
    "stalk": ("� BUY A LITTLE",
              "entry setups forming — accumulation (good business + "
              "washed tape + real discount), cycle-turns (street "
              "upgrading at the trough), turnarounds awaiting proof, "
              "and adds blocked by a near-term event. Starter size "
              "only — wait for the trigger; don't chase."),
    "attention": ("🟡 WEAK HOLD",
                  "one leg degrading, fundamentals cooling, or data "
                  "unresolved — monitor closely, tighten mental stops, "
                  "no new money."),
    "add": ("🟢 BUY A LOT",
            "constructive tape + strong fundamentals + below fair "
            "value + clear event window + no hard risks — the engine's "
            "highest-conviction candidates for new capital. Size and "
            "timing are still yours."),
    "hold": ("⚪ HOLD",
             "nothing failing, nothing setting up — let them work."),
}
_PRICED_ABBR = {
    "not_priced": "✅not priced", "partial": "half",
    "substantial": "substantial", "full": "⚠️priced",
    "beyond_lt_avg": "⚠️beyond", "fx_suspect": "?fx",
    "unknown": "—",
}
_MOM_RANK = {"breakout": 9, "climax": 8, "uptrend": 7, "pullback": 6,
             "recovery": 5, "basing": 4, "rolling_over": 3,
             "downtrend": 2, "capitulation": 2, "breakdown": 1,
             "knife": 0}


def _trans(cur, prev):
    """Direction arrow — is the tape better or worse than yesterday."""
    c, p = _MOM_RANK.get(cur, -1), _MOM_RANK.get(prev)
    if p is None:
        return "—"
    if c > p:
        return "⬆ improving"
    if c < p:
        return "⬇ degrading"
    return "→ flat"


@st.cache_data(ttl=120, show_spinner="reading the board…")
def _pulse():
    return client.get("api/v1/board/portfolio-pulse") or {}


if st.button("🔄 refresh"):
    st.cache_data.clear()
    st.rerun()

D = _pulse()
rows = D.get("rows") or []
if not rows:
    st.warning("no holdings found")
    st.stop()

# ------------------------------------------- 🎯 book vs target
# the accountability strip — is the book compounding at the
# PORTFOLIO_TARGET_PCT pace? snapshots accrue daily; pace shows once
# the baseline has a day behind it.
bk = D.get("book") or {}
if bk:
    c = st.columns(6)
    c[0].metric("book value", f"${bk.get('value', 0):,.0f}")
    _pl = bk.get("pnl_pct")
    c[1].metric("unrealized P/L",
                f"${bk.get('pnl', 0):,.0f}",
                f"{_pl:+.1f}%" if _pl is not None else None)
    c[2].metric("🎯 target", f"{bk.get('target_pct'):.0f}%/yr",
                f"{bk.get('pace_month')}%/mo needed")
    c[3].metric("12-mo goal", f"${bk.get('target_value_12m', 0):,.0f}",
                f"${bk.get('goal_month', 0):,.0f}/mo pace")
    if bk.get("track_days"):
        c[4].metric(f"track ({bk['track_days']}d)",
                    f"{bk.get('track_ret_pct'):+.1f}%",
                    f"goal {bk.get('track_target_pct'):+.1f}%")
        _spy = (f"{bk.get('excess_pct'):+.1f}% vs SPY "
                f"({bk.get('spy_ret_pct'):+.1f}%)"
                if bk.get("spy_ret_pct") is not None else None)
        c[5].metric("pace", "🟢 on pace" if bk.get("on_pace")
                    else "🔴 behind", _spy)
    else:
        c[4].metric("track", "day 1")
        c[5].metric("pace", "—")
    if bk.get("unpriced_cost"):
        st.caption(f"⚠️ ${bk['unpriced_cost']:,.0f} of cost basis has no "
                   "price — book value understated until data lands")

# ------------------------------------------- 🛡 hedge — book insurance
# the put-spread ladder: coverage vs regime-scaled target, spend vs
# adaptive budget, and the suggested next tranche. Advisory — the
# engine sizes it, you open it at your broker, then journal it here.
try:
    _hs = client.get("api/v1/board/hedge") or {}
    _hg = client.get("api/v1/board/hedge/suggest") or {}
except Exception:
    _hs, _hg = {}, {}
if _hs:
    with st.expander(
            f"🛡 hedge — {_hs.get('coverage_now_pct', 0)}% covered "
            f"vs {_hs.get('coverage_target_pct', 0)}% target "
            f"({_hs.get('tier', '—')})", expanded=False):
        hc = st.columns(5)
        hc[0].metric("exposure (β-adj)",
                     f"${_hs.get('exposure_beta_adj', 0):,.0f}",
                     f"β {_hs.get('book_beta', 0):.2f}")
        hc[1].metric("coverage",
                     f"${_hs.get('covered_notional', 0):,.0f}",
                     f"gap ${_hs.get('coverage_gap', 0):,.0f}")
        hc[2].metric("spent YTD", f"${_hs.get('spent_ytd', 0):,.0f}",
                     f"cap ${_hs.get('budget_cap_usd', 0):,.0f}")
        hc[3].metric("open spreads", _hs.get("n_open", 0))
        hc[4].metric("regime", _hs.get("defensive_state") or
                     _hs.get("tier") or "—")
        if _hs.get("regime_note"):
            st.caption(f"target logic: {_hs['regime_note']}")
        if _hg.get("long_put"):
            st.markdown(
                f"**suggested tranche:** {_hg['underlier']} put spread "
                f"**{_hg['long_put']}/{_hg['short_put']}** · "
                f"expiry window {_hg['dte_window']} · "
                f"~{_hg['qty_for_gap']} spreads to close the "
                f"${_hg['coverage_gap_usd']:,.0f} gap "
                f"(spot {_hg['spot']})")
            st.caption(_hg.get("note") or "")
        elif _hg.get("note"):
            st.caption(f"suggestion: {_hg['note']}")
        if _hs.get("open"):
            st.dataframe(pd.DataFrame(_hs["open"]),
                         use_container_width=True, hide_index=True)
        # journal the spread you actually opened at the broker
        with st.form("hedge_open_form"):
            st.caption("journal a spread you opened")
            f = st.columns(5)
            _exp = f[0].text_input("expiry", "YYYY-MM-DD")
            _lk = f[1].number_input("long put K", value=float(
                _hg.get("long_put") or 0), step=1.0)
            _sk = f[2].number_input("short put K", value=float(
                _hg.get("short_put") or 0), step=1.0)
            _qty = f[3].number_input("qty", value=int(
                _hg.get("qty_for_gap") or 1), min_value=1, step=1)
            _cost = f[4].number_input("net debit $", min_value=0.0,
                                      step=10.0)
            if st.form_submit_button("record spread"):
                try:
                    client.post("api/v1/board/hedge/open", {
                        "expiry": _exp, "long_strike": _lk,
                        "short_strike": _sk, "qty": int(_qty),
                        "cost": _cost,
                        "notional": _qty * (_hg.get("spot") or 0) * 100,
                        "spot_at_entry": _hg.get("spot")})
                    st.success("spread journaled — the ladder will "
                               "track monetization")
                    st.rerun()
                except Exception as e:
                    st.error(f"record failed: {e}")


def _table(rws, label):
    if not rws:
        return
    st.subheader(label)
    df = pd.DataFrame([{
        "stock": f"/Stock?sym={r['symbol']}",
        "ticker": r["symbol"],
        "portfolio": r["portfolio"],
        "price": r["price"],
        "P&L %": r["pnl_pct"],
        "tape": f"{_TAPE_DOT.get(r['mom_state'], '⚪')} "
                f"{r['mom_state'] or '—'}",
        "direction": _trans(r["mom_state"], r["mom_prev"]),
        "rsi": r["rsi"],
        "vs 50dma %": round(r["vs_sma50"] * 100, 1)
                      if r.get("vs_sma50") is not None else None,
        "fundamentals": f"{_FUND_DOT.get(r['fund_state'], '⚪')} "
                        f"{r['fund_state'] or '—'}",
        "fwd": (f"{r['revision_grade'] or '—'}·"
              f"{_PRICED_ABBR.get(r['priced_status'], '—')}"
              + ("🌱" if r.get("emerging_growth") else "")),
        "sector": (f"{r['sector_etf']} {r['sector_flow']}"
                   if r.get("sector_etf") and r.get("sector_flow")
                   else (r.get("sector") or "—")),
        "FV gap %": r["fv_upside"],
        "growth qual": r["gq_pct"],
        "action": (_ACT.get(r.get("bucket") or r["action"],
                            ("⚪",))[0]
                   + (f"·{r['action_label']}"
                      if r.get("action_label") else "")),
        "why": r["why"],
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
            "FV gap %": st.column_config.NumberColumn(
                format="%+.1f%%",
                help="engine fair value vs spot — negative = rich"),
            "growth qual": st.column_config.ProgressColumn(
                min_value=0, max_value=100,
                help="growth-quality percentile vs tracked universe"),
            "vs 50dma %": st.column_config.NumberColumn(
                format="%+.1f%%"),
            "fwd": st.column_config.TextColumn(
                "fwd", width="small",
                help="forward flags — revision grade·how much growth "
                     "is already priced. 🌱 = emerging product ramp "
                     "(option/material tier)"),
            "sector": st.column_config.TextColumn(
                help="GICS sector ETF + its capital-flow state from the "
                     "rotation board — is the weakness the stock's or "
                     "the sector's?"),
            "why": st.column_config.TextColumn(width="large"),
        })


pos_spec = [r for r in rows
            if r["kind"] == "position" and r.get("spec")]
pos = [r for r in rows
       if r["kind"] == "position" and not r.get("spec")]
watch = [r for r in rows if r["kind"] == "watch"]

if pos_spec:
    _sv = " · ".join(r["symbol"] for r in pos_spec[:20]) \
          + (" …" if len(pos_spec) > 20 else "")
    st.info(f"🧬 **{len(pos_spec)} speculative holding"
            f"{'s' if len(pos_spec) != 1 else ''}** live on the "
            f"[Spec Pulse](/Spec_Pulse) board — different playbook "
            f"(thesis = position, no averaging down): {_sv}")

n = {a: sum(1 for r in pos if r["bucket"] == a) for a in _ACT}
opts = [f"All ({len(pos)})"] + [
    f"{_ACT[a][0]} ({n.get(a, 0)})"
    for a in ("add", "stalk", "attention", "hold", "trim", "reduce")]
pick = st.radio(
    "filter positions", opts, horizontal=True,
    help="filters the positions table — the watchlist below "
         "always stays visible")
lbl = pick.split("(", 1)[0].strip()
sel = next((a for a in _ACT if _ACT[a][0] == lbl), None)
if sel:
    st.caption(f"**{_ACT[sel][0]}** — {_ACT[sel][1]}")
with st.expander("what do the buckets mean?"):
    for a in ("add", "stalk", "attention", "hold", "trim", "reduce",
              "avoid"):
        st.markdown(f"**{_ACT[a][0]}** — {_ACT[a][1]}")

_table([r for r in pos if sel is None or r["bucket"] == sel],
       "📦 Positions — money is in these"
       + (f" · filtered: {_ACT[sel][0]}" if sel else ""))
_table(watch,
       "👀 Watch candidates — theme-rotation book (no capital)")

st.caption(
    "**reading the board:** REDUCE needs *both* legs failing "
    "(broken tape + deteriorating fundamentals) — a dip on a strong "
    "business is not a sell. TRIM is extension, not exit. BUY A LOT "
    "needs constructive tape + strong fundamentals + below fair "
    "value. BUY A LITTLE is an entry setup forming (accumulation, "
    "cycle-turn, add-blocked) — starter size, not a chase. WEAK HOLD "
    "is a warning or unresolved data (cooling, degraded leg, review) "
    "— no new money. 'direction' compares today's tape state to "
    "yesterday's journal — it populates from tomorrow's refresh "
    "onward.")
