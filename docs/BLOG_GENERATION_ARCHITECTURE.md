# Blog Generation Architecture

## Overview

Agentic blog generation system for Elite users and admins, following existing architecture patterns (DRY, SOLID, pluggable, scalable).

## Architecture Design

### ✅ Key Principles

1. **Deterministic Topic Ranking** - System decides what's important, not LLM
2. **Structured Context** - Rich, unambiguous context for LLM
3. **Pluggable LLM** - Support for OpenAI, Anthropic, LangGraph, n8n
4. **Pluggable Publishing** - WordPress, Medium, Ghost, custom API, etc.
5. **Tiered Access** - Elite users and admins only
6. **Event-Driven** - Triggers via events (signal changes, earnings, etc.)

### System Flow

```
User Data (Watchlists + Portfolios)
        ↓
Signal Engine (Existing)
        ↓
BlogTopicRanker (NEW - Deterministic)
        ↓
BlogContextBuilder (NEW - Structured)
        ↓
BlogAgent (Uses Existing Agent System)
        ↓
BlogPublisherPlugin (NEW - Pluggable)
        ↓
Published Blog
```

## Components

### 1. BlogTopicRanker Service

**Purpose**: Deterministic topic scoring (system decides, not LLM)

**Location**: `python-worker/app/services/blog_topic_ranker.py`

**Responsibilities**:

- Score topics based on signals, trends, volume, earnings
- Return top 5 topics with structured schema
- No LLM involvement in ranking

**Scoring Formula**:

```python
TopicScore = (
    TrendStrength * 0.35 +
    SignalChange * 0.25 +
    VolumeSpike * 0.20 +
    EarningsOrNews * 0.10 +
    UserExposureWeight * 0.10
)
```

**Output Schema**:

```python
{
    "topic_id": "NVDA_GOLDEN_CROSS",
    "symbol": "NVDA",
    "reason": ["price_above_200MA", "volume_spike"],
    "urgency": "high",
    "audience": "basic_to_pro",
    "confidence": 0.91,
    "score": 87.5
}
```

### 2. BlogContextBuilder Service

**Purpose**: Build structured, unambiguous context for LLM

**Location**: `python-worker/app/services/blog_context_builder.py`

**Responsibilities**:

- Aggregate data from signals, indicators, fundamentals
- Structure context in deterministic format
- No raw indicators, no opinions, no guessing

**Context Schema**:

```python
{
    "system_role": "financial_content_explainer",
    "domain": "stocks",
    "topic": {
        "symbol": "NVDA",
        "title_hint": "Golden Cross Buy Signal",
        "urgency": "high"
    },
    "signal_summary": {
        "trend": "BULLISH",
        "signal": "BUY",
        "confidence": 0.91
    },
    "technical_context": {
        "price_vs_200ma": "+12%",
        "ema_cross": "EMA9 crossed above EMA21",
        "macd": "positive and rising",
        "rsi": 61,
        "volume": "above average"
    },
    "risk_context": {
        "overextension": "moderate",
        "earnings_days_away": 9,
        "market_risk": "neutral"
    },
    "user_relevance": {
        "watchlisted": true,
        "portfolio_exposure_pct": 18
    },
    "allowed_assumptions": [
        "Explain in simple terms",
        "Avoid technical jargon",
        "Do not give financial advice"
    ]
}
```

### 3. BlogGenerator Service

**Purpose**: Orchestrate blog generation workflow

**Location**: `python-worker/app/services/blog_generator.py`

**Responsibilities**:

- Coordinate topic ranking, context building, LLM generation
- Manage blog lifecycle (draft, review, publish)
- Integrate with existing services (signals, indicators, portfolios)

**Dependencies**:

- `BlogTopicRanker`
- `BlogContextBuilder`
- `BlogAgent` (via AgentManager)
- `BlogPublisherPlugin` (via PluginRegistry)

### 4. BlogAgent

**Purpose**: LLM integration for blog generation

**Location**: `python-worker/app/agents/blog_agent.py`

**Implementation**:

- Extends `BaseAgent`
- Can use LangGraph, n8n, or direct LLM (OpenAI, Anthropic)
- Implements `AgentCapability.BLOG_GENERATION`

**System Prompt** (Locked):

```
You are a financial market explainer AI.

Your task is to generate clear, factual, and useful blog content
based ONLY on the structured context provided.

RULES:
- Do NOT invent data
- Do NOT add indicators not provided
- Do NOT give financial advice
- Explain concepts in plain English
- Focus on "why it matters" for investors
- Highlight risks clearly
- Keep tone neutral and educational

STYLE:
- Simple for beginners
- Insightful for experienced readers
- No hype, no predictions

OUTPUT STRUCTURE:
1. What happened
2. Why it matters
3. Signal explanation (in plain English)
4. Risks to watch
5. What investors should monitor next

SEO REQUIREMENTS:
- Include stock symbol naturally
- Use phrases like "buy or sell", "stock trend"
- 800–1200 words
- Headings and bullet points

You are explaining signals, not recommending trades.
```

### 5. BlogPublisherPlugin

**Purpose**: Pluggable blog publishing destinations

**Location**: `python-worker/app/plugins/blog_publisher_plugin.py`

**Base Class**: `Plugin` with `PluginType.WORKFLOW`

