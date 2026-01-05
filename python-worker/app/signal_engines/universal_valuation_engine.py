"""
Universal Valuation Engine
Configurable fundamental valuation engine that adapts to sector, market cap, and growth stage
"""

from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from .base import (
    BaseSignalEngine, SignalResult, SignalType, SignalEngineError,
    InsufficientDataError, MarketRegime, EngineTier
)
from app.observability.logging import get_logger

logger = get_logger(__name__)


class UniversalValuationEngine(BaseSignalEngine):
    """
    Universal valuation engine with sector-specific configuration
    
    Uses same calculation logic for all stocks but adapts inputs based on:
    - Sector (Tech, Financials, Energy, Real Estate, etc.)
    - Market cap (Mega, Large, Mid, Small, Micro)
    - Growth stage (High-growth, Profitable, Mature)
    
    Formula: Fair_Value = Base_Value × Growth_Score × Quality_Score × Risk_Score
    """
    
    def __init__(self):
        super().__init__()
        self.engine_name = "universal_valuation"
        self.engine_version = "1.0.0"
        self.min_data_length = 20
        
        # Load configurations
        self.sector_config = self._load_sector_config()
        self.marketcap_config = self._load_marketcap_config()
    
    def generate_signal(
        self,
        symbol: str,
        market_data: pd.DataFrame,
        indicators: Dict[str, Any],
        fundamentals: Dict[str, Any],
        market_context
    ) -> SignalResult:
        """
        Generate valuation-based signal
        
        Args:
            symbol: Stock symbol
            market_data: Historical price data
            indicators: Technical indicators
            fundamentals: Fundamental data
            market_context: Market regime context
            
        Returns:
            SignalResult with valuation analysis
        """
        try:
            # Validate inputs
            self.validate_inputs(symbol, market_data, indicators, fundamentals, market_context)
            
            # Classify stock to determine which config to use
            stock_type = self._classify_stock(fundamentals)
            config = self._get_config(stock_type)
            
            if config is None:
                return self._create_signal_result(
                    symbol=symbol,
                    signal=SignalType.HOLD,
                    confidence=0.1,
                    reasoning=[f"Unable to value {stock_type} - insufficient data"],
                    position_size_pct=0.0,
                    timeframe='position'
                )
            
            # Get current price
            current_price = market_data.iloc[-1]['close']
            
            # Calculate base value using primary metric
            base_value, base_reasoning = self._calculate_base_value(
                fundamentals, config, market_context
            )
            
            if base_value is None or base_value <= 0:
                return self._create_signal_result(
                    symbol=symbol,
                    signal=SignalType.HOLD,
                    confidence=0.2,
                    reasoning=base_reasoning + ["Cannot calculate fair value - missing key metrics"],
                    position_size_pct=0.0,
                    timeframe='position'
                )
            
            # Calculate component scores
            growth_score, growth_reasoning = self._calculate_growth_score(
                fundamentals, config
            )
            
            quality_score, quality_reasoning = self._calculate_quality_score(
                fundamentals, config
            )
            
            risk_score, risk_reasoning = self._calculate_risk_score(
                fundamentals, config, market_context
            )
            
            # Apply market cap adjustments
            marketcap_tier, cap_adjustments = self._get_marketcap_adjustments(
                fundamentals.get('market_cap', 0)
            )

            expect_adj, expect_reason = self._calculate_expectation_adjustment(
                fundamentals, config
            )
            
            # Calculate final multiplier
            weights = config.get('weights', {})
            growth_mult = 1 + (growth_score - 1) * weights.get('growth', 0.3)
            quality_mult = 1 + (quality_score - 1) * weights.get('quality', 0.3)
            risk_mult = 1 + (risk_score - 1) * weights.get('risk', 0.2)
            
            total_multiplier = growth_mult * quality_mult * risk_mult
            
            # Apply market cap adjustments
            adjusted_multiplier = (total_multiplier * 
                                 cap_adjustments['risk_discount'] * 
                                 cap_adjustments['liquidity_premium'])
            
            adjusted_multiplier *= expect_adj
            
            # Calculate fair value
            fair_value = base_value * adjusted_multiplier
            
            # Calculate upside/downside
            upside_pct = (fair_value - current_price) / current_price * 100
            
            # Determine signal based on valuation gap
            signal, confidence, signal_reasoning = self._determine_valuation_signal(
                upside_pct, market_context, quality_score
            )
            
            # Calculate position size
            position_size = self._calculate_position_size(
                signal, confidence, upside_pct, market_context
            )
            
            # Calculate entry/exit levels
            entry_range, stop_loss, take_profit = self._calculate_value_levels(
                signal, current_price, fair_value, confidence
            )
            
            # Combine all reasoning
            reasoning = (base_reasoning + growth_reasoning + quality_reasoning + 
                        risk_reasoning + signal_reasoning)
            
            reasoning.append(f"Fair value: ${fair_value:.2f} (current: ${current_price:.2f})")
            reasoning.append(f"Valuation gap: {upside_pct:+.1f}%")
            reasoning.append(f"Market cap tier: {marketcap_tier}")
            
            return self._create_signal_result(
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                reasoning=reasoning,
                position_size_pct=position_size,
                entry_price_range=entry_range,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timeframe='position',
                metadata={
                    'stock_type': stock_type,
                    'fair_value': fair_value,
                    'current_price': current_price,
                    'upside_pct': upside_pct,
                    'base_value': base_value,
                    'total_multiplier': adjusted_multiplier,
                    'growth_score': growth_score,
                    'quality_score': quality_score,
                    'risk_score': risk_score,
                    'marketcap_tier': marketcap_tier,
                    'primary_metric': config.get('primary_metric'),
                    'primary_multiple': config.get('primary_multiple')
                }
            )
            
        except Exception as e:
            if isinstance(e, SignalEngineError):
                raise
            raise SignalEngineError(
                f"Failed to generate universal valuation signal: {str(e)}", 
                self.engine_name, symbol
            )
    
    def _load_sector_config(self) -> Dict[str, Any]:
        """Load sector-specific configurations"""
        return {
            'technology': {
                'profitable': {
                    'primary_metric': 'eps',
                    'primary_multiple': 'pe',
                    'base_pe': 25,
                    'growth_metrics': ['revenue_growth', 'earnings_growth'],
                    'quality_metrics': ['roe', 'gross_margin', 'fcf_margin'],
                    'risk_metrics': ['debt_to_equity', 'earnings_volatility'],
                    'weights': {'growth': 0.40, 'quality': 0.30, 'risk': 0.20}
                },
                'high_growth': {
                    'primary_metric': 'revenue',
                    'primary_multiple': 'ps',
                    'base_ps': 8,
                    'growth_metrics': ['revenue_growth', 'user_growth'],
                    'quality_metrics': ['gross_margin', 'burn_rate'],
                    'risk_metrics': ['cash_runway', 'revenue_volatility'],
                    'weights': {'growth': 0.50, 'quality': 0.25, 'risk': 0.15}
                }
            },
            'financials': {
                'banks': {
                    'primary_metric': 'book_value',
                    'primary_multiple': 'pb',
                    'base_pb': 1.2,
                    'growth_metrics': ['loan_growth', 'deposit_growth'],
                    'quality_metrics': ['roe', 'efficiency_ratio'],
                    'risk_metrics': ['npl_ratio', 'tier1_capital'],
                    'weights': {'growth': 0.20, 'quality': 0.40, 'risk': 0.30}
                }
            },
            'energy': {
                'oil_gas': {
                    'primary_metric': 'ebitda',
                    'primary_multiple': 'ev_ebitda',
                    'base_ev_ebitda': 6,
                    'growth_metrics': ['production_growth', 'reserve_growth'],
                    'quality_metrics': ['roic', 'operating_margin'],
                    'risk_metrics': ['debt_to_ebitda', 'oil_price_sensitivity'],
                    'weights': {'growth': 0.25, 'quality': 0.30, 'risk': 0.30},
                    'cycle_aware': True
                }
            },
            'real_estate': {
                'reits': {
                    'primary_metric': 'ffo',
                    'primary_multiple': 'p_ffo',
                    'base_p_ffo': 18,
                    'growth_metrics': ['ffo_growth', 'noi_growth'],
                    'quality_metrics': ['occupancy_rate', 'ffo_dividend_coverage'],
                    'risk_metrics': ['debt_to_ebitda', 'interest_coverage'],
                    'weights': {'growth': 0.25, 'quality': 0.35, 'risk': 0.30}
                }
            },
            'default': {
                'profitable': {
                    'primary_metric': 'eps',
                    'primary_multiple': 'pe',
                    'base_pe': 18,
                    'growth_metrics': ['revenue_growth', 'earnings_growth'],
                    'quality_metrics': ['roe', 'operating_margin'],
                    'risk_metrics': ['debt_to_equity', 'current_ratio'],
                    'weights': {'growth': 0.35, 'quality': 0.30, 'risk': 0.25}
                }
            }
        }
    
    def _load_marketcap_config(self) -> Dict[str, Any]:
        """Load market cap adjustment configurations"""
        return {
            'mega_cap': {
                'threshold': 200e9,
                'risk_discount': 0.95,
                'liquidity_premium': 1.05,
                'growth_dampener': 0.90
            },
            'large_cap': {
                'threshold': 10e9,
                'risk_discount': 1.0,
                'liquidity_premium': 1.0,
                'growth_dampener': 1.0
            },
            'mid_cap': {
                'threshold': 2e9,
                'risk_discount': 1.05,
                'liquidity_premium': 0.95,
                'growth_dampener': 1.10
            },
            'small_cap': {
                'threshold': 300e6,
                'risk_discount': 1.15,
                'liquidity_premium': 0.85,
                'growth_dampener': 1.25
            },
            'micro_cap': {
                'threshold': 0,
                'risk_discount': 1.30,
                'liquidity_premium': 0.70,
                'growth_dampener': 1.40
            }
        }
    
    def _classify_stock(self, fundamentals: Dict[str, Any]) -> str:
        """Classify stock to determine which config to use"""
        sector = fundamentals.get('sector', 'unknown').lower()
        net_income = fundamentals.get('net_income', 0)
        net_margin = fundamentals.get('net_margin', 0)
        revenue = fundamentals.get('revenue', 0)
        
        # Technology classification
        if sector == 'technology':
            if net_income > 0 and net_margin > 0.10:
                return 'technology.profitable'
            else:
                return 'technology.high_growth'
        
        # Financials classification
        elif sector == 'financials':
            industry = fundamentals.get('industry', '').lower()
            if 'bank' in industry:
                return 'financials.banks'
        
        # Energy classification
        elif sector == 'energy':
            return 'energy.oil_gas'
        
        # Real Estate classification
        elif sector == 'real estate':
            return 'real_estate.reits'
        
        # Default classification
        if net_income > 0:
            return 'default.profitable'
        else:
            return 'unknown'
    
    def _get_config(self, stock_type: str) -> Optional[Dict[str, Any]]:
        """Get configuration for stock type"""
        parts = stock_type.split('.')
        if len(parts) != 2:
            return None
        
        sector, category = parts
        
        if sector in self.sector_config:
            return self.sector_config[sector].get(category)
        
        return None
    
    def _calculate_base_value(
        self, fundamentals: Dict[str, Any], config: Dict[str, Any], market_context
    ) -> Tuple[Optional[float], List[str]]:
        """Calculate base value using primary metric"""
        reasoning = []
        
        primary_metric = config.get('primary_metric')
        primary_multiple_key = config.get('primary_multiple')
        
        # Get metric value
        metric_value = fundamentals.get(primary_metric)
        
        if metric_value is None or metric_value <= 0:
            reasoning.append(f"Missing or invalid {primary_metric}")
            return None, reasoning
        
        # Get base multiple
        base_multiple_key = f"base_{primary_multiple_key}"
        base_multiple = config.get(base_multiple_key, 15)
        
        # Adjust for cycle if needed
        if config.get('cycle_aware', False):
            # In bear markets, use lower multiples
            if market_context.regime == MarketRegime.BEAR:
                base_multiple *= 0.8
                reasoning.append(f"Base multiple adjusted for bear market")
        
        base_value = metric_value * base_multiple
        
        reasoning.append(
            f"Base valuation: {primary_metric}=${metric_value:.2f} × {primary_multiple_key}={base_multiple:.1f}"
        )
        
        return base_value, reasoning
    
    def _calculate_growth_score(
        self, fundamentals: Dict[str, Any], config: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """Calculate normalized growth score"""
        reasoning = []
        scores = []
        
        growth_metrics = config.get('growth_metrics', [])
        
        for metric in growth_metrics:
            value = fundamentals.get(metric, 0)
            
            # Normalize growth rates
            if 'growth' in metric:
                if value > 0.30:  # >30% growth
                    normalized = 1.5
                    reasoning.append(f"Strong {metric}: {value*100:.1f}%")
                elif value > 0.15:  # >15% growth
                    normalized = 1.2
                    reasoning.append(f"Good {metric}: {value*100:.1f}%")
                elif value > 0.05:  # >5% growth
                    normalized = 1.0
                elif value > 0:  # Positive growth
                    normalized = 0.9
                else:  # Negative growth
                    normalized = 0.7
                    reasoning.append(f"Weak {metric}: {value*100:.1f}%")
                
                scores.append(normalized)
        
        if not scores:
            return 1.0, ["No growth metrics available"]
        
        avg_score = sum(scores) / len(scores)
        avg_score = max(0.5, min(2.0, avg_score))  # Cap at 0.5-2.0
        
        return avg_score, reasoning
    
    def _calculate_quality_score(
        self, fundamentals: Dict[str, Any], config: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """Calculate normalized quality score"""
        reasoning = []
        scores = []
        
        quality_metrics = config.get('quality_metrics', [])
        
        for metric in quality_metrics:
            value = fundamentals.get(metric, 0)
            
            # ROE scoring
            if metric == 'roe':
                if value > 0.25:  # >25% ROE
                    normalized = 1.4
                    reasoning.append(f"Excellent ROE: {value*100:.1f}%")
                elif value > 0.15:  # >15% ROE
                    normalized = 1.2
                    reasoning.append(f"Good ROE: {value*100:.1f}%")
                elif value > 0.10:  # >10% ROE
                    normalized = 1.0
                else:
                    normalized = 0.8
                    reasoning.append(f"Low ROE: {value*100:.1f}%")
                scores.append(normalized)
            
            # Margin scoring
            elif 'margin' in metric:
                if value > 0.30:  # >30% margin
                    normalized = 1.3
                    reasoning.append(f"High {metric}: {value*100:.1f}%")
                elif value > 0.20:  # >20% margin
                    normalized = 1.1
                elif value > 0.10:  # >10% margin
                    normalized = 1.0
                else:
                    normalized = 0.9
                    reasoning.append(f"Low {metric}: {value*100:.1f}%")
                scores.append(normalized)
            
            # Other quality metrics (higher is better)
            else:
                if value > 0:
                    normalized = min(1.3, 1 + (value * 0.5))
                else:
                    normalized = 0.8
                scores.append(normalized)
        
        if not scores:
            return 1.0, ["No quality metrics available"]
        
        avg_score = sum(scores) / len(scores)
        avg_score = max(0.6, min(1.5, avg_score))  # Cap at 0.6-1.5
        
        return avg_score, reasoning
    
    def _calculate_risk_score(
        self, fundamentals: Dict[str, Any], config: Dict[str, Any], market_context
    ) -> Tuple[float, List[str]]:
        """Calculate normalized risk score (lower risk = higher score)"""
        reasoning = []
        scores = []
        
        risk_metrics = config.get('risk_metrics', [])
        
        for metric in risk_metrics:
            value = fundamentals.get(metric, 0)
            
            # Debt metrics (lower is better)
            if 'debt' in metric:
                if value < 0.3:  # <0.3 debt ratio
                    normalized = 1.2
                    reasoning.append(f"Low {metric}: {value:.2f}")
                elif value < 0.6:  # <0.6
                    normalized = 1.0
                elif value < 1.0:  # <1.0
                    normalized = 0.9
                else:
                    normalized = 0.7
                    reasoning.append(f"High {metric}: {value:.2f}")
                scores.append(normalized)
            
            # Volatility metrics (lower is better)
            elif 'volatility' in metric:
                # Assume normalized to 0-1 range
                if value < 0.15:
                    normalized = 1.2
                elif value < 0.25:
                    normalized = 1.0
                else:
                    normalized = 0.8
                    reasoning.append(f"High volatility: {value:.2f}")
                scores.append(normalized)
        
        # Market regime risk adjustment
        if market_context.regime == MarketRegime.HIGH_VOL_CHOP:
            regime_adjustment = 0.9
            reasoning.append("Risk discount for volatile market")
        elif market_context.regime == MarketRegime.BEAR:
            regime_adjustment = 0.85
            reasoning.append("Risk discount for bear market")
        else:
            regime_adjustment = 1.0
        
        if not scores:
            avg_score = 1.0
        else:
            avg_score = sum(scores) / len(scores)
            avg_score = max(0.7, min(1.3, avg_score))  # Cap at 0.7-1.3
        
        final_score = avg_score * regime_adjustment
        
        return final_score, reasoning
    
    def _get_marketcap_adjustments(self, market_cap: float) -> Tuple[str, Dict[str, float]]:
        """Get market cap tier and adjustments"""
        for tier, config in sorted(
            self.marketcap_config.items(), 
            key=lambda x: x[1]['threshold'], 
            reverse=True
        ):
            if market_cap >= config['threshold']:
                return tier, config
        
        return 'micro_cap', self.marketcap_config['micro_cap']
    
    def _determine_valuation_signal(
        self, upside_pct: float, market_context, quality_score: float
    ) -> Tuple[SignalType, float, List[str]]:
        """Determine signal based on valuation gap"""
        reasoning = []
        
        # Valuation thresholds
        if upside_pct > 25:
            signal = SignalType.BUY
            confidence = min(0.9, 0.7 + (upside_pct - 25) / 100)
            reasoning.append(f"Significantly undervalued: {upside_pct:+.1f}% upside")
        elif upside_pct > 15:
            signal = SignalType.BUY
            confidence = 0.7
            reasoning.append(f"Undervalued: {upside_pct:+.1f}% upside")
        elif upside_pct > 5:
            signal = SignalType.BUY if quality_score > 1.1 else SignalType.HOLD
            confidence = 0.6
            reasoning.append(f"Moderately undervalued: {upside_pct:+.1f}% upside")
        elif upside_pct > -5:
            signal = SignalType.HOLD
            confidence = 0.5
            reasoning.append(f"Fairly valued: {upside_pct:+.1f}%")
        elif upside_pct > -15:
            signal = SignalType.HOLD
            confidence = 0.6
            reasoning.append(f"Slightly overvalued: {upside_pct:+.1f}% downside")
        else:
            signal = SignalType.SELL
            confidence = min(0.8, 0.6 + abs(upside_pct + 15) / 100)
            reasoning.append(f"Overvalued: {upside_pct:+.1f}% downside")
        
        # Regime adjustment
        if market_context.regime == MarketRegime.BEAR and signal == SignalType.BUY:
            confidence *= 0.8
            reasoning.append("Confidence reduced in bear market")
        elif market_context.regime == MarketRegime.BULL and signal == SignalType.SELL:
            confidence *= 0.9
            reasoning.append("Caution: selling in bull market")
        
        return signal, confidence, reasoning
    
    def _calculate_position_size(
        self, signal: SignalType, confidence: float, upside_pct: float, market_context
    ) -> float:
        """Calculate position size based on signal strength"""
        if signal == SignalType.HOLD or signal == SignalType.SELL:
            return 0.0
        
        # Base size scaled by confidence
        base_size = 0.10  # 10%
        confidence_multiplier = confidence / 0.6  # Normalize to 60% threshold
        
        # Scale by upside potential
        upside_multiplier = min(1.5, 1.0 + (upside_pct / 100))
        
        # Regime-based limits
        if market_context.regime == MarketRegime.BULL:
            max_size = 0.15
        elif market_context.regime == MarketRegime.BEAR:
            max_size = 0.08
        else:
            max_size = 0.10
        
        position_size = base_size * confidence_multiplier * upside_multiplier
        position_size = max(0, min(max_size, position_size))
        
        return position_size
    
    def _calculate_value_levels(
        self, signal: SignalType, current_price: float, fair_value: float, confidence: float
    ) -> Tuple:
        """Calculate entry, stop loss, and take profit based on valuation"""
        if signal == SignalType.HOLD or signal == SignalType.SELL:
            return None, None, []
        
        # Entry range around current price
        entry_width = 0.02 if confidence > 0.7 else 0.03
        entry_range = (
            current_price * (1 - entry_width),
            current_price * (1 + entry_width)
        )
        
        # Stop loss based on distance to fair value
        gap = abs(fair_value - current_price)
        stop_distance = min(0.15, gap / current_price * 0.5)  # Max 15%, or half the gap
        
        if signal == SignalType.BUY:
            stop_loss = current_price * (1 - stop_distance)
            # Take profits at fair value and beyond
            take_profit = [
                fair_value * 0.90,  # 90% of fair value
                fair_value * 1.05   # 5% above fair value
            ]
        else:
            stop_loss = current_price * (1 + stop_distance)
            take_profit = []
        
        return entry_range, stop_loss, take_profit
    
    def get_engine_metadata(self) -> Dict[str, Any]:
        """Return engine metadata"""
        return {
            'name': self.engine_name,
            'display_name': 'Universal Valuation Engine',
            'description': 'Sector-adaptive fundamental valuation with configurable metrics (P/E, P/S, P/B, EV/EBITDA, P/FFO)',
            'tier': 'PRO',
            'timeframe': 'position',
            'version': self.engine_version,
            'features': [
                'Sector-specific valuation models',
                'Market cap risk adjustments',
                'Growth/Quality/Risk scoring',
                'Fair value calculation',
                'Configurable metric selection'
            ]
        }

    def _calculate_expectation_adjustment(
        self, fundamentals: Dict[str, Any], config: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """
        Penalize stocks where valuation already prices in extreme growth
        """
        reasoning = []

        pe = fundamentals.get("pe")
        growth = fundamentals.get("earnings_growth", 0)

        if pe and growth > 0:
            peg = pe / (growth * 100)
            if peg > 2.0:
                reasoning.append("High expectations already priced in (high PEG)")
                return 0.85, reasoning
            elif peg < 1.0:
                reasoning.append("Growth undervalued relative to price")
                return 1.10, reasoning

        return 1.0, ["Expectations neutral"]

    
    def get_required_indicators(self) -> List[str]:
        """Return required indicators"""
        return ['price', 'volume']
    
    def get_required_fundamentals(self) -> List[str]:
        """Return required fundamentals"""
        return [
            'sector', 'market_cap', 'eps', 'revenue', 'book_value',
            'roe', 'gross_margin', 'operating_margin', 'debt_to_equity',
            'revenue_growth', 'earnings_growth', 'net_income', 'net_margin'
        ]