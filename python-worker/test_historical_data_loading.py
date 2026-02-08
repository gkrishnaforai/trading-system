#!/usr/bin/env python3
"""
Load Historical Data for Specified Symbols
Based on the working TQQQ data loading pattern
"""

import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def load_historical_data_for_symbols():
    """Load historical data for specified symbols using TQQQ pattern"""
    
    print("🎯 LOADING HISTORICAL DATA FOR SPECIFIED SYMBOLS")
    print("=" * 60)
    print("Based on working TQQQ data loading pattern")
    print()
    
    # Your specified symbols (same pattern as TQQQ script)
    symbols = ["SOFI", "NVDA", "AVGO", "MU", "GOOGL", "APLD", "IREN", "ZETA", "NBIS", "CRWV", "QQQ", "SMH"]
    
    print(f"📊 Loading historical data for {len(symbols)} symbols")
    print(f"🔤 Symbols: {', '.join(symbols)}")
    print()
    
    try:
        from app.data_management.refresh_manager import DataRefreshManager, DataType, RefreshMode
        
        print("✅ DataRefreshManager imported successfully")
        
        # Create refresh manager (exact same as TQQQ script)
        refresh_manager = DataRefreshManager()
        print("✅ DataRefreshManager initialized")
        
        results = {}
        
        for i, symbol in enumerate(symbols, 1):
            print(f"🔄 [{i}/{len(symbols)}] Loading {symbol}...")
            
            try:
                # Use exact same call as TQQQ script
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL, DataType.INDICATORS],
                    mode=RefreshMode.ON_DEMAND,
                    force=True,
                )
                
                results[symbol] = result
                
                # Use exact same success logic as TQQQ script
                if result.total_failed == 0:
                    print(f"✅ {symbol}: Successfully loaded {result.total_successful} records")
                else:
                    print(f"⚠️  {symbol}: {result.total_failed} operations failed")
                    if result.total_successful > 0:
                        print(f"   But {result.total_successful} succeeded")
                
                # Show detailed operation results (fixed version)
                if hasattr(result, 'results') and result.results:
                    for data_type, operation_result in result.results.items():
                        if hasattr(operation_result, 'status') and operation_result.status.value == 'success':
                            print(f"   ✓ {data_type}: {operation_result.message}")
                        else:
                            print(f"   ✗ {data_type}: {operation_result.error if hasattr(operation_result, 'error') else 'Unknown error'}")
                
            except Exception as e:
                print(f"❌ {symbol}: Failed to load data - {str(e)}")
                results[symbol] = None
        
        # Summary (exact same as TQQQ script)
        print(f"\n📋 HISTORICAL DATA LOADING SUMMARY")
        print("=" * 40)
        
        successful_symbols = []
        failed_symbols = []
        
        for symbol, result in results.items():
            if result and result.total_failed == 0:
                successful_symbols.append(symbol)
                print(f"✅ {symbol}: READY")
            else:
                failed_symbols.append(symbol)
                print(f"❌ {symbol}: FAILED")
        
        if successful_symbols:
            print(f"\n🎉 Ready for swing trading: {', '.join(successful_symbols)}")
        
        if failed_symbols:
            print(f"\n⚠️  Need attention: {', '.join(failed_symbols)}")
            print("   Check API keys or database connection")
        
        # Check if we have enough symbols (exact same logic as TQQQ script)
        if len(successful_symbols) >= 1:
            print(f"\n✅ Swing trading possible with {len(successful_symbols)} symbols")
            
            if len(successful_symbols) == len(symbols):
                print("🎉 All symbols loaded successfully!")
            else:
                print(f"⚠️  {len(successful_symbols)}/{len(symbols)} symbols available")
        else:
            print(f"\n❌ No symbols loaded successfully")
        
        return successful_symbols, failed_symbols
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all dependencies are installed")
        return [], []
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return [], []

