"""
Data Frequency Strategies
Industry Standard: Handle different data frequencies (daily, quarterly, intraday) with appropriate duplicate prevention
"""
import logging
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, date, timedelta

from app.database import db

logger = logging.getLogger(__name__)


class DataFrequency(Enum):
    """Data frequency types"""
    INTRADAY = "intraday"  # Multiple times per day
    DAILY = "daily"  # Once per day (EOD)
    WEEKLY = "weekly"  # Once per week
    MONTHLY = "monthly"  # Once per month
    QUARTERLY = "quarterly"  # Once per quarter (earnings, fundamentals)
    YEARLY = "yearly"  # Once per year


class DuplicatePreventionStrategy:
    """
    Strategy for preventing duplicates based on data frequency
    Industry Standard: Idempotent operations, no duplicate data
    """
    
    def __init__(self, frequency: DataFrequency):
        self.frequency = frequency
    
    def should_insert(
        self,
        symbol: str,
        data_date: date,
        existing_data: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, str]:
        """
        Determine if data should be inserted based on frequency and existing data
        
        Returns:
            Tuple of (should_insert, reason)
        """
        if not existing_data:
            return True, "No existing data"
        
        existing_date = existing_data.get('date')
        if not existing_date:
            return True, "No existing date found"
        
        # Convert to date if needed
        if isinstance(existing_date, str):
            existing_date = datetime.strptime(existing_date, '%Y-%m-%d').date()
        elif isinstance(existing_date, datetime):
            existing_date = existing_date.date()
        
        days_diff = (data_date - existing_date).days
        
        if self.frequency == DataFrequency.INTRADAY:
            # Intraday: Allow multiple records per day, but check timestamp
            # For intraday, we'd need a timestamp column (not just date)
            # For now, allow if it's the same day but different time
            return True, "Intraday data allows multiple records per day"
        
        elif self.frequency == DataFrequency.DAILY:
            # Daily: Only one record per day
            if days_diff == 0:
                # Same day - check if data is newer
                existing_updated = existing_data.get('updated_at')
                if existing_updated:
                    # Allow update if new data is more recent
                    return True, "Same day - will update if newer"
                return False, "Duplicate daily record exists"
            elif days_diff > 0:
                # Newer date - allow
                return True, "Newer date"
            else:
                # Older date - don't insert
                return False, f"Data date ({data_date}) is older than existing ({existing_date})"
        
        elif self.frequency == DataFrequency.QUARTERLY:
            # Quarterly: Check if in same quarter
            existing_quarter = (existing_date.month - 1) // 3 + 1
            data_quarter = (data_date.month - 1) // 3 + 1
            
            if existing_date.year == data_date.year and existing_quarter == data_quarter:
                # Same quarter - check if newer
                if days_diff >= 0:
                    return True, "Same quarter - will update if newer"
                return False, "Duplicate quarterly record exists"
            elif data_date > existing_date:
                return True, "Newer quarter"
            else:
                return False, f"Data date ({data_date}) is older than existing ({existing_date})"
        
        elif self.frequency == DataFrequency.MONTHLY:
            # Monthly: Check if in same month
            if existing_date.year == data_date.year and existing_date.month == data_date.month:
                if days_diff >= 0:
                    return True, "Same month - will update if newer"
                return False, "Duplicate monthly record exists"
            elif data_date > existing_date:
                return True, "Newer month"
            else:
                return False, f"Data date ({data_date}) is older than existing ({existing_date})"
        
        else:
            # Default: Allow if newer
            if days_diff >= 0:
                return True, "Newer or equal date"
            return False, f"Data date ({data_date}) is older than existing ({existing_date})"
    
    def get_existing_data(self, symbol: str, data_date: date) -> Optional[Dict[str, Any]]:
        """Get existing data for symbol and date"""
        try:
            # For daily data, check exact date match
            if self.frequency == DataFrequency.DAILY:
                result = db.execute_query(
                    """
                    SELECT date, updated_at, data_source, data_frequency
                    FROM raw_market_data
                    WHERE stock_symbol = :symbol AND date = :date
                    LIMIT 1
                    """,
                    {"symbol": symbol, "date": data_date}
                )
                if result:
                    return result[0]
            
            # For quarterly, check if in same quarter
            elif self.frequency == DataFrequency.QUARTERLY:
                quarter = (data_date.month - 1) // 3 + 1
                result = db.execute_query(
                    """
                    SELECT date, updated_at, data_source, data_frequency
                    FROM raw_market_data
                    WHERE stock_symbol = :symbol 
                      AND strftime('%Y', date) = :year
                      AND ((CAST(strftime('%m', date) AS INTEGER) - 1) / 3 + 1) = :quarter
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    {
                        "symbol": symbol,
                        "year": str(data_date.year),
                        "quarter": quarter
                    }
                )
                if result:
                    return result[0]
            
            # For monthly, check if in same month
            elif self.frequency == DataFrequency.MONTHLY:
                result = db.execute_query(
                    """
                    SELECT date, updated_at, data_source, data_frequency
                    FROM raw_market_data
                    WHERE stock_symbol = :symbol 
                      AND strftime('%Y-%m', date) = :year_month
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    {
                        "symbol": symbol,
                        "year_month": data_date.strftime('%Y-%m')
                    }
                )
                if result:
                    return result[0]
            
            # Default: Check exact date
            result = db.execute_query(
                """
                SELECT date, updated_at, data_source, data_frequency
                FROM raw_market_data
                WHERE stock_symbol = :symbol AND date = :date
                LIMIT 1
                """,
                {"symbol": symbol, "date": data_date}
            )
            if result:
                return result[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking existing data for {symbol}: {e}", exc_info=True)
            return None


class IdempotentDataSaver:
    """
    Idempotent data saver that prevents duplicates
    Industry Standard: Safe to retry/re-run without creating duplicates
    """
    
    def __init__(self, frequency: DataFrequency = DataFrequency.DAILY):
        self.frequency = frequency
        self.strategy = DuplicatePreventionStrategy(frequency)
    
    def save_market_data(
        self,
        symbol: str,
        data: 'pd.DataFrame',
        data_source: str = 'yahoo_finance',
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Save market data with duplicate prevention
        
        Args:
            symbol: Stock symbol
            data: DataFrame with market data
            data_source: Data source name
            force: Force insert even if duplicate exists
        
        Returns:
            Dict with save results: {rows_inserted, rows_updated, rows_skipped, duplicates_prevented}
        """
        import pandas as pd
        
        rows_inserted = 0
        rows_updated = 0
        rows_skipped = 0
        duplicates_prevented = 0
        
        for idx, row in data.iterrows():
            # Get date from row
            date_value = row.get('date') or row.get('Date')
            if date_value is None or pd.isna(date_value):
                if isinstance(data.index, pd.DatetimeIndex):
                    date_value = data.index[data.index.get_loc(idx)]
                else:
                    continue
            
            # Convert to date
            if isinstance(date_value, pd.Timestamp):
                data_date = date_value.date()
            elif hasattr(date_value, 'date'):
                data_date = date_value.date()
            else:
                data_date = datetime.strptime(str(date_value), '%Y-%m-%d').date()
            
            # Check for existing data
            existing = self.strategy.get_existing_data(symbol, data_date)
            
            if not force and existing:
                should_insert, reason = self.strategy.should_insert(symbol, data_date, existing)
                
                if not should_insert:
                    duplicates_prevented += 1
                    rows_skipped += 1
                    logger.debug(f"⏭️ Skipped {symbol} {data_date}: {reason}")
                    continue
            
            # Insert or replace (UNIQUE constraint handles duplicates at DB level)
            try:
                # Use INSERT OR REPLACE for idempotency
                # The UNIQUE constraint on (stock_symbol, date) ensures no duplicates
                db.execute_update(
                    """
                    INSERT OR REPLACE INTO raw_market_data
                    (stock_symbol, date, open, high, low, close, volume,
                     fundamental_data, options_data, news_metadata,
                     data_source, data_frequency, updated_at)
                    VALUES (:symbol, :date, :open, :high, :low, :close, :volume,
                            :fundamental_data, :options_data, :news_metadata,
                            :data_source, :data_frequency, CURRENT_TIMESTAMP)
                    """,
                    {
                        "symbol": symbol,
                        "date": data_date,
                        "open": float(row.get('open', 0)),
                        "high": float(row.get('high', 0)),
                        "low": float(row.get('low', 0)),
                        "close": float(row.get('close', 0)),
                        "volume": int(row.get('volume', 0)),
                        "fundamental_data": None,  # Set separately if needed
                        "options_data": None,  # Set separately if needed
                        "news_metadata": None,  # Set separately if needed
                        "data_source": data_source,
                        "data_frequency": self.frequency.value
                    }
                )
                
                if existing:
                    rows_updated += 1
                else:
                    rows_inserted += 1
                    
            except Exception as e:
                # Log error and continue with next row (fail-fast on critical errors)
                logger.error(f"Error saving data for {symbol} {data_date}: {e}", exc_info=True)
                rows_skipped += 1
                # Re-raise if it's a critical error that should stop processing
                if isinstance(e, (ValueError, RuntimeError, AttributeError)):
                    raise
        
        return {
            "rows_inserted": rows_inserted,
            "rows_updated": rows_updated,
            "rows_skipped": rows_skipped,
            "duplicates_prevented": duplicates_prevented,
            "total_processed": len(data)
        }

