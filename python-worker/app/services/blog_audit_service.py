"""
Blog Generation Audit Service
Industry Standard: Event Sourcing + Audit Log Pattern
Purpose: Full audit trail, retry/recovery, LLM provider switching, compliance
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
import json

from app.database import db
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.utils.exception_handler import handle_database_errors


class BlogAuditService(BaseService):
    """
    Service for managing blog generation audit trail
    
    SOLID: Single Responsibility - only handles audit logging
    Industry Standard: Event Sourcing pattern for full audit trail
    """
    
    def __init__(self):
        """Initialize blog audit service"""
        super().__init__()
    
    def create_audit_record(
        self,
        user_id: str,
        topic_id: str,
        generation_request: Dict[str, Any],
        context_data: Dict[str, Any],
        agent_config: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> str:
        """
        Create a new audit record for blog generation
        
        Args:
            user_id: User ID
            topic_id: Topic ID
            generation_request: Complete generation request
            context_data: Full context data for LLM
            agent_config: Agent configuration (provider, model, etc.)
            correlation_id: Optional correlation ID for tracing
        
        Returns:
            Audit ID
        """
        try:
            audit_id = f"audit_{uuid.uuid4().hex[:16]}"
            
            query = """
                INSERT INTO blog_generation_audit
                (audit_id, user_id, topic_id, generation_request, context_data,
                 agent_type, agent_config, llm_provider, llm_model, llm_parameters,
                 status, stage, correlation_id, started_at)
                VALUES (:audit_id, :user_id, :topic_id, :generation_request, :context_data,
                        :agent_type, :agent_config, :llm_provider, :llm_model, :llm_parameters,
                        'pending', 'topic_ranked', :correlation_id, CURRENT_TIMESTAMP)
            """
            
            db.execute_update(query, {
                "audit_id": audit_id,
                "user_id": user_id,
                "topic_id": topic_id,
                "generation_request": json.dumps(generation_request),
                "context_data": json.dumps(context_data),
                "agent_type": agent_config.get('agent_type', 'direct_llm'),
                "agent_config": json.dumps(agent_config),
                "llm_provider": agent_config.get('llm_provider', 'openai'),
                "llm_model": agent_config.get('llm_model', 'gpt-4'),
                "llm_parameters": json.dumps(agent_config.get('llm_parameters', {})),
                "correlation_id": correlation_id or f"corr_{uuid.uuid4().hex[:16]}"
            })
            
            logger.info(f"✅ Created audit record {audit_id} for topic {topic_id}")
            return audit_id
            
        except Exception as e:
            logger.error(f"Error creating audit record: {e}", exc_info=True)
            raise DatabaseError(f"Failed to create audit record: {str(e)}") from e
    
    def update_audit_stage(
        self,
        audit_id: str,
        stage: str,
        status: str = 'in_progress',
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Update audit record stage and status
        
        Args:
            audit_id: Audit ID
            stage: Current stage
            status: Status (pending, in_progress, success, failed)
            data: Optional data to update (prompts, results, etc.)
        """
        try:
            updates = ["stage = :stage", "status = :status", "updated_at = CURRENT_TIMESTAMP"]
            params = {
                "audit_id": audit_id,
                "stage": stage,
                "status": status
            }
            
            if data:
                if 'system_prompt' in data:
                    updates.append("system_prompt = :system_prompt")
                    params["system_prompt"] = data['system_prompt']
                
                if 'user_prompt' in data:
                    updates.append("user_prompt = :user_prompt")
                    params["user_prompt"] = data['user_prompt']
                
                if 'prompt_template' in data:
                    updates.append("prompt_template = :prompt_template")
                    params["prompt_template"] = data['prompt_template']
                
                if 'generation_result' in data:
                    updates.append("generation_result = :generation_result")
                    params["generation_result"] = json.dumps(data['generation_result'])
                
                if 'generated_content' in data:
                    updates.append("generated_content = :generated_content")
                    params["generated_content"] = data['generated_content']
                
                if 'generation_metadata' in data:
                    updates.append("generation_metadata = :generation_metadata")
                    params["generation_metadata"] = json.dumps(data['generation_metadata'])
                
                if 'error_message' in data:
                    updates.append("error_message = :error_message")
                    params["error_message"] = data['error_message']
                
                if 'error_details' in data:
                    updates.append("error_details = :error_details")
                    params["error_details"] = json.dumps(data['error_details'])
            
            if status in ['success', 'failed', 'cancelled']:
                updates.append("completed_at = CURRENT_TIMESTAMP")
            
            query = f"""
                UPDATE blog_generation_audit
                SET {', '.join(updates)}
                WHERE audit_id = :audit_id
            """
            
            db.execute_update(query, params)
            
            logger.debug(f"Updated audit {audit_id} to stage {stage}, status {status}")
            
        except Exception as e:
            logger.error(f"Error updating audit record: {e}", exc_info=True)
            raise DatabaseError(f"Failed to update audit record: {str(e)}") from e
    
    def record_agent_invocation(
        self,
        audit_id: str,
        system_prompt: str,
        user_prompt: str,
        prompt_template: Optional[str] = None
    ):
        """Record agent invocation with prompts"""
        self.update_audit_stage(
            audit_id,
            stage='agent_invoked',
            status='in_progress',
            data={
                'system_prompt': system_prompt,
                'user_prompt': user_prompt,
                'prompt_template': prompt_template
            }
        )
    
    def record_generation_result(
        self,
        audit_id: str,
        generation_result: Dict[str, Any],
        generated_content: str,
        generation_metadata: Dict[str, Any]
    ):
        """Record generation result from agent"""
        self.update_audit_stage(
            audit_id,
            stage='content_generated',
            status='success',
            data={
                'generation_result': generation_result,
                'generated_content': generated_content,
                'generation_metadata': generation_metadata
            }
        )
    
    def record_generation_failure(
        self,
        audit_id: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None,
        can_retry: bool = True
    ):
        """Record generation failure"""
        try:
            # Get current retry count
            query = """
                SELECT retry_count, max_retries FROM blog_generation_audit
                WHERE audit_id = :audit_id
            """
            result = db.execute_query(query, {"audit_id": audit_id})
            
            if result:
                retry_count = result[0].get('retry_count', 0)
                max_retries = result[0].get('max_retries', 3)
                
                # Check if can retry
                if retry_count >= max_retries:
                    can_retry = False
            else:
                retry_count = 0
                can_retry = False
            
            updates = [
                "stage = 'failed'",
                "status = 'failed'",
                "error_message = :error_message",
                "can_retry = :can_retry",
                "updated_at = CURRENT_TIMESTAMP"
            ]
            params = {
                "audit_id": audit_id,
                "error_message": error_message,
                "can_retry": can_retry
            }
            
            if error_details:
                updates.append("error_details = :error_details")
                params["error_details"] = json.dumps(error_details)
            
            query = f"""
                UPDATE blog_generation_audit
                SET {', '.join(updates)}
                WHERE audit_id = :audit_id
            """
            
            db.execute_update(query, params)
            
            logger.warning(f"Recorded failure for audit {audit_id}: {error_message}")
            
        except Exception as e:
            logger.error(f"Error recording failure: {e}", exc_info=True)
            raise DatabaseError(f"Failed to record failure: {str(e)}") from e
    
    def get_audit_record(self, audit_id: str) -> Optional[Dict[str, Any]]:
        """Get full audit record"""
        try:
            query = """
                SELECT * FROM blog_generation_audit
                WHERE audit_id = :audit_id
            """
            result = db.execute_query(query, {"audit_id": audit_id})
            
            if result:
                record = result[0]
                # Parse JSON fields
                return {
                    "audit_id": record['audit_id'],
                    "user_id": record.get('user_id'),
                    "topic_id": record.get('topic_id'),
                    "draft_id": record.get('draft_id'),
                    "generation_request": json.loads(record['generation_request']) if record.get('generation_request') else {},
                    "context_data": json.loads(record['context_data']) if record.get('context_data') else {},
                    "system_prompt": record.get('system_prompt'),
                    "user_prompt": record.get('user_prompt'),
                    "prompt_template": record.get('prompt_template'),
                    "agent_type": record.get('agent_type'),
                    "agent_config": json.loads(record['agent_config']) if record.get('agent_config') else {},
                    "llm_provider": record.get('llm_provider'),
                    "llm_model": record.get('llm_model'),
                    "llm_parameters": json.loads(record['llm_parameters']) if record.get('llm_parameters') else {},
                    "generation_result": json.loads(record['generation_result']) if record.get('generation_result') else None,
                    "generated_content": record.get('generated_content'),
                    "generation_metadata": json.loads(record['generation_metadata']) if record.get('generation_metadata') else None,
                    "status": record['status'],
                    "stage": record['stage'],
                    "error_message": record.get('error_message'),
                    "error_details": json.loads(record['error_details']) if record.get('error_details') else None,
                    "retry_count": record.get('retry_count', 0),
                    "max_retries": record.get('max_retries', 3),
                    "can_retry": record.get('can_retry', False),
                    "retry_with_llm": record.get('retry_with_llm'),
                    "correlation_id": record.get('correlation_id'),
                    "parent_audit_id": record.get('parent_audit_id'),
                    "started_at": record.get('started_at'),
                    "completed_at": record.get('completed_at'),
                    "created_at": record.get('created_at')
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting audit record: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get audit record: {str(e)}") from e
    
    def get_retryable_failures(
        self,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get failed audits that can be retried"""
        try:
            query = """
                SELECT audit_id, user_id, topic_id, error_message, retry_count,
                       llm_provider, llm_model, retry_with_llm, created_at
                FROM blog_generation_audit
                WHERE status = 'failed' AND can_retry = true
            """
            params = {}
            
            if user_id:
                query += " AND user_id = :user_id"
                params["user_id"] = user_id
            
            query += " ORDER BY created_at DESC LIMIT :limit"
            params["limit"] = limit
            
            result = db.execute_query(query, params)
            
            return [
                {
                    "audit_id": r['audit_id'],
                    "user_id": r.get('user_id'),
                    "topic_id": r.get('topic_id'),
                    "error_message": r.get('error_message'),
                    "retry_count": r.get('retry_count', 0),
                    "llm_provider": r.get('llm_provider'),
                    "llm_model": r.get('llm_model'),
                    "retry_with_llm": r.get('retry_with_llm'),
                    "created_at": r.get('created_at')
                }
                for r in result
            ]
            
        except Exception as e:
            logger.error(f"Error getting retryable failures: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get retryable failures: {str(e)}") from e
    
    def create_retry_audit(
        self,
        parent_audit_id: str,
        new_llm_provider: Optional[str] = None,
        new_llm_model: Optional[str] = None
    ) -> str:
        """
        Create a new audit record for retry
        
        Args:
            parent_audit_id: Original audit ID that failed
            new_llm_provider: Optional different LLM provider to use
            new_llm_model: Optional different LLM model to use
        
        Returns:
            New audit ID
        """
        try:
            # Get parent audit record
            parent_audit = self.get_audit_record(parent_audit_id)
            if not parent_audit:
                raise ValidationError(f"Parent audit {parent_audit_id} not found")
            
            # Increment retry count in parent
            query = """
                UPDATE blog_generation_audit
                SET retry_count = retry_count + 1,
                    last_retry_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE audit_id = :audit_id
            """
            db.execute_update(query, {"audit_id": parent_audit_id})
            
            # Create new audit record with same context but different LLM
            new_audit_id = f"audit_{uuid.uuid4().hex[:16]}"
            
            # Use new LLM if specified, otherwise use parent's LLM
            agent_config = parent_audit['agent_config'].copy()
            if new_llm_provider:
                agent_config['llm_provider'] = new_llm_provider
            if new_llm_model:
                agent_config['llm_model'] = new_llm_model
            
            query = """
                INSERT INTO blog_generation_audit
                (audit_id, user_id, topic_id, generation_request, context_data,
                 system_prompt, user_prompt, prompt_template,
                 agent_type, agent_config, llm_provider, llm_model, llm_parameters,
                 status, stage, correlation_id, parent_audit_id, started_at)
                VALUES (:audit_id, :user_id, :topic_id, :generation_request, :context_data,
                        :system_prompt, :user_prompt, :prompt_template,
                        :agent_type, :agent_config, :llm_provider, :llm_model, :llm_parameters,
                        'pending', 'topic_ranked', :correlation_id, :parent_audit_id, CURRENT_TIMESTAMP)
            """
            
            db.execute_update(query, {
                "audit_id": new_audit_id,
                "user_id": parent_audit['user_id'],
                "topic_id": parent_audit['topic_id'],
                "generation_request": json.dumps(parent_audit['generation_request']),
                "context_data": json.dumps(parent_audit['context_data']),
                "system_prompt": parent_audit.get('system_prompt'),
                "user_prompt": parent_audit.get('user_prompt'),
                "prompt_template": parent_audit.get('prompt_template'),
                "agent_type": agent_config.get('agent_type', 'direct_llm'),
                "agent_config": json.dumps(agent_config),
                "llm_provider": agent_config.get('llm_provider', 'openai'),
                "llm_model": agent_config.get('llm_model', 'gpt-4'),
                "llm_parameters": json.dumps(agent_config.get('llm_parameters', {})),
                "correlation_id": parent_audit.get('correlation_id'),
                "parent_audit_id": parent_audit_id
            })
            
            logger.info(f"✅ Created retry audit {new_audit_id} from parent {parent_audit_id}")
            return new_audit_id
            
        except Exception as e:
            logger.error(f"Error creating retry audit: {e}", exc_info=True)
            raise DatabaseError(f"Failed to create retry audit: {str(e)}") from e
    
    def get_audit_for_agent(
        self,
        audit_id: str
    ) -> Dict[str, Any]:
        """
        Get audit data formatted for agent consumption
        Agent can use this to regenerate without needing original context
        
        Returns:
            Dictionary with all data needed for agent to generate blog
        """
        audit = self.get_audit_record(audit_id)
        if not audit:
            raise ValidationError(f"Audit {audit_id} not found")
        
        return {
            "audit_id": audit['audit_id'],
            "context_data": audit['context_data'],
            "generation_request": audit['generation_request'],
            "system_prompt": audit.get('system_prompt'),
            "user_prompt": audit.get('user_prompt'),
            "prompt_template": audit.get('prompt_template'),
            "agent_config": audit['agent_config'],
            "llm_provider": audit['llm_provider'],
            "llm_model": audit['llm_model'],
            "llm_parameters": audit['llm_parameters']
        }

