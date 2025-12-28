#!/usr/bin/env python3
"""
Test Data Validation System
Fetches data for TQQQ and displays validation report
"""
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_database, db
from app.data_validation import DataValidator
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import RefreshMode, DataType

def test_validation():
    """Test validation system with TQQQ"""
    print("🧪 Testing Data Validation System")
    print("=" * 60)
    
    # Initialize database
    init_database()
    
    # Initialize validator and refresh manager
    validator = DataValidator()
    refresh_manager = DataRefreshManager()
    
    symbol = "TQQQ"
    print(f"\n📊 Testing with symbol: {symbol}")
    
    # Fetch and validate data
    print(f"\n1️⃣ Fetching historical data for {symbol}...")
    refresh_result = refresh_manager.refresh_data(
        symbol=symbol,
        data_types=[DataType.PRICE_HISTORICAL],
        mode=RefreshMode.ON_DEMAND,
        force=True
    )
    
    price_result = refresh_result.results.get('price_historical')
    if price_result:
        print(f"   Status: {price_result.status.value}")
        print(f"   Message: {price_result.message}")
        print(f"   Rows affected: {price_result.rows_affected}")
        if price_result.error:
            print(f"   Error: {price_result.error}")
    
    # Get validation report from database
    print(f"\n2️⃣ Retrieving validation report from database...")
    query = """
        SELECT 
            report_id,
            symbol,
            data_type,
            overall_status,
            critical_issues,
            warnings,
            rows_dropped,
            datetime(validation_timestamp) as timestamp,
            report_json
        FROM data_validation_reports
        WHERE symbol = :symbol AND data_type = 'price_historical'
        ORDER BY validation_timestamp DESC
        LIMIT 1
    """
    result = db.execute_query(query, {"symbol": symbol})
    
    if result:
        report_data = result[0]
        print(f"\n✅ Validation Report Found:")
        print(f"   Report ID: {report_data['report_id']}")
        print(f"   Symbol: {report_data['symbol']}")
        print(f"   Data Type: {report_data['data_type']}")
        print(f"   Overall Status: {report_data['overall_status'].upper()}")
        print(f"   Critical Issues: {report_data['critical_issues']}")
        print(f"   Warnings: {report_data['warnings']}")
        print(f"   Rows Dropped: {report_data['rows_dropped']}")
        print(f"   Timestamp: {report_data['timestamp']}")
        
        # Parse and display detailed report
        report_json = json.loads(report_data['report_json'])
        print(f"\n📋 Detailed Validation Results:")
        print(f"   Total Rows: {report_json.get('total_rows', 0)}")
        print(f"   Rows After Cleaning: {report_json.get('rows_after_cleaning', 0)}")
        print(f"   Rows Dropped: {report_json.get('rows_dropped', 0)}")
        
        validation_results = report_json.get('validation_results', [])
        print(f"\n   Validation Checks:")
        for val_result in validation_results:
            check_name = val_result.get('check_name', 'Unknown')
            passed = val_result.get('passed', False)
            severity = val_result.get('severity', 'info')
            status_icon = "✅" if passed else "❌" if severity == "critical" else "⚠️"
            print(f"   {status_icon} {check_name}: {'PASSED' if passed else 'FAILED'}")
            
            if not passed:
                issues = val_result.get('issues', [])
                for issue in issues:
                    print(f"      - {issue.get('message', 'N/A')}")
        
        recommendations = report_json.get('recommendations', [])
        if recommendations:
            print(f"\n   💡 Recommendations:")
            for rec in recommendations:
                print(f"      - {rec}")
    else:
        print(f"\n⚠️ No validation report found for {symbol}")
        print("   This means validation hasn't run yet or data wasn't fetched.")
    
    # Test swing signal to see diagnostics
    print(f"\n3️⃣ Testing Swing Signal Generation...")
    try:
        from app.di import get_container
        container = get_container()
        strategy_service = container.get('strategy_service')
        data_source = container.get('data_source')
        
        market_data = data_source.fetch_price_data(symbol, period="1y")
        if market_data is not None and not market_data.empty:
            strategy_result = strategy_service.execute_strategy(
                strategy_name="swing_trend",
                indicators={},
                market_data=market_data,
                context={'symbol': symbol, 'user_id': 'user1'}
            )
            
            print(f"   Signal: {strategy_result.signal.upper()}")
            print(f"   Confidence: {strategy_result.confidence:.2f}")
            print(f"   Reason: {strategy_result.reason}")
            
            # Parse reason if it contains diagnostics
            if "|" in strategy_result.reason:
                print(f"\n   📊 Detailed Diagnostics:")
                reason_parts = [r.strip() for r in strategy_result.reason.split("|")]
                for part in reason_parts:
                    print(f"      {part}")
        else:
            print(f"   ⚠️ No market data available for {symbol}")
    except Exception as e:
        print(f"   ❌ Error generating swing signal: {e}")
    
    # Summary statistics
    print(f"\n4️⃣ Validation Report Summary:")
    summary_query = """
        SELECT 
            COUNT(*) as total_reports,
            COUNT(DISTINCT symbol) as unique_symbols,
            SUM(critical_issues) as total_critical,
            SUM(warnings) as total_warnings,
            AVG(rows_dropped) as avg_rows_dropped
        FROM data_validation_reports
    """
    summary = db.execute_query(summary_query)
    if summary:
        stats = summary[0]
        print(f"   Total Reports: {stats['total_reports']}")
        print(f"   Unique Symbols: {stats['unique_symbols']}")
        print(f"   Total Critical Issues: {stats['total_critical']}")
        print(f"   Total Warnings: {stats['total_warnings']}")
        print(f"   Avg Rows Dropped: {stats['avg_rows_dropped']:.1f}")
    
    print("\n" + "=" * 60)
    print("✅ Validation test complete!")

if __name__ == "__main__":
    test_validation()

