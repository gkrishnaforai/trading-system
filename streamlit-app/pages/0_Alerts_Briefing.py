"""Alerts & Briefing — morning cockpit.

Regime card + ranked catalyst inbox for the portfolio ∪ watchlist universe.
Alerts never decide; each can trigger a full swing review on demand.
"""
import sys
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient, APIError, APIConnectionError
from api_config import api_config
from trade_card import render_trade_card, render_universe_expander
from utils import render_top_nav

python_client = APIClient(api_config.python_worker_url, timeout=120)

st.set_page_config(page_title="Alerts & Briefing", page_icon="🔔", layout="wide")
render_top_nav()


def alerts_get(endpoint: str, params=None):
    return python_client.get(f"api/v1/alerts/{endpoint.lstrip('/')}", params=params)


def alerts_post(endpoint: str, data=None):
    return python_client.post(f"api/v1/alerts/{endpoint.lstrip('/')}", json_data=data)


_DIR_ICON = {"POSITIVE": "🟢", "NEGATIVE": "🔴", "MIXED": "🟡", "NEUTRAL": "⚪"}
_MAT_COLOR = {"HIGH": "🔥", "MODERATE": "🔶", "LOW": "🔹"}

# canonical stocks.momentum_state — group bearish vs bullish regimes so an
# alert row instantly shows whether the tape agrees with the catalyst
_MOM_BEAR = {"knife", "capitulation", "breakdown", "downtrend", "rolling_over"}
_MOM_BULL = {"breakout", "uptrend", "recovery", "climax"}
_MOM_ICON = {"climax": "🔥", "breakout": "🚀", "uptrend": "📈",
             "recovery": "🌱", "basing": "😴", "pullback": "🟢",
             "rolling_over": "🟠", "knife": "🔪", "capitulation": "💥",
             "breakdown": "⬇️", "downtrend": "📉"}


def _mom_badge(item: dict) -> str:
    """Compact momentum flag for the alert header — 🔴 bearish tape,
    🟢 bullish tape, so a POSITIVE alert on a knife reads as a warning
    and a NEGATIVE alert on a knife reads as confirmation."""
    mom = item.get("momentum")
    if not mom:
        return ""
    if mom in _MOM_BEAR:
        mark = "🔴"
    elif mom in _MOM_BULL:
        mark = "🟢"
    else:
        mark = "⚪"
    return f"{mark}{_MOM_ICON.get(mom, '')} `{mom}`"


_FUND_ICON = {"accelerating": "🟢⚡", "growing": "🟢", "watch": "🟡",
              "cyclical": "🔵", "slowing": "🟠", "declining": "🔻",
              "deteriorating": "🔴", "unknown": "⚪"}


def _fund_badge(item: dict) -> str:
    """Compact fundamental flag for the alert header — the 'how is the
    company' axis next to the tape flag; ⚠️ suffix when the week-over-
    week change alert is elevated."""
    fs = item.get("fund_state")
    if not fs:
        return ""
    warn = "⚠️" if item.get("fund_alert") in ("warning", "critical") else ""
    return f"{_FUND_ICON.get(fs, '')} `{fs}`{warn}"


def _mom_read(item: dict) -> str:
    """One line: does the tape confirm or fight the alert direction?"""
    mom = item.get("momentum")
    if not mom:
        return ""
    bear, bull = mom in _MOM_BEAR, mom in _MOM_BULL
    neg, pos = item["direction"] == "NEGATIVE", item["direction"] == "POSITIVE"
    if neg and bear:
        return f"Momentum **{mom}** 🔴 — tape confirms the negative alert; downside risk is live, not hypothetical"
    if neg and bull:
        return f"Momentum **{mom}** 🟢 — alert against a strong tape; dip may be shallow — verify before acting"
    if pos and bear:
        return f"Momentum **{mom}** 🔴 — good news into hostile tape; counter-trend entry, size down or wait for stabilization"
    if pos and bull:
        return f"Momentum **{mom}** 🟢 — catalyst + tailwind aligned; favorable entry context"
    return f"Momentum **{mom}** ⚪ — neutral tape; alert stands on its own merits"


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


def render_regime(regime: dict | None):
    if not regime:
        st.warning("No market regime snapshot available — run a market_regime agent or data refresh.")
        return
    env = regime.get("swing_environment") or {}
    permission = env.get("long_permission", "unknown")
    mult = env.get("size_multiplier")
    color = {"allowed": "🟢", "limited": "🟡", "blocked": "🔴"}.get(
        str(permission).lower(), "⚪")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Market Regime", regime.get("regime") or "n/a")
    c2.metric("Long Entries", f"{color} {permission}")
    c3.metric("Size Multiplier", f"{mult:g}×" if mult is not None else "n/a")
    c4.metric("As Of", _age(regime.get("as_of", "")))
    reasons = env.get("reasons") or []
    if reasons:
        with st.expander("Regime reasons"):
            for r in reasons:
                st.write(f"- {r}")


