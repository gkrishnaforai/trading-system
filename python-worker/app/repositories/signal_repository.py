"""Signal Repository
Handles database operations for signal storage and retrieval.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional
from datetime import date
import json

from app.exceptions import DatabaseError
from app.database import db
from app.repositories.base_repository import BaseRepository
from app.signal_engines.base import SignalResult
from app.signal_engines.aggregation_service import AggregatedSignalResult
from app.observability.logging import get_logger

logger = get_logger(__name__)


class SignalRepository(BaseRepository):
    """Repository for stock_signals_snapshots + signal_screener_cache."""

    @staticmethod
    def save_signal_result(result: SignalResult) -> int:
        """
        Save a single signal result to database
        
        Args:
            result: SignalResult to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # First, get stock_id from symbol
            stock_query = "SELECT id FROM stocks WHERE symbol = :symbol"
            stock_result = db.execute_query(stock_query, {"symbol": result.symbol})
            
            if not stock_result:
                raise DatabaseError(f"Stock {result.symbol} not found in stocks table")
            
            stock_id = stock_result[0]["id"]
            
            # Map SignalResult to stock_signals table schema
            row = {
                "stock_id": stock_id,
                "engine_name": result.engine_name,
                "engine_version": result.engine_version,
                "engine_tier": result.engine_tier.value,
                "signal": result.signal.value,
                "confidence": result.confidence,
                "fair_value": None,  # Not in SignalResult
                "upside_pct": None,  # Not in SignalResult  
                "reasoning": result.reasoning,
                "metadata": result.metadata,
                "created_at": result.generated_at,
            }

            return BaseRepository.upsert_many(
                table="stock_signals",
                unique_columns=["stock_id", "engine_name"],
                rows=[row],
            )
        except Exception as e:
            raise DatabaseError(
                f"Failed to save signal result: {e}",
                details={"symbol": result.symbol, "engine": result.engine_name},
            ) from e
    
    @staticmethod
    def save_aggregated_result(result: AggregatedSignalResult) -> int:
        """
        Save aggregated signal result with consensus data
        
        Args:
            result: AggregatedSignalResult to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Save individual engine results
            for _, engine_result in result.engine_results.items():
                SignalRepository.save_signal_result(engine_result)

            aggregated_row = {
                "stock_symbol": result.symbol,
                "signal_date": result.generated_at.date(),
                "engine_name": "aggregated",
                "signal": result.consensus_signal.value,
                "confidence": result.consensus_confidence,
                "consensus_signal": result.consensus_signal.value,
                "consensus_confidence": result.consensus_confidence,
                "recommended_engine": result.recommended_engine,
                "conflicts": result.conflicts,
                "reasoning": result.reasoning,
                "metadata": result.to_dict(),
                "generated_at": result.generated_at,
                "expires_at": result.generated_at,
            }

            return BaseRepository.upsert_many(
                table="stock_signals_snapshots",
                unique_columns=["stock_symbol", "signal_date", "engine_name"],
                rows=[aggregated_row],
            )
        except Exception as e:
            raise DatabaseError(
                f"Failed to save aggregated signal result: {e}",
                details={"symbol": result.symbol},
            ) from e
    
    @staticmethod
    def fetch_signals_by_symbol(
        symbol: str, 
        engine_name: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch signal results for a symbol
        
        Args:
            symbol: Stock symbol
            engine_name: Specific engine name (optional)
            limit: Maximum number of results to return
            
        Returns:
            List of signal dictionaries
        """
        try:
            # Join with stocks table to get symbol
            query = """
                SELECT 
                    ss.stock_id,
                    s.symbol,
                    ss.engine_name,
                    ss.engine_version,
                    ss.signal,
                    ss.confidence,
                    ss.reasoning,
                    ss.metadata,
                    ss.created_at
                FROM stock_signals ss
                JOIN stocks s ON ss.stock_id = s.id
                WHERE s.symbol = :symbol
            """
            params = {"symbol": symbol}
            
            if engine_name:
                query += " AND ss.engine_name = :engine_name"
                params["engine_name"] = engine_name
            
            query += " ORDER BY ss.created_at DESC LIMIT :limit"
            params["limit"] = limit

            results = db.execute_query(query, params)

            return results
        except Exception as e:
            raise DatabaseError(f"Failed to fetch signals for {symbol}: {e}") from e
    
    @staticmethod
    def fetch_latest_signal(symbol: str, engine_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch the latest signal for a symbol
        
        Args:
            symbol: Stock symbol
            engine_name: Specific engine name (optional)
            
        Returns:
            Latest signal dictionary or None
        """
        signals = SignalRepository.fetch_signals_by_symbol(symbol, engine_name, limit=1)
        return signals[0] if signals else None
    
    @staticmethod
    def fetch_signals_by_criteria(
        signal: Optional[str] = None,
        confidence_min: Optional[float] = None,
        timeframe: Optional[str] = None,
        engine_name: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Fetch signals matching specific criteria (for screeners)
        
        Args:
            signal: Signal type (BUY/SELL/HOLD)
            confidence_min: Minimum confidence threshold
            timeframe: Timeframe filter (not available in stock_signals schema)
            engine_name: Engine name filter
            limit: Maximum results
            
        Returns:
            List of matching signals
        """
        try:
            query = """
                SELECT 
                    ss.stock_id,
                    s.symbol,
                    ss.engine_name,
                    ss.engine_version,
                    ss.signal,
                    ss.confidence,
                    ss.reasoning,
                    ss.metadata,
                    ss.created_at
                FROM stock_signals ss
                JOIN stocks s ON ss.stock_id = s.id
                WHERE 1=1
            """
            params: Dict[str, Any] = {}

            if signal:
                query += " AND ss.signal = :signal"
                params["signal"] = signal

            if confidence_min is not None:
                query += " AND ss.confidence >= :confidence_min"
                params["confidence_min"] = confidence_min

            if engine_name:
                query += " AND ss.engine_name = :engine_name"
                params["engine_name"] = engine_name

            # Note: timeframe is not available in stock_signals schema
            if timeframe:
                logger.warning(f"Timeframe filter not supported by stock_signals schema, ignoring: {timeframe}")

            query += " ORDER BY ss.confidence DESC, ss.created_at DESC LIMIT :limit"
            params["limit"] = limit

            return db.execute_query(query, params)
        except Exception as e:
            raise DatabaseError(
                f"Failed to fetch signals by criteria: {e}",
                details={
                    "signal": signal,
                    "confidence_min": confidence_min,
                    "timeframe": timeframe,
                    "engine_name": engine_name,
                    "limit": limit,
                },
            ) from e
    
    @staticmethod
    def save_screener_cache(screener_name: str, signals: List[Dict[str, Any]]) -> int:
        """
        Save screener results to cache table
        
        Args:
            screener_name: Name of the screener
            signals: List of signal dictionaries
            
        Returns:
            True if successful
        """
        try:
            db.execute_update(
                "DELETE FROM signal_screener_cache WHERE screener_name = :screener_name",
                {"screener_name": screener_name},
            )

            if not signals:
                return 0

            insert_query = """
                INSERT INTO signal_screener_cache (
                    screener_name, stock_symbol, signal, confidence, engine,
                    timeframe, rank_score, sector, market_cap, snapshot_date
                ) VALUES (
                    :screener_name, :stock_symbol, :signal, :confidence, :engine,
                    :timeframe, :rank_score, :sector, :market_cap, :snapshot_date
                )
            """

            rows: List[Dict[str, Any]] = []
            for row in signals:
                rows.append(
                    {
                        "screener_name": screener_name,
                        "stock_symbol": row.get("symbol") or row.get("stock_symbol"),
                        "signal": row.get("signal"),
                        "confidence": row.get("confidence"),
                        "engine": row.get("engine_name") or row.get("engine"),
                        "timeframe": row.get("timeframe"),
                        "rank_score": row.get("rank_score", 0.0),
                        "sector": row.get("sector"),
                        "market_cap": row.get("market_cap"),
                        "snapshot_date": date.today(),
                    }
                )

            return db.execute_many(insert_query, rows)
        except Exception as e:
            raise DatabaseError(
                f"Failed to save screener cache: {e}",
                details={"screener_name": screener_name, "rows": len(signals)},
            ) from e
    
    @staticmethod
    def fetch_screener_results(screener_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch cached screener results
        
        Args:
            screener_name: Name of the screener
            limit: Maximum results to return
            
        Returns:
            List of cached signals
        """
        try:
            return db.execute_query(
                """
                SELECT * FROM signal_screener_cache
                WHERE screener_name = :screener_name
                ORDER BY rank_score DESC
                LIMIT :limit
                """,
                {"screener_name": screener_name, "limit": limit},
            )
        except Exception as e:
            raise DatabaseError(
                f"Failed to fetch screener results: {e}",
                details={"screener_name": screener_name, "limit": limit},
            ) from e
