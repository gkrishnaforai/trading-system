"""
Integration Tests for Blog Generation Audit System
Tests: Topic ranking, context building, blog generation, audit table population
Industry Standard: Real database, no mocks for audit, fail-fast, DRY, SOLID
"""
import unittest
import sys
import os
import uuid
import json
from datetime import datetime, date
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import init_database, db
from app.services.blog_topic_ranker import BlogTopicRanker
from app.services.blog_context_builder import BlogContextBuilder
from app.services.blog_generator import BlogGenerator
from app.services.blog_audit_service import BlogAuditService
from app.config import settings


class TestBlogGenerationAudit(unittest.TestCase):
    """
    Comprehensive integration tests for blog generation audit system
    Tests with real data (AAPL, GOOGL, NVDA)
    Verifies audit table is populated correctly
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("BLOG GENERATION AUDIT INTEGRATION TESTS")
        print("="*80)
        
        # Ensure database directory exists
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database (runs migrations)
        init_database()
        
        cls.topic_ranker = BlogTopicRanker()
        cls.context_builder = BlogContextBuilder()
        cls.blog_generator = BlogGenerator()
        cls.audit_service = BlogAuditService()
        
        # Test user and symbols
        cls.test_user_id = f"test_user_{int(datetime.now().timestamp() * 1000000)}"
        cls.test_symbols = ["AAPL", "GOOGL", "NVDA"]
        
        print(f"\n📊 Test user: {cls.test_user_id}")
        print(f"📊 Test symbols: {', '.join(cls.test_symbols)}")
        print(f"📅 Test date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.topic_ranker = self.__class__.topic_ranker
        self.context_builder = self.__class__.context_builder
        self.blog_generator = self.__class__.blog_generator
        self.audit_service = self.__class__.audit_service
        self.test_user_id = self.__class__.test_user_id
        self.test_symbols = self.__class__.test_symbols
    
    def _create_test_portfolio(self):
        """Create test portfolio with holdings"""
        try:
            portfolio_id = f"portfolio_{self.test_user_id}_{str(uuid.uuid4())[:8]}"
            query = """
                INSERT OR REPLACE INTO portfolios (portfolio_id, user_id, portfolio_name)
                VALUES (:portfolio_id, :user_id, :portfolio_name)
            """
            db.execute_update(query, {
                "portfolio_id": portfolio_id,
                "user_id": self.test_user_id,
                "portfolio_name": "Test Portfolio"
            })
            
            # Add holdings
            for symbol in self.test_symbols:
                holding_id = f"holding_{portfolio_id}_{symbol}_{int(datetime.now().timestamp() * 1000000)}"
                query = """
                    INSERT OR REPLACE INTO holdings
                    (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, position_type, purchase_date)
                    VALUES (:holding_id, :portfolio_id, :symbol, :quantity, :price, :position_type, :purchase_date)
                """
                db.execute_update(query, {
                    "holding_id": holding_id,
                    "portfolio_id": portfolio_id,
                    "symbol": symbol,
                    "quantity": 10.0,
                    "price": 100.0,
                    "position_type": "long",
                    "purchase_date": date.today()
                })
            
            return portfolio_id
            
        except Exception as e:
            print(f"⚠️  Error creating test portfolio: {e}")
            return None
    
    def _ensure_data_for_symbol(self, symbol: str):
        """Ensure we have data for a symbol"""
        try:
            # Check if we have indicators
            query = """
                SELECT COUNT(*) as count FROM aggregated_indicators
                WHERE stock_symbol = :symbol
            """
            result = db.execute_query(query, {"symbol": symbol})
            
            if result and result[0].get('count', 0) == 0:
                print(f"⚠️  No indicators for {symbol}, skipping...")
                return False
            
            return True
            
        except Exception:
            return False
    
    # ==================== Topic Ranking Tests ====================
    
    def test_rank_topics_for_user(self):
        """Test ranking topics for a user"""
        print("\n📊 Testing topic ranking for user...")
        
        try:
            # Create test portfolio
            portfolio_id = self._create_test_portfolio()
            self.assertIsNotNone(portfolio_id, "Should create portfolio")
            
            # Rank topics
            topics = self.topic_ranker.rank_topics_for_user(
                self.test_user_id,
                limit=5,
                min_score=30.0
            )
            
            self.assertIsInstance(topics, list, "Topics should be a list")
            
            print(f"✅ Ranked {len(topics)} topics")
            if topics:
                for i, topic in enumerate(topics[:3], 1):
                    print(f"   {i}. {topic['symbol']} - {topic['topic_type']} (score: {topic['score']:.1f})")
            
        except Exception as e:
            self.fail(f"Failed to rank topics: {e}")
    
    def test_get_top_topics(self):
        """Test getting top topics from database"""
        print("\n📊 Testing get top topics...")
        
        try:
            topics = self.topic_ranker.get_top_topics(
                user_id=self.test_user_id,
                limit=5
            )
            
            self.assertIsInstance(topics, list, "Topics should be a list")
            
            print(f"✅ Retrieved {len(topics)} topics from database")
            
        except Exception as e:
            self.fail(f"Failed to get top topics: {e}")
    
    # ==================== Context Building Tests ====================
    
    def test_build_context(self):
        """Test building context for a topic"""
        print("\n📊 Testing context building...")
        
        try:
            # First, create a topic
            topic_id = f"AAPL_GOLDEN_CROSS_{int(datetime.now().timestamp())}"
            query = """
                INSERT OR REPLACE INTO blog_topics
                (topic_id, user_id, symbol, topic_type, reason, urgency, audience, confidence, score)
                VALUES (:topic_id, :user_id, :symbol, :topic_type, :reason, :urgency, :audience, :confidence, :score)
            """
            db.execute_update(query, {
                "topic_id": topic_id,
                "user_id": self.test_user_id,
                "symbol": "AAPL",
                "topic_type": "golden_cross",
                "reason": json.dumps(["price_above_200MA"]),
                "urgency": "high",
                "audience": "basic_to_pro",
                "confidence": 0.90,
                "score": 85.0
            })
            
            # Build context
            context = self.context_builder.build_context(topic_id, self.test_user_id)
            
            # Verify structure
            self.assertIn("system_role", context, "Should have system_role")
            self.assertIn("topic", context, "Should have topic")
            self.assertIn("signal_summary", context, "Should have signal_summary")
            self.assertIn("technical_context", context, "Should have technical_context")
            self.assertIn("risk_context", context, "Should have risk_context")
            self.assertIn("allowed_assumptions", context, "Should have allowed_assumptions")
            
            # Verify topic context
            self.assertEqual(context['topic']['symbol'], "AAPL", "Topic symbol should match")
            self.assertEqual(context['topic']['topic_type'], "golden_cross", "Topic type should match")
            
            print(f"✅ Built context for topic {topic_id}")
            print(f"   Symbol: {context['topic']['symbol']}")
            print(f"   Signal: {context['signal_summary'].get('signal', 'N/A')}")
            print(f"   Trend: {context['signal_summary'].get('trend', 'N/A')}")
            
        except Exception as e:
            self.fail(f"Failed to build context: {e}")
    
    # ==================== Blog Generation Tests ====================
    
    def test_generate_blog_with_audit(self):
        """Test generating blog and verify audit table is populated"""
        print("\n📊 Testing blog generation with audit...")
        
        try:
            # Ensure we have data for AAPL
            if not self._ensure_data_for_symbol("AAPL"):
                print("⚠️  Skipping - no data for AAPL")
                return
            
            # Create a topic
            topic_id = f"AAPL_BLOG_TEST_{int(datetime.now().timestamp())}"
            query = """
                INSERT OR REPLACE INTO blog_topics
                (topic_id, user_id, symbol, topic_type, reason, urgency, audience, confidence, score)
                VALUES (:topic_id, :user_id, :symbol, :topic_type, :reason, :urgency, :audience, :confidence, :score)
            """
            db.execute_update(query, {
                "topic_id": topic_id,
                "user_id": self.test_user_id,
                "symbol": "AAPL",
                "topic_type": "signal_change",
                "reason": json.dumps(["signal_changed_HOLD_to_BUY"]),
                "urgency": "high",
                "audience": "basic_to_pro",
                "confidence": 0.85,
                "score": 80.0
            })
            
            # Generate blog
            result = self.blog_generator.generate_blog(
                topic_id=topic_id,
                user_id=self.test_user_id,
                llm_provider="openai",
                llm_model="gpt-4"
            )
            
            # Verify result
            self.assertIn("audit_id", result, "Should have audit_id")
            self.assertIn("draft_id", result, "Should have draft_id")
            self.assertIn("topic_id", result, "Should have topic_id")
            
            audit_id = result['audit_id']
            draft_id = result['draft_id']
            
            print(f"✅ Generated blog (audit: {audit_id}, draft: {draft_id})")
            
            # Verify audit table is populated
            audit_record = self.audit_service.get_audit_record(audit_id)
            self.assertIsNotNone(audit_record, "Audit record should exist")
            
            # Verify audit fields
            self.assertEqual(audit_record['topic_id'], topic_id, "Topic ID should match")
            self.assertEqual(audit_record['user_id'], self.test_user_id, "User ID should match")
            self.assertIsNotNone(audit_record['generation_request'], "Should have generation_request")
            self.assertIsNotNone(audit_record['context_data'], "Should have context_data")
            self.assertIsNotNone(audit_record['system_prompt'], "Should have system_prompt")
            self.assertIsNotNone(audit_record['user_prompt'], "Should have user_prompt")
            self.assertEqual(audit_record['llm_provider'], "openai", "LLM provider should match")
            self.assertEqual(audit_record['llm_model'], "gpt-4", "LLM model should match")
            self.assertIsNotNone(audit_record['status'], "Should have status")
            self.assertIsNotNone(audit_record['stage'], "Should have stage")
            
            print(f"✅ Audit record verified:")
            print(f"   Status: {audit_record['status']}")
            print(f"   Stage: {audit_record['stage']}")
            print(f"   LLM Provider: {audit_record['llm_provider']}")
            print(f"   LLM Model: {audit_record['llm_model']}")
            
            # Verify generation_request JSON
            generation_request = audit_record['generation_request']
            self.assertIsInstance(generation_request, dict, "generation_request should be dict")
            self.assertEqual(generation_request['topic_id'], topic_id, "Topic ID in request should match")
            self.assertEqual(generation_request['user_id'], self.test_user_id, "User ID in request should match")
            
            # Verify context_data JSON
            context_data = audit_record['context_data']
            self.assertIsInstance(context_data, dict, "context_data should be dict")
            self.assertIn("topic", context_data, "Context should have topic")
            self.assertIn("signal_summary", context_data, "Context should have signal_summary")
            
            # Verify prompts
            self.assertIsNotNone(audit_record['system_prompt'], "Should have system_prompt")
            self.assertGreater(len(audit_record['system_prompt']), 100, "System prompt should be substantial")
            self.assertIsNotNone(audit_record['user_prompt'], "Should have user_prompt")
            self.assertGreater(len(audit_record['user_prompt']), 50, "User prompt should be substantial")
            
            print(f"✅ All audit fields verified")
            
        except Exception as e:
            self.fail(f"Failed to generate blog with audit: {e}")
    
    def test_audit_table_completeness(self):
        """Test that audit table has all required fields populated"""
        print("\n📊 Testing audit table completeness...")
        
        try:
            # Generate a blog
            if not self._ensure_data_for_symbol("GOOGL"):
                print("⚠️  Skipping - no data for GOOGL")
                return
            
            topic_id = f"GOOGL_AUDIT_TEST_{int(datetime.now().timestamp())}"
            query = """
                INSERT OR REPLACE INTO blog_topics
                (topic_id, user_id, symbol, topic_type, reason, urgency, audience, confidence, score)
                VALUES (:topic_id, :user_id, :symbol, :topic_type, :reason, :urgency, :audience, :confidence, :score)
            """
            db.execute_update(query, {
                "topic_id": topic_id,
                "user_id": self.test_user_id,
                "symbol": "GOOGL",
                "topic_type": "golden_cross",
                "reason": json.dumps(["price_above_200MA", "volume_spike"]),
                "urgency": "high",
                "audience": "basic_to_pro",
                "confidence": 0.90,
                "score": 87.5
            })
            
            result = self.blog_generator.generate_blog(
                topic_id=topic_id,
                user_id=self.test_user_id
            )
            
            audit_id = result['audit_id']
            
            # Query audit table directly
            query = """
                SELECT * FROM blog_generation_audit
                WHERE audit_id = :audit_id
            """
            audit_result = db.execute_query(query, {"audit_id": audit_id})
            
            self.assertGreater(len(audit_result), 0, "Should have audit record")
            audit = audit_result[0]
            
            # Verify all critical fields
            required_fields = [
                'audit_id', 'user_id', 'topic_id', 'generation_request',
                'context_data', 'system_prompt', 'user_prompt',
                'agent_type', 'agent_config', 'llm_provider', 'llm_model',
                'status', 'stage', 'started_at', 'created_at'
            ]
            
            missing_fields = []
            for field in required_fields:
                if audit.get(field) is None:
                    missing_fields.append(field)
            
            self.assertEqual(len(missing_fields), 0, 
                          f"Missing required fields: {missing_fields}")
            
            # Verify JSON fields are valid JSON
            json_fields = ['generation_request', 'context_data', 'agent_config']
            for field in json_fields:
                if audit.get(field):
                    try:
                        json.loads(audit[field])
                    except json.JSONDecodeError:
                        self.fail(f"Field {field} is not valid JSON")
            
            print(f"✅ All required fields present in audit table")
            print(f"   Fields checked: {len(required_fields)}")
            print(f"   JSON fields validated: {len(json_fields)}")
            
        except Exception as e:
            self.fail(f"Failed to verify audit table completeness: {e}")
    
    def test_audit_stage_progression(self):
        """Test that audit stages progress correctly"""
        print("\n📊 Testing audit stage progression...")
        
        try:
            if not self._ensure_data_for_symbol("NVDA"):
                print("⚠️  Skipping - no data for NVDA")
                return
            
            topic_id = f"NVDA_STAGE_TEST_{int(datetime.now().timestamp())}"
            query = """
                INSERT OR REPLACE INTO blog_topics
                (topic_id, user_id, symbol, topic_type, reason, urgency, audience, confidence, score)
                VALUES (:topic_id, :user_id, :symbol, :topic_type, :reason, :urgency, :audience, :confidence, :score)
            """
            db.execute_update(query, {
                "topic_id": topic_id,
                "user_id": self.test_user_id,
                "symbol": "NVDA",
                "topic_type": "rsi_extreme",
                "reason": json.dumps(["rsi_overbought"]),
                "urgency": "medium",
                "audience": "pro",
                "confidence": 0.75,
                "score": 65.0
            })
            
            result = self.blog_generator.generate_blog(
                topic_id=topic_id,
                user_id=self.test_user_id
            )
            
            audit_id = result['audit_id']
            audit = self.audit_service.get_audit_record(audit_id)
            
            # Verify final stage
            self.assertIn(audit['stage'], ['draft_created', 'content_generated'], 
                         f"Final stage should be draft_created or content_generated, got {audit['stage']}")
            self.assertIn(audit['status'], ['success', 'in_progress'],
                         f"Final status should be success or in_progress, got {audit['status']}")
            
            # Verify stages were recorded
            # The final stage should be 'draft_created' or 'content_generated'
            # which means it progressed through 'context_built'
            final_stage = audit['stage']
            self.assertIn(final_stage, ['draft_created', 'content_generated', 'context_built', 'agent_invoked'],
                         f"Final stage should be one of the expected stages, got {final_stage}")
            
            # Verify it progressed through context_built (either current stage or already passed)
            # If stage is draft_created, it means it went through context_built
            stages_progressed = ['topic_ranked', 'context_built', 'agent_invoked', 'content_generated', 'draft_created']
            stage_index = stages_progressed.index(final_stage) if final_stage in stages_progressed else -1
            context_built_index = stages_progressed.index('context_built')
            self.assertGreaterEqual(stage_index, context_built_index,
                         f"Should have reached context_built stage (current: {final_stage})")
            
            print(f"✅ Audit stage progression verified")
            print(f"   Final stage: {audit['stage']}")
            print(f"   Final status: {audit['status']}")
            
        except Exception as e:
            self.fail(f"Failed to verify audit stage progression: {e}")
    
    def test_get_audit_for_agent(self):
        """Test getting audit data formatted for agent"""
        print("\n📊 Testing get audit for agent...")
        
        try:
            if not self._ensure_data_for_symbol("AAPL"):
                print("⚠️  Skipping - no data for AAPL")
                return
            
            # Generate a blog first
            topic_id = f"AAPL_AGENT_TEST_{int(datetime.now().timestamp())}"
            query = """
                INSERT OR REPLACE INTO blog_topics
                (topic_id, user_id, symbol, topic_type, reason, urgency, audience, confidence, score)
                VALUES (:topic_id, :user_id, :symbol, :topic_type, :reason, :urgency, :audience, :confidence, :score)
            """
            db.execute_update(query, {
                "topic_id": topic_id,
                "user_id": self.test_user_id,
                "symbol": "AAPL",
                "topic_type": "signal_change",
                "reason": json.dumps(["signal_changed"]),
                "urgency": "high",
                "audience": "basic_to_pro",
                "confidence": 0.85,
                "score": 80.0
            })
            
            result = self.blog_generator.generate_blog(
                topic_id=topic_id,
                user_id=self.test_user_id
            )
            
            audit_id = result['audit_id']
            
            # Get audit data for agent
            audit_data = self.audit_service.get_audit_for_agent(audit_id)
            
            # Verify structure
            self.assertIn("audit_id", audit_data, "Should have audit_id")
            self.assertIn("context_data", audit_data, "Should have context_data")
            self.assertIn("generation_request", audit_data, "Should have generation_request")
            self.assertIn("system_prompt", audit_data, "Should have system_prompt")
            self.assertIn("user_prompt", audit_data, "Should have user_prompt")
            self.assertIn("agent_config", audit_data, "Should have agent_config")
            self.assertIn("llm_provider", audit_data, "Should have llm_provider")
            self.assertIn("llm_model", audit_data, "Should have llm_model")
            
            # Verify agent can use this data
            self.assertIsInstance(audit_data['context_data'], dict, "Context should be dict")
            self.assertIsInstance(audit_data['agent_config'], dict, "Agent config should be dict")
            self.assertIsNotNone(audit_data['system_prompt'], "Should have system prompt")
            self.assertIsNotNone(audit_data['user_prompt'], "Should have user prompt")
            
            print(f"✅ Audit data for agent verified")
            print(f"   Has context_data: {bool(audit_data['context_data'])}")
            print(f"   Has prompts: {bool(audit_data['system_prompt'] and audit_data['user_prompt'])}")
            print(f"   LLM Provider: {audit_data['llm_provider']}")
            print(f"   LLM Model: {audit_data['llm_model']}")
            
        except Exception as e:
            self.fail(f"Failed to get audit for agent: {e}")
    
    def test_retry_audit_creation(self):
        """Test creating retry audit from failed audit"""
        print("\n📊 Testing retry audit creation...")
        
        try:
            if not self._ensure_data_for_symbol("GOOGL"):
                print("⚠️  Skipping - no data for GOOGL")
                return
            
            # Create a topic and generate blog
            topic_id = f"GOOGL_RETRY_TEST_{int(datetime.now().timestamp())}"
            query = """
                INSERT OR REPLACE INTO blog_topics
                (topic_id, user_id, symbol, topic_type, reason, urgency, audience, confidence, score)
                VALUES (:topic_id, :user_id, :symbol, :topic_type, :reason, :urgency, :audience, :confidence, :score)
            """
            db.execute_update(query, {
                "topic_id": topic_id,
                "user_id": self.test_user_id,
                "symbol": "GOOGL",
                "topic_type": "golden_cross",
                "reason": json.dumps(["price_above_200MA"]),
                "urgency": "high",
                "audience": "basic_to_pro",
                "confidence": 0.90,
                "score": 85.0
            })
            
            result = self.blog_generator.generate_blog(
                topic_id=topic_id,
                user_id=self.test_user_id,
                llm_provider="openai"
            )
            
            original_audit_id = result['audit_id']
            
            # Create retry audit with different LLM
            new_audit_id = self.audit_service.create_retry_audit(
                original_audit_id,
                new_llm_provider="anthropic",
                new_llm_model="claude-3-opus"
            )
            
            # Verify retry audit
            retry_audit = self.audit_service.get_audit_record(new_audit_id)
            self.assertIsNotNone(retry_audit, "Retry audit should exist")
            self.assertEqual(retry_audit['parent_audit_id'], original_audit_id, 
                           "Parent audit ID should match")
            self.assertEqual(retry_audit['llm_provider'], "anthropic", 
                           "Should use new LLM provider")
            self.assertEqual(retry_audit['llm_model'], "claude-3-opus", 
                           "Should use new LLM model")
            
            # Verify context is preserved
            self.assertIsNotNone(retry_audit['context_data'], "Should have context_data")
            self.assertIsNotNone(retry_audit['generation_request'], "Should have generation_request")
            
            print(f"✅ Retry audit created")
            print(f"   Original audit: {original_audit_id}")
            print(f"   Retry audit: {new_audit_id}")
            print(f"   New LLM Provider: {retry_audit['llm_provider']}")
            print(f"   New LLM Model: {retry_audit['llm_model']}")
            
        except Exception as e:
            self.fail(f"Failed to create retry audit: {e}")
    
    # ==================== Integration Tests ====================
    
    def test_full_blog_generation_workflow(self):
        """Test full workflow: topic ranking → context building → blog generation → audit"""
        print("\n🔄 Testing full blog generation workflow...")
        
        try:
            # Create test portfolio
            portfolio_id = self._create_test_portfolio()
            
            # Step 1: Rank topics
            topics = self.topic_ranker.rank_topics_for_user(
                self.test_user_id,
                limit=3,
                min_score=30.0
            )
            
            if not topics:
                print("⚠️  No topics ranked, skipping workflow test")
                return
            
            # Step 2: Build context for first topic
            topic_id = topics[0]['topic_id']
            context = self.context_builder.build_context(topic_id, self.test_user_id)
            self.assertIsNotNone(context, "Context should be built")
            
            # Step 3: Generate blog
            result = self.blog_generator.generate_blog(
                topic_id=topic_id,
                user_id=self.test_user_id
            )
            
            self.assertIn("audit_id", result, "Should have audit_id")
            self.assertIn("draft_id", result, "Should have draft_id")
            
            # Step 4: Verify audit
            audit = self.audit_service.get_audit_record(result['audit_id'])
            self.assertIsNotNone(audit, "Audit should exist")
            self.assertIsNotNone(audit['context_data'], "Should have context_data")
            self.assertIsNotNone(audit['system_prompt'], "Should have system_prompt")
            
            print("✅ Full workflow successful")
            print(f"   Topic: {topics[0]['symbol']} - {topics[0]['topic_type']}")
            print(f"   Audit ID: {result['audit_id']}")
            print(f"   Draft ID: {result['draft_id']}")
            
        except Exception as e:
            self.fail(f"Failed full workflow: {e}")


if __name__ == '__main__':
    unittest.main(verbosity=2)

