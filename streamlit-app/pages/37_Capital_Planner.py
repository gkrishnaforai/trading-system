"""Capital Planner — 'I have $X, build me a book.'

Regime posture sets the sleeve mix (how aggressive, never what to
buy), readiness boards supply candidates, the trade-plan engine
supplies real structure levels, and accepting a book opens one
trade_plan per position — the status ladder + alert feed + email
digest then track it daily. Sleeves fill only with what qualified;
the rest stays cash and the book says so.
"""
import sys
import os

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient
from api_config import api_config
from utils import render_top_nav, health_col, health_cfg

client = APIClient(api_config.python_worker_url, timeout=300)

st.set_page_config(page_title="Capital Planner", page_icon="🧭",
                   layout="wide")
render_top_nav()
st.title("🧭 Capital Planner")
st.caption("enter capital → the engines compose a book: regime sets "
           "the sleeves, readiness picks the names, the plan engine "
           "sets real stops/targets. Accept it and every position "
           "becomes a tracked trade plan. Advisory only — nothing "
           "executes.")

# ------------------------------------------------ inputs
_i1, _i2, _i3, _i4 = st.columns([2, 1.5, 1.5, 1.5])
cap = _i1.number_input("capital $", min_value=1000.0, value=50000.0,
                       step=1000.0)
tgt = _i2.number_input("target %/yr", min_value=5.0, value=24.0,
                       step=1.0)
risk = _i3.number_input("risk %/trade", min_value=0.25, value=1.0,
                        step=0.25)
st.caption("sleeves auto-mix from regime stance — edit nothing, "
           "or accept the default")

# ------------------------------------------------ today's posture
try:
    PO = client.get("api/v1/board/posture") or {}
except Exception:
    PO = {}
if PO.get("posture"):
    _PI = {"aggressive": "🟢", "constructive": "🟢",
           "neutral": "⚪", "caution": "🟡", "defensive": "🔴"}
    _perm = ("new longs ✅" if PO.get("new_longs") else
             "new longs ⛔") + \
            (" · shorts ✅" if PO.get("shorts") else "") + \
            (" · hedge 🛡" if PO.get("hedge_on") else "")
    st.markdown(
        f"{_PI.get(PO['posture'],'•')} **today's posture: "
        f"{PO['posture']}** — {_perm} · `{PO.get('matched') or '—'}`"
        + (f" — {PO['note']}" if PO.get("note") else ""))
    if PO.get("shorts"):
        _ins = (PO.get("instruments") or {}).get("short") or {}
        st.caption(f"short instrument: {_ins.get('etf','SQQQ')} — "
                   f"{_ins.get('note','')}")
    _st = PO.get("stats") or []
    if _st:
        st.caption("posture backtest (fwd QQQ): " + " · ".join(
            f"{s['posture']} → 5d {s['avg_5d']}% / 20d "
            f"{s['avg_20d']}% (n={s['n']})" for s in _st))

if st.button("🧠 build proposal", type="primary"):
    try:
        st.session_state["plan_proposal"] = client.post(
            "api/v1/board/planner/propose",
            {"capital": cap, "target_pct": tgt, "risk_pct": risk},
            timeout=300)
    except Exception as e:
        st.error(f"propose failed: {e}")

P = st.session_state.get("plan_proposal") or {}

