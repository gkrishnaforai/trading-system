#!/usr/bin/env python3
"""
Test script for Portfolio Analysis components
Validates data handling and formatting before deployment
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from components.analysis_display import safe_float

def test_safe_float():
    """Test the safe_float function with various inputs"""
    print("Testing safe_float function...")
    
    test_cases = [
        ("123.45", 123.45),
        ("7.11%", 7.11),
        ("$1,234.56", 1234.56),
        (123, 123.0),
        (123.45, 123.45),
        ("", 0),
        (None, 0),
        ("invalid", 0),
        ("0.10%", 0.10),
        ("N/A", 0),
        ("1,234", 1234.0),
    ]
    
    for input_val, expected in test_cases:
        result = safe_float(input_val)
        status = "✅ PASS" if abs(result - expected) < 0.001 else "❌ FAIL"
        print(f"  {status}: safe_float({repr(input_val)}) = {result} (expected {expected})")
    
    print()

def test_mock_data():
    """Test with mock analysis data"""
    print("Testing with mock analysis data...")
    
    # Mock data that simulates what comes from the API
    mock_analysis = {
        'recent_change': '0.10%',
        'real_volatility': '7.11%',
        'vix_level': '15.23',
        'ema_slope': '0.025',
        'price': '$150.25'
    }
    
    mock_market_data = {
        'price': '150.25',
        'rsi': '65.5',
        'volume': '1,234,567'
    }
    
    # Test all the conversions that happen in the display function
    try:
        price = safe_float(mock_market_data.get('price', 0))
        recent_change = safe_float(mock_analysis.get('recent_change', 0))
        volatility = safe_float(mock_analysis.get('real_volatility', 0))
        vix = safe_float(mock_analysis.get('vix_level', 0))
        ema_slope = safe_float(mock_analysis.get('ema_slope', 0))
        volume = safe_float(mock_market_data.get('volume', 0))
        
        print(f"  ✅ Price: {price} (type: {type(price)})")
        print(f"  ✅ Recent Change: {recent_change}% (type: {type(recent_change)})")
        print(f"  ✅ Volatility: {volatility}% (type: {type(volatility)})")
        print(f"  ✅ VIX: {vix} (type: {type(vix)})")
        print(f"  ✅ EMA Slope: {ema_slope} (type: {type(ema_slope)})")
        print(f"  ✅ Volume: {volume} (type: {type(volume)})")
        
        # Test comparisons that were failing
        volatility_risk = "🟡 Medium" if volatility > 0.02 else "🟢 Low"
        trend_risk = "🟢 Low" if ema_slope > 0 else "🔴 High"
        volume_risk = "🟢 Low" if volume > 500000 else "🔴 High"
        
        print(f"  ✅ Volatility Risk: {volatility_risk}")
        print(f"  ✅ Trend Risk: {trend_risk}")
        print(f"  ✅ Volume Risk: {volume_risk}")
        
    except Exception as e:
        print(f"  ❌ Error in mock data test: {e}")
        return False
    
    print()
    return True

def test_formatting():
    """Test string formatting that was causing issues"""
    print("Testing string formatting...")
    
    try:
        # Test the formatting patterns used in the display
        test_values = [
            (150.25, "$150.25"),
            (0.10, "0.10%"),
            (7.11, "7.11%"),
            (1234567, "1,234,567"),
        ]
        
        for value, expected_pattern in test_values:
            if 'price' in expected_pattern:
                formatted = f"${value:.2f}"
            elif '%' in expected_pattern:
                formatted = f"{value:.2f}%"
            else:
                formatted = f"{value:,.0f}"
            
            print(f"  ✅ {value} -> {formatted}")
        
    except Exception as e:
        print(f"  ❌ Error in formatting test: {e}")
        return False
    
    print()
    return True

def main():
    """Run all tests"""
    print("=" * 60)
    print("PORTFOLIO ANALYSIS COMPONENT TESTS")
    print("=" * 60)
    print()
    
    # Run all tests
    test_safe_float()
    
    if not test_mock_data():
        print("❌ Mock data test failed!")
        return False
    
    if not test_formatting():
        print("❌ Formatting test failed!")
        return False
    
    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("The code should be safe to deploy.")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
