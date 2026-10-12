"""LEAPS Screener — deep-ITM long-dated option picks per symbol.

Technicals drive the direction verdict (CALL / PUT / WAIT); the chain
(yfinance, >400 DTE) is enriched with Black-Scholes delta/theta on each
contract's own IV and ranked by a desk-style score: delta closeness,
extrinsic drag, spread, liquidity, IV-vs-realized-vol discipline.
"""
import sys
import os

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import APIClient
from api_config import api_config
from utils import render_top_nav, health_col, health_cfg, sym_md

client = APIClient(api_config.python_worker_url, timeout=180)

st.set_page_config(page_title="LEAPS Options", page_icon="📜", layout="wide")
render_top_nav()
st.title("📜 LEAPS Screener")
st.caption("Long-dated calls/puts (>400 DTE) — deep-ITM stock replacement "
           "with leverage. Score = delta fit (35) + low extrinsic (25) + "
           "tight spread (15) + liquidity (15) + IV discipline (10).")

# --- 🎯 put-candidate universe — WHICH names deserve a put screen --------
# put-worthiness: high beta to QQQ, high realized vol, IV in the sweet
# spot (ranked high enough to matter, not so high the entry's crushed),
# rich valuation, expectation fragility. Entry timing is the phase
# engine's job below — this is the candidate list.
with st.expander("🎯 Put candidates — which names deserve a screen",
                 expanded=False):
    if st.button("scan universe", key="pu_scan"):
        st.session_state["put_uni"] = client.get(
            "api/v1/board/put-universe")
    _pu = st.session_state.get("put_uni")
    if _pu:
        st.caption("score = beta 25 + realized-vol 20 + IV sweet-spot 20 "
                   "+ valuation 20 + expectation-risk 15 · "
                   "**conv** = (β×HV)÷IV — expected downside move per "
                   "dollar of premium · IV/HV ~1.0 = fairly priced vol, "
                   "1.4+ = paying a volatility premium")
        _tier_icon = {"prime": "🔴", "watch": "🟡", "poor": "⚪",
                      "no": "⚪"}
        for _r in (_pu.get("rows") or [])[:15]:
            _ivhv = _r.get("iv_hv")
            _conv = _r.get("convexity")
            _thin = " 🚫thin-chain" if _r.get("thin_chain") else ""
            st.caption(
                f"{_tier_icon.get(_r['tier'], '⚪')} "
                f"**{sym_md(_r['symbol'])}** {_r['score']:.0f} "
                f"({_r['tier']}){_thin} · β {_r.get('beta') or '—'} · "
                f"HV {_r.get('hv20') or '—'} · "
                f"IV/HV {_ivhv if _ivhv is not None else '—'} · "
                f"conv {_conv if _conv is not None else '—'} · "
                f"PE {_r.get('fwd_pe') or '—'} · "
                f"`{_r.get('momentum') or '—'}`")
        if _pu.get("prime"):
            st.caption("prime = put-quality profile; still needs the "
                       "tape stall/crack trigger before entry")

# --- inputs ------------------------------------------------------------------
_c1, _c2, _c3, _c4 = st.columns([2, 1, 1, 1])
_sym = _c1.text_input("Symbol", value="AMD", key="leaps_sym").strip().upper()
_beta = _c2.number_input("Beta (0 = auto from profile)", value=0.0,
                         step=0.05, format="%.2f", key="leaps_beta")
_rf = _c3.number_input("Risk-free %", value=4.5, step=0.25,
                     format="%.2f", key="leaps_rf")
_run = _c4.button("🔍 Screen", type="primary", key="leaps_run")

# --- 📡 tracked-name phase sweep — who's in CALL zone vs PUT zone ----
# Same verdict path as the single-symbol screen (technicals +
# fundamentals gate + cyclicality), minus the chain pull.
if st.button("📡 Scan tracked names (portfolio · watchlist · boards)",
             key="phase_scan_run"):
    with st.spinner("Phase-sweeping tracked symbols — no option chains, "
                    "still ~1-2s per name…"):
        try:
            st.session_state["phase_scan"] = client.get(
                "api/v1/options/phase-scan")
        except Exception as e:
            st.error(f"Scan failed: {e}")
