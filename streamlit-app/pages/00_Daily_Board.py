"""Daily Action Board — today's top ~10 actions.

Moto: fear → deploy cash into quality dips; greed → take profits.
Exits rank first (protect the book), then accumulates ranked by
confluence: momentum flag × fundamentals (RB/5x tier, gap score,
beat streak) × swing-screen readiness × catalyst tailwind.
Advisory only — you decide, you execute.
"""
import sys
import os
from datetime import date

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient
from api_config import api_config
from utils import render_top_nav, health_col, health_cfg, sym_md

client = APIClient(api_config.python_worker_url, timeout=180)

st.set_page_config(page_title="Daily Board", page_icon="🎯", layout="wide")
render_top_nav()
st.title("🎯 Daily Action Board")
st.caption("Exits first, then deploys. Momentum flag × fundamentals × "
           "swing readiness × catalysts — market regime sets the posture, "
           "not the picks.")

# --- today's posture — the permission layer for everything below ---
try:
    _PO = client.get("api/v1/board/posture") or {}
except Exception:
    _PO = {}
if _PO.get("posture"):
    _PI = {"aggressive": "🟢", "constructive": "🟢",
           "neutral": "⚪", "caution": "🟡", "defensive": "🔴"}
    _perm = ("new longs ✅" if _PO.get("new_longs") else
             "new longs ⛔") + \
            (" · shorts ✅" if _PO.get("shorts") else "") + \
            (" · hedge 🛡" if _PO.get("hedge_on") else "")
    st.markdown(
        f"{_PI.get(_PO['posture'],'•')} **today's posture: "
        f"{_PO['posture']}** — {_perm} · `{_PO.get('matched') or '—'}`"
        + (f" — {_PO['note']}" if _PO.get("note") else ""))
    if _PO.get("shorts"):
        _ins = (_PO.get("instruments") or {}).get("short") or {}
        st.caption(f"short instrument: {_ins.get('etf','SQQQ')} — "
                   f"{_ins.get('note','')}")

_MOM_I = {"climax": "🔥", "breakout": "🚀", "uptrend": "📈",
          "recovery": "🌱", "basing": "😴", "pullback": "🟢",
          "rolling_over": "🟠", "knife": "🔪", "capitulation": "💥",
          "breakdown": "⬇️", "downtrend": "📉", "unknown": "⚪"}
_ACT_I = {"EXIT": "🔴", "TRIM": "🟠", "ACCUMULATE": "🟢",
          "PUT": "🔻", "BOUNCE": "🏀"}
_STANCE_I = {"FEAR — DEPLOY": "🟢", "GREED — HARVEST": "🟠",
             "DEFENSIVE": "🔴", "NEUTRAL": "⚪"}
_FUND_I = {"accelerating": "🟢⚡", "growing": "🟢", "watch": "🟡",
           "cyclical": "🔵", "slowing": "🟠", "declining": "🔻",
           "deteriorating": "🔴", "unknown": "⚪"}
_FUND_RISK = {"low": "", "medium": "risk·med", "high": "risk·HIGH",
              "very_high": "risk·V.HIGH"}

# --- 📡 technicals feed — the data pipeline strip ----------------------------
# momentum loads bars+technicals at :30 hourly through the session;
# alerts and focus-scan ride each refresh 15/20 min later.
try:
    _cat = (client.get("api/v1/board/jobs/catalog") or {}).get("jobs") or []
    _st = (client.get("api/v1/board/refresh/status") or {}).get("jobs") or {}
except Exception:
    _cat, _st = [], {}

def _hm(iso: str) -> str:
    return str(iso or "")[11:16] or "—"

_feed = [j for j in _cat if j.get("name") in
         ("morning-regime", "momentum", "alerts", "focus-scan")]
if _feed:
    _parts = []
    for j in sorted(_feed, key=lambda x: x.get("name") != "momentum"):
        s = _st.get(j["name"]) or {}
        mark = ("⏳" if s.get("running") else
                "❌" if (s.get("error") or j.get("last_error")) else
                "✅" if j.get("last_run") else "⚪")
        _parts.append(
            f"{mark} **{j['name']}** `{j.get('cron') or '—'}` "
            f"last {_hm(str(j.get('last_run') or ''))} → "
            f"next {_hm(str(j.get('next_run') or ''))}")
    st.caption("📡 **technicals feed** (all times UTC) — "
               + " · ".join(_parts))

if st.button("🔄 Refresh board"):
    st.cache_data.clear()
    st.rerun()

# --- ⚙️ data & refresh control panel ------------------------------------------
# every layer the board reads gets a named button; "all" runs them in
# dependency order. jobs run in the background — poll status below.
_REFRESH_GROUPS = [
    ("📡 Market & tape", [
        ("regime", "Regime card (SPY/VIX/breadth)"),
        ("momentum", "Momentum flags (all tracked symbols ~90s)"),
    ]),
    ("🔬 Signals & fundamentals", [
        ("swing-scan", "Swing scan (setups + regime buckets)"),
        ("rule-breakers", "Rule Breaker eval + discovery"),
        ("smallcap", "5x Scout eval + discovery"),
        ("flywheel", "Expectation-gap scores"),
        ("fund-flags", "Fundamental flags (growth/health)"),
        ("priors", "Pattern priors (replay history ~10min)"),
    ]),
    ("📥 Inbox & book", [
        ("alerts", "Catalyst alert scan + auto-review"),
        ("focus-scan", "Focus book scan (conviction names)"),
        ("outcomes", "Evaluate alert/pattern outcomes"),
        ("leaps-mark", "Mark LEAPS positions (exit alerts)"),
        ("daily-calls", "Top-3 swing calls (journaled plans)"),
        ("meta", "Self-training weights"),
    ]),
    ("🩺 Ops", [
        ("custodian", "Support agent pass (detect→fix→verify)"),
    ]),
]


def _kick(job: str):
    try:
        r = client.post(f"api/v1/board/refresh/{job}")
        st.toast(f"{job}: {r.get('status', 'started')}")
    except Exception as e:
        st.error(f"{job} failed to start: {e}")


