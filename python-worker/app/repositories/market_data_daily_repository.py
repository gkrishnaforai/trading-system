from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Any, List, Optional, Iterable
from .base_repository import BaseRepository
from ..models.market_data import DailyBarUpsertRow
from ..database import db
from ..exceptions import DatabaseError
from ..observability.logging import get_logger

logger = get_logger(__name__)


class TechnicalIndicatorUpsertRow:
    stock_symbol: str
    date: date
    sma_20: Optional[float]
    sma_50: Optional[float]
    sma_200: Optional[float]
    ema_12: Optional[float]
    ema_26: Optional[float]
    rsi_14: Optional[float]
    macd: Optional[float]
    macd_signal: Optional[float]
    macd_histogram: Optional[float]
    bollinger_upper: Optional[float]
    bollinger_middle: Optional[float]
    bollinger_lower: Optional[float]
    stoch_k: Optional[float]
    stoch_d: Optional[float]
    atr_14: Optional[float]
    adx: Optional[float]
    cci: Optional[float]
    roc: Optional[float]
    williams_r: Optional[float]
    source: Optional[str]


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
    """Repository for stock_market_metrics (daily)."""

    @staticmethod
    def _ensure_stock_id(symbol: str) -> str:
        row = db.execute_query(
            """
            INSERT INTO stocks (symbol)
            VALUES (:symbol)
            ON CONFLICT (symbol) DO UPDATE SET symbol = EXCLUDED.symbol
            RETURNING id
            """,
            {"symbol": symbol},
        )
        if not row or not row[0].get("id"):
            raise DatabaseError("Failed to resolve stock_id", details={"symbol": symbol})
        return row[0]["id"]

    @staticmethod
    def upsert_many(rows: Iterable[DailyBarUpsertRow]) -> int:
        rows_list = [
            {
                "symbol": r.stock_symbol,
                "date": r.trade_date,
                "open_price": r.open,
                "high_price": r.high,
                "low_price": r.low,
                "close_price": r.close,
                "adj_close_price": r.adj_close,
                "volume": r.volume,
                "source": r.source,
            }
            for r in rows
        ]

        # Resolve stock_id for each row (dedupe symbols).
        symbol_to_stock_id: Dict[str, str] = {}
        for r in rows_list:
            sym = r.get("symbol")
            if not sym:
                continue
            if sym not in symbol_to_stock_id:
                symbol_to_stock_id[sym] = MarketDataDailyRepository._ensure_stock_id(sym)

        # Translate to raw_market_data_daily rows
        upsert_rows = [
            {
                "symbol": r.get("symbol"),
                "date": r.get("date"),
                "open": r.get("open_price"),
                "high": r.get("high_price"),
                "low": r.get("low_price"),
                "close": r.get("close_price"),
                "adjusted_close": r.get("adj_close_price"),
                "volume": r.get("volume"),
                "data_source": r.get("source"),
            }
            for r in rows_list
        ]
        try:
            return BaseRepository.upsert_many(
                table="raw_market_data_daily",
                unique_columns=["symbol", "date", "data_source"],
                rows=upsert_rows,
            )
        except Exception as e:
            raise DatabaseError(
                f"Failed to upsert daily market data: {e}",
                details={"rows": len(rows_list)},
            ) from e

    @staticmethod
    def upsert_indicators(rows: Iterable[TechnicalIndicatorUpsertRow]) -> int:
        rows_list = [
            {
                "symbol": r.stock_symbol,
                "date": r.date,
                "sma_20": r.sma_20,
                "sma_50": r.sma_50,
                "sma_200": r.sma_200,
                "ema_12": r.ema_12,
                "ema_26": r.ema_26,
                "rsi_14": r.rsi_14,
                "macd": r.macd,
                "macd_signal": r.macd_signal,
                "macd_histogram": r.macd_histogram,
                "bollinger_upper": r.bollinger_upper,
                "bollinger_middle": r.bollinger_middle,
                "bollinger_lower": r.bollinger_lower,
                "stoch_k": r.stoch_k,
                "stoch_d": r.stoch_d,
                "atr_14": r.atr_14,
                "adx": r.adx,
                "cci": r.cci,
                "roc": r.roc,
                "williams_r": r.williams_r,
                "source": r.source,
            }
            for r in rows
        ]

        # Resolve stock_id for each row (dedupe symbols).
        symbol_to_stock_id: Dict[str, str] = {}
        for r in rows_list:
            sym = r.get("symbol")
            if not sym:
                continue
            if sym not in symbol_to_stock_id:
                symbol_to_stock_id[sym] = MarketDataDailyRepository._ensure_stock_id(sym)

        upsert_rows = [
            {
                "stock_id": symbol_to_stock_id.get(r.get("symbol")),
                "date": r.get("date"),
                "sma_20": r.get("sma_20"),
                "sma_50": r.get("sma_50"),
                "sma_200": r.get("sma_200"),
                "ema_12": r.get("ema_12"),
                "ema_26": r.get("ema_26"),
                "rsi_14": r.get("rsi_14"),
                "macd": r.get("macd"),
                "macd_signal": r.get("macd_signal"),
                "macd_histogram": r.get("macd_histogram"),
                "bollinger_upper": r.get("bollinger_upper"),
                "bollinger_middle": r.get("bollinger_middle"),
                "bollinger_lower": r.get("bollinger_lower"),
                "stoch_k": r.get("stoch_k"),
                "stoch_d": r.get("stoch_d"),
                "atr_14": r.get("atr_14"),
                "adx": r.get("adx"),
                "cci": r.get("cci"),
                "roc": r.get("roc"),
                "williams_r": r.get("williams_r"),
                "source": r.get("source"),
            }
            for r in rows_list
            if r.get("symbol") in symbol_to_stock_id
        ]
        try:
            return BaseRepository.upsert_many(
                table="stock_technical_indicators",
                unique_columns=["stock_id", "date", "source"],
                rows=upsert_rows,
            )
        except Exception as e:
            raise DatabaseError(
                f"Failed to upsert technical indicators: {e}",
                details={"rows": len(rows_list)},
            ) from e

    @staticmethod
    def fetch_by_symbol(symbol: str, order_by: str = "trade_date ASC", limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch daily closes for a symbol ordered by date."""

        order_clause = "date ASC"
        if order_by:
            # Backward compatible: map trade_date -> date
            order_clause = order_by.replace("trade_date", "date")

        query = f"""
            SELECT m.date as date,
                   m.open_price as open,
                   m.high_price as high,
                   m.low_price as low,
                   m.close_price as close,
                   m.adj_close_price as adj_close,
                   m.volume as volume
            FROM stock_market_metrics m
            JOIN stocks s ON s.id = m.stock_id
            WHERE s.symbol = :symbol
            ORDER BY {order_clause}
        """
        if limit is not None:
            query += " LIMIT :limit"
            return db.execute_query(query, {"symbol": symbol, "limit": int(limit)})
        return db.execute_query(query, {"symbol": symbol})

    @staticmethod
    def fetch_indicators_by_symbol(symbol: str, order_by: str = "date ASC", limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch technical indicators for a symbol ordered by date."""
        order_clause = order_by

        query = f"""
            SELECT i.date as date,
                   i.sma_20, i.sma_50, i.sma_200,
                   i.ema_12, i.ema_26,
                   i.rsi_14,
                   i.macd, i.macd_signal, i.macd_histogram,
                   i.bollinger_upper, i.bollinger_middle, i.bollinger_lower,
                   i.stoch_k, i.stoch_d,
                   i.atr_14, i.adx, i.cci, i.roc, i.williams_r
            FROM stock_technical_indicators i
            JOIN stocks s ON s.id = i.stock_id
            WHERE s.symbol = :symbol
            ORDER BY {order_clause}
        """
        if limit is not None:
            query += " LIMIT :limit"
            return db.execute_query(query, {"symbol": symbol, "limit": int(limit)})
        return db.execute_query(query, {"symbol": symbol})
