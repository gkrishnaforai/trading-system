#!/usr/bin/env python3
"""
Migration Helper: Rating Alerts to Universal Alerts
Converts rating-alerts configuration to universal-alerts format
"""

import requests
import json
from datetime import datetime
from typing import Dict, List, Any

class RatingToUniversalAlertMigrator:
    def __init__(self, python_worker_url: str = "http://localhost:8001"):
        self.python_worker_url = python_worker_url
        self.rating_alerts_url = f"{python_worker_url}/api/v1/rating-alerts"
        self.universal_alerts_url = f"{python_worker_url}/api/v1/universal-alerts"
        
    def get_rating_alerts(self, user_id: str = None) -> List[Dict]:
        """Get existing rating alerts for migration"""
        try:
            # Rating alerts API requires user_id parameter
            if not user_id:
                user_id = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"  # Default user ID
            
            params = {"user_id": user_id}
            response = requests.get(f"{self.rating_alerts_url}/alerts", params=params)
            
            if response.status_code == 200:
                data = response.json()
                alerts = data.get("alerts", [])
                print(f"✅ Successfully retrieved {len(alerts)} rating alerts")
                return alerts
            elif response.status_code == 422:
                print(f"❌ Validation error: {response.json()}")
                return []
            else:
                print(f"❌ Failed to get rating alerts: {response.status_code}")
                print(f"Response: {response.text}")
                return []
        except Exception as e:
            print(f"❌ Error getting rating alerts: {e}")
            return []
    
    def convert_rating_to_universal_alert(self, rating_alert: Dict) -> Dict:
        """Convert rating alert to universal alert format"""
        # Extract rating alert data
        alert_name = rating_alert.get("name", rating_alert.get("alert_name", "Migrated Rating Alert"))
        
        # Extract symbol from stock_symbol field or create from name
        symbol = rating_alert.get("stock_symbol", "")
        if not symbol and alert_name:
            # Try to extract symbol from alert name (e.g., "MSFT Rating Changes" -> "MSFT")
            import re
            symbol_match = re.match(r'^([A-Z]{1,5})', alert_name.upper())
            if symbol_match:
                symbol = symbol_match.group(1)
        
        # Extract alert types from config
        config = rating_alert.get("config", {})
        include_upgrades = config.get("include_upgrades", False)
        include_downgrades = config.get("include_downgrades", False)
        
        # Map rating alert types to universal alert event filters
        event_filters = {
            "include_upgrades": include_upgrades,
            "include_downgrades": include_downgrades,
            "tier_1_firms_only": config.get("tier_1_firms_only", False),
            "min_confidence": 0.5,  # Default value
            "min_priority": 1
        }
        
        # Create universal alert
        universal_alert = {
            "alert_name": f"[MIGRATED] {alert_name}",
            "alert_type": "grade_change",
            "alert_category": "migrated",
            "entity_filters": {
                "symbols": [symbol] if symbol else []
            },
            "event_filters": event_filters,
            "trigger_conditions": {
                "cooldown_minutes": config.get("notification_delay_minutes", 60),
                "max_alerts_per_day": 10
            },
            "suppression_rules": {
                "suppress_duplicates": False,
                "suppress_weekends": False
            },
            "notification_config": {
                "channels": rating_alert.get("notification_channels", ["email"])
            },
            "priority_level": 3,
            "is_test": False,
            "migration_metadata": {
                "migrated_from": "rating_alerts",
                "original_id": rating_alert.get("alert_id"),
                "migration_date": datetime.now().isoformat(),
                "original_config": rating_alert
            }
        }
        
        return universal_alert
    
    def create_universal_alert(self, universal_alert: Dict, user_id: str = None) -> Dict:
        """Create universal alert from converted data"""
        try:
            # Universal alerts API also requires user_id parameter
            if not user_id:
                user_id = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"  # Default user ID
            
            params = {"user_id": user_id}
            response = requests.post(
                f"{self.universal_alerts_url}/alerts",
                json=universal_alert,
                params=params
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Successfully created universal alert: {result.get('alert_id')}")
                return result
            elif response.status_code == 422:
                print(f"❌ Validation error: {response.json()}")
                return {"success": False, "error": response.json()}
            else:
                print(f"❌ Failed to create universal alert: {response.status_code}")
                print(f"Response: {response.text}")
                return {"success": False, "error": response.text}
        except Exception as e:
            print(f"❌ Error creating universal alert: {e}")
            return {"success": False, "error": str(e)}
    
    def migrate_all_alerts(self, user_id: str = None, dry_run: bool = False) -> Dict:
        """Migrate all rating alerts to universal alerts"""
        print("🔄 Starting migration from Rating Alerts to Universal Alerts...")
        
        # Get existing rating alerts
        rating_alerts = self.get_rating_alerts(user_id)
        
        if not rating_alerts:
            print("📭 No rating alerts found to migrate")
            return {"success": True, "migrated_count": 0, "alerts": []}
        
        print(f"📊 Found {len(rating_alerts)} rating alerts to migrate")
        
        migrated_alerts = []
        failed_migrations = []
        
        for i, rating_alert in enumerate(rating_alerts):
            print(f"\n🔄 Migrating alert {i+1}/{len(rating_alerts)}: {rating_alert.get('name', 'Unknown')}")
            
            # Convert to universal alert format
            universal_alert = self.convert_rating_to_universal_alert(rating_alert)
            
            if dry_run:
                print(f"🔍 DRY RUN - Would create:")
                print(json.dumps(universal_alert, indent=2))
                migrated_alerts.append({
                    "original": rating_alert,
                    "converted": universal_alert,
                    "status": "dry_run"
                })
            else:
                # Create universal alert
                result = self.create_universal_alert(universal_alert, user_id)
                
                if result.get("success"):
                    migrated_alerts.append({
                        "original_id": rating_alert.get("id"),
                        "new_id": result.get("alert_id"),
                        "name": universal_alert["alert_name"],
                        "status": "migrated"
                    })
                    print(f"✅ Migration successful")
                else:
                    failed_migrations.append({
                        "original": rating_alert,
                        "error": result.get("error"),
                        "status": "failed"
                    })
                    print(f"❌ Migration failed: {result.get('error')}")
        
        # Summary
        print(f"\n📊 Migration Summary:")
        print(f"   Total alerts: {len(rating_alerts)}")
        print(f"   Migrated: {len(migrated_alerts)}")
        print(f"   Failed: {len(failed_migrations)}")
        
        if failed_migrations:
            print(f"\n❌ Failed migrations:")
            for failure in failed_migrations:
                print(f"   - {failure['original'].get('name', 'Unknown')}: {failure['error']}")
        
        return {
            "success": len(failed_migrations) == 0,
            "total_count": len(rating_alerts),
            "migrated_count": len(migrated_alerts),
            "failed_count": len(failed_migrations),
            "migrated_alerts": migrated_alerts,
            "failed_migrations": failed_migrations
        }
    
    def validate_migration(self, user_id: str = None) -> Dict:
        """Validate migration by comparing rating and universal alerts"""
        print("🔍 Validating migration...")
        
        rating_alerts = self.get_rating_alerts(user_id)
        universal_alerts = self.get_universal_alerts(user_id)
        
        # Find migrated alerts (those with migration metadata)
        migrated_alerts = [
            alert for alert in universal_alerts 
            if alert.get("migration_metadata", {}).get("migrated_from") == "rating_alerts"
        ]
        
        print(f"📊 Validation Results:")
        print(f"   Original rating alerts: {len(rating_alerts)}")
        print(f"   Migrated universal alerts: {len(migrated_alerts)}")
        print(f"   Migration coverage: {len(migrated_alerts)/len(rating_alerts)*100:.1f}%" if rating_alerts else "N/A")
        
        return {
            "original_count": len(rating_alerts),
            "migrated_count": len(migrated_alerts),
            "coverage_percentage": len(migrated_alerts)/len(rating_alerts)*100 if rating_alerts else 0,
            "validation_passed": len(migrated_alerts) >= len(rating_alerts)
        }
    
    def get_universal_alerts(self, user_id: str = None) -> List[Dict]:
        """Get universal alerts for validation"""
        try:
            # Universal alerts API requires user_id parameter
            if not user_id:
                user_id = "4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"  # Default user ID
            
            params = {"user_id": user_id}
            response = requests.get(f"{self.universal_alerts_url}/alerts", params=params)
            
            if response.status_code == 200:
                data = response.json()
                alerts = data.get("alerts", [])
                return alerts
            elif response.status_code == 422:
                print(f"❌ Validation error: {response.json()}")
                return []
            else:
                print(f"❌ Failed to get universal alerts: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error getting universal alerts: {e}")
            return []

def main():
    """Main migration script"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate Rating Alerts to Universal Alerts")
    parser.add_argument("--user-id", help="User ID for migration (optional)")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without creating alerts")
    parser.add_argument("--validate", action="store_true", help="Validate existing migration")
    parser.add_argument("--python-worker-url", default="http://localhost:8001", help="Python Worker URL")
    
    args = parser.parse_args()
    
    migrator = RatingToUniversalAlertMigrator(args.python_worker_url)
    
    if args.validate:
        # Validate existing migration
        result = migrator.validate_migration(args.user_id)
        print(f"\n✅ Validation {'passed' if result['validation_passed'] else 'failed'}")
    else:
        # Perform migration
        result = migrator.migrate_all_alerts(args.user_id, args.dry_run)
        
        if result["success"]:
            print(f"\n🎉 Migration completed successfully!")
            print(f"   Migrated {result['migrated_count']} alerts")
        else:
            print(f"\n⚠️ Migration completed with {result['failed_count']} failures")
            print(f"   Successfully migrated {result['migrated_count']} alerts")

if __name__ == "__main__":
    main()