def _detail_lines(detail: dict) -> list[str]:
    """Human-readable lines per collector's detail payload."""
    lines = []
    if detail.get("grading_company"):
        lines.append(
            f"Analyst: **{detail['grading_company']}** — "
            f"{detail.get('previous_grade')} → {detail.get('new_grade')}"
            + (f" ({detail['grade_date']})" if detail.get("grade_date") else ""))
    if detail.get("delta_pct") is not None:
        lines.append(
            f"EPS estimate {detail['delta_pct']:+.1f}% — {detail.get('fiscal_period')} "
            f"FY{detail.get('fiscal_year')}: {detail.get('prev_eps_estimate')} → "
            f"{detail.get('eps_estimate')} ({detail.get('analysts_up')}↑ "
            f"{detail.get('analysts_down')}↓ analysts)")
    if detail.get("kind"):
        lines.append(
            f"Movers list: **{str(detail['kind']).replace('_', ' ')}** · "
            f"{(detail.get('change_pct') or 0):+.1f}%"
            + (f" · ${float(detail['price']):,.2f}" if detail.get("price") else ""))
    if detail.get("eps_surprise_pct") is not None:
        lines.append(f"EPS surprise {detail['eps_surprise_pct']:+.1f}%")
    if detail.get("days_to_earnings") is not None:
        lines.append(f"Earnings in {detail['days_to_earnings']} day(s)")
    if detail.get("catalyst_type"):
        lines.append(
            f"Catalyst: {detail['catalyst_type']} · reaction "
            f"{detail.get('reaction_state') or 'unconfirmed'} · "
            f"{detail.get('fresh_headlines', 0)} fresh headlines · "
            f"classified by {detail.get('classification_source') or 'keywords'}")
    if detail.get("triggers"):
        lines.append("Triggers: " + ", ".join(
            str(t).split(":")[0] for t in detail["triggers"]))
    for r in (detail.get("reasons") or [])[:3]:
        lines.append(str(r))
    return lines