with st.expander("⚙️ Data & refresh — every input the board reads",
                 expanded=False):
    # fetch job status up front so each button can show its last run
    try:
        _jobs = (client.get("api/v1/board/refresh/status") or {}) \
            .get("jobs") or {}
    except Exception:
        _jobs = {}

    def _last(job: str) -> str:
        v = _jobs.get(job) or {}
        if v.get("running"):
            return "⏳ running…"
        if not v.get("at"):
            return "never run"
        ago = v.get("at", "")[5:16].replace("T", " ") + "Z"
        return f"❌ {ago}" if v.get("error") else ago

    _a1, _a2 = st.columns([3, 1])
    _a1.caption("Jobs run in the background — refresh the board when they "
                "finish. 'Everything' runs them in dependency order.")
    if _a2.button("🔄 REFRESH EVERYTHING", type="primary",
                  use_container_width=True):
        _kick("all")
    _a2.markdown(f":red[⏱ {_last('all')}]")
    for title, jobs in _REFRESH_GROUPS:
        st.markdown(f"**{title}**")
        cols = st.columns(len(jobs))
        for col, (job, label) in zip(cols, jobs):
            if col.button(label, key=f"rf_{job}", use_container_width=True):
                _kick(job)
            col.markdown(f":red[⏱ {_last(job)}]")

    # --- ⏰ job registry — AutoSys-style catalog + schedules ------------------
    try:
        _cat = (client.get("api/v1/board/jobs/catalog") or {}) \
            .get("jobs") or []
    except Exception:
        _cat = []
    if _cat:
        with st.expander("⏰ Job registry & schedules — AutoSys-style "
                         "(manual until `enabled` is ticked)",
                         expanded=False):
            import pandas as _pd
            _df = _pd.DataFrame(_cat)[[
                "name", "purpose", "kind", "cron", "enabled",
                "depends_on", "last_run", "last_error"]]
            _df["last_run"] = _df["last_run"].astype(str).str[:16]
            _ed = st.data_editor(
                _df, hide_index=True, use_container_width=True,
                disabled=["name", "purpose", "kind", "depends_on",
                          "last_run", "last_error"],
                column_config={
                    "cron": st.column_config.TextColumn(
                        "cron (UTC)", help="min hour dom month dow — "
                        "e.g. */30 12-22 * * 1-5"),
                    "enabled": st.column_config.CheckboxColumn(
                        "enabled?", help="tick to let the dispatcher "
                        "fire on schedule"),
                }, key="sched_editor")
            if st.button("💾 Save schedules", key="sched_save"):
                try:
                    _orig = {r["name"]: r for r in _cat}
                    _saved = 0
                    for _, _r in _ed.iterrows():
                        _o = _orig.get(_r["name"]) or {}
                        _nc = (str(_r["cron"]).strip()
                               if str(_r["cron"]) != "nan" else "") \
                            or None
                        _ne = bool(_r["enabled"])
                        if _nc != (_o.get("cron") or None) \
                                or _ne != bool(_o.get("enabled")):
                            client.post(
                                f"api/v1/board/jobs/{_r['name']}/schedule",
                                json_data={"cron": _nc,
                                           "enabled": _ne})
                            _saved += 1
                    st.toast(f"saved {_saved} schedule change(s)")
                except Exception as _e:
                    st.error(f"save failed: {_e}")
            st.caption("cron is 5-field **UTC** · `depends_on` = "
                       "predecessor jobs that must have a clean run "
                       "first · runs land in the same ledger as the "
                       "buttons above")

    # --- 🔍 on-demand symbol lookup — technicals + fundamentals live --------
    with st.expander("🔍 Symbol lookup — on-demand technicals & "
                     "fundamentals (live fetch, not the last batch)",
                     expanded=False):
        _ls, _lb = st.columns([2, 3])
        _sym = _ls.text_input("symbol", key="lookup_sym",
                              placeholder="e.g. MU").strip().upper()
        _c1, _c2, _c3 = _lb.columns(3)
        if _c1.button("📈 Technicals", key="lk_tech_btn",
                      disabled=not _sym):
            try:
                st.session_state["lk_tech"] = client.get(
                    f"api/v1/board/symbol/{_sym}/technicals")
            except Exception as _e:
                st.error(str(_e)[:200])
        if _c2.button("🏛 Fundamentals", key="lk_fund_btn",
                      disabled=not _sym):
            try:
                st.session_state["lk_fund"] = client.get(
                    f"api/v1/board/symbol/{_sym}/fundamentals")
            except Exception as _e:
                st.error(str(_e)[:200])
        if _c3.button("🔄 Refresh this symbol", key="lk_ref_btn",
                      disabled=not _sym,
                      help="fetch bars now → store → recompute flag"):
            try:
                st.session_state["lk_ref"] = client.post(
                    f"api/v1/board/symbol/{_sym}/refresh")
            except Exception as _e:
                st.error(str(_e)[:200])
        _t = st.session_state.get("lk_tech")
        if _t and _t.get("symbol") == _sym:
            if _t.get("error"):
                st.warning(_t["error"])
            else:
                _d = _t.get("detail") or {}
                st.markdown(
                    f"**{sym_md(_t['symbol'])}** · ${_t['close']:,.2f} · "
                    f"`{_t['state']}` · dip `{_d.get('dip_phase','—')}` "
                    f"({_d.get('dip_health','—')}/5) · "
                    f"RSI {_d.get('rsi')} · %B {_d.get('pct_b')} · "
                    f"vs50 {_d.get('vs_sma50')} · "
                    f"bars {_t['bars']} · as of {_t['as_of']}")
        _f = st.session_state.get("lk_fund")
        if _f and _f.get("symbol") == _sym:
            _st_ = (_f.get("stored") or {})
            if _st_.get("fundamental_state"):
                st.markdown(
                    f"🏛 `{_st_['fundamental_state']}` · "
                    f"risk `{_st_.get('fundamental_risk','—')}` · "
                    f"flagged {str(_st_.get('fundamental_updated_at'))[:16]}")
            elif _f.get("live"):
                _lv = _f["live"]
                st.markdown(
                    f"🏛 live: {_lv.get('name','—')} · "
                    f"{_lv.get('sector','—')} · "
                    f"mcap {_lv.get('mktcap')} · "
                    f"revG {_lv.get('rev_growth')} · "
                    f"GM {_lv.get('gross_margins')} · "
                    f"fwdPE {_lv.get('fwd_pe')}")
            else:
                st.info("no stored flag or live profile")
        _r = st.session_state.get("lk_ref")
        if _r and _r.get("symbol") == _sym:
            st.caption(f"refreshed → `{_r.get('state')}` "
                       f"({_r.get('bars')} bars, {_r.get('as_of')})")

try:
    board = client.get("api/v1/board/daily") or {}
except Exception as e:
    st.error(f"Board unavailable: {e} — the worker may still be "
             "restarting after a deploy; wait ~60s and hit Refresh.")
    if st.button("↻ Retry"):
        st.rerun()
    board = {}

