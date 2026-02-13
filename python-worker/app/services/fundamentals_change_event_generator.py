"""Fundamentals Change Event Generator

Generates coarse fundamentals change events from the canonical fundamentals snapshot payload.
This is intentionally conservative until we add a richer change-detection engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        if isinstance(v, bool):
            return None
        return float(v)
    except Exception:
        return None


def _pick_first_row(rows: Any) -> Optional[Dict[str, Any]]:
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


def _extract_as_of_date(payload: Dict[str, Any]) -> Optional[date]:
    meta = payload.get("meta") if isinstance(payload, dict) else None
    if isinstance(meta, dict) and meta.get("as_of_date"):
        raw = str(meta.get("as_of_date"))
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def generate_events_from_fundamentals_snapshot(symbol: str, fundamentals: Dict[str, Any]) -> Tuple[Optional[date], List[Dict[str, Any]]]:
    symbol = (symbol or "").strip().upper()
    if not symbol or not isinstance(fundamentals, dict):
        return None, []

    as_of = _extract_as_of_date(fundamentals)

    events: List[Dict[str, Any]] = []

    # Revenue growth deterioration (from statement_growth income_statement)
    sg = fundamentals.get("statement_growth")
    income_g = None
    if isinstance(sg, dict):
        income_g = _pick_first_row(sg.get("income_statement"))

    rev_growth = None
    if isinstance(income_g, dict):
        # FMP tends to use camelCase keys; keep fallbacks.
        rev_growth = (
            income_g.get("growthRevenue")
            or income_g.get("revenueGrowth")
            or income_g.get("revenue_growth")
        )
    rev_growth_f = _to_float(rev_growth)
    if rev_growth_f is not None and rev_growth_f < 0:
        events.append(
            {
                "stock_symbol": symbol,
                "as_of_date": as_of,
                "event_type": "fundamentals_growth",
                "event_key": "revenue_growth_negative",
                "headline": "Revenue growth turned negative",
                "severity": "HIGH" if rev_growth_f < -0.1 else "MEDIUM",
                "direction": "negative",
                "evidence": {"revenue_growth": rev_growth_f},
                "recommended_action": "Avoid adding; consider trimming if technical signal is BUY",
                "payload": {"revenue_growth": rev_growth_f},
            }
        )

    # Leverage risk (from financial_ratios)
    fr = _pick_first_row(fundamentals.get("financial_ratios"))
    debt_to_equity = None
    if isinstance(fr, dict):
        debt_to_equity = (
            fr.get("debtEquityRatio")
            or fr.get("debtToEquity")
            or fr.get("debt_to_equity")
        )
    dte = _to_float(debt_to_equity)
    if dte is not None and dte >= 2.0:
        events.append(
            {
                "stock_symbol": symbol,
                "as_of_date": as_of,
                "event_type": "balance_sheet",
                "event_key": "debt_to_equity_high",
                "headline": "Debt-to-equity elevated",
                "severity": "HIGH" if dte >= 3.0 else "MEDIUM",
                "direction": "negative",
                "evidence": {"debt_to_equity": dte},
                "recommended_action": "Reduce position size; require stronger technical confirmation",
                "payload": {"debt_to_equity": dte},
            }
        )

    return as_of, events
