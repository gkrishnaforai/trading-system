"""Stock Health — the per-symbol decision page.

Every engine's persisted read on ONE symbol, composed into a card:
fundamental health · technical health · growth/estimates · real
quality · valuation · conviction/gem/hedge reads · future themes —
with a verdict line that names conflicts. Action buttons recompute
on demand: fresh technicals, the real swing-screener eval, and the
options chain screen. Advisory — nothing executes.
"""
import streamlit as st
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from api_client import APIClient
from api_config import api_config

setup_page_config("Stock Health", "🩺")
render_sidebar()

client = APIClient(api_config.python_worker_url, timeout=120)

qp = st.query_params
sym = (st.text_input("Symbol", value=(qp.get("sym") or ""),
                     placeholder="ALAB") or "").upper().strip()
if not sym:
    st.stop()
if qp.get("sym") != sym:
    st.query_params["sym"] = sym


@st.cache_data(ttl=300, show_spinner=False)
def _card(s):
    try:
        return client.get(f"api/v1/board/symbol/{s}/health") or {}
    except Exception as e:
        return {"error": str(e)}


H = _card(sym)
c1, c2 = st.columns([4, 1])
with c2:
    if st.button("🔄 reload"):
        _card.clear()
        st.rerun()

if not H or H.get("error"):
    st.warning(f"no data for {sym} — is it in the universe?")
    st.stop()

name = H.get("name") or sym
v = H.get("verdict") or {}
_VC = {"deploy": "🟢", "deploy on dips": "🟢", "watch": "🟡",
       "future shelf": "🔮", "momentum-only": "🟠", "avoid": "🔴",
       "neutral": "⚪"}

# technical freshness — the tape read's data date, above the title;
# flags stale so an old read can't masquerade as today's
_ta = (H.get("technical") or {}).get("as_of")
try:
    _ta_d = date.fromisoformat(str(_ta)[:10]) if _ta else None
except Exception:
    _ta_d = None
_stale = _ta_d is not None and (date.today() - _ta_d).days > 2
st.caption(
    (f"⚠️ technicals refreshed {_ta_d:%B} {_ta_d.day}, {_ta_d:%Y} — "
     f"stale, press 🔄 or run the momentum job"
     if _stale else
     f"technicals refreshed {_ta_d:%B} {_ta_d.day}, {_ta_d:%Y}"
     if _ta_d else
     "technicals never refreshed — press 🔄 to compute live"))
st.title(f"{_VC.get(v.get('verdict'), '⚪')} {sym} — {name}")
st.caption(f"verdict: **{v.get('verdict','—')}** — {v.get('why','')}"
           + (f" · {H.get('sector') or ''}"
              f" · mcap ${(H.get('market_cap') or 0)/1e9:.1f}B"
              if H.get('market_cap') else f" · {H.get('sector') or ''}"))
if H.get("next_earnings"):
    st.caption(f"📅 earnings: {H['next_earnings']}")

# ------------------------------------------------------------ the card
t, f, g = st.columns(3)
with f:
    fd = H.get("fundamental") or {}
    st.markdown(f"**🧬 Fundamentals — `{fd.get('state') or '—'}`**")
    fdet = fd.get("detail") or {}
    neg = [x for x in (fdet.get("neg") or [])]
    pos = [x for x in (fdet.get("pos") or [])]
    _EXPL = {
        "deteriorating": f"{len(neg)} independent negatives — the "
                         "business is weakening across multiple legs, "
                         "not just one bad print",
        "declining": "growth has gone negative or several legs are "
                     "worsening — the thesis is eroding",
        "slowing": "still growing, but the growth RATE is falling — "
                   "early warning, watch the next quarter",
        "accelerating": "growth improving on multiple legs — the "
                        "strongest fundamental profile",
        "growing": "solid growth, nothing materially deteriorating",
        "cyclical": "weakness may be cycle-driven — judge by the "
                    "leading legs (revs, estimates), not trailing EPS",
        "watch": "mixed signals — nothing decisive either way",
        "unknown": "no fundamental data",
    }
    if fd.get("state") in _EXPL:
        st.caption(_EXPL[fd["state"]])
    for n_ in neg[:4]:
        st.caption(f"✗ {n_}")
    for p_ in pos[:3]:
        st.caption(f"✓ {p_}")
    if fd.get("risk") and fd["risk"] not in ("low",):
        st.caption(f"risk: `{fd['risk']}` (valuation/coverage)")
    if fdet.get("alert") and fdet["alert"] != "normal":
        st.caption(f"⚠️ alert `{fdet['alert']}` — worsened vs last "
                   "snapshot")
    chg = fdet.get("changes") or []
    for c in (chg if isinstance(chg, list) else [chg])[:4]:
        st.caption(f"· {c}")
    if fdet.get("stale_inputs"):
        st.caption(f"⚠️ flywheel inputs "
                   f"{fdet.get('flywheel_age_days')}d stale")
    if fd.get("as_of"):
        st.caption(f"refreshed {str(fd['as_of'])[:16].replace('T',' ')}"
                   f"Z — 🧬 button below recomputes from provider")
    else:
        st.caption("never classified — press 🧬 refresh fundamentals")
with t:
    td = H.get("technical") or {}
    det = td.get("detail") or {}
    st.markdown(f"**📈 Tape — `{td.get('state') or '—'}`**")
    st.caption(
        f"RSI {det.get('rsi','—')} · %B {det.get('pct_b','—')} · "
        f"52w {((det.get('dd52w') or 0)*100):+.0f}% · "
        f"vs50 {((det.get('vs_sma50') or 0)*100):+.0f}%")
    if td.get("as_of"):
        st.caption(f"refreshed {str(td['as_of'])[:16].replace('T',' ')}"
                   f"Z — 🔄 button below recomputes live")
