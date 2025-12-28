"""
Base Agent Interface
Industry Standard: Adapter Pattern for AI agent frameworks
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import pandas as pd


class AgentCapability(Enum):
    """Capabilities that agents can provide"""
    STOCK_ANALYSIS = "stock_analysis"
    SIGNAL_GENERATION = "signal_generation"
    RESEARCH = "research"
    REPORT_GENERATION = "report_generation"
    RISK_ASSESSMENT = "risk_assessment"
    PORTFOLIO_OPTIMIZATION = "portfolio_optimization"
    CUSTOM_WORKFLOW = "custom_workflow"


@dataclass
class AgentResult:
    """Result from an agent execution"""
    success: bool
    result: Dict[str, Any]
    metadata: Dict[str, Any] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None


class BaseAgent(ABC):
    """
    Base interface for all AI agents
    Supports: n8n, LangGraph, custom agents
    """
    
    @abstractmethod
    def get_name(self) -> str:
        """Get agent name"""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[AgentCapability]:
        """Get list of agent capabilities"""
        pass
    
    @abstractmethod
    def can_handle(self, task: str, context: Dict[str, Any]) -> bool:
        """
        Check if agent can handle a task
        
        Args:
            task: Task name/type
            context: Task context
        
        Returns:
            True if agent can handle the task
        """
        pass
    
    @abstractmethod
    def execute(
        self,
        task: str,
        context: Dict[str, Any],
        **kwargs
    ) -> AgentResult:
        """
        Execute an agent task
        
        Args:
            task: Task name/type
            context: Task context (symbol, indicators, user preferences, etc.)
            **kwargs: Additional task-specific parameters
        
        Returns:
            AgentResult with execution results
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if agent is available/healthy"""
        pass
    
    def get_input_schema(self, task: str) -> Dict[str, Any]:
        """
        Get input schema for a task (optional)
        
        Args:
            task: Task name
        
        Returns:
            JSON schema for task inputs
        """
        return {}
    
    def get_output_schema(self, task: str) -> Dict[str, Any]:
        """
        Get output schema for a task (optional)
        
        Args:
            task: Task name
        
        Returns:
            JSON schema for task outputs
        """
        return {}