def render_alert_row(item: dict):
    icon = _DIR_ICON.get(item["direction"], "⚪")
    mat = _MAT_COLOR.get(item["materiality"], "")
    badges = []
    if item.get("in_portfolio"):
        badges.append("`HELD`")
    if item.get("in_watchlist"):
        badges.append("`WATCH`")
    status = item.get("status", "new")
    action = item.get("swing_action") or ""
    score = item.get("priority_score")
    ra = item.get("rating_action")
    if ra:
        badges.append({"upgrade": "`⬆️ upgrade`",
                       "downgrade": "`⬇️ downgrade`"}.get(ra, "`↔️ rating`"))
    kind = (item.get("detail") or {}).get("kind")
    if kind and item.get("event_type") == "catalyst":
        badges.append(f"`{kind}`")
    mbadge = _mom_badge(item)
    if mbadge:
        badges.append(mbadge)
    fbadge = _fund_badge(item)
    if fbadge:
        badges.append(fbadge)

    header = (
        f"{icon} {mat} **{item['symbol']}** — {item['title'][:90]} "
        f"{' '.join(badges)} · `{item['event_type']}` · {_age(item['created_at'])}"
        + (f" · score {score:.0f}" if score else "")
    )
    if status == "reviewed" and action:
        header += f" · **{action}**"

    with st.expander(header, expanded=False):
        if item.get("swing_summary"):
            st.info(item["swing_summary"])

        src_ts = item.get("source_timestamp")
        meta = [f"source `{item.get('source') or '?'}"]
        if src_ts:
            meta.append(f"event {_age(src_ts)}")
        if item.get("reviewed_at"):
            meta.append(f"reviewed {_age(item['reviewed_at'])}")
        st.caption(" · ".join(meta))

        for line in _detail_lines(item.get("detail") or {}):
            st.caption("· " + line)

        mread = _mom_read(item)
        if mread:
            mom = item.get("momentum")
            if mom in _MOM_BEAR:
                st.error(mread)
            elif mom in _MOM_BULL:
                st.success(mread)
            else:
                st.caption(mread)

        if item.get("fund_state"):
            _frisk = item.get("fund_risk") or "?"
            _falert = item.get("fund_alert") or "normal"
            _line = (f"Fundamentals **{item['fund_state']}** "
                     f"· risk {_frisk} · change-alert {_falert}")
            if _falert in ("warning", "critical"):
                st.warning(_line)
            elif item["fund_state"] in ("declining", "deteriorating"):
                st.error(_line)
            else:
                st.caption(_line)

        cache_key = f"review_result_{item['id']}"
        cached = st.session_state.get(cache_key)

        c1, c2, c3 = st.columns([1, 1, 2])
        label = "Re-run Review" if cached or status == "reviewed" else "Analyze & Swing Setup"
        if c1.button(label, key=f"rev_{item['id']}", type="primary"):
            try:
                res = alerts_post(f"{item['id']}/review")
                if res.get("status") in ("started", "already_running"):
                    st.session_state[cache_key] = {"_pending": True}
                    cached = {"_pending": True}
                else:
                    st.session_state[cache_key] = res
                    cached = res
            except (APIConnectionError, APIError) as e:
                st.error(f"Review failed to start: {e}")
        if status == "new" and c2.button("Dismiss", key=f"dis_{item['id']}"):
            try:
                alerts_post(f"{item['id']}/dismiss")
                st.session_state.pop(cache_key, None)
                st.rerun()
            except (APIConnectionError, APIError) as e:
                st.error(f"Dismiss failed: {e}")

        if cached:
            if cached.get("_pending"):
                # review runs server-side — poll until done (up to ~4min)
                try:
                    _st = alerts_get(f"{item['id']}/review/status") or {}
                    if _st.get("status") == "done":
                        st.session_state[cache_key] = _st.get("result")
                        st.rerun()
                    elif _st.get("status") == "error":
                        st.error(f"review failed: {_st.get('error')}")
                        st.session_state.pop(cache_key, None)
                    else:
                        st.info("⏳ review running in background — "
                                "it takes 1–2 min on heavy symbols")
                        if st.button("⟳ check result",
                                     key=f"poll_{item['id']}"):
                            st.rerun()
                except (APIConnectionError, APIError):
                    st.info("⏳ review running — check back shortly")
            else:
                if cached.get("summary"):
                    st.success(cached["summary"])
                render_trade_card(cached.get("result") or {},
                                  item["symbol"])


st.title("🔔 Alerts & Briefing")
st.caption("Catalyst alerts on portfolio + watchlist — scan, review, decide. Nothing executes.")

with st.expander("📖 Legend — what each field means"):
    st.markdown("""
**Direction** 🟢 positive / 🔴 negative / 🟡 mixed — expected impact of the event.

**Materiality** 🔥 `HIGH` = earnings surprise, imminent earnings, or a confirmed
price/volume reaction — auto-reviewed first. 🔶 `MODERATE` = fresh news headlines.

**Score** = priority rank — in-portfolio alerts, higher materiality, and a
confirmed market reaction each add points. The inbox sorts by it.

**Sources** — which collector produced the alert:
`grade_change_events` (analyst upgrades/downgrades only — maintains never alert),
`fundamental_estimate_snapshots` (daily EPS-consensus diffs),
`catalyst_intelligence` (news clusters + earnings proximity + price reaction),
`fmp_market_movers` (universe names on biggest-gainers/losers/most-active).

**Fresh vs stale** — `event` time is when the headline/grade happened;
the alert age is when *we* saw it. A big gap = feed lag, not a fresh signal.

**📈 Alert performance** — forward returns (1/5/10d) after each alert.
Tells you which event types *precede* moves (positive avg ret, MFE >> |MAE|)
vs which arrive as post-move commentary.

**📊 Pattern performance** — forward outcomes per setup type from every
swing review; scores self-calibrate once a pattern has ≥20 evaluated signals.
""")

# --- controls ---
c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1, 1])
lookback = c1.selectbox("Scan lookback", [0.5, 1, 3, 7], index=0,
                        format_func=lambda d: "12h" if d == 0.5 else f"{d}d")
status_filter = c2.selectbox("Status", ["new", "reviewed", "all"], index=0)
hours = c3.selectbox("Show last", [12, 24, 48, 72], index=0, format_func=lambda h: f"{h}h")
type_filter = c4.selectbox("Type", ["any", "catalyst", "mover", "eps_revision", "analyst"], index=0)

