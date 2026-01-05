"""
Streamlit TQQQ Backtesting Interface
Interactive backtesting interface for TQQQ swing trading engine validation
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Dict, Any, List
import numpy as np

from app.backtesting.tqqq_backtester import TQQQBacktester, BacktestConfig, BacktestPeriod
from app.observability.logging import get_logger

logger = get_logger(__name__)


def render_tqqq_backtest_interface():
    """Render the TQQQ backtesting interface"""
    
    st.header("📊 TQQQ Swing Engine Backtesting")
    st.markdown("---")
    
    st.markdown("""
    **Validate the TQQQ swing trading engine with historical performance data**
    
    This backtesting system allows you to:
    - Test the engine against 1 year of historical data
    - See BUY/SELL/HOLD signals for any given date
    - Analyze performance metrics and risk statistics
    - Validate system effectiveness before live trading
    """)
    
    # Data Requirements Section
    st.subheader("📋 Data Requirements")
    
    with st.expander("🔍 Check Data Availability", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            check_tqqq = st.button("Check TQQQ", key="check_tqqq_data")
        
        with col2:
            check_qqq = st.button("Check QQQ", key="check_qqq_data")
        
        with col3:
            check_vix = st.button("Check VIX", key="check_vix_data")
        
        if check_tqqq or check_qqq or check_vix:
            symbols_to_check = []
            if check_tqqq:
                symbols_to_check.append("TQQQ")
            if check_qqq:
                symbols_to_check.append("QQQ")
            if check_vix:
                symbols_to_check.append("^VIX")
            
            _check_data_availability(symbols_to_check)
    
    # Quick Load Section
    with st.expander("🚀 Quick Load TQQQ Data", expanded=False):
        st.info("""
        **TQQQ Backtesting requires data for:**
        - **TQQQ** (primary symbol)
        - **QQQ** (underlying for correlation analysis)
        - **VIX** (volatility monitoring)
        
        Use the buttons below to load missing data.
        """)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            load_tqqq = st.button("📈 Load TQQQ", key="load_tqqq_backtest", type="primary")
        
        with col2:
            load_qqq = st.button("📊 Load QQQ", key="load_qqq_backtest")
        
        with col3:
            load_vix = st.button("📉 Load VIX", key="load_vix_backtest")
        
        if load_tqqq or load_qqq or load_vix:
            symbols_to_load = []
            if load_tqqq:
                symbols_to_load.append("TQQQ")
            if load_qqq:
                symbols_to_load.append("QQQ")
            if load_vix:
                symbols_to_load.append("^VIX")
            
            _load_backtest_data(symbols_to_load)
    
    # Backtest configuration
    st.subheader("⚙️ Backtest Configuration")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        period = st.selectbox(
            "Backtest Period",
            options=[
                ("Last Month", BacktestPeriod.LAST_MONTH),
                ("Last Quarter", BacktestPeriod.LAST_QUARTER),
                ("Last 6 Months", BacktestPeriod.LAST_SEMI_ANNUAL),
                ("Last Year", BacktestPeriod.LAST_YEAR),
                ("Year to Date", BacktestPeriod.YEAR_TO_DATE),
                ("Custom", BacktestPeriod.CUSTOM)
            ],
            index=3,  # Default to Last Year
            help="Select the period to backtest"
        )
    
    with col2:
        initial_capital = st.number_input(
            "Initial Capital ($)",
            value=10000,
            min_value=1000,
            max_value=100000,
            step=1000,
            help="Starting capital for backtest"
        )
    
    with col3:
        position_size = st.number_input(
            "Position Size (%)",
            value=1.5,
            min_value=0.5,
            max_value=5.0,
            step=0.5,
            help="Percentage of capital allocated per trade"
        )
    
    # Custom date range
    if period == BacktestPeriod.CUSTOM:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", datetime.now() - timedelta(days=365))
        with col2:
            end_date = st.date_input("End Date", datetime.now())
    else:
        start_date = None
        end_date = None
    
    # Advanced settings
    with st.expander("🔧 Advanced Settings"):
        col1, col2 = st.columns(2)
        
        with col1:
            include_commission = st.checkbox("Include Commission", value=True)
            commission_rate = st.number_input(
                "Commission Rate (%)",
                value=0.1,
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                disabled=not include_commission,
                help="Commission rate per trade"
            )
        
        with col2:
            include_slippage = st.checkbox("Include Slippage", value=True)
            slippage_rate = st.number_input(
                "Slippage Rate (%)",
                value=0.05,
                min_value=0.0,
                max_value=0.5,
                step=0.01,
                disabled=not include_slippage,
                help="Slippage rate per trade"
            )
    
    # Run backtest button
    run_backtest = st.button(
        "🚀 Run Backtest",
        type="primary",
        help="Run the TQQQ swing engine backtest with selected parameters"
    )
    
    if run_backtest:
        _run_backtest(
            period=period,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            position_size_pct=position_size / 100,
            include_commission=include_commission,
            commission_rate=commission_rate / 100,
            include_slippage=include_slippage,
            slippage_rate=slippage_rate / 100
        )
    
    # Date-specific signal lookup
    st.markdown("---")
    st.subheader("🔍 Historical Signal Lookup")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        lookup_date = st.date_input(
            "Select Date",
            value=datetime.now() - timedelta(days=1),
            max_value=datetime.now() - timedelta(days=1),
            help="Check what signal the engine generated for this specific date"
        )
    
    with col2:
        st.write("")
        st.write("")
        lookup_signal = st.button(
            "📋 Get Signal",
            help="Get the signal for the selected date"
        )
    
    with col3:
        st.write("")
        st.write("")
        if st.button("📅 Random Date"):
            # Pick a random trading day from the last year
            random_days = np.random.randint(1, 365)
            random_date = datetime.now() - timedelta(days=random_days)
            # Adjust to weekday
            while random_date.weekday() >= 5:
                random_date -= timedelta(days=1)
            st.session_state.lookup_date = random_date.date()
    
    if lookup_signal:
        _get_historical_signal(lookup_date)


def _run_backtest(period: BacktestPeriod, start_date: datetime, end_date: datetime,
                 initial_capital: float, position_size_pct: float,
                 include_commission: bool, commission_rate: float,
                 include_slippage: bool, slippage_rate: float):
    """Run the backtest and display results"""
    
    try:
        # Create backtest configuration
        config = BacktestConfig(
            period=period,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            position_size_pct=position_size_pct,
            include_commission=include_commission,
            commission_rate=commission_rate,
            slippage=slippage_rate
        )
        
        # Show progress
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("🚀 Initializing backtest...")
        progress_bar.progress(10)
        
        # Run backtest
        backtester = TQQQBacktester(config)
        
        status_text.text("📊 Loading historical data...")
        progress_bar.progress(30)
        
        result = backtester.run_backtest("TQQQ")
        
        status_text.text("📈 Calculating performance metrics...")
        progress_bar.progress(80)
        
        # Display results
        _display_backtest_results(result)
        
        progress_bar.progress(100)
        status_text.text("✅ Backtest completed successfully!")
        
        # Clear progress indicators
        progress_bar.empty()
        status_text.empty()
        
    except Exception as e:
        st.error(f"❌ Backtest failed: {str(e)}")
        logger.error(f"Backtest error: {e}")


def _display_backtest_results(result):
    """Display comprehensive backtest results"""
    
    # Store results in session state for detailed analysis
    st.session_state.backtest_result = result
    
    # Summary metrics
    st.subheader("📊 Performance Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Return",
            f"{result.total_return:.2%}",
            help="Total return over the entire backtest period"
        )
        st.metric(
            "Annualized Return",
            f"{result.annualized_return:.2%}",
            help="Annualized return assuming compounding"
        )
    
    with col2:
        st.metric(
            "Win Rate",
            f"{result.win_rate:.1%}",
            help="Percentage of profitable trades"
        )
        st.metric(
            "Total Trades",
            result.total_trades,
            help="Total number of trades executed"
        )
    
    with col3:
        st.metric(
            "Max Drawdown",
            f"{result.max_drawdown:.2%}",
            help="Maximum peak-to-trough decline"
        )
        st.metric(
            "Sharpe Ratio",
            f"{result.sharpe_ratio:.2f}",
            help="Risk-adjusted return (higher is better)"
        )
    
    with col4:
        st.metric(
            "Profit Factor",
            f"{result.profit_factor:.2f}",
            help="Gross profit / Gross loss"
        )
        st.metric(
            "Avg Trade Return",
            f"{result.avg_trade_return:.2%}",
            help="Average return per trade"
        )
    
    # Trade statistics
    st.subheader("📈 Trade Statistics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Winning Trades:**")
        st.write(f"- Count: {result.winning_trades}")
        st.write(f"- Average Return: {result.avg_winning_trade:.2%}")
        st.write(f"- Largest Win: {result.largest_win:.2%}")
    
    with col2:
        st.write("**Losing Trades:**")
        st.write(f"- Count: {result.losing_trades}")
        st.write(f"- Average Return: {result.avg_losing_trade:.2%}")
        st.write(f"- Largest Loss: {result.largest_loss:.2%}")
    
    # Equity curve
    st.subheader("💰 Equity Curve")
    
    if result.equity_curve:
        equity_df = pd.DataFrame(result.equity_curve, columns=['date', 'equity'])
        equity_df['date'] = pd.to_datetime(equity_df['date'])
        
        fig = go.Figure()
        
        # Add equity curve
        fig.add_trace(go.Scatter(
            x=equity_df['date'],
            y=equity_df['equity'],
            mode='lines',
            name='Portfolio Value',
            line=dict(color='blue', width=2)
        ))
        
        # Add initial capital line
        fig.add_hline(
            y=result.config.initial_capital,
            line_dash="dash",
            line_color="gray",
            annotation_text="Initial Capital"
        )
        
        fig.update_layout(
            title="Portfolio Equity Curve",
            xaxis_title="Date",
            yaxis_title="Portfolio Value ($)",
            height=400,
            showlegend=True
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # Monthly returns
    if result.monthly_returns:
        st.subheader("📅 Monthly Returns")
        
        months = sorted(result.monthly_returns.keys())
        returns = [result.monthly_returns[month] for month in months]
        
        colors = ['green' if r > 0 else 'red' for r in returns]
        
        fig = go.Figure(data=[
            go.Bar(x=months, y=returns, marker_color=colors)
        ])
        
        fig.update_layout(
            title="Monthly Returns",
            xaxis_title="Month",
            yaxis_title="Return (%)",
            height=300
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # Regime performance
    if result.regime_performance:
        st.subheader("🎭 Performance by Market Regime")
        
        regime_data = []
        for regime, stats in result.regime_performance.items():
            regime_data.append({
                'Regime': regime,
                'Trades': stats['trades'],
                'Win Rate': f"{stats['win_rate']:.1%}",
                'Avg Return': f"{stats['avg_return']:.2%}",
                'Total Return': f"${stats['total_return']:.2f}"
            })
        
        regime_df = pd.DataFrame(regime_data)
        st.dataframe(regime_df, use_container_width=True)
    
    # Detailed trade list
    if result.trades:
        st.subheader("📋 Detailed Trade History")
        
        # Show recent trades first
        recent_trades = sorted(result.trades, key=lambda x: x.exit_date, reverse=True)[:20]
        
        trade_data = []
        for trade in recent_trades:
            trade_data.append({
                'Exit Date': trade.exit_date.strftime('%Y-%m-%d'),
                'Signal': trade.signal.value,
                'Exit Reason': trade.exit_reason,
                'Return': f"{trade.return_pct:.2%}",
                'P&L': f"${trade.net_pnl:.2f}",
                'Holding Days': trade.holding_days,
                'Regime': trade.regime_at_entry,
                'VIX': f"{trade.vix_at_entry:.1f}",
                'Confidence': f"{trade.confidence:.1%}"
            })
        
        trades_df = pd.DataFrame(trade_data)
        st.dataframe(trades_df, use_container_width=True)
        
        # Download button for full results
        if st.button("📥 Download Full Trade History"):
            full_trade_data = []
            for trade in result.trades:
                full_trade_data.append({
                    'Entry Date': trade.entry_date.strftime('%Y-%m-%d'),
                    'Exit Date': trade.exit_date.strftime('%Y-%m-%d'),
                    'Signal': trade.signal.value,
                    'Exit Reason': trade.exit_reason,
                    'Entry Price': f"${trade.entry_price:.2f}",
                    'Exit Price': f"${trade.exit_price:.2f}",
                    'Return %': f"{trade.return_pct:.4f}",
                    'Gross P&L': f"${trade.gross_pnl:.2f}",
                    'Net P&L': f"${trade.net_pnl:.2f}",
                    'Holding Days': trade.holding_days,
                    'Regime': trade.regime_at_entry,
                    'VIX at Entry': trade.vix_at_entry,
                    'Confidence': trade.confidence
                })
            
            full_df = pd.DataFrame(full_trade_data)
            csv = full_df.to_csv(index=False)
            st.download_button(
                label="📊 Download CSV",
                data=csv,
                file_name=f"tqqq_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )


def _get_historical_signal(date: datetime):
    """Get the signal for a specific historical date"""
    
    try:
        with st.spinner(f"🔍 Analyzing TQQQ signal for {date}..."):
            # Create backtester to get signal
            backtester = TQQQBacktester()
            
            # Load data for the specific date
            end_date = date + timedelta(days=30)  # Get some data after the date
            start_date = date - timedelta(days=60)  # Get data before the date
            
            tqqq_data, qqq_data, vix_data = backtester._load_historical_data("TQQQ", start_date, end_date)
            
            if date not in tqqq_data.index:
                st.error(f"No trading data available for {date}")
                return
            
            # Get data up to the selected date
            tqqq_hist = tqqq_data.loc[:date]
            qqq_hist = qqq_data.loc[:date] if date in qqq_data.index else qqq_data.loc[:date].iloc[-1:]
            vix_hist = vix_data.loc[:date] if date in vix_data.index else vix_data.loc[:date].iloc[-1:]
            
            if len(tqqq_hist) < 30:
                st.error("Insufficient historical data for signal generation")
                return
            
            # Create market context
            from app.signal_engines.base import MarketContext, MarketRegime
            market_context = MarketContext(
                current_date=date,
                market_regime=MarketRegime.NEUTRAL,
                vix=vix_hist['close'].iloc[-1] if not vix_hist.empty else 20.0,
                spx_change=0.0,
                ndx_change=0.0,
                sector_performance={},
                macro_indicators={}
            )
            
            # Generate signal
            signal_result = backtester.engine.generate_signal("TQQQ", tqqq_hist, market_context)
            
            # Display signal
            _display_historical_signal(signal_result, date, tqqq_data.loc[date, 'close'])
            
    except Exception as e:
        st.error(f"❌ Error getting signal for {date}: {str(e)}")
        logger.error(f"Historical signal error: {e}")


def _display_historical_signal(signal_result, date: datetime, actual_price: float):
    """Display the historical signal result"""
    
    st.subheader(f"📊 TQQQ Signal for {date.strftime('%B %d, %Y')}")
    
    # Signal display with color coding
    signal_color = {
        "BUY": "🟢",
        "SELL": "🔴",
        "HOLD": "🟡"
    }.get(signal_result.signal.value, "⚪")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Signal",
            f"{signal_color} {signal_result.signal.value}",
            help="Trading signal generated by the engine"
        )
    
    with col2:
        st.metric(
            "Confidence",
            f"{signal_result.confidence:.1%}",
            help="Engine confidence in this signal"
        )
    
    with col3:
        st.metric(
            "Actual Price",
            f"${actual_price:.2f}",
            help="Actual TQQQ closing price on this date"
        )
    
    # Signal details
    st.write("**Signal Details:**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if signal_result.entry_price_range:
            st.write(f"**Entry Range:** ${signal_result.entry_price_range[0]:.2f} - ${signal_result.entry_price_range[1]:.2f}")
        
        if signal_result.stop_loss:
            st.write(f"**Stop Loss:** ${signal_result.stop_loss:.2f}")
        
        if signal_result.take_profit:
            st.write(f"**Take Profit:** ${signal_result.take_profit[0]:.2f}")
    
    with col2:
        st.write(f"**Timeframe:** {signal_result.timeframe}")
        st.write(f"**Engine:** {signal_result.engine_name}")
        st.write(f"**Position Size:** {signal_result.position_size_pct:.1%}")
    
    # Market context
    st.write("**Market Context:**")
    
    metadata = signal_result.metadata
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.write(f"**Regime:** {metadata.get('regime', 'Unknown')}")
    
    with col2:
        st.write(f"**VIX:** {metadata.get('vix', 'N/A')}")
    
    with col3:
        st.write(f"**QQQ Correlation:** {metadata.get('qqq_correlation', 'N/A')}")
    
    with col4:
        st.write(f"**Leverage Decay Risk:** {'Yes' if metadata.get('leverage_decay_risk', False) else 'No'}")
    
    # Reasoning
    if signal_result.reasoning:
        st.write("**Engine Reasoning:**")
        for reason in signal_result.reasoning:
            st.write(f"• {reason}")
    
    # Performance note
    st.info("""
    **Note:** This is the signal that would have been generated on this date based on the 
    information available at that time. Actual performance may vary due to market conditions,
    execution delays, and other factors.
    """)


def _check_data_availability(symbols: List[str]):
    """Check data availability for given symbols"""
    
    try:
        from app.utils.database_helper import DatabaseQueryHelper
        from datetime import datetime, timedelta
        
        db = DatabaseQueryHelper()
        
        availability_data = {}
        
        for symbol in symbols:
            try:
                # Check for data in the last year
                end_date = datetime.now()
                start_date = end_date - timedelta(days=365)
                
                data = db.get_historical_data(symbol, start_date, end_date)
                
                if data and not data.empty:
                    latest_date = data.index[-1]
                    record_count = len(data)
                    price_range = f"${data['close'].min():.2f} - ${data['close'].max():.2f}"
                    
                    availability_data[symbol] = {
                        'status': '✅ Available',
                        'records': record_count,
                        'latest_date': latest_date.strftime('%Y-%m-%d'),
                        'price_range': price_range,
                        'sufficient': record_count >= 250  # Need at least 1 year of trading days
                    }
                else:
                    availability_data[symbol] = {
                        'status': '❌ Not Found',
                        'records': 0,
                        'latest_date': 'N/A',
                        'price_range': 'N/A',
                        'sufficient': False
                    }
                    
            except Exception as e:
                availability_data[symbol] = {
                    'status': f'❌ Error: {str(e)[:50]}...',
                    'records': 0,
                    'latest_date': 'N/A',
                    'price_range': 'N/A',
                    'sufficient': False
                }
        
        # Display results
        st.subheader("📊 Data Availability Results")
        
        for symbol, data in availability_data.items():
            with st.expander(f"{symbol}: {data['status']}", expanded=not data['sufficient']):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Status", data['status'])
                
                with col2:
                    st.metric("Records", data['records'])
                
                with col3:
                    st.metric("Latest Date", data['latest_date'])
                
                with col4:
                    st.metric("Price Range", data['price_range'])
                
                if not data['sufficient']:
                    st.warning(f"⚠️ Insufficient data for backtesting (need ≥250 records, have {data['records']})")
                else:
                    st.success("✅ Sufficient data for backtesting")
        
        # Summary
        sufficient_symbols = [s for s, d in availability_data.items() if d['sufficient']]
        missing_symbols = [s for s, d in availability_data.items() if not d['sufficient']]
        
        if sufficient_symbols:
            st.success(f"✅ Ready for backtesting: {', '.join(sufficient_symbols)}")
        
        if missing_symbols:
            st.warning(f"⚠️ Need to load data for: {', '.join(missing_symbols)}")
        
    except Exception as e:
        st.error(f"❌ Error checking data availability: {str(e)}")


def _load_backtest_data(symbols: List[str]):
    """Load historical data for backtesting"""
    
    try:
        from app.data_management.refresh_manager import DataRefreshManager, DataType, RefreshMode
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        refresh_manager = DataRefreshManager()
        
        for i, symbol in enumerate(symbols):
            status_text.text(f"🔄 Loading data for {symbol}...")
            progress_bar.progress((i + 1) / len(symbols) * 0.8)
            
            try:
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL, DataType.INDICATORS],
                    mode=RefreshMode.ON_DEMAND,
                    force=True,
                )
                
                if result.total_failed == 0:
                    st.success(f"✅ {symbol}: Loaded {result.total_successful} records")
                else:
                    st.error(f"❌ {symbol}: Failed to load data")
                    st.json(result.to_dict())
                    
            except Exception as e:
                st.error(f"❌ {symbol}: {str(e)}")
        
        progress_bar.progress(1.0)
        status_text.text("✅ Data loading completed!")
        
        # Clear cache and show success message
        st.cache_data.clear()
        st.success("🎉 Data loading completed! You can now run the backtest.")
        st.balloons()
        
        # Clean up progress indicators
        progress_bar.empty()
        status_text.empty()
        
    except Exception as e:
        st.error(f"❌ Error loading backtest data: {str(e)}")
