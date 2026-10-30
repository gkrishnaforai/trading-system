# -*- coding: utf-8 -*-
"""AI Research — the tailwind research engine's ops surface.

Deterministic evidence (quarters, products, commitments) → versioned
scores → skeptical review → gated recommendation → research_runs
journal. Nothing here places orders; this page reads and triggers
runs — the human decides.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from api_client import APIClient
from api_config import api_config

st.set_page_config(page_title="AI Research", page_icon="🧬",
                   layout="wide")
client = APIClient(api_config.python_worker_url, timeout=300)

st.title("🧬 AI-tailwind research")
st.caption("Evidence → deterministic scores → skeptical review → "
           "gated recommendation. A high tailwind score means AI "
           "exposure — not a cheap stock; the recommendation column "
           "is the gated read.")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        st.warning(f"fetch failed: {e}")
        return default


# ---------------------------------------------------------- controls
c1, c2, c3 = st.columns([2, 2, 4])
sector = c1.selectbox("sector", ["healthcare", "ai_infra"], index=0)
board = _safe(lambda: client.get("admin/research/board",
                                 params={"sector": sector}) or {})
rows = (board or {}).get("rows") or []
scored = [r for r in rows if r.get("ai_tailwind") is not None]

sym_pick = c2.selectbox(
    "run single symbol",
    [""] + [r["symbol"] for r in rows],
    format_func=lambda s: s or "pick…")
if c2.button("▶ run", disabled=not sym_pick):
    with st.spinner(f"researching {sym_pick}…"):
        res = _safe(lambda: client.post(
            f"admin/research/{sym_pick}", json_data={}, timeout=300))
    if res:
        st.success(f"{sym_pick}: tailwind "
                   f"{res.get('report', {}).get('scores', {}).get('ai_tailwind')} → "
                   f"{res.get('report', {}).get('recommendation', {}).get('action')}")
        st.rerun()

if c3.button("⟳ run board job (background)"):
    res = _safe(lambda: client.post("api/v1/board/refresh/research",
                                    json_data={}))
    st.info(f"job: {(res or {}).get('status')}")

c3.caption(f"{len(scored)} scored · {len(rows) - len(scored)} "
           "awaiting run · job skips same-day rows")


# ------------------------------------------------------------- board
st.subheader("Board — tailwind-ranked")
if not rows:
    st.info(f"No {sector} names in stocks yet, or board fetch failed.")
else:
    df = pd.DataFrame([{
        "symbol": r["symbol"],
        "name": (r.get("name") or "")[:28],
        "model": (r.get("business_model") or "").replace("_", " "),
        "AI tailwind": r.get("ai_tailwind"),
        "biz strength": r.get("business_strength"),
        "best product": (r.get("best_product") or {}).get("name"),
        "stage": (r.get("best_product") or {}).get("stage"),
        "moats": len((r.get("best_product") or {}).get("moats") or []),
        "stance": (r.get("recommendation") or "—").replace("_", " "),
        "as_of": r.get("as_of") or "—",
    } for r in rows])
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={
                     "AI tailwind": st.column_config.ProgressColumn(
                         min_value=0, max_value=100, format="%d"),
                     "biz strength": st.column_config.ProgressColumn(
                         min_value=0, max_value=100, format="%d")})
    st.caption("Rank: AI tailwind desc → best-product score desc "
               "(stage ×3 + moat breadth). Unscored = not yet "
               "researched — never a false zero.")

st.divider()

# ------------------------------------------------- symbol drill-down
st.subheader("Report drill-down")
detail = st.selectbox("symbol", [""] + [r["symbol"] for r in rows],
                      format_func=lambda s: s or "pick…",
                      key="detail")
if detail:
    run = _safe(lambda: (client.get(f"admin/research/{detail}") or {})
                        .get("run"))
    if not run:
        st.info(f"{detail}: no research run yet — run it above.")
    else:
        rep = run.get("report") or {}
        sc = run.get("scores") or {}
        tw, bs = sc.get("tailwind") or {}, sc.get("strength") or {}

        m = st.columns(6)
        m[0].metric("AI tailwind", run.get("ai_tailwind_score"))
        m[1].metric("business strength", run.get("business_strength"))
        m[2].metric("recommendation",
                    (run.get("recommendation") or "—").replace("_", " "))
        m[3].metric("model", (run.get("business_model") or "—")
                    .replace("_", " "))
        cov = (rep.get("coverage") or {})
        m[4].metric("coverage",
                    f"{int(round(100 * (cov.get('tailwind') or 0)))}%")
        m[5].metric("as of", str(run.get("as_of") or "—"))

        if tw.get("capped"):
            st.warning(f"score capped — {tw['capped']}")
        gates = rep.get("hard_gates") or []
        if gates:
            st.error("hard gates: " + ", ".join(gates))
        miss = cov.get("missing") or []
        if miss:
            st.caption("missing inputs: " + ", ".join(miss[:14]))

        # ---- score components — the 'why' -------------------------
        qual = sc.get("quality") or {}
        left, right = st.columns(2)
        for col, (label, comp_owner) in zip(
                (left, right),
                (("AI tailwind", tw), ("Business strength", bs))):
            with col:
                st.markdown(f"**{label} — component verdicts**")
                comps = comp_owner.get("components") or {}
                if comps:
                    cdf = pd.DataFrame([
                        {"component": k.replace("_", " "),
                         "score": v.get("score"),
                         "weight": v.get("weight"),
                         "note": v.get("note") or ""}
                        for k, v in comps.items()
                    ]).sort_values("weight", ascending=False)
                    st.dataframe(cdf, hide_index=True,
                                 use_container_width=True)

        # ---- quality — 10-dimension panel (/10) --------------------
        qcomps = qual.get("components") or {}
        if qcomps:
            st.markdown(f"**Quality — {round((qual.get('score') or 0) / 10, 1)}/10**"
                        " — 10 deterministic dimensions")
            qdf = pd.DataFrame([
                {"dimension": k.replace("_", " "),
                 "score": (v.get("score") or 0) / 10,
                 "reasoning": v.get("note") or ""}
                for k, v in qcomps.items()])
            st.dataframe(qdf, hide_index=True, use_container_width=True,
                         column_config={
                             "score": st.column_config.ProgressColumn(
                                 min_value=0, max_value=10, format="%.1f")})

        # ---- architecture score (ai_infra) -------------------------
        arch = sc.get("ai_infra_architecture") or {}
        acomps = arch.get("components") or {}
        if acomps:
            st.markdown(f"**Architecture exposure — "
                        f"{arch.get('score') or '—'}/100**")
            if arch.get("capped"):
                st.warning(f"architecture capped — {arch['capped']}")
            adf = pd.DataFrame([
                {"component": k.replace("_", " "),
                 "score": v.get("score"),
                 "weight": v.get("weight"),
                 "reasoning": v.get("note") or ""}
                for k, v in acomps.items()
            ]).sort_values("weight", ascending=False)
            st.dataframe(adf, hide_index=True, use_container_width=True)

        # ---- design wins -------------------------------------------
        wins = rep.get("design_wins") or []
        if wins:
            st.markdown("**Design wins — lifecycle**")
            st.dataframe(pd.DataFrame([{
                "customer": w.get("customer"),
                "product": w.get("product"),
                "stage": w.get("stage"),
                "revenue": "✓" if w.get("revenue_confirmed") else "—",
            } for w in wins]), hide_index=True,
                use_container_width=True)

        # ---- products ----------------------------------------------
        prods = rep.get("products") or []
        if prods:
            st.markdown("**Products & moat**")
            st.dataframe(pd.DataFrame([{
                "product": p.get("name"),
                "stage": p.get("stage"),
                "AI use": (p.get("ai_use") or "")[:80],
                "moat": ", ".join(p.get("moat") or
                                  (p.get("evidence") or {})
                                  .get("moat") or []),
                "why": (p.get("why") or "")[:110],
            } for p in prods]), hide_index=True,
                use_container_width=True)

        # ---- quarters ----------------------------------------------
        qs = rep.get("quarters") or []
        if qs:
            st.markdown("**Multi-quarter prints** "
                        "— reported values, calculated flags kept")

            def _v(q, k):
                return (q.get(k) or {}).get("value")

            qdf = pd.DataFrame([{
                "period": q.get("period_end"),
                "filed": q.get("filing_date"),
                "revenue": _v(q, "revenue"),
                "gross %": (_v(q, "gross_margin") or 0) * 100
                           if _v(q, "gross_margin") is not None else None,
                "op %": (_v(q, "op_margin") or 0) * 100
                        if _v(q, "op_margin") is not None else None,
                "FCF": _v(q, "free_cf"),
                "shares": _v(q, "shares_diluted"),
            } for q in qs])
            st.dataframe(qdf, hide_index=True,
                         use_container_width=True)
            tr = rep.get("trends") or {}
            if tr:
                st.caption(" · ".join(
                    f"{k.replace('_', ' ')} "
                    f"{v:.1%}" if isinstance(v, float) and abs(v) < 10
                    else f"{k.replace('_', ' ')} {v}"
                    for k, v in tr.items() if v is not None))

        # ---- commitments -------------------------------------------
        coms = rep.get("commitments") or []
        cred = rep.get("credibility") or {}
        if coms:
            st.markdown(f"**Management commitments** — record: "
                        f"`{cred.get('record', '?')}` "
                        f"({cred.get('tracked', 0)} tracked, "
                        f"{cred.get('negative', 0)} negative)")
            st.dataframe(pd.DataFrame(coms), hide_index=True,
                         use_container_width=True)

        # ---- skeptical review --------------------------------------
        chal = rep.get("challenge") or []
        findings = (chal if isinstance(chal, list)
                    else chal.get("findings") or [])
        if findings:
            st.markdown("**Skeptical review**")
            for f in findings:
                sev = (f.get("severity") or "").lower()
                icon = "🔴" if sev == "high" else \
                    "🟡" if sev == "medium" else "⚪"
                st.markdown(
                    f"{icon} **{f.get('question', '?')}** — "
                    f"{f.get('finding', '')}")
        elif isinstance(chal, dict) and chal.get("skipped"):
            st.caption(f"skeptical review skipped — {chal['skipped']}")

        st.caption("rules: " + " · ".join(
            (rep.get("rules_version") or {}).get("scores") or []) +
            f" · {run.get('rules_version')}")