with g:
    gr = H.get("growth") or {}
    st.markdown("**🚀 Growth / expectations**")
    def _p(x): return f"{x*100:+.0f}%" if x is not None else "—"
    st.caption(
        f"rev {_p(gr.get('rev_growth'))} · eps {_p(gr.get('eps_growth'))}"
        f" · rev_accel {_p(gr.get('rev_accel'))}")
    st.caption(
        f"revisions {_p(gr.get('est_revision_pct'))} · streak "
        f"{gr.get('beat_streak','—')} · fwd PE {gr.get('fwd_pe','—')} · "
        f"gap {gr.get('gap_score','—')}")
    fwd = H.get("forward") or {}
    if fwd.get("revision_grade") or fwd.get("priced_status") \
            or fwd.get("emerging_growth"):
        _fwd_line = (
            f"revision grade **{fwd.get('revision_grade') or '—'}**"
            f" ({fwd.get('revision_score') or '—'}) · priced "
            f"**{fwd.get('priced_status') or '—'}**"
            + (f" · emerging **{fwd['emerging_growth']}**"
               if fwd.get("emerging_growth") else ""))
        st.markdown(
            f"<div style='background:#ede9fe;color:#5b21b6;"
            f"border-radius:6px;padding:4px 8px;font-size:0.8rem;"
            f"margin:2px 0'>🔮 {_fwd_line}</div>",
            unsafe_allow_html=True)
        fdet_fwd = (fwd.get("detail") or {}).get("emerging") or {}
        if fdet_fwd.get("uplift_ratio_fy3"):
            st.markdown(
                f"<div style='color:#7c3aed;font-size:0.75rem;"
                f"margin:2px 0'>ramp uplift ≈ "
                f"{fdet_fwd['uplift_ratio_fy3']*100:.0f}% of street "
                f"fwd rev by FY+3 "
                f"({fdet_fwd.get('n_initiatives')} initiative(s))</div>",
                unsafe_allow_html=True)
    if gr.get("updated_at"):
        st.caption(f"flywheel refreshed "
                   f"{str(gr['updated_at'])[:16].replace('T',' ')}Z")

with st.expander("📖 legend — what the states mean", expanded=False):
    l1, l2, l3 = st.columns(3)
    with l1:
        st.markdown("**🧬 Fundamentals** — direction of the numbers")
        st.caption(
            "`accelerating` growth improving on multiple legs<br>"
            "`growing` solid growth, nothing deteriorating<br>"
            "`slowing` **still growing but decelerating — early "
            "warning** (ALAB: legs rolling over, not broken)<br>"
            "`declining` several metrics deteriorating — thesis "
            "weakening<br>"
            "`deteriorating` ≥4 independent negatives — serious<br>"
            "`cyclical` weakness may be cycle-driven — judge the "
            "leading legs<br>"
            "`watch` mixed / insufficient signal · `unknown` no data",
            unsafe_allow_html=True)
        st.caption("Axes: risk = valuation/coverage exposure · "
                   "alert = how much it worsened vs last snapshot")
    with l2:
        st.markdown("**📈 Tape** — what price is doing")
        st.caption(
            "`climax` RSI≥75 / %B>0.95 — euphoria, trim, no entries<br>"
            "`uptrend` above 200dma, 50>200 — hold, buy pullbacks<br>"
            "`pullback` washed inside uptrend — **the dip-buy zone**<br>"
            "`breakout` fresh 60d high + momentum — igniting<br>"
            "`recovery` reclaimed 200dma — early turn repair<br>"
            "`basing` tight 20d range — coiling, wait<br>"
            "`rolling_over` extended + first momentum crack<br>"
            "`knife` still collapsing — don't catch it<br>"
            "`capitulation` deep wash, trend broken<br>"
            "`breakdown` fresh 60d low — falling<br>"
            "`downtrend` below 200dma — broken until repaired",
            unsafe_allow_html=True)
    with l3:
        st.markdown("**Verdict** — the composite read")
        st.caption(
            "🟢 `deploy` engines aligned<br>"
            "🟢 `deploy on dips` aligned but extended — entries at "
            "zones<br>"
            "🟡 `watch` conflict (e.g. strong fund + broken tape — "
            "don't catch the knife)<br>"
            "🔮 `future shelf` thesis exposure without confirmation<br>"
            "🟠 `momentum-only` tape-led, fundamentals stretched<br>"
            "🔴 `avoid` fundamentals or tape broken<br>"
            "⚪ `neutral` insufficient signal",
            unsafe_allow_html=True)
        st.caption("fv = fair-value model upside vs price — value "
                   "signal, separate from momentum. ⚠ stretched = "
                   "value model disagrees.")

# ---- why is it moving? — attribution + event wire + expectations
_dg = H.get("diagnosis") or {}
if _dg:
    _at = _dg.get("attribution") or {}
    _di = "🔴" if _dg.get("direction") == "weak" else "🟢"
    _vi = {"market_beta": "🌐", "sector_rotation": "🔄",
           "idiosyncratic_catalyst": "📰", "multiple_compression": "📉",
           "earned_momentum": "✅", "catalyst_bounce": "📰",
           "hype_risk": "⚠️", "unexplained_spike": "⚠️",
           "unexplained": "❓", "flow_drift": "⚪"}.get(
        _dg.get("verdict"), "⚪")
    st.markdown(f"### {_di} {_dg.get('label')}")
    _a = [f"**{sym}** {((_at.get('stock_5d') or 0)*100):+.1f}% (5d)"
          f" · {((_at.get('stock_20d') or 0)*100):+.1f}% (20d)"]
    if _at.get("sector_etf"):
        _a.append(f"**{_at['sector_etf']}** "
                  f"{((_at.get('sector_5d') or 0)*100):+.1f}%")
    _a.append(f"**SPY** {((_at.get('spy_5d') or 0)*100):+.1f}%")
    st.caption("attribution: " + "  ·  ".join(_a))
    st.markdown(f"{_vi} **{_dg['verdict'].replace('_', ' ')}** — "
                f"{_dg.get('line')}")
    for c in (_dg.get("causes") or [])[:5]:
        st.caption(f"▸ {c}")
    if _dg.get("note"):
        st.caption(f"💡 {_dg['note']}")

# ------------------------------------------------- engine reads
st.divider()
e1, e2, e3, e4 = st.columns(4)
cv = H.get("conviction") or {}
with e1:
    st.markdown("**🏆 Conviction**")
    if cv:
        st.caption(f"#{cv.get('rank')} · {cv.get('score')}/100 · "
                   f"`{cv.get('lane')}` · future "
                   f"{cv.get('future_score') or '—'}/95")
        flags = [x for x in ("daily_pick", "weekly_pick",
                             "monthly_pick") if cv.get(x)]
        if flags:
            st.caption("⭐ " + " · ".join(flags))
        st.caption("src: " + " · ".join(cv.get("sources") or []))
    else:
        st.caption("not on The List")
with e2:
    gm = H.get("hidden_gem") or {}
    st.markdown("**💎 Hidden Gem**")
    if gm:
        st.caption(f"{gm.get('score')}/125 · {gm.get('aligned')}/7 "
                   f"aligned · {gm.get('valuation')} · "
                   f"{gm.get('snap_date')}")
    else:
        st.caption("not in gems")
