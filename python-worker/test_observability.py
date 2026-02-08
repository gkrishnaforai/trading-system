#!/usr/bin/env python3
"""
Test script to verify all observability imports work correctly
"""

import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_imports():
    """Test all observability imports"""
    print("🧪 Testing Observability Module Imports...")
    
    try:
        # Test core imports
        print("  📦 Testing core logging imports...")
        from app.observability import get_logger, setup_logging, log_with_context
        print("    ✅ Core logging imports successful")
        
        # Test metrics
        print("  📦 Testing metrics imports...")
        from app.observability import get_metrics, MetricsCollector, track_duration
        print("    ✅ Metrics imports successful")
        
        # Test API logging
        print("  📦 Testing API logging imports...")
        from app.observability.api_logging import APILoggingMiddleware, APIPerformanceLogger
        print("    ✅ API logging imports successful")
        
        # Test constants
        print("  📦 Testing constants imports...")
        from app.observability.constants import generate_tracking_id, LOG_PATTERNS, API_ENDPOINT_CONFIG
        print("    ✅ Constants imports successful")
        
        # Test audit logging
        print("  📦 Testing audit logging imports...")
        from app.observability.audit_logger import audit_log, AuditLogger
        print("    ✅ Audit logging imports successful")
        
        # Test log viewer
        print("  📦 Testing log viewer imports...")
        from app.observability.log_viewer import APILogViewer, log_viewer
        print("    ✅ Log viewer imports successful")
        
        # Test configuration
        print("  📦 Testing configuration imports...")
        from app.observability.api_logging_config import setup_universal_alert_logging, get_endpoint_config
        print("    ✅ Configuration imports successful")
        
        # Test functionality
        print("  🔧 Testing basic functionality...")
        
        # Test tracking ID generation
        tracking_id = generate_tracking_id("test")
        assert tracking_id.startswith("test_"), f"Invalid tracking ID: {tracking_id}"
        print(f"    ✅ Tracking ID generation: {tracking_id}")
        
        # Test logger creation
        logger = get_logger("test_logger")
        assert logger is not None, "Logger creation failed"
        print("    ✅ Logger creation successful")
        
        # Test log viewer creation
        viewer = APILogViewer()
        assert viewer is not None, "Log viewer creation failed"
        print("    ✅ Log viewer creation successful")
        
        # Test audit logger creation
        audit_logger_instance = AuditLogger()
        assert audit_logger_instance is not None, "Audit logger creation failed"
        print("    ✅ Audit logger creation successful")
        
        print("\n🎉 All imports and basic functionality tests passed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

def test_dry_principles():
    """Test that DRY principles are followed"""
    print("\n🔍 Testing DRY Principles...")
    
    try:
        # Test that constants are used consistently
        from app.observability.constants import API_ENDPOINT_CONFIG
        from app.observability.api_logging_config import get_endpoint_config
        
        # Test that both modules use the same endpoint config
        config1 = API_ENDPOINT_CONFIG.get("POST /alerts")
        config2 = get_endpoint_config("POST", "/alerts")
        
        assert config1 is not None, "API_ENDPOINT_CONFIG missing POST /alerts"
        assert config2 is not None, "get_endpoint_config failed for POST /alerts"
        assert config1["log_request_body"] == config2["log_request_body"], "Configuration mismatch"
        
        print("    ✅ DRY principles: Shared constants used consistently")
        
        # Test that tracking ID generation is consistent
        from app.observability.constants import generate_tracking_id
        
        id1 = generate_tracking_id("test")
        id2 = generate_tracking_id("test")
        
        assert id1 != id2, "Tracking IDs should be unique"
        assert id1.startswith("test_"), "Tracking ID should start with operation"
        assert id2.startswith("test_"), "Tracking ID should start with operation"
        
        print("    ✅ DRY principles: Tracking ID generation consistent")
        
        print("🎉 DRY principles test passed!")
        return True
        
    except Exception as e:
        print(f"❌ DRY test error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 80)
    print("🧪 Universal Alert System Observability Test Suite")
    print("=" * 80)
    
    success = True
    
    # Test imports
    if not test_imports():
        success = False
    
    # Test DRY principles
    if not test_dry_principles():
        success = False
    
    print("\n" + "=" * 80)
    if success:
        print("🎉 All tests passed! Observability system is ready.")
    else:
        print("❌ Some tests failed. Please check the errors above.")
    print("=" * 80)
    
    sys.exit(0 if success else 1)
