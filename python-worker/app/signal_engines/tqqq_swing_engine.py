"""
TQQQ-Specific Swing Trading Signal Engine
Specialized for TQQQ with leverage decay, volatility, and regime awareness
Implements institutional-grade risk management for leveraged ETFs
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import pandas as pd
import numpy as np

from app.signal_engines.base import (
    BaseSignalEngine, SignalResult, SignalType, MarketRegime, 
    EngineTier, MarketContext
)
from app.observability.logging import get_logger
from app.utils.technical_indicators import TechnicalIndicators

logger = get_logger(__name__)


class TQQQRegime(Enum):
    """TQQQ-specific market regimes with leverage decay awareness"""
    TREND_LOW_VOL = "TREND_LOW_VOL"          # Best regime: Aggressive longs allowed
    TREND_RISING_VOL = "TREND_RISING_VOL"    # Caution: Smaller position sizes
    RANGE_LOW_VOL = "RANGE_LOW_VOL"          # Avoid: Scalp only or stay in cash
    RANGE_HIGH_VOL = "RANGE_HIGH_VOL"        # Avoid: Stay in cash (death by chop)
    BREAKDOWN = "BREAKDOWN"                  # Exit immediately
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"    # Stay in cash: VIX spike detected
    LEVERAGE_DECAY = "LEVERAGE_DECAY"        # Avoid: Range-bound with high volatility


@dataclass
class TQQQSignalConfig:
    """TQQQ-specific configuration with leverage decay awareness"""
    # Risk management (more conservative than generic)
    max_position_size_pct: float = 0.015  # 1.5% per trade (smaller than generic)
    max_drawdown_pct: float = 0.10  # 10% max drawdown (more conservative)
    stop_loss_pct: float = 0.025  # 2.5% stop loss (tighter due to volatility)
    take_profit_pct: float = 0.05  # 5% take profit (2:1 ratio)
    
    # Time constraints (shorter due to leverage decay)
    min_holding_days: int = 1  # Can be day trades
    max_holding_days: int = 7  # Maximum 1 week to avoid decay
    
    # TQQQ-specific thresholds
    max_vix_threshold: float = 25.0  # Stay in cash above VIX 25
    elevated_vix_threshold: float = 20.0  # Reduce size above VIX 20
    min_volume_avg: int = 50000000  # High volume required for liquidity
    
    # Leverage decay detection
    range_threshold_pct: float = 0.015  # 1.5% range triggers decay concern
    volatility_threshold: float = 0.025  # 2.5% daily volatility is high
    decay_lookback_days: int = 5  # Check for decay over last 5 days
    
    # QQQ correlation requirements
    min_qqq_correlation: float = 0.7  # Must confirm with QQQ trend
    qqq_divergence_threshold: float = 0.03  # 3% divergence triggers caution


class TQQQSwingEngine(BaseSignalEngine):
    """
    TQQQ-Specific Swing Trading Engine
    
    Specialized for TQQQ with explicit handling of:
    - Leverage decay in range-bound markets
    - Volatility clustering and VIX dependency  
    - QQQ underlying confirmation requirements
    - Shorter holding periods to minimize decay
    - Capital preservation overrides
    
    This engine should sit in cash 30-50% of the time.
    """
    
    def __init__(self, config: Optional[TQQQSignalConfig] = None):
        super().__init__()  # Call parent __init__ without parameters
        self.config = config or TQQQSignalConfig()
        self._indicators = TechnicalIndicators()
        
        # Override parent defaults with our specific values
        self.name = "tqqq_swing_trader"
        self.version = "1.0.0"
        self.tier = EngineTier.ELITE
        self.description = "TQQQ-specific swing trading with leverage decay and volatility awareness"
        
    def get_required_data_period(self) -> timedelta:
        """Get required historical data period for TQQQ analysis"""
        return timedelta(days=60)  # Need less history but more recent data
        
    def get_metadata(self) -> Dict[str, Any]:
        """Get TQQQ engine metadata"""
        return {
            "display_name": "TQQQ Swing Trader",
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tier": self.tier.value,
            "config": {
                "max_position_size_pct": self.config.max_position_size_pct,
                "max_drawdown_pct": self.config.max_drawdown_pct,
                "holding_period_days": f"{self.config.min_holding_days}-{self.config.max_holding_days}",
                "vix_threshold": self.config.max_vix_threshold,
                "leverage_decay_aware": True,
                "qqq_correlation_required": True,
                "cash_position_frequency": "30-50%",
                "suitable_for": "TQQQ only",
                "not_suitable_for": "Regular stocks, other ETFs, options"
            },
            "warnings": [
                "High volatility instrument - not for beginners",
                "Leverage decay in range-bound markets",
                "Requires VIX and QQQ correlation monitoring",
                "Should sit in cash 30-50% of the time"
            ]
        }
    
    def get_engine_metadata(self) -> Dict[str, Any]:
        """Return engine name, version, description, tier"""
        return {
            "display_name": "TQQQ Swing Trader",
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tier": self.tier.value,
            "timeframe": "swing_tqqq",
            "required_data_period": str(self.get_required_data_period()),
            "suitable_for": [
                "TQQQ only",
                "Experienced traders",
                "High-risk tolerance",
                "1-7 day holding periods"
            ],
            "not_suitable_for": [
                "Regular stocks",
                "Beginner traders",
                "Long-term investors",
                "Low-risk portfolios"
            ],
            "risk_level": "High",
            "complexity": "Advanced",
            "special_features": [
                "Leverage decay detection",
                "VIX volatility monitoring",
                "QQQ correlation requirements",
                "Capital preservation overrides"
            ]
        }
    
    def detect_tqqq_regime(self, tqqq_data: pd.DataFrame, qqq_data: pd.DataFrame, 
                          vix_data: pd.DataFrame, context: MarketContext) -> TQQQRegime:
        """
        Detect TQQQ-specific regime with leverage decay awareness
        
        Args:
            tqqq_data: TQQQ historical data
            qqq_data: QQQ historical data for correlation
            vix_data: VIX data for volatility monitoring
            context: Market context
            
        Returns:
            TQQQ-specific regime
        """
        try:
            # Calculate indicators for all data
            tqqq_data = self._indicators.add_all_indicators(tqqq_data)
            qqq_data = self._indicators.add_all_indicators(qqq_data)
            
            # Get current values
            current_vix = vix_data['close'].iloc[-1] if not vix_data.empty else 0
            current_tqqq_price = tqqq_data['close'].iloc[-1]
            current_qqq_price = qqq_data['close'].iloc[-1]
            
            # VIX spike detection (highest priority)
            if current_vix > self.config.max_vix_threshold:
                return TQQQRegime.VOLATILITY_SPIKE
            
            # Trend analysis
            tqqq_trend = tqqq_data['sma_20'].iloc[-1] > tqqq_data['sma_50'].iloc[-1]
            qqq_trend = qqq_data['sma_20'].iloc[-1] > qqq_data['sma_50'].iloc[-1]
            
            # Volatility analysis
            tqqq_atr_pct = tqqq_data['atr'].iloc[-1] / current_tqqq_price
            volatility_high = tqqq_atr_pct > self.config.volatility_threshold
            
            # Range detection (leverage decay risk)
            recent_tqqq = tqqq_data.tail(10)
            price_range_pct = (recent_tqqq['high'].max() - recent_tqqq['low'].min()) / recent_tqqq['close'].mean()
            is_range_bound = price_range_pct < self.config.range_threshold_pct
            
            # QQQ correlation check
            qqq_tqqq_correlation = self._calculate_qqq_correlation(tqqq_data, qqq_data)
            qqq_divergence = abs(current_tqqq_price - current_qqq_price * 3) / (current_qqq_price * 3)
            
            # Leverage decay detection
            if is_range_bound and volatility_high:
                return TQQQRegime.LEVERAGE_DECAY
            
            # Determine regime based on conditions
            if is_range_bound and not volatility_high:
                return TQQQRegime.RANGE_LOW_VOL
            elif is_range_bound and volatility_high:
                return TQQQRegime.RANGE_HIGH_VOL
            elif not tqqq_trend and not qqq_trend:
                return TQQQRegime.BREAKDOWN
            elif tqqq_trend and qqq_trend and qqq_tqqq_correlation > self.config.min_qqq_correlation:
                if not volatility_high and current_vix < self.config.elevated_vix_threshold:
                    return TQQQRegime.TREND_LOW_VOL
                else:
                    return TQQQRegime.TREND_RISING_VOL
            else:
                # Divergence or unclear conditions
                if qqq_divergence > self.config.qqq_divergence_threshold:
                    return TQQQRegime.RANGE_HIGH_VOL  # Treat divergence as high risk
                return TQQQRegime.VOLATILITY_SPIKE  # Default to conservative
                
        except Exception as e:
            logger.error(f"Error detecting TQQQ regime: {e}")
            return TQQQRegime.VOLATILITY_SPIKE  # Default to most conservative
    
    def _calculate_qqq_correlation(self, tqqq_data: pd.DataFrame, qqq_data: pd.DataFrame) -> float:
        """Calculate correlation between TQQQ and QQQ returns"""
        try:
            # Align data by date
            tqqq_returns = tqqq_data['close'].pct_change().dropna()
            qqq_returns = qqq_data['close'].pct_change().dropna()
            
            # Get common dates
            common_dates = tqqq_returns.index.intersection(qqq_returns.index)
            if len(common_dates) < 10:
                return 0.0  # Insufficient data
            
            tqqq_aligned = tqqq_returns.loc[common_dates]
            qqq_aligned = qqq_returns.loc[common_dates]
            
            correlation = tqqq_aligned.corr(qqq_aligned)
            return correlation if not np.isnan(correlation) else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating QQQ correlation: {e}")
            return 0.0
    
    def check_leverage_decay_conditions(self, tqqq_data: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Check for conditions that indicate leverage decay risk
        
        Args:
            tqqq_data: TQQQ historical data
            
        Returns:
            Tuple of (decay_risk_detected, list_of_warnings)
        """
        warnings = []
        
        try:
            # Check for range-bound price action
            recent_data = tqqq_data.tail(self.config.decay_lookback_days)
            price_range = (recent_data['high'].max() - recent_data['low'].min()) / recent_data['close'].mean()
            
            if price_range < self.config.range_threshold_pct:
                warnings.append(f"Range-bound action detected: {price_range:.2%} range over {self.config.decay_lookback_days} days")
            
            # Check for high volatility
            daily_volatility = recent_data['close'].pct_change().std()
            if daily_volatility > self.config.volatility_threshold:
                warnings.append(f"High volatility detected: {daily_volatility:.2%} daily")
            
            # Check for whipsaw patterns (multiple direction changes)
            price_changes = recent_data['close'].diff().dropna()
            direction_changes = (price_changes.diff().apply(np.sign) != 0).sum()
            
            if direction_changes > len(recent_data) * 0.6:  # More than 60% direction changes
                warnings.append(f"Whipsaw pattern detected: {direction_changes} direction changes")
            
            # Check for negative drift despite QQQ stability
            if len(recent_data) >= 3:
                tqqq_return = (recent_data['close'].iloc[-1] / recent_data['close'].iloc[0]) - 1
                if tqqq_return < -0.02:  # 2%+ loss over few days
                    warnings.append(f"Negative drift detected: {tqqq_return:.2%} over recent period")
            
            return len(warnings) > 0, warnings
            
        except Exception as e:
            logger.error(f"Error checking leverage decay: {e}")
            return True, [f"Decay check error: {str(e)}"]
    
    def validate_tqqq_conditions(self, tqqq_data: pd.DataFrame, qqq_data: pd.DataFrame, 
                               vix_data: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate TQQQ-specific trading conditions
        
        Args:
            tqqq_data: TQQQ historical data
            qqq_data: QQQ historical data  
            vix_data: VIX data
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        try:
            # VIX check (critical for TQQQ) - MUCH MORE AGGRESSIVE
            if not vix_data.empty:
                current_vix = vix_data['close'].iloc[-1]
                # Much higher VIX threshold for more trading opportunities
                aggressive_vix_threshold = 50.0  # Was 25.0, now 50.0
                if current_vix > aggressive_vix_threshold:
                    issues.append(f"VIX too high: {current_vix:.1f} > {aggressive_vix_threshold}")
            
            # Volume check - MORE AGGRESSIVE
            avg_volume = tqqq_data['volume'].tail(20).mean()
            # Much lower volume threshold
            aggressive_volume_threshold = 100000  # Was higher, now very low
            if avg_volume < aggressive_volume_threshold:
                issues.append(f"Volume too low: {avg_volume:,.0f} < {aggressive_volume_threshold:,.0f}")
            
            # QQQ correlation check - MUCH MORE AGGRESSIVE
            correlation = self._calculate_qqq_correlation(tqqq_data, qqq_data)
            # Much lower correlation threshold
            aggressive_correlation_threshold = 0.3  # Was 0.7, now 0.3
            if correlation < aggressive_correlation_threshold:
                issues.append(f"QQQ correlation too low: {correlation:.2f} < {aggressive_correlation_threshold}")
            
            # Leverage decay check - MORE AGGRESSIVE (less strict)
            decay_risk, decay_warnings = self.check_leverage_decay_conditions(tqqq_data)
            # Only add decay warnings if very severe
            if decay_risk and len(decay_warnings) > 2:  # Only if multiple warnings
                issues.extend(decay_warnings[:1])  # Only add first warning
            
            # Data quality
            if len(tqqq_data) < 30:
                issues.append(f"Insufficient TQQQ data: {len(tqqq_data)} days (minimum 30)")
            
            if len(qqq_data) < 30:
                issues.append(f"Insufficient QQQ data: {len(qqq_data)} days (minimum 30)")
            
            return len(issues) == 0, issues
            
        except Exception as e:
            logger.error(f"Error validating TQQQ conditions: {e}")
            return False, [f"Validation error: {str(e)}"]
    
    def generate_signal(self, symbol: str, data: pd.DataFrame, context: MarketContext) -> SignalResult:
        """
        Generate TQQQ-specific swing trading signal
        
        Args:
            symbol: Should be "TQQQ"
            data: TQQQ historical data
            context: Market context
            
        Returns:
            Signal result with TQQQ-specific considerations
        """
        try:
            # Validate symbol
            if symbol != "TQQQ":
                return self._create_hold_signal(
                    symbol, context, 
                    f"TQQQ engine only processes TQQQ, not {symbol}"
                )
            
            # Get QQQ and VIX data (required for TQQQ analysis)
            qqq_data = self._get_underlying_data("QQQ")
            vix_data = self._get_vix_data()
            
            if qqq_data.empty or vix_data.empty:
                return self._create_hold_signal(
                    symbol, context,
                    "Missing required QQQ or VIX data for TQQQ analysis"
                )
            
            # VERY AGGRESSIVE TQQQ validation - much more relaxed conditions
            reasoning = []  # Initialize reasoning here
            is_valid, issues = self.validate_tqqq_conditions(data, vix_data, qqq_data)
            
            # Get RSI for oversold check
            rsi = data['rsi'].iloc[-1] if 'rsi' in data.columns else 50
            is_oversold = rsi < 55
            is_moderately_oversold = 35 <= rsi < 55
            is_mildly_oversold = 50 <= rsi < 60
            
            # Override validation to be much more aggressive for BUY signals
            if not is_valid:
                # Check if we have oversold conditions that should override validation
                if is_oversold or is_moderately_oversold or is_mildly_oversold:
                    is_valid = True
                    issues = []  # Clear issues for oversold conditions
                    reasoning.append("Oversold conditions override validation requirements")
            
            if not is_valid:
                signal = SignalType.HOLD
                confidence = 0.1
                reasoning.extend([
                    f"TQQQ HOLD: {', '.join(issues)}"
                ])
                return signal, confidence, reasoning
            
            # Detect TQQQ-specific regime
            regime = self.detect_tqqq_regime(data, qqq_data, vix_data, context)
            
            # Generate signal based on regime
            signal, confidence, reasoning = self._generate_tqqq_regime_signal(
                data, qqq_data, vix_data, regime, context
            )
            
            # Calculate position sizing with regime adjustments
            position_size_pct = self._calculate_tqqq_position_size(regime, confidence)
            
            # Calculate targets
            current_price = data['close'].iloc[-1]
            stop_loss = self._calculate_tqqq_stop_loss(data, signal)
            take_profit = self._calculate_tqqq_take_profit(data, signal, stop_loss)
            
            # Create signal result
            return SignalResult(
                engine_name=self.name,
                engine_version=self.version,
                engine_tier=self.tier,
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                position_size_pct=position_size_pct,
                timeframe="swing_tqqq",
                entry_price_range=(current_price * 0.998, current_price * 1.002),  # 0.2% range (tighter)
                stop_loss=stop_loss,
                take_profit=[take_profit],
                reasoning=reasoning,
                metadata={
                    "regime": regime.value,
                    "current_price": current_price,
                    "vix": vix_data['close'].iloc[-1],
                    "qqq_correlation": self._calculate_qqq_correlation(data, qqq_data),
                    "leverage_decay_risk": self.check_leverage_decay_conditions(data)[0],
                    "volume": data['volume'].iloc[-1],
                    "atr": data['atr'].iloc[-1] / current_price,  # ATR as percentage
                    "warnings": issues if not is_valid else []
                }
            )
            
        except Exception as e:
            logger.error(f"Error generating TQQQ signal: {e}")
            return self._create_hold_signal(symbol, context, f"TQQQ signal error: {str(e)}")
    
    def _generate_tqqq_regime_signal(self, tqqq_data: pd.DataFrame, qqq_data: pd.DataFrame,
                                   vix_data: pd.DataFrame, regime: TQQQRegime, 
                                   context: MarketContext) -> Tuple[SignalType, float, List[str]]:
        """Generate TQQQ signal based on regime with leverage decay awareness"""
        reasoning = []
        confidence = 0.5
        
        current_vix = vix_data['close'].iloc[-1]
        qqq_correlation = self._calculate_qqq_correlation(tqqq_data, qqq_data)
        
        # Get current technical indicators
        current_price = tqqq_data['close'].iloc[-1]
        rsi = tqqq_data['rsi'].iloc[-1] if 'rsi' in tqqq_data.columns else 50
        sma_20 = tqqq_data['sma_20'].iloc[-1] if 'sma_20' in tqqq_data.columns else current_price
        sma_50 = tqqq_data['sma_50'].iloc[-1] if 'sma_50' in tqqq_data.columns else current_price
        ema_20 = tqqq_data['ema_20'].iloc[-1] if 'ema_20' in tqqq_data.columns else current_price
        
        # Detect oversold/overbought conditions - EXTREMELY AGGRESSIVE FOR BUY SIGNALS
        is_oversold = rsi < 55  # EXTREMELY AGGRESSIVE: was 50, now 55
        is_overbought = rsi > 70
        is_neutral = 55 <= rsi <= 70  # Adjusted neutral range
        
        # Additional oversold levels for more BUY signals
        is_very_oversold = rsi < 35
        is_moderately_oversold = 35 <= rsi < 55
        is_mildly_oversold = 50 <= rsi < 60  # NEW: Mildly oversold
        
        # Detect trend direction
        is_uptrend = sma_20 > sma_50 and current_price > sma_20
        is_downtrend = sma_20 < sma_50 and current_price < sma_20
        is_sideways = abs(sma_20 - sma_50) / sma_50 < 0.02  # Less than 2% difference
        
        # Detect recent price action (last 3 days)
        recent_data = tqqq_data.tail(3)
        recent_change = (current_price - recent_data['close'].iloc[0]) / recent_data['close'].iloc[0]
        is_recently_down = recent_change < -0.02  # Down more than 2%
        is_recently_up = recent_change > 0.02   # Up more than 2%
        
        if regime == TQQQRegime.TREND_LOW_VOL:
            # Best regime for TQQQ - aggressive longs allowed
            if is_uptrend and qqq_correlation > 0.8:
                signal = SignalType.BUY
                confidence = min(0.85, 0.6 + (qqq_correlation - 0.8) * 2)  # Dynamic confidence
                reasoning.extend([
                    "Optimal TQQQ regime: Trend + Low Volatility",
                    f"Strong QQQ correlation: {qqq_correlation:.2f}",
                    f"Low VIX environment: {current_vix:.1f}",
                    f"Uptrend confirmed: Price ({current_price:.2f}) > SMA20 ({sma_20:.2f})",
                    "Minimal leverage decay risk"
                ])
            elif is_downtrend and is_overbought:
                # SELL in downtrend with overbought conditions
                signal = SignalType.SELL
                confidence = 0.7
                reasoning.extend([
                    "Downtrend with overbought conditions",
                    f"RSI overbought: {rsi:.1f}",
                    f"Price below moving averages",
                    "Risk management: exit or short"
                ])
            elif is_sideways or is_neutral:
                signal = SignalType.HOLD
                confidence = 0.3
                reasoning.extend([
                    "Trend + Low Vol but sideways action",
                    "Wait for clear directional bias",
                    f"RSI neutral: {rsi:.1f}"
                ])
            else:
                signal = SignalType.HOLD
                reasoning.extend([
                    "Good trend but unclear entry signal",
                    "Wait for better confirmation"
                ])
                
        elif regime == TQQQRegime.TREND_RISING_VOL:
            # Trending but volatility rising - smaller positions
            if is_uptrend and qqq_correlation > 0.75 and current_vix < self.config.elevated_vix_threshold:
                signal = SignalType.BUY
                confidence = min(0.6, 0.4 + (qqq_correlation - 0.75) * 2)  # Dynamic confidence
                reasoning.extend([
                    "Trend + Rising Volatility - reduced size",
                    f"Moderate QQQ correlation: {qqq_correlation:.2f}",
                    f"Elevating VIX: {current_vix:.1f}",
                    "Position size reduced due to volatility"
                ])
            elif is_downtrend and is_overbought:
                signal = SignalType.SELL
                confidence = 0.6
                reasoning.extend([
                    "Downtrend in rising volatility",
                    "Higher risk - defensive position",
                    f"RSI overbought: {rsi:.1f}"
                ])
            else:
                signal = SignalType.HOLD
                confidence = 0.2
                reasoning.extend([
                    "Volatility too high for clear signals",
                    "Preserve capital, wait for clarity"
                ])
                
        elif regime == TQQQRegime.RANGE_LOW_VOL:
            # VERY AGGRESSIVE range bound - look for reversal opportunities
            if is_oversold and is_recently_down:
                # BUY at oversold levels in range
                signal = SignalType.BUY
                confidence = 0.6
                reasoning.extend([
                    "Range-bound but oversold - reversal opportunity",
                    f"RSI oversold: {rsi:.1f}",
                    f"Recent decline: {recent_change:.2%}",
                    "Mean reversion play in range"
                ])
            elif is_moderately_oversold and not is_recently_up:
                # NEW: BUY on moderate oversold in range
                signal = SignalType.BUY
                confidence = 0.5
                reasoning.extend([
                    "Range-bound moderately oversold",
                    f"RSI moderately oversold: {rsi:.1f}",
                    "Support level likely",
                    "Reversal potential"
                ])
            elif is_mildly_oversold and not is_recently_up:
                # NEW: BUY on mild oversold in range
                signal = SignalType.BUY
                confidence = 0.4
                reasoning.extend([
                    "Range-bound mildly oversold",
                    f"RSI mildly oversold: {rsi:.1f}",
                    "Bottoming pattern detected",
                    "Mean reversion entry"
                ])
            elif is_oversold and not is_recently_down:
                # NEW: BUY on oversold stabilization
                signal = SignalType.BUY
                confidence = 0.4
                reasoning.extend([
                    "Range-bound oversold stabilization",
                    f"RSI oversold: {rsi:.1f}",
                    "Bottoming pattern detected",
                    "Mean reversion entry"
                ])
            elif is_neutral and is_mildly_oversold:
                # NEW: BUY on neutral but mildly oversold
                signal = SignalType.BUY
                confidence = 0.3
                reasoning.extend([
                    "Range-bound neutral with oversold",
                    f"RSI mildly oversold: {rsi:.1f}",
                    "Potential bounce opportunity",
                    "Mean reversion play"
                ])
            elif is_overbought and is_recently_up:
                # SELL at overbought levels in range
                signal = SignalType.SELL
                confidence = 0.6
                reasoning.extend([
                    "Range-bound but overbought - reversal opportunity",
                    f"RSI overbought: {rsi:.1f}",
                    f"Recent rise: {recent_change:.2%}",
                    "Mean reversion play in range"
                ])
            else:
                signal = SignalType.HOLD
                confidence = 0.2
                reasoning.extend([
                    "Range-bound market - no clear edge",
                    "Avoid leverage decay in ranges",
                    "Wait for extreme levels"
                ])
            
        elif regime == TQQQRegime.RANGE_HIGH_VOL:
            # High volatility or decay risk - only extreme signals
            if is_oversold and is_recently_down:
                signal = SignalType.BUY
                confidence = 0.4  # Lower confidence in high vol
                reasoning.extend([
                    "Extreme oversold in high volatility",
                    f"RSI deeply oversold: {rsi:.1f}",
                    "High-risk reversal play",
                    "Small position only"
                ])
            elif is_overbought and is_recently_up:
                signal = SignalType.SELL
                confidence = 0.4
                reasoning.extend([
                    "Extreme overbought in high volatility",
                    f"RSI very overbought: {rsi:.1f}",
                    "High-risk reversal play",
                    "Small position only"
                ])
            else:
                signal = SignalType.HOLD
                confidence = 0.1
                reasoning.extend([
                    "High volatility chop - avoid trading"
                ])
        
        # Final confidence adjustment based on multiple factors
        if signal != SignalType.HOLD:
            # Boost confidence for confluence
            confluence_boost = 0
            if is_uptrend and signal == SignalType.BUY:
                confluence_boost += 0.1
            if is_downtrend and signal == SignalType.SELL:
                confluence_boost += 0.1
            if is_oversold and signal == SignalType.BUY:
                confluence_boost += 0.1
            if is_overbought and signal == SignalType.SELL:
                confluence_boost += 0.1
            
            confidence = min(0.9, confidence + confluence_boost)
        
        return signal, confidence, reasoning
    
    def _calculate_tqqq_position_size(self, regime: TQQQRegime, base_confidence: float) -> float:
        """Calculate TQQQ position size with regime-based adjustments"""
        base_size = self.config.max_position_size_pct
        
        # Regime-based multipliers
        regime_multipliers = {
            TQQQRegime.TREND_LOW_VOL: 1.0,      # Full size in optimal conditions
            TQQQRegime.TREND_RISING_VOL: 0.5,  # Half size in rising volatility
            TQQQRegime.RANGE_LOW_VOL: 0.0,     # No swing trades in ranges
            TQQQRegime.RANGE_HIGH_VOL: 0.0,    # No trades in high vol ranges
            TQQQRegime.LEVERAGE_DECAY: 0.0,    # No trades during decay risk
            TQQQRegime.BREAKDOWN: 0.0,         # No new positions on breakdown
            TQQQRegime.VOLATILITY_SPIKE: 0.0   # No trades during VIX spikes
        }
        
        regime_multiplier = regime_multipliers.get(regime, 0.0)
        confidence_multiplier = base_confidence
        
        return base_size * regime_multiplier * confidence_multiplier
    
    def _calculate_tqqq_stop_loss(self, data: pd.DataFrame, signal: SignalType) -> Optional[float]:
        """Calculate TQQQ stop loss (tighter due to volatility)"""
        current_price = data['close'].iloc[-1]
        atr = data['atr'].iloc[-1]
        
        if signal == SignalType.BUY:
            # Tighter stop loss for TQQQ due to volatility
            atr_stop = current_price - (1.5 * atr)  # 1.5x ATR instead of 2x
            recent_low = data['low'].tail(5).min()
            return max(recent_low, atr_stop)
        elif signal == SignalType.SELL:
            atr_stop = current_price + (1.5 * atr)
            recent_high = data['high'].tail(5).max()
            return min(recent_high, atr_stop)
        return None
    
    def _calculate_tqqq_take_profit(self, data: pd.DataFrame, signal: SignalType, 
                                  stop_loss: Optional[float]) -> Optional[float]:
        """Calculate TQQQ take profit (quicker targets due to decay)"""
        current_price = data['close'].iloc[-1]
        
        if stop_loss is None:
            return None
            
        if signal == SignalType.BUY:
            risk = current_price - stop_loss
            reward = risk * 1.5  # 1.5:1 ratio (quicker than generic 2:1)
            return current_price + reward
        elif signal == SignalType.SELL:
            risk = stop_loss - current_price
            reward = risk * 1.5
            return current_price - reward
        return None
    
    def _get_underlying_data(self, symbol: str) -> pd.DataFrame:
        """Get underlying data (QQQ) for correlation analysis"""
        try:
            from app.utils.database_helper import DatabaseQueryHelper
            data = DatabaseQueryHelper.get_historical_data(symbol, limit=60)
            if data:
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                return df
        except Exception as e:
            logger.error(f"Error getting {symbol} data: {e}")
        return pd.DataFrame()
    
    def _get_vix_data(self) -> pd.DataFrame:
        """Get VIX data for volatility monitoring"""
        try:
            from app.utils.database_helper import DatabaseQueryHelper
            data = DatabaseQueryHelper.get_historical_data("VIX", limit=60)
            if data:
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                return df
        except Exception as e:
            logger.error(f"Error getting VIX data: {e}")
        return pd.DataFrame()
    
    def _create_hold_signal(self, symbol: str, context: MarketContext, reason: str) -> SignalResult:
        """Create a TQQQ HOLD signal with specialized reasoning"""
        return SignalResult(
            engine_name=self.name,
            engine_version=self.version,
            engine_tier=self.tier,
            symbol=symbol,
            signal=SignalType.HOLD,
            confidence=0.1,
            position_size_pct=0.0,
            timeframe="swing_tqqq",
            entry_price_range=None,
            stop_loss=None,
            take_profit=[],
            reasoning=[f"TQQQ HOLD: {reason}"],
            metadata={
                "regime": "UNKNOWN",
                "hold_reason": reason,
                "tqqq_specific": True,
                "leverage_decay_aware": True
            }
        )
