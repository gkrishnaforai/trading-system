"""Market Movers — today's gainers/losers/most-active, bucketed by whether
they're in your universe, plus the ORB day-trade watchlist."""
import re
import streamlit as st
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (setup_page_config, render_sidebar, health_col,
                   health_cfg, sym_md)
from api_client import APIClient
from api_config import api_config

setup_page_config("Market Movers", "📈")
render_sidebar()

st.title("📈 Market Movers")
st.caption("FMP biggest gainers / losers / most-active · your names first · "
           "ORB = opening-range breakout on the first 15 minutes")

client = APIClient(api_config.python_worker_url, timeout=120)


def _sget(key: str, path: str):
    """Session-cached GET — fetched once on first visit, then only when a
    section's own button refreshes it. Nothing refetches on widget reruns."""
    if key not in st.session_state:
        try:
            st.session_state[key] = client.get(path)
        except Exception:
            st.session_state[key] = {}
    return st.session_state[key] or {}


def _fmt_money(v):
    return f"${v:,.2f}" if v is not None else "—"


def _fmt_pct(v):
    return f"{v:+.1f}%" if v is not None else ""


_MS_RX = re.compile(
    r"^([A-Za-z_][\w: .]*?)\s*(>=|<=|>|<|==)\s*(-?[\d.]+%?)\s*$")
_MS_METRICS = {"rev_growth", "eps_growth", "rev_streak", "gross_margin",
               "op_margin", "fcf_margin", "market_cap", "ai_rev_pct"}
_MS_ALIAS = {"gm": "gross_margin", "rev": "rev_growth"}


def _parse_milestone(tok: str):
    """'gross_margin>0.52' / 'ai_rev_pct>25' → typed rule dict; prose
    ('DC rev >25% of sales') stays a display-only note."""
    m = _MS_RX.match(tok.strip())
    if not m:
        return tok.strip()
    metric, op, tgt = m.groups()
    metric = _MS_ALIAS.get(metric.strip(), metric.strip())
    if metric not in _MS_METRICS and not metric.startswith("segment_"):
        return tok.strip()
    try:
        val = float(tgt.rstrip("%"))
    except ValueError:
        return tok.strip()
    if tgt.endswith("%") and metric != "ai_rev_pct":
        val /= 100
    return {"metric": metric, "op": op, "target": val,
            "label": tok.strip()}


if "movers_data" not in st.session_state:
    st.session_state.update(movers_data=None, orb_data=None,
                            quality_data=None, ah_data=None, pm_data=None)
    # First visit reads the last *stored* results — no provider calls,
    # no scans. Every table below has its own button to fill/refresh it.
    try:
        st.session_state["orb_data"] = client.get("api/v1/movers/orb")
        st.session_state["quality_data"] = client.get("api/v1/movers/quality")
        st.session_state["ah_data"] = client.get("api/v1/movers/afterhours")
        st.session_state["pm_data"] = client.get("api/v1/movers/premarket")
    except Exception:
        pass

movers = st.session_state["movers_data"] or {}
orb = st.session_state["orb_data"] or {}
quality = st.session_state["quality_data"] or {}

# --- Fear & Greed (computed proxy) — recomputes on ⟳ (cached bars, ~2s).
if "fg_data" not in st.session_state or st.session_state.get("fg_data") is None:
    try:
        st.session_state["fg_data"] = client.get("api/v1/movers/fear-greed")
    except Exception:
        st.session_state["fg_data"] = {}
_fg = st.session_state["fg_data"] or {}
if _fg.get("score") is not None:
    _fcols = st.columns([1, 0.5, 2.5])
    _fcols[0].metric("Fear & Greed", f"{_fg['score']:.0f}", _fg.get("label"))
    if _fcols[1].button("⟳", help="recompute the gauge"):
        try:
            st.session_state["fg_data"] = client.get("api/v1/movers/fear-greed")
        except Exception as e:
            st.error(f"Fear/greed failed: {e}")
        st.rerun()
    _comp = _fg.get("components") or {}
    _fcols[2].caption(
        " · ".join(f"{k} {v:.0f}" for k, v in _comp.items() if v is not None)
        + " — computed proxy: SPY momentum + breadth + near-highs + VIX "
        + f"({_fg.get('detail', {}).get('vix', '?')})")
    _g = _fg.get("guidance") or {}
    if _g:
        _banner = {"success": st.success, "info": st.info,
                   "warning": st.warning, "error": st.error}.get(
            _g.get("level"), st.info)
        _banner(f"**{_g.get('stance')}** — {_g.get('size')}")
        with st.expander("📏 How to use it — swing vs investing "
                         "(contrarian gauge: extremes inform, middle is "
                         "noise; it sizes risk, doesn't predict)"):
            st.markdown(f"**⚡ Swing:** {_g.get('swing')}\n\n"
                        f"**🏦 Investing:** {_g.get('invest')}")
            st.markdown("**Legend — what each band means:**")
            st.dataframe(
                pd.DataFrame(_fg.get("bands") or []),
                use_container_width=True, hide_index=True)

# --- 🌐 regime + macro calendar — the scheduled dates that can flip it
_macro = _sget("macro_data", "api/v1/movers/macro")
_rg0 = _macro.get("regime") or {}
_rg = {**(_rg0.get("regime_detail") or {}), "regime": _rg0.get("regime")}
_ev = _macro.get("events") or []
if _rg or _ev:
    _rn = _rg.get("regime") or _rg.get("condition") or "—"
    _dir = _rg.get("direction") or ""
    _ts = _rg.get("transition_stage") or ""
    _cols = st.columns([2, 2, 3])
    _cols[0].markdown(
        f"**Regime** `{_rn}`" + (f" · {_dir}" if _dir else ""))
    _cols[1].markdown(
        f"**Stage** `{_ts}`" if _ts else "**Stage** —")
    _nxt = _ev[0] if _ev else None
    _cols[2].markdown(
        f"**Next macro:** {_nxt['name']} {_nxt['date']} "
        f"(in {_nxt['days_away']}d)" if _nxt else "**Next macro:** —")
    if _rg.get("key_drivers"):
        st.caption("drivers: " + " · ".join(
            str(d) for d in (_rg.get("key_drivers") or [])[:5]))
    # forward read + global-risk overlay — same stored context the
    # Daily Board posture consumes (one source, two surfaces)
    _fwd = _macro.get("forward") or {}
    _geo = _macro.get("geo") or {}
    if _fwd or _geo:
        _fc = st.columns(3)
        if _fwd:
            _fc[0].metric("🔮 deeper dip", 
                          f"{_fwd.get('p_deeper_dip_20d','—')}%")
            _fc[1].metric("chop", f"{_fwd.get('p_chop_20d','—')}%")
            _fc[2].metric("bullish res.",
                          f"{_fwd.get('p_bullish_20d','—')}%")
            st.caption(
                f"forward ~20d — lead **{_fwd.get('lead_scenario','—')}** "
                f"· conf {_fwd.get('confidence','—')}" +
                (" — " + " · ".join(_fwd.get("drivers") or [])[:180]
                 if _fwd.get("drivers") else ""))
        if _geo:
            _fl = _geo.get("defensive") or {}
            st.caption(
                f"🌍 geo-risk **{_geo.get('geo_risk','—')}/100** · "
                f"defensive flows `{_fl.get('flow','—')}`" +
                (" — " + " · ".join(_geo.get("drivers") or [])[:160]
                 if _geo.get("drivers") else ""))
            _cm = _geo.get("causal") or {}
            if _cm.get("chains") or _cm.get("watching"):
                _ws = {"calm": "🕊 calm", "war_ongoing": "⚔️ war ongoing",
                       "escalating": "🔥 escalating",
                       "de_escalating": "🕊 de-escalating",
                       "trade_war": "🚢 trade war"}.get(
                    _cm.get("world_state"), _cm.get("world_state"))
                with st.expander(
                        f"🗺 Causal map — world: {_ws} · "
                        f"{len(_cm.get('chains') or [])} active · "
                        f"{len(_cm.get('watching') or [])} watching",
                        expanded=False):
                    for c in (_cm.get("chains") or []) + (
                            _cm.get("watching") or []):
                        _icon = ("🔴" if c.get("status") == "active"
                                 else "⚪")
                        st.markdown(
                            f"**{_icon} {c['title']}** "
                            f"(conf {c['conf']}%) — _{c['fired_by']}_")
                        for i, s in enumerate(c["steps"], 1):
                            _bi = s.get("book_impact") or {}
                            _bis = (" · book: " + " · ".join(
                                f"{k} {v}" for k, v in _bi.items())
                                ) if _bi else ""
                            st.caption(
                                f"{i}. {s['driver']} → {s['market']} · "
                                f"{s['assets']} ({s['conf']}%){_bis}")
                        st.caption(f"watch: {c['watch_for']} · "
                                   f"dies if: {c['watch_against']}")
        _cx = (_macro.get("capex") or {})
        if _cx.get("score") is not None:
            _d3, _d6 = _cx.get("d3m"), _cx.get("d6m")
            _trend = (f" Δ3m {_d3:+} Δ6m {_d6:+}"
                      if _d3 is not None else "")
            _fl = " · ".join(_cx.get("flags") or [])
            with st.expander(
                    f"🏗 AI capex engine — {_cx['score']}/100 "
                    f"{_cx.get('band','—')}{_trend}"
                    + (f" · {_fl}" if _fl else ""), expanded=False):
                _comps = _cx.get("components") or {}
                for k, v in _comps.items():
                    st.caption(f"**{k}** {v.get('score')} — "
                               f"{v.get('kind')}")
                    for drow in (v.get("detail") or [])[:6] \
                            if isinstance(v.get("detail"), list) else []:
                        st.caption(f"   {drow}")
                _rot = _cx.get("rotation") or {}
                if _rot.get("rotation_spread") is not None:
                    st.caption(
                        f"rotation: new-build {_rot['new_build_rs_63d']}%"
                        f" vs operators {_rot['operator_rs_63d']}% (63d "
                        f"RS, spread {_rot['rotation_spread']:+.1f}%)")
                _g = _cx.get("guidance") or {}
                if _g.get("meaning"):
                    st.caption(f"ℹ️ {_g['meaning']}")
                    for _a in _g.get("actions") or []:
                        st.caption(f"▸ {_a}")
                    for _w in _g.get("watch") or []:
                        st.caption(f"👁 {_w}")
                st.caption(f"elevated components: "
                           f"{_cx.get('n_elevated',0)}/7 · "
                           f"_{_cx.get('note','')}_")
    if _ev:
        with st.expander("📅 Macro calendar — FOMC · jobs · CPI · "
                         "PPI · PCE (dates that move regime)",
                         expanded=False):
            for e in _ev[:10]:
                _tag = ("**today**" if e["days_away"] == 0 else
                        "**tomorrow**" if e["days_away"] == 1 else
                        f"in {e['days_away']}d")
                st.markdown(
                    f"`{e['date']}` {e['name']} · {e['time_et']} ET "
                    f"· {_tag}"
                    + (" · ⚠️ **regime-mover**"
                       if e["severity"] == "extreme" else "")
                    + (" · *(est)*" if e.get("est") else ""))
            st.caption("FOMC decisions are the official 2026 Fed "
                       "schedule · CPI from BLS calendar · NFP = first "
                       "Friday · PCE = last Friday · *(est)* = "
                       "rule-derived, verify vs the release calendar")


# --- 📅 Earnings this week — prints for tracked symbols (boards,
# portfolio, watchlist) grouped by day, with expectation-gap context so
# each report shows whether the setup is a live flywheel or a landmine.
try:
    _ew = client.get("api/v1/movers/earnings-week") or {}
except Exception:
    _ew = {}
