"""
Workflow Recovery Mechanisms
Industry Standard: Retry with backoff, checkpoints, dead letter queue
"""
import logging
import json
import time
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.database import db
from app.exceptions import ValidationError

logger = logging.getLogger(__name__)


class RetryPolicy:
    """
    Retry policy with exponential backoff
    Industry Standard: Exponential backoff for transient failures
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: int = 60,  # seconds
        max_delay: int = 3600,  # 1 hour
        backoff_multiplier: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
    
    def should_retry(self, error: Exception, retry_count: int) -> bool:
        """
        Determine if error is retryable
        
        Industry Standard:
        - Don't retry validation failures (data quality issues)
        - Retry transient errors (network, rate limits, timeouts)
        """
        # Don't retry validation failures (data quality issues)
        if isinstance(error, ValidationError):
            return False
        
        # Don't retry if max retries reached
        if retry_count >= self.max_retries:
            return False
        
        # Retry transient errors
        error_name = type(error).__name__
        retryable_errors = [
            'ConnectionError',
            'TimeoutError',
            'RateLimitError',
            'HTTPError',
            'RequestException'
        ]
        
        if any(retryable in error_name for retryable in retryable_errors):
            return True
        
        # Check error message for transient indicators
        error_msg = str(error).lower()
        transient_indicators = ['timeout', 'connection', 'rate limit', '503', '502', '429']
        if any(indicator in error_msg for indicator in transient_indicators):
            return True
        
        return False
    
    def get_delay(self, retry_count: int) -> int:
        """Calculate delay for retry (exponential backoff)"""
        delay = int(self.initial_delay * (self.backoff_multiplier ** retry_count))
        return min(delay, self.max_delay)
    
    def wait_for_retry(self, retry_count: int):
        """Wait for retry delay"""
        delay = self.get_delay(retry_count)
        logger.info(f"Waiting {delay} seconds before retry (attempt {retry_count + 1}/{self.max_retries})")
        time.sleep(delay)


class WorkflowCheckpoint:
    """
    Workflow checkpoint for recovery
    Industry Standard: Save state for resume capability
    """
    
    def save_checkpoint(
        self,
        workflow_id: str,
        stage: str,
        state: Dict[str, Any]
    ):
        """Save checkpoint for recovery"""
        try:
            checkpoint_id = str(uuid.uuid4())
            db.execute_update(
                """
                INSERT INTO workflow_checkpoints
                (checkpoint_id, workflow_id, stage, state_json, timestamp)
                VALUES (:checkpoint_id, :workflow_id, :stage, :state_json, CURRENT_TIMESTAMP)
                """,
                {
                    "checkpoint_id": checkpoint_id,
                    "workflow_id": workflow_id,
                    "stage": stage,
                    "state_json": json.dumps(state)
                }
            )
            logger.info(f"✅ Saved checkpoint for workflow {workflow_id} at stage {stage}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}", exc_info=True)
    
    def load_checkpoint(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Load last checkpoint for recovery"""
        try:
            result = db.execute_query(
                """
                SELECT stage, state_json, timestamp
                FROM workflow_checkpoints
                WHERE workflow_id = :workflow_id
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                {"workflow_id": workflow_id}
            )
            if result:
                return {
                    "stage": result[0]['stage'],
                    "state": json.loads(result[0]['state_json']),
                    "timestamp": result[0]['timestamp']
                }
            return None
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}", exc_info=True)
            return None
    
    def clear_checkpoints(self, workflow_id: str):
        """Clear checkpoints for completed workflow"""
        try:
            db.execute_update(
                "DELETE FROM workflow_checkpoints WHERE workflow_id = :workflow_id",
                {"workflow_id": workflow_id}
            )
            logger.debug(f"Cleared checkpoints for workflow {workflow_id}")
        except Exception as e:
            logger.warning(f"Failed to clear checkpoints: {e}")


class DeadLetterQueue:
    """
    Dead Letter Queue for failed items
    Industry Standard: Store failed items for manual review
    """
    
    def add_failed_item(
        self,
        workflow_id: str,
        symbol: str,
        stage: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ):
        """Add failed item to DLQ"""
        try:
            dlq_id = str(uuid.uuid4())
            error_type = self._classify_error(error)
            
            db.execute_update(
                """
                INSERT INTO workflow_dlq
                (dlq_id, workflow_id, symbol, stage, error_message, error_type, context_json, created_at)
                VALUES (:dlq_id, :workflow_id, :symbol, :stage, :error_message, :error_type, :context_json, CURRENT_TIMESTAMP)
                """,
                {
                    "dlq_id": dlq_id,
                    "workflow_id": workflow_id,
                    "symbol": symbol,
                    "stage": stage,
                    "error_message": str(error),
                    "error_type": error_type,
                    "context_json": json.dumps(context or {})
                }
            )
            logger.warning(f"📋 Added {symbol} to DLQ (stage: {stage}, error: {error_type})")
        except Exception as e:
            logger.error(f"Failed to add item to DLQ: {e}", exc_info=True)
    
    def _classify_error(self, error: Exception) -> str:
        """Classify error type"""
        error_name = type(error).__name__
        
        if 'Validation' in error_name:
            return 'validation'
        elif 'Gate' in error_name:
            return 'gate_failed'
        elif any(x in error_name for x in ['Connection', 'Timeout', 'RateLimit']):
            return 'transient'
        else:
            return 'computation'
    
    def get_unresolved_items(
        self,
        limit: int = 100,
        stage: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get unresolved items from DLQ"""
        try:
            query = """
                SELECT * FROM workflow_dlq
                WHERE resolved = 0
            """
            params = {}
            
            if stage:
                query += " AND stage = :stage"
                params['stage'] = stage
            
            query += " ORDER BY created_at DESC LIMIT :limit"
            params['limit'] = limit
            
            return db.execute_query(query, params)
        except Exception as e:
            logger.error(f"Failed to get DLQ items: {e}", exc_info=True)
            return []
    
    def resolve_item(self, dlq_id: str, resolved_by: str = "system"):
        """Mark DLQ item as resolved"""
        try:
            db.execute_update(
                """
                UPDATE workflow_dlq
                SET resolved = 1, resolved_at = CURRENT_TIMESTAMP, resolved_by = :resolved_by
                WHERE dlq_id = :dlq_id
                """,
                {"dlq_id": dlq_id, "resolved_by": resolved_by}
            )
            logger.info(f"✅ Resolved DLQ item {dlq_id}")
        except Exception as e:
            logger.error(f"Failed to resolve DLQ item: {e}", exc_info=True)

