"""
AI Agent Integration System
Supports: n8n workflows, LangGraph flows, custom AI agents
Industry Standard: Adapter Pattern for different agent frameworks
"""
from app.agents.base import BaseAgent, AgentResult, AgentCapability
from app.agents.manager import AgentManager, get_agent_manager
from app.agents.n8n_adapter import N8NAdapter
from app.agents.langgraph_adapter import LangGraphAdapter

__all__ = [
    'BaseAgent',
    'AgentResult',
    'AgentCapability',
    'AgentManager',
    'get_agent_manager',
    'N8NAdapter',
    'LangGraphAdapter',
]