if _ew.get("by_day"):
    _n = _ew.get("count", 0)
    st.subheader(f"📅 Earnings — next {_ew.get('days', 7)} days ({_n} prints)")
    for _d, _syms in _ew["by_day"].items():
        _dd = pd.Timestamp(_d)
        _tag = "**today**" if _dd.date() == pd.Timestamp.now().date() \
            else ("**tomorrow**" if _dd.date()
                  == (pd.Timestamp.now() + pd.Timedelta(days=1)).date()
                  else _dd.strftime("%a %b %d"))
        _chips = []
        for r in _syms:
            c = sym_md(r['symbol'])
            if r.get("eps_est") is not None:
                c += f" est ${r['eps_est']:.2f}"
            if r.get("beat_streak"):
                c += f" {r['beat_streak']}W"
            if r.get("muted_reaction"):
                c += "🔥"
            if r.get("gap_score") is not None:
                c += f" gap{r['gap_score']:.0f}"
            if r.get("boards"):
                c += f" ·{r['boards']}"
            _chips.append(c)
        st.markdown(f"{_tag} — " + " · ".join(_chips))
    st.caption("eps est = next-print consensus · nW = beat streak · "
               "🔥 = last beat got no pop · gap = expectation-gap /100 · "
               "boards = RB / 5x / portfolio / watchlist membership")


# --- 🎯 Daily edge — the morning confluence board. Catalyst × setup
# (lane A) and takeoff-watch (lane B), ranked from persisted data —
# screen_runs technicals, 48h alerts, RB tiers, accel streaks, PT
# momentum, and the empirical 5d win-rate of each alert kind. No
# provider calls: this is the synthesis of everything below.
_de = None
if st.button("🎯 Compute daily edge — top swing candidates", key="run_edge"):
    try:
        _de = client.get("api/v1/movers/daily-edge")
        st.session_state["edge_data"] = _de
        st.toast("Edge computed — catalyst × setup × proof × win-rate")
    except Exception as e:
        st.error(f"Edge failed: {e}")
_de = st.session_state.get("edge_data") or {}
if _de:
    _swing, _bo, _veto = (_de.get("swing") or [], _de.get("breakout") or [],
                          _de.get("vetoed") or [])
    st.subheader(
        f"🎯 Daily edge — {len(_swing)} swing / {len(_bo)} breakout-watch")
    st.caption(
        "conviction = catalyst (fresh analyst/RB/PT events, recency-decayed) "
        "+ setup (technical pattern) + proof (tier/streaks/PT momentum) "
        "+ the kind's own 5d win rate. Entry/stop/target from the screen. "
        "**HL** = higher-low structure (✅ confirmed breakout of the "
        "pullback's swing high · ⏳ low carved above prior low, "
        "**confirm>** = the close that proves it · ⛔ pivot chain broken).")
    _sc1, _sc2 = st.columns(2)
    with _sc1:
        st.markdown("**Top swing candidates — catalyst × setup**")
        if _swing:
            _sr = [{"symbol": p["symbol"],
                    "conviction": p["conviction"],
                    "catalyst": p.get("catalyst"),
                    "setup": p.get("setup"),
                    "HL": {"confirmed": "✅", "higher_low": "⏳",
                           "broken": "⛔"}.get(p.get("swing_phase"), ""),
                    "RS": (f"{p['rs_pct']}"
                           if p.get("rs_pct") is not None else ""),
                    "pts": f"{p.get('cat_pts',0):.0f}+{p.get('setup_pts',0):.0f}+{p.get('proof_pts',0):.0f}",
                    "entry": _fmt_money(p.get("entry")),
                    "stop": _fmt_money(p.get("stop")),
                    "target": _fmt_money(p.get("target")),
                    "confirm>": _fmt_money(p.get("confirm_level"))
                    if p.get("confirm_level") else "",
                    "dd20": _fmt_pct((p.get("dd20") or 0) * 100) if p.get("dd20") is not None else "",
                    "vs_spy": _fmt_pct((p.get("vs_spy20") or 0) * 100) if p.get("vs_spy20") is not None else "",
                    "vol": f"{p.get('volume_ratio'):.1f}x" if p.get("volume_ratio") else "",
                    "rb": p.get("rb_tier") or "",
                    "pf": "✅" if p.get("in_portfolio") else "",
                    "wl": "✅" if p.get("in_watchlist") else "",
                    "size": f"{p.get('size_mult')}x" if p.get("size_mult") else ""}
                   for p in _swing]
            st.dataframe(health_col(pd.DataFrame(_sr)),
                         column_config={"🩺": health_cfg()},
                         use_container_width=True, hide_index=True)
        else:
            st.caption("No fresh catalyst × setup confluence in window.")
        if _veto:
            with st.expander(f"⛔ {len(_veto)} vetoed (downgrade/knife/dilution)"):
                st.dataframe(health_col(pd.DataFrame(
                    [{"symbol": v["symbol"], "veto": v["veto"],
                      "catalyst": v.get("catalyst"),
                      "conviction": v.get("conviction")}
                     for v in _veto])),
                    column_config={"🩺": health_cfg()},
                    use_container_width=True, hide_index=True)
    with _sc2:
        st.markdown("**Breakout watch — moving into / starting to take off**")
        if _bo:
            _br = [{"symbol": p["symbol"],
                    "score": p["score"],
                    "dd20": _fmt_pct((p.get("dd20") or 0) * 100) if p.get("dd20") is not None else "",
                    "vs_spy": _fmt_pct((p.get("vs_spy20") or 0) * 100) if p.get("vs_spy20") is not None else "",
                    "vol": f"{p.get('volume_ratio'):.1f}x" if p.get("volume_ratio") else "",
                    "squeeze": "🌀" if p.get("bb_squeeze") else "",
                    "setup": "+".join(p.get("patterns") or []),
                    "entry": _fmt_money(p.get("entry")),
                    "stop": _fmt_money(p.get("stop")),
                    "catalyst": "⚡" if p.get("has_catalyst") else "",
                    "pf": "✅" if p.get("in_portfolio") else ""}
                   for p in _bo]
            st.dataframe(health_col(pd.DataFrame(_br)),
                         column_config={"🩺": health_cfg()},
                         use_container_width=True, hide_index=True)
            st.caption("🌀 squeeze coiling · ⚡ also has a fresh catalyst · "
                       "dd20 = distance from 20d high · vs_spy = 20d relative strength")
        else:
            st.caption("None near the 20d high or coiling right now.")
    _ec1, _ec2 = st.columns([1, 3])
    with _ec1:
        if st.button("💾 Persist today's picks", key="edge_persist"):
            try:
                client.post("api/v1/movers/daily-edge/persist")
                st.toast("Picks persisted to daily_picks")
            except Exception as e:
                st.error(f"Persist failed: {e}")
    with _ec2:
        _sc = _sget("edge_scorecard", "api/v1/movers/daily-edge/scorecard")
        _bits = []
        for _s in _sc.get("scorecard") or []:
            _bits.append(
                f"**{_s['lane']}**: {_s['wins']}/{_s['n']} up "
                f"({_s['avg_ret'] or 0:+.1f}% avg · "
                f"{_s['beat_spy']}/{_s['n']} beat SPY · "
                f"{_s['targeted']}T/{_s['stopped']}S)")
        if _bits:
            st.caption("📊 Pick scorecard (5d): " + "  ·  ".join(_bits))


# --- Extended-hours boards — post-market + pre-market, each with its own
# scan button + manual progress check (button-only, no auto-refresh).
def _session_board(session: str, icon: str, title: str, ep: str, key: str):
    b1, b2 = st.columns([1, 3])
    with b1:
        if st.button(f"{icon} Scan {title}", key=f"run_{session}"):
            try:
                client.post(f"api/v1/movers/{ep}/run")
                st.session_state[f"{key}_status"] = {"running": True}
                st.toast(f"{title} scan started")
                st.rerun()
            except Exception as e:
                st.error(f"{title} scan failed: {e}")
    with b2:
        _st = _sget(f"{key}_status", f"api/v1/movers/{ep}/status")
        if _st.get("running"):
            if st.button(f"⟳ check {title}", key=f"chk_{session}"):
                try:
                    st.session_state[key] = client.get(f"api/v1/movers/{ep}")
                    st.session_state[f"{key}_status"] = client.get(
                        f"api/v1/movers/{ep}/status")
                except Exception:
                    pass
                st.rerun()
            st.caption(f"{title} scan running — extended-hours quotes "
                       "per symbol (~90s).")
    d = st.session_state.get(key) or {}
    if not (d.get("top_gainers") or d.get("universe_movers")):
        st.caption(f"{icon} {title}: no board yet — "
                   f"scan during the session window or load the last run.")
        if st.button(f"📥 load last {title}", key=f"ld_{session}"):
            try:
                st.session_state[key] = client.get(f"api/v1/movers/{ep}")
            except Exception:
                pass
            st.rerun()
        return
    with st.expander(f"{icon} {title} board "
                     f"(as of {d.get('as_of', '—')} · {d.get('scanned', 0)} "
                     f"scanned)", expanded=True):
        _tg = d.get("top_gainers") or []
        if _tg:
            st.markdown("**Top gainers** — " + " · ".join(
                f"**{sym_md(g['symbol'])}** {g['ah_pct']:+.1f}% → "
                f"${g['ah_price']:,.2f}"
                for g in _tg))
        _um = d.get("universe_movers") or []
        if _um:
            df = pd.DataFrame(_um)
            df["scope"] = df.apply(
                lambda r: "📦 held" if r.get("in_portfolio")
                else ("👁 watch" if r.get("in_watchlist") else ""), axis=1)
            keep = ["symbol", "scope", "reg_close", "ah_price", "ah_pct"]
            st.dataframe(
                health_col(df[keep]).rename(columns={
                    "reg_close": "ref close", "ah_price": f"{title} price",
                    "ah_pct": f"{title} %"}),
                column_config={"🩺": health_cfg()},
                use_container_width=True, hide_index=True)
        st.caption("Quotes via Yahoo (FMP after-market is 403 on the plan). "
                   "≥±2% on a held/watch name fires an alert — the planning "
                   "signal: gap vs setup, not a trade trigger.")


_session_board("post", "🌙", "after-hours", "afterhours", "ah_data")
_session_board("pre", "🌅", "pre-market", "premarket", "pm_data")

# --- Sector momentum & rotation — which sector leads, where capital is
# arriving. Computed from sector/theme ETF bars (cached EOD reads, not a
# scan). "flow" proxies funding via price×volume since no fund-flow feed
# is on the plan.
if "rot_data" not in st.session_state:
    try:
        st.session_state["rot_data"] = client.get("api/v1/movers/sector-rotation")
    except Exception:
        st.session_state["rot_data"] = {}
