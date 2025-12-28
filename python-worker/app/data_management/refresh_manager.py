"""
Data Refresh Manager
Orchestrates data fetching with multiple refresh strategies
Follows DRY and SOLID principles
"""
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta, date
from enum import Enum
import pandas as pd
import json

from app.services.base import BaseService
from app.data_sources import get_data_source, BaseDataSource
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
from app.utils.trading_calendar import expected_trading_days, expected_intraday_15m_timestamps


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
            try:
                if not force:
                    last_refresh = self._get_last_refresh(symbol, data_type)
                    if not strategy.should_refresh(symbol, data_type, last_refresh):
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
                            elif data_type == DataType.PRICE_INTRADAY_15M:
                                self._auto_backfill_intraday_15m(symbol, lookback_days=2)
                        except Exception as e:
                            self.logger.warning(f"Auto backfill failed for {symbol} {data_type}: {e}")
                    successful += 1
                    self.logger.info(f"✅ Refreshed {data_type} for {symbol}: {result.message}")
                else:
                    self._update_refresh_tracking(symbol, data_type, status='failed', error=result.error)
                    failed += 1
                    self.logger.warning(f"⚠️ Failed to refresh {data_type} for {symbol}: {result.error or result.message}")
            except Exception as e:
                error_msg = str(e)
                self.logger.error(f"Error refreshing {data_type} for {symbol}: {e}", exc_info=True)
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
            SELECT trade_date
            FROM raw_market_data_daily
            WHERE stock_symbol = :symbol
              AND trade_date >= :start_date
              AND trade_date <= :end_date
            """,
            {"symbol": symbol, "start_date": start_date, "end_date": end_date},
        )
        present = {r["trade_date"] for r in present_rows if r.get("trade_date")}
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

    def _auto_backfill_intraday_15m(self, symbol: str, lookback_days: int = 2) -> None:
        """Detect and backfill missing 15m bars for the last N trading days."""
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=int(lookback_days))

        expected_ts = expected_intraday_15m_timestamps(start_date, end_date)
        if not expected_ts:
            return

        start_ts = min(expected_ts)
        end_ts = max(expected_ts) + pd.Timedelta(minutes=15)

        actual_rows = db.execute_query(
            """
            SELECT ts
            FROM raw_market_data_intraday
            WHERE stock_symbol = :symbol
              AND interval = '15m'
              AND ts >= :start_ts
              AND ts <= :end_ts
            """,
            {"symbol": symbol, "start_ts": start_ts.to_pydatetime(), "end_ts": end_ts.to_pydatetime()},
        )
        actual = {pd.to_datetime(r["ts"]).tz_convert("UTC").floor("15min") for r in actual_rows if r.get("ts")}
        expected = {pd.to_datetime(t).tz_convert("UTC").floor("15min") for t in expected_ts}
        missing = sorted(expected - actual)
        if not missing:
            return

        # Fetch full range covering missing; upsert makes it idempotent.
        df = self.data_source.fetch_price_data(
            symbol,
            start_date=min(missing).to_pydatetime(),
            end_date=(max(missing) + pd.Timedelta(minutes=15)).to_pydatetime(),
            interval="15m",
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

        MarketDataIntradayRepository.upsert_many(rows)
        self._update_ingestion_window(
            symbol=symbol,
            dataset=self._dataset_for_data_type(DataType.PRICE_INTRADAY_15M),
            interval="15m",
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
                (stock_symbol, dataset, interval, source, historical_start_date, historical_end_date, cursor_date, cursor_ts, last_attempt_at, last_success_at, status)
                VALUES (:symbol, :dataset, :interval, :source, :hs, :he, :cd, :cts, NOW(), NOW(), 'success')
                ON CONFLICT (stock_symbol, dataset, interval)
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
                SELECT DISTINCT stock_symbol
                FROM holdings
                WHERE stock_symbol IS NOT NULL AND stock_symbol != ''
                ORDER BY stock_symbol
                """
            )
        except Exception:
            holdings = []

        symbols = [h.get("stock_symbol") for h in holdings if h.get("stock_symbol")]
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
        if data_type == DataType.PRICE_INTRADAY_15M:
            return "15m"
        return "daily"
    
    def _refresh_data_type_with_result(self, symbol: str, data_type: DataType) -> DataTypeRefreshResult:
        """Refresh a specific data type with detailed result"""
        start_time = datetime.now()
        
        try:
            if data_type == DataType.PRICE_HISTORICAL:
                rows, cleaned_data = self._refresh_price_historical(symbol)
                if rows > 0:
                    # Industry Standard: Auto-calculate indicators immediately after price data load
                    # Use the cleaned/validated data for indicator calculation to ensure data quality
                    try:
                        from app.services.indicator_service import IndicatorService
                        indicator_service = IndicatorService()
                        # Pass cleaned_data to ensure indicators use validated data
                        if not indicator_service.calculate_indicators(symbol, data=cleaned_data):
                            error_msg = f"Failed to calculate indicators for {symbol} after price data fetch"
                            self.logger.error(error_msg)
                            raise RuntimeError(error_msg)
                        self.logger.info(f"✅ Auto-calculated indicators for {symbol} after price data fetch (Industry Standard: Always calculate after data load)")
                    except Exception as e:
                        # Fail fast - indicators are critical for signal generation
                        error_msg = f"Critical: Failed to calculate indicators for {symbol} after price data fetch: {str(e)}"
                        self.logger.error(error_msg, exc_info=True)
                        raise RuntimeError(error_msg) from e
                    
                    return DataTypeRefreshResult(
                        data_type=data_type.value,
                        status=RefreshStatus.SUCCESS,
                        message=f"Successfully fetched {rows} rows of historical price data and calculated indicators",
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
            elif data_type == DataType.PRICE_INTRADAY_15M:
                rows = self._refresh_price_intraday_15m(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                    message=f"Saved {rows} 15m candles" if rows > 0 else "No 15m candles saved",
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
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                    message=f"Fetched {rows} news articles" if rows > 0 else "No news articles found",
                    rows_affected=rows,
                    error=None if rows > 0 else "No news data available",
                    timestamp=start_time
                )
            elif data_type == DataType.EARNINGS:
                rows = self._refresh_earnings(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                    message=f"Fetched {rows} earnings records" if rows > 0 else "No earnings data found",
                    rows_affected=rows,
                    error=None if rows > 0 else "No earnings data available",
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
            elif data_type == DataType.INDICATORS:
                from app.services.indicator_service import IndicatorService
                service = IndicatorService()
                success = service.calculate_indicators(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if success else RefreshStatus.FAILED,
                    message="Indicators calculated successfully" if success else "Failed to calculate indicators",
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
                rows = self._refresh_income_statements(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                    message=f"Fetched {rows} income statements" if rows > 0 else "No income statements found",
                    rows_affected=rows,
                    error=None if rows > 0 else "No income statement data available",
                    timestamp=start_time
                )
            elif data_type == DataType.BALANCE_SHEETS:
                rows = self._refresh_balance_sheets(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                    message=f"Fetched {rows} balance sheets" if rows > 0 else "No balance sheets found",
                    rows_affected=rows,
                    error=None if rows > 0 else "No balance sheet data available",
                    timestamp=start_time
                )
            elif data_type == DataType.CASH_FLOW_STATEMENTS:
                rows = self._refresh_cash_flow_statements(symbol)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if rows > 0 else RefreshStatus.FAILED,
                    message=f"Fetched {rows} cash flow statements" if rows > 0 else "No cash flow statements found",
                    rows_affected=rows,
                    error=None if rows > 0 else "No cash flow statement data available",
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
                result = service.aggregate_to_weekly(symbol, force=True)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if result.get('success') else RefreshStatus.FAILED,
                    message=f"Aggregated {result.get('rows_created', 0)} weekly bars" if result.get('success') else "Weekly aggregation failed",
                    rows_affected=result.get('rows_created', 0),
                    error=None if result.get('success') else result.get('error', 'Unknown error'),
                    timestamp=start_time
                )
            elif data_type == DataType.GROWTH_CALCULATIONS:
                from app.services.growth_calculation_service import GrowthCalculationService
                service = GrowthCalculationService()
                result = service.calculate_growth_metrics(symbol, force=True)
                return DataTypeRefreshResult(
                    data_type=data_type.value,
                    status=RefreshStatus.SUCCESS if result.get('success') else RefreshStatus.FAILED,
                    message="Growth metrics calculated" if result.get('success') else "Growth calculation failed",
                    error=None if result.get('success') else result.get('error', 'Unknown error'),
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
            
            if data is not None and not data.empty:
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
            else:
                error_message = "No data returned from data source"
                self.logger.warning(f"⚠️ {error_message} for {symbol}")
                cleaned_data = pd.DataFrame()  # Empty DataFrame if no data
            
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

    def _refresh_price_intraday_15m(self, symbol: str, days: int = 5) -> int:
        """Fetch and persist true 15m candles into raw_market_data_intraday."""
        import time

        start_time = time.time()
        fetch_success = False
        rows_fetched = 0
        rows_saved = 0
        error_message = None

        try:
            data = self.data_source.fetch_price_data(symbol, period=f"{days}d", interval="15m")
            rows_fetched = len(data) if data is not None and not getattr(data, "empty", True) else 0
            if data is None or getattr(data, "empty", True):
                error_message = "No intraday data returned"
                return 0

            rows: List[IntradayBarUpsertRow] = []
            for _, r in data.iterrows():
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

            rows_saved = MarketDataIntradayRepository.upsert_many(rows)
            fetch_success = rows_saved > 0
            if rows_saved > 0:
                self._update_ingestion_window(
                    symbol=symbol,
                    dataset=self._dataset_for_data_type(DataType.PRICE_INTRADAY_15M),
                    interval="15m",
                    source=self.data_source.name,
                    cursor_ts=max(pd.to_datetime(r.get("ts")).tz_convert("UTC") for r in data.to_dict("records") if r.get("ts")),
                )
            return rows_saved
        except Exception as e:
            error_message = str(e)
            self.logger.error(f"Error refreshing 15m candles for {symbol}: {e}", exc_info=True)
            return 0
        finally:
            fetch_duration_ms = int((time.time() - start_time) * 1000)
            self._audit_data_fetch(
                symbol=symbol,
                fetch_type='price_intraday_15m',
                fetch_mode='periodic',
                data_source=self.data_source.name,
                rows_fetched=rows_fetched,
                rows_saved=rows_saved,
                fetch_duration_ms=fetch_duration_ms,
                success=fetch_success,
                error_message=error_message,
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
            price = self.data_source.fetch_current_price(symbol)
            if price is None:
                error_message = "No current price returned"
                return False

            rows_fetched = 1
            ts = datetime.utcnow()
            row = IntradayBarUpsertRow(
                stock_symbol=symbol,
                ts=ts,
                interval="last",
                open=float(price),
                high=float(price),
                low=float(price),
                close=float(price),
                volume=None,
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
                error_message=error_message,
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
            # Database error - fail fast
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
        """Refresh fundamental data and save to fundamentals_snapshots"""
        try:
            # Fetch enhanced fundamentals (includes all metrics)
            if hasattr(self.data_source, 'fetch_enhanced_fundamentals'):
                fundamentals = self.data_source.fetch_enhanced_fundamentals(symbol)
            else:
                fundamentals = self.data_source.fetch_fundamentals(symbol)
            if fundamentals:
                query = """
                    INSERT INTO fundamentals_snapshots
                    (stock_symbol, as_of_date, source, payload)
                    VALUES (:symbol, :as_of_date, :source, CAST(:payload AS JSONB))
                    ON CONFLICT (stock_symbol, as_of_date)
                    DO UPDATE SET payload = EXCLUDED.payload, source = EXCLUDED.source, updated_at = NOW()
                """

                db.execute_update(
                    query,
                    {
                        "symbol": symbol,
                        "as_of_date": datetime.utcnow().date(),
                        "source": self.data_source.name,
                        "payload": json.dumps(fundamentals),
                    },
                )

                self.logger.info(f"✅ Saved fundamentals snapshot for {symbol}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error refreshing fundamentals for {symbol}: {e}", exc_info=True)
            raise  # Fail fast - fundamentals refresh should not silently fail
    
    def _refresh_news(self, symbol: str) -> int:
        """Refresh news data
        
        Returns:
            Number of news articles saved (0 if failed)
        """
        """Refresh news data"""
        try:
            news = self.data_source.fetch_news(symbol, limit=20)
            if news:
                import uuid
                import json
                from datetime import datetime
                
                # Save to stock_news table
                for article in news:
                    news_id = str(uuid.uuid4())
                    published_date = None
                    if article.get('published_date'):
                        if isinstance(article['published_date'], datetime):
                            published_date = article['published_date']
                        else:
                            try:
                                published_date = datetime.fromisoformat(str(article['published_date']).replace('Z', '+00:00'))
                            except (ValueError, TypeError) as e:
                                self.logger.warning(f"Invalid published_date format for {symbol} news article '{article.get('title', 'unknown')}': {e}")
                                published_date = None
                    
                    query = """
                        INSERT INTO stock_news
                        (news_id, stock_symbol, title, publisher, link, published_at, related_symbols, source)
                        VALUES (:news_id, :symbol, :title, :publisher, :link, :published_at, CAST(:related_symbols AS JSONB), :source)
                        ON CONFLICT (news_id) DO NOTHING
                    """

                    related_symbols_json = article.get('related_symbols', [])
                    db.execute_update(query, {
                        "news_id": news_id,
                        "symbol": symbol,
                        "title": article.get('title', ''),
                        "publisher": article.get('publisher', ''),
                        "link": article.get('link', ''),
                        "published_at": published_date,
                        "related_symbols": json.dumps(related_symbols_json),
                        "source": self.data_source.name,
                    })
                
                self.logger.info(f"✅ Saved {len(news)} news articles for {symbol}")
                return len(news)
            return 0
        except Exception as e:
            self.logger.error(f"Error refreshing news for {symbol}: {e}", exc_info=True)
            raise  # Re-raise to be caught by caller
    
    def _refresh_earnings(self, symbol: str) -> int:
        """Refresh earnings data
        
        Returns:
            Number of earnings records saved (0 if failed)
        """
        import time
        start_time = time.time()
        fetch_success = False
        rows_fetched = 0
        rows_saved = 0
        error_message = None
        audit_done = False  # Track if audit has been performed
        
        try:
            earnings = self.data_source.fetch_earnings(symbol)
            rows_fetched = len(earnings) if earnings else 0
            
            if earnings:
                import json
                from datetime import datetime
                
                # Save to earnings_data table
                # Only save records with valid earnings_date (NOT NULL constraint)
                saved_count = 0
                for earning in earnings:
                    # Parse earnings_date - must be valid for database insertion
                    earnings_date = None
                    if earning.get('earnings_date'):
                        try:
                            if isinstance(earning['earnings_date'], datetime):
                                earnings_date = earning['earnings_date'].date()
                            elif isinstance(earning['earnings_date'], pd.Timestamp):
                                earnings_date = earning['earnings_date'].to_pydatetime().date()
                            elif isinstance(earning['earnings_date'], str):
                                earnings_date = datetime.fromisoformat(earning['earnings_date']).date()
                            else:
                                self.logger.warning(f"Invalid earnings_date type for {symbol}: {type(earning['earnings_date'])}")
                                continue  # Skip this record
                        except (ValueError, TypeError, AttributeError) as e:
                            self.logger.warning(f"Invalid earnings_date format for {symbol}: {e}")
                            continue  # Skip this record
                    
                    # Skip records without valid earnings_date (NOT NULL constraint)
                    if not earnings_date:
                        self.logger.debug(f"Skipping earnings record for {symbol} - no valid earnings_date")
                        continue
                    
                    # Generate earnings_id from symbol and date
                    earnings_id = f"{symbol}_{earnings_date.strftime('%Y-%m-%d')}"
                    
                    query = """
                        INSERT INTO earnings_data
                        (earnings_id, stock_symbol, earnings_date, eps_estimate, eps_actual,
                         revenue_estimate, revenue_actual, surprise_percentage, source)
                        VALUES (:earnings_id, :symbol, :earnings_date, :eps_estimate, :eps_actual,
                                :revenue_estimate, :revenue_actual, :surprise_percentage, :source)
                        ON CONFLICT (stock_symbol, earnings_date)
                        DO UPDATE SET
                          eps_estimate = EXCLUDED.eps_estimate,
                          eps_actual = EXCLUDED.eps_actual,
                          revenue_estimate = EXCLUDED.revenue_estimate,
                          revenue_actual = EXCLUDED.revenue_actual,
                          surprise_percentage = EXCLUDED.surprise_percentage,
                          source = EXCLUDED.source,
                          updated_at = NOW()
                    """
                    
                    # Calculate surprise percentage if both estimate and actual exist
                    surprise_pct = None
                    if earning.get('eps_estimate') is not None and earning.get('eps_actual') is not None:
                        try:
                            estimate = float(earning['eps_estimate'])
                            actual = float(earning['eps_actual'])
                            if estimate != 0:
                                surprise_pct = ((actual - estimate) / abs(estimate)) * 100
                            else:
                                self.logger.debug(f"EPS estimate is zero for {symbol}, cannot calculate surprise percentage")
                        except (ValueError, TypeError, ZeroDivisionError) as e:
                            self.logger.debug(f"Failed to calculate surprise percentage for {symbol}: {e}")
                            surprise_pct = None
                    # Also use surprise_percentage from source if available
                    elif earning.get('surprise_percentage') is not None:
                        try:
                            surprise_pct = float(earning['surprise_percentage'])
                        except (ValueError, TypeError):
                            surprise_pct = None
                    
                    try:
                        db.execute_update(query, {
                            "earnings_id": earnings_id,
                            "symbol": symbol,
                            "earnings_date": earnings_date,
                            "eps_estimate": earning.get('eps_estimate'),
                            "eps_actual": earning.get('eps_actual'),
                            "revenue_estimate": earning.get('revenue_estimate'),
                            "revenue_actual": earning.get('revenue_actual'),
                            "surprise_percentage": surprise_pct,
                            "source": self.data_source.name,
                        })
                        saved_count += 1
                    except Exception as e:
                        self.logger.error(f"Failed to save earnings record for {symbol} on {earnings_date}: {e}")
                        # Continue with next record instead of failing completely
                        continue
                
                rows_saved = saved_count
                fetch_duration_ms = int((time.time() - start_time) * 1000)
                
                # Determine success and error message
                if rows_saved == 0 and rows_fetched > 0:
                    # Fetched data but couldn't save any - this is a failure
                    fetch_success = False
                    error_message = f"Fetched {rows_fetched} earnings records but saved 0. All records had invalid or missing earnings_date. Check data source format."
                    self.logger.warning(f"⚠️ {error_message} for {symbol}")
                elif rows_saved < rows_fetched:
                    # Partial success - some records saved, some failed
                    fetch_success = True  # Partial success is still success
                    skipped = rows_fetched - rows_saved
                    error_message = f"Partially successful: Saved {rows_saved} out of {rows_fetched} records. {skipped} records skipped due to invalid earnings_date."
                    self.logger.warning(f"⚠️ {error_message} for {symbol}")
                else:
                    # All records saved successfully
                    fetch_success = True
                    error_message = None
                    self.logger.info(f"✅ Saved {saved_count} out of {len(earnings)} earnings records for {symbol} from {self.data_source.name}")
                
                # Audit the fetch with proper success/error status
                self._audit_data_fetch(
                    symbol=symbol,
                    fetch_type='earnings',
                    fetch_mode='on_demand',
                    data_source=self.data_source.name,
                    rows_fetched=rows_fetched,
                    rows_saved=rows_saved,
                    fetch_duration_ms=fetch_duration_ms,
                    success=fetch_success,
                    error_message=error_message
                )
                audit_done = True
                return saved_count
            else:
                error_message = f"No earnings data returned from data source ({self.data_source.name}). Possible reasons: 1) Earnings data not available for this symbol, 2) Data source doesn't support earnings (e.g., Massive.com placeholder), 3) Earnings API endpoint requires subscription tier."
                self.logger.warning(f"⚠️ {error_message} for {symbol}")
                # Audit the fetch even if no data was returned
                fetch_duration_ms = int((time.time() - start_time) * 1000)
                self._audit_data_fetch(
                    symbol=symbol,
                    fetch_type='earnings',
                    fetch_mode='on_demand',
                    data_source=self.data_source.name,
                    rows_fetched=0,
                    rows_saved=0,
                    fetch_duration_ms=fetch_duration_ms,
                    success=False,
                    error_message=error_message
                )
                audit_done = True
            return 0
        except Exception as e:
            error_message = f"Exception fetching earnings from {self.data_source.name}: {str(e)}"
            self.logger.error(f"Error refreshing earnings for {symbol} from {self.data_source.name}: {e}", exc_info=True)
            # Audit the failed fetch before re-raising
            if not audit_done:
                fetch_duration_ms = int((time.time() - start_time) * 1000)
                self._audit_data_fetch(
                    symbol=symbol,
                    fetch_type='earnings',
                    fetch_mode='on_demand',
                    data_source=self.data_source.name,
                    rows_fetched=rows_fetched,
                    rows_saved=rows_saved,
                    fetch_duration_ms=fetch_duration_ms,
                    success=False,
                    error_message=error_message
                )
            raise  # Re-raise to be caught by caller
    
    def _refresh_income_statements(self, symbol: str) -> int:
        """Deprecated in the new DRY schema (not stored as structured statements currently)."""
        self.logger.info("Skipping income statements refresh (not enabled in baseline schema)")
        return 0
    
    def _refresh_balance_sheets(self, symbol: str) -> int:
        """Deprecated in the new DRY schema (not stored as structured statements currently)."""
        self.logger.info("Skipping balance sheets refresh (not enabled in baseline schema)")
        return 0
    
    def _refresh_cash_flow_statements(self, symbol: str) -> int:
        """Stub for cash flow statements refresh in new baseline schema."""
        self.logger.info("Cash flow statements refresh not implemented in baseline schema")
        return 0
    
    def _refresh_financial_ratios(self, symbol: str) -> int:
        """Stub for financial ratios refresh in new baseline schema."""
        self.logger.info("Financial ratios refresh not implemented in baseline schema")
        return 0
    
    def _refresh_industry_peers(self, symbol: str) -> bool:
        """Refresh industry peers and save to industry_peers."""
        try:
            peers_data = self.data_source.fetch_industry_peers(symbol)
            if not peers_data:
                return False

            if not isinstance(peers_data, dict):
                return False

            sector = peers_data.get('sector')
            industry = peers_data.get('industry')
            peers_list = peers_data.get('peers') or []

            if not peers_list:
                return bool(sector or industry)

            saved = 0
            for peer in peers_list:
                peer_symbol = (peer.get('symbol') or peer.get('ticker') or '').strip()
                if not peer_symbol:
                    continue

                query = """
                    INSERT INTO industry_peers
                    (stock_symbol, peer_symbol, sector, industry, peer_name, peer_market_cap, source)
                    VALUES (:symbol, :peer_symbol, :sector, :industry, :peer_name, :peer_market_cap, :source)
                    ON CONFLICT (stock_symbol, peer_symbol)
                    DO UPDATE SET
                      sector = EXCLUDED.sector,
                      industry = EXCLUDED.industry,
                      peer_name = EXCLUDED.peer_name,
                      peer_market_cap = EXCLUDED.peer_market_cap,
                      source = EXCLUDED.source,
                      updated_at = NOW()
                """

                db.execute_update(
                    query,
                    {
                        "symbol": symbol,
                        "peer_symbol": peer_symbol,
                        "sector": sector,
                        "industry": industry,
                        "peer_name": peer.get('name'),
                        "peer_market_cap": peer.get('market_cap') or peer.get('peer_market_cap'),
                        "source": self.data_source.name,
                    },
                )
                saved += 1

            self.logger.info(f"✅ Saved {saved} peers to industry_peers for {symbol}")
            return saved > 0
        except Exception as e:
            self.logger.error(f"Error refreshing industry peers for {symbol}: {e}", exc_info=True)
            raise
    
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
            WHERE stock_symbol = :symbol
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
            query = """
                INSERT INTO data_ingestion_state
                (stock_symbol, dataset, interval, source, last_attempt_at, last_success_at, status, error_message)
                VALUES (:symbol, :dataset, :interval, :source, :last_attempt_at, :last_success_at, :status, :error)
                ON CONFLICT (stock_symbol, dataset, interval)
                DO UPDATE SET
                  source = EXCLUDED.source,
                  last_attempt_at = EXCLUDED.last_attempt_at,
                  last_success_at = EXCLUDED.last_success_at,
                  status = EXCLUDED.status,
                  error_message = EXCLUDED.error_message,
                  updated_at = NOW()
            """

            db.execute_update(
                query,
                {
                    "symbol": symbol,
                    "dataset": dataset,
                    "interval": interval,
                    "source": self.data_source.name,
                    "last_attempt_at": datetime.utcnow(),
                    "last_success_at": datetime.utcnow() if status == 'success' else None,
                    "status": status,
                    "error": error
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to update refresh tracking for {symbol}: {e}", exc_info=True)
