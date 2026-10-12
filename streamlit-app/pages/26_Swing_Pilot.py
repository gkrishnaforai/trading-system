"""Swing Pilot — the paper-trading engine that tests the flag system.

Trades the flag stack's calls on paper, exits on plan or momentum
decay, and writes what it learns back into engine_weights — the
correction layer the flag engine reads. Simulation only.
"""
import sys
import os

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient
from api_config import api_config

client = APIClient(api_config.python_worker_url, timeout=60)

st.set_page_config(page_title="Swing Pilot", page_icon="🛩️", layout="wide")
st.title("🛩️ Swing Pilot — paper trades that grade the flag engine")
st.caption(
    "buys pullback/recovery entries on the flag stack, exits on stop / "
    "target / **momentum decay** / climax / 15d timeout — then writes "
    "the journal back into learned weights the flags read.")

try:
    rep = client.get("api/v1/board/pilot") or {}
except Exception as e:
    st.error(f"pilot report failed: {e}")
    rep = {}

# --- headline stats -----------------------------------------------------------
s = rep.get("stats") or {}
open_t = rep.get("open") or []
closed = rep.get("closed") or []
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("open trades", len(open_t))
c2.metric("closed trades", int(s.get("n") or 0))
c3.metric("win rate", f"{(s.get('win') or 0) * 100:.0f}%")
c4.metric("avg trade", f"{(s.get('ar') or 0) * 100:+.1f}%")
c5.metric("total P&L", f"{(s.get('total') or 0) * 100:+.1f}%")

# --- open book ----------------------------------------------------------------
st.subheader(f"📗 Open book ({len(open_t)})")
if open_t:
    df = pd.DataFrame(open_t)[
        ["symbol", "entry_date", "entry_px", "stop_px", "target_px",
         "pattern_key", "momentum_state", "mfe_pct", "mae_pct",
         "hold_days"]]
    df["unrealized%"] = "—"
    st.dataframe(df.rename(columns={
        "momentum_state": "tape now", "mfe_pct": "MFE",
        "mae_pct": "MAE", "hold_days": "days held",
        "pattern_key": "pattern"}), use_container_width=True,
        hide_index=True)
else:
    st.info("no open paper trades — run the pilot job")

# --- equity curve + closed journal ---------------------------------------------
st.subheader("📒 Closed journal — did each sell make money?")
if closed:
    dfc = pd.DataFrame(closed)
    dfc["ret_%"] = (dfc["ret_pct"] * 100).round(1)
    dfc = dfc.sort_values("exit_date")
    dfc["cum_pnl"] = dfc["ret_pct"].cumsum() * 100
    st.line_chart(dfc.set_index("exit_date")["cum_pnl"])
    st.dataframe(
        dfc[["symbol", "entry_date", "entry_px", "exit_date", "exit_px",
             "exit_reason", "ret_%", "hold_days", "pattern_key",
             "mae_pct", "mfe_pct"]].iloc[::-1].rename(columns={
            "exit_reason": "exit", "hold_days": "held",
            "pattern_key": "pattern"}),
        use_container_width=True, hide_index=True)
    for t in closed[:3]:
        ev = t.get("evidence") or {}
        if isinstance(ev, str):
            import json
            try:
                ev = json.loads(ev)
            except Exception:
                ev = {}
        st.caption(
            f"· {t['symbol']} {t['pattern_key']}: entered {t['entry_date']} "
            f"@ {t['entry_px']:.2f} → {t['exit_reason']} {t['exit_date']} "
            f"@ {t['exit_px']:.2f} = {t['ret_pct'] * 100:+.1f}% "
            f"| entry evidence: fund {ev.get('fund')}, "
            f"phase {ev.get('dip_phase')}, "
            f"prior {ev.get('prior') or 'none'}")
else:
    st.info("no closed trades yet — entries close on stop / target / "
            "momentum decay / 15d timeout")

# --- what the journal says -----------------------------------------------------
c1, c2 = st.columns(2)
with c1:
    st.subheader("P&L by pattern")
    if rep.get("by_pattern"):
        dfp = pd.DataFrame(rep["by_pattern"])
        dfp["win%"] = (dfp["win"] * 100).round(0)
        dfp["total%"] = (dfp["total"] * 100).round(1)
        st.dataframe(dfp[["pattern_key", "n", "win%", "total%"]],
                     use_container_width=True, hide_index=True)
with c2:
    st.subheader("P&L by exit reason")
    if rep.get("by_exit"):
        dfe = pd.DataFrame(rep["by_exit"])
        dfe["avg%"] = (dfe["ar"] * 100).round(1)
        st.dataframe(dfe[["exit_reason", "n", "avg%"]],
                     use_container_width=True, hide_index=True)

# --- learned weights — the feedback loop ---------------------------------------
with st.expander("🧠 Learned weights — what the pilot wrote back to the "
                 "flag engine", expanded=False):
    w = rep.get("weights") or []
    if w:
        dfw = pd.DataFrame(w)
        st.dataframe(dfw[["key", "value", "n", "win_rate",
                          "updated_at"]],
                     use_container_width=True, hide_index=True)
    else:
        st.info("no weights learned yet — needs ≥4 closed trades "
                "per pattern")
    st.caption(
        "`gate:` patterns that lose get disabled → board penalizes "
        "them; `dip:` phases get their score penalty softened/hardened "
        "by real P&L; `risk:stop_mult` widens if stopped trades kept "
        "whipsawing back up.")
