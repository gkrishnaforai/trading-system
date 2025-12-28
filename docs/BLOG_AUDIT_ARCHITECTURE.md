# Blog Generation Audit Architecture

## Overview

Comprehensive audit system for blog generation following **Event Sourcing** and **Audit Log** patterns. Enables retry/recovery, LLM provider switching, compliance, and debugging.

## Design Principles

### ✅ Industry Standards

1. **Event Sourcing Pattern**
   - Store all events (immutable log)
   - Full audit trail
   - Can replay events

2. **Audit Log Pattern**
   - Immutable records
   - Complete context capture
   - Compliance-ready

3. **Idempotency**
   - Safe to retry
   - Correlation IDs
   - Parent-child relationships

4. **Loose Coupling**
   - Agent doesn't need to know about audit
   - Audit service is separate
   - Agent reads from audit when needed

5. **Separation of Concerns**
   - Audit is separate from business logic
   - Can be enabled/disabled
   - Doesn't affect agent performance

## Database Schema

### `blog_generation_audit` Table

**Purpose**: Complete audit trail for every blog generation attempt

**Key Fields**:

#### Input (What We Give to Agent)
- `generation_request` (JSON) - Complete request
- `context_data` (JSON) - Full structured context
- `system_prompt` (TEXT) - System prompt used
- `user_prompt` (TEXT) - User prompt/instruction
- `prompt_template` (TEXT) - Template for reproducibility

#### Agent Configuration
- `agent_type` - 'openai', 'anthropic', 'langgraph', 'n8n', etc.
- `agent_config` (JSON) - Agent-specific config
- `llm_provider` - Provider name
- `llm_model` - Model used
- `llm_parameters` (JSON) - Temperature, max_tokens, etc.

#### Output (What Agent Generated)
- `generation_result` (JSON) - Full agent response
- `generated_content` (TEXT) - Actual blog content
- `generation_metadata` (JSON) - Tokens, latency, cost

#### Status & Lifecycle
- `status` - pending, in_progress, success, failed, retrying, cancelled
- `stage` - topic_ranked, context_built, agent_invoked, content_generated, etc.

#### Error Handling
- `error_message` - Error message
- `error_details` (JSON) - Stack trace, error codes
- `retry_count` - Number of retries
- `can_retry` - Whether retry is possible

#### Retry/Recovery
- `retry_with_llm` - Different LLM to try
- `recovery_data` (JSON) - Data for recovery
- `parent_audit_id` - Links to previous attempt

#### Correlation
- `correlation_id` - For tracing across services
- `parent_audit_id` - For retry chains

## Architecture Flow

### Normal Flow

```
1. BlogGenerator creates audit record
   ↓
2. BlogGenerator builds context
   ↓
3. BlogGenerator updates audit (context_built)
   ↓
4. BlogGenerator invokes agent
   ↓
5. BlogGenerator updates audit (agent_invoked, prompts)
   ↓
6. Agent generates content
   ↓
7. BlogGenerator updates audit (content_generated, result)
   ↓
8. BlogGenerator creates draft
   ↓
9. BlogGenerator updates audit (draft_created, success)
```

### Retry Flow

```
1. BlogGenerator detects failure
   ↓
2. BlogAuditService.record_generation_failure()
   ↓
3. BlogGenerator checks can_retry
   ↓
4. BlogAuditService.create_retry_audit()
   ↓
5. New audit record created (parent_audit_id links to original)
   ↓
6. BlogGenerator retries with new audit_id
   ↓
7. (Can use different LLM provider)
```

### Agent Reading from Audit

```
1. Agent needs to regenerate
   ↓
2. Agent calls BlogAuditService.get_audit_for_agent(audit_id)
   ↓
3. Gets all context, prompts, config
   ↓
4. Agent can regenerate without original context
   ↓
5. (Loosely coupled - agent doesn't need BlogGenerator)
```

## Service: BlogAuditService

**Location**: `python-worker/app/services/blog_audit_service.py`

**Responsibilities**:
- Create audit records
- Update audit stages
- Record agent invocations
- Record generation results
- Record failures
- Get audit records
- Create retry audits
- Get retryable failures

**Key Methods**:

```python
# Create audit record
audit_id = audit_service.create_audit_record(
    user_id, topic_id, generation_request, context_data, agent_config
)

# Update stage
audit_service.update_audit_stage(audit_id, 'context_built', 'in_progress')

# Record agent invocation
audit_service.record_agent_invocation(
    audit_id, system_prompt, user_prompt, prompt_template
)

# Record result
audit_service.record_generation_result(
    audit_id, generation_result, generated_content, metadata
)

# Record failure
audit_service.record_generation_failure(
    audit_id, error_message, error_details, can_retry=True
)

# Get audit for agent (loosely coupled)
audit_data = audit_service.get_audit_for_agent(audit_id)

# Create retry
new_audit_id = audit_service.create_retry_audit(
    parent_audit_id, new_llm_provider='anthropic'
)
```

## Integration with BlogGenerator

### BlogGenerator Uses Audit Service