_ps = st.session_state.get("phase_scan")
if _ps:
    _cnt = _ps.get("counts") or {}
    _mkt = _ps.get("market") or {}
    if _mkt:
        # tape = the canonical posture read (same engine the Daily
        # Board, calls/puts and the capital planner obey)
        _tape_icon = {"aggressive": "🟢🟢", "constructive": "🟢",
                      "neutral": "⚪", "caution": "🟡",
                      "defensive": "🔴", "risk-on": "�",
                      "elevated-vol": "🟡", "risk-off": "🔴"}.get(
                      _mkt.get("tape"), "⚪")
        _po = (f" · posture of {_mkt['posture_as_of']}"
               if _mkt.get("posture_as_of") else "")
        st.info(f"{_tape_icon} **Posture:** {_mkt.get('tape')}"
                f"{_po} — SPY {_mkt.get('spy_vs_sma200')}% vs 200dma · "
                f"VIX {_mkt.get('vix')} — {_mkt.get('note')}")

    def _row(r):
        d_out = None
        if r.get("next_earnings"):
            try:
                d_out = (pd.Timestamp(r["next_earnings"]).date()
                         - pd.Timestamp.now().date()).days
            except Exception:
                d_out = None
        _mom_i = {"climax": "🔥", "breakout": "🚀", "uptrend": "📈",
                  "recovery": "🌱", "basing": "😴", "pullback": "🟢",
                  "rolling_over": "🟠", "knife": "🔪",
                  "capitulation": "💥", "breakdown": "⬇️",
                  "downtrend": "📉"}
        return {
            "symbol": r["symbol"],
            "mom": (f"{_mom_i.get(r.get('momentum'), '⚪')} "
                    f"{r.get('momentum')}") if r.get("momentum")
                   else "—",
            "stage": r.get("stage"),
            "px": r.get("spot"),
            "RSI": round(r["rsi"]) if r.get("rsi") else None,
            "%B": round(r["pct_b"], 2) if r.get("pct_b") is not None
                  else None,
            "vs200%": round((r.get("vs_sma200") or 0) * 100, 1),
            "52wH%": round((r.get("dd52w") or 0) * 100, 1),
            "cycl": "♻" if r.get("cyclical") else "",
            "gap": r.get("gap_score"),
            "earn": (f"📅{d_out}d" if d_out is not None
                     and 0 <= d_out <= 21 else ""),
            "boards": r.get("boards"),
            "why": (r.get("why") or "")[:70],
            "blocked": (r.get("blocks") or "")[:60]}

    _pc, _pp = st.columns(2)
    with _pc:
        st.success(f"🟢 CALL zone — washed inside uptrend "
                   f"({_cnt.get('calls', 0)})")
        if _ps.get("calls"):
            st.dataframe(
                health_col(pd.DataFrame(
                    [_row(r) for r in _ps["calls"]])),
                column_config={"🩺": health_cfg()},
                use_container_width=True, hide_index=True)
        else:
            st.caption("none right now")
    with _pp:
        st.error(f"🔴 PUT zone — extended + stalling "
                 f"({_cnt.get('puts', 0)})")
        if _ps.get("puts"):
            st.dataframe(
                health_col(pd.DataFrame(
                    [_row(r) for r in _ps["puts"]])),
                column_config={"🩺": health_cfg()},
                use_container_width=True, hide_index=True)
        else:
            st.caption("none right now")
    with st.expander(f"🟡 watching / waiting ({_cnt.get('watch', 0)}) · "
                     f"⛔ fundamentals-gated ({_cnt.get('skipped', 0)})"
                     + (f" · ⏳ cooldown ({_cnt.get('cooling', 0)})"
                        if _cnt.get('cooling') else "")):
        for r in (_ps.get("cooling") or []):
            st.caption(f"⏳ `{r['symbol']}` — {r.get('verdict')} "
                       f"signal suppressed: {r.get('cooldown_reason')} "
                       f"on {r.get('cooldown_until')} — book memory "
                       "blocks re-entry at a level that just failed")
        for r in (_ps.get("watch") or []) + (_ps.get("skipped") or []):
            st.caption(f"`{r['symbol']}` — {r.get('stage')}"
                       + (f" · {r['blocks']}" if r.get("blocks") else "")
                       + (f" ({r['boards']})" if r.get("boards") else ""))
    st.caption("verdict = same engine as the single-symbol screen · "
               "♻ cyclical (puts on tape alone) vs structural (puts "
               "need deterioration) · 📅 = earnings ≤3w (IV-crush "
               "risk on calls) · ⏳ = post-failure cooldown from the "
               "book · screen a name below for contracts")
    st.divider()