**Supported Destinations**:

- WordPress (REST API)
- Medium (API)
- Ghost (Admin API)
- Custom API (webhook)
- Internal blog (save to DB)
- n8n workflow (trigger webhook)

**Interface**:

```python
class BlogPublisherPlugin(Plugin):
    def publish(self, blog: Dict[str, Any]) -> Dict[str, Any]:
        """Publish blog to destination"""
        pass

    def get_supported_destinations(self) -> List[str]:
        """List supported publishing destinations"""
        pass
```

### 6. Database Schema

**Migration**: `008_add_blog_generation.sql`

**Tables**:

- `blog_topics` - Ranked topics for blog generation
- `blog_drafts` - Generated blog drafts
- `blog_published` - Published blogs with metadata
- `blog_publishing_config` - User publishing preferences

### 7. API Endpoints

**Elite Only** (subscription check required):

- `POST /api/v1/blog/generate` - Generate blog for topic
- `GET /api/v1/blog/topics` - Get top ranked topics
- `GET /api/v1/blog/drafts` - List blog drafts
- `POST /api/v1/blog/{draft_id}/publish` - Publish blog
- `GET /api/v1/blog/published` - List published blogs
- `POST /api/v1/blog/auto-generate` - Auto-generate top topics

### 8. Event Integration

**New Event Types**:

- `BLOG_TOPIC_RANKED` - When topics are ranked
- `BLOG_GENERATED` - When blog is generated
- `BLOG_PUBLISHED` - When blog is published

**Event Subscribers**:

- Auto-generate blogs on signal changes (Elite users)
- Notify admins of high-urgency topics
- Trigger publishing workflows

## Implementation Plan

### Phase 1: Core Services

1. ✅ `BlogTopicRanker` - Deterministic topic scoring
2. ✅ `BlogContextBuilder` - Structured context building
3. ✅ `BlogGenerator` - Orchestration service

### Phase 2: Agent Integration

4. ✅ `BlogAgent` - LLM agent for blog generation
5. ✅ Integration with `AgentManager`
6. ✅ Support for LangGraph/n8n workflows

### Phase 3: Publishing

7. ✅ `BlogPublisherPlugin` - Base plugin
8. ✅ WordPress publisher
9. ✅ Medium publisher
10. ✅ Custom API publisher
11. ✅ Internal blog publisher

### Phase 4: API & Events

12. ✅ Database schema
13. ✅ API endpoints (Elite only)
14. ✅ Event integration
15. ✅ Batch worker integration

## Benefits of This Architecture

### ✅ Pluggable

- New LLM providers: Add new `BlogAgent` implementation
- New publishers: Add new `BlogPublisherPlugin`
- New topic triggers: Extend `BlogTopicRanker`

### ✅ Scalable

- Event-driven: Can scale with message queue
- Caching: Topic scores cached, context cached
- Async: Blog generation can be async

### ✅ DRY

- Reuses existing services (signals, indicators, portfolios)
- Shared context building logic
- Common publishing interface

### ✅ SOLID

- Single Responsibility: Each service has one job
- Open/Closed: Extend via plugins
- Liskov Substitution: All publishers implement same interface
- Interface Segregation: Clear plugin interfaces
- Dependency Injection: Services injected via DI container

### ✅ Tiered Access

- Subscription check in API endpoints
- Elite-only features clearly marked
- Admin override capability

## Usage Examples

### Generate Blog for Top Topic

```python
# Get top topics
topics = blog_topic_ranker.get_top_topics(user_id, limit=5)

# Generate blog for first topic
blog = blog_generator.generate_blog(
    topic_id=topics[0]['topic_id'],
    user_id=user_id
)

# Publish to WordPress
publisher = plugin_registry.get_plugin('wordpress_publisher')
result = publisher.publish(blog)
```

### Auto-Generate on Signal Change

```python
# Event subscriber
@event_manager.subscribe(EventType.SIGNAL_GENERATED)
def on_signal_generated(event: TradingEvent):
    if event.data['user_subscription'] == 'elite':
        # Rank topics
        topics = blog_topic_ranker.rank_topics_for_user(event.data['user_id'])

        # Generate blog for top topic
        if topics:
            blog_generator.generate_blog_async(
                topic_id=topics[0]['topic_id'],
                user_id=event.data['user_id']
            )
```

### LangGraph Workflow Integration

```python
# BlogAgent can use LangGraph flow
blog_agent = LangGraphBlogAgent(
    flow_id="blog_generation_flow",
    config={
        "system_prompt": BLOG_SYSTEM_PROMPT,
        "context_builder": blog_context_builder
    }
)

# Generate blog
result = blog_agent.execute(
    task="generate_blog",
    context=context_data
)
```

## Summary

✅ **Deterministic Topic Ranking** - System decides, not LLM
✅ **Structured Context** - Rich, unambiguous context
✅ **Pluggable LLM** - LangGraph, n8n, direct LLM
✅ **Pluggable Publishing** - WordPress, Medium, Ghost, custom
✅ **Tiered Access** - Elite only
✅ **Event-Driven** - Auto-generate on triggers
✅ **DRY, SOLID** - Follows existing patterns
✅ **Scalable** - Event-driven, async, cached

This architecture leverages existing systems while adding powerful, pluggable blog generation capabilities.
