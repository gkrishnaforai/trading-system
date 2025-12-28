"""
n8n Workflow Adapter
Industry Standard: Adapter Pattern for n8n integration
Allows running n8n workflows as AI agents
"""
import logging
import requests
from typing import Dict, Any, Optional, List

from app.agents.base import BaseAgent, AgentResult, AgentCapability
from app.config import settings

logger = logging.getLogger(__name__)


class N8NAdapter(BaseAgent):
    """
    Adapter for n8n workflows
    Executes n8n workflows as AI agents
    """
    
    def __init__(self, n8n_url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize n8n adapter
        
        Args:
            n8n_url: n8n instance URL (defaults to env var)
            api_key: n8n API key (defaults to env var)
        """
        self.n8n_url = n8n_url or getattr(settings, 'n8n_url', None)
        self.api_key = api_key or getattr(settings, 'n8n_api_key', None)
        self._workflows: Dict[str, str] = {}  # workflow_name -> workflow_id
    
    def get_name(self) -> str:
        return "n8n"
    
    def get_capabilities(self) -> List[AgentCapability]:
        """n8n can handle any custom workflow"""
        return [
            AgentCapability.CUSTOM_WORKFLOW,
            AgentCapability.STOCK_ANALYSIS,
            AgentCapability.RESEARCH,
            AgentCapability.REPORT_GENERATION,
        ]
    
    def can_handle(self, task: str, context: Dict[str, Any]) -> bool:
        """Check if n8n has a workflow for this task"""
        if not self.is_available():
            return False
        
        # Check if we have a workflow registered for this task
        return task in self._workflows or self._find_workflow_by_name(task) is not None
    
    def is_available(self) -> bool:
        """Check if n8n is available"""
        if not self.n8n_url:
            return False
        
        try:
            response = requests.get(
                f"{self.n8n_url}/healthz",
                timeout=5,
                headers=self._get_headers()
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"n8n health check failed: {e}")
            return False
    
    def register_workflow(self, workflow_name: str, workflow_id: str) -> None:
        """
        Register a workflow mapping
        
        Args:
            workflow_name: Task/workflow name
            workflow_id: n8n workflow ID
        """
        self._workflows[workflow_name] = workflow_id
        logger.info(f"✅ Registered n8n workflow: {workflow_name} -> {workflow_id}")
    
    def execute(
        self,
        task: str,
        context: Dict[str, Any],
        **kwargs
    ) -> AgentResult:
        """
        Execute n8n workflow
        
        Args:
            task: Task/workflow name
            context: Task context
            **kwargs: Additional parameters
        
        Returns:
            AgentResult with workflow execution results
        """
        try:
            # Find workflow ID
            workflow_id = self._workflows.get(task)
            if not workflow_id:
                workflow_id = self._find_workflow_by_name(task)
                if not workflow_id:
                    return AgentResult(
                        success=False,
                        result={},
                        error=f"Workflow '{task}' not found"
                    )
            
            # Execute workflow via n8n API
            response = requests.post(
                f"{self.n8n_url}/api/v1/workflows/{workflow_id}/execute",
                json={
                    "data": context,
                    **kwargs
                },
                headers=self._get_headers(),
                timeout=300  # 5 minutes for long-running workflows
            )
            
            if response.status_code == 200:
                result_data = response.json()
                return AgentResult(
                    success=True,
                    result=result_data.get('data', {}),
                    metadata={
                        'workflow_id': workflow_id,
                        'workflow_name': task
                    }
                )
            else:
                return AgentResult(
                    success=False,
                    result={},
                    error=f"n8n API error: {response.status_code} - {response.text}"
                )
                
        except Exception as e:
            logger.error(f"Error executing n8n workflow '{task}': {e}", exc_info=True)
            return AgentResult(
                success=False,
                result={},
                error=str(e)
            )
    
    def _find_workflow_by_name(self, task: str) -> Optional[str]:
        """Find workflow ID by name via n8n API"""
        try:
            response = requests.get(
                f"{self.n8n_url}/api/v1/workflows",
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                workflows = response.json()
                for workflow in workflows:
                    if workflow.get('name') == task or workflow.get('id') == task:
                        return workflow.get('id')
            
        except Exception as e:
            logger.debug(f"Error finding workflow: {e}")
        
        return None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for n8n API requests"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-N8N-API-KEY"] = self.api_key
        return headers

