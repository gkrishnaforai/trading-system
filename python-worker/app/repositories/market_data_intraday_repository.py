"""
Repository for raw_market_data_intraday.
Industry Standard: Repository Pattern; hides SQL dialect differences.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from app.repositories.base_repository import BaseRepository
from app.exceptions import DatabaseError


@dataclass(frozen=True)
class IntradayBarUpsertRow:
    stock_symbol: str
    ts: datetime
    interval: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[int]
    source: Optional[str]


class MarketDataIntradayRepository(BaseRepository):
    """Repository for raw_market_data_intraday."""

    @staticmethod
    def upsert_many(rows: Iterable[IntradayBarUpsertRow]) -> int:
        rows_list = [
            {
                "symbol": r.stock_symbol,  # Map to actual column name
                "ts": r.ts,
                "interval": r.interval,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "data_source": r.source,  # Map to actual column name
            }
            for r in rows
        ]
        try:
            return BaseRepository.upsert_many(
                table="raw_market_data_intraday",
                unique_columns=["symbol", "ts", "interval", "data_source"],  # Include data_source to match actual constraint
                rows=rows_list,
            )
        except Exception as e:
            raise DatabaseError(
                f"Failed to upsert intraday market data: {e}",
                details={"rows": len(rows_list)},
            ) from e

    @staticmethod
    def fetch_latest_by_symbol(symbol: str, interval: str = "last", limit: int = 2) -> List[Dict[str, Any]]:
        return BaseRepository.fetch_many(
            table="raw_market_data_intraday",
            where={"symbol": symbol, "interval": interval},
            select_cols=["ts", "close"],
            order_by="ts DESC",
            limit=limit,
        )

    @staticmethod
    def fetch_recent_symbols(hours: int = 24) -> List[str]:
        """Fetch distinct symbols with intraday data in the last N hours."""
        # Postgres-only: use INTERVAL syntax
        query = f"""
            SELECT DISTINCT symbol
            FROM raw_market_data_intraday
            WHERE interval = 'last'
              AND ts >= NOW() - INTERVAL '{hours} hours'
        """
        result = db.execute_query(query)
        return [r["symbol"] for r in result]
