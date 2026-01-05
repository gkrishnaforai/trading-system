#!/usr/bin/env python3
"""
Test Suite for Signal Calculator Core
Comprehensive testing of signal calculation logic
"""

import unittest
import pandas as pd
import numpy as np
from app.signal_engines.signal_calculator_core import (
    SignalCalculator, SignalConfig, MarketConditions, SignalType,
    calculate_signal_from_dataframe
)

class TestSignalCalculatorCore(unittest.TestCase):
    """Test cases for Signal Calculator Core"""
    
    def setUp(self):
        """Set up test data"""
        self.calculator = SignalCalculator()
        self.config = SignalConfig()
        
        # Create sample market data
        self.sample_df = self._create_sample_dataframe()
        self.oversold_df = self._create_oversold_dataframe()
        self.overbought_df = self._create_overbought_dataframe()
        self.uptrend_df = self._create_uptrend_dataframe()
        self.downtrend_df = self._create_downtrend_dataframe()
    
    def _create_sample_dataframe(self) -> pd.DataFrame:
        """Create sample DataFrame with neutral conditions"""
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        base_price = 100
        
        return pd.DataFrame({
            'date': dates,
            'open': [base_price] * 50,
            'high': [base_price * 1.02] * 50,
            'low': [base_price * 0.98] * 50,
            'close': [base_price] * 50,
            'volume': [2000000] * 50,
            'rsi': [50.0] * 50,  # Neutral RSI
            'sma_20': [base_price] * 50,
            'sma_50': [base_price] * 50,
            'ema_20': [base_price] * 50,
            'macd': [0.0] * 50,
            'macd_signal': [0.0] * 50
        })
    
    def _create_oversold_dataframe(self) -> pd.DataFrame:
        """Create DataFrame with oversold conditions"""
        df = self._create_sample_dataframe()
        df['rsi'] = [25.0] * 50  # Oversold RSI
        # Create recent decline
        df.loc[45:, 'close'] = [98, 97, 96, 95, 94]
        return df
    
    def _create_overbought_dataframe(self) -> pd.DataFrame:
        """Create DataFrame with overbought conditions"""
        df = self._create_sample_dataframe()
        df['rsi'] = [75.0] * 50  # Overbought RSI
        # Create recent rise
        df.loc[45:, 'close'] = [102, 103, 104, 105, 106]
        return df
    
    def _create_uptrend_dataframe(self) -> pd.DataFrame:
        """Create DataFrame with uptrend conditions"""
        df = self._create_sample_dataframe()
        df['sma_20'] = [102] * 50  # SMA20 above SMA50
        df['sma_50'] = [100] * 50
        df['close'] = [103] * 50  # Price above SMA20
        df['macd'] = [0.5] * 50
        df['macd_signal'] = [0.3] * 50
        return df
    
    def _create_downtrend_dataframe(self) -> pd.DataFrame:
        """Create DataFrame with downtrend conditions"""
        df = self._create_sample_dataframe()
        df['sma_20'] = [98] * 50  # SMA20 below SMA50
        df['sma_50'] = [100] * 50
        df['close'] = [97] * 50  # Price below SMA20
        df['macd'] = [-0.5] * 50
        df['macd_signal'] = [-0.3] * 50
        return df
    
    def test_market_conditions_creation(self):
        """Test MarketConditions creation from DataFrame"""
        conditions = MarketConditions.from_dataframe(self.sample_df)
        
        self.assertEqual(conditions.rsi, 50.0)
        self.assertEqual(conditions.current_price, 100.0)
        self.assertIsInstance(conditions.recent_change, float)
        self.assertIsInstance(conditions.volatility, float)
    
    def test_oversold_buy_signal(self):
        """Test BUY signal generation for oversold conditions"""
        result = calculate_signal_from_dataframe(self.oversold_df)
        
        self.assertEqual(result.signal, SignalType.BUY)
        self.assertGreater(result.confidence, 0.5)
        self.assertTrue(any("oversold" in reason.lower() for reason in result.reasoning))
        print(f"✅ Oversold BUY: {result.signal.value} ({result.confidence:.2f}) - {' | '.join(result.reasoning)}")
    
    def test_overbought_sell_signal(self):
        """Test SELL signal generation for overbought conditions"""
        result = calculate_signal_from_dataframe(self.overbought_df)
        
        self.assertEqual(result.signal, SignalType.SELL)
        self.assertGreater(result.confidence, 0.5)
        self.assertTrue(any("overbought" in reason.lower() for reason in result.reasoning))
        print(f"✅ Overbought SELL: {result.signal.value} ({result.confidence:.2f}) - {' | '.join(result.reasoning)}")
    
    def test_uptrend_buy_signal(self):
        """Test BUY signal generation for uptrend conditions"""
        result = calculate_signal_from_dataframe(self.uptrend_df, regime="TRENDING_UP")
        
        self.assertEqual(result.signal, SignalType.BUY)
        self.assertGreater(result.confidence, 0.5)
        self.assertTrue(any("uptrend" in reason.lower() for reason in result.reasoning))
        print(f"✅ Uptrend BUY: {result.signal.value} ({result.confidence:.2f}) - {' | '.join(result.reasoning)}")
    
    def test_downtrend_sell_signal(self):
        """Test SELL signal generation for downtrend conditions"""
        result = calculate_signal_from_dataframe(self.downtrend_df, regime="TRENDING_DOWN")
        
        self.assertEqual(result.signal, SignalType.SELL)
        self.assertGreater(result.confidence, 0.5)
        self.assertTrue(any("downtrend" in reason.lower() for reason in result.reasoning))
        print(f"✅ Downtrend SELL: {result.signal.value} ({result.confidence:.2f}) - {' | '.join(result.reasoning)}")
    
    def test_neutral_hold_signal(self):
        """Test HOLD signal generation for neutral conditions"""
        result = calculate_signal_from_dataframe(self.sample_df)
        
        self.assertEqual(result.signal, SignalType.HOLD)
        self.assertLess(result.confidence, 0.5)
        self.assertTrue(any("no clear signal" in reason.lower() for reason in result.reasoning))
        print(f"✅ Neutral HOLD: {result.signal.value} ({result.confidence:.2f}) - {' | '.join(result.reasoning)}")
    
    def test_tqqq_symbol_adjustments(self):
        """Test TQQQ-specific symbol adjustments"""
        # TQQQ should be more aggressive with BUY signals
        result = calculate_signal_from_dataframe(self.sample_df, symbol="TQQQ")
        
        # With TQQQ adjustments, even neutral RSI (50) should trigger BUY
        # because TQQQ oversold threshold is 55
        self.assertEqual(result.signal, SignalType.BUY)
        print(f"✅ TQQQ adjustment: {result.signal.value} ({result.confidence:.2f}) - {' | '.join(result.reasoning)}")
    
    def test_regime_adjustments(self):
        """Test regime-specific adjustments"""
        # Test same conditions with different regimes
        base_result = calculate_signal_from_dataframe(self.uptrend_df)
        uptrend_result = calculate_signal_from_dataframe(self.uptrend_df, regime="TRENDING_UP")
        downtrend_result = calculate_signal_from_dataframe(self.uptrend_df, regime="TRENDING_DOWN")
        
        # Uptrend regime should boost confidence for BUY signals
        if base_result.signal == SignalType.BUY:
            self.assertGreaterEqual(uptrend_result.confidence, base_result.confidence)
            print(f"✅ Regime boost: Base {base_result.confidence:.2f} -> Uptrend {uptrend_result.confidence:.2f}")
    
    def test_volatility_filter(self):
        """Test volatility filtering"""
        # Create high volatility DataFrame
        high_vol_df = self._create_sample_dataframe()
        high_vol_df['close'] = [100 + i * 2 for i in range(50)]  # High volatility
        
        result = calculate_signal_from_dataframe(high_vol_df)
        
        # Should be HOLD due to high volatility
        self.assertEqual(result.signal, SignalType.HOLD)
        self.assertTrue(any("volatility" in reason.lower() for reason in result.reasoning))
        print(f"✅ Volatility filter: {result.signal.value} - {' | '.join(result.reasoning)}")
    
    def test_custom_configuration(self):
        """Test custom configuration"""
        custom_config = SignalConfig(
            rsi_oversold=40,  # More aggressive
            max_volatility=8.0,  # Allow higher volatility
            oversold_boost=0.2  # Higher boost
        )
        
        result = calculate_signal_from_dataframe(
            self.sample_df, 
            config=custom_config
        )
        
        # With more aggressive config, should get BUY signal
        self.assertEqual(result.signal, SignalType.BUY)
        print(f"✅ Custom config: {result.signal.value} ({result.confidence:.2f}) - {' | '.join(result.reasoning)}")
    
    def test_metadata_generation(self):
        """Test metadata generation"""
        result = calculate_signal_from_dataframe(self.sample_df)
        
        self.assertIn('rsi', result.metadata)
        self.assertIn('current_price', result.metadata)
        self.assertIn('signal_strength', result.metadata)
        self.assertEqual(result.metadata['rsi'], 50.0)
        self.assertEqual(result.metadata['current_price'], 100.0)
        print(f"✅ Metadata: {result.metadata}")
    
    def test_confidence_clamping(self):
        """Test confidence clamping between 0.1 and 0.9"""
        # Test with conditions that would normally give very high confidence
        extreme_oversold_df = self._create_oversold_dataframe()
        extreme_oversold_df['rsi'] = [10.0] * 50  # Extremely oversold
        
        result = calculate_signal_from_dataframe(extreme_oversold_df)
        
        # Confidence should be clamped to max 0.9
        self.assertLessEqual(result.confidence, 0.9)
        self.assertGreaterEqual(result.confidence, 0.1)
        print(f"✅ Confidence clamping: {result.confidence:.2f}")
    
    def test_empty_dataframe_handling(self):
        """Test handling of empty DataFrame"""
        with self.assertRaises(ValueError):
            MarketConditions.from_dataframe(pd.DataFrame())
    
    def test_missing_columns_handling(self):
        """Test handling of missing indicator columns"""
        minimal_df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=10, freq='D'),
            'close': [100] * 10,
            'volume': [1000000] * 10
        })
        
        # Should not crash and should use default values
        result = calculate_signal_from_dataframe(minimal_df)
        self.assertIsNotNone(result.signal)
        print(f"✅ Missing columns: {result.signal.value} ({result.confidence:.2f})")

