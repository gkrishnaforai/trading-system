"""Theme Intelligence engine — orchestration + journal.

  evaluate()  read the registry + journaled member evidence
              (research_runs, fair_value_v2_runs, symbol_flywheel,
              daily_bars) + macro stack (morning regime, liquidity,
              FRED) → scenario probs → per-theme opportunity + index
              weights. Pure read — no writes.
  run()       evaluate() + journal theme_intelligence_snapshots +
              theme_index_membership rows (PIT membership — never
              rebuild history from today's survivors).
  read()      latest snapshot for the themes page.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from statistics import mean
from typing import Any, Optional

from app.metals.engine import _fred_chg

from . import index_builder as _ib
from . import opportunity as _opp
from . import scenarios as _sc

logger = logging.getLogger(__name__)


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _members(registry: dict) -> dict[str, set[str]]:
    """theme_key → member symbols."""
    return {k: set((t.get("members") or {}).keys())
            for k, t in registry.items()}


def _member_facts(symbols: list[str]) -> dict[str, dict]:
    """Latest journaled evidence per member — one query per store."""
    from app.database import db
    facts: dict[str, dict] = {s: {} for s in symbols}
    if not symbols:
        return facts
    try:
        for r in db.execute_query(
                "SELECT DISTINCT ON (symbol) symbol,"
                " ai_tailwind_score, business_strength"
                " FROM research_runs WHERE symbol=ANY(:s)"
                " ORDER BY symbol, as_of DESC", {"s": symbols}):
            facts[r["symbol"]].update(
                ai_tailwind=_f(r.get("ai_tailwind_score")),
                business_strength=_f(r.get("business_strength")))
    except Exception as e:                                  # noqa: BLE001
        logger.debug("themes research facts: %s", e)
    try:
        for r in db.execute_query(
                "SELECT DISTINCT ON (symbol) symbol, fv_upside_pct"
                " FROM fair_value_v2_runs WHERE symbol=ANY(:s)"
                " ORDER BY symbol, as_of DESC", {"s": symbols}):
            facts[r["symbol"]]["fv_upside_pct"] = \
                _f(r.get("fv_upside_pct"))
    except Exception as e:                                  # noqa: BLE001
        logger.debug("themes fv facts: %s", e)
    try:
        for r in db.execute_query(
                "SELECT symbol, est_revision_pct, rev_growth,"
                " eps_growth FROM symbol_flywheel"
                " WHERE symbol=ANY(:s)", {"s": symbols}):
            facts[r["symbol"]].update(
                est_revision_pct=_f(r.get("est_revision_pct")),
                rev_growth=_f(r.get("rev_growth")),
                eps_growth=_f(r.get("eps_growth")))
    except Exception as e:                                  # noqa: BLE001
        logger.debug("themes flywheel facts: %s", e)
    # momentum — latest 65 closes per symbol in one windowed query
    try:
        rows = db.execute_query(
            "SELECT symbol, close, rn FROM ("
            " SELECT symbol, close,"
            " ROW_NUMBER() OVER (PARTITION BY symbol"
            " ORDER BY date DESC) rn"
            " FROM daily_bars WHERE symbol=ANY(:s)"
            " AND date<=:d) t WHERE rn<=65",
            {"s": symbols + ["SPY"], "d": date.today()})
        closes: dict[str, list[float]] = {}
        for r in rows:
            closes.setdefault(r["symbol"], []).append(
                float(r["close"]))
        for sym, c in closes.items():
            if sym == "SPY":
                continue
            cur = facts.get(sym)
            if cur is None:
                continue
            px = c[0]
            cur["ret20"] = px / c[20] - 1 if len(c) > 20 else None
            cur["ret60"] = px / c[60] - 1 if len(c) > 60 else None
            cur["above_sma50"] = ((px / mean(c[:50])) * 100
                                  if len(c) >= 50 else None)
        sp = closes.get("SPY") or []
        facts["__spy__"] = {
            "ret20": sp[0] / sp[20] - 1 if len(sp) > 20 else None,
            "ret60": sp[0] / sp[60] - 1 if len(sp) > 60 else None}
    except Exception as e:                                  # noqa: BLE001
        logger.debug("themes momentum facts: %s", e)
    return facts


def _macro_inputs() -> dict[str, Any]:
    """Live inputs the scenario probabilities tilt on."""
    m: dict[str, Any] = {}
    try:
        from app.database import db
        r = db.execute_query(
            "SELECT regime, buckets FROM morning_regime_snapshots"
            " ORDER BY as_of DESC LIMIT 1")
        if r:
            m["regime"] = r[0].get("regime")
            b = r[0].get("buckets")
            if isinstance(b, str):
                b = json.loads(b)
            fwd = (b or {}).get("forward") or {}
            m["fwd_bull"] = _f(fwd.get("p_bullish_20d"))
            m["fwd_bear"] = _f(fwd.get("p_deeper_dip_20d"))
    except Exception as e:                                  # noqa: BLE001
        logger.debug("themes regime inputs: %s", e)
    try:
        from app.signals import liquidity_engine
        liq = liquidity_engine.read() or {}
        m["liquidity_score"] = liq.get("liquidity_score")
        m["liquidity_direction"] = liq.get("liquidity_direction")
    except Exception:                                       # noqa: BLE001
        pass
    _, m["hy_chg20"] = _fred_chg("BAMLH0A0HYM2")
    _, m["real_yield_chg20"] = _fred_chg("DFII10")
    return m


def evaluate() -> dict[str, Any]:
    from app.signals.future_themes import registry
    reg = registry()
    members_by_theme = _members(reg)
    all_syms = sorted({s for ms in members_by_theme.values()
                       for s in ms})
    facts = _member_facts(all_syms)
    spy = facts.pop("__spy__", {})
    probs = _sc.probabilities(_macro_inputs())

    themes: dict[str, Any] = {}
    for key, t in reg.items():
        mems = []
        for sym in members_by_theme.get(key, ()):
            f = dict(facts.get(sym) or {})
            f["symbol"] = sym
            f["exposure"] = (t.get("members") or {}).get(sym)
            f["expo_w"] = _ib.EXPO_W.get(f["exposure"], 0.0)
            mems.append(f)
        legs = {"members": mems, "stage": t.get("stage"),
                "spy_ret20": spy.get("ret20"),
                "spy_ret60": spy.get("ret60")}
        sc_eval = _sc.evaluate_theme(key, probs)
        opp = _opp.score(key, legs, sc_eval["expected"])
        idx = _ib.build(key, mems)
        themes[key] = {
            "name": t.get("name"), "stage": t.get("stage"),
            "thesis": t.get("thesis"),
            "opportunity": opp["score"],
            "verdict": _sc.verdict(opp["score"]),
            **sc_eval,
            "legs": opp["legs"], "missing": opp["missing"],
            "index": {"pure_n": idx["pure"]["n"],
                      "quality_n": idx["quality"]["n"],
                      "ineligible": idx["ineligible"],
                      "top": [{"symbol": s, "weight": w,
                               "score": idx["quality"]
                               ["scores"].get(s)}
                              for s, w in list(
                                  idx["quality"]["weights"]
                                  .items())[:8]]},
            "_weights": idx,
        }
    return {"as_of": str(date.today()),
            "scenario_probs": probs,
            "themes": themes}


def run() -> dict[str, Any]:
    """Weekly compute + journal. Membership rows are append-only —
    PIT membership is what the index actually held, never today's
    survivor list projected backward."""
    from app.database import db
    st = evaluate()
    try:
        db.execute_update(
            "INSERT INTO theme_intelligence_snapshots (as_of, payload)"
            " VALUES (:d, CAST(:p AS jsonb))"
            " ON CONFLICT (as_of) DO UPDATE SET"
            " payload=EXCLUDED.payload",
            {"d": date.today(),
             "p": json.dumps({k: v for k, v in st.items()},
                             default=str)})
        for key, th in (st.get("themes") or {}).items():
            w = th.get("_weights") or {}
            for version, block in (("pure", w.get("pure") or {}),
                                   ("quality",
                                    w.get("quality") or {})):
                for sym, wt in (block.get("weights") or {}).items():
                    db.execute_update(
                        "INSERT INTO theme_index_membership"
                        " (theme_key, as_of, version, symbol, weight,"
                        "  score) VALUES (:t,:d,:v,:s,:w,:sc)"
                        " ON CONFLICT (theme_key,as_of,version,symbol)"
                        " DO UPDATE SET weight=EXCLUDED.weight,"
                        " score=EXCLUDED.score",
                        {"t": key, "d": date.today(), "v": version,
                         "s": sym, "w": wt,
                         "sc": (block.get("scores") or {}).get(sym)})
    except Exception as exc:
        logger.warning("themes journal: %s", exc)
        st["journal_error"] = str(exc)[:120]
    return st


def read() -> Optional[dict[str, Any]]:
    """Latest journaled snapshot — the themes page's fast read."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT as_of, payload FROM theme_intelligence_snapshots"
            " ORDER BY as_of DESC LIMIT 1")
        if not rows:
            return None
        p = rows[0].get("payload")
        if isinstance(p, str):
            p = json.loads(p)
        p = p or {}
        d = rows[0]["as_of"]
        p["as_of"] = str(d)
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        p["age_days"] = (date.today() - d).days
        return p
    except Exception:                                       # noqa: BLE001
        return None