with e3:
    hg = H.get("hedge") or {}
    st.markdown("**🛡 Hedge (put)**")
    if hg:
        st.caption(f"{hg.get('score')} · `{hg.get('tier')}` · "
                   f"corr {hg.get('corr_target')} · β→tgt "
                   f"{hg.get('beta_to_target')} · "
                   f"{hg.get('setup')}")
    else:
        st.caption("not a hedge candidate")
with e4:
    sc = H.get("swing_call") or {}
    st.markdown("**📞 Swing call**")
    if sc:
        st.caption(f"#{sc.get('rank')} score {sc.get('score')} · "
                   f"{sc.get('call_date')} · entry {sc.get('entry_px')}"
                   f" stop {sc.get('stop_px')}")
    else:
        st.caption("no recent call")

# ------------------------------------------------- quality + themes
q = H.get("quality") or {}
th = H.get("themes") or []
q1, q2 = st.columns(2)
with q1:
    if q:
        def _pc(x): return f"{x*100:.0f}%" if x is not None else "—"
        st.caption(f"🧾 quality: ROE {_pc(q.get('roe'))} · FCF margin "
                   f"{_pc(q.get('fcf_margin'))} · dilution "
                   f"{_pc(q.get('dilution'))} · D/E "
                   f"{(q.get('debt_to_equity') or 0):.1f}")
with q2:
    if th:
        _RC = {"early": "🌱early", "leading": "🚀leading",
               "extended": "🔥extended", "fading": "📉fading",
               "building": "🧱building"}
        st.caption("🔮 themes: " + " · ".join(
            f"{t['name']} ({t['exposure'][:4]}, {t['stage']}"
            + (f", rotation #{t['rotation']['rank']} "
               f"{_RC.get(t['rotation'].get('call'), '')}"
               if t.get("rotation") else "")
            + ")" for t in th))
an = H.get("analyst") or {}
if an.get("price_target") or an.get("rating"):
    st.caption(f"🎯 analysts: {an.get('rating') or '—'} · PT "
               f"{an.get('price_target') or '—'}")

# ------------------------------------- 🎯 fair-value scenario ladder
fvd = H.get("fv") or {}
_scen = fvd.get("scenarios") or {}
if fvd.get("scenarios") and fvd.get("spot"):
    st.markdown("**🎯 Fair value — engine scenarios** "
                f"`{fvd.get('regime') or '—'}`")
    _sp = float(fvd["spot"])
    _keys = [("bear", "🔻 bear"), ("base", "◆ base"),
             ("expected", "⧗ expected"), ("bull", "🔺 bull"),
             ("explosive", "🚀 explosive")]
    _vals = {"expected": fvd.get("expected"), **_scen}
    # ladder line — every level as % vs spot
    bits = []
    for k, lbl in _keys:
        v = _vals.get(k)
        if v is None:
            continue
        bits.append(f"{lbl.split()[1]} **${float(v):.2f}** "
                    f"({float(v) / _sp - 1:+.0%})")
    st.markdown(f"price **${_sp:.2f}** — " + " · ".join(bits))
    st.caption("expected = Σ p·scenario "
               "(bear 25% · base 50% · bull 20% · explosive 5%) — "
               "a probability-weighted value, not just the base case")

    # v1 legacy engine — still computes inside /fair-value; shown here
    # for comparison. Different math (regime keyword heuristics +
    # hardcoded blend), so divergence itself is signal.
    _fv1 = H.get("fv_v1") or {}
    if _fv1.get("fv"):
        _b = _vals.get("base") or fvd.get("expected")
        _l1 = f"🧮 **v1 engine** — fv **${float(_fv1['fv']):.2f}**"
        if _fv1.get("upside_pct") is not None:
            _l1 += f" ({_fv1['upside_pct']:+.0f}% vs spot)"
        if _fv1.get("regime"):
            _l1 += f" · regime `{_fv1['regime']}`"
        if _b:
            _d = float(_fv1["fv"]) / float(_b) - 1
            _l1 += f" · vs v2 base {_d:+.0%}"
        st.markdown(_l1)
        if _fv1.get("methods"):
            st.caption("v1 methods: " + " · ".join(
                f"{k.replace('_v2', '')} ${float(v):.0f}"
                for k, v in _fv1["methods"].items()))

    # per-method FVs — each method's independent answer before the blend,
    # same pattern as the old v1 method table (PEG/PE rows)
    _mtab = [m for m in (fvd.get("methods") or []) if m.get("fv")]
    if _mtab:
        st.caption("methods → " + " · ".join(
            f"`{m['key']}` **${float(m['fv']):.2f}** "
            f"({float(m['fv']) / _sp - 1:+.0%})"
            + (f" w{m['w']:.2f}" if isinstance(m.get("w"), (int, float))
               else "")
            for m in _mtab))

    # decision layer — fair value prices worth; buy_below prices safety
    _dec = fvd.get("decision") or {}
    _cls = _dec.get("classification") or {}
    if _cls.get("primary"):
        _arch = "`" + _cls["primary"] + "`" + "".join(
            f" · `{a}`" for a in (_cls.get("secondary") or []))
        st.caption("🏷 archetypes: " + _arch +
                   (f"  ·  src: {_cls.get('source')}"
                    if _cls.get("source") == "override" else ""))
    if _dec.get("buy_below"):
        _bb = float(_dec["buy_below"])
        _gate = "🟢 **below gate — accumulable**" if _sp <= _bb \
            else "🔴 above gate — wait for discount"
        _bits = [f"buy below **${_bb:.2f}** "
                 f"(MoS {_dec.get('mos_pct', 0):.0%})"]
        if _dec.get("expected_return_2y") is not None:
            _bits.append(f"2y exp **{_dec['expected_return_2y']:+.1%}**/yr")
        if _dec.get("valuation_confidence"):
            _bits.append(f"conf `{_dec['valuation_confidence']}`")
        _bits.append(_gate)
        st.markdown("**🛡 decision** — " + " · ".join(_bits))
        if _dec.get("risk_flags"):
            st.caption("⛔ risk flags: " +
                       ", ".join(f"`{f}`" for f in _dec["risk_flags"]))
        if _dec.get("mos_adders"):
            st.caption("MoS adders: " +
                       ", ".join(f"`{a}`" for a in _dec["mos_adders"]))

    # macro-scenario stress — what happens to THIS name if the AI
    # capex cycle turns each way (archetype-weighted, not base FV)
    _msc = _dec.get("macro_scenarios") or {}
    if _msc:
        with st.expander("🌪 AI-capex stress — FV under each macro path"):
            for sk, sv in _msc.items():
                if sk.startswith("_"):
                    continue
                _imp = sv.get("impact") or 0
                _line = (f"**{sk.replace('_', ' ')}** — {sv.get('label')}: "
                         f"{_imp:+.0%} → fv **${sv.get('stressed_fv', 0):.2f}**")
                if sv.get("stressed_buy_below"):
                    _line += f" · buy ≤ ${sv['stressed_buy_below']:.2f}"
                st.caption(_line)
            _w = _msc.get("_worst") or {}
            if _w:
                st.caption(f"worst path: `{_w.get('scenario')}` "
                           f"{(_w.get('impact') or 0):+.0%}")

    # deterministic per-scenario math — method contributions recomputed
    # from the run's own inputs, no narrative
    with st.expander("why these numbers — method breakdown"):
        _ms = fvd.get("methods") or []
        for k, lbl in _keys:
            v = _vals.get(k)
            if v is None:
                continue
            parts = []
            for m in _ms:
                mv = (m.get("scenarios") or {}).get(k) \
                    if k != "expected" else None
                if k == "expected":
                    mv = None
                ex = (m.get("explain") or {}).get(k)
                if mv is not None:
                    parts.append(f"`{m['key']}` ${float(mv):.2f}"
                                 f"{f' — {ex}' if ex else ''}")
            st.caption(f"{lbl}: **${float(v):.2f}**"
                       + (" = " + " + ".join(parts) if parts else ""))
        st.caption("implied multiples recomputed from run inputs — "
                   "EPS × PE means 'earnings times the multiple the "
                   "method applied'; weight shows blend share")
        for m in _ms:
            w = m.get("w")
            st.caption(f"· `{m['key']}` w={w} → base "
                       f"${float(m.get('fv') or 0):.2f}")
    if fvd.get("flags"):
        st.caption("⚠️ quality flags: " + ", ".join(fvd["flags"]))

    # what moves it — tailwinds justify the bull path, headwinds
    # the bear path (channel journal, corroboration-tiered)
    _tws = H.get("tailwinds") or []
    _up = [t for t in _tws if t.get("direction") != "headwind"]
    _dn = [t for t in _tws if t.get("direction") == "headwind"]
    if _up or _dn:
        c1, c2 = st.columns(2)
        with c1:
            if _up:
                st.caption("🔺 **to bull:** " + " · ".join(
                    f"`{t['channel']}` ({t['tier']})" for t in _up[:4]))
        with c2:
            if _dn:
                st.caption("🔻 **to bear:** " + " · ".join(
                    f"`{t['channel']}` ({t['tier']})" for t in _dn[:4]))

    _an = fvd.get("analyst") or {}
    if _an.get("consensus_price_target"):
        st.caption(
            f"🏛 street view: ${float(_an['consensus_price_target']):.2f} "
            f"consensus"
            + (f" (${_an['price_target_low']:.0f}–"
               f"${_an['price_target_high']:.0f})"
               if _an.get("price_target_low")
               and _an.get("price_target_high") else "")
            + (f" · {_an['analyst_count']} analysts"
               if _an.get("analyst_count") else "")
            + " — reference only, not blended into our number")

