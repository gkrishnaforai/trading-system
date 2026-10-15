"""Market Regime — the full engine detail behind today's posture.

Moved off the Daily Board for load time: posture + morning regime,
released prints → tape effect, horizon trees, buckets, structure,
breadth, book risk, forward probabilities, dip character, allocation,
hedge book, crash alpha, geo context, causal map, capex engine and
the macro calendar. Advisory only — regime sets posture, not picks.
"""
import sys
import os
from datetime import date

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient
from api_config import api_config
from utils import render_top_nav, sym_md

client = APIClient(api_config.python_worker_url, timeout=180)


def _safe_get(p):
    try:
        return p, client.get(p) or {}
    except Exception:
        return p, {}


@st.cache_data(ttl=120, show_spinner=False)
def _prefetch() -> dict:
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        return dict(ex.map(_safe_get, ["api/v1/board/daily",
                                     "api/v1/board/macro-events",
                                     "api/v1/board/posture"]))


st.set_page_config(page_title="Market Regime", page_icon="🌐",
                   layout="wide")
render_top_nav()
st.title("🌐 Market Regime")
st.caption("The full engine detail behind today's posture — what the "
           "regime sees, and the dates that can flip it. "
           "Posture decides *how aggressive* — never *what to buy*.")

with st.spinner("Loading regime…"):
    _PRE = _prefetch()

board = _PRE.get("api/v1/board/daily") or {}
p = board.get("posture") or {}
_PO = _PRE.get("api/v1/board/posture") or {}
_mev = (_PRE.get("api/v1/board/macro-events") or {}).get("events") or []
_rd = p.get("regime_detail") or {}

if not p:
    st.error("Regime payload unavailable — the worker may be restarting. "
             "Wait ~60s and refresh.")
    st.stop()

try:
    _rd_d = date.fromisoformat(
        str(p.get("regime_session_date") or p.get("as_of"))[:10])
except Exception:
    _rd_d = date.today()
try:
    _data_d = date.fromisoformat(str(p.get("as_of"))[:10])
except Exception:
    _data_d = _rd_d
_vintage = (f" · data thru {_data_d:%b} {_data_d.day}"
            if _data_d != _rd_d else "")
st.caption(f"regime session {_rd_d:%B} {_rd_d.day}, {_rd_d:%Y}{_vintage}")

if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

# --- posture banner -----------------------------------------------------
_STANCE_I = {"FEAR — DEPLOY": "🟢", "GREED — HARVEST": "🟠",
             "DEFENSIVE": "🔴", "NEUTRAL": "⚪"}
stance = p.get("stance") or "?"
c1, c2, c3, c4 = st.columns(4)
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
if p.get("note"):
    st.caption(f"_{p['note']}_")
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

# macro event-day judge — the bounded green/red/choppy read
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

# --- morning regime: the daily engine's dashboard -----------------------
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
                            if _te.get('prev') is not None else "")
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
    _chg = (_vd.get("changes") or [])
    if _chg:
        st.caption("**Δ today:** " + " · ".join(_chg[:6]))
    # released prints → what they did to the tape
    _prints = [e for e in _mev
               if e.get("actual") is not None
               and isinstance(e.get("days_away"), int)
               and e["days_away"] <= 0]
    if _prints:
        st.markdown("**🗞️ released prints → tape effect**")
    for _e in _prints[:3]:
        try:
            _ep = (f"printed **{float(_e['actual']):g}**"
                   + (f" vs est {float(_e['estimate']):g}"
                      if _e.get('estimate') is not None
                      else "")
                   + (f" (prior {float(_e['prev']):g})"
                      if _e.get('prev') is not None else ""))
        except (TypeError, ValueError):
            _ep = "printed"
        _ej = _e.get("judge") or {}
        _rx = ""
        if _ej.get("verdict"):
            _rx = (f" · judge "
                   f"**{str(_ej['verdict']).upper()}**"
                   + (f" ({_ej['confidence']}%)"
                      if _ej.get('confidence') is not None
                      else ""))
        if _ej.get("spy_ret") is not None:
            try:
                _rx += (f" · SPY "
                        f"{float(_ej['spy_ret']) * 100:+.2f}%"
                        + (" ✓" if _ej.get("correct") else
                           " ✗" if _ej.get("correct")
                           is False else ""))
            except (TypeError, ValueError):
                pass
        st.caption(
            f"`{_e['date']}` {_e['name']} — {_ep}"
            + (f" — **{_e['reading']}**"
               if _e.get('reading') else "") + _rx)
        if _e.get("impact"):
            st.caption(f"   ↳ {_e['impact']}")
        if _ej.get("debrief"):
            st.caption(f"   ↳ debrief: {_ej['debrief']}")
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

