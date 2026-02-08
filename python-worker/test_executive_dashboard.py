#!/usr/bin/env python3
"""
Test Executive Dashboard API endpoints
"""

import requests
import json

def test_executive_dashboard_apis():
    """Test the APIs used by the Executive Dashboard"""
    
    base_url = "http://127.0.0.1:8001"
    
    print("🏢 Testing Executive Dashboard APIs...")
    print("=" * 60)
    
    # Test 1: Main health endpoint
    print("\n📊 1. Main Health Endpoint:")
    try:
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Status: {data.get('status', 'unknown')}")
            print(f"  📅 Timestamp: {data.get('timestamp', 'unknown')}")
        else:
            print(f"  ❌ Failed: {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    # Test 2: Universal Alerts health
    print("\n🚨 2. Universal Alerts Health:")
    try:
        response = requests.get(f"{base_url}/api/v1/universal-alerts/health")
        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Response: {data}")
        else:
            print(f"  ❌ Failed: {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    # Test 3: Universal Alerts metrics
    print("\n📈 3. Universal Alerts Metrics:")
    try:
        response = requests.get(f"{base_url}/api/v1/universal-alerts/metrics")
        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Metrics available: {bool(data.get('success', False))}")
            if data.get('success'):
                metrics = data.get('metrics', {})
                print(f"  📊 Error count: {metrics.get('error_count', 0)}")
                print(f"  📊 Total requests: {metrics.get('total_requests', 0)}")
        else:
            print(f"  ❌ Failed: {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    # Test 4: Universal Alerts alerts
    print("\n🔔 4. Universal Alerts (Sample):")
    try:
        response = requests.get(f"{base_url}/api/v1/universal-alerts/alerts", 
                              params={"user_id": "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4", "limit": 3})
        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Alerts available: {bool(data.get('success', False))}")
            if data.get('success'):
                alerts = data.get('alerts', [])
                print(f"  📊 Total alerts found: {len(alerts)}")
                if alerts:
                    print(f"  🔔 Sample alert: {alerts[0].get('alert_name', 'unknown')}")
        else:
            print(f"  ❌ Failed: {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 Executive Dashboard API Test completed!")

if __name__ == "__main__":
    test_executive_dashboard_apis()