# ---------------------- 🧠 classification assistant (LLM proposes,
# human applies via the category-override path — rules stay default)
with st.expander("🧠 classification — archetype review"):
    _cur = ((H.get("fv") or {}).get("decision") or {}).get(
        "classification") or {}
    st.caption("current: " +
               ("`" + _cur.get("primary", "?") + "`" +
                "".join(f" · `{a}`" for a in (_cur.get("secondary") or []))
                if _cur.get("primary") else "no run yet"))
    if st.button("suggest (LLM)", key="cls_suggest"):
        _r = client.post("admin/fair-value-v2/classify-suggest",
                         json_data={"symbol": sym})
        st.session_state["cls_sug"] = _r
    _sug = st.session_state.get("cls_sug") or {}
    if _sug.get("success") and _sug.get("suggestion"):
        _s = _sug["suggestion"]
        _p = _s.get("proposed") or {}
        st.caption(f"proposed: `{_p.get('primary')}`" +
                   "".join(f" · `{a}`" for a in (_p.get("secondary") or []))
                   + f"  ·  conf {_s.get('confidence') or '—'}"
                   + ("  ·  ⚠️ differs from rules" if _s.get("changed")
                      else "  ·  agrees with rules"))
        if _s.get("rationale"):
            st.caption("why: " + _s["rationale"])
        for _e in (_s.get("evidence") or [])[:3]:
            st.caption("· " + _e)
        if _s.get("changed") and st.button("apply as category override",
                                           key="cls_apply"):
            _w = client.post("admin/fair-value-v2/category-overrides",
                             json_data={
                                 "symbol": sym,
                                 "category_override": _p.get("primary"),
                                 "enabled": True,
                                 "reason": ("llm-suggested: "
                                            + (_s.get("rationale") or "")
                                            )[:400],
                                 "updated_by": "llm-assist",
                             })
            if _w.get("success"):
                st.success("override stored — next FV run uses it")
                st.session_state.pop("cls_sug", None)
            else:
                st.error(str(_w.get("error") or "apply failed"))
    elif _sug and not _sug.get("success"):
        st.caption("⚠️ " + (_sug.get("error") or "LLM tier unavailable — "
                            "set OPENAI_API_KEY / ANTHROPIC_API_KEY"))
    st.caption("rules are the default; an LLM proposal becomes an "
               "override only after you apply it — deterministic "
               "routing is never auto-changed")

