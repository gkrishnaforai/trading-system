"""Trade Plans — every open entry bound to its exit plan. Status is
computed live by the YAML plan_status rules: thesis death, stop hit,
targets, extension, staleness, trail opportunities. Transitions are
the alert feed — the human decides and closes the plan."""
import sys
import os

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient
from api_config import api_config
from utils import render_top_nav, sym_md

client = APIClient(api_config.python_worker_url, timeout=120)

st.set_page_config(page_title="Trade Plans", page_icon="📋", layout="wide")
render_top_nav()
st.title("📋 Trade Plans")
st.caption("each entry bound to its exit plan — structure stop, "
           "R-targets, trail rule, time stop. Status re-computes live "
           "on every load; transitions become alerts. Advisory — "
           "you decide, you execute.")

_ICON = {"stop_hit": "🔴", "invalidated": "🔴", "target2_hit": "🟢",
         "extended": "🟡", "stalled": "🟠", "trail_up": "🔵",
         "target1_hit": "🟡", "on_track": "⚪", "closed": "📁"}
_URG = {"stop_hit": 0, "invalidated": 0, "target2_hit": 1,
        "extended": 1, "stalled": 2, "trail_up": 3, "target1_hit": 3,
        "on_track": 4}


@st.cache_data(ttl=120, show_spinner="evaluating plans…")
def _plans():
    return client.get("api/v1/board/trade-plans",
                      params={"all": True}) or {}


@st.cache_data(ttl=60)
def _events():
    return client.get("api/v1/board/trade-plans/events",
                      params={"limit": 30}) or {}


if st.button("🔄 re-evaluate"):
    st.cache_data.clear()
    st.rerun()

# --------------------------------------------- 🔔 alerts
ev = _events()
unseen = ev.get("unseen") or 0
events = ev.get("events") or []
if unseen:
    st.subheader(f"🔔 {unseen} alert{'s' if unseen != 1 else ''}")
    for e in events:
        if e.get("seen"):
            continue
        c1, c2 = st.columns([6, 1])
        c1.markdown(
            f"{_ICON.get(e.get('kind'),'🔔')} **{e['symbol']}** · "
            f"`{e['kind']}` — {e.get('message') or ''} "
            f"· _{e.get('action_hint') or ''}_")
        if c2.button("seen", key=f"s{e['id']}"):
            client.post(
                f"api/v1/board/trade-plans/events/{e['id']}/seen")
            st.cache_data.clear()
            st.rerun()

# --------------------------------------------- open plans
d = _plans()
plans = d.get("open") or []
if not plans and not events:
    st.info("no trade plans yet — open one from the readiness "
            "section on the Stock page (📋 plan under any use-case).")
    st.stop()

plans.sort(key=lambda p: (_URG.get(
    (p.get("eval") or {}).get("status"), 4), p["symbol"]))

# --------------------------------------------- ⚡ actions
# same lines the email digest carries — anything with an action hint
# other than 'hold' is something the plan wants decided today
acts = [p for p in plans
        if (p.get("eval") or {}).get("action_hint") not in
        (None, "hold")]
if acts:
    st.subheader(f"⚡ Actions ({len(acts)})")
    for p in acts:
        evd = p.get("eval") or {}
        st.markdown(
            f"{_ICON.get(evd.get('status'),'⚡')} **{p['symbol']}** — "
            f"`{evd.get('status')}` → **{evd.get('action_hint')}** · "
            f"{evd.get('why') or ''}")
    st.divider()

st.subheader(f"Open plans ({len(plans)})")
_LBL = {"swing": "🎯", "invest": "🏦", "leap_call": "📞",
        "leap_put": "📕"}
for p in plans:
    evd = p.get("eval") or {}
    stt = evd.get("status") or "?"
    dirn = "short" if p.get("direction") == "short" else "long"
    r_txt = (f"**{p['r']:+.1f}R**" if p.get("r") is not None else "—")
    stop_txt = (f"stop **{float(p['stop_px']):.2f}**"
                if p.get("stop_px") else "no stop")
    days = f"{p['days']}d" if p.get("days") is not None else "—"
    head = (f"{_ICON.get(stt,'❓')} {sym_md(p['symbol'])} "
            f"{_LBL.get(p['use_case'],'')} `{p['use_case']}` {dirn} · "
            f"entry {float(p['entry_px']):.2f} · px {p.get('px') or '—'} · "
            f"{r_txt} · {days} · {stop_txt} → `{stt}`")
    with st.expander(head):
        st.markdown(f"**{evd.get('action_hint','—')}** — "
                    + (evd.get("why") or ""))
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**plan**\n\nstop {p.get('stop_px') or '—'} "
                    f"(`{p.get('stop_basis') or '—'}`)\n\n"
                    f"T1 {p.get('target1_px') or '—'} · "
                    f"T2 {p.get('target2_px') or '—'}")
        c2.markdown(f"**rules**\n\ntrail `{p.get('trail_rule') or '—'}`"
                    f"\n\ntime stop {p.get('time_stop_days') or '—'}d\n\n"
                    f"entry {p.get('entry_date')}")
        c3.markdown(f"**thesis**\n\n{p.get('thesis') or '—'}\n\n"
                    f"pulse `{stt}`")
        with st.form(f"close_{p['id']}"):
            cc1, cc2, cc3 = st.columns([1, 2, 1])
            cpx = cc1.number_input("close px",
                                   value=float(p.get("px") or 0),
                                   step=0.01)
            crs = cc2.text_input("reason",
                                 placeholder="stop hit / target / "
                                             "thesis dead / manual")
            if cc3.form_submit_button("close plan"):
                r2 = client.post(
                    f"api/v1/board/trade-plans/{p['id']}/close",
                    json_data={"close_px": cpx, "reason": crs}) or {}
                if r2.get("ok"):
                    st.cache_data.clear()
                    st.success("plan closed")
                    st.rerun()
        # delete — for accidentally-entered plans; gated behind an
        # explicit confirm so a stray click can't wipe a plan
        dcol, _ = st.columns([1, 3])
        sure = dcol.checkbox("⚠️ yes, delete this plan",
                             key=f"sure_{p['id']}")
        if sure and dcol.button("🗑 delete permanently",
                                key=f"del_{p['id']}"):
            r3 = client.delete(
                f"api/v1/board/trade-plans/{p['id']}") or {}
            if r3.get("ok"):
                st.cache_data.clear()
                st.success("plan deleted")
                st.rerun()
            else:
                st.error("delete failed")

# --------------------------------------------- closed
closed = d.get("closed") or []
if closed:
    st.divider()
    st.subheader(f"Closed ({len(closed)})")
    for p in closed:
        out_r = None
        if p.get("close_px") and p.get("stop_px"):
            risk = abs(float(p["entry_px"]) - float(p["stop_px"]))
            if risk:
                sgn = -1 if p.get("direction") == "short" else 1
                out_r = round((float(p["close_px"])
                               - float(p["entry_px"])) * sgn / risk, 2)
        st.caption(
            f"{sym_md(p['symbol'])} `{p['use_case']}` · "
            f"in {float(p['entry_px']):.2f} → "
            f"out {p.get('close_px') or '—'}"
            + (f" · **{out_r:+.1f}R**" if out_r is not None else "")
            + f" · {p.get('close_reason') or '—'}")