if c5.button("🏠 Scan portfolio", type="primary", use_container_width=True,
             help="Fast pass — holdings only. Your money's inbox first."):
    try:
        res = alerts_post("scan", {"lookback_days": lookback,
                                   "auto_review": True,
                                   "portfolio_only": True})
        if res.get("status") == "started":
            st.toast("Portfolio scan started — holdings only")
            st.rerun()
        elif res.get("status") == "already_running":
            st.info("A scan is already running")
        else:
            st.warning(f"Unexpected response: {res}")
    except (APIConnectionError, APIError) as e:
        st.error(f"Scan failed to start: {e}")

if c6.button("🔍 Scan all", use_container_width=True,
             help="Full universe — portfolio ∪ watchlist ∪ tracked"):
    try:
        res = alerts_post("scan", {"lookback_days": lookback, "auto_review": True})
        if res.get("status") == "started":
            st.toast("Scan started — runs in background over the full universe")
            st.rerun()
        elif res.get("status") == "already_running":
            st.info("A scan is already running")
        else:
            st.warning(f"Unexpected response: {res}")
    except (APIConnectionError, APIError) as e:
        st.error(f"Scan failed to start: {e}")

# --- background scan status ----------------------------------------------------
try:
    status = alerts_get("scan/status") or {}
except (APIConnectionError, APIError):
    status = {}

if status.get("running"):
    st.info("⏳ Scan in progress — new alerts appear as they're found. "
            "Click below to check progress.")
    if st.button("⟳ Check scan progress"):
        st.rerun()
elif status.get("last_result"):
    lr = status["last_result"]
    last = _age(status.get("last_run_at", ""))
    err = len(lr.get("errors") or [])
    st.caption(
        f"Last scan {last}: {lr.get('scanned_symbols', 0)} symbols → "
        f"{lr.get('new_alerts', 0)} new alerts · {lr.get('duplicates_skipped', 0)} dupes · "
        f"{lr.get('reviews_triggered', 0)} auto-reviews"
        + (f" · {err} symbol errors" if err else "")
    )
    if err:
        with st.expander("Symbol errors"):
            for e in lr["errors"]:
                st.write(f"- {e}")
elif status.get("last_error"):
    st.error(f"Last scan failed: {status['last_error']}")

# --- data ---
try:
    resp = alerts_get("", params={
        "hours": hours,
        "status": None if status_filter == "all" else status_filter,
    })
except (APIConnectionError, APIError) as e:
    st.error(f"Cannot reach alerts API: {e}")
    st.stop()

render_regime(resp.get("regime"))
st.divider()

# --- pattern performance (the learning loop, as it accumulates) ---------------
try:
    pstats = alerts_get("patterns/stats").get("stats") or []
except (APIConnectionError, APIError):
    pstats = []
