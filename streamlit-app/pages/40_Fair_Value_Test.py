# -*- coding: utf-8 -*-
"""Fair Value Test — run the v2 engine on demand for a watchlist and
inspect the full chain: classification → method blend → scenarios →
decision layer (buy_below / MoS / confidence / risk flags) → macro
stress. Every number is deterministic engine output; nothing here
trades.
"""
from __future__ import annotations

import streamlit as st

from api_client import APIClient
from api_config import api_config

st.set_page_config(page_title="Fair Value Test", page_icon="🎯",
                   layout="wide")
client = APIClient(api_config.python_worker_url, timeout=180)

DEFAULT_UNIVERSE = ["MCD", "NBIS", "MRVL", "NVDA", "GOOGL", "CRDO",
                    "NKE", "JPM", "COIN", "RIVN", "SOFI", "ALGM", "RZLV"]

st.title("🎯 Fair Value — engine test")
st.caption("Deterministic v2 run per symbol: archetype → methods → "
           "bear/base/bull/explosive → probability-weighted EV → "
           "margin-of-safety buy gate → AI-capex stress. "
           "force-refresh recomputes even when a fresh stored run exists.")

syms = st.multiselect("Universe", DEFAULT_UNIVERSE +
                      [""], default=DEFAULT_UNIVERSE)
extra = st.text_input("add symbol", placeholder="e.g. TSLA").strip().upper()
if extra and extra not in syms:
    syms.append(extra)
force = st.checkbox("force refresh (ignore cached runs)", value=True)


def _run(s: str):
    return client.post("api/v1/fundamentals/fair-value-v2/run",
                       json_data={"symbol": s, "force_refresh": force})


if st.button("▶ calculate", type="primary", use_container_width=True):
    results = {}
    prog = st.progress(0.0)
    for i, s in enumerate(syms):
        if not s:
            continue
        with st.spinner(f"{s}…"):
            try:
                results[s] = _run(s)
            except Exception as e:
                results[s] = {"success": False, "error": str(e)}
        prog.progress((i + 1) / max(len(syms), 1))
    prog.empty()
    st.session_state["fv_test"] = results

# ------------------------------------------------ engine backtest
# Replays every stored fv run against realized prices — fv bias/MAE,
# bear-breach calibration, buy_below gate reach, and forward returns
# inside vs outside the gate. Read-only, safe to run any time.
with st.expander("📐 engine backtest — did stored FVs & gates predict?",
                 expanded=False):
    bc1, bc2, bc3 = st.columns([2, 1, 1])
    with bc1:
        _bt_sym = st.text_input("symbol (blank = all runs)",
                                key="bt_sym").strip().upper() or None
    with bc2:
        _bt_hz = st.text_input("horizons (days)", "90,180,365",
                               key="bt_hz")
    with bc3:
        st.write("")
        _go = st.button("▶ run backtest", key="bt_go")
    if _go:
        try:
            _r = client.get("admin/fair-value-v2/backtest", params={
                "symbol": _bt_sym or "", "horizons": _bt_hz})
            st.session_state["fv_bt"] = _r
        except Exception as e:
            st.session_state["fv_bt"] = {"success": False, "error": str(e)}
    _bt = st.session_state.get("fv_bt") or {}
    if _bt.get("success") and (_bt.get("result") or {}).get("horizons"):
        st.caption(f"{_bt['result']['total_runs']} stored runs evaluated")
        import pandas as _pd
        _f = lambda x: f"{x:+.1%}" if x is not None else "—"
        _g = lambda x: f"{x:.0%}" if x is not None else "—"
        _rows = [{
            "horizon": f"{h['days']}d", "n": h["n"],
            "fv_bias": _f(h["fv_bias"]), "fv_mae": _f(h["fv_mae"]),
            "bear breach (target ~25%)": _g(h["bear_breach"]),
            "gate reached": _g(h["gate_reach"]),
            f"ret if ≤buy_below (n={h['n_inside']})":
                _f(h["ret_inside_gate"]),
            f"ret if >buy_below (n={h['n_outside']})":
                _f(h["ret_outside_gate"]),
        } for h in _bt["result"]["horizons"]]
        st.dataframe(_pd.DataFrame(_rows), hide_index=True,
                     use_container_width=True)
        st.caption("fv_bias<0 → realized price UNDER fair value "
                   "(engine overshot) · bear breach ~25% = calibrated · "
                   "ret≤bb > ret>bb → the gate separates good entries")
    elif _bt and not _bt.get("success"):
        st.error(_bt.get("error") or "backtest failed")
    elif _bt.get("success"):
        st.caption("no evaluable runs — horizons longer than run age")