# --- 📒 LEAPS book — positions + exit alerts (the memory layer) ----------
_bc1, _bc2, _bc3 = st.columns([2, 1, 1])
_bc1.markdown("### 📒 LEAPS book — sequential convexity positions")
if _bc2.button("📓 Load book", key="book_load"):
    try:
        st.session_state["leaps_book"] = client.get(
            "api/v1/options/leaps-book")
    except Exception as e:
        st.error(f"book load failed: {e}")
if _bc3.button("💹 Mark + evaluate", key="book_mark"):
    with st.spinner("repricing open positions…"):
        try:
            st.session_state["leaps_book"] = client.get(
                "api/v1/options/leaps-book?mark=true")
        except Exception as e:
            st.error(f"mark failed: {e}")
_book = st.session_state.get("leaps_book")
if _book:
    _mk = _book.get("mark") or {}
    for a in (_mk.get("alerts") or []):
        st.warning(f"**{a['symbol']} {a['side']}** ({a['pnl_pct']}%): "
                   f"{a['alert']}")
    _opens = _book.get("open") or []
    if _opens:
        _orow = [{"sym": p["stock_symbol"], "side": p["side"],
                  "K": f"${float(p['strike']):.0f}",
                  "exp": str(p["expiry"]),
                  "entry": (f"${float(p['entry_mid']):.2f}"
                            if p.get("entry_mid") else "—"),
                  "mark": (f"${float(p['mark_mid']):.2f}"
                           if p.get("mark_mid") else "—"),
                  "P&L%": p.get("unrealized_pct"),
                  "stage": p.get("thesis_stage"),
                  "ladder": "·".join(p.get("ladder_fired") or []),
                  "alert": (p.get("exit_alert") or "")[:60],
                  "id": p["id"]}
                 for p in _opens]
        st.dataframe(pd.DataFrame(_orow), use_container_width=True,
                     hide_index=True)
        _cl1, _cl2, _cl3 = st.columns([1, 1, 2])
        _cid = _cl1.number_input("close id", min_value=0, step=1,
                                 key="book_close_id",
                                 help="id column from the table")
        _creason = _cl2.selectbox(
            "reason", ["manual", "climax_tp", "stall_tp",
                       "capitulation_tp", "invalidated",
                       "thesis_broken", "time_stop"],
            key="book_close_reason")
        if _cl3.button("close position", key="book_close_btn"):
            try:
                client.post(
                    f"api/v1/options/leaps-book/close/{int(_cid)}"
                    f"?reason={_creason}")
                st.session_state.pop("leaps_book")
                st.rerun()
            except Exception as e:
                st.error(f"close failed: {e}")
    else:
        st.caption("no open positions — screen a name, take a pick, "
                   "record it below")
    _st = _book.get("stats") or {}
    if _st.get("closed"):
        st.caption(f"closed {_st['closed']} · win rate "
                   f"{_st.get('win_rate')}% · avg realized "
                   f"{_st.get('avg_realized'):+.0f}%")
    if _book.get("cooldowns"):
        st.caption("⏳ cooldowns: " + " · ".join(
            f"`{s}` ({c['reason']}, until {c['until']})"
            for s, c in _book["cooldowns"].items()))

    with st.expander("➕ record a position (you placed the trade "
                     "— log it here)"):
        _d = st.session_state.get("leaps_data") or {}
        _f1, _f2, _f3, _f4 = st.columns(4)
        _nsym = _f1.text_input("symbol", value=_d.get("symbol", ""),
                               key="nb_sym").strip().upper()
        _nside = _f2.selectbox("side", ["CALL", "PUT"], key="nb_side")
        _nexp = _f3.text_input("expiry (YYYY-MM-DD)", key="nb_exp",
                               value=str((_d.get("expiries") or [{}])
                                         [0].get("expiry", "")))
        _nk = _f4.number_input("strike", min_value=0.0, step=5.0,
                               key="nb_k")
        _g1, _g2, _g3, _g4 = st.columns(4)
        _nmid = _g1.number_input("entry mid ($/sh)", min_value=0.0,
                                 step=0.5, key="nb_mid")
        _nspot = _g2.number_input("spot at entry", min_value=0.0,
                                  step=1.0, key="nb_spot",
                                  value=float(_d.get("spot") or 0))
        _nn = _g3.number_input("contracts", min_value=1, step=1,
                               key="nb_n")
        _nhi = _g4.number_input("pre-stall 60d high (puts)", 0.0,
                                step=1.0, key="nb_hi")
        if st.button("📥 open book entry", key="nb_open"):
            try:
                client.post("api/v1/options/leaps-book/open", json={
                    "symbol": _nsym, "side": _nside, "expiry": _nexp,
                    "strike": _nk, "contracts": int(_nn),
                    "entry_mid": _nmid or None,
                    "entry_spot": _nspot or None,
                    "thesis_stage": _d.get("cycle_stage"),
                    "gap_score": (_d.get("fundamentals") or {})
                    .get("gap_score"),
                    "cyclical": _d.get("cyclical"),
                    "entry_hi_60d": _nhi or None})
                st.session_state.pop("leaps_book", None)
                st.success("recorded — book will mark it on next load")
            except Exception as e:
                st.error(f"record failed: {e}")
    st.divider()

