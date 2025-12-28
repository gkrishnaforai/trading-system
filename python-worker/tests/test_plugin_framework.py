"""
Plugin Framework Tests
DRY & SOLID: Comprehensive testing of plugin architecture with best practices
"""
import unittest
from unittest.mock import Mock, patch
from typing import Dict, Any

from app.plugins.base import PluginType, PluginMetadata
from app.plugins.base_adapter import (
    BasePluginAdapter, 
    DataSourceAdapter, 
    PluginError,
    PluginInitializationError,
    handle_plugin_errors
)
from app.plugins.data_source_adapters import (
    MassivePluginAdapter,
    YahooFinancePluginAdapter,
    FallbackPluginAdapter
)
from app.plugins.registration_manager import (
    PluginRegistrationManager,
    get_registration_manager,
    initialize_data_sources
)
from app.plugins import get_registry


class MockDataSource:
    """Mock data source for testing"""
    
    def __init__(self, available=True):
        self.available = available
        self.initialized = False
    
    def is_available(self) -> bool:
        return self.available
    
    def initialize(self, config=None) -> bool:
        self.initialized = True
        return True
    
    def cleanup(self) -> None:
        self.initialized = False
    
    def fetch_price_data(self, symbol: str, **kwargs):
        return f"Mock data for {symbol}"


class MockPluginAdapter(DataSourceAdapter):
    """Mock plugin adapter for testing"""
    
    def __init__(self, wrapped_instance=None, available=True):
        super().__init__(wrapped_instance or MockDataSource(available), "mock")
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="mock",
            version="1.0.0",
            description="Mock plugin for testing",
            author="Test Suite",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=[]
        )


class TestBaseAdapter(unittest.TestCase):
    """Test base adapter functionality"""
    
    def setUp(self):
        self.mock_source = MockDataSource()
        self.adapter = MockPluginAdapter(self.mock_source)
    
    def test_initialization_success(self):
        """Test successful plugin initialization"""
        config = {"test_key": "test_value"}
        result = self.adapter.initialize(config)
        
        self.assertTrue(result)
        self.assertTrue(self.adapter._initialized)
        self.assertEqual(self.adapter._config, config)
    
    def test_initialization_failure_unavailable(self):
        """Test initialization failure when source unavailable"""
        unavailable_source = MockDataSource(available=False)
        adapter = MockPluginAdapter(unavailable_source)
        
        with self.assertRaises(PluginInitializationError):
            adapter.initialize()
    
    def test_availability_check(self):
        """Test plugin availability checking"""
        self.assertTrue(self.adapter.is_available())
        
        # Test unavailable source
        unavailable_source = MockDataSource(available=False)
        adapter = MockPluginAdapter(unavailable_source)
        self.assertFalse(adapter.is_available())
    
    def test_cleanup(self):
        """Test plugin cleanup"""
        self.adapter.initialize()
        self.assertTrue(self.adapter._initialized)
        
        self.adapter.cleanup()
        self.assertFalse(self.adapter._initialized)
    
    def test_config_validation(self):
        """Test configuration validation"""
        adapter = MockPluginAdapter()
        
        # Should pass with required keys
        adapter._config = {"required_key": "value"}
        adapter._validate_config(["required_key"])  # Should not raise
        
        # Should fail with missing keys
        adapter._config = {}
        with self.assertRaises(PluginInitializationError):
            adapter._validate_config(["missing_key"])
    
    def test_error_decorator(self):
        """Test error handling decorator"""
        @handle_plugin_errors("test_plugin")
        def test_function():
            raise ValueError("Test error")
        
        with self.assertRaises(PluginError):
            test_function()


