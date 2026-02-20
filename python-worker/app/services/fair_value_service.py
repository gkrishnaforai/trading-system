"""
Fair Value Analysis Service
Implements institutional-grade fair value calculation using multiple valuation methods
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging
import math

from sqlalchemy import text
from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)

@dataclass
class FairValueResult:
    symbol: str
    current_price: float
    fair_value: float
    valuation_metrics: Dict[str, Any]
    quality_score: float
    individual_valuations: Dict[str, float]
    fundamentals: Dict[str, Any]
    updated_at: datetime

@dataclass
class FundamentalData:
    current_price: float
    eps_ttm: float
    eps_forward: float
    eps_yoy_growth: float
    revenue: float
    revenue_yoy_growth: float
    gross_margin: float
    operating_margin: float
    net_margin: float
    roic: float
    debt_to_equity: float
    current_pe: float
    forward_pe: float
    peg_ratio: float
    industry: str
    market_cap: float
    free_cash_flow: float
    book_value: float

class FairValueService:
    """Service for calculating fair value using multiple valuation methods"""
    
    def __init__(self):
        self.industry_benchmarks = self._load_industry_benchmarks()
        self.quality_thresholds = self._load_quality_thresholds()
        
    def _load_industry_benchmarks(self) -> Dict[str, Dict[str, float]]:
        """Load industry-specific benchmarks for valuation"""
        return {
            'Technology': {
                'avg_pe': 25.0,
                'avg_peg': 1.2,
                'avg_growth': 15.0,
                'avg_margin': 70.0,
                'avg_roic': 18.0,
                'avg_debt_equity': 0.3
            },
            'Healthcare': {
                'avg_pe': 20.0,
                'avg_peg': 1.0,
                'avg_growth': 12.0,
                'avg_margin': 65.0,
                'avg_roic': 15.0,
                'avg_debt_equity': 0.4
            },
            'Finance': {
                'avg_pe': 12.0,
                'avg_peg': 0.8,
                'avg_growth': 8.0,
                'avg_margin': 25.0,
                'avg_roic': 10.0,
                'avg_debt_equity': 1.0
            },
            'Consumer': {
                'avg_pe': 18.0,
                'avg_peg': 1.0,
                'avg_growth': 10.0,
                'avg_margin': 30.0,
                'avg_roic': 12.0,
                'avg_debt_equity': 0.5
            },
            'Energy': {
                'avg_pe': 15.0,
                'avg_peg': 0.9,
                'avg_growth': 5.0,
                'avg_margin': 20.0,
                'avg_roic': 8.0,
                'avg_debt_equity': 0.6
            },
            'Industrial': {
                'avg_pe': 16.0,
                'avg_peg': 0.9,
                'avg_growth': 8.0,
                'avg_margin': 25.0,
                'avg_roic': 11.0,
                'avg_debt_equity': 0.4
            },
            'Materials': {
                'avg_pe': 14.0,
                'avg_peg': 0.8,
                'avg_growth': 6.0,
                'avg_margin': 22.0,
                'avg_roic': 9.0,
                'avg_debt_equity': 0.5
            },
            'Utilities': {
                'avg_pe': 17.0,
                'avg_peg': 1.1,
                'avg_growth': 4.0,
                'avg_margin': 35.0,
                'avg_roic': 7.0,
                'avg_debt_equity': 0.8
            },
            'Real Estate': {
                'avg_pe': 19.0,
                'avg_peg': 1.0,
                'avg_growth': 7.0,
                'avg_margin': 28.0,
                'avg_roic': 8.0,
                'avg_debt_equity': 0.9
            },
            'Telecommunications': {
                'avg_pe': 16.0,
                'avg_peg': 0.9,
                'avg_growth': 6.0,
                'avg_margin': 40.0,
                'avg_roic': 9.0,
                'avg_debt_equity': 0.7
            }
        }
    
    def _load_quality_thresholds(self) -> Dict[str, Dict[str, float]]:
        """Load quality assessment thresholds"""
        return {
            'eps_growth': {
                'excellent': 20.0,
                'good': 10.0,
                'average': 5.0,
                'poor': 0.0
            },
            'gross_margin': {
                'excellent': 60.0,
                'good': 40.0,
                'average': 20.0,
                'poor': 10.0
            },
            'roic': {
                'excellent': 15.0,
                'good': 10.0,
                'average': 5.0,
                'poor': 0.0
            },
            'debt_to_equity': {
                'excellent': 0.3,
                'good': 0.6,
                'average': 1.0,
                'poor': 2.0
            }
        }
    
    def calculate_fair_value(self, symbol: str) -> FairValueResult:
        """Calculate comprehensive fair value analysis"""
        
        try:
            # Get fundamental data
            fundamentals = self._get_fundamentals(symbol)
            
            if not fundamentals:
                logger.warning(f"No fundamental data available for {symbol}")
                return self._create_empty_result(symbol)
            
            # Calculate different fair value methods
            peg_value = self._calculate_peg_value(fundamentals)
            pe_value = self._calculate_pe_value(fundamentals)
            dcf_value = self._calculate_dcf_value(fundamentals)
            
            # Weight the methods based on data quality and industry
            weighted_fair_value = self._weight_valuations(peg_value, pe_value, dcf_value, fundamentals)
            
            # Calculate valuation metrics
            valuation_metrics = self._calculate_valuation_metrics(weighted_fair_value, fundamentals)
            
            # Quality assessment
            quality_score = self._assess_quality(fundamentals)
            
            return FairValueResult(
                symbol=symbol,
                current_price=fundamentals.current_price,
                fair_value=weighted_fair_value,
                valuation_metrics=valuation_metrics,
                quality_score=quality_score,
                individual_valuations={
                    'peg_method': peg_value,
                    'pe_method': pe_value,
                    'dcf_method': dcf_value
                },
                fundamentals={
                    'eps_ttm': fundamentals.eps_ttm,
                    'eps_forward': fundamentals.eps_forward,
                    'eps_yoy_growth': fundamentals.eps_yoy_growth,
                    'revenue_yoy_growth': fundamentals.revenue_yoy_growth,
                    'gross_margin': fundamentals.gross_margin,
                    'roic': fundamentals.roic,
                    'debt_to_equity': fundamentals.debt_to_equity,
                    'current_pe': fundamentals.current_pe,
                    'forward_pe': fundamentals.forward_pe,
                    'peg_ratio': fundamentals.peg_ratio,
                    'industry': fundamentals.industry,
                    'market_cap': fundamentals.market_cap
                },
                updated_at=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error calculating fair value for {symbol}: {e}")
            return self._create_empty_result(symbol)
    
    def _get_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """Get fundamental data for a symbol"""
        
        try:
            with db.get_session() as session:
                # Get latest price
                price_query = """
                SELECT close
                FROM raw_market_data_daily
                WHERE symbol = :symbol
                ORDER BY date DESC
                LIMIT 1
                """
                result = session.execute(text(price_query), {"symbol": symbol})
                price_row = result.fetchone()
                
                if not price_row:
                    return None
                
                current_price = price_row[0]
                
                # Get fundamental data from fundamentals_snapshots
                fundamentals_query = """
                SELECT payload
                FROM fundamentals_snapshots
                WHERE UPPER(symbol) = UPPER(:symbol)
                ORDER BY as_of_date DESC
                LIMIT 1
                """
                result = session.execute(text(fundamentals_query), {"symbol": symbol})
                row = result.fetchone()
                
                if not row or not row[0]:
                    logger.info(f"No fundamental data available for {symbol}")
                    return None
                
                # Extract data from JSONB payload
                import json
                payload = row[0] if isinstance(row[0], dict) else json.loads(row[0]) if isinstance(row[0], str) else row[0]
                
                # Map JSONB fields to expected structure
                eps_ttm = payload.get('eps')
                eps_forward = payload.get('eps_forward')
                revenue_ttm = payload.get('revenue')
                market_cap = payload.get('market_cap')
                pe_ratio = payload.get('pe_ratio')
                
                # Create FundamentalData object from JSONB payload
                fundamentals = FundamentalData(
                    current_price=current_price,
                    eps_ttm=float(eps_ttm) if eps_ttm else None,
                    eps_forward=float(eps_forward) if eps_forward else None,
                    revenue_ttm=float(revenue_ttm) if revenue_ttm else None,
                    market_cap=float(market_cap) if market_cap else None,
                    pe_ttm=float(pe_ratio) if pe_ratio else None,
                    # Add other fields as needed from payload
                )
                
                return fundamentals
                
        except Exception as e:
            logger.error(f"Error getting fundamentals for {symbol}: {e}")
            return None
    
    def _calculate_peg_value(self, fundamentals: FundamentalData) -> float:
        """Calculate fair value based on PEG ratio"""
        
        if fundamentals.eps_ttm <= 0 or fundamentals.eps_yoy_growth <= 0:
            return fundamentals.current_price  # Fallback to current price
        
        # Get industry PEG benchmark
        industry = fundamentals.industry
        industry_peg = self.industry_benchmarks.get(industry, {}).get('avg_peg', 1.0)
        
        # Calculate fair P/E based on growth and industry benchmark
        fair_pe = fundamentals.eps_yoy_growth * 100 * industry_peg
        
        # Calculate fair price
        fair_price = fundamentals.eps_ttm * fair_pe
        
        return fair_price
    
    def _calculate_pe_value(self, fundamentals: FundamentalData) -> float:
        """Calculate fair value based on forward P/E"""
        
        if fundamentals.eps_forward <= 0:
            return fundamentals.current_price
        
        # Get industry P/E benchmark
        industry = fundamentals.industry
        industry_pe = self.industry_benchmarks.get(industry, {}).get('avg_pe', 18.0)
        
        # Adjust P/E based on growth rate
        growth_adjustment = min(fundamentals.eps_yoy_growth / 10.0, 1.5)  # Cap at 1.5x
        adjusted_pe = industry_pe * (1 + growth_adjustment)
        
        # Calculate fair price
        fair_price = fundamentals.eps_forward * adjusted_pe
        
        return fair_price
    
    def _calculate_dcf_value(self, fundamentals: FundamentalData) -> float:
        """Calculate fair value using simplified DCF analysis"""
        
        if fundamentals.free_cash_flow <= 0:
            return fundamentals.current_price
        
        # Assumptions for DCF
        growth_rate = min(fundamentals.eps_yoy_growth / 100, 0.20)  # Cap at 20%
        discount_rate = 0.10  # 10% discount rate
        terminal_growth = 0.03  # 3% terminal growth
        
        # 5-year FCF projections
        fcf_projections = []
        current_fcf = fundamentals.free_cash_flow
        
        for year in range(1, 6):
            projected_fcf = current_fcf * (1 + growth_rate) ** year
            fcf_projections.append(projected_fcf)
        
        # Calculate terminal value
        terminal_fcf = fcf_projections[-1]
        terminal_value = terminal_fcf * (1 + terminal_growth) / (discount_rate - terminal_growth)
        
        # Discount to present value
        pv_projections = sum(fcf / ((1 + discount_rate) ** year) for year, fcf in enumerate(fcf_projections, 1))
        pv_terminal = terminal_value / ((1 + discount_rate) ** 5)
        
        enterprise_value = pv_projections + pv_terminal
        
        # Convert to per-share value (simplified)
        if fundamentals.market_cap > 0:
            shares_outstanding = fundamentals.market_cap / fundamentals.current_price
            fair_price_per_share = enterprise_value / shares_outstanding
        else:
            fair_price_per_share = fundamentals.current_price
        
        return fair_price_per_share
    
    def _weight_valuations(self, peg_value: float, pe_value: float, dcf_value: float, 
                         fundamentals: FundamentalData) -> float:
        """Weight different valuation methods based on data quality"""
        
        weights = {'peg': 0.4, 'pe': 0.4, 'dcf': 0.2}  # Default weights
        
        # Adjust weights based on data quality
        if fundamentals.eps_yoy_growth <= 0 or fundamentals.eps_yoy_growth > 100:
            weights['peg'] *= 0.5  # Reduce PEG weight if growth data is unreliable
            weights['pe'] += 0.2  # Increase P/E weight
            weights['dcf'] += 0.1
        
        if fundamentals.eps_forward <= 0:
            weights['pe'] *= 0.5  # Reduce P/E weight if forward EPS is unreliable
            weights['peg'] += 0.2
            weights['dcf'] += 0.1
        
        if fundamentals.free_cash_flow <= 0:
            weights['dcf'] *= 0.3  # Reduce DCF weight if FCF is unreliable
            weights['peg'] += 0.35
            weights['pe'] += 0.35
        
        # Normalize weights
        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}
        
        # Calculate weighted fair value
        weighted_value = (
            peg_value * weights['peg'] +
            pe_value * weights['pe'] +
            dcf_value * weights['dcf']
        )
        
        return weighted_value
    
    def _calculate_valuation_metrics(self, fair_value: float, fundamentals: FundamentalData) -> Dict[str, Any]:
        """Calculate valuation metrics"""
        
        current_price = fundamentals.current_price
        valuation_ratio = current_price / fair_value
        
        # P/E comparison
        industry = fundamentals.industry
        industry_pe = self.industry_benchmarks.get(industry, {}).get('avg_pe', 18.0)
        pe_vs_industry = fundamentals.current_pe - industry_pe if fundamentals.current_pe else 0
        
        # Margin comparison
        industry_margin = self.industry_benchmarks.get(industry, {}).get('avg_margin', 30.0)
        margin_vs_industry = fundamentals.gross_margin - industry_margin
        
        return {
            'valuation_ratio': valuation_ratio,
            'undervaluation_pct': (1 - valuation_ratio) * 100,
            'pe_vs_industry': pe_vs_industry,
            'margin_vs_industry': margin_vs_industry,
            'valuation_rating': self._get_valuation_rating(valuation_ratio)
        }
    
    def _get_valuation_rating(self, valuation_ratio: float) -> str:
        """Get valuation rating based on price/fair value ratio"""
        if valuation_ratio < 0.7:
            return "Deeply Undervalued"
        elif valuation_ratio < 0.85:
            return "Undervalued"
        elif valuation_ratio < 1.0:
            return "Slightly Undervalued"
        elif valuation_ratio < 1.15:
            return "Fair Value"
        elif valuation_ratio < 1.3:
            return "Slightly Overvalued"
        else:
            return "Overvalued"
    
    def _assess_quality(self, fundamentals: FundamentalData) -> float:
        """Calculate overall quality score (0-100)"""
        
        scores = {}
        
        # EPS Growth Quality (25% weight)
        eps_growth = fundamentals.eps_yoy_growth
        scores['eps_growth'] = self._score_eps_growth(eps_growth)
        
        # Margin Quality (20% weight)
        gross_margin = fundamentals.gross_margin
        industry_avg = self.industry_benchmarks.get(fundamentals.industry, {}).get('avg_margin', 30.0)
        scores['margin'] = self._score_margin(gross_margin, industry_avg)
        
        # ROIC Quality (20% weight)
        roic = fundamentals.roic
        scores['roic'] = self._score_roic(roic)
        
        # Debt Quality (15% weight)
        debt_to_equity = fundamentals.debt_to_equity
        scores['debt'] = self._score_debt(debt_to_equity)
        
        # PEG Quality (20% weight)
        peg_ratio = fundamentals.peg_ratio
        scores['peg'] = self._score_peg(peg_ratio)
        
        # Weighted average
        weights = {
            'eps_growth': 0.25,
            'margin': 0.20,
            'roic': 0.20,
            'debt': 0.15,
            'peg': 0.20
        }
        
        total_score = sum(scores[key] * weights[key] for key in scores)
        return min(total_score, 100)
    
    def _score_eps_growth(self, eps_growth: float) -> float:
        """Score EPS growth (0-100)"""
        thresholds = self.quality_thresholds['eps_growth']
        
        if eps_growth >= thresholds['excellent']:
            return 90
        elif eps_growth >= thresholds['good']:
            return 75
        elif eps_growth >= thresholds['average']:
            return 60
        elif eps_growth >= thresholds['poor']:
            return 40
        else:
            return 20
    
    def _score_margin(self, margin: float, industry_avg: float) -> float:
        """Score gross margin relative to industry (0-100)"""
        if industry_avg == 0:
            return 50
        
        margin_vs_industry = margin - industry_avg
        
        if margin_vs_industry >= 10:
            return 90
        elif margin_vs_industry >= 5:
            return 75
        elif margin_vs_industry >= 0:
            return 60
        elif margin_vs_industry >= -5:
            return 40
        else:
            return 20
    
    def _score_roic(self, roic: float) -> float:
        """Score ROIC (0-100)"""
        thresholds = self.quality_thresholds['roic']
        
        if roic >= thresholds['excellent']:
            return 90
        elif roic >= thresholds['good']:
            return 75
        elif roic >= thresholds['average']:
            return 60
        elif roic >= thresholds['poor']:
            return 40
        else:
            return 20
    
    def _score_debt(self, debt_to_equity: float) -> float:
        """Score debt-to-equity (0-100) - lower is better"""
        thresholds = self.quality_thresholds['debt_to_equity']
        
        if debt_to_equity <= thresholds['excellent']:
            return 90
        elif debt_to_equity <= thresholds['good']:
            return 75
        elif debt_to_equity <= thresholds['average']:
            return 60
        elif debt_to_equity <= thresholds['poor']:
            return 40
        else:
            return 20
    
    def _score_peg(self, peg_ratio: float) -> float:
        """Score PEG ratio (0-100) - lower is better"""
        if peg_ratio <= 0:
            return 50  # Neutral for invalid data
        elif peg_ratio <= 0.5:
            return 90
        elif peg_ratio <= 1.0:
            return 75
        elif peg_ratio <= 1.5:
            return 60
        elif peg_ratio <= 2.0:
            return 40
        else:
            return 20
    
    def _create_empty_result(self, symbol: str) -> FairValueResult:
        """Create empty result when data is unavailable"""
        return FairValueResult(
            symbol=symbol,
            current_price=0.0,
            fair_value=0.0,
            valuation_metrics={},
            quality_score=0.0,
            individual_valuations={},
            fundamentals={},
            updated_at=datetime.now()
        )
    
    def get_top_undervalued_stocks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top undervalued stocks based on fair value analysis"""
        
        try:
            with db.get_session() as session:
                # Get list of stocks with fundamental data
                query = """
                SELECT DISTINCT symbol
                FROM fundamentals_snapshots
                WHERE payload->>'eps' IS NOT NULL
                AND (payload->>'eps')::numeric > 0
                AND as_of_date >= CURRENT_DATE - INTERVAL '7 days'
                LIMIT 100
                """
                
                result = session.execute(text(query))
                symbols = [row[0] for row in result.fetchall()]
                
                # Analyze each symbol
                undervalued_stocks = []
                
                for symbol in symbols:
                    try:
                        result = self.calculate_fair_value(symbol)
                        
                        if result.fair_value > 0 and result.current_price > 0:
                            valuation_ratio = result.current_price / result.fair_value
                            
                            if valuation_ratio < 0.9 and result.quality_score > 50:  # Undervalued + decent quality
                                undervalued_stocks.append({
                                    'symbol': symbol,
                                    'current_price': result.current_price,
                                    'fair_value': result.fair_value,
                                    'valuation_ratio': valuation_ratio,
                                    'undervaluation_pct': (1 - valuation_ratio) * 100,
                                    'quality_score': result.quality_score,
                                    'industry': result.fundamentals.get('industry', 'Unknown')
                                })
                    except Exception:
                        continue
                
                # Sort by undervaluation and quality
                undervalued_stocks.sort(key=lambda x: (x['undervaluation_pct'], x['quality_score']), reverse=True)
                
                return undervalued_stocks[:limit]
                
        except Exception as e:
            logger.error(f"Error getting top undervalued stocks: {e}")
            return []
    
    def get_industry_comparison(self, symbol: str) -> Dict[str, Any]:
        """Get industry comparison for a symbol"""
        
        try:
            result = self.calculate_fair_value(symbol)
            industry = result.fundamentals.get('industry', 'Unknown')
            
            if industry == 'Unknown':
                return {}
            
            # Get industry averages
            industry_bench = self.industry_benchmarks.get(industry, {})
            
            # Calculate comparisons
            comparisons = {
                'pe_vs_industry': result.fundamentals.get('current_pe', 0) - industry_bench.get('avg_pe', 0),
                'peg_vs_industry': result.fundamentals.get('peg_ratio', 0) - industry_bench.get('avg_peg', 0),
                'growth_vs_industry': result.fundamentals.get('eps_yoy_growth', 0) - industry_bench.get('avg_growth', 0),
                'margin_vs_industry': result.fundamentals.get('gross_margin', 0) - industry_bench.get('avg_margin', 0),
                'roic_vs_industry': result.fundamentals.get('roic', 0) - industry_bench.get('avg_roic', 0),
                'debt_vs_industry': result.fundamentals.get('debt_to_equity', 0) - industry_bench.get('avg_debt_equity', 0)
            }
            
            return {
                'industry': industry,
                'benchmarks': industry_bench,
                'comparisons': comparisons,
                'symbol_metrics': {
                    'pe': result.fundamentals.get('current_pe', 0),
                    'peg': result.fundamentals.get('peg_ratio', 0),
                    'growth': result.fundamentals.get('eps_yoy_growth', 0),
                    'margin': result.fundamentals.get('gross_margin', 0),
                    'roic': result.fundamentals.get('roic', 0),
                    'debt_to_equity': result.fundamentals.get('debt_to_equity', 0)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting industry comparison for {symbol}: {e}")
            return {}