if _run and _sym:
    try:
        params = f"?symbol={_sym}&risk_free={_rf / 100:.4f}"
        if _beta:
            params += f"&beta={_beta}"
        st.session_state["leaps_data"] = client.get(
            f"api/v1/options/leaps{params}")
    except Exception as e:
        st.error(f"Screen failed: {e}")

d = st.session_state.get("leaps_data")
if not d:
    st.info("Enter a symbol and hit 🔍 Screen — the chain pull takes a "
            "few seconds (one fetch per expiry).")
    st.stop()

if d.get("error"):
    st.error(d["error"])
    st.stop()

# --- verdict + technicals -----------------------------------------------------
V = {"CALL": "🟢", "PUT": "🔴", "WAIT": "🟡", "SKIP": "⛔"}
CYCLE = {"pullback_in_uptrend": "pullback inside uptrend → CALLS "
         "(ride back to highs)",
         "ath_extension": "ATH extension + stall → PUTS "
         "(harvest the pullback)",
         "extended": "extended above band + stall → PUTS",
         "climax": "EUPHORIA — trim calls 50-70%, no new entries",
         "climax_structural": "stall at extension but fundamentals "
         "intact → exit calls, NO puts (structural name)",
         "extended_no_stall": "extended, still ripping — wait for "
         "the stall before puts",
         "falling_knife": "washed but still collapsing — let it base",
         "wash_not_stabilized": "washed but MACD hist still falling — "
         "wait for momentum to stop bleeding (dead-cat filter)",
         "stale_stall": "extended, but the momentum crack is old — "
         "the put window was the crack day; wait for next extension",
         "mid_range": "mid-range — wait for the cycle",
         "downtrend": "below SMA200 — trend broken, not a pullback",
         "disqualified": "fundamentals too weak for this strategy",
         "unknown": ""}
