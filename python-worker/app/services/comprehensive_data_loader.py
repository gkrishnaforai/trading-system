"""
Comprehensive Data Loading Service
Uses configured data sources (Massive, Alpha Vantage, Yahoo) to load all required data
Follows proper service architecture with data source adapters
"""
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from uuid import uuid4
import pandas as pd

from app.config import settings
from app.database import db
from app.services.base import BaseService
from app.observability.logging import get_logger
from app.observability.tracing import trace_function
from app.observability import audit
from app.observability.context import get_ingestion_run_id, set_ingestion_run_id
from app.utils.technical_calculator import TechnicalIndicatorCalculator
from app.utils.data_converter import DataConverter, SafeDatabaseOperations
from sqlalchemy import text

logger = get_logger("comprehensive_data_loader")

def parse_date(date_str: str):
    """Parse date string in various formats"""
    if not date_str or date_str.lower() == 'none':
        return None
    
    try:
        # Try different date formats
        formats = ['%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%Y%m%d']
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # If none of the formats work, return None
        return None
        
    except Exception:
        return None

def parse_float(value_str: str):
    """Parse float string"""
    if not value_str or value_str.lower() in ['none', 'nan', '']:
        return None
    
    try:
        return float(value_str.replace(',', ''))
    except ValueError:
        return None

@dataclass
class LoadResult:
    """Result of data loading operation"""
    success: bool
    records_loaded: int
    data_type: str
    source: str
    message: str
    duration_seconds: float