_rot = st.session_state.get("rot_data") or {}
_secs, _themes = _rot.get("sectors") or [], _rot.get("themes") or []
if _secs:
    _rh1, _rh2 = st.columns([4, 1])
    _rh1.subheader("🏭 Sector momentum & rotation")
    _rh1.caption("**check:** where to fish — buy candidates in ⚡ swing-now "
                 "sectors; 🏦 accumulate = 6-month positioning; 📉 outflow "
                 "sectors = avoid new entries / trim held names")
    if _rh2.button("⟳ recompute", help="recompute from cached EOD ETF bars"):
        try:
            st.session_state["rot_data"] = client.get("api/v1/movers/sector-rotation")
        except Exception as e:
            st.error(f"Rotation failed: {e}")
        st.rerun()
    _sw = " · ".join(_rot.get("swing_now") or [])
    _acc = " · ".join(_rot.get("accumulate_6m") or [])
    _out = " · ".join(_rot.get("outflows") or [])
    st.markdown(
        f"⚡ **Swing now** (ride confirmed momentum): {_sw or '—'}\n\n"
        f"🏦 **6-month accumulate** (capital arriving early, room to run): "
        f"{_acc or '—'}\n\n"
        f"📉 **Distribution** (money leaving): {_out or 'none'}")

    def _sdf(rows):
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        for c in ("ret1", "ret5", "ret20", "ret60", "vs_spy20"):
            if c in df.columns:
                df[c] = df[c].apply(
                    lambda v: f"{v * 100:+.1f}%" if v is not None else "—")
        if "volume_ratio" in df.columns:
            df["volume_ratio"] = df["volume_ratio"].apply(
                lambda v: f"{v:.1f}×" if v is not None else "—")
        df["trend"] = df.apply(
            lambda r: (">50" if r.get("above_sma50") else "<50")
            + (" · >200" if r.get("above_sma200") else " · <200"), axis=1)
        df["names"] = df["swing_names"].apply(
            lambda s: " ".join(s[:8]) + (" …" if len(s) > 8 else "")
            if isinstance(s, list) else "")
        keep = ["symbol", "name", "action", "score", "flow", "ret5", "ret20",
                "ret60", "vs_spy20", "volume_ratio", "trend", "names"]
        return df[[c for c in keep if c in df.columns]].rename(columns={
            "ret5": "5d", "ret20": "20d", "ret60": "60d",
            "vs_spy20": "vs SPY 20d", "volume_ratio": "vol",
            "names": "uptrend names"})

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Sectors** (GICS)")
        st.dataframe(_sdf(_secs), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Themes** — the funding question at finer grain")
        st.dataframe(_sdf(_themes), use_container_width=True, hide_index=True)
    st.caption("⚡ swing = confirmed uptrend + momentum (extended >8%/wk = "
               "wait for the pullback) · 🏦 accumulate 6m = early rotation — "
               "capital arriving before trend confirms, the 6-month "
               "positioning zone · 📉 outflow = distribution. "
               "'uptrend names' = your universe symbols in that sector "
               "currently 🟢 (coverage grows as profiles cache). "
               f"as of {_rot.get('as_of') or '—'}")

# --- 🧭 Theme rotation board — the chips→memory→data-center question.
# Sector ETFs can't see sub-industry rotation (memory, optics and power
# all sit inside SMH). This scores each registry theme on member tape
# (relative strength, breadth, RS slope) + evidence (headline hits,
# tailwind channels) + member fundamentals — deterministic, journaled
# weekly so rank/call transitions are the signal.
if "trot_data" not in st.session_state:
    try:
        st.session_state["trot_data"] = client.get(
            "api/v1/board/themes/rotation")
    except Exception:
        st.session_state["trot_data"] = {}
_tro = st.session_state.get("trot_data") or {}
_trows = _tro.get("themes") or []
if _trows:
    _th1, _th2 = st.columns([4, 1])
    _th1.subheader("🧭 Theme rotation — where the 6-month money is going")
    _th1.caption("**check:** 🌱 early = capital arriving before trend "
                 "confirms (the accumulation zone) · 🚀 leading = the "
                 "trade is working · 🔥 extended = late, don't chase · "
                 "📉 fading = money leaving. Rank deltas vs last week "
                 "show the rotation *moving*.")
    if _th2.button("⟳ score", key="trot_refresh",
                   help="recompute + journal a board snapshot"):
        try:
            st.session_state["trot_data"] = client.get(
                "api/v1/board/themes/rotation?refresh=1")
        except Exception as e:
            st.error(f"Theme rotation failed: {e}")
        st.rerun()

    _CALL = {"early": "🌱 early", "leading": "🚀 leading",
             "extended": "🔥 extended", "fading": "📉 fading",
             "building": "🧱 building", "no_data": "·"}
    _dl = _tro.get("deltas") or {}

    def _trow_fmt(t):
        d = _dl.get(t["theme_key"]) or {}
        mv = ""
        if d.get("rank_delta"):
            mv = f" ↑{d['rank_delta']}" if d["rank_delta"] > 0 \
                else f" ↓{-d['rank_delta']}"
        tr = d.get("call_transition") or d.get("stage_transition") or ""
        return {
            "#": f"{t.get('rank') or '—'}{mv}",
            "theme": t["name"],
            "call": _CALL.get(t.get("call"), t.get("call") or "—")
                    + (f" ⟳{tr}" if tr else ""),
            "stage": t.get("stage"),
            "score": t.get("score"),
            "RS 20d": (f"{t['rs20'] * 100:+.1f}%" if t.get("rs20")
                       is not None else "—"),
            "slope": (f"{t['rs_slope'] * 100:+.1f}%" if t.get("rs_slope")
                      is not None else "—"),
            ">50d": (f"{t['breadth'] * 100:.0f}%" if t.get("breadth")
                     is not None else "—"),
            "growth": (f"{t['median_rev_growth'] * 100:+.0f}%"
                       if t.get("median_rev_growth") is not None
                       else "—"),
            "evid": f"{t.get('news_hits', 0)}📰 {t.get('channel_evidence', 0)}✦",
            "names": " ".join((t.get("top_members") or [])[:6]),
        }

    _tdf = pd.DataFrame([_trow_fmt(t) for t in _trows
                         if t.get("score") is not None])
    st.dataframe(_tdf, use_container_width=True, hide_index=True)
    _nocov = [t["name"] for t in _trows if t.get("score") is None]
    if _nocov:
        st.caption("no member bars yet: " + " · ".join(_nocov))
    st.caption("RS = median member return vs SPY · slope = short-term RS "
               "improving vs the 60d leg — the rotation *starting* signal · "
               "evid = 📰 headline hits / ✦ journaled tailwind channels · "
               "names = strongest 20d members with bars. "
               f"as of {_tro.get('as_of') or '—'}")

# --- 🌱 Growth-quality board — structural growers vs cyclical peaks.
# Composite of slope (acceleration), earnings quality (FCF+dilution),
# estimate revisions, and structural proof (durability+margins+LT
# curve+channels). Percentile-ranked vs the tracked universe.
if "gq_data" not in st.session_state:
    try:
        st.session_state["gq_data"] = client.get(
            "api/v1/board/growth-quality")
    except Exception:
        st.session_state["gq_data"] = {}
_gqs = (st.session_state.get("gq_data") or {}).get("symbols") or []
if _gqs:
    _gq1, _gq2 = st.columns([4, 1])
    _gq1.subheader("🌱 Growth quality — structural vs cyclical")
    _gq1.caption("**check:** slope = growth accelerating · quality = "
                 "FCF-backed, per-share real · revisions = street "
                 "raising the curve · structural = multi-yr durability "
                 "+ margins + LT estimates + channel evidence. Cyclicals "
                 "discounted — a hot growth print at a cycle peak "
                 "scores *lower*, not higher.")
    if _gq2.button("⟳ score", key="gq_refresh",
                   help="recompute + journal the universe"):
        try:
            st.session_state["gq_data"] = client.get(
                "api/v1/board/growth-quality?refresh=1")
        except Exception as e:
            st.error(f"Growth quality failed: {e}")
        st.rerun()

    def _gq_fmt(r):
        c = r.get("components") or {}
        d = r.get("detail") or {}
        _n = lambda v: f"{v:.0f}" if isinstance(v, (int, float)) else "—"
        return {
            "pctl": (f"{r['percentile']:.0f}" if r.get("percentile")
                     is not None else "—"),
            "symbol": r["symbol"],
            "score": r.get("score"),
            "slope": _n(c.get("growth_slope")),
            "quality": _n(c.get("earnings_quality")),
            "revisions": _n(c.get("revision_momentum")),
            "structural": _n(c.get("structural_proof")),
            "rev g": (f"{d['rev_g_latest'] * 100:+.0f}%"
                      if d.get("rev_g_latest") is not None else "—"),
            "3y CAGR": (f"{d['rev_cagr_3y'] * 100:+.0f}%"
                        if d.get("rev_cagr_3y") is not None else "—"),
            "flags": " ".join(r.get("flags") or []),
        }

    st.dataframe(pd.DataFrame([_gq_fmt(r) for r in _gqs]),
                 use_container_width=True, hide_index=True)

# --- Sector candidates — top ~10 per sector ranked on CANSLIM fundamentals.
# Background job (~3-5 min cold: ~150 symbols x 3 provider calls each).
if "cand_data" not in st.session_state:
    st.session_state["cand_data"] = None
    try:
        st.session_state["cand_data"] = client.get(
            "api/v1/movers/sectors/candidates")
    except Exception:
        pass

_cc1, _cc2 = st.columns([1, 3])
with _cc1:
    if st.button("🎯 Rank sector candidates"):
        try:
            client.post("api/v1/movers/sectors/candidates/run")
            st.session_state["cand_status"] = {"running": True}
            st.toast("Candidate ranking started")
            st.rerun()
        except Exception as e:
            st.error(f"Candidate ranking failed: {e}")
with _cc2:
    _cst = _sget("cand_status", "api/v1/movers/sectors/candidates/status")
    if _cst.get("running"):
        if st.button("⟳ check ranking progress"):
            try:
                st.session_state["cand_data"] = client.get(
                    "api/v1/movers/sectors/candidates")
                st.session_state["cand_status"] = client.get(
                    "api/v1/movers/sectors/candidates/status")
                st.session_state["cand_moves"] = client.get(
                    "api/v1/movers/sectors/candidates/moves")
            except Exception as e:
                st.error(f"Candidate results failed: {e}")
            st.rerun()
        st.caption("Ranking candidates — fundamentals fetch ~3-5 min "
                   "(cold run longer against provider throttling).")
    elif _cst.get("error"):
        st.warning(f"Last ranking errored: {_cst['error']}")

_cand = st.session_state.get("cand_data") or {}
_csectors = _cand.get("sectors") or {}
# rank movement between the last two runs — persisted candidate_ranks history
_mv = (_sget("cand_moves", "api/v1/movers/sectors/candidates/moves")
       .get("moves") or {})


def _delta_chip(mv_rows, sym):
    m = (mv_rows or {}).get(sym)
    if not m or m.get("prev_rank") is None:
        return "NEW" if m else "—"
    d = m.get("delta") or 0
    return f"↑{d}" if d > 0 else (f"↓{-d}" if d < 0 else "—")


if _csectors:
    st.subheader("🎯 Sector candidates — ranked top 10")
    st.caption("**check:** who to buy inside the leading sector/theme — "
               "top-ranked + a live catalyst = the strongest buy candidates. "
               "CANSLIM-weighted: EPS growth (the #1 factor) + revenue growth "
               "(validates the EPS isn't engineered) + ROE + estimate revisions "
               "(the product-pipeline proxy — analysts price future products "
               "into estimates) + fair-value upside + trend position. "
               "Pools are curated sector-leader lists — the ranking is computed.")
    _rot_map = {r["symbol"]: r["action"]
                for r in (_secs + _themes)} if _secs or _themes else {}
    _opts = [e for e in (_rot.get("swing_now") or []) if e in _csectors] + \
            [e for e in (_rot.get("accumulate_6m") or []) if e in _csectors] + \
            [e for e in _csectors if e not in
             (_rot.get("swing_now") or []) + (_rot.get("accumulate_6m") or [])]
    _pick = st.selectbox(
        "Sector / theme",
        _opts,
        format_func=lambda e: f"{e} — {_csectors[e]['name']}"
        + (f" · {_rot_map[e]}" if e in _rot_map else ""),
    ) if _opts else None
    if _pick:
        _cands = _csectors[_pick]["candidates"]
        _cdf = pd.DataFrame(_cands)
        if not _cdf.empty:
            _cdf["rank"] = range(1, len(_cdf) + 1)
            _cdf["why"] = _cdf["why"].apply(
                lambda w: " · ".join(w[:3]) if isinstance(w, list) else "")
            _cdf["risks"] = _cdf["risks"].apply(
                lambda r: " · ".join(x.split(" — ")[0] for x in (r or [])) or "—")
            _mvmap = {e["symbol"]: e for e in (_mv.get(_pick) or [])}
            _cdf["Δ"] = _cdf["symbol"].apply(
                lambda s: _delta_chip(_mvmap, s))
            _cdf["accel"] = _cdf["accelerating"].map(
                {True: "📈", False: ""}).fillna("") \
                if "accelerating" in _cdf.columns else ""
            keep = ["rank", "Δ", "accel", "symbol", "rank_score", "verdict",
                    "eps_growth", "rev_growth", "roe", "vs_sma50", "dd20_pct",
                    "why", "risks", "in_portfolio", "in_watchlist"]
            st.dataframe(
                health_col(_cdf[[c for c in keep
                                 if c in _cdf.columns]]).rename(columns={
                    "rank_score": "score", "eps_growth": "EPS g%",
                    "rev_growth": "Rev g%", "roe": "ROE%",
                    "vs_sma50": "vs50%", "dd20_pct": "dd20%",
                    "in_portfolio": "port", "in_watchlist": "watch"}),
                column_config={"🩺": health_cfg()},
                use_container_width=True, hide_index=True)
        st.caption(f"Pool of {_csectors[_pick]['pool_size']} sector leaders · "
                   f"scored {_cand.get('scored', 0)} symbols total · "
                   f"as of {(_cand.get('as_of') or '—')[:16].replace('T', ' ')}")

# --- Thematic baskets — cross-sector growth themes (Agentic AI, tokenization)
# MSCI relevance-score style: purity tier × fundamentals + R&D intensity.
_themes = _cand.get("themes") or {}
if _themes:
    st.markdown("**🧬 Thematic baskets** — who wins the structural theme, "
                "not just the sector")
    _tkeys = list(_themes.keys())
    _tpick = st.selectbox(
        "Theme", _tkeys,
        format_func=lambda k: _themes[k]["name"])
    _tb = _themes.get(_tpick) or {}
    if _tb.get("thesis"):
        st.caption(_tb["thesis"])
    _tdf = pd.DataFrame(_tb.get("candidates") or [])
    if not _tdf.empty:
        _tdf["rank"] = range(1, len(_tdf) + 1)
        _tdf["tier"] = _tdf["purity"].map(
            {1: "1 pure play", 2: "2 platform", 3: "3 enabler"}).fillna("?")
        _tdf["rd"] = _tdf["rd_intensity"].apply(
            lambda v: f"{v * 100:.0f}%" if v is not None else "—")
        _tdf["why"] = _tdf["why"].apply(
            lambda w: " · ".join(w[:3]) if isinstance(w, list) else "")
        _tdf["risks"] = _tdf["risks"].apply(
            lambda r: " · ".join(x.split(" — ")[0] for x in (r or [])) or "—")
        _tmvmap = {e["symbol"]: e for e in (_mv.get(_tpick) or [])}
        _tdf["Δ"] = _tdf["symbol"].apply(
            lambda s: _delta_chip(_tmvmap, s))
        _tdf["accel"] = _tdf["accelerating"].map(
            {True: "📈", False: ""}).fillna("") \
            if "accelerating" in _tdf.columns else ""
        keep = ["rank", "Δ", "accel", "symbol", "tier", "angle",
                "theme_score", "fund_score", "rd", "verdict", "eps_growth",
                "rev_growth", "roe", "why", "risks"]
        st.dataframe(
            _tdf[[c for c in keep if c in _tdf.columns]].rename(columns={
                "theme_score": "theme", "fund_score": "fund",
                "rd": "R&D%", "eps_growth": "EPS g%",
                "rev_growth": "Rev g%", "roe": "ROE%"}),
            use_container_width=True, hide_index=True)
    st.caption("theme score = fundamentals × purity weight + R&D-intensity "
               "bonus — MSCI 'relevance score' style: pure plays with the "
               "product outrank diversified giants. tier 1 = flagship product / "
               "pure play · tier 2 = major platform beneficiary · tier 3 = "
               "enabler. angle = the product evidence behind the linkage.")

    # 📣 Theme catalysts — positive events on this theme's members over the
    # last 7d: EPS surprises, estimate revisions, confirmed reactions.
    # Filtered lens on alert_items — the Alerts page is the full feed.
    _tc = _sget("tc_data", "api/v1/movers/themes/catalysts")
    _feeds = (_tc.get("themes") or {}).get(_tpick) or []
    if _feeds:
        with st.expander(f"📣 Theme catalysts — {_tb['name']} · last {_tc.get('days', 7)}d "
                         f"({len(_feeds)})", expanded=True):
            for e in _feeds[:15]:
                _mat = "🔴" if e.get("materiality") == "HIGH" else "🟡"
                _sur = (f" · EPS surprise {e['eps_surprise_pct']:+.0f}%"
                        if e.get("eps_surprise_pct") is not None else "")
                _rxn = (" · confirmed" if "CONFIRMED" in
                        str(e.get("reaction") or "") else "")
                st.markdown(
                    f"{_mat} **{e['symbol']}** — {e.get('title') or e['event']}"
                    f"{_sur}{_rxn} · "
                    f"{(e.get('when') or '')[:10]}")
            st.caption("Positive catalyst + EPS-revision events on theme "
                       "members — names printing improving fundamentals now. "
                       "Full unfiltered feed lives on the Alerts page.")
    else:
        st.caption(f"📣 No fresh positive catalysts on {_tb.get('name', _tpick)} "
                   "members in the last 7d.")
elif not (_csectors or _themes) and not (
        _cst.get("running") or _cst.get("error")):
    st.caption("🎯 Sector candidates not ranked yet — click the button "
               "(one-off ~3-5 min; results stay until you re-run).")

# --- 📈 Acceleration watch — companies whose growth RATE has risen for
# 2+ consecutive quarters (the early-inflection signature), plus the
# mirrors: decelerating held names and streaks that just broke.
_aw = _sget("accel_data", "api/v1/movers/acceleration")
_basket = _aw.get("basket") or []
_decel = _aw.get("decelerating") or []
_broken = _aw.get("broken") or []
_ah1, _ah2 = st.columns([4, 1])
_ah1.subheader(f"📈 Acceleration watch — {len(_basket)} inflecting")
_ah1.caption("**check:** early accumulation candidates — growth *rate* "
             "rising 2+ consecutive quarters = the emerging-leader "
             "signature, found before the movers list does. "
             "📉 = held names decelerating (trim warning) · "
             "💔 = streak just broke (thesis dead). "
             "Refreshes when you re-run sector candidates.")
with _ah2:
    if st.button("⟳", key="chk_accel", help="reload acceleration watch"):
        st.session_state.pop("accel_data", None)
        st.rerun()

if _basket or _decel or _broken:
    def _path(p):
        return "→".join(f"{v:+.0f}%" for v in (p or [])[:4]) or "—"

    def _adf2(rows, decel=False):
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["streak"] = df.apply(
            lambda r: f"rev ×{r['rev_streak']} · eps ×{r['eps_streak']}"
            if not decel
            else f"rev ↓{r.get('rev_decel', 0)} · eps ↓{r.get('eps_decel', 0)}",
            axis=1)
        df["rev path"] = df["rev_path"].apply(_path)
        df["eps path"] = df["eps_path"].apply(_path)
        df["scope"] = df.apply(
            lambda r: "📦 held" if r.get("in_portfolio")
            else ("👁 watch" if r.get("in_watchlist") else "🆕 new"),
            axis=1)
        keep = ["symbol", "scope", "streak", "rev path", "eps path",
                "verdict", "price"]
        return df[[c for c in keep if c in df.columns]]

    if _basket:
        st.markdown(f"**📈 Acceleration basket — {len(_basket)}** "
                    "(rev OR eps streak ≥2)")
        st.dataframe(_adf2(_basket), use_container_width=True,
                     hide_index=True)
    if _decel:
        st.markdown(f"**📉 Decelerating holds — {len(_decel)}** "
                    "(growth falling 2+ consecutive quarters)")
        st.dataframe(_adf2(_decel, decel=True), use_container_width=True,
                     hide_index=True)
    if _broken:
        st.markdown(f"**💔 Streak broken — {len(_broken)}** "
                    "(was accelerating last run — thesis check)")
        st.dataframe(_adf2(_broken), use_container_width=True,
                     hide_index=True)
    st.caption(
        "**Legend** — **scope**: 📦 held = already in your portfolio · "
        "👁 watch = on your watchlist · 🆕 new = not tracked yet (the "
        "discovery names). **streak**: rev ×3 = revenue growth improved "
        "3 quarters in a row · eps ×2 = EPS growth improved 2 in a row · "
        "↓ = consecutive *declines* (deceleration warning). **path** = "
        "the actual YoY growth per quarter, newest→oldest — read the shape, "
        "not just the count (improving from negative = turnaround). "
        f"Max streak 4 — FMP returns 5 quarters. "
        f"as of {(_aw.get('as_of') or '—')[:16].replace('T', ' ')}")
elif _aw.get("as_of") is None:
    st.caption("📈 No streak data yet — fills on the next sector-candidates "
               "run; click ⟳ after it completes.")
else:
    st.caption("📈 No streaks ≥2 in the latest run — quiet tape for "
               "acceleration.")

# --- 🎯 PT watch — analyst price-target repricing. FMP's grades feed is
# dead on this plan, but PT data works: month avg pulling away from the
# quarter avg + fresh PTs printing = analysts re-rating the name. This is
# the upgrade signal when no upgrade headline hits the feed.
_pt = _sget("pt_data", "api/v1/movers/pt-watch")
_pt_rows = _pt.get("symbols") or []
_ph1, _ph2 = st.columns([4, 1])
_ph1.subheader("🎯 Analyst PT watch")
_ph1.caption("**check:** upgrades you can trade before the headline — "
             "PT momentum ≥+5% month-vs-quarter with fresh PTs printing = "
             "analysts re-rating now. Fires a `pt_repricing` alert. "
             "Runs daily at the scan tail; ⟳ reloads the board.")
with _ph2:
    _pc1, _pc2 = st.columns(2)
    with _pc1:
        if st.button("🎯 run", key="run_ptw",
                     help="snapshot PT data for the universe (~2-4 min)"):
            try:
                client.post("api/v1/movers/pt-watch/run")
                st.session_state["pt_status"] = {"running": True}
                st.toast("PT watch started")
            except Exception as e:
                st.error(f"PT watch failed: {e}")
            st.rerun()
    with _pc2:
        if st.button("⟳", key="chk_ptw",
                     help="check progress / reload the board"):
            try:
                st.session_state.pop("pt_data", None)
                st.session_state["pt_status"] = client.get(
                    "api/v1/movers/pt-watch/status")
            except Exception as e:
                st.error(f"PT watch reload failed: {e}")
            st.rerun()
_ptst = _sget("pt_status", "api/v1/movers/pt-watch/status")
if _ptst.get("running"):
    st.caption("🎯 PT watch running — ~2-4 min over the universe + "
               "candidate pools.")
if _pt_rows:
    _pdf = pd.DataFrame(_pt_rows)
    _pdf["scope"] = _pdf.apply(
        lambda r: "📦 held" if r.get("in_portfolio")
        else ("👁 watch" if r.get("in_watchlist") else "🆕 new"), axis=1)
    for c in ("pt_momentum_pct", "upside_pct"):
        _pdf[c] = _pdf[c].apply(
            lambda v: f"{v:+.0f}%" if v is not None else "—")
    keep = ["symbol", "scope", "pt_momentum_pct", "month_count",
            "month_avg", "quarter_avg", "consensus", "upside_pct", "price"]
    st.dataframe(
        _pdf[[c for c in keep if c in _pdf.columns]].rename(columns={
            "pt_momentum_pct": "PT momentum", "month_count": "fresh PTs",
            "month_avg": "mo avg PT", "quarter_avg": "qtr avg PT",
            "upside_pct": "to consensus"}),
        use_container_width=True, hide_index=True)
    st.caption(f"{len(_pt_rows)} symbols · as of {_pt.get('as_of') or '—'} · "
               "momentum = month-avg PT vs quarter-avg PT")
else:
    st.caption("🎯 No PT snapshots yet — click **run** or wait for the "
               "daily scan-tail pass.")

# --- 🏦 Analyst tape — event-level upgrades/downgrades/PT changes.
# This is the "BNP raised NBIS to $399" feed: FMP's latest-news firehoses,
# filtered to our universe. Catches the call hours before recap headlines.
_tape = _sget("tape_data", "api/v1/movers/analyst-tape?hours=48")
_tape_rows = _tape.get("actions") or []
_th1, _th2 = st.columns([4, 1])
_th1.subheader("🏦 Analyst tape")
_th1.caption("**check:** upgrades/downgrades/PT changes as they print — "
             "the event itself (firm, old→new grade, new target, gap vs "
             "price), not the recap. Fires an `analyst_action` alert. "
             "Runs at every scan tail; ⟳ reloads.")
with _th2:
    _tc1, _tc2 = st.columns(2)
    with _tc1:
        if st.button("🏦 run", key="run_tape",
                     help="poll the analyst firehose now (~seconds)"):
            try:
                client.post("api/v1/movers/analyst-tape/run")
                st.session_state["tape_status"] = {"running": True}
                st.toast("Analyst tape poll started")
            except Exception as e:
                st.error(f"Analyst tape failed: {e}")
            st.rerun()
    with _tc2:
        if st.button("⟳", key="chk_tape",
                     help="reload the tape"):
            try:
                st.session_state.pop("tape_data", None)
                st.session_state["tape_status"] = client.get(
                    "api/v1/movers/analyst-tape/status")
            except Exception as e:
                st.error(f"Tape reload failed: {e}")
            st.rerun()
_tst = _sget("tape_status", "api/v1/movers/analyst-tape/status")
if _tst.get("running"):
    st.caption("🏦 Tape poll running — a few seconds.")
if _tape_rows:
    _tdf = pd.DataFrame(_tape_rows)
    _tdf["scope"] = _tdf.apply(
        lambda r: "📦 held" if r.get("in_portfolio")
        else ("👁 watch" if r.get("in_watchlist") else "🆕 new"), axis=1)
    _tdf["grade"] = _tdf.apply(
        lambda r: (f"{r.get('prev_grade') or '?'} → {r['new_grade']}"
                   if r.get("new_grade") else "—"), axis=1)
    _tdf["target"] = _tdf.apply(
        lambda r: (f"${r['price_target']:g}"
                   + (f" ({r['target_gap_pct']:+.0f}%)"
                      if r.get("target_gap_pct") is not None else ""))
        if r.get("price_target") else "—", axis=1)
    _tdf["when"] = pd.to_datetime(_tdf["published"]).dt.strftime("%m-%d %H:%M")
    keep = ["when", "symbol", "scope", "firm", "action", "grade", "target"]
    st.dataframe(
        _tdf[[c for c in keep if c in _tdf.columns]].rename(columns={
            "firm": "firm", "action": "action"}),
        use_container_width=True, hide_index=True)
    st.caption(f"{len(_tape_rows)} actions · last {_tape.get('hours', 48)}h "
               "· target % = new PT vs price when posted")
else:
    st.caption("🏦 No analyst actions on universe symbols in the window — "
               "click **run** to poll now.")

# --- 💥 Rule Breakers — milestone-ladder tracking. Emerging names prove
# the secular engine (AI/space/cyber) is becoming the dominant driver.
# Quant gates auto-verify; thesis checklist stays human.
_rb = _sget("rb_data", "api/v1/movers/rule-breakers")
_rb_rows = _rb.get("members") or []
_rh1, _rh2 = st.columns([4, 1])
_rh1.subheader("💥 Rule Breakers")
_rh1.caption("**check:** the ladder — confirmed growers vs emerging names "
             "proving the transition. Gates: rev >25% · rev streak ≥2 · "
             "gross margin rising · mcap $1–500B (room to 2x). Weekly auto-discovery "
             "scans the whole universe and adds qualifiers; auto-added "
             "names drop out when gates collapse (your adds never do). "
             "AI exposure + thesis checklist are agent-researched 🤖; "
             "confirmed auto-promotes when all gates pass. "
             "⟳ reloads; 🏃 evaluates now.")
with _rh2:
    _rc1, _rc2 = st.columns(2)
    with _rc1:
        if st.button("🏃 eval", key="run_rb",
                     help="evaluate all members against the gates"):
            try:
                client.post("api/v1/movers/rule-breakers/run")
                st.session_state["rb_status"] = {"running": True}
                st.toast("Rule Breaker eval started")
            except Exception as e:
                st.error(f"RB eval failed: {e}")
            st.rerun()
    with _rc2:
        if st.button("⟳", key="chk_rb", help="reload the ladder"):
            try:
                st.session_state.pop("rb_data", None)
                st.session_state["rb_status"] = client.get(
                    "api/v1/movers/rule-breakers/status")
            except Exception as e:
                st.error(f"RB reload failed: {e}")
            st.rerun()
_rbst = _sget("rb_status", "api/v1/movers/rule-breakers/status")
if _rbst.get("running"):
    _rp1, _rp2 = st.columns([4, 1])
    _rp1.info("⏳ Eval in progress — ~51 members × 4 calls each, "
              "~4–6 min under rate limits.")
    if _rp2.button("� check", key="rb_chk_now",
                   help="refresh eval status + reload the board"):
        st.session_state.pop("rb_status", None)
        st.session_state.pop("rb_data", None)
        st.session_state["rb_status"] = client.get(
            "api/v1/movers/rule-breakers/status")
        st.rerun()
else:
    _last = _rbst.get("last_run_at")
    _lbl = (_last[:16].replace("T", " ") + " UTC" if _last else "never")
    st.caption(
        f"✅ last eval: **{_lbl}** · {_rbst.get('evaluated', 0)} members"
        + (f" · ⚠ {_rbst['error']}" if _rbst.get("error") else ""))
_TIER_ICON = {"confirmed": "💥", "emerging": "🌱",
              "speculative": "🧪", "watchlist": "👁"}
_MOM_ICONS = {"climax": "🔥", "breakout": "🚀", "uptrend": "📈",
              "recovery": "🌱", "basing": "😴", "pullback": "🟢",
              "rolling_over": "🟠", "knife": "🔪",
              "capitulation": "💥", "breakdown": "⬇️",
              "downtrend": "📉", "unknown": "⚪"}
_FUND_ICONS = {"accelerating": "🟢⚡", "growing": "🟢", "watch": "🟡",
               "cyclical": "🔵", "slowing": "🟠", "declining": "🔻",
               "deteriorating": "🔴", "unknown": "⚪"}
# momentum-going-up first within a tier: the dip-buy and ignition
# states lead, broken/tired states sink
_MOM_RANK = {"pullback": 0, "breakout": 1, "uptrend": 2, "recovery": 3,
             "basing": 4, "climax": 5, "rolling_over": 6,
             "knife": 7, "capitulation": 8, "breakdown": 9,
             "downtrend": 10, "unknown": 11}
if _rb_rows:
    _rdf = pd.DataFrame(_rb_rows)
    # sort momentum-first inside each tier — "what's actually moving"
    # ahead of "what's merely good"
    _TIER_RANK = {"confirmed": 0, "emerging": 1, "speculative": 2}
    _rdf["_tr"] = _rdf["tier"].map(_TIER_RANK).fillna(3)
    _rdf["_mr"] = _rdf.get("momentum", pd.Series(
        [None] * len(_rdf))).map(_MOM_RANK).fillna(11)
    _rdf = _rdf.sort_values(["_tr", "_mr", "symbol"])
    _rdf["mom_disp"] = _rdf.get("momentum", pd.Series(
        [None] * len(_rdf))).apply(
        lambda m: f"{_MOM_ICONS.get(m, '⚪')} {m}" if pd.notna(m)
        and m else "—")
    _rdf["fund_disp"] = _rdf.get("fund_state", pd.Series(
        [None] * len(_rdf))).apply(
        lambda f: f"{_FUND_ICONS.get(f, '⚪')} {f}" if pd.notna(f)
        and f else "—")
    _rdf["tier_disp"] = _rdf["tier"].map(
        lambda t: f"{_TIER_ICON.get(t, '')} {t}")
    _rdf["gates_disp"] = _rdf["gates_met"].apply(
        lambda g: f"{g}/4" if pd.notna(g) else "—")
    _rdf["checklist_disp"] = _rdf["checklist_met"].apply(
        lambda c: f"{c}/6" if pd.notna(c) else "—")
    _rdf["rev_disp"] = _rdf["rev_growth"].apply(
        lambda v: f"{v * 100:+.0f}%" if pd.notna(v) else "—")
    _rdf["gm_disp"] = _rdf.apply(
        lambda r: (f"{r['gross_margin']*100:.0f}%"
                   + (f"↑{((r['gross_margin']-r['gross_margin_prev'])*100):.0f}"
                      if pd.notna(r.get("gross_margin_prev")) and
                      r["gross_margin"] > r["gross_margin_prev"] else ""))
        if pd.notna(r.get("gross_margin")) else "—", axis=1)
    _rdf["ai_disp"] = _rdf.apply(
        lambda r: ((f"{r['ai_rev_pct']:.0f}%"
                    + ("🤖" if (r.get("checklist") or {}).get(
                        "ai_rev_pct_source") == "agent" else ""))
                   if pd.notna(r.get("ai_rev_pct")) else "—"), axis=1)
    _rdf["mcap_disp"] = _rdf["market_cap_b"].apply(
        lambda v: f"${v:.1f}B" if pd.notna(v) else "—")
    _rdf["fcf_disp"] = _rdf.get("fcf_margin", pd.Series(
        [None] * len(_rdf))).apply(
        lambda v: f"{v * 100:.0f}%" if pd.notna(v) else "—")
    _rdf["ms_disp"] = _rdf.get("milestones", pd.Series(
        [{}] * len(_rdf))).apply(
        lambda ms: f"{sum(1 for v in ms.values() if v)}/{len(ms)}"
        if isinstance(ms, dict) and ms else "—")
    _rdf["grade_disp"] = _rdf.apply(
        lambda r: (f"{r['rb_grade']} ({r['rb_score']})"
                   + ("~" if r.get("rb_grade_pending") else ""))
        if pd.notna(r.get("rb_score")) else "—", axis=1)
    _rdf["gap_disp"] = _rdf.apply(
        lambda r: (f"{r['gap_score']:.0f}"
                   + ("🔥" if r.get("muted_reaction") else "")
                   + (f"·{r['beat_streak']}W" if pd.notna(
                       r.get("beat_streak")) else ""))
        if pd.notna(r.get("gap_score")) else "—", axis=1)
    _rdf["earn_disp"] = _rdf["next_earnings"].apply(
        lambda d: f"📅{(pd.Timestamp(d) - pd.Timestamp.now().normalize()).days}d"
        if pd.notna(d) and
        0 <= (pd.Timestamp(d) - pd.Timestamp.now().normalize()).days <= 21
        else "—")
    keep = ["symbol", "tier_disp", "mom_disp", "fund_disp", "grade_disp",
            "gap_disp", "earn_disp", "suggested_tier", "rev_disp",
            "rev_streak", "gm_disp", "fcf_disp", "ai_disp", "mcap_disp",
            "gates_disp", "checklist_disp", "ms_disp"]
    st.dataframe(
        _rdf[[c for c in keep if c in _rdf.columns]].rename(columns={
            "tier_disp": "tier", "suggested_tier": "sugg",
            "rev_disp": "rev", "rev_streak": "streak",
            "gm_disp": "GM", "fcf_disp": "FCF", "ai_disp": "AI rev%",
            "mcap_disp": "mcap", "gates_disp": "gates", "grade_disp": "grade",
            "checklist_disp": "thesis", "ms_disp": "ms",
            "mom_disp": "mom", "fund_disp": "fund",
            "gap_disp": "gap", "earn_disp": "earn"}),
        use_container_width=True, hide_index=True)
    st.caption("💥 confirmed · 🌱 emerging · 🧪 speculative (roadmap, "
               "not yet proven in financials) · 👁 watchlist · "
               "sugg = what the gates say · GM↑ = margin expanding YoY · "
               "ms = typed milestones hit · "
               "grade = gates+thesis+tailwind /100 (~ = floor, "
               "checklist un-researched) · "
               "mom = canonical momentum flag (🟢 pullback = the "
               "dip-buy zone · 🚀 breakout · 🟠 rolling_over · 🔪 "
               "knife · 📉 downtrend — sorted momentum-first inside "
               "each tier) · "
               "gap = expectation-gap score /100 — business trajectory "
               "vs Wall St's model (accel+beats+revisions+coverage+"
               "muted reaction+valuation); 🔥 = beat >5% but stock "
               "didn't pop; nW = beat streak · 📅 = earnings within "
               "3 weeks · "
               "AI rev% + checklist = agent-researched 🤖 "
               "(manual marks still win)")
    with st.expander("📖 How to read this board"):
        st.markdown("""
**Tiers — where a name sits on the conviction ladder**

| icon | tier | meaning |
|---|---|---|
| 💥 | confirmed | **Auto-promoted** when all 4 gates + AI rev% ≥20 + checklist ≥4/6 + proven pass — the secular engine verified in the financials (CRDO/ALAB-style). |
| 🌱 | emerging | ≥3 of 4 quant gates pass — the transition is *starting* to show in numbers (ALGM, MP). |
| 🧪 | speculative | Interesting roadmap/optionality, **not yet proven in financials** (ATEN: buying the roadmap). Manual tier — auto-discovery never lands here. |
| 👁 | watchlist | Quant candidates (2/4 gates), mostly auto-discovered. Auto-added names get auto-removed if gates collapse. |

**Columns — what each number means**

| col | definition |
|---|---|
| rev | Latest-quarter **YoY** revenue growth (not QoQ — computed from 8 quarterly income statements). |
| streak | Consecutive quarters where YoY revenue growth *accelerated* vs the prior year-ago quarter. 27% after 18% after 12% = streak 2. The "engine is emerging" proof. |
| GM | Latest gross margin; **↑** = higher than the *same quarter a year ago* (YoY margin expansion). |
| FCF | Latest-quarter free-cash-flow margin (freeCashFlow ÷ revenue). |
| AI rev% | Share of revenue from the secular engine (AI/data-center/space…). **Manual** — end-market splits live in earnings-call prose, no API exposes them. ≥20% is the promotion milestone. |
| mcap | Room-to-grow gate: $1–500B — big enough to survive, small enough to 2x. AMD ($330B) and PLTR ($400B) both doubled inside this band; only true mega-caps ($500B+) fail by design. |
| gates | Of 4 quant gates: **rev>25% · streak≥2 · GM rising YoY · mcap $1–500B**. |
| thesis | Qualitative checklist /6: tam · moat · ai_exposure · vectors · optionality · **proven** (engine already visible in financials — required for confirmed). **Agent-researched 🤖**; manual marks override. |
| sugg | What the pure numbers suggest (confirmed-eligible / emerging / watchlist). Divergence from tier = *your thesis vs the data* — information, not error. |
| ms | Typed milestones hit / defined — machine-checked every eval (e.g. `gross_margin>0.52`, `segment_growth:power integrated circuits>0.25`). A flip fires an alert. |

**Health score** (traction-detail ordering): tier weight + gates×8 + thesis×3 + milestones×5 + streak×3 — "how sure are we" compressed to one number.
        """)
    # traction detail — product-segment mix + typed milestone verdicts,
    # sorted by health score: tier + gates + thesis + milestones hit +
    # streak = "how sure are we" (proven engines at the top).
    _TIER_W = {"confirmed": 40, "emerging": 30, "speculative": 20,
               "watchlist": 10}

    def _rb_health(r):
        ms = r.get("milestones") or {}
        return (_TIER_W.get(r.get("tier"), 0)
                + (r.get("gates_met") or 0) * 8
                + min(r.get("checklist_met") or 0, 6) * 3
                + sum(1 for v in ms.values() if v is True) * 5
                + min(r.get("rev_streak") or 0, 4) * 3
                + (r.get("ai_traction") or 0))

    _trac = sorted([r for r in _rb_rows
                    if r.get("segments") or r.get("milestones")],
                   key=_rb_health, reverse=True)
    if _trac:
        with st.expander(f"🔬 Traction detail — {len(_trac)} names "
                         "with segments/milestones (healthiest first)"):
            for r in _trac:
                _line = (f"**{r['symbol']}** `health {_rb_health(r)}`"
                         + (f" `{r['rb_grade']}`"
                            if r.get("rb_grade") else ""))
                if r.get("ai_traction"):
                    _line += f" 🤖`AI {r['ai_traction']:.0f}`"
                _tagged = (r.get("ai_detail") or {}).get(
                    "tagged_segments") or {}
                _seg_bits = []
                for _n, _s in (r.get("segments") or {}).items():
                    _tag = "🤖 " if _n in _tagged else ""
                    _seg_bits.append(
                        f"{_tag}{_n} ${_s['rev']/1e6:.0f}M"
                        f" ({(_s.get('share') or 0) * 100:.0f}% share"
                        + (f", {_s['yoy'] * 100:+.0f}% YoY"
                           if _s.get("yoy") is not None else "") + ")")
                _ms_bits = " · ".join(
                    f"{'✅' if v else '❌' if v is False else '❔'} {lbl}"
                    for lbl, v in (r.get("milestones") or {}).items())
                if _seg_bits:
                    _line += " — " + " | ".join(_seg_bits)
                if _ms_bits:
                    _line += f" — {_ms_bits}"
                st.markdown(_line)
                _chans = (r.get("ai_detail") or {}).get(
                    "growth_channels") or {}
                if len(_chans) >= 2:
                    st.caption(
                        f"↳ 🚀 multi-channel: {len(_chans)} revenue "
                        f"lines growing >25% YoY — "
                        + ", ".join(f"{n} {v * 100:+.0f}%"
                                    for n, v in _chans.items())
                        + "  (the CRDO/PLTR 2x pattern)")
                _sugg = (r.get("ai_detail") or {}).get(
                    "suggested_segments") or []
                if _sugg:
                    st.caption(
                        f"↳ 🤖 AI-sounding segments you haven't tagged "
                        f"for {r['symbol']}: {', '.join(_sugg)} — tag in "
                        "Manage → 'AI-tagged segments' if they serve AI")
    with st.expander("⚙️ Manage members / checklist"):
        _mc1, _mc2, _mc3 = st.columns([1, 1, 2])
        _add_sym = _mc1.text_input("Symbol", key="rb_add_sym",
                                 placeholder="ALGM")
        _add_tier = _mc2.selectbox(
            "Tier", ["watchlist", "speculative", "emerging", "confirmed"],
            key="rb_add_tier")
        _ai_pct = _mc3.number_input("AI/secular rev %", 0, 100, 0,
                                    key="rb_ai_pct")
        _ai_segs = st.text_input(
            "AI-tagged product segments (comma-sep, must match segment "
            "names exactly)", key="rb_ai_segs",
            placeholder="power integrated circuits")
        _thesis = st.text_input("Thesis notes", key="rb_thesis",
                                placeholder="AI DC 17% of sales, "
                                            ">$425/rack content...")
        _miles = st.text_input(
            "Milestones (comma-sep; typed metric>target auto-checks)",
            key="rb_miles",
            placeholder="gross_margin>0.52 · ai_rev_pct>25 · "
                        "segment_share:power integrated circuits>0.5 · "
                        "DC rev >25% of sales")
        _cl_cols = st.columns(6)
        _cl = {}
        for i, k in enumerate(["tam", "moat", "ai_exposure",
                               "vectors", "optionality", "proven"]):
            _cl[k] = _cl_cols[i].checkbox(
                k, key=f"rb_cl_{k}",
                help="engine already visible in financials"
                if k == "proven" else k)
        if st.button("💾 Save member", key="rb_save"):
            try:
                cl = dict(_cl)
                if _ai_pct:
                    cl["ai_rev_pct"] = _ai_pct
                if _ai_segs:
                    cl["ai_segments"] = [s.strip().lower() for s in
                                         _ai_segs.split(",") if s.strip()]
                if _thesis:
                    cl["thesis"] = _thesis
                if _miles:
                    cl["milestones"] = [_parse_milestone(m) for m in
                                        _miles.split(",") if m.strip()]
                if _ai_pct:
                    cl["ai_rev_pct_source"] = "human"  # manual wins
                client.post("api/v1/movers/rule-breakers/member",
                            {"symbol": _add_sym.strip().upper(),
                             "tier": _add_tier, "checklist": cl})
                st.session_state.pop("rb_data", None)
                st.toast(f"{_add_sym.upper()} saved")
            except Exception as e:
                st.error(f"Save failed: {e}")
            st.rerun()
        _rs1, _rs2 = st.columns([1, 3])
        if _rs1.button("🤖 Research AI exposure", key="rb_research",
                       help="Agent researches ai_rev_pct + AI segments "
                            "for a symbol (typed above) or all members "
                            "missing it"):
            try:
                _sym = _add_sym.strip().upper()
                _res = client.post(
                    "api/v1/movers/rule-breakers/research-ai"
                    + (f"?symbol={_sym}" if _sym else ""))
                st.session_state.pop("rb_data", None)
                st.toast("AI research done — see ai_rev_pct 🤖 values")
                st.json(_res)
            except Exception as e:
                st.error(f"Research failed: {e}")
else:
    st.caption("💥 No members yet — add symbols in Manage, then run eval.")

# --- 🚀 5x Scout — separate engine. Finds the PLTR-2022 fingerprint in
# the $1-30B zone BEFORE the repricing: platform GM, moderate-but-
# accelerating rev, hidden fast-growing segment, net cash, beaten down.
_sc = _sget("sc_data", "api/v1/movers/smallcap")
_sch1, _sch2, _sch3, _sch4 = st.columns([3, 1, 1, 1])
_sch1.subheader("🚀 5x Scout — small-cap multibagger hunter")
_sch1.caption("**check:** $1–30B names with the pre-inflection "
              "fingerprint — rev ≥15% · GM ≥40% · net cash · profit "
              "path — plus hidden engines (segments >40% YoY) and "
              "beaten-down entries. Tiers: 👀 watch → 🌿 inflecting "
              "(≥4 gates) → 🏃 runner (all gates + engine). "
              "Not tied to Rule Breakers — that board is 2x/proven.")
if _sch2.button("🏃 eval", key="sc_eval",
                help="Deep-eval members (6 calls each — gates, "
                     "segments, hidden engine)"):
    try:
        client.post("api/v1/movers/smallcap/run")
        st.session_state["sc_status"] = {"running": True}
        st.toast("5x eval started")
    except Exception as e:
        st.error(f"Eval failed: {e}")
if _sch3.button("🔭 sweep", key="sc_sweep",
                help="Discovery sweep — next ~350-name slice of the "
                     "$1-30B pool (light eval, deep on qualifiers)"):
    try:
        client.post("api/v1/movers/smallcap/run?discover=true")
        st.session_state["sc_status"] = {"running": True}
        st.toast("5x discovery sweep started")
    except Exception as e:
        st.error(f"Sweep failed: {e}")
if _sch4.button("⟳", key="sc_reload"):
    st.session_state.pop("sc_data", None)
    st.session_state.pop("sc_status", None)
    st.rerun()

_scst = _sget("sc_status", "api/v1/movers/smallcap/status")
if _scst.get("running"):
    _sc_row = st.columns([3, 1])
    _sc_row[0].info("⏳ 5x Scout running — members × 6 calls, "
                    "a few minutes (sweeps are longer).")
    if _sc_row[1].button("🔄 check", key="sc_check"):
        st.session_state.pop("sc_status", None)
        st.session_state.pop("sc_data", None)
        st.rerun()
elif _scst.get("last_run_at"):
    st.caption(f"✅ last eval: {_scst['last_run_at'][:16].replace('T',' ')} "
               f"UTC · {_scst.get('evaluated', 0)} evaluated"
               + (f" · ⚠ {_scst['error'][:80]}" if _scst.get("error")
                  else ""))

if _sc and _sc.get("members"):
    _srows = _sc["members"]
    _SC_TIER = {"runner": "🏃", "inflecting": "🌿", "watch": "👀"}
    _sdf = pd.DataFrame(_srows)
    _sdf["tier_disp"] = _sdf["tier"].map(
        lambda t: f"{_SC_TIER.get(t, '👀')} {t}")
    _sdf["grade_disp"] = _sdf.apply(
        lambda r: (f"{r['grade']} ({r['sc_score']:.0f})"
                   + ("~" if r.get("checklist_pending") else ""))
        if pd.notna(r.get("sc_score")) else "—", axis=1)
    _sdf["rev_disp"] = _sdf["rev_growth"].apply(
        lambda v: f"{v * 100:+.0f}%" if pd.notna(v) else "—")
    _sdf["gm_disp"] = _sdf["gross_margin"].apply(
        lambda v: f"{v * 100:.0f}%" if pd.notna(v) else "—")
    _sdf["cash_disp"] = _sdf.apply(
        lambda r: ("💰net" if r.get("net_cash") else
                   (f"${r['cash_b']:.1f}/${r['debt_b']:.1f}B"
                    if pd.notna(r.get("cash_b")) else "—")), axis=1)
    _sdf["dd_disp"] = _sdf["dd52w"].apply(
        lambda v: f"{v * 100:.0f}%" if pd.notna(v) else "—")
    _sdf["he_disp"] = _sdf["hidden_engine"].apply(
        lambda he: ("🔥 " + ", ".join(
            f"{n} {s['yoy'] * 100:+.0f}%"
            for n, s in list(he.items())[:2]))
        if isinstance(he, dict) and he else "—")
    _sdf["mcap_disp"] = _sdf["market_cap_b"].apply(
        lambda v: f"${v:.1f}B" if pd.notna(v) else "—")
    _sdf["gates_disp"] = _sdf["gates_met"].apply(
        lambda g: f"{g}/5" if pd.notna(g) else "—")
    _sdf["gap_disp"] = _sdf.apply(
        lambda r: (f"{r['gap_score']:.0f}"
                   + ("🔥" if r.get("muted_reaction") else "")
                   + (f"·{r['beat_streak']}W" if pd.notna(
                       r.get("beat_streak")) else ""))
        if pd.notna(r.get("gap_score")) else "—", axis=1)
    _sdf["earn_disp"] = _sdf["next_earnings"].apply(
        lambda d: f"📅{(pd.Timestamp(d) - pd.Timestamp.now().normalize()).days}d"
        if pd.notna(d) and
        0 <= (pd.Timestamp(d) - pd.Timestamp.now().normalize()).days <= 21
        else "—")
    _sdf["ana_disp"] = _sdf["num_analysts"].apply(
        lambda v: f"{v:.0f}" if pd.notna(v) else "—")
    _sdf["mom_disp"] = _sdf.get("momentum", pd.Series(
        [None] * len(_sdf))).apply(
        lambda m: f"{_MOM_ICONS.get(m, '⚪')} {m}" if pd.notna(m)
        and m else "—")
    _sdf["fund_disp"] = _sdf.get("fund_state", pd.Series(
        [None] * len(_sdf))).apply(
        lambda f: f"{_FUND_ICONS.get(f, '⚪')} {f}" if pd.notna(f)
        and f else "—")
    st.dataframe(
        _sdf[["symbol", "tier_disp", "mom_disp", "fund_disp",
              "grade_disp", "gap_disp",
              "earn_disp", "rev_disp", "rev_streak", "gm_disp",
              "cash_disp",
              "dd_disp", "he_disp", "mcap_disp", "ana_disp",
              "gates_disp"]].rename(columns={
            "mom_disp": "mom", "fund_disp": "fund",
            "tier_disp": "tier", "grade_disp": "grade",
            "gap_disp": "gap", "earn_disp": "earn",
            "rev_disp": "rev", "rev_streak": "streak",
            "gm_disp": "GM", "cash_disp": "cash/debt",
            "dd_disp": "vs high", "he_disp": "hidden engine",
            "mcap_disp": "mcap", "ana_disp": "analysts",
            "gates_disp": "gates"}),
        use_container_width=True, hide_index=True)
    st.caption("grade = size+growth+platform+fortress+engine+early "
               "/100 (~ = floor, checklist un-researched) · "
               "gap = expectation-gap /100 — acceleration + beat "
               "streak + estimate revisions + thin coverage + muted "
               "reaction (� = big beat, small pop) · "
               "�💰net = cash > debt · vs high = drawdown from 52w "
               "high (more negative = earlier) · 🔥 in hidden engine "
               "= product line compounding >40% YoY inside a "
               "moderate total (the PLTR-2022 tell) · "
               "analysts = coverage count (low = under-covered = "
               "bigger expectation gap possible)")
    with st.expander("⚙️ Manage 5x members / research"):
        _sm1, _sm2 = st.columns([2, 2])
        _sm_sym = _sm1.text_input("Symbol", key="sc_add_sym",
                                placeholder="e.g. IONQ")
        if _sm1.button("➕ add / 🔍 research", key="sc_add"):
            try:
                _s = _sm_sym.strip().upper()
                client.post("api/v1/movers/smallcap/member",
                            json={"symbol": _s, "tier": "watch",
                                  "checklist": {}})
                _res = client.post(
                    f"api/v1/movers/smallcap/research?symbol={_s}")
                st.session_state.pop("sc_data", None)
                st.json(_res)
            except Exception as e:
                st.error(f"Add/research failed: {e}")
        if _sm2.button("🤖 Research all missing", key="sc_research"):
            try:
                _res = client.post("api/v1/movers/smallcap/research")
                st.session_state.pop("sc_data", None)
                st.json(_res)
            except Exception as e:
                st.error(f"Research failed: {e}")
else:
    st.caption("🚀 No members yet — hit 🔭 sweep to start scanning the "
               "$1-30B pool, or add symbols in Manage.")

# --- Accumulation picks — days_on_list ≥3 + quality verdict + rising volume ---
_qh1, _qh2 = st.columns([4, 1])
_qh1.subheader("🏆 Quality movers & accumulation")
_qh1.caption("**check:** the actual buy list — movers passing the CANSLIM "
             "gate + repeat presence = institutional accumulation, not "
             "one-day spikes. Empty = today's movers are speculative junk; "
             "when it fills, it's your highest-conviction buy source.")
with _qh2:
    _qc1, _qc2 = st.columns(2)
    with _qc1:
        if st.button("🧪 run", help="run the quality screen "
                     "(~1-2 min, fundamentals per mover)"):
            try:
                client.post("api/v1/movers/quality/run")
                st.session_state["quality_status"] = {"running": True}
                st.toast("Quality screen started")
            except Exception as e:
                st.error(f"Quality screen failed: {e}")
            st.rerun()
    with _qc2:
        if st.button("⟳", help="check quality progress / reload results",
                     key="chk_quality"):
            try:
                st.session_state["quality_data"] = client.get(
                    "api/v1/movers/quality")
                st.session_state["quality_status"] = client.get(
                    "api/v1/movers/quality/status")
            except Exception as e:
                st.error(f"Quality results failed: {e}")
            st.rerun()
_qst = _sget("quality_status", "api/v1/movers/quality/status")
if _qst.get("running"):
    st.caption("🧪 Quality screen running — click ⟳ to refresh results.")
elif _qst.get("error"):
    st.warning(f"Last quality screen errored: {_qst['error']}")
elif not _qst.get("last_run_at") and not quality.get("items"):
    st.caption("Quality screen hasn't run yet — click 🧪 "
               "(~1-2 min, fundamentals per mover).")

qitems = quality.get("items") or []
acc = [i for i in qitems if i.get("accumulation")]
if acc:
    st.subheader(f"🔁 Accumulation picks — {len(acc)}")
    st.caption("On the movers list ≥3 days in the last 10 + QUALITY/GROWTH verdict "
               "+ volume rising — repeat institutional presence, not a one-day spike")
    def _adf(rows):
        df = pd.DataFrame(rows)
        keep = ["symbol", "verdict", "days_on_list", "volume_trend", "change_pct",
                "eps_growth", "rev_growth", "roe", "price",
                "in_portfolio", "in_watchlist"]
        return df[[c for c in keep if c in df.columns]].rename(columns={
            "days_on_list": "days", "volume_trend": "vol trend",
            "change_pct": "chg%", "eps_growth": "EPS g%", "rev_growth": "Rev g%",
            "roe": "ROE%", "in_portfolio": "port", "in_watchlist": "watch"})
    st.dataframe(_adf(acc), use_container_width=True, hide_index=True)
else:
    st.caption("🔁 Accumulation picks: none — no mover has repeated ≥3 days "
               "with a passing quality verdict yet (memory builds daily).")

# --- Quality movers (fundamental gate over movers) ---
if qitems:
    n_q = quality.get("quality_count", 0)
    n_g = sum(1 for i in qitems if i.get("verdict") == "GROWTH MOVER")
    st.markdown(f"**🏆 Quality movers — {n_q} quality · {n_g} growth**")
    st.caption("QUALITY = EPS+Rev ≥25% QoQ **and** ROE >15% (proven CANSLIM leader) · "
               "GROWTH = EPS+Rev ≥25% without proven ROE (young/emerging leader) · "
               "price >$10 · vol >300K · above SMA20/50 · within 12% of 20d high")
    def _qdf(rows):
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["checks"] = df["checks"].apply(
            lambda c: " ".join(f"{'✅' if v else '—'}{k.split('_')[0]}"
                               for k, v in (c or {}).items()))
        df["risks"] = df["risks"].apply(
            lambda r: " · ".join(x.split(" — ")[0] for x in (r or [])) or "—")
        keep = ["symbol", "verdict", "days_on_list", "volume_trend", "passed",
                "eps_growth", "rev_growth", "roe", "price", "volume",
                "vs_sma20", "dd20_pct", "checks",
                "risk_level", "risks", "in_portfolio", "in_watchlist"]
        return df[[c for c in keep if c in df.columns]].rename(columns={
            "eps_growth": "EPS g%", "rev_growth": "Rev g%", "roe": "ROE%",
            "vs_sma20": "vs20", "dd20_pct": "dd20%", "risk_level": "risk",
            "days_on_list": "days", "volume_trend": "vol trend",
            "in_portfolio": "port", "in_watchlist": "watch"})
    st.dataframe(_qdf(qitems), use_container_width=True, hide_index=True)
    # spike → quality gate → watchlist: promote a passing mover into
    # the tracking universe. From there pulse/stalk/readiness take
    # over — the entry comes later, at the dip, not at the spike.
    _promo = [i["symbol"] for i in qitems
              if i.get("verdict") in ("QUALITY MOVER", "GROWTH MOVER")
              and not i.get("in_watchlist") and not i.get("in_portfolio")]
    if _promo:
        _pc1, _pc2 = st.columns([3, 1])
        _sel = _pc1.multiselect(
            "promote to watchlist (mover-candidates) — the pipeline: "
            "spike → quality gate → watchlist → stalk → readiness → "
            "trade plan", _promo, key="promote_sel")
        if _pc2.button("→ watchlist", key="promote_btn",
                       disabled=not _sel):
            _ok, _err = [], []
            for _s in _sel:
                try:
                    client.post(f"api/v1/movers/watchlist/{_s}")
                    _ok.append(_s)
                except Exception as e:
                    _err.append(f"{_s}: {e}")
            if _ok:
                st.success("watchlisted: " + ", ".join(_ok)
                           + " — now in the stalk pipeline")
            if _err:
                st.error(" · ".join(_err))
            st.session_state.pop("quality_data", None)
            st.rerun()

# --- Verdict performance — did the quality gate actually predict? -----------
# mover_outcomes records forward returns after each snapshot; this rollup is
# the honesty loop for QUALITY/GROWTH verdicts and the accumulation flag.
_ms = (_sget("stats_data", "api/v1/movers/stats").get("stats") or [])
if _ms:
    with st.expander("📈 Verdict performance — did the verdict predict?",
                     expanded=False):
        if st.button("⟳", key="chk_stats", help="reload verdict stats"):
            st.session_state.pop("stats_data", None)
            st.rerun()
        st.caption("Forward returns after a symbol appeared on movers lists, "
                   "by verdict × accumulation flag. If 'fails quality gate' "
                   "beats the verdicts, the gate gets re-thought.")
        sdf = pd.DataFrame(_ms)
        sdf["accumulation"] = sdf["accumulation"].map(
            {True: "🔁 acc", False: "—"}).fillna("—")
        keep = ["verdict", "accumulation", "horizon_days", "n",
                "avg_ret_pct", "avg_mfe_pct", "avg_mae_pct", "win_rate",
                "last_seen"]
        st.dataframe(
            sdf[[c for c in keep if c in sdf.columns]].rename(columns={
                "horizon_days": "horizon", "avg_ret_pct": "avg ret%",
                "avg_mfe_pct": "avg MFE%", "avg_mae_pct": "avg MAE%"}),
            use_container_width=True, hide_index=True)
        # Per-symbol receipts — the aggregate hides names; this shows who
        # got which verdict and what happened after (1/5/10d fwd returns).
        _sym_stats = (_sget("sym_stats", "api/v1/movers/stats/symbols")
                      .get("symbols") or [])
        if _sym_stats:
            st.markdown("**By symbol** — the receipts behind the rollup")
            _sdf2 = pd.DataFrame(_sym_stats)
            _sdf2["scope"] = _sdf2.apply(
                lambda r: "📦" if r.get("in_portfolio")
                else ("👁" if r.get("in_watchlist") else ""), axis=1)
            for c in ("ret1d", "ret5d", "ret10d", "snap_chg"):
                if c in _sdf2.columns:
                    _sdf2[c] = _sdf2[c].apply(
                        lambda v: f"{v:+.1f}%" if v is not None else "—")
            _sdf2["accumulation"] = _sdf2["accumulation"].map(
                {True: "🔁", False: "—"}).fillna("—")
            keep2 = ["symbol", "scope", "verdict", "accumulation", "as_of",
                     "snap_chg", "ret1d", "ret5d", "ret10d"]
            st.dataframe(
                _sdf2[[c for c in keep2 if c in _sdf2.columns]].rename(
                    columns={"as_of": "date", "snap_chg": "day move",
                             "ret1d": "+1d", "ret5d": "+5d",
                             "ret10d": "+10d", "accumulation": "acc"}),
                use_container_width=True, hide_index=True)

# --- 💡 Option structure ideas — keep/trim/add decisions rendered as
# structures. Rules-only, no chain pricing on the plan.
_ideas = (_sget("oi_data", "api/v1/movers/option-ideas").get("ideas") or [])
if _ideas:
    with st.expander(f"💡 Option structure ideas — {len(_ideas)}",
                     expanded=True):
        if st.button("⟳", key="chk_oi", help="recompute option ideas "
                     "from the latest screen run"):
            st.session_state.pop("oi_data", None)
            st.rerun()
        st.caption("**check:** covered call on extended = the trim list · "
                   "cash-secured put = where to add at support/mean · "
                   "spread = defined-risk entry. Structures, not orders.")
        _odf = pd.DataFrame(_ideas)
        keep = ["symbol", "context", "structure", "zone", "why"]
        st.dataframe(_odf[[c for c in keep if c in _odf.columns]],
                     use_container_width=True, hide_index=True)

# --- 🎡 Wheel tracker — your open CSPs/CCs vs latest prices. Manual log;
# the daily read answers "is any strike threatened — roll or accept?".
_pos = (_sget("wheel_data", "api/v1/movers/wheel").get("positions") or [])
with st.expander(f"🎡 Wheel tracker — {len(_pos)} open "
                 "(log your CSP/CC positions; status vs latest scan price)",
                 expanded=bool(_pos)):
    if st.button("⟳", key="chk_wheel", help="reload positions + re-price "
                 "against the latest scan"):
        st.session_state.pop("wheel_data", None)
        st.rerun()
    with st.form("wheel_add", clear_on_submit=True):
        w1, w2, w3, w4, w5, w6 = st.columns([1, 1, 1, 1, 1, 1])
        w_sym = w1.text_input("Symbol").upper()
        w_kind = w2.selectbox("Kind", ["csp", "cc"],
                              format_func=lambda k:
                              "CSP (cash-secured put)" if k == "csp"
                              else "Covered call")
        w_strike = w3.number_input("Strike", min_value=0.0, step=0.5)
        w_exp = w4.text_input("Expiry", placeholder="2026-10-16")
        w_prem = w5.number_input("Premium/sh", min_value=0.0, step=0.05)
        w_ct = w6.number_input("Contracts", min_value=1, step=1)
        if st.form_submit_button("＋ Log position"):
            try:
                r = client.post("api/v1/movers/wheel", {
                    "symbol": w_sym, "kind": w_kind, "strike": w_strike,
                    "expiry": w_exp, "contracts": int(w_ct),
                    "premium": w_prem or None})
                if r.get("error"):
                    st.error(r["error"])
                else:
                    st.toast(f"Logged {w_sym} {w_kind.upper()}")
                    st.session_state.pop("wheel_data", None)
                    st.rerun()
            except Exception as e:
                st.error(f"Log failed: {e}")
    if _pos:
        _wdf = pd.DataFrame(_pos)
        _wdf["pos"] = _wdf["kind"].map(
            {"csp": "CSP", "cc": "CC"})
        _wdf["px vs strike"] = _wdf.apply(
            lambda r: f"${r['price']:,.1f} ({r['dist_pct']:+.1f}%)"
            if r.get("price") else "—", axis=1)
        _wdf["state"] = _wdf["status_icon"] + " " + _wdf["status_note"]
        keep = ["symbol", "pos", "strike", "expiry", "dte", "px vs strike",
                "state", "breakeven", "premium", "id"]
        st.dataframe(
            _wdf[[c for c in keep if c in _wdf.columns]].rename(columns={
                "dte": "DTE", "premium": "prem/sh"}),
            use_container_width=True, hide_index=True)
        st.caption("🔴 ITM = assignment/call-away imminent · 🟡 = decide: "
                   "roll or accept · CSP breakeven = strike − premium. "
                   "Close via API: POST /movers/wheel/{id}/close "
                   "(status assigned/called/expired).")

# =====================================================================
# 📚 INFORMATIONAL — intraday / speculative context below this line.
# Useful color, but none of it is a swing-trade decision.
st.divider()
st.subheader("📚 Informational — context, not swing decisions")
st.caption("ORB = day-trade instrument (15-min breakout, not your "
           "timeframe) · movers feed = raw lists with no verdict — the "
           "quality gate above is what makes a mover actionable.")

# --- ORB day-trade watchlist ---
_oh1, _oh2 = st.columns([4, 1])
_oh1.subheader(f"⚡ ORB watchlist — session {orb.get('session_date') or '—'}")
with _oh2:
    _oc1, _oc2 = st.columns(2)
    with _oc1:
        if st.button("⚡ run", help="run the ORB screen "
                     "(~30-60s, intraday 5m bars)"):
            try:
                client.post("api/v1/movers/orb/run")
                st.session_state["orb_status"] = {"running": True}
                st.toast("ORB screen started")
            except Exception as e:
                st.error(f"ORB screen failed: {e}")
            st.rerun()
    with _oc2:
        if st.button("⟳", help="check ORB progress / reload results",
                     key="chk_orb"):
            try:
                st.session_state["orb_data"] = client.get("api/v1/movers/orb")
                st.session_state["orb_status"] = client.get(
                    "api/v1/movers/orb/status")
            except Exception as e:
                st.error(f"ORB results failed: {e}")
            st.rerun()
_ost = _sget("orb_status", "api/v1/movers/orb/status")
if _ost.get("running"):
    st.caption("⚡ ORB screen running — click ⟳ to refresh results.")
elif _ost.get("error"):
    st.warning(f"Last ORB screen errored: {_ost['error']}")

items = orb.get("items") or []
if items:
    st.caption("Gap ≥1% + RVOL ≥1.5 → qualified · break of 15-min range high = long trigger, "
               "break of low = short trigger")
    if orb.get("spy_change_pct") is not None:
        st.caption(f"SPY today: {orb['spy_change_pct']:+.2f}% "
                   f"({'tailwind for longs' if orb['spy_change_pct'] > 0 else 'tailwind for shorts'})")

    picks = orb.get("top_picks") or []
    if picks:
        st.markdown("**🏆 Top picks of the day** — scored on the Zarattini/Aziz "
                    "stocks-in-play factors: range break, RVOL, gap size, "
                    "tight range vs ATR, market tailwind, universe membership")
        cols = st.columns(len(picks))
        for col, p in zip(cols, picks):
            direction = "🟢 LONG" if (p.get("gap_pct") or 0) > 0 else "🔴 SHORT"
            with col:
                st.markdown(f"### {p['symbol']} — {direction}")
                st.metric("ORB score", f"{p.get('orb_score', 0):.0f}",
                          delta=f"gap {p.get('gap_pct', 0):+.1f}% · RVOL {p.get('rvol') or 0}×")
                for w in p.get("why") or []:
                    st.caption(f"• {w}")
                if p.get("swing_ok") is True:
                    st.success("↗ swing-hold candidate: " +
                               " · ".join(p.get("swing_reasons") or []))
                elif p.get("swing_reasons"):
                    st.caption("✖ swing: " + " · ".join(p["swing_reasons"]))

    def _orb_df(rows):
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["range"] = df.apply(lambda r: f"{r['or_low']}–{r['or_high']}", axis=1)
        df["pick"] = df["top_pick"].map({True: "🏆", False: ""})
        df["swing"] = df["swing_ok"].map({True: "↗ yes", False: "✖", None: ""}).fillna("")
        keep = ["pick", "symbol", "orb_score", "gap_pct", "rvol", "change_pct",
                "price", "range", "or_range_pct", "or_state", "swing",
                "verdict", "in_portfolio", "in_watchlist"]
        return df[[c for c in keep if c in df.columns]].rename(columns={
            "orb_score": "score", "gap_pct": "gap%", "rvol": "RVOL",
            "change_pct": "chg%", "or_range_pct": "OR width%",
            "or_state": "OR state", "in_portfolio": "port",
            "in_watchlist": "watch"})
    st.dataframe(_orb_df(items), use_container_width=True,
                 hide_index=True)
    if orb.get("as_of"):
        st.caption(f"As of {orb['as_of'][:16].replace('T', ' ')} UTC")
else:
    st.info("No ORB candidates — click ⚡ Run ORB screen (needs intraday 5m bars).")

# --- Universe movers ---
def _movers_df(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    keep = [c for c in ["symbol", "company", "price", "change_percent", "volume",
                        "kind", "in_portfolio", "in_watchlist"] if c in df.columns]
    return df[keep].rename(columns={
        "change_percent": "chg%", "in_portfolio": "port", "in_watchlist": "watch"})

uni = movers.get("universe_movers") or []
_uh1, _uh2 = st.columns([4, 1])
_uh1.subheader(f"🎯 Your universe — {len(uni)} moving")
with _uh2:
    if st.button("🔄 load feed", help="fetch today's movers feed "
                 "(gainers/losers/most-active — fills this + market-wide)"):
        try:
            st.session_state["movers_data"] = client.get("api/v1/movers")
        except Exception as e:
            st.error(f"Movers feed failed: {e}")
        st.rerun()
if uni:
    st.dataframe(_movers_df(uni), use_container_width=True, hide_index=True)
elif st.session_state["movers_data"] is None:
    st.caption("Feed not loaded — click **🔄 load feed** (live fetch, "
               "fills this and market-wide below).")
else:
    st.caption("No portfolio/watchlist names on today's movers lists.")

st.subheader("🌐 Market-wide")
for label, key in [("Top Gainers", "gainers"), ("Top Losers", "losers"),
                   ("Most Active", "most_active")]:
    rows = movers.get(key) or []
    if rows:
        with st.expander(f"{label} ({len(rows)})", expanded=False):
            st.dataframe(_movers_df(rows), use_container_width=True, hide_index=True)

if movers.get("last_updated"):
    st.caption(f"Updated {movers['last_updated']}")
