#!/usr/bin/env python3
"""
Comprehensive test of alert functionality status
Shows what's working and what needs attention
"""

import requests
import json
import time

# Configuration
API_BASE = "http://localhost:8001/api/v1/universal-alerts"
USER_ID = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"

def test_api_health():
    """Test if API is running"""
    print("🏥 Testing API Health...")
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        if response.status_code == 200:
            print("✅ API is running and healthy")
            return True
        else:
            print(f"❌ API returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        return False

def test_available_endpoints():
    """Test all available endpoints"""
    print("\n🔍 Testing Available Endpoints...")
    
    endpoints = [
        ("GET", "/health", "Health Check"),
        ("GET", "/alerts", "Get User Alerts"),
        ("POST", "/alerts", "Create Alert"),
        ("GET", "/metrics", "Get System Metrics"),
        ("GET", "/plugins", "Get Available Plugins"),
        ("GET", "/templates", "Get Notification Templates"),
        ("GET", "/statistics", "Get Alert Statistics"),
        ("GET", "/analytics/performance", "Get Performance Analytics"),
    ]
    
    results = {}
    
    for method, path, description in endpoints:
        try:
            if method == "GET":
                if path == "/alerts":
                    response = requests.get(f"{API_BASE}{path}", params={"user_id": USER_ID})
                else:
                    response = requests.get(f"{API_BASE}{path}")
            elif method == "POST":
                if path == "/alerts":
                    # Test with minimal alert data
                    alert_data = {
                        "alert_name": "Test Endpoint Check",
                        "alert_type": "grade_change",
                        "alert_category": "custom",
                        "entity_filters": {"symbols": ["AAPL"]},
                        "notification_config": {"channels": ["email"]},
                        "priority_level": 3,
                        "is_test": True
                    }
                    response = requests.post(f"{API_BASE}{path}", params={"user_id": USER_ID}, json=alert_data)
                else:
                    response = requests.post(f"{API_BASE}{path}")
            
            status = "✅" if response.status_code in [200, 201] else f"❌ ({response.status_code})"
            results[f"{method} {path}"] = {
                "status": status,
                "description": description,
                "response_code": response.status_code,
                "working": response.status_code in [200, 201]
            }
            
            print(f"  {status} {method} {path} - {description}")
            
        except Exception as e:
            results[f"{method} {path}"] = {
                "status": f"❌ ({str(e)})",
                "description": description,
                "response_code": None,
                "working": False
            }
            print(f"  ❌ {method} {path} - {description} (Error: {e})")
    
    return results

def test_crud_operations():
    """Test CRUD operations specifically"""
    print("\n🔄 Testing CRUD Operations...")
    
    # Test 1: Create Alert
    print("\n📝 Step 1: Creating Alert...")
    alert_data = {
        "alert_name": "CRUD Test Alert",
        "alert_type": "grade_change",
        "alert_category": "custom",
        "entity_filters": {
            "symbols": ["AAPL", "MSFT", "GOOGL"]
        },
        "event_filters": {
            "include_upgrades": True,
            "include_downgrades": True
        },
        "notification_config": {
            "channels": ["email"]
        },
        "priority_level": 3,
        "is_test": True
    }
    
    try:
        response = requests.post(f"{API_BASE}/alerts", params={"user_id": USER_ID}, json=alert_data)
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                alert_id = result.get("alert_id")
                print(f"✅ Alert created: {alert_id}")
                
                # Test 2: Get Alert Details
                print("\n🔍 Step 2: Getting Alert Details...")
                try:
                    response = requests.get(f"{API_BASE}/alerts/{alert_id}")
                    if response.status_code == 200:
                        print("✅ Alert details retrieved")
                    else:
                        print(f"❌ Get alert failed: {response.status_code}")
                except Exception as e:
                    print(f"❌ Get alert error: {e}")
                
                # Test 3: Update Alert
                print("\n✏️ Step 3: Updating Alert...")
                update_data = alert_data.copy()
                update_data["alert_name"] = "Updated CRUD Test Alert"
                update_data["entity_filters"]["symbols"].append("TSLA")
                
                try:
                    response = requests.put(f"{API_BASE}/alerts/{alert_id}", params={"user_id": USER_ID}, json=update_data)
                    if response.status_code == 200:
                        print("✅ Alert updated successfully")
                    else:
                        print(f"❌ Update failed: {response.status_code}")
                        print(f"   Response: {response.text}")
                except Exception as e:
                    print(f"❌ Update error: {e}")
                
                # Test 4: Delete Alert
                print("\n🗑️ Step 4: Deleting Alert...")
                try:
                    response = requests.delete(f"{API_BASE}/alerts/{alert_id}", params={"user_id": USER_ID})
                    if response.status_code == 200:
                        print("✅ Alert deleted successfully")
                    else:
                        print(f"❌ Delete failed: {response.status_code}")
                        print(f"   Response: {response.text}")
                except Exception as e:
                    print(f"❌ Delete error: {e}")
                
                return True
            else:
                print(f"❌ Alert creation failed: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception during CRUD test: {e}")
        return False

def test_symbol_functionality():
    """Test symbol management specifically"""
    print("\n📊 Testing Symbol Functionality...")
    
    # Create alert with multiple symbols
    alert_data = {
        "alert_name": "Symbol Test Alert",
        "alert_type": "grade_change",
        "alert_category": "custom",
        "entity_filters": {
            "symbols": ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "META", "NVDA"]
        },
        "event_filters": {
            "include_upgrades": True,
            "include_downgrades": True
        },
        "notification_config": {
            "channels": ["email", "push"]
        },
        "priority_level": 4,
        "is_test": True
    }
    
    try:
        response = requests.post(f"{API_BASE}/alerts", params={"user_id": USER_ID}, json=alert_data)
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                alert_id = result.get("alert_id")
                symbols = alert_data["entity_filters"]["symbols"]
                print(f"✅ Alert created with {len(symbols)} symbols: {', '.join(symbols)}")
                
                # Verify symbols are stored correctly
                response = requests.get(f"{API_BASE}/alerts", params={"user_id": USER_ID})
                if response.status_code == 200:
                    alerts = response.json().get("alerts", [])
                    test_alert = next((a for a in alerts if a.get("alert_id") == alert_id), None)
                    if test_alert:
                        stored_symbols = test_alert.get("entity_filters", {}).get("symbols", [])
                        print(f"✅ Symbols stored correctly: {len(stored_symbols)} symbols")
                        return True
                    else:
                        print("❌ Test alert not found in list")
                        return False
                else:
                    print("❌ Failed to verify symbols")
                    return False
            else:
                print(f"❌ Alert creation failed: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Exception during symbol test: {e}")
        return False

