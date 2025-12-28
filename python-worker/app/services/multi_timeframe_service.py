"""
Multi-Timeframe Data Service
Collects and manages data across daily, weekly, monthly timeframes
Industry Standard: Multi-timeframe analysis for swing trading
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from app.database import db
from app.services.base import BaseService
from app.data_sources.base import BaseDataSource
from app.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)


class MultiTimeframeService(BaseService):
    """
    Service for managing multi-timeframe data
    
    SOLID: Single Responsibility - only handles multi-timeframe data
    DRY: Reusable aggregation logic
    """
    
    def __init__(self, data_source: Optional[BaseDataSource] = None):
        """
        Initialize multi-timeframe service
        
        Args:
            data_source: Data source (optional, will get from DI if not provided)
        """
        super().__init__()
        from app.di import get_container
        container = get_container()
        self.data_source = data_source or container.get('data_source')
        
        if self.data_source is None:
            raise ValidationError("Data source is required for MultiTimeframeService")
    
    def fetch_and_save_timeframe(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """
        Fetch and save data for a specific timeframe
        
        Args:
            symbol: Stock symbol
            timeframe: 'daily', 'weekly', or 'monthly'
            start_date: Optional start date
            end_date: Optional end date
        
        Returns:
            Number of rows saved
        
        Raises:
            ValidationError: If timeframe is invalid
            DatabaseError: If save fails
        """
        if timeframe not in ['daily', 'weekly', 'monthly']:
            raise ValidationError(f"Invalid timeframe: {timeframe}. Must be 'daily', 'weekly', or 'monthly'")
        
        if not symbol:
            raise ValidationError("Symbol is required")
        
        try:
            # Fetch daily data first (source data)
            logger.info(f"Fetching daily data for {symbol} to aggregate to {timeframe}")
            daily_data = self.data_source.fetch_historical_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )
            
            if daily_data is None or daily_data.empty:
                logger.warning(f"No daily data available for {symbol}")
                return 0
            
            # Normalize date column
            daily_data = self._normalize_dataframe(daily_data)
            
            # Aggregate to requested timeframe
            if timeframe == 'daily':
                aggregated = daily_data.copy()
            elif timeframe == 'weekly':
                aggregated = self._aggregate_to_weekly(daily_data)
            elif timeframe == 'monthly':
                aggregated = self._aggregate_to_monthly(daily_data)
            else:
                raise ValidationError(f"Unsupported timeframe: {timeframe}")
            
            if aggregated.empty:
                logger.warning(f"No data after aggregation for {symbol} {timeframe}")
                return 0
            
            # Save to database
            rows_saved = self._save_timeframe_data(symbol, timeframe, aggregated)
            logger.info(f"✅ Saved {rows_saved} rows of {timeframe} data for {symbol}")
            
            return rows_saved
            
        except Exception as e:
            logger.error(f"Error fetching and saving {timeframe} data for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to fetch and save {timeframe} data: {str(e)}") from e
    
    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize dataframe columns"""
        # Ensure date column exists
        if 'date' not in df.columns and 'Date' in df.columns:
            df = df.rename(columns={'Date': 'date'})
        
        if 'date' not in df.columns:
            if df.index.name == 'date' or df.index.name == 'Date':
                df = df.reset_index()
                if 'date' not in df.columns and 'Date' in df.columns:
                    df = df.rename(columns={'Date': 'date'})
            else:
                raise ValidationError("DataFrame must have a 'date' column")
        
        # Ensure date is datetime
        if not pd.api.types.is_datetime64_any_dtype(df['date']):
            df['date'] = pd.to_datetime(df['date'])
        
        # Ensure required columns exist
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValidationError(f"Missing required columns: {missing_cols}")
        
        # Sort by date
        df = df.sort_values('date').reset_index(drop=True)
        
        return df
    
    def _aggregate_to_weekly(self, daily_data: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate daily data to weekly
        
        Args:
            daily_data: Daily OHLCV data
        
        Returns:
            Weekly OHLCV data
        """
        if daily_data.empty:
            return pd.DataFrame()
        
        # Set date as index
        df = daily_data.set_index('date')
        
        # Resample to weekly (Monday to Friday)
        weekly = df.resample('W').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        
        # Remove NaN rows (incomplete weeks)
        weekly = weekly.dropna()
        
        # Reset index
        weekly = weekly.reset_index()
        weekly['date'] = pd.to_datetime(weekly['date'])
        
        return weekly
    
    def _aggregate_to_monthly(self, daily_data: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate daily data to monthly
        
        Args:
            daily_data: Daily OHLCV data
        
        Returns:
            Monthly OHLCV data
        """
        if daily_data.empty:
            return pd.DataFrame()
        
        # Set date as index
        df = daily_data.set_index('date')
        
        # Resample to monthly (end of month)
        monthly = df.resample('M').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        
        # Remove NaN rows
        monthly = monthly.dropna()
        
        # Reset index
        monthly = monthly.reset_index()
        monthly['date'] = pd.to_datetime(monthly['date'])
        
        return monthly
    
    def _save_timeframe_data(
        self,
        symbol: str,
        timeframe: str,
        data: pd.DataFrame
    ) -> int:
        """
        Save timeframe data to database
        
        Args:
            symbol: Stock symbol
            timeframe: Timeframe ('daily', 'weekly', 'monthly')
            data: DataFrame with OHLCV data
        
        Returns:
            Number of rows saved
        
        Raises:
            DatabaseError: If save fails
        """
        if data.empty:
            return 0
        
        rows_saved = 0
        
        try:
            for _, row in data.iterrows():
                query = """
                    INSERT OR REPLACE INTO multi_timeframe_data
                    (stock_symbol, timeframe, date, open, high, low, close, volume)
                    VALUES (:symbol, :timeframe, :date, :open, :high, :low, :close, :volume)
                """
                
                db.execute_update(query, {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "date": row['date'].date() if isinstance(row['date'], pd.Timestamp) else row['date'],
                    "open": float(row['open']) if not pd.isna(row['open']) else None,
                    "high": float(row['high']) if not pd.isna(row['high']) else None,
                    "low": float(row['low']) if not pd.isna(row['low']) else None,
                    "close": float(row['close']) if not pd.isna(row['close']) else None,
                    "volume": int(row['volume']) if not pd.isna(row['volume']) else None
                })
                rows_saved += 1
            
            return rows_saved
            
        except Exception as e:
            logger.error(f"Error saving {timeframe} data for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to save {timeframe} data: {str(e)}") from e
    
    def get_timeframe_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get timeframe data from database
        
        Args:
            symbol: Stock symbol
            timeframe: 'daily', 'weekly', or 'monthly'
            start_date: Optional start date
            end_date: Optional end date
            limit: Optional limit on number of rows
        
        Returns:
            DataFrame with OHLCV data
        
        Raises:
            ValidationError: If timeframe is invalid
            DatabaseError: If query fails
        """
        if timeframe not in ['daily', 'weekly', 'monthly']:
            raise ValidationError(f"Invalid timeframe: {timeframe}")
        
        if not symbol:
            raise ValidationError("Symbol is required")
        
        try:
            query = """
                SELECT date, open, high, low, close, volume
                FROM multi_timeframe_data
                WHERE stock_symbol = :symbol AND timeframe = :timeframe
            """
            params = {"symbol": symbol, "timeframe": timeframe}
            
            if start_date:
                query += " AND date >= :start_date"
                params["start_date"] = start_date.date() if isinstance(start_date, datetime) else start_date
            
            if end_date:
                query += " AND date <= :end_date"
                params["end_date"] = end_date.date() if isinstance(end_date, datetime) else end_date
            
            query += " ORDER BY date DESC"
            
            if limit:
                query += f" LIMIT {limit}"
            
            result = db.execute_query(query, params)
            
            if not result:
                # Fallback to raw_market_data if multi_timeframe_data is empty
                logger.warning(f"No {timeframe} data found in multi_timeframe_data for {symbol}, trying raw_market_data")
                return self._get_from_raw_market_data(symbol, timeframe, start_date, end_date, limit)
            
            df = pd.DataFrame(result)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting {timeframe} data for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get {timeframe} data: {str(e)}") from e
    
    def _get_from_raw_market_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fallback: Get data from raw_market_data and aggregate to requested timeframe
        
        Args:
            symbol: Stock symbol
            timeframe: 'daily', 'weekly', or 'monthly'
            start_date: Optional start date
            end_date: Optional end date
            limit: Optional limit on number of rows
        
        Returns:
            DataFrame with OHLCV data aggregated to requested timeframe
        """
        try:
            query = """
                SELECT date, open, high, low, close, volume
                FROM raw_market_data
                WHERE stock_symbol = :symbol
            """
            params = {"symbol": symbol}
            
            if start_date:
                query += " AND date >= :start_date"
                params["start_date"] = start_date.date() if isinstance(start_date, datetime) else start_date
            
            if end_date:
                query += " AND date <= :end_date"
                params["end_date"] = end_date.date() if isinstance(end_date, datetime) else end_date
            
            query += " ORDER BY date DESC"
            
            if limit:
                # For weekly/monthly, we need more raw data to aggregate
                multiplier = {'daily': 1, 'weekly': 7, 'monthly': 30}.get(timeframe, 1)
                query += f" LIMIT {limit * multiplier}"
            
            result = db.execute_query(query, params)
            
            if not result:
                return pd.DataFrame()
            
            df = pd.DataFrame(result)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            # Aggregate to requested timeframe
            if timeframe == 'daily':
                return df
            elif timeframe == 'weekly':
                return self._aggregate_to_weekly(df)
            elif timeframe == 'monthly':
                return self._aggregate_to_monthly(df)
            else:
                return df
                
        except Exception as e:
            logger.error(f"Error getting raw market data for {symbol}: {e}", exc_info=True)
            return pd.DataFrame()