# --------------------------- ⏳ long-duration repricing lens (lt_power)
# Separate from the fair-value ladder on purpose: the FV engine values
# ~1y-forward fundamentals; this lens asks whether the market is
# repricing on LONG-DATED earnings power (the AMD pattern — street
# CY2030 EPS × mature multiple ≈ the actual reprice).
ltp = H.get("lt_power") or {}
if ltp.get("lt_band") and ltp.get("spot"):
    _ltb = ltp["lt_band"]
    _lsp = float(ltp["spot"])
    st.markdown("**⏳ long-duration repricing lens** "
                f"`{ltp.get('repricing_setup') or '—'} setup "
                f"({ltp.get('repricing_score') or '—'})`")
    _lbits = []
    for _k, _lbl in [("bear", "bear"), ("base", "base"),
                     ("bull", "bull"), ("explosive", "expl")]:
        _v = _ltb.get(_k)
        if _v is not None:
            _lbits.append(f"{_lbl} **${float(_v):.0f}** "
                          f"({float(_v) / _lsp - 1:+.0%})")
    st.markdown(f"if street capitalizes {ltp.get('lt_period') or 'LT'} "
                f"EPS **${ltp.get('eps_lt_avg'):.2f}** at mature "
                "multiples — " + " · ".join(_lbits))
    _chk = ltp.get("checklist") or {}
    _mark = {True: "✓", False: "✗", None: "·"}
    st.caption("repricing setup — " + " · ".join(
        f"{_mark.get(_chk.get(k), '·')} {lbl}" for k, lbl in [
            ("lt_curve_exists", "LT estimate curve"),
            ("back_loaded", f"back-loaded EPS "
             f"({ltp.get('duration_ratio')}x fwd)" if ltp.get(
                 'duration_ratio') else "back-loaded EPS"),
            ("coverage", f"{int(ltp['lt_analysts'])} analysts" if ltp.get(
                'lt_analysts') else "LT coverage"),
            ("revisions_up", "LT revisions rising"),
            ("tailwind_evidence", "channel evidence"),
            ("tape_confirm", "tape confirming")]))
    _ipe = ltp.get("implied_lt_pe")
    if _ipe:
        st.caption(
            f"market already pays **{_ipe}x** on "
            f"{ltp.get('lt_period') or 'LT'} EPS avg "
            f"({ltp.get('already_priced') or '—'}) — deterministic "
            "from stored estimates; not blended into fair value")
    if ltp.get("fx_suspect"):
        st.caption("⚠️ LT estimate looks native-currency on an ADR "
                   "(implied PE <4x) — band likely overstated")

# --------------------------- 🌱 growth-quality composite
# Slope(30)/quality(20)/revisions(25)/structural(25) — separates real
# structural growers from cyclical peaks and manufactured EPS. Rendered
# in plain English first; the raw scores stay as a caption for anyone
# who wants the numbers.
gq = H.get("growth_quality") or {}
if gq.get("score") is not None:
    _gc = gq.get("components") or {}
    _gd = gq.get("detail") or {}
    _pctl = gq.get("percentile")
    _score = float(gq["score"])
    _fl = gq.get("flags") or []

    def _gw(v, good=65, ok=40):
        if v is None:
            return "no data yet"
        v = float(v)
        return "strong" if v >= good else ("mixed" if v >= ok else "weak")

    # headline — the percentile translated
    if _pctl is not None:
        _p = float(_pctl)
        _head = ("one of the strongest growers we track" if _p >= 80 else
                 "above-average growth" if _p >= 60 else
                 "middle of the pack" if _p >= 40 else
                 "growth is weaker than most names we track")
        st.markdown(f"**🌱 Is the growth real? `{_score:.0f}`/100 — "
                    f"{_head}** (beats {_p:.0f}% of tracked companies)")
    else:
        st.markdown(f"**🌱 Is the growth real? `{_score:.0f}`/100**")

    # the "so what" sentence — combines growth LEVEL (slope score),
    # DIRECTION (rev_accel), and DURABILITY (structural score) without
    # conflating them.
    _sl = _gc.get("growth_slope")
    _sp = _gc.get("structural_proof")
    _acc = _gd.get("rev_accel")
    if _sl is not None and _sp is not None:
        _slw, _spw = float(_sl), float(_sp)
        if _acc is None:
            _dir = "growth direction unknown"
        elif float(_acc) > 0.02:
            _dir = "growth is accelerating"
        elif float(_acc) < -0.02:
            _dir = "growth is decelerating"
        else:
            _dir = "growth is steady"
        if _slw >= 65 and _spw >= 65:
            _so = (f"Growth is **strong and durable** — high level, "
                   f"{_dir.replace('growth is ', '')}, and a multi-year "
                   "record behind it.")
        elif _slw >= 65 and _spw < 40:
            _so = ("Growth is **hot but thin** — fast now"
                   + (f", and {_dir}" if "decelerating" in _dir else "")
                   + " — could be a cycle peak rather than a durable "
                   "trend. Don't overpay.")
        elif _slw < 40 and _spw >= 65:
            _so = ("Growth **hasn't shown up in recent numbers yet** "
                   f"({_dir}), but long-range forecasts + track record "
                   "say it's ahead — a future-growth profile, not "
                   "growth today.")
        elif _slw < 40 and _spw < 40:
            _so = (f"Growth is **weak and unproven** — {_dir}, and no "
                   "durable track record behind it.")
        else:
            _so = (f"Growth is **mixed** — {_dir}; durability "
                   + ("confirmed" if _spw >= 60 else "not yet proven")
                   + ".")
        st.markdown(_so)

    _ln = []
    if _sl is not None:
        _acc = _gd.get("rev_accel")
        _ln.append("**Speeding up or slowing down?** — " + _gw(_sl)
                   + (" — growth accelerating"
                      if _acc is not None and float(_acc) > 0.02 else
                      " — growth decelerating"
                      if _acc is not None and float(_acc) < -0.02 else
                      " — growth steady" if _acc is not None else ""))
    _eq = _gc.get("earnings_quality")
    if _eq is not None:
        _fcf = _gd.get("fcf")
        _ln.append("**Are the profits real cash?** — " + _gw(_eq)
                   + (" — generates real free cash flow"
                      if _fcf is not None and float(_fcf) > 0 else
                      " — burning cash" if _fcf is not None else ""))
    _rm = _gc.get("revision_momentum")
    if _rm is not None:
        _md = _gd.get("rev_mean_delta")
        _ln.append("**Are analysts getting more bullish?** — " + _gw(_rm)
                   + (" — estimates rising" if _md is not None
                      and float(_md) > 0 else
                      " — estimates falling" if _md is not None
                      and float(_md) < 0 else
                      " — not enough history yet" if _md is None else ""))
    if _sp is not None:
        _lt = _gd.get("lt_curve_days")
        _ln.append("**Is it durable?** — " + _gw(_sp)
                   + (f" — analysts model {int(_lt) // 30}+ months out"
                      if _lt else "")
                   + (" · cyclical name — peak numbers discounted"
                      if "cyclical" in _fl else ""))
    for _l in _ln:
        st.markdown(_l)

    # raw numbers for the fluent reader
    _bits = []
    if _gd.get("rev_g_latest") is not None:
        _bits.append(f"revenue {float(_gd['rev_g_latest']):+.0%} last FY")
    if _gd.get("rev_cagr_3y") is not None:
        _bits.append(f"{float(_gd['rev_cagr_3y']):+.0%}/yr avg over 3 yrs")
    if _gd.get("dilution") is not None and float(_gd["dilution"]) > 0.03:
        _bits.append(f"dilution {float(_gd['dilution']):+.0%}/yr")
    _bits += [f"{'⚠️ ' if f in ('fcf_negative', 'dilutive', 'cyclical') else ''}"
              f"{f.replace('_', ' ')}" for f in _fl]
    if _bits:
        st.caption(" · ".join(_bits))
    st.caption("weights: momentum 30 · cash quality 20 · revisions 25 · "
               "durability 25 — percentile-ranked vs everything we track")