```python
class BlogGenerator:
    def __init__(self):
        self.audit_service = BlogAuditService()
    
    def generate_blog(self, topic_id, user_id):
        # 1. Create audit record
        audit_id = self.audit_service.create_audit_record(
            user_id, topic_id, generation_request, context_data, agent_config
        )
        
        try:
            # 2. Build context
            context = self.context_builder.build(topic_id)
            self.audit_service.update_audit_stage(
                audit_id, 'context_built', 'in_progress'
            )
            
            # 3. Invoke agent
            self.audit_service.record_agent_invocation(
                audit_id, system_prompt, user_prompt
            )
            
            result = self.agent.execute('generate_blog', context)
            
            # 4. Record result
            self.audit_service.record_generation_result(
                audit_id, result, result['content'], result['metadata']
            )
            
            return result
            
        except Exception as e:
            # 5. Record failure
            self.audit_service.record_generation_failure(
                audit_id, str(e), {'exception': type(e).__name__}
            )
            raise
```

## Integration with BlogAgent

### Agent Can Read from Audit (Loosely Coupled)

```python
class BlogAgent(BaseAgent):
    def execute(self, task, context, audit_id=None, **kwargs):
        # If audit_id provided, agent can read from audit
        if audit_id:
            audit_service = BlogAuditService()
            audit_data = audit_service.get_audit_for_agent(audit_id)
            
            # Use audit data instead of context
            context = audit_data['context_data']
            system_prompt = audit_data['system_prompt']
            user_prompt = audit_data['user_prompt']
            agent_config = audit_data['agent_config']
        
        # Generate blog...
        return result
```

**Benefits**:
- Agent doesn't need BlogGenerator
- Can regenerate from audit alone
- Loosely coupled
- Can be called independently

## Retry/Recovery Flow

### Automatic Retry

```python
# Get failed audits
failures = audit_service.get_retryable_failures(user_id)

for failure in failures:
    # Create retry with different LLM
    new_audit_id = audit_service.create_retry_audit(
        failure['audit_id'],
        new_llm_provider='anthropic',  # Try different provider
        new_llm_model='claude-3-opus'
    )
    
    # Retry generation
    blog_generator.generate_blog_from_audit(new_audit_id)
```

### Manual Retry via API

```python
# API endpoint
@app.post("/api/v1/blog/retry/{audit_id}")
async def retry_blog_generation(
    audit_id: str,
    new_llm_provider: Optional[str] = None
):
    # Create retry audit
    new_audit_id = audit_service.create_retry_audit(
        audit_id, new_llm_provider=new_llm_provider
    )
    
    # Regenerate
    blog = blog_generator.generate_blog_from_audit(new_audit_id)
    
    return {"audit_id": new_audit_id, "blog": blog}
```

## Benefits

### ✅ Full Audit Trail
- Every generation attempt recorded
- Complete context captured
- Compliance-ready

### ✅ Retry/Recovery
- Can retry failed generations
- Can switch LLM providers
- Can regenerate from audit alone

### ✅ Debugging
- See exactly what was sent to agent
- See exactly what agent returned
- Full error details

### ✅ LLM Provider Switching
- Try different provider on failure
- A/B test different models
- Cost optimization

### ✅ Loose Coupling
- Agent doesn't need to know about audit
- Audit is separate service
- Can be enabled/disabled

### ✅ Performance
- Audit is async (doesn't block)
- Indexed for fast queries
- Denormalized log table for quick access

## Usage Examples

### Generate Blog with Audit

```python
# BlogGenerator automatically creates audit
blog = blog_generator.generate_blog(topic_id, user_id)

# Audit record created automatically
# All stages recorded
# Full context stored
```

### Retry Failed Generation

```python
# Get failed audit
audit = audit_service.get_audit_record(audit_id)

# Create retry with different LLM
new_audit_id = audit_service.create_retry_audit(
    audit_id,
    new_llm_provider='anthropic',
    new_llm_model='claude-3-opus'
)

# Regenerate from audit
blog = blog_generator.generate_blog_from_audit(new_audit_id)
```

### Agent Reads from Audit

```python
# Agent can regenerate without BlogGenerator
audit_data = audit_service.get_audit_for_agent(audit_id)

# Agent uses audit data
result = blog_agent.execute(
    'generate_blog',
    context=audit_data['context_data'],
    system_prompt=audit_data['system_prompt'],
    user_prompt=audit_data['user_prompt']
)
```

### Query Audit Trail

```python
# Get all generations for user
query = """
    SELECT * FROM blog_generation_audit
    WHERE user_id = :user_id
    ORDER BY created_at DESC
"""

# Get retryable failures
failures = audit_service.get_retryable_failures(user_id)

# Get audit chain (retries)
query = """
    SELECT * FROM blog_generation_audit
    WHERE parent_audit_id = :parent_id
    OR audit_id = :parent_id
    ORDER BY created_at ASC
"""
```

## Summary

✅ **Complete Audit Trail** - Everything stored
✅ **Retry/Recovery** - Can retry with different LLM
✅ **Loose Coupling** - Agent independent of audit
✅ **Industry Standards** - Event Sourcing + Audit Log
✅ **Compliance Ready** - Full audit trail
✅ **Debugging** - See exactly what happened
✅ **LLM Switching** - Easy to try different providers

The audit table is the **source of truth** for blog generation. Agents can read from it, retries can use it, and it provides full transparency.