def verify_data_loaded():
    """Verify that data was loaded successfully including indicators"""
    
    print("\n🔍 VERIFYING DATA LOADING")
    print("=" * 40)
    
    try:
        import psycopg2
        import os
        from datetime import datetime
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check data for all target symbols
        target_symbols = ["SOFI", "NVDA", "AVGO", "MU", "GOOGL", "APLD", "IREN", "ZETA", "NBIS", "CRWV", "QQQ", "SMH"]
        
        # Check price data
        cursor.execute("""
            SELECT DISTINCT symbol, 
                   COUNT(*) as record_count,
                   MIN(date) as start_date,
                   MAX(date) as end_date
            FROM raw_market_data_daily 
            WHERE symbol = ANY(%s)
            GROUP BY symbol 
            ORDER BY symbol
        """, (target_symbols,))
        
        price_results = cursor.fetchall()
        
        # Check indicators data
        cursor.execute("""
            SELECT DISTINCT symbol, 
                   COUNT(*) as record_count,
                   COUNT(ema_20) FILTER (WHERE ema_20 IS NOT NULL) as ema_count,
                   COUNT(sma_50) FILTER (WHERE sma_50 IS NOT NULL) as sma_count,
                   COUNT(rsi_14) FILTER (WHERE rsi_14 IS NOT NULL) as rsi_count,
                   MIN(date) as start_date,
                   MAX(date) as end_date,
                   COUNT(DISTINCT data_source) as source_count
            FROM indicators_daily 
            WHERE symbol = ANY(%s)
            GROUP BY symbol 
            ORDER BY symbol
        """, (target_symbols,))
        
        indicator_results = cursor.fetchall()
        
        if not price_results and not indicator_results:
            print("❌ No data found for target symbols")
            return False
        
        print(f"✅ Found data for {len(price_results)} symbols with price data")
        print(f"✅ Found indicators for {len(indicator_results)} symbols")
        print()
        
        # Display price data summary
        if price_results:
            print(f"{'PRICE DATA':<12} {'Records':<8} {'Date Range':<22} {'Status':<10}")
            print("-" * 60)
            
            for row in price_results:
                symbol, count, start_date, end_date = row
                date_range = f"{start_date} to {end_date}"
                
                # Determine status
                if count >= 200:
                    status = "Full Year"
                elif count >= 50:
                    status = "Partial"
                else:
                    status = "Limited"
                
                print(f"{symbol:<12} {count:<8} {date_range:<22} {status:<10}")
        
        print()
        
        # Display indicators data summary
        if indicator_results:
            print(f"{'INDICATORS':<12} {'Total':<6} {'EMA':<4} {'SMA50':<6} {'RSI':<4} {'Sources':<7} {'Date Range':<22} {'Status':<10}")
            print("-" * 80)
            
            symbols_with_indicators = []
            
            for row in indicator_results:
                symbol, total, ema_count, sma_count, rsi_count, start_date, end_date, source_count = row
                date_range = f"{start_date} to {end_date}"
                
                # Determine status based on indicator coverage
                if ema_count >= 50 and sma_count >= 50 and rsi_count >= 50:
                    status = "Complete"
                    symbols_with_indicators.append(symbol)
                elif ema_count >= 20 and sma_count >= 20:
                    status = "Partial"
                else:
                    status = "Limited"
                
                sources = f"{source_count} src"
                
                print(f"{symbol:<12} {total:<6} {ema_count:<4} {sma_count:<6} {rsi_count:<4} {sources:<7} {date_range:<22} {status:<10}")
        
        print()
        
        # Check for FMP API usage
        cursor.execute("""
            SELECT DISTINCT symbol, data_source, COUNT(*) as count
            FROM indicators_daily 
            WHERE symbol = ANY(%s) AND data_source = 'fmp_api'
            GROUP BY symbol, data_source
            ORDER BY symbol
        """, (target_symbols,))
        
        fmp_results = cursor.fetchall()
        if fmp_results:
            print(f"🎯 FMP API INDICATORS:")
            print(f"{'Symbol':<12} {'Data Source':<12} {'Records':<8}")
            print("-" * 40)
            for symbol, data_source, count in fmp_results:
                print(f"{symbol:<12} {data_source:<12} {count:<8}")
            print()
        
        # Summary
        print(f"📊 SUMMARY:")
        print(f"   Symbols with price data: {len(price_results)}/{len(target_symbols)}")
        print(f"   Symbols with indicators: {len(indicator_results)}/{len(target_symbols)}")
        print(f"   Symbols with FMP indicators: {len(fmp_results)}/{len(target_symbols)}")
        print(f"   Symbols with complete indicators: {len(symbols_with_indicators)}")
        
        if symbols_with_indicators:
            print(f"   ✅ Complete indicators: {', '.join(symbols_with_indicators)}")
        
        missing_price = [s for s in target_symbols if s not in [r[0] for r in price_results]]
        missing_indicators = [s for s in target_symbols if s not in [r[0] for r in indicator_results]]
        
        if missing_price:
            print(f"   ❌ Missing price data: {', '.join(missing_price)}")
        if missing_indicators:
            print(f"   ❌ Missing indicators: {', '.join(missing_indicators)}")
        
        conn.close()
        
        return len(symbols_with_indicators) > 0
        
    except Exception as e:
        print(f"❌ Error verifying data: {e}")
        return False