# ------------------------------------------- ✦ tailwinds / headwinds
tw = H.get("tailwinds") or []
if tw:
    st.markdown("**✦ Channels — pre-revenue signals from newsflow**")
    _TW = {"revenue": "💰", "shipping": "📦", "announced": "📣",
           "rumor": "💬"}
    for t in tw[:6]:
        icon = "🔻" if t.get("direction") == "headwind" else \
            _TW.get(t.get("tier"), "✦")
        st.caption(
            f"{icon} **{t['channel']}** — `{t['tier']}` · "
            f"{t.get('hit_count',1)} source(s)"
            + (f" — {t['summary']}" if t.get("summary") else ""))
    st.caption("extracted from live catalysts · tiers promote only on "
               "corroboration — rumor→announced→shipping→revenue")

# open thesis watches — falsifiable checks a doc extraction set
for w_ in (H.get("watches") or []):
    st.caption(f"⏳ watching: **{w_['metric']}** "
               f"{w_.get('threshold') or ''} by {w_.get('horizon') or '—'}"
               " — auto-graded when fundamentals refresh")

# 📄 analyze a doc — paste an article; claims must carry verbatim
# quotes (hallucinated evidence is dropped), facts get cross-checked
with st.expander("📄 analyze an article / note into the system"):
    st.caption("Bounded LLM pass — extracts channel claims, mechanisms, "
               "numbered facts, risks, and falsifiable watch items. "
               "No scores, no targets. Channel claims journal into "
               "tailwinds; watches get graded quarterly.")
    _url = st.text_input("url (optional — paywalled sources need "
                         "pasted text)", key="doc_url")
    _title = st.text_input("title", key="doc_title")
    _text = st.text_area("article text", height=180, key="doc_text")
    if st.button("extract claims"):
        with st.spinner("extracting…"):
            res = client.post(
                f"api/v1/board/symbol/{sym}/analyze-doc",
                json_data={"url": _url, "title": _title,
                           "text": _text}, timeout=90)
        if res.get("error"):
            st.error(res["error"])
        else:
            st.markdown(f"**thesis:** {res.get('thesis') or '—'}")
            for c in res.get("claims") or []:
                st.caption(f"`{c.get('type')}` {c.get('text','')[:120]}"
                           + (f" → channel `{c['channel']}` "
                              f"({c.get('tier')})" if c.get('channel')
                              else ""))
            if res.get("journaled_channels"):
                st.success(f"journaled {res['journaled_channels']} "
                           "channel claim(s) into tailwinds")
            if res.get("watches"):
                st.success("watch items set: "
                           + ", ".join(res["watches"]))
            for f_ in res.get("fact_checks") or []:
                mark = {"consistent": "✅"}.get(f_.get("check"), "⚠️")
                st.caption(f"{mark} fact: {f_.get('metric')} = "
                           f"{f_.get('value')} ({f_.get('period') or '—'})"
                           f" → {f_.get('check')}")
            if res.get("dropped"):
                st.caption(f"⚠️ {len(res['dropped'])} claim(s) dropped "
                           "— quote not verbatim in the document")

# ------------------------------------------- ✅ readiness by use case
rd = H.get("readiness") or {}
if rd:
    st.subheader("✅ Readiness — what the technicals allow, per use case")
    st.caption("deterministic checklist on stored engine data — "
               "✓ rule passed · ✗ blocking. The buttons below run the "
               "full engine eval for the authoritative answer.")
    _RI = {"ready": "🟢", "close": "🟡", "no": "🔴"}
    _LBL = {"swing": "🎯 Swing (dip-buy)", "invest": "🏦 Investing",
            "leap_call": "📞 LEAP calls", "leap_put": "📕 LEAP puts"}
    cols = st.columns(4)
    for col, key in zip(cols, ("swing", "invest", "leap_call",
                               "leap_put")):
        r = rd.get(key) or {}
        with col:
            head = (f"{_RI.get(r.get('state'),'⚪')} **{_LBL[key]}"
                    f" — {r.get('state','—')}** ")
            if key == "leap_put" and r.get("band"):
                head += f"({r.get('score','—')}/100 · `{r['band']}`)"
            else:
                head += f"({r.get('score','—')}/{r.get('of','—')})"
            st.markdown(head)
            if key == "leap_put" and r.get("category_note"):
                st.caption(("🅰 " if r.get("category") ==
                            "valuation_put" else "🅱 ")
                           + r["category_note"])
            for rule in r.get("rules") or []:
                st.caption(("✓ " if rule.get("ok") else "✗ ")
                           + rule.get("line", ""))
            if key == "leap_put" and r.get("stage_txt"):
                st.caption("🪜 " + r["stage_txt"])
            # 📋 trade plan — bind the entry to the engine's levels;
            # the plan board tracks stop/targets/trail/time-stop live
            with st.popover("📋 plan"):
                try:
                    sug = client.get(
                        "api/v1/board/trade-plans/suggest",
                        params={"sym": sym, "uc": key}) or {}
                except Exception:
                    sug = {}
                if not sug.get("stop_px"):
                    st.caption("no stored levels — refresh momentum "
                               "first")
                else:
                    st.caption(
                        f"engine suggests — stop **{sug['stop_px']}** "
                        f"(`{sug.get('stop_basis')}`)"
                        + (f" · T1 {sug['target1_px']} · "
                           f"T2 {sug['target2_px']}"
                           if sug.get("target1_px") else "")
                        + f" · trail `{sug.get('trail_rule')}`"
                        + f" · {sug.get('time_stop_days')}d time stop")
                    with st.form(f"plan_{key}"):
                        ep = st.number_input(
                            "entry px", value=float(
                                sug.get("spot") or 0), step=0.01,
                            key=f"ep_{key}")
                        ed = st.date_input(
                            "entry date", key=f"ed_{key}")
                        th = st.text_input(
                            "thesis (1 line)", key=f"th_{key}",
                            placeholder="why this trade, why now")
                        if st.form_submit_button("open plan"):
                            res = client.post(
                                "api/v1/board/trade-plans",
                                json_data={"symbol": sym.upper(),
                                           "use_case": key,
                                           "entry_px": ep,
                                           "entry_date": str(ed),
                                           "thesis": th or None}) or {}
                            if res.get("ok"):
                                st.success(
                                    f"plan #{res.get('id')} open — "
                                    "tracked on Trade Plans")
                            else:
                                st.error(res.get("error") or "failed")
    cat = rd.get("catalyst")
    if cat:
        arrow = "▲" if cat["direction"] == "tailwind" else "▼"
        tag = "corroborated" if cat.get("corroborated") \
            else "single-source"
        st.caption(
            f"{arrow} **channel catalyst** — `{cat['channel']}` at "
            f"`{cat['tier']}` tier, {cat['hits']} source(s) "
            f"({tag}) → conviction ±{abs(cat['bonus']):.0f}. "
            "Leading evidence, not confirmed revenue — a promotion "
            "fires an alert.")
    if (rd.get("leap_put") or {}).get("state") == "no":
        st.caption("📕 note — LEAP puts need extension AND a fresh "
                   "stall; without both the put fights the trend "
                   "(hedge engine's PUT WINDOW rule)")