class TestSignalCalculatorIntegration(unittest.TestCase):
    """Integration tests for Signal Calculator"""
    
    def test_buy_signal_rate_target(self):
        """Test that BUY signal rate is reasonable (target: 30-40%)"""
        # Generate diverse test scenarios
        test_scenarios = []
        
        # Create various market conditions
        for i in range(100):
            df = self._create_random_scenario(i)
            test_scenarios.append(df)
        
        # Calculate signals
        buy_count = 0
        sell_count = 0
        hold_count = 0
        
        for df in test_scenarios:
            result = calculate_signal_from_dataframe(df, symbol="TQQQ")
            
            if result.signal == SignalType.BUY:
                buy_count += 1
            elif result.signal == SignalType.SELL:
                sell_count += 1
            else:
                hold_count += 1
        
        total = buy_count + sell_count + hold_count
        buy_rate = buy_count / total * 100
        sell_rate = sell_count / total * 100
        hold_rate = hold_count / total * 100
        
        print(f"📊 Signal Distribution:")
        print(f"  BUY: {buy_count}/{total} ({buy_rate:.1f}%)")
        print(f"  SELL: {sell_count}/{total} ({sell_rate:.1f}%)")
        print(f"  HOLD: {hold_count}/{total} ({hold_rate:.1f}%)")
        
        # Target: 30-40% BUY signals
        self.assertGreaterEqual(buy_rate, 25.0)  # At least 25%
        self.assertLessEqual(buy_rate, 45.0)     # At most 45%
        
        # Should have reasonable distribution
        self.assertGreater(buy_count, 0)
        self.assertGreater(sell_count, 0)
        self.assertGreater(hold_count, 0)
    
    def _create_random_scenario(self, seed: int) -> pd.DataFrame:
        """Create random market scenario for testing"""
        np.random.seed(seed)
        
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        base_price = 100
        
        # Random walk with trend
        price_changes = np.random.randn(50) * 2
        trend = np.random.choice([-1, 0, 1]) * 0.5  # Random trend
        price = base_price + np.cumsum(price_changes + trend)
        
        # Generate corresponding indicators
        rsi = 30 + np.random.rand(50) * 40  # RSI between 30-70
        sma_20 = price + np.random.randn(50) * 3
        sma_50 = price + np.random.randn(50) * 5
        ema_20 = price + np.random.randn(50) * 2
        macd = np.random.randn(50) * 1
        macd_signal = macd + np.random.randn(50) * 0.5
        
        return pd.DataFrame({
            'date': dates,
            'open': price * (1 + np.random.rand(50) * 0.01 - 0.005),
            'high': price * (1 + np.random.rand(50) * 0.02),
            'low': price * (1 - np.random.rand(50) * 0.02),
            'close': price,
            'volume': np.random.randint(1000000, 5000000, 50),
            'rsi': rsi,
            'sma_20': sma_20,
            'sma_50': sma_50,
            'ema_20': ema_20,
            'macd': macd,
            'macd_signal': macd_signal
        })

if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
