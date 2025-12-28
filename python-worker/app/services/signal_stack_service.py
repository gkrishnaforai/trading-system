"""
Best-Practice Signal Stack Service
Implements industry-standard buy/sell signal logic
Based on what professional systems actually use
"""
from typing import Dict, Any, Optional, List
import pandas as pd

from app.services.base import BaseService
from app.utils.database_helper import DatabaseQueryHelper


class SignalStackService(BaseService):
    """
    Implements best-practice signal stack for buy/sell decisions
    
    Industry Standard Buy Signal (All must align):
    1. Trend: Price > 200-day MA, 50-day MA rising
    2. Entry: EMA20 pullback OR EMA crossover
    3. Momentum: MACD rising, RSI between 45-65
    4. Confirmation: Volume above average, no major resistance
    
    Industry Standard Sell Signal:
    - Price breaks below 50-day MA
    - EMA short crosses below long EMA
    - RSI falls below ~45
    - MACD turns negative
    - Volume expands on down days
    """
    
    def __init__(self):
        """Initialize signal stack service"""
        super().__init__()
    
    def evaluate_buy_signal(
        self,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Evaluate buy signal using best-practice stack
        
        Args:
            indicators: Dictionary of calculated indicators
            market_data: Optional DataFrame with price data
        
        Returns:
            Dictionary with:
            - signal: 'buy', 'hold', 'sell'
            - confidence: 0.0 to 1.0
            - trend_status: 'bullish', 'bearish', 'neutral'
            - entry_status: 'pullback', 'crossover', 'none'
            - momentum_status: 'strong', 'moderate', 'weak'
            - confirmation_status: 'confirmed', 'partial', 'weak'
            - reason: Human-readable explanation
            - details: Breakdown of each component
        """
        # Extract indicators
        price = self._get_latest_value(indicators.get('price'))
        sma50 = self._get_latest_value(indicators.get('sma50'))
        sma200 = self._get_latest_value(indicators.get('sma200'))
        ema20 = self._get_latest_value(indicators.get('ema20'))
        ema50 = self._get_latest_value(indicators.get('ema50'))
        macd_line = self._get_latest_value(indicators.get('macd_line'))
        macd_signal = self._get_latest_value(indicators.get('macd_signal'))
        macd_histogram = self._get_latest_value(indicators.get('macd_histogram'))
        rsi = self._get_latest_value(indicators.get('rsi'))
        volume = self._get_latest_value(indicators.get('volume'))
        volume_ma = self._get_latest_value(indicators.get('volume_ma'))
        atr = self._get_latest_value(indicators.get('atr'))
        
        details = {}
        passed_checks = []
        failed_checks = []
        
        # 1. TREND CHECK (Must have)
        trend_status = 'neutral'
        trend_passed = False
        
        if price and sma200:
            price_above_200 = price > sma200
            details['price_above_200'] = price_above_200
            details['price'] = price
            details['sma200'] = sma200
            
            if sma50:
                sma50_rising = self._is_ma_rising(indicators.get('sma50'))
                details['sma50_rising'] = sma50_rising
                
                if price_above_200 and sma50_rising:
                    trend_status = 'bullish'
                    trend_passed = True
                    passed_checks.append('trend')
                else:
                    failed_checks.append('trend')
                    if not price_above_200:
                        details['trend_fail_reason'] = 'Price below 200-day MA'
                    if not sma50_rising:
                        details['trend_fail_reason'] = '50-day MA not rising'
            else:
                if price_above_200:
                    trend_status = 'bullish'
                    trend_passed = True
                    passed_checks.append('trend')
                else:
                    failed_checks.append('trend')
        else:
            failed_checks.append('trend')
            details['trend_fail_reason'] = 'Missing price or SMA200 data'
        
        # 2. ENTRY CHECK (EMA20 pullback OR EMA crossover)
        entry_status = 'none'
        entry_passed = False
        
        if ema20 and ema50:
            ema20_above_ema50 = ema20 > ema50
            details['ema20_above_ema50'] = ema20_above_ema50
            
            # Check for EMA crossover
            ema_cross_above = self._check_ema_crossover(indicators.get('ema20'), indicators.get('ema50'))
            details['ema_crossover'] = ema_cross_above
            
            # Check for pullback (price near EMA20 but above it)
            if price and ema20:
                pullback_distance = ((price - ema20) / ema20) * 100
                is_pullback = -2.0 <= pullback_distance <= 2.0 and price > ema20
                details['pullback_distance_pct'] = pullback_distance
                details['is_pullback'] = is_pullback
                
                if ema_cross_above or (ema20_above_ema50 and is_pullback):
                    entry_status = 'crossover' if ema_cross_above else 'pullback'
                    entry_passed = True
                    passed_checks.append('entry')
                else:
                    failed_checks.append('entry')
            else:
                if ema_cross_above or ema20_above_ema50:
                    entry_status = 'crossover' if ema_cross_above else 'above'
                    entry_passed = True
                    passed_checks.append('entry')
                else:
                    failed_checks.append('entry')
        else:
            failed_checks.append('entry')
            details['entry_fail_reason'] = 'Missing EMA20 or EMA50 data'
        
        # 3. MOMENTUM CHECK (MACD rising, RSI healthy)
        momentum_status = 'weak'
        momentum_passed = False
        
        # MACD check
        macd_rising = False
        if macd_line and macd_signal:
            macd_above_signal = macd_line > macd_signal
            details['macd_above_signal'] = macd_above_signal
            
            if macd_histogram is not None:
                macd_positive = macd_histogram > 0
                details['macd_histogram_positive'] = macd_positive
                macd_rising = macd_positive and macd_above_signal
            else:
                macd_rising = macd_above_signal
        
        # RSI check (industry standard: 45-65 is healthy)
        rsi_healthy = False
        if rsi is not None:
            details['rsi'] = rsi
            if 45 <= rsi <= 65:
                rsi_healthy = True
                details['rsi_zone'] = 'healthy'
            elif rsi < 45:
                details['rsi_zone'] = 'weak'
            elif rsi > 65:
                details['rsi_zone'] = 'overbought'
            else:
                details['rsi_zone'] = 'unknown'
        
        if macd_rising and rsi_healthy:
            momentum_status = 'strong'
            momentum_passed = True
            passed_checks.append('momentum')
        elif macd_rising or rsi_healthy:
            momentum_status = 'moderate'
            momentum_passed = True
            passed_checks.append('momentum')
        else:
            failed_checks.append('momentum')
            details['momentum_fail_reason'] = f'MACD rising: {macd_rising}, RSI healthy: {rsi_healthy}'
        
        # 4. CONFIRMATION CHECK (Volume above average)
        confirmation_status = 'weak'
        confirmation_passed = False
        
        if volume and volume_ma:
            volume_above_avg = volume > volume_ma
            volume_spike = volume > (volume_ma * 1.5)
            details['volume_above_average'] = volume_above_avg
            details['volume_spike'] = volume_spike
            details['volume'] = volume
            details['volume_ma'] = volume_ma
            
            if volume_spike:
                confirmation_status = 'strong'
                confirmation_passed = True
                passed_checks.append('confirmation')
            elif volume_above_avg:
                confirmation_status = 'confirmed'
                confirmation_passed = True
                passed_checks.append('confirmation')
            else:
                failed_checks.append('confirmation')
                details['confirmation_fail_reason'] = 'Volume below average'
        else:
            failed_checks.append('confirmation')
            details['confirmation_fail_reason'] = 'Missing volume data'
        
        # Determine overall signal
        total_checks = len(passed_checks) + len(failed_checks)
        if total_checks == 0:
            signal = 'hold'
            confidence = 0.0
            reason = "Insufficient data for signal evaluation"
        elif trend_passed and entry_passed and momentum_passed and confirmation_passed:
            signal = 'buy'
            confidence = min(1.0, 0.6 + (len(passed_checks) / max(total_checks, 1)) * 0.4)
            reason = f"✅ High-quality BUY signal: All checks passed (Trend: {trend_status}, Entry: {entry_status}, Momentum: {momentum_status}, Confirmation: {confirmation_status})"
        elif trend_passed and (entry_passed or momentum_passed):
            signal = 'buy'
            confidence = 0.4 + (len(passed_checks) / max(total_checks, 1)) * 0.2
            reason = f"⚠️ Moderate BUY signal: Trend confirmed, partial alignment (Passed: {len(passed_checks)}/{total_checks})"
        else:
            signal = 'hold'
            confidence = len(passed_checks) / max(total_checks, 1) * 0.4
            reason = f"⏸️ HOLD: Insufficient alignment (Passed: {len(passed_checks)}/{total_checks}). Failed: {', '.join(failed_checks)}"
        
        return {
            'signal': signal,
            'confidence': round(confidence, 2),
            'trend_status': trend_status,
            'entry_status': entry_status,
            'momentum_status': momentum_status,
            'confirmation_status': confirmation_status,
            'reason': reason,
            'details': details,
            'passed_checks': passed_checks,
            'failed_checks': failed_checks,
            'total_checks': total_checks
        }
    
    def evaluate_sell_signal(
        self,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Evaluate sell signal using best-practice stack
        
        Returns:
            Dictionary with sell signal evaluation
        """
        # Extract indicators
        price = self._get_latest_value(indicators.get('price'))
        sma50 = self._get_latest_value(indicators.get('sma50'))
        ema20 = self._get_latest_value(indicators.get('ema20'))
        ema50 = self._get_latest_value(indicators.get('ema50'))
        macd_line = self._get_latest_value(indicators.get('macd_line'))
        macd_signal = self._get_latest_value(indicators.get('macd_signal'))
        rsi = self._get_latest_value(indicators.get('rsi'))
        volume = self._get_latest_value(indicators.get('volume'))
        volume_ma = self._get_latest_value(indicators.get('volume_ma'))
        
        details = {}
        sell_signals = []
        
        # Check sell conditions
        if price and sma50:
            if price < sma50:
                sell_signals.append('price_below_50ma')
                details['price_below_50ma'] = True
        
        if ema20 and ema50:
            ema_cross_below = self._check_ema_crossover_below(indicators.get('ema20'), indicators.get('ema50'))
            if ema_cross_below:
                sell_signals.append('ema_cross_below')
                details['ema_cross_below'] = True
        
        if rsi is not None and rsi < 45:
            sell_signals.append('rsi_below_45')
            details['rsi'] = rsi
        
        if macd_line and macd_signal:
            if macd_line < macd_signal:
                sell_signals.append('macd_negative')
                details['macd_below_signal'] = True
        
        if volume and volume_ma:
            # Volume expanding on down days
            if price and sma50 and price < sma50 and volume > volume_ma * 1.2:
                sell_signals.append('volume_expanding_down')
                details['volume_expanding_down'] = True
        
        if sell_signals:
            signal = 'sell'
            confidence = min(1.0, 0.5 + (len(sell_signals) / 5.0) * 0.5)
            reason = f"⚠️ SELL signal: {', '.join(sell_signals)}"
        else:
            signal = 'hold'
            confidence = 0.0
            reason = "No sell signals detected"
        
        return {
            'signal': signal,
            'confidence': round(confidence, 2),
            'reason': reason,
            'details': details,
            'sell_signals': sell_signals
        }
    
    def _get_latest_value(self, indicator: Any) -> Optional[float]:
        """Get latest value from indicator (Series or scalar)"""
        if indicator is None:
            return None
        if isinstance(indicator, pd.Series):
            if len(indicator) > 0:
                val = indicator.iloc[-1]
                return None if pd.isna(val) else float(val)
            return None
        if isinstance(indicator, (int, float)):
            return None if pd.isna(indicator) else float(indicator)
        return None
    
    def _is_ma_rising(self, ma_series: Any) -> bool:
        """Check if moving average is rising"""
        if ma_series is None:
            return False
        if isinstance(ma_series, pd.Series) and len(ma_series) >= 2:
            return ma_series.iloc[-1] > ma_series.iloc[-2]
        return False
    
    def _check_ema_crossover(self, ema_short: Any, ema_long: Any) -> bool:
        """Check if short EMA crossed above long EMA"""
        if ema_short is None or ema_long is None:
            return False
        if isinstance(ema_short, pd.Series) and isinstance(ema_long, pd.Series):
            if len(ema_short) >= 2 and len(ema_long) >= 2:
                # Current: short > long, Previous: short <= long
                return (ema_short.iloc[-1] > ema_long.iloc[-1]) and (ema_short.iloc[-2] <= ema_long.iloc[-2])
        return False
    
    def _check_ema_crossover_below(self, ema_short: Any, ema_long: Any) -> bool:
        """Check if short EMA crossed below long EMA"""
        if ema_short is None or ema_long is None:
            return False
        if isinstance(ema_short, pd.Series) and isinstance(ema_long, pd.Series):
            if len(ema_short) >= 2 and len(ema_long) >= 2:
                # Current: short < long, Previous: short >= long
                return (ema_short.iloc[-1] < ema_long.iloc[-1]) and (ema_short.iloc[-2] >= ema_long.iloc[-2])
        return False

