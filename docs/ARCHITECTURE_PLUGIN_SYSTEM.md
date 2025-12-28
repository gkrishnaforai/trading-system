# Plugin System Architecture

## Overview

The Trading System uses industry-standard design patterns (as of December 2025) to ensure maximum flexibility and extensibility. The architecture supports:

- **Plug-and-play data providers** (Yahoo Finance, Alpha Vantage, Polygon, etc.)
- **Pluggable trading strategies** (Technical, LLM-based, Custom)
- **Extensible indicators** (Add custom technical indicators)
- **AI Agent integration** (n8n workflows, LangGraph flows, custom agents)
- **Workflow automation** (n8n, LangGraph, custom workflows)

## Design Patterns Used

### 1. Plugin Registry Pattern
**Purpose**: Centralized plugin management with dynamic loading

**Implementation**: `app/plugins/registry.py`
- Singleton pattern for global registry
- Dynamic plugin loading from modules/directories
- Dependency resolution
- Hot-swapping support
- Health monitoring

**Usage**:
```python
from app.plugins import get_registry

registry = get_registry()
registry.register(MyCustomDataSource)
plugin = registry.get("my_custom_data_source")
```

### 2. Strategy Pattern
**Purpose**: Interchangeable algorithms (data sources, strategies, indicators)

**Implementation**: 
- `app/data_sources/base.py` - BaseDataSource interface
- `app/strategies/base.py` - BaseStrategy interface
- `app/plugins/base.py` - Plugin interfaces

**Benefits**:
- Easy to swap implementations
- No code changes needed to add new providers
- Runtime selection of strategies

### 3. Adapter Pattern
**Purpose**: Integrate different frameworks (n8n, LangGraph) with consistent interface

**Implementation**: 
- `app/agents/n8n_adapter.py` - n8n workflow adapter
- `app/agents/langgraph_adapter.py` - LangGraph flow adapter

**Benefits**:
- Unified interface for different AI frameworks
- Easy to add new agent frameworks
- Framework-agnostic code

### 4. Factory Pattern
**Purpose**: Create objects without specifying exact classes

**Implementation**: 
- `app/data_sources/__init__.py` - `get_data_source()` factory
- `app/plugins/registry.py` - Plugin factory

**Benefits**:
- Centralized object creation
- Configuration-driven instantiation
- Easy to extend with new types

### 5. Dependency Injection
**Purpose**: Loose coupling and testability

**Implementation**: `app/di/container.py`

**Benefits**:
- Easy to mock for testing
- Flexible service swapping
- Clear dependencies

### 6. Observer Pattern (Event-Driven)
**Purpose**: Decoupled communication for AI agents

**Implementation**: Event system for agent workflows

**Benefits**:
- Agents can react to events
- Loose coupling between components
- Easy to add new event handlers

## Architecture Components

### Plugin System

```
app/plugins/
├── __init__.py          # Plugin system exports
├── base.py              # Base plugin interfaces
└── registry.py          # Plugin registry (Singleton)
```

**Plugin Types**:
1. **DataSourcePlugin** - Data providers (Yahoo, Alpha Vantage, etc.)
2. **StrategyPlugin** - Trading strategies
3. **IndicatorPlugin** - Technical indicators
4. **AgentPlugin** - AI agents (n8n, LangGraph, custom)
5. **WorkflowPlugin** - Automation workflows

### Agent System

```
app/agents/
├── __init__.py          # Agent system exports
├── base.py              # Base agent interface
├── manager.py           # Agent manager (orchestration)
├── n8n_adapter.py      # n8n workflow adapter
└── langgraph_adapter.py # LangGraph flow adapter
```

**Agent Capabilities**:
- Stock Analysis
- Signal Generation
- Research
- Report Generation
- Risk Assessment
- Portfolio Optimization
- Custom Workflows

## Adding New Components

### Adding a New Data Source

1. **Create plugin class**:
```python
from app.plugins.base import DataSourcePlugin, PluginMetadata, PluginType

class AlphaVantageSource(DataSourcePlugin):
    def get_metadata(self):
        return PluginMetadata(
            name="alpha_vantage",
            version="1.0.0",
            description="Alpha Vantage data source",
            author="Your Name",
            plugin_type=PluginType.DATA_SOURCE
        )
    
    def initialize(self, config):
        # Initialize Alpha Vantage client
        return True
    
    # Implement all abstract methods...
```

