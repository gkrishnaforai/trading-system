"""Swing Screener — which held/watched stocks have a buyable setup right now.

Runs the real analyze_stock + detect_setup across the universe, ranked by the
criteria the backtest validated: practice patterns first (first_pullback /
rsi2_extreme), then setup score. Expand a row → full swing review → trade card.
"""
import sys
import os
import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient, APIError, APIConnectionError
from api_config import api_config
from utils import render_top_nav, health_col, health_cfg, sym_md
from trade_card import render_trade_card, render_universe_expander

python_client = APIClient(api_config.python_worker_url, timeout=120)

st.set_page_config(page_title="Swing Screener", page_icon="🔍", layout="wide")
render_top_nav()

_PERM_ICON = {"allowed": "🟢", "limited": "🟡", "restricted": "🟠",
              "disabled": "🔴", "unknown": "⚪"}
_PRACTICE = {"first_pullback", "rsi2_extreme"}


def _age(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
        if mins < 60:
            return f"{mins}m ago"
        if mins < 60 * 24:
            return f"{mins // 60}h ago"
        return f"{mins // (60 * 24)}d ago"
    except Exception:
        return ""


st.title("🔍 Swing Screener")
st.caption(
    "Setup scan over portfolio + watchlist — ranked by practice patterns "
    "(first_pullback · rsi2_extreme) then score. Nothing executes.")

with st.expander("📖 Legend — what every symbol means & how to pick"):
    st.markdown("""
**Stock regime icon** (left of each symbol — the stock's *own* trend health)

| Icon | Meaning |
|---|---|
| 🟢 `allowed` | Above SMA50 + SMA200, positive momentum — trend intact |
| 🟡 `limited` | Trend mostly intact but soft — half-size territory |
| 🟠 `restricted` | Stock weak — momentum broken |
| 🔴 `disabled` | Below SMA200 — the full no-no for trend setups |
| 🟣 `turn` | 🔴/🟠 regime **but** strong fundamentals/catalyst — early-turn profile, watchlist/half-size |
| ⚪ `unknown` | Insufficient history |

**Badges**

| Badge | Meaning |
|---|---|
| ✅ `ready` | Passes the scan-level checklist: entry setup (`first_pullback` / `rsi2_extreme` / `breakout`) + regimes ok + no knife + score ≥ 60 — `episodic_pivot` needs `strong` fundamentals instead of stock regime |
|| 🚀 `episodic_pivot` | High-volume thrust off a beaten-down base before trend confirms — counter-trend entry |
| ⭐ `practice` | One of your two validated patterns fired (`first_pullback` / `rsi2_extreme`) |
| `HELD` / `WATCH` | In portfolio / watchlist-only |
| `FV +x%` | Our fair value vs price (≥+15% votes strong, ≤−10% votes weak) |
| `PT +x%` | Analyst consensus target vs price |
| `EPS ±x%` | Latest annual EPS-estimate revision (needs 2+ daily snapshots) |
| 🎓 `upgrade` / 🔻 `downgrade` | Analyst grade change in last 14 days |
| ⚡ `positive:…` / `negative:…` | Latest catalyst alert direction |

**Score** = setup quality 0–100 (pattern base + strength/sector/volume/higher-low bonuses − regime penalties + empirical calibration).

**Expander metrics** — Entry/Stop/Target = the trade plan (stop = 2×ATR, target = 2R).
`Turn` = bars since the SMA50 trend turn (feeds first_pullback). `Vol` = today's
volume vs 20d average. `20d ret` + `vs SPY 20d` = momentum and relative
strength — the engine's trend + RS inputs. `Mkt perm` + `Size mult` = the
market regime's aggressiveness gate and sizing multiplier. `⏳ not ready`
lists exactly which ready-gate failed.

**How to pick:** `✅ Ready to buy` → expand row → check entry/stop/target →
**Full swing review** → trade card practice checklist. `✅ TAKE` = all five
checks pass. 🟣 rows are *watch*, not buy — they become entries when the
regime flips. Nothing on this page places trades.
""")

view = st.radio("Show", ["All", "⭐ Practice", "✅ Ready to buy",
                         "🔄 Turn candidates"], horizontal=True)
cat_filter = st.radio("Catalyst", ["Any", "⚡ positive", "⚡ negative",
                                   "🎓 upgrades"], horizontal=True)
c1, c2, c3 = st.columns([1, 2, 2])
hide_no_setup = c1.toggle("Hide no_setup", value=True)
min_score = c2.slider("Min score", 0, 100, 0)

if c3.button("▶ Run screen", type="primary", use_container_width=True):
    try:
        res = python_client.post("api/v1/screener/run", json_data={})
        if res.get("status") == "started":
            st.toast("Screen started — scanning the universe in background")
            st.rerun()
        elif res.get("status") == "already_running":
            st.info("A screen is already running")
    except (APIConnectionError, APIError) as e:
        st.error(f"Screen failed to start: {e}")

try:
    status = python_client.get("api/v1/screener/status") or {}
except (APIConnectionError, APIError):
    status = {}

if status.get("running"):
    st.info("⏳ Screening in progress — page refreshes automatically.")
    time.sleep(8)
    st.rerun()

# --- 🎯 Breakout watch — names parked under their 20d-high pivot ----------
# EOD scan populates candidates within 5% of the pivot; the hourly alert
# scan checks live quotes and alerts the hour price crosses — instead of
# the breakout only appearing "ready" at the next EOD scan.
try:
    watch = python_client.get("api/v1/screener/breakout-watch") or {}
except (APIConnectionError, APIError):
    watch = {}
watch_items = watch.get("items") or []
if watch_items:
    wcol1, wcol2 = st.columns([3, 1])
    wcol1.subheader("🎯 Breakout watch")
    if wcol2.button("↻ check prices now", key="bw_refresh"):
        with st.spinner("Checking quotes vs pivots…"):
            try:
                res = python_client.post("api/v1/screener/breakout-watch/refresh",
                                         json_data={})
                st.toast(f"Checked {res.get('checked', 0)} · "
                         f"triggered {res.get('triggered', 0)}")
                st.rerun()
            except (APIConnectionError, APIError) as e:
                st.error(f"Refresh failed: {e}")
    wdf = pd.DataFrame(watch_items)
    wdf["dist%"] = pd.to_numeric(wdf["distance_pct"], errors="coerce").round(2)
    wdf["pivot"] = pd.to_numeric(wdf["pivot"], errors="coerce").round(2)
    wdf["last"] = pd.to_numeric(wdf["last_price"], errors="coerce").round(2)
    wdf["status"] = wdf["status"].map(
        {"watching": "👀 watching", "triggered": "🚀 triggered",
         "expired": "expired"}).fillna(wdf["status"])
    keep = ["symbol", "status", "pivot", "last", "dist%", "score",
            "days_on_watch", "setup_type"]
    st.dataframe(health_col(wdf[[c for c in keep if c in wdf.columns]]),
                 column_config={"🩺": health_cfg()},
                 use_container_width=True, hide_index=True)
    st.caption("`dist%` = last price vs pivot (negative = below the level). "
               "Within −1% → `breakout_approach` alert · cross → "
               "`breakout_trigger` alert (both appear in Alerts Briefing). "
               "Entry plan: buy the cross with a tight stop, not the +7% close.")

try:
    data = python_client.get("api/v1/screener/results") or {}
except (APIConnectionError, APIError) as e:
    st.error(f"Cannot reach screener API: {e}")
    st.stop()

items = data.get("items") or []

# --- run history — view a previous scan's results ---------------------------
try:
    _runs = (python_client.get("api/v1/screener/history") or {}).get("runs") or []
except (APIConnectionError, APIError):
    _runs = []
if _runs:
    # "latest" already covers the newest run (live or persisted fallback)
    _labels = {
        r["id"]: f"{_age(str(r['ran_at']))} · {r.get('result_count', 0)} candidates"
        for r in _runs[1:]}
    _sel = st.selectbox(
        "📜 Run", ["latest"] + list(_labels),
        format_func=lambda x: "latest" if x == "latest" else _labels[x])
    if _sel != "latest":
        try:
            _past = python_client.get(f"api/v1/screener/history/{_sel}") or {}
            items = _past.get("items") or []
            st.caption(f"🕘 viewing run from {_age(str(_past.get('as_of') or ''))} "
                       f"— {_past.get('count', 0)} candidates")
        except (APIConnectionError, APIError) as e:
            st.error(f"Cannot load run: {e}")

if data.get("as_of"):
    _stale = False
    try:
        _last = datetime.fromisoformat(str(data["as_of"]).replace("Z", "+00:00"))
        _stale = (datetime.now(timezone.utc) - _last).total_seconds() > 20 * 3600
    except Exception:
        pass
    st.caption(f"Last screen {_age(data['as_of'])} · {data.get('count', 0)} candidates"
               + (" · ⚠️ stale — click ▶ Run screen to refresh" if _stale else "")
               + (f" · {len(data['errors'])} errors" if data.get("errors") else ""))
if data.get("errors"):
    with st.expander("Symbol errors"):
        for e in data["errors"]:
            st.write(f"- {e}")

if not items:
    st.info("No results yet — hit 'Run screen' to scan the universe.")
    st.stop()

# --- � Breadth — is the tape improving? ------------------------------------
# Each run is a full-universe regime census; the series across runs is the
# market-breadth signal. Thrust = rapid improvement (historically strong).
try:
    _br = python_client.get("api/v1/screener/breadth") or {}
except (APIConnectionError, APIError):
    _br = {}
_cur = _br.get("current") or {}
if _cur.get("universe"):
    bc1, bc2, bc3, bc4, bc5 = st.columns(5)
    bc1.metric("Uptrend", f"{_cur.get('uptrend_pct', 0)}%",
               delta=(f"{_cur['uptrend_delta']:+.1f}pts" if _cur.get("uptrend_delta") is not None else None))
    bc2.metric("Downtrend", f"{_cur.get('downtrend_pct', 0)}%")
    bc3.metric("Turning up", _cur.get("turning", 0))
    bc4.metric("New uptrends", len(_cur.get("new_uptrends") or []))
    bc5.metric("Breadth thrust", "⚡ yes" if _cur.get("thrust") else "—",
               help="Rapid breadth improvement — historically a strong market buy signal")
    if _cur.get("new_uptrends"):
        st.caption("⬆ entered uptrend this run: "
                   + " · ".join(_cur["new_uptrends"]))
    if _cur.get("new_downtrends"):
        st.caption("⬇ entered downtrend this run: "
                   + " · ".join(_cur["new_downtrends"]))

# --- 🔀 Run diff — who's improving / deteriorating --------------------------
try:
    _diff = python_client.get("api/v1/screener/diff") or {}
except (APIConnectionError, APIError):
    _diff = {}
def _sd(r: dict) -> str:
    v = r.get("score_delta")
    return f"{v:+.0f}" if isinstance(v, (int, float)) else "—"


if _diff.get("available"):
    with st.expander("🔀 Momentum shift — run-over-run changes", expanded=False):
        d1, d2, d3 = st.columns(3)
        with d1:
            st.markdown("**⬆ Improving**")
            for r in (_diff.get("improving") or [])[:10]:
                st.caption(f"{sym_md(r['symbol'])} · {r.get('perm','')} · "
                           f"score {_sd(r)} "
                           f"· {r.get('setup') or ''}")
        with d2:
            st.markdown("**⬇ Deteriorating**")
            for r in (_diff.get("deteriorating") or [])[:10]:
                st.caption(f"{sym_md(r['symbol'])} · {r.get('perm','')} · "
                           f"score {_sd(r)}")
        with d3:
            st.markdown("**🎯 Approaching pivot**")
            st.caption("Improving AND within 5% of the 20d high — "
                       "next candidates for breakout watch")
            for r in (_diff.get("approaching_pivot") or [])[:10]:
                st.caption(f"{sym_md(r['symbol'])} · {r.get('dist_to_pivot')}% "
                           f"to pivot · score {r.get('score')}")

# --- �📊 EOD regime board — tomorrow's tape at a glance ----------------------
# Group the whole scan by stock regime: who's in uptrend (allowed), who's
# weakening, who's in downtrend, who's turning up. One glance answers
# "what's the tape giving me tomorrow" without scanning 130+ rows.
_PULLBACK_SETUPS = {"mean_reversion", "first_pullback"}

def _regime_bucket(r: dict) -> str:
    if r.get("falling_knife"):
        return "🔪 falling knife"
    if r.get("turn_candidate"):
        return "🟣 turning up"
    # Weakness that IS the entry — a limited stock with a live MR/pullback
    # setup is actionable, not just decaying. Stays honest: restricted/
    # disabled names never land here, and neither do weak names with no setup.
    if (r.get("stock_permission") == "limited"
            and r.get("setup_type") in _PULLBACK_SETUPS
            and (r.get("score") or 0) >= 60):
        return "🎯 pullback entry"
    # Rubber-band extension: uptrend but price at/above the upper
    # Bollinger band (%b ≥ 1.0 = >2σ stretch) → trim zone, not entry.
    if (r.get("stock_permission") == "allowed"
            and (r.get("pctb") or 0) >= 1.0):
        return "🎈 extended"
    return {"allowed": "🟢 uptrend", "limited": "🟡 weakening",
            "restricted": "🟠 restricted", "disabled": "🔴 downtrend"}.get(
            r.get("stock_permission"), "⚪ unknown")

_buckets: dict[str, list] = {}
for _r in items:
    _buckets.setdefault(_regime_bucket(_r), []).append(_r)
_order = ["🟢 uptrend", "🎈 extended", "🎯 pullback entry", "🟣 turning up",
          "🟡 weakening", "🟠 restricted", "🔴 downtrend", "🔪 falling knife",
          "⚪ unknown"]
_ACTION = {
    "🟢 uptrend": "✅ ENTER",
    "🎈 extended": "✂️ TRIM",
    "🎯 pullback entry": "✅ ENTER",
    "🟣 turning up": "👁 WATCH",
    "🟡 weakening": "⏸ WAIT",
    "🟠 restricted": "🚫 AVOID",
    "🔴 downtrend": "🚫 AVOID",
    "🔪 falling knife": "🚫 AVOID",
    "⚪ unknown": "—",
}
with st.expander("📊 Regime board — who's in uptrend / downtrend into tomorrow",
                 expanded=True):
    _bh1, _bh2 = st.columns([5, 1])
    with _bh2:
        if st.button("⟳ recompute board",
                     help="runs a fresh screen — recomputes every bucket "
                     "incl. %b/extension/squeeze fields"):
            try:
                python_client.post("api/v1/screener/run", json_data={})
                st.toast("Screen started — board refreshes when it lands")
            except Exception as e:
                st.error(f"Screen start failed: {e}")
        if (status or {}).get("running"):
            if st.button("⟳ check", key="chk_board"):
                st.rerun()
    _bh1.caption(
        "🎈 extended + ⚡ squeeze + →$ targets need a post-upgrade scan — "
        "if the 🎈 column is empty everywhere, hit ⟳ recompute.")
    _cols = st.columns(len(_order))
    for _col, _b in zip(_cols, _order):
        _rows_b = sorted(_buckets.get(_b) or [],
                       key=lambda r: -(r.get("score") or 0))
        _col.markdown(f"**{_b}** · {len(_rows_b)}")
        _col.caption(_ACTION.get(_b, ("—",))[0])
        # scrollable — every symbol visible, no truncation
        with _col.container(height=240):
            for r in _rows_b:
                _coil = " ⚡" if r.get("bb_squeeze") else ""
                if _b == "🎈 extended" and r.get("sma20"):
                    _x = f" → ${r['sma20']:,.0f}"
                elif _b == "🎯 pullback entry" and r.get("pivot"):
                    _x = f" → ${r['pivot']:,.0f}"
                else:
                    _x = ""
                st.caption(f"{sym_md(r['symbol'])} · {r.get('score', 0):.0f}{_x}{_coil}")
    st.markdown("**What each bucket means for you** — regime = the stock's "
                "*own* trend (SMA50/SMA200/momentum), not the market's:")
    st.dataframe(pd.DataFrame([
        {"bucket": "🟢 uptrend", "action": "✅ ENTER",
         "rule": "above SMA50+SMA200, momentum positive — buy the entry "
                 "setups (pullback/retest/breakout) at score ≥60"},
        {"bucket": "🎈 extended", "action": "✂️ TRIM",
         "rule": "uptrend but price ≥2σ above the 20d mean (%b≥1) — "
                 "trim into strength, don't chase; →$ = the SMA20 it "
                 "tends to revert to"},
        {"bucket": "🎯 pullback entry", "action": "✅ ENTER",
         "rule": "trend weakening **with** a live pullback/mean-reversion "
                 "setup — the weakness IS the entry"},
        {"bucket": "🟣 turning up", "action": "👁 WATCH",
         "rule": "downtrend but strong fundamentals/catalyst — becomes an "
                 "entry when the regime flips; do not buy yet"},
        {"bucket": "🟡 weakening", "action": "⏸ WAIT",
         "rule": "trend soft, no live setup — nothing to do; half-size if "
                 "a setup appears later"},
        {"bucket": "🟠 restricted", "action": "🚫 AVOID",
         "rule": "momentum broken — can never be ready"},
        {"bucket": "🔴 downtrend", "action": "🚫 AVOID",
         "rule": "below SMA200 — the full no-no for trend setups"},
        {"bucket": "🔪 falling knife", "action": "🚫 AVOID",
         "rule": "hard veto — vertical drop; knife-catching is how "
                 "accounts die"},
        {"bucket": "⚪ unknown", "action": "—",
         "rule": "insufficient history to classify"},
    ]), use_container_width=True, hide_index=True)
    st.caption("\u26a1 suffix = Bollinger squeeze \u2014 volatility at a 6-month "
               "low (coiled; a move is coming, direction TBD \u2014 watch for "
               "the break). \u2192$ on \U0001f388 = SMA20 reversion target \u00b7 on \U0001f3af = "
               "the pivot it bounces back toward.")

_ENTRY_SETUPS = {"first_pullback", "mean_reversion", "breakout",
                 "breakout_retest"}

_MOM_I = {"climax": "🔥", "breakout": "🚀", "uptrend": "📈",
          "recovery": "🌱", "basing": "😴", "pullback": "🟢",
          "rolling_over": "🟠", "knife": "🔪", "capitulation": "💥",
          "breakdown": "⬇️", "downtrend": "📉"}


def _not_ready_reasons(it: dict) -> list[str]:
    """Which ready-gate(s) failed — shown so a skipped row explains itself."""
    gaps = []
    if it.get("falling_knife"):
        gaps.append("falling knife")
    if it.get("market_permission", "allowed") not in {"allowed", "limited"}:
        gaps.append(f"market {it.get('market_permission')}")
    st_ = it.get("setup_type")
    if st_ == "episodic_pivot":
        if it.get("fund_signal") != "strong":
            gaps.append(f"fundamentals {it.get('fund_signal') or 'unknown'} — EP needs strong")
    elif st_ not in _ENTRY_SETUPS:
        gaps.append(f"`{st_}` is not an entry setup")
    elif it.get("stock_permission") not in {"allowed", "limited"}:
        gaps.append(f"stock regime {it.get('stock_permission')}")
    if (it.get("score") or 0) < 60:
        gaps.append(f"score {it.get('score', 0):.0f} < 60")
    return gaps


def _ready(it: dict) -> bool:
    """Deterministic scan-level approximation of the practice checklist.

    Full risk gate + vetoes still require the per-symbol review."""
    if it.get("falling_knife"):
        return False
    if it.get("market_permission", "allowed") not in {"allowed", "limited"}:
        return False
    if it.get("setup_type") == "episodic_pivot":
        # Counter-trend ignition — the fundamental overlay substitutes for
        # the missing trend regime; weak-regime stocks are the design target.
        return bool(
            it.get("fund_signal") == "strong"
            and it.get("score", 0) >= 60
        )
    return bool(
        it.get("setup_type") in _ENTRY_SETUPS
        and it.get("stock_permission") in {"allowed", "limited"}
        and it.get("score", 0) >= 60
    )


# --- filters ---
rows = []
for it in items:
    pats = set(it.get("detected_patterns") or [])
    if view == "⭐ Practice" and not (pats & _PRACTICE):
        continue
    if view == "✅ Ready to buy" and not _ready(it):
        continue
    if view == "🔄 Turn candidates" and not it.get("turn_candidate"):
        continue
    if cat_filter == "⚡ positive" and not (
            it.get("catalyst_direction") == "positive"
            or it.get("grade_action") == "upgrade"
            or (it.get("eps_delta_pct") or 0) >= 5):
        continue
    if cat_filter == "⚡ negative" and not (
            it.get("catalyst_direction") == "negative"
            or it.get("grade_action") == "downgrade"
            or (it.get("eps_delta_pct") or 0) <= -5):
        continue
    if cat_filter == "🎓 upgrades" and it.get("grade_action") != "upgrade":
        continue
    if hide_no_setup and it.get("setup_type") == "no_setup":
        continue
    if it.get("score", 0) < min_score:
        continue
    rows.append(it)

# --- 📦 Open trades monitor — exit suggestions on what you hold ---
try:
    _mon = python_client.get("api/v1/trades/open") or {}
    _tsum = python_client.get("api/v1/trades/summary") or {}
except (APIConnectionError, APIError):
    _mon, _tsum = {}, {}

_open = _mon.get("items") or []
if _open:
    if _tsum.get("closed_n"):
        st.caption(f"💰 Realized P&L ${(_tsum.get('realized_pl') or 0):,.0f} · "
                   f"win rate {(_tsum.get('win_rate') or 0) * 100:.0f}% "
                   f"over {_tsum['closed_n']} closed trades")
    st.subheader(f"📦 Open trades — {len(_open)}")
    for tr in _open:
        flags = tr.get("flags") or []
        icon = ("🔴" if flags & {"STOP_HIT", "TRAIL_STOP", "DISTRIBUTION",
                                 "REGIME_FLIP"}
                else "💰" if flags & {"CLIMAX", "GAIN_100", "GAIN_50",
                                      "T1_HIT", "EXTENDED"}
                else "🟢" if (tr.get("gain_pct") or 0) > 0 else "🟡")
        with st.expander(
                f"{icon} **{sym_md(tr['symbol'])}** `{tr['trade_type']}` — "
                f"{tr.get('open_qty', 0):g} @ ${tr['entry_price']:,.2f} → "
                f"${(tr.get('current_price') or 0):,.2f} · "
                f"{(tr.get('gain_pct') or 0):+.1f}% · **{tr['suggestion']}**", expanded=False):
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("P&L", f"${(tr.get('unrealized_pl') or 0):,.0f}",
                      delta=f"{(tr.get('gain_pct') or 0):+.1f}%")
            c2.metric("R now", tr.get("r_now"))
            c3.metric("To stop", f"{tr['pct_to_stop']}%" if tr.get("pct_to_stop") is not None else "—")
            c4.metric("To T1", f"{tr['pct_to_t1']}%" if tr.get("pct_to_t1") is not None else "—")
            c5.metric("Held", f"{tr.get('days_held')}d / {tr.get('bars_held')} bars")
            m1, m2, m3 = st.columns(3)
            m1.metric("Trail stop",
                      f"${tr['trail_stop']:,.2f}" if tr.get("trail_stop") else "—",
                      delta=(f"{tr['trail_pct_below']}% below" if tr.get("trail_pct_below") is not None else None),
                      help="Chandelier: highest close since entry − 3×ATR, ratchets up only")
            m2.metric("vs SMA50",
                      f"{tr['pct_above_sma50']:+.1f}%" if tr.get("pct_above_sma50") is not None else "—",
                      help=">20% = extended (trim zone)")
            m3.metric("Base range",
                      f"{tr['consol_range_pct']}%" if tr.get("consol_range_pct") is not None else "—",
                      help="10-bar high-low span — <8% = tight consolidation")
            if flags:
                st.markdown("**Flags:** " + " ".join(f"`{f}`" for f in flags))
            ec1, ec2, ec3, ec4 = st.columns(4)
            ex_px = ec1.number_input("Exit $", value=float(tr.get("current_price") or 0),
                                     key=f"expx_{tr['id']}")
            ex_q = ec2.number_input("Qty", value=float(tr.get("open_qty") or 0),
                                    min_value=0.0, key=f"exq_{tr['id']}")
            ex_r = ec3.selectbox("Reason",
                                 ["manual", "stop", "t1", "t2", "profit_band",
                                  "bounce", "time", "regime", "thesis"],
                                 key=f"exr_{tr['id']}")
            if ec4.button("Log exit", key=f"exb_{tr['id']}", type="primary"):
                try:
                    python_client.post(f"api/v1/trades/{tr['id']}/exit",
                                       json_data={"price": ex_px, "qty": ex_q,
                                                  "reason": ex_r})
                    st.success("Exit logged")
                    st.rerun()
                except (APIConnectionError, APIError) as e:
                    st.error(f"Exit failed: {e}")

st.subheader(f"{len(rows)} candidates")

for it in rows:
    # 🟣 turn candidate: weak stock regime but strong fundamentals/catalyst —
    # distinct from 🔴 (weak stock + nothing underneath = no-no)
    icon = "🟣" if it.get("turn_candidate") else _PERM_ICON.get(
        it.get("stock_permission"), "⚪")
    fv = it.get("fv_upside_pct")
    pt = it.get("pt_upside_pct")
    grade = it.get("grade_action")
    badges = " ".join(
        b for b in [
            "✅ `ready`" if _ready(it) else "",
            "🔄 `turn`" if it.get("turn_candidate") else "",
            "`HELD`" if it.get("in_portfolio") else "",
            "`WATCH`" if it.get("in_watchlist") else "",
            "⭐ `practice`" if it.get("practice") else "",
            "🎓 `upgrade`" if grade == "upgrade" else "",
            "🔻 `downgrade`" if grade == "downgrade" else "",
            f"`FV {fv:+.0f}%`" if fv is not None else "",
            f"`PT {pt:+.0f}%`" if pt is not None else "",
            (f"`EPS {it['eps_delta_pct']:+.0f}%"
              + (f" FY{str(it['eps_fiscal_year'])[-2:]}" if it.get("eps_fiscal_year") else "")
              + "`" if it.get("eps_delta_pct") is not None else ""),
            f"⚡ `{it['catalyst']}`" if it.get("catalyst") else "",
            # canonical symbol-level momentum flag (stocks.momentum_state)
            # — context badge only; the swing engine's own fine-grained
            # regime (episodic_pivot is deliberately counter-trend)
            # stays authoritative for setup eligibility
            (f"{_MOM_I.get(it['momentum'], '⚪')} `{it['momentum']}`"
             if it.get("momentum") else ""),
        ] if b)
    pats = " ".join(f"`{p}`" for p in (it.get("detected_patterns") or []))
    header = (
        f"{icon} **{sym_md(it['symbol'])}** — `{it['setup_type']}` · score "
        f"**{it['score']:.0f}** · stk `{it.get('stock_permission', '?')}` "
        f"· ${it.get('price', 0):,.2f} · {badges}"
    )
    with st.expander(header, expanded=False):
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Entry", f"${it['entry']:,.2f}" if it.get("entry") else "n/a")
        c2.metric("Stop", f"${it['stop']:,.2f}" if it.get("stop") else "n/a")
        c3.metric("Target", f"${it['target']:,.2f}" if it.get("target") else "n/a")
        c4.metric("RSI", f"{it['rsi']:.0f}" if it.get("rsi") is not None else "n/a",
                  delta=f"RSI2 {it['rsi2']:.0f}" if it.get("rsi2") is not None else None)
        c5.metric("Turn", f"{it['trend_turn_bars']} bars" if it.get("trend_turn_bars") is not None else "—")
        c6.metric("Vol", f"{it['volume_ratio']:.1f}×" if it.get("volume_ratio") else "n/a")
        # second row: momentum context + market regime that gates the trade
        d1, d2, d3, d4, d5, d6 = st.columns(6)
        d1.metric("20d ret", f"{it['ret20'] * 100:+.1f}%" if it.get("ret20") is not None else "n/a")
        d2.metric("vs SPY 20d", f"{it['vs_spy20'] * 100:+.1f}%" if it.get("vs_spy20") is not None else "n/a")
        d3.metric("ATR", f"{it['atr_pct'] * 100:.1f}%" if it.get("atr_pct") else "n/a")
        d4.metric("Mkt perm", it.get("market_permission") or "n/a")
        d5.metric("Size mult", f"{it['size_multiplier']:g}×" if it.get("size_multiplier") is not None else "n/a")
        d6.metric("Quality", it.get("quality") or "n/a")
        if pats:
            st.markdown(f"**Patterns:** {pats}")
        if it.get("setup_type") == "mean_reversion":
            st.caption("↩️ MR exit: sell on the first close above the prior day's high, "
                       "or after 5 bars — the 2R target does not apply.")
        fund = it.get("fund_signal")
        if fund and fund != "unknown":
            fv_txt = (f"FV {it['fv_upside_pct']:+.0f}%"
                      if it.get("fv_upside_pct") is not None else "no FV")
            pt_txt = (f" · PT ${it['pt_target']:,.0f} ({it['pt_upside_pct']:+.0f}%, "
                      f"{it.get('pt_analysts') or '?'} analysts)"
                      if it.get("pt_upside_pct") is not None else "")
            grade_txt = (f" · {it['grade_action']} {it.get('grade_detail') or ''}"
                         if it.get("grade_action") else "")
            st.caption(f"Fundamentals: **{fund}** · {fv_txt}{pt_txt}{grade_txt}"
                       + (f" · catalyst {it['catalyst']}" if it.get("catalyst") else ""))
        for r in (it.get("reasons") or [])[:4]:
            st.caption(f"· {r}")
        if not _ready(it):
            gaps = _not_ready_reasons(it)
            if gaps:
                st.caption("⏳ not ready — " + " · ".join(gaps))

        cache_key = f"screen_review_{it['symbol']}"
        cached = st.session_state.get(cache_key)
        if st.button("📊 Full swing review", key=f"full_{it['symbol']}"):
            with st.spinner(f"Running full analysis for {it['symbol']}…"):
                try:
                    res = python_client.post(f"api/v1/screener/review/{it['symbol']}")
                    st.session_state[cache_key] = res
                    cached = res
                except (APIConnectionError, APIError) as e:
                    st.error(f"Review failed: {e}")
        if cached:
            render_trade_card(cached.get("result") or {}, it["symbol"])

        if st.checkbox("📝 Log trade", key=f"log_{it['symbol']}"):
            lc = st.columns(5)
            l_qty = lc[0].number_input("Shares", min_value=0.0, value=10.0,
                                       key=f"lq_{it['symbol']}")
            l_entry = lc[1].number_input("Entry", value=float(it.get("price") or 0),
                                         key=f"le_{it['symbol']}")
            l_stop = lc[2].number_input("Stop", value=float(it.get("stop") or 0),
                                        key=f"ls_{it['symbol']}")
            l_t1 = lc[3].number_input("Target", value=float(it.get("target") or 0),
                                      key=f"lt_{it['symbol']}")
            l_type = lc[4].selectbox("Type", ["swing", "day", "investment"],
                                     key=f"lty_{it['symbol']}")
            if st.button("Save trade", key=f"lb_{it['symbol']}", type="primary"):
                try:
                    python_client.post("api/v1/trades", json_data={
                        "symbol": it["symbol"], "trade_type": l_type,
                        "entry_price": l_entry, "shares": l_qty,
                        "initial_stop": l_stop, "target_1": l_t1,
                        "setup_type": it.get("setup_type"),
                        "regime_snapshot": {
                            "stock_permission": it.get("stock_permission"),
                            "market_permission": it.get("market_permission"),
                        },
                    })
                    st.success(f"Logged {it['symbol']} {l_type} trade")
                    st.rerun()
                except (APIConnectionError, APIError) as e:
                    st.error(f"Log failed: {e}")


render_universe_expander(python_client)