t = d.get("technicals") or {}
f = d.get("fundamentals") or {}
st.subheader(f"{V.get(d['verdict'], '⚪')} {d['symbol']} @ "
             f"${d['spot']} → **{d['verdict']}** "
             f"· beta {d.get('beta') or 'n/a'}"
             + (f" · mom **{d['momentum']}**"
                if d.get("momentum") else ""))
if d.get("cycle_stage"):
    st.caption(f"**Cycle:** {CYCLE.get(d['cycle_stage'], d['cycle_stage'])}"
               + (" · cyclical name — full rotation allowed"
                  if d.get("cyclical")
                  else " · structural — puts need fundamental "
                       "deterioration"))
cyc = d.get("cyclicality") or {}
_ov1, _ov2 = st.columns([3, 1])
_ov1.caption(
    f"**Cyclicality:** {'cyclical' if d.get('cyclical') else 'structural'}"
    f" ({cyc.get('source', '?')}"
    + (f"·{cyc.get('confidence')}" if cyc.get("confidence") else "")
    + ")"
    + (f" — {cyc['rationale']}" if cyc.get("rationale") else ""))
_ov = _ov2.selectbox("override", ["—", "cyclical", "structural",
                                  "reset→agent"],
                     key="leaps_cyc_override",
                     label_visibility="collapsed")
if _ov != "—":
    try:
        if _ov == "reset→agent":
            client.delete(f"api/v1/options/cyclicality/{d['symbol']}")
        else:
            client.post("api/v1/options/cyclicality",
                        json={"symbol": d["symbol"],
                              "cyclical": _ov == "cyclical"})
        st.session_state.pop("leaps_data")
        st.rerun()
    except Exception as e:
        st.error(f"override failed: {e}")
if d.get("vol_regime"):
    st.caption(f"**Vol:** {d['vol_regime']}")
if d.get("actions"):
    st.markdown("**Playbook:**")
    for a in d["actions"]:
        st.caption("▸ " + a)
if f:
    st.caption(
        f"**Fundamentals gate:** {'✅ solid' if f.get('solid') else '❌ fails'} — "
        f"rev {(f.get('rev_growth') or 0) * 100:+.0f}% · "
        f"GM {(f.get('gross_margin') or 0) * 100:.0f}% · "
        f"op {(f.get('op_margin') or 0) * 100:+.0f}%"
        + (f" · expectation-gap {f['gap_score']:.0f}/100"
           + (f" · {f['beat_streak']}Q beat streak"
              if f.get('beat_streak') else "")
           + (f" · est rev {(f['est_revision_pct'] or 0)*100:+.0f}%"
              if f.get('est_revision_pct') is not None else "")
           if f.get('gap_score') is not None else "")
        + (f" · 📅 earnings {f['next_earnings']}"
           + (f" (est ${f['next_earnings_eps_est']:.2f})"
              if f.get('next_earnings_eps_est') else "")
           if f.get('next_earnings') else "")
        + (f" · boards: {', '.join(f['engine_membership'])}"
           if f.get('engine_membership') else ""))
for r in d.get("reasons", []):
    st.caption("• " + r)

cols = st.columns(8)
def _chip(c, label, val, fmt="{:.1f}"):
    c.metric(label, fmt.format(val) if isinstance(val, (int, float))
             else "—")
_chip(cols[0], "RSI14", t.get("rsi14"))
_chip(cols[1], "MACD hist", t.get("macd_hist"), "{:.2f}")
_chip(cols[2], "BB %B", (t.get("bollinger") or {}).get("pct_b"),
      "{:.2f}")
_chip(cols[3], "vs SMA50", (t.get("vs_sma50") or 0) * 100
      if t.get("vs_sma50") is not None else None, "{:+.1f}%")
