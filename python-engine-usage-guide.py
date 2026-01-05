"""
Swing Trading Engine Usage Guide
Complete guide for using Generic and TQQQ swing engines for different symbols
"""

def print_engine_comparison():
    """Print detailed comparison of swing trading engines"""
    
    print("🎯 Swing Trading Engine Comparison Guide")
    print("=" * 60)
    
    print("\n📊 Available Engines:")
    print("-" * 30)
    
    print("\n1️⃣ Generic Swing Engine")
    print("   🎯 Purpose: Standard stocks and regular ETFs")
    print("   ⏱️  Holding Period: 2-10 days")
    print("   💰 Position Size: 2.0% maximum")
    print("   🛑 Stop Loss: 3.0%")
    print("   🎯 Take Profit: 6.0%")
    print("   📈 Risk Level: Moderate")
    print("   🔧 Features:")
    print("      • Standard technical analysis (RSI, MACD, Moving Averages)")
    print("      • Market regime awareness")
    print("      • Volume and momentum analysis")
    print("      • Trend following strategies")
    print("   ✅ Suitable For:")
    print("      • Large-cap stocks (AAPL, MSFT, GOOGL)")
    print("      • Regular ETFs (SPY, QQQ, IWM)")
    print("      • Growth stocks with normal volatility")
    print("   ❌ Not Suitable For:")
    print("      • Leveraged ETFs (TQQQ, SQQQ, SOXL)")
    print("      • Penny stocks (high volatility, low liquidity)")
    print("      • Options and derivatives")
    
    print("\n2️⃣ TQQQ Swing Engine")
    print("   🎯 Purpose: TQQQ (3x leveraged QQQ) only")
    print("   ⏱️  Holding Period: 1-7 days (shorter due to leverage decay)")
    print("   💰 Position Size: 1.5% maximum (conservative)")
    print("   🛑 Stop Loss: 2.5% (tighter due to volatility)")
    print("   🎯 Take Profit: 4.0% (smaller targets)")
    print("   📈 Risk Level: High")
    print("   🔧 Special Features:")
    print("      • Leverage decay detection (avoids range-bound markets)")
    print("      • VIX volatility monitoring (reduces exposure during spikes)")
    print("      • QQQ correlation requirements (70%+ correlation needed)")
    print("      • Regime-based strategies (7 different market regimes)")
    print("      • Time-based exits (max 7 days to minimize decay)")
    print("   ✅ Suitable For:")
    print("      • TQQQ only (highly specialized)")
    print("      • Traders understanding leverage decay risks")
    print("      • Short-term swing trading with high risk tolerance")
    print("   ❌ Not Suitable For:")
    print("      • Regular stocks and ETFs")
    print("      • Buy-and-hold strategies")
    print("      • Risk-averse traders")

def print_symbol_recommendations():
    """Print recommendations for different symbol types"""
    
    print("\n🎯 Engine Recommendations by Symbol Type")
    print("=" * 50)
    
    recommendations = {
        "Large-Cap Tech Stocks": {
            "examples": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
            "engine": "Generic Swing Engine",
            "reasoning": "Normal volatility, good liquidity, standard patterns"
        },
        "Regular ETFs": {
            "examples": ["SPY", "QQQ", "IWM", "VTI", "VOO"],
            "engine": "Generic Swing Engine", 
            "reasoning": "Diversified, moderate volatility, predictable patterns"
        },
        "3x Leveraged ETFs": {
            "examples": ["TQQQ"],
            "engine": "TQQQ Swing Engine",
            "reasoning": "Highly specialized for leverage decay and volatility"
        },
        "Other Leveraged ETFs": {
            "examples": ["SQQQ", "SOXL", "TECL", "FNGU"],
            "engine": "Generic Swing Engine (with caution)",
            "reasoning": "Generic engine with reduced position size and tighter stops"
        },
        "Growth Stocks": {
            "examples": ["NVDA", "TSLA", "AMD", "NFLX"],
            "engine": "Generic Swing Engine",
            "reasoning": "Higher volatility but normal leverage characteristics"
        },
        "Value Stocks": {
            "examples": ["JPM", "WMT", "KO", "PG"],
            "engine": "Generic Swing Engine",
            "reasoning": "Lower volatility, stable patterns, suitable for swing trading"
        }
    }
    
    for category, info in recommendations.items():
        print(f"\n📊 {category}:")
        print(f"   Examples: {', '.join(info['examples'])}")
        print(f"   Engine: {info['engine']}")
        print(f"   Reasoning: {info['reasoning']}")

