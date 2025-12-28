-- Blog Generation System
-- Industry Standard: Content management with publishing workflow
-- Supports: Topic ranking, blog drafts, publishing, multi-destination

-- Blog Topics (ranked topics for blog generation)
CREATE TABLE IF NOT EXISTS blog_topics (
    topic_id TEXT PRIMARY KEY,
    user_id TEXT,
    symbol TEXT NOT NULL,
    topic_type TEXT NOT NULL CHECK(topic_type IN ('signal_change', 'golden_cross', 'rsi_extreme', 'earnings_proximity', 'portfolio_heavy', 'volume_spike', 'trend_reversal')),
    reason JSON NOT NULL, -- Array of reasons: ["price_above_200MA", "volume_spike"]
    urgency TEXT CHECK(urgency IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',
    audience TEXT CHECK(audience IN ('basic', 'pro', 'elite', 'basic_to_pro', 'all')) DEFAULT 'basic_to_pro',
    confidence REAL DEFAULT 0.5, -- 0.0 to 1.0
    score REAL DEFAULT 0.0, -- Calculated topic score
    context_data JSON, -- Pre-built context for LLM
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP, -- Topic expires after certain time
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Blog Drafts (generated blogs before publishing)
CREATE TABLE IF NOT EXISTS blog_drafts (
    draft_id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    title TEXT NOT NULL,
    meta_description TEXT,
    slug TEXT UNIQUE,
    content TEXT NOT NULL, -- Full blog content (HTML or Markdown)
    tags JSON, -- Array of tags
    status TEXT CHECK(status IN ('draft', 'review', 'approved', 'rejected')) DEFAULT 'draft',
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by TEXT, -- Admin user_id
    review_notes TEXT,
    context_used JSON, -- Context data used for generation
    llm_metadata JSON, -- LLM provider, model, tokens used, etc.
    FOREIGN KEY (topic_id) REFERENCES blog_topics(topic_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Published Blogs (blogs that have been published)
CREATE TABLE IF NOT EXISTS blog_published (
    published_id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    meta_description TEXT,
    tags JSON,
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_to JSON NOT NULL, -- Array of destinations: [{"type": "wordpress", "url": "...", "post_id": "..."}]
    seo_data JSON, -- SEO metadata
    view_count INTEGER DEFAULT 0,
    engagement_score REAL DEFAULT 0.0, -- Calculated from views, shares, etc.
    FOREIGN KEY (draft_id) REFERENCES blog_drafts(draft_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Blog Publishing Configuration (user preferences for publishing)
CREATE TABLE IF NOT EXISTS blog_publishing_config (
    config_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    auto_generate BOOLEAN DEFAULT false, -- Auto-generate blogs on signal changes
    auto_publish BOOLEAN DEFAULT false, -- Auto-publish approved blogs
    min_topic_score REAL DEFAULT 70.0, -- Minimum score to generate blog
    publishing_destinations JSON, -- Array of enabled destinations: [{"type": "wordpress", "enabled": true, "config": {...}}]
    content_preferences JSON, -- Tone, length, audience level, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Blog Generation Audit (Comprehensive audit trail for blog generation)
-- Industry Standard: Event Sourcing + Audit Log Pattern
-- Purpose: Full audit trail, retry/recovery, LLM provider switching, compliance
CREATE TABLE IF NOT EXISTS blog_generation_audit (
    audit_id TEXT PRIMARY KEY,
    user_id TEXT,
    topic_id TEXT,
    draft_id TEXT,
    
    -- Generation Request (Input to Agent)
    generation_request JSON NOT NULL, -- Complete request: topic, context, user preferences, etc.
    context_data JSON NOT NULL, -- Full context built for LLM (structured context)
    system_prompt TEXT, -- System prompt used
    user_prompt TEXT, -- User prompt/instruction
    prompt_template TEXT, -- Template used (for reproducibility)
    
    -- Agent Configuration
    agent_type TEXT, -- 'openai', 'anthropic', 'langgraph', 'n8n', etc.
    agent_config JSON, -- Agent-specific configuration
    llm_provider TEXT, -- 'openai', 'anthropic', 'langgraph', etc.
    llm_model TEXT, -- Model used (e.g., 'gpt-4', 'claude-3-opus')
    llm_parameters JSON, -- Temperature, max_tokens, etc.
    
    -- Generation Result (Output from Agent)
    generation_result JSON, -- Full response from agent
    generated_content TEXT, -- The actual blog content generated
    generation_metadata JSON, -- Tokens used, latency, cost, etc.
    
    -- Status & Lifecycle
    status TEXT NOT NULL CHECK(status IN ('pending', 'in_progress', 'success', 'failed', 'retrying', 'cancelled')) DEFAULT 'pending',
    stage TEXT NOT NULL CHECK(stage IN ('topic_ranked', 'context_built', 'agent_invoked', 'content_generated', 'content_validated', 'draft_created', 'published', 'failed')) DEFAULT 'topic_ranked',
    
    -- Error Handling
    error_message TEXT,
    error_details JSON, -- Stack trace, error codes, etc.
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    last_retry_at TIMESTAMP,
    
    -- Retry/Recovery
    can_retry BOOLEAN DEFAULT true,
    retry_with_llm TEXT, -- Different LLM to try on retry
    recovery_data JSON, -- Data needed for recovery
    
    -- Timestamps
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Correlation
    correlation_id TEXT, -- For tracing across services
    parent_audit_id TEXT, -- For retry chains (links to previous attempt)
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (topic_id) REFERENCES blog_topics(topic_id) ON DELETE SET NULL,
    FOREIGN KEY (draft_id) REFERENCES blog_drafts(draft_id) ON DELETE SET NULL,
    FOREIGN KEY (parent_audit_id) REFERENCES blog_generation_audit(audit_id) ON DELETE SET NULL
);

-- Blog Generation Log (Simplified log for quick queries)
-- This is a denormalized view for performance, audit table is source of truth
CREATE TABLE IF NOT EXISTS blog_generation_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id TEXT NOT NULL, -- Links to full audit record
    user_id TEXT,
    topic_id TEXT,
    draft_id TEXT,
    action TEXT NOT NULL CHECK(action IN ('topic_ranked', 'context_built', 'blog_generated', 'blog_published', 'blog_failed')),
    status TEXT CHECK(status IN ('success', 'failed', 'partial')) DEFAULT 'success',
    error_message TEXT,
    metadata JSON, -- Additional context
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (audit_id) REFERENCES blog_generation_audit(audit_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (topic_id) REFERENCES blog_topics(topic_id) ON DELETE SET NULL,
    FOREIGN KEY (draft_id) REFERENCES blog_drafts(draft_id) ON DELETE SET NULL
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_blog_topics_user ON blog_topics(user_id);
CREATE INDEX IF NOT EXISTS idx_blog_topics_symbol ON blog_topics(symbol);
CREATE INDEX IF NOT EXISTS idx_blog_topics_score ON blog_topics(score DESC);
CREATE INDEX IF NOT EXISTS idx_blog_topics_urgency ON blog_topics(urgency, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_blog_drafts_user ON blog_drafts(user_id);
CREATE INDEX IF NOT EXISTS idx_blog_drafts_topic ON blog_drafts(topic_id);
CREATE INDEX IF NOT EXISTS idx_blog_drafts_status ON blog_drafts(status, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_blog_published_user ON blog_published(user_id);
CREATE INDEX IF NOT EXISTS idx_blog_published_symbol ON blog_published(symbol);
CREATE INDEX IF NOT EXISTS idx_blog_published_date ON blog_published(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_blog_publishing_config_user ON blog_publishing_config(user_id);
-- Audit table indexes
CREATE INDEX IF NOT EXISTS idx_blog_generation_audit_user ON blog_generation_audit(user_id);
CREATE INDEX IF NOT EXISTS idx_blog_generation_audit_topic ON blog_generation_audit(topic_id);
CREATE INDEX IF NOT EXISTS idx_blog_generation_audit_draft ON blog_generation_audit(draft_id);
CREATE INDEX IF NOT EXISTS idx_blog_generation_audit_status ON blog_generation_audit(status, stage);
CREATE INDEX IF NOT EXISTS idx_blog_generation_audit_correlation ON blog_generation_audit(correlation_id);
CREATE INDEX IF NOT EXISTS idx_blog_generation_audit_parent ON blog_generation_audit(parent_audit_id);
CREATE INDEX IF NOT EXISTS idx_blog_generation_audit_retry ON blog_generation_audit(can_retry, status, retry_count);
CREATE INDEX IF NOT EXISTS idx_blog_generation_audit_created ON blog_generation_audit(created_at DESC);

-- Log table indexes
CREATE INDEX IF NOT EXISTS idx_blog_generation_log_audit ON blog_generation_log(audit_id);
CREATE INDEX IF NOT EXISTS idx_blog_generation_log_user ON blog_generation_log(user_id);
CREATE INDEX IF NOT EXISTS idx_blog_generation_log_topic ON blog_generation_log(topic_id);
CREATE INDEX IF NOT EXISTS idx_blog_generation_log_action ON blog_generation_log(action, created_at DESC);

