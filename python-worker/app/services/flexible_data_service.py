#!/usr/bin/env python3
"""
Flexible Data Service
Allows choosing data source (Massive/Yahoo) per API call
Optimized for: Historical from Yahoo, Real-time from Massive
"""
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from enum import Enum
import pandas as pd

from app.data_sources.adapters.factory import AdapterFactory
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.observability.tracing import trace_function
from app.observability.logging import get_logger

logger = get_logger("flexible_data_service")

class DataSource(Enum):
    """Data source options"""
    MASSIVE = "massive"
    YAHOO = "yahoo"
    AUTO = "auto"  # Choose best based on data type/age

class DataStrategy(Enum):
    """Data selection strategies"""
    MASSIVE_FIRST = "massive_first"  # Try Massive first, fallback to Yahoo
    YAHOO_FIRST = "yahoo_first"      # Try Yahoo first, fallback to Massive
    HISTORICAL_YAHOO = "historical_yahoo"  # Use Yahoo for historical (>30 days), Massive for recent
    REAL_TIME_MASSIVE = "real_time_massive"  # Use Massive for real-time, Yahoo for historical

class FlexibleDataService:
    """Flexible data service supporting multiple sources with per-request selection"""
    
    def __init__(self):
        self.yahoo_source = YahooFinanceSource()
        self.adapter_factory = AdapterFactory()
        self.massive_adapter = None
        
        # Try to get Massive adapter (may not be available)
        try:
            self.massive_adapter = self.adapter_factory.create_adapter("massive")
        except Exception as e:
            logger.warning(f"Massive adapter not available: {e}")
    
    @trace_function("get_price_data")
    def get_price_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = "1y",
        data_source: DataSource = DataSource.AUTO,
        strategy: DataStrategy = DataStrategy.HISTORICAL_YAHOO
    ) -> Optional[pd.DataFrame]:
        """
        Get price data with flexible source selection
        
        Args:
            symbol: Stock symbol
            start_date: Start date for historical data
            end_date: End date for historical data
            period: Period if no dates specified (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            data_source: Force specific source or AUTO
            strategy: Strategy for source selection when AUTO
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Determine which source to use
            source = self._select_source(
                data_type="price_data",
                data_source=data_source,
                strategy=strategy,
                start_date=start_date,
                end_date=end_date
            )
            
            logger.info(f"Getting price data for {symbol} from {source.value}")
            
            if source == DataSource.YAHOO:
                return self._get_yahoo_price_data(symbol, start_date, end_date, period)
            elif source == DataSource.MASSIVE and self.massive_adapter:
                return self._get_massive_price_data(symbol, start_date, end_date)
            else:
                logger.error(f"Source {source.value} not available")
                return None
                
        except Exception as e:
            logger.error(f"Error getting price data for {symbol}: {e}")
            return None
    
    @trace_function("get_technical_indicators")
    def get_technical_indicators(
        self,
        symbol: str,
        indicators: List[str] = None,
        data_source: DataSource = DataSource.MASSIVE,
        strategy: DataStrategy = DataStrategy.MASSIVE_FIRST
    ) -> Dict[str, Any]:
        """
        Get technical indicators with flexible source selection
        
        Args:
            symbol: Stock symbol
            indicators: List of indicators (RSI, MACD, EMA, SMA)
            data_source: Force specific source
            strategy: Strategy for source selection
        
        Returns:
            Dictionary with indicator data
        """
        try:
            if indicators is None:
                indicators = ["RSI", "MACD", "EMA", "SMA"]
            
            # Determine which source to use
            source = self._select_source(
                data_type="technical_indicators",
                data_source=data_source,
                strategy=strategy
            )
            
            logger.info(f"Getting technical indicators for {symbol} from {source.value}")
            
            if source == DataSource.MASSIVE and self.massive_adapter:
                return self._get_massive_indicators(symbol, indicators)
            elif source == DataSource.YAHOO:
                return self._get_yahoo_indicators(symbol, indicators)
            else:
                logger.error(f"Source {source.value} not available for technical indicators")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting technical indicators for {symbol}: {e}")
            return {}
    
    @trace_function("get_fundamentals")
    def get_fundamentals(
        self,
        symbol: str,
        data_types: List[str] = None,
        data_source: DataSource = DataSource.MASSIVE,
        strategy: DataStrategy = DataStrategy.MASSIVE_FIRST
    ) -> Dict[str, Any]:
        """
        Get fundamentals data with flexible source selection
        
        Args:
            symbol: Stock symbol
            data_types: List of data types (balance_sheet, income_statement, cash_flow, ratios)
            data_source: Force specific source
            strategy: Strategy for source selection
        
        Returns:
            Dictionary with fundamentals data
        """
        try:
            if data_types is None:
                data_types = ["balance_sheet", "income_statement", "cash_flow", "ratios"]
            
            # Determine which source to use
            source = self._select_source(
                data_type="fundamentals",
                data_source=data_source,
                strategy=strategy
            )
            
            logger.info(f"Getting fundamentals for {symbol} from {source.value}")
            
            if source == DataSource.MASSIVE and self.massive_adapter:
                return self._get_massive_fundamentals(symbol, data_types)
            elif source == DataSource.YAHOO:
                return self._get_yahoo_fundamentals(symbol, data_types)
            else:
                logger.error(f"Source {source.value} not available for fundamentals")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting fundamentals for {symbol}: {e}")
            return {}
    
    def _select_source(
        self,
        data_type: str,
        data_source: DataSource,
        strategy: DataStrategy,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> DataSource:
        """Select the best data source based on strategy and availability"""
        
        # If specific source requested, try to honor it
        if data_source != DataSource.AUTO:
            if data_source == DataSource.YAHOO:
                return DataSource.YAHOO
            elif data_source == DataSource.MASSIVE and self.massive_adapter:
                return DataSource.MASSIVE
            else:
                logger.warning(f"Requested source {data_source.value} not available, falling back")
        
        # Apply strategy
        if strategy == DataStrategy.MASSIVE_FIRST:
            if self.massive_adapter and self.massive_adapter.is_available():
                return DataSource.MASSIVE
            else:
                return DataSource.YAHOO
                
        elif strategy == DataStrategy.YAHOO_FIRST:
            return DataSource.YAHOO
            
        elif strategy == DataStrategy.HISTORICAL_YAHOO:
            # Use Yahoo for historical data, Massive for recent
            if start_date and start_date < (datetime.now() - timedelta(days=30)):
                return DataSource.YAHOO
            elif self.massive_adapter and self.massive_adapter.is_available():
                return DataSource.MASSIVE
            else:
                return DataSource.YAHOO
                
        elif strategy == DataStrategy.REAL_TIME_MASSIVE:
            # Use Massive for real-time, Yahoo for historical
            if start_date and start_date < (datetime.now() - timedelta(days=7)):
                return DataSource.YAHOO
            elif self.massive_adapter and self.massive_adapter.is_available():
                return DataSource.MASSIVE
            else:
                return DataSource.YAHOO
        
        # Default fallback
        return DataSource.YAHOO
    
    def _get_yahoo_price_data(self, symbol: str, start_date: Optional[datetime], end_date: Optional[datetime], period: str) -> Optional[pd.DataFrame]:
        """Get price data from Yahoo Finance"""
        try:
            kwargs: Dict[str, Any] = {"period": period}
            if start_date and end_date:
                kwargs.update({"start": start_date, "end": end_date})
            return self.yahoo_source.fetch_price_data(symbol, **kwargs)
        except Exception as e:
            logger.error(f"Yahoo price data failed for {symbol}: {e}")
            return None
    
    def _get_massive_price_data(self, symbol: str, start_date: Optional[datetime], end_date: Optional[datetime]) -> Optional[pd.DataFrame]:
        """Get price data from Massive"""
        try:
            # Note: Massive doesn't have direct historical price data in the same format
            # This would need to be implemented based on Massive endpoints
            logger.warning("Massive historical price data not fully implemented")
            return None
        except Exception as e:
            logger.error(f"Massive price data failed for {symbol}: {e}")
            return None
    
    def _get_massive_indicators(self, symbol: str, indicators: List[str]) -> Dict[str, Any]:
        """Get technical indicators from Massive"""
        try:
            from app.data_sources.massive_fundamentals import MassiveFundamentalsLoader
            loader = MassiveFundamentalsLoader()
            
            result = {}
            
            if "RSI" in indicators:
                rsi_data = loader.load_rsi(symbol, limit="10")
                result["RSI"] = rsi_data
            
            if "MACD" in indicators:
                macd_data = loader.load_macd(symbol, limit="10")
                result["MACD"] = macd_data
            
            if "EMA" in indicators:
                ema_data = loader.load_ema(symbol, limit="10")
                result["EMA"] = ema_data
            
            return result
            
        except (ImportError, Exception) as e:
            logger.warning(f"Massive indicators not available for {symbol}: {e}")
            return {}
    
    def _get_yahoo_indicators(self, symbol: str, indicators: List[str]) -> Dict[str, Any]:
        """Get technical indicators from Yahoo (calculated from historical data)"""
        try:
            result: Dict[str, Any] = {}
            for ind in indicators:
                try:
                    result[ind] = self.yahoo_source.fetch_technical_indicators(symbol, indicator_type=ind)
                except Exception as e:
                    logger.warning(f"Yahoo indicator {ind} failed for {symbol}: {e}")
            return result
            
        except Exception as e:
            logger.error(f"Yahoo indicators failed for {symbol}: {e}")
            return {}
    
    def _get_massive_fundamentals(self, symbol: str, data_types: List[str]) -> Dict[str, Any]:
        """Get fundamentals from Massive"""
        try:
            from app.data_sources.massive_fundamentals import MassiveFundamentalsLoader
            loader = MassiveFundamentalsLoader()
            
            result = {}
            
            if "balance_sheet" in data_types:
                balance_data = loader.load_balance_sheets(symbol, limit=5)
                result["balance_sheet"] = balance_data
            
            if "income_statement" in data_types:
                income_data = loader.load_income_statements(symbol, limit=5)
                result["income_statement"] = income_data
            
            if "cash_flow" in data_types:
                cash_flow_data = loader.load_cash_flow_statements(symbol, limit=5)
                result["cash_flow"] = cash_flow_data
            
            if "ratios" in data_types:
                ratios_data = loader.load_financial_ratios(symbol, limit=5)
                result["ratios"] = ratios_data
            
            return result
            
        except (ImportError, Exception) as e:
            logger.warning(f"Massive fundamentals not available for {symbol}: {e}")
            return {}
    
    def _get_yahoo_fundamentals(self, symbol: str, data_types: List[str]) -> Dict[str, Any]:
        """Get fundamentals from Yahoo Finance"""
        try:
            # The thin source exposes a single normalized fundamentals payload.
            # Keep the old shape but derive it from the normalized payload.
            payload = self.yahoo_source.fetch_fundamentals(symbol)
            result: Dict[str, Any] = {}
            if "ratios" in data_types:
                result["ratios"] = {
                    "pe_ratio": payload.get("pe_ratio"),
                    "pb_ratio": payload.get("pb_ratio") or payload.get("price_to_book"),
                    "dividend_yield": payload.get("dividend_yield"),
                    "roe": payload.get("return_on_equity"),
                    "debt_to_equity": payload.get("debt_to_equity"),
                }
            # The provider client already includes some balance-sheet-like fields, but not full statements.
            if "balance_sheet" in data_types:
                result["balance_sheet"] = {}
            if "income_statement" in data_types:
                result["income_statement"] = {}
            if "cash_flow" in data_types:
                result["cash_flow"] = {}
            return result
            
        except Exception as e:
            logger.error(f"Yahoo fundamentals failed for {symbol}: {e}")
            return {}
    
    @trace_function("get_available_sources")
    def get_available_sources(self) -> Dict[str, bool]:
        """Get status of available data sources"""
        return {
            "yahoo": True,  # Yahoo is always available
            "massive": self.massive_adapter is not None and self.massive_adapter.is_available()
        }


# Global service instance
flexible_data_service = FlexibleDataService()
