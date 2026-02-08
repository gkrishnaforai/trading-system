#!/usr/bin/env python3
"""
Test script to verify all problematic table fixes
"""

import requests
import json

def test_all_problematic_tables():
    """Test all the problematic tables that were causing UndefinedColumn errors"""
    
    base_url = "http://127.0.0.1:8001"
    
    # All tables that were failing
    problematic_tables = [
        "short_interest", "short_volume", "corporate_actions", "stock_grades",
        "stock_consensus_history", "income_statements", "balance_sheets", 
        "cash_flow_statements", "financial_ratios", "earnings_transcripts"
    ]
    
    print("🔧 Testing ALL problematic table fixes...")
    print("=" * 80)
    
    success_count = 0
    error_count = 0
    
    for table in problematic_tables:
        print(f"\n📊 Testing {table}...")
        
        try:
            # Test data summary endpoint
            summary_url = f"{base_url}/admin/data-summary/{table}"
            response = requests.get(summary_url)
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ Summary API: SUCCESS")
                print(f"     Total records: {data.get('total_records', 'N/A')}")
                print(f"     Last updated: {data.get('last_updated', 'N/A')}")
                success_count += 1
            else:
                print(f"  ❌ Summary API: FAILED ({response.status_code})")
                print(f"     Error: {response.text}")
                error_count += 1
            
            # Test data quality endpoint
            quality_url = f"{base_url}/admin/data-quality/{table}"
            response = requests.get(quality_url)
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ Quality API: SUCCESS")
                print(f"     Total: {data.get('total', 'N/A')}")
                print(f"     Null rate: {data.get('null_rate', 'N/A')}%")
            else:
                print(f"  ❌ Quality API: FAILED ({response.status_code})")
                print(f"     Error: {response.text}")
                error_count += 1
                
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Connection Error: Server not running at {base_url}")
            return False
        except Exception as e:
            print(f"  ❌ Unexpected Error: {e}")
            error_count += 1
    
    print("\n" + "=" * 80)
    print(f"🎯 Test completed!")
    print(f"✅ Successful tables: {success_count}")
    print(f"❌ Failed tables: {error_count}")
    
    if error_count == 0:
        print("🎉 ALL TABLES FIXED SUCCESSFULLY!")
    else:
        print("⚠️ Some tables still need fixing")
    
    return error_count == 0

if __name__ == "__main__":
    test_all_problematic_tables()
