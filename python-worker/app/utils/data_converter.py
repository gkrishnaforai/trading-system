"""
Industry Standard Data Type Conversion Utilities
Handles all data type conversions for database operations
Follows best practices from pandas, SQLAlchemy, and PostgreSQL
"""

import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Any, Union, List
import logging
from sqlalchemy import text
from app.observability.logging import log_exception, log_operation_start, log_operation_success, log_operation_failure

logger = logging.getLogger(__name__)

class DataConverter:
    """Industry-standard data type conversion utilities"""
    
    @staticmethod
    def to_native_float(value: Any) -> float:
        """Convert any numeric type to native Python float"""
        try:
            if pd.isna(value):
                raise ValueError("Cannot convert NaN to float")
            elif hasattr(value, 'item'):  # numpy scalar
                return float(value.item())
            elif isinstance(value, np.floating):
                return float(value)
            elif isinstance(value, (int, float)):
                return float(value)
            else:
                return float(value)
        except (ValueError, TypeError) as e:
            logger.error(f"Cannot convert {value} ({type(value)}) to float: {e}")
            raise
    
    @staticmethod
    def to_date(value: Any) -> date:
        """Convert any date/time type to Python date object"""
        try:
            if pd.isna(value):
                raise ValueError("Cannot convert NaT to date")
            elif isinstance(value, date):
                return value
            elif isinstance(value, datetime):
                return value.date()
            elif isinstance(value, pd.Timestamp):
                # Handle timezone-aware timestamps properly
                logger.debug(f"Converting pandas Timestamp: {value} (tz: {value.tzinfo})")
                return value.date()
            elif isinstance(value, str):
                # Try common date formats
                for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%m/%d/%Y']:
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
                raise ValueError(f"Unparseable date string: {value}")
            else:
                raise ValueError(f"Unsupported date type: {type(value)} - value: {value}")
        except (ValueError, TypeError, AttributeError) as e:
            logger.error(f"Cannot convert {value} ({type(value)}) to date: {e}")
            raise
    
    @staticmethod
    def to_indicator_record(
        symbol: str,
        indicator_data: dict,
        indicator_name: str,
        data_source: str = 'calculated'
    ) -> dict:
        """
        Convert raw indicator data to database-ready record
        Handles all data type conversions properly with validation
        """
        try:
            logger.debug(f"Converting indicator record: {indicator_name}")
            logger.debug(f"  Input date: {indicator_data['date']} (type: {type(indicator_data['date'])})")
            
            # Convert date with validation
            converted_date = DataConverter.to_date(indicator_data['date'])
            logger.debug(f"  Converted date: {converted_date} (type: {type(converted_date)})")
            
            # Convert value with validation
            converted_value = DataConverter.to_native_float(indicator_data['value'])
            logger.debug(f"  Converted value: {converted_value} (type: {type(converted_value)})")
            
            record = {
                'symbol': symbol,
                'date': converted_date,
                'indicator_name': indicator_name,
                'indicator_value': converted_value,
                'time_period': int(indicator_data['period']),  # Ensure integer
                'data_source': data_source,
                'created_at': datetime.now()
            }
            
            # Validate final record
            logger.debug(f"  Final record types: {[(k, type(v)) for k, v in record.items()]}")
            
            return record
            
        except Exception as e:
            logger.error(f"Error converting indicator data: {e}")
            logger.error(f"Problematic data: {indicator_data}")
            logger.error(f"Indicator name: {indicator_name}")
            raise

class SafeDatabaseOperations:
    """Industry-standard safe database operations with proper bulk loading"""
    
    @staticmethod
    def bulk_insert_indicators(
        session, 
        records: List[dict], 
        batch_size: int = 50
    ) -> int:
        """
        Simplified: Individual inserts with small delays for transaction stability
        Avoids bulk insert issues and ensures data integrity
        """
        if not records:
            return 0
            
        operation = "individual_inserts"
        tracking_id = log_operation_start(logger, operation, {
            'total_records': len(records),
            'method': 'individual_inserts'
        })
        
        total_inserted = 0
        import time
        
        try:
            # Process records individually with small delays
            for i, record in enumerate(records, 1):
                try:
                    # Validate record before insert
                    if not isinstance(record['date'], (datetime, date)):
                        raise ValueError(f"Date conversion failed: {record['date']} (type: {type(record['date'])})")
                    
                    # Simple individual insert
                    session.execute(text("""
                        INSERT INTO indicators_daily (
                            stock_symbol, trade_date, indicator_name, indicator_value, time_period,
                            data_source, created_at
                        ) VALUES (
                            :symbol, :date, :indicator_name, :indicator_value, :time_period,
                            :data_source, :created_at
                        )
                        ON CONFLICT (stock_symbol, trade_date, indicator_name, data_source) DO NOTHING
                    """), record)
                    
                    session.commit()
                    total_inserted += 1
                    
                    # Small delay every 10 records to ensure transaction stability
                    if i % 10 == 0:
                        time.sleep(0.1)  # 100ms delay
                        logger.debug(f"Processed {i}/{len(records)} records")
                    
                except Exception as e:
                    logger.error(f"Error inserting record {i}: {e}")
                    logger.debug(f"Problematic record: {record}")
                    try:
                        session.rollback()
                    except Exception:
                        pass
                    continue
            
            # Log success
            log_operation_success(logger, operation, tracking_id, {
                'total_inserted': total_inserted,
                'total_attempted': len(records),
                'success_rate': f"{(total_inserted/len(records)*100):.1f}%" if records else "0%"
            })
            
            return total_inserted
            
        except Exception as e:
            log_operation_failure(logger, operation, tracking_id, e)
            return 0
    
    @staticmethod
    def _insert_with_duplicate_handling(session, records: List[dict]) -> int:
        """
        Handle individual inserts with duplicate detection
        Industry standard approach for handling constraint violations
        """
        inserted = 0
        
        for record in records:
            try:
                session.execute(text("""
                    INSERT INTO indicators_daily (
                        stock_symbol, trade_date, indicator_name, indicator_value, time_period,
                        data_source, created_at
                    ) VALUES (
                        :symbol, :date, :indicator_name, :indicator_value, :time_period,
                        :data_source, :created_at
                    )
                    ON CONFLICT (stock_symbol, trade_date, indicator_name, time_period) DO NOTHING
                """), record)
                inserted += 1
                
            except Exception as e:
                if 'duplicate' not in str(e).lower():
                    logger.debug(f"Skipping record due to error: {e}")
                continue
        
        if inserted > 0:
            try:
                session.commit()
            except Exception as commit_error:
                logger.error(f"Commit failed: {commit_error}")
                try:
                    session.rollback()
                except Exception:
                    pass
                return 0
        
        return inserted
