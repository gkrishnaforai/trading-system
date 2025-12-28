"""Utilities for common query patterns (DRY)."""

from typing import Any, Dict, List, Optional
from datetime import date, datetime

from app.database import db


def fetch_latest_by_symbol(
    table: str,
    symbol: str,
    date_column: str = "trade_date",
    select_cols: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch the latest row for a symbol by date/timestamp."""
    cols = ", ".join(select_cols) if select_cols else "*"
    # Postgres-only: same query works for both
    query = f"SELECT {cols} FROM {table} WHERE stock_symbol = :symbol ORDER BY {date_column} DESC LIMIT 1"
    result = db.execute_query(query, {"symbol": symbol})
    return result[0] if result else None


def fetch_recent_symbols(
    table: str,
    hours: Optional[int] = None,
    days: Optional[int] = None,
    ts_column: str = "ts",
    date_column: str = "trade_date",
    interval_filter: Optional[str] = None,
) -> List[str]:
    """Fetch distinct symbols with recent activity. Use hours for intraday, days for daily."""
    if hours and days:
        raise ValueError("Specify either hours or days, not both.")
    if not hours and not days:
        raise ValueError("Specify either hours or days.")

    query_parts = [f"SELECT DISTINCT stock_symbol FROM {table}"]
    conditions = []
    if interval_filter:
        conditions.append("interval = :interval")
    if hours:
        # Postgres-only: use INTERVAL syntax
        conditions.append(f"{ts_column} >= NOW() - INTERVAL '{hours} hours'")
    elif days:
        # Postgres-only: use INTERVAL syntax
        conditions.append(f"{date_column} >= CURRENT_DATE - INTERVAL '{days} days'")
    if conditions:
        query_parts.append(" WHERE " + " AND ".join(conditions))

    query = "".join(query_parts)
    params = {"interval": interval_filter} if interval_filter else {}
    result = db.execute_query(query, params)
    return [r["stock_symbol"] for r in result]
