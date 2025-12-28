# Integration Examples

## Quick Start: Using the Plugin System

### 1. Register Existing Yahoo Finance as Plugin

```python
from app.plugins import get_registry
from app.data_sources.adapters import YahooFinancePluginAdapter

# Register Yahoo Finance as a plugin
registry = get_registry()
registry.register(YahooFinancePluginAdapter)

# Use it
data_source = registry.get("yahoo_finance")
data = data_source.fetch_price_data("AAPL")
```

### 2. Add n8n Workflow Agent

```python
from app.agents import get_agent_manager, N8NAdapter

# Initialize n8n adapter
agent_manager = get_agent_manager()
n8n = N8NAdapter(n8n_url="http://localhost:5678", api_key="your-api-key")

# Register a workflow
n8n.register_workflow("stock_analysis", "workflow_id_123")
agent_manager.register_agent(n8n)

# Execute workflow
result = agent_manager.execute_task(
    task="stock_analysis",
    context={
        "symbol": "AAPL",
        "indicators": {...},
        "user_preferences": {"risk_tolerance": "moderate"}
    }
)

if result.success:
    print(f"Analysis: {result.result}")
```

### 3. Add LangGraph Flow Agent

```python
from app.agents import get_agent_manager, LangGraphAdapter
from langgraph.graph import StateGraph

# Create your LangGraph flow
def create_stock_analysis_flow():
    workflow = StateGraph(...)
    # Define your flow logic
    return workflow.compile()

# Register flow
agent_manager = get_agent_manager()
langgraph = LangGraphAdapter()
langgraph.register_flow("stock_analysis", create_stock_analysis_flow())
agent_manager.register_agent(langgraph)

# Execute flow
result = agent_manager.execute_task(
    task="stock_analysis",
    context={"symbol": "AAPL", "indicators": {...}}
)
```

### 4. Event-Driven Agent Workflows

```python
from app.events import get_event_manager, EventType

event_manager = get_event_manager()

# Subscribe to signal generation events
def on_signal_generated(event):
    # Trigger agent workflow when signal is generated
    from app.agents import get_agent_manager

    agent_manager = get_agent_manager()
    result = agent_manager.execute_task(
        task="analyze_signal",
        context=event.data
    )
    print(f"Agent analysis: {result.result}")

event_manager.subscribe(EventType.SIGNAL_GENERATED, on_signal_generated)
```

### 5. Add Custom Data Source

```python
from app.plugins.base import DataSourcePlugin, PluginMetadata, PluginType
import pandas as pd

class AlphaVantagePlugin(DataSourcePlugin):
    def get_metadata(self):
        return PluginMetadata(
            name="alpha_vantage",
            version="1.0.0",
            description="Alpha Vantage data source",
            author="Your Name",
            plugin_type=PluginType.DATA_SOURCE
        )

    def initialize(self, config):
        self.api_key = config.get('api_key')
        return True

    def is_available(self):
        return self.api_key is not None

    def cleanup(self):
        pass

    def fetch_price_data(self, symbol, start_date=None, end_date=None, period="1y"):
        # Implement Alpha Vantage API calls
        # ...
        return pd.DataFrame(...)

    # Implement other methods...

# Register
from app.plugins import get_registry
registry = get_registry()
registry.register(AlphaVantagePlugin, config={'api_key': 'your-key'})
```

### 6. Configuration-Driven Loading

Create `config/plugins.yaml`:

```yaml
plugins:
  data_sources:
    - module: app.data_sources.adapters
      class: YahooFinancePluginAdapter
      config: {}

    - module: app.plugins.custom.alpha_vantage
      class: AlphaVantagePlugin
      config:
        api_key: ${ALPHA_VANTAGE_API_KEY}

  agents:
    - module: app.agents.n8n_adapter
      class: N8NAdapter
      config:
        n8n_url: ${N8N_URL}
        api_key: ${N8N_API_KEY}

  strategies:
    - module: app.strategies.custom.my_strategy
      class: MyCustomStrategy
      config: {}
```

Load plugins:

```python
from app.plugins.loader import load_plugins_from_config
from pathlib import Path

load_plugins_from_config(Path("config/plugins.yaml"))
```

## Benefits

1. **Zero Code Changes**: Add new providers/agents without modifying existing code
2. **Hot-Swapping**: Reload plugins without restarting the system
3. **Framework Agnostic**: Support n8n, LangGraph, and custom agents
4. **Event-Driven**: Agents can react to system events
5. **Configuration-Driven**: Load plugins from config files
6. **Type-Safe**: Clear interfaces and type hints