# --- posture banner -----------------------------------------------------------
p = board.get("posture") or {}
if p:
    stance = p.get("stance") or "?"
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Stance", f"{_STANCE_I.get(stance, '⚪')} {stance}")
    c2.metric("VIX", f"{p['vix']:.1f}" if p.get("vix") else "n/a",
              delta="rising" if p.get("vix_rising") else "calm")
    c3.metric("SPY vs 200dma",
              f"{p['spy_vs_200'] * 100:+.1f}%" if p.get("spy_vs_200")
              is not None else "n/a",
              delta=(f"{p['spy_5d'] * 100:+.1f}% wk" if p.get("spy_5d")
                     is not None else None))
    c4.metric("Size multiplier",
              f"{p['size_multiplier']:g}×" if p.get("size_multiplier")
              is not None else "n/a")
    c5.metric("Tranche ≈", f"${board.get('suggested_tranche', 0):,.0f}",
              help="2% of equity × size multiplier — per-idea risk budget")

    # macro event-day judge — the bounded green/red/choppy read,
    # journaled + graded; advisory overlay on the regime card
    _ed = p.get("event_day") or {}
    if _ed.get("verdict"):
        _ev_i = {"green": "🟢", "red": "🔴", "choppy": "⚪"}.get(
            _ed["verdict"], "⚪")
        _rec = _ed.get("record") or {}
        _trk = (f" · {_ed['event_kind']} judge {_rec['hits']}/"
                f"{_rec['graded']} graded ({_rec['hit_rate'] * 100:.0f}%)"
                if _rec.get("graded") else " · track record accruing")
        _pm = (f" · premarket {_ed['premarket_spy']:+.1%}"
               if _ed.get("premarket_spy") is not None else "")
        st.markdown(
            f"**🗓️ {_ed.get('event_name', 'Macro event')}** — judge: "
            f"{_ev_i} **{_ed['verdict'].upper()} day** "
            f"({_ed.get('confidence', '—')}% conf){_pm} "
            f"· `{_ed.get('judge', '—')}`{_trk}")
        _pb = _ed.get("probs") or {}
        if isinstance(_pb, str):
            try:
                import json as _json
                _pb = _json.loads(_pb)
            except Exception:
                _pb = {}
        if _pb:
            st.caption(
                f"p: 🟢{_pb.get('p_green','—')} · "
                f"🔴{_pb.get('p_red','—')} · "
                f"⚪{_pb.get('p_choppy','—')}   ·   regime read: "
                f"`{_ed.get('regime_read') or '—'}`")
        _ql = _ed.get("qqq_lean")
        if _ql:
            _qi = {"up": "🟢", "down": "🔴", "flat": "⚪"}.get(_ql, "⚪")
            st.caption(f"▸ Nasdaq: {_qi} `{_ql}` — "
                       f"{_ed.get('qqq_note') or ''}")
        if _ed.get("thesis"):
            st.caption(f"▸ {_ed['thesis']}")
        # flag when the event judge's day call cuts against the
        # engine's regime — divergence is information, not a bug
        _mr_v = ((p.get("morning") or {}).get("verdict") or {})
        _mr_r = (p.get("morning") or {}).get("regime")
        _bearish_ev = _ed["verdict"] == "red"
        _bullish_rg = _mr_r in ("strong_risk_on", "risk_on")
        _bearish_rg = _mr_r in ("risk_off", "stress")
        if _mr_r and ((_bearish_ev and _bullish_rg) or
                      (_ed["verdict"] == "green" and _bearish_rg)):
            st.caption(
                f"⚠️ event judge `{_ed['verdict']}` vs regime "
                f"`{_mr_r}` — dissenting call, journaled for grading")

    # regime details + the scheduled macro dates that can flip it
    _rd = p.get("regime_detail") or {}
    try:
        _mev = (client.get("api/v1/board/macro-events") or {}) \
            .get("events") or []
    except Exception:
        _mev = []
    if _rd or _mev:
        try:
            _rd_d = date.fromisoformat(str(p.get("as_of"))[:10])
        except Exception:
            _rd_d = date.today()
        with st.expander(f"🌐 Market regime — {_rd_d:%B} {_rd_d.day}, "
                         f"{_rd_d:%Y} — what the posture sees, and the "
                         f"dates that can flip it",
                         expanded=False):
            # --- morning regime: the daily engine's dashboard -------
            _mr = p.get("morning") or {}
            if _mr.get("regime"):
                _rg = _mr["regime"]
                _rc_i = {"strong_risk_on": "🟢🟢", "risk_on": "🟢",
                         "neutral": "⚪", "risk_off": "🔴",
                         "stress": "🔴🔴"}.get(_rg, "⚪")
                _vd = _mr.get("verdict") or {}
                _conf = _vd.get("confirmation")
                _evr = _vd.get("event_risk")
                st.markdown(
                    f"**🌅 Morning regime** — {_rc_i} "
                    f"**{_rg.replace('_', ' ').upper()}** "
                    f"({_mr.get('score', '—')}/100 · "
                    f"{_mr.get('confidence', '—')} conf)   ·   "
                    f"AI sleeve: `{_mr.get('ai_regime') or '—'}`")
                # today's catalyst — status banner (pending or printed)
                for _te in (e for e in _mev if e.get("days_away") == 0):
                    try:
                        if _te.get("actual") is not None:
                            _tmsg = (f"printed {float(_te['actual']):g}"
                                     + (f" vs est {float(_te['estimate']):g}"
                                        if _te.get('estimate') is not None
                                        else "")
                                     + (f" — {_te['reading']}"
                                        if _te.get('reading') else ""))
                        else:
                            _tmsg = ((f"{_te['time_et']} ET"
                                      if _te.get("time_et") else "today")
                                     + (f" · est {float(_te['estimate']):g}"
                                        if _te.get('estimate') is not None
                                        else "")
                                     + (f" · prior {float(_te['prev']):g}"
                                        if _te.get('prev') is not None
                                        else "")
                                     + " — release pending")
                    except (TypeError, ValueError):
                        _tmsg = "today — release pending"
                    st.markdown(f":orange[⚡ **{_te['name']}** — {_tmsg}]")
                if _conf or _evr:
                    _cf_i = {"high": "🟢", "mixed": "🟡",
                             "low": "🔴"}.get(_conf, "⚪")
                    st.caption(
                        f"cross-asset confirmation {_cf_i} "
                        f"**{_conf or '—'}** · event risk "
                        f"`{_evr or '—'}` · data "
                        f"`{_vd.get('data_quality') or '—'}`"
                        + (" · ⚠️ STRESS DIVERGENCE — score capped"
                           if (_mr.get('buckets') or {}).get(
                               '_divergent') else ""))
                _rls = _vd.get("rules") or {}
                if _rls:
                    st.caption(
                        f"rules → core `{_rls.get('core','—')}` · "
                        f"AI `{_rls.get('ai','—')}` · "
                        f"LEAPS `{_rls.get('leaps','—')}` · "
                        f"hedge `{_rls.get('hedge','—')}` · "
                        f"cash `{_rls.get('cash','—')}`")
                if _vd.get("plain"):
                    st.markdown(
                        f"> 💬 {_vd['plain']}")
                # horizon scenarios — 1m + 3m trees with triggers
                for _hz, _lbl in (("horizon_1m", "📅 this month"),
                                  ("horizon_3m", "🔭 next 3 months")):
                    _h = _mr.get(_hz) or {}
                    if not isinstance(_h, dict) or not _h.get("base"):
                        continue
                    _hb = _h.get("base")
                    _hi = {"strong_risk_on": "🟢🟢", "risk_on": "🟢",
                           "neutral": "⚪", "risk_off": "🔴",
                           "stress": "🔴🔴"}.get(_hb, "⚪")
                    st.caption(
                        f"{_lbl}: {_hi} **{_hb.replace('_',' ')}**"
                        + (f" · bull→{_h['bull']}" if _h.get('bull') else "")
                        + (f" · bear→{_h['bear']}" if _h.get('bear') else "")
                        + (f" · risk: {_h['key_risk']}"
                           if _h.get('key_risk') else "")
                        + (f" · catalyst: {_h['key_catalyst']}"
                           if _h.get('key_catalyst') else ""))
                    _tr = (_h.get("triggers") or {})
                    _tt = []
                    for _tk in ("to_bull", "to_bear", "to_stress"):
                        for _t in (_tr.get(_tk) or [])[:1]:
                            _tt.append(f"{_tk}: {_t}")
                    if _tt:
                        st.caption("   triggers ▸ " + " · ".join(_tt))
                _bkts = _mr.get("buckets") or {}
                if isinstance(_bkts, dict):
                    _cells = []
                    # canonical dims (new engine) with legacy names as
                    # fallback for pre-consolidation rows
                    for _bn in ("trend", "momentum", "breadth",
                                "volatility", "participation", "macro",
                                "structure",
                                "growth", "inflation", "liquidity",
                                "credit", "dollar"):
                        _s = (_bkts.get(_bn) or {}).get("score") \
                            if isinstance(_bkts.get(_bn), dict) else None
                        if _s is not None:
                            _ic = ("🟢" if _s >= 60 else
                                   "🔴" if _s <= 40 else "🟡")
                            _cells.append(f"{_bn} {_ic} {_s}")
                    if _cells:
                        st.caption(" · ".join(_cells))
                # "what changed" — the transition layer, not the level
                _chg = (_vd.get("changes") or [])
                if _chg:
                    st.caption("**Δ today:** " + " · ".join(_chg[:6]))
                # structural strip — the slow monitors' current read
                _sx = (_bkts.get("structural") or {}) \
                    if isinstance(_bkts, dict) else {}
                _cx = _sx.get("capex") or {}
                if _cx.get("band"):
                    _al = {"watch": "🟡 WATCH", "prepare": "🟠 PREPARE",
                           "act": "🔴 ACT", "confirmed": "⛔ CONFIRMED"
                           }.get(_cx.get("alert"), "")
                    _fm = _sx.get("macro") or {}
                    _lg = _sx.get("language") or {}
                    st.caption(
                        f"🏗️ **structural:** capex "
                        f"**{_cx.get('score','—')} "
                        f"{_cx.get('band','—').replace('_',' ')}** "
                        f"{_al}"
                        + (f" · Δ3m {_cx['d3m']:+.0f}"
                           if _cx.get("d3m") is not None else "")
                        + (f" · FRED {_fm['overall']:.0f}/100"
                           if _fm.get("overall") is not None else
                           " · FRED —")
                        + (f" · language {_lg.get('scored_quarters')}"
                           f"q scored"
                           if _lg.get("scored_quarters") else ""))
                _lm = _mr.get("llm") or {}
                if isinstance(_lm, str):
                    try:
                        import json as _json
                        _lm = _json.loads(_lm)
                    except Exception:
                        _lm = {}
                for _d in (_lm.get("drivers") or [])[:3]:
                    st.caption(f"· {_d.get('observation','')}")
                for _c in (_lm.get("contradictions") or [])[:2]:
                    st.caption(f"⚠️ {_c.get('observation','')}")
                if _lm.get("invalidations"):
                    st.caption("invalidations: " + " · ".join(
                        str(i) for i in _lm["invalidations"]))
            if _rd:
                _r1, _r2, _r3 = st.columns(3)
                _r1.markdown(
                    f"**{_rd.get('condition','—')} · "
                    f"{_rd.get('direction','—')}** · conf "
                    f"{_rd.get('confidence','—')}")
                _r2.markdown(
                    f"stage `{_rd.get('transition_stage','—')}` · "
                    f"risk `{_rd.get('risk_level','—')}`")
                _r3.markdown(
                    f"dip-buying `{_rd.get('dip_buying_environment','—')}`"
                    + (f" · transition {_rd['bullish_transition_score']:.0f}"
                       if isinstance(_rd.get('bullish_transition_score'),
                                     (int, float)) else ""))
                for d in (_rd.get("key_drivers") or [])[:5]:
                    st.caption(f"· {d}")
                _sp = _rd.get("strategies_preferred") or []
                if _sp:
                    st.caption("preferred: " + " · ".join(
                        str(s) for s in _sp[:4]))
            _brx = p.get("breadth") or {}
            if _brx:
                st.markdown("**📊 Universe internals** — our own breadth")
                st.caption(
                    f"{_brx.get('pct_above_50','—')}% above 50dma · "
                    f"{_brx.get('pct_up_5d','—')}% up 5d · "
                    f"{_brx.get('pct_20d_high','—')}% at 20dH / "
                    f"{_brx.get('pct_20d_low','—')}% at 20dL · "
                    f"HL {_brx.get('pct_hl_confirmed','—')}% confirmed / "
                    f"{_brx.get('pct_hl_broken','—')}% broken — "
                    f"breadth score **{_brx.get('breadth_score','—')}**")
            _bk = p.get("book_risk") or {}
            if _bk.get("positions"):
                _wrn = _bk.get("warnings") or []
                st.markdown("**📒 Book risk**"
                            + (" — ⚠️ " + " · ".join(_wrn) if _wrn else ""))
                st.caption(
                    f"beta {_bk.get('book_beta','—')} · "
                    f"top sector {_bk.get('top_sector','—')} "
                    f"{_bk.get('top_sector_pct','—')}%")
            _fw = p.get("forward") or {}
            if _fw:
                st.markdown("**🔮 Forward ~20 sessions** — evidence-"
                            "weighted, not a crystal ball")
                _f1, _f2, _f3 = st.columns(3)
                _f1.metric("deeper dip", f"{_fw.get('p_deeper_dip_20d','—')}%")
                _f2.metric("chop", f"{_fw.get('p_chop_20d','—')}%")
                _f3.metric("bullish res.", f"{_fw.get('p_bullish_20d','—')}%")
                st.caption(
                    f"lead: **{_fw.get('lead_scenario','—')}** · conf "
                    f"{_fw.get('confidence','—')} — "
                    + " · ".join(_fw.get("drivers") or [])[:220])
            # --- dip character: IF a dip comes, does AI infra drag? --
            _dc = p.get("dip_character") or {}
            if _dc:
                _ch = _dc.get("character") or "—"
                _ic = {"no_dip": "🟢", "sympathetic": "🟡",
                       "narrow_leadership": "🏰",
                       "rotation_out_of_ai": "🩸",
                       "broad_deleveraging": "🔴",
                       "idiosyncratic_ai": "🧠"}.get(_ch, "⚪")
                _lbl = _ch.replace("_", " ")
                st.markdown(f"**🧭 Dip character** — {_ic} `{_lbl}`")
                st.caption(_dc.get("read") or "")
                _met = []
                if _dc.get("ai_rs20") is not None:
                    _met.append(f"AI RS {_dc['ai_rs20'] * 100:+.1f}pts")
                if _dc.get("corr_vs_baseline") is not None:
                    _met.append(f"corr {_dc['corr_smh_spy_20d']:.2f} "
                                f"({_dc['corr_vs_baseline']:+.2f})")
                if _dc.get("defensive_bid_5d") is not None:
                    _met.append(f"defensives "
                                f"{_dc['defensive_bid_5d'] * 100:+.1f}%")
                if _met:
                    st.caption(" · ".join(_met))
                if _dc.get("action"):
                    st.caption(f"▸ {_dc['action']}")
            # --- allocation: cash buffer + where money rotates ------
            _al = p.get("allocation") or {}
            if _al:
                _cb = _al.get("cash_buffer_pct") or 0
                _a1, _a2 = st.columns(2)
                _a1.markdown(
                    f"**💵 Cash buffer** — stage **{_cb}%**"
                    + ("  (deploy on triggers, never all-at-once)"
                       if _cb else "  (nothing staged)"))
                if _al.get("within_ai"):
                    _a2.caption("within AI: " + _al["within_ai"])
                for w in (_al.get("cash_why") or [])[:3]:
                    st.caption(f"· {w}")
                _rt, _ra = _al.get("rotate_to") or [], \
                    _al.get("rotate_away") or []
                _rc = set(_al.get("rotate_confirmed") or [])
                if _rt or _ra:
                    _rt_s = ", ".join(
                        f"**{s}**" if s in _rc else f"{s}·"
                        for s in _rt)
                    st.caption(
                        (f"rotating in: {_rt_s}  " if _rt else "")
                        + (f"· leaving: {', '.join(_ra)}" if _ra
                           else ""))
                if _al.get("rotate_note"):
                    st.caption(f"· {_al['rotate_note']}")
                if _al.get("redeploy_when"):
                    with st.expander("redeploy triggers"):
                        for t in _al["redeploy_when"]:
                            st.caption(f"▸ {t}")
                _rows = _al.get("sector_rows") or []
                if _rows:
                    with st.expander("sector flow board"):
                        _top = [r for r in _rows
                                if r["flow"] != "quiet"][:10]
                        for r in _top:
                            _fi = {"inflow": "🔥", "rotating_in": "↩",
                                   "outflow": "📉"}.get(r["flow"], "·")
                            _mf = ""
                            if r.get("money5") is not None:
                                _mf = (f" · vol {'↑' if r['money5'] > 0 else '↓'}"
                                       f"{abs(r['money5']):.0%}")
                                if r.get("vol_ratio"):
                                    _mf += f" @{r['vol_ratio']:.1f}×"
                                if r.get("vol_confirmed"):
                                    _mf += " ✓"
                            st.caption(
                                f"{_fi} **{r['etf']}** {r['name']} — "
                                f"{r['ret5'] * 100:+.1f}%/5d · "
                                f"{r['vs_spy20'] * 100:+.1f}pts vs SPY"
                                f"{_mf}")
            # --- hedge book — the insurance card ---------------------
            _hb = p.get("hedge") or {}
            if _hb:
                _gap = _hb.get("coverage_gap") or 0
                _tier = _hb.get("tier") or "—"
                _tic = {"calm": "🟢", "watch": "🟡",
                        "elevated": "🟠", "fat_tail": "🔴"}.get(
                    _tier, "⚪")
                st.markdown(
                    f"**🛡 Hedge** — {_tic} `{_tier}` · coverage "
                    f"**{_hb.get('coverage_now_pct', 0)}%** of "
                    f"beta-adj book · target "
                    f"{_hb.get('coverage_target_pct', 0)}%"
                    + (f" — **gap ${_gap:,.0f}**" if _gap else ""))
                st.caption(
                    f"book ${_hb.get('book_value', 0):,.0f} × beta "
                    f"{_hb.get('book_beta', 1)} = "
                    f"${_hb.get('exposure_beta_adj', 0):,.0f} exposure · "
                    f"spent ${_hb.get('spent_ytd', 0):,.0f} of "
                    f"${_hb.get('budget_cap_usd', 0):,.0f} "
                    f"({_hb.get('budget_cap_pct', 0)}% cap)")
                st.caption(f"· {_hb.get('regime_note', '')}")
                for h in (_hb.get("open") or []):
                    _vp = (f" · value {h['value_pct']:.0f}% of width"
                           if h.get("value_pct") is not None else "")
                    st.caption(
                        f"▸ {h['underlier']} {h['long']:.0f}/"
                        f"{h['short']:.0f} put spread ×{h['qty']} "
                        f"exp {h['expiry']} · cost "
                        f"${h['cost']:,.0f}{_vp}")
                if _gap and st.button("📐 Structure the next tranche",
                                      key="hb_suggest"):
                    _sg = client.get("api/v1/board/hedge/suggest") or {}
                    st.caption(
                        f"suggested: buy {_sg.get('qty_for_gap')}× "
                        f"{_sg.get('underlier')} "
                        f"{_sg.get('long_put')}/{_sg.get('short_put')} "
                        f"put spread, {_sg.get('dte_window')} — "
                        f"{_sg.get('note', '')[:110]}")
            # --- crash alpha — PUT entry + capitulation + rotation ---
            _ca = p.get("crash_alpha") or {}
            if _ca:
                _cap = _ca.get("capitulation") or {}
                _cs = _cap.get("score") or 0
                _ct = _cap.get("tier") or "none"
                _cic = {"none": "🟢", "watch": "🟡", "cap_zone": "🟠",
                        "capitulating": "🔴"}.get(_ct, "⚪")
                st.markdown(
                    f"**💥 Crash alpha** — {_cic} capitulation "
                    f"**{_cs}/100** `{_ct}`"
                    + (f" · VIX {_cap['vix']:.0f}"
                       if _cap.get("vix") else ""))
                if _cap.get("why"):
                    st.caption(" · ".join(_cap["why"][:4]))
                _pc = _ca.get("put_candidates") or []
                if _pc:
                    st.caption("**put-spread candidates** (extended "
                               "quality — rotates to CALLs later):")
                    for c in _pc[:4]:
                        st.caption(
                            f"▸ **{sym_md(c['symbol'])}** {c['score']:.0f}"
                            f"{' · 🔄 rotatable' if c.get('rotatable') else ''}"
                            f" — {c['why'][:95]}")
                _ivg = _ca.get("iv_gate") or {}
                if _ivg.get("status") == "insufficient history":
                    st.caption(f"⏳ IV pricing gate: {_ivg.get('note')}")
                elif _ivg.get("iv_rank") is not None:
                    st.caption(f"IV rank {_ivg['iv_rank']} — "
                               f"{_ivg.get('verdict', '')}")
                _rd = _ca.get("redeploy") or {}
                if _rd.get("armed") and _rd.get("candidates"):
                    st.caption(
                        f"**🔄 PUT→CALL armed** — proceeds "
                        f"~${_rd.get('proceeds_est', 0):,.0f}; "
                        f"redeploy into:")
                    for c in _rd["candidates"][:5]:
                        st.caption(
                            f"▸ **{sym_md(c['symbol'])}** "
                            f"{c['alloc_pct']}% (~${c['alloc_usd']:,}) "
                            f"· dd {c['dd52w']:.0f}% · {c['dip_phase']}")
            _gc = p.get("geo") or {}
            if _gc:
                _fl = (_gc.get("defensive") or {})
                _legs = " · ".join(
                    f"{l['etf']}{'🔥' if l.get('hot') else ''}"
                    f"{l['rs_5d']:+.1f}%"
                    for l in (_fl.get("legs") or [])[:5])
                st.markdown(
                    f"**🌍 Global risk** — geo-risk "
                    f"**{_gc.get('geo_risk','—')}/100** · defensive flows: "
                    f"`{_fl.get('flow','—')}`")
                if _legs:
                    st.caption(f"defensive RS 5d vs SPY: {_legs}")
                for h in (_gc.get("drivers") or [])[:3]:
                    st.caption(f"· {h}")
            # --- causal map: where the world is → the propagation ----
            _cm = (_gc.get("causal") or {})
            if _cm:
                _ws = {"calm": "🕊 calm", "war_ongoing": "⚔️ war ongoing",
                       "escalating": "🔥 escalating",
                       "de_escalating": "🕊 de-escalating",
                       "trade_war": "🚢 trade war"}.get(
                    _cm.get("world_state"), _cm.get("world_state") or "—")
                st.markdown(f"**🗺 Causal map** — world state: `{_ws}`")
                if not _cm.get("chains") and not _cm.get("watching"):
                    st.caption("no active event chains — calm tape is a "
                               "valid state")
                for c in _cm.get("chains") or []:
                    with st.expander(
                            f"🔴 {c['title']} — conf {c['conf']}% "
                            f"({c['fired_by']})", expanded=False):
                        for i, s in enumerate(c["steps"], 1):
                            _bi = s.get("book_impact") or {}
                            _bis = (" → book: " + " · ".join(
                                f"{k} {v}" for k, v in _bi.items())
                                ) if _bi else ""
                            st.caption(
                                f"{i}. {s['driver']} → {s['market']} · "
                                f"{s['assets']} (conf {s['conf']}%){_bis}")
                        st.caption(f"watch: {c['watch_for']}")
                        st.caption(f"dies if: {c['watch_against']}")
                for c in _cm.get("watching") or []:
                    with st.expander(
                            f"⚪ {c['title']} — watching "
                            f"({c['fired_by']})", expanded=False):
                        for i, s in enumerate(c["steps"], 1):
                            _bi = s.get("book_impact") or {}
                            _bis = (" → book: " + " · ".join(
                                f"{k} {v}" for k, v in _bi.items())
                                ) if _bi else ""
                            st.caption(
                                f"{i}. {s['driver']} → {s['market']} · "
                                f"{s['assets']} (conf {s['conf']}%){_bis}")
                        st.caption(f"watch: {c['watch_for']}")
                        st.caption(f"dies if: {c['watch_against']}")
            # --- AI capex-cycle engine -------------------------------
            _cx = (p.get("capex") or {})
            if _cx.get("score") is not None:
                _d3, _d6 = _cx.get("d3m"), _cx.get("d6m")
                _trend = (f" Δ3m {_d3:+} Δ6m {_d6:+}"
                          if _d3 is not None else "")
                _fl = " · ".join(_cx.get("flags") or [])
                st.markdown(
                    f"**🏗 AI capex engine** — `{_cx['score']}/100` "
                    f"**{_cx.get('band','—')}**{_trend}"
                    + (f" · `{_fl}`" if _fl else ""))
                st.caption("bands: 0-25 expansion · 25-50 normalization "
                           "· 50-70 slowing · 70-85 serious · "
                           "85+ contraction — allocation dial, not a "
                           "sell signal")
                _comps = _cx.get("components") or {}
                _cl = " · ".join(
                    f"{k} {(v or {}).get('score','—')}"
                    for k, v in _comps.items())
                st.caption(f"components: {_cl} · elevated: "
                           f"{_cx.get('n_elevated',0)}/7")
                _rot = _cx.get("rotation") or {}
                if _rot.get("rotation_spread") is not None:
                    st.caption(
                        f"63d RS — new-build {_rot['new_build_rs_63d']}% "
                        f"vs operators {_rot['operator_rs_63d']}% · "
                        f"rotation {_rot['rotation_spread']:+}%")
                _g = _cx.get("guidance") or {}
                if _g.get("meaning"):
                    st.caption(f"ℹ️ {_g['meaning']}")
                    for _a in _g.get("actions") or []:
                        st.caption(f"▸ {_a}")
                    for _w in _g.get("watch") or []:
                        st.caption(f"👁 {_w}")
                with st.expander("component detail", expanded=False):
                    for k, v in _comps.items():
                        st.caption(
                            f"**{k}** {v.get('score')} — {v.get('kind')}")
                        for drow in (v.get("detail") or [])[:8] \
                                if isinstance(v.get("detail"), list) \
                                else []:
                            st.caption(f"   {drow}")
                st.caption(f"_{_cx.get('note','')}_")
            if _mev:
                st.markdown("**📅 Macro calendar**")
                for e in _mev[:8]:
                    _tag = ("**today**" if e["days_away"] == 0 else
                            "**tomorrow**" if e["days_away"] == 1 else
                            f"in {e['days_away']}d")
                    _mv = (f" 🔀 moved from `{e['rescheduled_from']}`"
                           if e.get("rescheduled") else "")
                    st.caption(
                        f"`{e['date']}` {e['name']} {_tag}"
                        + (" ⚠️" if e["severity"] == "extreme" else "")
                        + (" *(est)*" if e.get("est") else "")
                        + (" *(unconfirmed)*" if e.get("unconfirmed") else "")
                        + _mv)

