"""
LangGraph Flow Adapter
Industry Standard: Adapter Pattern for LangGraph integration
Allows running LangGraph flows as AI agents
"""
import logging
from typing import Dict, Any, Optional, List

from app.agents.base import BaseAgent, AgentResult, AgentCapability

logger = logging.getLogger(__name__)


class LangGraphAdapter(BaseAgent):
    """
    Adapter for LangGraph flows
    Executes LangGraph flows as AI agents
    """
    
    def __init__(self, flow_path: Optional[str] = None):
        """
        Initialize LangGraph adapter
        
        Args:
            flow_path: Path to LangGraph flow definition
        """
        self.flow_path = flow_path
        self._flows: Dict[str, Any] = {}  # flow_name -> flow_instance
    
    def get_name(self) -> str:
        return "langgraph"
    
    def get_capabilities(self) -> List[AgentCapability]:
        """LangGraph can handle complex agentic workflows"""
        return [
            AgentCapability.STOCK_ANALYSIS,
            AgentCapability.SIGNAL_GENERATION,
            AgentCapability.RESEARCH,
            AgentCapability.REPORT_GENERATION,
            AgentCapability.RISK_ASSESSMENT,
            AgentCapability.CUSTOM_WORKFLOW,
        ]
    
    def can_handle(self, task: str, context: Dict[str, Any]) -> bool:
        """Check if LangGraph has a flow for this task"""
        if not self.is_available():
            return False
        return task in self._flows
    
    def is_available(self) -> bool:
        """Check if LangGraph is available"""
        try:
            # Try to import LangGraph
            import langgraph
            return True
        except ImportError:
            logger.debug("LangGraph not installed")
            return False
    
    def register_flow(self, flow_name: str, flow_instance: Any) -> None:
        """
        Register a LangGraph flow
        
        Args:
            flow_name: Task/flow name
            flow_instance: LangGraph flow instance
        """
        self._flows[flow_name] = flow_instance
        logger.info(f"✅ Registered LangGraph flow: {flow_name}")
    
    def execute(
        self,
        task: str,
        context: Dict[str, Any],
        **kwargs
    ) -> AgentResult:
        """
        Execute LangGraph flow
        
        Args:
            task: Task/flow name
            context: Task context
            **kwargs: Additional parameters
        
        Returns:
            AgentResult with flow execution results
        """
        try:
            if task not in self._flows:
                return AgentResult(
                    success=False,
                    result={},
                    error=f"Flow '{task}' not found"
                )
            
            flow = self._flows[task]
            
            # Execute flow
            # LangGraph flows are typically invoked with an initial state
            result = flow.invoke({
                **context,
                **kwargs
            })
            
            return AgentResult(
                success=True,
                result=result if isinstance(result, dict) else {'output': result},
                metadata={
                    'flow_name': task,
                    'flow_type': 'langgraph'
                }
            )
            
        except Exception as e:
            logger.error(f"Error executing LangGraph flow '{task}': {e}", exc_info=True)
            return AgentResult(
                success=False,
                result={},
                error=str(e)
            )

