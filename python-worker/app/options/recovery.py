"""Recovery engine — the closed loop after hedges monetize.

Recovery capital is DERIVED, never seeded from the book: it is the
realized P&L the insurance program actually returned (hedge_positions
trims + closes vs proportional cost). If the hedges never paid, there
is no special capital — entries just follow normal sizing rules.

Deployment is staged on SPY structure reclaims, not on dates or hope:

  stage 1   price back above SMA20   -> deploy 25% of capital
  stage 2   price back above SMA50   -> deploy 35%
  stage 3   price back above SMA200  -> deploy 40%

Abort rule: if the canonical defensive_state re-enters
HEDGE/DEFENSIVE/CAPITULATION, undeployed tranches freeze — recovery
capital is not drawdown purchased early. Deployed rows are journaled
in recovery_deployments; the human executes, same as every layer here.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

STAGE_FRACTIONS = {1: 0.25, 2: 0.35, 3: 0.40}
STAGE_LABELS = {1: "SMA20 reclaim", 2: "SMA50 reclaim",
                3: "SMA200 reclaim"}
_BEARISH = {"HEDGE", "DEFENSIVE", "CAPITULATION"}


def _realized_pnl() -> float:
    """Sum of realized hedge P&L across trims and closes.

    cost is the per-unit net debit; each contract covers 100 units.
    A trim of pct p at mid m realizes p*qty*(m-cost)*100.
    A close realizes remaining_qty*(mark_value-cost)*100 where
    remaining = qty*(1 - sum(trim pcts))."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT qty, cost, mark_value, status, trim_events "
            "FROM hedge_positions "
            "WHERE status IN ('trimmed','closed')")
    except Exception:
        return 0.0
    pnl = 0.0
    for r in rows:
        qty = float(r.get("qty") or 0)
        cost = float(r.get("cost") or 0)
        evs = r.get("trim_events") or []
        if isinstance(evs, str):
            import json as _j
            evs = _j.loads(evs)
        trimmed = 0.0
        for e in evs:
            pct = float(e.get("pct") or 0)
            mid = e.get("mid")
            if mid is not None:
                trimmed += pct
                pnl += pct * qty * (float(mid) - cost) * 100
        if r.get("status") == "closed" and r.get("mark_value") is not None:
            rem = max(0.0, 1.0 - trimmed)
            pnl += rem * qty * (float(r["mark_value"]) - cost) * 100
    return pnl


def _spy_reclaims() -> dict[str, bool]:
    """Which reclaim stages the tape currently satisfies."""
    out = {"sma20": False, "sma50": False, "sma200": False,
           "price": None}
    try:
        from app.market_data import bars as bars_mod
        bars = bars_mod.load(["SPY"], days=260).get("SPY") or []
        if len(bars) < 200:
            return out
        px = bars[-1].close
        out["price"] = px
        for n, key in ((20, "sma20"), (50, "sma50"), (200, "sma200")):
            sma = sum(b.close for b in bars[-n:]) / n
            out[key] = px > sma
    except Exception as exc:
        logger.debug("recovery reclaims: %s", exc)
    return out


def _deployed() -> list[dict[str, Any]]:
    from app.database import db
    try:
        return db.execute_query(
            "SELECT stage, symbol, alloc_usd FROM recovery_deployments "
            "ORDER BY id") or []
    except Exception:
        return []


def record_deployment(stage: int, symbol: str, alloc_usd: float,
                      note: Optional[str] = None) -> dict[str, Any]:
    """Journal a staged recovery entry the human made."""
    from app.database import db
    if stage not in STAGE_FRACTIONS:
        return {"error": "stage must be 1|2|3"}
    db.execute_update(
        "INSERT INTO recovery_deployments (as_of, stage, symbol, "
        "alloc_usd, note) VALUES (:d, :s, :y, :a, :n)",
        {"d": date.today(), "s": stage, "y": symbol.upper(),
         "a": alloc_usd, "n": note})
    return {"recorded": symbol.upper(), "stage": stage,
            "alloc_usd": alloc_usd}


def state() -> dict[str, Any]:
    """The recovery card — capital pool, stage progress, abort flag,
    and the ranked candidates when deployment is armed."""
    try:
        from app.market_regime.defensive_store import (
            DefensiveTransitionStore)
        ds = DefensiveTransitionStore().latest() or {}
    except Exception:
        ds = {}
    d_state = ds.get("stage") or "NORMAL"

    capital = max(0.0, _realized_pnl())
    deployed = _deployed()
    deployed_usd = sum(float(d.get("alloc_usd") or 0) for d in deployed)
    deployed_stages = {int(d["stage"]) for d in deployed}
    remaining = max(0.0, capital - deployed_usd)

    reclaims = _spy_reclaims()
    stage_now = (3 if reclaims["sma200"] else
                 2 if reclaims["sma50"] else
                 1 if reclaims["sma20"] else 0)
    armed = d_state in {"RECOVERY", "NORMAL"} and capital > 0
    frozen = d_state in _BEARISH

    # next tranche = the smallest un-deployed stage the tape has earned
    next_stage = next((s for s in (1, 2, 3)
                       if s <= stage_now and s not in deployed_stages),
                      None)
    tranche = round(capital * STAGE_FRACTIONS[next_stage], 0) \
        if next_stage else 0.0

    out = {
        "defensive_state": d_state,
        "recovery_capital": round(capital, 0),
        "deployed_usd": round(deployed_usd, 0),
        "remaining_usd": round(remaining, 0),
        "spy_reclaims": {k: v for k, v in reclaims.items()
                         if k != "price"},
        "stage_available": stage_now,
        "next_stage": next_stage,
        "next_tranche_usd": tranche,
        "deployments": deployed,
        "frozen": frozen,
        "armed": armed and not frozen,
    }
    if frozen:
        out["note"] = ("defensive state re-entered — undeployed "
                       "tranches frozen; deployed names carry their "
                       "own stops")
    elif armed and next_stage:
        try:
            from app.options.crash_alpha import redeploy_candidates
            out["candidates"] = redeploy_candidates(tranche)
        except Exception:
            out["candidates"] = []
    return out
