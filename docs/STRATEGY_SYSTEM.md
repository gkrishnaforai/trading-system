# Pluggable Strategy System

## Overview

The trading system uses a **pluggable strategy architecture** that allows:
- Multiple strategies to be registered and used
- User-level strategy preferences
- Portfolio-level strategy overrides
- Easy addition of new strategies
- Strategy composition (e.g., technical + LLM)

## Architecture

### Components

1. **BaseStrategy** (`app/strategies/base.py`)
   - Abstract base class for all strategies
   - Defines interface: `generate_signal()`, `get_name()`, `get_description()`

2. **StrategyRegistry** (`app/strategies/registry.py`)
   - Singleton registry for managing strategies
   - Allows dynamic registration of new strategies
   - Provides lookup and instantiation

3. **StrategyService** (`app/services/strategy_service.py`)
   - Manages user/portfolio strategy preferences
   - Executes strategies with proper context
   - Handles strategy selection logic

### Strategy Selection Priority

1. **Portfolio-level strategy** (highest priority)
2. **User-level preferred strategy**
3. **Default strategy** (`technical`)

## Available Strategies

### 1. Technical Strategy (`technical`)
- **Description**: Standard technical analysis using EMA crossovers, MACD, RSI
- **Default**: Yes
- **Requirements**: Standard indicators (EMA20, EMA50, SMA200, MACD, RSI)

### 2. Hybrid LLM Strategy (`hybrid_llm`)
- **Description**: Combines technical analysis (70%) with LLM-based geopolitical/news analysis (30%)
- **Requirements**: 
  - Standard indicators
  - LLM API key (OpenAI/Anthropic)
- **Configuration**:
  - `technical_weight`: 0.7 (default)
  - `llm_weight`: 0.3 (default)
  - `require_llm_confirmation`: false (default)

## Adding a New Strategy

### Step 1: Create Strategy Class

```python
# app/strategies/my_custom_strategy.py
from app.strategies.base import BaseStrategy, StrategyResult
from typing import Dict, Any, Optional
import pandas as pd

class MyCustomStrategy(BaseStrategy):
    def get_name(self) -> str:
        return "my_custom"
    
    def get_description(self) -> str:
        return "My custom trading strategy"
    
    def generate_signal(
        self,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> StrategyResult:
        # Your strategy logic here
        return StrategyResult(
            signal='buy',  # or 'sell', 'hold'
            confidence=0.75,
            reason="Your explanation",
            metadata={},
            strategy_name=self.name
        )
```

### Step 2: Register Strategy

```python
# In app/strategies/__init__.py
from app.strategies.my_custom_strategy import MyCustomStrategy

# Auto-register
register_strategy(MyCustomStrategy)
```

Or register manually:
```python
from app.strategies import register_strategy
from app.strategies.my_custom_strategy import MyCustomStrategy

register_strategy(MyCustomStrategy)
```

### Step 3: Use Strategy

```python
from app.services.strategy_service import StrategyService

strategy_service = StrategyService()

# Set user strategy
strategy_service.set_user_strategy("user1", "my_custom")

# Or set portfolio strategy
strategy_service.set_portfolio_strategy("portfolio1", "my_custom")
```

## Example: Hybrid Strategy (Technical + LLM)

The `HybridLLMStrategy` demonstrates how to combine multiple strategies:

```python
class HybridLLMStrategy(BaseStrategy):
    def __init__(self, config=None):
        super().__init__(config)
        # Use TechnicalStrategy internally
        self.technical_strategy = TechnicalStrategy()
        self.llm_agent = LLMAgent()
    
    def generate_signal(self, indicators, market_data, context):
        # Get technical signal
        tech_result = self.technical_strategy.generate_signal(...)
        
        # Get LLM signal
        llm_signal = self._get_llm_signal(...)
        
        # Combine signals
        return self._combine_signals(tech_result, llm_signal)
```

## Database Schema

### Users Table
- `preferred_strategy`: User's default strategy preference

### Portfolios Table
- `strategy_name`: Portfolio-specific strategy (overrides user preference)

## API Usage

### Get Available Strategies

```python
from app.strategies import list_strategies

strategies = list_strategies()
# Returns: {'technical': 'Description...', 'hybrid_llm': 'Description...'}
```

### Execute Strategy

```python
from app.services.strategy_service import StrategyService

service = StrategyService()
result = service.execute_strategy(
    strategy_name="hybrid_llm",
    indicators={...},
    context={'symbol': 'AAPL'}
)

print(f"Signal: {result.signal}")
print(f"Confidence: {result.confidence}")
print(f"Reason: {result.reason}")
```

## Configuration

### User-Level Strategy

```sql
UPDATE users 
SET preferred_strategy = 'hybrid_llm' 
WHERE user_id = 'user1';
```

### Portfolio-Level Strategy

```sql
UPDATE portfolios 
SET strategy_name = 'hybrid_llm' 
WHERE portfolio_id = 'portfolio1';
```

### Strategy-Specific Configuration

```python
# When executing strategy
config = {
    'technical_weight': 0.6,
    'llm_weight': 0.4,
    'require_llm_confirmation': True
}

result = service.execute_strategy(
    "hybrid_llm",
    indicators,
    config=config
)
```

## Best Practices

1. **Strategy Independence**: Each strategy should be self-contained
2. **Clear Interfaces**: Follow the `BaseStrategy` interface
3. **Error Handling**: Return `hold` signal with low confidence on errors
4. **Documentation**: Document strategy logic and requirements
5. **Testing**: Write unit tests for each strategy
6. **Configuration**: Make strategies configurable via `config` parameter

## Future Strategies Ideas

- **Momentum Strategy**: Pure momentum-based signals
- **Mean Reversion Strategy**: Counter-trend signals
- **Sentiment Strategy**: News/social media sentiment analysis
- **Multi-Timeframe Strategy**: Combines signals from multiple timeframes
- **ML Strategy**: Machine learning model-based signals