results = st.session_state.get("fv_test") or {}
if not results:
    st.stop()

# ---------------------------------------------------------- summary grid
st.subheader("summary")
rows = []
for s, r in results.items():
    if not r.get("success"):
        rows.append({"symbol": s, "error": r.get("error", "failed")})
        continue
    res, d = r["result"], (r["result"].get("decision") or {})
    spot = d.get("spot")
    cls = d.get("classification") or {}
    worst = (d.get("macro_scenarios") or {}).get("_worst") or {}
    dem = d.get("demand_profile") or {}
    dur = (dem.get("durability") or {}).get("score")
    dgate = (dem.get("gate") or {}).get("gate")
    bb = d.get("buy_below")
    gate = ("🟢 below" if spot and bb and spot <= bb else
            "🔴 above" if bb else "—")
    rows.append({
        "symbol": s,
        "regime": res.get("regime"),
        "archetypes": "+".join(cls.get("all") or []),
        "demand": dem.get("demand_model"),
        "dur": dur,
        "fund": dem.get("capital_funding_risk"),
        "d-gate": dgate,
        "spot": spot,
        "fv": res.get("fair_value"),
        "expected": res.get("expected_fair_value"),
        "upside%": (round(d["fv_upside_pct"] * 100, 1)
                    if d.get("fv_upside_pct") is not None else None),
        "buy_below": bb,
        "mos%": (round(d["mos_pct"] * 100) if d.get("mos_pct") else None),
        "gate": gate,
        "conf": d.get("valuation_confidence"),
        "risk": ",".join(d.get("risk_flags") or []),
        "worst": (f"{worst.get('scenario','')} "
                  f"{worst.get('impact',0):+.0%}" if worst else ""),
        "src": r["run_meta"].get("reason"),
    })
st.dataframe(rows, use_container_width=True, hide_index=True)

st.caption("🟢/🔴 per row in the detail below — 'gate' shows whether "
           "today's price is under buy_below; the engine prices worth, "
           "the decision layer prices what's safe to pay.")