2. **Register plugin**:
```python
from app.plugins import get_registry

registry = get_registry()
registry.register(AlphaVantageSource, config={'api_key': '...'})
```

3. **Use plugin**:
```python
data_source = registry.get("alpha_vantage")
data = data_source.fetch_price_data("AAPL")
```

### Adding a New Strategy

1. **Create strategy plugin**:
```python
from app.plugins.base import StrategyPlugin, PluginMetadata, PluginType
from app.strategies.base import StrategyResult

class MyCustomStrategy(StrategyPlugin):
    def get_metadata(self):
        return PluginMetadata(
            name="my_custom_strategy",
            version="1.0.0",
            description="My custom trading strategy",
            author="Your Name",
            plugin_type=PluginType.STRATEGY
        )
    
    def generate_signal(self, indicators, market_data, context):
        # Your strategy logic
        return StrategyResult(...)
```

2. **Register and use**:
```python
registry.register(MyCustomStrategy)
strategy = registry.get("my_custom_strategy")
```

### Adding n8n Workflow

1. **Create workflow in n8n** (e.g., "Stock Analysis Workflow")

2. **Register in code**:
```python
from app.agents import get_agent_manager, N8NAdapter

agent_manager = get_agent_manager()
n8n_adapter = N8NAdapter(n8n_url="http://localhost:5678")
n8n_adapter.register_workflow("stock_analysis", "workflow_id_123")
agent_manager.register_agent(n8n_adapter)
```

3. **Execute workflow**:
```python
result = agent_manager.execute_task(
    task="stock_analysis",
    context={
        "symbol": "AAPL",
        "indicators": {...},
        "user_preferences": {...}
    }
)
```

### Adding LangGraph Flow

1. **Create LangGraph flow**:
```python
from langgraph.graph import StateGraph

def create_stock_analysis_flow():
    # Define your LangGraph flow
    workflow = StateGraph(...)
    return workflow.compile()
```

2. **Register flow**:
```python
from app.agents import get_agent_manager, LangGraphAdapter

agent_manager = get_agent_manager()
langgraph_adapter = LangGraphAdapter()
langgraph_adapter.register_flow("stock_analysis", create_stock_analysis_flow())
agent_manager.register_agent(langgraph_adapter)
```

3. **Execute flow**:
```python
result = agent_manager.execute_task(
    task="stock_analysis",
    context={"symbol": "AAPL", "indicators": {...}}
)
```

## Configuration-Driven Loading

Plugins can be loaded from configuration:

```python
# config/plugins.yaml
plugins:
  data_sources:
    - module: app.plugins.custom.alpha_vantage_source
      class: AlphaVantageSource
      config:
        api_key: ${ALPHA_VANTAGE_API_KEY}
  
  agents:
    - module: app.agents.n8n_adapter
      class: N8NAdapter
      config:
        n8n_url: ${N8N_URL}
        api_key: ${N8N_API_KEY}
```

## Benefits

1. **Flexibility**: Add/remove components without code changes
2. **Extensibility**: Easy to add new providers, strategies, agents
3. **Testability**: Mock plugins for testing
4. **Maintainability**: Clear separation of concerns
5. **Scalability**: Load only needed plugins
6. **Hot-swapping**: Reload plugins without restart
7. **Framework-agnostic**: Support multiple AI frameworks

## Industry Standards Compliance

- **SOLID Principles**: All interfaces follow SOLID
- **Design Patterns**: Strategy, Adapter, Factory, Registry, Observer
- **Plugin Architecture**: Industry-standard plugin system
- **Event-Driven**: Support for event-driven workflows
- **Microservices-Ready**: Components can be extracted to services
- **Cloud-Native**: Supports containerization and scaling

## Future Enhancements

1. **Plugin Marketplace**: Centralized plugin repository
2. **Plugin Versioning**: Support multiple versions
3. **Plugin Sandboxing**: Isolated execution environment
4. **Plugin Metrics**: Performance monitoring
5. **Plugin Dependencies**: Automatic dependency resolution
6. **Plugin Updates**: Automatic update mechanism

