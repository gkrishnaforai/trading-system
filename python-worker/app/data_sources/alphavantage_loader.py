"""
Alpha Vantage Data Loader
Comprehensive database loading from Alpha Vantage API
Loads all required tables with proper data transformation
"""
import logging
import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.data_sources.alphavantage_configured import ConfiguredAlphaVantageSource
from app.database import db
from app.observability.tracing import trace_function
from app.observability.logging import get_logger
from sqlalchemy import text

logger = get_logger("alphavantage_loader")

@dataclass
class LoadResult:
    """Result of data loading operation"""
    success: bool
    records_loaded: int
    table_name: str
    message: str
    duration_seconds: float

class AlphaVantageDataLoader:
    """Comprehensive Alpha Vantage data loader for database tables"""
    
    def __init__(self, api_key: str):
        self.source = ConfiguredAlphaVantageSource(api_key)
        logger.info("🚀 Alpha Vantage Data Loader initialized")
    
    @trace_function("load_symbol_data")
    def load_symbol_data(self, symbol: str) -> List[LoadResult]:
        """
        Load comprehensive data for a single symbol
        Returns list of load results for each table
        """
        results = []
        start_time = datetime.now()
        
        logger.info(f"📊 Loading comprehensive data for {symbol}")
        
        try:
            # 1. Load Company Overview (fundamentals_summary table)
            result = self._load_company_overview(symbol)
            results.append(result)
            
            # 2. Load Income Statement (fundamentals table)
            result = self._load_income_statement(symbol)
            results.append(result)
            
            # 3. Load Balance Sheet (fundamentals table)
            result = self._load_balance_sheet(symbol)
            results.append(result)
            
            # 4. Load Cash Flow (fundamentals table)
            result = self._load_cash_flow(symbol)
            results.append(result)
            
            # 5. Load Earnings (fundamentals table)
            result = self._load_earnings(symbol)
            results.append(result)
            
            # 6. Load Price Data (raw_market_data_daily table)
            result = self._load_price_data(symbol)
            results.append(result)
            
            # 7. Load Technical Indicators (indicators_daily table)
            result = self._load_technical_indicators(symbol)
            results.append(result)
            
            total_duration = (datetime.now() - start_time).total_seconds()
            successful_loads = sum(1 for r in results if r.success)
            
            logger.info(f"✅ Completed loading for {symbol}: {successful_loads}/{len(results)} tables in {total_duration:.1f}s")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error loading data for {symbol}: {e}")
            return [LoadResult(False, 0, "error", str(e), 0)]
    
    def _load_company_overview(self, symbol: str) -> LoadResult:
        """Load company overview into fundamentals_summary table"""
        start_time = datetime.now()
        
        try:
            overview = self.source.fetch_company_overview(symbol)
            
            if not overview:
                return LoadResult(False, 0, "fundamentals_summary", "No overview data", 0)
            
            # Transform to database format
            record = {
                'symbol': overview.get('Symbol'),
                'name': overview.get('Name'),
                'sector': overview.get('Sector'),
                'industry': overview.get('Industry'),
                'market_cap': self._safe_float(overview.get('MarketCapitalization')),
                'pe_ratio': self._safe_float(overview.get('PERatio')),
                'pb_ratio': self._safe_float(overview.get('PriceToBookRatio')),
                'eps': self._safe_float(overview.get('EPS')),
                'beta': self._safe_float(overview.get('Beta')),
                'dividend_yield': self._safe_float(overview.get('DividendYield')),
                'revenue_ttm': self._safe_float(overview.get('RevenueTTM')),
                'gross_profit_ttm': self._safe_float(overview.get('GrossProfitTTM')),
                'operating_margin_ttm': self._safe_float(overview.get('OperatingMarginTTM')),
                'profit_margin': self._safe_float(overview.get('ProfitMargin')),
                'roe': self._safe_float(overview.get('ReturnOnEquityTTM')),
                'debt_to_equity': None,  # Not provided by Alpha Vantage
                'price_to_sales': self._safe_float(overview.get('PriceToSalesRatioTTM')),
                'ev_to_revenue': self._safe_float(overview.get('EVToRevenue')),
                'ev_to_ebitda': self._safe_float(overview.get('EVToEBITDA')),
                'price_to_book': self._safe_float(overview.get('PriceToBookRatio')),
                'data_source': 'alphavantage',
                'updated_at': datetime.now()
            }
            
            # Save to database
            success = self._save_to_fundamentals_summary([record])
            duration = (datetime.now() - start_time).total_seconds()
            
            if success:
                logger.info(f"✅ Loaded company overview for {symbol}")
                return LoadResult(True, 1, "fundamentals_summary", "Success", duration)
            else:
                return LoadResult(False, 0, "fundamentals_summary", "Database save failed", duration)
                
        except Exception as e:
            logger.error(f"Error loading company overview for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "fundamentals_summary", str(e), duration)
    
    def _load_income_statement(self, symbol: str) -> LoadResult:
        """Load income statement into fundamentals table"""
        start_time = datetime.now()
        
        try:
            income_data = self.source.fetch_income_statement(symbol)
            
            if not income_data:
                return LoadResult(False, 0, "fundamentals", "No income statement data", 0)
            
            records = []
            for report in income_data.get("annualReports", []):
                record = {
                    'symbol': symbol,
                    'report_type': 'income_statement',
                    'fiscal_date_ending': self._safe_date(report.get('fiscalDateEnding')),
                    'reported_currency': report.get('reportedCurrency'),
                    'total_revenue': self._safe_float(report.get('totalRevenue')),
                    'gross_profit': self._safe_float(report.get('grossProfit')),
                    'operating_income': self._safe_float(report.get('operatingIncome')),
                    'net_income': self._safe_float(report.get('netIncome')),
                    'research_and_development': self._safe_float(report.get('researchAndDevelopment')),
                    'selling_general_and_admin': self._safe_float(report.get('sellingGeneralAndAdministrative')),
                    'interest_expense': self._safe_float(report.get('interestExpense')),
                    'income_tax_expense': self._safe_float(report.get('incomeTaxExpense')),
                    'data_source': 'alphavantage',
                    'updated_at': datetime.now()
                }
                records.append(record)
            
            # Save to database
            success = self._save_to_fundamentals(records)
            duration = (datetime.now() - start_time).total_seconds()
            
            if success:
                logger.info(f"✅ Loaded {len(records)} income statement records for {symbol}")
                return LoadResult(True, len(records), "fundamentals", "Success", duration)
            else:
                return LoadResult(False, 0, "fundamentals", "Database save failed", duration)
                
        except Exception as e:
            logger.error(f"Error loading income statement for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "fundamentals", str(e), duration)
    
    def _load_balance_sheet(self, symbol: str) -> LoadResult:
        """Load balance sheet into fundamentals table"""
        start_time = datetime.now()
        
        try:
            balance_data = self.source.fetch_balance_sheet(symbol)
            
            if not balance_data:
                return LoadResult(False, 0, "fundamentals", "No balance sheet data", 0)
            
            records = []
            for report in balance_data.get("annualReports", []):
                record = {
                    'symbol': symbol,
                    'report_type': 'balance_sheet',
                    'fiscal_date_ending': self._safe_date(report.get('fiscalDateEnding')),
                    'reported_currency': report.get('reportedCurrency'),
                    'total_assets': self._safe_float(report.get('totalAssets')),
                    'total_liabilities': self._safe_float(report.get('totalLiabilities')),
                    'total_shareholder_equity': self._safe_float(report.get('totalShareholderEquity')),
                    'cash_and_cash_equivalents': self._safe_float(report.get('cashAndCashEquivalentsAtCarryingValue')),
                    'short_term_investments': self._safe_float(report.get('shortTermInvestments')),
                    'long_term_debt': self._safe_float(report.get('longTermDebt')),
                    'data_source': 'alphavantage',
                    'updated_at': datetime.now()
                }
                records.append(record)
            
            # Save to database
            success = self._save_to_fundamentals(records)
            duration = (datetime.now() - start_time).total_seconds()
            
            if success:
                logger.info(f"✅ Loaded {len(records)} balance sheet records for {symbol}")
                return LoadResult(True, len(records), "fundamentals", "Success", duration)
            else:
                return LoadResult(False, 0, "fundamentals", "Database save failed", duration)
                
        except Exception as e:
            logger.error(f"Error loading balance sheet for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "fundamentals", str(e), duration)
    
    def _load_cash_flow(self, symbol: str) -> LoadResult:
        """Load cash flow into fundamentals table"""
        start_time = datetime.now()
        
        try:
            cash_flow_data = self.source.fetch_cash_flow(symbol)
            
            if not cash_flow_data:
                return LoadResult(False, 0, "fundamentals", "No cash flow data", 0)
            
            records = []
            for report in cash_flow_data.get("annualReports", []):
                record = {
                    'symbol': symbol,
                    'report_type': 'cash_flow',
                    'fiscal_date_ending': self._safe_date(report.get('fiscalDateEnding')),
                    'reported_currency': report.get('reportedCurrency'),
                    'operating_cash_flow': self._safe_float(report.get('operatingCashflow')),
                    'investing_cash_flow': self._safe_float(report.get('cashflowFromInvestment')),
                    'financing_cash_flow': self._safe_float(report.get('cashflowFromFinancing')),
                    'free_cash_flow': self._safe_float(report.get('operatingCashflow')) - self._safe_float(report.get('cashflowFromInvestment')),
                    'capital_expenditures': self._safe_float(report.get('capitalExpenditures')),
                    'data_source': 'alphavantage',
                    'updated_at': datetime.now()
                }
                records.append(record)
            
            # Save to database
            success = self._save_to_fundamentals(records)
            duration = (datetime.now() - start_time).total_seconds()
            
            if success:
                logger.info(f"✅ Loaded {len(records)} cash flow records for {symbol}")
                return LoadResult(True, len(records), "fundamentals", "Success", duration)
            else:
                return LoadResult(False, 0, "fundamentals", "Database save failed", duration)
                
        except Exception as e:
            logger.error(f"Error loading cash flow for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "fundamentals", str(e), duration)
    
    def _load_earnings(self, symbol: str) -> LoadResult:
        """Load earnings data into fundamentals table"""
        start_time = datetime.now()
        
        try:
            earnings_data = self.source.fetch_earnings(symbol)
            
            if not earnings_data:
                return LoadResult(False, 0, "fundamentals", "No earnings data", 0)
            
            records = []
            for report in earnings_data.get("quarterlyEarnings", []):
                record = {
                    'symbol': symbol,
                    'report_type': 'earnings',
                    'fiscal_date_ending': self._safe_date(report.get('fiscalDateEnding')),
                    'reported_date': self._safe_date(report.get('reportedDate')),
                    'reported_eps': self._safe_float(report.get('reportedEPS')),
                    'estimated_eps': self._safe_float(report.get('estimatedEPS')),
                    'surprise': self._safe_float(report.get('surprise')),
                    'surprise_percentage': self._safe_float(report.get('surprisePercentage')),
                    'data_source': 'alphavantage',
                    'updated_at': datetime.now()
                }
                records.append(record)
            
            # Save to database
            success = self._save_to_fundamentals(records)
            duration = (datetime.now() - start_time).total_seconds()
            
            if success:
                logger.info(f"✅ Loaded {len(records)} earnings records for {symbol}")
                return LoadResult(True, len(records), "fundamentals", "Success", duration)
            else:
                return LoadResult(False, 0, "fundamentals", "Database save failed", duration)
                
        except Exception as e:
            logger.error(f"Error loading earnings for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "fundamentals", str(e), duration)
    
    def _load_price_data(self, symbol: str, days: int = 365) -> LoadResult:
        """Load price data into raw_market_data_daily table"""
        start_time = datetime.now()
        
        try:
            time_series = self.source.fetch_time_series_daily(symbol, outputsize="compact")
            
            if not time_series:
                return LoadResult(False, 0, "raw_market_data_daily", "No price data", 0)
            
            records = []
            time_series_data = time_series.get("Time Series (Daily)", {})
            
            for date_str, price_data in time_series_data.items():
                record = {
                    'symbol': symbol,
                    'date': self._safe_date(date_str),
                    'open': self._safe_float(price_data.get('1. open')),
                    'high': self._safe_float(price_data.get('2. high')),
                    'low': self._safe_float(price_data.get('3. low')),
                    'close': self._safe_float(price_data.get('4. close')),
                    'volume': self._safe_int(price_data.get('5. volume')),
                    'adjusted_close': self._safe_float(price_data.get('4. close')),  # Alpha Vantage doesn't provide adjusted close
                    'data_source': 'alphavantage',
                    'created_at': datetime.now()
                }
                records.append(record)
            
            # Save to database
            success = self._save_to_market_data_daily(records)
            duration = (datetime.now() - start_time).total_seconds()
            
            if success:
                logger.info(f"✅ Loaded {len(records)} price records for {symbol}")
                return LoadResult(True, len(records), "raw_market_data_daily", "Success", duration)
            else:
                return LoadResult(False, 0, "raw_market_data_daily", "Database save failed", duration)
                
        except Exception as e:
            logger.error(f"Error loading price data for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "raw_market_data_daily", str(e), duration)
    
    def _load_technical_indicators(self, symbol: str) -> LoadResult:
        """Load technical indicators into indicators_daily table"""
        start_time = datetime.now()
        
        try:
            indicators = {}
            
            # Load RSI
            rsi_data = self.source.fetch_technical_indicator(symbol, "RSI", interval="daily", time_period=14)
            if rsi_data:
                indicators['RSI'] = rsi_data
            
            # Load MACD
            macd_data = self.source.fetch_technical_indicator(symbol, "MACD", interval="daily")
            if macd_data:
                indicators['MACD'] = macd_data
            
            # Load SMA
            sma_data = self.source.fetch_technical_indicator(symbol, "SMA", interval="daily", time_period=20)
            if sma_data:
                indicators['SMA'] = sma_data
            
            # Load EMA
            ema_data = self.source.fetch_technical_indicator(symbol, "EMA", interval="daily", time_period=20)
            if ema_data:
                indicators['EMA'] = ema_data
            
            if not indicators:
                return LoadResult(False, 0, "indicators_daily", "No technical indicators", 0)
            
            # Transform and combine indicators
            records = []
            for indicator_name, data in indicators.items():
                # Find the time series key (varies by indicator)
                time_series_key = None
                for key in data.keys():
                    if "Time Series" in key:
                        time_series_key = key
                        break
                
                if not time_series_key:
                    continue
                
                time_series_data = data.get(time_series_key, {})
                
                for date_str, values in time_series_data.items():
                    # Extract the indicator value (key varies by indicator)
                    value_key = None
                    for key in values.keys():
                        if key != "Date" and not key.startswith("1. "):
                            value_key = key
                            break
                    
                    if value_key:
                        record = {
                            'symbol': symbol,
                            'date': self._safe_date(date_str),
                            'indicator_name': indicator_name,
                            'indicator_value': self._safe_float(values.get(value_key)),
                            'time_period': self._extract_time_period(indicator_name, data),
                            'data_source': 'alphavantage',
                            'created_at': datetime.now()
                        }
                        records.append(record)
            
            # Save to database
            success = self._save_to_indicators_daily(records)
            duration = (datetime.now() - start_time).total_seconds()
            
            if success:
                logger.info(f"✅ Loaded {len(records)} technical indicator records for {symbol}")
                return LoadResult(True, len(records), "indicators_daily", "Success", duration)
            else:
                return LoadResult(False, 0, "indicators_daily", "Database save failed", duration)
                
        except Exception as e:
            logger.error(f"Error loading technical indicators for {symbol}: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            return LoadResult(False, 0, "indicators_daily", str(e), duration)
    
    def _save_to_fundamentals_summary(self, records: List[Dict[str, Any]]) -> bool:
        """Save records to fundamentals_summary table"""
        try:
            with db.get_session() as session:
                # Use UPSERT to avoid duplicates
                for record in records:
                    # Check if record exists
                    existing = session.execute(
                        text("""
                        SELECT id FROM fundamentals_summary 
                        WHERE symbol = :symbol AND data_source = 'alphavantage'
                        """),
                        {"symbol": record['symbol']}
                    ).fetchone()
                    
                    if existing:
                        # Update existing record
                        session.execute(
                            text("""
                            UPDATE fundamentals_summary SET
                                name = :name, sector = :sector, industry = :industry,
                                market_cap = :market_cap, pe_ratio = :pe_ratio, pb_ratio = :pb_ratio,
                                eps = :eps, beta = :beta, dividend_yield = :dividend_yield,
                                revenue_ttm = :revenue_ttm, gross_profit_ttm = :gross_profit_ttm,
                                operating_margin_ttm = :operating_margin_ttm, profit_margin = :profit_margin,
                                roe = :roe, debt_to_equity = :debt_to_equity, price_to_sales = :price_to_sales,
                                ev_to_revenue = :ev_to_revenue, ev_to_ebitda = :ev_to_ebitda,
                                price_to_book = :price_to_book, updated_at = :updated_at
                            WHERE symbol = :symbol AND data_source = 'alphavantage'
                            """),
                            record
                        )
                    else:
                        # Insert new record
                        session.execute(
                            text("""
                            INSERT INTO fundamentals_summary (
                                symbol, name, sector, industry, market_cap, pe_ratio, pb_ratio,
                                eps, beta, dividend_yield, revenue_ttm, gross_profit_ttm,
                                operating_margin_ttm, profit_margin, roe, debt_to_equity,
                                price_to_sales, ev_to_revenue, ev_to_ebitda, price_to_book,
                                data_source, updated_at
                            ) VALUES (
                                :symbol, :name, :sector, :industry, :market_cap, :pe_ratio, :pb_ratio,
                                :eps, :beta, :dividend_yield, :revenue_ttm, :gross_profit_ttm,
                                :operating_margin_ttm, :profit_margin, :roe, :debt_to_equity,
                                :price_to_sales, :ev_to_revenue, :ev_to_ebitda, :price_to_book,
                                :data_source, :updated_at
                            )
                            """),
                            record
                        )
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error saving to fundamentals_summary: {e}")
            return False
    
    def _save_to_fundamentals(self, records: List[Dict[str, Any]]) -> bool:
        """Save records to fundamentals table"""
        try:
            with db.get_session() as session:
                for record in records:
                    # Use UPSERT to avoid duplicates
                    session.execute(
                        text("""
                        INSERT INTO fundamentals (
                            symbol, report_type, fiscal_date_ending, reported_currency,
                            total_revenue, gross_profit, operating_income, net_income,
                            research_and_development, selling_general_and_admin,
                            interest_expense, income_tax_expense, total_assets,
                            total_liabilities, total_shareholder_equity,
                            cash_and_cash_equivalents, short_term_investments,
                            long_term_debt, operating_cash_flow, investing_cash_flow,
                            financing_cash_flow, free_cash_flow, capital_expenditures,
                            reported_eps, estimated_eps, surprise, surprise_percentage,
                            data_source, updated_at
                        ) VALUES (
                            :symbol, :report_type, :fiscal_date_ending, :reported_currency,
                            :total_revenue, :gross_profit, :operating_income, :net_income,
                            :research_and_development, :selling_general_and_admin,
                            :interest_expense, :income_tax_expense, :total_assets,
                            :total_liabilities, :total_shareholder_equity,
                            :cash_and_cash_equivalents, :short_term_investments,
                            :long_term_debt, :operating_cash_flow, :investing_cash_flow,
                            :financing_cash_flow, :free_cash_flow, :capital_expenditures,
                            :reported_eps, :estimated_eps, :surprise, :surprise_percentage,
                            :data_source, :updated_at
                        ) ON CONFLICT (symbol, report_type, fiscal_date_ending, data_source) 
                        DO UPDATE SET
                            reported_currency = EXCLUDED.reported_currency,
                            total_revenue = EXCLUDED.total_revenue,
                            gross_profit = EXCLUDED.gross_profit,
                            operating_income = EXCLUDED.operating_income,
                            net_income = EXCLUDED.net_income,
                            research_and_development = EXCLUDED.research_and_development,
                            selling_general_and_admin = EXCLUDED.selling_general_and_admin,
                            interest_expense = EXCLUDED.interest_expense,
                            income_tax_expense = EXCLUDED.income_tax_expense,
                            total_assets = EXCLUDED.total_assets,
                            total_liabilities = EXCLUDED.total_liabilities,
                            total_shareholder_equity = EXCLUDED.total_shareholder_equity,
                            cash_and_cash_equivalents = EXCLUDED.cash_and_cash_equivalents,
                            short_term_investments = EXCLUDED.short_term_investments,
                            long_term_debt = EXCLUDED.long_term_debt,
                            operating_cash_flow = EXCLUDED.operating_cash_flow,
                            investing_cash_flow = EXCLUDED.investing_cash_flow,
                            financing_cash_flow = EXCLUDED.financing_cash_flow,
                            free_cash_flow = EXCLUDED.free_cash_flow,
                            capital_expenditures = EXCLUDED.capital_expenditures,
                            reported_eps = EXCLUDED.reported_eps,
                            estimated_eps = EXCLUDED.estimated_eps,
                            surprise = EXCLUDED.surprise,
                            surprise_percentage = EXCLUDED.surprise_percentage,
                            updated_at = EXCLUDED.updated_at
                        """),
                        record
                    )
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error saving to fundamentals: {e}")
            return False
    
    def _save_to_market_data_daily(self, records: List[Dict[str, Any]]) -> bool:
        """Save records to raw_market_data_daily table"""
        try:
            with db.get_session() as session:
                for record in records:
                    session.execute(
                        text("""
                        INSERT INTO raw_market_data_daily (
                            symbol, date, open, high, low, close, volume, adjusted_close,
                            data_source, created_at
                        ) VALUES (
                            :symbol, :date, :open, :high, :low, :close, :volume, :adjusted_close,
                            :data_source, :created_at
                        ) ON CONFLICT (symbol, date, data_source) 
                        DO UPDATE SET
                            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                            close = EXCLUDED.close, volume = EXCLUDED.volume,
                            adjusted_close = EXCLUDED.adjusted_close,
                            created_at = EXCLUDED.created_at
                        """),
                        record
                    )
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error saving to raw_market_data_daily: {e}")
            return False
    
    def _save_to_indicators_daily(self, records: List[Dict[str, Any]]) -> bool:
        """Save records to indicators_daily table"""
        try:
            with db.get_session() as session:
                for record in records:
                    session.execute(
                        text("""
                        INSERT INTO indicators_daily (
                            symbol, date, indicator_name, indicator_value, time_period,
                            data_source, created_at
                        ) VALUES (
                            :symbol, :date, :indicator_name, :indicator_value, :time_period,
                            :data_source, :created_at
                        ) ON CONFLICT (symbol, date, indicator_name, data_source) 
                        DO UPDATE SET
                            indicator_value = EXCLUDED.indicator_value,
                            time_period = EXCLUDED.time_period,
                            created_at = EXCLUDED.created_at
                        """),
                        record
                    )
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error saving to indicators_daily: {e}")
            return False
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None or value == "None" or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert value to int"""
        if value is None or value == "None" or value == "":
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    def _safe_date(self, value: Any) -> Optional[datetime]:
        """Safely convert value to datetime"""
        if value is None or value == "None" or value == "":
            return None
        try:
            if isinstance(value, str):
                return datetime.strptime(value, "%Y-%m-%d")
            return value
        except (ValueError, TypeError):
            return None
    
    def _extract_time_period(self, indicator_name: str, data: Dict[str, Any]) -> Optional[int]:
        """Extract time period from indicator data"""
        # Try to find time period in metadata
        metadata = data.get("Meta Data", {})
        for key, value in metadata.items():
            if "Time Period" in key:
                try:
                    return int(value)
                except (ValueError, TypeError):
                    pass
        
        # Default time periods based on indicator
        defaults = {
            "RSI": 14,
            "MACD": None,
            "SMA": 20,
            "EMA": 20
        }
        
        return defaults.get(indicator_name)
