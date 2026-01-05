#!/usr/bin/env python3
"""
Unit Test for Fear/Greed Engine

Tests the active fear_greed_engine.py to ensure it works correctly with TQQQ market data.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.engines.fear_greed_engine import UniversalFearGreedEngine, MarketData, ETFConfiguration, create_fear_greed_engine

def test_fear_greed_engine():
    """Test the active fear_greed_engine.py"""
    print("=" * 60)
    print("TESTING FEAR/GREED ENGINE")
    print("=" * 60)
    
    # Create engine with ETF configuration
    etf_config = ETFConfiguration()
    engine = UniversalFearGreedEngine(etf_config)
    
    # Test data from your May 12, 2025 example
    market_data = MarketData(
        vix_level=25.92,      # High VIX
        volatility=9.57,      # High volatility
        rsi=43.0,            # Low RSI
        price=33.055,        # TQQQ price
        sma20=49.67,         # SMA20
        sma50=49.99,         # SMA50
        volatility_trend="stable"
    )
    
    print(f"Input data: VIX={market_data.vix_level}, Vol={market_data.volatility}, RSI={market_data.rsi}")
    print(f"ETF Config thresholds: {engine.thresholds}")
    
    try:
        result = engine.calculate_fear_greed_state(market_data)
        print(f"✅ Engine Result:")
        print(f"   State: {result.state.value}")
        print(f"   Bias: {result.signal_bias}")
        print(f"   Confidence: {result.confidence:.2f}")
        print(f"   Raw Score: {result.raw_score:.2f}")
        print(f"   Reasoning: {result.reasoning}")
        print(f"   Risk Adjustment: {result.risk_adjustment}")
        return result
    except Exception as e:
        print(f"❌ Engine Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_scenarios():
    """Test different market scenarios"""
    print("\n" + "=" * 60)
    print("TESTING DIFFERENT SCENARIOS")
    print("=" * 60)
    
    etf_config = ETFConfiguration()
    engine = UniversalFearGreedEngine(etf_config)
    
    scenarios = {
        "Extreme Fear": MarketData(vix_level=35.0, volatility=12.0, rsi=25.0, price=30.0, sma20=40.0, sma50=45.0),
        "Fear": MarketData(vix_level=26.0, volatility=8.0, rsi=35.0, price=35.0, sma20=40.0, sma50=42.0),
        "Neutral": MarketData(vix_level=18.0, volatility=4.0, rsi=50.0, price=40.0, sma20=40.0, sma50=40.0),
        "Greed": MarketData(vix_level=14.0, volatility=2.5, rsi=70.0, price=45.0, sma20=40.0, sma50=38.0),
        "Extreme Greed": MarketData(vix_level=12.0, volatility=1.5, rsi=75.0, price=50.0, sma20=40.0, sma50=35.0)
    }
    
    for scenario_name, data in scenarios.items():
        print(f"\n--- {scenario_name} ---")
        try:
            result = engine.calculate_fear_greed_state(data)
            print(f"State: {result.state.value} | Bias: {result.signal_bias} | Confidence: {result.confidence:.2f}")
        except Exception as e:
            print(f"Error: {e}")

def test_bias_application():
    """Test the bias application function"""
    print("\n" + "=" * 60)
    print("TESTING BIAS APPLICATION")
    print("=" * 60)
    
    from app.engines.fear_greed_engine import apply_fear_greed_bias, FearGreedAnalysis, FearGreedState
    
    # Create a mock Fear/Greed analysis
    analysis = FearGreedAnalysis(
        state=FearGreedState.FEAR,
        confidence=0.7,
        raw_score=-25.0,
        signal_bias="bullish",
        reasoning=["Test reasoning"],
        risk_adjustment=1.2,
        confidence_adjustment=0.1,
        stop_loss_adjustment=1.2
    )
    
    # Test bias application
    try:
        final_signal, adjustments = apply_fear_greed_bias("sell", analysis)
        print(f"✅ Bias Application: sell -> {final_signal}")
        print(f"   Adjustments: {adjustments}")
    except Exception as e:
        print(f"❌ Bias Application Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Run all tests"""
    print("🧪 Fear/Greed Engine Unit Tests")
    print("Testing with TQQQ May 12, 2025 data")
    
    # Test the engine
    result = test_fear_greed_engine()
    
    # Test scenarios
    test_scenarios()
    
    # Test bias application
    test_bias_application()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if result:
        print(f"✅ Engine Working: {result.state.value} (bias: {result.signal_bias})")
        
        # Expected result for May 12, 2025:
        # VIX 25.92 (high), Volatility 9.57% (high), RSI 43 (oversold)
        # Should be FEAR or EXTREME_FEAR with bullish bias
        if result.state.value in ['fear', 'extreme_fear']:
            print("✅ Correct fear state detected")
        else:
            print(f"⚠️  Expected fear state, got {result.state.value}")
            
        if result.signal_bias in ['bullish', 'strongly_bullish']:
            print("✅ Correct bullish bias for fear state")
        else:
            print(f"⚠️  Expected bullish bias, got {result.signal_bias}")
    else:
        print("❌ Engine FAILED")

if __name__ == "__main__":
    main()
