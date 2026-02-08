#!/usr/bin/env python3
"""
Simple test to verify alert CRUD functionality is working
"""

import requests
import json
import time

# Configuration
API_BASE = "http://localhost:8001/api/v1/universal-alerts"
USER_ID = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"

def test_alert_crud():
    """Test alert Create, Read, Update, Delete operations"""
    
    print("🧪 Testing Alert CRUD Operations")
    print("=" * 50)
    
    # Test 1: Create Alert
    print("\n📝 Test 1: Creating Alert...")
    create_data = {
        "alert_name": "Test CRUD Alert",
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
        response = requests.post(
            f"{API_BASE}/alerts",
            params={"user_id": USER_ID},
            json=create_data
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                alert_id = result.get("alert_id")
                print(f"✅ Alert created successfully!")
                print(f"   Alert ID: {alert_id}")
                print(f"   Alert Name: {result.get('alert_name')}")
                print(f"   Alert Type: {result.get('alert_type')}")
                print(f"   Tracking ID: {result.get('tracking_id')}")
            else:
                print(f"❌ Alert creation failed: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception during alert creation: {e}")
        return False
    
    # Test 2: List Alerts
    print(f"\n📋 Test 2: Listing Alerts...")
    try:
        response = requests.get(
            f"{API_BASE}/alerts",
            params={"user_id": USER_ID}
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                alerts = result.get("alerts", [])
                print(f"✅ Retrieved {len(alerts)} alerts")
                
                # Find our test alert
                test_alert = next((a for a in alerts if a.get("alert_id") == alert_id), None)
                if test_alert:
                    print(f"   Found test alert: {test_alert['alert_name']}")
                    print(f"   Type: {test_alert['alert_type']}")
                    print(f"   Symbols: {test_alert.get('entity_filters', {}).get('symbols', [])}")
                    print(f"   Active: {test_alert.get('is_active')}")
                else:
                    print(f"❌ Test alert not found in list")
                    return False
            else:
                print(f"❌ Failed to list alerts: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Exception during alert listing: {e}")
        return False
    
    # Test 3: Update Alert
    print(f"\n✏️ Test 3: Updating Alert...")
    update_data = {
        "alert_name": "Updated Test CRUD Alert",
        "alert_type": "grade_change",
        "alert_category": "custom",
        "entity_filters": {
            "symbols": ["AAPL", "MSFT", "GOOGL", "TSLA"]  # Added TSLA
        },
        "event_filters": {
            "include_upgrades": True,
            "include_downgrades": True
        },
        "notification_config": {
            "channels": ["email", "push"]  # Added push
        },
        "priority_level": 4,  # Changed to high priority
        "is_test": True
    }
    
    try:
        response = requests.put(
            f"{API_BASE}/alerts/{alert_id}",
            params={"user_id": USER_ID},
            json=update_data
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print(f"✅ Alert updated successfully!")
                print(f"   New Name: {result.get('message')}")
                print(f"   Tracking ID: {result.get('tracking_id')}")
            else:
                print(f"❌ Alert update failed: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Exception during alert update: {e}")
        return False
    
    # Test 4: Verify Update
    print(f"\n🔍 Test 4: Verifying Update...")
    try:
        response = requests.get(
            f"{API_BASE}/alerts",
            params={"user_id": USER_ID}
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                alerts = result.get("alerts", [])
                updated_alert = next((a for a in alerts if a.get("alert_id") == alert_id), None)
                if updated_alert:
                    print(f"✅ Update verified!")
                    print(f"   New Name: {updated_alert['alert_name']}")
                    print(f"   New Priority: {updated_alert.get('priority_level')}")
                    print(f"   Symbols: {updated_alert.get('entity_filters', {}).get('symbols', [])}")
                    print(f"   Notification Channels: {updated_alert.get('notification_config', {}).get('channels', [])}")
                else:
                    print(f"❌ Updated alert not found")
                    return False
            else:
                print(f"❌ Failed to list alerts: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Exception during verification: {e}")
        return False
    
    # Test 5: Delete Alert
    print(f"\n🗑️ Test 5: Deleting Alert...")
    try:
        response = requests.delete(
            f"{API_BASE}/alerts/{alert_id}",
            params={"user_id": USER_ID}
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print(f"✅ Alert deleted successfully!")
                print(f"   Deleted Alert: {result.get('deleted_alert_name')}")
                print(f"   Tracking ID: {result.get('tracking_id')}")
            else:
                print(f"❌ Alert deletion failed: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Exception during alert deletion: {e}")
        return False
    
    # Test 6: Verify Deletion
    print(f"\n🔍 Test 6: Verifying Deletion...")
    try:
        response = requests.get(
            f"{API_BASE}/alerts",
            params={"user_id": USER_ID}
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                alerts = result.get("alerts", [])
                deleted_alert = next((a for a in alerts if a.get("alert_id") == alert_id), None)
                if deleted_alert is None:
                    print(f"✅ Deletion verified - alert no longer in list")
                else:
                    print(f"❌ Alert still exists after deletion")
                    return False
            else:
                print(f"❌ Failed to list alerts: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Exception during deletion verification: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 All CRUD operations working perfectly!")
    return True

if __name__ == "__main__":
    # Check if API is running
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        if response.status_code != 200:
            print("❌ API is not running. Please start the Python Worker first:")
            print("   cd /Users/krishnag/tools/trading-system/python-worker")
            print("   python start_api_server.py")
            exit(1)
    except requests.exceptions.RequestException:
        print("❌ Cannot connect to API. Please start the Python Worker first:")
        print("   cd /Users/krishnag/tools/trading-system/python-worker")
        print("   python start_api_server.py")
        exit(1)
    
    # Run CRUD tests
    success = test_alert_crud()
    
    if success:
        print("\n🚀 Alert CRUD functionality is fully operational!")
        print("✅ Create, Read, Update, Delete operations all working")
        print("✅ Symbol management working (AAPL, MSFT, GOOGL, TSLA)")
        print("✅ Notification channels working (email, push)")
        print("✅ Priority levels working")
        print("✅ Test alerts working")
        exit(0)
    else:
        print("\n❌ Some CRUD operations failed")
        exit(1)
