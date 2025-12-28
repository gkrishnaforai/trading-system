"""
Data Aggregation Service
Aggregates daily data to weekly/monthly timeframes for swing trading
Industry Standard: Multi-timeframe analysis for swing trading
"""
import logging
import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import datetime, date

from app.repositories.market_data_daily_repository import MarketDataDailyRepository
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.utils.exception_handler import handle_database_errors

logger = logging.getLogger(__name__)


class DataAggregationService(BaseService):
    """
    Service for aggregating daily price data to weekly/monthly timeframes
    
    Supports:
    - Weekly aggregation (for swing trading trend confirmation)
    - Monthly aggregation (for long-term analysis)
    """
    
    def __init__(self):
        """Initialize data aggregation service"""
        super().__init__()
        self.repository = MarketDataDailyRepository()
    
    def get_daily_data(self, symbol: str, days: int = 90) -> List[Dict[str, Any]]:
        """
        Get daily market data for a symbol
        
        Args:
            symbol: Stock symbol
            days: Number of days of data to retrieve
            
        Returns:
            List of daily market data records
        """
        try:
            from datetime import timedelta
            end_date = date.today()
            start_date = end_date - timedelta(days=days)
            
            # Use repository to fetch data
            data = self.repository.fetch_by_symbol(symbol)
            
            # Filter by date range
            filtered_data = []
            for record in data:
                record_date = record.get('trade_date') or record.get('date')
                if record_date and start_date <= record_date <= end_date:
                    filtered_data.append(record)
            
            return filtered_data
            
        except Exception as e:
            logger.error(f"Failed to get daily data for {symbol}: {e}")
            return []
    
    def get_indicators_data(self, symbol: str, days: int = 90) -> List[Dict[str, Any]]:
        """
        Get indicators data for a symbol
        
        Args:
            symbol: Stock symbol
            days: Number of days of data to retrieve
            
        Returns:
            List of indicators data records
        """
        try:
            from app.repositories.indicators_repository import IndicatorsRepository
            from datetime import timedelta
            
            indicators_repo = IndicatorsRepository()
            end_date = date.today()
            start_date = end_date - timedelta(days=days)
            
            # Use repository to fetch data
            data = indicators_repo.fetch_by_symbol(symbol)
            
            # Filter by date range
            filtered_data = []
            for record in data:
                record_date = record.get('trade_date') or record.get('date')
                if record_date and start_date <= record_date <= end_date:
                    filtered_data.append(record)
            
            return filtered_data
            
        except Exception as e:
            logger.error(f"Failed to get indicators data for {symbol}: {e}")
            return []
    
    def get_available_symbols(self) -> List[str]:
        """
        Get list of symbols with available data
        
        Returns:
            List of stock symbols
        """
        try:
            # Get distinct symbols from market data
            from app.database import db
            result = db.execute_query("SELECT DISTINCT stock_symbol FROM raw_market_data_daily ORDER BY stock_symbol")
            return [row['stock_symbol'] for row in result]
        except Exception as e:
            logger.error(f"Failed to get available symbols: {e}")
            return []
    
    @handle_database_errors
    def aggregate_to_weekly(self, symbol: str, force: bool = False) -> Dict[str, Any]:
        """
        Aggregate daily price data to weekly timeframe
        
        Args:
            symbol: Stock symbol
            force: Force re-aggregation even if data exists
        
        Returns:
            Dict with aggregation results
        """
        try:
            # Check if weekly data already exists
            if not force:
                existing = db.execute_query(
                    "SELECT COUNT(*) as count FROM multi_timeframe_data WHERE stock_symbol = :stock_symbol AND timeframe = 'weekly'",
                    {'stock_symbol': symbol}
                )
                if existing and existing[0]['count'] > 0:
                    logger.info(f"✅ Weekly data already exists for {symbol}, skipping aggregation")
                    return {
                        'success': True,
                        'symbol': symbol,
                        'timeframe': 'weekly',
                        'rows_created': 0,
                        'message': 'Data already exists'
                    }
            
            # Fetch daily data via repository
            daily_data = MarketDataDailyRepository.fetch_by_symbol(symbol)

            if not daily_data or len(daily_data) < 7:
                raise ValidationError(f"Insufficient daily data for {symbol}: need at least 7 days, have {len(daily_data) if daily_data else 0}")
            
            # Convert to DataFrame
            df = pd.DataFrame(daily_data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            
            # Resample to weekly (Monday to Sunday)
            weekly = df.resample('W').agg({
                'open': 'first',  # First open of the week
                'high': 'max',    # Highest high of the week
                'low': 'min',     # Lowest low of the week
                'close': 'last',  # Last close of the week
                'volume': 'sum'   # Total volume for the week
            }).dropna()
            
            # Reset index to get date as column
            weekly = weekly.reset_index()
            weekly['timeframe'] = 'weekly'
            weekly['stock_symbol'] = symbol
            
            # Insert into database
            rows_inserted = 0
            for _, row in weekly.iterrows():
                try:
                    db.execute_update(
                        """
                        INSERT OR REPLACE INTO multi_timeframe_data
                        (stock_symbol, timeframe, date, open, high, low, close, volume)
                        VALUES (:stock_symbol, :timeframe, :date, :open, :high, :low, :close, :volume)
                        """,
                        {
                            'stock_symbol': symbol,
                            'timeframe': 'weekly',
                            'date': row['date'].date(),
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'volume': int(row['volume'])
                        }
                    )
                    rows_inserted += 1
                except Exception as e:
                    logger.warning(f"Error inserting weekly data for {symbol} on {row['date']}: {e}")
            
            logger.info(f"✅ Aggregated {rows_inserted} weekly bars for {symbol}")
            
            return {
                'success': True,
                'symbol': symbol,
                'timeframe': 'weekly',
                'rows_created': rows_inserted,
                'date_range': {
                    'start': weekly['date'].min().date().isoformat() if len(weekly) > 0 else None,
                    'end': weekly['date'].max().date().isoformat() if len(weekly) > 0 else None
                }
            }
            
        except Exception as e:
            self.log_error(f"Error aggregating weekly data for {symbol}", e)
            raise DatabaseError(f"Failed to aggregate weekly data for {symbol}: {str(e)}") from e
    
    @handle_database_errors
    def aggregate_to_monthly(self, symbol: str, force: bool = False) -> Dict[str, Any]:
        """
        Aggregate daily price data to monthly timeframe
        
        Args:
            symbol: Stock symbol
            force: Force re-aggregation even if data exists
        
        Returns:
            Dict with aggregation results
        """
        try:
            # Check if monthly data already exists
            if not force:
                existing = db.execute_query(
                    "SELECT COUNT(*) as count FROM multi_timeframe_data WHERE stock_symbol = :stock_symbol AND timeframe = 'monthly'",
                    {'stock_symbol': symbol}
                )
                if existing and existing[0]['count'] > 0:
                    logger.info(f"✅ Monthly data already exists for {symbol}, skipping aggregation")
                    return {
                        'success': True,
                        'symbol': symbol,
                        'timeframe': 'monthly',
                        'rows_created': 0,
                        'message': 'Data already exists'
                    }
            
            # Fetch daily data
            daily_data = db.execute_query(
                """
                SELECT trade_date as date, open, high, low, close, volume
                FROM raw_market_data_daily
                WHERE stock_symbol = :stock_symbol
                ORDER BY trade_date ASC
                """,
                {'stock_symbol': symbol}
            )
            
            if not daily_data or len(daily_data) < 30:
                raise ValidationError(f"Insufficient daily data for {symbol}: need at least 30 days, have {len(daily_data) if daily_data else 0}")
            
            # Convert to DataFrame
            df = pd.DataFrame(daily_data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            
            # Resample to monthly
            monthly = df.resample('M').agg({
                'open': 'first',  # First open of the month
                'high': 'max',    # Highest high of the month
                'low': 'min',     # Lowest low of the month
                'close': 'last',  # Last close of the month
                'volume': 'sum'   # Total volume for the month
            }).dropna()
            
            # Reset index to get date as column
            monthly = monthly.reset_index()
            monthly['timeframe'] = 'monthly'
            monthly['stock_symbol'] = symbol
            
            # Insert into database
            rows_inserted = 0
            for _, row in monthly.iterrows():
                try:
                    db.execute_update(
                        """
                        INSERT OR REPLACE INTO multi_timeframe_data
                        (stock_symbol, timeframe, date, open, high, low, close, volume)
                        VALUES (:stock_symbol, :timeframe, :date, :open, :high, :low, :close, :volume)
                        """,
                        {
                            'stock_symbol': symbol,
                            'timeframe': 'monthly',
                            'date': row['date'].date(),
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'volume': int(row['volume'])
                        }
                    )
                    rows_inserted += 1
                except Exception as e:
                    logger.warning(f"Error inserting monthly data for {symbol} on {row['date']}: {e}")
            
            logger.info(f"✅ Aggregated {rows_inserted} monthly bars for {symbol}")
            
            return {
                'success': True,
                'symbol': symbol,
                'timeframe': 'monthly',
                'rows_created': rows_inserted,
                'date_range': {
                    'start': monthly['date'].min().date().isoformat() if len(monthly) > 0 else None,
                    'end': monthly['date'].max().date().isoformat() if len(monthly) > 0 else None
                }
            }
            
        except Exception as e:
            self.log_error(f"Error aggregating monthly data for {symbol}", e)
            raise DatabaseError(f"Failed to aggregate monthly data for {symbol}: {str(e)}") from e
    
    @handle_database_errors
    def aggregate_symbol(self, symbol: str, timeframes: List[str] = ['weekly'], force: bool = False) -> Dict[str, Any]:
        """
        Aggregate symbol to specified timeframes
        
        Args:
            symbol: Stock symbol
            timeframes: List of timeframes to aggregate ('weekly', 'monthly')
            force: Force re-aggregation
        
        Returns:
            Dict with results for each timeframe
        """
        results = {}
        
        for timeframe in timeframes:
            if timeframe == 'weekly':
                results['weekly'] = self.aggregate_to_weekly(symbol, force)
            elif timeframe == 'monthly':
                results['monthly'] = self.aggregate_to_monthly(symbol, force)
            else:
                logger.warning(f"Unknown timeframe: {timeframe}")
        
        return {
            'success': all(r.get('success', False) for r in results.values()),
            'symbol': symbol,
            'results': results
        }

