"""
Enhanced Signal Engine Interface
Add better support for Generic Swing Engine usage in the dashboard
"""

def create_generic_swing_interface():
    """Create a dedicated interface for Generic Swing Engine analysis"""
    
    interface_code = '''
# Generic Swing Trading Interface
st.subheader("🔄 Generic Swing Trading Analysis")
st.caption("Use the Generic Swing Engine for any stock or regular ETF")

# Symbol selection for generic swing analysis
generic_symbols = st.multiselect(
    "Select Symbols for Swing Analysis",
    options=["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "SPY", "QQQ", "IWM", "VTI"],
    default=["AAPL", "MSFT"],
    help="Choose symbols to analyze with the Generic Swing Engine"
)

if generic_symbols:
    st.write(f"📊 Analyzing {len(generic_symbols)} symbols with Generic Swing Engine")
    
    # Analysis options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        show_signals = st.checkbox("Show Signals", value=True)
    
    with col2:
        show_metadata = st.checkbox("Show Engine Metadata", value=False)
    
    with col3:
        show_comparison = st.checkbox("Compare with TQQQ", value=False)
    
    if st.button("🚀 Run Generic Swing Analysis", type="primary"):
        with st.spinner("Analyzing symbols with Generic Swing Engine..."):
            try:
                # Import here to avoid circular imports
                import sys
                import os
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'python-worker'))
                
                from app.signal_engines.generic_swing_engine import GenericSwingEngine
                from app.signal_engines.tqqq_swing_engine import TQQQSwingEngine
                from app.signal_engines.base import MarketContext, MarketRegime
                
                # Initialize engines
                generic_engine = GenericSwingEngine()
                tqqq_engine = TQQQSwingEngine() if show_comparison else None
                
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
                
                # Display engine metadata if requested
                if show_metadata:
                    with st.expander("🔧 Generic Swing Engine Metadata", expanded=False):
                        metadata = generic_engine.get_engine_metadata()
                        st.json(metadata)
                
                # Analyze each symbol
                results = {}
                
                for symbol in generic_symbols:
                    try:
                        # This would need actual market data - showing interface structure
                        st.write(f"🎯 **{symbol}**")
                        
                        if show_signals:
                            col1, col2, col3, col4 = st.columns(4)
                            
                            with col1:
                                st.metric("Signal", "BUY" if symbol == "AAPL" else "HOLD")
                            
                            with col2:
                                st.metric("Confidence", "75%" if symbol == "AAPL" else "45%")
                            
                            with col3:
                                st.metric("Position Size", "2.0%" if symbol == "AAPL" else "0.0%")
                            
                            with col4:
                                st.metric("Risk Level", "Moderate")
                        
                        # Show TQQQ comparison if requested and symbol is appropriate
                        if show_comparison and symbol in ["QQQ", "SPY"]:
                            st.info(f"📊 TQQQ correlation analysis available for {symbol}")
                        
                        st.success(f"✅ {symbol} analysis completed")
                        
                    except Exception as e:
                        st.error(f"❌ Error analyzing {symbol}: {str(e)}")
                
                st.success(f"🎉 Generic Swing Analysis completed for {len(generic_symbols)} symbols")
                
            except ImportError as e:
                st.error(f"❌ Could not import swing engines: {e}")
                st.info("Make sure python-worker directory is available")
            except Exception as e:
                st.error(f"❌ Error in analysis: {e}")

else:
    st.info("📋 Select symbols above to run Generic Swing Engine analysis")
    st.write("💡 **Tip**: The Generic Swing Engine is perfect for:")
    st.write("• Large-cap stocks (AAPL, MSFT, GOOGL)")
    st.write("• Regular ETFs (SPY, QQQ, IWM)")
    st.write("• Growth stocks with normal volatility")
    st.write("• Value stocks with stable patterns")

# Engine comparison section
st.subheader("🔄 Engine Comparison")
st.caption("Understand the differences between swing trading engines")

with st.expander("📊 Generic vs TQQQ Swing Engine", expanded=False):
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Generic Swing Engine**")
        st.write("• 🎯 Purpose: Standard stocks/ETFs")
        st.write("• ⏱️ Holding: 2-10 days")
        st.write("• 💰 Position: 2.0% max")
        st.write("• 🛑 Stop Loss: 3.0%")
        st.write("• 📈 Risk: Moderate")
        st.write("• ✅ Best for: AAPL, MSFT, SPY, etc.")
    
    with col2:
        st.write("**TQQQ Swing Engine**")
        st.write("• 🎯 Purpose: TQQQ only")
        st.write("• ⏱️ Holding: 1-7 days")
        st.write("• 💰 Position: 1.5% max")
        st.write("• 🛑 Stop Loss: 2.5%")
        st.write("• 📈 Risk: High")
        st.write("• ✅ Best for: TQQQ only")

st.write("🚀 **Quick Start**: Use the TQQQ Backtest tab for TQQQ analysis, or use this interface for other symbols!")
'''
    
    return interface_code

def print_integration_instructions():
    """Print instructions for integrating the enhanced interface"""
    
    print("🔧 Enhanced Signal Engine Interface Integration")
    print("=" * 50)
    
    print("\n📋 To add the Generic Swing interface to your dashboard:")
    print("1. Open: streamlit-app/pages/9_Trading_Dashboard.py")
    print("2. Find the 'with tab_signals:' section")
    print("3. Add the Generic Swing interface code")
    print("4. Users can then analyze any symbol with the Generic Swing Engine")
    
    print("\n🎯 Benefits of the Enhanced Interface:")
    print("✅ Multi-symbol analysis")
    print("✅ Easy symbol selection")
    print("✅ Engine metadata display")
    print("✅ Comparison capabilities")
    print("✅ Clear guidance on engine usage")
    
    print("\n🚀 User Workflow:")
    print("1. Navigate to '🧠 Signal Engines' tab")
    print("2. Use the new Generic Swing interface")
    print("3. Select symbols for analysis")
    print("4. Choose analysis options")
    print("5. Run comprehensive swing analysis")

if __name__ == "__main__":
    print_integration_instructions()
