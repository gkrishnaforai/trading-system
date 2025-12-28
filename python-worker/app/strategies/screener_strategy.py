"""
Screener Strategy
User-defined screening strategies for filtering stocks
Industry Standard: Stock screening like Finviz, TradingView, Yahoo Finance
"""
from typing import Dict, Any, Optional, List
import pandas as pd

from app.strategies.base import BaseStrategy, StrategyResult
from app.exceptions import ValidationError


class ScreenerStrategy(BaseStrategy):
    """
    Pluggable screener strategy that allows users to define custom screening criteria
    
    Supports:
    - Price vs Moving Averages (below SMA50, below SMA200)
    - Fundamental filters (good fundamentals, growth stocks, exponential growth)
    - Technical filters (RSI, MACD, trend)
    - Custom combinations
    
    Industry Standard: Similar to Finviz, TradingView, Yahoo Finance screeners
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize screener strategy
        
        Config options:
        - price_below_sma50: Boolean - Filter for stocks below 50-day average
        - price_below_sma200: Boolean - Filter for stocks below 200-day average
        - has_good_fundamentals: Boolean - Filter for good fundamentals
        - is_growth_stock: Boolean - Filter for growth stocks
        - is_exponential_growth: Boolean - Filter for exponential growth stocks
        - min_fundamental_score: Float (0-100) - Minimum fundamental score
        - min_rsi: Float - Minimum RSI value
        - max_rsi: Float - Maximum RSI value
        - trend_filter: String - 'bullish', 'bearish', 'neutral', or None
        - min_market_cap: Float - Minimum market cap
        - max_pe_ratio: Float - Maximum P/E ratio
        """
        super().__init__(config)
        
        # Default config
        self.price_below_sma50 = self.config.get('price_below_sma50', False)
        self.price_below_sma200 = self.config.get('price_below_sma200', False)
        self.has_good_fundamentals = self.config.get('has_good_fundamentals', False)
        self.is_growth_stock = self.config.get('is_growth_stock', False)
        self.is_exponential_growth = self.config.get('is_exponential_growth', False)
        self.min_fundamental_score = self.config.get('min_fundamental_score', 0.0)
        self.min_rsi = self.config.get('min_rsi', None)
        self.max_rsi = self.config.get('max_rsi', None)
        self.trend_filter = self.config.get('trend_filter', None)
        self.min_market_cap = self.config.get('min_market_cap', None)
        self.max_pe_ratio = self.config.get('max_pe_ratio', None)
    
    def get_name(self) -> str:
        return "screener"
    
    def get_description(self) -> str:
        """Return description of current screener configuration"""
        filters = []
        if self.price_below_sma50:
            filters.append("Price below 50-day average")
        if self.price_below_sma200:
            filters.append("Price below 200-day average")
        if self.has_good_fundamentals:
            filters.append("Good fundamentals")
        if self.is_growth_stock:
            filters.append("Growth stock")
        if self.is_exponential_growth:
            filters.append("Exponential growth")
        if self.min_fundamental_score > 0:
            filters.append(f"Fundamental score >= {self.min_fundamental_score}")
        
        if not filters:
            return "Screener strategy (no filters applied)"
        return f"Screener: {', '.join(filters)}"
    
    def generate_signal(
        self,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> StrategyResult:
        """
        Generate signal based on screener criteria
        
        Returns:
            StrategyResult with:
            - signal: 'buy' if passes all filters, 'hold' otherwise
            - confidence: Based on how many filters pass
            - reason: Explanation of why it passed/failed
            - metadata: Detailed filter results
        """
        passed_filters = []
        failed_filters = []
        metadata = {}
        
        # Get current price
        price = indicators.get('price')
        if isinstance(price, pd.Series):
            price = price.iloc[-1] if len(price) > 0 else None
        elif price is None:
            price = indicators.get('close')
            if isinstance(price, pd.Series):
                price = price.iloc[-1] if len(price) > 0 else None
        
        # 1. Price vs SMA50 filter
        if self.price_below_sma50:
            sma50 = indicators.get('sma50')
            if isinstance(sma50, pd.Series):
                sma50 = sma50.iloc[-1] if len(sma50) > 0 else None
            
            if price and sma50:
                if price < sma50:
                    passed_filters.append('price_below_sma50')
                    metadata['price_below_sma50'] = {
                        'passed': True,
                        'price': price,
                        'sma50': sma50,
                        'discount_pct': ((sma50 - price) / sma50) * 100
                    }
                else:
                    failed_filters.append('price_below_sma50')
                    metadata['price_below_sma50'] = {
                        'passed': False,
                        'price': price,
                        'sma50': sma50,
                        'premium_pct': ((price - sma50) / sma50) * 100
                    }
            else:
                failed_filters.append('price_below_sma50')
                metadata['price_below_sma50'] = {'passed': False, 'reason': 'Missing data'}
        
        # 2. Price vs SMA200 filter
        if self.price_below_sma200:
            sma200 = indicators.get('sma200')
            if isinstance(sma200, pd.Series):
                sma200 = sma200.iloc[-1] if len(sma200) > 0 else None
            
            if price and sma200:
                if price < sma200:
                    passed_filters.append('price_below_sma200')
                    metadata['price_below_sma200'] = {
                        'passed': True,
                        'price': price,
                        'sma200': sma200,
                        'discount_pct': ((sma200 - price) / sma200) * 100
                    }
                else:
                    failed_filters.append('price_below_sma200')
                    metadata['price_below_sma200'] = {
                        'passed': False,
                        'price': price,
                        'sma200': sma200,
                        'premium_pct': ((price - sma200) / sma200) * 100
                    }
            else:
                failed_filters.append('price_below_sma200')
                metadata['price_below_sma200'] = {'passed': False, 'reason': 'Missing data'}
        
        # 3. Good fundamentals filter (from context or indicators)
        if self.has_good_fundamentals:
            # Check if flag is in context (set during indicator calculation)
            has_good_fundamentals = context.get('has_good_fundamentals', False) if context else False
            if has_good_fundamentals:
                passed_filters.append('has_good_fundamentals')
                metadata['has_good_fundamentals'] = {'passed': True}
            else:
                failed_filters.append('has_good_fundamentals')
                metadata['has_good_fundamentals'] = {'passed': False}
        
        # 4. Growth stock filter
        if self.is_growth_stock:
            is_growth = context.get('is_growth_stock', False) if context else False
            if is_growth:
                passed_filters.append('is_growth_stock')
                metadata['is_growth_stock'] = {'passed': True}
            else:
                failed_filters.append('is_growth_stock')
                metadata['is_growth_stock'] = {'passed': False}
        
        # 5. Exponential growth filter
        if self.is_exponential_growth:
            is_exp_growth = context.get('is_exponential_growth', False) if context else False
            if is_exp_growth:
                passed_filters.append('is_exponential_growth')
                metadata['is_exponential_growth'] = {'passed': True}
            else:
                failed_filters.append('is_exponential_growth')
                metadata['is_exponential_growth'] = {'passed': False}
        
        # 6. Minimum fundamental score
        if self.min_fundamental_score > 0:
            fundamental_score = context.get('fundamental_score', 0.0) if context else 0.0
            if fundamental_score >= self.min_fundamental_score:
                passed_filters.append('min_fundamental_score')
                metadata['fundamental_score'] = {
                    'passed': True,
                    'score': fundamental_score,
                    'threshold': self.min_fundamental_score
                }
            else:
                failed_filters.append('min_fundamental_score')
                metadata['fundamental_score'] = {
                    'passed': False,
                    'score': fundamental_score,
                    'threshold': self.min_fundamental_score
                }
        
        # 7. RSI filter
        if self.min_rsi is not None or self.max_rsi is not None:
            rsi = indicators.get('rsi')
            if isinstance(rsi, pd.Series):
                rsi = rsi.iloc[-1] if len(rsi) > 0 else None
            
            if rsi is not None:
                rsi_passed = True
                if self.min_rsi is not None and rsi < self.min_rsi:
                    rsi_passed = False
                if self.max_rsi is not None and rsi > self.max_rsi:
                    rsi_passed = False
                
                if rsi_passed:
                    passed_filters.append('rsi_filter')
                    metadata['rsi'] = {'passed': True, 'value': rsi}
                else:
                    failed_filters.append('rsi_filter')
                    metadata['rsi'] = {'passed': False, 'value': rsi}
            else:
                failed_filters.append('rsi_filter')
                metadata['rsi'] = {'passed': False, 'reason': 'Missing data'}
        
        # 8. Trend filter
        if self.trend_filter:
            long_term_trend = indicators.get('long_term_trend')
            if isinstance(long_term_trend, pd.Series):
                long_term_trend = long_term_trend.iloc[-1] if len(long_term_trend) > 0 else None
            
            if long_term_trend == self.trend_filter:
                passed_filters.append('trend_filter')
                metadata['trend'] = {'passed': True, 'value': long_term_trend}
            else:
                failed_filters.append('trend_filter')
                metadata['trend'] = {'passed': False, 'value': long_term_trend, 'required': self.trend_filter}
        
        # Determine signal
        total_filters = len(passed_filters) + len(failed_filters)
        if total_filters == 0:
            # No filters configured
            signal = 'hold'
            confidence = 0.5
            reason = "No screener filters configured"
        elif len(failed_filters) == 0:
            # All filters passed
            signal = 'buy'
            confidence = min(1.0, 0.5 + (len(passed_filters) / max(total_filters, 1)) * 0.5)
            reason = f"Passes all {len(passed_filters)} screener filters"
        else:
            # Some filters failed
            signal = 'hold'
            confidence = len(passed_filters) / max(total_filters, 1)
            reason = f"Passes {len(passed_filters)}/{total_filters} filters. Failed: {', '.join(failed_filters)}"
        
        return StrategyResult(
            signal=signal,
            confidence=confidence,
            reason=reason,
            metadata={
                'passed_filters': passed_filters,
                'failed_filters': failed_filters,
                'filter_details': metadata,
                'total_filters': total_filters
            },
            strategy_name=self.get_name()
        )

