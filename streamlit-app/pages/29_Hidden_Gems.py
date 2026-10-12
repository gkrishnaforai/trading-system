"""Hidden Gems — rules-based emerging-growth scanner.

Finds names whose EPS, revenue, margins, estimates and tape are all
improving together — 'fundamental alignment'. Deterministic, journaled
daily (hidden_gem_snapshots) so the NEW/↑/↓/REMOVED column and a later
backtest both come from stored scores.
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar, sym_md
from api_client import APIClient
from api_config import api_config

setup_page_config("Hidden Gems", "💎")
render_sidebar()

st.title("💎 Hidden Gems — emerging growth scanner")
st.caption("rules-based scan: acceleration + estimate revisions + "
           "quality + tape · score 0–125 · journaled daily — "
           "research flag, not a buy signal")

client = APIClient(api_config.python_worker_url, timeout=120)


@st.cache_data(ttl=600, show_spinner=False)
def _load():
    try:
        return client.get("api/v1/board/hidden-gems") or {}
    except Exception:
        return {}


@st.cache_data(ttl=600, show_spinner=False)
def _load_tw():
    try:
        return client.get("api/v1/board/tailwind-candidates") or {}
    except Exception:
        return {}


S = _load()
if st.button("🔄 rescan"):
    _load.clear()
    _load_tw.clear()
    st.rerun()

if not S:
    st.warning("scanner unavailable — is the worker up?")
    st.stop()

# ---------------------------------------------------------------- summary
c1, c2, c3, c4 = st.columns(4)
c1.metric("Universe", S.get("universe_n", 0))
c2.metric("Passed hard filters", S.get("passed", 0),
          f"{S.get('filtered_n', 0)} filtered out")
c3.metric("Full alignment (7/7)", len(S.get("aligned") or []))
c4.metric("Engine", S.get("engine_version", "—"))

# --------------------------------------------- tailwind candidates strip
# "early CAT" — economics repricing up while the stock hasn't, and the
# market hasn't filed it under a known theme yet. Deterministic flags
# over journaled data; advisory only.
TW = _load_tw()
disc = TW.get("discoveries") or []
conf = TW.get("confirmations") or []
if disc or conf:
    st.subheader(f"🌊 Tailwind — {len(disc)} discoveries · "
                 f"{len(conf)} known confirmations "
                 f"({TW.get('scanned', 0)} scanned)")
    st.caption("revisions > +5% · revenue accelerating · "
               "3m price < revisions (hasn't repriced) · below fair "
               "value · not a pure theme member")
    _LK = {"ai_direct": "🤖 AI-direct",
           "ai_indirect": "🔗 AI-indirect",
           "ai_adopter": "📈 AI-adopter",
           "non_ai_cyclical": "♻ cyclical",
           "idiosyncratic": "🏷 idiosyncratic",
           "unclear": "❓ unclear"}
    for r in disc:
        _tw = " 🏷 " + "+".join(r["themes"][:2]) \
              if r.get("themes") else ""
        _lk = r.get("linkage")
        _lk_txt = (f" · {_LK.get(_lk, _lk)}"
                   + (f" _{r['linkage_rationale']}_"
                      if r.get("linkage_rationale") else "")
                   if _lk else "")
        st.markdown(
            f"**{sym_md(r['symbol'])}** — revisions "
            f"**{(r['est_revision_pct'] or 0):+.0%}** · "
            f"3m price {(r['price_ret_63d'] or 0):+.0%} · "
            f"FV gap {(r['fv_gap'] or 0):+.0%} · "
            f"`{r.get('momentum_state') or '—'}` "
            f"{r.get('sector') or ''}{_tw}{_lk_txt}")
    if conf:
        with st.expander(f"already-filed names passing "
                         f"({len(conf)})"):
            for r in conf:
                st.caption(
                    f"{sym_md(r['symbol'])} — revisions "
                    f"{(r['est_revision_pct'] or 0):+.0%} · "
                    f"3m {(r['price_ret_63d'] or 0):+.0%} · "
                    f"FV {(r['fv_gap'] or 0):+.0%}")
    st.divider()

# --------------------------------------------------------- change column
ch = S.get("changes") or {}
if ch:
    st.subheader("Δ vs last run")
    cols = st.columns(4)
    with cols[0]:
        st.markdown("**🆕 new today**")
        for s in ch.get("new") or []:
            st.caption(sym_md(s))
    with cols[1]:
        st.markdown("**↑ improving**")
        for s, d in ch.get("improving") or []:
            st.caption(f"{sym_md(s)} {d:+.0f}")
    with cols[2]:
        st.markdown("**↓ falling**")
        for s, d in ch.get("falling") or []:
            st.caption(f"{sym_md(s)} {d:+.0f}")
    with cols[3]:
        st.markdown("**✕ removed**")
        for s in ch.get("removed") or []:
            st.caption(sym_md(s))
    st.divider()

# ---------------------------------------------------------------- leaders
rows = S.get("rows") or []
_V = {"reasonable": "🟢", "elevated": "🟡", "extreme": "🔴",
      "unknown": "⚪"}
st.subheader(f"Top {len(rows)} — 0–125 score")
for i, r in enumerate(rows, 1):
    al = r.get("aligned", 0)
    tag = " 🟢 FULL ALIGNMENT" if r.get("full_alignment") else \
          (f" · {al}/7 arrows" if al >= 5 else "")
    head = (f"**#{i} {sym_md(r['symbol'])}** — score "
            f"**{r['final']:.0f}**/125 "
            f"(core {r['core']:.0f} + gem {r['bonus']}) · "
            f"{_V.get(r.get('valuation'),'⚪')} {r.get('valuation','—')} · "
            f"`{r.get('momentum') or '—'}`{tag}")
    with st.expander(head, expanded=i <= 3):
        p = r.get("parts") or {}
        cc = st.columns(4)
        cc[0].caption(f"EPS accel **{p.get('eps_accel','—')}** · "
                      f"rev accel {p.get('rev_accel','—')}")
        cc[1].caption(f"EPS growth {p.get('eps_growth','—')} · "
                      f"rev growth {p.get('rev_growth','—')}")
        cc[2].caption(f"est revision **{p.get('revision','—')}**")
        cc[3].caption(f"RS {p.get('rel_strength','—')} · "
                      f"px/vol {p.get('price_vol','—')}")
        ar = r.get("arrows") or {}
        st.caption("alignment: " + " · ".join(
            f"{'🟢' if v else '⚪'} {k}" for k, v in ar.items()))
        if r.get("bonus_why"):
            st.caption("gem bonus: " + " · ".join(r["bonus_why"]))
        if r.get("mcap"):
            st.caption(f"mcap ${r['mcap']/1e9:.1f}B · "
                       f"{r.get('sector') or '—'}"
                       + (f" · fwd P/E {r['fwd_pe']:.0f}"
                          if r.get("fwd_pe") else ""))
        if r.get("proxies"):
            st.caption("⚠️ proxied factors: "
                       + "; ".join(r["proxies"]))

# --------------------------------------------------------- filtered-out
fs = S.get("filtered_sample") or {}
if fs:
    with st.expander(f"filtered out ({S.get('filtered_n', 0)} names)"):
        for s, why in list(fs.items())[:20]:
            st.caption(f"`{s}` — {why}")

st.caption(f"journaled `hidden_gem_snapshots` · hard filters: "
           f"EPS≥20% · rev≥15% · revisions>0 · GM>20% · "
           f"mcap $500M–$50B · px>$5 · {S.get('as_of','')[:19]}")

# ------------------------------------------------------------ backtest
st.divider()
st.subheader("📊 Does the score work? — backtest")
st.caption("Mode A: shadow grading — daily snapshots graded at "
           "+20d/+60d vs SPY once mature (the real out-of-sample "
           "test). Mode B: historical replay of the growth/tape "
           "factors that have point-in-time data.")


@st.cache_data(ttl=3600, show_spinner=False)
def _perf():
    try:
        return client.get("api/v1/board/hidden-gems/performance") or {}
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner="running replay…")
def _replay():
    try:
        return client.get("api/v1/board/hidden-gems/backtest") or {}
    except Exception:
        return {}


perf = _perf()
if perf.get("by_band"):
    st.markdown("**Shadow grading — hit rate by score band**")
    for b in perf["by_band"]:
        c = "🟢" if (b.get("hit20") or 0) >= 0.55 else \
            ("🔴" if (b.get("hit20") or 0) < 0.45 else "⚪")
        hit = f"{b['hit20']:.0%}" if b.get("hit20") is not None else "—"
        exc = (f"{b['avg_excess20']:+.1%}"
               if b.get("avg_excess20") is not None else "—")
        st.caption(f"{c} score {b['band']:5} · n={b['n']:3} · "
                   f"beat SPY {hit} @20d · avg excess {exc}")
    fa = perf.get("full_alignment") or {}
    if fa.get("n"):
        fa_hit = f"{fa['hit20']:.0%}" if fa.get("hit20") is not None \
            else "—"
        st.caption(f"7/7 aligned names: n={fa['n']} · hit {fa_hit}")
else:
    st.info(perf.get("status", "journal grading starts after ~30 days "
                               "of snapshots"))

with st.expander("Mode B — historical replay (partial factors)"):
    if st.button("Run replay (~1 min)"):
        _replay.clear()
    rep = _replay()
    if rep:
        top_exc = (f"{rep['top10_excess_20d']:+.1%}"
                   if rep.get("top10_excess_20d") is not None else "—")
        st.caption(f"window {rep.get('window')} · "
                   f"{rep.get('picks')} picks · "
                   f"top-10 portfolio avg excess 20d: **{top_exc}**")
        for b in rep.get("bucket_stats") or []:
            st.caption(
                f"score {b['band']:8} n={b['n']:4} · "
                f"hit20 {b.get('hit_20')} · exc20 {b.get('avg_excess_20')} · "
                f"hit60 {b.get('hit_60')} · exc60 {b.get('avg_excess_60')}")
        ic = rep.get("factor_ic") or {}
        if ic:
            st.caption("factor IC (hi−lo excess): "
                       + " · ".join(f"{k} {v:+.3f}"
                                   for k, v in ic.items()))
        for c in rep.get("caveats") or []:
            st.caption(f"⚠️ {c}")