# --- regime card detail -------------------------------------------------
if _rd:
    st.subheader("Regime card")
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

# --- dip character: IF a dip comes, does AI infra drag? ----------------
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

# --- allocation: cash buffer + where money rotates ---------------------
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

# --- hedge book — the insurance card ------------------------------------
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
               if h['value_pct'] is not None else "")
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

# --- crash alpha — PUT entry + capitulation + rotation ------------------
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
    _rd_ = _ca.get("redeploy") or {}
    if _rd_.get("armed") and _rd_.get("candidates"):
        st.caption(
            f"**🔄 PUT→CALL armed** — proceeds "
            f"~${_rd_.get('proceeds_est', 0):,.0f}; "
            f"redeploy into:")
        for c in _rd_["candidates"][:5]:
            st.caption(
                f"▸ **{sym_md(c['symbol'])}** "
                f"{c['alloc_pct']}% (~${c['alloc_usd']:,}) "
                f"· dd {c['dd52w']:.0f}% · {c['dip_phase']}")

# --- geo context + causal map -------------------------------------------
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

# --- AI capex-cycle engine ----------------------------------------------
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

# --- macro calendar -----------------------------------------------------
if _mev:
    st.subheader("📅 Macro calendar")
    for e in _mev[:8]:
        _da = e.get("days_away")
        _tag = ("**today**" if _da == 0 else
                "**tomorrow**" if _da == 1 else
                "**yesterday**" if _da == -1 else
                (f"{-_da}d ago" if isinstance(_da, int)
                 and _da < 0 else f"in {_da}d"))
        _mv = (f" 🔀 moved from `{e['rescheduled_from']}`"
               if e.get("rescheduled") else "")
        _prt = ""
        try:
            if e.get("actual") is not None:
                _prt = (f" — printed "
                        f"**{float(e['actual']):g}**"
                        + (f" vs est {float(e['estimate']):g}"
                           if e.get('estimate') is not None
                           else "")
                        + (f" (prior {float(e['prev']):g})"
                           if e.get('prev') is not None else ""))
            elif e.get("estimate") is not None:
                _prt = f" — est {float(e['estimate']):g}"
        except (TypeError, ValueError):
            _prt = ""
        st.caption(
            f"`{e['date']}` {e['name']} {_tag}"
            + (" ⚠️" if e["severity"] == "extreme" else "")
            + (" *(est)*" if e.get("est") else "")
            + (" *(unconfirmed)*" if e.get("unconfirmed") else "")
            + _mv + _prt
            + (f" — {e['reading']}" if e.get('reading') else ""))
        _sub = []
        if e.get("impact"):
            _sub.append(str(e["impact"]))
        _jg = e.get("judge") or {}
        if _jg.get("verdict"):
            _sub.append(
                f"judge **{str(_jg['verdict']).upper()}**"
                + (f" ({_jg['confidence']}%)"
                   if _jg.get("confidence") is not None else "")
                + (f" · SPY "
                   f"{float(_jg['spy_ret']) * 100:+.2f}%"
                   if _jg.get("spy_ret") is not None else "")
                + (f" — {_jg['thesis']}"
                   if _jg.get("thesis") else ""))
        _tail = (" · " + " · ".join(_sub)) if _sub else ""
        if _tail or e.get("source_url"):
            st.caption(
                "   ↳" + _tail
                + (f" — 📄 [official release ↗]"
                   f"({e['source_url']})"
                   if e.get("source_url") else ""))

st.caption("Advisory only — the regime sets posture and size; it never "
           "picks symbols and never trades.")