class ComprehensiveDataLoader(BaseService):
    """
    Comprehensive data loading service
    
    Architecture:
    - Uses data source adapters (Massive, Alpha Vantage, Yahoo)
    - Loads price data, fundamentals, technical indicators, earnings
    - Follows service layer pattern
    - Centralized data loading orchestration
    """
    
    def __init__(self):
        """Initialize comprehensive data loader"""
        super().__init__()
        self.data_sources = {}
        self.technical_calculator = TechnicalIndicatorCalculator()
        self.data_sources = self._initialize_data_sources()
        logger.info("🚀 Comprehensive Data Loader initialized")
    
    def _with_audit_run(self, *, operation: str, symbol: Optional[str], fn):
        existing = get_ingestion_run_id()
        if existing is not None:
            return fn(existing)

        run_id = uuid4()
        set_ingestion_run_id(run_id)
        try:
            audit.start_run(run_id, environment=getattr(settings, "environment", None))
        except Exception:
            pass

        try:
            audit.log_event(level="info", provider="system", operation=f"{operation}.run_start", symbol=symbol)
        except Exception:
            pass

        status = "success"
        try:
            result = fn(run_id)
            return result
        except Exception as e:
            status = "failed"
            try:
                audit.log_event(level="error", provider="system", operation=f"{operation}.run_failure", symbol=symbol, exception=e)
            except Exception:
                pass
            raise
        finally:
            try:
                audit.finish_run(run_id, status=status, metadata={"operation": operation, "symbol": symbol})
            except Exception:
                pass
    
    def _initialize_data_sources(self) -> Dict[str, Any]:
        """Initialize configured data sources using adapter factory"""
        sources = {}
        
        try:
            # Use adapter factory directly like existing architecture
            from app.data_sources.adapters.factory import get_adapter_factory
            from app.config import settings
            
            # Get adapter factory
            factory = get_adapter_factory()
            
            # Initialize Massive API if available
            if settings.massive_api_key:
                try:
                    massive_adapter = factory.create_adapter('massive')
                    if massive_adapter:
                        massive_config = {
                            'api_key': settings.massive_api_key,
                            'rate_limit_calls': 4,
                            'rate_limit_window': 60.0,
                            'timeout': 30
                        }
                        if massive_adapter.initialize(massive_config):
                            sources['massive'] = massive_adapter
                            logger.info("✅ Massive data source initialized")
                        else:
                            logger.warning("⚠️  Massive adapter initialization failed")
                    else:
                        logger.warning("⚠️  Failed to create Massive adapter")
                except Exception as e:
                    logger.warning(f"⚠️  Massive adapter initialization failed: {e}")
            
            # Initialize Alpha Vantage if available
            if settings.alphavantage_api_key:
                try:
                    alphavantage_adapter = factory.create_adapter('alphavantage')
                    if alphavantage_adapter:
                        av_config = {
                            'api_key': settings.alphavantage_api_key,
                            'rate_limit_calls': 5,
                            'rate_limit_window': 60.0,
                            'timeout': 30
                        }
                        if alphavantage_adapter.initialize(av_config):
                            sources['alphavantage'] = alphavantage_adapter
                            logger.info("✅ Alpha Vantage data source initialized")
                        else:
                            logger.warning("⚠️  Alpha Vantage adapter initialization failed")
                    else:
                        logger.warning("⚠️  Failed to create Alpha Vantage adapter")
                except Exception as e:
                    logger.warning(f"⚠️  Alpha Vantage adapter initialization failed: {e}")
            
            # Initialize Yahoo Finance if available
            if settings.yahoo_finance_enabled:
                try:
                    yahoo_adapter = factory.create_adapter('yahoo')
                    if yahoo_adapter:
                        yahoo_config = {
                            'timeout': 30
                        }
                        if yahoo_adapter.initialize(yahoo_config):
                            sources['yahoo'] = yahoo_adapter
                            logger.info("✅ Yahoo Finance data source initialized")
                        else:
                            logger.warning("⚠️  Yahoo Finance adapter initialization failed")
                    else:
                        logger.warning("⚠️  Failed to create Yahoo Finance adapter")
                except Exception as e:
                    logger.warning(f"⚠️  Yahoo Finance adapter initialization failed: {e}")
            
            logger.info(f"✅ Initialized {len(sources)} data sources: {list(sources.keys())}")
            return sources
            
        except Exception as e:
            logger.error(f"❌ Error initializing data sources: {e}")
            return {}
    
    @trace_function("load_price_data")
    def load_price_data(self, symbol: str, days: int = 90, data_type: str = "daily") -> LoadResult:
        """
        Load price data for a symbol from the best available source
        
        Args:
            symbol: Stock symbol (e.g., 'NVDA')
            days: Number of days of historical data to load
            data_type: "daily" for historical data, "intraday" for current data
        
        Returns:
            LoadResult object with price data loading results
        """
        def _do(_run_id):
            return self._load_price_data(symbol, days, data_type)

        return self._with_audit_run(operation="load_price_data", symbol=symbol, fn=_do)
    
    @trace_function("load_historical_price_data")
    def load_historical_price_data(self, symbol: str, days: int = 365) -> LoadResult:
        """
        Load historical daily price data (one-time load for 20+ years of data)
        
        Args:
            symbol: Stock symbol (e.g., 'NVDA')
            days: Number of days (will use 'full' for complete history)
            
        Returns:
            LoadResult object with historical price data loading results
        """
        def _do(_run_id):
            return self._load_price_data(symbol, days, "daily")

        return self._with_audit_run(operation="load_historical_price_data", symbol=symbol, fn=_do)
    
    @trace_function("load_current_price_data")
    def load_current_price_data(self, symbol: str) -> LoadResult:
        """
        Load current intraday price data (for 5-minute updates)
        
        Args:
            symbol: Stock symbol (e.g., 'NVDA')
            
        Returns:
            LoadResult object with current intraday price data loading results
        """
        def _do(_run_id):
            return self._load_price_data(symbol, 1, "intraday")

        return self._with_audit_run(operation="load_current_price_data", symbol=symbol, fn=_do)
    
    @trace_function("load_technical_indicators")
    def load_technical_indicators(self, symbol: str, days: int = 90) -> LoadResult:
        """
        Load technical indicators for a symbol
        
        Args:
            symbol: Stock symbol (e.g., 'NVDA')
            days: Number of days of historical data to load
            
        Returns:
            LoadResult object with technical indicators loading results
        """
        def _do(_run_id):
            return self._load_technical_indicators(symbol, days)

        return self._with_audit_run(operation="load_technical_indicators", symbol=symbol, fn=_do)
    
    @trace_function("load_fundamentals")
    def load_fundamentals(self, symbol: str) -> LoadResult:
        """
        Load fundamentals data for a symbol
        
        Args:
            symbol: Stock symbol (e.g., 'NVDA')
            
        Returns:
            LoadResult object with fundamentals loading results
        """
        def _do(_run_id):
            return self._load_fundamentals_data(symbol)

        return self._with_audit_run(operation="load_fundamentals", symbol=symbol, fn=_do)
    
    @trace_function("load_symbol_data")
    def load_symbol_data(self, symbol: str, days: int = 90) -> List[LoadResult]:
        """
        Load all available data for a symbol from configured sources
        
        Args:
            symbol: Stock symbol (e.g., 'NVDA')
            days: Number of days of historical data to load
            
        Returns:
            List of LoadResult objects for each data type
        """
        def _do(_run_id):
            start_time = datetime.now()
            results = []
            
            logger.info(f"📊 Loading comprehensive data for {symbol}")
            
            try:
                price_result = self._load_price_data(symbol, days)
                results.append(price_result)
                
                fundamentals_result = self._load_fundamentals_data(symbol)
                results.append(fundamentals_result)
                
                indicators_result = self._load_technical_indicators(symbol, days)
                results.append(indicators_result)
                
                earnings_result = self._load_earnings_data(symbol)
                results.append(earnings_result)
                
                total_duration = (datetime.now() - start_time).total_seconds()
                successful_loads = sum(1 for r in results if r.success)
                
                logger.info(f"✅ Completed comprehensive data loading for {symbol}: {successful_loads}/{len(results)} successful in {total_duration:.1f}s")
                
                return results
            
            except Exception as e:
                logger.error(f"❌ Error loading comprehensive data for {symbol}: {e}")
                return [LoadResult(False, 0, "error", "system", str(e), 0)]

        return self._with_audit_run(operation="load_symbol_data", symbol=symbol, fn=_do)
    
    def _load_price_data(self, symbol: str, days: int, data_type: str = "daily") -> LoadResult:
        """Load price data from Yahoo Finance only"""
        start_time = datetime.now()
        audit.log_event(level="info", provider="yahoo", operation="load_price_data.start", symbol=symbol, context={"data_type": data_type, "days": days})
        
        if data_type == "daily":
            # Use Yahoo Finance ONLY for daily data
            if 'yahoo' in self.data_sources:
                try:
                    logger.info(f"📈 Loading daily price data for {symbol} from Yahoo Finance")
                    price_data = self.data_sources['yahoo'].fetch_price_data(symbol, days=days)
                    
                    if price_data is not None and not price_data.empty:
                        records_loaded = self._save_price_data(price_data, symbol, 'yahoo')
                        
                        # 🏭 INDUSTRY STANDARD: Auto-calculate derived indicators after price data load
                        logger.info(f"🔧 Auto-calculating derived indicators from price data...")
                        derived_indicators = self.technical_calculator.calculate_all_derived_indicators(price_data)
                        if derived_indicators:
                            derived_records = self._save_derived_indicators(derived_indicators, symbol)
                            logger.info(f"✅ Saved {derived_records} derived indicator records")
                            audit.log_event(level="info", provider="calculated", operation="derived_indicators.saved", symbol=symbol, records_in=sum(len(v) for v in derived_indicators.values()), records_saved=derived_records)
                        duration = (datetime.now() - start_time).total_seconds()
                        audit.log_event(level="info", provider="yahoo", operation="load_price_data.success", symbol=symbol, duration_ms=int(duration * 1000), records_in=len(price_data), records_saved=records_loaded)
                        return LoadResult(True, records_loaded, "price_data", "yahoo", "Success", duration)
                    
                    else:
                        duration = (datetime.now() - start_time).total_seconds()
                        audit.log_event(level="warning", provider="yahoo", operation="load_price_data.no_data", symbol=symbol, duration_ms=int(duration * 1000), context={"data_type": data_type, "days": days})
                        return LoadResult(False, 0, "price_data", "yahoo", "No price data available", duration)
                
                except Exception as e:
                    logger.error(f"❌ Yahoo Finance daily price data failed for {symbol}: {e}")
                    import traceback
                    logger.debug(f"Full traceback: {traceback.format_exc()}")
                    duration = (datetime.now() - start_time).total_seconds()
                    audit.log_event(level="error", provider="yahoo", operation="load_price_data.failure", symbol=symbol, duration_ms=int(duration * 1000), exception=e)
                    return LoadResult(False, 0, "price_data", "yahoo", str(e), duration)
            
            else:
                duration = (datetime.now() - start_time).total_seconds()
                audit.log_event(level="warning", provider="yahoo", operation="load_price_data.no_data", symbol=symbol, duration_ms=int(duration * 1000), context={"data_type": data_type, "days": days})
                return LoadResult(False, 0, "price_data", "yahoo", "No price data available", duration)
        
        elif data_type == "intraday":
            # Skip intraday for now due to Alpha Vantage rate limits
            logger.warning("⚠️  Intraday data loading disabled due to API rate limits")
            duration = (datetime.now() - start_time).total_seconds()
            audit.log_event(level="warning", provider="yahoo", operation="load_price_data.no_data", symbol=symbol, duration_ms=int(duration * 1000), context={"data_type": data_type, "days": days})
            return LoadResult(False, 0, f"{data_type}_price_data", "none", f"No {data_type} price data available", duration)
    
    def _load_fundamentals_data(self, symbol: str) -> LoadResult:
        """Load fundamentals data from Massive API"""
        start_time = datetime.now()
        audit.log_event(level="info", provider="massive", operation="load_fundamentals.start", symbol=symbol)
        
        if 'massive' not in self.data_sources:
            duration = (datetime.now() - start_time).total_seconds()
            audit.log_event(level="warning", provider="massive", operation="load_fundamentals.not_configured", symbol=symbol, duration_ms=int(duration * 1000))
            return LoadResult(False, 0, "fundamentals", "none", "Massive API not configured", duration)
        
        try:
            logger.info(f"💼 Loading fundamentals for {symbol} from Massive")
            
            # Load company overview
            overview = self.data_sources['massive'].fetch_symbol_details(symbol)
            
            # Load financial statements
            financials = self.data_sources['massive'].fetch_fundamentals(symbol)
            
            records_loaded = 0
            
            # Save company overview
            if overview:
                records_loaded += self._save_company_overview(overview, symbol)
            
            # Save financial statements
            if financials:
                records_loaded += self._save_financial_statements(financials, symbol)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if records_loaded > 0:
                audit.log_event(level="info", provider="massive", operation="load_fundamentals.success", symbol=symbol, duration_ms=int(duration * 1000), records_saved=records_loaded)
                return LoadResult(True, records_loaded, "fundamentals", "massive", "Success", duration)
            else:
                audit.log_event(level="warning", provider="massive", operation="load_fundamentals.no_data", symbol=symbol, duration_ms=int(duration * 1000))
                return LoadResult(False, 0, "fundamentals", "massive", "No fundamentals data", duration)
                
        except Exception as e:
            logger.error(f"❌ Error loading fundamentals for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            audit.log_event(level="error", provider="massive", operation="load_fundamentals.failure", symbol=symbol, duration_ms=int(duration * 1000), exception=e)
            return LoadResult(False, 0, "fundamentals", "massive", str(e), duration)
    
    def _load_technical_indicators(self, symbol: str, days: int) -> LoadResult:
        """Load technical indicators from Massive API"""
        start_time = datetime.now()
        audit.log_event(level="info", provider="massive", operation="load_vendor_indicators.start", symbol=symbol, context={"days": days})
        
        if 'massive' not in self.data_sources:
            duration = (datetime.now() - start_time).total_seconds()
            audit.log_event(level="warning", provider="massive", operation="load_vendor_indicators.not_configured", symbol=symbol, duration_ms=int(duration * 1000))
            return LoadResult(False, 0, "technical_indicators", "none", "Massive API not configured", duration)
        
        try:
            logger.info(f"📈 Loading technical indicators for {symbol} from Massive")
            
            indicators_data = self.data_sources['massive'].fetch_technical_indicators(symbol, days)
            
            if not indicators_data:
                duration = (datetime.now() - start_time).total_seconds()
                audit.log_event(level="warning", provider="massive", operation="load_vendor_indicators.no_data", symbol=symbol, duration_ms=int(duration * 1000))
                return LoadResult(False, 0, "technical_indicators", "massive", "No indicators data", duration)
            
            records_loaded = self._save_technical_indicators(indicators_data, symbol)
            duration = (datetime.now() - start_time).total_seconds()
            audit.log_event(level="info", provider="massive", operation="load_vendor_indicators.success", symbol=symbol, duration_ms=int(duration * 1000), records_saved=records_loaded)
            
            return LoadResult(True, records_loaded, "technical_indicators", "massive", "Success", duration)
                
        except Exception as e:
            logger.error(f"❌ Error loading technical indicators for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            audit.log_event(level="error", provider="massive", operation="load_vendor_indicators.failure", symbol=symbol, duration_ms=int(duration * 1000), exception=e)
            return LoadResult(False, 0, "technical_indicators", "massive", str(e), duration)
    
    def _load_earnings_data(self, symbol: str) -> LoadResult:
        """Load earnings calendar data from Alpha Vantage"""
        start_time = datetime.now()
        
        if 'alphavantage' not in self.data_sources:
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "earnings", "none", "Alpha Vantage not configured", duration)
        
        try:
            logger.info(f"📅 Loading earnings data for {symbol} from Alpha Vantage")
            
            # Use the adapter's earnings calendar method
            earnings_data = self.data_sources['alphavantage'].fetch_earnings_calendar("3month")
            
            if not earnings_data:
                duration = (datetime.now() - start_time).total_seconds()
                return LoadResult(False, 0, "earnings", "alphavantage", "No earnings data", duration)
            
            records_loaded = self._save_earnings_data(earnings_data, symbol)
            duration = (datetime.now() - start_time).total_seconds()
            
            return LoadResult(True, records_loaded, "earnings", "alphavantage", "Success", duration)
                
        except Exception as e:
            logger.error(f"❌ Error loading earnings data for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "earnings", "alphavantage", str(e), duration)
    
    def _save_intraday_data(self, price_data: pd.DataFrame, symbol: str, source: str) -> int:
        """Save intraday price data to database"""
        try:
            records = []
            
            for timestamp, row in price_data.iterrows():
                records.append({
                    'symbol': symbol,
                    'timestamp': timestamp,
                    'open_price': float(row['open']),
                    'high_price': float(row['high']),
                    'low_price': float(row['low']),
                    'close_price': float(row['close']),
                    'volume': int(row['volume']),
                    'data_source': source,
                    'created_at': datetime.now()
                })
            
            logger.info(f"💾 Saving {len(records)} intraday price records to database...")
            
            with db.get_session() as session:
                saved_count = 0
                for i, record in enumerate(records):
                    try:
                        # Try simple INSERT first, ignore duplicates
                        session.execute(text("""
                            INSERT INTO raw_market_data_intraday (
                                symbol, timestamp, open_price, high_price, low_price, close_price, volume,
                                data_source, created_at
                            ) VALUES (
                                :symbol, :timestamp, :open_price, :high_price, :low_price, :close_price, :volume,
                                :data_source, :created_at
                            )
                        """), record)
                        saved_count += 1
                        
                        # Commit every 50 records to avoid large transactions
                        if (i + 1) % 50 == 0:
                            session.commit()
                            logger.debug(f"Committed {saved_count} intraday records so far...")
                            
                    except Exception as e:
                        # Check if it's a duplicate key error and ignore it
                        if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
                            logger.debug(f"Ignoring duplicate intraday record: {record}")
                        else:
                            logger.error(f"Error saving intraday record {record}: {type(e).__name__}: {str(e)}")
                        
                        # Rollback the current transaction and start fresh
                        try:
                            session.rollback()
                        except Exception as rollback_error:
                            logger.error(f"Error during rollback: {rollback_error}")
                        continue
                
                # Final commit for any remaining records
                try:
                    session.commit()
                    logger.info(f"✅ Successfully saved {saved_count} intraday price records to database")
                except Exception as final_commit_error:
                    logger.error(f"Error during final commit: {final_commit_error}")
                    try:
                        session.rollback()
                    except Exception as rollback_error:
                        logger.error(f"Error during final rollback: {rollback_error}")
                    return 0
                
                return saved_count
                
        except Exception as e:
            logger.error(f"❌ Error saving intraday price data: {type(e).__name__}: {str(e)}")
            import traceback
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            return 0
    
    def _save_price_data(self, price_data: pd.DataFrame, symbol: str, source: str) -> int:
        """Save price data to database"""
        try:
            records = []
            
            # Debug: Check the data structure
            logger.debug(f"Price data columns: {list(price_data.columns)}")
            logger.debug(f"Price data index: {price_data.index}")
            logger.debug(f"Price data shape: {price_data.shape}")
            logger.debug(f"Sample price data:\n{price_data.head(2)}")
            
            for idx, row in price_data.iterrows():
                # Handle different date formats
                if 'date' in price_data.columns:
                    # Date is a column
                    date_val = row['date']
                elif hasattr(idx, 'date'):
                    # Index is a datetime
                    date_val = idx.date()
                elif isinstance(idx, (int, float)):
                    # Index is numeric - this is wrong, we need to debug
                    logger.error(f"❌ Date index is numeric: {idx}, row data: {row}")
                    continue
                else:
                    # Try to convert index to date
                    try:
                        date_val = pd.to_datetime(idx).date()
                    except Exception as e:
                        logger.error(f"❌ Cannot convert index {idx} to date: {e}")
                        continue
                
                records.append({
                    'symbol': symbol,
                    'date': date_val,
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume'],
                    'data_source': source,
                    'created_at': datetime.now()
                })
            
            logger.info(f"💾 Saving {len(records)} daily price records to database...")
            
            # Use proper context manager
            with db.get_session() as session:
                saved_count = 0
                for i, record in enumerate(records):
                    try:
                        # Debug: Check record before saving
                        logger.debug(f"Saving record {i+1}: {record}")
                        
                        # Try simple INSERT first, ignore duplicates
                        session.execute(text("""
                            INSERT INTO raw_market_data_daily (
                                symbol, date, open, high, low, close, volume,
                                data_source, created_at
                            ) VALUES (
                                :symbol, :date, :open, :high, :low, :close, :volume,
                                :data_source, :created_at
                            )
                        """), record)
                        saved_count += 1
                        
                        # Commit every 50 records to avoid large transactions
                        if (i + 1) % 50 == 0:
                            session.commit()
                            logger.debug(f"Committed {saved_count} daily records so far...")
                            
                    except Exception as e:
                        # Check if it's a duplicate key error and ignore it
                        if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
                            logger.debug(f"Ignoring duplicate daily record: {record}")
                        else:
                            logger.error(f"Error saving daily record {record}: {type(e).__name__}: {str(e)}")
                        
                        # Rollback the current transaction and start fresh
                        try:
                            session.rollback()
                        except Exception as rollback_error:
                            logger.error(f"Error during rollback: {rollback_error}")
                        continue
                
                # Final commit for any remaining records
                try:
                    session.commit()
                    logger.info(f"✅ Successfully saved {saved_count} daily price records to database")
                except Exception as final_commit_error:
                    logger.error(f"Error during final commit: {final_commit_error}")
                    try:
                        session.rollback()
                    except Exception as rollback_error:
                        logger.error(f"Error during final rollback: {rollback_error}")
                    return 0
                
                return saved_count
                
        except Exception as e:
            logger.error(f"❌ Error saving daily price data: {type(e).__name__}: {str(e)}")
            import traceback
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            return 0
    
    def _save_derived_indicators(self, derived_indicators: Dict[str, List[Dict[str, Any]]], symbol: str) -> int:
        """
        Industry Standard: Bulk save derived indicators with proper transaction management
        Uses PostgreSQL bulk operations for optimal performance
        """
        try:
            total_saved = 0
            
            with db.get_session() as session:
                for indicator_name, indicators in derived_indicators.items():
                    if not indicators:
                        logger.debug(f"Skipping {indicator_name}: no data")
                        continue
                        
                    logger.info(f"💾 Bulk processing {indicator_name}: {len(indicators)} records")
                    
                    # Convert all records to database format
                    db_records = []
                    for indicator_data in indicators:
                        try:
                            record = DataConverter.to_indicator_record(
                                symbol=symbol,
                                indicator_data=indicator_data,
                                indicator_name=indicator_name,
                                data_source='calculated'
                            )
                            
                            # Validate the converted record
                            if not isinstance(record['date'], (datetime, date)):
                                raise ValueError(f"Date conversion failed: {record['date']} (type: {type(record['date'])})")
                            
                            db_records.append(record)
                            
                        except Exception as e:
                            logger.error(f"Error converting {indicator_name} record: {e}")
                            logger.error(f"  Input data: {indicator_data}")
                            continue
                    
                    # Industry Standard: Bulk insert with proper transaction handling
                    if db_records:
                        try:
                            saved_count = SafeDatabaseOperations.bulk_insert_indicators(
                                session=session,
                                records=db_records,
                                batch_size=500  # Optimal batch size for PostgreSQL
                            )
                            total_saved += saved_count
                            logger.info(f"✅ Bulk saved {saved_count} {indicator_name} records")
                            
                        except Exception as e:
                            logger.error(f"❌ Bulk save failed for {indicator_name}: {e}")
                            # Continue with other indicators
                            continue
                
            logger.info(f"✅ Successfully saved {total_saved} derived indicator records")
            return total_saved
            
        except Exception as e:
            logger.error(f"❌ Error in bulk save derived indicators: {e}")
            import traceback
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            return 0
    
    def validate_signal_generation_requirements(self, symbol: str) -> Dict[str, Any]:
        """
        Industry Standard: Validate data completeness before signal generation
        Ensures we have sufficient credible data before generating signals
        """
        logger.info(f"🔍 Validating signal generation requirements for {symbol}")
        
        validation_result = self.technical_calculator.validate_signal_data_requirements(symbol)
        
        if validation_result['is_valid']:
            logger.info(f"✅ {symbol} passes signal generation validation - {validation_result['data_quality']} data quality")
        else:
            logger.warning(f"❌ {symbol} fails signal generation validation - {validation_result['data_quality']} data quality")
            missing_critical = validation_result.get('missing_critical', [])
            if missing_critical:
                logger.warning(f"   Missing critical indicators: {[m['indicator'] for m in missing_critical]}")
        
        return validation_result
    
    def _load_fundamentals_data(self, symbol: str) -> LoadResult:
        """Load fundamentals data from Massive API"""
        start_time = datetime.now()
        
        if 'massive' not in self.data_sources:
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "fundamentals", "none", "Massive API not configured", duration)
        
        try:
            logger.info(f"💼 Loading fundamentals for {symbol} from Massive")
            
            # Load company overview
            overview = self.data_sources['massive'].fetch_symbol_details(symbol)
            
            if overview:
                # Save to database
                records_loaded = self._save_fundamentals_data(overview, symbol)
                duration = (datetime.now() - start_time).total_seconds()
                
                return LoadResult(True, records_loaded, "fundamentals", "massive", "Success", duration)
            else:
                duration = (datetime.now() - start_time).total_seconds()
                return LoadResult(False, 0, "fundamentals", "massive", "No fundamentals data available", duration)
                
        except Exception as e:
            logger.error(f"❌ Error loading fundamentals data for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "fundamentals", "massive", str(e), duration)
    
    def _save_fundamentals_data(self, overview: Dict[str, Any], symbol: str) -> int:
        """Save fundamentals data to database"""
        try:
            record = {
                'symbol': symbol,
                'name': overview.get('name'),
                'sector': overview.get('sector'),
                'industry': overview.get('industry'),
                'market_cap': overview.get('market_cap'),
                'pe_ratio': overview.get('pe_ratio'),
                'eps': overview.get('eps'),
                'beta': overview.get('beta'),
                'data_source': 'massive',
                'updated_at': datetime.now()
            }
            
            with db.get_session() as session:
                try:
                    # Try to insert first
                    session.execute(text("""
                        INSERT INTO fundamentals_summary (
                            symbol, name, sector, industry, market_cap, pe_ratio, eps, beta,
                            data_source, updated_at
                        ) VALUES (
                            :symbol, :name, :sector, :industry, :market_cap, :pe_ratio, :eps, :beta,
                            :data_source, :updated_at
                        )
                    """), record)
                    session.commit()
                    logger.info(f"✅ Successfully saved fundamentals for {symbol}")
                    return 1
                    
                except Exception as insert_error:
                    # Rollback the failed transaction
                    try:
                        session.rollback()
                    except Exception:
                        pass  # Ignore rollback errors
                    
                    # Check if it's a duplicate key error
                    if "duplicate key" in str(insert_error).lower() or "unique constraint" in str(insert_error).lower():
                        logger.debug(f"Fundamentals for {symbol} already exist, updating...")
                        try:
                            # Update existing record with a fresh transaction
                            session.execute(text("""
                                UPDATE fundamentals_summary SET
                                    name = :name, sector = :sector, industry = :industry,
                                    market_cap = :market_cap, pe_ratio = :pe_ratio, eps = :eps, beta = :beta,
                                    updated_at = :updated_at
                                WHERE symbol = :symbol AND data_source = :data_source
                            """), record)
                            session.commit()
                            logger.info(f"✅ Successfully updated fundamentals for {symbol}")
                            return 1
                        except Exception as update_error:
                            logger.error(f"Error updating fundamentals for {symbol}: {update_error}")
                            try:
                                session.rollback()
                            except Exception:
                                pass
                            return 0
                    else:
                        logger.error(f"Error saving fundamentals data: {insert_error}")
                        return 0
            
        except Exception as e:
            logger.error(f"❌ Error saving fundamentals data: {e}")
            return 0
    
    def _save_financial_statements(self, financials: Dict[str, Any], symbol: str) -> int:
        """Save financial statements to database"""
        try:
            # This would need to be implemented based on the financials structure
            # For now, return 0 as placeholder
            return 0
            
        except Exception as e:
            logger.error(f"Error saving financial statements: {e}")
            return 0
    
    def _save_earnings_data(self, earnings_data: Dict[str, Any], symbol: str) -> int:
        """Save earnings calendar data to database"""
        try:
            records = []
            
            # earnings_data is in format {header: [values]}
            if 'symbol' in earnings_data and len(earnings_data['symbol']) > 0:
                for i, symbol_val in enumerate(earnings_data['symbol']):
                    if symbol_val == symbol:  # Only save records for our symbol
                        record = {
                            'symbol': symbol_val,
                            'company_name': earnings_data.get('name', [])[i] if i < len(earnings_data.get('name', [])) else None,
                            'report_date': parse_date(earnings_data.get('fiscalDateEnding', [])[i]) if i < len(earnings_data.get('fiscalDateEnding', [])) else None,
                            'estimated_eps': parse_float(earnings_data.get('estimateEPS', [])[i]) if i < len(earnings_data.get('estimateEPS', [])) else None,
                            'currency': earnings_data.get('currency', [])[i] if i < len(earnings_data.get('currency', [])) else 'USD',
                            'horizon': '3month',
                            'data_source': 'alphavantage',
                            'created_at': datetime.now()
                        }
                        records.append(record)
            
            with db.get_session() as session:
                for record in records:
                    session.execute(text("""
                        INSERT INTO earnings_calendar (
                            symbol, company_name, report_date, estimated_eps, currency,
                            horizon, data_source, created_at
                        ) VALUES (
                            :symbol, :company_name, :report_date, :estimated_eps, :currency,
                            :horizon, :data_source, :created_at
                        ) ON CONFLICT (symbol, report_date, data_source) 
                        DO UPDATE SET
                            company_name = EXCLUDED.company_name,
                            estimated_eps = EXCLUDED.estimated_eps,
                            currency = EXCLUDED.currency,
                            horizon = EXCLUDED.horizon,
                            created_at = EXCLUDED.created_at
                    """), record)
                
                session.commit()
            
            return len(records)
            
        except Exception as e:
            logger.error(f"Error saving earnings data: {e}")
            return 0
    
    def _save_technical_indicators(self, indicators_data: Dict[str, Any], symbol: str) -> int:
        """Save technical indicators to database"""
        try:
            records = []
            
            for indicator_type, data in indicators_data.items():
                logger.debug(f"Processing indicator type: {indicator_type} with {len(data) if data else 0} items")
                
                if indicator_type == 'RSI':
                    for item in data:
                        try:
                            # Handle both date objects and strings
                            if isinstance(item['date'], datetime):
                                date_value = item['date'].date()
                            elif isinstance(item['date'], date):
                                date_value = item['date']
                            elif isinstance(item['date'], str):
                                date_value = datetime.strptime(item['date'], '%Y-%m-%d').date()
                            else:
                                logger.error(f"Unsupported date type for RSI: {type(item['date'])} - value: {item['date']}")
                                continue
                            
                            # Ensure time_period is an integer
                            time_period = item['period']
                            if isinstance(time_period, str):
                                # Extract numeric part from string like "12_26_9" -> use first number
                                try:
                                    time_period = int(time_period.split('_')[0])
                                except (ValueError, IndexError):
                                    # Default to 14 for RSI if parsing fails
                                    time_period = 14
                            elif not isinstance(time_period, int):
                                time_period = 14  # Default RSI period
                            
                            records.append({
                                'symbol': symbol,
                                'date': date_value,
                                'indicator_name': 'RSI',
                                'indicator_value': item['value'],
                                'time_period': time_period,
                                'data_source': 'massive',
                                'created_at': datetime.now()
                            })
                        except Exception as e:
                            logger.error(f"Error processing RSI item {item}: {type(e).__name__}: {str(e)}")
                            continue
                
                elif indicator_type == 'MACD':
                    for item in data:
                        try:
                            # Handle both date objects and strings
                            if isinstance(item['date'], datetime):
                                date_value = item['date'].date()
                            elif isinstance(item['date'], date):
                                date_value = item['date']
                            elif isinstance(item['date'], str):
                                date_value = datetime.strptime(item['date'], '%Y-%m-%d').date()
                            else:
                                logger.error(f"Unsupported date type for MACD: {type(item['date'])} - value: {item['date']}")
                                continue
                            
                            # Ensure time_period is an integer
                            time_period = item['period']
                            if isinstance(time_period, str):
                                # Extract numeric part from string like "12_26_9" -> use first number
                                try:
                                    time_period = int(time_period.split('_')[0])
                                except (ValueError, IndexError):
                                    # Default to 12 for MACD if parsing fails
                                    time_period = 12
                            elif not isinstance(time_period, int):
                                time_period = 12  # Default MACD period
                            
                            records.append({
                                'symbol': symbol,
                                'date': date_value,
                                'indicator_name': 'MACD',
                                'indicator_value': item['value'],
                                'time_period': time_period,
                                'data_source': 'massive',
                                'created_at': datetime.now()
                            })
                        except Exception as e:
                            logger.error(f"Error processing MACD item {item}: {type(e).__name__}: {str(e)}")
                            continue
                
                elif indicator_type == 'SMA':
                    for sma_name, sma_data in data.items():
                        logger.debug(f"Processing SMA indicator: {sma_name} with {len(sma_data)} items")
                        for item in sma_data:
                            try:
                                # Handle both date objects and strings
                                if isinstance(item['date'], datetime):
                                    date_value = item['date'].date()
                                elif isinstance(item['date'], date):
                                    date_value = item['date']
                                elif isinstance(item['date'], str):
                                    date_value = datetime.strptime(item['date'], '%Y-%m-%d').date()
                                else:
                                    logger.error(f"Unsupported date type for SMA: {type(item['date'])} - value: {item['date']}")
                                    continue
                                
                                # Extract period from SMA name (e.g., "SMA_20" -> 20)
                                time_period = 20  # Default
                                if '_' in sma_name:
                                    try:
                                        time_period = int(sma_name.split('_')[1])
                                    except (ValueError, IndexError):
                                        pass
                                
                                records.append({
                                    'symbol': symbol,
                                    'date': date_value,
                                    'indicator_name': f'SMA_{time_period}',
                                    'indicator_value': item['value'],
                                    'time_period': time_period,
                                    'data_source': 'massive',
                                    'created_at': datetime.now()
                                })
                            except Exception as e:
                                logger.error(f"Error processing SMA item {item}: {type(e).__name__}: {str(e)}")
                                continue
                
                elif indicator_type == 'EMA':
                    for ema_name, ema_data in data.items():
                        logger.debug(f"Processing EMA indicator: {ema_name} with {len(ema_data)} items")
                        for item in ema_data:
                            try:
                                # Handle both date objects and strings
                                if isinstance(item['date'], datetime):
                                    date_value = item['date'].date()
                                elif isinstance(item['date'], date):
                                    date_value = item['date']
                                elif isinstance(item['date'], str):
                                    date_value = datetime.strptime(item['date'], '%Y-%m-%d').date()
                                else:
                                    logger.error(f"Unsupported date type for EMA: {type(item['date'])} - value: {item['date']}")
                                    continue
                                
                                # Extract period from EMA name (e.g., "EMA_20" -> 20)
                                time_period = 20  # Default
                                if '_' in ema_name:
                                    try:
                                        time_period = int(ema_name.split('_')[1])
                                    except (ValueError, IndexError):
                                        pass
                                
                                records.append({
                                    'symbol': symbol,
                                    'date': date_value,
                                    'indicator_name': ema_name,
                                    'indicator_value': item['value'],
                                    'time_period': time_period,
                                    'data_source': 'massive',
                                    'created_at': datetime.now()
                                })
                            except Exception as e:
                                logger.error(f"Error processing EMA item {item}: {type(e).__name__}: {str(e)}")
                                continue
                                continue
            
            logger.info(f"💾 Saving {len(records)} technical indicators to database...")
            
            if not records:
                logger.warning("⚠️  No records to save to database")
                return 0
            
            with db.get_session() as session:
                saved_count = 0
                for i, record in enumerate(records):
                    try:
                        # Try simple INSERT first, ignore duplicates
                        session.execute(text("""
                            INSERT INTO indicators_daily (
                                symbol, date, indicator_name, indicator_value, time_period,
                                data_source, created_at
                            ) VALUES (
                                :symbol, :date, :indicator_name, :indicator_value, :time_period,
                                :data_source, :created_at
                            )
                        """), record)
                        saved_count += 1
                        
                        # Commit every 10 records to avoid large transactions
                        if (i + 1) % 10 == 0:
                            session.commit()
                            logger.debug(f"Committed {saved_count} records so far...")
                            
                    except Exception as e:
                        # Check if it's a duplicate key error and ignore it
                        if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
                            logger.debug(f"Ignoring duplicate record: {record}")
                        else:
                            logger.error(f"Error saving record {record}: {type(e).__name__}: {str(e)}")
                        
                        # Rollback the current transaction and start fresh
                        try:
                            session.rollback()
                        except Exception as rollback_error:
                            logger.error(f"Error during rollback: {rollback_error}")
                        continue
                
                # Final commit for any remaining records
                try:
                    session.commit()
                    logger.info(f"✅ Successfully saved {saved_count} technical indicators to database")
                except Exception as final_commit_error:
                    logger.error(f"Error during final commit: {final_commit_error}")
                    try:
                        session.rollback()
                    except Exception as rollback_error:
                        logger.error(f"Error during final rollback: {rollback_error}")
                    return 0
                
                return saved_count
                
        except Exception as e:
            logger.error(f"❌ Error saving technical indicators: {type(e).__name__}: {str(e)}")
            import traceback
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            return 0
