"""
Market data fetching service
Fetches data from Yahoo Finance and other sources
"""
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
import time

import yfinance as yf
import pandas as pd
import numpy as np
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.database import db
from app.repositories.market_data_daily_repository import DailyBarUpsertRow, MarketDataDailyRepository
from app.services.base import BaseService
from app.exceptions import DataSourceError
from app.utils.validation_patterns import validate_symbol_param, validate_period
from app.utils.exception_handler import handle_exceptions


class DataFetcher(BaseService):
    """Fetches market data from various sources"""
    
    def __init__(self):
        super().__init__()
        self.retry_attempts = settings.data_fetch_retry_attempts
        self.retry_delay = settings.data_fetch_retry_delay
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def fetch_stock_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = "1y"
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical stock data from Yahoo Finance
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            start_date: Start date for data
            end_date: End date for data
            period: Period string (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        
        Returns:
            DataFrame with OHLCV data
        """
        # Validate inputs
        symbol = validate_symbol_param(symbol)
        period = validate_period(period) if period else "1y"
        
        ticker = yf.Ticker(symbol)
        
        if start_date and end_date:
            data = ticker.history(start=start_date, end=end_date)
        else:
            data = ticker.history(period=period)
        
        if data.empty:
            self.log_warning(f"No data found for symbol {symbol}", context={'symbol': symbol})
            return None
        
        # Rename columns to lowercase
        data.columns = [col.lower() for col in data.columns]
        data.reset_index(inplace=True)
        
        self.log_info(f"✅ Fetched {len(data)} rows for {symbol}", context={'symbol': symbol, 'rows': len(data)})
        return data
    
    @handle_exceptions(default_exception=DataSourceError, context_keys=['symbol'])
    def fetch_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch fundamental data for a stock
        
        Returns:
            Dictionary with fundamental metrics
        """
        # Validate symbol
        symbol = validate_symbol_param(symbol)
        
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Extract key fundamental data
        fundamental_data = {
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "dividend_yield": info.get("dividendYield"),
            "eps": info.get("trailingEps"),
            "revenue": info.get("totalRevenue"),
            "profit_margin": info.get("profitMargins"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }
        
        self.log_info(f"✅ Fetched fundamental data for {symbol}", context={'symbol': symbol})
        return fundamental_data
    
    def fetch_options_data(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch options chain data
        
        Returns:
            Dictionary with options data summary
        """
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            
            if not expirations:
                return {}
            
            # Get nearest expiration
            nearest_exp = expirations[0] if expirations else None
            if not nearest_exp:
                return {}
            
            opt_chain = ticker.option_chain(nearest_exp)
            
            # Summarize options data
            options_data = {
                "nearest_expiration": nearest_exp,
                "call_count": len(opt_chain.calls) if opt_chain.calls is not None else 0,
                "put_count": len(opt_chain.puts) if opt_chain.puts is not None else 0,
                "expirations": list(expirations[:5])  # First 5 expirations
            }
            
            self.log_info(f"✅ Fetched options data for {symbol}", context={'symbol': symbol})
            return options_data
            
        except Exception as e:
            self.log_error(f"Error fetching options data for {symbol}", e, context={'symbol': symbol})
            return {}
    
    def save_raw_market_data(
        self,
        symbol: str,
        data: pd.DataFrame,
        fundamental_data: Optional[Dict[str, Any]] = None,
        options_data: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Save raw market data to database
        
        Returns:
            Number of rows inserted/updated
        """
        rows: list[DailyBarUpsertRow] = []

        # Normalize column names to handle both uppercase and lowercase
        col_map: dict[str, str] = {}
        for col in data.columns:
            col_lower = str(col).lower()
            if col_lower not in col_map:
                col_map[col_lower] = col

        def get_col_value(row, col_name: str, default=None):
            col_lower = col_name.lower()
            if col_name in data.columns:
                return row[col_name]
            if col_lower in col_map:
                return row[col_map[col_lower]]
            return default

        def to_float(value) -> Optional[float]:
            if value is None:
                return None
            try:
                if pd.isna(value):
                    return None
            except Exception:
                pass
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        def to_int(value) -> Optional[int]:
            f = to_float(value)
            if f is None:
                return None
            try:
                return int(f)
            except (ValueError, TypeError):
                return None

        for idx, row in data.iterrows():
            date_value = get_col_value(row, 'date') or get_col_value(row, 'Date')

            if date_value is None or (isinstance(date_value, (int, float)) and pd.isna(date_value)):
                if isinstance(data.index, pd.DatetimeIndex):
                    date_value = data.index[data.index.get_loc(idx)]
                elif hasattr(idx, 'date'):
                    date_value = idx
                else:
                    date_value = datetime.now()

            if isinstance(date_value, pd.Timestamp):
                trade_date = date_value.date()
            elif isinstance(date_value, datetime):
                trade_date = date_value.date()
            elif isinstance(date_value, date):
                trade_date = date_value
            elif isinstance(date_value, (np.datetime64,)):
                trade_date = pd.to_datetime(date_value).date()
            elif isinstance(date_value, str):
                try:
                    trade_date = pd.to_datetime(date_value).date()
                except Exception:
                    trade_date = datetime.now().date()
            elif hasattr(date_value, 'date'):
                try:
                    trade_date = date_value.date()
                except Exception:
                    trade_date = datetime.now().date()
            else:
                trade_date = datetime.now().date()

            # yfinance uses 'adj close' column name (space). Some sources use adj_close.
            adj_close = (
                to_float(get_col_value(row, 'adj close'))
                if get_col_value(row, 'adj close') is not None
                else to_float(get_col_value(row, 'adj_close'))
            )

            rows.append(
                DailyBarUpsertRow(
                    stock_symbol=symbol,
                    trade_date=trade_date,
                    open=to_float(get_col_value(row, 'open')),
                    high=to_float(get_col_value(row, 'high')),
                    low=to_float(get_col_value(row, 'low')),
                    close=to_float(get_col_value(row, 'close')),
                    adj_close=adj_close,
                    volume=to_int(get_col_value(row, 'volume')),
                    source=getattr(settings, 'default_market_data_source', None) or 'yahoo_finance',
                )
            )

        rows_saved = MarketDataDailyRepository.upsert_many(rows)

        # Store fundamentals snapshot separately (provider-agnostic)
        if fundamental_data:
            try:
                import json

                db.execute_update(
                    """
                    INSERT INTO fundamentals_snapshots (stock_symbol, as_of_date, source, payload)
                    VALUES (:symbol, :as_of_date, :source, :payload)
                    ON CONFLICT (stock_symbol, as_of_date)
                    DO UPDATE SET payload = EXCLUDED.payload, source = EXCLUDED.source, updated_at = NOW()
                    """,
                    {
                        "symbol": symbol,
                        "as_of_date": datetime.now().date(),
                        "source": getattr(settings, 'default_fundamentals_source', None) or 'yahoo_finance',
                        "payload": json.dumps(fundamental_data),
                    },
                )
            except Exception as e:
                # Fundamentals are optional for price ingestion; don't fail the price pipeline.
                self.logger.warning(f"Failed to save fundamentals snapshot for {symbol} (non-critical): {e}")

        self.logger.info(f"✅ Saved {rows_saved} daily bars for {symbol}")
        return rows_saved
    
    def fetch_and_save_stock(
        self,
        symbol: str,
        period: str = "1y",
        include_fundamentals: bool = True,
        include_options: bool = True
    ) -> bool:
        """
        Fetch and save all data for a stock
        
        Returns:
            True if successful
        """
        try:
            # Fetch price data
            price_data = self.fetch_stock_data(symbol, period=period)
            if price_data is None or price_data.empty:
                return False
            
            # Fetch additional data if requested
            fundamental_data = None
            options_data = None
            
            if include_fundamentals:
                fundamental_data = self.fetch_fundamental_data(symbol)
            
            if include_options:
                options_data = self.fetch_options_data(symbol)
            
            # Save to database
            self.save_raw_market_data(symbol, price_data, fundamental_data, options_data)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error in fetch_and_save_stock for {symbol}: {e}")
            return False