class TestDataSourceAdapters(unittest.TestCase):
    """Test data source adapters"""
    
    def test_massive_adapter_metadata(self):
        """Test Massive adapter metadata"""
        adapter = MassivePluginAdapter()
        metadata = adapter.get_metadata()
        
        self.assertEqual(metadata.name, "massive")
        self.assertEqual(metadata.version, "1.0.0")
        self.assertEqual(metadata.plugin_type, PluginType.DATA_SOURCE)
        self.assertIn("api_key", metadata.config_schema)
    
    def test_yahoo_adapter_metadata(self):
        """Test Yahoo Finance adapter metadata"""
        adapter = YahooFinancePluginAdapter()
        metadata = adapter.get_metadata()
        
        self.assertEqual(metadata.name, "yahoo_finance")
        self.assertEqual(metadata.version, "1.0.0")
        self.assertEqual(metadata.plugin_type, PluginType.DATA_SOURCE)
        self.assertIn("timeout", metadata.config_schema)
    
    def test_fallback_adapter_dependencies(self):
        """Test Fallback adapter dependencies"""
        adapter = FallbackPluginAdapter()
        metadata = adapter.get_metadata()
        
        self.assertEqual(metadata.name, "fallback")
        self.assertIn("yahoo_finance", metadata.dependencies)
    
    @patch('app.plugins.data_source_adapters.MassiveSource')
    def test_massive_adapter_initialization(self, mock_source_class):
        """Test Massive adapter initialization"""
        mock_source = Mock()
        mock_source.is_available.return_value = True
        mock_source_class.return_value = mock_source
        
        adapter = MassivePluginAdapter()
        config = {"api_key": "test_key"}
        
        result = adapter.initialize(config)
        self.assertTrue(result)
        self.assertTrue(adapter._initialized)


class TestRegistrationManager(unittest.TestCase):
    """Test plugin registration manager"""
    
    def setUp(self):
        self.manager = PluginRegistrationManager()
    
    def tearDown(self):
        # Clean up all registered plugins
        for plugin_name in list(self.manager._registered_plugins.keys()):
            self.manager.unregister_plugin(plugin_name)
    
    def test_register_plugin_success(self):
        """Test successful plugin registration"""
        result = self.manager.register_plugin(MockPluginAdapter)
        self.assertTrue(result)
        
        # Check plugin is in registry
        self.assertIn("mock", self.manager._registered_plugins)
    
    def test_register_plugin_with_config(self):
        """Test plugin registration with configuration"""
        config = {"test_config": "test_value"}
        result = self.manager.register_plugin(MockPluginAdapter, config)
        self.assertTrue(result)
    
    def test_unregister_plugin(self):
        """Test plugin unregistration"""
        # First register
        self.manager.register_plugin(MockPluginAdapter)
        self.assertIn("mock", self.manager._registered_plugins)
        
        # Then unregister
        result = self.manager.unregister_plugin("mock")
        self.assertTrue(result)
        self.assertNotIn("mock", self.manager._registered_plugins)
    
    def test_dependency_validation(self):
        """Test dependency validation"""
        # Create a plugin with dependencies
        class DependentPlugin(MockPluginAdapter):
            def get_metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="dependent",
                    version="1.0.0",
                    description="Dependent plugin",
                    author="Test",
                    plugin_type=PluginType.DATA_SOURCE,
                    dependencies=["nonexistent"]
                )
        
        # Should fail due to missing dependency
        result = self.manager.register_plugin(DependentPlugin)
        self.assertFalse(result)
    
    def test_health_check(self):
        """Test plugin health checking"""
        self.manager.register_plugin(MockPluginAdapter)
        
        health = self.manager.get_plugin_health()
        self.assertIn("mock", health)
        self.assertTrue(health["mock"]["healthy"])


class TestPluginIntegration(unittest.TestCase):
    """Integration tests for the complete plugin system"""
    
    def setUp(self):
        # Clean up registry before each test
        registry = get_registry()
        for plugin_name in list(registry._plugins.keys()):
            registry.unregister(plugin_name)
    
    def test_initialize_data_sources(self):
        """Test data source initialization"""
        config = {
            "mock": {"test_key": "test_value"}
        }
        
        # Mock the create_data_source_adapters function
        with patch('app.plugins.registration_manager.create_data_source_adapters') as mock_create:
            mock_create.return_value = [MockPluginAdapter()]
            
            results = initialize_data_sources(config)
            
            self.assertIn("mock", results)
            self.assertTrue(results["mock"])
    
    def test_plugin_lifecycle(self):
        """Test complete plugin lifecycle"""
        manager = get_registration_manager()
        
        # Register plugin
        success = manager.register_plugin(MockPluginAdapter, {"test": "config"})
        self.assertTrue(success)
        
        # Get plugin
        plugin = manager.get("mock")
        self.assertIsNotNone(plugin)
        self.assertTrue(plugin.is_available())
        
        # Check health
        health = manager.get_plugin_health()
        self.assertIn("mock", health)
        self.assertTrue(health["mock"]["healthy"])
        
        # Unregister plugin
        success = manager.unregister_plugin("mock")
        self.assertTrue(success)
        
        # Plugin should be gone
        plugin = manager.get("mock")
        self.assertIsNone(plugin)


if __name__ == "__main__":
    unittest.main()