# --- 🎯 today's swing calls — the distilled top-3 with plans ------------------
try:
    _cdata = client.get("api/v1/board/calls") or {}
    _calls = _cdata.get("calls") or []
    _rec = _cdata.get("record") or {}
    _rc = []
    if _rec.get("tgt") is not None and (_rec.get("tgt") or 0) \
            + (_rec.get("stp") or 0) + (_rec.get("exp") or 0) > 0:
        _rc.append(f"🎯 {_rec['tgt']} hit target first")
        _rc.append(f"🛑 {_rec['stp']} stopped out")
        if _rec.get("exp"):
            _rc.append(f"⏳ {_rec['exp']} expired")
        if _rec.get("open"):
            _rc.append(f"{_rec['open']} still open")
        if _rec.get("avg_held") is not None:
            _rc.append(f"avg {_rec['avg_held']}d to resolve")
    if _rc:
        st.caption("**calls track record** — " + " · ".join(_rc)
                   + " (plan-level: did stop or target hit first)")
    _cpo = _cdata.get("posture") or {}
    _blocked = bool(_cpo.get("posture")) and not _cpo.get("new_longs")
    _today = [c for c in _calls
              if c["call_date"] == str(date.today())]
    if not _today and not _blocked:
        _today = _calls[:3]                     # latest batch as fallback
    if _today:
        _d = _today[0]["call_date"]
        _stale = _d != str(date.today())
        with st.expander(
                f"🎯 {'Latest' if _stale else 'Today'} swing calls "
                f"({_d}) — top {len(_today)} with plans"
                + (" — next batch tonight" if _stale else ""),
                expanded=True):
            for c in _today:
                _e = " · ".join(c.get("evidence") or [])
                st.markdown(
                    f"**#{c['rank']} {sym_md(c['symbol'])}** — "
                    f"`{c.get('state') or '—'}`"
                    + (f" · dip `{c['dip_phase']}`" if c.get('dip_phase')
                       else "")
                    + (f" · rank **{c['swing_rank']}**"
                       if c.get('swing_rank') is not None else "")
                    + f" · score **{c['score']}**")
                st.caption(
                    f"entry ~**${c['entry_px']:,.2f}** · "
                    f"stop ${c['stop_px']:,.2f} · "
                    f"target ${c['target_px']:,.2f} · "
                    f"R:R {c['rr']:.1f} — {_e[:180]}")
            st.caption("journaled in `daily_calls` → resolved as "
                       "target/stop first-touch in `daily_call_outcomes` "
                       "· the meta job learns plan params from it · "
                       "advisory only")
    else:
        if _blocked:
            st.info(f"🟡 **no calls today** — posture "
                    f"`{_cpo['posture']}` blocked new longs "
                    f"(`{_cpo.get('matched')}`)")
        else:
            st.caption("no qualified setup today — no-trade is a "
                       "valid call")
