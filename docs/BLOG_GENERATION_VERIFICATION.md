# Blog Generation Audit Verification Guide

## Overview

This guide shows how to verify that the audit table is populated correctly with all data given to the AI agent.

## What Gets Stored in Audit Table

### ✅ Input Data (What We Give to Agent)

1. **`generation_request`** (JSON)
   - Complete generation request
   - Topic ID, user ID, agent config

2. **`context_data`** (JSON)
   - Full structured context
   - Topic, signal summary, technical context, risk context, user relevance

3. **`system_prompt`** (TEXT)
   - Locked system prompt
   - Instructions for LLM

4. **`user_prompt`** (TEXT)
   - User prompt built from context
   - Specific instructions for this blog

5. **`prompt_template`** (TEXT)
   - Template identifier for reproducibility

### ✅ Agent Configuration

1. **`agent_type`** - 'openai', 'anthropic', 'langgraph', 'n8n', etc.
2. **`agent_config`** (JSON) - Complete agent configuration
3. **`llm_provider`** - Provider name
4. **`llm_model`** - Model used
5. **`llm_parameters`** (JSON) - Temperature, max_tokens, etc.

### ✅ Output Data (What Agent Generated)

1. **`generation_result`** (JSON) - Full agent response
2. **`generated_content`** (TEXT) - Actual blog content
3. **`generation_metadata`** (JSON) - Tokens, latency, cost

### ✅ Status & Lifecycle

1. **`status`** - pending, in_progress, success, failed, retrying, cancelled
2. **`stage`** - topic_ranked, context_built, agent_invoked, content_generated, draft_created

### ✅ Error Handling

1. **`error_message`** - Error message
2. **`error_details`** (JSON) - Stack trace, error codes
3. **`retry_count`** - Number of retries
4. **`can_retry`** - Whether retry is possible

## Verification Queries

### Check Audit Table Structure

```sql
-- View audit table schema
.schema blog_generation_audit
```

### View All Audit Records

```sql
SELECT 
    audit_id,
    user_id,
    topic_id,
    draft_id,
    status,
    stage,
    llm_provider,
    llm_model,
    created_at
FROM blog_generation_audit
ORDER BY created_at DESC
LIMIT 10;
```

### Verify Complete Audit Record

```sql
SELECT 
    audit_id,
    user_id,
    topic_id,
    -- Input
    json_extract(generation_request, '$.topic_id') as req_topic_id,
    json_extract(context_data, '$.topic.symbol') as context_symbol,
    length(system_prompt) as system_prompt_length,
    length(user_prompt) as user_prompt_length,
    -- Config
    llm_provider,
    llm_model,
    -- Output
    length(generated_content) as content_length,
    -- Status
    status,
    stage,
    error_message,
    retry_count,
    can_retry
FROM blog_generation_audit
WHERE audit_id = 'YOUR_AUDIT_ID';
```

### Verify Context Data Structure

```sql
SELECT 
    audit_id,
    json_extract(context_data, '$.topic.symbol') as symbol,
    json_extract(context_data, '$.signal_summary.signal') as signal,
    json_extract(context_data, '$.signal_summary.trend') as trend,
    json_extract(context_data, '$.technical_context.price_vs_200ma') as price_vs_200ma,
    json_extract(context_data, '$.risk_context.overextension') as overextension
FROM blog_generation_audit
WHERE audit_id = 'YOUR_AUDIT_ID';
```

### Check Retry Chains

```sql
SELECT 
    parent.audit_id as parent_id,
    parent.llm_provider as parent_provider,
    parent.status as parent_status,
    child.audit_id as retry_id,
    child.llm_provider as retry_provider,
    child.status as retry_status
FROM blog_generation_audit parent
LEFT JOIN blog_generation_audit child ON child.parent_audit_id = parent.audit_id
WHERE parent.parent_audit_id IS NULL
ORDER BY parent.created_at DESC
LIMIT 10;
```

## Python Verification Script