if pstats:
    with st.expander("📊 Pattern performance — empirical outcomes", expanded=False):
        rows = [
            {
                "pattern": r["setup_type"],
                "horizon": f"{r['horizon_bars']} bars",
                "signals": r["n"],
                "win rate": f"{float(r['win_rate'] or 0):.0%}",
                "avg R": f"{float(r['avg_r'] or 0):+.2f}",
                "last signal": str(r.get("last_signal_date") or ""),
            }
            for r in pstats
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("Signals are captured on every swing review and evaluated "
                   "against forward bars (5/10/20). Score calibration activates "
                   "at n ≥ 20 per pattern.")

# --- alert performance — which event types actually precede moves ----------
try:
    astats = alerts_get("stats").get("stats") or []
except (APIConnectionError, APIError):
    astats = []
if astats:
    with st.expander("📈 Alert performance — did the alert precede the move?", expanded=False):
        rows = [
            {
                "event": r["event_type"],
                "dir": r["direction"],
                "horizon": f"{r['horizon_days']}d",
                "alerts": r["n"],
                "avg ret": f"{float(r['avg_ret_pct'] or 0):+.1f}%",
                "MFE": f"{float(r['avg_mfe_pct'] or 0):+.1f}%",
                "MAE": f"{float(r['avg_mae_pct'] or 0):+.1f}%",
                "hit rate": f"{float(r['win_rate'] or 0):.0%}",
            }
            for r in astats
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("Forward returns from alert-day close (1/5/10d), evaluated "
                   "at the tail of every scan. Predictive alerts show positive "
                   "avg ret with MFE >> |MAE|; post-move commentary won't.")

items = resp.get("items", [])
if type_filter == "analyst":
    items = [i for i in items
             if str(i.get("event_type") or "").startswith("analyst")]
elif type_filter != "any":
    items = [i for i in items if i.get("event_type") == type_filter]

hcol, dcol = st.columns([3, 2])
new_count = sum(1 for i in items if i.get("status") == "new")
hcol.subheader(f"Inbox — {new_count} new / {len(items)} shown")
dir_choice = dcol.radio("Direction", ["All", "🟢 Positive", "🔴 Negative"],
                        index=0, horizontal=True)
if dir_choice != "All":
    want = "POSITIVE" if "Positive" in dir_choice else "NEGATIVE"
    items = [i for i in items if i.get("direction") == want]

if items:
    pos = sum(1 for i in items if i.get("direction") == "POSITIVE")
    neg = sum(1 for i in items if i.get("direction") == "NEGATIVE")
    held = sum(1 for i in items if i.get("in_portfolio"))
    by_type = " · ".join(
        f"`{t}` {n}" for t, n in sorted(
            pd.Series([i.get("event_type") for i in items]).value_counts().items()))
    st.caption(f"🟢 {pos} positive · 🔴 {neg} negative · 📦 {held} on held names · {by_type}")

# Three buckets — actionable (events that move the stock: earnings,
# analyst actions, M&A, FDA, contracts...), price tape (your names are
# moving: movers feed, extended-hours gaps, price-action headlines — go
# check why), and news (opinion, recaps, awards, stake noise).
_TAPE_TYPES = {"mover", "after_hours", "pre_market"}


def _bucket_of(i: dict) -> str:
    d = i.get("detail") or {}
    if i.get("event_type") == "catalyst":
        return d.get("bucket") or ("tape" if d.get("kind") == "price_action"
                                   else "actionable")
    return "tape" if i.get("event_type") in _TAPE_TYPES else "actionable"


def _buckets(sub_items):
    """Split a slice into the four lanes — rating actions first
    (highest-signal headline class, stamped server-side via
    engine.rating_action)."""
    sig = [i for i in sub_items if _bucket_of(i) == "actionable"]
    tape = [i for i in sub_items if _bucket_of(i) == "tape"]
    news = [i for i in sub_items if _bucket_of(i) == "news"]
    rating = [i for i in sig if i.get("rating_action")]
    sig = [i for i in sig if not i.get("rating_action")]
    return rating, sig, tape, news


def _render_buckets(sub_items):
    rating, sig, tape, news = _buckets(sub_items)
    if rating:
        st.markdown(f"##### 🏷️ Upgrades & downgrades — {len(rating)}")
        _render_groups(rating)
    if sig:
        st.markdown(f"##### ⚡ Actionable — {len(sig)} "
                    "(events that move the stock)")
        _render_groups(sig)
    if tape:
        with st.expander(
                f"📊 Price tape — {len(tape)} "
                "(names are moving; context, not events)",
                expanded=False):
            _render_groups(tape)
    if news:
        with st.expander(
                f"📰 News — {len(news)} headlines "
                "(commentary, recaps — context, not catalysts)",
                expanded=False):
            _render_groups(news)


def _ts(v) -> float:
    """ISO string → epoch for newest-first sorting; naive treated as UTC."""
    if not v:
        return 0.0
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def _render_groups(rows):
    groups: dict[str, list] = {}
    for i in rows:
        groups.setdefault(i["symbol"], []).append(i)
    ordered = sorted(
        groups.items(),
        key=lambda kv: -max(
            _ts(a.get("source_timestamp") or a.get("created_at"))
            for a in kv[1]))
    for sym, sym_items in ordered:
        sym_items.sort(
            key=lambda i: _ts(i.get("source_timestamp") or i.get("created_at")),
            reverse=True)
        scope = " 📦" if any(i.get("in_portfolio") for i in sym_items) else \
                (" 👁" if any(i.get("in_watchlist") for i in sym_items) else "")
        st.markdown(f"#### {sym}{scope} — {len(sym_items)} alert"
                    f"{'s' if len(sym_items) > 1 else ''}")
        for item in sym_items:
            render_alert_row(item)


if not items:
    st.info("No alerts in window. Hit 'Scan now' to check for fresh catalysts.")
else:
    # two parts — your money first, then the rest of the universe
    pf_items = [i for i in items if i.get("in_portfolio")]
    rest_items = [i for i in items if not i.get("in_portfolio")]
    st.markdown(f"## 🏠 Part 1 — Portfolio holdings ({len(pf_items)})")
    if pf_items:
        _render_buckets(pf_items)
    else:
        st.caption("quiet — no alerts on held names in this window")
    st.divider()
    st.markdown(f"## 🌐 Part 2 — Watchlist & universe "
                f"({len(rest_items)})")
    if rest_items:
        _render_buckets(rest_items)
    else:
        st.caption("nothing outside the portfolio in this window")


render_universe_expander(python_client)