except Exception:
    pass

# --- � today's put calls — short-side distilled picks ----------------
try:
    _pdata = client.get("api/v1/board/put-calls") or {}
    _pcs = _pdata.get("calls") or []
    _prec = _pdata.get("record") or {}
    _ppo = _pdata.get("posture") or {}
    _prc = []
    if _prec.get("tgt") is not None and (_prec.get("tgt") or 0) \
            + (_prec.get("stp") or 0) + (_prec.get("exp") or 0) > 0:
        _prc.append(f"🎯 {_prec['tgt']} hit target first")
        _prc.append(f"🛑 {_prec['stp']} stopped out")
        if _prec.get("exp"):
            _prc.append(f"⏳ {_prec['exp']} expired")
        if _prec.get("open"):
            _prc.append(f"{_prec['open']} still open")
        if _prec.get("avg_held") is not None:
            _prc.append(f"avg {_prec['avg_held']}d to resolve")
    _ptoday = [c for c in _pcs
               if c["call_date"] == str(date.today())]
    if not _ptoday and _ppo.get("shorts"):
        _ptoday = _pcs[:3]                    # latest batch as fallback
    if _ptoday:
        _d = _ptoday[0]["call_date"]
        _stale = _d != str(date.today())
        with st.expander(
                f"🔻 {'Latest' if _stale else 'Today'} put calls "
                f"({_d}) — top {len(_ptoday)} leap_put-ready shorts"
                + (" — next batch tonight" if _stale else ""),
                expanded=bool(_ppo.get("shorts"))):
            for c in _ptoday:
                _e = " · ".join(c.get("evidence") or [])
                st.markdown(
                    f"**#{c['rank']} {sym_md(c['symbol'])}** — "
                    f"`{c.get('state') or '—'}`"
                    + f" · put score **{c['score']}**")
                st.caption(
                    f"thesis: drop toward **${c['target_px']:,.2f}** · "
                    f"invalidated above ${c['stop_px']:,.2f} · "
                    f"entry ~${c['entry_px']:,.2f} · "
                    f"R:R {c['rr']:.1f} — {_e[:180]}")
            if _prc:
                st.caption("**put track record** — " + " · ".join(_prc))
            st.caption("from the `leap_put`-ready board (put_entry "
                       "score ≥ 60) → journaled in `daily_puts` → "
                       "graded stop-vs-target first-touch in "
                       "`daily_put_outcomes` · advisory only")
    elif _ppo.get("posture") and not _ppo.get("shorts"):
        st.caption(f"🔻 put calls off today — posture "
                   f"`{_ppo['posture']}` doesn't permit shorts "
                   f"(`{_ppo.get('matched')}`)")
