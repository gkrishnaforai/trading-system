"""
Base Plugin Interfaces
Industry Standard: Plugin Pattern with clear contracts
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import pandas as pd


class PluginType(Enum):
    """Types of plugins supported"""
    DATA_SOURCE = "data_source"
    STRATEGY = "strategy"
    INDICATOR = "indicator"
    AGENT = "agent"
    WORKFLOW = "workflow"


@dataclass
class PluginMetadata:
    """Metadata for a plugin"""
    name: str
    version: str
    description: str
    author: str
    plugin_type: PluginType
    dependencies: List[str] = None
    config_schema: Dict[str, Any] = None


class Plugin(ABC):
    """
    Base plugin interface
    All plugins must implement this interface
    """
    
    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Get plugin metadata"""
        pass
    
    @abstractmethod
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Initialize the plugin
        
        Args:
            config: Plugin-specific configuration
        
        Returns:
            True if initialization successful
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if plugin is available/healthy"""
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup resources when plugin is unloaded"""
        pass


class DataSourcePlugin(Plugin):
    """
    Plugin interface for data sources
    Extends BaseDataSource with plugin capabilities
    """
    
    @abstractmethod
    def fetch_price_data(
        self,
        symbol: str,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        period: str = "1y"
    ) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV price data"""
        pass
    
    @abstractmethod
    def fetch_current_price(self, symbol: str) -> Optional[float]:
        """Fetch current/live price"""
        pass
    
    @abstractmethod
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data"""
        pass
    
    @abstractmethod
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent news articles"""
        pass
    
    @abstractmethod
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings calendar and history"""
        pass
    
    @abstractmethod
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Fetch industry peers and sector data"""
        pass


class StrategyPlugin(Plugin):
    """
    Plugin interface for trading strategies
    Extends BaseStrategy with plugin capabilities
    """
    
    @abstractmethod
    def generate_signal(
        self,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Generate trading signal"""
        pass
    
    @abstractmethod
    def get_required_indicators(self) -> List[str]:
        """Get list of required indicators"""
        pass


class IndicatorPlugin(Plugin):
    """
    Plugin interface for custom indicators
    Allows adding new technical indicators
    """
    
    @abstractmethod
    def calculate(
        self,
        data: pd.Series,
        **kwargs
    ) -> pd.Series:
        """Calculate indicator values"""
        pass
    
    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """Get indicator parameters and defaults"""
        pass


class AgentPlugin(Plugin):
    """
    Plugin interface for AI agents
    Supports: n8n workflows, LangGraph flows, custom AI agents
    """
    
    @abstractmethod
    def execute(
        self,
        task: str,
        context: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute agent task
        
        Args:
            task: Task name/type (e.g., 'analyze_stock', 'generate_report')
            context: Context data (symbol, indicators, user preferences, etc.)
            **kwargs: Additional task-specific parameters
        
        Returns:
            Task result dictionary
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Get list of tasks this agent can perform"""
        pass
    
    @abstractmethod
    def can_handle(self, task: str) -> bool:
        """Check if agent can handle a specific task"""
        pass


class WorkflowPlugin(Plugin):
    """
    Plugin interface for workflows
    Supports: n8n workflows, LangGraph flows, custom automation
    """
    
    @abstractmethod
    def run(
        self,
        workflow_name: str,
        input_data: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run a workflow
        
        Args:
            workflow_name: Name of the workflow to run
            input_data: Input data for the workflow
            **kwargs: Additional workflow parameters
        
        Returns:
            Workflow result dictionary
        """
        pass
    
    @abstractmethod
    def list_workflows(self) -> List[str]:
        """List available workflows"""
        pass
    
    @abstractmethod
    def get_workflow_schema(self, workflow_name: str) -> Dict[str, Any]:
        """Get workflow input/output schema"""
        pass