def show_audit_details():
    """Show audit details for the data loading operations"""
    
    print("\n🔍 AUDIT DETAILS")
    print("=" * 40)
    
    try:
        import psycopg2
        import os
        from datetime import datetime, timedelta
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Get recent audit runs (last 24 hours)
        cursor.execute("""
            SELECT run_id, status, started_at, finished_at, 
                   EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_seconds
            FROM data_ingestion_runs 
            WHERE started_at >= NOW() - INTERVAL '24 hours'
            ORDER BY started_at DESC
            LIMIT 10
        """)
        
        audit_runs = cursor.fetchall()
        
        if not audit_runs:
            print("❌ No audit runs found in the last 24 hours")
            conn.close()
            return
        
        print(f"📊 RECENT AUDIT RUNS (Last 24 Hours):")
        print(f"{'Run ID':<8} {'Status':<8} {'Duration':<10} {'Started':<20} {'Finished':<20}")
        print("-" * 80)
        
        for run in audit_runs:
            run_id, status, started_at, finished_at, duration = run
            
            duration_str = f"{duration:.1f}s" if duration else "N/A"
            started_str = started_at.strftime("%H:%M:%S") if started_at else "N/A"
            finished_str = finished_at.strftime("%H:%M:%S") if finished_at else "N/A"
            run_id_str = str(run_id)[:8] if run_id else "N/A"  # Convert UUID to string and show first 8 chars
            
            print(f"{run_id_str:<8} {status:<8} {duration_str:<10} {started_str:<20} {finished_str:<20}")
        
        print()
        
        # Get detailed events for the most recent runs
        cursor.execute("""
            SELECT DISTINCT run_id, operation, COUNT(*) as event_count,
                   MAX(created_at) as last_event
            FROM data_ingestion_events 
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY run_id, operation
            ORDER BY run_id, operation
        """)
        
        events_summary = cursor.fetchall()
        
        if events_summary:
            print(f"📋 AUDIT EVENTS SUMMARY:")
            print(f"{'Run ID':<8} {'Operation':<20} {'Count':<6} {'Last Event':<20}")
            print("-" * 70)
            
            for event in events_summary:
                run_id, operation, event_count, last_event = event
                last_event_str = last_event.strftime("%H:%M:%S") if last_event else "N/A"
                run_id_str = str(run_id)[:8] if run_id else "N/A"  # Convert UUID to string and show first 8 chars
                print(f"{run_id_str:<8} {operation:<20} {event_count:<6} {last_event_str:<20}")
            
            print()
        
        # Check for any fallback usage in the last 24 hours
        cursor.execute("""
            SELECT run_id, symbol, operation, provider, message, created_at
            FROM data_ingestion_events 
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            AND operation LIKE 'fallback_%'
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        fallback_events = cursor.fetchall()
        
        if fallback_events:
            print(f"🔄 FALLBACK USAGE DETECTED:")
            print(f"{'Run ID':<8} {'Symbol':<6} {'Operation':<20} {'Provider':<12} {'Time':<8} {'Message'}")
            print("-" * 100)
            for event in fallback_events:
                run_id, symbol, operation, provider, message, created_at = event
                run_id_str = str(run_id)[:8] if run_id else "N/A"
                time_str = created_at.strftime("%H:%M:%S")
                operation_clean = operation.replace('fallback_', '')
                print(f"{run_id_str:<8} {symbol:<6} {operation_clean:<20} {provider:<12} {time_str:<8} {message}")
            print()
        else:
            print("✅ No fallback usage detected in the last 24 hours")
            print()
        
        # Check for any errors in the last 24 hours
        cursor.execute("""
            SELECT run_id, operation, error_message, created_at
            FROM data_ingestion_events 
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            AND error_message IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 5
        """)
        
        errors = cursor.fetchall()
        
        if errors:
            print(f"❌ RECENT ERRORS:")
            print("-" * 60)
            for error in errors:
                run_id, operation, error_message, created_at = error
                time_str = created_at.strftime("%H:%M:%S")
                run_id_str = str(run_id)[:8] if run_id else "N/A"  # Convert UUID to string and show first 8 chars
                print(f"{time_str} [{run_id_str}] {operation}: {error_message}")
            print()
        else:
            print("✅ No errors found in the last 24 hours")
            print()
        
        # Get data source usage statistics
        cursor.execute("""
            SELECT data_source, COUNT(*) as record_count, 
                   COUNT(DISTINCT symbol) as symbol_count,
                   MAX(updated_at) as last_update
            FROM indicators_daily 
            WHERE updated_at >= NOW() - INTERVAL '24 hours'
            GROUP BY data_source
            ORDER BY record_count DESC
        """)
        
        source_stats = cursor.fetchall()
        
        if source_stats:
            print(f"📊 DATA SOURCE USAGE (Last 24 Hours):")
            print(f"{'Source':<12} {'Records':<8} {'Symbols':<8} {'Last Update':<20}")
            print("-" * 60)
            
            for source, record_count, symbol_count, last_update in source_stats:
                last_update_str = last_update.strftime("%H:%M:%S") if last_update else "N/A"
                print(f"{source:<12} {record_count:<8} {symbol_count:<8} {last_update_str:<20}")
            
            print()
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error fetching audit details: {e}")

def main():
    """Main function - enhanced with indicators and audit details"""
    
    print("🚀 HISTORICAL DATA LOADER WITH INDICATORS")
    print("=" * 60)
    print("Based on working TQQQ data loading pattern")
    print("Loads historical data and indicators for specified symbols")
    print("Includes comprehensive audit details")
    print()
    
    # Load data
    successful, failed = load_historical_data_for_symbols()
    
    # Verify data including indicators
    has_substantial_data = verify_data_loaded()
    
    # Show audit details
    show_audit_details()
    
    # Final summary
    print(f"\n📊 FINAL SUMMARY")
    print("=" * 30)
    print(f"✅ Successful: {len(successful)}/{len(successful + failed)} symbols")
    print(f"❌ Failed: {len(failed)}/{len(successful + failed)} symbols")
    print(f"📅 Substantial data: {'✅' if has_substantial_data else '❌'}")
    print()
    
    if successful:
        print("🎉 HISTORICAL DATA LOADING COMPLETED!")
        print("Price data and indicators loaded successfully.")
        print("You can now test swing engines with loaded data.")
        print()
        print("🚀 Next steps:")
        print("1. Test swing engines:")
        print("   python test_swing_engines_multiple_symbols.py")
        print("2. Analyze signals:")
        print("   python simple_data_loader.py")
        print("3. Compare engines:")
        print("   python comprehensive_signal_analysis.py")
        print("4. Check EMA data health:")
        print("   curl http://127.0.0.1:8001/admin/ema-data-health/AAPL")
        
        if not has_substantial_data:
            print("⚠️  Note: Some symbols may have limited historical data")
            print("   Consider loading more data if needed for comprehensive testing")
    else:
        print("❌ HISTORICAL DATA LOADING FAILED!")
        print("Check the errors above and troubleshoot accordingly.")
    
    return len(successful) > 0

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n🎉 HISTORICAL DATA LOADING WITH INDICATORS COMPLETED SUCCESSFULLY!")
        print("✅ Price data and indicators loaded for analysis engines.")
        print("✅ Audit details available for monitoring.")
        print("You can now test swing engines with your specified symbols.")
    else:
        print("\n❌ HISTORICAL DATA LOADING WITH INDICATORS FAILED!")
        print("Check the errors and audit details above for troubleshooting.")
