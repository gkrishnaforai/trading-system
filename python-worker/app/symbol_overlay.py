"""Symbol overlay: cheap per-symbol context shared by the screener and alerts.

Persisted sources only — no provider calls, so scans stay fast:
  - symbol_fair_values   → our fair value + valuation regime
  - alert_items          → latest scanned catalyst (direction, event)
  - grade_change_events  → latest analyst upgrade/downgrade

fund_signal() rolls them into one verdict so the screener and the alerts
surface judge a symbol's fundamental backdrop the same way.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

CATALYST_LOOKBACK_DAYS = 10
GRADE_LOOKBACK_DAYS = 14


def persisted_overlay(symbols: list[str]) -> dict[str, dict]:
    """{symbol: {fair_value, fv_regime, catalyst_direction, catalyst_event,
                 grade_action, grade_company, grade_date}}"""
    from app.database import db

    overlay: dict[str, dict] = {}
    syms = [s.upper() for s in symbols if s]
    if not syms:
        return overlay

    try:
        for r in db.execute_query(
            "SELECT symbol, fair_value, regime FROM symbol_fair_values "
            "WHERE symbol = ANY(:symbols)",
            {"symbols": syms},
        ):
            slot = overlay.setdefault(r["symbol"].upper(), {})
            slot["fair_value"] = r["fair_value"]
            slot["fv_regime"] = r["regime"]
    except Exception as exc:
        logger.debug("overlay fair-value lookup failed: %s", exc)

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=CATALYST_LOOKBACK_DAYS)
        for r in db.execute_query(
            """
            SELECT DISTINCT ON (symbol) symbol, direction, event_type
            FROM alert_items
            WHERE symbol = ANY(:symbols) AND created_at >= :cutoff
            ORDER BY symbol, created_at DESC
            """,
            {"symbols": syms, "cutoff": cutoff},
        ):
            slot = overlay.setdefault(r["symbol"].upper(), {})
            slot["catalyst_direction"] = r["direction"]
            slot["catalyst_event"] = r["event_type"]
    except Exception as exc:
        logger.debug("overlay catalyst lookup failed: %s", exc)

    try:
        # Most recent actual revision within the lookback — not the latest-day
        # diff (which reads 0% once a revision has been absorbed). If several
        # fiscal years moved on the same day, take the largest absolute move.
        cutoff_d = (datetime.now(timezone.utc) - timedelta(days=CATALYST_LOOKBACK_DAYS)).date()
        for r in db.execute_query(
            """
            WITH ranked AS (
                SELECT symbol, as_of_date, fiscal_year, eps_estimate,
                       lag(eps_estimate) OVER (
                           PARTITION BY symbol, fiscal_period, fiscal_year
                           ORDER BY as_of_date
                       ) AS prev_eps
                FROM fundamental_estimate_snapshots
                WHERE symbol = ANY(:symbols) AND fiscal_period = 'annual'
                  AND eps_estimate IS NOT NULL
            ), deltas AS (
                SELECT symbol, as_of_date, fiscal_year,
                       (eps_estimate - prev_eps) / abs(prev_eps) * 100 AS delta_pct
                FROM ranked
                WHERE prev_eps IS NOT NULL AND prev_eps <> 0
            )
            SELECT DISTINCT ON (symbol) symbol,
                   ROUND(delta_pct::numeric, 1) AS eps_delta_pct,
                   fiscal_year AS eps_fiscal_year,
                   as_of_date AS eps_revision_date
            FROM deltas
            WHERE delta_pct <> 0 AND as_of_date >= :cutoff
            ORDER BY symbol, as_of_date DESC, abs(delta_pct) DESC
            """,
            {"symbols": syms, "cutoff": cutoff_d},
        ):
            slot = overlay.setdefault(r["symbol"].upper(), {})
            slot["eps_delta_pct"] = float(r["eps_delta_pct"])
            slot["eps_fiscal_year"] = r["eps_fiscal_year"]
            slot["eps_revision_date"] = r["eps_revision_date"].isoformat() if r["eps_revision_date"] else None
    except Exception as exc:
        logger.debug("overlay eps-revision lookup failed: %s", exc)

    try:
        cutoff_d = (datetime.now(timezone.utc) - timedelta(days=GRADE_LOOKBACK_DAYS)).date()
        for r in db.execute_query(
            """
            SELECT DISTINCT ON (symbol) symbol, event_type, grading_company, grade_date
            FROM grade_change_events
            WHERE symbol = ANY(:symbols) AND grade_date >= :cutoff
              AND event_type IN ('upgrade', 'downgrade')
            ORDER BY symbol, grade_date DESC
            """,
            {"symbols": syms, "cutoff": cutoff_d},
        ):
            slot = overlay.setdefault(r["symbol"].upper(), {})
            slot["grade_action"] = r["event_type"]
            slot["grade_company"] = r["grading_company"]
            slot["grade_date"] = r["grade_date"].isoformat() if r["grade_date"] else None
    except Exception as exc:
        logger.debug("overlay grade lookup failed: %s", exc)

    return overlay


def estimate_refresh_triggers(symbols: list[str]) -> set[str]:
    """Symbols whose estimates plausibly moved today — event-driven re-poll.

    Baseline snapshot cadence is daily (watermark on as_of_date), but a
    same-day event means analysts may already have revised: reported
    earnings, a grade change, or a fresh alert catalyst. One batched
    lookup per scan; the screener bypasses the watermark for these names.
    """
    from app.database import db

    syms = [s.upper() for s in symbols if s]
    if not syms:
        return set()
    today = date.today()
    triggered: set[str] = set()
    for sql, params in (
        ("SELECT DISTINCT symbol FROM grade_change_events"
         " WHERE symbol = ANY(:symbols) AND grade_date >= :d",
         {"symbols": syms, "d": today}),
        ("SELECT DISTINCT symbol FROM earnings_calendar"
         " WHERE symbol = ANY(:symbols) AND earnings_date >= :d",
         {"symbols": syms, "d": today - timedelta(days=1)}),
        ("SELECT DISTINCT symbol FROM alert_items"
         " WHERE symbol = ANY(:symbols) AND created_at >= :d",
         {"symbols": syms, "d": datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)}),
    ):
        try:
            triggered.update(r["symbol"].upper() for r in db.execute_query(sql, params))
        except Exception as exc:
            logger.debug("estimate refresh trigger lookup failed: %s", exc)
    return triggered


def fund_signal(price: Optional[float], ov: dict[str, Any]) -> tuple[Optional[float], str]:
    """(fv_upside_pct, signal) where signal ∈ strong | neutral | weak | unknown.

    Vote count: fair-value upside ≥+15% or ≤−10% → ±1; latest catalyst
    direction → ±1; latest analyst upgrade/downgrade → ±1. Conflicting
    evidence nets to neutral rather than picking a side.
    """
    fv = ov.get("fair_value")
    upside = ((fv - price) / price * 100) if fv and price else None
    votes = 0
    if upside is not None:
        votes += 1 if upside >= 15 else (-1 if upside <= -10 else 0)
    direction = str(ov.get("catalyst_direction") or "").upper()
    if direction == "POSITIVE":
        votes += 1
    elif direction == "NEGATIVE":
        votes -= 1
    action = ov.get("grade_action")
    if action == "upgrade":
        votes += 1
    elif action == "downgrade":
        votes -= 1
    eps_delta = ov.get("eps_delta_pct")
    if eps_delta is not None:
        votes += 1 if eps_delta >= 5 else (-1 if eps_delta <= -5 else 0)
    if upside is None and not direction and not action and eps_delta is None:
        return upside, "unknown"
    return upside, "strong" if votes > 0 else "weak" if votes < 0 else "neutral"