# ------------------------------------------- 🍴 decision point
# call-ready AND put-watch coexist = a branch state — the arbiter is
# the swing level, not the flags. Show both confirmations + the
# triggers, and the honest default: wait for the level to resolve.
_lc = (rd.get("leap_call") or {}).get("state")
_lp = rd.get("leap_put") or {}
if _lc == "ready" and _lp.get("state") in ("close", "ready"):
    sw_d = (det.get("swing") or {}) if isinstance(det, dict) else {}
    spot_p = H.get("spot")
    st.subheader("🍴 Decision point — both trades are live")
    st.caption("call-ready + put-watch is not a contradiction: the "
               "name sits at a higher-low. The LEVEL decides which "
               "trade you're in — not the flags. Default: no trade "
               "until a trigger resolves.")
    c1, c2 = st.columns(2)
    s_low, conf, avw = (sw_d.get("swing_low"), sw_d.get("confirm_level"),
                        sw_d.get("avwap"))
    with c1:
        st.markdown("**✅ confirm the CALL** (dip-buy wins)")
        if s_low and spot_p:
            st.caption(f"· holds above ${s_low:.2f} swing low — "
                       f"now ${spot_p:.2f} "
                       f"({(spot_p/s_low-1)*100:+.0f}%)")
        else:
            st.caption("· holds above the swing low")
        if conf:
            st.caption(f"· reclaims ${conf:.2f} confirm — higher-low "
                       "turns confirmed")
        if avw:
            st.caption(f"· reclaims ${avw:.2f} AVWAP — buyers back "
                       "in control")
        st.caption("· MACD hist flattens (dir → 0) · dip_phase → "
                   "`confirmed`")
    with c2:
        st.markdown("**🔻 confirm the PUT** (multiple compression)")
        st.caption(f"· PUT_ENTRY {_lp.get('score') or '—'}"
                   f"/100 `{_lp.get('band')}` — needs "
                   "support_breakdown to climb")
        if _lp.get("stage"):
            for s_ in _lp["stage"]:
                st.caption(f"· break ${s_['level']:.2f} "
                           f"({s_['name']}) → tranche {s_['tranche']}")
        st.caption("· hist dir deepens · RS pct slides below 50 · "
                   "level-watch alert pings when price approaches")

# ------------------------------------------------------------ actions
st.divider()
st.subheader("⚡ On demand")
st.caption("recompute against live data — the same code paths the "
           "engines use, run just for this symbol")
a1, a2, a3, a4 = st.columns(4)
with a1:
    if st.button("🔄 refresh technicals", use_container_width=True):
        with st.spinner("fetching bars + recomputing…"):
            try:
                r = client.post(f"api/v1/board/symbol/{sym}/refresh")
                st.success(f"momentum → `{(r or {}).get('state','?')}`")
            except Exception as e:
                st.error(str(e))
        _card.clear()
        st.rerun()
with a2:
    if st.button("🧬 refresh fundamentals", use_container_width=True):
        with st.spinner("rebuilding flywheel + reclassifying…"):
            try:
                r = client.post(
                    f"api/v1/board/symbol/{sym}/fundamentals-refresh")
                st.success(
                    f"fundamentals → `{(r or {}).get('state','?')}`"
                    + (f" · risk {(r or {}).get('risk')}"
                       if (r or {}).get("risk") else ""))
                st.caption(
                    f"rev {_p((r or {}).get('rev_growth'))} · eps "
                    f"{_p((r or {}).get('eps_growth'))} · revisions "
                    f"{_p((r or {}).get('est_revision_pct'))}")
            except Exception as e:
                st.error(str(e))
        _card.clear()
        st.rerun()
with a3:
    if st.button("🎯 swing check", use_container_width=True):
        with st.spinner("running the real screener eval…"):
            try:
                r = client.get(f"api/v1/board/symbol/{sym}/swing-check")
                if r and r.get("setup_type"):
                    st.success(
                        f"`{r['setup_type']}` score {r.get('score')} · "
                        f"perm {r.get('stock_permission')} · "
                        f"quality {r.get('quality')}")
                    st.caption(
                        f"entry {r.get('entry')} · stop {r.get('stop')} "
                        f"· target {r.get('target')} · RSI "
                        f"{(r.get('rsi') or 0):.0f} · "
                        f"{r.get('reasons') or ''}")
                else:
                    st.info((r or {}).get("note", "no setup"))
            except Exception as e:
                st.error(str(e))
