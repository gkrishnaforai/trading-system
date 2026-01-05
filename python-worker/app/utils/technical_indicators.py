"""
Technical Indicators Utility Class
Wrapper class for all technical indicator calculations
Provides a unified interface for signal engines
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from app.indicators.moving_averages import (
    calculate_sma, calculate_ema, calculate_sma50, calculate_ema20, calculate_sma200
)
from app.indicators.momentum import (
    calculate_rsi, calculate_macd, calculate_momentum_score
)
from app.indicators.volatility import (
    calculate_atr, calculate_bollinger_bands
)
from app.indicators.trend import (
    detect_long_term_trend, detect_medium_term_trend
)
from app.indicators.swing import (
    calculate_adx, calculate_stochastic, calculate_williams_r, calculate_vwap
)

from app.observability.logging import get_logger

logger = get_logger(__name__)


class TechnicalIndicators:
    """
    Unified technical indicators interface for signal engines
    
    Provides a clean API for calculating all commonly used technical indicators
    with proper error handling and data validation.
    """
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    def add_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add all technical indicators to a DataFrame
        
        Args:
            df: DataFrame with OHLCV data (columns: open, high, low, close, volume)
            
        Returns:
            DataFrame with all indicators added as new columns
        """
        try:
            # Validate input data
            self._validate_dataframe(df)
            
            df_indicators = df.copy()
            
            # Moving Averages
            df_indicators = self._add_moving_averages(df_indicators)
            
            # Momentum Indicators
            df_indicators = self._add_momentum_indicators(df_indicators)
            
            # Volatility Indicators
            df_indicators = self._add_volatility_indicators(df_indicators)
            
            # Trend Indicators
            df_indicators = self._add_trend_indicators(df_indicators)
            
            # Swing Indicators
            df_indicators = self._add_swing_indicators(df_indicators)
            
            self.logger.debug(f"Added {len(df_indicators.columns) - len(df.columns)} indicators to DataFrame")
            
            return df_indicators
            
        except Exception as e:
            self.logger.error(f"Error adding indicators: {e}")
            raise
    
    def _validate_dataframe(self, df: pd.DataFrame) -> None:
        """Validate that DataFrame has required OHLCV columns"""
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise ValueError(f"DataFrame missing required columns: {missing_columns}")
        
        if len(df) < 20:
            raise ValueError(f"DataFrame has insufficient data: {len(df)} rows (minimum 20)")
    
    def _add_moving_averages(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add moving average indicators"""
        try:
            # Simple Moving Averages
            df['sma_20'] = calculate_sma(df['close'], window=20)
            df['sma_50'] = calculate_sma(df['close'], window=50)
            df['sma_200'] = calculate_sma(df['close'], window=200)
            
            # Exponential Moving Averages
            df['ema_20'] = calculate_ema(df['close'], window=20)
            df['ema_50'] = calculate_ema(df['close'], window=50)
            
            return df
            
        except Exception as e:
            self.logger.warning(f"Error adding moving averages: {e}")
            return df
    
    def _add_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add momentum indicators"""
        try:
            # RSI
            rsi_data = calculate_rsi(df['close'], window=14)
            if isinstance(rsi_data, pd.Series):
                df['rsi'] = rsi_data
            else:
                df['rsi'] = rsi_data.get('rsi', pd.Series([50] * len(df), index=df.index))
            
            # MACD
            macd_data = calculate_macd(df['close'])
            if isinstance(macd_data, dict):
                df['macd'] = macd_data.get('macd', pd.Series([0] * len(df), index=df.index))
                df['macd_signal'] = macd_data.get('signal', pd.Series([0] * len(df), index=df.index))
                df['macd_hist'] = macd_data.get('histogram', pd.Series([0] * len(df), index=df.index))
            else:
                df['macd'] = macd_data
                df['macd_signal'] = pd.Series([0] * len(df), index=df.index)
                df['macd_hist'] = pd.Series([0] * len(df), index=df.index)
            
            # Momentum Score
            df['momentum_score'] = calculate_momentum_score(df)
            
            return df
            
        except Exception as e:
            self.logger.warning(f"Error adding momentum indicators: {e}")
            return df
    
    def _add_volatility_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volatility indicators"""
        try:
            # ATR
            atr_data = calculate_atr(df['high'], df['low'], df['close'], window=14)
            if isinstance(atr_data, pd.Series):
                df['atr'] = atr_data
            else:
                df['atr'] = atr_data.get('atr', pd.Series([1] * len(df), index=df.index))
            
            # Bollinger Bands
            bb_data = calculate_bollinger_bands(df['close'], window=20, std_dev=2)
            if isinstance(bb_data, dict):
                df['bb_upper'] = bb_data.get('upper', df['close'])
                df['bb_middle'] = bb_data.get('middle', df['close'])
                df['bb_lower'] = bb_data.get('lower', df['close'])
                df['bb_width'] = (bb_data.get('upper', df['close']) - bb_data.get('lower', df['close'])) / df['close']
            else:
                df['bb_upper'] = bb_data
                df['bb_middle'] = df['close']
                df['bb_lower'] = bb_data
                df['bb_width'] = pd.Series([0.1] * len(df), index=df.index)
            
            return df
            
        except Exception as e:
            self.logger.warning(f"Error adding volatility indicators: {e}")
            return df
    
    def _add_trend_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add trend indicators"""
        try:
            # Long-term trend
            long_trend = detect_long_term_trend(df)
            df['trend_long'] = long_trend.get('trend', 'neutral')
            df['trend_long_strength'] = long_trend.get('strength', 0.5)
            
            # Medium-term trend
            medium_trend = detect_medium_term_trend(df)
            df['trend_medium'] = medium_trend.get('trend', 'neutral')
            df['trend_medium_strength'] = medium_trend.get('strength', 0.5)
            
            return df
            
        except Exception as e:
            self.logger.warning(f"Error adding trend indicators: {e}")
            # Add default values
            df['trend_long'] = 'neutral'
            df['trend_long_strength'] = 0.5
            df['trend_medium'] = 'neutral'
            df['trend_medium_strength'] = 0.5
            return df
    
    def _add_swing_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add swing trading indicators"""
        try:
            # ADX (Average Directional Index)
            adx_data = calculate_adx(df, period=14)
            if isinstance(adx_data, dict):
                df['adx'] = adx_data.get('adx', pd.Series([25] * len(df), index=df.index))
                df['di_plus'] = adx_data.get('di_plus', pd.Series([0] * len(df), index=df.index))
                df['di_minus'] = adx_data.get('di_minus', pd.Series([0] * len(df), index=df.index))
            else:
                df['adx'] = adx_data
                df['di_plus'] = pd.Series([0] * len(df), index=df.index)
                df['di_minus'] = pd.Series([0] * len(df), index=df.index)
            
            # Stochastic Oscillator
            stoch_data = calculate_stochastic(df, k_period=14, d_period=3)
            if isinstance(stoch_data, dict):
                df['stoch_k'] = stoch_data.get('k', pd.Series([50] * len(df), index=df.index))
                df['stoch_d'] = stoch_data.get('d', pd.Series([50] * len(df), index=df.index))
            else:
                df['stoch_k'] = stoch_data
                df['stoch_d'] = pd.Series([50] * len(df), index=df.index)
            
            # Williams %R
            williams_data = calculate_williams_r(df, period=14)
            if isinstance(williams_data, pd.Series):
                df['williams_r'] = williams_data
            else:
                df['williams_r'] = williams_data.get('williams_r', pd.Series([-50] * len(df), index=df.index))
            
            # VWAP (Volume Weighted Average Price)
            vwap_data = calculate_vwap(df)
            if isinstance(vwap_data, pd.Series):
                df['vwap'] = vwap_data
            else:
                df['vwap'] = vwap_data.get('vwap', df['close'])
            
            return df
            
        except Exception as e:
            self.logger.warning(f"Error adding swing indicators: {e}")
            # Add default values
            df['adx'] = pd.Series([25] * len(df), index=df.index)
            df['di_plus'] = pd.Series([0] * len(df), index=df.index)
            df['di_minus'] = pd.Series([0] * len(df), index=df.index)
            df['stoch_k'] = pd.Series([50] * len(df), index=df.index)
            df['stoch_d'] = pd.Series([50] * len(df), index=df.index)
            df['williams_r'] = pd.Series([-50] * len(df), index=df.index)
            df['vwap'] = df['close']
            return df
    
    def get_indicator_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Get a summary of current indicator values
        
        Args:
            df: DataFrame with indicators
            
        Returns:
            Dictionary with current indicator values
        """
        try:
            if df.empty:
                return {}
            
            latest = df.iloc[-1]
            
            summary = {
                'price': {
                    'close': latest.get('close', 0),
                    'volume': latest.get('volume', 0)
                },
                'moving_averages': {
                    'sma_20': latest.get('sma_20', 0),
                    'sma_50': latest.get('sma_50', 0),
                    'sma_200': latest.get('sma_200', 0),
                    'ema_20': latest.get('ema_20', 0),
                    'ema_50': latest.get('ema_50', 0)
                },
                'momentum': {
                    'rsi': latest.get('rsi', 50),
                    'macd': latest.get('macd', 0),
                    'macd_signal': latest.get('macd_signal', 0),
                    'macd_hist': latest.get('macd_hist', 0),
                    'momentum_score': latest.get('momentum_score', 0.5)
                },
                'volatility': {
                    'atr': latest.get('atr', 0),
                    'bb_upper': latest.get('bb_upper', 0),
                    'bb_middle': latest.get('bb_middle', 0),
                    'bb_lower': latest.get('bb_lower', 0),
                    'bb_width': latest.get('bb_width', 0.1)
                },
                'trend': {
                    'long_term': latest.get('trend_long', 'neutral'),
                    'long_strength': latest.get('trend_long_strength', 0.5),
                    'medium_term': latest.get('trend_medium', 'neutral'),
                    'medium_strength': latest.get('trend_medium_strength', 0.5)
                },
                'swing': {
                    'adx': latest.get('adx', 25),
                    'di_plus': latest.get('di_plus', 0),
                    'di_minus': latest.get('di_minus', 0),
                    'stoch_k': latest.get('stoch_k', 50),
                    'stoch_d': latest.get('stoch_d', 50),
                    'williams_r': latest.get('williams_r', -50),
                    'vwap': latest.get('vwap', latest.get('close', 0))
                }
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Error getting indicator summary: {e}")
            return {}
    
    def calculate_signal_strength(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate signal strength based on multiple indicators
        
        Args:
            df: DataFrame with indicators
            
        Returns:
            Dictionary with signal strengths for different directions
        """
        try:
            if df.empty or len(df) < 20:
                return {'buy': 0.0, 'sell': 0.0, 'hold': 1.0}
            
            latest = df.iloc[-1]
            
            # Initialize signal strengths
            buy_strength = 0.0
            sell_strength = 0.0
            
            # Moving Average signals
            if latest.get('sma_20', 0) > latest.get('sma_50', 0):
                buy_strength += 0.2
            else:
                sell_strength += 0.2
            
            # RSI signals
            rsi = latest.get('rsi', 50)
            if rsi < 30:
                buy_strength += 0.3
            elif rsi > 70:
                sell_strength += 0.3
            
            # MACD signals
            macd = latest.get('macd', 0)
            macd_signal = latest.get('macd_signal', 0)
            if macd > macd_signal:
                buy_strength += 0.2
            else:
                sell_strength += 0.2
            
            # ADX signals (trend strength)
            adx = latest.get('adx', 25)
            di_plus = latest.get('di_plus', 0)
            di_minus = latest.get('di_minus', 0)
            
            if adx > 25:  # Strong trend
                if di_plus > di_minus:
                    buy_strength += 0.3
                else:
                    sell_strength += 0.3
            
            # Normalize strengths
            total_strength = buy_strength + sell_strength
            if total_strength > 0:
                buy_strength = buy_strength / total_strength
                sell_strength = sell_strength / total_strength
            
            hold_strength = 1.0 - max(buy_strength, sell_strength)
            
            return {
                'buy': buy_strength,
                'sell': sell_strength,
                'hold': hold_strength
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating signal strength: {e}")
            return {'buy': 0.0, 'sell': 0.0, 'hold': 1.0}
