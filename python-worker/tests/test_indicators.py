"""
Unit tests for indicator calculations
"""
import pytest
import pandas as pd
import numpy as np

from app.indicators.moving_averages import calculate_sma, calculate_ema, calculate_sma200
from app.indicators.momentum import calculate_rsi, calculate_macd
from app.indicators.volatility import calculate_atr, calculate_bollinger_bands
from app.indicators.trend import detect_long_term_trend, detect_medium_term_trend
from app.indicators.signals import generate_signal, calculate_pullback_zones


class TestMovingAverages:
    """Test moving average calculations"""
    
    def test_sma_basic(self):
        """Test simple moving average calculation"""
        data = pd.Series([100, 101, 102, 103, 104, 105, 106])
        sma = calculate_sma(data, 3)
        
        assert len(sma) == len(data)
        assert not pd.isna(sma.iloc[2])  # First valid value
        assert sma.iloc[2] == 101.0  # (100+101+102)/3
    
    def test_ema_basic(self):
        """Test exponential moving average calculation"""
        data = pd.Series([100, 101, 102, 103, 104])
        ema = calculate_ema(data, 3)
        
        assert len(ema) == len(data)
        assert not pd.isna(ema.iloc[2])  # First valid value
    
    def test_insufficient_data(self):
        """Test handling of insufficient data"""
        data = pd.Series([100, 101])
        sma = calculate_sma(data, 10)
        
        assert all(pd.isna(sma))


class TestMomentum:
    """Test momentum indicators"""
    
    def test_rsi_basic(self):
        """Test RSI calculation"""
        # Create trending data
        data = pd.Series([100, 102, 104, 106, 108, 110, 112])
        rsi = calculate_rsi(data, window=5)
        
        assert len(rsi) == len(data)
        # RSI should be > 50 for uptrending data
        assert rsi.iloc[-1] > 50
    
    def test_macd_basic(self):
        """Test MACD calculation"""
        data = pd.Series(range(100, 150))
        macd_line, signal_line, histogram = calculate_macd(data)
        
        assert len(macd_line) == len(data)
        assert len(signal_line) == len(data)
        assert len(histogram) == len(data)


class TestVolatility:
    """Test volatility indicators"""
    
    def test_atr_basic(self):
        """Test ATR calculation"""
        high = pd.Series([105, 106, 107, 108, 109])
        low = pd.Series([100, 101, 102, 103, 104])
        close = pd.Series([102, 103, 104, 105, 106])
        
        atr = calculate_atr(high, low, close, window=3)
        
        assert len(atr) == len(high)
        assert not pd.isna(atr.iloc[-1])
        assert atr.iloc[-1] > 0
    
    def test_bollinger_bands(self):
        """Test Bollinger Bands calculation"""
        data = pd.Series(range(100, 120))
        upper, middle, lower = calculate_bollinger_bands(data, window=10)
        
        assert len(upper) == len(data)
        assert upper.iloc[-1] > middle.iloc[-1]
        assert middle.iloc[-1] > lower.iloc[-1]


class TestTrend:
    """Test trend detection"""
    
    def test_long_term_trend_bullish(self):
        """Test bullish long-term trend detection"""
        price = pd.Series([110, 111, 112, 113, 114])
        sma200 = pd.Series([100, 100, 100, 100, 100])
        
        trend = detect_long_term_trend(price, sma200)
        
        assert trend.iloc[-1] == 'bullish'
    
    def test_medium_term_trend(self):
        """Test medium-term trend detection"""
        ema20 = pd.Series([110, 111, 112])
        sma50 = pd.Series([100, 100, 100])
        
        trend = detect_medium_term_trend(ema20, sma50)
        
        assert trend.iloc[-1] == 'bullish'


class TestSignals:
    """Test signal generation"""
    
    def test_signal_generation(self):
        """Test trading signal generation"""
        # Create bullish scenario
        price = pd.Series([110, 111, 112, 113, 114])
        ema20 = pd.Series([108, 109, 110, 111, 112])
        ema50 = pd.Series([105, 105, 105, 105, 105])
        sma200 = pd.Series([100, 100, 100, 100, 100])
        macd_line = pd.Series([1, 1.5, 2, 2.5, 3])
        macd_signal = pd.Series([0.5, 1, 1.5, 2, 2.5])
        macd_histogram = macd_line - macd_signal
        rsi = pd.Series([55, 56, 57, 58, 59])
        volume = pd.Series([1000, 1100, 1200, 1300, 1400])
        volume_ma = pd.Series([900, 950, 1000, 1050, 1100])
        long_term_trend = pd.Series(['bullish'] * 5)
        medium_term_trend = pd.Series(['bullish'] * 5)
        
        signal = generate_signal(
            price, ema20, ema50, sma200,
            macd_line, macd_signal, macd_histogram,
            rsi, volume, volume_ma,
            long_term_trend, medium_term_trend
        )
        
        assert len(signal) == len(price)
        # Should generate buy signal in bullish scenario
        assert signal.iloc[-1] in ['buy', 'hold', 'sell']
    
    def test_pullback_zones(self):
        """Test pullback zone calculation"""
        price = pd.Series([110, 111, 112])
        ema20 = pd.Series([108, 109, 110])
        atr = pd.Series([2, 2, 2])
        trend = pd.Series(['bullish', 'bullish', 'bullish'])
        
        lower, upper = calculate_pullback_zones(price, ema20, atr, trend)
        
        assert len(lower) == len(price)
        assert lower.iloc[-1] < upper.iloc[-1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

