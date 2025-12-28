"""
Fundamental Scoring Service
Calculates fundamental scores and flags based on industry standards
Industry Standard: Financial analyst screening criteria
"""
from typing import Dict, Any, Optional
import json

from app.services.base import BaseService
from app.utils.database_helper import DatabaseQueryHelper


class FundamentalScorer(BaseService):
    """
    Scores stocks based on fundamental metrics
    Industry Standard Criteria:
    - Good Fundamentals: P/E < 25, PEG < 1.5, Revenue Growth > 10%, EPS Growth > 15%, Profit Margin > 10%, Debt/Equity < 1.0
    - Growth Stock: Revenue Growth 15-25%, EPS Growth 20-30%
    - Exponential Growth: Revenue Growth > 25%, EPS Growth > 30%, Accelerating growth
    """
    
    # Industry Standard Thresholds
    GOOD_PE_RATIO_MAX = 25.0  # P/E ratio < 25 considered reasonable
    EXCELLENT_PE_RATIO_MAX = 15.0  # P/E ratio < 15 considered excellent value
    
    GOOD_PEG_RATIO_MAX = 1.5  # PEG < 1.5 is good
    EXCELLENT_PEG_RATIO_MAX = 1.0  # PEG < 1.0 is excellent
    
    GOOD_REVENUE_GROWTH_MIN = 10.0  # Revenue growth > 10% YoY
    GROWTH_REVENUE_GROWTH_MIN = 15.0  # Growth stock: 15-25%
    GROWTH_REVENUE_GROWTH_MAX = 25.0
    EXPONENTIAL_REVENUE_GROWTH_MIN = 25.0  # Exponential growth: > 25%
    
    GOOD_EPS_GROWTH_MIN = 15.0  # EPS growth > 15% YoY
    GROWTH_EPS_GROWTH_MIN = 20.0  # Growth stock: 20-30%
    GROWTH_EPS_GROWTH_MAX = 30.0
    EXPONENTIAL_EPS_GROWTH_MIN = 30.0  # Exponential growth: > 30%
    
    GOOD_PROFIT_MARGIN_MIN = 10.0  # Profit margin > 10%
    EXCELLENT_PROFIT_MARGIN_MIN = 20.0  # Profit margin > 20% is excellent
    
    GOOD_DEBT_TO_EQUITY_MAX = 1.0  # Debt/Equity < 1.0 is low debt
    GOOD_CURRENT_RATIO_MIN = 1.5  # Current ratio > 1.5 is good liquidity
    
    def __init__(self):
        """Initialize fundamental scorer"""
        super().__init__()
    
    def score_fundamentals(self, fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score fundamentals and determine flags
        
        Args:
            fundamental_data: Dictionary with fundamental metrics
        
        Returns:
            Dictionary with:
            - fundamental_score: 0-100 score
            - has_good_fundamentals: Boolean flag
            - is_growth_stock: Boolean flag
            - is_exponential_growth: Boolean flag
            - breakdown: Detailed scoring breakdown
        """
        if not fundamental_data:
            return {
                'fundamental_score': 0.0,
                'has_good_fundamentals': False,
                'is_growth_stock': False,
                'is_exponential_growth': False,
                'breakdown': {}
            }
        
        score = 0.0
        max_score = 0.0
        breakdown = {}
        
        # 1. P/E Ratio (20 points max)
        pe_ratio = fundamental_data.get('pe_ratio') or fundamental_data.get('trailingPE')
        if pe_ratio is not None and pe_ratio > 0:
            max_score += 20
            if pe_ratio <= self.EXCELLENT_PE_RATIO_MAX:
                score += 20
                breakdown['pe_ratio'] = {'score': 20, 'value': pe_ratio, 'status': 'excellent'}
            elif pe_ratio <= self.GOOD_PE_RATIO_MAX:
                score += 15
                breakdown['pe_ratio'] = {'score': 15, 'value': pe_ratio, 'status': 'good'}
            else:
                score += max(0, 10 - (pe_ratio - self.GOOD_PE_RATIO_MAX) * 0.5)
                breakdown['pe_ratio'] = {'score': score, 'value': pe_ratio, 'status': 'fair'}
        
        # 2. PEG Ratio (15 points max) - Price/Earnings to Growth ratio
        forward_pe = fundamental_data.get('forwardPE')
        if pe_ratio and forward_pe and pe_ratio > 0:
            # Estimate PEG (simplified: forward PE / growth rate estimate)
            # If we have revenue growth, use that as proxy
            revenue_growth = fundamental_data.get('revenue_growth_yoy', 0)
            if revenue_growth > 0:
                peg_estimate = forward_pe / revenue_growth
                max_score += 15
                if peg_estimate <= self.EXCELLENT_PEG_RATIO_MAX:
                    score += 15
                    breakdown['peg_ratio'] = {'score': 15, 'value': peg_estimate, 'status': 'excellent'}
                elif peg_estimate <= self.GOOD_PEG_RATIO_MAX:
                    score += 12
                    breakdown['peg_ratio'] = {'score': 12, 'value': peg_estimate, 'status': 'good'}
                else:
                    breakdown['peg_ratio'] = {'score': 0, 'value': peg_estimate, 'status': 'poor'}
        
        # 3. Revenue Growth (20 points max)
        revenue_growth = fundamental_data.get('revenue_growth_yoy') or fundamental_data.get('revenueGrowth')
        if revenue_growth is not None:
            max_score += 20
            if revenue_growth >= self.EXPONENTIAL_REVENUE_GROWTH_MIN:
                score += 20
                breakdown['revenue_growth'] = {'score': 20, 'value': revenue_growth, 'status': 'exponential'}
            elif revenue_growth >= self.GROWTH_REVENUE_GROWTH_MIN:
                score += 15
                breakdown['revenue_growth'] = {'score': 15, 'value': revenue_growth, 'status': 'growth'}
            elif revenue_growth >= self.GOOD_REVENUE_GROWTH_MIN:
                score += 10
                breakdown['revenue_growth'] = {'score': 10, 'value': revenue_growth, 'status': 'good'}
            else:
                breakdown['revenue_growth'] = {'score': 0, 'value': revenue_growth, 'status': 'poor'}
        
        # 4. EPS Growth (20 points max)
        eps_growth = fundamental_data.get('eps_growth_yoy') or fundamental_data.get('earningsGrowth')
        if eps_growth is not None:
            max_score += 20
            if eps_growth >= self.EXPONENTIAL_EPS_GROWTH_MIN:
                score += 20
                breakdown['eps_growth'] = {'score': 20, 'value': eps_growth, 'status': 'exponential'}
            elif eps_growth >= self.GROWTH_EPS_GROWTH_MIN:
                score += 15
                breakdown['eps_growth'] = {'score': 15, 'value': eps_growth, 'status': 'growth'}
            elif eps_growth >= self.GOOD_EPS_GROWTH_MIN:
                score += 10
                breakdown['eps_growth'] = {'score': 10, 'value': eps_growth, 'status': 'good'}
            else:
                breakdown['eps_growth'] = {'score': 0, 'value': eps_growth, 'status': 'poor'}
        
        # 5. Profit Margin (15 points max)
        profit_margin = fundamental_data.get('profit_margin') or fundamental_data.get('profitMargins')
        if profit_margin is not None:
            profit_margin_pct = profit_margin * 100 if profit_margin < 1 else profit_margin
            max_score += 15
            if profit_margin_pct >= self.EXCELLENT_PROFIT_MARGIN_MIN:
                score += 15
                breakdown['profit_margin'] = {'score': 15, 'value': profit_margin_pct, 'status': 'excellent'}
            elif profit_margin_pct >= self.GOOD_PROFIT_MARGIN_MIN:
                score += 10
                breakdown['profit_margin'] = {'score': 10, 'value': profit_margin_pct, 'status': 'good'}
            else:
                breakdown['profit_margin'] = {'score': 0, 'value': profit_margin_pct, 'status': 'poor'}
        
        # 6. Debt-to-Equity (10 points max)
        debt_to_equity = fundamental_data.get('debt_to_equity') or fundamental_data.get('debtToEquity')
        if debt_to_equity is not None:
            max_score += 10
            if debt_to_equity <= self.GOOD_DEBT_TO_EQUITY_MAX:
                score += 10
                breakdown['debt_to_equity'] = {'score': 10, 'value': debt_to_equity, 'status': 'good'}
            else:
                score += max(0, 5 - (debt_to_equity - self.GOOD_DEBT_TO_EQUITY_MAX) * 2)
                breakdown['debt_to_equity'] = {'score': score, 'value': debt_to_equity, 'status': 'fair'}
        
        # Normalize score to 0-100
        if max_score > 0:
            normalized_score = (score / max_score) * 100
        else:
            normalized_score = 0.0
        
        # Determine flags
        has_good_fundamentals = (
            (pe_ratio is None or pe_ratio <= self.GOOD_PE_RATIO_MAX) and
            (revenue_growth is None or revenue_growth >= self.GOOD_REVENUE_GROWTH_MIN) and
            (eps_growth is None or eps_growth >= self.GOOD_EPS_GROWTH_MIN) and
            (profit_margin is None or (profit_margin * 100 if profit_margin < 1 else profit_margin) >= self.GOOD_PROFIT_MARGIN_MIN) and
            (debt_to_equity is None or debt_to_equity <= self.GOOD_DEBT_TO_EQUITY_MAX) and
            normalized_score >= 60.0  # At least 60% score
        )
        
        is_growth_stock = (
            (revenue_growth is not None and 
             self.GROWTH_REVENUE_GROWTH_MIN <= revenue_growth <= self.GROWTH_REVENUE_GROWTH_MAX) and
            (eps_growth is not None and 
             self.GROWTH_EPS_GROWTH_MIN <= eps_growth <= self.GROWTH_EPS_GROWTH_MAX)
        )
        
        is_exponential_growth = (
            (revenue_growth is not None and revenue_growth >= self.EXPONENTIAL_REVENUE_GROWTH_MIN) and
            (eps_growth is not None and eps_growth >= self.EXPONENTIAL_EPS_GROWTH_MIN)
        )
        
        return {
            'fundamental_score': round(normalized_score, 2),
            'has_good_fundamentals': has_good_fundamentals,
            'is_growth_stock': is_growth_stock,
            'is_exponential_growth': is_exponential_growth,
            'breakdown': breakdown
        }

