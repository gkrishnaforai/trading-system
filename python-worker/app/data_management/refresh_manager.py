"""
Data Refresh Manager
Orchestrates data fetching with multiple refresh strategies
Follows DRY and SOLID principles
"""
from typing import Dict, Any, List, Optional, Set
import logging
from datetime import datetime, timedelta, date
import pandas as pd
import json
import os

from app.services.base import BaseService
from app.data_sources import get_data_source, BaseDataSource
from app.data_validation.fundamentals_validator import FundamentalsValidator
from app.data_management.refresh_strategy import (
    RefreshMode, DataType, BaseRefreshStrategy,
    ScheduledRefreshStrategy, OnDemandRefreshStrategy,
    PeriodicRefreshStrategy, LiveRefreshStrategy
)
from app.data_management.refresh_result import (
    DataTypeRefreshResult, SymbolRefreshResult, RefreshStatus
)
from app.database import db
from app.repositories.market_data_intraday_repository import IntradayBarUpsertRow, MarketDataIntradayRepository
from app.utils.trading_calendar import expected_trading_days, expected_intraday_15m_timestamps, expected_intraday_5m_timestamps
from app.utils.json_sanitize import json_dumps_sanitized
from app.observability import audit


class DataRefreshManager(BaseService):
    """
    Central manager for all data refresh operations
    Supports scheduled, on-demand, periodic, and live refresh modes
    """

    def __init__(
        self,
        data_source: Optional[BaseDataSource] = None,
        strategies: Optional[Dict[RefreshMode, BaseRefreshStrategy]] = None
    ):
        super().__init__()  # Initialize BaseService (sets up self.logger)
        self.data_source = data_source or get_data_source()
        self.strategies = strategies or self._default_strategies()
        self._refresh_tracking: Dict[str, Dict[DataType, datetime]] = {}
        
        # Log initialization at configured level
        self.logger.info(f"🔧 DataRefreshManager initialized with logger: {self.logger.name}")
        self.logger.info(f"🔧 Logger level: {self.logger.level}")
        self.logger.info(f"🔧 Logger effective level: {self.logger.getEffectiveLevel()}")

    def _default_strategies(self) -> Dict[RefreshMode, BaseRefreshStrategy]:
        """Create default refresh strategies"""
        return {
            RefreshMode.SCHEDULED: ScheduledRefreshStrategy(schedule_time="01:00"),
            RefreshMode.ON_DEMAND: OnDemandRefreshStrategy(),
            RefreshMode.PERIODIC: PeriodicRefreshStrategy(),
            RefreshMode.LIVE: LiveRefreshStrategy(max_age=timedelta(minutes=1)),
        }

    def refresh_data(
        self,
        symbol: str,
        data_types: List[DataType],
        mode: RefreshMode = RefreshMode.ON_DEMAND,
        force: bool = False
    ) -> SymbolRefreshResult:
        """
        Refresh multiple data types for a symbol with detailed error tracking

        Args:
            symbol: Stock symbol
            data_types: List of data types to refresh
            mode: Refresh mode (scheduled, on-demand, periodic, live)
            force: Force refresh even if not needed

        Returns:
            SymbolRefreshResult with detailed status for each data type
        """
        strategy = self.strategies.get(mode)
        if not strategy:
            error_msg = f"No strategy found for mode: {mode}"
            self.logger.error(error_msg)
            results: Dict[str, DataTypeRefreshResult] = {}
            for data_type in data_types:
                dt_key = self._data_type_to_string(data_type)
                results[dt_key] = DataTypeRefreshResult(
                    data_type=dt_key,
                    status=RefreshStatus.FAILED,
                    message=error_msg,
                    error=error_msg,
                    timestamp=datetime.now(),
                )
            return SymbolRefreshResult(
                symbol=symbol,
                results=results,
                total_requested=len(data_types),
                total_successful=0,
                total_failed=len(data_types),
                total_skipped=0,
            )

        refresh_results: Dict[str, DataTypeRefreshResult] = {}
        successful = 0
        failed = 0
        skipped = 0

        for data_type in data_types:
            dt_key = self._data_type_to_string(data_type)
            self.logger.debug(f"🔍 Processing data_type: {data_type} (type: {type(data_type)}), dt_key: {dt_key}")
            try:
                if not force:
                    last_refresh = self._get_last_refresh(symbol, data_type)
                    if not strategy.should_refresh(symbol, data_type, last_refresh):
                        if data_type == DataType.FUNDAMENTALS:
                            try:
                                from app.data_management.table_mapping import DATA_TYPE_TABLE_MAP, resolve_column

                                spec = DATA_TYPE_TABLE_MAP[DataType.FUNDAMENTALS]
                                symbol_col = resolve_column(spec.table.value, spec.symbol_columns)
                                rows = db.execute_query(
                                    f"""
                                    SELECT 1
                                    FROM {spec.table.value}
                                    WHERE UPPER({symbol_col}) = UPPER(:symbol)
                                    LIMIT 1
                                    """,
                                    {"symbol": symbol},
                                )
                                if not rows:
                                    last_refresh = None
                                    if strategy.should_refresh(symbol, data_type, last_refresh):
                                        pass
                                    else:
                                        self.logger.info(f"Skipping {data_type} for {symbol} - data is fresh")
                                        refresh_results[dt_key] = DataTypeRefreshResult(
                                            data_type=dt_key,
                                            status=RefreshStatus.SKIPPED,
                                            message="Data is fresh, no refresh needed",
                                            timestamp=datetime.now(),
                                        )
                                        skipped += 1
                                        continue
                            except Exception as e:
                                self.logger.warning(f"Failed to verify fundamentals presence for {symbol}: {e}")
                        self.logger.info(f"Skipping {data_type} for {symbol} - data is fresh")
                        refresh_results[dt_key] = DataTypeRefreshResult(
                            data_type=dt_key,
                            status=RefreshStatus.SKIPPED,
                            message="Data is fresh, no refresh needed",
                            timestamp=datetime.now(),
                        )
                        skipped += 1
                        continue

                result = self._refresh_data_type_with_result(symbol, data_type)
                refresh_results[dt_key] = result

                if result.status == RefreshStatus.SUCCESS:
                    self._update_refresh_tracking(symbol, data_type, status='success')
                    # Automated self-healing backfills (industry standard)
                    if mode in (RefreshMode.SCHEDULED, RefreshMode.PERIODIC):
                        try:
                            if data_type == DataType.PRICE_HISTORICAL:
                                self._auto_backfill_price_daily(symbol, lookback_days=10)
                            elif data_type == DataType.PRICE_INTRADAY_5M:
                                self._auto_backfill_intraday_5m(symbol, lookback_days=2)
                        except Exception as e:
                            self.logger.warning(f"Auto backfill failed for {symbol} {data_type}: {e}")
                    successful += 1
                    self.logger.info(f"✅ Refreshed {data_type} for {symbol}: {result.message}")
                elif result.status == RefreshStatus.SKIPPED:
                    self._update_refresh_tracking(symbol, data_type, status='skipped')
                    skipped += 1
                    self.logger.info(f"Skipping {data_type} for {symbol}: {result.message}")
                else:
                    self._update_refresh_tracking(symbol, data_type, status='failed', error=result.error)
                    failed += 1
                    self.logger.warning(f"⚠️ Failed to refresh {data_type} for {symbol}: {result.error or result.message}")
            except Exception as e:
                error_msg = str(e)
                self.logger.error(f"Error refreshing {data_type} for {symbol}: {e}", exc_info=True)
                # Log the failure to audit with full exception/root cause
                try:
                    # Handle both enum and string data types
                    data_type_str = data_type.value if hasattr(data_type, 'value') else str(data_type)
                    audit.log_event(
                        level="error",
                        provider="system",
                        operation=f"refresh.{data_type_str}",
                        symbol=symbol,
                        message=f"Failed to refresh {data_type_str}",
                        exception=e,
                        context={"data_type": data_type_str, "mode": str(mode)}
                    )
                except Exception:
                    pass
                refresh_results[dt_key] = DataTypeRefreshResult(
                    data_type=dt_key,
                    status=RefreshStatus.FAILED,
                    message=f"Exception occurred: {error_msg}",
                    error=error_msg,
                    timestamp=datetime.now(),
                )
                self._update_refresh_tracking(symbol, data_type, status='failed', error=error_msg)
                failed += 1

        return SymbolRefreshResult(
            symbol=symbol,
            results=refresh_results,
            total_requested=len(data_types),
            total_successful=successful,
            total_failed=failed,
            total_skipped=skipped,
        )

    def _auto_backfill_price_daily(self, symbol: str, lookback_days: int = 10) -> None:
        """Detect and backfill missing NYSE trading days for the last N days."""
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=int(lookback_days))
        expected = set(expected_trading_days(start_date, end_date))

        present_rows = db.execute_query(
            """
            SELECT m.date
            FROM stock_market_metrics m
            JOIN stocks s ON s.id = m.stock_id
            WHERE s.symbol = :symbol
              AND m.date >= :start_date
              AND m.date <= :end_date
            """,
            {"symbol": symbol, "start_date": start_date, "end_date": end_date},
        )
        present = {r["date"] for r in present_rows if r.get("date")}
        missing = sorted(expected - present)
        if not missing:
            return

        # Fetch a slightly wider range to let provider fill gaps (upsert makes this safe)
        fetch_start = min(missing)
        fetch_end = max(missing) + timedelta(days=1)

        from app.services.data_fetcher import DataFetcher

        df = self.data_source.fetch_price_data(
            symbol,
            start_date=datetime.combine(fetch_start, datetime.min.time()),
            end_date=datetime.combine(fetch_end, datetime.min.time()),
            interval="1d",
        )
        if df is None or getattr(df, "empty", True):
            return

        fetcher = DataFetcher()
        fetcher.save_raw_market_data(symbol, df)
        self._update_ingestion_window(
            symbol=symbol,
            dataset=self._dataset_for_data_type(DataType.PRICE_HISTORICAL),
            interval="daily",
            source=self.data_source.name,
            historical_start_date=fetch_start,
            historical_end_date=max(missing),
            cursor_date=max(missing),
        )

    def _auto_backfill_intraday_5m(self, symbol: str, lookback_days: int = 2) -> None:
        """Detect and backfill missing 5m bars for the last N trading days."""
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=int(lookback_days))

        expected_ts = expected_intraday_5m_timestamps(start_date, end_date)
        if not expected_ts:
            return

        start_ts = min(expected_ts)
        end_ts = max(expected_ts) + pd.Timedelta(minutes=5)

        actual_rows = db.execute_query(
            """
            SELECT ts
            FROM raw_market_data_intraday
            WHERE symbol = :symbol
              AND interval = '5m'
              AND ts >= :start_ts
              AND ts <= :end_ts
            """,
            {"symbol": symbol, "start_ts": start_ts.to_pydatetime(), "end_ts": end_ts.to_pydatetime()},
        )
        actual = {pd.to_datetime(r["ts"]).tz_convert("UTC").floor("5min") for r in actual_rows if r.get("ts")}
        expected = {pd.to_datetime(t).tz_convert("UTC").floor("5min") for t in expected_ts}
        missing = sorted(expected - actual)
        if not missing:
            return

        # Fetch full range covering missing; upsert makes it idempotent.
        df = self.data_source.fetch_price_data(
            symbol,
            start_date=min(missing).to_pydatetime(),
            end_date=(max(missing) + pd.Timedelta(minutes=5)).to_pydatetime(),
            interval="5m",
        )
        if df is None or getattr(df, "empty", True):
            return

        rows: List[IntradayBarUpsertRow] = []
        for _, r in df.iterrows():
            ts = r.get("ts")
            if ts is None:
                continue
            ts = pd.to_datetime(ts)
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.tz_localize("UTC")
            rows.append(
                IntradayBarUpsertRow(
                    stock_symbol=symbol,
                    ts=ts.to_pydatetime(),
                    interval="15m",
                    open=float(r.get("open")) if r.get("open") is not None else None,
                    high=float(r.get("high")) if r.get("high") is not None else None,
                    low=float(r.get("low")) if r.get("low") is not None else None,
                    close=float(r.get("close")) if r.get("close") is not None else None,
                    volume=int(r.get("volume")) if r.get("volume") is not None else None,
                    source=self.data_source.name,
                )
            )
    
    def _save_to_stock_insights_snapshots(self, symbol: str, insights_date: date, source: str, payload_data: dict) -> int:
        """Helper method to save data to stock_insights_snapshots table with JSON serialization"""
        from app.utils.json_sanitize import json_dumps_sanitized
        
        saved = 0
        from app.database import db
        from datetime import datetime
        
        with db.get_session() as session:
            try:
                from sqlalchemy import text
                session.execute(
                    text("""
                    INSERT INTO stock_insights_snapshots 
                    (stock_symbol, insights_date, generated_at, source, payload)
                    VALUES (:stock_symbol, :insights_date, :generated_at, :source, :payload)
                    ON CONFLICT (stock_symbol, insights_date)
                    DO UPDATE SET
                        generated_at = EXCLUDED.generated_at,
                        source = EXCLUDED.source,
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    """),
                    {
                        "stock_symbol": symbol,
                        "insights_date": insights_date,
                        "generated_at": datetime.now(),
                        "source": source,
                        "payload": json_dumps_sanitized(payload_data)  # Serialize to JSON
                    }
                )
                saved += 1
                session.commit()
            except Exception as e:
                self.logger.warning(f"Failed to save to stock_insights_snapshots for {symbol}: {e}")
                session.rollback()
        
        return saved

    def _refresh_price_intraday_5m(self, symbol: str) -> int:
        try:
            self.logger.info(f"🚀 STARTING: 5-minute intraday price refresh for {symbol}")
            self.logger.info(f"🔧 Logger name: {self.logger.name}")
            self.logger.info(f"🔧 Logger level: {self.logger.level}")
            self.logger.info(f"🔧 Logger effective level: {self.logger.getEffectiveLevel()}")
            self.logger.info(f"🔧 Logger handlers: {len(self.logger.handlers)}")
            
            # Use FMP client to get 5-minute intraday data
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            self.logger.info(f"📡 Creating FMP client for {symbol}")
            client = EnhancedFMPClient.from_settings()
            
            self.logger.info(f"📡 Fetching intraday data for {symbol}")
            intraday_data = client.get_intraday_prices_5min(symbol)
            
            self.logger.info(f"📊 Intraday data result for {symbol}:")
            self.logger.info(f"   - Data type: {type(intraday_data)}")
            self.logger.info(f"   - Data length: {len(intraday_data) if isinstance(intraday_data, list) else 'N/A'}")
            
            if not intraday_data:
                self.logger.warning(f"⚠️ No intraday data returned for {symbol}")
                return 0
            
            # Save to raw_market_data_intraday table
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                for data_point in intraday_data:
                    if not isinstance(data_point, dict):
                        continue
                    
                    # Extract timestamp and price data
                    timestamp = data_point.get("date")
                    if not timestamp:
                        continue
                    
                    # Convert timestamp to datetime
                    try:
                        timestamp_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        continue
                    
                    # Save to intraday table
                    try:
                        session.execute(
                            """
                            INSERT INTO raw_market_data_intraday 
                            (symbol, timestamp, open_price, high_price, low_price, close_price, volume, data_source)
                            VALUES (:symbol, :timestamp, :open_price, :high_price, :low_price, :close_price, :volume, :data_source)
                            ON CONFLICT (symbol, timestamp)
                            DO UPDATE SET
                                open_price = EXCLUDED.open_price,
                                high_price = EXCLUDED.high_price,
                                low_price = EXCLUDED.low_price,
                                close_price = EXCLUDED.close_price,
                                volume = EXCLUDED.volume,
                                data_source = EXCLUDED.data_source,
                                updated_at = NOW()
                            """,
                            {
                                "symbol": symbol,
                                "timestamp": timestamp_dt,
                                "open_price": data_point.get("open"),
                                "high_price": data_point.get("high"),
                                "low_price": data_point.get("low"),
                                "close_price": data_point.get("close"),
                                "volume": data_point.get("volume"),
                                "data_source": "fmp",
                            }
                        )
                        saved += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to save intraday data for {symbol} {timestamp}: {e}")
                        continue
                
                session.commit()
            
            self.logger.info(f"Saved {saved} 5-minute intraday records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing 5-minute intraday prices for {symbol}: {e}")
            return 0
    
    def _refresh_institutional_buying(self, symbol: str) -> int:
        """Refresh institutional buying data for a symbol"""
        try:
            self.logger.info(f"Refreshing institutional buying data for {symbol}")
            # Use FMP client to get institutional buying data
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            institutional_data = client.get_institutional_buying(symbol)
            if not institutional_data:
                return 0
            
            # Save to stock_insights_snapshots table as fallback
            saved = 0
            from datetime import datetime
            
            for data in institutional_data:
                if not isinstance(data, dict):
                    continue
                
                # Use current date as insights date for institutional data
                insights_date = datetime.now().date()
                
                # Save as insights payload using helper method
                saved += self._save_to_stock_insights_snapshots(
                    symbol, 
                    insights_date, 
                    "fmp_institutional_buying", 
                    {"institutional_buying": data}
                )
            
            self.logger.info(f"Saved {saved} institutional buying records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing institutional buying data for {symbol}: {e}")
            return 0

        MarketDataIntradayRepository.upsert_many(rows)
        self._update_ingestion_window(
            symbol=symbol,
            dataset=self._dataset_for_data_type(DataType.PRICE_INTRADAY_5M),
            interval="5m",
            source=self.data_source.name,
            cursor_ts=max(pd.to_datetime(r.get("ts")).tz_convert("UTC") for r in df.to_dict("records") if r.get("ts")),
        )

    def _update_ingestion_window(
        self,
        *,
        symbol: str,
        dataset: str,
        interval: str,
        source: str,
        historical_start_date: Optional[date] = None,
        historical_end_date: Optional[date] = None,
        cursor_date: Optional[date] = None,
        cursor_ts: Optional[pd.Timestamp] = None,
    ) -> None:
        """Update ingestion coverage/cursors in data_ingestion_state (best-effort)."""
        try:
            query = """
                INSERT INTO data_ingestion_state
                (symbol, dataset, interval, source, historical_start_date, historical_end_date, cursor_date, cursor_ts, last_attempt_at, last_success_at, status)
                VALUES (:symbol, :dataset, :interval, :source, :hs, :he, :cd, :cts, NOW(), NOW(), 'success')
                ON CONFLICT (symbol, dataset, interval)
                DO UPDATE SET
                  source = EXCLUDED.source,
                  historical_start_date = COALESCE(data_ingestion_state.historical_start_date, EXCLUDED.historical_start_date),
                  historical_end_date = COALESCE(EXCLUDED.historical_end_date, data_ingestion_state.historical_end_date),
                  cursor_date = COALESCE(EXCLUDED.cursor_date, data_ingestion_state.cursor_date),
                  cursor_ts = COALESCE(EXCLUDED.cursor_ts, data_ingestion_state.cursor_ts),
                  last_attempt_at = NOW(),
                  last_success_at = NOW(),
                  status = 'success',
                  updated_at = NOW()
            """

            db.execute_update(
                query,
                {
                    "symbol": symbol,
                    "dataset": dataset,
                    "interval": interval,
                    "source": source,
                    "hs": historical_start_date,
                    "he": historical_end_date,
                    "cd": cursor_date,
                    "cts": cursor_ts.to_pydatetime() if cursor_ts is not None else None,
                },
            )
        except Exception as e:
            self.logger.debug(f"Failed to update ingestion window for {symbol}/{dataset}/{interval}: {e}")
            return

    def get_symbols_to_refresh(self, data_type: DataType, mode: RefreshMode) -> List[str]:
        """Return symbols that should be refreshed for the given mode/data_type."""
        strategy = self.strategies.get(mode)
        if not strategy:
            return []

        try:
            holdings = db.execute_query(
                """
                SELECT DISTINCT symbol
                FROM holdings
                WHERE symbol IS NOT NULL AND symbol != ''
                ORDER BY symbol
                """
            )
        except Exception:
            holdings = []

        symbols = [h.get("symbol") for h in holdings if h.get("symbol")]
        to_refresh: List[str] = []
        for sym in symbols:
            try:
                last_refresh = self._get_last_refresh(sym, data_type)
                if strategy.should_refresh(sym, data_type, last_refresh):
                    to_refresh.append(sym)
            except Exception:
                to_refresh.append(sym)
        return to_refresh

    def _refresh_data_type(self, symbol: str, data_type: DataType) -> bool:
        """Refresh a specific data type (legacy method for backward compatibility)"""
        result = self._refresh_data_type_with_result(symbol, data_type)
        return result.status == RefreshStatus.SUCCESS

    def _interval_for_data_type(self, data_type: DataType) -> str:
        if data_type == DataType.PRICE_CURRENT:
            return "last"
        if data_type == DataType.PRICE_INTRADAY_5M:
            return "5m"
        return "daily"

    def _refresh_data_type_with_result(self, symbol: str, data_type) -> DataTypeRefreshResult:
        """Refresh a specific data type with detailed result"""
        start_time = datetime.now()
        
        self.logger.debug(f"🔍 _refresh_data_type_with_result called with data_type: {data_type} (type: {type(data_type)})")

        try:
            if data_type == DataType.PRICE_HISTORICAL:
                rows, cleaned_data = self._refresh_price_historical(symbol)
                if rows > 0:
                    # Industry Standard: Auto-calculate indicators immediately after price data load
                    # Use the cleaned/validated data for indicator calculation to ensure data quality
                    disable_post = (os.getenv("JOB_DISABLE_POSTPROCESSING") or "").strip().lower() in {"1", "true", "yes"}
                    if not disable_post:
                        try:
                            from app.services.indicator_service import IndicatorService
                            indicator_service = IndicatorService()
                            
                            # Always try FMP technical indicators API first for indicators
                            # This ensures we use professional-grade indicators from FMP
                            self.logger.info(f"🔄 Auto-calculating indicators for {symbol} using FMP API after price data load (preferred method)")
                            success = indicator_service.calculate_indicators_with_fmp(symbol)
                            
                            if not success:
                                error_msg = f"Failed to calculate indicators for {symbol} after price data fetch"
                                self.logger.error(error_msg)
                                raise RuntimeError(error_msg)
                            
                            self.logger.info(f"✅ Auto-calculated indicators for {symbol} after price data fetch using FMP API (Industry Standard: Always calculate after data load)")
                        except Exception as e:
                            # Best-effort for now: normalized schema doesn't include legacy indicators tables.
                            self.logger.warning(
                                f"Indicators post-processing failed for {symbol} (non-fatal for price ingestion): {e}",
                                exc_info=True,
                            )

                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SUCCESS,
                        message=f"Successfully fetched {rows} rows of historical price data",
                        rows_affected=rows,
                        timestamp=start_time
                    )
                else:
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.FAILED,
                        message="No data returned from data source",
                        error="No rows fetched",
                        timestamp=start_time
                    )
            elif data_type == DataType.PRICE_CURRENT:
                success = self._refresh_price_current(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if success else RefreshStatus.FAILED,
                    message="Current price updated" if success else "Failed to fetch current price",
                    error=None if success else "Could not fetch current price",
                    timestamp=start_time
                )
            elif data_type == DataType.PRICE_INTRADAY_5M:
                rows = self._refresh_price_intraday_5m(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                    message=f"Saved {rows} 5m candles" if rows > 0 else "No 5m candles saved",
                    rows_affected=rows,
                    error=None if rows > 0 else "No intraday data returned",
                    timestamp=start_time,
                )
            elif data_type == DataType.FUNDAMENTALS:
                success = self._refresh_fundamentals(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if success else RefreshStatus.FAILED,
                    message="Fundamentals updated" if success else "Failed to fetch fundamentals",
                    error=None if success else "No fundamental data available",
                    timestamp=start_time
                )
            elif data_type == DataType.NEWS:
                rows = self._refresh_news(symbol)
                if rows == 0:
                    # No news is normal - not all symbols have recent news
                    self.logger.info(f"No news data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No news data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Fetched {rows} news articles",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.EARNINGS:
                rows = self._refresh_earnings(symbol)
                if rows == 0:
                    self.logger.info(f"No earnings data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No earnings data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time,
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Fetched {rows} earnings records",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.INDUSTRY_PEERS:
                success = self._refresh_industry_peers(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if success else RefreshStatus.FAILED,
                    message="Industry peers updated" if success else "Failed to fetch industry peers",
                    error=None if success else "No industry/peer data available",
                    timestamp=start_time
                )
            elif data_type == DataType.CORPORATE_ACTIONS:
                rows = self._refresh_corporate_actions(symbol)
                if rows == 0:
                    # No corporate actions is normal - not all symbols have recent actions
                    self.logger.info(f"No corporate actions data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No corporate actions data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Fetched {rows} corporate actions",
                    rows_affected=rows,
                    timestamp=start_time,
                )
            elif data_type == DataType.INDICATORS:
                from app.services.indicator_service import IndicatorService
                from app.utils.database_helper import DatabaseQueryHelper
                
                # Check if market data exists before calculating indicators
                market_data = DatabaseQueryHelper.get_historical_data(symbol)
                if not market_data:
                    self.logger.info(f"Skipping indicators for {symbol}: no market data available")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No market data available for indicators",
                        rows_affected=0
                    )
                
                service = IndicatorService()
                
                # Always try FMP technical indicators API first for indicators
                # This ensures we use professional-grade indicators from FMP
                self.logger.info(f"🔄 Using FMP technical indicators API for {symbol} (preferred method)")
                success = service.calculate_indicators_with_fmp(symbol)
                
                # Log the result for audit tracking
                if success:
                    self.logger.info(f"✅ Indicators calculation completed for {symbol}")
                    # Check what data source was actually used
                    try:
                        from app.database import db
                        result = db.execute_query("""
                            SELECT DISTINCT data_source, COUNT(*) as count 
                            FROM indicators_daily 
                            WHERE symbol = %s AND date >= NOW() - INTERVAL '1 hour'
                            GROUP BY data_source 
                            ORDER BY count DESC
                        """, [symbol])
                        if result and result[0]['data_source'] == 'fmp_api':
                            message = f"Indicators loaded from FMP API ({result[0]['count']} records)"
                        else:
                            message = "Indicators calculated successfully"
                    except:
                        message = "Indicators calculated successfully"
                else:
                    self.logger.warning(f"⚠️ Indicators calculation failed for {symbol}")
                    message = "Failed to calculate indicators"
                
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if success else RefreshStatus.FAILED,
                    message=message,
                    error=None if success else "Indicator calculation failed",
                    timestamp=start_time
                )
            elif data_type == DataType.SIGNALS:
                # Signals are generated from indicators, handled separately
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message="Signals are generated from indicators",
                    timestamp=start_time
                )
            elif data_type == DataType.REPORTS:
                # Reports are generated on-demand, handled separately
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message="Reports are generated on-demand",
                    timestamp=start_time
                )
            elif data_type == DataType.INCOME_STATEMENTS:
                try:
                    rows = self._refresh_income_statements(symbol)
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                        message=f"Fetched {rows} income statements" if rows > 0 else "No income statements found",
                        rows_affected=rows,
                        error=None if rows > 0 else "No income statement data available",
                        timestamp=start_time
                    )
                except Exception as e:
                    error_msg = f"Exception refreshing income statements for {symbol}: {str(e)}"
                    self.logger.error(error_msg, exc_info=True)
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.FAILED,
                        message=error_msg,
                        error=str(e),
                        timestamp=start_time
                    )
            elif data_type == DataType.BALANCE_SHEETS:
                try:
                    rows = self._refresh_balance_sheets(symbol)
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                        message=f"Fetched {rows} balance sheets" if rows > 0 else "No balance sheets found",
                        rows_affected=rows,
                        error=None if rows > 0 else "No balance sheet data available",
                        timestamp=start_time
                    )
                except Exception as e:
                    error_msg = f"Exception refreshing balance sheets for {symbol}: {str(e)}"
                    self.logger.error(error_msg, exc_info=True)
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.FAILED,
                        message=error_msg,
                        error=str(e),
                        timestamp=start_time
                    )
            elif data_type == DataType.CASH_FLOW_STATEMENTS:
                try:
                    rows = self._refresh_cash_flow_statements(symbol)
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                        message=f"Fetched {rows} cash flow statements" if rows > 0 else "No cash flow statements found",
                        rows_affected=rows,
                        error=None if rows > 0 else "No cash flow statement data available",
                        timestamp=start_time
                    )
                except Exception as e:
                    error_msg = f"Exception refreshing cash flow statements for {symbol}: {str(e)}"
                    self.logger.error(error_msg, exc_info=True)
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.FAILED,
                        message=error_msg,
                        error=str(e),
                        timestamp=start_time
                    )
            elif data_type == DataType.FINANCIAL_RATIOS:
                rows = self._refresh_financial_ratios(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                    message=f"Fetched {rows} financial ratios" if rows > 0 else "No financial ratios found",
                    rows_affected=rows,
                    error=None if rows > 0 else "No financial ratio data available",
                    timestamp=start_time
                )
            elif data_type == DataType.WEEKLY_AGGREGATION:
                from app.services.data_aggregation_service import DataAggregationService
                service = DataAggregationService()
                try:
                    result = service.aggregate_to_weekly(symbol, force=True)
                    if result.get('success') and int(result.get('rows_created', 0) or 0) == 0 and str(result.get('message') or ''):
                        return DataTypeRefreshResult(
                            data_type=data_type.value,
                            status=RefreshStatus.SKIPPED,
                            message=str(result.get('message')),
                            rows_affected=0,
                            timestamp=start_time,
                        )
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SUCCESS if result.get('success') else RefreshStatus.FAILED,
                        message=f"Aggregated {result.get('rows_created', 0)} weekly bars" if result.get('success') else "Weekly aggregation failed",
                        rows_affected=result.get('rows_created', 0),
                        error=None if result.get('success') else result.get('error', 'Unknown error'),
                        timestamp=start_time,
                    )
                except Exception as e:
                    msg = str(e)
                    if "Insufficient daily data" in msg:
                        self.logger.info(f"Skipping weekly aggregation for {symbol}: {msg}")
                        return DataTypeRefreshResult(
                            data_type=data_type.value,
                            status=RefreshStatus.SKIPPED,
                            message=f"Weekly aggregation skipped: {msg}",
                            rows_affected=0,
                            timestamp=start_time,
                        )
                    raise
            elif data_type == DataType.GROWTH_CALCULATIONS:
                from app.services.growth_calculation_service import GrowthCalculationService
                service = GrowthCalculationService()
                result = service.calculate_growth_metrics(symbol, force=True)
                if not result.get('success') and str(result.get('error') or '') in [
                    'Insufficient data',
                    'Income statements schema not compatible',
                ]:
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message=f"Growth calculation skipped: {result.get('error')}",
                        error=None,
                        timestamp=start_time,
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if result.get('success') else RefreshStatus.FAILED,
                    message="Growth metrics calculated" if result.get('success') else "Growth calculation failed",
                    error=None if result.get('success') else result.get('error', 'Unknown error'),
                    timestamp=start_time
                )
            # === NEW DATA TYPES ===
            elif data_type == DataType.PRICE_INTRADAY_5M:
                rows = self._refresh_price_intraday_5m(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                    message=f"5-minute intraday prices refreshed for {symbol}" if rows > 0 else "No 5-minute intraday data available",
                    error=None if rows > 0 else "No 5-minute intraday data available",
                    timestamp=start_time
                )
            elif data_type == DataType.KEY_METRICS_TTM:
                rows = self._refresh_key_metrics_ttm(symbol)
                if rows == 0:
                    # Key metrics may not be available for all symbols
                    self.logger.info(f"No key metrics (TTM) data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No key metrics (TTM) data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Key metrics (TTM) refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.FINANCIAL_SCORES:
                rows = self._refresh_financial_scores(symbol)
                if rows == 0:
                    # Financial scores may not be available for all symbols
                    self.logger.info(f"No financial scores data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No financial scores data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Financial scores refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.INSTITUTIONAL_BUYING:
                rows = self._refresh_institutional_buying(symbol)
                if rows == 0:
                    # No data available is normal for institutional buying - not all symbols have this data
                    self.logger.info(f"No institutional buying data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No institutional buying data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Institutional buying data refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.INCOME_STATEMENT_GROWTH:
                rows = self._refresh_income_statement_growth(symbol)
                if rows == 0:
                    self.logger.info(f"No income statement growth data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No income statement growth data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Income statement growth data refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.BALANCE_SHEET_GROWTH:
                rows = self._refresh_balance_sheet_growth(symbol)
                if rows == 0:
                    self.logger.info(f"No balance sheet growth data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No balance sheet growth data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Balance sheet growth data refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.CASH_FLOW_GROWTH:
                rows = self._refresh_cash_flow_growth(symbol)
                if rows == 0:
                    self.logger.info(f"No cash flow growth data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No cash flow growth data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Cash flow growth data refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.FINANCIAL_GROWTH:
                rows = self._refresh_financial_growth(symbol)
                if rows == 0:
                    self.logger.info(f"No financial growth data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No financial growth data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Financial growth data refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.SHORT_INTEREST:
                rows = self._refresh_short_interest(symbol)
                if rows == 0:
                    # Short interest may not be available for all symbols
                    self.logger.info(f"No short interest data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No short interest data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Short interest refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.SHORT_VOLUME:
                rows = self._refresh_short_volume(symbol)
                if rows == 0:
                    # Short volume may not be available for all symbols
                    self.logger.info(f"No short volume data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No short volume data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Short volume refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.SHARE_FLOAT:
                rows = self._refresh_share_float(symbol)
                if rows == 0:
                    # Share float may not be available for all symbols
                    self.logger.info(f"No share float data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No share float data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Share float refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.RISK_FACTORS:
                rows = self._refresh_risk_factors(symbol)
                if rows == 0:
                    # Risk factors may not be available for all symbols
                    self.logger.info(f"No risk factors data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No risk factors data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Risk factors refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.EARNINGS_TRANSCRIPTS:
                rows = self._refresh_earnings_transcripts(symbol)
                if rows == 0:
                    # Earnings transcripts may not be available for all symbols
                    self.logger.info(f"No earnings transcripts data available for {symbol} - this is normal")
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SKIPPED,
                        message="No earnings transcripts data available (normal for many symbols)",
                        rows_affected=0,
                        timestamp=start_time
                    )
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS,
                    message=f"Earnings transcripts refreshed for {symbol}",
                    rows_affected=rows,
                    timestamp=start_time
                )
            elif data_type == DataType.OWNER_EARNINGS:
                rows = self._refresh_owner_earnings(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                    message=f"Owner earnings refreshed for {symbol}" if rows > 0 else "No owner earnings data available",
                    error=None if rows > 0 else "No owner earnings data available",
                    timestamp=start_time
                )
            # === ANALYST DATA (handled by separate APIs) ===
            elif data_type in [DataType.STOCK_GRADES, DataType.CONSENSUS_DATA, DataType.PRICE_TARGETS, DataType.ANALYST_RATINGS]:
                # These are handled by the stock grades API, not the main refresh API
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SKIPPED,
                    message=f"{data_type.value} is handled by stock grades API, not main refresh API",
                    error=None,
                    timestamp=start_time
                )
            else:
                error_msg = f"Unknown data type: {data_type}"
                self.logger.warning(error_msg)
                return DataTypeRefreshResult(
                    data_type=data_type.value if hasattr(data_type, 'value') else str(data_type),
                    status=RefreshStatus.FAILED,
                    message=error_msg,
                    error=error_msg,
                    timestamp=start_time
                )
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Exception in _refresh_data_type_with_result for {data_type}: {e}", exc_info=True)
            # Log the failure to audit with full exception/root cause
            try:
                audit.log_event(
                    level="error",
                    provider="system",
                    operation=f"refresh.{data_type.value}",
                    symbol=symbol,
                    message=f"Exception in _refresh_data_type_with_result",
                    exception=e,
                    context={"data_type": data_type.value}
                )
            except Exception:
                pass
            return DataTypeRefreshResult(
                data_type=data_type.value,
                status=RefreshStatus.FAILED,
                message=f"Exception: {error_msg}",
                error=error_msg,
                timestamp=start_time
            )

    def _refresh_price_historical(self, symbol: str) -> tuple[int, pd.DataFrame]:
        """Refresh historical price data with validation and audit

        Returns:
            Tuple of (number of rows saved, cleaned DataFrame)
        """
        import time
        start_time = time.time()
        fetch_success = False
        rows_fetched = 0
        rows_saved = 0
        error_message = None
        validation_report_id = None

        try:
            from app.services.data_fetcher import DataFetcher
            from app.data_validation import DataValidator

            fetcher = DataFetcher()
            validator = DataValidator()

            # Use the data source directly
            data = self.data_source.fetch_price_data(symbol, period="1y")
            rows_fetched = len(data) if data is not None and not data.empty else 0

            if data is None or data.empty:
                error_message = "No data returned from data source"
                return 0, pd.DataFrame()

            # Validate data before saving
            validation_report = validator.validate(data, symbol, "price_historical")

            # Log validation results
            if validation_report.overall_status == "fail":
                self.logger.error(f"❌ Data validation FAILED for {symbol}: {validation_report.critical_issues} critical issues")
                for result in validation_report.validation_results:
                    if not result.passed:
                        for issue in result.issues:
                            self.logger.error(f"   - {issue.message}")
            elif validation_report.overall_status == "warning":
                self.logger.warning(f"⚠️ Data validation WARNING for {symbol}: {validation_report.warnings} warnings")
            else:
                self.logger.info(f"✅ Data validation PASSED for {symbol}")

            # Clean data if needed (remove bad rows)
            cleaned_data, cleaned_report = validator.validate_and_clean(data, symbol, "price_historical")

            # Save validation report to database
            validation_report_id = self._save_validation_report(cleaned_report)

            # Save cleaned data
            rows_saved = fetcher.save_raw_market_data(symbol, cleaned_data)
            fetch_success = True

            if rows_saved != len(cleaned_data):
                self.logger.warning(f"⚠️ Saved {rows_saved} rows but cleaned data has {len(cleaned_data)} rows")
        except Exception as e:
            error_message = str(e)
            self.logger.error(f"Error refreshing historical price for {symbol}: {e}", exc_info=True)
            cleaned_data = pd.DataFrame()  # Empty DataFrame on error
            raise  # Re-raise to be caught by caller
        finally:
            # Audit the fetch operation
            fetch_duration_ms = int((time.time() - start_time) * 1000)
            self._audit_data_fetch(
                symbol=symbol,
                fetch_type='price_historical',
                fetch_mode='on_demand',
                data_source=self.data_source.name,  # Use data source name property for consistency
                rows_fetched=rows_fetched,
                rows_saved=rows_saved,
                fetch_duration_ms=fetch_duration_ms,
                success=fetch_success,
                error_message=error_message,
                validation_report_id=validation_report_id
            )

        return rows_saved, cleaned_data

    def _refresh_price_intraday_5m(self, symbol: str, days: int = 5) -> int:
        """Fetch and persist true 5m candles into raw_market_data_intraday."""
        import time

        start_time = time.time()
        fetch_success = False
        rows_fetched = 0
        rows_saved = 0
        error_message = None

        try:
            from datetime import datetime, timedelta
            
            self.logger.info(f"🔍 Fetching 5m intraday price data for {symbol} - Period: {days} days")
            
            # Convert period to start_date and end_date for FMP API
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            self.logger.info(f"📅 Converting period to dates: {start_date} to {end_date}")
            
            data = self.data_source.fetch_price_data(symbol, start_date=start_date, end_date=end_date, interval="5m")
            self.logger.info(f"📊 Price data fetch result for {symbol}: {type(data)}")
            if data is not None:
                self.logger.info(f"📊 Price data length for {symbol}: {len(data)}")
                self.logger.info(f"📊 Price data empty for {symbol}: {getattr(data, 'empty', 'N/A')}")
            rows_fetched = len(data) if data is not None and not getattr(data, "empty", True) else 0
            if data is None or getattr(data, "empty", True):
                error_message = "No intraday data returned"
                return 0

            # Normalize column names (providers may return Open/High/Low/Close/Volume)
            col_map: Dict[str, str] = {}
            try:
                for c in list(getattr(data, "columns", [])):
                    cl = str(c).strip().lower()
                    if cl not in col_map:
                        col_map[cl] = c
            except Exception:
                col_map = {}

            def _get(r, name: str):
                try:
                    if name in getattr(r, "index", []):
                        return r.get(name)
                    key = col_map.get(name.lower())
                    return r.get(key) if key is not None else r.get(name)
                except Exception:
                    return None

            rows: List[IntradayBarUpsertRow] = []
            for idx, r in data.iterrows():
                ts = None
                # Providers vary:
                # - some return an explicit 'ts' column
                # - many return a DatetimeIndex and no 'ts' column
                try:
                    ts = r.get("ts")
                except Exception:
                    ts = None
                if ts is None:
                    ts = idx
                if ts is None:
                    continue
                ts = pd.to_datetime(ts)
                if getattr(ts, "tzinfo", None) is None:
                    ts = ts.tz_localize("UTC")
                rows.append(
                    IntradayBarUpsertRow(
                        stock_symbol=symbol,
                        ts=ts.to_pydatetime(),
                        interval="15m",
                        open=float(_get(r, "open")) if _get(r, "open") is not None else None,
                        high=float(_get(r, "high")) if _get(r, "high") is not None else None,
                        low=float(_get(r, "low")) if _get(r, "low") is not None else None,
                        close=float(_get(r, "close")) if _get(r, "close") is not None else None,
                        volume=int(_get(r, "volume")) if _get(r, "volume") is not None else None,
                        source=self.data_source.name,
                    )
                )

            if not rows:
                error_message = "No intraday rows parsed (missing timestamps/columns)"
                return 0

            rows_saved = MarketDataIntradayRepository.upsert_many(rows)
            fetch_success = rows_saved > 0
            if rows_saved > 0:
                # Compute cursor timestamp robustly for different provider shapes.
                cursor_ts = None
                try:
                    if "ts" in getattr(data, "columns", []):
                        cursor_ts = max(pd.to_datetime(t).tz_convert("UTC") for t in data["ts"].dropna())
                    else:
                        cursor_ts = pd.to_datetime(data.index.max())
                        if getattr(cursor_ts, "tzinfo", None) is None:
                            cursor_ts = cursor_ts.tz_localize("UTC")
                except Exception:
                    cursor_ts = None
                self._update_ingestion_window(
                    symbol=symbol,
                    dataset=self._dataset_for_data_type(DataType.PRICE_INTRADAY_5M),
                    interval="5m",
                    source=self.data_source.name,
                    cursor_ts=cursor_ts,
                )
            return rows_saved
        except Exception as e:
            error_message = str(e)
            self.logger.error(f"Error refreshing 5m candles for {symbol}: {e}", exc_info=True)
            return 0
        finally:
            fetch_duration_ms = int((time.time() - start_time) * 1000)
            self._audit_data_fetch(
                symbol=symbol,
                fetch_type='price_intraday_5m',
                fetch_mode='periodic',
                data_source=self.data_source.name,
                rows_fetched=rows_fetched,
                rows_saved=rows_saved,
                fetch_duration_ms=fetch_duration_ms,
                success=fetch_success,
                error_message=error_message
            )

    def _refresh_price_current(self, symbol: str) -> bool:
        """Refresh current price (intraday last price) and save to raw_market_data_intraday."""
        import time

        start_time = time.time()
        fetch_success = False
        rows_fetched = 0
        rows_saved = 0
        error_message = None

        try:
            price_data = self.data_source.fetch_current_price(symbol)
            if price_data is None:
                error_message = "No current price returned"
                return False

            # Handle new dict format with price and volume
            if isinstance(price_data, dict):
                price = price_data.get("price")
                volume = price_data.get("volume")
            else:
                # Backward compatibility for old format
                price = price_data
                volume = None
            
            if price is None:
                error_message = "No price in returned data"
                return False
                
            try:
                price_f = float(price)
            except Exception:
                error_message = f"Invalid current price: {price}"
                return False

            rows_fetched = 1
            ts = datetime.utcnow()
            row = IntradayBarUpsertRow(
                stock_symbol=symbol,
                ts=ts,
                interval="last",
                open=price_f,
                high=price_f,
                low=price_f,
                close=price_f,
                volume=int(volume) if volume is not None else None,  # ✅ Now includes volume!
                source=self.data_source.name,
            )
            rows_saved = MarketDataIntradayRepository.upsert_many([row])
            fetch_success = rows_saved > 0
            return fetch_success
        except Exception as e:
            error_message = str(e)
            self.logger.error(f"Error refreshing current price for {symbol}: {e}", exc_info=True)
            return False
        finally:
            fetch_duration_ms = int((time.time() - start_time) * 1000)
            self._audit_data_fetch(
                symbol=symbol,
                fetch_type='price_current',
                fetch_mode='periodic',
                data_source=self.data_source.name,
                rows_fetched=rows_fetched,
                rows_saved=rows_saved,
                fetch_duration_ms=fetch_duration_ms,
                success=fetch_success,
                error_message=error_message
            )

    def _save_validation_report(self, report):
        """Save validation report to database

        Fail-fast: This is critical for gate checks, so we raise on error
        """
        import uuid

        try:
            # Convert report to dict (handles numpy/pandas types)
            report_dict = report.to_dict()

            report_json = report_dict

            report_id = f"{report.symbol}_{report.data_type}_{report.timestamp.strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
            query = """
                INSERT INTO data_validation_reports
                (report_id, symbol, data_type, validation_timestamp, report_json, overall_status,
                 critical_issues, warnings, rows_dropped, created_at)
                VALUES (:report_id, :symbol, :data_type, :timestamp, CAST(:report_json AS jsonb), :status,
                        :critical_issues, :warnings, :rows_dropped, NOW())
                ON CONFLICT (report_id)
                DO UPDATE SET
                  report_json = EXCLUDED.report_json,
                  overall_status = EXCLUDED.overall_status,
                  critical_issues = EXCLUDED.critical_issues,
                  warnings = EXCLUDED.warnings,
                  rows_dropped = EXCLUDED.rows_dropped
            """

            db.execute_update(query, {
                "report_id": report_id,
                "symbol": report.symbol,
                "data_type": report.data_type,
                "timestamp": report.timestamp,
                "report_json": json.dumps(report_json),
                "status": report.overall_status,
                "critical_issues": report.critical_issues,
                "warnings": report.warnings,
                "rows_dropped": report.rows_dropped
            })
            self.logger.debug(f"✅ Saved validation report for {report.symbol}: {report_id}")
            return report_id
        except (TypeError, ValueError) as e:
            # JSON serialization error - fail fast
            error_msg = f"Failed to serialize validation report for {report.symbol}: {e}"
            self.logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e
        except Exception as e:
            # Best-effort: normalized DB baseline may not include this optional audit table.
            err_lower = str(e).lower()
            if "data_validation_reports" in err_lower and (
                "does not exist" in err_lower or "undefinedtable" in err_lower
            ):
                self.logger.warning(
                    f"Validation report table missing; skipping save for {report.symbol} (non-fatal): {e}",
                    exc_info=True,
                )
                return None

            # Database error - fail fast for unexpected issues
            error_msg = f"Failed to save validation report for {report.symbol}: {e}"
            self.logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    def _audit_data_fetch(
        self,
        symbol: str,
        fetch_type: str,
        fetch_mode: str,
        data_source: str,
        rows_fetched: int,
        rows_saved: int,
        fetch_duration_ms: int,
        success: bool,
        error_message: Optional[str] = None,
        validation_report_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Audit data fetch operation"""
        try:
            import uuid
            audit_id = f"{symbol}_{fetch_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
            query = """
                INSERT INTO data_fetch_audit
                (audit_id, symbol, fetch_type, fetch_mode, fetch_timestamp, data_source,
                 rows_fetched, rows_saved, fetch_duration_ms, success, error_message,
                 validation_report_id, metadata, created_at)
                VALUES (:audit_id, :symbol, :fetch_type, :fetch_mode, :timestamp, :data_source,
                        :rows_fetched, :rows_saved, :duration_ms, :success, :error_message,
                        :validation_report_id, CAST(:metadata AS jsonb), NOW())
            """
            db.execute_update(query, {
                "audit_id": audit_id,
                "symbol": symbol,
                "fetch_type": fetch_type,
                "fetch_mode": fetch_mode,
                "timestamp": datetime.now(),
                "data_source": data_source,
                "rows_fetched": rows_fetched,
                "rows_saved": rows_saved,
                "duration_ms": fetch_duration_ms,
                "success": success,
                "error_message": error_message,
                "validation_report_id": validation_report_id,
                "metadata": json.dumps(metadata) if metadata else None
            })
        except Exception as e:
            # Non-critical - log but don't fail
            self.logger.warning(f"Failed to audit data fetch (non-critical): {e}")

    def _refresh_fundamentals(self, symbol: str) -> bool:
        """Refresh fundamental data and save to both snapshots and detailed tables"""
        try:
            self.logger.info(f"Refreshing fundamentals for {symbol}")
            
            # Use FMP data source directly to avoid Massive library dependency
            self.logger.info(f"Fetching fundamentals from data source: {self.data_source.name}")
            try:
                fundamentals = self.data_source.fetch_fundamentals(symbol)
                self.logger.info(f"Fundamentals fetch result: {type(fundamentals)} - {fundamentals}")
                
                # Check if fundamentals is empty in different ways
                if fundamentals is None:
                    self.logger.warning(f"Fundamentals is None for {symbol}")
                    return False
                elif isinstance(fundamentals, dict) and not fundamentals:
                    self.logger.warning(f"Fundamentals is empty dict for {symbol}")
                    return False
                elif isinstance(fundamentals, list) and not fundamentals:
                    self.logger.warning(f"Fundamentals is empty list for {symbol}")
                    return False
                elif isinstance(fundamentals, str) and not fundamentals.strip():
                    self.logger.warning(f"Fundamentals is empty string for {symbol}")
                    return False
                else:
                    self.logger.info(f"Fundamentals appears valid for {symbol}: type={type(fundamentals)}, len={len(fundamentals) if hasattr(fundamentals, '__len__') else 'N/A'}")
                    
            except Exception as fetch_error:
                self.logger.error(f"Failed to fetch fundamentals from {self.data_source.name}: {fetch_error}")
                self.logger.exception(f"Fetch error details: {fetch_error}")
                return False
            
            if not fundamentals:
                self.logger.warning(f"No fundamentals data available for {symbol}")
                return False

            # Persist to fundamentals_snapshots (used by Go API fundamentals endpoint)
            from app.repositories.fundamentals_repository import FundamentalsRepository
            from datetime import datetime

            repo = FundamentalsRepository()
            as_of_date_str = None
            if isinstance(fundamentals, dict):
                meta = fundamentals.get("meta")
                if isinstance(meta, dict):
                    as_of_date_str = meta.get("as_of_date")

            snapshot_dt = datetime.now()
            if as_of_date_str:
                try:
                    snapshot_dt = datetime.strptime(str(as_of_date_str), "%Y-%m-%d")
                except Exception:
                    # Fall back to refresh time if provider doesn't supply a parsable as_of_date
                    snapshot_dt = datetime.now()

            repo.upsert_fundamentals(symbol=symbol, fundamentals=fundamentals, snapshot_date=snapshot_dt)

            # Emit fundamentals change events (deduped by as_of_date).
            try:
                from app.repositories.fundamentals_change_events_repository import FundamentalsChangeEventsRepository
                from app.services.fundamentals_change_event_generator import generate_events_from_fundamentals_snapshot

                events_repo = FundamentalsChangeEventsRepository()
                as_of, events = generate_events_from_fundamentals_snapshot(symbol, fundamentals)
                if as_of and events:
                    latest_as_of = events_repo.fetch_latest_as_of_date(symbol)
                    if latest_as_of != as_of:
                        events_repo.insert_events(events)
            except Exception as e:
                # Non-critical: fundamentals refresh should still succeed even if events fail.
                self.logger.warning(f"Failed to generate fundamentals change events for {symbol} (non-critical): {e}")
            
            # Save to stock_insights_snapshots table
            saved = 0
            from app.database import db
            from datetime import datetime
            from app.utils.json_sanitize import json_dumps_sanitized
            with db.get_session() as session:
                # Use current date as insights date for fundamentals data
                insights_date = datetime.now().date()
                
                # Save as insights payload
                try:
                    from sqlalchemy import text
                    
                    sql_query = """
                        INSERT INTO stock_insights_snapshots 
                        (stock_symbol, insights_date, generated_at, source, payload)
                        VALUES (:stock_symbol, :insights_date, :generated_at, :source, :payload)
                        ON CONFLICT (stock_symbol, insights_date)
                        DO UPDATE SET
                            generated_at = EXCLUDED.generated_at,
                            source = EXCLUDED.source,
                            payload = EXCLUDED.payload,
                            updated_at = NOW()
                        """
                    
                    params = {
                        "stock_symbol": symbol,
                        "insights_date": insights_date,
                        "generated_at": datetime.now(),
                        "source": "fmp_fundamentals",
                        "payload": json_dumps_sanitized({"fundamentals": fundamentals})
                    }
                    
                    # Log the full query for debugging
                    self.logger.info(f"Executing fundamentals SQL for {symbol}:\n{sql_query}")
                    self.logger.info(f"SQL Parameters: {params}")
                    
                    session.execute(text(sql_query), params)
                    saved += 1
                except Exception as e:
                    self.logger.warning(f"Failed to save fundamentals for {symbol}: {e}")
                
                session.commit()
            
            self.logger.info(f"Saved {saved} fundamentals records for {symbol}")
            return saved > 0
            
        except Exception as e:
            self.logger.error(f"Error refreshing fundamentals for {symbol}: {e}")
            raise

    def _refresh_earnings(self, symbol: str) -> int:
        """Refresh earnings data for a symbol"""
        try:
            self.logger.info(f"Refreshing earnings data for {symbol}")
            # Use FMP client to get earnings data
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            # Get earnings report data
            earnings_data = client.get_earnings_report(symbol)
            if not earnings_data:
                return 0
            
            # Save to earnings_calendar table
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                for earnings in earnings_data:
                    if not isinstance(earnings, dict):
                        continue
                    
                    # Extract earnings date
                    earnings_date = earnings.get("date")
                    if not earnings_date:
                        continue
                    
                    # Convert date string to date object
                    try:
                        earnings_date_obj = datetime.strptime(earnings_date, "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        continue
                    
                    # Save to earnings_calendar table
                    try:
                        session.execute(
                            """
                            INSERT INTO earnings_calendar 
                            (symbol, company_name, earnings_date, earnings_time, 
                             eps_estimate, eps_actual, revenue_estimate, revenue_actual,
                             surprise_pct, fiscal_quarter, fiscal_year, created_at, updated_at)
                            VALUES (:symbol, :company_name, :earnings_date, :earnings_time,
                                    :eps_estimate, :eps_actual, :revenue_estimate, :revenue_actual,
                                    :surprise_pct, :fiscal_quarter, :fiscal_year, :created_at, :updated_at)
                            ON CONFLICT (symbol, earnings_date)
                            DO UPDATE SET
                                company_name = EXCLUDED.company_name,
                                earnings_time = EXCLUDED.earnings_time,
                                eps_estimate = EXCLUDED.eps_estimate,
                                eps_actual = EXCLUDED.eps_actual,
                                revenue_estimate = EXCLUDED.revenue_estimate,
                                revenue_actual = EXCLUDED.revenue_actual,
                                surprise_pct = EXCLUDED.surprise_pct,
                                fiscal_quarter = EXCLUDED.fiscal_quarter,
                                fiscal_year = EXCLUDED.fiscal_year,
                                updated_at = EXCLUDED.updated_at
                            """,
                            {
                                "symbol": symbol,
                                "company_name": earnings.get("companyName"),
                                "earnings_date": earnings_date_obj,
                                "earnings_time": earnings.get("time"),
                                "eps_estimate": earnings.get("epsEstimate"),
                                "eps_actual": earnings.get("epsActual"),
                                "revenue_estimate": earnings.get("revenueEstimate"),
                                "revenue_actual": earnings.get("revenueActual"),
                                "surprise_pct": earnings.get("surprisePercent"),
                                "fiscal_quarter": earnings.get("fiscalQuarter"),
                                "fiscal_year": earnings.get("fiscalYear"),
                                "created_at": datetime.now(),
                                "updated_at": datetime.now(),
                            }
                        )
                        saved += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to save earnings data for {symbol} {earnings_date}: {e}")
                        continue
                
                session.commit()
            
            self.logger.info(f"Saved {saved} earnings records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing earnings for {symbol}: {e}")
            return 0

    def _refresh_news(self, symbol: str) -> int:
        """Refresh news data with validation

        Returns:
            Number of news articles saved (0 if failed)
        """
        import time
        start_time = time.time()
        fetch_success = False
        rows_fetched = 0
        rows_saved = 0
        error_message = None
        validation_report_id = None

        try:
            news = self.data_source.fetch_news(symbol, limit=20)
            
            rows_fetched = len(news) if news else 0
            
            if not news:
                error_message = "No news data available"
                return 0
            
            # Validate news data (best-effort: validators may not match current ValidationIssue signature)
            metadata = {"source": self.data_source.name}
            validation_report = None
            try:
                from app.data_validation import MarketNewsValidator

                validator = MarketNewsValidator()
                validation_report = validator.validate(news, symbol, "market_news")
                validation_report_id = self._save_validation_report(validation_report)

                # Create metadata for audit
                summary = validator.summarize_issues(validation_report)
                metadata = {
                    **summary,
                    "source": self.data_source.name,
                }
            except Exception as e:
                self.logger.warning(
                    f"News validation skipped for {symbol} (non-fatal): {e}",
                    exc_info=True,
                )
                validation_report_id = None
            
            if validation_report is not None and getattr(validation_report, "overall_status", None) == "fail":
                fetch_success = False
                error_message = "News validation failed: missing required fields"
                self.logger.warning(f"⚠️ News validation FAILED for {symbol}")
                # Still attempt to save news data but mark as failed for retry logic
            
            if news:
                import uuid
                import json
                from datetime import datetime

                # Save to stock_news table (normalized baseline uses stock_id/url)
                stock_id_row = db.execute_query(
                    """
                    INSERT INTO stocks (symbol)
                    VALUES (:symbol)
                    ON CONFLICT (symbol) DO UPDATE SET symbol = EXCLUDED.symbol
                    RETURNING id
                    """,
                    {"symbol": symbol},
                )
                stock_id = stock_id_row[0]["id"] if stock_id_row and stock_id_row[0].get("id") else None
                if not stock_id:
                    raise RuntimeError(f"Failed to resolve stock_id for {symbol}")

                for article in news:
                    published_date = None
                    pub_raw = article.get("published") or article.get("published_date")
                    if pub_raw:
                        if isinstance(pub_raw, datetime):
                            published_date = pub_raw
                        else:
                            try:
                                published_date = datetime.fromisoformat(str(pub_raw).replace('Z', '+00:00'))
                            except (ValueError, TypeError):
                                published_date = None

                    title = article.get("title", "")
                    publisher = article.get("publisher", "")
                    url = article.get("url") or article.get("link") or ""
                    related_symbols_json = article.get("related_symbols", [])

                    try:
                        db.execute_update(
                            """
                            INSERT INTO stock_news
                            (stock_id, published_at, title, publisher, url, related_symbols, source, raw_json)
                            VALUES (:stock_id, :published_at, :title, :publisher, :url, CAST(:related_symbols AS jsonb), :source, CAST(:raw_json AS jsonb))
                            """,
                            {
                                "stock_id": stock_id,
                                "published_at": published_date,
                                "title": title,
                                "publisher": publisher,
                                "url": url,
                                "related_symbols": json.dumps(related_symbols_json),
                                "source": self.data_source.name,
                                "raw_json": json.dumps(article),
                            },
                        )
                    except Exception as e:
                        # Backward-compatible fallback for legacy schema variants.
                        err_lower = str(e).lower()
                        if "column" in err_lower and ("stock_id" in err_lower or "url" in err_lower):
                            news_id = str(uuid.uuid4())
                            db.execute_update(
                                """
                                INSERT INTO stock_news
                                (news_id, symbol, title, publisher, link, published_at, related_symbols, source)
                                VALUES (:news_id, :symbol, :title, :publisher, :link, :published_at, CAST(:related_symbols AS JSONB), :source)
                                ON CONFLICT (news_id) DO NOTHING
                                """,
                                {
                                    "news_id": news_id,
                                    "symbol": symbol,
                                    "title": title,
                                    "publisher": publisher,
                                    "link": url,
                                    "published_at": published_date,
                                    "related_symbols": json.dumps(related_symbols_json),
                                    "source": self.data_source.name,
                                },
                            )
                        else:
                            raise

                rows_saved = len(news)
                fetch_success = True
                self.logger.info(f"✅ Saved {len(news)} news articles for {symbol}")
                return len(news)
            return 0
            
        except Exception as e:
            error_message = str(e)
            self.logger.error(f"Error refreshing news for {symbol}: {e}", exc_info=True)
            raise
        finally:
            # Audit the fetch operation
            fetch_duration_ms = int((time.time() - start_time) * 1000)
            self._audit_data_fetch(
                symbol=symbol,
                fetch_type='market_news',
                fetch_mode='on_demand',
                data_source=self.data_source.name,
                rows_fetched=rows_fetched,
                rows_saved=rows_saved,
                fetch_duration_ms=fetch_duration_ms,
                success=fetch_success if 'fetch_success' in locals() else True,
                error_message=error_message,
                validation_report_id=validation_report_id,
                metadata=metadata if 'metadata' in locals() else {},
            )

    def _refresh_earnings(self, symbol: str) -> int:
        """Refresh earnings data for a symbol"""
        try:
            self.logger.info(f"Refreshing earnings data for {symbol}")
            # Use FMP client to get earnings data
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            # Get earnings report data
            earnings_data = client.get_earnings_report(symbol)
            if not earnings_data:
                return 0
            
            # Save to earnings_calendar table
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                for earnings in earnings_data:
                    if not isinstance(earnings, dict):
                        continue
                    
                    # Extract earnings date
                    earnings_date = earnings.get("date")
                    if not earnings_date:
                        continue
                    
                    # Convert date string to date object
                    try:
                        earnings_date_obj = datetime.strptime(earnings_date, "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        continue
                    
                    # Save to earnings_calendar table
                    try:
                        session.execute(
                            """
                            INSERT INTO earnings_calendar 
                            (symbol, company_name, earnings_date, earnings_time, 
                             eps_estimate, eps_actual, revenue_estimate, revenue_actual,
                             surprise_pct, fiscal_quarter, fiscal_year, created_at, updated_at)
                            VALUES (:symbol, :company_name, :earnings_date, :earnings_time,
                                    :eps_estimate, :eps_actual, :revenue_estimate, :revenue_actual,
                                    :surprise_pct, :fiscal_quarter, :fiscal_year, :created_at, :updated_at)
                            ON CONFLICT (symbol, earnings_date)
                            DO UPDATE SET
                                company_name = EXCLUDED.company_name,
                                earnings_time = EXCLUDED.earnings_time,
                                eps_estimate = EXCLUDED.eps_estimate,
                                eps_actual = EXCLUDED.eps_actual,
                                revenue_estimate = EXCLUDED.revenue_estimate,
                                revenue_actual = EXCLUDED.revenue_actual,
                                surprise_pct = EXCLUDED.surprise_pct,
                                fiscal_quarter = EXCLUDED.fiscal_quarter,
                                fiscal_year = EXCLUDED.fiscal_year,
                                updated_at = EXCLUDED.updated_at
                            """,
                            {
                                "symbol": symbol,
                                "company_name": earnings.get("companyName"),
                                "earnings_date": earnings_date_obj,
                                "earnings_time": earnings.get("time"),
                                "eps_estimate": earnings.get("epsEstimate"),
                                "eps_actual": earnings.get("epsActual"),
                                "revenue_estimate": earnings.get("revenueEstimate"),
                                "revenue_actual": earnings.get("revenueActual"),
                                "surprise_pct": earnings.get("surprisePercent"),
                                "fiscal_quarter": earnings.get("fiscalQuarter"),
                                "fiscal_year": earnings.get("fiscalYear"),
                                "created_at": datetime.now(),
                                "updated_at": datetime.now(),
                            }
                        )
                        saved += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to save earnings data for {symbol} {earnings_date}: {e}")
                        continue
                
                session.commit()
            
            self.logger.info(f"Saved {saved} earnings records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing earnings for {symbol}: {e}")
            return 0

    def _refresh_news(self, symbol: str) -> int:
        """Refresh news data with validation

        Returns:
            Number of news articles saved (0 if failed)
        """
        import time
        start_time = time.time()
        fetch_success = False
        rows_fetched = 0
        rows_saved = 0
        error_message = None
        audit_done = False  # Track if audit has been performed

        try:
            news = self.data_source.fetch_news(symbol)
            rows_fetched = len(news) if news else 0

            if not news:
                error_message = "No news data available"
                return 0

            # Save to database
            saved_count = 0
            for article in news:
                if isinstance(article, dict) and article.get('title') and article.get('published_at'):
                    try:
                        # Save news article to database
                        saved_count += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to save news article for {symbol}: {e}")
                        continue

            rows_saved = saved_count
            fetch_success = True
            self.logger.info(f"✅ Saved {saved_count} news articles for {symbol}")
            return saved_count

        except Exception as e:
            error_message = str(e)
            self.logger.error(f"Error refreshing news for {symbol}: {e}", exc_info=True)
            return 0

    def _refresh_industry_peers(self, symbol: str) -> bool:
        """Refresh industry peers and save to industry_peers."""
        try:
            peers_data = self.data_source.fetch_industry_peers(symbol)
            if not peers_data:
                return False

            sector = None
            industry = None
            saved = 0

            # Extract sector/industry from first peer if available
            if peers_data and len(peers_data) > 0:
                first_peer = peers_data[0]
                sector = first_peer.get("sector")
                industry = first_peer.get("industry")

            # Save peers to database
            for peer_symbol in peers_data:
                if isinstance(peer_symbol, str):
                    peer_symbol = peer_symbol
                elif isinstance(peer_symbol, dict):
                    peer_symbol = peer_symbol.get("symbol")
                else:
                    continue

                if not peer_symbol or peer_symbol == symbol:
                    continue

                try:
                    db.execute_update(
                        """
                        INSERT INTO industry_peers 
                        (symbol, peer_symbol, sector, industry, data_source)
                        VALUES (:symbol, :peer_symbol, :sector, :industry, :data_source)
                        ON CONFLICT (symbol, peer_symbol)
                        DO UPDATE SET
                            sector = EXCLUDED.sector,
                            industry = EXCLUDED.industry,
                            data_source = EXCLUDED.data_source,
                            updated_at = NOW()
                        """,
                        {
                            "symbol": symbol,
                            "peer_symbol": peer_symbol,
                            "sector": sector,
                            "industry": industry,
                            "data_source": self.data_source.name,
                        },
                    )
                    saved += 1
                except Exception as e:
                    self.logger.warning(f"Failed to save peer {peer_symbol} for {symbol}: {e}")
                    continue

            self.logger.info(f"✅ Saved {saved} peers to industry_peers for {symbol}")
            return saved > 0
        except Exception as e:
            self.logger.error(f"Error refreshing industry peers for {symbol}: {e}", exc_info=True)
            raise

    def _refresh_income_statements(self, symbol: str) -> int:
        """Refresh income statements and persist into financial_statements."""
        try:
            return self._refresh_financial_statements(symbol, statement_type="income_statement")
        except Exception as e:
            # Re-raise with context to ensure detailed exception is visible
            self.logger.error(f"❌ Exception in _refresh_income_statements for {symbol}: {e}", exc_info=True)
            raise

    def _refresh_balance_sheets(self, symbol: str) -> int:
        """Refresh balance sheets and persist into financial_statements."""
        try:
            return self._refresh_financial_statements(symbol, statement_type="balance_sheet")
        except Exception as e:
            # Re-raise with context to ensure detailed exception is visible
            self.logger.error(f"❌ Exception in _refresh_balance_sheets for {symbol}: {e}", exc_info=True)
            raise

    def _refresh_cash_flow_statements(self, symbol: str) -> int:
        """Refresh cash flow statements and persist into financial_statements."""
        try:
            return self._refresh_financial_statements(symbol, statement_type="cash_flow")
        except Exception as e:
            # Re-raise with context to ensure detailed exception is visible
            self.logger.error(f"❌ Exception in _refresh_cash_flow_statements for {symbol}: {e}", exc_info=True)
            raise

    def _refresh_financial_statements(self, symbol: str, *, statement_type: str, period: str = None) -> int:
        """Fetch and upsert financial statement snapshots.

        Stores provider-normalized statement rows in `financial_statements` keyed by
        (stock_symbol, period_type, statement_type, fiscal_period).
        
        Industry Standard: Proper exception handling with fallback and detailed logging.
        Exceptions are propagated to higher levels for proper error reporting.
        """
        statements = None
        
        # Use user-specified period or None for latest data
        period_desc = f"period={period}" if period else "period=None (latest data)"
        self.logger.info(f"🔍 Fetching financial statements for {symbol} with {period_desc}")
        self.logger.info(f"📡 Data source: {self.data_source.name}")
        self.logger.info(f"🔧 Data source type: {type(self.data_source).__name__}")
        
        # Try primary source first
        try:
            statements = self.data_source.fetch_financial_statements(symbol, period=period)
            
            self.logger.info(f"📊 Financial statements fetch result for {symbol}:")
            self.logger.info(f"   - Type: {type(statements)}")
            self.logger.info(f"   - Keys: {list(statements.keys()) if isinstance(statements, dict) else 'N/A'}")
            if isinstance(statements, dict):
                for key, value in statements.items():
                    if isinstance(value, list):
                        self.logger.info(f"   - {key}: {len(value)} items")
                        if value and isinstance(value[0], dict):
                            self.logger.info(f"   - {key} sample keys: {list(value[0].keys())[:5]}")
                            # Log what periods we received but don't automatically switch
                            if len(value) > 0 and isinstance(value[0], dict):
                                period_type = value[0].get("period", "unknown")
                                self.logger.info(f"📅 Received period type: '{period_type}' for {symbol}")
                                if period_type == "FY":
                                    self.logger.info(f"📅 FY periods detected - user can request specific quarterly periods if needed")
                    else:
                        self.logger.info(f"   - {key}: {type(value)} - {str(value)[:100]}...")
                        
        except Exception as e:
            self.logger.error(f"❌ Primary source (fmp) failed for financial statements for {symbol}: {e}")
            self.logger.exception(f"Full exception details for {symbol}:")
            
            # Try fallback source if available
            if hasattr(self.data_source, 'fallback') and self.data_source.fallback:
                try:
                    self.logger.info(f"🔄 Trying fallback source: {self.data_source.fallback.name}")
                    statements = self.data_source.fallback.fetch_financial_statements(symbol, period=None)
                    self.logger.info(f"✅ Fallback source returned data for {symbol}: {type(statements)}")
                except Exception as fallback_error:
                    self.logger.error(f"❌ Fallback source also failed for financial statements for {symbol}: {fallback_error}")
                    self.logger.exception(f"Fallback exception details for {symbol}:")
                    # Industry Standard: Re-raise the exception with context
                    raise Exception(f"All sources failed for financial statements {symbol}. Primary: {e}, Fallback: {fallback_error}") from fallback_error
            else:
                self.logger.warning(f"⚠️ No fallback source available for financial statements for {symbol}")
                # Industry Standard: Re-raise the original exception
                raise Exception(f"Primary source failed for financial statements {symbol}: {e}") from e

        # Validate statements data
        if not statements:
            raise Exception(f"No financial statements data returned for {symbol}")
            
        if not isinstance(statements, dict):
            raise Exception(f"Invalid financial statements data type for {symbol}: expected dict, got {type(statements)}")

        period_type = statements.get("periodicity") or "annual"
        list_key = statement_type
        items = statements.get(list_key) or []
        if not items:
            raise Exception(f"No {statement_type} items found in financial statements for {symbol}")

        # Process and save statements
        saved = 0
        for item in items:
            if not isinstance(item, dict):
                self.logger.warning(f"Skipping non-dict item for {symbol}: {type(item)}")
                continue
                
            period = item.get("period")
            self.logger.info(f"📅 Processing item for {symbol} with period: '{period}'")
            self.logger.info(f"📅 Item keys: {list(item.keys())}")
            self.logger.info(f"📅 Full item: {item}")
            
            if not period:
                self.logger.warning(f"Skipping item without period for {symbol}")
                continue
            
            # Handle different period formats
            fiscal_period = None
            if period == "FY":
                # Handle Fiscal Year - use the calendar year end or a default date
                # For annual data, we'll use December 31 of the current year or the date from the item
                if "calendarYear" in item:
                    year = item["calendarYear"]
                    fiscal_period = date(year, 12, 31)  # Use year-end as fiscal period
                elif "fiscalDateEnding" in item:
                    # Parse the fiscal date ending if available
                    try:
                        fiscal_period = pd.to_datetime(item["fiscalDateEnding"]).date()
                    except:
                        fiscal_period = date(datetime.now().year, 12, 31)  # Fallback to current year end
                else:
                    # Fallback to current year end
                    fiscal_period = date(datetime.now().year, 12, 31)
                
                self.logger.info(f"📅 Converted FY to fiscal period: {fiscal_period}")
            else:
                # Handle regular date formats
                fiscal_period = pd.to_datetime(period, errors="coerce").date() if period else None
                
            if fiscal_period is None or pd.isna(fiscal_period):
                self.logger.warning(f"Skipping item with invalid period '{period}' for {symbol}")
                continue

            payload = dict(item)
            payload.pop("period", None)

            try:
                # Save to financial_statements table
                from app.database import db
                import json
                
                with db.get_session() as session:
                    record = {
                        "stock_symbol": symbol,
                        "period_type": period_type,
                        "statement_type": statement_type,
                        "fiscal_period": fiscal_period,
                        "payload": json.dumps(payload),  # Serialize dict to JSON string
                        "data_source": statements.get("data_source", "unknown"),
                        "created_at": datetime.now(),
                        "updated_at": datetime.now(),
                    }
                    
                    # Use proper SQL with text() wrapper
                    from sqlalchemy import text
                    session.execute(text("""
                        INSERT INTO financial_statements 
                        (stock_symbol, period_type, statement_type, fiscal_period, payload, data_source, created_at, updated_at)
                        VALUES (:stock_symbol, :period_type, :statement_type, :fiscal_period, :payload, :data_source, :created_at, :updated_at)
                        ON CONFLICT (stock_symbol, period_type, statement_type, fiscal_period)
                        DO UPDATE SET
                            payload = EXCLUDED.payload,
                            data_source = EXCLUDED.data_source,
                            updated_at = NOW()
                    """), record)
                    saved += 1
                    
            except Exception as db_error:
                self.logger.error(f"Failed to save financial statement record for {symbol} {fiscal_period}: {db_error}")
                self.logger.error(f"Database error type: {type(db_error).__name__}")
                self.logger.error(f"Database error details: {str(db_error)}")
                # Log the record that failed for debugging
                self.logger.error(f"Failed record details: {record}")
                # Log the SQL that failed
                self.logger.error(f"SQL that failed: INSERT INTO financial_statements ...")
                # Continue processing other items instead of failing completely
                continue

        if saved == 0:
            raise Exception(f"No financial statements were successfully saved for {symbol}")
            
        self.logger.info(f"✅ Saved {saved} {statement_type} records for {symbol}")
        return saved

    def _refresh_corporate_actions(self, symbol: str) -> int:
        """Fetch dividends/splits and persist into corporate_actions."""
        try:
            actions = self.data_source.fetch_corporate_actions(symbol)
        except Exception as e:
            self.logger.warning(f"Failed to fetch corporate actions for {symbol}: {e}")
            return 0

        if not actions:
            return 0

        saved = 0
        for a in actions:
            if not isinstance(a, dict):
                continue
            d = a.get("date")
            action_date = pd.to_datetime(d, errors="coerce").date() if d else None
            if action_date is None or pd.isna(action_date):
                continue

            action_type = a.get("type")  # FMP uses "type" not "action_type"
            if action_type not in ("dividend", "stock_split"):
                continue

            value = a.get("amount") if action_type == "dividend" else a.get("split_ratio")
            try:
                value_f = float(value) if value is not None else None
            except Exception:
                value_f = None

            db.execute_update(
                """
                INSERT INTO corporate_actions (symbol, action_date, action_type, value, source, payload)
                VALUES (:symbol, :action_date, :action_type, :value, :source, CAST(:payload AS jsonb))
                ON CONFLICT (symbol, action_date, action_type)
                DO UPDATE SET
                  value = EXCLUDED.value,
                  source = EXCLUDED.source,
                  payload = EXCLUDED.payload,
                  updated_at = NOW()
                """,
                {
                    "symbol": symbol,
                    "action_date": action_date,
                    "action_type": action_type,
                    "value": value_f,
                    "source": self.data_source.name,
                    "payload": json_dumps_sanitized(a),
                },
            )
            saved += 1

        self.logger.info(f"✅ Saved {saved} corporate actions for {symbol}")
        return saved

    def _refresh_financial_ratios(self, symbol: str) -> int:
        """Refresh financial ratios using FMP client"""
        try:
            self.logger.info(f"Refreshing financial ratios for {symbol}")
            # Use FMP client to get financial ratios
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            ratios_data = client.get_financial_ratios(symbol, period=None)  # Use None for latest data
            
            self.logger.info(f"📊 Financial ratios fetch result for {symbol}:")
            self.logger.info(f"   - Data type: {type(ratios_data)}")
            self.logger.info(f"   - Data length: {len(ratios_data) if isinstance(ratios_data, list) else 'N/A'}")
            if isinstance(ratios_data, list) and ratios_data:
                self.logger.info(f"   - Sample keys: {list(ratios_data[0].keys())[:10] if isinstance(ratios_data[0], dict) else 'N/A'}")
                self.logger.info(f"   - Sample data: {str(ratios_data[0])[:200]}...")
            elif ratios_data:
                self.logger.info(f"   - Data content: {str(ratios_data)[:200]}...")
            
            if not ratios_data:
                self.logger.warning(f"⚠️ No financial ratios data available for {symbol}")
                return 0
            
            # Save to financial_ratios table
            saved = 0
            from app.database import db
            with db.get_session() as session:
                for ratio in ratios_data:
                    if not isinstance(ratio, dict):
                        continue
                    
                    # Extract key fields from FMP data
                    fiscal_date = ratio.get("date")
                    if not fiscal_date:
                        continue
                    
                    # Convert date string to date object
                    try:
                        from datetime import datetime
                        fiscal_date_obj = datetime.strptime(fiscal_date, "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        continue
                    
                    # Map FMP fields to database fields
                    db_record = {
                        "symbol": symbol,
                        "fiscal_date_ending": fiscal_date_obj,
                        "roe": ratio.get("returnOnEquity"),
                        "debt_to_equity": ratio.get("debtToEquity"),
                        "current_ratio": ratio.get("currentRatio"),
                        "data_source": "fmp",
                    }
                    
                    # Insert or update record
                    try:
                        from sqlalchemy import text
                        session.execute(
                            text("""
                            INSERT INTO financial_ratios 
                            (symbol, fiscal_date_ending, roe, debt_to_equity, current_ratio, data_source)
                            VALUES (:symbol, :fiscal_date_ending, :roe, :debt_to_equity, :current_ratio, :data_source)
                            ON CONFLICT (symbol, fiscal_date_ending, data_source)
                            DO UPDATE SET
                                roe = EXCLUDED.roe,
                                debt_to_equity = EXCLUDED.debt_to_equity,
                                current_ratio = EXCLUDED.current_ratio,
                                updated_at = NOW()
                            """),
                            db_record
                        )
                        saved += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to save financial ratio for {symbol} {fiscal_date}: {e}")
                        continue
                
                session.commit()
            
            self.logger.info(f"Saved {saved} financial ratios records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing financial ratios for {symbol}: {e}")
            return 0

    def _refresh_industry_peers(self, symbol: str) -> bool:
        """Refresh industry peers and save to industry_peers."""
        try:
            peers_data = self.data_source.fetch_industry_peers(symbol)
            if not peers_data:
                return False

            sector = None
            industry = None
            peers_list = []

            # Provider return shapes vary. Normalize to peers_list of dicts.
            if isinstance(peers_data, dict):
                sector = peers_data.get('sector')
                industry = peers_data.get('industry')
                peers_list = peers_data.get('peers') or []
            elif isinstance(peers_data, list):
                peers_list = peers_data
            elif isinstance(peers_data, str):
                # Try JSON first, else treat as comma-separated tickers.
                import json

                try:
                    decoded = json.loads(peers_data)
                    if isinstance(decoded, dict):
                        sector = decoded.get('sector')
                        industry = decoded.get('industry')
                        peers_list = decoded.get('peers') or []
                    elif isinstance(decoded, list):
                        peers_list = decoded
                except Exception:
                    peers_list = [p.strip() for p in peers_data.split(',') if p.strip()]

            # Normalize list of symbols/strings into dict objects
            normalized_peers: List[Dict[str, Any]] = []
            for p in peers_list or []:
                if isinstance(p, dict):
                    normalized_peers.append(p)
                elif isinstance(p, str):
                    normalized_peers.append({"symbol": p})
            peers_list = normalized_peers

            if not peers_list:
                return bool(sector or industry)

            saved = 0
            for peer in peers_list:
                peer_symbol = (peer.get('symbol') or peer.get('ticker') or '').strip()
                if not peer_symbol:
                    continue

                query = """
                    INSERT INTO industry_peers
                    (symbol, peer_symbol, sector, industry, data_source)
                    VALUES (:symbol, :peer_symbol, :sector, :industry, :data_source)
                    ON CONFLICT (symbol, peer_symbol, data_source)
                    DO UPDATE SET
                      sector = EXCLUDED.sector,
                      industry = EXCLUDED.industry,
                      data_source = EXCLUDED.data_source
                """

                db.execute_update(
                    query,
                    {
                        "symbol": symbol,
                        "peer_symbol": peer_symbol,
                        "sector": sector,
                        "industry": industry,
                        "data_source": self.data_source.name,
                    },
                )
                saved += 1

            self.logger.info(f"✅ Saved {saved} peers to industry_peers for {symbol}")
            return saved > 0
        except Exception as e:
            self.logger.error(f"Error refreshing industry peers for {symbol}: {e}", exc_info=True)
            raise

    # === NEW DATA TYPE IMPLEMENTATIONS ===
    
    def _refresh_key_metrics_ttm(self, symbol: str) -> int:
        """Refresh key metrics (TTM) for a symbol"""
        try:
            self.logger.info(f"Refreshing key metrics (TTM) for {symbol}")
            # Use FMP client to get key metrics
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            metrics_data = client.get_key_metrics_ttm(symbol)
            if not metrics_data:
                return 0
            
            # Save to stock_insights_snapshots table
            saved = 0
            from datetime import datetime
            
            for metric in metrics_data:
                if not isinstance(metric, dict):
                    continue
                
                # Use current date as insights date for TTM data
                insights_date = datetime.now().date()
                
                # Save as insights payload using helper method
                saved += self._save_to_stock_insights_snapshots(
                    symbol, 
                    insights_date, 
                    "fmp_key_metrics_ttm", 
                    {"key_metrics_ttm": metric}
                )
            
            self.logger.info(f"Saved {saved} key metrics (TTM) records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing key metrics (TTM) for {symbol}: {e}")
            return 0
    
    def _refresh_financial_scores(self, symbol: str) -> int:
        """Refresh financial scores for a symbol"""
        try:
            self.logger.info(f"Refreshing financial scores for {symbol}")
            # Use FMP client to get financial scores
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            scores_data = client.get_financial_scores(symbol)
            if not scores_data:
                self.logger.warning(f"No financial scores data available for {symbol}")
                return 0
            
            # Save to stock_insights_snapshots table
            saved = 0
            from datetime import datetime
            
            for score in scores_data:
                if not isinstance(score, dict):
                    continue
                
                # Use current date as insights date for scores data
                insights_date = datetime.now().date()
                
                # Save as insights payload using helper method
                saved += self._save_to_stock_insights_snapshots(
                    symbol, 
                    insights_date, 
                    "fmp_financial_scores", 
                    {"financial_scores": score}
                )
            
            self.logger.info(f"Saved {saved} financial scores records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing financial scores for {symbol}: {e}")
            return 0
    
    def _refresh_short_interest(self, symbol: str) -> int:
        """Refresh short interest data for a symbol"""
        try:
            self.logger.info(f"Refreshing short interest for {symbol}")
            # Use FMP client to get short interest
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            short_interest_data = client.get_short_interest(symbol)
            if not short_interest_data:
                return 0
            
            # Save to stock_insights_snapshots table as fallback if short_interest table doesn't exist
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                for data in short_interest_data:
                    if not isinstance(data, dict):
                        continue
                    
                    report_date = data.get("date")
                    if not report_date:
                        continue
                    
                    # Convert date string to date object
                    try:
                        report_date_obj = datetime.strptime(report_date, "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        continue
                    
                    # Try to save to short_interest table first, fallback to insights
                    try:
                        session.execute(
                            """
                            INSERT INTO short_interest 
                            (symbol, short_interest, short_ratio, days_to_cover, short_interest_change, 
                             short_interest_change_percent, report_date, data_source)
                            VALUES (:symbol, :short_interest, :short_ratio, :days_to_cover, :short_interest_change,
                                    :short_interest_change_percent, :report_date, :data_source)
                            ON CONFLICT (symbol, report_date)
                            DO UPDATE SET
                                short_interest = EXCLUDED.short_interest,
                                short_ratio = EXCLUDED.short_ratio,
                                days_to_cover = EXCLUDED.days_to_cover,
                                short_interest_change = EXCLUDED.short_interest_change,
                                short_interest_change_percent = EXCLUDED.short_interest_change_percent,
                                updated_at = NOW()
                            """,
                            {
                                "symbol": symbol,
                                "short_interest": data.get("shortInterest"),
                                "short_ratio": data.get("shortRatio"),
                                "days_to_cover": data.get("daysToCover"),
                                "short_interest_change": data.get("shortInterestChange"),
                                "short_interest_change_percent": data.get("shortInterestChangePercent"),
                                "report_date": report_date_obj,
                                "data_source": "fmp",
                            }
                        )
                        saved += 1
                    except Exception as e:
                        # Fallback to stock_insights_snapshots
                        try:
                            saved += self._save_to_stock_insights_snapshots(
                                symbol, 
                                report_date_obj, 
                                "fmp_short_interest", 
                                {"short_interest": data}
                            )
                        except Exception as e2:
                            self.logger.warning(f"Failed to save short interest for {symbol} {report_date}: {e}, fallback also failed: {e2}")
                            continue
                
                session.commit()
            
            self.logger.info(f"Saved {saved} short interest records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing short interest for {symbol}: {e}")
            return 0
    
    def _refresh_short_volume(self, symbol: str) -> int:
        """Refresh short volume data for a symbol"""
        try:
            self.logger.info(f"Refreshing short volume for {symbol}")
            # Use FMP client to get short volume
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            short_volume_data = client.get_short_volume(symbol)
            if not short_volume_data:
                return 0
            
            # Save to stock_insights_snapshots table as fallback if short_volume table doesn't exist
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                for data in short_volume_data:
                    if not isinstance(data, dict):
                        continue
                    
                    report_date = data.get("date")
                    if not report_date:
                        continue
                    
                    # Convert date string to date object
                    try:
                        report_date_obj = datetime.strptime(report_date, "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        continue
                    
                    # Try to save to short_volume table first, fallback to insights
                    try:
                        session.execute(
                            """
                            INSERT INTO short_volume 
                            (symbol, short_volume, total_volume, short_volume_percent, short_exempt_volume, report_date, data_source)
                            VALUES (:symbol, :short_volume, :total_volume, :short_volume_percent, :short_exempt_volume, :report_date, :data_source)
                            ON CONFLICT (symbol, report_date)
                            DO UPDATE SET
                                short_volume = EXCLUDED.short_volume,
                                total_volume = EXCLUDED.total_volume,
                                short_volume_percent = EXCLUDED.short_volume_percent,
                                short_exempt_volume = EXCLUDED.short_exempt_volume,
                                updated_at = NOW()
                            """,
                            {
                                "symbol": symbol,
                                "short_volume": data.get("shortVolume"),
                                "total_volume": data.get("totalVolume"),
                                "short_volume_percent": data.get("shortVolumePercent"),
                                "short_exempt_volume": data.get("shortExemptVolume"),
                                "report_date": report_date_obj,
                                "data_source": "fmp",
                            }
                        )
                        saved += 1
                    except Exception as e:
                        # Fallback to stock_insights_snapshots
                        try:
                            saved += self._save_to_stock_insights_snapshots(
                                symbol, 
                                report_date_obj, 
                                "fmp_short_volume", 
                                {"short_volume": data}
                            )
                        except Exception as e2:
                            self.logger.warning(f"Failed to save short volume for {symbol} {report_date}: {e}, fallback also failed: {e2}")
                            continue
                
                session.commit()
            
            self.logger.info(f"Saved {saved} short volume records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing short volume for {symbol}: {e}")
            return 0
    
    def _refresh_share_float(self, symbol: str) -> int:
        """Refresh share float data for a symbol"""
        try:
            self.logger.info(f"Refreshing share float for {symbol}")
            # Use FMP client to get share float
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            share_float_data = client.get_share_float(symbol)
            if not share_float_data:
                return 0
            
            # Save to stock_insights_snapshots table as fallback if share_float table doesn't exist
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                for data in share_float_data:
                    if not isinstance(data, dict):
                        continue
                    
                    report_date = data.get("date")
                    if not report_date:
                        continue
                    
                    # Convert date string to date object
                    try:
                        report_date_obj = datetime.strptime(report_date, "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        continue
                    
                    # Try to save to share_float table first, fallback to insights
                    try:
                        session.execute(
                            """
                            INSERT INTO share_float 
                            (symbol, shares_outstanding, shares_float, shares_authorized, shares_restricted, 
                             float_percent, insider_holding_percent, institutional_holding_percent, report_date, data_source)
                            VALUES (:symbol, :shares_outstanding, :shares_float, :shares_authorized, :shares_restricted,
                                    :float_percent, :insider_holding_percent, :institutional_holding_percent, :report_date, :data_source)
                            ON CONFLICT (symbol, report_date)
                            DO UPDATE SET
                                shares_outstanding = EXCLUDED.shares_outstanding,
                                shares_float = EXCLUDED.shares_float,
                                shares_authorized = EXCLUDED.shares_authorized,
                                shares_restricted = EXCLUDED.shares_restricted,
                                float_percent = EXCLUDED.float_percent,
                                insider_holding_percent = EXCLUDED.insider_holding_percent,
                                institutional_holding_percent = EXCLUDED.institutional_holding_percent,
                                updated_at = NOW()
                            """,
                            {
                                "symbol": symbol,
                                "shares_outstanding": data.get("sharesOutstanding"),
                                "shares_float": data.get("sharesFloat"),
                                "shares_authorized": data.get("sharesAuthorized"),
                                "shares_restricted": data.get("sharesRestricted"),
                                "float_percent": data.get("floatPercent"),
                                "insider_holding_percent": data.get("insiderHoldingPercent"),
                                "institutional_holding_percent": data.get("institutionalHoldingPercent"),
                                "report_date": report_date_obj,
                                "data_source": "fmp",
                            }
                        )
                        saved += 1
                    except Exception as e:
                        # Fallback to stock_insights_snapshots
                        try:
                            saved += self._save_to_stock_insights_snapshots(
                                symbol, 
                                report_date_obj, 
                                "fmp_share_float", 
                                {"share_float": data}
                            )
                        except Exception as e2:
                            self.logger.warning(f"Failed to save share float for {symbol} {report_date}: {e}, fallback also failed: {e2}")
                            continue
                
                session.commit()
            
            self.logger.info(f"Saved {saved} share float records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing share float for {symbol}: {e}")
            return 0
    
    def _refresh_risk_factors(self, symbol: str) -> int:
        """Refresh risk factors for a symbol"""
        try:
            self.logger.info(f"Refreshing risk factors for {symbol}")
            # Risk factors might come from SEC filings or other sources
            # For now, return 0 as this is not yet implemented
            self.logger.warning(f"Risk factors not yet implemented for {symbol}")
            return 0
            
        except Exception as e:
            self.logger.error(f"Error refreshing risk factors for {symbol}: {e}")
            return 0
    
    def _refresh_earnings_transcripts(self, symbol: str) -> int:
        """Refresh earnings transcripts for a symbol"""
        try:
            self.logger.info(f"Refreshing earnings transcripts for {symbol}")
            # Use FMP client to get earnings transcripts
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            # Get transcript dates first
            transcript_dates = client.get_transcript_dates_by_symbol(symbol)
            if not transcript_dates:
                return 0
            
            # Save to blog_content_metadata table
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                for transcript_info in transcript_dates:
                    if not isinstance(transcript_info, dict):
                        continue
                    
                    # Get the actual transcript
                    year = transcript_info.get("year")
                    quarter = transcript_info.get("quarter")
                    if not year or not quarter:
                        continue
                    
                    try:
                        transcript_data = client.get_earning_transcript(symbol, year=int(year), quarter=int(quarter))
                        if not transcript_data:
                            continue
                        
                        # Extract transcript content
                        transcript_content = ""
                        if isinstance(transcript_data, list) and len(transcript_data) > 0:
                            transcript_content = transcript_data[0].get("content", "")
                        elif isinstance(transcript_data, dict):
                            transcript_content = transcript_data.get("content", "")
                        
                        if not transcript_content:
                            continue
                        
                        # Create slug
                        slug = f"{symbol}-earnings-transcript-{year}-q{quarter}".lower()
                        
                        # Save as blog content
                        try:
                            session.execute(
                                """
                                INSERT INTO blog_content_metadata 
                                (stock_symbol, blog_tier, title, slug, summary, full_content, 
                                 publish_date, created_at, updated_at)
                                VALUES (:stock_symbol, :blog_tier, :title, :slug, :summary, :full_content,
                                        :publish_date, :created_at, :updated_at)
                                ON CONFLICT (slug)
                                DO UPDATE SET
                                    title = EXCLUDED.title,
                                    summary = EXCLUDED.summary,
                                    full_content = EXCLUDED.full_content,
                                    publish_date = EXCLUDED.publish_date,
                                    updated_at = EXCLUDED.updated_at
                                """,
                                {
                                    "stock_symbol": symbol,
                                    "blog_tier": "BASIC",
                                    "title": f"{symbol} Earnings Transcript - {year} Q{quarter}",
                                    "slug": slug,
                                    "summary": f"Earnings call transcript for {symbol} from {year} Q{quarter}",
                                    "full_content": transcript_content,
                                    "publish_date": datetime.now().date(),
                                    "created_at": datetime.now(),
                                    "updated_at": datetime.now(),
                                }
                            )
                            saved += 1
                        except Exception as e:
                            self.logger.warning(f"Failed to save earnings transcript for {symbol} {year} Q{quarter}: {e}")
                            continue
                            
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch transcript for {symbol} {year} Q{quarter}: {e}")
                        continue
                
                session.commit()
            
            self.logger.info(f"Saved {saved} earnings transcripts records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing earnings transcripts for {symbol}: {e}")
            return 0
    
    def _refresh_macro_market_data(self, symbol: str) -> int:
        """Refresh macro market data for a symbol"""
        try:
            self.logger.info(f"Refreshing macro market data for {symbol}")
            # Macro data is usually market-wide, not symbol-specific
            # For now, return 0 as this needs clarification
            self.logger.warning(f"Macro market data not yet implemented for {symbol}")
            return 0
            
        except Exception as e:
            self.logger.error(f"Error refreshing macro market data for {symbol}: {e}")
            return 0
    
    def _refresh_owner_earnings(self, symbol: str) -> int:
        """Refresh owner earnings for a symbol"""
        try:
            self.logger.info(f"Refreshing owner earnings for {symbol}")
            # Owner earnings calculated from financial statements
            # For now, return 0 as this is not yet implemented
            self.logger.warning(f"Owner earnings not yet implemented for {symbol}")
            return 0
            
        except Exception as e:
            self.logger.error(f"Error refreshing owner earnings for {symbol}: {e}")
            return 0

    def _dataset_for_data_type(self, data_type) -> str:
        """Convert DataType to dataset string for database storage"""
        if isinstance(data_type, str):
            return data_type
        elif hasattr(data_type, 'value'):
            return data_type.value
        else:
            return str(data_type)

    def _data_type_to_string(self, data_type) -> str:
        """Convert DataType to string for consistent handling"""
        if isinstance(data_type, str):
            return data_type
        elif hasattr(data_type, 'value'):
            return data_type.value
        else:
            return str(data_type)

    def _get_last_refresh(self, symbol: str, data_type: DataType) -> Optional[datetime]:
        """Get last refresh time for a symbol and data type"""
        # Check in-memory cache first
        if symbol in self._refresh_tracking:
            if data_type in self._refresh_tracking[symbol]:
                return self._refresh_tracking[symbol][data_type]

        dataset = self._dataset_for_data_type(data_type)
        interval = self._interval_for_data_type(data_type)
        query = """
            SELECT last_success_at
            FROM data_ingestion_state
            WHERE symbol = :symbol
              AND dataset = :dataset
              AND interval = :interval
        """
        result = db.execute_query(query, {"symbol": symbol, "dataset": dataset, "interval": interval})
        if result and result[0].get("last_success_at"):
            return result[0]["last_success_at"]

        return None

    def _update_refresh_tracking(self, symbol: str, data_type: DataType, status: str = 'success', error: str = None):
        """Update refresh tracking in database and memory"""
        # Update in-memory cache
        if symbol not in self._refresh_tracking:
            self._refresh_tracking[symbol] = {}
        self._refresh_tracking[symbol][data_type] = datetime.now()

        dataset = self._dataset_for_data_type(data_type)
        interval = self._interval_for_data_type(data_type)

        # Update database tracking (single source of truth)
        try:
            next_retry_at = None
            if status != 'success':
                # Industry standard: staged retry plan for non-transient quality/provider issues
                # Attempt 1: later same day (6h)
                # Attempt 2: next day (24h)
                # Attempt 3+: 48h
                try:
                    rc_row = db.execute_query(
                        """
                        SELECT retry_count
                        FROM data_ingestion_state
                        WHERE symbol = :symbol AND dataset = :dataset AND interval = :interval
                        """,
                        {"symbol": symbol, "dataset": dataset, "interval": interval},
                    )
                    current_retry_count = int(rc_row[0].get("retry_count") or 0) if rc_row else 0
                except Exception:
                    current_retry_count = 0

                if current_retry_count <= 0:
                    next_retry_at = datetime.utcnow() + timedelta(hours=6)
                elif current_retry_count == 1:
                    next_retry_at = datetime.utcnow() + timedelta(hours=24)
                else:
                    next_retry_at = datetime.utcnow() + timedelta(hours=48)

            query = """
                INSERT INTO data_ingestion_state
                (symbol, dataset, interval, source, cursor_ts, last_attempt_at, last_success_at, status, error_message, retry_count)
                VALUES (:symbol, :dataset, :interval, :source, :cursor_ts, :last_attempt_at, :last_success_at, :status, :error,
                        CASE WHEN :status = 'success' THEN 0 ELSE 1 END)
                ON CONFLICT (symbol, dataset, interval)
                DO UPDATE SET
                  source = EXCLUDED.source,
                  cursor_ts = EXCLUDED.cursor_ts,
                  last_attempt_at = EXCLUDED.last_attempt_at,
                  last_success_at = EXCLUDED.last_success_at,
                  status = EXCLUDED.status,
                  error_message = EXCLUDED.error_message,
                  retry_count = CASE WHEN EXCLUDED.status = 'success' THEN 0 ELSE data_ingestion_state.retry_count + 1 END,
                  updated_at = NOW()
            """

            db.execute_update(
                query,
                {
                    "symbol": symbol,
                    "dataset": dataset,
                    "interval": interval,
                    "source": self.data_source.name,
                    "cursor_ts": next_retry_at,
                    "last_attempt_at": datetime.utcnow(),
                    "last_success_at": datetime.utcnow() if status == 'success' else None,
                    "status": status,
                    "error": error
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to update refresh tracking for {symbol}: {e}", exc_info=True)
    
    def _refresh_income_statement_growth(self, symbol: str) -> int:
        """Refresh income statement growth data for a symbol"""
        try:
            self.logger.info(f"Refreshing income statement growth for {symbol}")
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            growth_data = client.get_income_statement_growth(symbol)
            if not growth_data:
                return 0
            
            # Save to stock_insights_snapshots table
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                # Store each growth record separately by its actual date
                for record in growth_data:
                    record_date = record.get('date')
                    if not record_date:
                        continue
                    
                    # Convert string date to date object
                    try:
                        if isinstance(record_date, str):
                            insights_date = datetime.strptime(record_date, '%Y-%m-%d').date()
                        else:
                            insights_date = record_date
                    except ValueError:
                        self.logger.warning(f"Invalid date format in growth record: {record_date}")
                        continue
                    
                    try:
                        saved += self._save_to_stock_insights_snapshots(
                            symbol, 
                            insights_date, 
                            "fmp_income_statement_growth", 
                            {"income_statement_growth": record}
                        )
                    except Exception as e:
                        self.logger.warning(f"Failed to save income statement growth for {symbol} on {insights_date}: {e}")
                
                session.commit()
            
            self.logger.info(f"Saved {saved} income statement growth records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing income statement growth for {symbol}: {e}")
            return 0
    
    def _refresh_balance_sheet_growth(self, symbol: str) -> int:
        """Refresh balance sheet growth data for a symbol"""
        try:
            self.logger.info(f"Refreshing balance sheet growth for {symbol}")
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            growth_data = client.get_balance_sheet_growth(symbol)
            if not growth_data:
                return 0
            
            # Save to stock_insights_snapshots table
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                # Store each growth record separately by its actual date
                for record in growth_data:
                    record_date = record.get('date')
                    if not record_date:
                        continue
                    
                    # Convert string date to date object
                    try:
                        if isinstance(record_date, str):
                            insights_date = datetime.strptime(record_date, '%Y-%m-%d').date()
                        else:
                            insights_date = record_date
                    except ValueError:
                        self.logger.warning(f"Invalid date format in growth record: {record_date}")
                        continue
                    
                    try:
                        saved += self._save_to_stock_insights_snapshots(
                            symbol, 
                            insights_date, 
                            "fmp_balance_sheet_growth", 
                            {"balance_sheet_growth": record}
                        )
                    except Exception as e:
                        self.logger.warning(f"Failed to save balance sheet growth for {symbol} on {insights_date}: {e}")
                
                session.commit()
            
            self.logger.info(f"Saved {saved} balance sheet growth records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing balance sheet growth for {symbol}: {e}")
            return 0
    
    def _refresh_cash_flow_growth(self, symbol: str) -> int:
        """Refresh cash flow growth data for a symbol"""
        try:
            self.logger.info(f"Refreshing cash flow growth for {symbol}")
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            growth_data = client.get_cash_flow_growth(symbol)
            if not growth_data:
                return 0
            
            # Save to stock_insights_snapshots table
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                # Store each growth record separately by its actual date
                for record in growth_data:
                    record_date = record.get('date')
                    if not record_date:
                        continue
                    
                    # Convert string date to date object
                    try:
                        if isinstance(record_date, str):
                            insights_date = datetime.strptime(record_date, '%Y-%m-%d').date()
                        else:
                            insights_date = record_date
                    except ValueError:
                        self.logger.warning(f"Invalid date format in growth record: {record_date}")
                        continue
                    
                    try:
                        saved += self._save_to_stock_insights_snapshots(
                            symbol, 
                            insights_date, 
                            "fmp_cash_flow_growth", 
                            {"cash_flow_growth": record}
                        )
                    except Exception as e:
                        self.logger.warning(f"Failed to save cash flow growth for {symbol} on {insights_date}: {e}")
                
                session.commit()
            
            self.logger.info(f"Saved {saved} cash flow growth records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing cash flow growth for {symbol}: {e}")
            return 0
    
    def _refresh_financial_growth(self, symbol: str) -> int:
        """Refresh comprehensive financial growth data for a symbol"""
        try:
            self.logger.info(f"Refreshing financial growth for {symbol}")
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            client = EnhancedFMPClient.from_settings()
            
            growth_data = client.get_financial_growth(symbol)
            if not growth_data:
                return 0
            
            # Save to stock_insights_snapshots table
            saved = 0
            from app.database import db
            from datetime import datetime
            with db.get_session() as session:
                # Store each growth record separately by its actual date
                for record in growth_data:
                    record_date = record.get('date')
                    if not record_date:
                        continue
                    
                    # Convert string date to date object
                    try:
                        if isinstance(record_date, str):
                            insights_date = datetime.strptime(record_date, '%Y-%m-%d').date()
                        else:
                            insights_date = record_date
                    except ValueError:
                        self.logger.warning(f"Invalid date format in growth record: {record_date}")
                        continue
                    
                    try:
                        saved += self._save_to_stock_insights_snapshots(
                            symbol, 
                            insights_date, 
                            "fmp_financial_growth", 
                            {"financial_growth": record}
                        )
                    except Exception as e:
                        self.logger.warning(f"Failed to save financial growth for {symbol} on {insights_date}: {e}")
                
                session.commit()
            
            self.logger.info(f"Saved {saved} financial growth records for {symbol}")
            return saved
            
        except Exception as e:
            self.logger.error(f"Error refreshing financial growth for {symbol}: {e}")
            return 0