```python
from app.database import init_database, db
from app.services.blog_audit_service import BlogAuditService
import json

init_database()
audit_service = BlogAuditService()

# Get audit record
audit_id = "YOUR_AUDIT_ID"
audit = audit_service.get_audit_record(audit_id)

if audit:
    print("\n" + "="*80)
    print(f"AUDIT RECORD: {audit_id}")
    print("="*80)
    
    # Verify input
    print("\n📥 INPUT DATA:")
    print(f"  Generation Request: {bool(audit['generation_request'])}")
    print(f"  Context Data: {bool(audit['context_data'])}")
    print(f"  System Prompt: {len(audit.get('system_prompt', '') or '')} chars")
    print(f"  User Prompt: {len(audit.get('user_prompt', '') or '')} chars")
    
    # Verify config
    print("\n⚙️  AGENT CONFIG:")
    print(f"  LLM Provider: {audit['llm_provider']}")
    print(f"  LLM Model: {audit['llm_model']}")
    print(f"  Agent Type: {audit.get('agent_type', 'N/A')}")
    
    # Verify output
    print("\n📤 OUTPUT DATA:")
    print(f"  Generated Content: {len(audit.get('generated_content', '') or '')} chars")
    print(f"  Generation Result: {bool(audit.get('generation_result'))}")
    print(f"  Generation Metadata: {bool(audit.get('generation_metadata'))}")
    
    # Verify status
    print("\n📊 STATUS:")
    print(f"  Status: {audit['status']}")
    print(f"  Stage: {audit['stage']}")
    print(f"  Retry Count: {audit.get('retry_count', 0)}")
    print(f"  Can Retry: {audit.get('can_retry', False)}")
    
    # Verify context structure
    if audit['context_data']:
        context = audit['context_data']
        print("\n📋 CONTEXT STRUCTURE:")
        print(f"  Topic Symbol: {context.get('topic', {}).get('symbol', 'N/A')}")
        print(f"  Signal: {context.get('signal_summary', {}).get('signal', 'N/A')}")
        print(f"  Trend: {context.get('signal_summary', {}).get('trend', 'N/A')}")
        print(f"  Technical Context: {bool(context.get('technical_context'))}")
        print(f"  Risk Context: {bool(context.get('risk_context'))}")
        print(f"  User Relevance: {bool(context.get('user_relevance'))}")
    
    print("\n" + "="*80)
else:
    print(f"❌ Audit record {audit_id} not found")
```

## Test Commands

### Run All Blog Generation Tests

```bash
cd python-worker
python -m pytest tests/test_blog_generation_audit.py -v
```

### Run Specific Audit Tests

```bash
# Test audit table population
python -m pytest tests/test_blog_generation_audit.py::TestBlogGenerationAudit::test_generate_blog_with_audit -v -s

# Test audit completeness
python -m pytest tests/test_blog_generation_audit.py::TestBlogGenerationAudit::test_audit_table_completeness -v -s

# Test audit for agent (loosely coupled)
python -m pytest tests/test_blog_generation_audit.py::TestBlogGenerationAudit::test_get_audit_for_agent -v -s

# Test retry
python -m pytest tests/test_blog_generation_audit.py::TestBlogGenerationAudit::test_retry_audit_creation -v -s
```

## Expected Test Results

### ✅ Successful Test Run

```
test_rank_topics_for_user ... ✅ PASSED
test_get_top_topics ... ✅ PASSED
test_build_context ... ✅ PASSED
test_generate_blog_with_audit ... ✅ PASSED
test_audit_table_completeness ... ✅ PASSED
test_audit_stage_progression ... ✅ PASSED
test_get_audit_for_agent ... ✅ PASSED
test_retry_audit_creation ... ✅ PASSED
test_full_blog_generation_workflow ... ✅ PASSED

9 passed in X.XXs
```

### ✅ Audit Table Verification

After running tests, verify audit table:

```sql
-- Count audit records
SELECT COUNT(*) FROM blog_generation_audit;

-- Check all fields are populated
SELECT 
    COUNT(*) as total,
    COUNT(generation_request) as has_request,
    COUNT(context_data) as has_context,
    COUNT(system_prompt) as has_system_prompt,
    COUNT(user_prompt) as has_user_prompt,
    COUNT(llm_provider) as has_provider,
    COUNT(llm_model) as has_model,
    COUNT(status) as has_status,
    COUNT(stage) as has_stage
FROM blog_generation_audit;
```

All counts should match (all fields populated).

## Summary

✅ **Audit table stores everything**:
- ✅ All input (context, prompts, config)
- ✅ All output (result, content, metadata)
- ✅ All status (stages, errors, retries)

✅ **Can regenerate from audit**:
- ✅ Agent can read from audit
- ✅ Can retry with different LLM
- ✅ Full context preserved

✅ **Loosely coupled**:
- ✅ Agent doesn't need BlogGenerator
- ✅ Audit is separate service
- ✅ Can be enabled/disabled

The audit table is the **source of truth** for blog generation.

