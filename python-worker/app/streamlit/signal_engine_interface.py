"""
Streamlit Signal Engine Interface
UI components for running signal engines and displaying results
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import Dict, Any, List, Optional

from app.signal_engines.factory import SignalEngineFactory
from app.signal_engines.swing_engine_factory import get_swing_engine_for_symbol, SwingEngineType
from app.signal_engines.aggregation_service import SignalAggregationService
from app.repositories.signal_repository import SignalRepository
from app.services.market_context_service import MarketContextService
from app.services.stock_insights_service import StockInsightsService
from app.observability.logging import get_logger
from app.observability import audit

logger = get_logger(__name__)


def render_signal_engine_interface(symbol: str):
    """Render the signal engine interface for the selected symbol."""
    
    st.header("🔬 Signal Engine Analysis")
    st.markdown("---")
    
    # Initialize session state
    if 'signal_results' not in st.session_state:
        st.session_state.signal_results = {}
    
    # Engine selection with automatic recommendation
    col1, col2 = st.columns([2, 1])
    
    with col1:
        available_engines = SignalEngineFactory.get_available_engines()
        
        # Get recommended engine for the symbol
        if symbol.upper() == "TQQQ":
            recommended_engine = "tqqq_swing"
            st.info("🎯 **TQQQ Detected**: Automatically recommending TQQQ-specific swing engine for leverage decay awareness")
        else:
            # For non-TQQQ symbols, recommend generic swing if available, otherwise use first available
            swing_engines = [e for e in available_engines if 'swing' in e['name'].lower()]
            if swing_engines:
                recommended_engine = swing_engines[0]['name']
            else:
                recommended_engine = available_engines[0]['name'] if available_engines else "legacy"
        
        engine_options = {f"{engine['display_name']} ({engine['tier']})": engine['name'] 
                         for engine in available_engines}
        
        # Set default to recommended engine
        engine_display_names = list(engine_options.keys())
        default_index = 0
        for i, display_name in enumerate(engine_display_names):
            if engine_options[display_name] == recommended_engine:
                default_index = i
                break
        
        selected_engine_display = st.selectbox(
            "Select Signal Engine",
            options=engine_display_names,
            index=default_index,
            help=f"Recommended: {recommended_engine}. Choose which signal engine to run."
        )
        selected_engine = engine_options[selected_engine_display]
        
        # Show engine info
        if selected_engine == "tqqq_swing":
            st.warning("⚠️ **TQQQ Engine**: Specialized for TQQQ with leverage decay awareness. Should sit in cash 30-50% of the time.")
        elif "swing" in selected_engine.lower():
            st.info("📊 **Swing Engine**: Designed for 2-10 day holding periods with regime awareness.")
    
    with col2:
        run_multi = st.checkbox(
            "Run All Engines",
            value=False,
            help="Run all available engines and aggregate results"
        )
    
    col1, col2 = st.columns([2, 1])
    with col1:
        timeframe = st.selectbox(
            "Timeframe",
            options=["position", "swing", "day"],
            index=0,
            help="Analysis timeframe",
        )
    with col2:
        st.write("")
        run_button = st.button(
            "🚀 Run Analysis",
            type="primary",
            disabled=not bool(symbol),
        )
    
    if run_button and symbol:
        _run_signal_analysis(symbol, selected_engine, run_multi, timeframe)
    
    # Display results
    if st.session_state.signal_results:
        _display_signal_results()
    
    # Historical results
    st.markdown("---")
    _display_historical_signals(symbol if symbol else "")


def _run_signal_analysis(symbol: str, engine: str, run_multi: bool, timeframe: str):
    """Run signal analysis for the given symbol"""
    
    try:
        with st.spinner(f"Running signal analysis for {symbol}..."):
            market_context_service = MarketContextService()
            insights_service = StockInsightsService()
            aggregation_service = SignalAggregationService()
            
            # Get market context
            market_context = market_context_service.get_market_context()
            
            # Get market data
            market_data = insights_service._fetch_market_data(symbol)
            if market_data is None or len(market_data) == 0:
                st.error(f"No market data available for {symbol}")
                return
            
            # Get indicators
            indicators = insights_service._fetch_indicators(symbol)
            
            # Get fundamentals
            fundamentals = insights_service._fetch_fundamentals(symbol)
            
            # Run signal engines
            if run_multi:
                # Run all engines
                result = aggregation_service.generate_multi_engine_signal(
                    symbol, market_data, indicators, fundamentals, market_context
                )
                
                # Save aggregated result
                SignalRepository.save_aggregated_result(result)
                
                # Store in session state
                st.session_state.signal_results = {
                    'type': 'aggregated',
                    'result': result.to_dict()
                }
                
                audit.log_event(
                    level="INFO",
                    operation="signal_engine.run_multi",
                    provider="signal_engines",
                    symbol=symbol,
                    message="Multi-engine signal run completed",
                    context={
                        "engines": list(result.engine_results.keys()),
                        "consensus_signal": result.consensus_signal.value,
                        "consensus_confidence": result.consensus_confidence,
                        "recommended_engine": result.recommended_engine,
                    },
                )
                
            else:
                # Run single engine
                engine_instance = SignalEngineFactory.get_engine(engine)
                result = engine_instance.generate_signal(
                    symbol, market_data, indicators, fundamentals, market_context
                )
                
                # Save result
                SignalRepository.save_signal_result(result)
                
                # Store in session state
                st.session_state.signal_results = {
                    'type': 'single',
                    'result': result.to_dict()
                }
                
                audit.log_event(
                    level="INFO",
                    operation="signal_engine.run_single",
                    provider="signal_engines",
                    symbol=symbol,
                    message="Single-engine signal run completed",
                    context={
                        "engine": engine,
                        "signal": result.signal.value,
                        "confidence": result.confidence,
                    },
                )
            
            st.success(f"✅ Analysis complete for {symbol}")
            
    except Exception as e:
        st.error(f"❌ Error running analysis: {str(e)}")
        logger.error(f"Signal analysis failed for {symbol}: {str(e)}", 
                    extra={'symbol': symbol, 'engine': engine})
        audit.log_event(
            level="ERROR",
            operation="signal_engine.run_failed",
            provider="signal_engines",
            symbol=symbol,
            message="Signal engine run failed",
            context={"engine": engine, "run_multi": run_multi, "timeframe": timeframe},
            exception=e,
        )


def _display_signal_results():
    """Display signal analysis results"""
    
    results = st.session_state.signal_results
    
    if results['type'] == 'aggregated':
        _display_aggregated_results(results['result'])
    else:
        _display_single_engine_results(results['result'])


def _display_single_engine_results(result: Dict[str, Any]):
    """Display results from a single engine"""
    
    st.subheader(f"📊 {result['engine_name'].title()} Engine Results")
    
    # Main signal card
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        signal_color = {
            'BUY': '🟢',
            'HOLD': '🟡', 
            'SELL': '🔴'
        }.get(result['signal'], '⚪')
        
        st.metric(
            "Signal",
            f"{signal_color} {result['signal']}",
            help="Generated signal"
        )
    
    with col2:
        st.metric(
            "Confidence",
            f"{result['confidence']:.2f}",
            help="Confidence score (0-1)"
        )
    
    with col3:
        st.metric(
            "Position Size",
            f"{result['position_size_pct']*100:.1f}%",
            help="Recommended position size"
        )
    
    with col4:
        st.metric(
            "Timeframe",
            result['timeframe'].title(),
            help="Analysis timeframe"
        )
    
    # Entry/exit levels
    if result['signal'] != 'HOLD':
        st.subheader("📈 Entry & Exit Levels")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if result['entry_price_range']:
                st.write("**Entry Range:**")
                st.code(f"${result['entry_price_range'][0]:.2f} - ${result['entry_price_range'][1]:.2f}")
        
        with col2:
            if result['stop_loss']:
                st.write("**Stop Loss:**")
                st.code(f"${result['stop_loss']:.2f}")
        
        with col3:
            if result['take_profit']:
                st.write("**Take Profit:**")
                for i, target in enumerate(result['take_profit'], 1):
                    st.code(f"Target {i}: ${target:.2f}")
    
    # Reasoning
    st.subheader("🧠 Reasoning")
    for reason in result['reasoning']:
        st.write(f"• {reason}")
    
    # Metadata
    if result['metadata']:
        with st.expander("📋 Technical Details"):
            st.json(result['metadata'])


def _display_aggregated_results(result: Dict[str, Any]):
    """Display aggregated results from multiple engines"""
    
    st.subheader("🎯 Multi-Engine Analysis")
    
    # Consensus signal
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        signal_color = {
            'BUY': '🟢',
            'HOLD': '🟡',
            'SELL': '🔴'
        }.get(result['consensus_signal'], '⚪')
        
        st.metric(
            "Consensus Signal",
            f"{signal_color} {result['consensus_signal']}",
            help="Consensus signal from all engines"
        )
    
    with col2:
        st.metric(
            "Consensus Confidence",
            f"{result['consensus_confidence']:.2f}",
            help="Average confidence across engines"
        )
    
    with col3:
        st.metric(
            "Recommended Engine",
            result['recommended_engine'].title(),
            help="Best engine for current regime"
        )
    
    with col4:
        engines_count = len(result['engine_results'])
        st.metric(
            "Engines Run",
            str(engines_count),
            help="Number of engines analyzed"
        )
    
    # Engine comparison
    st.subheader("🔍 Engine Comparison")
    
    engine_data = []
    for engine_name, engine_result in result['engine_results'].items():
        engine_data.append({
            'Engine': engine_name.title(),
            'Signal': engine_result['signal'],
            'Confidence': f"{engine_result['confidence']:.2f}",
            'Position Size': f"{engine_result['position_size_pct']*100:.1f}%",
            'Timeframe': engine_result['timeframe'].title()
        })
    
    df = pd.DataFrame(engine_data)
    st.dataframe(df, use_container_width=True)
    
    # Conflicts
    if result['conflicts']:
        st.subheader("⚠️ Engine Conflicts")
        for conflict in result['conflicts']:
            st.warning(conflict)
    
    # Consensus reasoning
    st.subheader("🧠 Consensus Reasoning")
    for reason in result['reasoning']:
        st.write(f"• {reason}")
    
    # Individual engine details
    st.subheader("📊 Individual Engine Results")
    
    for engine_name, engine_result in result['engine_results'].items():
        with st.expander(f"{engine_name.title()} Engine Details"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Signal:** {engine_result['signal']}")
                st.write(f"**Confidence:** {engine_result['confidence']:.2f}")
                st.write(f"**Position Size:** {engine_result['position_size_pct']*100:.1f}%")
            
            with col2:
                if engine_result['entry_price_range']:
                    st.write(f"**Entry:** ${engine_result['entry_price_range'][0]:.2f} - ${engine_result['entry_price_range'][1]:.2f}")
                if engine_result['stop_loss']:
                    st.write(f"**Stop:** ${engine_result['stop_loss']:.2f}")
                if engine_result['take_profit']:
                    st.write(f"**Target:** ${engine_result['take_profit'][0]:.2f}")
            
            st.write("**Reasoning:**")
            for reason in engine_result['reasoning']:
                st.write(f"• {reason}")


def _display_historical_signals(symbol: str):
    """Display historical signal results"""
    
    if not symbol:
        st.info("Enter a symbol to view historical signals")
        return
    
    st.subheader(f"📚 Historical Signals for {symbol}")
    
    try:
        # Get historical signals
        historical_signals = SignalRepository.fetch_signals_by_symbol(symbol, limit=10)
        
        if not historical_signals:
            st.info(f"No historical signals found for {symbol}")
            return
        
        # Create dataframe
        signal_data = []
        for signal in historical_signals:
            signal_data.append({
                'Date': signal['signal_date'],
                'Engine': signal['engine_name'],
                'Signal': signal['signal'],
                'Confidence': f"{signal['confidence']:.2f}",
                'Position Size': f"{signal['position_size_pct']*100:.1f}%",
                'Timeframe': signal['timeframe']
            })
        
        df = pd.DataFrame(signal_data)
        st.dataframe(df, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error loading historical signals: {str(e)}")
        logger.error(f"Failed to load historical signals for {symbol}: {str(e)}")
        audit.log_event(
            level="ERROR",
            operation="signal_engine.history_failed",
            provider="signal_engines",
            symbol=symbol,
            message="Failed to load historical signals",
            context={},
            exception=e,
        )


def render_screener_interface():
    """Render the screener interface for signal-based filtering"""
    
    st.header("🔍 Signal Screener")
    st.markdown("---")
    
    # Screener selection
    screener_options = {
        "Strong Buy Signals (All Engines)": "strong_buy_all",
        "Strong Buy - Swing Trading": "strong_buy_swing", 
        "Strong Buy - Position Trading": "strong_buy_position",
        "High Confidence (>0.7)": "high_confidence",
        "Recent BUY Signals": "recent_buy",
        "All Current Signals": "all_signals"
    }
    
    selected_screener = st.selectbox(
        "Select Screener",
        options=list(screener_options.keys()),
        index=0
    )
    
    screener_key = screener_options[selected_screener]
    
    # Run screener button
    if st.button("🔍 Run Screener"):
        _run_screener(screener_key)
    
    # Display screener results
    if 'screener_results' in st.session_state:
        _display_screener_results()


def _run_screener(screener_key: str):
    """Run the selected screener"""
    
    try:
        with st.spinner("Running screener..."):
            # Get signals based on screener criteria
            if screener_key == "strong_buy_all":
                signals = SignalRepository.fetch_signals_by_criteria(
                    signal="BUY",
                    confidence_min=0.6,
                    limit=50
                )
            elif screener_key == "strong_buy_swing":
                signals = SignalRepository.fetch_signals_by_criteria(
                    signal="BUY",
                    confidence_min=0.65,
                    timeframe="swing",
                    limit=50
                )
            elif screener_key == "strong_buy_position":
                signals = SignalRepository.fetch_signals_by_criteria(
                    signal="BUY",
                    confidence_min=0.6,
                    timeframe="position",
                    limit=50
                )
            elif screener_key == "high_confidence":
                signals = SignalRepository.fetch_signals_by_criteria(
                    confidence_min=0.7,
                    limit=50
                )
            elif screener_key == "recent_buy":
                signals = SignalRepository.fetch_signals_by_criteria(
                    signal="BUY",
                    limit=50
                )
            else:  # all_signals
                signals = SignalRepository.fetch_signals_by_criteria(limit=50)
            
            # Store results
            st.session_state.screener_results = signals
            
            st.success(f"✅ Found {len(signals)} signals")
            
    except Exception as e:
        st.error(f"❌ Error running screener: {str(e)}")
        logger.error(f"Screener failed: {str(e)}")
        audit.log_event(
            level="ERROR",
            operation="signal_engine.screener_failed",
            provider="signal_engines",
            symbol=None,
            message="Signal screener failed",
            context={"screener_key": screener_key},
            exception=e,
        )


def _display_screener_results():
    """Display screener results"""
    
    signals = st.session_state.screener_results
    
    if not signals:
        st.info("No signals found")
        return
    
    st.subheader(f"📊 Screener Results ({len(signals)} signals)")
    
    # Create dataframe
    signal_data = []
    for signal in signals:
        signal_data.append({
            'Symbol': signal['stock_symbol'],
            'Signal': signal['signal'],
            'Confidence': f"{signal['confidence']:.2f}",
            'Engine': signal['engine_name'],
            'Position Size': f"{signal['position_size_pct']*100:.1f}%",
            'Timeframe': signal['timeframe'],
            'Date': signal['signal_date']
        })
    
    df = pd.DataFrame(signal_data)
    
    # Display with sorting
    st.dataframe(df, use_container_width=True)
    
    # Download button
    csv = df.to_csv(index=False)
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=f"signal_screener_{date.today()}.csv",
        mime="text/csv"
    )
