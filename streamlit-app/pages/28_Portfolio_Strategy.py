"""Portfolio Strategy — the top-down allocation layer.

Market regime → money rotation → macro/events → earnings → theme
scores → target weights. Daily Board answers "which name"; this page
answers "how much of each theme, and what evidence would change it".

Deterministic engine (strategy_v1), journaled daily — the scores are
parameters, the journal is how they get backtested.
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from api_client import APIClient
from api_config import api_config

setup_page_config("Portfolio Strategy", "🧭")
render_sidebar()

st.title("🧭 Portfolio Strategy")
st.caption("regime → capital flows → events → earnings → theme scores "
           "→ weights · advisory only — targets, never orders")

client = APIClient(api_config.python_worker_url, timeout=180)


@st.cache_data(ttl=600, show_spinner=False)
def _load():
    try:
        return client.get("api/v1/board/strategy") or {}
    except Exception:
        return {}


S = _load()
if st.button("🔄 refresh"):
    _load.clear()
    st.rerun()

if not S:
    st.warning("strategy engine unavailable — is the worker up?")
    st.stop()

# ---------------------------------------------------------------- header
m = S.get("morning") or {}
w = S.get("weights") or {}
ev = S.get("events") or {}
ea = S.get("earnings") or {}

_REG = {"strong_risk_on": "🟢", "risk_on": "🟢", "neutral": "⚪",
        "risk_off": "🟠", "stress": "🔴"}
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Market regime",
          f"{_REG.get(m.get('regime'), '⚪')} {m.get('regime', '—').upper()}",
          f"score {m.get('score', '—')}/100")
c2.metric("AI sleeve", (m.get("ai_regime") or "—").upper())
c3.metric("Event density", ev.get("density", "—").upper(),
          f"{ev.get('high_next10', 0)} high-impact ≤10d")
c4.metric("Earnings exposure", ea.get("summary", "—"),
          f"peak {ea.get('peak_exposure_pct', 0)}% of book")
c5.metric("Cash target", f"{w.get('cash_pct', '—')}%",
          f"deploy cap {round((w.get('deploy_cap') or 0) * 100)}%")

# ------------------------------------------------- horizon scenarios
_h1, _h3 = m.get("horizon_1m"), m.get("horizon_3m")
if _h1 or _h3:
    import json as _j
    if isinstance(_h1, str):
        _h1 = _j.loads(_h1)
    if isinstance(_h3, str):
        _h3 = _j.loads(_h3)
    hc1, hc2 = st.columns(2)
    for col, h, lbl in ((hc1, _h1, "this month"), (hc2, _h3, "next 3 months")):
        if h:
            col.markdown(
                f"**{lbl}:** `{h.get('base', '—')}` · "
                f"bull→{h.get('bull', '—')} · bear→{h.get('bear', '—')}")
            if h.get("to_bull") or h.get("to_bear"):
                col.caption(" ▸ ".join(
                    f"{k}: {v}" for k, v in
                    (("to_bull", h.get("to_bull")),
                     ("to_bear", h.get("to_bear")),
                     ("to_stress", h.get("to_stress"))) if v))

st.divider()

# ------------------------------------------------- 0. phase playbook
pb = S.get("playbook") or {}
phases = pb.get("phases") or []
if phases:
    st.subheader("📆 Execution Playbook — calendar-derived phases")
    st.caption("de-risk before the IV premium · freeze through the dead "
               "zone · deploy on facts — the phases are calendar math, "
               "not a prediction")
    cl = pb.get("cluster") or {}
    if cl.get("symbols"):
        st.caption(f"earnings cluster wk {cl['week']}: "
                   f"{', '.join(cl['symbols'])}")
    today_s = __import__("datetime").date.today().isoformat()
    for p in phases:
        w0, w1 = p["window"]
        active = (w0 <= today_s and (w1 == "+45d" or today_s <= w1))
        tag = " ◀ now" if active else ""
        with st.expander(f"**Phase {p['n']} — {p['name']}** "
                         f"({w0} → {w1}){tag}", expanded=active):
            st.caption(f"**criterion:** {p['criterion']}")
            for a in p["actions"]:
                st.caption(f"· {a}")
            if p["candidates"]:
                st.markdown("names: " + " · ".join(
                    f"`{s}`" for s in p["candidates"]))
            st.caption(f"*{p['rule']}*")
    st.divider()

# ------------------------------------------------- 1. money rotation
st.subheader("💸 Money Rotation — where capital is actually moving")
st.caption("30% relative strength · 25% flows · 20% breadth · "
           "15% volume · 10% acceleration — price×volume proxy, "
           "not fund-flow data")
rot = S.get("rotation") or {}
rows = rot.get("rows") or []
if rows:
    import pandas as pd
    df = pd.DataFrame([{
        "etf": r["etf"], "name": r["name"],
        "score": r["score"],
        "rel perf": r["parts"]["rel_perf"],
        "flow": r["parts"]["flow"],
        "breadth": r["parts"]["breadth"],
        "volume": r["parts"]["volume"],
        "accel": r["parts"]["accel"],
        "flow $5d": (f"${(r['flow_5d_usd'] or 0) / 1e6:+,.0f}M"
                     if r.get("flow_source") == "aum" else "proxy"),
        "5d": f"{(r['ret5'] or 0) * 100:+.1f}%",
        "vs SPY 20d": f"{(r['vs_spy20'] or 0) * 100:+.1f}%",
    } for r in rows])
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={"score": st.column_config.ProgressColumn(
                     "rotation", min_value=0, max_value=100)})
    _in = " · ".join(f"🟢 `{s}`" for s in rot.get("inflow") or [])
    _out = " · ".join(f"🔴 `{s}`" for s in rot.get("outflow") or [])
    if _in:
        st.caption(f"inflow: {_in}")
    if _out:
        st.caption(f"outflow: {_out}")

# --------------------------------------------- 1b. direction call
dr = S.get("direction") or []
if dr:
    st.subheader("🧭 Direction — where money goes next")
    st.caption("flow + macro tilt + member breadth + fresh catalysts — "
               "2+ aligned witnesses = confirmed, one = watch only")
    _V = {"accelerating_in": "🚀", "rotating_in": "🟢",
          "stable": "⚪", "rotating_out": "🟠", "avoid": "🔴"}
    for d in dr:
        lead = " · ".join(
            f"`{m['symbol']}`{'' if not m['in_book'] else '📚'}"
            f"({m['state']})"
            for m in d.get("leaders") or []) or "—"
        st.markdown(
            f"{_V.get(d['verdict'], '⚪')} **{d['name']}** "
            f"`{d['verdict'].replace('_', ' ')}` "
            f"— {d['witnesses']}/4 witnesses · lands first: {lead}")
        for wy in d.get("why") or []:
            st.caption(f"   · {wy}")

# ------------------------------------------------- 2. events + election
st.subheader("🗓️ Events — risk environment, not stock picks")
el = ev.get("election")
if el:
    st.markdown(
        f"**{el['name']}** — {el['days_away']}d away · sensitivity "
        f"`{el['sensitivity']}`")
    ch = el.get("channels") or {}
    st.caption("transmission channels: " + " · ".join(
        f"{k} → {', '.join(v)}" for k, v in ch.items()))
    st.caption("rule: election modifies risk budget — it never tells "
               "the system what to buy")
heat = ev.get("heatmap") or []
if heat:
    _sev_i = {"extreme": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}
    st.caption("next 45d: " + " · ".join(
        f"{_sev_i.get(h['severity'], '⚪')} {h['date'][5:]} {h['name']}"
        for h in heat[:12]))

# ------------------------------------------------- 3. earnings concentration
st.subheader("📊 Earnings Concentration — book exposure by week")
weeks = ea.get("weeks") or []
if weeks:
    _rk = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}
    for wk in weeks:
        syms = ", ".join(wk["symbols"]) or "—"
        st.markdown(
            f"{_rk.get(wk['risk'], '⚪')} **wk {wk['week']}** — "
            f"{wk['n']} names · {wk['pct_of_book']}% of book "
            f"· `{wk['risk']}` — {syms}")

# expectation board — who walks in hot vs. with a lowered bar
pv = ea.get("preview") or []
if pv:
    held = [p for p in pv if p.get("held")]
    rest = [p for p in pv if not p.get("held")]
    shown = held + rest[:max(0, 40 - len(held))]
    st.markdown(f"**📋 Print preview — next 60d** "
                f"({len(held)} held · {len(rest)} universe)")
    st.caption("est-revision direction + beat streak = the setup going "
               "in, not the prediction. 🔥 = high bar (asymmetric "
               "downside on miss) · 🧊 = bar lowering · 📚 = held")
    for p in shown:
        held = " 📚" if p.get("held") else ""
        rp = p.get("rev_pct")
        rev = (f"{rp:+.0f}%" if rp is not None and abs(rp) < 200
               else "⚠️ thin/erratic" if rp is not None else "—")
        eg = (f"{p['eps_growth']:+.0f}%" if p.get("eps_growth")
              is not None else "—")
        st.caption(
            f"`{p['date']}` **{p['symbol']}**{held} · {p['setup']} · "
            f"revisions {rev} · streak {p['streak']} · "
            f"eps growth {eg} · {p.get('analysts') or '—'} analysts")

st.divider()

# ------------------------------------------------- 4. theme scores
st.subheader("🏗️ Theme Scores — tailwind × fundamentals × momentum "
             "× money × valuation")
themes = S.get("themes") or []
for t in themes:
    p = t["parts"]
    head = (f"**{t['name']}** — score **{t['score']:.0f}** "
            f"(`{t['etf']}` · {t['member_count']} names)")
    with st.expander(head, expanded=t["score"] >= 65):
        cc = st.columns(5)
        for c, k in zip(cc, ("tailwind", "fundamentals", "momentum",
                             "money_flow", "valuation")):
            c.metric(k.replace("_", " "), f"{p[k]:.0f}")
        rr = t.get("rotation_row") or {}
        if rr:
            st.caption(f"rotation {rr.get('score')} · "
                       f"vs SPY 20d {(rr.get('vs_spy20') or 0) * 100:+.1f}% "
                       f"· {'above' if rr.get('above50') else 'below'} "
                       "50dma")
        for e in t.get("evidence") or []:
            st.caption(f"· {e}")

# --------------------------------------------- 4b. agentic AI bifurcation
ag = S.get("agentic") or {}
if ag:
    st.divider()
    st.subheader("🤖 Agentic AI — who agents can't bypass vs "
                 "who they replace")
    bif = ag.get("bifurcation")
    if bif is not None:
        tone = "🟢" if bif > 10 else "🟡" if bif > 0 else "🔴"
        st.markdown(
            f"{tone} **bifurcation spread {bif:+.1f}** — bypass-layer "
            f"mean {ag.get('beneficiary_mean')} vs seat-model mean "
            f"{ag.get('exposed_mean')} — {ag.get('read')}")

    held_b = ag.get("held_bypass") or []
    held_x = ag.get("held_exposed") or []
    if held_b:
        st.caption("book exposure to bypass layers: "
                   + " · ".join(f"`{s}`" for s in held_b))
    if held_x:
        st.warning("⚠️ book holds seat-model names: "
                   + " · ".join(f"`{s}`" for s in held_x)
                   + " — underwrite the agentic-AI risk explicitly")

    for l in ag.get("layers") or []:
        inb = (" · book: " + ", ".join(l["in_book"])) if l["in_book"] else ""
        with st.expander(f"**{l['name']}** — score **{l['score']:.0f}**"
                         f"{inb}", expanded=l["score"] >= 65):
            if l.get("note"):
                st.caption(l["note"])
            for n in l["names"]:
                tag = " 📚" if n["in_book"] else ""
                rg = (f" · rev {n['rev_growth']:+.0f}%"
                      if n.get("rev_growth") is not None else "")
                st.caption(f"· `{n['symbol']}`{tag} — {n['score']:.0f} "
                           f"· mom `{n['momentum']}` · "
                           f"fund `{n['fundamental']}`{rg}")

    xp = ag.get("exposed") or []
    if xp:
        with st.expander("🪑 Seat-model exposure list — BofA's "
                         "at-risk names, scored"):
            st.caption("agents consume fewer per-seat licenses — "
                       "a strong score here means the market hasn't "
                       "priced the risk yet")
            for n in xp:
                st.caption(f"{n['flag']} `{n['symbol']}` {n['name']} — "
                           f"{n['score']:.0f} · mom `{n['momentum']}` "
                           f"· fund `{n['fundamental']}`")

# ------------------------------------------------- 5. rotation confirmation
conf = w.get("confirmation") or []
if conf:
    st.subheader("✅ Rotation Confirmation")
    st.caption("shifts need ≥2 independent witnesses — flow alone is "
               "just a watch")
    for c in conf:
        st.markdown(f"**{c['theme']}** — {c['grade']} "
                    f"({c['witnesses']}/4 witnesses)")

# ------------------------------------------------- 6. targets vs book
st.subheader("⚖️ Target Weights vs Book")
cur = S.get("current") or {}
targets = w.get("targets") or {}
if targets:
    import pandas as pd
    rows_t = []
    names = {t["key"]: t["name"] for t in themes}
    for k, tgt in sorted(targets.items(), key=lambda x: -x[1]):
        cw = (cur.get("by_theme") or {}).get(k, 0.0)
        rows_t.append({"theme": names.get(k, k),
                       "target %": tgt, "current %": cw,
                       "Δ": round(tgt - cw, 1)})
    rows_t.append({"theme": "💵 cash", "target %": w.get("cash_pct"),
                   "current %": "—", "Δ": "—"})
    st.dataframe(pd.DataFrame(rows_t), use_container_width=True,
                 hide_index=True)
    hc = w.get("haircuts") or {}
    st.caption(f"regime `{w.get('regime')}` → deploy cap "
               f"{round((w.get('deploy_cap') or 0) * 100)}% · "
               f"earnings haircut ×{hc.get('earnings')} · "
               f"election haircut ×{hc.get('election')}")

    st.markdown("**Suggested rebalances** — advisory, monthly cadence")
    for d in w.get("deltas") or []:
        arrow = "🟢 +" if d["action"] == "increase" else "🔴 "
        rs = " · ".join(d["reasons"]) or "rebalance toward target"
        st.markdown(f"{arrow}**{abs(d['delta'])}% {d['theme']}** "
                    f"({d['current']}% → {d['target']}%) — {rs}")
    if not w.get("deltas"):
        st.caption("book within tolerance of targets — no rebalance")

bk = S.get("book") or {}
st.caption(f"book universe: {bk.get('n', 0)} symbols "
           f"(open positions + LEAPS + focus book) · "
           f"engine `{S.get('engine_version')}` · "
           f"journaled `strategy_snapshots` · {S.get('as_of', '')[:19]}")
