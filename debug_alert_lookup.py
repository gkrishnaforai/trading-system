#!/usr/bin/env python3
"""
Debug script to test alert lookup issue
"""

import requests
import json

# Configuration
API_BASE = "http://localhost:8001/api/v1/universal-alerts"
USER_ID = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"

def test_alert_lookup():
    """Test alert lookup with different approaches"""
    
    # Step 1: Get alerts from listing
    print("🔍 Step 1: Getting alerts from listing...")
    response = requests.get(f"{API_BASE}/alerts", params={"user_id": USER_ID, "limit": 5})
    if response.status_code == 200:
        alerts = response.json().get("alerts", [])
        print(f"✅ Found {len(alerts)} alerts in listing")
        
        if alerts:
            alert_id = alerts[0]["alert_id"]
            alert_name = alerts[0]["alert_name"]
            print(f"📝 Testing with alert: {alert_id} - {alert_name}")
            
            # Step 2: Test alert details
            print("\n🔍 Step 2: Testing alert details...")
            response = requests.get(f"{API_BASE}/alerts/{alert_id}", params={"user_id": USER_ID})
            print(f"📊 Status: {response.status_code}")
            print(f"📄 Response: {response.text}")
            
            # Step 3: Test alert update
            print("\n🔍 Step 3: Testing alert update...")
            update_data = {
                "alert_name": "Updated Test Alert",
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
            
            response = requests.put(f"{API_BASE}/alerts/{alert_id}", params={"user_id": USER_ID}, json=update_data)
            print(f"📊 Status: {response.status_code}")
            print(f"📄 Response: {response.text}")
            
            # Step 4: Test alert delete
            print("\n🔍 Step 4: Testing alert delete...")
            response = requests.delete(f"{API_BASE}/alerts/{alert_id}", params={"user_id": USER_ID})
            print(f"📊 Status: {response.status_code}")
            print(f"📄 Response: {response.text}")
            
        else:
            print("❌ No alerts found")
    else:
        print(f"❌ Failed to get alerts: {response.status_code}")

if __name__ == "__main__":
    test_alert_lookup()
