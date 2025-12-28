# Plugin Architecture Documentation

## Overview

This plugin system implements **DRY** (Don't Repeat Yourself) and **SOLID** principles with centralized logging, exception handling, and lifecycle management. The architecture follows industry best practices for extensible, maintainable plugin systems.

## Architecture Components

### 1. Base Plugin Framework (`app/plugins/base.py`)

**SOLID Principles Applied:**
- **Single Responsibility**: Each plugin type has one clear purpose
- **Open/Closed**: Open for extension, closed for modification
- **Liskov Substitution**: All plugins can be used interchangeably
- **Interface Segregation**: Focused interfaces for different plugin types
- **Dependency Inversion**: Depends on abstractions, not concretions

**Plugin Types:**
- `DataSourcePlugin`: For financial data providers
- `StrategyPlugin`: For trading strategies
- `IndicatorPlugin`: For custom technical indicators
- `AgentPlugin`: For AI agents
- `WorkflowPlugin`: For automation workflows

### 2. Base Adapter Framework (`app/plugins/base_adapter.py`)

**DRY Principles:**
- Centralized error handling decorator
- Common initialization logic
- Shared availability checking
- Unified cleanup procedures

**Best Practices Implemented:**
```python
@handle_plugin_errors("plugin_name")
def method_with_error_handling(self):
    # Automatic logging and error context
    pass
```

**Exception Hierarchy:**
- `PluginError`: Base exception
- `PluginInitializationError`: Initialization failures
- `PluginAvailabilityError`: Availability issues

### 3. Data Source Adapters (`app/plugins/data_source_adapters.py`)

**Adapter Pattern Benefits:**
- Wrap existing data sources without rewriting
- Provide consistent interface across different providers
- Enable hot-swapping of data sources
- Centralized configuration management

**Example Implementation:**
```python
class MassivePluginAdapter(DataSourceAdapter):
    def __init__(self):
        super().__init__(MassiveSource(), "massive")
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="massive",
            version="1.0.0",
            description="Massive.com financial data provider",
            author="Trading System",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=[],
            config_schema={
                "api_key": {"type": "string", "required": True},
                "rate_limit_calls": {"type": "integer", "default": 4}
            }
        )
```

### 4. Registration Manager (`app/plugins/registration_manager.py`)

**Centralized Management:**
- Dependency resolution
- Health monitoring
- Hot reloading
- Graceful shutdown

**DRY Registration:**
```python
# Single line to initialize all data sources
results = initialize_data_sources(config)
```

## Best Practices Implementation

### 1. Use Adapters Pattern ✅
- Wrap existing data sources instead of rewriting
- Maintain backward compatibility
- Enable gradual migration

### 2. Handle Failures ✅
- Comprehensive error handling decorator
- Graceful degradation
- Detailed error logging with context

### 3. Declare Dependencies ✅
- Explicit dependency declaration in metadata
- Automatic dependency validation
- Dependency resolution before initialization

### 4. Provide Cleanup ✅
- Mandatory cleanup method
- Automatic cleanup on shutdown
- Resource management

### 5. Version Control ✅
- Version information in metadata
- Compatibility tracking
- Hot reloading support

## DRY & SOLID Implementation

### DRY Principles
1. **Centralized Error Handling**: `@handle_plugin_errors` decorator
2. **Common Initialization**: Base adapter handles all setup
3. **Shared Configuration**: Unified config management
4. **Unified Logging**: Single logging pattern

### SOLID Principles
1. **Single Responsibility**: Each class has one reason to change
2. **Open/Closed**: Extensible without modification
3. **Liskov Substitution**: Plugins are interchangeable
4. **Interface Segregation**: Focused, minimal interfaces
5. **Dependency Inversion**: Depends on abstractions

## Centralized Logging & Exception Handling

### Logging Strategy
```python
# Plugin-specific loggers
logger = get_logger(f"plugin.{plugin_name}")

# Automatic error context
@handle_plugin_errors("massive")
def fetch_data(self):
    # Errors automatically include plugin context
    pass
```

### Exception Handling
```python
try:
    plugin_operation()
except PluginError as e:
    # Plugin errors include context and logging
    logger.error(f"Plugin operation failed: {e}")
except Exception as e:
    # Unexpected errors are wrapped with context
    raise PluginError(f"Unexpected error: {e}") from e
```

## Usage Examples

### Adding a New Data Source
```python
class NewDataSourceAdapter(DataSourceAdapter):
    def __init__(self):
        super().__init__(NewDataSource(), "new_source")
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="new_source",
            version="1.0.0",
            description="New financial data provider",
            author="Your Name",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=["yahoo_finance"],  # Optional dependencies
            config_schema={
                "api_key": {"type": "string", "required": True},
                "timeout": {"type": "integer", "default": 30}
            }
        )
    
    @handle_plugin_errors("new_source")
    def initialize(self, config=None) -> bool:
        super().initialize(config)
        self._validate_config(["api_key"])
        # Custom initialization logic
        return True
```

### Using Plugins in Application
```python
from app.plugins import get_registry, initialize_data_sources

# Initialize all plugins
config = {
    "massive": {"api_key": "your_key"},
    "yahoo_finance": {"timeout": 30}
}
results = initialize_data_sources(config)

# Use a specific plugin
registry = get_registry()
massive_plugin = registry.get("massive")
if massive_plugin and massive_plugin.is_available():
    data = massive_plugin.fetch_price_data("AAPL")
```

### Monitoring Plugin Health
```python
from app.plugins import get_registration_manager

manager = get_registration_manager()
health = manager.get_plugin_health()

for plugin_name, status in health.items():
    if status["healthy"]:
        print(f"✅ {plugin_name} is healthy")
    else:
        print(f"❌ {plugin_name} has issues: {status.get('error')}")
```

## Configuration Management

### Environment Variables
```bash
# .env file
MASSIVE_API_KEY=your_api_key
MASSIVE_RATE_LIMIT_CALLS=4
YAHOO_FINANCE_TIMEOUT=30
FALLBACK_CACHE_ENABLED=true
```

### Plugin Configuration
```python
# Automatic configuration from environment
plugin_config = {
    "massive": {
        "api_key": settings.massive_api_key,
        "rate_limit_calls": settings.massive_rate_limit_calls
    }
}
```

## Testing

### Unit Tests
```python
class TestPluginAdapter(unittest.TestCase):
    def test_initialization(self):
        adapter = MockPluginAdapter()
        result = adapter.initialize({"key": "value"})
        self.assertTrue(result)
    
    def test_error_handling(self):
        with self.assertRaises(PluginError):
            failing_operation()
```

### Integration Tests
```python
def test_plugin_lifecycle():
    # Register
    manager.register_plugin(MyPlugin)
    
    # Use
    plugin = manager.get("my_plugin")
    data = plugin.fetch_data()
    
    # Cleanup
    manager.unregister_plugin("my_plugin")
```

## Migration Guide

### From Direct Data Sources to Plugins
1. **Create Adapter**: Wrap existing data source
2. **Implement Metadata**: Add version and dependencies
3. **Add Error Handling**: Use decorators
4. **Register Plugin**: Use registration manager
5. **Update Usage**: Use registry instead of direct instantiation

### Example Migration
```python
# Before (direct usage)
from app.data_sources.massive_source import MassiveSource
source = MassiveSource()
data = source.fetch_price_data("AAPL")

# After (plugin usage)
from app.plugins import get_registry
registry = get_registry()
massive = registry.get("massive")
data = massive.fetch_price_data("AAPL")
```

## Performance Considerations

### Lazy Loading
- Plugins are initialized on first use
- Dependencies are resolved only when needed
- Health checks are asynchronous

### Resource Management
- Automatic cleanup on shutdown
- Connection pooling in adapters
- Rate limiting in data sources

### Caching
- Built-in caching in fallback plugin
- Configurable cache TTL
- Cache invalidation strategies

## Security

### API Key Management
- Keys passed through configuration
- Masked in logs
- Environment variable support

### Plugin Isolation
- Error boundaries prevent crashes
- Resource limits per plugin
- Sandboxed execution options

## Future Enhancements

### Plugin Distribution
- Plugin marketplace
- Version compatibility checking
- Automatic updates

### Advanced Features
- Plugin composition
- Event-driven architecture
- Distributed plugin execution

This architecture provides a robust, maintainable, and extensible foundation for the trading system's plugin ecosystem while following industry best practices and design principles.