except Exception:
    pass

# --- �🛡️ portfolio defense & recovery — regime-scaled insurance card ---
try:
    _def = client.get("api/v1/board/defense") or {}
    _ds = _def.get("defensive_state") or "NORMAL"
    _h = _def.get("hedge") or {}
    _rec = _def.get("recovery") or {}
    _ds_i = {"NORMAL": "🟢", "WATCH": "🟡", "HEDGE": "🟠",
             "DEFENSIVE": "🔴", "CAPITULATION": "🔴🔴",
             "RECOVERY": "🔄"}.get(_ds, "⚪")
    _iv = _def.get("iv_gate") or {}
    _rot = _def.get("theme_rotation") or {}
    _rot_s = _rot.get("score")
    _rot_b = _rot.get("band")
    _n_put = len(_def.get("bear_alpha_candidates") or [])
    with st.expander(
            f"🛡️ Portfolio defense — {_ds_i} **{_ds}** "
            f"(score {_def.get('defensive_score', '—')}/100"
            + (f" · {_def.get('defensive_streak')}d streak"
               if _def.get('defensive_streak') else "")
            + f") · AI-rotation **{_rot_s if _rot_s is not None else '—'}"
              f"/100 `{_rot_b or '—'}`**"
            + (f" · {_n_put} bear-alpha" if _n_put else "")
            + f" · hedge `{_h.get('tier','—')}` "
              f"{_h.get('coverage_target_pct','—')}% target",
            expanded=(_ds not in ("NORMAL",)
                      or (_rot_s or 0) >= 60)):
        if _def.get("defensive_reasons"):
            st.caption(" · ".join(_def["defensive_reasons"][:4]))
        st.caption(
            f"hedge: `{_h.get('tier','—')}` tier — "
            f"cover {_h.get('coverage_now_pct',0)}% of "
            f"${(_h.get('exposure_beta_adj') or 0)/1e6:,.1f}M "
            f"beta-adj book (target "
            f"{_h.get('coverage_target_pct','—')}%, gap "
            f"${(_h.get('coverage_gap') or 0)/1e6:,.1f}M) · "
            f"spent YTD ${(_h.get('spent_ytd') or 0)/1000:,.1f}K "
            f"of ${(_h.get('budget_cap_usd') or 0)/1000:,.1f}K cap · "
            f"source `{_h.get('target_source') or '—'}`")
        st.caption(
            f"IV gate: `{_iv.get('status','—')}`"
            + (f" rank {_iv.get('iv_rank')} — {_iv.get('verdict')}"
               if _iv.get("iv_rank") is not None else
               f" — {_iv.get('note','')}"[:80])
            + f" · capitulation {_def.get('capitulation',{}).get('score','—')}/100 "
              f"`{_def.get('capitulation',{}).get('tier','—')}`")
        if (_rec.get("recovery_capital") or 0) > 0:
            st.caption(
                f"🔄 recovery capital **${_rec['recovery_capital']:,.0f}** "
                f"· deployed ${_rec.get('deployed_usd',0):,.0f} · "
                f"stage {_rec.get('stage_available','—')}/3 earned "
                + (f"→ next tranche ${_rec.get('next_tranche_usd',0):,.0f}"
                   if _rec.get("next_stage") else "")
                + (" · ⛔ frozen — bearish state" if _rec.get("frozen")
                   else ""))
        for _c in (_def.get("bear_alpha_candidates") or [])[:3]:
            st.caption(
                f"🐻 {sym_md(_c['symbol'])} {_c['score']} `{_c['band']}` "
                f"{_c.get('category','')} — {_c.get('why','')[:120]}")
        st.caption("insurance = Engine A (index spreads, journaled) · "
                   "bear alpha = Engine B (gated puts) · recovery = "
                   "staged redeploy of realized hedge P&L · "
                   "advisory only")
except Exception:
    pass

# --- ⚡ HL triggers — higher-low confirmations at the line ----------------------
try:
    _hl = client.get("api/v1/board/hl-triggers") or {}
    _conf = _hl.get("confirmed") or []
    _trg = _hl.get("triggers") or []
    if _conf or _trg:
        with st.expander(f"⚡ Higher-low triggers — {len(_conf)} confirmed · "
                         f"{len(_trg)} within 3% of the break",
                         expanded=True):
            if _conf:
                st.markdown("**✅ confirmed — pullback structure proven**")
                for t in _conf[:8]:
                    st.markdown(
                        f"**{sym_md(t['symbol'])}** `{t.get('momentum')}` "
                        f"· {t.get('fund_state') or '—'} — "
                        f"px ${t['px']:,.2f} cleared "
                        f">${t['confirm_level']:,.2f} · low "
                        f"${t['swing_low']:,.2f} > "
                        f"${t['prior_low']:,.2f}")
            if _trg:
                st.markdown("**⏳ one close away — trigger = close > "
                            "the pullback's swing high**")
                _rows = [{"symbol": t["symbol"], "px": t["px"],
                          "trigger >": t["confirm_level"],
                          "away": f"{t['dist_pct']:+.1f}%",
                          "low > prior": f"{t['swing_low']:,.0f} > "
                                         f"{t['prior_low']:,.0f}",
                          "dip vol": (f"{t['vol_pullback_vs_rally']}×"
                                      if t.get("vol_pullback_vs_rally")
                                      else "—"),
                          "tape": t.get("momentum") or "—",
                          "fund": t.get("fund_state") or "—"}
                         for t in _trg[:15]]
                st.dataframe(health_col(pd.DataFrame(_rows)),
                             column_config={"🩺": health_cfg()},
                             hide_index=True, use_container_width=True)
            st.caption("stored swing state — refreshed by the momentum "
                       "job (13:30/21:30 UTC). `dip vol` <1.0 = pullback "
                       "resting on shrinking volume. Advisory: the "
                       "trigger is the *close* above the level, not "
                       "an intraday tag.")
except Exception:
    pass

# --- 🔥 fundamental momentum radar — rapidly improving names ------------------
try:
    _fm = (client.get("api/v1/board/fund-momentum") or {}) \
        .get("items") or []
    if _fm:
        _add = [r for r in _fm if not r["extended"]
                and r["tape"] not in ("knife", "downtrend",
                                      "capitulation", "breakdown",
                                      "rolling_over", "climax")]
        _early = [r for r in _fm if r not in _add]
        with st.expander(f"🔥 Fundamentals rapidly improving — "
                         f"{len(_add)} add-candidates · "
                         f"{len(_early)} early/watchlist",
                         expanded=False):
            for r in _add[:6]:
                st.markdown(
                    f"**{sym_md(r['symbol'])}** · `{r['tape']}`"
                    + (f" · dip `{r['dip_phase']}`" if r.get('dip_phase')
                       else "")
                    + f" — " + "; ".join(r["why"][:3]))
            if _early:
                st.caption("early (fundamentals improving, tape not "
                           "confirming): " + ", ".join(
                               f"{sym_md(r['symbol'])} `{r['tape']}`"
                               for r in _early[:6]))
except Exception:
    pass