# ---------------------------------------------------------- per-stock detail
for s, r in results.items():
    if not r.get("success"):
        st.error(f"**{s}** — {r.get('error')}")
        continue
    res, meta = r["result"], r["run_meta"]
    d = res.get("decision") or {}
    cls = d.get("classification") or {}
    scen = res.get("scenario_fair_values") or {}
    spot = d.get("spot")
    flags = res.get("quality_flags") or []

    with st.expander(f"**{s}** — {res.get('regime') or '—'} · "
                     f"fv {res.get('fair_value') or '—'}", expanded=False):
        # archetypes
        if cls.get("primary"):
            st.caption("🏷 " + " · ".join(f"`{a}`" for a in
                       (cls.get("all") or [])) +
                       (f"  (override)" if cls.get("source") == "override"
                        else ""))
        # ladder — shown even without spot (vs-spot % only when priced)
        if scen:
            bits = ([f"price **${float(spot):.2f}**"]
                    if spot else [])
            for k, lbl in [("bear", "bear"), ("base", "base"),
                           ("expected", "exp"), ("bull", "bull"),
                           ("explosive", "expl")]:
                v = res.get("expected_fair_value") if k == "expected" \
                    else scen.get(k)
                if v is not None:
                    seg = f"{lbl} **${float(v):.2f}**"
                    if spot:
                        seg += f" ({float(v)/float(spot)-1:+.0%})"
                    bits.append(seg)
            st.markdown(" · ".join(bits))
        elif res.get("fair_value"):
            st.markdown(f"fv **${float(res['fair_value']):.2f}**")

        # decision line
        if d.get("buy_below") and spot:
            bb = float(d["buy_below"])
            gate = "🟢 below gate — accumulable" if float(spot) <= bb \
                else "🔴 above gate — wait for discount"
            _line = (f"**🛡 buy ≤ ${bb:.2f}** · mos "
                     f"{d.get('mos_pct', 0):.0%} · conf "
                     f"`{d.get('valuation_confidence')}`")
            if d.get("expected_return_2y") is not None:
                _line += f" · 2y exp {d['expected_return_2y']:+.1%}/yr"
            st.markdown(_line)
            st.caption(gate +
                       (f"  ·  adders: {', '.join(d['mos_adders'])}"
                        if d.get("mos_adders") else ""))
        if d.get("risk_flags"):
            st.warning("⛔ " + " · ".join(f"`{f}`" for f in d["risk_flags"]))

        # macro stress
        msc = d.get("macro_scenarios") or {}
        real = {k: v for k, v in msc.items() if not k.startswith("_")}
        if real:
            st.caption("**AI-capex stress:**")
            for k, v in real.items():
                st.caption(f"· {v.get('label')}: {v.get('impact',0):+.0%} "
                           f"→ fv ${v.get('stressed_fv')} "
                           f"(vs spot {v.get('stressed_vs_spot',0):+.0%})")

        # demand / capital-cycle layer (shadow — informs, never trades)
        dem = d.get("demand_profile") or {}
        if dem:
            axes = " · ".join(
                f"{k.split('_')[0]} `{dem[k]}`" for k in
                ("demand_model", "capex_sensitivity", "demand_durability",
                 "utilization_health", "capital_funding_risk",
                 "ai_monetization") if dem.get(k))
            st.caption(f"**demand** — {axes}")
            dur = dem.get("durability") or {}
            gate = dem.get("gate") or {}
            reg = dem.get("ai_capex_regime") or {}
            warn = dem.get("ai_cycle_warning") or {}
            bits = []
            if dur.get("score") is not None:
                bits.append(f"durability **{dur['score']}**/100 "
                            f"({dur.get('confidence')})")
            if reg.get("regime"):
                bits.append(f"ai-regime `{reg['regime']}`")
            if warn.get("score") is not None:
                bits.append(f"cycle-warn **{warn['score']}**")
            if gate.get("gate"):
                lt = "· LT-eligible" if gate.get(
                    "long_term_eligible") else "· tactical-only"
                bits.append(f"gate `{gate['gate']}` {lt} *(shadow)*")
            st.caption(" · ".join(bits))
            if dem.get("conflicts"):
                st.warning("⚠ evidence conflicts: " +
                           ", ".join(f"`{c}`" for c in dem["conflicts"]))
            sc = dem.get("scenarios") or {}
            if sc.get("revenue_growth_base") not in (None, "unknown"):
                st.caption(
                    f"rev growth — base "
                    f"{sc['revenue_growth_base']:+.0%} · slowdown "
                    f"{sc.get('revenue_growth_slowdown'):+.0%} · stress "
                    f"{sc.get('revenue_growth_stress'):+.0%} · fcf-stress "
                    f"`{sc.get('fcf_stress_state')}`")
            if sc.get("thesis_break_conditions"):
                st.caption("thesis breaks if: " +
                           " · ".join(sc["thesis_break_conditions"]))

        # why — method contributions
        st.caption("**why this number — methods:**")
        for m in (res.get("method_results") or []):
            if m.get("status") != "ok":
                st.caption(f"· `{m.get('method_key')}` → "
                           f"{m.get('status')}"
                           + (f" ({m.get('reason_code')})"
                              if m.get("reason_code") else ""))
                _fr = (m.get("metrics") or {}).get("formula_repr") or {}
                if _fr.get("base"):
                    with st.expander(f"formula — {m.get('method_key')}",
                                     expanded=False):
                        st.code(_fr["base"], language=None)
                continue
            iu = m.get("inputs_used") or {}
            drivers = []
            for k in ("eps_ttm", "eps_forward", "revenue_growth_ttm",
                      "fcf_ttm", "pe_ratio", "ps_ratio",
                      "operating_margin_ttm", "roe_ttm", "book_value",
                      "analyst_count", "market_cap"):
                if iu.get(k) is not None:
                    v = iu[k]
                    drivers.append(f"{k}={v:.3g}" if isinstance(
                        v, (int, float)) else f"{k}={v}")
            met = m.get("metrics") or {}
            w = met.get("blend_weight")
            st.caption(f"· `{m.get('method_key')}` "
                       f"{f'w={w} ' if w else ''}→ "
                       f"**${float(m.get('fair_price') or 0):.2f}**"
                       + (f"  ({', '.join(drivers[:6])})"
                          if drivers else ""))
            # per-leg formulas — rendered from the deployed DSL with
            # this run's resolved values substituted inline
            frepr = met.get("formula_repr") or {}
            scenv = met.get("scenario_fair_values") or {}
            if frepr:
                with st.expander(f"formulas — {m.get('method_key')}",
                                 expanded=False):
                    for leg in ("bear", "base", "bull", "explosive"):
                        expr = frepr.get(leg)
                        if expr is None:
                            continue
                        fv = scenv.get(leg)
                        st.code(
                            f"{leg:>9} = {expr}\n"
                            f"{leg:>9} → "
                            f"{'$' + format(float(fv), '.2f') if fv is not None else 'null'}",
                            language=None)

        if flags:
            st.caption("⚠️ quality flags: " + ", ".join(flags))
        for w in (res.get("warnings") or [])[:4]:
            st.caption(f"· {w.get('reason')}")
        st.caption(f"run {meta.get('run_id')} · "
                   f"{meta.get('reason')} · {meta.get('run_as_of','')[:19]}")
