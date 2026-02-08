#!/usr/bin/env python3
"""
Final comprehensive test of alert CRUD functionality
"""

import requests
import json

# Configuration
API_BASE = "http://localhost:8001/api/v1/universal-alerts"
USER_ID = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"

def test_alert_creation():
    """Test alert creation"""
    print("📝 Testing Alert Creation...")
    
    alert_data = {
        "alert_name": "Final Test Alert",
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
                print(f"✅ Alert created successfully: {alert_id}")
                return alert_id
            else:
                print(f"❌ Alert creation failed: {result.get('error')}")
                return None
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None

def test_alert_listing():
    """Test alert listing"""
    print("\n📋 Testing Alert Listing...")
    
    try:
        response = requests.get(f"{API_BASE}/alerts", params={"user_id": USER_ID})
        if response.status_code == 200:
            result = response.json()
            alerts = result.get("alerts", [])
            total = result.get("total", 0)
            print(f"✅ Retrieved {len(alerts)} alerts (total: {total})")
            return alerts
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Exception: {e}")
        return []

def test_alert_details(alert_id):
    """Test alert details"""
    print(f"\n🔍 Testing Alert Details for {alert_id}...")
    
    try:
        response = requests.get(f"{API_BASE}/alerts/{alert_id}", params={"user_id": USER_ID})
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                alert = result.get("alert")
                print(f"✅ Alert details retrieved: {alert.get('alert_name')}")
                return alert
            else:
                print(f"❌ Alert not found")
                return None
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None

def test_alert_update(alert_id):
    """Test alert update"""
    print(f"\n✏️ Testing Alert Update for {alert_id}...")
    
    update_data = {
        "alert_name": "Updated Final Test Alert",
        "alert_type": "grade_change",
        "alert_category": "custom",
        "entity_filters": {
            "symbols": ["AAPL", "MSFT", "GOOGL", "TSLA"]
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
        response = requests.put(f"{API_BASE}/alerts/{alert_id}", params={"user_id": USER_ID}, json=update_data)
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print(f"✅ Alert updated successfully")
                return True
            else:
                print(f"❌ Alert update failed: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def test_alert_delete(alert_id):
    """Test alert deletion"""
    print(f"\n🗑️ Testing Alert Deletion for {alert_id}...")
    
    try:
        response = requests.delete(f"{API_BASE}/alerts/{alert_id}", params={"user_id": USER_ID})
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print(f"✅ Alert deleted successfully")
                return True
            else:
                print(f"❌ Alert deletion failed: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def main():
    """Run comprehensive CRUD test"""
    print("🧪 Final Alert CRUD Test")
    print("=" * 50)
    
    # Test creation
    alert_id = test_alert_creation()
    if not alert_id:
        print("\n❌ Cannot proceed without alert ID")
        return False
    
    # Test listing
    alerts = test_alert_listing()
    
    # Test details
    alert_details = test_alert_details(alert_id)
    
    # Test update
    update_success = test_alert_update(alert_id)
    
    # Test delete
    delete_success = test_alert_delete(alert_id)
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 FINAL RESULTS")
    print("=" * 50)
    
    results = {
        "Create": bool(alert_id),
        "List": len(alerts) > 0,
        "Details": bool(alert_details),
        "Update": update_success,
        "Delete": delete_success
    }
    
    for operation, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {operation}")
    
    working_count = sum(results.values())
    total_count = len(results)
    
    print(f"\n🎯 Overall: {working_count}/{total_count} operations working")
    
    if working_count == total_count:
        print("🎉 All CRUD operations are working perfectly!")
        return True
    else:
        print("⚠️ Some operations need attention")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
