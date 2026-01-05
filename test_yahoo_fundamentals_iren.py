#!/usr/bin/env python3
"""
Test script to download fundamentals for IREN using Yahoo Finance REST client
This demonstrates the Yahoo Finance data source implementation
"""

import sys
import os
import json
from datetime import datetime

# Add the python-worker directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'python-worker'))

from app.providers.yahoo_finance.client import YahooFinanceClient, YahooFinanceConfig
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.observability.logging import get_logger

logger = get_logger("yahoo_fundamentals_test")

def test_yahoo_fundamentals_iren():
    """Test downloading fundamentals for IREN using Yahoo Finance"""
    
    print("=" * 60)
    print("Testing Yahoo Finance Fundamentals Download for IREN")
    print("=" * 60)
    
    # Initialize Yahoo Finance client
    print("\n1. Initializing Yahoo Finance client...")
    config = YahooFinanceConfig(
        timeout=30,
        max_retries=3,
        retry_delay=1.0,
        rate_limit_calls=100,
        rate_limit_window=60.0
    )
    
    client = YahooFinanceClient(config)
    print("✅ Yahoo Finance client initialized")
    
    # Initialize Yahoo Finance source (thin adapter)
    print("\n2. Initializing Yahoo Finance data source...")
    yahoo_source = YahooFinanceSource(config)
    print("✅ Yahoo Finance data source initialized")
    
    # Test symbol
    symbol = "IREN"
    print(f"\n3. Fetching fundamentals for {symbol}...")
    
    try:
        # Method 1: Using the client directly
        print("\n--- Method 1: Using YahooFinanceClient directly ---")
        fundamentals_client = client.fetch_fundamentals(symbol)
        
        print(f"✅ Successfully fetched fundamentals using client")
        print(f"Number of fields: {len(fundamentals_client)}")
        
        # Display key fundamentals
        key_fields = [
            'symbol', 'shortName', 'longName', 'sector', 'industry',
            'marketCap', 'enterpriseValue', 'trailingPE', 'forwardPE',
            'pegRatio', 'priceToSalesTrailing12Months', 'priceToBook',
            'enterpriseToRevenue', 'enterpriseToEbitda',
            'beta', 'epsTrailingTwelveMonths', 'epsForward',
            'dividendYield', 'exDividendDate',
            'revenue', 'gross_profit', 'operating_income', 'net_income',
            'total_assets', 'total_liabilities', 'total_equity',
            'debt_to_equity', 'operating_cash_flow', 'free_cash_flow'
        ]
        
        print("\nKey Fundamentals (Client):")
        print("-" * 40)
        for field in key_fields:
            value = fundamentals_client.get(field)
            if value is not None:
                if isinstance(value, (int, float)):
                    if field in ['marketCap', 'enterpriseValue', 'revenue', 'gross_profit', 
                               'operating_income', 'net_income', 'total_assets', 'total_liabilities',
                               'total_equity', 'operating_cash_flow', 'free_cash_flow']:
                        # Format large numbers in millions/billions
                        if abs(value) >= 1e9:
                            formatted_value = f"${value/1e9:.2f}B"
                        elif abs(value) >= 1e6:
                            formatted_value = f"${value/1e6:.2f}M"
                        else:
                            formatted_value = f"${value:,.2f}"
                        print(f"  {field:25}: {formatted_value}")
                    elif field in ['trailingPE', 'forwardPE', 'pegRatio', 'priceToSalesTrailing12Months',
                                 'priceToBook', 'enterpriseToRevenue', 'enterpriseToEbitda', 'beta',
                                 'epsTrailingTwelveMonths', 'epsForward', 'dividendYield', 'debt_to_equity']:
                        print(f"  {field:25}: {value:.4f}")
                    else:
                        print(f"  {field:25}: {value}")
                else:
                    print(f"  {field:25}: {value}")
        
        # Method 2: Using the data source adapter
        print("\n--- Method 2: Using YahooFinanceSource adapter ---")
        fundamentals_source = yahoo_source.fetch_fundamentals(symbol)
        
        print(f"✅ Successfully fetched fundamentals using source adapter")
        print(f"Number of fields: {len(fundamentals_source)}")
        
        # Compare results
        print("\n--- Comparison ---")
        if len(fundamentals_client) == len(fundamentals_source):
            print("✅ Both methods returned same number of fields")
        else:
            print(f"⚠️ Different field counts: Client={len(fundamentals_client)}, Source={len(fundamentals_source)}")
        
        # Save results to JSON file for inspection
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"iren_fundamentals_{timestamp}.json"
        
        print(f"\n4. Saving fundamentals to {filename}...")
        
        # Create a more readable JSON output
        output_data = {
            "symbol": symbol,
            "fetch_timestamp": datetime.now().isoformat(),
            "data_source": "yahoo_finance",
            "fundamentals": {}
        }
        
        # Add all fundamentals with proper formatting
        for key, value in fundamentals_client.items():
            if value is not None:
                # Handle numpy types and special values
                if hasattr(value, 'item'):  # numpy scalar
                    value = value.item()
                elif str(value) == 'nan':
                    value = None
                elif str(value) in ['inf', '-inf']:
                    value = None
                output_data["fundamentals"][key] = value
        
        with open(filename, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)
        
        print(f"✅ Fundamentals saved to {filename}")
        
        # Test validation with our new validator
        print("\n5. Testing fundamentals validation...")
        try:
            from app.data_validation import FundamentalsValidator
            
            validator = FundamentalsValidator()
            validation_report = validator.validate(fundamentals_client, symbol, "fundamentals")
            
            print(f"Validation Status: {validation_report.overall_status}")
            print(f"Critical Issues: {validation_report.critical_issues}")
            print(f"Warnings: {validation_report.warnings}")
            
            if validation_report.validation_results:
                total_issues = sum(len(result.issues) for result in validation_report.validation_results)
                print(f"Issues found: {total_issues}")
                
                # Show first few issues
                issue_count = 0
                for result in validation_report.validation_results:
                    for issue in result.issues:
                        if issue_count < 5:  # Show first 5 issues
                            print(f"  - {issue.severity.name}: {issue.message}")
                            issue_count += 1
                        else:
                            break
                    if issue_count >= 5:
                        break
            else:
                print("✅ No validation issues found")
                
        except ImportError as e:
            print(f"⚠️ Could not test validation: {e}")
        except Exception as e:
            print(f"⚠️ Validation error: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("✅ Test completed successfully!")
        print("=" * 60)
        
        return fundamentals_client
        
    except Exception as e:
        print(f"\n❌ Error fetching fundamentals for {symbol}: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None

def test_rest_api_details():
    """Show REST API details and configuration"""
    print("\n" + "=" * 60)
    print("Yahoo Finance REST API Details")
    print("=" * 60)
    
    print("\n📡 API Configuration:")
    print("  • Library: yfinance (Python wrapper for Yahoo Finance REST API)")
    print("  • Base URL: https://query1.finance.yahoo.com/v8/finance/chart/")
    print("  • Authentication: None required (public API)")
    print("  • Rate Limit: ~100 calls per minute (conservative)")
    print("  • Timeout: 30 seconds")
    print("  • Retry Logic: 3 retries with exponential backoff")
    
    print("\n🔗 REST Endpoints Used:")
    print("  • Chart Data: /v8/finance/chart/{symbol}")
    print("  • Quote Summary: /v10/finance/quoteSummary/{symbol}")
    print("  • Financial Statements: /v1/finance/financials/{symbol}")
    
    print("\n📊 Data Retrieved:")
    print("  • Company Info (name, sector, industry)")
    print("  • Market Data (market cap, P/E ratios, beta)")
    print("  • Financial Statements (income statement, balance sheet, cash flow)")
    print("  • Calculated Metrics (debt/equity, free cash flow)")

if __name__ == "__main__":
    # Show API details
    test_rest_api_details()
    
    # Run the test
    fundamentals = test_yahoo_fundamentals_iren()
    
    if fundamentals:
        print(f"\n🎉 Success! Retrieved {len(fundamentals)} data fields for IREN")
    else:
        print("\n❌ Test failed. Check error messages above.")
        sys.exit(1)
