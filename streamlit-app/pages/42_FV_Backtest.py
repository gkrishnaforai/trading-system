# -*- coding: utf-8 -*-
"""FV Backtest — calibration of the fair-value engine.

Replays every stored v2 run against materialized forward outcomes
(fv_backtest_forwards — one windowed SQL pass, refreshed on load).
Tables: horizon-level aggregate metrics and per-symbol breakdown so a
systematically biased archetype is visible, not averaged away.

Read-only; nothing here trades.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from api_client import APIClient
from api_config import api_config

st.set_page_config(page_title="FV Backtest", page_icon="📐", layout="wide")
client = APIClient(api_config.python_worker_url, timeout=300)

st.title("📐 Fair Value — engine calibration")
st.caption(
    "Stored FV runs vs realized prices. **fv_bias** < 0 → engine overshot "
    "(realized under FV). **bear breach** ~25% = the bear leg is calibrated "
    "to its probability weight. **gate reach** + ret-split show whether "
    "buy_below actually separates good entries.")

c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    sym = st.text_input("symbol (blank = all runs)", "").strip().upper() or None
with c2:
    hz = st.text_input("horizons (days)", "90,180,365")
with c3:
    refresh = st.checkbox("refresh forwards", value=True,
                          help="upsert fv_backtest_forwards before scoring")


@st.cache_data(ttl=300, show_spinner="replaying stored runs…")
def _bt(symbol, horizons, do_refresh):
    return client.get("admin/fair-value-v2/backtest", params={
        "symbol": symbol or "", "horizons": horizons,
        "refresh": str(do_refresh).lower(), "per_symbol": "true"})


try:
    res = _bt(sym, hz, refresh)
except Exception as e:
    st.error(f"backtest call failed: {e}")
    st.stop()

if not res.get("success"):
    st.error(res.get("error") or "backtest failed")
    st.stop()

r = res.get("result") or {}
if not r.get("horizons"):
    st.info("no evaluable runs — horizons longer than run age")
    st.stop()

st.caption(
    f"{r.get('total_runs', 0)} stored runs · "
    f"forwards refreshed: {r.get('forwards_refreshed', '—')} rows")

_pct = lambda x: f"{x:+.1%}" if x is not None else "—"
_share = lambda x: f"{x:.0%}" if x is not None else "—"

# ------------------------------------------------ horizon aggregate
st.subheader("Aggregate by horizon")
rows = [{
    "horizon": f"{h['days']}d",
    "runs": h["n"],
    "fv bias": _pct(h["fv_bias"]),
    "fv mae": _pct(h["fv_mae"]),
    "bear breach (~25%)": _share(h["bear_breach"]),
    "gate reached": _share(h["gate_reach"]),
    f"ret ≤buy_below (n={h['n_inside']})": _pct(h["ret_inside_gate"]),
    f"ret >buy_below (n={h['n_outside']})": _pct(h["ret_outside_gate"]),
} for h in r["horizons"]]
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# ------------------------------------------------ per-symbol table
per = r.get("per_symbol") or {}
if per:
    st.subheader("Per-symbol")
    hsel = st.selectbox("horizon", [str(h["days"]) for h in r["horizons"]],
                        index=0)
    srows = []
    for s, hs in per.items():
        m = hs.get(hsel) or {}
        if not m.get("n"):
            continue
        srows.append({
            "symbol": s, "runs": m["n"],
            "fv bias": _pct(m["fv_bias"]), "fv mae": _pct(m["fv_mae"]),
            "bear breach": _share(m["bear_breach"]),
            "gate reach": _share(m["gate_reach"]),
            "ret in-gate": _pct(m["ret_inside_gate"]),
            "ret out-gate": _pct(m["ret_outside_gate"]),
        })
    df = pd.DataFrame(srows)
    if not df.empty:
        st.dataframe(df.sort_values("fv bias"), hide_index=True,
                     use_container_width=True)
        st.caption("sorted by fv bias — most-negative rows overshoot FV "
                   "the hardest; check archetype mix before re-tuning")
    else:
        st.caption("no symbols evaluable at this horizon")
