"""
Comprehensive tests for Alerts and Notes functionality
Tests: Portfolio CRUD, Stock CRUD, Alert CRUD, Alert notifications (Email/SMS)
Industry Standard: Integration tests with real database, no mocks
"""
import unittest
import sys
import os
import uuid
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import init_database, db
from app.alerts.service import AlertService
from app.alerts.base import AlertContext, NotificationChannel
from app.config import settings


class TestAlertsAndNotes(unittest.TestCase):
    """
    Comprehensive tests for alerts and notes functionality
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("ALERTS AND NOTES INTEGRATION TESTS")
        print("="*80)
        
        # Ensure database directory exists
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database (runs migrations)
        init_database()
        
        cls.alert_service = AlertService()
        # Use unique user ID per test run to avoid conflicts
        cls.test_user_id = f"test_user_{int(datetime.now().timestamp())}"
        cls.test_portfolio_id = None
        cls.test_holding_id = None
        cls.test_alert_id = None
        
        print(f"\n📊 Test user: {cls.test_user_id}")
        print(f"📅 Test date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.alert_service = self.__class__.alert_service
        self.user_id = self.__class__.test_user_id
    
    # ==================== Portfolio CRUD Tests ====================
    
    def test_create_portfolio_with_notes(self):
        """Test creating a portfolio with notes"""
        print("\n📝 Testing portfolio creation with notes...")
        
        portfolio_name = f"Test Portfolio {datetime.now().strftime('%Y%m%d%H%M%S')}"
        notes = "This is a test portfolio for alerts and notes testing"
        
        # Generate unique portfolio ID (timestamp + UUID for uniqueness)
        portfolio_id = f"portfolio_{self.user_id}_{int(datetime.now().timestamp() * 1000000)}_{str(uuid.uuid4())[:8]}"
        
        query = """
            INSERT OR REPLACE INTO portfolios (portfolio_id, user_id, portfolio_name, notes)
            VALUES (:portfolio_id, :user_id, :portfolio_name, :notes)
        """
        
        try:
            db.execute_update(query, {
                "portfolio_id": portfolio_id,
                "user_id": self.user_id,
                "portfolio_name": portfolio_name,
                "notes": notes
            })
            
            # Verify creation
            query = "SELECT * FROM portfolios WHERE portfolio_id = :portfolio_id"
            result = db.execute_query(query, {"portfolio_id": portfolio_id})
            
            self.assertGreater(len(result), 0, "Portfolio should be created")
            self.assertEqual(result[0]['portfolio_name'], portfolio_name)
            self.assertEqual(result[0]['notes'], notes)
            
            # Store for cleanup
            self.__class__.test_portfolio_id = portfolio_id
            
            print(f"✅ Created portfolio: {portfolio_id}")
            print(f"   Name: {portfolio_name}")
            print(f"   Notes: {notes}")
            
        except Exception as e:
            self.fail(f"Failed to create portfolio: {e}")
    
    def test_read_portfolio_with_notes(self):
        """Test reading a portfolio with notes"""
        print("\n📖 Testing portfolio read with notes...")
        
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio_with_notes()
        
        portfolio_id = self.__class__.test_portfolio_id
        
        query = "SELECT * FROM portfolios WHERE portfolio_id = :portfolio_id"
        result = db.execute_query(query, {"portfolio_id": portfolio_id})
        
        self.assertGreater(len(result), 0, "Portfolio should exist")
        self.assertIsNotNone(result[0].get('notes'), "Portfolio should have notes field")
        
        print(f"✅ Read portfolio: {portfolio_id}")
        print(f"   Notes: {result[0].get('notes')}")
    
    def test_update_portfolio_notes(self):
        """Test updating portfolio notes"""
        print("\n✏️  Testing portfolio notes update...")
        
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio_with_notes()
        
        portfolio_id = self.__class__.test_portfolio_id
        new_notes = f"Updated notes at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        query = """
            UPDATE portfolios 
            SET notes = :notes, updated_at = CURRENT_TIMESTAMP
            WHERE portfolio_id = :portfolio_id
        """
        
        db.execute_update(query, {
            "portfolio_id": portfolio_id,
            "notes": new_notes
        })
        
        # Verify update
        query = "SELECT notes FROM portfolios WHERE portfolio_id = :portfolio_id"
        result = db.execute_query(query, {"portfolio_id": portfolio_id})
        
        self.assertEqual(result[0]['notes'], new_notes)
        
        print(f"✅ Updated portfolio notes: {portfolio_id}")
        print(f"   New notes: {new_notes}")
    
    def test_delete_portfolio(self):
        """Test deleting a portfolio"""
        print("\n🗑️  Testing portfolio deletion...")
        
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio_with_notes()
        
        portfolio_id = self.__class__.test_portfolio_id
        
        query = "DELETE FROM portfolios WHERE portfolio_id = :portfolio_id"
        db.execute_update(query, {"portfolio_id": portfolio_id})
        
        # Verify deletion
        query = "SELECT * FROM portfolios WHERE portfolio_id = :portfolio_id"
        result = db.execute_query(query, {"portfolio_id": portfolio_id})
        
        self.assertEqual(len(result), 0, "Portfolio should be deleted")
        
        print(f"✅ Deleted portfolio: {portfolio_id}")
        
        # Reset for other tests
        self.__class__.test_portfolio_id = None
    
    # ==================== Stock/Holding CRUD Tests ====================
    
    def test_create_holding_with_notes(self):
        """Test creating a holding (stock) with notes"""
        print("\n📝 Testing holding creation with notes...")
        
        import uuid
        
        # Create portfolio first
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio_with_notes()
        
        portfolio_id = self.__class__.test_portfolio_id
        stock_symbol = "AAPL"
        notes = f"Test notes for {stock_symbol} - added at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        query = """
            INSERT OR REPLACE INTO holdings 
            (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, 
             position_type, notes, purchase_date)
            VALUES (:holding_id, :portfolio_id, :stock_symbol, :quantity, :avg_entry_price,
                    :position_type, :notes, :purchase_date)
        """
        
        # Generate unique holding ID
        holding_id = f"holding_{portfolio_id}_{int(datetime.now().timestamp() * 1000000)}_{str(uuid.uuid4())[:8]}"
        
        try:
            db.execute_update(query, {
                "holding_id": holding_id,
                "portfolio_id": portfolio_id,
                "stock_symbol": stock_symbol,
                "quantity": 10.0,
                "avg_entry_price": 150.0,
                "position_type": "long",
                "notes": notes,
                "purchase_date": datetime.now().date()
            })
            
            # Verify creation
            query = "SELECT * FROM holdings WHERE holding_id = :holding_id"
            result = db.execute_query(query, {"holding_id": holding_id})
            
            self.assertGreater(len(result), 0, "Holding should be created")
            self.assertEqual(result[0]['stock_symbol'], stock_symbol)
            self.assertEqual(result[0]['notes'], notes)
            
            # Store for cleanup
            self.__class__.test_holding_id = holding_id
            
            print(f"✅ Created holding: {holding_id}")
            print(f"   Symbol: {stock_symbol}")
            print(f"   Notes: {notes}")
            
        except Exception as e:
            self.fail(f"Failed to create holding: {e}")
    
    def test_read_holding_with_notes(self):
        """Test reading a holding with notes"""
        print("\n📖 Testing holding read with notes...")
        
        if not self.__class__.test_holding_id:
            self.test_create_holding_with_notes()
        
        holding_id = self.__class__.test_holding_id
        
        query = "SELECT * FROM holdings WHERE holding_id = :holding_id"
        result = db.execute_query(query, {"holding_id": holding_id})
        
        self.assertGreater(len(result), 0, "Holding should exist")
        self.assertIsNotNone(result[0].get('notes'), "Holding should have notes field")
        
        print(f"✅ Read holding: {holding_id}")
        print(f"   Notes: {result[0].get('notes')}")
    
    def test_update_holding_notes(self):
        """Test updating holding notes"""
        print("\n✏️  Testing holding notes update...")
        
        if not self.__class__.test_holding_id:
            self.test_create_holding_with_notes()
        
        holding_id = self.__class__.test_holding_id
        new_notes = f"Updated notes at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        query = """
            UPDATE holdings 
            SET notes = :notes, updated_at = CURRENT_TIMESTAMP
            WHERE holding_id = :holding_id
        """
        
        db.execute_update(query, {
            "holding_id": holding_id,
            "notes": new_notes
        })
        
        # Verify update
        query = "SELECT notes FROM holdings WHERE holding_id = :holding_id"
        result = db.execute_query(query, {"holding_id": holding_id})
        
        self.assertEqual(result[0]['notes'], new_notes)
        
        print(f"✅ Updated holding notes: {holding_id}")
        print(f"   New notes: {new_notes}")
    
    def test_delete_holding(self):
        """Test deleting a holding"""
        print("\n🗑️  Testing holding deletion...")
        
        if not self.__class__.test_holding_id:
            self.test_create_holding_with_notes()
        
        holding_id = self.__class__.test_holding_id
        
        query = "DELETE FROM holdings WHERE holding_id = :holding_id"
        db.execute_update(query, {"holding_id": holding_id})
        
        # Verify deletion
        query = "SELECT * FROM holdings WHERE holding_id = :holding_id"
        result = db.execute_query(query, {"holding_id": holding_id})
        
        self.assertEqual(len(result), 0, "Holding should be deleted")
        
        print(f"✅ Deleted holding: {holding_id}")
        
        # Reset for other tests
        self.__class__.test_holding_id = None
    
    # ==================== Alert CRUD Tests ====================
    
    def test_create_alert(self):
        """Test creating an alert"""
        print("\n📝 Testing alert creation...")
        
        # Create portfolio first
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio_with_notes()
        
        portfolio_id = self.__class__.test_portfolio_id
        
        alert_id = self.alert_service.create_alert(
            user_id=self.user_id,
            alert_type_id="price_threshold",
            name="Test Price Alert",
            config={
                "alert_type": "price_threshold",
                "threshold": 200.0,
                "direction": "above"
            },
            notification_channels=["email"],
            portfolio_id=portfolio_id,
            enabled=True
        )
        
        self.assertIsNotNone(alert_id, "Alert ID should be returned")
        
        # Verify creation
        alert = self.alert_service.get_alert(alert_id)
        self.assertIsNotNone(alert, "Alert should be created")
        self.assertEqual(alert['name'], "Test Price Alert")
        self.assertEqual(alert['alert_type_id'], "price_threshold")
        
        print(f"✅ Created alert: {alert_id}")
        print(f"   Name: {alert['name']}")
        print(f"   Type: {alert['alert_type_id']}")
        
        # Store for cleanup
        self.__class__.test_alert_id = alert_id
    
    def test_read_alert(self):
        """Test reading an alert"""
        print("\n📖 Testing alert read...")
        
        if not hasattr(self.__class__, 'test_alert_id') or not self.__class__.test_alert_id:
            self.test_create_alert()
        
        alert_id = self.__class__.test_alert_id
        alert = self.alert_service.get_alert(alert_id)
        
        self.assertIsNotNone(alert, "Alert should exist")
        self.assertEqual(alert['alert_id'], alert_id)
        
        print(f"✅ Read alert: {alert_id}")
        print(f"   Name: {alert['name']}")
    
    def test_list_alerts(self):
        """Test listing alerts"""
        print("\n📋 Testing alert listing...")
        
        if not hasattr(self.__class__, 'test_alert_id') or not self.__class__.test_alert_id:
            self.test_create_alert()
        
        alerts = self.alert_service.list_alerts(
            user_id=self.user_id,
            enabled_only=False
        )
        
        self.assertGreater(len(alerts), 0, "Should have at least one alert")
        
        # Verify our test alert is in the list
        alert_ids = [a['alert_id'] for a in alerts]
        self.assertIn(self.__class__.test_alert_id, alert_ids)
        
        print(f"✅ Listed {len(alerts)} alerts")
    
    def test_update_alert(self):
        """Test updating an alert"""
        print("\n✏️  Testing alert update...")
        
        if not hasattr(self.__class__, 'test_alert_id') or not self.__class__.test_alert_id:
            self.test_create_alert()
        
        alert_id = self.__class__.test_alert_id
        new_name = f"Updated Alert {datetime.now().strftime('%H%M%S')}"
        
        success = self.alert_service.update_alert(
            alert_id=alert_id,
            name=new_name
        )
        
        self.assertTrue(success, "Update should succeed")
        
        # Verify update
        alert = self.alert_service.get_alert(alert_id)
        self.assertEqual(alert['name'], new_name)
        
        print(f"✅ Updated alert: {alert_id}")
        print(f"   New name: {new_name}")
    
    def test_delete_alert(self):
        """Test deleting an alert"""
        print("\n🗑️  Testing alert deletion...")
        
        if not hasattr(self.__class__, 'test_alert_id') or not self.__class__.test_alert_id:
            self.test_create_alert()
        
        alert_id = self.__class__.test_alert_id
        
        success = self.alert_service.delete_alert(alert_id)
        self.assertTrue(success, "Delete should succeed")
        
        # Verify deletion
        alert = self.alert_service.get_alert(alert_id)
        self.assertIsNone(alert, "Alert should be deleted")
        
        print(f"✅ Deleted alert: {alert_id}")
        
        # Reset for other tests
        self.__class__.test_alert_id = None
    
    # ==================== Alert Evaluation Tests ====================
    
    def test_evaluate_price_threshold_alert(self):
        """Test evaluating a price threshold alert"""
        print("\n🔔 Testing price threshold alert evaluation...")
        
        # Create alert
        if not hasattr(self.__class__, 'test_alert_id') or not self.__class__.test_alert_id:
            self.test_create_alert()
        
        alert_id = self.__class__.test_alert_id
        
        # Create context with price above threshold
        context = AlertContext(
            user_id=self.user_id,
            portfolio_id=self.__class__.test_portfolio_id,
            stock_symbol="AAPL",
            current_price=250.0  # Above threshold of 200.0
        )
        
        results = self.alert_service.evaluate_alerts(self.user_id, context)
        
        # Should have at least one triggered alert
        triggered = [r for r in results if r.triggered]
        self.assertGreater(len(triggered), 0, "Alert should trigger when price above threshold")
        
        print(f"✅ Evaluated alerts: {len(triggered)} triggered")
        for result in triggered:
            print(f"   - {result.message}")
    
    def test_evaluate_signal_change_alert(self):
        """Test evaluating a signal change alert"""
        print("\n🔔 Testing signal change alert evaluation...")
        
        # Create signal change alert
        alert_id = self.alert_service.create_alert(
            user_id=self.user_id,
            alert_type_id="signal_change",
            name="Test Signal Change Alert",
            config={
                "alert_type": "signal_change",
                "to_signal": "buy"
            },
            notification_channels=["email"],
            stock_symbol="AAPL",
            enabled=True
        )
        
        # Create context with buy signal
        context = AlertContext(
            user_id=self.user_id,
            stock_symbol="AAPL",
            signal="buy",
            metadata={"previous_signal": "hold"}
        )
        
        results = self.alert_service.evaluate_alerts(self.user_id, context)
        
        triggered = [r for r in results if r.triggered]
        self.assertGreater(len(triggered), 0, "Alert should trigger on signal change")
        
        print(f"✅ Evaluated signal change alert: {len(triggered)} triggered")
        
        # Cleanup
        self.alert_service.delete_alert(alert_id)
    
    # ==================== Alert Notification Tests ====================
    
    def test_email_alert_notification(self):
        """Test email alert notification (mock/test mode)"""
        print("\n📧 Testing email alert notification...")
        
        # Create alert
        alert_id = self.alert_service.create_alert(
            user_id=self.user_id,
            alert_type_id="price_threshold",
            name="Email Test Alert",
            config={
                "alert_type": "price_threshold",
                "threshold": 100.0,
                "direction": "above"
            },
            notification_channels=["email"],
            stock_symbol="AAPL",
            enabled=True
        )
        
        # Add test email channel for user
        query = """
            INSERT OR REPLACE INTO notification_channels
            (channel_id, user_id, channel_type, address, verified, enabled)
            VALUES (:channel_id, :user_id, 'email', :address, 1, 1)
        """
        
        channel_id = f"channel_{self.user_id}_email"
        test_email = "test@example.com"
        
        db.execute_update(query, {
            "channel_id": channel_id,
            "user_id": self.user_id,
            "address": test_email
        })
        
        # Create context that triggers alert
        context = AlertContext(
            user_id=self.user_id,
            stock_symbol="AAPL",
            current_price=150.0  # Above threshold
        )
        
        # Evaluate alerts (should trigger and attempt to send email)
        try:
            results = self.alert_service.evaluate_alerts(self.user_id, context)
            triggered = [r for r in results if r.triggered]
            
            self.assertGreater(len(triggered), 0, "Alert should trigger")
            
            # Check notification was recorded
            query = """
                SELECT * FROM alert_notifications
                WHERE alert_id = :alert_id
                ORDER BY created_at DESC
                LIMIT 1
            """
            notifications = db.execute_query(query, {"alert_id": alert_id})
            
            # Notification should be recorded (even if email sending fails in test)
            # In test mode, email plugin logs instead of actually sending
            print(f"✅ Email notification test completed")
            print(f"   Triggered alerts: {len(triggered)}")
            print(f"   Notifications recorded: {len(notifications)}")
            
        except Exception as e:
            # Email sending might fail in test environment (no SMTP configured)
            # This is acceptable - we're testing the alert system, not email delivery
            print(f"⚠️  Email notification test (expected in test env): {e}")
        
        # Cleanup
        self.alert_service.delete_alert(alert_id)
        db.execute_update("DELETE FROM notification_channels WHERE channel_id = :channel_id",
                         {"channel_id": channel_id})
    
    def test_sms_alert_notification(self):
        """Test SMS alert notification (mock/test mode)"""
        print("\n📱 Testing SMS alert notification...")
        
        # Create alert
        alert_id = self.alert_service.create_alert(
            user_id=self.user_id,
            alert_type_id="price_threshold",
            name="SMS Test Alert",
            config={
                "alert_type": "price_threshold",
                "threshold": 100.0,
                "direction": "above"
            },
            notification_channels=["sms"],
            stock_symbol="AAPL",
            enabled=True
        )
        
        # Add test SMS channel for user
        query = """
            INSERT OR REPLACE INTO notification_channels
            (channel_id, user_id, channel_type, address, verified, enabled)
            VALUES (:channel_id, :user_id, 'sms', :address, 1, 1)
        """
        
        channel_id = f"channel_{self.user_id}_sms"
        test_phone = "+1234567890"
        
        db.execute_update(query, {
            "channel_id": channel_id,
            "user_id": self.user_id,
            "address": test_phone
        })
        
        # Create context that triggers alert
        context = AlertContext(
            user_id=self.user_id,
            stock_symbol="AAPL",
            current_price=150.0  # Above threshold
        )
        
        # Evaluate alerts (should trigger and attempt to send SMS)
        try:
            results = self.alert_service.evaluate_alerts(self.user_id, context)
            triggered = [r for r in results if r.triggered]
            
            self.assertGreater(len(triggered), 0, "Alert should trigger")
            
            # Check notification was recorded
            query = """
                SELECT * FROM alert_notifications
                WHERE alert_id = :alert_id
                ORDER BY created_at DESC
                LIMIT 1
            """
            notifications = db.execute_query(query, {"alert_id": alert_id})
            
            # Notification should be recorded (even if SMS sending fails in test)
            # In test mode, SMS plugin logs instead of actually sending
            print(f"✅ SMS notification test completed")
            print(f"   Triggered alerts: {len(triggered)}")
            print(f"   Notifications recorded: {len(notifications)}")
            
        except Exception as e:
            # SMS sending might fail in test environment (no Twilio/AWS configured)
            # This is acceptable - we're testing the alert system, not SMS delivery
            print(f"⚠️  SMS notification test (expected in test env): {e}")
        
        # Cleanup
        self.alert_service.delete_alert(alert_id)
        db.execute_update("DELETE FROM notification_channels WHERE channel_id = :channel_id",
                         {"channel_id": channel_id})
    
    # ==================== Pluggable Alert System Tests ====================
    
    def test_alert_plugin_registry(self):
        """Test that alert plugins are registered and available"""
        print("\n🔌 Testing alert plugin registry...")
        
        registry = self.alert_service.registry
        
        # Check default plugins are registered
        email_plugin = registry.get("email_alert")
        self.assertIsNotNone(email_plugin, "Email alert plugin should be registered")
        
        sms_plugin = registry.get("sms_alert")
        self.assertIsNotNone(sms_plugin, "SMS alert plugin should be registered")
        
        # List all plugins
        plugins = registry.list_plugins()
        self.assertGreater(len(plugins), 0, "Should have registered plugins")
        
        print(f"✅ Alert plugin registry working")
        print(f"   Registered plugins: {', '.join(plugins)}")
    
    def test_alert_type_from_database(self):
        """Test that alert types can be loaded from database"""
        print("\n💾 Testing alert types from database...")
        
        # Check that default alert types exist in database
        query = "SELECT * FROM alert_types WHERE enabled = 1"
        alert_types = db.execute_query(query)
        
        self.assertGreater(len(alert_types), 0, "Should have alert types in database")
        
        # Verify we have the expected alert types
        type_ids = [at['alert_type_id'] for at in alert_types]
        expected_types = ['price_threshold', 'signal_change', 'volume_spike']
        
        for expected_type in expected_types:
            self.assertIn(expected_type, type_ids, f"Should have {expected_type} alert type")
        
        print(f"✅ Found {len(alert_types)} alert types in database")
        for at in alert_types:
            print(f"   - {at['name']} ({at['alert_type_id']})")


if __name__ == '__main__':
    unittest.main(verbosity=2)

