"""Daily Sheet — tonight's best expressions.

Every engine says WHICH names; the sheet says HOW: stock at the armed
swing zone, a priced call LEAP, a priced put LEAP, or a put watch.
Journaled nightly (daily-sheet job, after conviction + hedge scan)
and graded on zone-hit + returns vs SPY. Advisory — you decide and
place the trade.
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar, sym_md
from api_client import APIClient
from api_config import api_config

setup_page_config("Daily Sheet", "📄")
render_sidebar()

client = APIClient(api_config.python_worker_url, timeout=120)


@st.cache_data(ttl=300, show_spinner=False)
def _sheet():
    try:
        return client.get("api/v1/board/daily-sheet") or {}
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=300, show_spinner=False)
def _perf():
    try:
        return client.get("api/v1/board/daily-sheet/performance") or {}
    except Exception:
        return {}


S = _sheet()
c_reload, c_recompute = st.columns([1, 2])
if c_reload.button("🔄 reload"):
    _sheet.clear()
    _perf.clear()
    st.rerun()
if c_recompute.button(
        "⚙️ recompute (runs stale deps)",
        help="runs the sheet's dependency chain — momentum → flywheel → "
             "tailwinds → hedge-universe → conviction → daily-sheet — "
             "skipping any job that succeeded in the last hour"):
    res = client.post("api/v1/board/recompute-sheet") or {}
    if res.get("status") == "started":
        _sheet.clear()
        st.success("recompute started — running: "
                   + ", ".join(res.get("running") or [])
                   + (" · skipped (fresh): "
                      + ", ".join(res.get("skipped_fresh") or [])
                      if res.get("skipped_fresh") else ""))
        st.caption("chain runs in the background — watch the jobs "
                   "catalog on Daily Board; reload in a few minutes")
    else:
        st.info(res.get("status") or "no response")

# freshness strip — the 1-hour rule is only useful if visible
try:
    st_jobs = (client.get("api/v1/board/refresh/status") or {}
               ).get("jobs") or {}
    deps = ["momentum", "flywheel", "tailwinds", "hedge-universe",
            "conviction", "daily-sheet"]
    bits = []
    for j in deps:
        d = st_jobs.get(j) or {}
        mark = "⏳" if d.get("running") else \
               ("✗" if d.get("error") else "·")
        bits.append(f"{mark} `{j}` "
                    f"{str(d.get('at') or 'never')[:16].replace('T',' ')}")
    st.caption("deps freshness (UTC): " + " · ".join(bits))
except Exception:
    pass

rows = S.get("rows") or []
st.title("📄 Daily Sheet")
env = S.get("env") or {}
bits = [f"**{S.get('snap_date') or '—'}**"]
if env.get("long_permission"):
    bits.append(f"market `{env['long_permission']}`")
if env.get("size_multiplier") is not None:
    bits.append(f"size ×{env['size_multiplier']}")
st.caption(" · ".join(bits) + " — conviction picks the names; "
           "the sheet picks the instrument + zone. Advisory only.")
if S.get("error") or (not rows and S):
    st.warning(S.get("error") or "no sheet yet — runs 23:30 UTC "
               "weekdays after conviction + hedge scan")


def _fmt_contract(c):
    if not c:
        return ""
    bits = [f"`{c.get('contract', '')}`", f"Δ{c.get('delta', '—')}",
            f"${c.get('mid', '—')}"]
    if c.get("expiry"):
        bits.append(str(c["expiry"])[:10])
    if c.get("iv_vs_hv"):
        bits.append(f"IV/HV {c['iv_vs_hv']}")
    if c.get("spread_pct") is not None:
        bits.append(f"spr {c['spread_pct']}%")
    if c.get("oi") is not None:
        bits.append(f"OI {c['oi']}")
    if c.get("roi_50") is not None:
        bits.append(f"ROI@+50% {c['roi_50']}%")
    return " · ".join(bits)


def _row(r):
    tag = ""
    if r.get("verdict") == "CALL":
        tag = "📞"
    elif r.get("verdict") == "PUT":
        tag = "📕"
    lo, hi = r.get("zone_lo"), r.get("zone_hi")
    if lo and hi:
        zone = (f"zone **${lo:,.0f}–${hi:,.0f}**"
                if abs(hi - lo) > 1 else f"zone **~${hi:,.0f}**")
    elif hi:
        zone = f"zone **${hi:,.0f}**"
    else:
        zone = "no zone yet"
    stop = (f" · stop ${r['stop_px']:,.0f}" if r.get("stop_px") else "")
    trig = (f" · trigger ${r['trigger_px']:,.0f}"
            if r.get("trigger_px") else "")
    fv = ""
    if r.get("fv_upside_pct") is not None:
        warn = " ⚠️ stretched" if r["fv_upside_pct"] <= -20 else ""
        fv = f" · fv {r['fv_upside_pct']:+.0f}%{warn}"
    st.markdown(f"{tag} **{sym_md(r['symbol'])}** — `{r['verdict']}` "
                f"`{r.get('cycle_stage') or '—'}` · {zone}{stop}{trig}{fv}")
    ct = _fmt_contract(r.get("contract"))
    if ct:
        st.caption(f"&nbsp;&nbsp;&nbsp;{ct}")
    at = _fmt_contract(r.get("alt"))
    if at:
        st.caption(f"&nbsp;&nbsp;&nbsp;alt (flip): {at}")
    for w in (r.get("reasons") or [])[:2]:
        st.caption(f"&nbsp;&nbsp;&nbsp;· {w[:140]}")


_SEC = [("call_leap", "📞 CALL LEAPs — pull-back-and-rally"),
        ("stock_zone", "📈 STOCK ZONES — armed entry bands"),
        ("put_leap", "📕 PUT LEAPs — extended + fresh stall"),
        ("put_watch", "👁 PUT WATCH — armed, waiting on confirmation")]
for key, title in _SEC:
    rs = [r for r in rows if r.get("section") == key]
    if not rs:
        continue
    st.subheader(f"{title} ({len(rs)})")
    for r in rs:
        _row(r)

st.divider()
st.subheader("📋 Sheet track record")
perf = _perf()
bs = perf.get("by_section") or []
if bs:
    for b in bs:
        n = b.get("n") or 0
        zh = b.get("zone_hit_rate")
        st.caption(
            f"`{b['section']:10}` n={n}"
            + (f" · zone-hit {zh:.0%}" if zh is not None else "")
            + (f" · avg +5d {b['r5']:+.1%}" if b.get("r5") is not None
               else "")
            + (f" · avg +20d {b['r20']:+.1%} (SPY {b['vs']:+.1%})"
               if b.get("r20") is not None else ""))
else:
    st.caption("grading starts once rows are ~8 days old")
