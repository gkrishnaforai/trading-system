"""Earnings calendar — feeds the existing earnings pipeline, doesn't
replace it.

    yfinance calendar + earnings_dates
        → earnings_data            (canonical event table: est/actual/
                                    surprise per print)
        → EarningsIndexService     (derives stocks.next_earnings_* —
                                    date/session/source/timezone)
        → stocks.next_earnings_eps_est / next_earnings_rev_est
                                   (consensus for the upcoming print —
                                    the only new columns, migration 071)

Alerting is intentionally NOT here: app.alerts.scanner already emits
"earnings in N days" / "EPS surprise" alerts off the same tables when
screeners run. This module's job is keeping them fed.

Sources: yfinance Ticker.calendar (next date + consensus) and
Ticker.earnings_dates (history). FMP earnings-calendar endpoints are
legacy-gated on the current tier.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

HISTORY_EVENTS = 8        # past prints to keep synced in earnings_data


def _sync_earnings_events(sym: str, tk,
                          eps_est=None, rev_est=None) -> None:
    """Upsert the last ~8 earnings events + the upcoming print into
    earnings_data. Past rows carry actuals + surprise; the upcoming row
    carries the consensus estimates so next_earnings_* has full context."""
    import pandas as pd
    from app.database import db
    try:
        ed = tk.earnings_dates
    except Exception as exc:
        logger.debug("earnings_dates %s failed: %s", sym, exc)
        return
    if ed is None or ed.empty:
        return
    for idx, row in ed.head(HISTORY_EVENTS + 2).iterrows():
        try:
            rep = idx.date() if hasattr(idx, "date") else idx
            is_future = rep >= date.today()
            db.execute_update(
                "INSERT INTO earnings_data "
                "(stock_symbol, earnings_date, eps_estimate, eps_actual, "
                " revenue_estimate, surprise_percentage, source) "
                "VALUES (:s, :d, :est, :act, :rev, :surp, 'yahoo') "
                "ON CONFLICT (stock_symbol, earnings_date) DO UPDATE SET "
                "eps_estimate = COALESCE(EXCLUDED.eps_estimate, "
                "                        earnings_data.eps_estimate), "
                "eps_actual = COALESCE(EXCLUDED.eps_actual, "
                "                      earnings_data.eps_actual), "
                "revenue_estimate = COALESCE(EXCLUDED.revenue_estimate, "
                "                        earnings_data.revenue_estimate), "
                "surprise_percentage = COALESCE(EXCLUDED.surprise_percentage, "
                "                        earnings_data.surprise_percentage), "
                "updated_at = now()",
                {"s": sym, "d": rep,
                 "est": (float(row["EPS Estimate"])
                         if pd.notna(row.get("EPS Estimate"))
                         else (float(eps_est) if is_future and eps_est
                               else None)),
                 "act": (float(row["Reported EPS"])
                         if pd.notna(row.get("Reported EPS")) else None),
                 "rev": (int(rev_est) if is_future and rev_est else None),
                 "surp": (float(row["Surprise(%)"])
                          if pd.notna(row.get("Surprise(%)")) else None)})
        except Exception as exc:
            logger.debug("earnings_data upsert %s %s: %s", sym, idx, exc)


def refresh_earnings_calendar(sym: str) -> dict:
    """Refresh one symbol's earnings calendar. Called from
    compute_flywheel so every existing refresh path (board evals, LEAPS
    screens, fundamentals data loads) keeps the calendar current."""
    from app.database import db
    from app.signals.expectation_gap import _ensure_stock
    from app.services.earnings_index_service import EarningsIndexService
    sym = sym.upper().strip()
    out: dict[str, Any] = {"symbol": sym}
    try:
        _ensure_stock(sym)
        import yfinance as yf
        tk = yf.Ticker(sym)
        cal = tk.calendar or {}
        dates = cal.get("Earnings Date") or []
        next_date = dates[0] if dates else None
        if isinstance(next_date, datetime):
            next_date = next_date.date()
        eps_est, rev_est = (cal.get("Earnings Average"),
                            cal.get("Revenue Average"))

        _sync_earnings_events(sym, tk, eps_est, rev_est)
        # Derive stocks.next_earnings_* (date/session/source/tz) from the
        # event table via the existing indexer, then stamp the consensus
        # snapshot on top.
        EarningsIndexService().update_stock_next_earnings(sym)
        if next_date or eps_est or rev_est:
            db.execute_update(
                "UPDATE stocks SET next_earnings_eps_est=:e, "
                "next_earnings_rev_est=:r WHERE symbol=:s",
                {"s": sym, "e": eps_est, "r": rev_est})
        out = {"symbol": sym, "next_earnings_date": next_date,
               "eps_est": eps_est, "rev_est": rev_est}
    except Exception as exc:
        logger.debug("earnings calendar %s: %s", sym, exc)
    return out


def earnings_window(days: int = 14) -> list[dict]:
    """Symbols with a print inside the window — for UI banners and the
    eval-time 'earnings risk' flag."""
    from app.database import db
    return db.execute_query(
        "SELECT symbol, next_earnings_date, next_earnings_eps_est, "
        "next_earnings_rev_est, next_earnings_session, "
        "next_earnings_date - CURRENT_DATE AS days_out "
        "FROM stocks WHERE next_earnings_date BETWEEN CURRENT_DATE "
        "AND CURRENT_DATE + :d ORDER BY next_earnings_date",
        {"d": days})
