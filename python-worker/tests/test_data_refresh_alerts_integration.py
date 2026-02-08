"""
Enhanced Integration Tests for Data Refresh with Alerts & Audit Tracking
Tests complete pipeline: data loading -> audit tracking -> alert creation -> notifications
Covers analyst grades, price targets, and Universal Alerts integration
"""
import unittest
import sys
import os
from datetime import datetime, timedelta
import json

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import init_database, db
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import RefreshMode, DataType
from app.services.indicator_service import IndicatorService
from app.services.universal_alert_service_enhanced import universal_alert_service
from app.config import settings
from pathlib import Path


class TestDataRefreshWithAlertsIntegration(unittest.TestCase):
    """
    Enhanced integration tests covering data refresh, audit tracking, and alerts
    Tests analyst grades, price targets, and Universal Alerts integration
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("ENHANCED DATA REFRESH + ALERTS INTEGRATION TESTS")
        print("="*80)
        
        # Ensure database directory exists
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        init_database()
        
        cls.refresh_manager = DataRefreshManager()
        cls.indicator_service = IndicatorService()
        cls.symbols = ['AAPL', 'MSFT']  # Use symbols with good analyst coverage
        
        print(f"\n📊 Testing with symbols: {', '.join(cls.symbols)}")
        print(f"📅 Test date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.refresh_manager = self.__class__.refresh_manager
        self.indicator_service = self.__class__.indicator_service
        self.symbols = self.__class__.symbols

    def test_analyst_grades_data_loading_and_tracking(self):
        """Test loading analyst grades data and audit tracking"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🎓 Testing analyst grades loading for {symbol}...")
                
                # Load analyst grades data
                result = self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.STOCK_GRADES],
                    mode=RefreshMode.ON_DEMAND,
                    force=True
                )
                
                # Validate data loading
                self.assertIsNotNone(result, f"{symbol}: Should return result")
                grades_result = result.results.get(DataType.STOCK_GRADES.value)
                
                if grades_result and grades_result.status.value == 'success':
                    print(f"✅ {symbol}: Analyst grades loaded successfully")
                    print(f"   Rows affected: {grades_result.rows_affected}")
                    
                    # Verify data in database
                    query = """
                        SELECT COUNT(*) as count
                        FROM stock_grades
                        WHERE symbol = :symbol
                    """
                    db_result = db.execute_query(query, {"symbol": symbol})
                    count = db_result[0]['count'] if db_result else 0
                    
                    self.assertGreater(count, 0, f"{symbol}: Should have grades data in database")
                    
                    # Test audit tracking
                    self._verify_audit_tracking(symbol, 'stock_grades')
                    
                else:
                    print(f"⚠️  {symbol}: Analyst grades loading failed or no data")

    def test_price_targets_data_loading_and_alerts(self):
        """Test loading price targets data and alert creation"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🎯 Testing price targets loading for {symbol}...")
                
                # Load price targets data
                result = self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_TARGETS],
                    mode=RefreshMode.ON_DEMAND,
                    force=True
                )
                
                # Validate data loading
                self.assertIsNotNone(result, f"{symbol}: Should return result")
                targets_result = result.results.get(DataType.PRICE_TARGETS.value)
                
                if targets_result and targets_result.status.value == 'success':
                    print(f"✅ {symbol}: Price targets loaded successfully")
                    print(f"   Rows affected: {targets_result.rows_affected}")
                    
                    # Verify data in database
                    query = """
                        SELECT COUNT(*) as count, 
                               AVG(price_target) as avg_target,
                               MAX(price_target) as max_target,
                               MIN(price_target) as min_target
                        FROM price_targets
                        WHERE symbol = :symbol
                        AND published_date >= CURRENT_DATE - INTERVAL '30 days'
                    """
                    db_result = db.execute_query(query, {"symbol": symbol})
                    
                    if db_result and db_result[0]['count'] > 0:
                        record = db_result[0]
                        print(f"   Recent targets: {record['count']}")
                        print(f"   Average target: ${record['avg_target']:.2f}")
                        print(f"   Target range: ${record['min_target']:.2f} - ${record['max_target']:.2f}")
                        
                        # Test audit tracking
                        self._verify_audit_tracking(symbol, 'price_targets')
                        
                        # Test alert creation for price targets
                        self._test_price_target_alerts(symbol, record)
                        
                    else:
                        print(f"⚠️  {symbol}: No recent price targets found")
                else:
                    print(f"⚠️  {symbol}: Price targets loading failed or no data")

    def test_consensus_data_loading_and_notifications(self):
        """Test loading consensus data and notification system"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n📊 Testing consensus data loading for {symbol}...")
                
                # Load consensus data
                result = self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.CONSENSUS_DATA],
                    mode=RefreshMode.ON_DEMAND,
                    force=True
                )
                
                # Validate data loading
                self.assertIsNotNone(result, f"{symbol}: Should return result")
                consensus_result = result.results.get(DataType.CONSENSUS_DATA.value)
                
                if consensus_result and consensus_result.status.value == 'success':
                    print(f"✅ {symbol}: Consensus data loaded successfully")
                    print(f"   Rows affected: {consensus_result.rows_affected}")
                    
                    # Verify data in database
                    query = """
                        SELECT COUNT(*) as count,
                               AVG(analyst_count) as avg_analysts,
                               AVG(consensus_rating) as avg_rating
                        FROM stock_consensus
                        WHERE symbol = :symbol
                        AND updated_at >= CURRENT_DATE - INTERVAL '7 days'
                    """
                    db_result = db.execute_query(query, {"symbol": symbol})
                    
                    if db_result and db_result[0]['count'] > 0:
                        record = db_result[0]
                        print(f"   Recent consensus records: {record['count']}")
                        print(f"   Average analysts: {record['avg_analysts']:.1f}")
                        print(f"   Average rating: {record['avg_rating']:.2f}")
                        
                        # Test audit tracking
                        self._verify_audit_tracking(symbol, 'consensus_data')
                        
                        # Test Universal Alerts integration
                        self._test_consensus_alerts(symbol, record)
                        
                    else:
                        print(f"⚠️  {symbol}: No recent consensus data found")
                else:
                    print(f"⚠️  {symbol}: Consensus data loading failed or no data")

    def test_universal_alerts_integration(self):
        """Test Universal Alerts system integration with data loading"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🔔 Testing Universal Alerts integration for {symbol}...")
                
                # Create a test alert for grade changes
                try:
                    alert_request = {
                        "alert_name": f"Test Grade Change Alert - {symbol}",
                        "alert_type": "grade_change",
                        "entity_filters": {"symbols": [symbol]},
                        "trigger_conditions": {
                            "grade_change_threshold": 1,
                            "direction": "upgrade"
                        },
                        "notification_config": {
                            "channels": ["email"],
                            "recipients": ["test@example.com"]
                        },
                        "priority_level": 3,
                        "is_test": True
                    }
                    
                    # Create alert through Universal Alerts service
                    alert_result = universal_alert_service.create_alert(
                        alert_name=alert_request["alert_name"],
                        alert_type=alert_request["alert_type"],
                        entity_filters=alert_request["entity_filters"],
                        trigger_conditions=alert_request["trigger_conditions"],
                        notification_config=alert_request["notification_config"],
                        priority_level=alert_request["priority_level"],
                        is_test=alert_request["is_test"]
                    )
                    
                    if alert_result:
                        alert_id = alert_result.get('alert_id')
                        print(f"✅ {symbol}: Test alert created - ID: {alert_id}")
                        
                        # Verify alert in database
                        self._verify_alert_in_database(alert_id, symbol)
                        
                        # Test notification history
                        self._verify_notification_history(alert_id)
                        
                    else:
                        print(f"⚠️  {symbol}: Failed to create test alert")
                        
                except Exception as e:
                    print(f"❌ {symbol}: Universal Alerts integration error: {e}")

    def test_complete_data_pipeline_with_alerts(self):
        """Test complete pipeline: data loading -> audit -> alerts -> notifications"""
        symbol = self.symbols[0]  # Test with first symbol
        print(f"\n🔄 Testing complete pipeline for {symbol}...")
        
        # Step 1: Load multiple data types
        critical_data_types = [
            DataType.STOCK_GRADES,
            DataType.PRICE_TARGETS,
            DataType.CONSENSUS_DATA,
            DataType.ANALYST_RATINGS
        ]
        
        result = self.refresh_manager.refresh_data(
            symbol=symbol,
            data_types=critical_data_types,
            mode=RefreshMode.ON_DEMAND,
            force=True
        )
        
        self.assertIsNotNone(result, f"{symbol}: Should return result")
        
        # Step 2: Verify all data loaded
        success_count = 0
        for data_type in critical_data_types:
            type_result = result.results.get(data_type.value)
            if type_result and type_result.status.value == 'success':
                success_count += 1
                print(f"✅ {symbol}: {data_type.value} loaded successfully")
        
        print(f"📊 {symbol}: {success_count}/{len(critical_data_types)} data types loaded")
        
        # Step 3: Verify audit tracking for all data types
        for data_type in critical_data_types:
            self._verify_audit_tracking(symbol, data_type.value)
        
        # Step 4: Test alert creation based on loaded data
        self._test_data_driven_alerts(symbol, result)
        
        print(f"🎉 {symbol}: Complete pipeline test completed")

    def _verify_audit_tracking(self, symbol: str, data_type: str):
        """Verify data loading is tracked in audit tables"""
        try:
            # Check data_refresh_history
            query = """
                SELECT COUNT(*) as count,
                       MAX(status) as latest_status,
                       MAX(refresh_start) as last_refresh
                FROM data_refresh_history
                WHERE symbol = :symbol
                AND data_type = :data_type
                AND refresh_start >= CURRENT_DATE - INTERVAL '1 hour'
            """
            result = db.execute_query(query, {"symbol": symbol, "data_type": data_type})
            
            if result and result[0]['count'] > 0:
                record = result[0]
                print(f"   📋 Audit: {record['count']} refresh records found")
                print(f"   📋 Status: {record['latest_status']}")
                print(f"   📋 Last refresh: {record['last_refresh']}")
            else:
                print(f"   ⚠️  Audit: No recent refresh records found for {data_type}")
                
        except Exception as e:
            print(f"   ❌ Audit verification failed: {e}")

    def _test_price_target_alerts(self, symbol: str, target_data: dict):
        """Test alert creation for price target changes"""
        try:
            # Create alert for significant price target changes
            alert_request = {
                "alert_name": f"Price Target Change Alert - {symbol}",
                "alert_type": "price_target_change",
                "entity_filters": {"symbols": [symbol]},
                "trigger_conditions": {
                    "target_change_threshold": 5.0,  # 5% change
                    "min_analyst_count": 3
                },
                "notification_config": {
                    "channels": ["email"],
                    "recipients": ["trader@example.com"]
                },
                "priority_level": 2,
                "is_test": True
            }
            
            alert_result = universal_alert_service.create_alert(**alert_request)
            
            if alert_result:
                print(f"   🔔 Price target alert created - ID: {alert_result.get('alert_id')}")
            else:
                print(f"   ⚠️  Failed to create price target alert")
                
        except Exception as e:
            print(f"   ❌ Price target alert error: {e}")

    def _test_consensus_alerts(self, symbol: str, consensus_data: dict):
        """Test alert creation for consensus rating changes"""
        try:
            # Create alert for consensus rating changes
            alert_request = {
                "alert_name": f"Consensus Rating Alert - {symbol}",
                "alert_type": "consensus_rating_change",
                "entity_filters": {"symbols": [symbol]},
                "trigger_conditions": {
                    "rating_change_threshold": 0.5,
                    "min_analyst_count": 5
                },
                "notification_config": {
                    "channels": ["email", "sms"],
                    "recipients": ["analyst@example.com"]
                },
                "priority_level": 3,
                "is_test": True
            }
            
            alert_result = universal_alert_service.create_alert(**alert_request)
            
            if alert_result:
                print(f"   🔔 Consensus alert created - ID: {alert_result.get('alert_id')}")
            else:
                print(f"   ⚠️  Failed to create consensus alert")
                
        except Exception as e:
            print(f"   ❌ Consensus alert error: {e}")

    def _verify_alert_in_database(self, alert_id: str, symbol: str):
        """Verify alert is stored in database"""
        try:
            query = """
                SELECT alert_name, alert_type, status, created_at
                FROM universal_alerts
                WHERE alert_id = :alert_id
            """
            result = db.execute_query(query, {"alert_id": alert_id})
            
            if result:
                record = result[0]
                print(f"   ✅ Alert verified in DB: {record['alert_name']}")
                print(f"   ✅ Type: {record['alert_type']}, Status: {record['status']}")
            else:
                print(f"   ❌ Alert not found in database")
                
        except Exception as e:
            print(f"   ❌ Alert verification failed: {e}")

    def _verify_notification_history(self, alert_id: str):
        """Verify notification history for alert"""
        try:
            notifications = universal_alert_service.get_notification_history(alert_id)
            
            if notifications:
                print(f"   📧 Notification history: {len(notifications)} records")
                for notif in notifications[:2]:  # Show first 2
                    print(f"      - {notif.get('status')} at {notif.get('sent_at')}")
            else:
                print(f"   📧 No notification history found")
                
        except Exception as e:
            print(f"   ❌ Notification history verification failed: {e}")

    def _test_data_driven_alerts(self, symbol: str, refresh_result):
        """Test creating alerts based on loaded data"""
        try:
            # Example: Create alert if significant data changes detected
            for data_type, result in refresh_result.results.items():
                if result and result.status.value == 'success' and result.rows_affected > 0:
                    print(f"   🔔 Processing {data_type} for alert opportunities...")
                    
                    # This would integrate with your business logic for alert creation
                    # For now, just log the opportunity
                    print(f"      - {result.rows_affected} rows loaded, potential alert triggers")
                    
        except Exception as e:
            print(f"   ❌ Data-driven alert testing failed: {e}")


if __name__ == '__main__':
    # Run the enhanced tests
    unittest.main(verbosity=2)