with a4:
    if st.button("🎲 options screen", use_container_width=True):
        with st.spinner("screening LEAPS chain…"):
            try:
                r = client.get(
                    f"api/v1/board/symbol/{sym}/options-screen")
                if r and r.get("verdict"):
                    st.success(f"verdict: `{r['verdict']}`"
                               + (f" · IV rank {r.get('iv_rank')}"
                                  if r.get("iv_rank") is not None else ""))
                    for a in (r.get("actions") or [])[:3]:
                        st.caption(f"→ {a}")
                    for why in (r.get("reasons") or [])[:5]:
                        st.caption(f"· {why}")
                    t2 = r.get("technicals") or {}
                    if t2:
                        st.caption(
                            f"RSI {t2.get('rsi','—')} · %B "
                            f"{t2.get('pct_b','—')} · vs50 "
                            f"{t2.get('vs_sma50','—')}")
                    n_c = sum(len(e.get("calls") or [])
                              for e in (r.get("expiries") or []))
                    n_p = sum(len(e.get("puts") or [])
                              for e in (r.get("expiries") or []))
                    st.caption(f"chain: {len(r.get('expiries') or [])} "
                               f"expiries · {n_c} calls · {n_p} puts "
                               f"scored")
                else:
                    st.info("no chain / no verdict")
            except Exception as e:
                st.error(str(e))

st.caption("advisory — every read composes what the engines already "
           "compute; nothing here executes or recommends size")

# ------------------------------------------- 📊 plain-english technicals
with st.expander("📊 what each indicator is saying", expanded=True):
    if not det:
        st.caption("no technicals stored — press 🔄 refresh technicals")
    else:
        rsi, rd = det.get("rsi"), det.get("rsi_dir")
        hist, hd = det.get("hist"), det.get("hist_dir")
        pb, v50, v200 = det.get("pct_b"), det.get("vs_sma50"), \
            det.get("vs_sma200")
        dd, atr = det.get("dd52w"), det.get("atr_pct")
        vd = det.get("vol_dip"); vpr = (det.get("swing") or {}).get(
            "vol_pullback_vs_rally")
        sw = det.get("swing") or {}

        def _arrow(d):
            return " ↑ rising" if (d or 0) > 1 else \
                " ↓ falling" if (d or 0) < -1 else " → flat"

        c1, c2 = st.columns(2)
        with c1:
            if rsi is not None:
                z = ("washed (<30)" if rsi < 30 else
                     "weak (30–45)" if rsi < 45 else
                     "neutral (45–55)" if rsi < 55 else
                     "strong (55–70)" if rsi < 70 else
                     "overbought (>70)")
                note = ("sellers exhausted — bounce candidates live here"
                        if rsi < 30 else
                        "favoring sellers but not extreme" if rsi < 45 else
                        "nothing extreme — mid-band resting"
                        if rsi < 55 else
                        "buyers in control" if rsi < 70 else
                        "stretched — entries here chase, not buy")
                st.markdown(f"**RSI(14) {rsi:.0f}** — {z}{_arrow(rd)}"
                            f" — {note}")
            if hist is not None:
                dirn = ("still fading — the dip isn't done until the "
                        "histogram flattens"
                        if hd is not None and hd < -0.5 else
                        "sell pressure easing — histogram turning "
                        "toward zero"
                        if hd is not None and hd > 0.5 else
                        "flat — momentum balanced")
                word = "negative" if hist < 0 else "positive"
                st.markdown(f"**MACD histogram {hist:.2f}** — {word}, "
                            f"{dirn}")
            if pb is not None:
                z = ("above the upper band — euphoric, stretched"
                     if pb > 0.95 else
                     "upper half — healthy strength" if pb > 0.5 else
                     "lower half — washed but above the lower rail"
                     if pb > 0.05 else
                     "at/below the lower band — free-fall territory")
                st.markdown(f"**Bollinger %B {pb:.2f}** — {z}")
            if v50 is not None or v200 is not None:
                a = ("above" if (v50 or 0) > 0 else "below")
                b = ("above" if (v200 or 0) > 0 else "below")
                trend = ("uptrend frame intact — short-term dip inside "
                         "a longer climb"
                         if (v50 or 0) > 0 and (v200 or 0) > 0 else
                         "below the 200dma — trend broken; bounces are "
                         "suspicious until reclaimed"
                         if (v200 or 0) < 0 else
                         "between the averages — transition zone")
                st.markdown(
                    f"**vs 50dma {((v50 or 0)*100):+.1f}% · "
                    f"vs 200dma {((v200 or 0)*100):+.1f}%** — {a} the "
                    f"50, {b} the 200 — {trend}")
        with c2:
            if dd is not None:
                st.markdown(
                    f"**{dd*100:+.0f}% off the 52w high** — " +
                    ("a scratch — near highs" if dd > -0.05 else
                     "a normal pullback" if dd > -0.15 else
                     "a real drawdown — the dip is substantial"
                     if dd > -0.35 else
                     "a deep wash — trend usually broken this far down"))
            if atr is not None:
                st.markdown(
                    f"**ATR {atr*100:.1f}%** — daily range is ~"
                    f"{atr*100:.0f}% of price — " +
                    ("calm name — tight stops viable" if atr < 0.02 else
                     "normal vol — a 1×ATR stop sits ~"
                     f"{atr*100:.0f}% away" if atr < 0.04 else
                     "hot name — size down; tight stops get noise-stopped"))
            if vd is not None or vpr is not None:
                vtxt = (f"dip volume {vd:.2f}× avg" if vd is not None
                        else "")
                ptxt = (f", pullback-vs-rally volume {vpr:.2f}"
                        if vpr is not None else "")
                note = ("sellers drying up vs the rally — exhaustion "
                        "signature" if (vpr or 1) < 0.8 else
                        "pullback volume still heavy — sellers not done")
                st.markdown(f"**Volume** — {vtxt}{ptxt} — {note}")
            ph = det.get("dip_phase"); dh = det.get("dip_health")
            if ph:
                st.markdown(
                    f"**Dip phase `{ph}`** (health {dh}/5, "
                    f"low-streak {det.get('low_streak','—')}) — " +
                    {"washing": "still falling — no base yet",
                     "stabilizing": "early turn attempt — forming a "
                                    "low, not confirmed",
                     "turning_up": "momentum hooking up off the low — "
                                   "the constructive phase",
                     "confirmed": "the dip resolved up — the move "
                                  "already happened"}.get(
                        str(ph), "watch"))
            if sw:
                conf = "confirmed" if sw.get("confirmed") else \
                    f"not confirmed — needs {sw.get('confirm_level','—')}"
                av = (f"AVWAP ${sw['avwap']}"
                      f" ({'reclaimed' if sw.get('avwap_reclaimed') else 'not reclaimed'})"
                      if sw.get("avwap") else "")
                st.markdown(
                    f"**Swing `{sw.get('phase','—')}`** — {conf} · "
                    f"{av} · support ${sw.get('support_px','—')} · "
                    f"prior low ${sw.get('prior_low','—')}")