_chip(cols[4], "vs SMA200", (t.get("vs_sma200") or 0) * 100
      if t.get("vs_sma200") is not None else None, "{:+.1f}%")
_chip(cols[5], "HV20", (t.get("hv20") or 0) * 100
      if t.get("hv20") else None, "{:.0f}%")
_chip(cols[6], "ATR%", (t.get("atr_pct") or 0) * 100
      if t.get("atr_pct") else None, "{:.1f}%")
_chip(cols[7], "1m perf", (t.get("perf_1m") or 0) * 100
      if t.get("perf_1m") is not None else None, "{:+.0f}%")

bb = t.get("bollinger") or {}
st.caption(f"Bollinger(20,2σ): lower ${bb.get('lower', 0):.2f} · "
           f"mid ${bb.get('mid', 0):.2f} · upper ${bb.get('upper', 0):.2f}"
           if bb else "")

# --- contracts ----------------------------------------------------------------
_exps = d.get("expiries", [])
_max_dte = max((e["dte"] for e in _exps), default=0)
for ex in _exps:
    _th = ((ex.get("safe_pick_call") or {}).get("theta_annual_pct"))
    _theta_note = (f" · θ {_th:.0f}%/yr" if _th else "")
    _far = " ⟳ farthest — lowest decay" if ex["dte"] == _max_dte else ""
    with st.expander(
            f"📅 {ex['expiry']} — {ex['dte']}d ({ex['dte']/365:.1f}y)"
            f"{_theta_note}{_far} "
            f"({ex['n_calls_scanned']}C/{ex['n_puts_scanned']}P scanned)",
            expanded=ex == _exps[0]):
        for side, key, icon in (("calls", "calls", "📈 CALLS"),
                                ("puts", "puts", "📉 PUTS")):
            rows = ex.get(key)
            if not rows:
                if key == "calls" and ex.get("chain_note"):
                    st.caption("📈 CALLS — " + ex["chain_note"])
                continue
            st.markdown(f"**{icon}**")
            df = pd.DataFrame(rows)
            _cols = ["contract", "strike", "moneyness", "mid", "delta",
                     "theta_day", "theta_annual_pct", "iv", "iv_vs_hv",
                     "extrinsic_pct", "spread_pct", "oi", "volume",
                     "breakeven", "breakeven_vs_spot", "gearing",
                     "score"]
            if key == "calls":
                _cols += ["gamma", "roi_flip15", "roi_flip30",
                          "roi_dn10", "roi_hi52", "roi_30", "roi_50",
                          "roi_60", "roi_100", "ev_roi", "p_profit"]
            df["strike"] = df.apply(
                lambda r: (f"${r['strike']:.0f}"
                           + (" ◀ spot" if r.get("moneyness") == "ATM"
                              else "")), axis=1)
            df = df[[c for c in _cols if c in df.columns]].rename(columns={
                "theta_day": "θ/day", "theta_annual_pct": "θ/yr%",
                "iv": "IV%", "iv_vs_hv": "IV/HV", "gamma": "γ",
                "extrinsic_pct": "extr%", "spread_pct": "sprd%",
                "oi": "OI", "breakeven": "BE",
                "breakeven_vs_spot": "BE vs spot%",
                "roi_flip15": "+15%·60d", "roi_flip30": "+30%·60d",
                "roi_dn10": "−10%·60d",
                "roi_hi52": "ROI@52wH", "roi_30": "ROI@+30%",
                "roi_50": "ROI@+50%", "roi_60": "ROI@+60%",
                "roi_100": "ROI@+100%", "ev_roi": "EV%",
                "p_profit": "P(profit)%"})
            st.dataframe(df, use_container_width=True, hide_index=True)
            top = rows[0]
            st.caption(
                f"⭐ best {key[:-1]}: **{top['contract']}** — "
                f"δ {top['delta']:+.2f}, {top['extrinsic_pct']:.0f}% "
                f"extrinsic, gearing {top['gearing']:.1f}x, BE "
                f"{top['breakeven_vs_spot']:+.0f}% vs spot, θ drag "
                f"{top['theta_annual_pct'] or 0:.0f}%/yr, OI {top['oi']}")
            if key == "calls":
                # merge labels when independent criteria land on the
                # same contract — two identical lines is noise
                _picks = [
                    ("flip_pick_call", "⚡ flip (1-2mo)",
                     "δ0.55-0.85 ranked by BS-repriced +15%-in-60d "
                     "ROI — the contract for your actual exit "
                     "horizon; −10%·60d column is the honest downside"),
                    ("balanced_pick_call", "⚖️ balanced",
                     "max expected ROI w/ ≥40% chance of profit and "
                     "≤65% extrinsic — the leverage sweet spot"),
                    ("growth_pick_call", "🚀 growth",
                     "max expected ROI w/ ≥45% chance of ITM — less "
                     "capital, more upside if the thesis plays, but "
                     "mostly extrinsic and faster decay"),
                    ("burst_pick_call", "💥 burst",
                     "slightly-ITM δ0.55-0.75 ranked by +50% scenario "
                     "ROI — the dip-buy contract for encashing growth "
                     "quickly; moderate extrinsic, less IV-crush "
                     "exposed than pure ATM"),
                    ("atm_pick_call", "🎯 ATM",
                     "nearest strike to spot — max gamma, ~100% "
                     "extrinsic: cheapest capital + sharpest spike "
                     "response, but full IV-crush exposure (enter "
                     "quiet/post-earnings)")]
                _seen = {}
                for pick, label, note in _picks:
                    pp = ex.get(pick)
                    if not pp:
                        continue
                    _cid = pp.get("contract")
                    if _cid in _seen:
                        _seen[_cid][0] += " = " + label
                        _seen[_cid][2] += " · also " + note
                    else:
                        _seen[_cid] = [label, pp, note]
                for _cid, (label, pp, note) in _seen.items():
                    _extra = (f" · +15%/60d→{pp.get('roi_flip15')}% · "
                              f"−10%/60d→{pp.get('roi_dn10')}% · "
                              f"+50%→{pp.get('roi_50')}% · "
                              f"+100%→{pp.get('roi_100')}%")
                    st.caption(
                        f"{label}: **{pp['contract']}** — "
                        f"${pp.get('capital', 0):,}/contract "
                        f"(δ {pp['delta']:+.2f}, γ {pp.get('gamma')}, "
                        f"extr {pp['extrinsic_pct']:.0f}%) · EV "
                        f"{pp.get('ev_roi')}% · P(profit) "
                        f"{pp.get('p_profit')}%{_extra} · BE "
                        f"${pp['breakeven']:.0f} — {note}")
                st.caption("EV/P(profit) modeled at +25%/yr drift on "
                           "each contract's IV — thesis-dependent, not "
                           "a guarantee")
            for sp_key, sp_label in (
                    ("call_spread", "📈 CALL debit spread"),
                    ("put_spread", "📉 PUT debit spread")):
                sp = ex.get(sp_key)
                if not sp:
                    continue
                st.caption(
                    f"{sp_label}: buy **{sp['buy']}** "
                    f"(${sp['buy_strike']:.0f} δ{sp['buy_delta']:+.2f}) "
                    f"/ sell **{sp['sell']}** "
                    f"(${sp['sell_strike']:.0f} δ{sp['sell_delta']:+.2f}) "
                    f"— net debit ${sp['net_debit']:.2f} "
                    f"(${sp['capital']:,}), max gain ${sp['max_gain']:.2f} "
                    f"(ROI {sp.get('roi_max')}%), "
                    f"{sp.get('vs_straight_premium')}% cheaper than "
                    "the straight contract")

st.caption(f"as of {d.get('as_of', '')[:19]} · chain: yfinance · "
           "greeks: Black-Scholes on contract IV · filters: OI≥25, "
           "spread≤25%, mid≥$0.50")
