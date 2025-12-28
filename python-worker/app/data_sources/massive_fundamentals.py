"""
Massive.com Fundamentals Data Loader
Comprehensive financial data loading using Massive Python client
Stores all financial statements, ratios, and market data in database
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date
import pandas as pd
from sqlalchemy import text
from massive import RESTClient

from app.config import settings
from app.observability.tracing import trace_function
from app.observability.logging import get_logger
from app.database import db
from app.utils.rate_limiter import RateLimiter

logger = get_logger("massive_fundamentals")


class MassiveFundamentalsLoader:
    """Comprehensive fundamentals data loader for Massive.com"""
    
    def __init__(self):
        self.api_key = settings.massive_api_key
        if not self.api_key:
            raise ValueError("Massive API key required")
        
        self.client = RESTClient(self.api_key)
        # Conservative rate limiting for bulk operations
        self.rate_limiter = RateLimiter(2, 60)  # 2 calls per minute
        
        logger.info("✅ Massive Fundamentals Loader initialized")
    
    @trace_function("load_balance_sheets")
    def load_balance_sheets(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Load balance sheets data"""
        try:
            self.rate_limiter.acquire()
            
            balance_sheets = []
            for b in self.client.list_financials_balance_sheets(
                tickers=symbol.upper(),
                limit=str(limit),
                sort="period_end.asc"
            ):
                balance_sheets.append({
                    "symbol": symbol.upper(),
                    "period_end": getattr(b, 'period_end', None),
                    "fiscal_period": getattr(b, 'fiscal_period', None),
                    "fiscal_year": getattr(b, 'fiscal_year', None),
                    "cash_and_equivalents": getattr(b, 'cash_and_equivalents', None),
                    "short_term_investments": getattr(b, 'short_term_investments', None),
                    "cash_and_short_term_investments": getattr(b, 'cash_and_short_term_investments', None),
                    "net_receivables": getattr(b, 'net_receivables', None),
                    "inventory": getattr(b, 'inventory', None),
                    "other_current_assets": getattr(b, 'other_current_assets', None),
                    "total_current_assets": getattr(b, 'total_current_assets', None),
                    "property_plant_equipment": getattr(b, 'property_plant_equipment', None),
                    "goodwill": getattr(b, 'goodwill', None),
                    "intangibles": getattr(b, 'intangibles', None),
                    "long_term_investments": getattr(b, 'long_term_investments', None),
                    "tax_assets": getattr(b, 'tax_assets', None),
                    "other_non_current_assets": getattr(b, 'other_non_current_assets', None),
                    "total_non_current_assets": getattr(b, 'total_non_current_assets', None),
                    "total_assets": getattr(b, 'total_assets', None),
                    "accounts_payable": getattr(b, 'accounts_payable', None),
                    "short_term_debt": getattr(b, 'short_term_debt', None),
                    "tax_payables": getattr(b, 'tax_payables', None),
                    "deferred_revenue": getattr(b, 'deferred_revenue', None),
                    "other_current_liabilities": getattr(b, 'other_current_liabilities', None),
                    "total_current_liabilities": getattr(b, 'total_current_liabilities', None),
                    "long_term_debt": getattr(b, 'long_term_debt', None),
                    "deferred_revenue_non_current": getattr(b, 'deferred_revenue_non_current', None),
                    "tax_liabilities": getattr(b, 'tax_liabilities', None),
                    "other_non_current_liabilities": getattr(b, 'other_non_current_liabilities', None),
                    "total_non_current_liabilities": getattr(b, 'total_non_current_liabilities', None),
                    "total_liabilities": getattr(b, 'total_liabilities', None),
                    "shareholders_equity": getattr(b, 'shareholders_equity', None),
                    "common_stock": getattr(b, 'common_stock', None),
                    "retained_earnings": getattr(b, 'retained_earnings', None),
                    "accumulated_other_comprehensive_income": getattr(b, 'accumulated_other_comprehensive_income', None),
                    "other_shareholder_equity": getattr(b, 'other_shareholder_equity', None),
                    "total_liabilities_and_shareholders_equity": getattr(b, 'total_liabilities_and_shareholders_equity', None),
                    "source": "massive",
                    "loaded_at": datetime.utcnow()
                })
            
            logger.info(f"✅ Loaded {len(balance_sheets)} balance sheets for {symbol}")
            return balance_sheets
            
        except Exception as e:
            logger.error(f"Error loading balance sheets for {symbol}: {e}")
            return []
    
    @trace_function("load_cash_flow_statements")
    def load_cash_flow_statements(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Load cash flow statements data"""
        try:
            self.rate_limiter.acquire()
            
            cash_flow_statements = []
            for c in self.client.list_financials_cash_flow_statements(
                tickers=symbol.upper(),
                limit=str(limit),
                sort="period_end.asc"
            ):
                cash_flow_statements.append({
                    "symbol": symbol.upper(),
                    "period_end": getattr(c, 'period_end', None),
                    "fiscal_period": getattr(c, 'fiscal_period', None),
                    "fiscal_year": getattr(c, 'fiscal_year', None),
                    "net_income": getattr(c, 'net_income', None),
                    "depreciation_amortization": getattr(c, 'depreciation_amortization', None),
                    "deferred_income_tax": getattr(c, 'deferred_income_tax', None),
                    "stock_based_compensation": getattr(c, 'stock_based_compensation', None),
                    "change_in_working_capital": getattr(c, 'change_in_working_capital', None),
                    "accounts_receivables": getattr(c, 'accounts_receivables', None),
                    "inventory": getattr(c, 'inventory', None),
                    "accounts_payables": getattr(c, 'accounts_payables', None),
                    "other_working_capital": getattr(c, 'other_working_capital', None),
                    "other_non_cash_items": getattr(c, 'other_non_cash_items', None),
                    "net_cash_from_operating_activities": getattr(c, 'net_cash_from_operating_activities', None),
                    "investments_in_property_plant_equipment": getattr(c, 'investments_in_property_plant_equipment', None),
                    "acquisitions_net": getattr(c, 'acquisitions_net', None),
                    "purchases_of_investments": getattr(c, 'purchases_of_investments', None),
                    "sales_maturities_of_investments": getattr(c, 'sales_maturities_of_investments', None),
                    "other_investing_activities": getattr(c, 'other_investing_activities', None),
                    "net_cash_from_investing_activities": getattr(c, 'net_cash_from_investing_activities', None),
                    "debt_repayment": getattr(c, 'debt_repayment', None),
                    "common_stock_issued": getattr(c, 'common_stock_issued', None),
                    "common_stock_repurchased": getattr(c, 'common_stock_repurchased', None),
                    "dividends_paid": getattr(c, 'dividends_paid', None),
                    "other_financing_activities": getattr(c, 'other_financing_activities', None),
                    "net_cash_from_financing_activities": getattr(c, 'net_cash_from_financing_activities', None),
                    "net_change_in_cash": getattr(c, 'net_change_in_cash', None),
                    "cash_at_end_of_period": getattr(c, 'cash_at_end_of_period', None),
                    "cash_at_beginning_of_period": getattr(c, 'cash_at_beginning_of_period', None),
                    "operating_cash_flow": getattr(c, 'operating_cash_flow', None),
                    "capital_expenditure": getattr(c, 'capital_expenditure', None),
                    "free_cash_flow": getattr(c, 'free_cash_flow', None),
                    "source": "massive",
                    "loaded_at": datetime.utcnow()
                })
            
            logger.info(f"✅ Loaded {len(cash_flow_statements)} cash flow statements for {symbol}")
            return cash_flow_statements
            
        except Exception as e:
            logger.error(f"Error loading cash flow statements for {symbol}: {e}")
            return []
    
    @trace_function("load_income_statements")
    def load_income_statements(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Load income statements data"""
        try:
            self.rate_limiter.acquire()
            
            income_statements = []
            for i in self.client.list_financials_income_statements(
                tickers=symbol.upper(),
                limit=str(limit),
                sort="period_end.asc"
            ):
                income_statements.append({
                    "symbol": symbol.upper(),
                    "period_end": getattr(i, 'period_end', None),
                    "fiscal_period": getattr(i, 'fiscal_period', None),
                    "fiscal_year": getattr(i, 'fiscal_year', None),
                    "revenues": getattr(i, 'revenues', None),
                    "revenue_growth": getattr(i, 'revenue_growth', None),
                    "cost_of_revenue": getattr(i, 'cost_of_revenue', None),
                    "gross_profit": getattr(i, 'gross_profit', None),
                    "gross_profit_growth": getattr(i, 'gross_profit_growth', None),
                    "research_and_development": getattr(i, 'research_and_development', None),
                    "sga_expenses": getattr(i, 'sga_expenses', None),
                    "operating_expenses": getattr(i, 'operating_expenses', None),
                    "operating_income": getattr(i, 'operating_income', None),
                    "operating_income_growth": getattr(i, 'operating_income_growth', None),
                    "interest_income": getattr(i, 'interest_income', None),
                    "interest_expense": getattr(i, 'interest_expense', None),
                    "other_income_expense": getattr(i, 'other_income_expense', None),
                    "income_before_tax": getattr(i, 'income_before_tax', None),
                    "income_before_tax_growth": getattr(i, 'income_before_tax_growth', None),
                    "income_tax_expense": getattr(i, 'income_tax_expense', None),
                    "net_income": getattr(i, 'net_income', None),
                    "net_income_growth": getattr(i, 'net_income_growth', None),
                    "earnings_per_share_basic": getattr(i, 'earnings_per_share_basic', None),
                    "earnings_per_share_diluted": getattr(i, 'earnings_per_share_diluted', None),
                    "weighted_average_shares_outstanding_basic": getattr(i, 'weighted_average_shares_outstanding_basic', None),
                    "weighted_average_shares_outstanding_diluted": getattr(i, 'weighted_average_shares_outstanding_diluted', None),
                    "ebitda": getattr(i, 'ebitda', None),
                    "ebitda_growth": getattr(i, 'ebitda_growth', None),
                    "operating_margin": getattr(i, 'operating_margin', None),
                    "gross_margin": getattr(i, 'gross_margin', None),
                    "net_profit_margin": getattr(i, 'net_profit_margin', None),
                    "source": "massive",
                    "loaded_at": datetime.utcnow()
                })
            
            logger.info(f"✅ Loaded {len(income_statements)} income statements for {symbol}")
            return income_statements
            
        except Exception as e:
            logger.error(f"Error loading income statements for {symbol}: {e}")
            return []
    
    @trace_function("load_financial_ratios")
    def load_financial_ratios(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Load financial ratios data"""
        try:
            self.rate_limiter.acquire()
            
            ratios = []
            for r in self.client.list_financials_ratios(
                tickers=symbol.upper(),
                limit=str(limit),
                sort="ticker.asc"
            ):
                ratios.append({
                    "symbol": symbol.upper(),
                    "period_end": getattr(r, 'period_end', None),
                    "fiscal_period": getattr(r, 'fiscal_period', None),
                    "fiscal_year": getattr(r, 'fiscal_year', None),
                    "current_ratio": getattr(r, 'current_ratio', None),
                    "quick_ratio": getattr(r, 'quick_ratio', None),
                    "cash_ratio": getattr(r, 'cash_ratio', None),
                    "debt_to_equity_ratio": getattr(r, 'debt_to_equity_ratio', None),
                    "debt_to_assets_ratio": getattr(r, 'debt_to_assets_ratio', None),
                    "long_term_debt_to_equity_ratio": getattr(r, 'long_term_debt_to_equity_ratio', None),
                    "total_debt_to_capital": getattr(r, 'total_debt_to_capital', None),
                    "interest_coverage_ratio": getattr(r, 'interest_coverage_ratio', None),
                    "cash_flow_to_debt_ratio": getattr(r, 'cash_flow_to_debt_ratio', None),
                    "return_on_assets": getattr(r, 'return_on_assets', None),
                    "return_on_equity": getattr(r, 'return_on_equity', None),
                    "return_on_capital": getattr(r, 'return_on_capital', None),
                    "gross_profit_margin": getattr(r, 'gross_profit_margin', None),
                    "operating_profit_margin": getattr(r, 'operating_profit_margin', None),
                    "net_profit_margin": getattr(r, 'net_profit_margin', None),
                    "asset_turnover": getattr(r, 'asset_turnover', None),
                    "inventory_turnover": getattr(r, 'inventory_turnover', None),
                    "receivables_turnover": getattr(r, 'receivables_turnover', None),
                    "payables_turnover": getattr(r, 'payables_turnover', None),
                    "days_sales_outstanding": getattr(r, 'days_sales_outstanding', None),
                    "days_inventory": getattr(r, 'days_inventory', None),
                    "days_payables_outstanding": getattr(r, 'days_payables_outstanding', None),
                    "cash_conversion_cycle": getattr(r, 'cash_conversion_cycle', None),
                    "source": "massive",
                    "loaded_at": datetime.utcnow()
                })
            
            logger.info(f"✅ Loaded {len(ratios)} financial ratios for {symbol}")
            return ratios
            
        except Exception as e:
            logger.error(f"Error loading financial ratios for {symbol}: {e}")
            return []
    
    @trace_function("load_short_interest")
    def load_short_interest(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Load short interest data"""
        try:
            self.rate_limiter.acquire()
            
            items = []
            for item in self.client.list_short_interest(
                tickers=symbol.upper(),
                limit=limit,
                sort="ticker.asc",
            ):
                items.append({
                    "symbol": symbol.upper(),
                    "settlement_date": getattr(item, 'settlement_date', None),
                    "short_interest": getattr(item, 'short_interest', None),
                    "short_interest_percent": getattr(item, 'short_interest_percent', None),
                    "days_to_cover": getattr(item, 'days_to_cover', None),
                    "source": "massive",
                    "loaded_at": datetime.utcnow()
                })
            
            logger.info(f"✅ Loaded {len(items)} short interest records for {symbol}")
            return items
            
        except Exception as e:
            logger.error(f"Error loading short interest for {symbol}: {e}")
            return []
    
    @trace_function("load_short_volume")
    def load_short_volume(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Load short volume data"""
        try:
            self.rate_limiter.acquire()
            
            items = []
            for item in self.client.list_short_volume(
                tickers=symbol.upper(),
                limit=limit,
                sort="ticker.asc",
            ):
                items.append({
                    "symbol": symbol.upper(),
                    "trading_date": getattr(item, 'trading_date', None),
                    "short_volume": getattr(item, 'short_volume', None),
                    "short_volume_percent": getattr(item, 'short_volume_percent', None),
                    "total_volume": getattr(item, 'total_volume', None),
                    "source": "massive",
                    "loaded_at": datetime.utcnow()
                })
            
            logger.info(f"✅ Loaded {len(items)} short volume records for {symbol}")
            return items
            
        except Exception as e:
            logger.error(f"Error loading short volume for {symbol}: {e}")
            return []
    
    @trace_function("load_rsi")
    def load_rsi(self, symbol: str, timespan: str = "day", window: str = "14", limit: str = "10") -> List[Dict[str, Any]]:
        """Load RSI technical indicator"""
        try:
            self.rate_limiter.acquire()
            
            rsi_data = self.client.get_rsi(
                ticker=symbol.upper(),
                timespan=timespan,
                adjusted="true",
                window=window,
                series_type="close",
                order="desc",
                limit=limit,
            )
            
            indicators = []
            # Handle single object result
            if hasattr(rsi_data, 'values') and rsi_data.values:
                for item in rsi_data.values:
                    # Convert Unix timestamp to datetime
                    timestamp = getattr(item, 'timestamp', None)
                    if timestamp and isinstance(timestamp, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp / 1000)  # Convert from milliseconds
                    
                    indicators.append({
                        "symbol": symbol.upper(),
                        "indicator_type": "RSI",
                        "timestamp": timestamp,
                        "value": getattr(item, 'value', None),
                        "window": int(window),
                        "timespan": timespan,
                        "series_type": "close",
                        "source": "massive",
                        "loaded_at": datetime.utcnow()
                    })
            elif hasattr(rsi_data, '__iter__'):
                # Handle iterable result
                for item in rsi_data:
                    # Convert Unix timestamp to datetime
                    timestamp = getattr(item, 'timestamp', None)
                    if timestamp and isinstance(timestamp, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp / 1000)  # Convert from milliseconds
                    
                    indicators.append({
                        "symbol": symbol.upper(),
                        "indicator_type": "RSI",
                        "timestamp": timestamp,
                        "value": getattr(item, 'value', None),
                        "window": int(window),
                        "timespan": timespan,
                        "series_type": "close",
                        "source": "massive",
                        "loaded_at": datetime.utcnow()
                    })
            
            logger.info(f"✅ Loaded {len(indicators)} RSI values for {symbol}")
            return indicators
            
        except Exception as e:
            logger.error(f"Error loading RSI for {symbol}: {e}")
            return []
    
    @trace_function("load_macd")
    def load_macd(self, symbol: str, timespan: str = "day", short_window: str = "12", long_window: str = "26", signal_window: str = "9", limit: str = "10") -> List[Dict[str, Any]]:
        """Load MACD technical indicator"""
        try:
            self.rate_limiter.acquire()
            
            macd_data = self.client.get_macd(
                ticker=symbol.upper(),
                timespan=timespan,
                adjusted="true",
                short_window=short_window,
                long_window=long_window,
                signal_window=signal_window,
                series_type="close",
                order="desc",
                limit=limit,
            )
            
            indicators = []
            # Handle single object result
            if hasattr(macd_data, 'values') and macd_data.values:
                for item in macd_data.values:
                    # Convert Unix timestamp to datetime
                    timestamp = getattr(item, 'timestamp', None)
                    if timestamp and isinstance(timestamp, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp / 1000)  # Convert from milliseconds
                    
                    indicators.append({
                        "symbol": symbol.upper(),
                        "indicator_type": "MACD",
                        "timestamp": timestamp,
                        "macd_value": getattr(item, 'value', None),
                        "signal_value": getattr(item, 'signal', None),
                        "histogram_value": getattr(item, 'histogram', None),
                        "short_window": int(short_window),
                        "long_window": int(long_window),
                        "signal_window": int(signal_window),
                        "timespan": timespan,
                        "series_type": "close",
                        "source": "massive",
                        "loaded_at": datetime.utcnow()
                    })
            elif hasattr(macd_data, '__iter__'):
                # Handle iterable result
                for item in macd_data:
                    # Convert Unix timestamp to datetime
                    timestamp = getattr(item, 'timestamp', None)
                    if timestamp and isinstance(timestamp, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp / 1000)  # Convert from milliseconds
                    
                    indicators.append({
                        "symbol": symbol.upper(),
                        "indicator_type": "MACD",
                        "timestamp": timestamp,
                        "macd_value": getattr(item, 'value', None),
                        "signal_value": getattr(item, 'signal', None),
                        "histogram_value": getattr(item, 'histogram', None),
                        "short_window": int(short_window),
                        "long_window": int(long_window),
                        "signal_window": int(signal_window),
                        "timespan": timespan,
                        "series_type": "close",
                        "source": "massive",
                        "loaded_at": datetime.utcnow()
                    })
            
            logger.info(f"✅ Loaded {len(indicators)} MACD values for {symbol}")
            return indicators
            
        except Exception as e:
            logger.error(f"Error loading MACD for {symbol}: {e}")
            return []
    
    @trace_function("load_ema")
    def load_ema(self, symbol: str, timespan: str = "day", window: str = "50", limit: str = "10") -> List[Dict[str, Any]]:
        """Load EMA technical indicator"""
        try:
            self.rate_limiter.acquire()
            
            ema_data = self.client.get_ema(
                ticker=symbol.upper(),
                timespan=timespan,
                adjusted="true",
                window=window,
                series_type="close",
                order="desc",
                limit=limit,
            )
            
            indicators = []
            # Handle single object result
            if hasattr(ema_data, 'values') and ema_data.values:
                for item in ema_data.values:
                    # Convert Unix timestamp to datetime
                    timestamp = getattr(item, 'timestamp', None)
                    if timestamp and isinstance(timestamp, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp / 1000)  # Convert from milliseconds
                    
                    indicators.append({
                        "symbol": symbol.upper(),
                        "indicator_type": "EMA",
                        "timestamp": timestamp,
                        "value": getattr(item, 'value', None),
                        "window": int(window),
                        "timespan": timespan,
                        "series_type": "close",
                        "source": "massive",
                        "loaded_at": datetime.utcnow()
                    })
            elif hasattr(ema_data, '__iter__'):
                # Handle iterable result
                for item in ema_data:
                    # Convert Unix timestamp to datetime
                    timestamp = getattr(item, 'timestamp', None)
                    if timestamp and isinstance(timestamp, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp / 1000)  # Convert from milliseconds
                    
                    indicators.append({
                        "symbol": symbol.upper(),
                        "indicator_type": "EMA",
                        "timestamp": timestamp,
                        "value": getattr(item, 'value', None),
                        "window": int(window),
                        "timespan": timespan,
                        "series_type": "close",
                        "source": "massive",
                        "loaded_at": datetime.utcnow()
                    })
            
            logger.info(f"✅ Loaded {len(indicators)} EMA values for {symbol}")
            return indicators
            
        except Exception as e:
            logger.error(f"Error loading EMA for {symbol}: {e}")
            return []
    
    @trace_function("load_sma")
    def load_sma(self, symbol: str, timespan: str = "day", window: str = "50", limit: str = "10") -> List[Dict[str, Any]]:
        """Load SMA technical indicator"""
        try:
            self.rate_limiter.acquire()
            
            sma_data = self.client.get_sma(
                ticker=symbol.upper(),
                timespan=timespan,
                adjusted="true",
                window=window,
                series_type="close",
                order="desc",
                limit=limit,
            )
            
            indicators = []
            # Handle single object result
            if hasattr(sma_data, 'values') and sma_data.values:
                for item in sma_data.values:
                    # Convert Unix timestamp to datetime
                    timestamp = getattr(item, 'timestamp', None)
                    if timestamp and isinstance(timestamp, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp / 1000)  # Convert from milliseconds
                    
                    indicators.append({
                        "symbol": symbol.upper(),
                        "indicator_type": "SMA",
                        "timestamp": timestamp,
                        "value": getattr(item, 'value', None),
                        "window": int(window),
                        "timespan": timespan,
                        "series_type": "close",
                        "source": "massive",
                        "loaded_at": datetime.utcnow()
                    })
            elif hasattr(sma_data, '__iter__'):
                # Handle iterable result
                for item in sma_data:
                    # Convert Unix timestamp to datetime
                    timestamp = getattr(item, 'timestamp', None)
                    if timestamp and isinstance(timestamp, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp / 1000)  # Convert from milliseconds
                    
                    indicators.append({
                        "symbol": symbol.upper(),
                        "indicator_type": "SMA",
                        "timestamp": timestamp,
                        "value": getattr(item, 'value', None),
                        "window": int(window),
                        "timespan": timespan,
                        "series_type": "close",
                        "source": "massive",
                        "loaded_at": datetime.utcnow()
                    })
            
            logger.info(f"✅ Loaded {len(indicators)} SMA values for {symbol}")
            return indicators
            
        except Exception as e:
            logger.error(f"Error loading SMA for {symbol}: {e}")
            return []
    
    @trace_function("create_fundamentals_tables")
    def create_fundamentals_tables(self):
        """Create database tables for fundamentals data"""
        try:
            # Initialize database if needed
            if db.session_factory is None:
                logger.info("Initializing database connection...")
                db.initialize()
            
            # Double-check after initialization
            if db.session_factory is None:
                logger.error("Database session factory still not initialized after initialize() call")
                raise RuntimeError("Database not properly initialized")
            
            with db.get_session() as session:
                # Create balance sheets table
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS massive_balance_sheets (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        period_end DATE,
                        fiscal_period VARCHAR(20),
                        fiscal_year INTEGER,
                        cash_and_equivalents DECIMAL(20,2),
                        short_term_investments DECIMAL(20,2),
                        cash_and_short_term_investments DECIMAL(20,2),
                        net_receivables DECIMAL(20,2),
                        inventory DECIMAL(20,2),
                        other_current_assets DECIMAL(20,2),
                        total_current_assets DECIMAL(20,2),
                        property_plant_equipment DECIMAL(20,2),
                        goodwill DECIMAL(20,2),
                        intangibles DECIMAL(20,2),
                        long_term_investments DECIMAL(20,2),
                        tax_assets DECIMAL(20,2),
                        other_non_current_assets DECIMAL(20,2),
                        total_non_current_assets DECIMAL(20,2),
                        total_assets DECIMAL(20,2),
                        accounts_payable DECIMAL(20,2),
                        short_term_debt DECIMAL(20,2),
                        tax_payables DECIMAL(20,2),
                        deferred_revenue DECIMAL(20,2),
                        other_current_liabilities DECIMAL(20,2),
                        total_current_liabilities DECIMAL(20,2),
                        long_term_debt DECIMAL(20,2),
                        deferred_revenue_non_current DECIMAL(20,2),
                        tax_liabilities DECIMAL(20,2),
                        other_non_current_liabilities DECIMAL(20,2),
                        total_non_current_liabilities DECIMAL(20,2),
                        total_liabilities DECIMAL(20,2),
                        shareholders_equity DECIMAL(20,2),
                        common_stock DECIMAL(20,2),
                        retained_earnings DECIMAL(20,2),
                        accumulated_other_comprehensive_income DECIMAL(20,2),
                        other_shareholder_equity DECIMAL(20,2),
                        total_liabilities_and_shareholders_equity DECIMAL(20,2),
                        source VARCHAR(20) DEFAULT 'massive',
                        loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, period_end, fiscal_period)
                    )
                """))
                
                # Create cash flow statements table
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS massive_cash_flow_statements (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        period_end DATE,
                        fiscal_period VARCHAR(20),
                        fiscal_year INTEGER,
                        net_income DECIMAL(20,2),
                        depreciation_amortization DECIMAL(20,2),
                        deferred_income_tax DECIMAL(20,2),
                        stock_based_compensation DECIMAL(20,2),
                        change_in_working_capital DECIMAL(20,2),
                        accounts_receivables DECIMAL(20,2),
                        inventory DECIMAL(20,2),
                        accounts_payables DECIMAL(20,2),
                        other_working_capital DECIMAL(20,2),
                        other_non_cash_items DECIMAL(20,2),
                        net_cash_from_operating_activities DECIMAL(20,2),
                        investments_in_property_plant_equipment DECIMAL(20,2),
                        acquisitions_net DECIMAL(20,2),
                        purchases_of_investments DECIMAL(20,2),
                        sales_maturities_of_investments DECIMAL(20,2),
                        other_investing_activities DECIMAL(20,2),
                        net_cash_from_investing_activities DECIMAL(20,2),
                        debt_repayment DECIMAL(20,2),
                        common_stock_issued DECIMAL(20,2),
                        common_stock_repurchased DECIMAL(20,2),
                        dividends_paid DECIMAL(20,2),
                        other_financing_activities DECIMAL(20,2),
                        net_cash_from_financing_activities DECIMAL(20,2),
                        net_change_in_cash DECIMAL(20,2),
                        cash_at_end_of_period DECIMAL(20,2),
                        cash_at_beginning_of_period DECIMAL(20,2),
                        operating_cash_flow DECIMAL(20,2),
                        capital_expenditure DECIMAL(20,2),
                        free_cash_flow DECIMAL(20,2),
                        source VARCHAR(20) DEFAULT 'massive',
                        loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, period_end, fiscal_period)
                    )
                """))
                
                # Create income statements table
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS massive_income_statements (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        period_end DATE,
                        fiscal_period VARCHAR(20),
                        fiscal_year INTEGER,
                        revenues DECIMAL(20,2),
                        revenue_growth DECIMAL(10,4),
                        cost_of_revenue DECIMAL(20,2),
                        gross_profit DECIMAL(20,2),
                        gross_profit_growth DECIMAL(10,4),
                        research_and_development DECIMAL(20,2),
                        sga_expenses DECIMAL(20,2),
                        operating_expenses DECIMAL(20,2),
                        operating_income DECIMAL(20,2),
                        operating_income_growth DECIMAL(10,4),
                        interest_income DECIMAL(20,2),
                        interest_expense DECIMAL(20,2),
                        other_income_expense DECIMAL(20,2),
                        income_before_tax DECIMAL(20,2),
                        income_before_tax_growth DECIMAL(10,4),
                        income_tax_expense DECIMAL(20,2),
                        net_income DECIMAL(20,2),
                        net_income_growth DECIMAL(10,4),
                        earnings_per_share_basic DECIMAL(10,4),
                        earnings_per_share_diluted DECIMAL(10,4),
                        weighted_average_shares_outstanding_basic DECIMAL(20,2),
                        weighted_average_shares_outstanding_diluted DECIMAL(20,2),
                        ebitda DECIMAL(20,2),
                        ebitda_growth DECIMAL(10,4),
                        operating_margin DECIMAL(10,4),
                        gross_margin DECIMAL(10,4),
                        net_profit_margin DECIMAL(10,4),
                        source VARCHAR(20) DEFAULT 'massive',
                        loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, period_end, fiscal_period)
                    )
                """))
                
                # Create financial ratios table
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS massive_financial_ratios (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        period_end DATE,
                        fiscal_period VARCHAR(20),
                        fiscal_year INTEGER,
                        current_ratio DECIMAL(10,4),
                        quick_ratio DECIMAL(10,4),
                        cash_ratio DECIMAL(10,4),
                        debt_to_equity_ratio DECIMAL(10,4),
                        debt_to_assets_ratio DECIMAL(10,4),
                        long_term_debt_to_equity_ratio DECIMAL(10,4),
                        total_debt_to_capital DECIMAL(10,4),
                        interest_coverage_ratio DECIMAL(10,4),
                        cash_flow_to_debt_ratio DECIMAL(10,4),
                        return_on_assets DECIMAL(10,4),
                        return_on_equity DECIMAL(10,4),
                        return_on_capital DECIMAL(10,4),
                        gross_profit_margin DECIMAL(10,4),
                        operating_profit_margin DECIMAL(10,4),
                        net_profit_margin DECIMAL(10,4),
                        asset_turnover DECIMAL(10,4),
                        inventory_turnover DECIMAL(10,4),
                        receivables_turnover DECIMAL(10,4),
                        payables_turnover DECIMAL(10,4),
                        days_sales_outstanding DECIMAL(10,2),
                        days_inventory DECIMAL(10,2),
                        days_payables_outstanding DECIMAL(10,2),
                        cash_conversion_cycle DECIMAL(10,2),
                        source VARCHAR(20) DEFAULT 'massive',
                        loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, period_end, fiscal_period)
                    )
                """))
                
                # Create short interest table
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS massive_short_interest (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        settlement_date DATE,
                        short_interest BIGINT,
                        short_interest_percent DECIMAL(10,4),
                        days_to_cover DECIMAL(10,2),
                        source VARCHAR(20) DEFAULT 'massive',
                        loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, settlement_date)
                    )
                """))
                
                # Create short volume table
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS massive_short_volume (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        trading_date DATE,
                        short_volume BIGINT,
                        short_volume_percent DECIMAL(10,4),
                        total_volume BIGINT,
                        source VARCHAR(20) DEFAULT 'massive',
                        loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, trading_date)
                    )
                """))
                
                # Create technical indicators table
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS massive_technical_indicators (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        indicator_type VARCHAR(20) NOT NULL,
                        timestamp TIMESTAMP,
                        value DECIMAL(20,8),
                        macd_value DECIMAL(20,8),
                        signal_value DECIMAL(20,8),
                        histogram_value DECIMAL(20,8),
                        "window" INTEGER,
                        short_window INTEGER,
                        long_window INTEGER,
                        signal_window INTEGER,
                        timespan VARCHAR(20),
                        series_type VARCHAR(20),
                        source VARCHAR(20) DEFAULT 'massive',
                        loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, indicator_type, timestamp, "window", short_window, long_window, signal_window)
                    )
                """))
                
                session.commit()
                logger.info("✅ Created all fundamentals database tables")
                
        except Exception as e:
            logger.error(f"Error creating fundamentals tables: {e}")
            raise
    
    @trace_function("save_to_database")
    def save_to_database(self, table_name: str, data: List[Dict[str, Any]]):
        """Save data to database with upsert"""
        if not data:
            return
        
        try:
            # Initialize database if needed
            if db.session_factory is None:
                logger.info("Initializing database connection...")
                db.initialize()
            
            # Double-check after initialization
            if db.session_factory is None:
                logger.error("Database session factory still not initialized after initialize() call")
                raise RuntimeError("Database not properly initialized")
            
            with db.get_session() as session:
                # Convert to DataFrame for easier handling
                df = pd.DataFrame(data)
                
                # Generate upsert SQL based on table
                if table_name == "massive_balance_sheets":
                    columns = [col for col in df.columns if col not in ['source', 'loaded_at']]
                    placeholders = ", ".join([f":{col}" for col in columns])
                    update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns])
                    
                    sql = f"""
                        INSERT INTO massive_balance_sheets ({", ".join(columns)})
                        VALUES ({placeholders})
                        ON CONFLICT (symbol, period_end, fiscal_period) 
                        DO UPDATE SET {update_clause}
                    """
                    
                elif table_name == "massive_cash_flow_statements":
                    columns = [col for col in df.columns if col not in ['source', 'loaded_at']]
                    placeholders = ", ".join([f":{col}" for col in columns])
                    update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns])
                    
                    sql = f"""
                        INSERT INTO massive_cash_flow_statements ({", ".join(columns)})
                        VALUES ({placeholders})
                        ON CONFLICT (symbol, period_end, fiscal_period) 
                        DO UPDATE SET {update_clause}
                    """
                    
                elif table_name == "massive_income_statements":
                    columns = [col for col in df.columns if col not in ['source', 'loaded_at']]
                    placeholders = ", ".join([f":{col}" for col in columns])
                    update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns])
                    
                    sql = f"""
                        INSERT INTO massive_income_statements ({", ".join(columns)})
                        VALUES ({placeholders})
                        ON CONFLICT (symbol, period_end, fiscal_period) 
                        DO UPDATE SET {update_clause}
                    """
                    
                elif table_name == "massive_financial_ratios":
                    columns = [col for col in df.columns if col not in ['source', 'loaded_at']]
                    placeholders = ", ".join([f":{col}" for col in columns])
                    update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns])
                    
                    sql = f"""
                        INSERT INTO massive_financial_ratios ({", ".join(columns)})
                        VALUES ({placeholders})
                        ON CONFLICT (symbol, period_end, fiscal_period) 
                        DO UPDATE SET {update_clause}
                    """
                    
                elif table_name == "massive_short_interest":
                    columns = [col for col in df.columns if col not in ['source', 'loaded_at']]
                    placeholders = ", ".join([f":{col}" for col in columns])
                    update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns])
                    
                    sql = f"""
                        INSERT INTO massive_short_interest ({", ".join(columns)})
                        VALUES ({placeholders})
                        ON CONFLICT (symbol, settlement_date) 
                        DO UPDATE SET {update_clause}
                    """
                    
                elif table_name == "massive_short_volume":
                    columns = [col for col in df.columns if col not in ['source', 'loaded_at']]
                    placeholders = ", ".join([f":{col}" for col in columns])
                    update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns])
                    
                    sql = f"""
                        INSERT INTO massive_short_volume ({", ".join(columns)})
                        VALUES ({placeholders})
                        ON CONFLICT (symbol, trading_date) 
                        DO UPDATE SET {update_clause}
                    """
                
                elif table_name == "massive_technical_indicators":
                    columns = [col for col in df.columns if col not in ['source', 'loaded_at']]
                    placeholders = ", ".join([f":{col}" for col in columns])
                    update_clause = ", ".join([f'"{col}" = EXCLUDED."{col}"' if col == 'window' else f"{col} = EXCLUDED.{col}" for col in columns])
                    
                    sql = f"""
                        INSERT INTO massive_technical_indicators ({", ".join([f'"{col}"' if col == 'window' else col for col in columns])})
                        VALUES ({placeholders})
                        ON CONFLICT (symbol, indicator_type, timestamp, "window", short_window, long_window, signal_window) 
                        DO UPDATE SET {update_clause}
                    """
                
                # Execute upsert for all records
                for _, row in df.iterrows():
                    session.execute(text(sql), row.to_dict())
                
                session.commit()
                logger.info(f"✅ Saved {len(data)} records to {table_name}")
                
        except Exception as e:
            logger.error(f"Error saving data to {table_name}: {e}")
            raise
    
    @trace_function("load_all_fundamentals")
    def load_all_fundamentals(self, symbol: str):
        """Load all fundamentals data for a symbol"""
        logger.info(f"🔄 Loading all fundamentals for {symbol}")
        
        # Create tables if they don't exist
        self.create_fundamentals_tables()
        
        # Load all data types
        balance_sheets = self.load_balance_sheets(symbol)
        cash_flow_statements = self.load_cash_flow_statements(symbol)
        income_statements = self.load_income_statements(symbol)
        financial_ratios = self.load_financial_ratios(symbol)
        short_interest = self.load_short_interest(symbol)
        short_volume = self.load_short_volume(symbol)
        
        # Load technical indicators
        rsi_data = self.load_rsi(symbol)
        macd_data = self.load_macd(symbol)
        ema_data = self.load_ema(symbol)
        sma_data = self.load_sma(symbol)
        
        # Save to database
        if balance_sheets:
            self.save_to_database("massive_balance_sheets", balance_sheets)
        
        if cash_flow_statements:
            self.save_to_database("massive_cash_flow_statements", cash_flow_statements)
        
        if income_statements:
            self.save_to_database("massive_income_statements", income_statements)
        
        if financial_ratios:
            self.save_to_database("massive_financial_ratios", financial_ratios)
        
        if short_interest:
            self.save_to_database("massive_short_interest", short_interest)
        
        if short_volume:
            self.save_to_database("massive_short_volume", short_volume)
        
        # Save technical indicators
        if rsi_data:
            self.save_to_database("massive_technical_indicators", rsi_data)
        
        if macd_data:
            self.save_to_database("massive_technical_indicators", macd_data)
        
        if ema_data:
            self.save_to_database("massive_technical_indicators", ema_data)
        
        if sma_data:
            self.save_to_database("massive_technical_indicators", sma_data)
        
        total_records = (len(balance_sheets) + len(cash_flow_statements) + len(income_statements) + 
                        len(financial_ratios) + len(short_interest) + len(short_volume) + 
                        len(rsi_data) + len(macd_data) + len(ema_data) + len(sma_data))
        
        logger.info(f"🎉 Loaded {total_records} total fundamentals records for {symbol}")
        
        return {
            "symbol": symbol,
            "balance_sheets": len(balance_sheets),
            "cash_flow_statements": len(cash_flow_statements),
            "income_statements": len(income_statements),
            "financial_ratios": len(financial_ratios),
            "short_interest": len(short_interest),
            "short_volume": len(short_volume),
            "rsi": len(rsi_data),
            "macd": len(macd_data),
            "ema": len(ema_data),
            "sma": len(sma_data),
            "total_records": total_records
        }


# Convenience function for easy usage
def load_symbol_fundamentals(symbol: str) -> Dict[str, Any]:
    """Load all fundamentals data for a symbol"""
    loader = MassiveFundamentalsLoader()
    return loader.load_all_fundamentals(symbol)
