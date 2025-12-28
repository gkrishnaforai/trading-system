from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Any, List, Optional
from app.database import db
from app.repositories.base_repository import BaseRepository
from app.exceptions import DatabaseError


@dataclass(frozen=True)
class DailyBarUpsertRow:
    stock_symbol: str
    trade_date: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    adj_close: Optional[float]
    volume: Optional[int]
    source: Optional[str]


class MarketDataDailyRepository(BaseRepository):
    """Repository for raw_market_data_daily."""

    @staticmethod
    def upsert_many(rows: Iterable[DailyBarUpsertRow]) -> int:
        rows_list = [
            {
                "stock_symbol": r.stock_symbol,
                "trade_date": r.trade_date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "adj_close": r.adj_close,
                "volume": r.volume,
                "source": r.source,
            }
            for r in rows
        ]
        try:
            return BaseRepository.upsert_many(
                table="raw_market_data_daily",
                unique_columns=["stock_symbol", "trade_date"],
                rows=rows_list,
            )
        except Exception as e:
            raise DatabaseError(
                f"Failed to upsert daily market data: {e}",
                details={"rows": len(rows_list)},
            ) from e

    @staticmethod
    def fetch_by_symbol(symbol: str, order_by: str = "trade_date ASC", limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch all daily bars for a symbol ordered by date."""
        return BaseRepository.fetch_many(
            table="raw_market_data_daily",
            where={"stock_symbol": symbol},
            select_cols=["trade_date as date", "open", "high", "low", "close", "volume"],
            order_by=order_by,
            limit=limit,
        )
