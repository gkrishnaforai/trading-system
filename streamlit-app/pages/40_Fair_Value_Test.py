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
    bb = d.get("buy_below")
    gate = ("🟢 below" if spot and bb and spot <= bb else
            "🔴 above" if bb else "—")
    rows.append({
        "symbol": s,
        "regime": res.get("regime"),
        "archetypes": "+".join(cls.get("all") or []),
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
        # ladder
        if scen and spot:
            bits = [f"price **${float(spot):.2f}**"]
            for k, lbl in [("bear", "bear"), ("base", "base"),
                           ("expected", "exp"), ("bull", "bull"),
                           ("explosive", "expl")]:
                v = res.get("expected_fair_value") if k == "expected" \
                    else scen.get(k)
                if v is not None:
                    bits.append(f"{lbl} **${float(v):.2f}** "
                                f"({float(v)/float(spot)-1:+.0%})")
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

        # why — method contributions
        st.caption("**why this number — methods:**")
        for m in (res.get("method_results") or []):
            if m.get("status") != "ok":
                st.caption(f"· `{m.get('method_key')}` → "
                           f"{m.get('status')}"
                           + (f" ({m.get('reason_code')})"
                              if m.get("reason_code") else ""))
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
            w = (m.get("metrics") or {}).get("blend_weight")
            st.caption(f"· `{m.get('method_key')}` "
                       f"{f'w={w} ' if w else ''}→ "
                       f"**${float(m.get('fair_price') or 0):.2f}**"
                       + (f"  ({', '.join(drivers[:6])})"
                          if drivers else ""))

        if flags:
            st.caption("⚠️ quality flags: " + ", ".join(flags))
        for w in (res.get("warnings") or [])[:4]:
            st.caption(f"· {w.get('reason')}")
        st.caption(f"run {meta.get('run_id')} · "
                   f"{meta.get('reason')} · {meta.get('run_as_of','')[:19]}")