def print_usage_examples():
    """Print code examples for using both engines"""
    
    print("\n💻 Code Usage Examples")
    print("=" * 30)
    
    print("\n🔧 Using Generic Swing Engine:")
    print("-" * 35)
    print("""
from app.signal_engines.generic_swing_engine import GenericSwingEngine
from app.signal_engines.base import MarketContext, MarketRegime

# Initialize engine
engine = GenericSwingEngine()

# Create market context
market_context = MarketContext(
    regime=MarketRegime.BULL,
    regime_confidence=0.7,
    vix=20.0,
    nasdaq_trend="bullish",
    sector_rotation={},
    breadth=0.6,
    yield_curve_spread=0.02
)

# Generate signal for any stock
symbol = "AAPL"
signal_result = engine.generate_signal(symbol, market_data, market_context)

print(f"Signal: {signal_result.signal.value}")
print(f"Confidence: {signal_result.confidence:.1%}")
print(f"Position Size: {signal_result.position_size_pct:.1%}")
""")
    
    print("\n🔧 Using TQQQ Swing Engine:")
    print("-" * 35)
    print("""
from app.signal_engines.tqqq_swing_engine import TQQQSwingEngine
from app.signal_engines.base import MarketContext, MarketRegime

# Initialize TQQQ engine
engine = TQQQSwingEngine()

# Create market context
market_context = MarketContext(
    regime=MarketRegime.BULL,
    regime_confidence=0.7,
    vix=18.0,  # Lower VIX preferred for TQQQ
    nasdaq_trend="bullish",
    sector_rotation={},
    breadth=0.6,
    yield_curve_spread=0.02
)

# Generate signal for TQQQ only
symbol = "TQQQ"
signal_result = engine.generate_signal(symbol, market_data, market_context)

print(f"Signal: {signal_result.signal.value}")
print(f"Confidence: {signal_result.confidence:.1%}")
print(f"Position Size: {signal_result.position_size_pct:.1%}")
print(f"Regime: {signal_result.metadata.get('regime', 'Unknown')}")
""")

def print_integration_guide():
    """Print integration guide for the Streamlit dashboard"""
    
    print("\n🖥️ Streamlit Dashboard Integration")
    print("=" * 40)
    
    print("\n📊 Current Dashboard Setup:")
    print("   • Main Dashboard: streamlit-app/pages/9_Trading_Dashboard.py")
    print("   • TQQQ Backtest Tab: Uses TQQQ Swing Engine")
    print("   • Signal Engines Tab: Can use Generic Swing Engine")
    
    print("\n🔧 How to Use Generic Swing Engine in Dashboard:")
    print("   1. Navigate to '🧠 Signal Engines' tab")
    print("   2. Select any symbol (AAPL, MSFT, SPY, etc.)")
    print("   3. Choose 'generic_swing' engine")
    print("   4. Generate signals and analyze")
    
    print("\n🎯 How to Use TQQQ Backtest:")
    print("   1. Navigate to '📊 TQQQ Backtest' tab")
    print("   2. Load TQQQ, QQQ, and ^VIX data")
    print("   3. Configure backtest parameters")
    print("   4. Run comprehensive backtesting")
    
    print("\n📋 Custom Symbol Loading:")
    print("   1. Use sidebar '🔧 Custom Symbol Loading'")
    print("   2. Enter any ticker symbol")
    print("   3. Load price data and indicators")
    print("   4. Use with either engine as appropriate")

def print_risk_considerations():
    """Print important risk considerations"""
    
    print("\n⚠️ Risk Considerations")
    print("=" * 30)
    
    print("\n🎯 Generic Swing Engine Risks:")
    print("   • Market risk: Standard market volatility")
    print("   • Gap risk: Price gaps overnight/weekends")
    print("   • Liquidity risk: Lower volume stocks")
    print("   • Systematic risk: Market-wide corrections")
    
    print("\n🎯 TQQQ Swing Engine Risks:")
    print("   • Leverage decay: Daily rebalancing erosion")
    print("   • Volatility risk: 3x daily movements")
    print("   • Correlation risk: Must track QQQ closely")
    print("   • Time decay: Longer holds increase decay risk")
    print("   • Market timing: Critical for 3x leverage")
    
    print("\n🛡️ Risk Management Recommendations:")
    print("   • Position sizing: Never exceed recommended limits")
    print("   • Stop losses: Always use provided stop loss levels")
    print("   • Portfolio allocation: Limit swing trading to portion of portfolio")
    print("   • Market conditions: Avoid trading during high volatility")
    print("   • Backtesting: Validate strategies before live trading")

def main():
    """Main function to print the complete guide"""
    
    print_engine_comparison()
    print_symbol_recommendations()
    print_usage_examples()
    print_integration_guide()
    print_risk_considerations()
    
    print(f"\n🎉 Summary:")
    print("=" * 20)
    print("✅ Generic Swing Engine: Use for most stocks and regular ETFs")
    print("✅ TQQQ Swing Engine: Use only for TQQQ (highly specialized)")
    print("✅ Both engines available in the Streamlit dashboard")
    print("✅ Always validate with backtesting before live trading")
    print("✅ Follow risk management guidelines strictly")
    
    print(f"\n🚀 Next Steps:")
    print("1. Start Streamlit dashboard: streamlit run streamlit-app/pages/9_Trading_Dashboard.py")
    print("2. Load data for your desired symbols")
    print("3. Use appropriate engine for your symbol type")
    print("4. Backtest strategies before live implementation")
    print("5. Follow risk management principles")

if __name__ == "__main__":
    main()
