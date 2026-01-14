"""
Repository for indicators_daily (and future indicators_intraday).
Industry Standard: Repository Pattern; hides SQL dialect differences.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Any, List, Optional
from app.database import db
from app.repositories.base_repository import BaseRepository
from app.exceptions import DatabaseError


@dataclass(frozen=True)
class DailyIndicatorUpsertRow:
    stock_symbol: str
    trade_date: date
    ema9: Optional[float]
    ema21: Optional[float]
    sma50: Optional[float]
    sma100: Optional[float]
    sma200: Optional[float]
    ema12: Optional[float]
    ema26: Optional[float]
    ema20: Optional[float]
    ema50: Optional[float]
    rsi: Optional[float]
    macd: Optional[float]
    macd_signal: Optional[float]
    atr: Optional[float]
    source: Optional[str]


class IndicatorsRepository(BaseRepository):
    """Repository for indicators_daily."""

    @staticmethod
    def upsert_daily_many(rows: Iterable[DailyIndicatorUpsertRow]) -> int:
        rows_list = [
            {
                "symbol": r.stock_symbol,
                "date": r.trade_date,
                "ema9": r.ema9,
                "ema21": r.ema21,
                "sma50": r.sma50,
                "sma100": r.sma100,
                "sma200": r.sma200,
                "ema12": r.ema12,
                "ema26": r.ema26,
                "ema20": r.ema20,
                "ema50": r.ema50,
                "rsi": r.rsi,
                "macd": r.macd,
                "macd_signal": r.macd_signal,
                "atr": r.atr,
                "source": r.source,
            }
            for r in rows
        ]
        try:
            return BaseRepository.upsert_many(
                table="indicators_daily",
                unique_columns=["symbol", "date"],
                rows=rows_list,
            )
        except Exception as e:
            raise DatabaseError(
                f"Failed to upsert daily indicators: {e}",
                details={"rows": len(rows_list)},
            ) from e

    @staticmethod
    def fetch_by_symbol(symbol: str, order_by: str = "trade_date ASC", limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch all indicators for a symbol ordered by date."""
        return BaseRepository.fetch_many(
            table="indicators_daily",
            where={"symbol": symbol},
            select_cols=[
                "trade_date as date",
                "sma_50 as sma50",
                "sma_200 as sma200", 
                "ema_20 as ema20",
                "rsi_14 as rsi",
                "macd as macd_line",
                "macd_signal",
                "macd_hist",
                "signal",
                "confidence_score"
            ],
            order_by=order_by,
            limit=limit,
        )

    @staticmethod
    def fetch_latest_by_symbol(symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch the latest indicators for a symbol"""
        result = BaseRepository.fetch_many(
            table="indicators_daily",
            where={"symbol": symbol},
            select_cols=[
                "sma_50 as sma50",
                "sma_200 as sma200", 
                "ema_20 as ema20",
                "rsi_14 as rsi",
                "macd as macd_line",
                "macd_signal",
                "macd_hist",
                "atr",
                "bb_width",
                "signal",
                "confidence_score"
            ],
            order_by="trade_date DESC",
            limit=1
        )
        return result[0] if result else None

    @staticmethod
    def fetch_recent_symbols(days: int = 30) -> List[str]:
        """Fetch distinct symbols with indicators in the last N days."""
        query = f"""
            SELECT DISTINCT symbol
            FROM indicators_daily
            WHERE date >= CURRENT_DATE - INTERVAL '{days} days'
        """
        result = db.execute_query(query)
        return [r["symbol"] for r in result]
