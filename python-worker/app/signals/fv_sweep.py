"""Fair-value sweep — keeps fair_value_v2_runs fresh for the tracked
universe.

Two guarantees per symbol:
  1. eps freshness: if the last quarterly print is newer than the
     stored fmp_fundamentals snapshot, refetch the fundamentals
     bundle first — FV never prices a name on pre-print estimates.
  2. FV recompute: FairValueV2Resolver.resolve() re-runs the method
     blend; its inputs watermark makes unchanged inputs a cheap reuse.

The weekly job covers drift; refresh_after_print() is the earnings-day
hook earnings_watch calls the moment a print lands, so 'eps from the
last quarterly report' holds within minutes, not just weekly.
"""

import logging
from typing import Any, Dict, List

from app.database import db

logger = logging.getLogger(__name__)


def _needs_fundamentals_refresh(sym: str,
                                max_snapshot_age_days: int = 30) -> bool:
    """Refresh when (a) the last actual print landed after the latest
    fmp_fundamentals snapshot → the stored eps_forward predates the
    report, or (b) the bundle itself is stale — estimates drift
    between prints, and a month-old snapshot can be missing fields
    entirely (AAPL/MA/PYPL resolved every FV method to missing_data
    on Sep-26 payloads that never refreshed between prints)."""
    snap = db.execute_query(
        "SELECT MAX(generated_at)::date AS d"
        " FROM stock_insights_snapshots"
        " WHERE stock_symbol=:s AND source='fmp_fundamentals'",
        {"s": sym})[0]["d"]
    rep = db.execute_query(
        "SELECT MAX(earnings_date) AS d FROM earnings_data"
        " WHERE stock_symbol=:s AND eps_actual IS NOT NULL",
        {"s": sym})[0]["d"]
    if rep and (not snap or rep > snap):
        return True
    if not snap:
        return True
    from datetime import date
    return (date.today() - snap).days > max_snapshot_age_days


def _resolve_fv(sym: str) -> Dict[str, Any]:
    from app.fair_value_v2.resolver import FairValueV2Resolver
    res, meta = FairValueV2Resolver().resolve(sym)
    return {"fv": res.fair_value, "regime": res.regime,
            "reused": bool(meta.get("reused"))}


def _fundamentals_snap_stamp(sym: str):
    """Latest fmp_fundamentals snapshot stamp — the row the resolver's
    inputs watermark actually reads."""
    try:
        return db.execute_query(
            "SELECT MAX(generated_at) AS g FROM stock_insights_snapshots"
            " WHERE stock_symbol=:s AND source='fmp_fundamentals'",
            {"s": sym})[0]["g"]
    except Exception:
        return None


def refresh_after_print(sym: str) -> Dict[str, Any]:
    """Post-print refresh: refetch the FMP fundamentals bundle (fresh
    eps_forward, estimates, TTM actuals) then re-resolve FV. Reports
    honestly — a fetch that wrote no new snapshot is not 'refreshed':
    re-resolving on the same inputs just stamps a fresh run on the
    same broken blend (TEM kept showing '2d old run' on 86d inputs)."""
    out: Dict[str, Any] = {"symbol": sym}
    before = _fundamentals_snap_stamp(sym)
    try:
        from app.data_management.refresh_manager import (
            DataRefreshManager, RefreshMode)
        res = DataRefreshManager().refresh_fundamentals_bundle(
            sym, mode=RefreshMode.ON_DEMAND, force=True)
        after = _fundamentals_snap_stamp(sym)
        if after is not None and (before is None or after > before):
            out["fundamentals"] = "refreshed"
            # re-score the derived state — the bundle refresh updates raw
            # inputs but stocks.fundamental_state/risk/detail only move
            # when the flywheel recomputes and fundamental_health grades
            try:
                from app.providers.financial_modeling_prep.client import (
                    EnhancedFMPClient)
                from app.signals.expectation_gap import compute_flywheel
                from app.signals import fundamental_health
                compute_flywheel(EnhancedFMPClient.from_settings(), sym)
                fundamental_health.refresh_all([sym])
                out["fundamental_state"] = "rescored"
            except Exception as exc:
                logger.warning(
                    "fv_sweep fundamental rescore %s: %s", sym, exc)
                out["fundamental_state"] = f"error: {exc}"
        else:
            failed = getattr(res, "total_failed", None)
            req = getattr(res, "total_requested", None)
            out["fundamentals"] = (
                "no_new_snapshot"
                + (f" ({failed}/{req} legs failed)"
                   if failed is not None and req is not None else ""))
    except Exception as exc:
        logger.warning("fv_sweep refresh %s: %s", sym, exc)
        out["fundamentals"] = f"error: {exc}"
    try:
        out.update(_resolve_fv(sym))
    except Exception as exc:
        logger.warning("fv_sweep resolve %s: %s", sym, exc)
        out["fv"] = f"error: {exc}"
    return out


def run(symbols: List[str]) -> Dict[str, Any]:
    stats: Dict[str, Any] = {"symbols": len(symbols),
                             "fund_refreshed": 0, "fv_runs": 0,
                             "fv_reused": 0, "errors": []}
    for sym in symbols:
        try:
            if _needs_fundamentals_refresh(sym):
                r = refresh_after_print(sym)
                stats["fund_refreshed"] += 1
                if isinstance(r.get("fv"), (int, float)):
                    stats["fv_runs"] += 1
                continue
            r = _resolve_fv(sym)
            stats["fv_reused" if r.get("reused") else "fv_runs"] += 1
        except Exception as exc:
            logger.warning("fv_sweep %s: %s", sym, exc)
            stats["errors"].append(f"{sym}: {exc}")
    return stats