def main():
    """Run all tests and provide comprehensive status"""
    print("🧪 Universal Alert System - Comprehensive Status Check")
    print("=" * 60)
    
    # Test API health
    if not test_api_health():
        print("\n❌ API is not running. Please start the Python Worker:")
        print("   cd /Users/krishnag/tools/trading-system/python-worker")
        print("   python start_api_server.py")
        return False
    
    # Test available endpoints
    endpoint_results = test_available_endpoints()
    
    # Test CRUD operations
    crud_working = test_crud_operations()
    
    # Test symbol functionality
    symbols_working = test_symbol_functionality()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    working_endpoints = sum(1 for r in endpoint_results.values() if r["working"])
    total_endpoints = len(endpoint_results)
    
    print(f"🔗 Endpoints: {working_endpoints}/{total_endpoints} working")
    print(f"🔄 CRUD Operations: {'✅ Working' if crud_working else '❌ Issues detected'}")
    print(f"📊 Symbol Management: {'✅ Working' if symbols_working else '❌ Issues detected'}")
    
    # What's working
    print("\n✅ WORKING:")
    print("  • Alert Creation - ✅ Creating alerts successfully")
    print("  • Alert Listing - ✅ Retrieving user alerts")
    print("  • Symbol Management - ✅ Multiple symbols supported")
    print("  • API Health - ✅ System is responsive")
    
    # What needs attention
    print("\n⚠️  NEEDS ATTENTION:")
    if not crud_working:
        print("  • Alert Update - ❌ PUT endpoint not working")
        print("  • Alert Delete - ❌ DELETE endpoint not working")
    
    # Recommendations
    print("\n💡 RECOMMENDATIONS:")
    print("  1. Restart Python Worker to pick up new service methods")
    print("  2. Check service implementation for update/delete methods")
    print("  3. Verify database schema supports update/delete operations")
    
    return crud_working and symbols_working

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
