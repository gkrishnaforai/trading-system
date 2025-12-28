#!/usr/bin/env python3
"""
Verify Blog Generation Audit Table
Checks that audit table is populated correctly with all data
"""
import sys
import os
from pathlib import Path

# Add python-worker to path
sys.path.insert(0, str(Path(__file__).parent.parent / "python-worker"))

from app.database import init_database, db
from app.services.blog_topic_ranker import BlogTopicRanker
from app.services.blog_context_builder import BlogContextBuilder
from app.services.blog_generator import BlogGenerator
from app.services.blog_audit_service import BlogAuditService
import json
import uuid
from datetime import datetime

def verify_audit_table():
    """Verify audit table is populated correctly"""
    print("\n" + "="*80)
    print("BLOG GENERATION AUDIT TABLE VERIFICATION")
    print("="*80)
    
    init_database()
    
    # Create test user
    test_user_id = f"test_user_{int(datetime.now().timestamp() * 1000000)}"
    
    # Create test portfolio
    portfolio_id = f"portfolio_{test_user_id}_{str(uuid.uuid4())[:8]}"
    query = """
        INSERT OR REPLACE INTO portfolios (portfolio_id, user_id, portfolio_name)
        VALUES (:portfolio_id, :user_id, :portfolio_name)
    """
    db.execute_update(query, {
        "portfolio_id": portfolio_id,
        "user_id": test_user_id,
        "portfolio_name": "Test Portfolio"
    })
    
    # Add holding for AAPL
    holding_id = f"holding_{portfolio_id}_AAPL_{int(datetime.now().timestamp() * 1000000)}"
    query = """
        INSERT OR REPLACE INTO holdings
        (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, position_type, purchase_date)
        VALUES (:holding_id, :portfolio_id, :symbol, :quantity, :price, :position_type, :purchase_date)
    """
    db.execute_update(query, {
        "holding_id": holding_id,
        "portfolio_id": portfolio_id,
        "symbol": "AAPL",
        "quantity": 10.0,
        "price": 100.0,
        "position_type": "long",
        "purchase_date": datetime.now().date()
    })
    
    print(f"\n✅ Created test portfolio for user {test_user_id}")
    
    # Check if we have data for AAPL
    query = """
        SELECT COUNT(*) as count FROM aggregated_indicators
        WHERE stock_symbol = 'AAPL'
    """
    result = db.execute_query(query)
    has_data = result[0].get('count', 0) > 0 if result else False
    
    if not has_data:
        print("\n⚠️  No indicators found for AAPL")
        print("   Please run data refresh first:")
        print("   curl -X POST http://localhost:8001/api/v1/refresh-data \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -d '{\"symbol\": \"AAPL\", \"data_types\": [\"price_historical\", \"indicators\"]}'")
        return
    
    print("✅ Found indicators for AAPL")
    
    # Step 1: Rank topics
    print("\n📊 Step 1: Ranking topics...")
    topic_ranker = BlogTopicRanker()
    topics = topic_ranker.rank_topics_for_user(test_user_id, limit=1, min_score=30.0)
    
    if not topics:
        print("⚠️  No topics ranked")
        return
    
    topic_id = topics[0]['topic_id']
    print(f"✅ Ranked topic: {topic_id}")
    print(f"   Symbol: {topics[0]['symbol']}")
    print(f"   Type: {topics[0]['topic_type']}")
    print(f"   Score: {topics[0]['score']:.1f}")
    
    # Step 2: Build context
    print("\n📊 Step 2: Building context...")
    context_builder = BlogContextBuilder()
    context = context_builder.build_context(topic_id, test_user_id)
    
    print(f"✅ Built context")
    print(f"   Symbol: {context['topic']['symbol']}")
    print(f"   Signal: {context['signal_summary'].get('signal', 'N/A')}")
    print(f"   Trend: {context['signal_summary'].get('trend', 'N/A')}")
    
    # Step 3: Generate blog
    print("\n📊 Step 3: Generating blog (with audit)...")
    blog_generator = BlogGenerator()
    
    result = blog_generator.generate_blog(
        topic_id=topic_id,
        user_id=test_user_id,
        llm_provider="openai",
        llm_model="gpt-4"
    )
    
    audit_id = result['audit_id']
    draft_id = result['draft_id']
    
    print(f"✅ Generated blog")
    print(f"   Audit ID: {audit_id}")
    print(f"   Draft ID: {draft_id}")
    
    # Step 4: Verify audit table
    print("\n📊 Step 4: Verifying audit table...")
    audit_service = BlogAuditService()
    audit = audit_service.get_audit_record(audit_id)
    
    if not audit:
        print("❌ Audit record not found!")
        return
    
    print("\n" + "="*80)
    print("AUDIT TABLE VERIFICATION")
    print("="*80)
    
    # Verify input fields
    print("\n📥 INPUT DATA:")
    checks = {
        "generation_request": bool(audit.get('generation_request')),
        "context_data": bool(audit.get('context_data')),
        "system_prompt": len(audit.get('system_prompt', '') or '') > 0,
        "user_prompt": len(audit.get('user_prompt', '') or '') > 0,
        "prompt_template": bool(audit.get('prompt_template'))
    }
    
    for field, is_populated in checks.items():
        status = "✅" if is_populated else "❌"
        print(f"  {status} {field}: {is_populated}")
    
    all_input_ok = all(checks.values())
    
    # Verify config fields
    print("\n⚙️  AGENT CONFIG:")
    config_checks = {
        "agent_type": bool(audit.get('agent_type')),
        "agent_config": bool(audit.get('agent_config')),
        "llm_provider": audit.get('llm_provider') == "openai",
        "llm_model": audit.get('llm_model') == "gpt-4",
        "llm_parameters": bool(audit.get('llm_parameters'))
    }
    
    for field, is_populated in config_checks.items():
        status = "✅" if is_populated else "❌"
        print(f"  {status} {field}: {is_populated}")
    
    all_config_ok = all(config_checks.values())
    
    # Verify output fields
    print("\n📤 OUTPUT DATA:")
    output_checks = {
        "generation_result": bool(audit.get('generation_result')),
        "generated_content": len(audit.get('generated_content', '') or '') > 0,
        "generation_metadata": bool(audit.get('generation_metadata'))
    }
    
    for field, is_populated in output_checks.items():
        status = "✅" if is_populated else "❌"
        print(f"  {status} {field}: {is_populated}")
    
    all_output_ok = all(output_checks.values())
    
    # Verify status fields
    print("\n📊 STATUS:")
    status_checks = {
        "status": bool(audit.get('status')),
        "stage": bool(audit.get('stage')),
        "started_at": bool(audit.get('started_at')),
        "created_at": bool(audit.get('created_at'))
    }
    
    for field, is_populated in status_checks.items():
        status = "✅" if is_populated else "❌"
        print(f"  {status} {field}: {is_populated}")
    
    all_status_ok = all(status_checks.values())
    
    # Verify context structure
    print("\n📋 CONTEXT STRUCTURE:")
    if audit.get('context_data'):
        context = audit['context_data']
        context_checks = {
            "topic": bool(context.get('topic')),
            "signal_summary": bool(context.get('signal_summary')),
            "technical_context": bool(context.get('technical_context')),
            "risk_context": bool(context.get('risk_context')),
            "allowed_assumptions": bool(context.get('allowed_assumptions'))
        }
        
        for field, is_populated in context_checks.items():
            status = "✅" if is_populated else "❌"
            print(f"  {status} {field}: {is_populated}")
        
        all_context_ok = all(context_checks.values())
    else:
        all_context_ok = False
        print("  ❌ No context_data")
    
    # Summary
    print("\n" + "="*80)
    print("VERIFICATION SUMMARY")
    print("="*80)
    
    all_ok = all_input_ok and all_config_ok and all_output_ok and all_status_ok and all_context_ok
    
    if all_ok:
        print("✅ ALL CHECKS PASSED - Audit table is fully populated!")
    else:
        print("⚠️  Some checks failed:")
        if not all_input_ok:
            print("  - Input data incomplete")
        if not all_config_ok:
            print("  - Agent config incomplete")
        if not all_output_ok:
            print("  - Output data incomplete")
        if not all_status_ok:
            print("  - Status fields incomplete")
        if not all_context_ok:
            print("  - Context structure incomplete")
    
    # Show sample data
    print("\n📄 SAMPLE DATA:")
    print(f"  Audit ID: {audit_id}")
    print(f"  Status: {audit.get('status')}")
    print(f"  Stage: {audit.get('stage')}")
    print(f"  LLM Provider: {audit.get('llm_provider')}")
    print(f"  LLM Model: {audit.get('llm_model')}")
    if audit.get('context_data'):
        print(f"  Context Symbol: {audit['context_data'].get('topic', {}).get('symbol', 'N/A')}")
        print(f"  Context Signal: {audit['context_data'].get('signal_summary', {}).get('signal', 'N/A')}")
    print(f"  System Prompt Length: {len(audit.get('system_prompt', '') or '')} chars")
    print(f"  User Prompt Length: {len(audit.get('user_prompt', '') or '')} chars")
    print(f"  Generated Content Length: {len(audit.get('generated_content', '') or '')} chars")
    
    print("\n" + "="*80)
    
    # Query audit table directly
    print("\n📊 DIRECT DATABASE QUERY:")
    query = """
        SELECT 
            audit_id,
            status,
            stage,
            llm_provider,
            llm_model,
            length(generation_request) as req_len,
            length(context_data) as ctx_len,
            length(system_prompt) as sys_prompt_len,
            length(user_prompt) as user_prompt_len,
            length(generated_content) as content_len
        FROM blog_generation_audit
        WHERE audit_id = :audit_id
    """
    db_result = db.execute_query(query, {"audit_id": audit_id})
    
    if db_result:
        r = db_result[0]
        print(f"  ✅ Audit record found in database")
        print(f"     Request JSON: {r.get('req_len', 0)} chars")
        print(f"     Context JSON: {r.get('ctx_len', 0)} chars")
        print(f"     System Prompt: {r.get('sys_prompt_len', 0)} chars")
        print(f"     User Prompt: {r.get('user_prompt_len', 0)} chars")
        print(f"     Generated Content: {r.get('content_len', 0)} chars")
    
    print("\n" + "="*80)
    print("✅ VERIFICATION COMPLETE")
    print("="*80)

if __name__ == "__main__":
    try:
        verify_audit_table()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

