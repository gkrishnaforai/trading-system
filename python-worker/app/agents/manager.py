"""
Agent Manager
Orchestrates multiple AI agents (n8n, LangGraph, custom)
Industry Standard: Strategy Pattern with Adapter Pattern
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.agents.base import BaseAgent, AgentResult, AgentCapability

logger = logging.getLogger(__name__)


class AgentManager:
    """
    Manages multiple AI agents
    Routes tasks to appropriate agents based on capabilities
    """
    
    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._agent_capabilities: Dict[AgentCapability, List[str]] = {}
    
    def register_agent(self, agent: BaseAgent) -> bool:
        """
        Register an agent
        
        Args:
            agent: Agent instance to register
        
        Returns:
            True if successful
        """
        try:
            agent_name = agent.get_name()
            
            if agent_name in self._agents:
                logger.warning(f"Agent '{agent_name}' already registered. Overwriting.")
            
            self._agents[agent_name] = agent
            
            # Index by capabilities
            for capability in agent.get_capabilities():
                if capability not in self._agent_capabilities:
                    self._agent_capabilities[capability] = []
                self._agent_capabilities[capability].append(agent_name)
            
            logger.info(f"✅ Registered agent: {agent_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error registering agent: {e}", exc_info=True)
            return False
    
    def get_agent(self, agent_name: str) -> Optional[BaseAgent]:
        """Get an agent by name"""
        return self._agents.get(agent_name)
    
    def find_agent_for_task(
        self,
        task: str,
        context: Dict[str, Any],
        capability: Optional[AgentCapability] = None
    ) -> Optional[BaseAgent]:
        """
        Find an agent that can handle a task
        
        Args:
            task: Task name/type
            context: Task context
            capability: Optional specific capability to look for
        
        Returns:
            Agent that can handle the task, or None
        """
        # If capability specified, check only those agents
        if capability:
            agent_names = self._agent_capabilities.get(capability, [])
            agents_to_check = [self._agents[name] for name in agent_names if name in self._agents]
        else:
            agents_to_check = list(self._agents.values())
        
        # Find first agent that can handle the task
        for agent in agents_to_check:
            if agent.can_handle(task, context):
                return agent
        
        return None
    
    def execute_task(
        self,
        task: str,
        context: Dict[str, Any],
        agent_name: Optional[str] = None,
        capability: Optional[AgentCapability] = None,
        **kwargs
    ) -> AgentResult:
        """
        Execute a task using an appropriate agent
        
        Args:
            task: Task name/type
            context: Task context
            agent_name: Optional specific agent to use
            capability: Optional capability to look for
            **kwargs: Additional task parameters
        
        Returns:
            AgentResult with execution results
        """
        start_time = datetime.now()
        
        try:
            # Get agent
            if agent_name:
                agent = self.get_agent(agent_name)
                if not agent:
                    return AgentResult(
                        success=False,
                        result={},
                        error=f"Agent '{agent_name}' not found"
                    )
            else:
                agent = self.find_agent_for_task(task, context, capability)
                if not agent:
                    return AgentResult(
                        success=False,
                        result={},
                        error=f"No agent found that can handle task: {task}"
                    )
            
            # Execute task
            result = agent.execute(task, context, **kwargs)
            
            # Add execution time
            execution_time = (datetime.now() - start_time).total_seconds()
            if result.metadata is None:
                result.metadata = {}
            result.metadata['execution_time'] = execution_time
            result.execution_time = execution_time
            
            logger.info(
                f"✅ Task '{task}' executed by agent '{agent.get_name()}' "
                f"in {execution_time:.2f}s"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing task '{task}': {e}", exc_info=True)
            execution_time = (datetime.now() - start_time).total_seconds()
            return AgentResult(
                success=False,
                result={},
                error=str(e),
                execution_time=execution_time
            )
    
    def list_agents(self) -> List[str]:
        """List all registered agents"""
        return list(self._agents.keys())
    
    def get_agents_by_capability(self, capability: AgentCapability) -> List[str]:
        """Get agents that have a specific capability"""
        return self._agent_capabilities.get(capability, [])


# Global agent manager instance
_agent_manager: Optional[AgentManager] = None


def get_agent_manager() -> AgentManager:
    """Get global agent manager instance"""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
    return _agent_manager