# --- 🩺 custodian strip — the support agent's ledger --------------------------
try:
    _inc = client.get("api/v1/board/incidents") or {}
    _open = _inc.get("open") or []
    if _open:
        _esc = [i for i in _open if i.get("status") == "escalated"]
        _mit = [i for i in _open if i.get("status") == "mitigated"]
        _new = [i for i in _open if i.get("status") == "open"]
        with st.expander(
                f"🩺 Custodian — {len(_esc)} escalated · "
                f"{len(_mit)} auto-mitigated · {len(_new)} new",
                expanded=bool(_esc)):
            for i in _open:
                _ic = {"escalated": "🔴", "mitigated": "🟡",
                       "open": "⚪"}.get(i["status"], "⚪")
                st.caption(
                    f"{_ic} `{i['signature']}` ×{i['occurrences']} — "
                    f"{i.get('diagnosis') or '—'} · attempts "
                    f"{i['attempts']}/3"
                    + (f" · {i['remediation']}" if i.get('remediation')
                       else ""))
            _acts = _inc.get("actions") or []
            if _acts:
                st.caption("recent self-fixes: " + " · ".join(
                    f"{a['action']} ({a['result'][:60]})"
                    for a in _acts[:3]))
except Exception:
    pass

# --- 🎯 focus book — developments at conviction names -------------------------
with st.expander("🎯 Focus book — members & scan", expanded=False):
    _fs1, _fs2 = st.columns([3, 1])
    _fs1.caption("Conviction names watched for contracts, design wins, "
                 "roadmap, backlog, analyst moves and SEC filings.")
    if _fs2.button("🔄 Run focus scan", key="fx_scan",
                   use_container_width=True):
        _kick("focus-scan")
    _fs2.markdown(f":red[⏱ {_last('focus-scan')}]")

    try:
        _fmem = client.get("api/v1/board/focus/members") or []
    except Exception:
        _fmem = []
    _pend = st.session_state.get("fx_pending")
    for m in _fmem:
        _sym = m["symbol"]
        r1, r2, r3 = st.columns([1, 5, 2])
        r1.markdown(f"**{sym_md(_sym)}**")
        r2.caption(m.get("thesis") or "—")
        if _pend == _sym:
            r3.warning(f"Remove {_sym}?", icon="⚠️")
            _y, _n = r3.columns(2)
            if _y.button("yes", key=f"fx_yes_{_sym}"):
                try:
                    client.delete(f"api/v1/board/focus/{_sym}")
                    st.toast(f"{_sym} removed from focus book")
                except Exception as e:
                    st.error(f"remove failed: {e}")
                st.session_state.pop("fx_pending", None)
                st.rerun()
            if _n.button("no", key=f"fx_no_{_sym}"):
                st.session_state.pop("fx_pending", None)
                st.rerun()
        elif r3.button("🗑 remove", key=f"fx_rm_{_sym}"):
            st.session_state["fx_pending"] = _sym
            st.rerun()

    _fa, _fb, _fc = st.columns([1, 3, 1])
    _new = _fa.text_input("symbol", key="fx_add_sym",
                          placeholder="NVDA").strip().upper()
    _th = _fb.text_input("thesis (one line)", key="fx_add_th",
                         placeholder="AI GPU franchise — hyperscaler capex")
    if _fc.button("＋ Add", key="fx_add_btn"):
        if _new:
            try:
                client.post(f"api/v1/board/focus/{_new}",
                            params={"thesis": _th} if _th else None)
                st.toast(f"{_new} added — run Focus book scan")
                st.rerun()
            except Exception as e:
                st.error(f"add failed: {e}")
        else:
            st.warning("enter a symbol")

_FOCUS_I = {"contract": "📜", "design_win": "📜", "backlog": "📦",
            "guidance": "📈", "product": "🧪", "partnership": "🤝",
            "capacity": "🏭", "ai_infra": "🤖", "analyst_up": "⬆️",
            "analyst_down": "⬇️", "analyst": "🏦", "pt_raise": "⬆️",
            "pt_cut": "⬇️", "filing_8k": "📄", "holder_13d": "🐋",
            "filing": "📄", "risk": "⚠️", "other": "·"}
for fe in (board.get("focus") or []):
    _mat = fe.get("materiality") or 0
    _heat = "🔥" if _mat >= 5 else ""
    _age = (fe.get("published_at") or "")[:10]
    _line = (f"{_FOCUS_I.get(fe.get('event_type'), '·')} "
             f"**{sym_md(fe['symbol'])}** · "
             f"{fe.get('event_type', '').replace('_', ' ')} "
             f"· mat {_mat} {_heat} · {_age}\n\n{fe.get('title', '')}")
    if _mat >= 5:
        st.warning(_line + (f" — [link]({fe['url']})" if fe.get("url") else ""))
    else:
        st.markdown("> " + _line +
                    (f" — [link]({fe['url']})" if fe.get("url") else ""))
if board.get("focus"):
    st.caption("🎯 Focus book — company developments at conviction names "
               "(contracts, design wins, roadmap, backlog). Materiality "
               "4-5 = thesis-moving; 🔥 = act today.")
    st.caption(f"_{p.get('note')}_"
               + (f" · regime `{p['regime']}`" if p.get("regime") else ""))

# --- the board ----------------------------------------------------------------
items = board.get("items") or []
counts = board.get("counts") or {}
st.subheader(f"{len(items)} actions "
             f"({counts.get('exits', 0)} exits · "
             f"{counts.get('accumulate', 0)} longs · "
             f"{counts.get('puts', 0)} put setups)")
if counts.get("accumulate_ready") or counts.get("accumulate_watch"):
    st.caption(f"longs → ✅ {counts.get('accumulate_ready', 0)} "
               f"buy-eligible now (screener entry gate) · "
               f"⏸️ {counts.get('accumulate_watch', 0)} watch-zone "
               "LEAPS (trend intact, no live entry — zones on card)")
if counts.get("frozen"):
    st.caption(f"❄️ {counts['frozen']} entries FROZEN — execution-freeze "
               "phase: gate passed but the calendar holds fire until "
               "the earnings cluster")
if counts.get("peer_drag"):
    st.caption(f"🎯 {counts['peer_drag']} peer-drag flags — down on a "
               "cluster-mate's print, not their own news; phase-3 "
               "reactive deploy candidates")

# --- 📊 action track record — were the suggestions right? ----------------------
try:
    _trd = (client.get("api/v1/board/track-record") or {})
    _cells = ((_trd.get("instruments") or {}).get("cells")) or []
    _reg = (_trd.get("regime") or {})
    if _cells or (_reg.get("summary") or {}).get("n"):
        _leaps = [c for c in _cells if "LEAPS" in (c["inst"] or "")]
        _stock = [c for c in _cells if "LEAPS" not in (c["inst"] or "")]
        with st.expander("📊 Action track record — journaled picks "
                         "graded at 5/10/20d (LEAPS out to 60d)",
                         expanded=False):
            _rs = _reg.get("summary") or {}
            if _rs.get("n"):
                st.markdown(
                    f"**🔮 Regime calibration** — {_rs['n']} reads "
                    f"journaled, {_rs.get('graded', 0)} graded · "
                    f"lead-scenario hit "
                    f"**{_rs.get('overall_hit') or 0:.0f}%**")
                for c in (_reg.get("cells") or [])[:8]:
                    st.caption(
                        f"lead `{c['lead_scenario']}` when dip-char "
                        f"`{c.get('dip_character') or '—'}` — {c['n']}× · "
                        f"SPY {c['avg_spy_20d']:+.1f}%/20d · "
                        f"hit {c['lead_hit']:.0f}%")
            def _cell_lines(cells):
                for c in cells:
                    st.caption(
                        f"`{c['inst']}` {c['action']} · "
                        f"{c['horizon_days']}d — {c['n']} graded · "
                        f"hit **{c['hit_rate']:.0f}%** · "
                        f"avg {c['avg_ret']:+.1f}%")
            if _leaps:
                st.markdown("**Options / LEAPS**")
                _cell_lines(_leaps)
            if _stock:
                st.markdown("**Stock actions**")
                _cell_lines(_stock)
            st.caption("PUT/EXIT returns are direction-flipped — "
                       "positive = the call paid. Grading accrues "
                       "nightly via the outcomes job.")
except Exception:
    pass

if not items:
    st.info("Nothing actionable today — the discipline IS the position. "
            "Run a swing scan or momentum refresh if this looks stale.")