# ------------------------------------------------ proposal render
if P and P.get("positions") is not None:
    po = P.get("posture") or {}
    st.markdown("---")
    _rc = st.columns(5)
    _rc[0].metric("regime stance", po.get("stance") or "—",
                  po.get("regime") or "")
    _rc[1].metric("size multiplier", f"{po.get('size_mult') or 1.0}×")
    _rc[2].metric("deeper-dip odds (20d)",
                  f"{po.get('p_deeper')}%" if po.get("p_deeper")
                  is not None else "—")
    _rc[3].metric("goal pace",
                  f"${P.get('goal_month_usd', 0):,.0f}/mo",
                  f"{P.get('target_pct')}%/yr")
    _rc[4].metric("posture as of", po.get("as_of") or "—")
    if po.get("note"):
        st.caption(f"posture: {po['note']}")

    sl = P.get("sleeves") or {}
    tot = P.get("totals") or {}
    _sc = st.columns(5)
    for i, k in enumerate(("invest", "swing", "options", "cash")):
        _sc[i].metric(k, f"${sl.get(k, 0):,.0f}")
    _sc[4].metric("total risk", f"${tot.get('risk_usd', 0):,.0f}",
                  f"{tot.get('risk_pct')}% of capital")

    rows = P.get("positions") or []
    if rows:
        df = pd.DataFrame(rows)
        df["cost"] = df["est_cost"].apply(lambda v: f"${v:,.0f}")
        df["risk"] = df["risk_usd"].apply(
            lambda v: f"${v:,.0f}" if v is not None else "—")
        keep = ["symbol", "sleeve", "use_case", "rank", "why",
                "qty", "entry_px", "stop_px", "stop_basis",
                "target1_px", "target2_px", "cost", "risk",
                "readiness", "thesis"]
        df = health_col(df[[c for c in keep if c in df.columns]])
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={"🩺": health_cfg()})
    else:
        st.warning("no positions qualified — the book is all cash. "
                   "That's a valid answer: it means nothing is ready.")

    for n in P.get("notes") or []:
        st.caption(f"⚠️ {n}")

    hd = P.get("hedge") or {}
    if hd.get("long_put"):
        st.markdown(
            f"🛡 **hedge tranche:** {hd['underlier']} put spread "
            f"**{hd['long_put']}/{hd['short_put']}** · "
            f"{hd['dte_window']} · ~{hd['qty_for_gap']} spreads · "
            f"spend cap ${hd.get('budget_cap_usd', 0):,.0f}")

    _ac1, _ac2 = st.columns([1, 3])
    if _ac1.button("✅ accept & track", type="primary",
                   help="open a trade plan per position — the status "
                        "ladder, alerts and digest track the book"):
        try:
            res = client.post("api/v1/board/planner/accept", P)
            if res.get("book_id"):
                st.success(f"book #{res['book_id']} accepted — "
                           f"{len(res.get('plan_ids') or [])} plans "
                           "opened and now tracked")
                st.session_state.pop("plan_proposal", None)
            else:
                st.error(str(res))
        except Exception as e:
            st.error(f"accept failed: {e}")

# ------------------------------------------------ today's plan
st.markdown("---")
st.subheader("📅 today's plan for the accepted book")
try:
    D = client.get("api/v1/board/planner/daily") or {}
except Exception as e:
    D = {}
    st.error(f"daily failed: {e}")

if D.get("book"):
    bk = D["book"]
    st.caption(f"book #{bk['id']} · ${bk['capital']:,.0f} · "
               f"target {bk['target_pct']}%/yr · opened {bk['as_of']} "
               f"under {bk['stance']}")
    if D.get("regime_shift"):
        st.warning(f"🌦 {D['regime_shift']}")
    acts = D.get("actions") or []
    if acts:
        _IC = {"plan_status": "🚩", "entry_ready": "🟢",
               "improving": "🟡", "degraded": "🔴",
               "regime_shift": "🌦"}
        for a in acts:
            st.markdown(f"- {_IC.get(a['kind'], '•')} "
                        f"**{a.get('symbol') or '—'}** {a.get('detail')}"
                        + (f" ({a.get('status')})"
                           if a.get('status') else ""))
    else:
        st.caption("nothing needs a decision today — plans on track, "
                   "no transitions on book symbols")
    poss = D.get("positions") or []
    if poss:
        _pk = ["symbol", "use_case", "rank", "why", "status", "hint",
               "r", "days", "dist_stop"]
        df = pd.DataFrame(poss)
        st.dataframe(health_col(
            df[[c for c in _pk if c in df.columns]]),
            use_container_width=True, hide_index=True,
            column_config={"🩺": health_cfg()})
else:
    st.caption(D.get("note") or "no accepted book yet — "
                               "build a proposal above and accept it")
