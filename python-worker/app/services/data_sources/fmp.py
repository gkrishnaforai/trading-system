"""
FMP Data Source Implementation
Follows SOLID: Single Responsibility Principle
Handles FMP-specific data fetching and normalization
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date

from app.providers.financial_modeling_prep.client import enhanced_fmp_client
from app.services.data_sources.base import (
    BaseDataSource, DataSourceType, StockGrade, ConsensusData,
    DataSourceError, DataSourceUnavailableError, DataSourceRateLimitError
)

logger = logging.getLogger(__name__)


class FMPDataSource(BaseDataSource):
    """Financial Modeling Prep data source implementation
    
    Single Responsibility: Handles only FMP API interactions
    Open/Closed: Open for extension, closed for modification
    """
    
    def __init__(self):
        super().__init__(DataSourceType.FMP)
        self.client = enhanced_fmp_client
        self._setup_default_mappings()
    
    def _setup_default_mappings(self):
        """Setup default FMP-specific mappings"""
        # Grade mappings
        grade_mappings = {
            'Overweight': 'Buy',
            'Underweight': 'Sell',
            'Equal-Weight': 'Hold',
            'Market Perform': 'Hold',
            'Outperform': 'Buy',
            'Underperform': 'Sell',
            'Neutral': 'Hold',
            'Positive': 'Buy',
            'Negative': 'Sell'
        }
        
        # Action mappings
        action_mappings = {
            'upgrade': 'upgrade',
            'downgrade': 'downgrade',
            'maintain': 'maintain',
            'initiated': 'initiate',
            'suspended': 'suspend'
        }
        
        # Company name normalization
        company_mappings = {
            'Wells Fargo & Co': 'Wells Fargo',
            'Goldman Sachs Group': 'Goldman Sachs',
            'Morgan Stanley': 'Morgan Stanley',
            'J.P. Morgan': 'J.P. Morgan',
            'Bank of America Corp': 'Bank of America',
            'Citigroup Inc': 'Citigroup',
            'UBS Group': 'UBS',
            'Credit Suisse Group': 'Credit Suisse',
            'Barclays PLC': 'Barclays',
            'Deutsche Bank AG': 'Deutsche Bank'
        }
        
        # Apply mappings
        for external, internal in grade_mappings.items():
            self.add_mapping('grade', external, internal)
        
        for external, internal in action_mappings.items():
            self.add_mapping('action', external, internal)
        
        for external, internal in company_mappings.items():
            self.add_mapping('company', external, internal)
    
    async def get_stock_grades(self, symbol: str) -> List[Dict[str, Any]]:
        """Get stock grades from FMP API"""
        try:
            logger.info(f"📊 Fetching stock grades for {symbol} from FMP")
            
            # Use existing FMP client
            grades_data = self.client.get_stock_grades(symbol)
            
            if not grades_data:
                logger.warning(f"No grades data found for {symbol}")
                return []
            
            logger.info(f"✅ Retrieved {len(grades_data)} grades for {symbol}")
            return grades_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching stock grades for {symbol}: {e}")
            raise DataSourceError(f"FMP API error: {e}")
    
    async def get_consensus_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get consensus data from FMP API"""
        try:
            logger.info(f"📊 Fetching consensus data for {symbol} from FMP")
            
            # Use existing FMP client
            consensus_data_list = self.client.get_stock_grades_summary(symbol)
            
            if not consensus_data_list or len(consensus_data_list) == 0:
                logger.warning(f"No consensus data found for {symbol}")
                return None
            
            # Take the first (and typically only) consensus entry
            consensus_data = consensus_data_list[0]
            
            logger.info(f"✅ Retrieved consensus data for {symbol}")
            return consensus_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching consensus data for {symbol}: {e}")
            raise DataSourceError(f"FMP consensus API error: {e}")
    
    async def validate_symbol(self, symbol: str) -> bool:
        """Validate if symbol exists in FMP"""
        try:
            # Try to get company profile
            profile = self.client.get_company_profile(symbol)
            return profile is not None and len(profile) > 0
        except Exception as e:
            logger.warning(f"Symbol validation failed for {symbol}: {e}")
            return False
    
    async def get_historical_grades(self, symbol: str, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Get historical grades within date range"""
        try:
            logger.info(f"📊 Fetching historical grades for {symbol} from {start_date} to {end_date}")
            
            # Use existing FMP client
            historical_data = self.client.get_historical_stock_grades(symbol)
            
            if not historical_data:
                return []
            
            # Filter by date range
            filtered_data = []
            for grade in historical_data:
                grade_date = self._parse_date(grade.get('date', ''))
                if start_date <= grade_date <= end_date:
                    filtered_data.append(grade)
            
            logger.info(f"✅ Retrieved {len(filtered_data)} historical grades for {symbol}")
            return filtered_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching historical grades for {symbol}: {e}")
            raise DataSourceError(f"FMP historical grades API error: {e}")
    
    async def get_price_targets(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get price target consensus data"""
        try:
            logger.info(f"📊 Fetching price targets for {symbol} from FMP")
            
            price_targets = self.client.get_price_target_consensus(symbol)
            
            if not price_targets:
                return None
            
            logger.info(f"✅ Retrieved price targets for {symbol}")
            return price_targets
            
        except Exception as e:
            logger.error(f"❌ Error fetching price targets for {symbol}: {e}")
            raise DataSourceError(f"FMP price targets API error: {e}")
    
    async def get_price_target_consensus(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get price target consensus data from FMP API
        API: https://site.financialmodelingprep.com/developer/docs/stable/price-target-consensus
        """
        try:
            logger.info(f"🎯 Fetching price target consensus for {symbol} from FMP")
            
            # Use the FMP client to get price target consensus
            price_target_data = self.client.get_price_target_consensus(symbol)
            
            if not price_target_data:
                logger.warning(f"⚠️ No price target consensus data available for {symbol}")
                return None
            
            # Normalize the data structure
            normalized_data = {
                'symbol': symbol,
                'target_mean': price_target_data.get('targetMean'),
                'target_high': price_target_data.get('targetHigh'),
                'target_low': price_target_data.get('targetLow'),
                'median_target': price_target_data.get('medianTarget'),
                'analyst_count': price_target_data.get('analystCount', 0),
                'last_updated': price_target_data.get('updatedDate'),
                'data_source': 'fmp',
                'fetched_at': datetime.now()
            }
            
            logger.info(f"✅ Retrieved price target consensus for {symbol}: "
                       f"Mean=${normalized_data['target_mean']}, "
                       f"Count={normalized_data['analyst_count']}")
            
            return normalized_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching price target consensus for {symbol}: {e}")
            raise DataSourceError(f"FMP price target consensus API error: {e}")
    
    def _parse_date(self, date_str: str) -> date:
        """Parse FMP date format"""
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            try:
                # FMP sometimes returns datetime strings
                return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%fZ').date()
            except ValueError:
                raise ValueError(f"Unable to parse FMP date: {date_str}")
    
    async def test_connection(self) -> bool:
        """Test connection to FMP API"""
        try:
            # Try to get a simple request
            test_data = self.client.get_stock_grades('AAPL')
            return test_data is not None
        except Exception as e:
            logger.error(f"FMP connection test failed: {e}")
            return False
    
    def get_rate_limit_info(self) -> Dict[str, Any]:
        """Get rate limit information for FMP"""
        return {
            'requests_per_minute': 300,  # FMP free tier limit
            'requests_per_day': 1000,
            'current_usage': 'Unknown - check FMP dashboard',
            'reset_time': 'Unknown - check FMP dashboard'
        }
    
    # === FINANCIAL DATA METHODS (for refresh_manager.py compatibility) ===
    
    def fetch_financial_statements(self, symbol: str, period: str = None) -> Dict[str, Any]:
        """Fetch financial statements data for refresh manager"""
        try:
            logger.info(f"📊 Fetching financial statements for {symbol}")
            
            # Use period directly (None for latest data)
            income_statements = self.client.get_income_statement(symbol, period)
            balance_sheets = self.client.get_balance_sheet_statement(symbol, period)
            cash_flow_statements = self.client.get_cash_flow_statement(symbol, period)
            
            return {
                "periodicity": period or "latest",
                "income_statement": income_statements,
                "balance_sheet": balance_sheets,
                "cash_flow_statement": cash_flow_statements
            }
            
        except Exception as e:
            logger.error(f"❌ Error fetching financial statements for {symbol}: {e}")
            raise DataSourceError(f"FMP financial statements API error: {e}")
    
    def fetch_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch fundamental data for refresh manager"""
        try:
            logger.info(f"📊 Fetching fundamentals for {symbol}")
            
            # Get company profile as fundamentals
            profile = self.client.get_company_profile(symbol)
            if not profile:
                return None
            
            # Add some key metrics
            metrics = self.client.get_key_metrics_ttm(symbol)
            
            # Combine profile and metrics
            fundamentals = profile.copy()
            if metrics and len(metrics) > 0:
                fundamentals["key_metrics"] = metrics[0]  # Take latest metrics
            
            return fundamentals
            
        except Exception as e:
            logger.error(f"❌ Error fetching fundamentals for {symbol}: {e}")
            raise DataSourceError(f"FMP fundamentals API error: {e}")
    
    def fetch_enhanced_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch enhanced fundamental data"""
        # For now, same as regular fundamentals
        return self.fetch_fundamentals(symbol)
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings data for refresh manager"""
        try:
            logger.info(f"📊 Fetching earnings data for {symbol}")
            
            # Get earnings calendar (for all symbols, then filter)
            earnings_calendar = self.client.get_earnings_calendar()
            
            # Filter for our symbol
            symbol_earnings = []
            if earnings_calendar:
                for earnings in earnings_calendar:
                    if earnings.get("symbol") == symbol:
                        symbol_earnings.append({
                            "type": "calendar",
                            "date": earnings.get("date"),
                            "eps_actual": earnings.get("epsActual"),
                            "eps_estimate": earnings.get("epsEstimate"),
                            "revenue_actual": earnings.get("revenueActual"),
                            "revenue_estimate": earnings.get("revenueEstimate"),
                            "quarter": earnings.get("period"),
                            "year": earnings.get("year"),
                        })
            
            # Try to get earnings surprises (if available)
            try:
                # Note: FMP might not have this endpoint, so we'll handle gracefully
                earnings_surprises = self.client.get_earnings_surprises(symbol, limit=20)
                
                # Add surprises data
                if earnings_surprises:
                    for surprise in earnings_surprises:
                        symbol_earnings.append({
                            "type": "surprise",
                            "date": surprise.get("date"),
                            "eps_actual": surprise.get("epsActual"),
                            "eps_estimate": surprise.get("epsEstimate"),
                            "eps_surprise": surprise.get("epsSurprise"),
                            "revenue_actual": surprise.get("revenueActual"),
                            "revenue_estimate": surprise.get("revenueEstimate"),
                            "revenue_surprise": surprise.get("revenueSurprise"),
                            "quarter": surprise.get("period"),
                            "year": surprise.get("year"),
                        })
            except Exception as e:
                logger.warning(f"Could not fetch earnings surprises for {symbol}: {e}")
            
            return symbol_earnings
            
        except Exception as e:
            logger.error(f"❌ Error fetching earnings data for {symbol}: {e}")
            raise DataSourceError(f"FMP earnings API error: {e}")
    
    def fetch_industry_peers(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch industry peers for refresh manager"""
        try:
            logger.info(f"📊 Fetching industry peers for {symbol}")
            
            # Get company profile first to get sector/industry
            profile = self.client.get_company_profile(symbol)
            if not profile:
                return []
            
            sector = profile.get("sector")
            industry = profile.get("industry")
            
            if not sector and not industry:
                return []
            
            # Get companies in the same sector/industry
            # Note: FMP doesn't have a direct peers endpoint, so we'll use a simple approach
            # For now, return empty list - this would need a more sophisticated implementation
            logger.warning(f"Industry peers not fully implemented for {symbol} (sector: {sector}, industry: {industry})")
            return []
            
        except Exception as e:
            logger.error(f"❌ Error fetching industry peers for {symbol}: {e}")
            raise DataSourceError(f"FMP industry peers API error: {e}")
    
    def fetch_corporate_actions(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch corporate actions for refresh manager"""
        try:
            logger.info(f"📊 Fetching corporate actions for {symbol}")
            
            # Get stock splits and dividends as corporate actions
            stock_splits = self.client.get_stock_split_details(symbol)
            dividends = self.client.get_dividends_company(symbol)
            
            corporate_actions = []
            
            # Add stock splits
            if stock_splits:
                for split in stock_splits:
                    corporate_actions.append({
                        "type": "stock_split",
                        "date": split.get("date"),
                        "description": f"Stock split: {split.get('numerator')}:{split.get('denominator')}",
                        "split_ratio": f"{split.get('numerator')}:{split.get('denominator')}",
                    })
            
            # Add dividends
            if dividends:
                for dividend in dividends:
                    corporate_actions.append({
                        "type": "dividend",
                        "date": dividend.get("date"),
                        "description": f"Dividend: ${dividend.get('dividend')}",
                        "amount": dividend.get("dividend"),
                        "yield": dividend.get("yield"),
                    })
            
            return corporate_actions
            
        except Exception as e:
            logger.error(f"❌ Error fetching corporate actions for {symbol}: {e}")
            raise DataSourceError(f"FMP corporate actions API error: {e}")