for it in items:
    icon = _ACT_I.get(it["action"], "⚪")
    mom = it.get("momentum")
    mtxt = f"{_MOM_I.get(mom, '')} `{mom}`" if mom else "`no flag`"
    held = " · `HELD`" if it.get("in_portfolio") else ""
    gain = (f" · {it['gain_pct']:+.0f}%" if it.get("gain_pct") is not None
            else "")
    fstate = it.get("fund_state")
    ftxt = (f" · {_FUND_I.get(fstate, '')} `{fstate}`" if fstate else "")
    _es = {"ready": " · ✅ entry-ready",
           "watch_zone": " · ⏸️ watch-zone",
           "frozen": " · ❄️ FROZEN (freeze phase)",
           "peer_drag": " · 🎯 PEER-DRAG"}.get(it.get("entry_status"), "")
    head = (f"{icon} **{it['action']}** — **{sym_md(it['symbol'])}** · "
            f"{it.get('instrument') or 'stock'}{gain} · {mtxt}{ftxt}{held}"
            f"{_es} · score **{it['score']:.0f}**")
    with st.expander(head, expanded=it["action"] == "EXIT"):
        if it.get("suggestion"):
            st.markdown(f"**Monitor:** {it['suggestion']}")
        for w in it.get("why") or []:
            st.caption(f"· {w}")
        _rk = _FUND_RISK.get(it.get("fund_risk") or "", "")
        _chg = it.get("fund_changes") or []
        if _rk or _chg:
            st.caption(f"fundamentals: {it.get('fund_state') or '—'}"
                       + (f" · {_rk}" if _rk else "")
                       + ("  Δ " + " · ".join(_chg[:4]) if _chg else ""))
        _dp = it.get("dip_phase")
        if _dp:
            _dpt = {"turning_up": "↗️ dip resolving — lows rising",
                    "stabilizing": "⏸️ dip pausing — wait for a leg",
                    "still_falling": "↘️ dip still falling — knife risk"
                    }.get(_dp, _dp)
            st.caption(f"dip phase: {_dpt} "
                       f"({it.get('dip_health', '?')}/5 legs)")
        _sw = it.get("swing") or {}
        if _sw.get("phase"):
            _swp = _sw["phase"]
            _swt = {
                "confirmed": "✅ higher low confirmed",
                "higher_low": "⏳ higher low forming",
                "unconfirmed": "… structure forming",
                "broken": "⛔ swing structure broken",
            }.get(_swp, _swp)
            _swl = (f"low ${(_sw.get('swing_low') or 0):,.2f} vs prior "
                    f"${(_sw.get('prior_low') or 0):,.2f}")
            if _swp == "higher_low":
                _swl += (f" — confirm on close >"
                         f" ${(_sw.get('confirm_level') or 0):,.2f}")
            if _sw.get("vol_pullback_vs_rally"):
                _swl += f" · dip vol {_sw['vol_pullback_vs_rally']}× rally"
            if _sw.get("avwap"):
                _swl += (f" · AVWAP ${_sw['avwap']:,.2f}"
                         + (" ✓" if _sw.get("avwap_reclaimed") else ""))
            st.caption(f"swing: {_swt} — {_swl}")
        _rs = it.get("rs_pct")
        _er = it.get("days_to_earnings")
        if _rs is not None or (_er is not None and _er <= 15):
            _cx = ""
            if _rs is not None:
                _cx = (f"RS {_rs} pct"
                       + (" · RS line new high 📈" if it.get("rs_nh")
                          else ""))
            if _er is not None and _er <= 15:
                _cx += (" · " if _cx else "") \
                    + f"⚠️ earnings in {_er}d"
            st.caption(f"context: {_cx}")
        if it["action"] in ("ACCUMULATE", "BOUNCE", "PUT"):
            # desk rule: no pick without a written plan — pull the
            # swing screen's entry/stop/target when the scan computed one
            if it.get("entry") and it.get("stop"):
                _plan = (f"plan: entry ${it['entry']:,.2f} · "
                         f"stop ${it['stop']:,.2f}"
                         + (f" · target ${it['target']:,.2f}"
                            if it.get("target") else ""))
                st.markdown(f"📋 **{_plan}**")
            _lv = it.get("levels") or {}
            if _lv.get("watch") and it.get("entry_status") == "watch_zone":
                _w = _lv["watch"]
                _zt = (f"zones: ⏸️ watch ${_w[0]:,.2f}–${_w[1]:,.2f} "
                       f"(deeper adds near ${_w[0]:,.2f})")
                if _lv.get("reclaim"):
                    _zt += (f" · reclaim ${_lv['reclaim']:,.2f} "
                            "with volume = pullback repairing")
                if _lv.get("confirm") and _lv["confirm"] != _lv.get("reclaim"):
                    _zt += f" · full repair >${_lv['confirm']:,.2f}"
                st.caption(f"🗺️ {_zt}")
            st.caption(f"💵 risk budget ≈ "
                       f"${board.get('suggested_tranche', 0):,.0f} "
                       f"(2% equity × size mult)")
            inst = it.get("instrument") or ""
            if "LEAPS" in inst:
                if st.button(f"📜 Open Options screen for "
                             f"{it['symbol']}", key=f"opt_{it['symbol']}"):
                    st.session_state["leaps_sym"] = it["symbol"]
                    st.switch_page("pages/9_Options.py")
                if "put" in inst:
                    st.caption("🔻 contract pick: the PUT verdict's "
                               "ranked table — prefer fresh cracks over "
                               "names that already fell")
                elif it["action"] == "BOUNCE":
                    st.caption("🏀 wounded winner — starter stock size, "
                               "or a call debit spread (defined risk) "
                               "instead of a naked call")
                else:
                    st.caption("⚡ flip / 💥 burst columns on that page "
                               "rank contracts for the 1-2 month exit")
        else:
            st.caption("Exit/trim per your plan — partial exits log on "
                       "the Swing Screener trade card.")

st.caption("Assembled " + (board.get("as_of") or "?")
           + " — reads stored flags; run the relevant refresh jobs if "
             "data looks stale.")

# --- � GARP — good company at a fair price ------------------------------------
# fundamental flag (quality axis) × fwd P/E + PEG (price axis) × tape
# (entry quality). A great company at the peak is a bad trade.
with st.expander("📈 GARP screen — quality at fair price", expanded=False):
    _gp1, _gp2, _gp3 = st.columns([1, 2, 1])
    _mpe = _gp1.selectbox("max fwd P/E", [15, 25, 40, 60], index=2,
                          key="garp_pe")
    if _gp3.button("🔁 Recompute flags", key="rf_fundflags",
                   help="Reclassify every symbol's fundamental health "
                        "flag from the latest flywheel data"):
        _kick("fund-flags")
    _gp3.markdown(f":red[⏱ {_last('fund-flags')}]")
    try:
        _g = client.get("api/v1/board/garp",
                        params={"max_pe": _mpe}) or {}
    except Exception:
        _g = {}
    _gi = _g.get("items") or []
    _gp2.caption(f"{len(_gi)} of {_g.get('scanned', 0)} flagged names "
                 f"with fwd P/E ≤ {_mpe} — sorted by quality×value×tape")
    if _gi:
        import pandas as _pd
        _gdf = _pd.DataFrame([{
            "symbol": r["symbol"],
            "fund": f"{_FUND_I.get(r.get('fund_state'), '')} "
                    f"{r.get('fund_state')}",
            "risk": r.get("risk"), "score": r.get("score"),
            "fwd_pe": r.get("fwd_pe"), "peg": r.get("peg"),
            "rev": (f"{r['rev_growth'] * 100:+.0f}%"
                    if r.get("rev_growth") is not None else None),
            "accel": (f"{r['rev_accel'] * 100:+.0f}pts"
                      if r.get("rev_accel") is not None else None),
            "mom": f"{_MOM_I.get(r.get('momentum'), '')} "
                   f"{r.get('momentum') or '—'}"} for r in _gi])
        st.dataframe(health_col(_gdf), column_config={"🩺": health_cfg()},
                     use_container_width=True, hide_index=True)
        _pick = st.selectbox("evidence:", [r["symbol"] for r in _gi],
                             key="garp_pick")
        _row = next(r for r in _gi if r["symbol"] == _pick)
        for w in _row.get("why") or []:
            st.caption(f"· {w}")
    else:
        st.info("Nothing clears the bar right now — loosen the P/E cap "
                "or run flywheel + fundamental-flag refreshes.")

# --- �📊 track record — the board grading itself -------------------------------
# every published pick is journaled (board_decisions) and graded at
# 5/10/20d forward returns (board_outcomes) by the outcomes refresh job.
# this strip is the answer to "is the board actually right?"
try:
    tr = client.get("api/v1/board/track-record") or {}
    cells = tr.get("cells") or []
    if cells:
        import pandas as pd
        with st.expander("📊 Board track record — does following it pay?",
                         expanded=False):
            df = pd.DataFrame(cells).rename(columns={
                "momentum_state": "momentum", "horizon_days": "days",
                "avg_ret": "avg%", "avg_mfe": "MFE%", "avg_mae": "MAE%",
                "hit_rate": "hit%"})
            st.dataframe(df[["action", "momentum", "days", "n",
                             "avg%", "MFE%", "MAE%", "hit%"]],
                         use_container_width=True, hide_index=True)
            st.caption("Ret is direction-aware — PUT/EXIT cells score "
                       "positive when the stock fell. MFE/MAE show how "
                       "much room and pain the pick needed.")
except Exception:
    pass
